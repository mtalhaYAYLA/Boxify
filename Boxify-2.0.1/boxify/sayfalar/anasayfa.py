"""Ana sayfa — araçları kartlar halinde gösterir, tıklayınca aracı açar."""

import os

from PyQt5.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QScrollArea, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from .. import SURUM
from ..araclar import ARACLAR

IKON_YOLU = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ikon.png",
)


class AracKarti(QFrame):
    """Tıklanabilir araç kartı: amblem rozeti + ad + özet + açıklama."""

    tiklandi = pyqtSignal(str)

    def __init__(self, arac: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("Kart")
        self._anahtar = arac["anahtar"]
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(16, 14, 16, 14)
        kok.setSpacing(6)

        ust = QHBoxLayout()
        ust.setSpacing(10)
        rozet = QLabel(arac["amblem"])
        rozet.setObjectName("KartRozet")
        rozet.setFixedSize(32, 32)
        rozet.setAlignment(Qt.AlignCenter)
        ust.addWidget(rozet)

        baslik = QLabel(arac["ad"])
        baslik.setObjectName("KartBaslik")
        ust.addWidget(baslik)
        ust.addStretch()
        kok.addLayout(ust)

        ozet = QLabel(arac["ozet"])
        ozet.setObjectName("KartOzet")
        ozet.setWordWrap(True)
        kok.addWidget(ozet)

        aciklama = QLabel(arac["aciklama"])
        aciklama.setObjectName("KartAciklama")
        aciklama.setWordWrap(True)
        kok.addWidget(aciklama)
        kok.addStretch()

    def mouseReleaseEvent(self, olay):
        if olay.button() == Qt.LeftButton and self.rect().contains(olay.pos()):
            self.tiklandi.emit(self._anahtar)
        super().mouseReleaseEvent(olay)


class AnaSayfa(QScrollArea):
    """Karşılama + araç panosu."""

    arac_istendi = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        govde = QWidget()
        kok = QVBoxLayout(govde)
        kok.setContentsMargins(36, 30, 36, 30)
        kok.setSpacing(18)

        # ── Başlık şeridi ────────────────────────────────────────────────
        serit = QHBoxLayout()
        serit.setSpacing(18)
        if os.path.exists(IKON_YOLU):
            logo = QLabel()
            logo.setPixmap(QPixmap(IKON_YOLU).scaledToHeight(
                72, Qt.SmoothTransformation))
            serit.addWidget(logo)

        yazi = QVBoxLayout()
        yazi.setSpacing(4)
        baslik = QLabel("Boxify")
        baslik.setObjectName("AnaBaslik")
        alt = QLabel(
            f"Nesne tespiti için veri seti ve model atölyesi — sürüm {SURUM}\n"
            "Hangi nesneyle çalışırsan çalış — balon, araç, ürün, kusur — "
            "videodan hazır modele giden her adım tek çatı altında."
        )
        alt.setObjectName("AnaAltBaslik")
        alt.setWordWrap(True)
        yazi.addWidget(baslik)
        yazi.addWidget(alt)
        serit.addLayout(yazi)
        serit.addStretch()
        kok.addLayout(serit)

        # ── Araç kartları ────────────────────────────────────────────────
        izgara = QGridLayout()
        izgara.setSpacing(16)
        for i, arac in enumerate(ARACLAR):
            kart = AracKarti(arac)
            kart.tiklandi.connect(self.arac_istendi)
            izgara.addWidget(kart, i // 2, i % 2)
        izgara.setColumnStretch(0, 1)
        izgara.setColumnStretch(1, 1)
        kok.addLayout(izgara)

        ipucu = QLabel(
            "Nereden başlayacağını bilmiyorsan soldaki İpuçları sayfasına göz at: "
            "genel akış ve her aracın püf noktaları orada anlatılıyor."
        )
        ipucu.setObjectName("KartAciklama")
        ipucu.setWordWrap(True)
        kok.addWidget(ipucu)
        kok.addStretch()

        self.setWidget(govde)
