"""Boxify kabuğu: kenar çubuğu + sayfa yığını.

Araç pencereleri (her biri kendi modülünde bir QMainWindow) ilk açılışta
import edilip yığına gömülür; sonraki geçişler anındadır ve araçların
QThread işçileri sekme değişince çalışmaya devam eder.
"""

import importlib
import traceback

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QFrame, QMessageBox, QApplication, QButtonGroup,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from . import SURUM
from .araclar import ARACLAR, arac_bul
from .sayfalar.anasayfa import AnaSayfa, IKON_YOLU


class AnaPencere(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Boxify {SURUM} — YOLO Veri ve Model Atölyesi")
        self.resize(1500, 920)

        self._sayfa_no = {}      # anahtar -> stack indeksi
        self._nav_dugmeler = {}  # anahtar -> QPushButton

        kok = QWidget()
        yatay = QHBoxLayout(kok)
        yatay.setContentsMargins(0, 0, 0, 0)
        yatay.setSpacing(0)

        yatay.addWidget(self._kenar_cubugu_kur())

        self.yigin = QStackedWidget()
        self.anasayfa = AnaSayfa()
        self.anasayfa.arac_istendi.connect(self.arac_ac)
        self.yigin.addWidget(self.anasayfa)          # indeks 0
        yatay.addWidget(self.yigin, 1)

        self.setCentralWidget(kok)
        self.statusBar().showMessage(
            "Hoş geldin — soldaki çubuktan ya da kartlardan bir araç seç.")

    # ── Kenar çubuğu ─────────────────────────────────────────────────────
    def _kenar_cubugu_kur(self) -> QWidget:
        cubuk = QFrame()
        cubuk.setObjectName("KenarCubuk")
        cubuk.setFixedWidth(232)

        dikey = QVBoxLayout(cubuk)
        dikey.setContentsMargins(0, 14, 0, 8)
        dikey.setSpacing(2)

        # Logo + ad
        logo_kutu = QHBoxLayout()
        logo_kutu.setContentsMargins(14, 0, 14, 6)
        logo_kutu.setSpacing(10)
        logo = QLabel()
        pix = QPixmap(IKON_YOLU)
        if not pix.isNull():
            logo.setPixmap(pix.scaledToHeight(40, Qt.SmoothTransformation))
        logo_kutu.addWidget(logo)
        ad_kutu = QVBoxLayout()
        ad_kutu.setSpacing(0)
        ad = QLabel("Boxify")
        ad.setObjectName("LogoAd")
        surum = QLabel(f"sürüm {SURUM}")
        surum.setObjectName("Surum")
        ad_kutu.addWidget(ad)
        ad_kutu.addWidget(surum)
        logo_kutu.addLayout(ad_kutu)
        logo_kutu.addStretch()
        dikey.addLayout(logo_kutu)

        dikey.addWidget(self._ayrac())

        self._grup = QButtonGroup(self)
        self._grup.setExclusive(True)

        dikey.addWidget(self._nav_dugme("anasayfa", "⌂  Ana Sayfa", secili=True))

        baslik = QLabel("ARAÇ ZİNCİRİ")
        baslik.setObjectName("KenarBaslik")
        dikey.addWidget(baslik)

        for arac in ARACLAR:
            metin = f'{arac["adim"]}   {arac["amblem"]}  {arac["ad"]}'
            dugme = self._nav_dugme(arac["anahtar"], metin,
                                    ipucu=arac["ozet"])
            dikey.addWidget(dugme)

        dikey.addStretch()
        dikey.addWidget(self._ayrac())
        dip = QLabel("veri → eğitim → analiz → hat\nBoxify1 araçlarının birleşimi")
        dip.setObjectName("KenarDip")
        dip.setWordWrap(True)
        dikey.addWidget(dip)
        return cubuk

    def _ayrac(self) -> QFrame:
        cizgi = QFrame()
        cizgi.setFrameShape(QFrame.HLine)
        cizgi.setStyleSheet("background:#3a3a3a; max-height:1px; border:none;")
        return cizgi

    def _nav_dugme(self, anahtar: str, metin: str,
                   secili: bool = False, ipucu: str = "") -> QPushButton:
        dugme = QPushButton(metin)
        dugme.setObjectName("NavDugme")
        dugme.setCheckable(True)
        dugme.setChecked(secili)
        dugme.setCursor(Qt.PointingHandCursor)
        if ipucu:
            dugme.setToolTip(ipucu)
        dugme.clicked.connect(lambda: self.arac_ac(anahtar))
        self._grup.addButton(dugme)
        self._nav_dugmeler[anahtar] = dugme
        return dugme

    # ── Sayfa yönetimi ───────────────────────────────────────────────────
    def arac_ac(self, anahtar: str):
        """Aracı göster; ilk istekte modülünü yükleyip yığına ekle."""
        if anahtar == "anasayfa":
            self.yigin.setCurrentIndex(0)
            self._nav_dugmeler["anasayfa"].setChecked(True)
            self.statusBar().showMessage("Ana sayfa")
            return

        arac = arac_bul(anahtar)
        if anahtar not in self._sayfa_no:
            if not self._arac_yukle(arac):
                # Yükleme başarısız: ana sayfada kal
                self._nav_dugmeler["anasayfa"].setChecked(True)
                self.yigin.setCurrentIndex(0)
                return

        self.yigin.setCurrentIndex(self._sayfa_no[anahtar])
        self._nav_dugmeler[anahtar].setChecked(True)
        self.statusBar().showMessage(
            f'{arac["adim"]}. {arac["ad"]} — {arac["ozet"]}')

    def _arac_yukle(self, arac: dict) -> bool:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage(f'{arac["ad"]} yükleniyor…')
        QApplication.processEvents()
        try:
            modul = importlib.import_module(arac["modul"])
            pencere = modul.MainWindow()
            pencere.setWindowFlags(Qt.Widget)   # gömülü kullanım
        except Exception:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(
                self, f'{arac["ad"]} açılamadı',
                "Araç yüklenirken hata oluştu (eksik bağımlılık olabilir):\n\n"
                + traceback.format_exc(limit=6))
            return False
        QApplication.restoreOverrideCursor()

        indeks = self.yigin.addWidget(pencere)
        self._sayfa_no[arac["anahtar"]] = indeks
        return True

    # ── Kapanış ──────────────────────────────────────────────────────────
    def closeEvent(self, olay):
        """Açık araçların kendi kapanış onayları varsa onlara sor."""
        for indeks in self._sayfa_no.values():
            sayfa = self.yigin.widget(indeks)
            if sayfa is not None and not sayfa.close():
                olay.ignore()
                return
        olay.accept()
