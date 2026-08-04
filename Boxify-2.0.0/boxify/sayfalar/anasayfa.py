"""Ana sayfa — Boxify zincirini kartlar halinde gösterir, tıklayınca aracı açar."""

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
    """Tıklanabilir araç kartı: adım rozeti + ad + özet + açıklama."""

    tiklandi = pyqtSignal(str)

    def __init__(self, arac: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("Kart")
        self._anahtar = arac["anahtar"]
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        kok = QVBoxLayout(self)
        kok.setContentsMargins(14, 12, 14, 12)
        kok.setSpacing(6)

        ust = QHBoxLayout()
        ust.setSpacing(10)
        rozet = QLabel(str(arac["adim"]))
        rozet.setObjectName("KartRozet")
        rozet.setFixedSize(26, 26)
        rozet.setAlignment(Qt.AlignCenter)
        ust.addWidget(rozet)

        baslik = QLabel(f'{arac["amblem"]}  {arac["ad"]}')
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
    """Karşılama + araç zinciri panosu."""

    arac_istendi = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        govde = QWidget()
        kok = QVBoxLayout(govde)
        kok.setContentsMargins(34, 28, 34, 28)
        kok.setSpacing(16)

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
            f"YOLO veri hazırlama ve model yaşam döngüsü atölyesi — sürüm {SURUM}\n"
            "Videodan hatta giden zincirin yedi halkası tek çatı altında."
        )
        alt.setObjectName("AnaAltBaslik")
        alt.setWordWrap(True)
        yazi.addWidget(baslik)
        yazi.addWidget(alt)
        serit.addLayout(yazi)
        serit.addStretch()
        kok.addLayout(serit)

        # ── Zincir özeti ─────────────────────────────────────────────────
        zincir = QLabel(
            "1 kırp  →  2 kare al  →  3 oto etiketle  →  4 elle düzelt  →  "
            "5 denetle ve böl  →  (eğitim)  →  6 hatayı çöz  →  7 hatta çıkar"
        )
        zincir.setObjectName("ZincirSatir")
        zincir.setWordWrap(True)
        kok.addWidget(zincir)

        # ── Araç kartları ────────────────────────────────────────────────
        izgara = QGridLayout()
        izgara.setSpacing(14)
        for i, arac in enumerate(ARACLAR):
            kart = AracKarti(arac)
            kart.tiklandi.connect(self.arac_istendi)
            izgara.addWidget(kart, i // 2, i % 2)
        izgara.setColumnStretch(0, 1)
        izgara.setColumnStretch(1, 1)
        kok.addLayout(izgara)

        ipucu = QLabel(
            "İpucu: araçlar soldaki çubuktan da açılır; her araç ilk tıklamada "
            "yüklenir, sekmeler arasında geçiş yaparken işler arka planda sürer."
        )
        ipucu.setObjectName("KartAciklama")
        ipucu.setWordWrap(True)
        kok.addWidget(ipucu)
        kok.addStretch()

        self.setWidget(govde)
