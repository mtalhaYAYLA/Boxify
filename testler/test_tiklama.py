"""Araç içindeki düğmeler gerçekten tıklanabiliyor mu? (gerçek ekran gerekir)

Araçlar kendi modüllerinde üst düzey birer QMainWindow olarak doğuyor ve
macOS'ta buna yerel bir pencere atanıyor. `setWindowFlags(Qt.Widget)` gömme
işleminden ÖNCE çağrılırsa o pencere ayakta kalıyor ve konumunu eski
koordinatlarından bildiriyor: araç doğru yerde çiziliyor ama fare isabeti
yüzlerce piksel ötede aranıyor, yani hiçbir düğmeye basılamıyor.

Bu ancak GERÇEK bir ekranda görülür — offscreen platformda `widgetAt()`
anlamlı sonuç vermez. Ekransız ortamda (CI, ssh) test kendini atlar.

    python testler/test_tiklama.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, KOK   # noqa: E402

# Bu test offscreen çalışamaz: isabet testi gerçek pencere yöneticisi ister.
os.environ.pop("QT_QPA_PLATFORM", None)
yolu_kur(sahte_ultralytics=False)
os.environ.pop("QT_QPA_PLATFORM", None)

from PyQt5.QtWidgets import QApplication, QPushButton
from PyQt5.QtCore import QTimer, QPoint
from boxify import dil; dil.dil_yukle(); dil.yamalari_kur()
from boxify.tema import STYLE
from boxify.ana_pencere import AnaPencere
from boxify.araclar import ARACLAR
app = QApplication(sys.argv)
if not app.screens() or app.platformName() in ("offscreen", "minimal"):
    print("ATLANDI — gerçek ekran yok (offscreen/başsız ortam)")
    sys.exit(0)
app.setStyleSheet(STYLE)
win = AnaPencere(); win.show()
sira = [a["anahtar"] for a in ARACLAR]
sonuc = []

def ac(i):
    if i >= len(sira):
        QTimer.singleShot(300, bitir); return
    win.arac_ac(sira[i])
    QTimer.singleShot(2200, lambda: olc(i))

def olc(i):
    k = sira[i]; arac = win._arac_sayfalari.get(k)
    if arac is None:
        sonuc.append((k, "YUKLENMEDI", 0, 0)); QTimer.singleShot(100, lambda: ac(i+1)); return
    ref = win.yigin.mapToGlobal(QPoint(0, 0))
    ag = arac.mapToGlobal(QPoint(0, 0))
    sapma = abs(ag.x()-ref.x()) + abs(ag.y()-ref.y())
    toplam = kotu = 0
    for b in arac.findChildren(QPushButton):
        if not b.isVisible() or b.visibleRegion().isEmpty(): continue
        toplam += 1
        if QApplication.widgetAt(b.mapToGlobal(b.rect().center())) is not b: kotu += 1
    sonuc.append((k, "ok", sapma, f"{toplam-kotu}/{toplam}"))
    QTimer.singleShot(150, lambda: ac(i+1))

def bitir():
    print(f"{'arac':<20s} {'sapma':>6s}  {'tiklanabilir dugme':>18s}")
    hepsi_ok = True
    for k, d, s, o in sonuc:
        if d != "ok": print(f"{k:<20s} {d}"); hepsi_ok = False; continue
        ok = isinstance(o, str) and o.split('/')[0] == o.split('/')[1]
        if not ok or s > 4: hepsi_ok = False
        print(f"{k:<20s} {s:>6d}  {o:>18s}  {'' if ok and s<=4 else '  <-- SORUN'}")
    print("\nSONUC:", "GECTI — tüm araçlarda tıklama doğru"
          if hepsi_ok else "BASARISIZ — isabet sapması var")
    app.exit(0 if hepsi_ok else 1)

QTimer.singleShot(1200, lambda: ac(0))
QTimer.singleShot(70000, app.quit)
sys.exit(app.exec_())
