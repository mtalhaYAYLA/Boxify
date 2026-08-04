import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QSplitter, QListWidget,
                              QListWidgetItem, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFileDialog, QStatusBar,
                              QMessageBox, QFrame, QAction, QShortcut)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QKeySequence, QIcon, QPixmap

from core.dataset import Dataset
from core.annotation import BBox
from ui.canvas import Canvas
from ui.label_panel import LabelPanel
from ui.training_dialog import TrainingDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dataset = Dataset()
        self.setWindowTitle("YOLOLabel")
        self.setMinimumSize(1200, 720)
        self._build_ui()
        self._build_menu()
        self._build_shortcuts()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)

        splitter.addWidget(self._build_image_list())
        splitter.addWidget(self._build_canvas_area())

        self.label_panel = LabelPanel()
        self.label_panel.class_added.connect(self._on_class_added)
        self.label_panel.class_removed.connect(self._on_class_removed)
        self.label_panel.class_selected.connect(self._on_class_selected)
        self.label_panel.class_renamed.connect(self._on_class_renamed)
        self.label_panel.class_recolored.connect(self._on_class_recolored)
        splitter.addWidget(self.label_panel)

        splitter.setSizes([200, 820, 200])
        vbox.addWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Hoş geldiniz — Dosya > Klasör Aç ile başlayın")

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background:#222; border-bottom:1px solid #3a3a3a;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)

        def btn(text, slot, tip="", color=""):
            b = QPushButton(text)
            if tip:
                b.setToolTip(tip)
            if color:
                b.setStyleSheet(f"background:{color}; color:white; font-weight:bold; padding:5px 14px;")
            b.clicked.connect(slot)
            return b

        row.addWidget(btn("Klasör Aç", self._open_folder, "Ctrl+O"))
        row.addWidget(btn("Kaydet", self._save_current, "Ctrl+S"))
        row.addWidget(btn("Tümünü Kaydet", self._save_all, "Ctrl+Shift+S"))
        row.addStretch()

        self.prev_btn = btn("◀  Önceki", self._prev)
        self.prev_btn.setEnabled(False)
        row.addWidget(self.prev_btn)

        self.nav_lbl = QLabel("—")
        self.nav_lbl.setAlignment(Qt.AlignCenter)
        self.nav_lbl.setMinimumWidth(90)
        self.nav_lbl.setStyleSheet("color:#ccc; font-size:13px;")
        row.addWidget(self.nav_lbl)

        self.next_btn = btn("Sonraki  ▶", self._next)
        self.next_btn.setEnabled(False)
        row.addWidget(self.next_btn)

        row.addStretch()
        row.addWidget(btn("  Eğitimi Başlat  ", self._open_training, color="#1b5e20"))

        return bar

    def _build_image_list(self) -> QWidget:
        w = QWidget()
        w.setMaximumWidth(230)
        w.setMinimumWidth(160)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(4, 6, 4, 4)

        lbl = QLabel("Resimler")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:2px 4px;")
        vbox.addWidget(lbl)

        self.img_list = QListWidget()
        self.img_list.currentRowChanged.connect(self._on_image_row_changed)
        vbox.addWidget(self.img_list)

        self.labeled_lbl = QLabel("Etiketli: 0 / 0")
        self.labeled_lbl.setStyleSheet("color:#777; font-size:11px; padding:2px 4px;")
        vbox.addWidget(self.labeled_lbl)

        return w

    def _build_canvas_area(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        self.canvas = Canvas()
        self.canvas.bbox_added.connect(self._on_bbox_added)
        self.canvas.bbox_deleted.connect(self._on_bbox_deleted)
        self.canvas.bbox_class_changed.connect(self._on_bbox_class_changed)
        self.canvas.bbox_modified.connect(self._update_status)
        vbox.addWidget(self.canvas)
        return w

    def _build_menu(self):
        mb = self.menuBar()
        file_m = mb.addMenu("Dosya")

        def act(label, slot, shortcut=""):
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            file_m.addAction(a)

        act("Klasör Aç", self._open_folder, "Ctrl+O")
        act("Kaydet", self._save_current, "Ctrl+S")
        act("Tümünü Kaydet", self._save_all, "Ctrl+Shift+S")
        file_m.addSeparator()
        act("Eğitim Başlat...", self._open_training)
        file_m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    def _build_shortcuts(self):
        for key in (Qt.Key_Left, Qt.Key_A):
            QShortcut(QKeySequence(key), self, self._prev)
        for key in (Qt.Key_Right, Qt.Key_D):
            QShortcut(QKeySequence(key), self, self._next)

    # ------------------------------------------------------------------ slots

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Resim Klasörü Seç")
        if not folder:
            return
        self._autosave()
        self.dataset.load_folder(folder)
        self.dataset.load_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        self._refresh_list()
        if self.dataset.images:
            self._load(0)
        self.setWindowTitle(f"YOLOLabel — {os.path.basename(folder)}")
        self.status.showMessage(f"{len(self.dataset.images)} resim yüklendi: {folder}")

    def _load(self, idx: int):
        self._autosave()
        self.dataset.current_index = idx
        ann = self.dataset.current_image
        if ann is None:
            return

        pix = QPixmap(ann.image_path)
        if pix.isNull():
            self.status.showMessage(f"Yüklenemedi: {ann.image_path}")
            return

        ann.img_width = pix.width()
        ann.img_height = pix.height()
        ann.load()

        self.canvas.set_image(pix)
        self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
        self.canvas.set_current_class(self.label_panel.current_class_id)

        self.img_list.blockSignals(True)
        self.img_list.setCurrentRow(idx)
        self.img_list.blockSignals(False)

        self._update_nav()
        self._update_list_item(idx)
        self._update_status()

    def _autosave(self):
        ann = self.dataset.current_image
        if ann and ann.img_width > 0:
            ann.save()
            self._update_list_item(self.dataset.current_index)

    def _save_current(self):
        self._autosave()
        self._refresh_labeled_count()
        self.status.showMessage("Kaydedildi.")

    def _save_all(self):
        n = 0
        for ann in self.dataset.images:
            if ann.img_width > 0:
                ann.save()
                n += 1
        self._refresh_list()
        self.status.showMessage(f"{n} dosya kaydedildi.")

    def _prev(self):
        if self.dataset.current_index > 0:
            self._load(self.dataset.current_index - 1)

    def _next(self):
        if self.dataset.current_index < len(self.dataset.images) - 1:
            self._load(self.dataset.current_index + 1)

    def _open_training(self):
        if not self.dataset.images:
            QMessageBox.warning(self, "Uyarı", "Önce bir klasör açın.")
            return
        self._save_all()
        TrainingDialog(self.dataset, self).exec_()

    def _on_image_row_changed(self, row: int):
        if row >= 0 and row != self.dataset.current_index:
            self._load(row)

    def _on_bbox_added(self, x1, y1, x2, y2):
        ann = self.dataset.current_image
        if ann is None:
            return
        if not self.dataset.label_classes:
            QMessageBox.information(self, "Bilgi",
                "Sağ panelden önce bir etiket sınıfı ekleyin.")
            return
        cid = min(self.label_panel.current_class_id,
                  len(self.dataset.label_classes) - 1)
        ann.bboxes.append(BBox(x1, y1, x2, y2, cid))
        self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
        self._update_status()

    def _on_bbox_deleted(self, idx: int):
        ann = self.dataset.current_image
        if ann and 0 <= idx < len(ann.bboxes):
            ann.bboxes.pop(idx)
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
            self._update_status()

    def _on_class_added(self, name, color):
        self.dataset.add_class(name, color)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    def _on_class_removed(self, idx: int):
        self.dataset.remove_class(idx)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    def _on_class_selected(self, cid: int):
        self.canvas.set_current_class(cid)

    def _on_bbox_class_changed(self, bbox_idx: int, new_cid: int):
        ann = self.dataset.current_image
        if ann and 0 <= bbox_idx < len(ann.bboxes):
            ann.bboxes[bbox_idx].class_id = new_cid
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
            self._update_status()

    def _on_class_renamed(self, idx: int, new_name: str):
        self.dataset.rename_class(idx, new_name)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    def _on_class_recolored(self, idx: int, color):
        self.dataset.recolor_class(idx, color)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    # ------------------------------------------------------------------ ui helpers

    def _img_display_name(self, ann) -> str:
        """Alt klasör varsa göreceli yolu göster, yoksa sadece dosya adı."""
        if self.dataset.folder:
            rel = os.path.relpath(ann.image_path, self.dataset.folder)
            return rel
        return os.path.basename(ann.image_path)

    def _refresh_list(self):
        self.img_list.blockSignals(True)
        self.img_list.clear()
        for ann in self.dataset.images:
            item = QListWidgetItem(self._img_display_name(ann))
            item.setToolTip(ann.image_path)
            item.setForeground(QColor(100, 210, 100) if ann.is_labeled
                               else QColor(170, 170, 170))
            self.img_list.addItem(item)
        self.img_list.blockSignals(False)
        self._refresh_labeled_count()

    def _update_list_item(self, idx: int):
        if 0 <= idx < self.img_list.count():
            ann = self.dataset.images[idx]
            item = self.img_list.item(idx)
            item.setText(self._img_display_name(ann))
            item.setForeground(
                QColor(100, 210, 100) if ann.is_labeled else QColor(170, 170, 170)
            )
        self._refresh_labeled_count()

    def _refresh_labeled_count(self):
        labeled = sum(1 for a in self.dataset.images if a.is_labeled)
        total = len(self.dataset.images)
        self.labeled_lbl.setText(f"Etiketli: {labeled} / {total}")

    def _update_nav(self):
        total = len(self.dataset.images)
        cur = self.dataset.current_index
        self.nav_lbl.setText(f"{cur + 1} / {total}")
        self.prev_btn.setEnabled(cur > 0)
        self.next_btn.setEnabled(cur < total - 1)

    def _update_status(self):
        ann = self.dataset.current_image
        if ann:
            fname = os.path.basename(ann.image_path)
            self.status.showMessage(
                f"{fname}  |  {ann.img_width}×{ann.img_height}  |  {len(ann.bboxes)} bbox"
            )

    def closeEvent(self, event):
        self._autosave()
        event.accept()
