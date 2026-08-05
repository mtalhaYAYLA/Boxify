"""Yigin gecisinde gomulu aracin hideEvent'i tetikleniyor mu?"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=False)

from PyQt5.QtWidgets import (QApplication, QMainWindow, QStackedWidget,
                             QScrollArea, QLabel, QWidget, QVBoxLayout)
app = QApplication([])

olaylar = []
class SahteArac(QMainWindow):
    def __init__(self, ad):
        super().__init__(); self.ad = ad
        c = QWidget(); QVBoxLayout(c).addWidget(QLabel(ad)); self.setCentralWidget(c)
    def hideEvent(self, ev):
        olaylar.append(("gizlendi", self.ad)); super().hideEvent(ev)
    def showEvent(self, ev):
        olaylar.append(("gosterildi", self.ad)); super().showEvent(ev)

yigin = QStackedWidget()
kutular = []
for ad in ("A", "B"):
    t = SahteArac(ad)
    sa = QScrollArea(); sa.setWidgetResizable(True); sa.setWidget(t)
    yigin.addWidget(sa); kutular.append(t)
pencere = QMainWindow(); pencere.setCentralWidget(yigin); pencere.show()
app.processEvents()
olaylar.clear()
yigin.setCurrentIndex(1); app.processEvents()
print("A -> B gecisinde olaylar:", olaylar)
yigin.setCurrentIndex(0); app.processEvents()
print("B -> A gecisinde olaylar:", olaylar)
gizlendi = [o for o in olaylar if o[0] == "gizlendi"]
print("\nSONUC:", "hideEvent kaydirma kutusundan gecerek ARACA ULASIYOR"
      if gizlendi else "!! hideEvent ULASMIYOR — duraklatma calismaz")
sys.exit(0 if gizlendi else 1)
