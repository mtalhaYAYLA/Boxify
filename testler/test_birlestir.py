"""Birlestirme testi: sinif id'leri CAKISAN iki veri seti dogru esleniyor mu?

Set A: 0=kamyon, 1=tir
Set B: 0=tir,    1=dorse      <-- ayni id, farkli anlam
Duz kopyalama B'nin 'tir'ini A'nin 'kamyon'u yapardi. Dogru sonuc:
hedef 0=kamyon 1=tir 2=dorse ve B'nin kutulari yeniden numaralanmis olmali.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shutil
import time
import tempfile

from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=False)

# Test verisi geçici klasörde üretilir; depoya bir şey yazılmaz.
SP = tempfile.mkdtemp(prefix='boxify_test_')

IS = os.path.join(SP, "birlestir"); shutil.rmtree(IS, ignore_errors=True)

import numpy as np, cv2
rng = np.random.default_rng(7)

def set_kur(ad, siniflar, n, kutu_sinifi):
    kok = os.path.join(IS, ad)
    img_d, lbl_d = os.path.join(kok, "images"), os.path.join(kok, "labels")
    os.makedirs(img_d); os.makedirs(lbl_d)
    for i in range(n):
        cv2.imwrite(os.path.join(img_d, f"kare_{i:03d}.jpg"),
                    rng.integers(0, 255, (80, 120, 3), dtype=np.uint8))
        with open(os.path.join(lbl_d, f"kare_{i:03d}.txt"), "w") as f:
            f.write(f"{kutu_sinifi(i)} 0.5 0.5 0.2 0.3\n")
    with open(os.path.join(kok, "data.yaml"), "w") as f:
        f.write(f"nc: {len(siniflar)}\nnames:\n")
        for j, s in enumerate(siniflar):
            f.write(f"  {j}: {s}\n")
    return img_d

A = set_kur("setA", ["kamyon", "tir"], 6, lambda i: i % 2)          # 0,1,0,1,0,1
B = set_kur("setB", ["tir", "dorse"], 4, lambda i: i % 2)           # 0,1,0,1
print("Set A: 0=kamyon 1=tir  (6 gorsel: 3 kamyon, 3 tir)")
print("Set B: 0=tir    1=dorse (4 gorsel: 2 tir,    2 dorse)")
print("Beklenen hedef: 0=kamyon 1=tir 2=dorse  ->  kamyon 3, tir 5, dorse 2\n")

from PyQt5.QtWidgets import QApplication, QMessageBox
app = QApplication([]); kutular = []
for ad in ("warning", "critical", "information", "question"):
    setattr(QMessageBox, ad, staticmethod(
        lambda p, t, x="", *a, **k: (kutular.append((t, str(x)[:100])), QMessageBox.Yes)[1]))

from boxify.araclar.veri_birlestir import BirlestirDialog
d = BirlestirDialog()

from PyQt5.QtWidgets import QFileDialog
secim = [A, B]
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: secim.pop(0) if secim else "")
d._kaynak_ekle(); d._kaynak_ekle()
print("1) kaynak sayisi:", len(d._kaynaklar))
for k in d._kaynaklar:
    print(f"   {k['ad']:<8s} {len(k['gorseller'])} gorsel  siniflar={k['names']}")
print("2) otomatik hedef listesi:", d.hedef_edit.text())

print("3) esleme tablosu:")
for r in range(d.esleme_tablo.rowCount()):
    cb = d.esleme_tablo.cellWidget(r, 3)
    print(f"   {d.esleme_tablo.item(r,0).text():<8s} "
          f"{d.esleme_tablo.item(r,1).text():<8s} (id {d.esleme_tablo.item(r,2).text()})"
          f"  ->  {cb.currentText()}")

OUT = os.path.join(IS, "birlesik")
d.out_edit.setText(OUT); d.mode_combo.setCurrentIndex(0)
kutular.clear()
d._start()
t0 = time.time()
while d._worker is not None and time.time() - t0 < 120:
    app.processEvents(); time.sleep(0.05)
app.processEvents()

print("\n4) sonuc:")
sayim = {}
for f in sorted(os.listdir(os.path.join(OUT, "labels"))):
    with open(os.path.join(OUT, "labels", f)) as fh:
        for ln in fh:
            if ln.strip():
                sayim[int(ln.split()[0])] = sayim.get(int(ln.split()[0]), 0) + 1
hedef = d._hedef_adlar
print("   hedef siniflar:", {i: a for i, a in enumerate(hedef)})
print("   kutu dagilimi :", {hedef[i]: n for i, n in sorted(sayim.items())})
print("   gorsel sayisi :", len(os.listdir(os.path.join(OUT, "images"))))
print("   ad cakismasi cozuldu mu:",
      sorted(os.listdir(os.path.join(OUT, "images")))[:4], "...")
print("   data.yaml:")
print("     " + open(os.path.join(OUT, "data.yaml")).read().replace("\n", "\n     ").strip())

beklenen = {"kamyon": 3, "tir": 5, "dorse": 2}
gercek = {hedef[i]: n for i, n in sayim.items()}
print("\n" + "=" * 60)
print("SONUC:", "GECTI — sinif esleme dogru" if gercek == beklenen
      else f"!! YANLIS  beklenen={beklenen}  gercek={gercek}")

# ── 5) '(atla)' testi: dorse'yi disarida birak
print("\n5) '(atla)' testi — dorse alinmasin:")
for r in range(d.esleme_tablo.rowCount()):
    if d.esleme_tablo.item(r, 1).text() == "dorse":
        d.esleme_tablo.cellWidget(r, 3).setCurrentIndex(0)   # (atla)
OUT2 = os.path.join(IS, "birlesik2")
d.out_edit.setText(OUT2); d.bos_chk.setChecked(True)
d._start()
t0 = time.time()
while d._worker is not None and time.time() - t0 < 120:
    app.processEvents(); time.sleep(0.05)
app.processEvents()
sayim2 = {}
for f in os.listdir(os.path.join(OUT2, "labels")):
    with open(os.path.join(OUT2, "labels", f)) as fh:
        for ln in fh:
            if ln.strip():
                sayim2[int(ln.split()[0])] = sayim2.get(int(ln.split()[0]), 0) + 1
print("   kutu dagilimi:", {hedef[i]: n for i, n in sorted(sayim2.items())})
print("   gorsel sayisi:", len(os.listdir(os.path.join(OUT2, "images"))),
      "(dorse'li 2 gorsel dusmeli -> 8)")
print("   dorse kutusu kaldi mi:", "HAYIR (dogru)" if 2 not in sayim2 else "!! EVET")

shutil.rmtree(SP, ignore_errors=True)
