"""Kutunun üstünde açılan sınıf editörü.

Neden var: sınıf atamak için sağ panele gitmek, kutu çizme ritmini her seferinde
kesiyordu. Daha kötüsü, hiç sınıf tanımlanmamışken çizilen kutu sessizce
düşüyor ve yerine "önce sağ panelden bir sınıf ekleyin" uyarısı çıkıyordu —
yani araç, kullanıcıyı yapmak istediği işten alıkoyup form doldurmaya
gönderiyordu. Burada sınıf, kutunun yanında yazılarak atanıyor; olmayan bir ad
yazılırsa sınıf o anda yaratılıyor.

Odak kuralı: panel normalde odağı çalmaz (arka arkaya kutu çizmek yavaşlamasın).
Yalnızca sınıf atanması zorunlu olduğunda — hiç sınıf yokken — imleç alana
kendiliğinden gider.
"""

from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QComboBox)
from PyQt5.QtCore import Qt, QEvent, pyqtSignal


class SinifPopup(QFrame):
    uygulandi = pyqtSignal(str)   # sınıf adı (yeni de olabilir)
    silindi = pyqtSignal()
    kapatildi = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SinifPopup")
        self.setFixedWidth(210)
        self.setStyleSheet(
            "QFrame#SinifPopup { background:#f5f7f9; border:1px solid #2e6da4;"
            " border-radius:10px; }"
        )

        kok = QVBoxLayout(self)
        kok.setContentsMargins(10, 8, 10, 10)
        kok.setSpacing(6)

        ust = QHBoxLayout()
        baslik = QLabel("Sınıf")
        baslik.setStyleSheet("font-weight:bold; font-size:12px;")
        kapat = QPushButton("✕")
        kapat.setFixedSize(20, 20)
        kapat.setStyleSheet("padding:0; font-size:11px;")
        kapat.clicked.connect(self.kapatildi.emit)
        ust.addWidget(baslik)
        ust.addStretch()
        ust.addWidget(kapat)
        kok.addLayout(ust)

        self.alan = QComboBox()
        self.alan.setEditable(True)
        self.alan.setInsertPolicy(QComboBox.NoInsert)
        self.alan.lineEdit().setPlaceholderText("sınıf seç ya da yaz")
        self.alan.lineEdit().returnPressed.connect(self._uygula)
        tamamlayici = self.alan.completer()
        if tamamlayici is not None:
            tamamlayici.setCaseSensitivity(Qt.CaseInsensitive)
        # Alanın herhangi bir yerine tıklayınca liste açılsın; küçük oku
        # nişan almak zorunda kalmak, hızlı etiketlemede sürtünme yaratıyor.
        self.alan.lineEdit().installEventFilter(self)
        kok.addWidget(self.alan)

        satir = QHBoxLayout()
        satir.setSpacing(6)
        self.sil_btn = QPushButton("Sil")
        self.sil_btn.clicked.connect(self.silindi.emit)
        self.uygula_btn = QPushButton("Uygula")
        self.uygula_btn.setDefault(True)
        self.uygula_btn.clicked.connect(self._uygula)
        satir.addWidget(self.sil_btn)
        satir.addWidget(self.uygula_btn)
        kok.addLayout(satir)

        self.hide()

    # ------------------------------------------------------------------ public

    def siniflari_ver(self, adlar):
        mevcut = self.alan.currentText()
        self.alan.blockSignals(True)
        self.alan.clear()
        self.alan.addItems(adlar)
        self.alan.setEditText(mevcut)
        self.alan.blockSignals(False)

    def goster(self, adlar, secili_ad: str, odak: bool):
        self.siniflari_ver(adlar)
        self.alan.setEditText(secili_ad)
        self.show()
        self.raise_()
        if odak:
            self.alan.setFocus()
            self.alan.lineEdit().selectAll()

    def onayla(self):
        """Dışarıdan Enter ile onaylama (pencere kısayolu)."""
        if self.isVisible():
            self._uygula()

    # ------------------------------------------------------------------ iç

    def _uygula(self):
        ad = self.alan.currentText().strip()
        if ad:
            self.uygulandi.emit(ad)

    def eventFilter(self, nesne, olay):
        if (nesne is self.alan.lineEdit()
                and olay.type() == QEvent.MouseButtonPress
                and not self.alan.view().isVisible()):
            self.alan.showPopup()
            return True
        return super().eventFilter(nesne, olay)

    def keyPressEvent(self, olay):
        if olay.key() == Qt.Key_Escape:
            self.kapatildi.emit()
            return
        super().keyPressEvent(olay)

    # Panelin boş alanına yapılan tıklama arkadaki tuvale geçmemeli;
    # yoksa panele tıklarken yanlışlıkla yeni kutu çizilmeye başlanıyor.
    def mousePressEvent(self, olay):
        olay.accept()

    def mouseReleaseEvent(self, olay):
        olay.accept()
