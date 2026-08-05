"""Uc isletim sisteminin de dogru davrandigini dogrula (platformu taklit ederek)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib

from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=False)

from PyQt5.QtWidgets import QApplication
app = QApplication([])
hata = []

print("=== 1. Cihaz secenekleri ===")
import boxify.araclar.model_bilgi as mb
for plat, bekle in (("darwin", "mps"), ("linux", 0), ("win32", 0)):
    sys.platform = plat
    importlib.reload(mb)
    sec = mb.cihaz_secenekleri()
    gpu = [d for e, d in sec if e != "Otomatik" and e != "CPU"]
    print(f"  {plat:<8s} -> {[e for e,_ in sec]}")
    if gpu[0] != bekle: hata.append(f"cihaz {plat}: {gpu[0]} != {bekle}")

print("\n=== 2. ffmpeg kurulum ipucu ===")
import boxify.araclar.ffmpeg_yardim as fy
for plat, anahtar in (("darwin", "brew"), ("linux", "apt"), ("win32", "winget")):
    sys.platform = plat
    importlib.reload(fy)
    ip = fy.kurulum_ipucu()
    print(f"  {plat:<8s} -> {ip}")
    if anahtar not in ip: hata.append(f"ffmpeg {plat}: '{anahtar}' yok")

print("\n=== 3. GStreamer duzeltmesi platformla sinirli mi ===")
import boxify.gstreamer_yardim as gy
for plat in ("darwin", "win32"):
    sys.platform = plat
    importlib.reload(gy)
    once = dict(os.environ)
    gy.hazirla()          # hicbir sey yapmamali, exec de etmemeli
    if os.environ.get("GST_PLUGIN_FEATURE_RANK") != once.get("GST_PLUGIN_FEATURE_RANK"):
        hata.append(f"gstreamer {plat}: ortam degiskeni degistirildi")
    print(f"  {plat:<8s} -> dokunmadi (dogru)")
sys.platform = "linux"
importlib.reload(gy)
os.environ.pop("GST_PLUGIN_FEATURE_RANK", None)
gy.vaapi_sink_kapat()
print(f"  linux    -> GST_PLUGIN_FEATURE_RANK={os.environ.get('GST_PLUGIN_FEATURE_RANK')}")
if os.environ.get("GST_PLUGIN_FEATURE_RANK") != "vaapisink:0":
    hata.append("gstreamer linux: vaapi kapatilmadi")

print("\n=== 4. Kutuphane dizini taramasi (ARM Linux dahil) ===")
print(f"  bulunan dizinler: {gy._kutuphane_dizinleri()[:4] or '(bu makinede yok — macOS)'}")
print("  eski kod sabit '/usr/lib/x86_64-linux-gnu' kullaniyordu -> ARM'de hic calismazdi")

print("\n=== 5. Egitimde yukleyici sureci varsayilani ===")
import boxify.araclar.egitim as eg
for plat, bekle in (("darwin", 0), ("win32", 0), ("linux", 8)):
    sys.platform = plat
    importlib.reload(eg)
    w = eg.MainWindow()
    v = w.workers_spin.value()
    print(f"  {plat:<8s} -> {v}")
    if v != bekle: hata.append(f"workers {plat}: {v} != {bekle}")
    w.close()

print("\n=== 6. Klasor acma ===")
import inspect, boxify.klasor_ac as ka
kaynak = inspect.getsource(ka.klasoru_ac)
for anahtar in ("startfile", "open", "xdg-open"):
    if anahtar not in kaynak: hata.append(f"klasor_ac: {anahtar} yok")
print("  startfile / open / xdg-open -> ucu de var")

print("\n" + "="*58)
print("SONUC:", "GECTI — uc sistem de dogru" if not hata else f"!! {hata}")
