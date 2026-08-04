"""Veri seti birleştirme + sınıf eşleme.

İkinci turda kaçınılmaz olan iş: elinde farklı zamanlarda toplanmış birden çok
veri seti var ve sınıf id'leri birbirini tutmuyor. Bir sette `0=kamyon, 1=tır`,
ötekinde `0=tır, 1=dorse` olabilir; ikisini düpedüz üst üste kopyalamak
etiketleri sessizce bozar — model `kamyon` diye `tır` öğrenir.

Burada her kaynağın her sınıfı, hedef sette hangi sınıfa denk geleceği
tek tek seçilir. Aynı isimli sınıflar kendiliğinden eşlenir, kalanları
kullanıcı belirler; istenmeyen sınıf "(atla)" ile dışarıda bırakılabilir —
o sınıfın kutuları etiket dosyalarından düşer, kutusu kalmayan görsel de
istenirse hiç kopyalanmaz.

Dosya adı çakışması kaynak adıyla ön ek verilerek çözülür, yani iki settin de
`kare_00001.jpg`'i varsa ikisi de korunur.

Veri Denetçi'den açılır; tek başına da çalışır:
    python -m boxify.araclar.veri_birlestir
"""

import os
import shutil
import sys

from PyQt5.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QGroupBox, QMessageBox, QLineEdit, QComboBox,
    QProgressBar, QCheckBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

ATLA = "(atla — bu sınıfı alma)"


# ─────────────────────────────────────────────── yardımcılar

def gorselleri_bul(kok: str) -> list:
    bulunan = []
    for dizin, _alt, dosyalar in os.walk(kok):
        for ad in dosyalar:
            if ad.lower().endswith(IMG_EXTS):
                bulunan.append(os.path.join(dizin, ad))
    return sorted(bulunan)


def etiket_yolu(img: str, img_kok: str, lbl_kok: str) -> str:
    """Görselin karşılığı olan .txt yolu (klasör yapısı korunarak)."""
    bagil = os.path.relpath(img, img_kok)
    return os.path.join(lbl_kok, os.path.splitext(bagil)[0] + ".txt")


def sinif_adlari_oku(*klasorler) -> dict:
    """data.yaml ya da classes.txt içinden {id: ad}."""
    from .veri_denetci import load_class_names
    return load_class_names(*klasorler)


def etiket_klasoru_tahmin(img_dir: str) -> str:
    """'…/images' → '…/labels'; bulunamazsa görselin yanındaki klasör."""
    p = img_dir.rstrip(os.sep)
    if os.path.basename(p).lower() == "images":
        aday = os.path.join(os.path.dirname(p), "labels")
        if os.path.isdir(aday):
            return aday
    for aday in (os.path.join(p, "labels"), p):
        if os.path.isdir(aday):
            return aday
    return p


# ─────────────────────────────────────────────── işçi

class BirlestirIscisi(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._iptal = False

    def iptal(self):
        self._iptal = True

    def run(self):
        cfg = self.cfg
        out = cfg["out_dir"]
        img_out = os.path.join(out, "images")
        lbl_out = os.path.join(out, "labels")
        os.makedirs(img_out, exist_ok=True)
        os.makedirs(lbl_out, exist_ok=True)

        hedef_adlar = cfg["hedef_adlar"]                 # [ad, …] sıralı
        kopyala = cfg["mode"] == "copy"

        toplam = sum(len(k["gorseller"]) for k in cfg["kaynaklar"])
        yapilan = 0
        sayac = {"gorsel": 0, "kutu": 0, "atlanan_kutu": 0,
                 "bos_atlanan": 0, "etiketsiz": 0, "hata": 0}
        sinif_sayim = {ad: 0 for ad in hedef_adlar}
        kaynak_ozet = []

        for k in cfg["kaynaklar"]:
            if self._iptal:
                break
            ad_on = k["onek"]
            esleme = k["esleme"]          # {kaynak_id: hedef_id or None}
            k_gorsel = k_kutu = k_atlanan = k_bos = 0
            self.log.emit(f"── {k['ad']} ({len(k['gorseller'])} görsel) ──")

            for img in k["gorseller"]:
                if self._iptal:
                    break
                yapilan += 1
                if yapilan % 20 == 0:
                    self.progress.emit(yapilan, toplam)

                lbl = etiket_yolu(img, k["img_dir"], k["lbl_dir"])
                satirlar = []
                if os.path.exists(lbl):
                    try:
                        with open(lbl, "r", encoding="utf-8") as f:
                            ham = [ln.strip() for ln in f if ln.strip()]
                    except OSError as e:
                        self.log.emit(f"HATA — {os.path.basename(lbl)}: {e}")
                        sayac["hata"] += 1
                        continue
                    for ln in ham:
                        parca = ln.split()
                        try:
                            eski = int(float(parca[0]))
                        except (ValueError, IndexError):
                            sayac["hata"] += 1
                            continue
                        yeni = esleme.get(eski)
                        if yeni is None:
                            k_atlanan += 1
                            continue
                        satirlar.append(" ".join([str(yeni)] + parca[1:]))
                        sinif_sayim[hedef_adlar[yeni]] += 1
                        k_kutu += 1
                else:
                    sayac["etiketsiz"] += 1

                if not satirlar and cfg["bos_atla"]:
                    k_bos += 1
                    continue

                yeni_ad = f"{ad_on}_{os.path.basename(img)}" if ad_on else os.path.basename(img)
                hedef_img = os.path.join(img_out, yeni_ad)
                # aynı ad iki kez gelirse üzerine yazma; sıra numarası ekle
                sayi = 1
                kok, uzanti = os.path.splitext(hedef_img)
                while os.path.exists(hedef_img):
                    hedef_img = f"{kok}__{sayi}{uzanti}"
                    sayi += 1
                try:
                    if kopyala:
                        shutil.copy2(img, hedef_img)
                    else:
                        os.symlink(os.path.abspath(img), hedef_img)
                except OSError as e:
                    self.log.emit(f"HATA — {os.path.basename(img)}: {e}")
                    sayac["hata"] += 1
                    continue

                hedef_lbl = os.path.join(
                    lbl_out, os.path.splitext(os.path.basename(hedef_img))[0] + ".txt")
                try:
                    with open(hedef_lbl, "w", encoding="utf-8") as f:
                        f.write("\n".join(satirlar) + ("\n" if satirlar else ""))
                except OSError as e:
                    self.log.emit(f"HATA — {os.path.basename(hedef_lbl)}: {e}")
                    sayac["hata"] += 1
                    continue
                k_gorsel += 1

            sayac["gorsel"] += k_gorsel
            sayac["kutu"] += k_kutu
            sayac["atlanan_kutu"] += k_atlanan
            sayac["bos_atlanan"] += k_bos
            kaynak_ozet.append((k["ad"], k_gorsel, k_kutu, k_atlanan, k_bos))
            self.log.emit(f"   {k_gorsel} görsel, {k_kutu} kutu"
                          + (f", {k_atlanan} kutu atlandı" if k_atlanan else "")
                          + (f", {k_bos} boş görsel alınmadı" if k_bos else ""))

        self.progress.emit(toplam, toplam)

        # data.yaml + classes.txt
        yaml_yolu = os.path.join(out, "data.yaml")
        try:
            with open(yaml_yolu, "w", encoding="utf-8") as f:
                f.write(f"path: {os.path.abspath(out)}\n")
                f.write("train: images\n")
                f.write("val: images\n")
                f.write(f"nc: {len(hedef_adlar)}\n")
                f.write("names:\n")
                for i, ad in enumerate(hedef_adlar):
                    f.write(f"  {i}: {ad}\n")
            with open(os.path.join(out, "classes.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(hedef_adlar) + "\n")
        except OSError as e:
            self.log.emit(f"HATA — data.yaml yazılamadı: {e}")

        self.done.emit({
            "iptal": self._iptal, "out": out, "yaml": yaml_yolu,
            "sayac": sayac, "sinif_sayim": sinif_sayim,
            "kaynaklar": kaynak_ozet, "hedef_adlar": hedef_adlar,
        })


# ─────────────────────────────────────────────── diyalog

class BirlestirDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Veri Setlerini Birleştir — sınıf eşlemeli")
        self.resize(1080, 800)
        self.setMinimumSize(820, 560)
        self._kaynaklar = []        # [{ad, img_dir, lbl_dir, names, gorseller}]
        self._hedef_adlar = []
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        aciklama = QLabel(
            "Birden çok veri setini tek sete indirger. Sınıf id'leri setler arasında "
            "farklı olabilir; aşağıdaki tabloda her kaynağın her sınıfının hedefte neye "
            "denk geleceğini belirlersin. Aynı isimli sınıflar kendiliğinden eşlenir.")
        aciklama.setWordWrap(True)
        aciklama.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(aciklama)

        sp = QSplitter(Qt.Vertical)

        # ── kaynaklar
        g1 = QGroupBox("Kaynak veri setleri")
        v1 = QVBoxLayout(g1)
        self.kaynak_tablo = QTableWidget(0, 4)
        self.kaynak_tablo.setHorizontalHeaderLabels(
            ["Ad (dosya ön eki)", "Görsel klasörü", "Görsel", "Sınıf"])
        self.kaynak_tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Başlık kendi genişliğinden dar kalırsa kesiliyor ("Ad (dosya ön e…")
        self.kaynak_tablo.setColumnWidth(0, 150)
        self.kaynak_tablo.horizontalHeader().setMinimumSectionSize(64)
        self.kaynak_tablo.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kaynak_tablo.setEditTriggers(QAbstractItemView.DoubleClicked
                                          | QAbstractItemView.EditKeyPressed)
        self.kaynak_tablo.setMinimumHeight(120)
        v1.addWidget(self.kaynak_tablo)

        h1 = QHBoxLayout()
        b_ekle = QPushButton("+ Veri Seti Ekle…")
        b_ekle.setMinimumWidth(170)      # kalın yazı dar düğmede kırpılıyor
        b_ekle.clicked.connect(self._kaynak_ekle)
        h1.addWidget(b_ekle)
        b_sil = QPushButton("Seçileni Kaldır")
        b_sil.setMinimumWidth(140)
        b_sil.clicked.connect(self._kaynak_sil)
        h1.addWidget(b_sil)
        h1.addStretch()
        self.kaynak_bilgi = QLabel("Henüz veri seti eklenmedi")
        self.kaynak_bilgi.setStyleSheet("color:#6b7686; font-size:11px;")
        h1.addWidget(self.kaynak_bilgi)
        v1.addLayout(h1)
        sp.addWidget(g1)

        # ── sınıf eşleme
        g2 = QGroupBox("Sınıf eşleme")
        v2 = QVBoxLayout(g2)
        self.esleme_tablo = QTableWidget(0, 4)
        self.esleme_tablo.setHorizontalHeaderLabels(
            ["Kaynak", "Kaynak sınıfı", "id", "Hedef sınıfı"])
        self.esleme_tablo.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.esleme_tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.esleme_tablo.setMinimumHeight(240)
        v2.addWidget(self.esleme_tablo)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Hedef sınıflar (virgülle, sıra = id):"))
        self.hedef_edit = QLineEdit()
        self.hedef_edit.setPlaceholderText("kaynaklardan otomatik doldurulur")
        self.hedef_edit.editingFinished.connect(self._hedef_degisti)
        h2.addWidget(self.hedef_edit, 1)
        b_oto = QPushButton("Otomatik Eşle")
        b_oto.setToolTip("Aynı isimli sınıfları eşleştirir, kalanları hedefe ekler")
        b_oto.clicked.connect(self._otomatik_esle)
        h2.addWidget(b_oto)
        v2.addLayout(h2)
        sp.addWidget(g2)
        # Eşleme tablosu kaynak sayısı × sınıf sayısı kadar satır tutar, yani
        # kaynak listesinden hep uzundur; alanın büyük kısmı ona verilir.
        sp.setSizes([210, 430])
        sp.setStretchFactor(0, 0)
        sp.setStretchFactor(1, 1)
        v.addWidget(sp, 1)

        # ── çıktı
        g3 = QGroupBox("Çıktı")
        v3 = QVBoxLayout(g3)
        h3 = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("birleştirilmiş setin yazılacağı klasör")
        h3.addWidget(self.out_edit, 1)
        b_out = QPushButton("Seç…")
        b_out.setFixedWidth(60)
        b_out.clicked.connect(self._out_sec)
        h3.addWidget(b_out)
        v3.addLayout(h3)

        h4 = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Kopyala (güvenli)", "copy")
        self.mode_combo.addItem("Sembolik bağ (yer kaplamaz)", "symlink")
        self.mode_combo.setFixedWidth(220)
        h4.addWidget(QLabel("Görseller:"))
        h4.addWidget(self.mode_combo)
        self.bos_chk = QCheckBox("Kutusu kalmayan görselleri alma")
        self.bos_chk.setToolTip(
            "Sınıfları '(atla)' seçilince bazı görsellerde hiç kutu kalmaz.\n"
            "İşaretliyse bunlar hiç kopyalanmaz; kapalıysa arka plan örneği olarak kalır.")
        h4.addWidget(self.bos_chk)
        h4.addStretch()
        v3.addLayout(h4)
        v.addWidget(g3)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.log_box.setMaximumHeight(110)
        v.addWidget(self.log_box)

        h5 = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        h5.addWidget(self.progress, 1)
        self.start_btn = QPushButton("⇉  Birleştir")
        self.start_btn.setMinimumHeight(34)
        self.start_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:6px 14px;")
        self.start_btn.clicked.connect(self._start)
        h5.addWidget(self.start_btn)
        self.close_btn = QPushButton("Kapat")
        self.close_btn.clicked.connect(self.reject)
        h5.addWidget(self.close_btn)
        v.addLayout(h5)

    # ── kaynaklar
    def _log(self, t: str):
        self.log_box.append(t)

    def _kaynak_ekle(self):
        d = QFileDialog.getExistingDirectory(self, "Veri setinin görsel klasörü")
        if not d:
            return
        lbl = etiket_klasoru_tahmin(d)
        gorseller = gorselleri_bul(d)
        if not gorseller:
            QMessageBox.warning(self, "Boş klasör", "Bu klasörde görsel bulunamadı.")
            return
        names = sinif_adlari_oku(lbl, d)
        ad = os.path.basename(d.rstrip(os.sep)) or f"set{len(self._kaynaklar) + 1}"
        if ad.lower() == "images":
            ad = os.path.basename(os.path.dirname(d.rstrip(os.sep))) or ad
        self._kaynaklar.append({"ad": ad, "img_dir": d, "lbl_dir": lbl,
                                "names": names, "gorseller": gorseller})
        self._kaynak_tazele()
        self._otomatik_esle()

    def _kaynak_sil(self):
        row = self.kaynak_tablo.currentRow()
        if 0 <= row < len(self._kaynaklar):
            self._kaynaklar.pop(row)
            self._kaynak_tazele()
            self._otomatik_esle()

    def _kaynak_tazele(self):
        self.kaynak_tablo.setRowCount(len(self._kaynaklar))
        for i, k in enumerate(self._kaynaklar):
            ad_it = QTableWidgetItem(k["ad"])
            ad_it.setToolTip("Dosya adlarına bu ön ek eklenir (çakışma olmasın diye). "
                             "Çift tıklayıp değiştirebilirsin.")
            self.kaynak_tablo.setItem(i, 0, ad_it)
            for sutun, metin in ((1, k["img_dir"]),
                                 (2, str(len(k["gorseller"]))),
                                 (3, str(len(k["names"])) if k["names"] else "?")):
                it = QTableWidgetItem(metin)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if sutun == 3 and not k["names"]:
                    it.setToolTip("data.yaml/classes.txt bulunamadı — sınıflar "
                                  "etiket dosyalarındaki id'lerden çıkarılır")
                self.kaynak_tablo.setItem(i, sutun, it)
        toplam = sum(len(k["gorseller"]) for k in self._kaynaklar)
        self.kaynak_bilgi.setText(
            f"{len(self._kaynaklar)} veri seti, {toplam} görsel"
            if self._kaynaklar else "Henüz veri seti eklenmedi")

    # ── sınıf eşleme
    def _kaynak_siniflari(self, k: dict) -> dict:
        """Kaynağın sınıfları; adı yoksa etiketlerde geçen id'lerden üret.

        Ad dosyası yoksa etiketler taranıyor; sonuç kaynakta saklanır çünkü
        tablo her tazelendiğinde yeniden taramak yüzlerce dosya okuması demek.
        """
        if k["names"]:
            return dict(k["names"])
        if k.get("_cikarilan") is not None:
            return k["_cikarilan"]
        gorulen = set()
        for img in k["gorseller"][:400]:      # örnekle: hepsini okumaya gerek yok
            lbl = etiket_yolu(img, k["img_dir"], k["lbl_dir"])
            if not os.path.exists(lbl):
                continue
            try:
                with open(lbl, "r", encoding="utf-8") as f:
                    for ln in f:
                        p = ln.split()
                        if p:
                            try:
                                gorulen.add(int(float(p[0])))
                            except ValueError:
                                pass
            except OSError:
                pass
        k["_cikarilan"] = {i: f"sinif_{i}" for i in sorted(gorulen)}
        return k["_cikarilan"]

    def _otomatik_esle(self):
        """Aynı isimli sınıfları eşle; hedef listesini kaynakların birleşimi yap."""
        hedef = []
        for k in self._kaynaklar:
            for _i, ad in sorted(self._kaynak_siniflari(k).items()):
                if ad not in hedef:
                    hedef.append(ad)
        self._hedef_adlar = hedef
        self.hedef_edit.setText(", ".join(hedef))
        self._esleme_tazele()

    def _hedef_degisti(self):
        adlar = [a.strip() for a in self.hedef_edit.text().split(",") if a.strip()]
        if adlar != self._hedef_adlar:
            self._hedef_adlar = adlar
            self._esleme_tazele()

    def _esleme_tazele(self):
        satirlar = []
        for k in self._kaynaklar:
            for kid, kad in sorted(self._kaynak_siniflari(k).items()):
                satirlar.append((k["ad"], kad, kid))
        self.esleme_tablo.setRowCount(len(satirlar))
        for r, (kaynak, kad, kid) in enumerate(satirlar):
            for sutun, metin in ((0, kaynak), (1, kad), (2, str(kid))):
                it = QTableWidgetItem(metin)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.esleme_tablo.setItem(r, sutun, it)
            cb = QComboBox()
            cb.addItem(ATLA, None)
            for i, ad in enumerate(self._hedef_adlar):
                cb.addItem(f"{i}: {ad}", i)
            if kad in self._hedef_adlar:
                cb.setCurrentIndex(self._hedef_adlar.index(kad) + 1)
            self.esleme_tablo.setCellWidget(r, 3, cb)
        self.esleme_tablo.resizeColumnsToContents()
        self.esleme_tablo.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def _eslemeleri_topla(self) -> list:
        """Tablodaki seçimleri kaynak başına {kaynak_id: hedef_id} sözlüğüne çevirir."""
        sonuc = [{} for _ in self._kaynaklar]
        ad_indeks = {k["ad"]: i for i, k in enumerate(self._kaynaklar)}
        for r in range(self.esleme_tablo.rowCount()):
            kaynak = self.esleme_tablo.item(r, 0).text()
            kid = int(self.esleme_tablo.item(r, 2).text())
            cb = self.esleme_tablo.cellWidget(r, 3)
            sonuc[ad_indeks[kaynak]][kid] = cb.currentData() if cb else None
        return sonuc

    def _out_sec(self):
        d = QFileDialog.getExistingDirectory(self, "Birleşik setin yazılacağı klasör",
                                             self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    # ── çalıştır
    def _start(self):
        if self._worker:
            return
        if len(self._kaynaklar) < 1:
            QMessageBox.warning(self, "Kaynak yok", "En az bir veri seti ekle.")
            return
        if not self._hedef_adlar:
            QMessageBox.warning(self, "Hedef sınıf yok",
                                "Hedef sınıf listesi boş. 'Otomatik Eşle'ye bas ya da "
                                "sınıfları virgülle yaz.")
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "Klasör yok", "Çıktı klasörünü seç.")
            return
        for k in self._kaynaklar:
            if os.path.abspath(out).startswith(os.path.abspath(k["img_dir"]) + os.sep):
                QMessageBox.warning(
                    self, "Geçersiz klasör",
                    f"Çıktı klasörü '{k['ad']}' kaynağının içinde olamaz.")
                return
        if os.path.isdir(out) and os.listdir(out):
            if QMessageBox.question(
                    self, "Klasör dolu",
                    "Çıktı klasörü boş değil. İçindekilerin üstüne yazılabilir.\n"
                    "Devam edilsin mi?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        eslemeler = self._eslemeleri_topla()
        alinan = sum(1 for e in eslemeler for v in e.values() if v is not None)
        if not alinan:
            QMessageBox.warning(self, "Hiç sınıf seçilmedi",
                                "Bütün sınıflar '(atla)' — birleştirilecek kutu kalmıyor.")
            return

        # tablodaki ön ekleri kaynaklara geri yaz
        kaynaklar = []
        for i, k in enumerate(self._kaynaklar):
            onek = self.kaynak_tablo.item(i, 0).text().strip()
            kaynaklar.append({**k, "onek": onek, "esleme": eslemeler[i]})

        self.log_box.clear()
        self._log(f"Hedef sınıflar: " + ", ".join(
            f"{i}:{a}" for i, a in enumerate(self._hedef_adlar)))
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.start_btn.setEnabled(False)

        self._worker = BirlestirIscisi({
            "kaynaklar": kaynaklar, "hedef_adlar": list(self._hedef_adlar),
            "out_dir": out, "mode": self.mode_combo.currentData(),
            "bos_atla": self.bos_chk.isChecked(),
        })
        self._worker.log.connect(self._log)
        self._worker.progress.connect(
            lambda d, t: self.progress.setValue(int(100 * d / max(1, t))))
        self._worker.done.connect(self._bitti)
        self._worker.finished.connect(self._worker_bitti)
        self._worker.start()

    def _worker_bitti(self):
        self._worker = None
        self.progress.setVisible(False)
        self.start_btn.setEnabled(True)

    def _bitti(self, r: dict):
        s = r["sayac"]
        sat = ["", "═══ BİRLEŞTİRME ÖZETİ ═══"]
        sat.append(f"çıktı        : {r['out']}")
        sat.append(f"görsel       : {s['gorsel']}")
        sat.append(f"kutu         : {s['kutu']}")
        if s["atlanan_kutu"]:
            sat.append(f"atlanan kutu : {s['atlanan_kutu']}  (hedefi '(atla)' olan sınıflar)")
        if s["bos_atlanan"]:
            sat.append(f"boş görsel   : {s['bos_atlanan']} alınmadı")
        if s["etiketsiz"]:
            sat.append(f"etiketsiz    : {s['etiketsiz']} görselin .txt'si yok")
        if s["hata"]:
            sat.append(f"hata         : {s['hata']}")
        sat.append("")
        sat.append("── kaynak başına ──")
        for ad, g, kt, at, bo in r["kaynaklar"]:
            sat.append(f"  {ad:<22s} {g:>5d} görsel  {kt:>6d} kutu"
                       + (f"  ({at} atlandı)" if at else ""))
        sat.append("")
        sat.append("── hedef sınıf dağılımı ──")
        for ad in r["hedef_adlar"]:
            n = r["sinif_sayim"].get(ad, 0)
            isaret = "   ← hiç örnek yok" if n == 0 else ""
            sat.append(f"  {ad:<22s} {n:>6d}{isaret}")
        bos_sinif = [a for a in r["hedef_adlar"] if r["sinif_sayim"].get(a, 0) == 0]
        if bos_sinif:
            sat.append("")
            sat.append(f"! {len(bos_sinif)} sınıfın hiç örneği yok — bunlar hedef "
                       f"listesinde durursa model o id'leri boşuna taşır.")
        sat.append("")
        sat.append(f"data.yaml    : {r['yaml']}")
        sat.append("Sıradaki adım: Veri Denetçi ile denetle ve sızıntısız böl.")
        self._log("\n".join(sat))

        if r.get("iptal"):
            self.setWindowTitle("Veri Setlerini Birleştir — iptal edildi")
            return
        QMessageBox.information(
            self, "Birleştirme bitti",
            f"{s['gorsel']} görsel, {s['kutu']} kutu yazıldı.\n\n{r['out']}\n\n"
            f"Sıradaki adım: Veri Denetçi ile denetleyip sızıntısız böl.")

    def closeEvent(self, olay):
        if self._worker is not None and self._worker.isRunning():
            self._worker.iptal()
            self._worker.wait(5000)
        olay.accept()


def main():
    from ..tema import STYLE
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    d = BirlestirDialog()
    d.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
