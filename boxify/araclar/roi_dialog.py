"""ROI çizim penceresi — örnek kare üzerinde poligon çiz.

Etkileşim bilerek az kurallı tutuldu: sol tık nokta koyar, çift tık ya da
Enter bölgeyi kapatır, sağ tık son noktayı geri alır. Sürükleyerek düzenleme
yok — ROI bir kez çizilip bırakılan bir şey; düzenleme kipi eklemek, yılda
birkaç kez kullanılacak bir iş için öğrenilecek yeni kurallar demek.
"""

import os

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QWidget, QSizePolicy, QMessageBox)
from PyQt5.QtCore import Qt, QPoint, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap, QPolygon, QFont

from . import roi as roi_modulu
from ..tema import renk


class RoiTuvali(QWidget):
    """Kare + üstünde çizilen poligonlar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 340)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.pixmap = None
        self.poligonlar = []        # tamamlanmış, normalize (0-1)
        self._acik = []             # çizilmekte olan, normalize
        self._imlec = None

    # ---------------------------------------------------------------- geometri

    def _hedef(self) -> QRect:
        """Görüntünün tuval içindeki dikdörtgeni (en-boy korunur)."""
        if not self.pixmap:
            return QRect()
        olcek = min(self.width() / self.pixmap.width(),
                    self.height() / self.pixmap.height())
        g = int(self.pixmap.width() * olcek)
        y = int(self.pixmap.height() * olcek)
        return QRect((self.width() - g) // 2, (self.height() - y) // 2, g, y)

    def _normalize(self, p: QPoint):
        h = self._hedef()
        if h.isEmpty():
            return None
        x = (p.x() - h.x()) / h.width()
        y = (p.y() - h.y()) / h.height()
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            return None
        return (x, y)

    def _ekrana(self, nokta):
        h = self._hedef()
        return QPoint(int(h.x() + nokta[0] * h.width()),
                      int(h.y() + nokta[1] * h.height()))

    # ---------------------------------------------------------------- public

    def kare_ver(self, pixmap: QPixmap):
        self.pixmap = pixmap if (pixmap and not pixmap.isNull()) else None
        self.update()

    def poligon_ver(self, poligonlar):
        self.poligonlar = [list(p) for p in poligonlar]
        self._acik = []
        self.update()

    def bolgeyi_kapat(self):
        if len(self._acik) >= 3:
            self.poligonlar.append(self._acik)
        self._acik = []
        self.update()

    def son_noktayi_geri_al(self):
        if self._acik:
            self._acik.pop()
        elif self.poligonlar:
            self._acik = self.poligonlar.pop()
        self.update()

    def hepsini_temizle(self):
        self.poligonlar = []
        self._acik = []
        self.update()

    # ---------------------------------------------------------------- olaylar

    def mousePressEvent(self, olay):
        if not self.pixmap:
            return
        if olay.button() == Qt.RightButton:
            self.son_noktayi_geri_al()
            return
        nokta = self._normalize(olay.pos())
        if nokta:
            self._acik.append(nokta)
            self.update()

    def mouseDoubleClickEvent(self, _olay):
        self.bolgeyi_kapat()

    def mouseMoveEvent(self, olay):
        self._imlec = olay.pos()
        if self._acik:
            self.update()

    def keyPressEvent(self, olay):
        if olay.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.bolgeyi_kapat()
        elif olay.key() == Qt.Key_Escape:
            self._acik = []
            self.update()
        else:
            super().keyPressEvent(olay)

    # ---------------------------------------------------------------- çizim

    def paintEvent(self, _olay):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(renk("#dde1e7")))

        if not self.pixmap:
            p.setPen(QColor(renk("#6b7686")))
            p.setFont(QFont("Arial", 13))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Örnek kare yok — önce bir görsel klasörü seç")
            return

        h = self._hedef()
        p.drawPixmap(h, self.pixmap)

        # ROI dışını karart: neyin dışarıda kaldığı bakınca anlaşılsın
        if self.poligonlar:
            p.save()
            p.setClipRect(h)
            karart = QColor(0, 0, 0, 110)
            bolge = None
            from PyQt5.QtGui import QRegion
            for poligon in self.poligonlar:
                r = QRegion(QPolygon([self._ekrana(n) for n in poligon]))
                bolge = r if bolge is None else bolge.united(r)
            disari = QRegion(h).subtracted(bolge)
            p.setClipRegion(disari)
            p.fillRect(h, karart)
            p.restore()

        for i, poligon in enumerate(self.poligonlar):
            self._poligon_ciz(p, poligon, QColor("#2e6da4"), kapali=True,
                              etiket=f"bölge {i + 1}")
        if self._acik:
            self._poligon_ciz(p, self._acik, QColor("#d9a62e"), kapali=False)

    def _poligon_ciz(self, p, poligon, cizgi_rengi, kapali: bool, etiket=""):
        noktalar = [self._ekrana(n) for n in poligon]
        dolgu = QColor(cizgi_rengi)
        dolgu.setAlpha(45)
        if kapali and len(noktalar) >= 3:
            p.setBrush(dolgu)
            p.setPen(QPen(cizgi_rengi, 2))
            p.drawPolygon(QPolygon(noktalar))
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(cizgi_rengi, 2, Qt.DashLine))
            for a, b in zip(noktalar, noktalar[1:]):
                p.drawLine(a, b)
            if noktalar and self._imlec is not None:
                p.drawLine(noktalar[-1], self._imlec)

        p.setBrush(QColor(255, 255, 255))
        p.setPen(QPen(QColor(40, 40, 40), 1))
        for n in noktalar:
            p.drawEllipse(n, 4, 4)

        if etiket and noktalar:
            p.setPen(QColor(renk("#2b3442")))
            p.setFont(QFont("Arial", 9, QFont.Bold))
            p.drawText(noktalar[0] + QPoint(8, -8), etiket)


class RoiDialog(QDialog):
    """Örnek kare üzerinde ROI çiz, veri setinin yanına kaydet."""

    def __init__(self, klasor: str, ornek_kare: QPixmap, parent=None):
        super().__init__(parent)
        self.setWindowTitle("İlgi Alanı (ROI)")
        self.resize(940, 640)
        self._klasor = klasor

        kok = QVBoxLayout(self)
        kok.setSpacing(8)

        yardim = QLabel(
            "Sol tık nokta koyar · çift tık ya da Enter bölgeyi kapatır · "
            "sağ tık son noktayı geri alır · Esc çizimi bırakır\n"
            "Karartılan alan ROI dışıdır: oradaki tespitler kullanılmaz.")
        yardim.setStyleSheet("color:#6b7686; font-size:11px;")
        yardim.setWordWrap(True)
        kok.addWidget(yardim)

        self.tuval = RoiTuvali()
        self.tuval.kare_ver(ornek_kare)
        self.tuval.poligon_ver(roi_modulu.yukle(klasor))
        self.tuval.setFocus()
        kok.addWidget(self.tuval, 1)

        self.ozet_lbl = QLabel()
        self.ozet_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        kok.addWidget(self.ozet_lbl)

        satir = QHBoxLayout()
        satir.setSpacing(6)

        def dugme(metin, slot, tip=""):
            b = QPushButton(metin)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(slot)
            satir.addWidget(b)
            return b

        dugme("Bölgeyi Kapat", self._kapat_bolge, "Enter ile aynı")
        dugme("Geri Al", self._geri_al, "Son noktayı ya da son bölgeyi geri alır")
        dugme("Hepsini Temizle", self._temizle)
        satir.addStretch()
        dugme("Vazgeç", self.reject)
        kaydet_btn = dugme("Kaydet", self._kaydet)
        kaydet_btn.setDefault(True)
        kaydet_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; padding:6px 16px;")
        kok.addLayout(satir)

        self._ozeti_tazele()

    # ---------------------------------------------------------------- iç

    def _ozeti_tazele(self):
        self.ozet_lbl.setText(roi_modulu.ozet(self.tuval.poligonlar)
                              + f"   ·   {roi_modulu.roi_dosyasi(self._klasor)}")

    def _kapat_bolge(self):
        self.tuval.bolgeyi_kapat()
        self._ozeti_tazele()

    def _geri_al(self):
        self.tuval.son_noktayi_geri_al()
        self._ozeti_tazele()

    def _temizle(self):
        self.tuval.hepsini_temizle()
        self._ozeti_tazele()

    def _kaydet(self):
        self.tuval.bolgeyi_kapat()       # yarım kalan bölge de sayılsın
        yol = roi_modulu.kaydet(self._klasor, self.tuval.poligonlar)
        if not yol:
            QMessageBox.warning(self, "Kaydedilemedi",
                                "ROI dosyası yazılamadı — klasör yazılabilir mi?")
            return
        self.accept()

    def poligonlar(self):
        return self.tuval.poligonlar
