"""COCO / Pascal VOC veri setini YOLO biçimine çevirir.

Boxify'ın etiket biçimi baştan beri YOLO txt. Dışarıdan gelen veri setleri ise
çoğunlukla COCO JSON ya da Pascal VOC XML oluyor. Bunları elle çevirmek hem
sıkıcı hem hataya açık: kutu biçimleri farklı (COCO mutlak `x,y,w,h`; VOC
mutlak köşeler; YOLO normalize edilmiş merkez), sınıf id'leri farklı ve
görsel boyutları çözünürlük başına değişiyor.

Ele alınan ayrıntılar:

* **Kutu dönüşümü.** COCO `[x, y, w, h]` sol-üst köşeden; VOC `xmin, ymin,
  xmax, ymax`. İkisi de görsel boyutuna bölünüp merkez tabanlı hâle getirilir.
* **Görsel boyutu.** COCO'da JSON içinde yazar ama bazen yanlıştır ya da hiç
  yoktur; VOC'ta `<size>` bloğu eksik olabilir. İkisinde de değer yoksa ya da
  sıfırsa görsel diskten okunur.
* **Sınıf eşleme.** Kaynak sınıflarının hedefte neye denk geleceği tek tek
  seçilir — Veri Setlerini Birleştir'deki mantığın aynısı. İstenmeyen sınıf
  "(atla)" ile düşürülür.
* **Elenen kutular.** COCO'da `iscrowd=1`, VOC'ta `<difficult>1</difficult>`
  olan nesneler eğitimi bozabildiği için isteğe bağlı olarak atlanır; kaç tane
  atlandığı raporlanır.
* **Aralık dışı kutular.** Görsel sınırlarını taşan kutular kırpılır; tamamen
  dışarıda kalan ya da sıfır alanlı olanlar elenir ve sayılır.

Veri Denetçi'den açılır; tek başına da çalışır:
    python -m boxify.araclar.veri_ice_aktar
"""

import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

from PyQt5.QtWidgets import (
    QApplication, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QGroupBox, QMessageBox, QLineEdit, QComboBox,
    QProgressBar, QCheckBox, QTextEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

ATLA = "(atla — bu sınıfı alma)"


# ─────────────────────────────────────────────── biçim okuyucular

def gorsel_boyutu(yol: str):
    """(genişlik, yükseklik) — okunamazsa (0, 0)."""
    try:
        import cv2
        import numpy as np
        im = cv2.imdecode(np.fromfile(yol, dtype=np.uint8), cv2.IMREAD_COLOR)
        if im is not None:
            return im.shape[1], im.shape[0]
    except Exception:
        pass
    try:
        from PyQt5.QtGui import QImageReader
        sz = QImageReader(yol).size()
        if sz.isValid():
            return sz.width(), sz.height()
    except Exception:
        pass
    return 0, 0


def coco_oku(json_yolu: str, gorsel_kok: str) -> dict:
    """COCO JSON → {"siniflar": {id: ad}, "kayitlar": [...], "hata": str}

    kayıt: {"gorsel": tam_yol, "w": int, "h": int,
            "kutular": [(sinif_id, x, y, w, h, kalabalik)]}  (mutlak piksel)
    """
    try:
        with open(json_yolu, encoding="utf-8") as f:
            veri = json.load(f)
    except Exception as e:
        return {"hata": f"JSON okunamadı: {e}"}

    if not isinstance(veri, dict) or "images" not in veri:
        return {"hata": "Bu dosya COCO biçiminde görünmüyor "
                        "('images' anahtarı yok)."}

    siniflar = {}
    for k in veri.get("categories", []) or []:
        try:
            siniflar[int(k["id"])] = str(k.get("name", k["id"]))
        except (KeyError, ValueError, TypeError):
            continue

    gorseller = {}
    for g in veri.get("images", []) or []:
        try:
            gid = int(g["id"])
        except (KeyError, ValueError, TypeError):
            continue
        ad = g.get("file_name") or g.get("filename") or ""
        gorseller[gid] = {
            "ad": ad,
            "w": int(g.get("width") or 0),
            "h": int(g.get("height") or 0),
            "kutular": [],
        }

    for a in veri.get("annotations", []) or []:
        try:
            gid = int(a["image_id"])
            kutu = a["bbox"]
            sid = int(a["category_id"])
        except (KeyError, ValueError, TypeError):
            continue
        if gid not in gorseller or not isinstance(kutu, (list, tuple)) \
                or len(kutu) < 4:
            continue
        try:
            x, y, w, h = (float(v) for v in kutu[:4])
        except (ValueError, TypeError):
            continue
        gorseller[gid]["kutular"].append(
            (sid, x, y, w, h, bool(a.get("iscrowd", 0))))

    kayitlar = []
    for g in gorseller.values():
        if not g["ad"]:
            continue
        yol = g["ad"] if os.path.isabs(g["ad"]) else os.path.join(gorsel_kok, g["ad"])
        kayitlar.append({"gorsel": yol, "w": g["w"], "h": g["h"],
                         "kutular": g["kutular"]})
    return {"siniflar": siniflar, "kayitlar": kayitlar, "hata": ""}


def voc_oku(xml_kok: str, gorsel_kok: str) -> dict:
    """Pascal VOC XML klasörü → coco_oku ile aynı biçimde sözlük.

    VOC'ta sınıf id'si yoktur, yalnızca ad vardır; id'ler burada karşılaşma
    sırasına göre üretilir.
    """
    xmller = []
    for dizin, _alt, dosyalar in os.walk(xml_kok):
        for ad in dosyalar:
            if ad.lower().endswith(".xml"):
                xmller.append(os.path.join(dizin, ad))
    if not xmller:
        return {"hata": "Bu klasörde .xml dosyası bulunamadı."}

    ad_id, siniflar, kayitlar = {}, {}, []
    for xml_yolu in sorted(xmller):
        try:
            kok = ET.parse(xml_yolu).getroot()
        except Exception:
            continue

        dosya = (kok.findtext("filename") or "").strip()
        if not dosya:
            dosya = os.path.splitext(os.path.basename(xml_yolu))[0] + ".jpg"

        # görsel yolu: <folder> varsa onu da dene, sonra xml'in yanına bak
        adaylar = [os.path.join(gorsel_kok, dosya),
                   os.path.join(os.path.dirname(xml_yolu), dosya)]
        klasor = (kok.findtext("folder") or "").strip()
        if klasor:
            adaylar.insert(1, os.path.join(gorsel_kok, klasor, dosya))
        yol = next((p for p in adaylar if os.path.exists(p)), adaylar[0])

        boyut = kok.find("size")
        w = int(float(boyut.findtext("width") or 0)) if boyut is not None else 0
        h = int(float(boyut.findtext("height") or 0)) if boyut is not None else 0

        kutular = []
        for nesne in kok.findall("object"):
            ad = (nesne.findtext("name") or "").strip()
            if not ad:
                continue
            if ad not in ad_id:
                ad_id[ad] = len(ad_id)
                siniflar[ad_id[ad]] = ad
            kutu = nesne.find("bndbox")
            if kutu is None:
                continue
            try:
                x1 = float(kutu.findtext("xmin"))
                y1 = float(kutu.findtext("ymin"))
                x2 = float(kutu.findtext("xmax"))
                y2 = float(kutu.findtext("ymax"))
            except (TypeError, ValueError):
                continue
            zor = (nesne.findtext("difficult") or "0").strip() == "1"
            # VOC köşe tabanlı; ortak biçime (sol-üst + boyut) çevir
            kutular.append((ad_id[ad], x1, y1, x2 - x1, y2 - y1, zor))

        kayitlar.append({"gorsel": yol, "w": w, "h": h, "kutular": kutular})
    return {"siniflar": siniflar, "kayitlar": kayitlar, "hata": ""}


def bicim_tahmin(yol: str) -> str:
    """'coco', 'voc' ya da '' — seçilen yola bakarak biçimi tahmin eder."""
    if os.path.isfile(yol) and yol.lower().endswith(".json"):
        return "coco"
    if os.path.isdir(yol):
        for dizin, _alt, dosyalar in os.walk(yol):
            if any(d.lower().endswith(".xml") for d in dosyalar):
                return "voc"
            if any(d.lower().endswith(".json") for d in dosyalar):
                return "coco"
    return ""


# ─────────────────────────────────────────────── işçi

class AktarIscisi(QThread):
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

        hedef = cfg["hedef_adlar"]
        esleme = cfg["esleme"]              # {kaynak_id: hedef_id | None}
        kopyala = cfg["mode"] == "copy"
        kayitlar = cfg["kayitlar"]

        sayac = {"gorsel": 0, "kutu": 0, "atlanan_sinif": 0, "kalabalik": 0,
                 "gecersiz": 0, "kirpilan": 0, "gorsel_yok": 0, "bos_atlanan": 0}
        sinif_sayim = {ad: 0 for ad in hedef}
        toplam = len(kayitlar)

        for i, kayit in enumerate(kayitlar):
            if self._iptal:
                break
            if i % 20 == 0:
                self.progress.emit(i + 1, toplam)

            gorsel = kayit["gorsel"]
            if not os.path.exists(gorsel):
                sayac["gorsel_yok"] += 1
                if sayac["gorsel_yok"] <= 5:
                    self.log.emit(f"görsel yok: {os.path.basename(gorsel)}")
                continue

            w, h = kayit["w"], kayit["h"]
            if w <= 0 or h <= 0:
                # üstveride boyut yok ya da bozuk — diskten oku
                w, h = gorsel_boyutu(gorsel)
            if w <= 0 or h <= 0:
                sayac["gorsel_yok"] += 1
                self.log.emit(f"boyut okunamadı: {os.path.basename(gorsel)}")
                continue

            satirlar = []
            for sid, x, y, bw, bh, isaret in kayit["kutular"]:
                if isaret and cfg["isaretli_atla"]:
                    sayac["kalabalik"] += 1
                    continue
                yeni = esleme.get(sid)
                if yeni is None:
                    sayac["atlanan_sinif"] += 1
                    continue
                # sınırların dışına taşan kutuyu kırp
                x1, y1 = max(0.0, x), max(0.0, y)
                x2, y2 = min(float(w), x + bw), min(float(h), y + bh)
                if x2 - x1 <= 1e-6 or y2 - y1 <= 1e-6:
                    sayac["gecersiz"] += 1
                    continue
                if (x1, y1, x2, y2) != (x, y, x + bw, y + bh):
                    sayac["kirpilan"] += 1
                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                nw = (x2 - x1) / w
                nh = (y2 - y1) / h
                if not (0 < nw <= 1 and 0 < nh <= 1):
                    sayac["gecersiz"] += 1
                    continue
                satirlar.append(f"{yeni} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
                sinif_sayim[hedef[yeni]] += 1
                sayac["kutu"] += 1

            if not satirlar and cfg["bos_atla"]:
                sayac["bos_atlanan"] += 1
                continue

            ad = os.path.basename(gorsel)
            hedef_img = os.path.join(img_out, ad)
            kok_ad, uzanti = os.path.splitext(hedef_img)
            n = 1
            while os.path.exists(hedef_img):
                hedef_img = f"{kok_ad}__{n}{uzanti}"
                n += 1
            try:
                if kopyala:
                    shutil.copy2(gorsel, hedef_img)
                else:
                    os.symlink(os.path.abspath(gorsel), hedef_img)
                with open(os.path.join(
                        lbl_out,
                        os.path.splitext(os.path.basename(hedef_img))[0] + ".txt"),
                        "w", encoding="utf-8") as f:
                    f.write("\n".join(satirlar) + ("\n" if satirlar else ""))
            except OSError as e:
                self.log.emit(f"HATA — {ad}: {e}")
                sayac["gecersiz"] += 1
                continue
            sayac["gorsel"] += 1

        self.progress.emit(toplam, toplam)

        yaml_yolu = os.path.join(out, "data.yaml")
        try:
            with open(yaml_yolu, "w", encoding="utf-8") as f:
                f.write(f"path: {os.path.abspath(out)}\n")
                f.write("train: images\nval: images\n")
                f.write(f"nc: {len(hedef)}\nnames:\n")
                for i, ad in enumerate(hedef):
                    f.write(f"  {i}: {ad}\n")
            with open(os.path.join(out, "classes.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(hedef) + "\n")
        except OSError as e:
            self.log.emit(f"HATA — data.yaml yazılamadı: {e}")

        self.done.emit({"iptal": self._iptal, "out": out, "yaml": yaml_yolu,
                        "sayac": sayac, "sinif_sayim": sinif_sayim,
                        "hedef_adlar": hedef})


# ─────────────────────────────────────────────── diyalog

class IceAktarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("COCO / Pascal VOC İçe Aktar")
        self.resize(980, 760)
        self.setMinimumSize(780, 560)
        self._kaynak = ""
        self._veri = {}
        self._hedef_adlar = []
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        aciklama = QLabel(
            "Dışarıdan gelen COCO (JSON) ya da Pascal VOC (XML) veri setini YOLO txt "
            "biçimine çevirir. Kutu biçimleri ve sınıf id'leri farklı olduğu için "
            "her kaynak sınıfının hedefte neye denk geleceğini aşağıda belirlersin.")
        aciklama.setWordWrap(True)
        aciklama.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(aciklama)

        # ── kaynak
        g1 = QGroupBox("Kaynak")
        v1 = QVBoxLayout(g1)
        h = QHBoxLayout()
        self.bicim_grup = QButtonGroup(self)
        self.coco_rb = QRadioButton("COCO (tek .json)")
        self.voc_rb = QRadioButton("Pascal VOC (.xml klasörü)")
        self.coco_rb.setChecked(True)
        for rb in (self.coco_rb, self.voc_rb):
            self.bicim_grup.addButton(rb)
            h.addWidget(rb)
        h.addStretch()
        v1.addLayout(h)

        h2 = QHBoxLayout()
        self.kaynak_edit = QLineEdit()
        self.kaynak_edit.setReadOnly(True)
        self.kaynak_edit.setPlaceholderText("annotations.json ya da xml klasörü")
        h2.addWidget(self.kaynak_edit, 1)
        b = QPushButton("Seç…")
        b.setFixedWidth(60)
        b.clicked.connect(self._kaynak_sec)
        h2.addWidget(b)
        v1.addLayout(h2)

        h3 = QHBoxLayout()
        self.gorsel_edit = QLineEdit()
        self.gorsel_edit.setReadOnly(True)
        self.gorsel_edit.setPlaceholderText("görsellerin bulunduğu klasör")
        h3.addWidget(QLabel("Görseller:"))
        h3.addWidget(self.gorsel_edit, 1)
        b2 = QPushButton("Seç…")
        b2.setFixedWidth(60)
        b2.clicked.connect(self._gorsel_sec)
        h3.addWidget(b2)
        v1.addLayout(h3)

        self.kaynak_bilgi = QLabel("Henüz kaynak seçilmedi")
        self.kaynak_bilgi.setWordWrap(True)
        self.kaynak_bilgi.setStyleSheet("color:#6b7686; font-size:11px;")
        v1.addWidget(self.kaynak_bilgi)
        v.addWidget(g1)

        # ── sınıf eşleme
        g2 = QGroupBox("Sınıf eşleme")
        v2 = QVBoxLayout(g2)
        self.esleme_tablo = QTableWidget(0, 4)
        self.esleme_tablo.setHorizontalHeaderLabels(
            ["Kaynak sınıfı", "id", "Kutu", "Hedef sınıfı"])
        self.esleme_tablo.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.esleme_tablo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.esleme_tablo.setMinimumHeight(220)
        v2.addWidget(self.esleme_tablo)

        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Hedef sınıflar (virgülle, sıra = id):"))
        self.hedef_edit = QLineEdit()
        self.hedef_edit.setPlaceholderText("kaynaktan otomatik doldurulur")
        self.hedef_edit.editingFinished.connect(self._hedef_degisti)
        h4.addWidget(self.hedef_edit, 1)
        b3 = QPushButton("Otomatik Eşle")
        b3.clicked.connect(self._otomatik_esle)
        h4.addWidget(b3)
        v2.addLayout(h4)
        v.addWidget(g2, 1)

        # ── çıktı
        g3 = QGroupBox("Çıktı")
        v3 = QVBoxLayout(g3)
        h5 = QHBoxLayout()
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("YOLO veri setinin yazılacağı klasör")
        h5.addWidget(self.out_edit, 1)
        b4 = QPushButton("Seç…")
        b4.setFixedWidth(60)
        b4.clicked.connect(self._out_sec)
        h5.addWidget(b4)
        v3.addLayout(h5)

        h6 = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Kopyala (güvenli)", "copy")
        self.mode_combo.addItem("Sembolik bağ (yer kaplamaz)", "symlink")
        self.mode_combo.setFixedWidth(220)
        h6.addWidget(QLabel("Görseller:"))
        h6.addWidget(self.mode_combo)
        self.isaretli_chk = QCheckBox("iscrowd / difficult kutuları alma")
        self.isaretli_chk.setChecked(True)
        self.isaretli_chk.setToolTip(
            "COCO'da iscrowd=1, VOC'ta difficult=1 olan nesneler belirsiz ya da\n"
            "yığın hâlindedir; eğitimde gürültü yapabilirler.")
        h6.addWidget(self.isaretli_chk)
        self.bos_chk = QCheckBox("Kutusuz görselleri alma")
        h6.addWidget(self.bos_chk)
        h6.addStretch()
        v3.addLayout(h6)
        v.addWidget(g3)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.log_box.setMaximumHeight(120)
        v.addWidget(self.log_box)

        h7 = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        h7.addWidget(self.progress, 1)
        self.start_btn = QPushButton("⇩  İçe Aktar")
        self.start_btn.setMinimumHeight(34)
        self.start_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:6px 14px;")
        self.start_btn.clicked.connect(self._start)
        h7.addWidget(self.start_btn)
        kapat = QPushButton("Kapat")
        kapat.clicked.connect(self.reject)
        h7.addWidget(kapat)
        v.addLayout(h7)

    # ── kaynak seçimi
    def _log(self, t: str):
        self.log_box.append(t)

    def _kaynak_sec(self):
        if self.coco_rb.isChecked():
            p, _ = QFileDialog.getOpenFileName(
                self, "COCO açıklama dosyası", "", "COCO JSON (*.json)")
        else:
            p = QFileDialog.getExistingDirectory(self, "VOC XML klasörü")
        if not p:
            return
        self._kaynak = p
        self.kaynak_edit.setText(p)
        self.kaynak_edit.setCursorPosition(0)
        tahmin = bicim_tahmin(p)
        if tahmin == "coco" and not self.coco_rb.isChecked():
            self.coco_rb.setChecked(True)
        elif tahmin == "voc" and not self.voc_rb.isChecked():
            self.voc_rb.setChecked(True)
        if not self.gorsel_edit.text():
            varsayilan = (os.path.dirname(p) if os.path.isfile(p) else p)
            self.gorsel_edit.setText(varsayilan)
            self.gorsel_edit.setCursorPosition(0)
        self._oku()

    def _gorsel_sec(self):
        d = QFileDialog.getExistingDirectory(self, "Görsellerin bulunduğu klasör",
                                             self.gorsel_edit.text())
        if d:
            self.gorsel_edit.setText(d)
            self.gorsel_edit.setCursorPosition(0)
            if self._kaynak:
                self._oku()

    def _oku(self):
        gorsel_kok = self.gorsel_edit.text().strip()
        if self.coco_rb.isChecked():
            self._veri = coco_oku(self._kaynak, gorsel_kok)
        else:
            self._veri = voc_oku(self._kaynak, gorsel_kok)

        if self._veri.get("hata"):
            self.kaynak_bilgi.setText(self._veri["hata"])
            self.esleme_tablo.setRowCount(0)
            return

        kayitlar = self._veri["kayitlar"]
        kutu = sum(len(k["kutular"]) for k in kayitlar)
        eksik = sum(1 for k in kayitlar if not os.path.exists(k["gorsel"]))
        metin = (f"{len(kayitlar)} görsel, {kutu} kutu, "
                 f"{len(self._veri['siniflar'])} sınıf")
        if eksik:
            metin += (f"  |  ! {eksik} görsel bulunamadı — "
                      f"'Görseller' klasörünü kontrol et")
        self.kaynak_bilgi.setText(metin)
        self._otomatik_esle()

    # ── sınıf eşleme
    def _sinif_kutu_sayisi(self) -> dict:
        sayim = {}
        for k in self._veri.get("kayitlar", []):
            for sid, *_ in k["kutular"]:
                sayim[sid] = sayim.get(sid, 0) + 1
        return sayim

    def _otomatik_esle(self):
        siniflar = self._veri.get("siniflar", {})
        self._hedef_adlar = [siniflar[i] for i in sorted(siniflar)]
        self.hedef_edit.setText(", ".join(self._hedef_adlar))
        self._esleme_tazele()

    def _hedef_degisti(self):
        adlar = [a.strip() for a in self.hedef_edit.text().split(",") if a.strip()]
        if adlar != self._hedef_adlar:
            self._hedef_adlar = adlar
            self._esleme_tazele()

    def _esleme_tazele(self):
        siniflar = self._veri.get("siniflar", {})
        sayim = self._sinif_kutu_sayisi()
        satirlar = sorted(siniflar.items())
        self.esleme_tablo.setRowCount(len(satirlar))
        for r, (sid, ad) in enumerate(satirlar):
            for sutun, metin in ((0, ad), (1, str(sid)), (2, str(sayim.get(sid, 0)))):
                it = QTableWidgetItem(metin)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.esleme_tablo.setItem(r, sutun, it)
            cb = QComboBox()
            cb.addItem(ATLA, None)
            for i, h in enumerate(self._hedef_adlar):
                cb.addItem(f"{i}: {h}", i)
            if ad in self._hedef_adlar:
                cb.setCurrentIndex(self._hedef_adlar.index(ad) + 1)
            self.esleme_tablo.setCellWidget(r, 3, cb)
        self.esleme_tablo.resizeColumnsToContents()
        self.esleme_tablo.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    def _eslemeyi_topla(self) -> dict:
        sonuc = {}
        for r in range(self.esleme_tablo.rowCount()):
            sid = int(self.esleme_tablo.item(r, 1).text())
            cb = self.esleme_tablo.cellWidget(r, 3)
            sonuc[sid] = cb.currentData() if cb else None
        return sonuc

    def _out_sec(self):
        d = QFileDialog.getExistingDirectory(self, "YOLO veri setinin yazılacağı klasör",
                                             self.out_edit.text())
        if d:
            self.out_edit.setText(d)

    # ── çalıştır
    def _start(self):
        if self._worker:
            return
        if not self._veri or self._veri.get("hata") or not self._veri.get("kayitlar"):
            QMessageBox.warning(self, "Kaynak yok",
                                "Önce geçerli bir COCO ya da VOC kaynağı seç.")
            return
        if not self._hedef_adlar:
            QMessageBox.warning(self, "Hedef sınıf yok",
                                "Hedef sınıf listesi boş. 'Otomatik Eşle'ye bas.")
            return
        out = self.out_edit.text().strip()
        if not out:
            QMessageBox.warning(self, "Klasör yok", "Çıktı klasörünü seç.")
            return
        gorsel_kok = self.gorsel_edit.text().strip()
        if gorsel_kok and os.path.abspath(out).startswith(
                os.path.abspath(gorsel_kok) + os.sep):
            QMessageBox.warning(self, "Geçersiz klasör",
                                "Çıktı klasörü kaynak görsellerin içinde olamaz.")
            return
        esleme = self._eslemeyi_topla()
        if not any(v is not None for v in esleme.values()):
            QMessageBox.warning(self, "Hiç sınıf seçilmedi",
                                "Bütün sınıflar '(atla)' — alınacak kutu kalmıyor.")
            return
        if os.path.isdir(out) and os.listdir(out):
            if QMessageBox.question(
                    self, "Klasör dolu",
                    "Çıktı klasörü boş değil. İçindekilerin üstüne yazılabilir.\n"
                    "Devam edilsin mi?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        self.log_box.clear()
        self._log("Hedef sınıflar: " + ", ".join(
            f"{i}:{a}" for i, a in enumerate(self._hedef_adlar)))
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.start_btn.setEnabled(False)

        self._worker = AktarIscisi({
            "kayitlar": self._veri["kayitlar"],
            "hedef_adlar": list(self._hedef_adlar),
            "esleme": esleme, "out_dir": out,
            "mode": self.mode_combo.currentData(),
            "isaretli_atla": self.isaretli_chk.isChecked(),
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
        sat = ["", "═══ İÇE AKTARMA ÖZETİ ═══",
               f"çıktı           : {r['out']}",
               f"görsel          : {s['gorsel']}",
               f"kutu            : {s['kutu']}"]
        for etiket, anahtar in (("atlanan sınıf  ", "atlanan_sinif"),
                                ("iscrowd/difficult", "kalabalik"),
                                ("kırpılan kutu  ", "kirpilan"),
                                ("geçersiz kutu  ", "gecersiz"),
                                ("görsel yok     ", "gorsel_yok"),
                                ("kutusuz atlanan", "bos_atlanan")):
            if s.get(anahtar):
                sat.append(f"{etiket} : {s[anahtar]}")
        sat += ["", "── hedef sınıf dağılımı ──"]
        for ad in r["hedef_adlar"]:
            n = r["sinif_sayim"].get(ad, 0)
            sat.append(f"  {ad:<22s} {n:>6d}" + ("   ← hiç örnek yok" if not n else ""))
        sat += ["", f"data.yaml       : {r['yaml']}",
                "Sıradaki adım: Veri Denetçi ile denetle ve sızıntısız böl."]
        self._log("\n".join(sat))
        if r.get("iptal"):
            return
        QMessageBox.information(
            self, "İçe aktarma bitti",
            f"{s['gorsel']} görsel, {s['kutu']} kutu yazıldı.\n\n{r['out']}\n\n"
            f"Sıradaki adım: Veri Denetçi ile denetleyip sızıntısız böl.")

    def closeEvent(self, olay):
        if self._worker is not None and self._worker.isRunning():
            self._worker.iptal()
            self._worker.wait(5000)
        olay.accept()


def main():
    from .. import tema as _tema
    from .. import proje as _proje
    app = QApplication(sys.argv)
    _tema.tema_yukle()
    _tema.yamalari_kur()
    _proje.yukle()
    _proje.yamalari_kur()
    app.setStyleSheet(_tema.stil())
    d = IceAktarDialog()
    d.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
