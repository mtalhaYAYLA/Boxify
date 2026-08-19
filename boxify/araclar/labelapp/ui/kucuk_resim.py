"""Resim listesi için küçük resim (thumbnail) üretici.

Neden arka planda: 500 karelik bir klasörde küçük resimleri liste kurulurken
üretmek arayüzü saniyelerce donduruyor. İşçi kareleri sırayla okur ve teker
teker yollar; liste dolarken uygulama kullanılabilir kalır.

Neden QImage yollanıyor: QPixmap yalnızca ana iş parçacığında güvenli. İşçi
QImage üretir, ana taraf onu QPixmap'e çevirir.
"""

import os

from PyQt5.QtCore import QThread, pyqtSignal, Qt, QSize
from PyQt5.QtGui import QImage

KUCUK = QSize(104, 78)


class KucukResimIscisi(QThread):
    hazir = pyqtSignal(int, QImage)    # (indeks, küçük resim)

    def __init__(self, yollar, parent=None):
        super().__init__(parent)
        self._yollar = list(yollar)
        self._dur = False

    def durdur(self):
        self._dur = True

    def run(self):
        for i, yol in enumerate(self._yollar):
            if self._dur:
                return
            try:
                if not os.path.exists(yol):
                    continue
                img = QImage(yol)
                if img.isNull():
                    continue
                kucuk = img.scaled(KUCUK, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
            except Exception:
                continue
            if self._dur:
                return
            self.hazir.emit(i, kucuk)
