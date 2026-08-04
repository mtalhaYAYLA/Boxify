"""Oto Label — elindeki YOLO modeliyle fotoğrafları tek tek etiketleyip
YOLO formatında kaydeder. Çıktı doğrudan yeniden eğitim için kullanılabilir.

Kullanım: model (.pt) + fotoğraf klasörü + çıktı klasörü seç → Başlat.
"""
import os
import sys
import shutil
import traceback

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog, QFrame,
    QStatusBar, QGroupBox, QMessageBox, QLineEdit, QAction, QSizePolicy,
    QComboBox, QProgressBar, QCheckBox, QDoubleSpinBox, QSpinBox, QTextEdit,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

from ..tema import STYLE  # ortak açık tema — bkz. boxify/tema.py
from .model_bilgi import SinifYukleyici

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

# Durum işaretleri (renk yerine sembol; renk sadece destek)
MARK_OK = "✓"      # tespit var
MARK_EMPTY = "–"   # tespit yok
MARK_ERR = "!"     # hata
MARK_SKIP = "»"    # atlandı (zaten etiketli)


def out_stem(path: str, img_dir: str) -> str:
    """Çıktı dosya adı: alt klasördeki görsellere klasör yolu ön ek yapılır.

    kamera1/frame_001.jpg → kamera1_frame_001
    frame_001.jpg         → frame_001        (kök klasörde ön ek yok)
    Böylece ayrı klasörlerdeki aynı isimli dosyalar birbirini ezmez.
    """
    try:
        rel = os.path.relpath(path, img_dir)
    except ValueError:                       # farklı sürücü/kök
        rel = os.path.basename(path)
    rel_dir = os.path.dirname(rel)
    stem = os.path.splitext(os.path.basename(path))[0]
    if rel_dir and rel_dir != "." and not rel_dir.startswith(os.pardir):
        return rel_dir.replace(os.sep, "_").strip("_") + "_" + stem
    return stem


def list_images(folder: str, recursive: bool) -> list:
    out = []
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in files:
                if f.lower().endswith(IMG_EXTS):
                    out.append(os.path.join(root, f))
    else:
        for f in os.listdir(folder):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and f.lower().endswith(IMG_EXTS):
                out.append(p)
    return sorted(out)


class LabelWorker(QThread):
    """Modeli yükler, görselleri tek tek işler, YOLO txt yazar."""
    model_ready = pyqtSignal(dict)                  # {id: isim}
    image_done = pyqtSignal(int, str, int, str)     # index, dosya, tespit, durum
    preview = pyqtSignal(object)                    # QImage
    progress = pyqtSignal(int, int)                 # işlenen, toplam
    log = pyqtSignal(str)
    failed = pyqtSignal(str)
    summary = pyqtSignal(dict)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    # ── yardımcılar
    def _write_yaml(self, names: dict):
        out_dir = self.cfg["out_dir"]
        with open(os.path.join(out_dir, "classes.txt"), "w", encoding="utf-8") as f:
            for i in sorted(names):
                f.write(f"{names[i]}\n")
        img_sub = "images" if self.cfg["copy_images"] else self.cfg["img_dir"]
        with open(os.path.join(out_dir, "data.yaml"), "w", encoding="utf-8") as f:
            f.write(f"path: {out_dir}\n")
            f.write(f"train: {img_sub}\n")
            f.write(f"val: {img_sub}\n")
            f.write(f"nc: {len(names)}\n")
            f.write("names:\n")
            for i in sorted(names):
                f.write(f"  {i}: {names[i]}\n")

    def run(self):
        cfg = self.cfg
        try:
            from ultralytics import YOLO
            import cv2
        except Exception as e:
            self.failed.emit(f"ultralytics/opencv içe aktarılamadı:\n{e}")
            return

        try:
            self.log.emit(f"Model yükleniyor: {cfg['model_path']}")
            model = YOLO(cfg["model_path"])
            names = dict(model.names)
            self.model_ready.emit(names)
            self.log.emit(f"Model hazır — {len(names)} sınıf: "
                          + ", ".join(names[i] for i in sorted(names)))
        except Exception as e:
            self.failed.emit(f"Model yüklenemedi:\n{e}")
            return

        images = cfg["images"]
        lbl_dir = os.path.join(cfg["out_dir"], "labels")
        os.makedirs(lbl_dir, exist_ok=True)
        img_out_dir = os.path.join(cfg["out_dir"], "images")
        if cfg["copy_images"]:
            os.makedirs(img_out_dir, exist_ok=True)
        pred_dir = os.path.join(cfg["out_dir"], "predictions")
        if cfg["save_preview_files"]:
            os.makedirs(pred_dir, exist_ok=True)

        stats = {"islenen": 0, "tespitli": 0, "bos": 0, "atlanan": 0, "hatali": 0,
                 "tespit_toplam": 0, "sinif": {}}
        used_stems = {}          # çıktı adı çakışmalarını engellemek için
        prefix_bildirildi = False

        for idx, path in enumerate(images):
            if self._cancel:
                self.log.emit("İptal edildi.")
                break

            stem = out_stem(path, cfg["img_dir"])
            if stem in used_stems:                    # nadir: iki yol aynı ada düşerse
                used_stems[stem] += 1
                stem = f"{stem}__{used_stems[stem]}"
            else:
                used_stems[stem] = 0
            if not prefix_bildirildi and stem != os.path.splitext(os.path.basename(path))[0]:
                prefix_bildirildi = True
                self.log.emit("Alt klasördeki görsellere klasör ön eki ekleniyor "
                              f"(örn. {stem}) — aynı isimli dosyalar çakışmıyor.")
            ext = os.path.splitext(path)[1]
            txt_path = os.path.join(lbl_dir, stem + ".txt")

            if cfg["skip_existing"] and os.path.exists(txt_path):
                stats["atlanan"] += 1
                self.image_done.emit(idx, path, -1, MARK_SKIP)
                self.progress.emit(idx + 1, len(images))
                continue

            try:
                res = model.predict(
                    source=path,
                    conf=cfg["conf"], iou=cfg["iou"], imgsz=cfg["imgsz"],
                    device=cfg["device"], classes=cfg["classes"] or None,
                    max_det=cfg["max_det"], verbose=False,
                )[0]

                boxes = res.boxes
                n = 0 if boxes is None else len(boxes)
                lines = []
                if n:
                    xywhn = boxes.xywhn.cpu().numpy()
                    clss = boxes.cls.cpu().numpy().astype(int)
                    confs = boxes.conf.cpu().numpy()
                    for (x, y, w, h), c, cf in zip(xywhn, clss, confs):
                        if cfg["save_conf"]:
                            lines.append(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f} {cf:.4f}")
                        else:
                            lines.append(f"{c} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
                        cname = names.get(int(c), str(c))
                        stats["sinif"][cname] = stats["sinif"].get(cname, 0) + 1
                    stats["tespit_toplam"] += n

                if n or cfg["write_empty"]:
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write("\n".join(lines) + ("\n" if lines else ""))

                if cfg["copy_images"] and (n or cfg["write_empty"]):
                    dst = os.path.join(img_out_dir, stem + ext)
                    if os.path.abspath(dst) != os.path.abspath(path):
                        shutil.copy2(path, dst)      # birebir kopya, yeniden kodlama yok

                # görselleştirme (önizleme ve/veya diske kayıt)
                if cfg["show_preview"] or cfg["save_preview_files"]:
                    drawn = res.plot()                       # BGR ndarray
                    if cfg["save_preview_files"]:
                        cv2.imwrite(os.path.join(pred_dir, stem + ext), drawn)
                    if cfg["show_preview"]:
                        h0, w0 = drawn.shape[:2]
                        scale = min(1.0, 900.0 / max(h0, w0))
                        if scale < 1.0:
                            drawn = cv2.resize(drawn, (int(w0 * scale), int(h0 * scale)),
                                               interpolation=cv2.INTER_AREA)
                        rgb = drawn[:, :, ::-1].copy()
                        h1, w1 = rgb.shape[:2]
                        self.preview.emit(
                            QImage(rgb.data, w1, h1, 3 * w1, QImage.Format_RGB888).copy())

                stats["islenen"] += 1
                if n:
                    stats["tespitli"] += 1
                else:
                    stats["bos"] += 1
                self.image_done.emit(idx, path, n, MARK_OK if n else MARK_EMPTY)

            except Exception as e:
                stats["hatali"] += 1
                self.image_done.emit(idx, path, 0, MARK_ERR)
                self.log.emit(f"HATA — {os.path.basename(path)}: {e}")
                self.log.emit(traceback.format_exc(limit=2).strip())

            self.progress.emit(idx + 1, len(images))

        if cfg["write_yaml"]:
            try:
                self._write_yaml(names)
                self.log.emit("classes.txt ve data.yaml yazıldı.")
            except Exception as e:
                self.log.emit(f"HATA — data.yaml yazılamadı: {e}")

        stats["iptal"] = self._cancel
        self.summary.emit(stats)


class PreviewLabel(QLabel):
    """Görseli oranını koruyarak pencereye sığdırır."""

    def __init__(self):
        super().__init__("Önizleme — soldaki listeden bir görsel seç")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#eceff3; color:#6b7686; border:1px dashed #b4bfcb; border-radius:8px; font-size:13px;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(240)
        self._img = None

    def set_image(self, img: QImage):
        self._img = img
        self._redraw()

    def clear_image(self):
        self._img = None
        self.setText("Önizleme — soldaki listeden bir görsel seç")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._redraw()

    def _redraw(self):
        if self._img is None:
            return
        pix = QPixmap.fromImage(self._img).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pix)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Oto Label — YOLO ile otomatik etiketleme")
        self.setMinimumSize(1280, 780)
        self._model_path = ""
        self._img_dir = ""
        self._out_dir = ""
        self._images = []
        self._names = {}
        self._worker = None
        self._sinif_yukleyici = None
        self._build_ui()
        self._build_menu()

    # ─────────────────────────────── UI

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_file_list())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([260, 700, 340])
        vbox.addWidget(splitter, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Model, fotoğraf klasörü ve çıktı klasörünü seçip Başlat'a bas")

    def _build_file_list(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(220)
        w.setMaximumWidth(340)
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)

        lbl = QLabel("Fotoğraflar")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:2px 4px;")
        v.addWidget(lbl)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.file_list.currentRowChanged.connect(self._show_selected)
        v.addWidget(self.file_list, 1)

        self.file_count_lbl = QLabel("0 görsel")
        self.file_count_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(self.file_count_lbl)
        return w

    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.preview = PreviewLabel()
        v.addWidget(self.preview, 1)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(150)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        v.addWidget(self.log_box)
        return w

    def _dir_row(self, edit: QLineEdit, slot) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        edit.setReadOnly(True)
        edit.setStyleSheet("font-size:11px; font-family:monospace;")
        h.addWidget(edit, 1)
        b = QPushButton("Seç…")
        b.setFixedWidth(60)
        b.clicked.connect(slot)
        h.addWidget(b)
        return h

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(320)
        w.setMaximumWidth(420)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        # ── Model
        grp_m = QGroupBox("Model")
        gm = QVBoxLayout(grp_m)
        gm.setSpacing(6)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("model.pt seç")
        gm.addLayout(self._dir_row(self.model_edit, self._pick_model))
        self.model_info_lbl = QLabel("Sınıflar: —")
        self.model_info_lbl.setWordWrap(True)
        self.model_info_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        gm.addWidget(self.model_info_lbl)
        v.addWidget(grp_m)

        # ── Girdi
        grp_i = QGroupBox("Fotoğraf Klasörü")
        gi = QVBoxLayout(grp_i)
        gi.setSpacing(6)
        self.img_edit = QLineEdit()
        self.img_edit.setPlaceholderText("fotoğrafların olduğu klasör")
        gi.addLayout(self._dir_row(self.img_edit, self._pick_img_dir))
        self.recursive_chk = QCheckBox("Alt klasörleri de tara")
        self.recursive_chk.toggled.connect(self._rescan_images)
        gi.addWidget(self.recursive_chk)
        v.addWidget(grp_i)

        # ── Çıktı
        grp_o = QGroupBox("Çıktı Klasörü")
        go = QVBoxLayout(grp_o)
        go.setSpacing(6)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("etiketlerin kaydedileceği klasör")
        go.addLayout(self._dir_row(self.out_edit, self._pick_out_dir))

        self.copy_img_chk = QCheckBox("Görselleri de kopyala (images/)")
        self.copy_img_chk.setChecked(True)
        self.copy_img_chk.setToolTip("Eğitime hazır yapı: images/ + labels/")
        go.addWidget(self.copy_img_chk)

        self.yaml_chk = QCheckBox("data.yaml + classes.txt yaz")
        self.yaml_chk.setChecked(True)
        go.addWidget(self.yaml_chk)

        self.empty_chk = QCheckBox("Tespit yoksa boş .txt yaz")
        self.empty_chk.setChecked(True)
        self.empty_chk.setToolTip("Negatif örnek olarak eğitimde kullanılır")
        go.addWidget(self.empty_chk)

        self.pred_chk = QCheckBox("Çizimli önizlemeleri kaydet (predictions/)")
        self.pred_chk.setToolTip("Kontrol için kutuları çizili kopyalar")
        go.addWidget(self.pred_chk)

        self.skip_chk = QCheckBox("Zaten etiketlenmişleri atla")
        self.skip_chk.setChecked(True)
        self.skip_chk.setToolTip("Yarıda kalan işi kaldığı yerden sürdürür")
        go.addWidget(self.skip_chk)

        self.conf_col_chk = QCheckBox("txt'ye güven değerini de yaz")
        self.conf_col_chk.setToolTip("6. kolon olarak güven; ultralytics eğitimi bunu "
                                     "beklemez, sadece inceleme için")
        go.addWidget(self.conf_col_chk)
        v.addWidget(grp_o)

        # ── Çıkarım ayarları
        grp_p = QGroupBox("Çıkarım Ayarları")
        gp = QVBoxLayout(grp_p)
        gp.setSpacing(6)

        def spin_row(text, widget):
            h = QHBoxLayout()
            lb = QLabel(text)
            lb.setStyleSheet("font-weight:normal;")
            h.addWidget(lb)
            h.addStretch()
            h.addWidget(widget)
            return h

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.01, 0.99)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.25)
        self.conf_spin.setFixedWidth(90)
        gp.addLayout(spin_row("Güven eşiği (conf)", self.conf_spin))

        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.1, 0.95)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setValue(0.45)
        self.iou_spin.setFixedWidth(90)
        gp.addLayout(spin_row("NMS IoU", self.iou_spin))

        self.imgsz_spin = QSpinBox()
        self.imgsz_spin.setRange(160, 2048)
        self.imgsz_spin.setSingleStep(32)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setFixedWidth(90)
        gp.addLayout(spin_row("Görsel boyutu", self.imgsz_spin))

        self.maxdet_spin = QSpinBox()
        self.maxdet_spin.setRange(1, 1000)
        self.maxdet_spin.setValue(300)
        self.maxdet_spin.setFixedWidth(90)
        gp.addLayout(spin_row("Maks tespit", self.maxdet_spin))

        self.device_combo = QComboBox()
        self.device_combo.addItem("Otomatik", None)
        self.device_combo.addItem("GPU (cuda:0)", 0)
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.setFixedWidth(140)
        gp.addLayout(spin_row("Cihaz", self.device_combo))

        self.show_preview_chk = QCheckBox("İşlerken önizleme göster")
        self.show_preview_chk.setChecked(True)
        self.show_preview_chk.setToolTip("Kapatmak işlemi hızlandırır")
        gp.addWidget(self.show_preview_chk)

        gp.addWidget(QLabel("Sınıf filtresi (boş = hepsi)"))
        self.class_list = QListWidget()
        self.class_list.setMaximumHeight(110)
        self.class_list.setToolTip("Kutucuğu işaretlenen sınıflar etiketlenir; "
                                   "hiçbiri işaretli değilse hepsi")
        gp.addWidget(self.class_list)
        v.addWidget(grp_p)

        # ── Çalıştır
        self.start_btn = QPushButton("▶  Etiketlemeyi Başlat")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.start_btn.clicked.connect(self._start)
        v.addWidget(self.start_btn)

        h_run = QHBoxLayout()
        h_run.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        h_run.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setFixedWidth(70)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        h_run.addWidget(self.cancel_btn)
        v.addLayout(h_run)

        self.stats_lbl = QLabel("—")
        self.stats_lbl.setWordWrap(True)
        self.stats_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(self.stats_lbl)

        v.addStretch()
        return w

    def _build_menu(self):
        file_m = self.menuBar().addMenu("Dosya")

        def act(label, slot, shortcut=""):
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            file_m.addAction(a)

        act("Model Seç…", self._pick_model, "Ctrl+M")
        act("Fotoğraf Klasörü…", self._pick_img_dir, "Ctrl+O")
        act("Çıktı Klasörü…", self._pick_out_dir, "Ctrl+S")
        file_m.addSeparator()
        act("Çıktı Klasörünü Aç", self._open_out_dir)
        file_m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    # ─────────────────────────────── seçimler

    def _log(self, text: str):
        self.log_box.append(text)

    def _pick_model(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "YOLO modeli seç", self._model_path or "",
            "YOLO modeli (*.pt *.engine *.onnx);;Tüm Dosyalar (*)")
        if not p:
            return
        self._model_path = p
        self.model_edit.setText(p)
        self.model_edit.setToolTip(p)
        self.model_edit.setCursorPosition(0)
        self.status.showMessage(f"Model: {os.path.basename(p)}")
        self._load_class_names(p)

    def _load_class_names(self, path: str):
        """Sınıf listesini modelden oku (filtre kutuları için).

        Okuma arka planda yapılır: `from ultralytics import YOLO` ilk çağrıda
        torch'u da yükler ve bu, arayüz iş parçacığında saniyelerce süren bir
        donma demektir.
        """
        self.model_info_lbl.setText("Sınıflar okunuyor…")
        self.class_list.clear()
        eski = getattr(self, "_sinif_yukleyici", None)
        if eski is not None:
            try:
                eski.tamamlandi.disconnect()
            except TypeError:
                pass
        self._sinif_yukleyici = SinifYukleyici(path, self)
        self._sinif_yukleyici.tamamlandi.connect(self._on_class_names)
        self._sinif_yukleyici.start()

    def _on_class_names(self, yol: str, names: dict, hata: str):
        yukleyici = getattr(self, "_sinif_yukleyici", None)
        if yukleyici is not None:
            yukleyici.deleteLater()
        self._sinif_yukleyici = None
        # Kullanıcı bu arada başka model seçtiyse geç gelen sonucu yut
        if yol != self._model_path:
            return
        if hata:
            self.model_info_lbl.setText("Sınıflar okunamadı (Başlat'ta tekrar denenecek)")
            self._log(f"Model sınıfları okunamadı: {hata}")
            return
        self._set_names(names)

    def _set_names(self, names: dict):
        self._names = names
        self.class_list.clear()
        for i in sorted(names):
            it = QListWidgetItem(f"{i}  {names[i]}")
            it.setData(Qt.UserRole, i)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.class_list.addItem(it)
        self.model_info_lbl.setText(
            f"{len(names)} sınıf: " + ", ".join(names[i] for i in sorted(names)))

    def _pick_img_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Fotoğrafların olduğu klasör",
                                             self._img_dir or "")
        if not d:
            return
        self._img_dir = d
        self.img_edit.setText(d)
        self.img_edit.setToolTip(d)
        self.img_edit.setCursorPosition(0)
        self._rescan_images()

    def _rescan_images(self):
        if not self._img_dir:
            return
        self._images = list_images(self._img_dir, self.recursive_chk.isChecked())
        self.file_list.clear()
        for p in self._images:
            it = QListWidgetItem(os.path.basename(p))
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            self.file_list.addItem(it)
        self.file_count_lbl.setText(f"{len(self._images)} görsel")
        self.status.showMessage(f"{len(self._images)} görsel bulundu: {self._img_dir}")
        if self._images:
            self.file_list.setCurrentRow(0)

    def _pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Etiketlerin kaydedileceği klasör",
                                             self._out_dir or self._img_dir or "")
        if not d:
            return
        self._out_dir = d
        self.out_edit.setText(d)
        self.out_edit.setToolTip(d)
        self.out_edit.setCursorPosition(0)

    def _open_out_dir(self):
        if not self._out_dir:
            return
        try:
            from ..klasor_ac import klasoru_ac
            klasoru_ac(self._out_dir)
        except Exception as e:
            self.status.showMessage(f"HATA: klasör açılamadı — {e}")

    def _show_selected(self, row: int):
        """Listeden seçilen görseli göster (etiketlenmişse çizimli kopyayı)."""
        if row < 0 or row >= len(self._images):
            return
        path = self._images[row]
        shown = path
        if self._out_dir and self._img_dir:
            # çizimli kopya, çıktıdaki adıyla aranır (alt klasör ön eki dahil)
            pred = os.path.join(self._out_dir, "predictions",
                                out_stem(path, self._img_dir) + os.path.splitext(path)[1])
            if os.path.exists(pred):
                shown = pred
        img = QImage(shown)
        if img.isNull():
            self.preview.clear_image()
            return
        self.preview.set_image(img)

    # ─────────────────────────────── çalıştırma

    def _checked_classes(self) -> list:
        out = []
        for i in range(self.class_list.count()):
            it = self.class_list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

    def _start(self):
        if self._worker:
            return
        if not self._model_path or not os.path.exists(self._model_path):
            QMessageBox.warning(self, "Model yok", "Geçerli bir model (.pt) seç.")
            return
        if not self._img_dir or not self._images:
            QMessageBox.warning(self, "Fotoğraf yok",
                                "Fotoğraf klasörü seç (klasörde desteklenen görsel bulunamadı).")
            return
        if not self._out_dir:
            QMessageBox.warning(self, "Çıktı klasörü yok",
                                "Etiketlerin kaydedileceği klasörü seç.")
            return
        if os.path.abspath(self._out_dir) == os.path.abspath(self._img_dir) \
                and self.copy_img_chk.isChecked():
            if QMessageBox.question(
                    self, "Aynı klasör",
                    "Çıktı klasörü fotoğraf klasörüyle aynı.\n"
                    "Görseller images/ altına kopyalanacak. Devam edilsin mi?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        try:
            os.makedirs(self._out_dir, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Çıktı klasörü oluşturulamadı:\n{e}")
            return

        cfg = {
            "model_path": self._model_path,
            "images": list(self._images),
            "img_dir": self._img_dir,
            "out_dir": self._out_dir,
            "conf": float(self.conf_spin.value()),
            "iou": float(self.iou_spin.value()),
            "imgsz": int(self.imgsz_spin.value()),
            "max_det": int(self.maxdet_spin.value()),
            "device": self.device_combo.currentData(),
            "classes": self._checked_classes(),
            "copy_images": self.copy_img_chk.isChecked(),
            "write_yaml": self.yaml_chk.isChecked(),
            "write_empty": self.empty_chk.isChecked(),
            "save_preview_files": self.pred_chk.isChecked(),
            "skip_existing": self.skip_chk.isChecked(),
            "save_conf": self.conf_col_chk.isChecked(),
            "show_preview": self.show_preview_chk.isChecked(),
        }

        self.log_box.clear()
        self._log(f"{len(self._images)} görsel işlenecek → {self._out_dir}")
        if cfg["classes"]:
            self._log("Sınıf filtresi: " + ", ".join(
                str(self._names.get(c, c)) for c in cfg["classes"]))

        self._worker = LabelWorker(cfg)
        self._worker.model_ready.connect(self._on_model_ready)
        self._worker.image_done.connect(self._on_image_done)
        self._worker.preview.connect(self.preview.set_image)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log)
        self._worker.failed.connect(self._on_failed)
        self._worker.summary.connect(self._on_summary)
        self._worker.finished.connect(self._on_worker_finished)

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self.status.showMessage("İptal isteniyor… (işlenen görsel bitince duracak)")

    def _on_model_ready(self, names: dict):
        if not self._names:
            self._set_names(names)

    def _on_image_done(self, idx: int, path: str, n: int, mark: str):
        it = self.file_list.item(idx)
        if it is None:
            return
        base = os.path.basename(path)
        if mark == MARK_SKIP:
            it.setText(f"{MARK_SKIP} {base}  (atlandı)")
        elif mark == MARK_ERR:
            it.setText(f"{MARK_ERR} {base}  (hata)")
        else:
            it.setText(f"{mark} {base}  ({n} nesne)")
        self.file_list.scrollToItem(it)

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status.showMessage(f"İşleniyor: {done}/{total}")

    def _on_failed(self, msg: str):
        self._log("HATA: " + msg)
        QMessageBox.critical(self, "Hata", msg)

    def _on_summary(self, s: dict):
        siniflar = ", ".join(f"{k}: {v}" for k, v in
                             sorted(s["sinif"].items(), key=lambda kv: -kv[1]))
        text = (f"İşlenen {s['islenen']} | tespitli {s['tespitli']} | boş {s['bos']} | "
                f"atlanan {s['atlanan']} | hatalı {s['hatali']}\n"
                f"Toplam {s['tespit_toplam']} nesne")
        if siniflar:
            text += f"\n{siniflar}"
        if s.get("iptal"):
            text += "\n(iptal edildi)"
        self.stats_lbl.setText(text)
        self._log("── Özet ──\n" + text)
        self.status.showMessage("Bitti. " + text.replace("\n", "  |  "))

    def _on_worker_finished(self):
        self._worker = None
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def closeEvent(self, ev):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(5000)
        if self._sinif_yukleyici is not None:
            self._sinif_yukleyici.wait(3000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Oto Label")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
