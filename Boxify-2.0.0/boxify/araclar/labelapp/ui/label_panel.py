from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QListWidget, QListWidgetItem, QLabel,
                              QInputDialog, QColorDialog)
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtCore import pyqtSignal, Qt

DEFAULT_COLORS = [
    QColor(255, 80, 80), QColor(80, 200, 80), QColor(80, 120, 255),
    QColor(255, 165, 0), QColor(180, 80, 255), QColor(0, 200, 200),
    QColor(255, 60, 180), QColor(0, 180, 100),
]


class LabelPanel(QWidget):
    class_added = pyqtSignal(str, QColor)
    class_removed = pyqtSignal(int)
    class_selected = pyqtSignal(int)
    class_renamed = pyqtSignal(int, str)        # index, yeni_ad
    class_recolored = pyqtSignal(int, QColor)   # index, yeni_renk

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(220)
        self.setMinimumWidth(180)
        self.current_class_id = 0
        self._setup()

    def _setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("Etiket Sınıfları")
        title.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(title)

        self.list_w = QListWidget()
        self.list_w.currentRowChanged.connect(self._on_row_changed)
        self.list_w.itemDoubleClicked.connect(self._rename_current)
        layout.addWidget(self.list_w)

        # Ekle / Sil
        row1 = QHBoxLayout()
        add_btn = QPushButton("+ Ekle")
        add_btn.clicked.connect(self._add)
        rem_btn = QPushButton("Sil")
        rem_btn.clicked.connect(self._remove)
        row1.addWidget(add_btn)
        row1.addWidget(rem_btn)
        layout.addLayout(row1)

        # Yeniden Adlandır / Renk Değiştir
        row2 = QHBoxLayout()
        rename_btn = QPushButton("Adını Değiştir")
        rename_btn.clicked.connect(self._rename_current)
        color_btn = QPushButton("Renk")
        color_btn.clicked.connect(self._recolor_current)
        row2.addWidget(rename_btn)
        row2.addWidget(color_btn)
        layout.addLayout(row2)

        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #444;")
        layout.addWidget(sep)

        hint = QLabel(
            "Sol tık: bbox çiz\n"
            "Sağ tık: menü (sil/sınıf)\n"
            "Del: seçili sil\n"
            "2× tık: adını değiştir\n"
            "A / ◀ : önceki\n"
            "D / ▶ : sonraki"
        )
        hint.setStyleSheet("color: #777; font-size: 11px; line-height: 1.6;")
        layout.addWidget(hint)
        layout.addStretch()

    def _color_icon(self, color: QColor) -> QIcon:
        pix = QPixmap(14, 14)
        pix.fill(color)
        return QIcon(pix)

    def _next_color(self) -> QColor:
        return DEFAULT_COLORS[self.list_w.count() % len(DEFAULT_COLORS)]

    def _add(self):
        name, ok = QInputDialog.getText(self, "Yeni Sınıf", "Sınıf adı:")
        if not (ok and name.strip()):
            return
        color = QColorDialog.getColor(self._next_color(), self, "Renk Seç")
        if color.isValid():
            self.class_added.emit(name.strip(), color)

    def _remove(self):
        row = self.list_w.currentRow()
        if row >= 0:
            self.class_removed.emit(row)

    def _rename_current(self, *_):
        row = self.list_w.currentRow()
        if row < 0:
            return
        current_name = self.list_w.item(row).text().split("  ", 1)[-1]
        name, ok = QInputDialog.getText(self, "Adını Değiştir", "Yeni ad:", text=current_name)
        if ok and name.strip():
            self.class_renamed.emit(row, name.strip())

    def _recolor_current(self):
        row = self.list_w.currentRow()
        if row < 0:
            return
        color = QColorDialog.getColor(parent=self, title="Yeni Renk Seç")
        if color.isValid():
            self.class_recolored.emit(row, color)

    def _on_row_changed(self, row: int):
        if row >= 0:
            self.current_class_id = row
            self.class_selected.emit(row)

    def refresh(self, label_classes):
        self.list_w.blockSignals(True)
        self.list_w.clear()
        for i, lc in enumerate(label_classes):
            item = QListWidgetItem(self._color_icon(lc.color), f"{i}  {lc.name}")
            self.list_w.addItem(item)
        self.list_w.blockSignals(False)
        if self.list_w.count() > 0:
            row = min(self.current_class_id, self.list_w.count() - 1)
            self.current_class_id = row
            self.list_w.setCurrentRow(row)
