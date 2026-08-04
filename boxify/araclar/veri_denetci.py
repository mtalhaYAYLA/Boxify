"""Veri Denetçi — YOLO veri setini denetler, yakın-kopyaları bulur,
sızıntısız (grup bazlı) train/val/test bölmesi üretir.

Üç işi var:
  1. Sağlık kontrolü : eksik/bozuk etiket, aralık dışı koordinat, hatalı sınıf id
  2. Yakın-kopya     : aynı sahnenin tekrar eden kareleri (dHash + Hamming)
  3. Bölme           : aynı klibin kareleri aynı tarafa → val sızıntısı olmaz

Bağımlılık: PyQt5, opencv-python, numpy (ultralytics gerekmez).
"""
import os
import re
import sys
import random
import shutil

import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog, QStatusBar,
    QGroupBox, QMessageBox, QLineEdit, QAction, QSizePolicy, QComboBox,
    QProgressBar, QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTabWidget,
    QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF, QTimer
from PyQt5.QtGui import QImage, QPainter, QPen, QColor, QFont

from ..tema import STYLE  # ortak açık tema — bkz. boxify/tema.py
# Yakın-kopya bulma ve sızıntısız dağıtım tek yerde tutulur; Labelapp'in veri
# seti dışa aktarımı da aynı modülü kullanır (bkz. veri_bolme.py)
from .veri_bolme import dhash64, group_duplicates, bolumlere_dagit

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")

# Kutu renkleri: kırmızı-yeşil ayrımına dayanmaz (mavi / sarı / mor / camgöbeği).
# 6'dan fazla sınıfta aynı renkler kesikli çizgiyle tekrar eder.
CLASS_COLORS = ["#2e6da4", "#f5c518", "#275b8c", "#b39ddb", "#00bcd4", "#eeeeee"]

MARK_OK = "✓"
MARK_ERR = "!"      # bozuk — düzeltilmeli
MARK_WARN = "?"     # şüpheli
MARK_NOLBL = "○"    # etiketsiz
MARK_DUP = "»"      # yakın-kopya (temsilci değil)


# ─────────────────────────────────────────────── yardımcılar

def list_images(folder: str) -> list:
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(IMG_EXTS):
                out.append(os.path.join(root, f))
    return sorted(out)


def detect_dirs(root: str):
    """Kökten images/ ve labels/ klasörlerini tahmin et."""
    cand_img = [os.path.join(root, n) for n in ("images", "image", "img", "fotolar")]
    cand_lbl = [os.path.join(root, n) for n in ("labels", "label", "etiketler")]
    img = next((p for p in cand_img if os.path.isdir(p)), root)
    lbl = next((p for p in cand_lbl if os.path.isdir(p)), root)
    return img, lbl


def load_class_names(*folders) -> dict:
    """data.yaml veya classes.txt içinden sınıf adlarını oku (elle ayrıştırma)."""
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for parent in (folder, os.path.dirname(folder.rstrip(os.sep))):
            y = os.path.join(parent, "data.yaml")
            if os.path.exists(y):
                names = _parse_yaml_names(y)
                if names:
                    return names
            c = os.path.join(parent, "classes.txt")
            if os.path.exists(c):
                try:
                    with open(c, encoding="utf-8") as f:
                        lines = [ln.strip() for ln in f if ln.strip()]
                    if lines:
                        return {i: n for i, n in enumerate(lines)}
                except OSError:
                    pass
    return {}


def _parse_yaml_names(path: str) -> dict:
    """'names:' bloğunu okur: hem 'names: [a, b]' hem '  0: a' biçimini destekler."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    names = {}
    in_block = False
    for raw in lines:
        line = raw.rstrip()
        if not in_block:
            m = re.match(r"^names:\s*\[(.*)\]\s*$", line)
            if m:                                     # tek satır liste
                parts = [p.strip().strip("'\"") for p in m.group(1).split(",")]
                return {i: p for i, p in enumerate(parts) if p}
            if re.match(r"^names:\s*$", line):
                in_block = True
            continue
        if not line.startswith((" ", "\t", "-")):     # blok bitti
            break
        m = re.match(r"^\s*(\d+)\s*:\s*(.+?)\s*$", line)
        if m:
            names[int(m.group(1))] = m.group(2).strip().strip("'\"")
            continue
        m = re.match(r"^\s*-\s*(.+?)\s*$", line)      # sıralı liste
        if m:
            names[len(names)] = m.group(1).strip().strip("'\"")
    return names


def parse_label_file(path: str, nc: int, min_area: float):
    """Etiket dosyasını oku. → (kutular, hatalar, uyarılar)

    Kutu: (cls, x, y, w, h) — normalize (0-1) merkez + genişlik/yükseklik.
    """
    boxes, errors, warns = [], [], []
    try:
        with open(path, encoding="utf-8") as f:
            raw_lines = f.read().splitlines()
    except OSError as e:
        return boxes, [f"dosya okunamadı: {e}"], warns

    seen = set()
    for i, raw in enumerate(raw_lines, 1):
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) not in (5, 6):
            errors.append(f"satır {i}: {len(parts)} kolon (5 olmalı, güvenle 6)")
            continue
        if len(parts) == 6:
            warns.append(f"satır {i}: 6. kolon (güven) var — eğitim bunu beklemez")
        try:
            cls_f = float(parts[0])
            x, y, w, h = (float(v) for v in parts[1:5])
        except ValueError:
            errors.append(f"satır {i}: sayıya çevrilemedi")
            continue
        if cls_f != int(cls_f) or cls_f < 0:
            errors.append(f"satır {i}: geçersiz sınıf id ({parts[0]})")
            continue
        cls = int(cls_f)
        if nc and cls >= nc:
            errors.append(f"satır {i}: sınıf id {cls}, sınıf sayısı {nc}")
        if not all(0.0 - 1e-6 <= v <= 1.0 + 1e-6 for v in (x, y, w, h)):
            errors.append(f"satır {i}: koordinat 0-1 dışında")
            continue
        if w <= 0 or h <= 0:
            errors.append(f"satır {i}: sıfır/negatif kutu boyutu")
            continue
        if x - w / 2 < -1e-3 or x + w / 2 > 1 + 1e-3 or \
           y - h / 2 < -1e-3 or y + h / 2 > 1 + 1e-3:
            warns.append(f"satır {i}: kutu görsel kenarından taşıyor")
        if w * h < min_area:
            warns.append(f"satır {i}: çok küçük kutu (alan %{w * h * 100:.3f})")
        key = (cls, round(x, 5), round(y, 5), round(w, 5), round(h, 5))
        if key in seen:
            warns.append(f"satır {i}: aynı kutu tekrar ediyor")
        seen.add(key)
        boxes.append((cls, x, y, w, h))
    return boxes, errors, warns


def bar(n: int, maxn: int, width: int = 22) -> str:
    filled = int(round(width * n / max(1, maxn)))
    return "█" * filled + "·" * (width - filled)


# ─────────────────────────────────────────────── denetim işçisi

class AuditWorker(QThread):
    progress = pyqtSignal(int, int)
    log = pyqtSignal(str)
    result = pyqtSignal(dict)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        cfg = self.cfg
        try:
            import cv2
        except Exception as e:
            self.log.emit(f"HATA: opencv yüklenemedi — {e}")
            cv2 = None

        images = list_images(cfg["img_dir"])
        self.log.emit(f"{len(images)} görsel bulundu.")
        items = []
        hashes = []
        used_lbl = set()

        need_pixels = cfg["do_hash"] or cfg["check_readable"]

        for i, img_path in enumerate(images):
            if self._cancel:
                self.log.emit("İptal edildi.")
                break
            stem = os.path.splitext(os.path.basename(img_path))[0]
            lbl_path = os.path.join(cfg["lbl_dir"], stem + ".txt")
            item = {"img": img_path, "lbl": None, "boxes": [], "errors": [],
                    "warns": [], "hash": None, "dup_group": None}

            if os.path.exists(lbl_path):
                item["lbl"] = lbl_path
                used_lbl.add(os.path.abspath(lbl_path))
                boxes, errs, warns = parse_label_file(lbl_path, cfg["nc"], cfg["min_area"])
                item["boxes"] = boxes
                item["errors"] += errs
                item["warns"] += warns
                if not boxes and not errs:
                    item["warns"].append("etiket dosyası boş (negatif örnek)")
            else:
                item["warns"].append("etiket dosyası yok")

            if need_pixels and cv2 is not None:
                gray = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
                if gray is None:
                    item["errors"].append("görsel okunamadı / bozuk")
                else:
                    if cfg["do_hash"]:
                        item["hash"] = dhash64(gray)

            items.append(item)
            hashes.append(item["hash"])
            self.progress.emit(i + 1, len(images))

        # görseli olmayan etiketler
        orphans = []
        if os.path.isdir(cfg["lbl_dir"]):
            for root, _d, files in os.walk(cfg["lbl_dir"]):
                for f in files:
                    if not f.lower().endswith(".txt") or f in ("classes.txt",):
                        continue
                    p = os.path.abspath(os.path.join(root, f))
                    if p not in used_lbl:
                        orphans.append(p)

        dup_groups = []
        if cfg["do_hash"] and not self._cancel:
            self.log.emit("Yakın-kopyalar taranıyor…")
            dup_groups = group_duplicates(hashes, cfg["hash_thresh"])
            for gid, grp in enumerate(dup_groups):
                for k, idx in enumerate(grp):
                    items[idx]["dup_group"] = gid
                    items[idx]["dup_rep"] = (k == 0)      # ilki temsilci
            self.log.emit(f"{len(dup_groups)} kopya grubu, "
                          f"{sum(len(g) - 1 for g in dup_groups)} fazlalık görsel.")

        self.result.emit({
            "items": items,
            "orphans": orphans,
            "dup_groups": dup_groups,
            "iptal": self._cancel,
        })


# ─────────────────────────────────────────────── bölme işçisi

class SplitWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(str)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg

    def run(self):
        cfg = self.cfg
        pairs = cfg["pairs"]                  # [(img, lbl, group_key)]
        out_dir = cfg["out_dir"]
        os.makedirs(out_dir, exist_ok=True)

        total = len(pairs)
        # Dağıtımın kendisi veri_bolme'de: aynı grubun kareleri asla ikiye
        # ayrılmaz (val sızıntısı olmaz), oranlar yine de korunur.
        kova = bolumlere_dagit([k for _i, _l, k in pairs],
                               cfg["ratios"], cfg["seed"])
        buckets = {ad: [(pairs[i][0], pairs[i][1]) for i in idxs]
                   for ad, idxs in kova.items()}
        grup_sayisi = len({k for _i, _l, k in pairs})

        self.log.emit(f"{grup_sayisi} grup → " + ", ".join(
            f"{k}: {len(v)} görsel" for k, v in buckets.items()))

        names = cfg["names"]
        report = [f"Bölme (tohum {cfg['seed']}, gruplama: {cfg['group_desc']})",
                  f"Toplam {total} görsel, {grup_sayisi} grup", ""]

        mode = cfg["mode"]
        done_n = 0
        for split, rows in buckets.items():
            if not rows:
                continue
            if mode == "list":
                with open(os.path.join(out_dir, f"{split}.txt"), "w", encoding="utf-8") as f:
                    for img, _lbl in rows:
                        f.write(os.path.abspath(img) + "\n")
            else:
                img_dst = os.path.join(out_dir, "images", split)
                lbl_dst = os.path.join(out_dir, "labels", split)
                os.makedirs(img_dst, exist_ok=True)
                os.makedirs(lbl_dst, exist_ok=True)
                for img, lbl in rows:
                    try:
                        di = os.path.join(img_dst, os.path.basename(img))
                        if mode == "symlink":
                            if not os.path.exists(di):
                                os.symlink(os.path.abspath(img), di)
                        else:
                            shutil.copy2(img, di)
                        if lbl:
                            dl = os.path.join(lbl_dst, os.path.basename(lbl))
                            if mode == "symlink":
                                if not os.path.exists(dl):
                                    os.symlink(os.path.abspath(lbl), dl)
                            else:
                                shutil.copy2(lbl, dl)
                    except OSError as e:
                        self.log.emit(f"HATA — {os.path.basename(img)}: {e}")
                    done_n += 1
                    self.progress.emit(done_n, total)

            # bölüm istatistiği
            cls_counts, nbox = {}, 0
            for _img, lbl in rows:
                if not lbl:
                    continue
                boxes, _e, _w = parse_label_file(lbl, cfg["nc"], 0.0)
                nbox += len(boxes)
                for c, *_ in boxes:
                    cname = names.get(c, str(c))
                    cls_counts[cname] = cls_counts.get(cname, 0) + 1
            report.append(f"[{split}] {len(rows)} görsel, {nbox} kutu")
            for cname in sorted(cls_counts, key=lambda k: -cls_counts[k]):
                report.append(f"    {cname:<20s} {cls_counts[cname]}")
            eksik = [names[i] for i in sorted(names) if names[i] not in cls_counts]
            if eksik and split in ("val", "test"):
                report.append(f"    UYARI: {split} içinde hiç örneği olmayan sınıf: "
                              + ", ".join(eksik))
            report.append("")

        # data.yaml
        yaml_path = os.path.join(out_dir, "data.yaml")
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(f"path: {os.path.abspath(out_dir)}\n")
            if mode == "list":
                f.write("train: train.txt\n")
                f.write("val: val.txt\n" if buckets["val"] else "val: train.txt\n")
                if buckets["test"]:
                    f.write("test: test.txt\n")
            else:
                f.write("train: images/train\n")
                f.write("val: images/val\n" if buckets["val"] else "val: images/train\n")
                if buckets["test"]:
                    f.write("test: images/test\n")
            f.write(f"nc: {len(names) or cfg['nc']}\n")
            f.write("names:\n")
            for i in sorted(names):
                f.write(f"  {i}: {names[i]}\n")
        report.append(f"data.yaml yazıldı: {yaml_path}")
        self.done.emit("\n".join(report))


# ─────────────────────────────────────────────── önizleme

class PreviewCanvas(QWidget):
    """Görseli oranını koruyarak gösterir, üzerine kutuları çizer."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(260)
        self._img = None
        self._boxes = []
        self._names = {}
        self._info = "Soldaki listeden bir görsel seç"

    def show_item(self, img_path: str, boxes: list, names: dict, info: str = ""):
        img = QImage(img_path)
        self._img = None if img.isNull() else img
        self._boxes = boxes
        self._names = names
        self._info = info or os.path.basename(img_path)
        self.update()

    def clear_item(self, info="Görsel yok"):
        self._img = None
        self._boxes = []
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
        scale = min(self.width() / iw, (self.height() - 18) / ih)
        dw, dh = iw * scale, ih * scale
        ox, oy = (self.width() - dw) / 2, (self.height() - 18 - dh) / 2
        p.drawImage(QRectF(ox, oy, dw, dh), self._img)

        f = QFont("monospace", 8)
        p.setFont(f)
        for cls, x, y, w, h in self._boxes:
            color = QColor(CLASS_COLORS[cls % len(CLASS_COLORS)])
            pen = QPen(color)
            pen.setWidth(2)
            if cls >= len(CLASS_COLORS):       # ikinci tur: kesikli
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            bx = ox + (x - w / 2) * dw
            by = oy + (y - h / 2) * dh
            p.drawRect(QRectF(bx, by, w * dw, h * dh))
            label = self._names.get(cls, str(cls))
            p.fillRect(QRectF(bx, by - 13, 8 + 6.5 * len(label), 13), QColor(0, 0, 0, 170))
            p.setPen(color)
            p.drawText(QRectF(bx + 3, by - 13, 200, 13), Qt.AlignVCenter, label)

        p.setPen(QColor("#4d5765"))
        p.drawText(QRectF(4, self.height() - 17, self.width() - 8, 16),
                   Qt.AlignVCenter, f"{self._info}   ({iw}×{ih}, {len(self._boxes)} kutu)")


# ─────────────────────────────────────────────── ana pencere

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Veri Denetçi — YOLO veri seti kontrolü ve bölme")
        self.setMinimumSize(1320, 800)
        self._img_dir = ""
        self._lbl_dir = ""
        self._names = {}
        self._items = []
        self._orphans = []
        self._dup_groups = []
        self._shown = []            # listede görünen item indeksleri
        self._worker = None
        self._split_worker = None
        self._build_ui()
        self._build_menu()

    # ── UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right())
        splitter.setSizes([300, 660, 360])
        v.addWidget(splitter, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Veri seti klasörünü seç → Denetle")

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(260)
        w.setMaximumWidth(380)
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.filter_combo = QComboBox()
        for text, key in (("Hepsi", "all"), ("Bozuk (!)", "err"), ("Şüpheli (?)", "warn"),
                          ("Etiketsiz (○)", "nolbl"), ("Yakın-kopya (»)", "dup"),
                          ("Temiz (✓)", "ok")):
            self.filter_combo.addItem(text, key)
        self.filter_combo.currentIndexChanged.connect(self._refill_list)
        v.addWidget(self.filter_combo)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._show_row)
        v.addWidget(self.file_list, 1)

        self.count_lbl = QLabel("0 kayıt")
        self.count_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(self.count_lbl)

        h = QHBoxLayout()
        h.setSpacing(6)
        b1 = QPushButton("Seçilenleri Karantinaya Al")
        b1.setToolTip("Görsel + etiketi _karantina/ klasörüne taşır (silmez)")
        b1.clicked.connect(self._quarantine_selected)
        h.addWidget(b1)
        v.addLayout(h)

        b2 = QPushButton("Kopya Fazlalıklarını Karantinaya Al")
        b2.setToolTip("Her kopya grubunda ilk görsel kalır, gerisi taşınır")
        b2.clicked.connect(self._quarantine_dups)
        v.addWidget(b2)
        return w

    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.canvas = PreviewCanvas()
        v.addWidget(self.canvas, 3)

        self.tabs = QTabWidget()
        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs.addTab(self.report_box, "Rapor")

        self.detail_box = QTextEdit()
        self.detail_box.setReadOnly(True)
        self.detail_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs.addTab(self.detail_box, "Seçili Dosya")

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs.addTab(self.log_box, "Log")
        v.addWidget(self.tabs, 2)
        return w

    def _path_row(self, edit: QLineEdit, slot) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        edit.setReadOnly(True)
        edit.setStyleSheet("font-size:11px; font-family:monospace;")
        h.addWidget(edit, 1)
        b = QPushButton("Seç…")
        b.setFixedWidth(58)
        b.clicked.connect(slot)
        h.addWidget(b)
        return h

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(330)
        w.setMaximumWidth(430)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        # Veri seti
        grp = QGroupBox("Veri Seti")
        g = QVBoxLayout(grp)
        g.setSpacing(6)
        self.root_edit = QLineEdit()
        self.root_edit.setPlaceholderText("veri seti kökü (images/ + labels/)")
        g.addLayout(self._path_row(self.root_edit, self._pick_root))
        self.img_edit = QLineEdit()
        self.img_edit.setPlaceholderText("görseller")
        g.addLayout(self._path_row(self.img_edit, self._pick_img))
        self.lbl_edit = QLineEdit()
        self.lbl_edit.setPlaceholderText("etiketler (.txt)")
        g.addLayout(self._path_row(self.lbl_edit, self._pick_lbl))
        self.names_lbl = QLabel("Sınıflar: —")
        self.names_lbl.setWordWrap(True)
        self.names_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        g.addWidget(self.names_lbl)

        self.merge_btn = QPushButton("⇉  Veri Setlerini Birleştir…")
        self.merge_btn.setToolTip(
            "Birden çok veri setini tek sete indirger. Sınıf id'leri setler arasında\n"
            "farklıysa hangisinin neye denk geleceğini tek tek seçersin — üst üste\n"
            "kopyalamak etiketleri sessizce bozar.")
        self.merge_btn.clicked.connect(self._birlestir_ac)
        g.addWidget(self.merge_btn)
        v.addWidget(grp)

        # Denetim
        grp2 = QGroupBox("Denetim")
        g2 = QVBoxLayout(grp2)
        g2.setSpacing(6)

        def row(text, widget):
            h = QHBoxLayout()
            lb = QLabel(text)
            lb.setStyleSheet("font-weight:normal;")
            h.addWidget(lb)
            h.addStretch()
            h.addWidget(widget)
            return h

        self.minarea_spin = QDoubleSpinBox()
        self.minarea_spin.setRange(0.0, 5.0)
        self.minarea_spin.setDecimals(3)
        self.minarea_spin.setSingleStep(0.01)
        self.minarea_spin.setValue(0.02)
        self.minarea_spin.setSuffix(" %")
        self.minarea_spin.setFixedWidth(100)
        self.minarea_spin.setToolTip("Bundan küçük alanlı kutular şüpheli işaretlenir")
        g2.addLayout(row("Küçük kutu eşiği", self.minarea_spin))

        self.readable_chk = QCheckBox("Görselleri açıp bozuk olanları bul")
        self.readable_chk.setChecked(True)
        g2.addWidget(self.readable_chk)

        self.hash_chk = QCheckBox("Yakın-kopyaları tara")
        self.hash_chk.setChecked(True)
        g2.addWidget(self.hash_chk)

        self.hash_spin = QSpinBox()
        self.hash_spin.setRange(0, 20)
        self.hash_spin.setValue(5)
        self.hash_spin.setFixedWidth(100)
        self.hash_spin.setToolTip("Hamming mesafesi: 0 = birebir aynı, 5 = çok benzer, "
                                  "10+ = gevşek")
        g2.addLayout(row("Kopya eşiği", self.hash_spin))

        self.audit_btn = QPushButton("🔍  Denetle")
        self.audit_btn.setMinimumHeight(36)
        self.audit_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.audit_btn.clicked.connect(self._start_audit)
        g2.addWidget(self.audit_btn)
        v.addWidget(grp2)

        # Bölme
        grp3 = QGroupBox("Train / Val / Test Bölmesi")
        g3 = QVBoxLayout(grp3)
        g3.setSpacing(6)

        h_r = QHBoxLayout()
        self.tr_spin, self.va_spin, self.te_spin = (QDoubleSpinBox() for _ in range(3))
        for sp, val, name in ((self.tr_spin, 0.80, "train"), (self.va_spin, 0.20, "val"),
                              (self.te_spin, 0.00, "test")):
            sp.setRange(0.0, 1.0)
            sp.setSingleStep(0.05)
            sp.setDecimals(2)
            sp.setValue(val)
            sp.setPrefix(f"{name} ")
            h_r.addWidget(sp)
        g3.addLayout(h_r)

        self.group_combo = QComboBox()
        self.group_combo.addItem("Yakın-kopya grubu (önerilen)", "dup")
        self.group_combo.addItem("Alt klasör adı", "folder")
        self.group_combo.addItem("Dosya adı: ilk _ öncesi", "prefix")
        self.group_combo.addItem("Gruplama yok (rastgele)", "none")
        self.group_combo.setToolTip(
            "Aynı gruptaki görseller aynı bölüme gider.\n"
            "Video karelerinde bu, val sızıntısını (aynı sahnenin hem train hem "
            "val'de olması) engeller.")
        g3.addWidget(self.group_combo)

        self.excl_dup_chk = QCheckBox("Kopya fazlalıklarını bölmeye alma")
        self.excl_dup_chk.setChecked(True)
        self.excl_dup_chk.setToolTip("Her kopya grubundan sadece bir temsilci kullanılır")
        g3.addWidget(self.excl_dup_chk)

        self.only_labeled_chk = QCheckBox("Sadece etiketi olan görseller")
        self.only_labeled_chk.setChecked(True)
        g3.addWidget(self.only_labeled_chk)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Liste dosyaları (train.txt/val.txt)", "list")
        self.mode_combo.addItem("Klasöre kopyala", "copy")
        self.mode_combo.addItem("Sembolik bağ (symlink)", "symlink")
        self.mode_combo.setToolTip("Liste modu veriyi çoğaltmaz; ultralytics txt listeyi "
                                  "doğrudan okur")
        g3.addWidget(self.mode_combo)

        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 99999)
        self.seed_spin.setValue(42)
        self.seed_spin.setFixedWidth(100)
        g3.addLayout(row("Rastgelelik tohumu", self.seed_spin))

        self.split_out_edit = QLineEdit()
        self.split_out_edit.setPlaceholderText("bölme çıktı klasörü")
        g3.addLayout(self._path_row(self.split_out_edit, self._pick_split_out))

        self.split_btn = QPushButton("✂  Bölmeyi Oluştur")
        self.split_btn.setMinimumHeight(36)
        self.split_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.split_btn.clicked.connect(self._start_split)
        self.split_btn.setEnabled(False)
        g3.addWidget(self.split_btn)
        v.addWidget(grp3)

        h_p = QHBoxLayout()
        h_p.setSpacing(6)
        self.progress = QProgressBar()
        h_p.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setFixedWidth(70)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        h_p.addWidget(self.cancel_btn)
        v.addLayout(h_p)

        self.save_report_btn = QPushButton("Raporu Kaydet…")
        self.save_report_btn.clicked.connect(self._save_report)
        v.addWidget(self.save_report_btn)

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

        act("Veri Seti Kökü…", self._pick_root, "Ctrl+O")
        act("Denetle", self._start_audit, "Ctrl+R")
        act("Raporu Kaydet…", self._save_report, "Ctrl+S")
        m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    # ── yol seçimleri
    def _log(self, t: str):
        self.log_box.append(t)

    def _pick_root(self):
        d = QFileDialog.getExistingDirectory(self, "Veri seti kökü", self.root_edit.text())
        if not d:
            return
        self.root_edit.setText(d)
        img, lbl = detect_dirs(d)
        self._set_dirs(img, lbl)
        self._log(f"Kök: {d}\n  görseller: {img}\n  etiketler: {lbl}")

    def _pick_img(self):
        d = QFileDialog.getExistingDirectory(self, "Görsel klasörü", self.img_edit.text())
        if d:
            self._set_dirs(d, self._lbl_dir or d)

    def _pick_lbl(self):
        d = QFileDialog.getExistingDirectory(self, "Etiket klasörü", self.lbl_edit.text())
        if d:
            self._set_dirs(self._img_dir or d, d)

    def _set_dirs(self, img: str, lbl: str):
        self._img_dir, self._lbl_dir = img, lbl
        self.img_edit.setText(img)
        self.lbl_edit.setText(lbl)
        for e in (self.img_edit, self.lbl_edit, self.root_edit):
            e.setToolTip(e.text())
            e.setCursorPosition(0)
        self._names = load_class_names(lbl, img, self.root_edit.text())
        if self._names:
            self.names_lbl.setText(f"{len(self._names)} sınıf: " +
                                   ", ".join(self._names[i] for i in sorted(self._names)))
        else:
            self.names_lbl.setText("Sınıflar: data.yaml/classes.txt bulunamadı "
                                   "(id'ler sayı olarak gösterilir)")
        if not self.split_out_edit.text():
            self.split_out_edit.setText(os.path.join(
                os.path.dirname(img.rstrip(os.sep)) or img, "split"))

    def _birlestir_ac(self):
        """Birleştirme diyalogunu aç; kapanınca çıktı klasörünü denetime yükle.

        Modül burada import ediliyor: birleştirme çoğu oturumda hiç açılmıyor,
        araç açılışını onun için yavaşlatmanın anlamı yok.
        """
        from .veri_birlestir import BirlestirDialog
        d = BirlestirDialog(self)
        d.exec_()
        out = d.out_edit.text().strip()
        img = os.path.join(out, "images")
        if out and os.path.isdir(img):
            if QMessageBox.question(
                    self, "Birleşik seti denetle",
                    "Birleştirilen veri seti denetime yüklensin mi?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes) == QMessageBox.Yes:
                self._set_dirs(img, os.path.join(out, "labels"))
                self.root_edit.setText(out)

    def _pick_split_out(self):
        d = QFileDialog.getExistingDirectory(self, "Bölme çıktı klasörü",
                                             self.split_out_edit.text())
        if d:
            self.split_out_edit.setText(d)

    # ── denetim
    def _start_audit(self):
        if self._worker or self._split_worker:
            return
        if not self._img_dir or not os.path.isdir(self._img_dir):
            QMessageBox.warning(self, "Klasör yok", "Görsel klasörünü seç.")
            return
        cfg = {
            "img_dir": self._img_dir,
            "lbl_dir": self._lbl_dir or self._img_dir,
            "nc": len(self._names),
            "min_area": self.minarea_spin.value() / 100.0,
            "do_hash": self.hash_chk.isChecked(),
            "hash_thresh": self.hash_spin.value(),
            "check_readable": self.readable_chk.isChecked(),
        }
        self._log("── denetim başlıyor ──")      # log geçmişi korunur
        self._worker = AuditWorker(cfg)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log)
        self._worker.result.connect(self._on_audit_result)
        self._worker.finished.connect(self._on_worker_finished)
        self.audit_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self._worker.start()

    def _on_progress(self, done: int, total: int):
        self.progress.setMaximum(total)
        self.progress.setValue(done)
        self.status.showMessage(f"{done}/{total}")

    def _on_audit_result(self, res: dict):
        self._items = res["items"]
        self._orphans = res["orphans"]
        self._dup_groups = res["dup_groups"]
        self._refill_list()
        self.report_box.setPlainText(self._build_report())
        self.tabs.setCurrentIndex(0)
        self.split_btn.setEnabled(bool(self._items))
        self.status.showMessage("Denetim bitti." + (" (iptal edildi)" if res["iptal"] else ""))

    def _mark(self, it: dict) -> str:
        if it["errors"]:
            return MARK_ERR
        if it["lbl"] is None:
            return MARK_NOLBL
        if it.get("dup_group") is not None and not it.get("dup_rep"):
            return MARK_DUP
        if it["warns"]:
            return MARK_WARN
        return MARK_OK

    def _refill_list(self):
        key = self.filter_combo.currentData()
        self.file_list.clear()
        self._shown = []
        for i, it in enumerate(self._items):
            mark = self._mark(it)
            keep = (key == "all"
                    or (key == "err" and it["errors"])
                    or (key == "warn" and it["warns"] and not it["errors"])
                    or (key == "nolbl" and it["lbl"] is None)
                    or (key == "dup" and it.get("dup_group") is not None)
                    or (key == "ok" and mark == MARK_OK))
            if not keep:
                continue
            extra = ""
            if it.get("dup_group") is not None:
                extra = f"  [kopya g{it['dup_group']}" + ("/temsilci]" if it.get("dup_rep") else "]")
            item = QListWidgetItem(f"{mark} {os.path.basename(it['img'])}"
                                   f"  ({len(it['boxes'])}){extra}")
            item.setData(Qt.UserRole, i)
            item.setToolTip(it["img"])
            self.file_list.addItem(item)
            self._shown.append(i)
        self.count_lbl.setText(f"{len(self._shown)} / {len(self._items)} kayıt")

    def _show_row(self, row: int):
        if row < 0 or row >= len(self._shown):
            return
        it = self._items[self._shown[row]]
        self.canvas.show_item(it["img"], it["boxes"], self._names)
        lines = [it["img"], f"etiket: {it['lbl'] or '(yok)'}",
                 f"kutu sayısı: {len(it['boxes'])}"]
        if it.get("dup_group") is not None:
            grp = self._dup_groups[it["dup_group"]]
            lines.append(f"kopya grubu {it['dup_group']} — {len(grp)} görsel"
                         + ("  (temsilci)" if it.get("dup_rep") else ""))
            for idx in grp[:12]:
                lines.append("    " + os.path.basename(self._items[idx]["img"]))
        if it["errors"]:
            lines.append("\nBOZUK:")
            lines += ["  " + e for e in it["errors"]]
        if it["warns"]:
            lines.append("\nŞÜPHELİ:")
            lines += ["  " + wn for wn in it["warns"]]
        self.detail_box.setPlainText("\n".join(lines))

    # ── rapor
    def _build_report(self) -> str:
        items = self._items
        n = len(items)
        labeled = [i for i in items if i["lbl"]]
        errs = [i for i in items if i["errors"]]
        warns = [i for i in items if i["warns"] and not i["errors"]]
        nolbl = [i for i in items if i["lbl"] is None]
        boxes_total = sum(len(i["boxes"]) for i in items)

        cls_counts = {}
        area_buckets = {"küçük (<%0,5)": 0, "orta (%0,5-5)": 0, "büyük (>%5)": 0}
        per_img = {}
        for it in items:
            per_img[len(it["boxes"])] = per_img.get(len(it["boxes"]), 0) + 1
            for c, _x, _y, w, h in it["boxes"]:
                name = self._names.get(c, str(c))
                cls_counts[name] = cls_counts.get(name, 0) + 1
                a = w * h
                if a < 0.005:
                    area_buckets["küçük (<%0,5)"] += 1
                elif a < 0.05:
                    area_buckets["orta (%0,5-5)"] += 1
                else:
                    area_buckets["büyük (>%5)"] += 1

        L = []
        L.append("═══ VERİ SETİ RAPORU ═══")
        L.append(f"görseller      : {self._img_dir}")
        L.append(f"etiketler      : {self._lbl_dir}")
        L.append("")
        L.append(f"görsel sayısı  : {n}")
        L.append(f"etiketli       : {len(labeled)}")
        L.append(f"etiketsiz      : {len(nolbl)}")
        L.append(f"bozuk kayıt    : {len(errs)}")
        L.append(f"şüpheli kayıt  : {len(warns)}")
        L.append(f"görselsiz etiket: {len(self._orphans)}")
        fazlalik = sum(len(g) - 1 for g in self._dup_groups)
        L.append(f"kopya grubu    : {len(self._dup_groups)}  (fazlalık {fazlalik} görsel)")
        L.append(f"toplam kutu    : {boxes_total}")
        if labeled:
            L.append(f"kutu/görsel    : {boxes_total / len(labeled):.2f} ortalama")
        L.append("")

        if cls_counts:
            L.append("── Sınıf dağılımı ──")
            mx = max(cls_counts.values())
            for name in sorted(cls_counts, key=lambda k: -cls_counts[k]):
                c = cls_counts[name]
                L.append(f"{name:<22s} {bar(c, mx)} {c:>6d}  (%{100 * c / boxes_total:.1f})")
            az = [k for k, v in cls_counts.items() if v < 0.2 * mx]
            if az:
                L.append(f"  ! dengesiz: {', '.join(az)} — en çok görülen sınıfın "
                         "%20'sinden az örneği var")
            eksik = [self._names[i] for i in sorted(self._names)
                     if self._names[i] not in cls_counts]
            if eksik:
                L.append(f"  ! hiç örneği olmayan sınıf: {', '.join(eksik)}")
            L.append("")

        if boxes_total:
            L.append("── Kutu boyutu ──")
            mx = max(area_buckets.values())
            for k, vv in area_buckets.items():
                L.append(f"{k:<22s} {bar(vv, mx)} {vv:>6d}")
            kucuk = area_buckets["küçük (<%0,5)"]
            if kucuk > 0.3 * boxes_total:
                L.append("  ! kutuların çoğu çok küçük — imgsz'yi büyütmek doğruluğu artırır")
            L.append("")

        L.append("── Görsel başına kutu ──")
        mx = max(per_img.values()) if per_img else 1
        for k in sorted(per_img):
            L.append(f"{k:>3d} kutu               {bar(per_img[k], mx)} {per_img[k]:>6d}")
        L.append("")

        if errs:
            L.append("── Bozuk kayıtlar (ilk 40) ──")
            for it in errs[:40]:
                L.append(f"{os.path.basename(it['img'])}: {it['errors'][0]}")
            if len(errs) > 40:
                L.append(f"… ve {len(errs) - 40} tane daha")
            L.append("")

        if self._orphans:
            L.append("── Görseli olmayan etiketler (ilk 20) ──")
            for p in self._orphans[:20]:
                L.append("  " + os.path.basename(p))
            L.append("")

        if self._dup_groups:
            L.append("── En büyük kopya grupları ──")
            for grp in sorted(self._dup_groups, key=len, reverse=True)[:10]:
                names = ", ".join(os.path.basename(self._items[i]["img"]) for i in grp[:4])
                L.append(f"  {len(grp)} görsel: {names}" + (" …" if len(grp) > 4 else ""))
            L.append("  → 'Kopya Fazlalıklarını Karantinaya Al' ile temizlenebilir")
        return "\n".join(L)

    def _save_report(self):
        if not self.report_box.toPlainText():
            self.status.showMessage("Önce denetle.")
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "Raporu kaydet",
            os.path.join(self._img_dir or "", "veri_raporu.txt"), "Metin (*.txt)")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.report_box.toPlainText())
            self.status.showMessage(f"Rapor kaydedildi: {p}")
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")

    # ── karantina
    def _quarantine(self, indices: list, baslik: str):
        if self._worker or self._split_worker:
            self.status.showMessage("İşlem sürüyor — bitmesini bekle.")
            return
        if not indices:
            self.status.showMessage("Taşınacak kayıt yok.")
            return
        root = os.path.dirname(self._img_dir.rstrip(os.sep)) or self._img_dir
        qdir = os.path.join(root, "_karantina")
        if QMessageBox.question(
                self, baslik,
                f"{len(indices)} görsel (varsa etiketiyle birlikte) şuraya taşınacak:\n"
                f"{qdir}\n\nDosyalar silinmiyor, geri alabilirsin. Devam?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        qi = os.path.join(qdir, "images")
        ql = os.path.join(qdir, "labels")
        os.makedirs(qi, exist_ok=True)
        os.makedirs(ql, exist_ok=True)
        moved = 0
        for i in indices:
            it = self._items[i]
            try:
                shutil.move(it["img"], os.path.join(qi, os.path.basename(it["img"])))
                if it["lbl"] and os.path.exists(it["lbl"]):
                    shutil.move(it["lbl"], os.path.join(ql, os.path.basename(it["lbl"])))
                moved += 1
            except OSError as e:
                self._log(f"HATA — taşınamadı {it['img']}: {e}")
        self._log(f"{moved} kayıt karantinaya taşındı → {qdir}")
        for i in sorted(indices, reverse=True):
            del self._items[i]
        self._dup_groups = []          # indeksler kaydı → yeniden denetim şart
        for it in self._items:
            it["dup_group"] = None
        self._refill_list()
        if moved:
            # Taşıma sonrası kopya grupları geçersiz kaldı: denetimi tazele
            self.status.showMessage(f"{moved} kayıt taşındı — denetim tazeleniyor…")
            self._log("── taşıma sonrası yeniden denetim ──")
            QTimer.singleShot(0, self._start_audit)
        else:
            self.status.showMessage("Hiçbir kayıt taşınamadı (loga bak).")

    def _quarantine_selected(self):
        rows = [self._shown[self.file_list.row(x)] for x in self.file_list.selectedItems()]
        self._quarantine(rows, "Seçilenleri karantinaya al")

    def _quarantine_dups(self):
        extra = []
        for grp in self._dup_groups:
            extra += grp[1:]
        self._quarantine(sorted(set(extra)), "Kopya fazlalıklarını karantinaya al")

    # ── bölme
    def _group_key(self, it: dict, idx: int, mode: str) -> str:
        if mode == "dup":
            g = it.get("dup_group")
            return f"dup{g}" if g is not None else f"tek{idx}"
        if mode == "folder":
            return os.path.relpath(os.path.dirname(it["img"]), self._img_dir)
        if mode == "prefix":
            return os.path.basename(it["img"]).split("_")[0]
        return f"tek{idx}"

    def _start_split(self):
        if self._worker or self._split_worker:
            return
        if not self._items:
            QMessageBox.warning(self, "Veri yok", "Önce denetle.")
            return
        ratios = (self.tr_spin.value(), self.va_spin.value(), self.te_spin.value())
        total_r = sum(ratios)
        if total_r <= 0:
            QMessageBox.warning(self, "Oran hatası", "Oranların toplamı 0 olamaz.")
            return
        ratios = tuple(r / total_r for r in ratios)
        out_dir = self.split_out_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Klasör yok", "Bölme çıktı klasörünü seç.")
            return

        mode_group = self.group_combo.currentData()
        pairs, atlanan = [], 0
        for idx, it in enumerate(self._items):
            if it["errors"]:
                atlanan += 1
                continue
            if self.only_labeled_chk.isChecked() and not it["lbl"]:
                atlanan += 1
                continue
            if self.excl_dup_chk.isChecked() and it.get("dup_group") is not None \
                    and not it.get("dup_rep"):
                atlanan += 1
                continue
            pairs.append((it["img"], it["lbl"], self._group_key(it, idx, mode_group)))

        if not pairs:
            QMessageBox.warning(self, "Boş", "Bölünecek görsel kalmadı (filtreler çok sıkı).")
            return

        self._log(f"Bölme: {len(pairs)} görsel, {atlanan} atlandı "
                  f"(bozuk/etiketsiz/kopya fazlası)")
        cfg = {
            "pairs": pairs, "ratios": ratios, "out_dir": out_dir,
            "seed": self.seed_spin.value(), "mode": self.mode_combo.currentData(),
            "names": self._names, "nc": len(self._names),
            "group_desc": self.group_combo.currentText(),
        }
        self._split_worker = SplitWorker(cfg)
        self._split_worker.log.connect(self._log)
        self._split_worker.progress.connect(self._on_progress)
        self._split_worker.done.connect(self._on_split_done)
        self._split_worker.finished.connect(self._on_worker_finished)
        self.split_btn.setEnabled(False)
        self.audit_btn.setEnabled(False)
        self._split_worker.start()

    def _on_split_done(self, report: str):
        self.report_box.setPlainText(report + "\n\n" +
                                     "─" * 40 + "\n" + self.report_box.toPlainText())
        self.tabs.setCurrentIndex(0)
        self.status.showMessage("Bölme tamam.")

    # ── ortak
    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self.status.showMessage("İptal isteniyor…")

    def _on_worker_finished(self):
        self._worker = None
        self._split_worker = None
        self.audit_btn.setEnabled(True)
        self.split_btn.setEnabled(bool(self._items))
        self.cancel_btn.setEnabled(False)

    def closeEvent(self, ev):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
        if self._split_worker:
            self._split_worker.wait(3000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    # Tek başına çalıştırıldığında tema ayarını kabuk yüklemez; buradan okunur
    from .. import tema as _tema
    _tema.tema_yukle()
    _tema.yamalari_kur()
    app.setStyleSheet(_tema.stil())
    app.setApplicationName("Veri Denetçi")
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        win.root_edit.setText(sys.argv[1])
        img, lbl = detect_dirs(sys.argv[1])
        win._set_dirs(img, lbl)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
