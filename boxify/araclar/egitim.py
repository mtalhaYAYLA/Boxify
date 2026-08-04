"""Eğitim — veri setini modele dönüştürür.

Döngünün kapandığı yer: Veri Denetçi'nin ürettiği `data.yaml` burada eğitilir,
çıkan `best.pt` Hata Analizi ve Model Karşılaştır'a girer, oradan gelen bilgiyle
veri büyür ve aynı model üstüne yeniden eğitilir.

Tasarım kararları:

* **Kendi modelinden devam edebilirsin.** Hazır ağırlık adı (yolo11n…) yerine
  bir `.pt` dosyası seçebilirsin; ince ayar döngüsünün tamamı buna bağlı.
* **Eğitim ayrı bir süreçte değil, ayrı bir iş parçacığında koşar.** Eski
  yaklaşım eğitim betiğini metin olarak kurup `python -c` ile çalıştırıyordu;
  yolunda tek tırnak olan bir klasör (Ali'nin kayitlari) sözdizimi hatası
  veriyordu. Burada ultralytics doğrudan çağrılıyor, ilerleme de stdout
  ayrıştırarak değil `add_callback` ile alınıyor.
* **Sızıntı denetimi eğitimden önce.** train ve val aynı sahnenin karelerini
  paylaşıyorsa skor şişer; bu sessizce olursa modelin iyi olduğunu sanırsın.
  Denetim Veri Denetçi ile aynı koddan gelir (veri_bolme.py).

Bağımlılık: PyQt5, ultralytics, PyYAML, opencv (sızıntı denetimi için).
"""

import os
import sys
import time
import traceback

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QStatusBar, QGroupBox, QMessageBox,
    QLineEdit, QAction, QComboBox, QProgressBar, QCheckBox, QSpinBox,
    QDoubleSpinBox, QTextEdit, QTabWidget, QScrollArea, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPainter, QColor, QPen, QFont

from ..tema import STYLE
from ..klasor_ac import klasoru_ac
from .model_bilgi import cihaz_combo_doldur

# Hazır ağırlıklar: ilk turda kendi modelin yokken buradan başlanır.
HAZIR_MODELLER = [
    "yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x",
    "yolov8n", "yolov8s", "yolov8m", "yolov8l", "yolov8x",
]


# ─────────────────────────────────────────────── sızıntı denetimi

class SizintiIscisi(QThread):
    """data.yaml'daki train/val bölümleri aynı sahneyi paylaşıyor mu?

    Aynı karenin (ya da neredeyse aynısının) hem train'e hem val'e düşmesi
    doğrulama skorunu şişirir. Denetim, Veri Denetçi'nin yakın-kopya
    gruplamasını kullanır: bir grup hem train hem val tarafında görünüyorsa
    sızıntı vardır.
    """

    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(dict)

    def __init__(self, yaml_yolu: str, esik: int = 5, en_fazla: int = 4000):
        super().__init__()
        self.yaml_yolu = yaml_yolu
        self.esik = esik
        self.en_fazla = en_fazla
        self._iptal = False

    def iptal(self):
        self._iptal = True

    def run(self):
        try:
            from .veri_bolme import (dhash64, group_duplicates,
                                     gorselleri_listele)
            import cv2
            import numpy as np
            import yaml
        except ImportError as e:
            self.done.emit({"hata": f"Gerekli paket yok: {e}"})
            return

        try:
            with open(self.yaml_yolu, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            self.done.emit({"hata": f"data.yaml okunamadı: {e}"})
            return

        kok = cfg.get("path") or os.path.dirname(os.path.abspath(self.yaml_yolu))

        def coz(deger):
            """train/val alanı klasör, liste dosyası ya da liste olabilir."""
            if not deger:
                return []
            if isinstance(deger, (list, tuple)):
                yollar = []
                for d in deger:
                    yollar += coz(d)
                return yollar
            p = deger if os.path.isabs(deger) else os.path.join(kok, deger)
            if os.path.isdir(p):
                return gorselleri_listele(p)
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8") as f:
                    return [l.strip() for l in f if l.strip()]
            return []

        train = coz(cfg.get("train"))
        val = coz(cfg.get("val"))
        if not train or not val:
            self.done.emit({"hata": "",
                            "uyari": "train veya val bölümü boş — sızıntı denetimi atlandı.",
                            "train": len(train), "val": len(val), "sizan": 0})
            return

        # Çok büyük veri setinde her kareyi okumak pahalı; eşit aralıkla örnekle
        def ornekle(liste):
            if len(liste) <= self.en_fazla:
                return list(enumerate(liste))
            adim = len(liste) / self.en_fazla
            return [(int(i * adim), liste[int(i * adim)]) for i in range(self.en_fazla)]

        t_orn, v_orn = ornekle(train), ornekle(val)
        tumu = [p for _i, p in t_orn] + [p for _i, p in v_orn]
        tarafi = ["train"] * len(t_orn) + ["val"] * len(v_orn)

        hashes = []
        for i, p in enumerate(tumu):
            if self._iptal:
                self.done.emit({"hata": "", "iptal": True})
                return
            h = None
            try:
                g = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if g is not None:
                    h = dhash64(g)
            except Exception:
                h = None
            hashes.append(h)
            if i % 25 == 0:
                self.progress.emit(i + 1, len(tumu))
        self.progress.emit(len(tumu), len(tumu))

        sizan, ornekler = 0, []
        for grup in group_duplicates(hashes, self.esik):
            taraflar = {tarafi[i] for i in grup}
            if len(taraflar) > 1:
                sizan += 1
                if len(ornekler) < 5:
                    t = next(i for i in grup if tarafi[i] == "train")
                    v = next(i for i in grup if tarafi[i] == "val")
                    ornekler.append((os.path.basename(tumu[t]),
                                     os.path.basename(tumu[v])))

        self.done.emit({"hata": "", "train": len(train), "val": len(val),
                        "orneklenen": len(tumu), "sizan": sizan,
                        "ornekler": ornekler})


# ─────────────────────────────────────────────── eğitim işçisi

class EgitimIscisi(QThread):
    """ultralytics eğitimini arka planda koşturur, epoch başına metrik yollar."""

    log = pyqtSignal(str)
    epoch = pyqtSignal(dict)          # {"epoch", "epochs", "loss", "map50", "map"}
    failed = pyqtSignal(str)
    done = pyqtSignal(dict)           # {"best", "last", "dizin", "sure", "epoch"}

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._iptal = False
        self._trainer = None
        self._son_epoch = 0

    def iptal(self):
        """Bir sonraki epoch sınırında dur; ultralytics kendi durma bayrağını
        `trainer.stop` ile okuyor, yani süreci öldürmeye gerek yok — o ana
        kadarki en iyi ağırlık diske yazılmış olarak kalır."""
        self._iptal = True
        if self._trainer is not None:
            self._trainer.stop = True

    def run(self):
        cfg = self.cfg
        t0 = time.time()
        try:
            from ultralytics import YOLO
        except Exception as e:
            self.failed.emit(f"ultralytics yüklenemedi: {e}")
            return

        try:
            model = YOLO(cfg["baslangic"])
        except Exception as e:
            self.failed.emit(f"Model açılamadı ({cfg['baslangic']}):\n{e}")
            return

        def kaydet_trainer(trainer):
            self._trainer = trainer
            if self._iptal:
                trainer.stop = True

        def epoch_sonu(trainer):
            self._trainer = trainer
            if self._iptal:
                trainer.stop = True
                return
            m = dict(getattr(trainer, "metrics", {}) or {})
            kayip = None
            try:
                tl = trainer.label_loss_items(trainer.tloss)
                kayip = float(sum(v for v in tl.values() if v is not None))
            except Exception:
                kayip = None

            def al(*adaylar):
                for a in adaylar:
                    if a in m and m[a] is not None:
                        return float(m[a])
                return None

            # Eğitim bitince ultralytics best.pt'yi bir kez daha doğruluyor ve bu
            # da aynı geri çağrımı tetikliyor. O turda trainer.epoch son epoch'ta
            # kalır, yani numara toplam epoch'u bir aşar: yeni bir epoch değil,
            # aynı sonucun tekrarı. Eğriye ikinci kez nokta koymamak için elenir.
            no = int(getattr(trainer, "epoch", 0)) + 1
            toplam = int(getattr(trainer, "epochs", cfg["epochs"]))
            if no > toplam or no <= self._son_epoch:
                return
            self._son_epoch = no

            self.epoch.emit({
                "epoch": no,
                "epochs": toplam,
                "loss": kayip,
                "map50": al("metrics/mAP50(B)", "metrics/mAP50(P)", "metrics/mAP50(M)"),
                "map": al("metrics/mAP50-95(B)", "metrics/mAP50-95(P)", "metrics/mAP50-95(M)"),
                "fitness": float(getattr(trainer, "fitness", 0.0) or 0.0),
            })

        model.add_callback("on_train_start", kaydet_trainer)
        model.add_callback("on_fit_epoch_end", epoch_sonu)

        kw = dict(
            data=cfg["data"],
            epochs=cfg["epochs"],
            batch=cfg["batch"],
            imgsz=cfg["imgsz"],
            patience=cfg["patience"],
            project=cfg["proje"],
            name=cfg["ad"],
            exist_ok=True,
            workers=cfg["workers"],
            seed=cfg["seed"],
            optimizer=cfg["optimizer"],
            lr0=cfg["lr0"],
            val=True,
            plots=cfg["plots"],
            verbose=True,
        )
        if cfg["device"] is not None:
            kw["device"] = cfg["device"]
        if cfg["freeze"]:
            kw["freeze"] = cfg["freeze"]
        if cfg["resume"]:
            kw["resume"] = True
        if cfg["save_period"] > 0:
            kw["save_period"] = cfg["save_period"]

        ayar = ", ".join(f"{k}={v}" for k, v in sorted(kw.items())
                         if k not in ("data", "project"))
        self.log.emit(f"Başlangıç ağırlığı: {cfg['baslangic']}")
        self.log.emit(f"Veri: {cfg['data']}")
        self.log.emit(f"Ayarlar: {ayar}")

        try:
            model.train(**kw)
        except Exception as e:
            if self._iptal:
                self.log.emit("Eğitim iptal edildi.")
            else:
                self.failed.emit(f"{type(e).__name__}: {e}\n\n"
                                 + traceback.format_exc(limit=4))
                return

        tr = self._trainer
        dizin = str(getattr(tr, "save_dir", "") or
                    os.path.join(cfg["proje"], cfg["ad"]))
        best = os.path.join(dizin, "weights", "best.pt")
        last = os.path.join(dizin, "weights", "last.pt")
        self.done.emit({
            "best": best if os.path.exists(best) else "",
            "last": last if os.path.exists(last) else "",
            "dizin": dizin,
            "sure": time.time() - t0,
            "epoch": int(getattr(tr, "epoch", 0)) + 1 if tr is not None else 0,
            "iptal": self._iptal,
        })


# ─────────────────────────────────────────────── eğri çizimi

class EgriWidget(QWidget):
    """Epoch başına kayıp ve mAP eğrisi.

    Renk körlüğü dostu: kayıp mavi ve düz çizgi, mAP kehribar ve kesikli;
    ayrıca her ikisinin son değeri sayı olarak da yazılır.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._veri = []
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background:#ffffff; border:1px solid #d4dae2;")

    def sizeHint(self):
        return QSize(520, 230)

    def temizle(self):
        self._veri = []
        self.update()

    def ekle(self, d: dict):
        self._veri.append(d)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        sol, sag, ust, alt = 44, 44, 14, 26
        gw, gh = max(1, w - sol - sag), max(1, h - ust - alt)

        p.fillRect(self.rect(), QColor("#ffffff"))
        p.setPen(QPen(QColor("#e3e8ee"), 1))
        for i in range(5):
            y = ust + gh * i / 4
            p.drawLine(sol, int(y), sol + gw, int(y))

        f = QFont(); f.setPixelSize(10); p.setFont(f)
        if not self._veri:
            p.setPen(QColor("#8b95a3"))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Eğitim başlayınca kayıp ve mAP eğrisi burada çizilir")
            return

        n = len(self._veri)
        kayiplar = [d.get("loss") for d in self._veri if d.get("loss") is not None]
        maks_k = max(kayiplar) if kayiplar else 1.0
        maks_k = maks_k if maks_k > 0 else 1.0

        def x_at(i):
            return sol + (gw * i / max(1, n - 1) if n > 1 else gw / 2)

        # eksen yazıları
        p.setPen(QColor("#2e6da4"))
        for i in range(5):
            deger = maks_k * (1 - i / 4)
            p.drawText(2, int(ust + gh * i / 4) + 4, f"{deger:.2f}")
        p.setPen(QColor("#8a6d00"))
        for i in range(5):
            p.drawText(sol + gw + 6, int(ust + gh * i / 4) + 4, f"{1 - i / 4:.2f}")

        def ciz(anahtar, renk, kesikli, olcek):
            noktalar = [(x_at(i), ust + gh * (1 - min(1.0, (d.get(anahtar) or 0) / olcek)))
                        for i, d in enumerate(self._veri) if d.get(anahtar) is not None]
            if len(noktalar) < 2:
                if noktalar:
                    p.setPen(QPen(QColor(renk), 2))
                    p.drawEllipse(int(noktalar[0][0]) - 2, int(noktalar[0][1]) - 2, 4, 4)
                return
            pen = QPen(QColor(renk), 2)
            if kesikli:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            for a, b in zip(noktalar, noktalar[1:]):
                p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))

        ciz("loss", "#2e6da4", False, maks_k)
        ciz("map", "#f5c518", True, 1.0)

        son = self._veri[-1]
        p.setPen(QColor("#42505f"))
        etiket = f"epoch {son.get('epoch', n)}/{son.get('epochs', '?')}"
        if son.get("loss") is not None:
            etiket += f"   kayıp {son['loss']:.3f}"
        if son.get("map") is not None:
            etiket += f"   mAP50-95 {son['map']:.3f}"
        if son.get("map50") is not None:
            etiket += f"   mAP50 {son['map50']:.3f}"
        p.drawText(sol, h - 8, etiket)


# ─────────────────────────────────────────────── ana pencere

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Eğitim — veri setinden model")
        self.setMinimumSize(1240, 800)
        self._data_yaml = ""
        self._baslangic = ""      # kendi .pt'n (boşsa hazır ağırlık adı)
        self._proje = ""
        self._worker = None
        self._sizinti = None
        self._son_best = ""
        self._build_ui()
        self._build_menu()

    # ── UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self._build_left())
        sp.addWidget(self._build_right())
        sp.setSizes([390, 850])
        sp.setStretchFactor(1, 1)
        v.addWidget(sp, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("data.yaml seç → başlangıç ağırlığını seç → Eğitimi Başlat")

    def _path_row(self, edit: QLineEdit, slot, btn="Seç…") -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(4)
        edit.setReadOnly(True)
        h.addWidget(edit, 1)
        b = QPushButton(btn)
        b.setFixedWidth(60)
        b.clicked.connect(slot)
        h.addWidget(b)
        return h

    def _row(self, metin, widget) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        lbl = QLabel(metin)
        lbl.setStyleSheet("color:#42505f;")
        h.addWidget(lbl, 1)
        h.addWidget(widget)
        return h

    def _build_left(self) -> QWidget:
        kutu = QWidget()
        kutu.setMinimumWidth(340)
        kutu.setMaximumWidth(470)
        dis = QVBoxLayout(kutu)
        dis.setContentsMargins(0, 0, 0, 0)
        dis.setSpacing(0)

        kaydir = QScrollArea()
        kaydir.setWidgetResizable(True)
        kaydir.setFrameShape(QFrame.NoFrame)
        kaydir.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        ic = QWidget()
        v = QVBoxLayout(ic)
        v.setContentsMargins(6, 8, 6, 8)
        v.setSpacing(8)

        # veri
        g0 = QGroupBox("Veri seti")
        v0 = QVBoxLayout(g0)
        v0.addWidget(QLabel("data.yaml (Veri Denetçi ya da Labelapp çıktısı)"))
        self.data_edit = QLineEdit()
        self.data_edit.setPlaceholderText("data.yaml seç")
        v0.addLayout(self._path_row(self.data_edit, self._pick_data))
        self.data_info = QLabel("—")
        self.data_info.setWordWrap(True)
        self.data_info.setStyleSheet("color:#6b7686; font-size:11px;")
        v0.addWidget(self.data_info)

        self.leak_chk = QCheckBox("Eğitimden önce sızıntı denetimi yap")
        self.leak_chk.setChecked(True)
        self.leak_chk.setToolTip(
            "train ve val aynı sahnenin karelerini paylaşıyorsa doğrulama skoru\n"
            "gerçekte olduğundan yüksek çıkar. Denetim bunu eğitim başlamadan söyler.")
        v0.addWidget(self.leak_chk)
        v.addWidget(g0)

        # başlangıç ağırlığı
        g1 = QGroupBox("Başlangıç ağırlığı")
        v1 = QVBoxLayout(g1)
        self.hazir_combo = QComboBox()
        self.hazir_combo.addItems(HAZIR_MODELLER)
        self.hazir_combo.setCurrentText("yolo11n")
        v1.addLayout(self._row("Hazır ağırlık", self.hazir_combo))

        self.kendi_chk = QCheckBox("Kendi modelimden devam et (.pt)")
        self.kendi_chk.setToolTip(
            "Önceki turun best.pt'sini seçersen eğitim sıfırdan değil, o modelin\n"
            "üstüne devam eder — ince ayar döngüsünün çalışma biçimi budur.")
        self.kendi_chk.toggled.connect(self._on_kendi_toggled)
        v1.addWidget(self.kendi_chk)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("model.pt seç")
        self.model_edit.setEnabled(False)
        self.model_row = self._path_row(self.model_edit, self._pick_model)
        v1.addLayout(self.model_row)
        v.addWidget(g1)

        # eğitim ayarları
        g2 = QGroupBox("Eğitim ayarları")
        v2 = QVBoxLayout(g2)
        self.epochs_spin = QSpinBox()
        self.epochs_spin.setRange(1, 5000)
        self.epochs_spin.setValue(100)
        self.epochs_spin.setFixedWidth(90)
        v2.addLayout(self._row("Epoch", self.epochs_spin))

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 512)
        self.batch_spin.setValue(16)
        self.batch_spin.setFixedWidth(90)
        self.batch_spin.setToolTip("Bellek yetmezse düşür (ör. 8 ya da 4)")
        v2.addLayout(self._row("Batch", self.batch_spin))

        self.imgsz_spin = QSpinBox()
        self.imgsz_spin.setRange(160, 2048)
        self.imgsz_spin.setSingleStep(32)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setFixedWidth(90)
        v2.addLayout(self._row("Görsel boyutu", self.imgsz_spin))

        self.patience_spin = QSpinBox()
        self.patience_spin.setRange(0, 1000)
        self.patience_spin.setValue(50)
        self.patience_spin.setFixedWidth(90)
        self.patience_spin.setToolTip(
            "Erken durdurma: bu kadar epoch boyunca doğrulama skoru\n"
            "iyileşmezse eğitim kendiliğinden biter. 0 = kapalı.")
        v2.addLayout(self._row("Sabır (erken durdurma)", self.patience_spin))

        self.device_combo = QComboBox()
        cihaz_combo_doldur(self.device_combo)
        self.device_combo.setFixedWidth(150)
        v2.addLayout(self._row("Cihaz", self.device_combo))

        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(0, 32)
        self.workers_spin.setValue(0 if sys.platform == "darwin" else 8)
        self.workers_spin.setFixedWidth(90)
        self.workers_spin.setToolTip(
            "Veri yükleyici süreç sayısı. macOS'ta 0 önerilir: fazlası\n"
            "arayüzden başlatılan eğitimde takılmaya yol açabiliyor.")
        v2.addLayout(self._row("Yükleyici süreci", self.workers_spin))
        v.addWidget(g2)

        # ileri ayarlar
        g3 = QGroupBox("İleri ayarlar")
        v3 = QVBoxLayout(g3)
        self.optim_combo = QComboBox()
        self.optim_combo.addItems(["auto", "SGD", "Adam", "AdamW", "RMSProp"])
        self.optim_combo.setFixedWidth(110)
        v3.addLayout(self._row("Optimizer", self.optim_combo))

        self.lr_spin = QDoubleSpinBox()
        self.lr_spin.setDecimals(5)
        self.lr_spin.setRange(0.00001, 1.0)
        self.lr_spin.setSingleStep(0.001)
        self.lr_spin.setValue(0.01)
        self.lr_spin.setFixedWidth(110)
        self.lr_spin.setToolTip("optimizer=auto iken ultralytics bunu kendisi seçebilir")
        v3.addLayout(self._row("Başlangıç lr", self.lr_spin))

        self.freeze_spin = QSpinBox()
        self.freeze_spin.setRange(0, 24)
        self.freeze_spin.setFixedWidth(90)
        self.freeze_spin.setToolTip(
            "İlk N katmanı dondur. Az veriyle ince ayarda 10 civarı işe yarar;\n"
            "0 = hiçbir katman donmaz.")
        v3.addLayout(self._row("Dondurulacak katman", self.freeze_spin))

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 10 ** 6)
        self.seed_spin.setValue(0)
        self.seed_spin.setFixedWidth(90)
        v3.addLayout(self._row("Tohum", self.seed_spin))

        self.save_period_spin = QSpinBox()
        self.save_period_spin.setRange(0, 500)
        self.save_period_spin.setFixedWidth(90)
        self.save_period_spin.setToolTip("Her N epoch'ta ara ağırlık kaydet. 0 = kapalı.")
        v3.addLayout(self._row("Ara kayıt sıklığı", self.save_period_spin))

        self.resume_chk = QCheckBox("Yarım kalan eğitimi sürdür (resume)")
        self.resume_chk.setToolTip(
            "Kendi modelin olarak bir çalışmanın last.pt'sini seçtiysen, eğitim\n"
            "o çalışmanın kaldığı epoch'tan devam eder.")
        v3.addWidget(self.resume_chk)

        self.plots_chk = QCheckBox("ultralytics grafiklerini de üret")
        self.plots_chk.setChecked(True)
        v3.addWidget(self.plots_chk)
        v.addWidget(g3)

        v.addStretch()
        kaydir.setWidget(ic)
        dis.addWidget(kaydir, 1)

        # sabit şerit — iş bitince aranmasın
        serit = QWidget()
        sv = QVBoxLayout(serit)
        sv.setContentsMargins(6, 6, 6, 6)
        sv.setSpacing(6)

        sv.addWidget(QLabel("Çıktı klasörü"))
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("runs klasörü seç (boşsa data.yaml yanına)")
        sv.addLayout(self._path_row(self.out_edit, self._pick_out))

        h = QHBoxLayout()
        h.setSpacing(6)
        self.open_btn = QPushButton("Klasörü Aç")
        self.open_btn.clicked.connect(self._open_out)
        self.open_btn.setEnabled(False)
        h.addWidget(self.open_btn)
        self.copy_btn = QPushButton("best.pt Yolunu Kopyala")
        self.copy_btn.clicked.connect(self._copy_best)
        self.copy_btn.setEnabled(False)
        h.addWidget(self.copy_btn)
        sv.addLayout(h)

        self.start_btn = QPushButton("▶  Eğitimi Başlat")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.start_btn.clicked.connect(self._start)
        sv.addWidget(self.start_btn)

        h2 = QHBoxLayout()
        h2.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        h2.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("Durdur")
        self.cancel_btn.setFixedWidth(76)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setToolTip("Sıradaki epoch sınırında durur; o ana kadarki "
                                   "en iyi ağırlık korunur")
        self.cancel_btn.clicked.connect(self._cancel)
        h2.addWidget(self.cancel_btn)
        sv.addLayout(h2)
        dis.addWidget(serit)
        return kutu

    def _build_right(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.egri = EgriWidget()
        v.addWidget(self.egri, 2)

        self.tabs = QTabWidget()
        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.report_box.setPlainText(
            "Eğitim bitince özet buraya gelir.\n\n"
            "Akış: Veri Denetçi ile sızıntısız böl → burada eğit → çıkan best.pt'yi\n"
            "Hata Analizi'ne ver → eksik kalan kareleri etiketle → aynı best.pt'den\n"
            "devam ederek yeniden eğit.")
        self.tabs.addTab(self.report_box, "Rapor")

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs.addTab(self.log_box, "Log")
        v.addWidget(self.tabs, 3)
        return w

    def _build_menu(self):
        m = self.menuBar().addMenu("Dosya")
        for etiket, slot, kisayol in (
                ("data.yaml Seç…", self._pick_data, "Ctrl+O"),
                ("Model (.pt) Seç…", self._pick_model, "Ctrl+M"),
                ("Çıktı Klasörü Seç…", self._pick_out, ""),
                ("Kapat", self.close, "Ctrl+W")):
            a = QAction(etiket, self)
            if kisayol:
                a.setShortcut(kisayol)
            a.triggered.connect(slot)
            m.addAction(a)

    # ── seçimler
    def _log(self, t: str):
        self.log_box.append(t)

    def _pick_data(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "data.yaml seç", os.path.dirname(self._data_yaml) or "",
            "YAML (*.yaml *.yml)")
        if not p:
            return
        self._data_yaml = p
        self.data_edit.setText(p)
        self.data_edit.setToolTip(p)
        self.data_edit.setCursorPosition(0)
        self._oku_data(p)

    def _oku_data(self, p: str):
        try:
            import yaml
            with open(p, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception as e:
            self.data_info.setText(f"Okunamadı: {e}")
            return
        adlar = cfg.get("names")
        if isinstance(adlar, dict):
            adlar = [adlar[k] for k in sorted(adlar)]
        n = len(adlar) if adlar else cfg.get("nc", 0)
        parcalar = [f"{n} sınıf"]
        if adlar:
            gosterilen = ", ".join(str(a) for a in adlar[:8])
            if len(adlar) > 8:
                gosterilen += f" … (+{len(adlar) - 8})"
            parcalar.append(gosterilen)
        for k in ("train", "val", "test"):
            if cfg.get(k):
                parcalar.append(f"{k}: {cfg[k]}")
        self.data_info.setText("  |  ".join(parcalar))
        if not self.out_edit.text():
            self._proje = os.path.join(os.path.dirname(os.path.abspath(p)), "runs")
            self.out_edit.setText(self._proje)
            self.out_edit.setCursorPosition(0)

    def _on_kendi_toggled(self, on: bool):
        self.model_edit.setEnabled(on)
        self.hazir_combo.setEnabled(not on)

    def _pick_model(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Başlangıç ağırlığı seç", os.path.dirname(self._baslangic) or "",
            "PyTorch modeli (*.pt)")
        if not p:
            return
        self._baslangic = p
        self.model_edit.setText(p)
        self.model_edit.setToolTip(p)
        self.model_edit.setCursorPosition(0)
        self.kendi_chk.setChecked(True)

    def _pick_out(self):
        d = QFileDialog.getExistingDirectory(self, "Çıktı klasörü", self._proje or "")
        if not d:
            return
        self._proje = d
        self.out_edit.setText(d)
        self.out_edit.setCursorPosition(0)

    def _open_out(self):
        hedef = self._son_calisma or self._proje
        if hedef and os.path.isdir(hedef):
            klasoru_ac(hedef)

    def _copy_best(self):
        if self._son_best:
            QApplication.clipboard().setText(self._son_best)
            self.status.showMessage(f"Kopyalandı: {self._son_best}")

    # ── başlat
    _son_calisma = ""

    def _start(self):
        if self._worker or self._sizinti:
            return
        if not self._data_yaml or not os.path.exists(self._data_yaml):
            QMessageBox.warning(self, "Veri yok", "Önce bir data.yaml seç.")
            return
        if self.kendi_chk.isChecked():
            if not self._baslangic or not os.path.exists(self._baslangic):
                QMessageBox.warning(self, "Model yok",
                                    "Kendi modelinden devam etmek için bir .pt seç.")
                return
        proje = self.out_edit.text().strip() or os.path.join(
            os.path.dirname(os.path.abspath(self._data_yaml)), "runs")
        try:
            os.makedirs(proje, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Çıktı klasörü oluşturulamadı:\n{e}")
            return
        self._proje = proje

        if self.leak_chk.isChecked():
            self._sizinti_baslat()
        else:
            self._egitimi_baslat()

    def _sizinti_baslat(self):
        self.status.showMessage("Sızıntı denetimi: train ve val aynı kareleri paylaşıyor mu?")
        self._log("── sızıntı denetimi ──")
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._sizinti = SizintiIscisi(self._data_yaml)
        self._sizinti.log.connect(self._log)
        self._sizinti.progress.connect(
            lambda d, t: self.progress.setValue(int(100 * d / max(1, t))))
        self._sizinti.done.connect(self._sizinti_bitti)
        self._sizinti.finished.connect(lambda: setattr(self, "_sizinti", None))
        self._sizinti.start()

    def _sizinti_bitti(self, r: dict):
        self.progress.setVisible(False)
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        if r.get("iptal"):
            self.status.showMessage("Denetim iptal edildi.")
            return
        if r.get("hata"):
            if QMessageBox.question(
                    self, "Denetim yapılamadı",
                    f"{r['hata']}\n\nEğitime yine de devam edilsin mi?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self._egitimi_baslat()
            return
        if r.get("uyari"):
            self._log(r["uyari"])
            self._egitimi_baslat()
            return

        sizan = r.get("sizan", 0)
        self._log(f"train {r['train']}, val {r['val']} görsel; "
                  f"{r.get('orneklenen', 0)} tanesi tarandı → {sizan} sızıntı grubu")
        if not sizan:
            self._log("Sızıntı yok — train ve val ayrı sahnelerden.")
            self._egitimi_baslat()
            return

        ornek = "\n".join(f"    {a}  ↔  {b}" for a, b in r.get("ornekler", []))
        cevap = QMessageBox.question(
            self, "Sızıntı bulundu",
            f"{sizan} grup hem train hem val tarafında görünüyor — yani doğrulama "
            f"kümesi, modelin eğitimde gördüğü karelerin neredeyse aynısını "
            f"içeriyor.\n\nBu hâliyle çıkacak mAP gerçekte olduğundan yüksek olur.\n\n"
            f"Örnekler:\n{ornek}\n\n"
            f"Önerilen: Veri Denetçi'de 'Yakın-kopya grubu' ile yeniden böl.\n\n"
            f"Yine de eğitilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if cevap == QMessageBox.Yes:
            self._log("Sızıntıya rağmen devam edildi — skorları buna göre oku.")
            self._egitimi_baslat()
        else:
            self.status.showMessage("Eğitim başlatılmadı; önce bölmeyi düzelt.")

    def _egitimi_baslat(self):
        baslangic = (self._baslangic if self.kendi_chk.isChecked()
                     else self.hazir_combo.currentText() + ".pt")
        ad = time.strftime("egitim_%Y%m%d_%H%M")
        cfg = {
            "data": self._data_yaml,
            "baslangic": baslangic,
            "epochs": self.epochs_spin.value(),
            "batch": self.batch_spin.value(),
            "imgsz": self.imgsz_spin.value(),
            "patience": self.patience_spin.value(),
            "device": self.device_combo.currentData(),
            "workers": self.workers_spin.value(),
            "optimizer": self.optim_combo.currentText(),
            "lr0": float(self.lr_spin.value()),
            "freeze": self.freeze_spin.value() or None,
            "seed": self.seed_spin.value(),
            "save_period": self.save_period_spin.value(),
            "resume": self.resume_chk.isChecked() and self.kendi_chk.isChecked(),
            "plots": self.plots_chk.isChecked(),
            "proje": self._proje,
            "ad": ad,
        }
        self.egri.temizle()
        self.progress.setVisible(True)
        self.progress.setRange(0, cfg["epochs"])
        self.progress.setValue(0)
        self.progress.setFormat("epoch %v / %m")
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.tabs.setCurrentIndex(1)
        self.status.showMessage("Eğitim sürüyor…")
        self._log(f"── eğitim: {ad} ──")

        self._worker = EgitimIscisi(cfg)
        self._worker.log.connect(self._log)
        self._worker.epoch.connect(self._on_epoch)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._on_done)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _cancel(self):
        if self._sizinti:
            self._sizinti.iptal()
            return
        if self._worker:
            self._worker.iptal()
            self.cancel_btn.setEnabled(False)
            self.status.showMessage("Durduruluyor — sıradaki epoch sınırında bitecek…")

    # ── geri bildirim
    def _on_epoch(self, d: dict):
        self.egri.ekle(d)
        self.progress.setMaximum(d.get("epochs") or self.progress.maximum())
        self.progress.setValue(d.get("epoch", 0))
        parcalar = [f"epoch {d.get('epoch')}/{d.get('epochs')}"]
        if d.get("loss") is not None:
            parcalar.append(f"kayıp {d['loss']:.4f}")
        if d.get("map50") is not None:
            parcalar.append(f"mAP50 {d['map50']:.4f}")
        if d.get("map") is not None:
            parcalar.append(f"mAP50-95 {d['map']:.4f}")
        self._log("  ".join(parcalar))
        self.status.showMessage("  ".join(parcalar))

    def _on_failed(self, msg: str):
        self._log("HATA — " + msg)
        QMessageBox.critical(self, "Eğitim başarısız", msg)
        self.status.showMessage("Eğitim başarısız.")

    def _on_done(self, r: dict):
        self._son_best = r.get("best", "")
        self._son_calisma = r.get("dizin", "")
        self.open_btn.setEnabled(bool(self._son_calisma))
        self.copy_btn.setEnabled(bool(self._son_best))

        dk = r.get("sure", 0) / 60
        sat = ["═══ EĞİTİM ÖZETİ ═══", ""]
        sat.append(f"durum        : {'iptal edildi' if r.get('iptal') else 'tamamlandı'}")
        sat.append(f"epoch        : {r.get('epoch', 0)}")
        sat.append(f"süre         : {dk:.1f} dk")
        sat.append(f"çalışma      : {r.get('dizin', '—')}")
        sat.append(f"best.pt      : {r.get('best') or '— (yazılmadı)'}")
        sat.append(f"last.pt      : {r.get('last') or '—'}")

        if self.egri._veri:
            son = self.egri._veri[-1]
            en_iyi = max((d for d in self.egri._veri if d.get("map") is not None),
                         key=lambda d: d["map"], default=None)
            sat += ["", "── son epoch ──"]
            for etiket, anahtar in (("kayıp", "loss"), ("mAP50", "map50"),
                                    ("mAP50-95", "map")):
                if son.get(anahtar) is not None:
                    sat.append(f"{etiket:<12s} : {son[anahtar]:.4f}")
            if en_iyi is not None:
                sat.append(f"en iyi mAP50-95 : {en_iyi['map']:.4f} "
                           f"(epoch {en_iyi['epoch']})")

        sat += ["", "── sırada ne var ──",
                "1. best.pt'yi Hata Analizi'ne ver: model nerede yanılıyor?",
                "2. Aktif Öğrenme ile etiketlenecek kareleri sırala.",
                "3. Eksikleri Labelapp'te etiketle, Veri Denetçi ile yeniden böl.",
                "4. Buraya dön, 'Kendi modelimden devam et' ile best.pt'yi seç."]
        if not r.get("best"):
            sat += ["", "! best.pt yazılmadı — eğitim ilk doğrulamaya varmadan "
                        "bitmiş olabilir."]

        self.report_box.setPlainText("\n".join(sat))
        self.tabs.setCurrentIndex(0)
        self.status.showMessage(
            f"Eğitim {'iptal edildi' if r.get('iptal') else 'bitti'} — {dk:.1f} dk")

    def _on_worker_finished(self):
        self._worker = None
        self.progress.setVisible(False)
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    # ── kapanış
    def closeEvent(self, olay):
        if self._worker is not None and self._worker.isRunning():
            if QMessageBox.question(
                    self, "Eğitim sürüyor",
                    "Eğitim hâlâ çalışıyor. Durdurup kapatılsın mı?\n"
                    "(O ana kadarki en iyi ağırlık diskte kalır.)",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                olay.ignore()
                return
            self._worker.iptal()
            self._worker.wait(15000)
        if self._sizinti is not None and self._sizinti.isRunning():
            self._sizinti.iptal()
            self._sizinti.wait(5000)
        olay.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
