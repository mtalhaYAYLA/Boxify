import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=True)

SP=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,os.path.join(SP,"fake")); sys.path.insert(0,KOK)
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PyQt5.QtWidgets import QApplication, QPushButton
from boxify.tema import STYLE
app=QApplication([]); app.setStyleSheet(STYLE)
from boxify.araclar.model_karsilastir import MainWindow
w=MainWindow(); w.resize(1262,895); w.show(); app.processEvents()
kotu=[]
for b in w.findChildren(QPushButton):
    if not b.isVisibleTo(w): continue
    r=b.visibleRegion().boundingRect()
    durum = "gorunur" if r.height()>0 else "!! KIVRIM ALTINDA"
    if r.height()==0: kotu.append(b.text())
    print(f"  {b.text()[:34]:<34s} {r.width():>4}x{r.height():<3} {durum}")
print("\nErisilemeyen dugme:", kotu or "YOK — hepsi ilk bakista tiklanabilir")
