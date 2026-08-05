"""Model Karsilastir uctan uca testi: gercek video + sahte YOLO."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time
import tempfile

from ortak import yolu_kur, KOK   # noqa: E402

yolu_kur(sahte_ultralytics=True)

# Test verisi geçici klasörde üretilir; depoya bir şey yazılmaz.
SP = tempfile.mkdtemp(prefix='boxify_test_')


import cv2, numpy as np
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

hatalar = []
def bekle(kosul, saniye=30, app=None):
    t0 = time.time()
    while time.time() - t0 < saniye:
        app.processEvents()
        if kosul(): return True
        time.sleep(0.02)
    return False

# --- test verisi
VID = os.path.join(SP, "test.mp4")
if not os.path.exists(VID):
    w = cv2.VideoWriter(VID, cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (321, 241))  # tek sayili olcu bilerek
    for i in range(75):
        f = np.full((241, 321, 3), (i * 3) % 255, dtype=np.uint8)
        w.write(f)
    w.release()
for ad in ("model_uc.pt", "model_iki.pt", "model_bos.pt"):
    open(os.path.join(SP, ad), "wb").close()

app = QApplication([])
from boxify.araclar.model_karsilastir import MainWindow
OUT = os.path.join(SP, "cikti")

def kur(model_dosyalari):
    win = MainWindow()
    win._video_path = VID; win._probe_video(VID)
    win._out_dir = OUT
    # istenen sayida yuva ac
    while sum(1 for s in win._slot_rows if s["aktif"]) < len(model_dosyalari):
        win._model_ekle()
    while sum(1 for s in win._slot_rows if s["aktif"]) > len(model_dosyalari):
        aktif = [i for i, s in enumerate(win._slot_rows) if s["aktif"]]
        win._model_kaldir(aktif[-1])
    for i, dosya in enumerate(model_dosyalari):
        yol = os.path.join(SP, dosya)
        s = win._slot_rows[i]
        s["path"] = yol; s["path_edit"].setText(yol)
        s["label_edit"].setText(os.path.splitext(dosya)[0])
        win._load_class_names(i, yol)
    ok = bekle(lambda: not win._sinif_yukleyiciler, 20, app)
    if not ok: hatalar.append("sinif yukleyici zaman asimi")
    return win

def calistir(win, ad):
    win.range_chk.setChecked(True)
    win.start_edit.setText("00:00.000"); win.end_edit.setText("00:02.000")
    win.sample_fps_spin.setValue(5.0)
    win._start()
    if win._worker is None:
        hatalar.append(f"{ad}: worker baslamadi (dogrulama engelledi)"); return None
    ok = bekle(lambda: win._worker is None, 60, app)
    if not ok: hatalar.append(f"{ad}: worker zaman asimi"); return None
    return win.report_box.toPlainText()

print("=" * 70)
print("TEST 1 — iki model, tum siniflar acik")
w1 = kur(["model_uc.pt", "model_iki.pt"])
print("  A sinif ozeti:", w1._slot_rows[0]["sinif_durum"].text())
r = calistir(w1, "T1")
if r:
    print("  rapor satiri:", [l for l in r.splitlines() if l.startswith("model_uc")][:1])
    for beklenen in ("Model ayarları", "Öne çıkanlar", "Sınıf kümeleri farklı"):
        if beklenen not in r: hatalar.append(f"T1: raporda '{beklenen}' yok")
    if not os.path.exists(os.path.join(OUT, "karsilastirma.mp4")):
        hatalar.append("T1: karsilastirma.mp4 yazilmadi")
    else:
        c = cv2.VideoCapture(os.path.join(OUT, "karsilastirma.mp4"))
        print(f"  video: {int(c.get(cv2.CAP_PROP_FRAME_COUNT))} kare, "
              f"{int(c.get(cv2.CAP_PROP_FRAME_WIDTH))}x{int(c.get(cv2.CAP_PROP_FRAME_HEIGHT))}")
        c.release()
w1.close()

print("\nTEST 2 — TEK model")
w2 = kur(["model_uc.pt"])
print("  aktif model sayisi:", len(w2._active_slots()))
r = calistir(w2, "T2")
if r:
    if "Tek model çalıştırıldı" not in r: hatalar.append("T2: tek-model notu yok")
    if "Öne çıkanlar" in r: hatalar.append("T2: tek modelde 'Öne çıkanlar' cikti")
    print("  tek model raporu OK")
w2.close()

print("\nTEST 3 — sinif filtresi (A'da sadece 'tir'), modele ozel ayar")
w3 = kur(["model_uc.pt", "model_iki.pt"])
lst = w3._slot_rows[0]["class_list"]
for i in range(lst.count()):
    lst.item(i).setCheckState(Qt.Checked if lst.item(i).data(Qt.UserRole) == 1 else Qt.Unchecked)
w3._sinif_ozet_tazele(0)
print("  A durumu:", w3._slot_rows[0]["sinif_durum"].text())
print("  A filtresi:", w3._selected_classes(w3._slot_rows[0]))
w3._slot_rows[1]["ozel_chk"].setChecked(True)
w3._slot_rows[1]["conf"].setValue(0.85)
w3.layout_combo.setCurrentIndex(1)   # dikey
r = calistir(w3, "T3")
if r:
    for satir in r.splitlines():
        if satir.startswith("model_uc:") or satir.startswith("model_iki:"):
            print("  ", satir)
    if "açık sınıflar: tir" not in r: hatalar.append("T3: sinif filtresi rapora yansimadi")
    if "[özel]" not in r: hatalar.append("T3: ozel ayar rapora yansimadi")
    if "! En az bir model özel ayarla koştu" not in r: hatalar.append("T3: ozel ayar uyarisi yok")
w3.close()

print("\nTEST 4 — hicbir sinif acik degil -> uyari ile engelleniyor mu")
w4 = kur(["model_uc.pt", "model_iki.pt"])
w4._set_all_classes(0, False)
uyarilar = []
QMessageBox.warning = staticmethod(lambda p, t, x, *a, **k: (uyarilar.append(t), QMessageBox.Ok)[1])
w4._start()
if w4._worker is not None: hatalar.append("T4: bos filtreyle baslamamaliydi")
print("  uyari:", uyarilar)
w4.close()

print("\nTEST 5 — sinif kumesi bos model (names yok)")
w5 = kur(["model_bos.pt"])
print("  bos model durumu:", w5._slot_rows[0]["sinif_durum"].text())
r = calistir(w5, "T5")
print("  bos model kosusu:", "tamam" if r else "BASARISIZ")
w5.close()

print("\n" + "=" * 70)
print("HATALAR:", hatalar or "YOK — tum testler gecti")
sys.exit(1 if hatalar else 0)
