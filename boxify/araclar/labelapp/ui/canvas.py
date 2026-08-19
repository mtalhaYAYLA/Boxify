from PyQt5.QtWidgets import QWidget, QSizePolicy, QMenu, QAction
from PyQt5.QtCore import Qt, QRect, QPoint, QEvent, pyqtSignal
from PyQt5.QtGui import QPainter, QPixmap, QColor, QPen, QFont

from ....tema import renk

# Etkileşim modları
IDLE, DRAWING, MOVING, RESIZING, PANNING = range(5)
HANDLE_HIT = 11   # köşe tutamaç isabet alanı (piksel)
HANDLE_DRAW = 7   # tutamaç çizim yarıçapı

ZOOM_MIN = 1.0    # sığdırılmış hâlden daha da küçültmenin faydası yok
ZOOM_MAX = 16.0
TIKLAMA_ESIGI = 4  # sağ tıkta bu kadar pikselden az hareket "tıklama" sayılır


class Canvas(QWidget):
    bbox_added = pyqtSignal(int, int, int, int)
    bbox_deleted = pyqtSignal(int)
    bbox_class_changed = pyqtSignal(int, int)
    bbox_modified = pyqtSignal()
    bbox_degisecek = pyqtSignal()      # taşıma/boyutlandırma başlıyor (geri al için)
    zoom_degisti = pyqtSignal(float)
    secim_degisti = pyqtSignal(int)    # seçili kutu indeksi, yoksa -1

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
        self._drag_bildirildi = False   # bu sürüklemede geri al anlığı alındı mı

        # Yakınlaştırma / kaydırma
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._pan_start = QPoint()
        self._pan_orig = (0.0, 0.0)
        self._imlec = None              # kılavuz çizgileri için son imleç konumu

    # ------------------------------------------------------------------ public

    def set_image(self, pixmap: QPixmap):
        # Boş bir QPixmap None gibi davranmaz (nesne olarak "doğru"dur), ama
        # genişliği 0'dır — ölçek hesabı sıfıra bölerdi. Burada None'a
        # indirgeniyor; aşağıdaki bütün `if not self.pixmap` kontrolleri ve
        # "klasör aç" yazısı böylece doğru çalışıyor.
        self.pixmap = None if (pixmap is None or pixmap.isNull()) else pixmap
        self.sec(-1)
        self._hover = -1
        self._mode = IDLE
        # Yeni görüntüde sığdırılmış hâle dön: bir önceki karenin yakınlaştırması
        # burada nesnenin bulunduğu yeri göstermeyebilir, kullanıcıyı şaşırtır.
        self._zoom = 1.0
        self._pan_x = self._pan_y = 0.0
        self._update_transform()
        self.zoom_degisti.emit(self._zoom)
        self.update()

    def set_annotations(self, bboxes, label_classes):
        self.annotations = bboxes
        self.label_classes = label_classes
        self.update()

    def set_current_class(self, cid: int):
        self.current_class_id = cid


    def sec(self, idx: int):
        """Seçimi değiştir ve bildir (kutu üstündeki sınıf paneli buna bakıyor)."""
        if idx != self._selected:
            self._selected = idx
            self.secim_degisti.emit(idx)
        self.update()

    def secili_rect(self):
        """Seçili kutunun tuval koordinatındaki dikdörtgeni; yoksa None."""
        if 0 <= self._selected < len(self.annotations):
            return self._bbox_rect(self.annotations[self._selected])
        return None

    # ------------------------------------------------------------------ koordinat dönüşümleri

    def _fit_scale(self) -> float:
        """Yakınlaştırma olmadan görüntüyü tuvale sığdıran ölçek."""
        sx = self.width() / self.pixmap.width()
        sy = self.height() / self.pixmap.height()
        return min(sx, sy) * 0.98

    def _update_transform(self):
        """`_scale` / `_ox` / `_oy`'yi zoom ve pan'i içerecek şekilde tazeler.

        Kaydırma, görüntü tuvale sığıyorken kilitlenir ve büyütülmüşken
        kenarlarda boşluk kalmayacak biçimde sınırlanır — böylece görüntüyü
        ekran dışına sürükleyip kaybetmek mümkün değil.
        """
        if not self.pixmap:
            return
        self._scale = self._fit_scale() * self._zoom
        sw = self.pixmap.width() * self._scale
        sh = self.pixmap.height() * self._scale
        temel_ox = (self.width() - sw) / 2
        temel_oy = (self.height() - sh) / 2

        if sw <= self.width():
            self._pan_x = 0.0
            self._ox = temel_ox
        else:
            ox = min(0.0, max(self.width() - sw, temel_ox + self._pan_x))
            self._pan_x = ox - temel_ox
            self._ox = ox

        if sh <= self.height():
            self._pan_y = 0.0
            self._oy = temel_oy
        else:
            oy = min(0.0, max(self.height() - sh, temel_oy + self._pan_y))
            self._pan_y = oy - temel_oy
            self._oy = oy

    # ------------------------------------------------------------------ yakınlaştırma

    def _apply_zoom(self, yeni: float, cx: float, cy: float):
        """(cx, cy) tuval noktasını sabit tutarak yakınlaştırmayı değiştirir.

        İmlecin altındaki pikselin yerinde kalması, tekerlekle yakınlaşırken
        aradığın nesnenin ekrandan kaçmamasını sağlar.
        """
        if not self.pixmap:
            return
        yeni = max(ZOOM_MIN, min(ZOOM_MAX, yeni))
        if abs(yeni - self._zoom) < 1e-6:
            return

        ix = (cx - self._ox) / self._scale      # imlecin altındaki görüntü koordinatı
        iy = (cy - self._oy) / self._scale
        self._zoom = yeni

        yeni_olcek = self._fit_scale() * yeni
        temel_ox = (self.width() - self.pixmap.width() * yeni_olcek) / 2
        temel_oy = (self.height() - self.pixmap.height() * yeni_olcek) / 2
        self._pan_x = cx - ix * yeni_olcek - temel_ox
        self._pan_y = cy - iy * yeni_olcek - temel_oy

        self._update_transform()
        self.zoom_degisti.emit(self._zoom)
        self.update()

    def zoom_step(self, carpan: float):
        self._apply_zoom(self._zoom * carpan, self.width() / 2, self.height() / 2)

    def reset_zoom(self):
        if not self.pixmap:
            return
        self._zoom = 1.0
        self._pan_x = self._pan_y = 0.0
        self._update_transform()
        self.zoom_degisti.emit(self._zoom)
        self.update()

    def wheelEvent(self, event):
        if not self.pixmap:
            return super().wheelEvent(event)
        # Sürükleme sürerken ölçeği değiştirmek, başlangıç noktası tuval
        # koordinatında saklandığı için kutuyu kaydırırdı.
        if self._mode in (DRAWING, MOVING, RESIZING):
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self._apply_zoom(self._zoom * (1.0015 ** delta),
                         event.pos().x(), event.pos().y())
        event.accept()

    def event(self, e):
        # Touchpad'de iki parmakla sıkıştırma (macOS/Windows destekliyorsa)
        if e.type() == QEvent.NativeGesture and self.pixmap:
            try:
                if e.gestureType() == Qt.ZoomNativeGesture:
                    self._apply_zoom(self._zoom * (1.0 + e.value()),
                                     e.pos().x(), e.pos().y())
                    return True
            except Exception:
                pass
        return super().event(e)

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
        """İmlecin altındaki kutulardan **en küçük alanlısını** döndürür.

        İlk eşleşeni döndürmek, büyük bir kutunun içindeki küçük kutuyu
        seçilemez yapıyordu (araç içindeki plaka, insan üstündeki baret gibi
        iç içe etiketlerde sürekli büyük olan yakalanıyordu).
        """
        en_iyi, en_kucuk = -1, None
        for i, b in enumerate(self.annotations):
            r = self._bbox_rect(b)
            if r.contains(pos):
                alan = r.width() * r.height()
                if en_kucuk is None or alan < en_kucuk:
                    en_iyi, en_kucuk = i, alan
        return en_iyi

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
        if dx == 0 and dy == 0:
            return
        # Geri al anlık görüntüsü, kutu gerçekten kımıldadığında alınıyor:
        # basma anında almak, seçmek için yapılan her tıklamayı yığına
        # boş bir adım olarak eklerdi.
        if not self._drag_bildirildi:
            self._drag_bildirildi = True
            self.bbox_degisecek.emit()
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
        # Kendi boyamasını yapan widget'lar tema yamasının dışında kalıyor;
        # rengi `renk()`ten istemek koyu temada da doğru zemini verir.
        p.fillRect(self.rect(), QColor(renk("#dde1e7")))

        if not self.pixmap:
            p.setPen(QColor(renk("#6b7686")))
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

        # Kılavuz çizgileri — imleci takip eden hizalama çizgileri. Kutunun
        # kenarını nesneye oturtmak, kenarın uzak ucunun nereye denk geldiğini
        # görmeden tahmine dayanıyordu.
        if self._mode in (IDLE, DRAWING) and self._imlec is not None:
            gorsel = QRect(int(self._ox), int(self._oy), sw, sh)
            cx, cy = self._imlec.x(), self._imlec.y()
            if gorsel.contains(cx, cy):
                # Önce koyu, üstüne kesikli açık: her iki zeminde de okunur.
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(0, 0, 0, 90), 1))
                p.drawLine(cx, gorsel.top(), cx, gorsel.bottom())
                p.drawLine(gorsel.left(), cy, gorsel.right(), cy)
                p.setPen(QPen(QColor(255, 255, 255, 220), 1, Qt.DashLine))
                p.drawLine(cx, gorsel.top(), cx, gorsel.bottom())
                p.drawLine(gorsel.left(), cy, gorsel.right(), cy)

    # ------------------------------------------------------------------ fare olayları

    def mousePressEvent(self, event):
        if not self.pixmap:
            return

        if event.button() == Qt.LeftButton:
            self._drag_bildirildi = False
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
                    self.sec(hit)
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
                    self.sec(-1)

        elif event.button() in (Qt.RightButton, Qt.MiddleButton):
            # Sağ tuş iki iş yapıyor: sürüklenirse kaydırma, yerinde bırakılırsa
            # bağlam menüsü. Hangisi olduğuna bırakma anında karar veriliyor.
            self._mode = PANNING
            self._pan_start = event.pos()
            self._pan_orig = (self._pan_x, self._pan_y)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        self._imlec = event.pos()
        if self._mode == PANNING:
            fark = event.pos() - self._pan_start
            self._pan_x = self._pan_orig[0] + fark.x()
            self._pan_y = self._pan_orig[1] + fark.y()
            self._update_transform()
            self.update()
        elif self._mode == DRAWING:
            self._cur_rect = QRect(self._start, event.pos()).normalized()
            self.update()
        elif self._mode in (MOVING, RESIZING):
            self._apply_drag(event.pos())
        else:
            old = self._hover
            self._hover = self._bbox_at(event.pos())
            self._update_cursor(event.pos())
            # Kılavuz çizgileri imleci takip etmeli; hover değişmese de tazele.
            self.update()

    def leaveEvent(self, event):
        self._imlec = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if (event.button() in (Qt.RightButton, Qt.MiddleButton)
                and self._mode == PANNING):
            self._mode = IDLE
            yer_degistirme = (event.pos() - self._pan_start).manhattanLength()
            self._update_cursor(event.pos())
            if (event.button() == Qt.RightButton
                    and yer_degistirme <= TIKLAMA_ESIGI):
                hit = self._bbox_at(event.pos())
                if hit >= 0:
                    self.sec(hit)
                    self._show_context_menu(event.globalPos(), hit)
            return

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
            elif self._mode in (MOVING, RESIZING) and self._drag_bildirildi:
                self.bbox_modified.emit()

            self._mode = IDLE
            self._drag_orig = None
            self._update_cursor(event.pos())
            self.update()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self._selected >= 0:
            idx = self._selected
            self.sec(-1)
            self.bbox_deleted.emit(idx)

    def resizeEvent(self, event):
        self._update_transform()
        self.update()

    # ------------------------------------------------------------------ bağlam menüsü

    def _show_context_menu(self, global_pos: QPoint, bbox_idx: int):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#f5f7f9; color:#2b3442; border:1px solid #c9d1da; border-radius:6px; }
            QMenu::item:selected { background:#2e6da4; color:#f5f8fb; }
            QMenu::separator { height:1px; background:#c9d1da; margin:3px 0; }
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
        self.sec(-1)
        self.bbox_deleted.emit(idx)
