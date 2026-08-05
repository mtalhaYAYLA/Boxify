"""Yol hafizasi: diyalog son kullanilan yerden aciliyor mu, alanlar birbirine karisiyor mu?"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shutil
import json
import tempfile

from ortak import yolu_kur, gecici_ayar, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=False)

from PyQt5.QtWidgets import QApplication, QFileDialog
app = QApplication([])
from boxify import proje

# Kullanicinin gercek ayar dosyasina dokunulmuyor: yollar gecici klasore cevrilir
AYAR, ayar_geri_al = gecici_ayar()
proje._yollar = {}; proje._kaydet()

# cagrilari yakala: hangi baslangic dizini ile acildi?
acilan = []
_ozgun_dir = QFileDialog.getExistingDirectory
_ozgun_dosya = QFileDialog.getOpenFileName
sonuc_dir = {"deger": ""}
sonuc_dosya = {"deger": ""}
QFileDialog.getExistingDirectory = staticmethod(
    lambda parent=None, caption="", directory="", *a, **k:
        (acilan.append((caption, directory)), sonuc_dir["deger"])[1])
QFileDialog.getOpenFileName = staticmethod(
    lambda parent=None, caption="", directory="", *a, **k:
        (acilan.append((caption, directory)), (sonuc_dosya["deger"], ""))[1])

proje._yamalar_kuruldu = False
proje.yamalari_kur()

A = tempfile.mkdtemp(prefix="boxify_A_")
B = tempfile.mkdtemp(prefix="boxify_B_")
M = os.path.join(B, "model.pt"); open(M, "w").close()
hata = []

print("=== 1. ilk acilis: hafiza bos, baslangic bos olmali ===")
sonuc_dir["deger"] = A
QFileDialog.getExistingDirectory(None, "Fotoğrafların olduğu klasör", "")
print(f"   baslangic: {acilan[-1][1]!r}")
if acilan[-1][1]: hata.append("ilk aciliste bos olmaliydi")

print("\n=== 2. ikinci acilis: az onceki klasorden baslamali ===")
acilan.clear(); sonuc_dir["deger"] = A
QFileDialog.getExistingDirectory(None, "Fotoğrafların olduğu klasör", "")
print(f"   baslangic: {acilan[-1][1]}")
if acilan[-1][1] != A: hata.append(f"hatirlanmadi: {acilan[-1][1]} != {A}")

print("\n=== 3. FARKLI bir alan bundan etkilenmemeli ===")
acilan.clear(); sonuc_dir["deger"] = B
QFileDialog.getExistingDirectory(None, "Bölme çıktı klasörü", "")
print(f"   'Bölme çıktı klasörü' baslangici: {acilan[-1][1]!r}  (bos olmali)")
if acilan[-1][1]: hata.append("alanlar birbirine karisti")

print("\n=== 4. cagiran bir baslangic verirse ona dokunulmamali ===")
acilan.clear(); sonuc_dir["deger"] = A
QFileDialog.getExistingDirectory(None, "Fotoğrafların olduğu klasör", B)
print(f"   verilen: {B}\n   kullanilan: {acilan[-1][1]}")
if acilan[-1][1] != B: hata.append("cagiranin secimi ezildi")

print("\n=== 5. dosya diyalogu: dosyanin KLASORU hatirlanmali ===")
acilan.clear(); sonuc_dosya["deger"] = M
QFileDialog.getOpenFileName(None, "Model seç", "")
acilan.clear()
QFileDialog.getOpenFileName(None, "Model seç", "")
print(f"   secilen dosya: {M}\n   sonraki baslangic: {acilan[-1][1]}")
if acilan[-1][1] != B: hata.append(f"dosya klasoru hatirlanmadi: {acilan[-1][1]}")

print("\n=== 6. silinen klasor elenmeli ===")
shutil.rmtree(A)
proje.yukle()
kalan = [k for k, v in proje._yollar.items() if v == A]
print(f"   silinen klasore isaret eden anahtar: {kalan or '(yok — dogru)'}")
if kalan: hata.append("silinen klasor elenmedi")

print("\n=== 7. ayar dosyasi dil/temayi ezmiyor mu ===")
from boxify import dil, tema
dil.dil_kaydet("en"); tema.tema_kaydet("koyu")
proje.hatirla("getExistingDirectory:Test", B)
icerik = json.load(open(AYAR, encoding="utf-8"))
print(f"   {sorted(icerik.keys())}")
if not {"dil", "tema", "yollar"} <= set(icerik): hata.append(f"ayar eksik: {icerik.keys()}")

shutil.rmtree(B, ignore_errors=True)
ayar_geri_al()
print("\n" + "="*56)
print("SONUC:", "GECTI — yol hafizasi dogru" if not hata else f"!! {hata}")
