"""Hata Analizi — eğitilmiş modelin nerede yanıldığını gösterir ve
sıradaki etiketlenecek kareleri seçer.

İki sekme:
  1. Değerlendirme : model + etiketli veri → kaçırılan (FN), uydurulan (FP),
                     sınıf karışıklıkları, karışıklık matrisi, en kötü görseller
  2. Aktif öğrenme : model + etiketsiz havuz → modelin en çok tereddüt ettiği
                     kareleri sıraya koyar (etiketlemeye onlardan başla)

Bağımlılık: PyQt5, ultralytics, opencv-python, numpy.
"""
import os
import sys
import shutil

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog, QStatusBar,
    QGroupBox, QMessageBox, QLineEdit, QAction, QSizePolicy, QComboBox,
    QProgressBar, QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTabWidget,
    QAbstractItemView, QInputDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF, QLineF
from PyQt5.QtGui import QImage, QPainter, QPen, QColor, QFont

from ..tema import STYLE  # ortak açık tema — bkz. boxify/tema.py
from .model_bilgi import SinifYukleyici, sinif_ozeti, cihaz_combo_doldur

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

# Hata türü renkleri — kırmızı-yeşil ayrımına dayanmaz, ayrıca çizgi deseni farklı
COL_TP = "#2e6da4"      # doğru tespit        — düz mavi
COL_FP = "#f5c518"      # uydurma (FP)        — noktalı sarı
COL_FN = "#00bcd4"      # kaçırılan (FN)      — kalın kesikli camgöbeği
COL_CONF = "#b39ddb"    # sınıf karışıklığı   — düz mor
COL_GT = "#9e9e9e"      # referans etiket     — ince kesikli gri


# ─────────────────────────────────────────────── yardımcılar

def list_images(folder: str) -> list:
    out = []
    for root, _d, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(IMG_EXTS):
                out.append(os.path.join(root, f))
    return sorted(out)


def read_gt(path: str) -> list:
    """YOLO txt → [(cls, x, y, w, h)] normalize. Bozuk satırları atlar."""
    boxes = []
    if not path or not os.path.exists(path):
        return boxes
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                p = line.split()
                if len(p) < 5:
                    continue
                try:
                    c = int(float(p[0]))
                    x, y, w, h = (float(v) for v in p[1:5])
                except ValueError:
                    continue
                if w > 0 and h > 0:
                    boxes.append((c, x, y, w, h))
    except OSError:
        pass
    return boxes


def xywhn_to_xyxy(box, W: int, H: int):
    _c, x, y, w, h = box
    return ((x - w / 2) * W, (y - h / 2) * H, (x + w / 2) * W, (y + h / 2) * H)


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def match_boxes(gt_px: list, pred_px: list, iou_thr: float):
    """Sınıftan bağımsız IoU eşleştirme (sınıf karışıklığını görebilmek için).

    gt_px  : [(cls, x1,y1,x2,y2)]
    pred_px: [(cls, conf, x1,y1,x2,y2)]  güvene göre azalan sıralı
    → (tahmin sonuçları, eşleşmeyen gt indeksleri)
      sonuç: ("tp"|"conf"|"fp", gt_index|None, iou)
    """
    used = set()
    results = []
    for p in pred_px:
        best_i, best_v = -1, 0.0
        for gi, g in enumerate(gt_px):
            if gi in used:
                continue
            v = iou(p[2:], g[1:])
            if v > best_v:
                best_i, best_v = gi, v
        if best_v >= iou_thr and best_i >= 0:
            used.add(best_i)
            kind = "tp" if gt_px[best_i][0] == p[0] else "conf"
            results.append((kind, best_i, best_v))
        else:
            results.append(("fp", None, best_v))
    fns = [gi for gi in range(len(gt_px)) if gi not in used]
    return results, fns


def bar(n, maxn, width=18) -> str:
    filled = int(round(width * n / max(1, maxn)))
    return "█" * filled + "·" * (width - filled)


def find_label(img_path: str, img_dir: str, lbl_dir: str) -> str:
    """Görselin etiketini bul: aynı köke göre alt klasör yapısını da dener."""
    stem = os.path.splitext(os.path.basename(img_path))[0]
    direct = os.path.join(lbl_dir, stem + ".txt")
    if os.path.exists(direct):
        return direct
    try:
        rel = os.path.relpath(os.path.dirname(img_path), img_dir)
        nested = os.path.join(lbl_dir, rel, stem + ".txt")
        if os.path.exists(nested):
            return nested
    except ValueError:
        pass
    return ""


# ─────────────────────────────────────────────── değerlendirme işçisi

class EvalWorker(QThread):
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    result = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        cfg = self.cfg
        try:
            from ultralytics import YOLO
        except Exception as e:
            self.failed.emit(f"ultralytics içe aktarılamadı:\n{e}")
            return
        try:
            model = YOLO(cfg["model_path"])
            names = dict(model.names)
        except Exception as e:
            self.failed.emit(f"Model yüklenemedi:\n{e}")
            return
        self.log.emit(f"Model: {os.path.basename(cfg['model_path'])} — "
                      f"{len(names)} sınıf")

        images = cfg["images"]
        nc = len(names)
        # karışıklık matrisi: satır = gerçek (son satır: arka plan), kolon = tahmin
        cm = [[0] * (nc + 1) for _ in range(nc + 1)]
        items = []
        toplam = {"tp": 0, "fp": 0, "fn": 0, "conf": 0, "gt": 0, "pred": 0}

        for i, img_path in enumerate(images):
            if self._cancel:
                self.log.emit("İptal edildi.")
                break
            lbl = find_label(img_path, cfg["img_dir"], cfg["lbl_dir"])
            gt_n = read_gt(lbl)

            try:
                res = model.predict(source=img_path, conf=cfg["conf"], iou=cfg["iou_nms"],
                                    imgsz=cfg["imgsz"], device=cfg["device"],
                                    max_det=cfg["max_det"], verbose=False)[0]
            except Exception as e:
                self.log.emit(f"HATA — {os.path.basename(img_path)}: {e}")
                self.progress.emit(i + 1, len(images))
                continue

            H, W = res.orig_shape
            gt_px = [(c, *xywhn_to_xyxy((c, x, y, w, h), W, H)) for c, x, y, w, h in gt_n]
            pred_px = []
            if res.boxes is not None and len(res.boxes):
                xyxy = res.boxes.xyxy.cpu().numpy()
                clss = res.boxes.cls.cpu().numpy().astype(int)
                cfs = res.boxes.conf.cpu().numpy()
                order = cfs.argsort()[::-1]
                for k in order:
                    pred_px.append((int(clss[k]), float(cfs[k]), *xyxy[k].tolist()))

            results, fns = match_boxes(gt_px, pred_px, cfg["iou_match"])

            marks = []            # önizlemede çizilecek kutular (normalize xyxy)
            n_tp = n_fp = n_conf = 0
            for (kind, gi, v), p in zip(results, pred_px):
                box_n = (p[2] / W, p[3] / H, p[4] / W, p[5] / H)
                if kind == "tp":
                    n_tp += 1
                    cm[p[0]][p[0]] += 1
                    etiket = f"{names.get(p[0], p[0])} {p[1]:.2f}"
                elif kind == "conf":
                    n_conf += 1
                    gcls = gt_px[gi][0]
                    cm[gcls][p[0]] += 1
                    etiket = (f"{names.get(gcls, gcls)} → {names.get(p[0], p[0])} "
                              f"{p[1]:.2f}")
                else:
                    n_fp += 1
                    cm[nc][p[0]] += 1
                    etiket = f"FP {names.get(p[0], p[0])} {p[1]:.2f}"
                marks.append({"kind": kind, "box": box_n, "text": etiket})

            for gi in fns:
                g = gt_px[gi]
                cm[g[0]][nc] += 1
                marks.append({"kind": "fn",
                              "box": (g[1] / W, g[2] / H, g[3] / W, g[4] / H),
                              "text": f"kaçırıldı: {names.get(g[0], g[0])}"})

            skor = len(fns) + n_fp + 1.5 * n_conf
            items.append({
                "img": img_path, "lbl": lbl, "marks": marks, "skor": skor,
                "tp": n_tp, "fp": n_fp, "fn": len(fns), "conf": n_conf,
                "gt": len(gt_px), "pred": len(pred_px),
            })
            toplam["tp"] += n_tp
            toplam["fp"] += n_fp
            toplam["fn"] += len(fns)
            toplam["conf"] += n_conf
            toplam["gt"] += len(gt_px)
            toplam["pred"] += len(pred_px)
            self.progress.emit(i + 1, len(images))

        items.sort(key=lambda d: -d["skor"])
        self.result.emit({"mode": "eval", "items": items, "cm": cm,
                          "names": names, "toplam": toplam, "iptal": self._cancel})


# ─────────────────────────────────────────────── aktif öğrenme işçisi

class ActiveWorker(QThread):
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    result = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        cfg = self.cfg
        try:
            from ultralytics import YOLO
        except Exception as e:
            self.failed.emit(f"ultralytics içe aktarılamadı:\n{e}")
            return
        try:
            model = YOLO(cfg["model_path"])
            names = dict(model.names)
        except Exception as e:
            self.failed.emit(f"Model yüklenemedi:\n{e}")
            return

        lo, hi = cfg["band"]
        self.log.emit(f"Belirsizlik bandı: {lo:.2f}–{hi:.2f}  "
                      f"(tarama eşiği conf={cfg['conf']:.2f})")
        images = cfg["images"]
        items = []

        for i, img_path in enumerate(images):
            if self._cancel:
                self.log.emit("İptal edildi.")
                break
            try:
                res = model.predict(source=img_path, conf=cfg["conf"], iou=cfg["iou_nms"],
                                    imgsz=cfg["imgsz"], device=cfg["device"],
                                    max_det=cfg["max_det"], verbose=False)[0]
            except Exception as e:
                self.log.emit(f"HATA — {os.path.basename(img_path)}: {e}")
                self.progress.emit(i + 1, len(images))
                continue

            H, W = res.orig_shape
            marks, confs = [], []
            if res.boxes is not None and len(res.boxes):
                xyxy = res.boxes.xyxy.cpu().numpy()
                clss = res.boxes.cls.cpu().numpy().astype(int)
                cfs = res.boxes.conf.cpu().numpy()
                for k in range(len(cfs)):
                    c = float(cfs[k])
                    confs.append(c)
                    x1, y1, x2, y2 = xyxy[k].tolist()
                    belirsiz = lo <= c <= hi
                    marks.append({
                        "kind": "conf" if belirsiz else "tp",
                        "box": (x1 / W, y1 / H, x2 / W, y2 / H),
                        "text": f"{names.get(int(clss[k]), clss[k])} {c:.2f}",
                    })

            band = [c for c in confs if lo <= c <= hi]
            # belirsizlik: 0.5'e yakın güvenler en bilgilendiricidir
            skor = sum(1.0 - abs(2 * c - 1) for c in band)
            if not confs:
                skor += cfg["empty_bonus"]        # hiç tespit yok → olası kaçırma
            items.append({
                "img": img_path, "lbl": "", "marks": marks, "skor": skor,
                "n_box": len(confs), "n_band": len(band),
                "max_conf": max(confs) if confs else 0.0,
            })
            self.progress.emit(i + 1, len(images))

        items.sort(key=lambda d: -d["skor"])
        self.result.emit({"mode": "active", "items": items, "names": names,
                          "iptal": self._cancel})


# ─────────────────────────────────────────────── önizleme

class PreviewCanvas(QWidget):
    """Görseli sığdırır; tahmin/referans kutularını türüne göre çizer."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(280)
        self._img = None
        self._marks = []
        self._gt = []
        self._info = "Soldaki listeden bir görsel seç"
        self._show_gt = True

    def set_show_gt(self, on: bool):
        self._show_gt = on
        self.update()

    def show_item(self, img_path: str, marks: list, gt: list, info: str):
        img = QImage(img_path)
        self._img = None if img.isNull() else img
        self._marks = marks
        self._gt = gt
        self._info = info
        self.update()

    def clear_item(self, info="Görsel yok"):
        self._img, self._marks, self._gt = None, [], []
        self._info = info
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#dde1e7"))
        if self._img is None:
            p.setPen(QColor("#6b7686"))
            p.drawText(self.rect(), Qt.AlignCenter, self._info)
            return

        iw, ih = self._img.width(), self._img.height()
        avail_h = self.height() - 34
        scale = min(self.width() / iw, avail_h / ih)
        dw, dh = iw * scale, ih * scale
        ox, oy = (self.width() - dw) / 2, (avail_h - dh) / 2
        p.drawImage(QRectF(ox, oy, dw, dh), self._img)
        p.setFont(QFont("monospace", 8))

        # referans etiketler (ince kesikli gri) — arkada dursun
        if self._show_gt:
            pen = QPen(QColor(COL_GT))
            pen.setWidth(1)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            for _c, x, y, w, h in self._gt:
                p.drawRect(QRectF(ox + (x - w / 2) * dw, oy + (y - h / 2) * dh,
                                  w * dw, h * dh))

        style = {
            "tp":   (COL_TP, 2, Qt.SolidLine),
            "fp":   (COL_FP, 2, Qt.DotLine),
            "fn":   (COL_FN, 3, Qt.DashLine),
            "conf": (COL_CONF, 2, Qt.SolidLine),
        }
        for m in self._marks:
            color, wpen, dash = style.get(m["kind"], (COL_TP, 2, Qt.SolidLine))
            pen = QPen(QColor(color))
            pen.setWidth(wpen)
            pen.setStyle(dash)
            p.setPen(pen)
            x1, y1, x2, y2 = m["box"]
            bx, by = ox + x1 * dw, oy + y1 * dh
            p.drawRect(QRectF(bx, by, (x2 - x1) * dw, (y2 - y1) * dh))
            txt = m.get("text", "")
            if txt:
                p.fillRect(QRectF(bx, by - 13, 8 + 6.4 * len(txt), 13),
                           QColor(0, 0, 0, 175))
                p.setPen(QColor(color))
                p.drawText(QRectF(bx + 3, by - 13, 400, 13), Qt.AlignVCenter, txt)

        # alt bilgi + gösterge
        p.setPen(QColor("#4d5765"))
        p.drawText(QRectF(4, self.height() - 32, self.width() - 8, 15),
                   Qt.AlignVCenter, f"{self._info}   ({iw}×{ih})")
        legend = [("düz mavi: doğru", COL_TP, 2, Qt.SolidLine),
                  ("noktalı sarı: uydurma", COL_FP, 2, Qt.DotLine),
                  ("kalın kesikli: kaçırılan", COL_FN, 3, Qt.DashLine),
                  ("mor: sınıf karışıklığı", COL_CONF, 2, Qt.SolidLine),
                  ("ince kesikli: referans", COL_GT, 1, Qt.DashLine)]
        x = 6
        yl = self.height() - 10
        for text, col, wpen, dash in legend:
            pen = QPen(QColor(col))
            pen.setWidth(wpen)
            pen.setStyle(dash)
            p.setPen(pen)
            p.drawLine(QLineF(x, yl, x + 18, yl))
            p.setPen(QColor("#4d5765"))
            p.drawText(QRectF(x + 22, self.height() - 17, 240, 15),
                       Qt.AlignVCenter, text)
            x += 30 + 6.4 * len(text)


# ─────────────────────────────────────────────── ana pencere

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hata Analizi — model nerede yanılıyor?")
        self.setMinimumSize(1340, 820)
        self._model_path = ""
        self._items = []
        self._shown = []
        self._names = {}
        self._mode = ""
        self._worker = None
        self._sinif_yukleyici = None
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
        sp.addWidget(self._build_center())
        sp.addWidget(self._build_right())
        sp.setSizes([320, 660, 380])
        v.addWidget(sp, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Model seç → Değerlendirme veya Aktif Öğrenme sekmesinden başlat")

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(280)
        w.setMaximumWidth(400)
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.filter_combo = QComboBox()
        for text, key in (("En kötüden iyiye", "all"), ("Kaçırılan var (FN)", "fn"),
                          ("Uydurma var (FP)", "fp"), ("Sınıf karışıklığı", "conf"),
                          ("Hatasız", "clean")):
            self.filter_combo.addItem(text, key)
        self.filter_combo.currentIndexChanged.connect(self._refill)
        v.addWidget(self.filter_combo)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.currentRowChanged.connect(self._show_row)
        v.addWidget(self.list, 1)

        self.count_lbl = QLabel("0 kayıt")
        self.count_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(self.count_lbl)

        self.gt_chk = QCheckBox("Referans etiketleri göster")
        self.gt_chk.setChecked(True)
        self.gt_chk.toggled.connect(lambda on: self.canvas.set_show_gt(on))
        v.addWidget(self.gt_chk)

        b1 = QPushButton("Seçilenleri Klasöre Kopyala…")
        b1.setToolTip("Düzeltilecek / etiketlenecek görselleri ayrı klasöre çıkarır "
                      "(varsa etiketiyle birlikte)")
        b1.clicked.connect(self._export_selected)
        v.addWidget(b1)

        b2 = QPushButton("İlk N Kaydı Kopyala…")
        b2.setToolTip("Listedeki en öncelikli N görseli çıkarır")
        b2.clicked.connect(self._export_top)
        v.addWidget(b2)
        return w

    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.canvas = PreviewCanvas()
        v.addWidget(self.canvas, 3)

        self.tabs_out = QTabWidget()
        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs_out.addTab(self.report_box, "Rapor")
        self.detail_box = QTextEdit()
        self.detail_box.setReadOnly(True)
        self.detail_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs_out.addTab(self.detail_box, "Seçili Görsel")
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs_out.addTab(self.log_box, "Log")
        v.addWidget(self.tabs_out, 2)
        return w

    def _path_row(self, edit: QLineEdit, slot, btn="Seç…") -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        edit.setReadOnly(True)
        edit.setStyleSheet("font-size:11px; font-family:monospace;")
        h.addWidget(edit, 1)
        b = QPushButton(btn)
        b.setFixedWidth(58)
        b.clicked.connect(slot)
        h.addWidget(b)
        return h

    def _row(self, text, widget) -> QHBoxLayout:
        h = QHBoxLayout()
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:normal;")
        h.addWidget(lb)
        h.addStretch()
        h.addWidget(widget)
        return h

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(340)
        w.setMaximumWidth(460)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        # Model (iki sekme için ortak)
        grp = QGroupBox("Model")
        g = QVBoxLayout(grp)
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("eğitilmiş model.pt")
        g.addLayout(self._path_row(self.model_edit, self._pick_model))
        self.model_info = QLabel("Sınıflar: —")
        self.model_info.setWordWrap(True)
        self.model_info.setStyleSheet("color:#6b7686; font-size:11px;")
        g.addWidget(self.model_info)
        v.addWidget(grp)

        # Ortak çıkarım ayarları
        grp_i = QGroupBox("Çıkarım")
        gi = QVBoxLayout(grp_i)
        gi.setSpacing(6)
        self.imgsz_spin = QSpinBox()
        self.imgsz_spin.setRange(160, 2048)
        self.imgsz_spin.setSingleStep(32)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setFixedWidth(90)
        gi.addLayout(self._row("Görsel boyutu", self.imgsz_spin))
        self.iou_nms_spin = QDoubleSpinBox()
        self.iou_nms_spin.setRange(0.1, 0.95)
        self.iou_nms_spin.setSingleStep(0.05)
        self.iou_nms_spin.setValue(0.45)
        self.iou_nms_spin.setFixedWidth(90)
        gi.addLayout(self._row("NMS IoU", self.iou_nms_spin))
        self.maxdet_spin = QSpinBox()
        self.maxdet_spin.setRange(1, 1000)
        self.maxdet_spin.setValue(300)
        self.maxdet_spin.setFixedWidth(90)
        gi.addLayout(self._row("Maks tespit", self.maxdet_spin))
        self.device_combo = QComboBox()
        cihaz_combo_doldur(self.device_combo)
        self.device_combo.setFixedWidth(130)
        gi.addLayout(self._row("Cihaz", self.device_combo))
        v.addWidget(grp_i)

        # Sekmeler
        self.tabs_in = QTabWidget()
        self.tabs_in.addTab(self._build_eval_tab(), "Değerlendirme")
        self.tabs_in.addTab(self._build_active_tab(), "Aktif Öğrenme")
        v.addWidget(self.tabs_in)

        h = QHBoxLayout()
        h.setSpacing(6)
        self.progress = QProgressBar()
        h.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setFixedWidth(70)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        h.addWidget(self.cancel_btn)
        v.addLayout(h)

        self.save_btn = QPushButton("Raporu Kaydet…")
        self.save_btn.clicked.connect(self._save_report)
        v.addWidget(self.save_btn)

        v.addStretch()
        return w

    def _build_eval_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 10, 8, 8)
        v.setSpacing(6)

        v.addWidget(QLabel("Görseller (etiketli set — genelde val)"))
        self.eval_img_edit = QLineEdit()
        v.addLayout(self._path_row(self.eval_img_edit, self._pick_eval_img))
        v.addWidget(QLabel("Etiketler"))
        self.eval_lbl_edit = QLineEdit()
        v.addLayout(self._path_row(self.eval_lbl_edit, self._pick_eval_lbl))

        self.eval_conf = QDoubleSpinBox()
        self.eval_conf.setRange(0.01, 0.99)
        self.eval_conf.setSingleStep(0.05)
        self.eval_conf.setValue(0.25)
        self.eval_conf.setFixedWidth(90)
        self.eval_conf.setToolTip("Bu eşikteki tahminler değerlendirilir "
                                  "(hattaki çalışma eşiğini kullan)")
        v.addLayout(self._row("Güven eşiği", self.eval_conf))

        self.eval_iou = QDoubleSpinBox()
        self.eval_iou.setRange(0.1, 0.95)
        self.eval_iou.setSingleStep(0.05)
        self.eval_iou.setValue(0.50)
        self.eval_iou.setFixedWidth(90)
        self.eval_iou.setToolTip("Tahmin ile referansın 'aynı nesne' sayılması için "
                                 "gereken örtüşme")
        v.addLayout(self._row("Eşleştirme IoU", self.eval_iou))

        self.eval_btn = QPushButton("🔍  Değerlendir")
        self.eval_btn.setMinimumHeight(36)
        self.eval_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.eval_btn.clicked.connect(self._start_eval)
        v.addWidget(self.eval_btn)
        v.addStretch()
        return w

    def _build_active_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 10, 8, 8)
        v.setSpacing(6)

        v.addWidget(QLabel("Etiketsiz havuz (kare klasörü)"))
        self.pool_edit = QLineEdit()
        v.addLayout(self._path_row(self.pool_edit, self._pick_pool))

        self.pool_conf = QDoubleSpinBox()
        self.pool_conf.setRange(0.01, 0.5)
        self.pool_conf.setSingleStep(0.01)
        self.pool_conf.setValue(0.05)
        self.pool_conf.setFixedWidth(90)
        self.pool_conf.setToolTip("Tarama eşiği: düşük tut, zayıf tespitleri de görelim")
        v.addLayout(self._row("Tarama eşiği", self.pool_conf))

        self.band_lo = QDoubleSpinBox()
        self.band_lo.setRange(0.0, 0.9)
        self.band_lo.setSingleStep(0.05)
        self.band_lo.setValue(0.25)
        self.band_lo.setFixedWidth(90)
        v.addLayout(self._row("Belirsizlik bandı alt", self.band_lo))

        self.band_hi = QDoubleSpinBox()
        self.band_hi.setRange(0.1, 1.0)
        self.band_hi.setSingleStep(0.05)
        self.band_hi.setValue(0.70)
        self.band_hi.setFixedWidth(90)
        v.addLayout(self._row("Belirsizlik bandı üst", self.band_hi))

        self.empty_bonus = QDoubleSpinBox()
        self.empty_bonus.setRange(0.0, 10.0)
        self.empty_bonus.setSingleStep(0.5)
        self.empty_bonus.setValue(1.0)
        self.empty_bonus.setFixedWidth(90)
        self.empty_bonus.setToolTip("Hiç tespit çıkmayan kareye eklenen öncelik puanı "
                                    "(olası kaçırma)")
        v.addLayout(self._row("Boş kare önceliği", self.empty_bonus))

        self.active_btn = QPushButton("⚡  Havuzu Sırala")
        self.active_btn.setMinimumHeight(36)
        self.active_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.active_btn.clicked.connect(self._start_active)
        v.addWidget(self.active_btn)

        hint = QLabel("En üstteki kareleri etiketle → yeniden eğit → tekrar sırala. "
                      "Rastgele etiketlemeye göre aynı emekle daha çok kazanç.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(hint)
        v.addStretch()
        return w

    def _build_menu(self):
        m = self.menuBar().addMenu("Dosya")

        def act(label, slot, sc=""):
            a = QAction(label, self)
            if sc:
                a.setShortcut(sc)
            a.triggered.connect(slot)
            m.addAction(a)

        act("Model Seç…", self._pick_model, "Ctrl+M")
        act("Raporu Kaydet…", self._save_report, "Ctrl+S")
        m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    # ── seçimler
    def _log(self, t: str):
        self.log_box.append(t)

    def _pick_model(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Model seç", self._model_path or "",
            "YOLO modeli (*.pt *.engine *.onnx);;Tüm Dosyalar (*)")
        if not p:
            return
        self._model_path = p
        self.model_edit.setText(p)
        self.model_edit.setToolTip(p)
        self.model_edit.setCursorPosition(0)
        self._load_class_names(p)

    def _load_class_names(self, path: str):
        """Sınıf adlarını arka planda oku.

        `from ultralytics import YOLO` ilk çağrıda torch'u da yükler; bunu
        arayüz iş parçacığında yapmak pencereyi saniyelerce dondurur.
        """
        self.model_info.setText("Sınıflar okunuyor…")
        eski = self._sinif_yukleyici
        if eski is not None:
            try:
                eski.tamamlandi.disconnect()
            except TypeError:
                pass
        self._sinif_yukleyici = SinifYukleyici(path, self)
        self._sinif_yukleyici.tamamlandi.connect(self._on_class_names)
        self._sinif_yukleyici.start()

    def _on_class_names(self, yol: str, names: dict, hata: str):
        if self._sinif_yukleyici is not None:
            self._sinif_yukleyici.deleteLater()
        self._sinif_yukleyici = None
        # Kullanıcı bu arada başka model seçtiyse geç gelen sonucu yut
        if yol != self._model_path:
            return
        if hata:
            self.model_info.setText("Sınıflar okunamadı (çalıştırırken tekrar denenecek)")
            self._log(f"Model sınıfları okunamadı: {hata}")
            return
        self._names = names
        self.model_info.setText(sinif_ozeti(names))

    def _pick_eval_img(self):
        d = QFileDialog.getExistingDirectory(self, "Etiketli görsel klasörü",
                                             self.eval_img_edit.text())
        if not d:
            return
        self.eval_img_edit.setText(d)
        self.eval_img_edit.setCursorPosition(0)
        # kardeş labels/ klasörünü tahmin et
        if not self.eval_lbl_edit.text():
            guess = os.path.join(os.path.dirname(d.rstrip(os.sep)), "labels")
            base = os.path.basename(d.rstrip(os.sep))
            nested = os.path.join(os.path.dirname(d.rstrip(os.sep)), "labels", base)
            for cand in (nested, guess):
                if os.path.isdir(cand):
                    self.eval_lbl_edit.setText(cand)
                    break

    def _pick_eval_lbl(self):
        d = QFileDialog.getExistingDirectory(self, "Etiket klasörü", self.eval_lbl_edit.text())
        if d:
            self.eval_lbl_edit.setText(d)
            self.eval_lbl_edit.setCursorPosition(0)

    def _pick_pool(self):
        d = QFileDialog.getExistingDirectory(self, "Etiketsiz havuz", self.pool_edit.text())
        if d:
            self.pool_edit.setText(d)
            self.pool_edit.setCursorPosition(0)

    # ── çalıştırma
    def _guard(self) -> bool:
        if self._worker:
            self.status.showMessage("İşlem sürüyor.")
            return False
        if not self._model_path or not os.path.exists(self._model_path):
            QMessageBox.warning(self, "Model yok", "Geçerli bir model seç.")
            return False
        return True

    def _common_cfg(self) -> dict:
        return {
            "model_path": self._model_path,
            "imgsz": int(self.imgsz_spin.value()),
            "iou_nms": float(self.iou_nms_spin.value()),
            "max_det": int(self.maxdet_spin.value()),
            "device": self.device_combo.currentData(),
        }

    def _start_eval(self):
        if not self._guard():
            return
        img_dir = self.eval_img_edit.text().strip()
        lbl_dir = self.eval_lbl_edit.text().strip()
        if not os.path.isdir(img_dir):
            QMessageBox.warning(self, "Klasör yok", "Etiketli görsel klasörünü seç.")
            return
        if not os.path.isdir(lbl_dir):
            QMessageBox.warning(self, "Klasör yok", "Etiket klasörünü seç.")
            return
        images = list_images(img_dir)
        if not images:
            QMessageBox.warning(self, "Görsel yok", "Klasörde görsel bulunamadı.")
            return

        cfg = self._common_cfg()
        cfg.update({"images": images, "img_dir": img_dir, "lbl_dir": lbl_dir,
                    "conf": float(self.eval_conf.value()),
                    "iou_match": float(self.eval_iou.value())})
        self._log(f"── değerlendirme: {len(images)} görsel ──")
        self._worker = EvalWorker(cfg)
        self._wire(self._worker)

    def _start_active(self):
        if not self._guard():
            return
        pool = self.pool_edit.text().strip()
        if not os.path.isdir(pool):
            QMessageBox.warning(self, "Klasör yok", "Etiketsiz havuz klasörünü seç.")
            return
        images = list_images(pool)
        if not images:
            QMessageBox.warning(self, "Görsel yok", "Havuzda görsel bulunamadı.")
            return
        lo, hi = self.band_lo.value(), self.band_hi.value()
        if lo >= hi:
            QMessageBox.warning(self, "Bant hatası", "Bandın altı üstünden küçük olmalı.")
            return

        cfg = self._common_cfg()
        cfg.update({"images": images, "conf": float(self.pool_conf.value()),
                    "band": (lo, hi), "empty_bonus": float(self.empty_bonus.value())})
        self._log(f"── aktif öğrenme: {len(images)} görsel ──")
        self._worker = ActiveWorker(cfg)
        self._wire(self._worker)

    def _wire(self, worker):
        worker.progress.connect(self._on_progress)
        worker.log.connect(self._log)
        worker.result.connect(self._on_result)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_finished)
        self.eval_btn.setEnabled(False)
        self.active_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setValue(0)
        worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self.status.showMessage("İptal isteniyor…")

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status.showMessage(f"{done}/{total}")

    def _on_failed(self, msg: str):
        self._log("HATA: " + msg)
        QMessageBox.critical(self, "Hata", msg)

    def _on_finished(self):
        self._worker = None
        self.eval_btn.setEnabled(True)
        self.active_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def _on_result(self, res: dict):
        self._mode = res["mode"]
        self._items = res["items"]
        self._names = res.get("names", self._names)
        self.filter_combo.setEnabled(self._mode == "eval")
        self._refill()
        if self._mode == "eval":
            self.report_box.setPlainText(self._eval_report(res))
        else:
            self.report_box.setPlainText(self._active_report(res))
        self.tabs_out.setCurrentIndex(0)
        self.status.showMessage("Bitti." + (" (iptal edildi)" if res["iptal"] else ""))

    # ── liste / önizleme
    def _refill(self):
        key = self.filter_combo.currentData()
        self.list.clear()
        self._shown = []
        for i, it in enumerate(self._items):
            if self._mode == "eval":
                keep = (key == "all"
                        or (key == "fn" and it["fn"])
                        or (key == "fp" and it["fp"])
                        or (key == "conf" and it["conf"])
                        or (key == "clean" and not (it["fn"] or it["fp"] or it["conf"])))
                if not keep:
                    continue
                text = (f"{os.path.basename(it['img'])}  "
                        f"FN{it['fn']} FP{it['fp']} K{it['conf']} / doğru {it['tp']}")
            else:
                text = (f"{os.path.basename(it['img'])}  "
                        f"skor {it['skor']:.2f}  belirsiz {it['n_band']}/{it['n_box']}")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, i)
            item.setToolTip(it["img"])
            self.list.addItem(item)
            self._shown.append(i)
        self.count_lbl.setText(f"{len(self._shown)} / {len(self._items)} kayıt")

    def _show_row(self, row: int):
        if row < 0 or row >= len(self._shown):
            return
        it = self._items[self._shown[row]]
        gt = read_gt(it["lbl"]) if it.get("lbl") else []
        self.canvas.show_item(it["img"], it["marks"], gt, os.path.basename(it["img"]))
        lines = [it["img"]]
        if self._mode == "eval":
            lines += [f"etiket: {it['lbl'] or '(bulunamadı)'}",
                      f"referans kutu: {it['gt']}    tahmin: {it['pred']}",
                      f"doğru (TP): {it['tp']}",
                      f"kaçırılan (FN): {it['fn']}",
                      f"uydurma (FP): {it['fp']}",
                      f"sınıf karışıklığı: {it['conf']}",
                      f"hata skoru: {it['skor']:.2f}"]
        else:
            lines += [f"tespit: {it['n_box']}  belirsiz bantta: {it['n_band']}",
                      f"en yüksek güven: {it['max_conf']:.2f}",
                      f"öncelik skoru: {it['skor']:.2f}"]
        lines += ["", "Kutular:"]
        for m in it["marks"][:40]:
            lines.append(f"  [{m['kind']}] {m['text']}")
        self.detail_box.setPlainText("\n".join(lines))

    # ── raporlar
    def _eval_report(self, res: dict) -> str:
        cm = res["cm"]
        names = res["names"]
        nc = len(names)
        t = res["toplam"]
        L = ["═══ DEĞERLENDİRME ═══",
             f"model: {os.path.basename(self._model_path)}",
             f"görsel: {len(res['items'])}   referans kutu: {t['gt']}   "
             f"tahmin: {t['pred']}",
             f"güven eşiği: {self.eval_conf.value():.2f}   "
             f"eşleştirme IoU: {self.eval_iou.value():.2f}",
             "(tek eşikte TP/FP/FN sayımı — mAP değil, hattaki davranışın ölçüsü)",
             ""]
        tp, fp, fn, cf = t["tp"], t["fp"], t["fn"], t["conf"]
        prec = tp / (tp + fp + cf) if (tp + fp + cf) else 0.0
        rec = tp / (tp + fn + cf) if (tp + fn + cf) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        L += [f"doğru (TP)            : {tp}",
              f"uydurma (FP)          : {fp}",
              f"kaçırılan (FN)        : {fn}",
              f"sınıf karışıklığı     : {cf}",
              f"kesinlik (precision)  : {prec:.3f}",
              f"duyarlılık (recall)   : {rec:.3f}",
              f"F1                    : {f1:.3f}", ""]

        L.append("── Sınıf başına ──")
        L.append(f"{'sınıf':<18s}{'TP':>6s}{'FP':>6s}{'FN':>6s}{'kesinlik':>10s}"
                 f"{'duyarlılık':>12s}")
        for c in range(nc):
            c_tp = cm[c][c]
            c_fp = sum(cm[r][c] for r in range(nc + 1)) - c_tp
            c_fn = sum(cm[c]) - c_tp
            p = c_tp / (c_tp + c_fp) if (c_tp + c_fp) else 0.0
            r = c_tp / (c_tp + c_fn) if (c_tp + c_fn) else 0.0
            L.append(f"{names.get(c, c):<18s}{c_tp:>6d}{c_fp:>6d}{c_fn:>6d}"
                     f"{p:>10.3f}{r:>12.3f}")
            if r < 0.7 and (c_tp + c_fn) > 0:
                L.append(f"  ! '{names.get(c, c)}' duyarlılığı düşük — bu sınıftan "
                         "daha çok örnek gerekiyor")
        L.append("")

        L.append("── Karışıklık matrisi (satır: gerçek, kolon: tahmin) ──")
        head = "".join(f"{str(names.get(i, i))[:6]:>7s}" for i in range(nc))
        L.append(f"{'':<14s}{head}{'kaçtı':>8s}")
        for r in range(nc):
            row = "".join(f"{cm[r][c]:>7d}" for c in range(nc))
            L.append(f"{str(names.get(r, r))[:13]:<14s}{row}{cm[r][nc]:>8d}")
        row = "".join(f"{cm[nc][c]:>7d}" for c in range(nc))
        L.append(f"{'arka plan':<14s}{row}{'':>8s}")
        L.append("")

        worst = [i for i in res["items"] if i["skor"] > 0][:15]
        if worst:
            L.append("── En sorunlu görseller ──")
            mx = worst[0]["skor"]
            for it in worst:
                L.append(f"{os.path.basename(it['img'])[:34]:<35s} "
                         f"{bar(it['skor'], mx)} FN{it['fn']} FP{it['fp']} K{it['conf']}")
            L.append("  → 'Seçilenleri Klasöre Kopyala' ile Labelapp'te düzelt")
        else:
            L.append("Hatalı görsel yok — bu eşikte model temiz çalışıyor.")
        return "\n".join(L)

    def _active_report(self, res: dict) -> str:
        items = res["items"]
        bos = [i for i in items if i["n_box"] == 0]
        belirsiz = [i for i in items if i["n_band"] > 0]
        L = ["═══ AKTİF ÖĞRENME SIRASI ═══",
             f"model: {os.path.basename(self._model_path)}",
             f"havuz: {len(items)} görsel",
             f"belirsiz tespiti olan: {len(belirsiz)}",
             f"hiç tespit çıkmayan  : {len(bos)}",
             "",
             "Skor = 0,5 güvene yakın kutuların toplam belirsizliği "
             "(+ boş kare önceliği).",
             "Yüksek skor = model tereddüt ediyor = etiketlenince en çok öğretir.",
             "",
             "── İlk 25 ──"]
        mx = items[0]["skor"] if items else 1
        for it in items[:25]:
            L.append(f"{os.path.basename(it['img'])[:34]:<35s} {bar(it['skor'], mx)} "
                     f"{it['skor']:.2f}  ({it['n_band']}/{it['n_box']} belirsiz)")
        L.append("")
        L.append("→ 'İlk N Kaydı Kopyala' ile bunları ayır, oto-label ile ön etiketle, "
                 "Labelapp'te düzelt, yeniden eğit.")
        return "\n".join(L)

    def _save_report(self):
        if not self.report_box.toPlainText():
            self.status.showMessage("Önce çalıştır.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Raporu kaydet",
                                           "analiz_raporu.txt", "Metin (*.txt)")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.report_box.toPlainText())
            self.status.showMessage(f"Kaydedildi: {p}")
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")

    # ── dışa aktarma
    def _copy_items(self, idxs: list):
        if not idxs:
            self.status.showMessage("Kopyalanacak kayıt yok.")
            return
        d = QFileDialog.getExistingDirectory(self, "Hedef klasör")
        if not d:
            return
        img_dst = os.path.join(d, "images")
        lbl_dst = os.path.join(d, "labels")
        os.makedirs(img_dst, exist_ok=True)
        n_img = n_lbl = 0
        for i in idxs:
            it = self._items[i]
            try:
                shutil.copy2(it["img"], os.path.join(img_dst, os.path.basename(it["img"])))
                n_img += 1
                if it.get("lbl") and os.path.exists(it["lbl"]):
                    os.makedirs(lbl_dst, exist_ok=True)
                    shutil.copy2(it["lbl"], os.path.join(lbl_dst,
                                                        os.path.basename(it["lbl"])))
                    n_lbl += 1
            except OSError as e:
                self._log(f"HATA — kopyalanamadı {it['img']}: {e}")
        with open(os.path.join(d, "liste.txt"), "w", encoding="utf-8") as f:
            for i in idxs:
                f.write(os.path.abspath(self._items[i]["img"]) + "\n")
        self._log(f"{n_img} görsel, {n_lbl} etiket kopyalandı → {d}")
        self.status.showMessage(f"{n_img} görsel kopyalandı → {d}")

    def _export_selected(self):
        rows = [self._shown[self.list.row(x)] for x in self.list.selectedItems()]
        self._copy_items(rows)

    def _export_top(self):
        if not self._shown:
            self.status.showMessage("Liste boş.")
            return
        n, ok = QInputDialog.getInt(self, "İlk N kayıt",
                                    "Kaç görsel kopyalanacak?", 50, 1,
                                    len(self._shown), 10)
        if not ok:
            return
        self._copy_items(self._shown[:n])

    def closeEvent(self, ev):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(5000)
        if self._sinif_yukleyici is not None:
            self._sinif_yukleyici.wait(3000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    # Tek başına çalıştırıldığında tema ayarını kabuk yüklemez; buradan okunur
    from .. import tema as _tema
    _tema.tema_yukle()
    _tema.yamalari_kur()
    app.setStyleSheet(_tema.stil())
    app.setApplicationName("Hata Analizi")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
