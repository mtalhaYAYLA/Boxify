"""oto_label ve hata_analizi'nde sinif okuma ARKA PLANDA mi?
Sahte ultralytics'e yapay gecikme koyup arayuzun bloke olup olmadigini olcuyoruz."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import tempfile

from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=True)

# Test verisi geçici klasörde üretilir; depoya bir şey yazılmaz.
SP = tempfile.mkdtemp(prefix='boxify_test_')


import ultralytics
_asil = ultralytics.YOLO.__init__
def yavas(self, path):          # torch importunu taklit eden 2 sn'lik gecikme
    time.sleep(2.0); _asil(self, path)
ultralytics.YOLO.__init__ = yavas

from PyQt5.QtWidgets import QApplication
app = QApplication([])
MODEL = os.path.join(SP, "model_uc.pt")
open(MODEL, "wb").close()
hatalar = []

def olc(ad, win, tetikle, bitti, oku):
    t0 = time.time(); tetikle(); cagri_ms = (time.time() - t0) * 1000
    # arayuz bloke olmadan olay islenebiliyor mu?
    donguler = 0; t1 = time.time()
    while time.time() - t1 < 6:
        app.processEvents(); donguler += 1
        if bitti(): break
        time.sleep(0.01)
    print(f"  {ad}: cagri {cagri_ms:6.1f} ms (bloke olsaydi ~2000)  "
          f"olay dongusu {donguler} kez dondu  ->  {oku()}")
    if cagri_ms > 500: hatalar.append(f"{ad}: cagri arayuzu {cagri_ms:.0f} ms bloke etti")
    if donguler < 10: hatalar.append(f"{ad}: olay dongusu donmedi (arayuz kilitli)")

print("oto_label:")
from boxify.araclar.oto_label import MainWindow as OL
ol = OL(); ol._model_path = MODEL
olc("_load_class_names", ol, lambda: ol._load_class_names(MODEL),
    lambda: ol._sinif_yukleyici is None, lambda: ol.model_info_lbl.text())
if ol.class_list.count() != 3: hatalar.append("oto_label: sinif listesi dolmadi")
ol.close()

print("hata_analizi:")
from boxify.araclar.hata_analizi import MainWindow as HA
ha = HA(); ha._model_path = MODEL
olc("_load_class_names", ha, lambda: ha._load_class_names(MODEL),
    lambda: ha._sinif_yukleyici is None, lambda: ha.model_info.text())
if len(ha._names) != 3: hatalar.append("hata_analizi: _names dolmadi")
ha.close()

print("model_karsilastir:")
from boxify.araclar.model_karsilastir import MainWindow as MK
mk = MK(); mk._slot_rows[0]["path"] = MODEL
olc("_load_class_names", mk, lambda: mk._load_class_names(0, MODEL),
    lambda: not mk._sinif_yukleyiciler, lambda: mk._slot_rows[0]["sinif_durum"].text())
if mk._slot_rows[0]["class_list"].count() != 3: hatalar.append("model_karsilastir: sinif listesi dolmadi")
mk.close()

print("\nHATALAR:", hatalar or "YOK — sinif okuma her uc aracta da arka planda")
sys.exit(1 if hatalar else 0)
