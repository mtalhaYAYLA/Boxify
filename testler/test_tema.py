"""Dort kombinasyonun hepsi: {TR,EN} x {acik,koyu} — 9 arac aciliyor mu, metin okunuyor mu."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import re
import json

from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=False)

from PyQt5.QtWidgets import QApplication, QLabel, QAbstractButton, QGroupBox, QLineEdit
app = QApplication([])
from boxify import dil, tema
from boxify.araclar import ARACLAR
import importlib

TRCH = re.compile(r"[çğıöşüÇĞİÖŞÜ]")
sorun = []

def parlaklik(h):
    h = h.lstrip("#"); r,g,b = int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return (0.299*r+0.587*g+0.114*b)/255

for tema_kod in ("acik", "koyu"):
    for dil_kod in ("tr", "en"):
        dil._dil = dil_kod
        dil._yamalar_kuruldu = False
        dil.yamalari_kur()
        tema._tema = tema_kod
        # yama bir kez kurulur; koyu icin zaten kurulu olmali
        tema.yamalari_kur()
        app.setStyleSheet(tema.stil())
        acilan, ceviri_eksik, okunaksiz = 0, 0, 0
        for a in ARACLAR:
            if a["anahtar"] == "labelapp":
                continue
            try:
                m = importlib.import_module(a["modul"])
                w = m.MainWindow()
                acilan += 1
            except Exception as e:
                sorun.append(f"{tema_kod}/{dil_kod}/{a['anahtar']}: {type(e).__name__}: {e}")
                continue
            for c in w.findChildren(QLabel) + w.findChildren(QAbstractButton) + w.findChildren(QGroupBox):
                # EN modunda Turkce kalan metin
                if dil_kod == "en":
                    for g in ("text", "title"):
                        f = getattr(c, g, None)
                        if callable(f):
                            try: t = f()
                            except Exception: continue
                            if isinstance(t, str) and TRCH.search(t): ceviri_eksik += 1
                # koyu temada koyu metin
                if tema_kod == "koyu":
                    mm = re.search(r"color:\s*(#[0-9a-fA-F]{6})", c.styleSheet())
                    if mm and parlaklik(mm.group(1)) < 0.35: okunaksiz += 1
            w.close()
        etiket = f"{tema_kod:<5s}/{dil_kod}"
        print(f"  {etiket}  acilan={acilan}/8  ceviri_eksik={ceviri_eksik}  okunaksiz={okunaksiz}")
        if acilan != 8: sorun.append(f"{etiket}: {acilan}/8 acildi")
        if ceviri_eksik: sorun.append(f"{etiket}: {ceviri_eksik} cevrilmemis")
        if okunaksiz: sorun.append(f"{etiket}: {okunaksiz} okunaksiz")

print("\n=== ayar dosyasi ikisini birden tutuyor mu ===")
import tempfile, shutil
yedek = None
if os.path.exists(tema.AYAR_DOSYA):
    yedek = tema.AYAR_DOSYA + ".yedek"; shutil.copy2(tema.AYAR_DOSYA, yedek)
dil.dil_kaydet("en"); tema.tema_kaydet("koyu")
icerik = json.load(open(tema.AYAR_DOSYA, encoding="utf-8"))
print("  ", icerik)
if icerik.get("dil") != "en" or icerik.get("tema") != "koyu":
    sorun.append(f"ayar dosyasi: {icerik}")
dil.dil_kaydet("tr"); tema.tema_kaydet("acik")
icerik2 = json.load(open(tema.AYAR_DOSYA, encoding="utf-8"))
print("   geri alindi:", icerik2)
if yedek: shutil.move(yedek, tema.AYAR_DOSYA)

print("\n" + "="*60)
print("SONUC:", "GECTI — dort kombinasyon da temiz" if not sorun else f"!! {sorun[:5]}")
