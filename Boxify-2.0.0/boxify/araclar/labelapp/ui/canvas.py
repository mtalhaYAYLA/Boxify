from PyQt5.QtWidgets import QWidget, QSizePolicy, QMenu, QAction
from PyQt5.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QFont

# Etkileşim modları
IDLE, DRAWING, MOVING, RESIZING = range(4)
HANDLE_HIT = 11   # köşe tutamaç isabet alanı (piksel)
HANDLE_DRAW = 7   # tutamaç çizim yarıçapı


class Canvas(QWidget):
    bbox_added = pyqtSignal(int, int, int, int)
    bbox_deleted = pyqtSignal(int)
    bbox_class_changed = pyqtSignal(int, int)
    bbox_modified = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)

        self.pixmap: QPixmap = None
        self.annotations = []
        self.label_classes = []
        self.current_class_id = 0

        self._mode = IDLE
        self._start = QPoint()          # DRAWING başlangıç noktası
        self._cur_rect = QRect()        # DRAWING rubber-band
        self._scale = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._selected = -1
        self._hover = -1

        # Sürükleme durumu
        self._drag_start = QPoint()
        self._drag_orig = None          # (x1, y1, x2, y2) orijinal
        self._drag_handle = -1          # -1=taşı, 0-3=köşe

    # ------------------------------------------------------------------ public

    def set_image(self, pixmap: QPixmap):
        self.pixmap = pixmap
        self._selected = -1
        self._hover = -1
        self._mode = IDLE
        self._update_transform()
        self.update()

    def set_annotations(self, bboxes, label_classes):
        self.annotations = bboxes
        self.label_classes = label_classes
        self.update()

    def set_current_class(self, cid: int):
        self.current_class_id = cid

    # ------------------------------------------------------------------ koordinat dönüşümleri

    def _update_transform(self):
        if not self.pixmap:
            return
        sx = self.width() / self.pixmap.width()
        sy = self.height() / self.pixmap.height()
        self._scale = min(sx, sy) * 0.98
        self._ox = (self.width() - self.pixmap.width() * self._scale) / 2
        self._oy = (self.height() - self.pixmap.height() * self._scale) / 2

    def _to_img(self, p: QPoint) -> QPoint:
        return QPoint(int((p.x() - self._ox) / self._scale),
                      int((p.y() - self._oy) / self._scale))

    def _to_canvas(self, x, y) -> QPoint:
        return QPoint(int(x * self._scale + self._ox),
                      int(y * self._scale + self._oy))

    def _bbox_rect(self, b) -> QRect:
        return QRect(self._to_canvas(b.x1, b.y1),
                     self._to_canvas(b.x2, b.y2)).normalized()

    # ------------------------------------------------------------------ yardımcılar

    def _class_color(self, cid: int) -> QColor:
        fallback = [
            QColor(255, 80, 80), QColor(80, 200, 80), QColor(80, 120, 255),
            QColor(255, 165, 0), QColor(180, 80, 255), QColor(0, 200, 200),
        ]
        if self.label_classes and 0 <= cid < len(self.label_classes):
            return self.label_classes[cid].color
        return fallback[cid % len(fallback)]

    def _class_name(self, cid: int) -> str:
        if self.label_classes and 0 <= cid < len(self.label_classes):
            return self.label_classes[cid].name
        return f"cls{cid}"

    def _bbox_at(self, pos: QPoint) -> int:
        for i, b in enumerate(self.annotations):
            if self._bbox_rect(b).contains(pos):
                return i
        return -1

    def _handle_at(self, pos: QPoint) -> int:
        """Seçili bbox'ın köşe tutamaçlarından birine yakın mı? 0-3 döner, yoksa -1."""
        if self._selected < 0 or self._selected >= len(self.annotations):
            return -1
        b = self.annotations[self._selected]
        rect = self._bbox_rect(b)
        corners = [rect.topLeft(), rect.topRight(),
                   rect.bottomLeft(), rect.bottomRight()]
        for i, c in enumerate(corners):
            if (pos - c).manhattanLength() <= HANDLE_HIT:
                return i
        return -1

    def _apply_drag(self, cur_pos: QPoint):
        if self._selected < 0 or self._drag_orig is None:
            return
        dx = int((cur_pos.x() - self._drag_start.x()) / self._scale)
        dy = int((cur_pos.y() - self._drag_start.y()) / self._scale)
        ox1, oy1, ox2, oy2 = self._drag_orig
        b = self.annotations[self._selected]
        pw = self.pixmap.width()
        ph = self.pixmap.height()

        if self._drag_handle == -1:          # taşıma
            bw, bh = ox2 - ox1, oy2 - oy1
            b.x1 = max(0, min(ox1 + dx, pw - bw))
            b.y1 = max(0, min(oy1 + dy, ph - bh))
            b.x2 = b.x1 + bw
            b.y2 = b.y1 + bh
        else:                                # yeniden boyutlandırma
            x1, y1, x2, y2 = ox1, oy1, ox2, oy2
            if self._drag_handle == 0:       # sol-üst
                x1 = max(0, ox1 + dx)
                y1 = max(0, oy1 + dy)
            elif self._drag_handle == 1:     # sağ-üst
                x2 = min(pw, ox2 + dx)
                y1 = max(0, oy1 + dy)
            elif self._drag_handle == 2:     # sol-alt
                x1 = max(0, ox1 + dx)
                y2 = min(ph, oy2 + dy)
            elif self._drag_handle == 3:     # sağ-alt
                x2 = min(pw, ox2 + dx)
                y2 = min(ph, oy2 + dy)
            if abs(x2 - x1) > 5 and abs(y2 - y1) > 5:
                b.x1, b.y1, b.x2, b.y2 = x1, y1, x2, y2

        self.update()

    def _update_cursor(self, pos: QPoint):
        handle = self._handle_at(pos)
        if handle in (0, 3):
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in (1, 2):
            self.setCursor(Qt.SizeBDiagCursor)
        elif (self._selected >= 0
              and self._selected < len(self.annotations)
              and self._bbox_rect(self.annotations[self._selected]).contains(pos)):
            self.setCursor(Qt.SizeAllCursor)
        elif self._bbox_at(pos) >= 0:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------ çizim

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(35, 35, 35))

        if not self.pixmap:
            p.setPen(QColor(120, 120, 120))
            p.setFont(QFont("Arial", 14))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Klasör aç ve resim seç\n(Dosya > Klasör Aç)")
            return

        sw = int(self.pixmap.width() * self._scale)
        sh = int(self.pixmap.height() * self._scale)
        p.drawPixmap(int(self._ox), int(self._oy), sw, sh, self.pixmap)

        p.setFont(QFont("Arial", 9, QFont.Bold))

        for i, b in enumerate(self.annotations):
            color = self._class_color(b.class_id)
            rect = self._bbox_rect(b)
            is_sel = (i == self._selected)
            is_hov = (i == self._hover)

            fill = QColor(color)
            fill.setAlpha(60 if is_sel else 25)
            p.fillRect(rect, fill)

            pen = QPen(color, 3 if is_sel else 2)
            if is_hov and not is_sel:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawRect(rect)

            # Seçili bbox üzerinde köşe tutamaçları
            if is_sel:
                p.setBrush(QColor(255, 255, 255))
                p.setPen(QPen(QColor(50, 50, 50), 1))
                for cx, cy in [
                    (rect.left(), rect.top()), (rect.right(), rect.top()),
                    (rect.left(), rect.bottom()), (rect.right(), rect.bottom()),
                ]:
                    p.drawRect(cx - HANDLE_DRAW, cy - HANDLE_DRAW,
                               HANDLE_DRAW * 2, HANDLE_DRAW * 2)
                p.setBrush(Qt.NoBrush)

            name = self._class_name(b.class_id)
            lw = max(70, len(name) * 9 + 10)
            lr = QRect(rect.x(), rect.y() - 22, lw, 22)
            p.fillRect(lr, color)
            p.setPen(QColor(255, 255, 255))
            p.drawText(lr, Qt.AlignCenter, name)

        # Çizilen rubber-band
        if self._mode == DRAWING and not self._cur_rect.isNull():
            p.setPen(QPen(QColor(255, 220, 0), 2, Qt.DashLine))
            p.fillRect(self._cur_rect, QColor(255, 220, 0, 30))
            p.drawRect(self._cur_rect)

    # ------------------------------------------------------------------ fare olayları

    def mousePressEvent(self, event):
        if not self.pixmap:
            return

        if event.button() == Qt.LeftButton:
            handle = self._handle_at(event.pos())
            if handle >= 0:
                # Köşe tutamaç → boyutlandırma
                self._mode = RESIZING
                self._drag_start = event.pos()
                self._drag_handle = handle
                b = self.annotations[self._selected]
                self._drag_orig = (b.x1, b.y1, b.x2, b.y2)
            elif (self._selected >= 0
                  and self._selected < len(self.annotations)
                  and self._bbox_rect(self.annotations[self._selected]).contains(event.pos())):
                # Seçili bbox içi → taşıma
                self._mode = MOVING
                self._drag_start = event.pos()
                self._drag_handle = -1
                b = self.annotations[self._selected]
                self._drag_orig = (b.x1, b.y1, b.x2, b.y2)
            else:
                hit = self._bbox_at(event.pos())
                if hit >= 0:
                    # Başka bbox'a tıklandı → seç ve taşıma başlat
                    self._selected = hit
                    self._mode = MOVING
                    self._drag_start = event.pos()
                    self._drag_handle = -1
                    b = self.annotations[hit]
                    self._drag_orig = (b.x1, b.y1, b.x2, b.y2)
                    self.update()
                else:
                    # Boş alan → yeni bbox çiz
                    self._mode = DRAWING
                    self._start = event.pos()
                    self._cur_rect = QRect()
                    self._selected = -1
                    self.update()

        elif event.button() == Qt.RightButton:
            hit = self._bbox_at(event.pos())
            if hit >= 0:
                self._selected = hit
                self.update()
                self._show_context_menu(event.globalPos(), hit)

    def mouseMoveEvent(self, event):
        if self._mode == DRAWING:
            self._cur_rect = QRect(self._start, event.pos()).normalized()
            self.update()
        elif self._mode in (MOVING, RESIZING):
            self._apply_drag(event.pos())
        else:
            old = self._hover
            self._hover = self._bbox_at(event.pos())
            self._update_cursor(event.pos())
            if old != self._hover:
                self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._mode == DRAWING:
                r = self._cur_rect
                if r.width() > 5 and r.height() > 5 and self.pixmap:
                    p1 = self._to_img(r.topLeft())
                    p2 = self._to_img(r.bottomRight())
                    pw, ph = self.pixmap.width(), self.pixmap.height()
                    self.bbox_added.emit(
                        max(0, min(p1.x(), pw)), max(0, min(p1.y(), ph)),
                        max(0, min(p2.x(), pw)), max(0, min(p2.y(), ph)),
                    )
                self._cur_rect = QRect()
            elif self._mode in (MOVING, RESIZING):
                self.bbox_modified.emit()

            self._mode = IDLE
            self._drag_orig = None
            self._update_cursor(event.pos())
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self._selected >= 0:
            idx = self._selected
            self._selected = -1
            self.bbox_deleted.emit(idx)

    def resizeEvent(self, event):
        self._update_transform()
        self.update()

    # ------------------------------------------------------------------ bağlam menüsü

    def _show_context_menu(self, global_pos: QPoint, bbox_idx: int):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#2b2b2b; color:#d4d4d4; border:1px solid #555; }
            QMenu::item:selected { background:#0d7acc; }
            QMenu::separator { height:1px; background:#444; margin:3px 0; }
        """)

        class_menu = QMenu("Sınıf Değiştir", self)
        class_menu.setStyleSheet(menu.styleSheet())
        cur_cid = self.annotations[bbox_idx].class_id
        for i, lc in enumerate(self.label_classes):
            act = QAction(lc.name, self)
            act.setCheckable(True)
            act.setChecked(i == cur_cid)
            act.triggered.connect(lambda checked, idx=i: self.bbox_class_changed.emit(bbox_idx, idx))
            class_menu.addAction(act)
        menu.addMenu(class_menu)
        menu.addSeparator()

        del_act = QAction("Sil", self)
        del_act.triggered.connect(lambda: self._delete_bbox(bbox_idx))
        menu.addAction(del_act)

        menu.exec_(global_pos)

    def _delete_bbox(self, idx: int):
        self._selected = -1
        self.bbox_deleted.emit(idx)
