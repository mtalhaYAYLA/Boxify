"""EN modunda TUM araclarin gorunen metinlerini tarayip cevrilmemis olanlari bul."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=True)

import re
from boxify import dil
dil._dil = "en"; dil.yamalari_kur()
from PyQt5.QtWidgets import (QApplication, QLabel, QAbstractButton, QGroupBox,
                             QLineEdit, QComboBox)
app = QApplication([])
TR = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
import importlib
from boxify.araclar import ARACLAR
eksik = {}
for arac in ARACLAR:
    if arac["anahtar"] == "labelapp":      # ayri paket, kapsam disi
        continue
    m = importlib.import_module(arac["modul"])
    w = m.MainWindow()
    bulunan = []
    for c in w.findChildren(object):
        for getter in ("text", "title", "placeholderText"):
            f = getattr(c, getter, None)
            if not callable(f) or isinstance(c, QLineEdit) and getter == "text":
                continue
            try: t = f()
            except Exception: continue
            if isinstance(t, str) and t and TR.search(t):
                bulunan.append(f"{type(c).__name__}.{getter}: {t[:70]}")
        if isinstance(c, QComboBox):
            for i in range(c.count()):
                if TR.search(c.itemText(i)): bulunan.append(f"QComboBox[{i}]: {c.itemText(i)}")
    if TR.search(w.windowTitle()): bulunan.append("windowTitle: " + w.windowTitle())
    if bulunan: eksik[arac["anahtar"]] = sorted(set(bulunan))
    w.close()

for k, v in eksik.items():
    print(f"\n{k}  ({len(v)} cevrilmemis):")
    for s in v: print("   ", s)
if not eksik: print("Tum araclarda gorunen metinler cevrili.")
print("\nMODEL KARSILASTIR eksik sayisi:", len(eksik.get("model_karsilastir", [])))
