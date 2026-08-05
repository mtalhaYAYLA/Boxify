"""Boxify kabugu testi: gercek olay dongusu, tum araclari yukle, gecis yap."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import traceback

from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=True)


from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer

mesajlar = []
QMessageBox.critical = staticmethod(lambda p, t, x="", *a, **k: (mesajlar.append((t, x)), QMessageBox.Ok)[1])

from boxify import dil
dil.dil_yukle(); dil.yamalari_kur()
from boxify.tema import STYLE
from boxify.ana_pencere import AnaPencere
from boxify.araclar import ARACLAR

ATLA = set(os.environ.get("ATLA", "").split(",")) - {""}
ANAHTARLAR = [a["anahtar"] for a in ARACLAR if a["anahtar"] not in ATLA]

app = QApplication([]); app.setStyleSheet(STYLE)
win = AnaPencere(); win.show()
BASLANGIC_MIN = (win.minimumWidth(), win.minimumHeight())

hatalar = []
adimlar = []
for k in ANAHTARLAR:                       # once hepsini yukle
    adimlar.append(("yukle", k))
for tur in range(3):                       # sonra ileri geri gez
    for k in ["anasayfa"] + ANAHTARLAR + ["ipuclari"]:
        adimlar.append(("gec", k))

durum = {"i": 0, "t0": 0.0, "bekliyor": None}

def sonraki():
    if durum["i"] >= len(adimlar):
        bitir(); return
    tip, k = adimlar[durum["i"]]
    durum["i"] += 1
    durum["t0"] = time.time()
    try:
        win.arac_ac(k)
    except Exception:
        hatalar.append(f"{k}: {traceback.format_exc(limit=3)}")
        QTimer.singleShot(0, sonraki); return
    if tip == "yukle":
        durum["bekliyor"] = k
        kontrol()
    else:
        dt = (time.time() - durum["t0"]) * 1000
        if dt > 120:
            hatalar.append(f"GECIS YAVAS {k}: {dt:.0f} ms")
        QTimer.singleShot(0, sonraki)

def kontrol():
    k = durum["bekliyor"]
    if k in win._sayfa_no:
        dt = (time.time() - durum["t0"]) * 1000
        print(f"  yuklendi {k:<20s} {dt:7.0f} ms   pencere-min="
              f"{win.minimumWidth()}x{win.minimumHeight()}", flush=True)
        durum["bekliyor"] = None
        QTimer.singleShot(0, sonraki)
    elif time.time() - durum["t0"] > 25:
        hatalar.append(f"{k}: yukleme zaman asimi")
        durum["bekliyor"] = None
        QTimer.singleShot(0, sonraki)
    else:
        QTimer.singleShot(20, kontrol)

def bitir():
    print(f"\npencere minimumu: baslangic {BASLANGIC_MIN} -> son "
          f"({win.minimumWidth()}, {win.minimumHeight()})", flush=True)
    if win.minimumWidth() > BASLANGIC_MIN[0] + 50:
        hatalar.append(f"pencere minimumu buyudu: {win.minimumWidth()} "
                       f"(gomulu sayfalarin minimumSize'i sizmis)")
    yuklenmeyen = [k for k in ANAHTARLAR if k not in win._sayfa_no]
    if yuklenmeyen: hatalar.append(f"yuklenmeyen: {yuklenmeyen}")
    for t, x in mesajlar:
        hatalar.append(f"HATA KUTUSU: {t} :: {x.splitlines()[-1] if x else ''}")
    print("\nHATALAR:", hatalar or "YOK — kabuk testi gecti", flush=True)
    win.close()
    app.exit(1 if hatalar else 0)

QTimer.singleShot(50, sonraki)
sys.exit(app.exec_())
