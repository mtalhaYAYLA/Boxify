"""Labelapp editörü — sınıf paneli, yapışkan sınıf, kısayollar, görsel silme.

Bu testlerin ortak derdi tek bir soru: **etiketleme akışı kesiliyor mu?**
Kutu çizince sınıf atamak için başka bir panele gitmek, sınıf yokken kutunun
sessizce düşmesi, her kutuda sınıfı yeniden seçmek — hepsi akışı kesen
davranışlardı ve hepsi burada sınanıyor.

    python testler/test_editor.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, Rapor   # noqa: E402

yolu_kur()

import numpy as np                                          # noqa: E402
import cv2                                                  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox       # noqa: E402
from PyQt5.QtCore import Qt, QPoint                         # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_dayaniklilik import surukle_c                     # noqa: E402


def _klasor(kare_sayisi=4, sinif_dosyasi=True):
    kok = tempfile.mkdtemp(prefix="boxify_editor_")
    for i in range(kare_sayisi):
        cv2.imwrite(os.path.join(kok, f"k{i}.jpg"),
                    np.random.default_rng(i).integers(
                        0, 255, (300, 400, 3), dtype=np.uint8))
    if sinif_dosyasi:
        with open(os.path.join(kok, "classes.txt"), "w") as f:
            f.write("arac\ninsan\ntekerlek\n")
    return kok


def _pencere(app, kok):
    from boxify.araclar.labelapp import MainWindow
    w = MainWindow()
    w.resize(1300, 820)
    w.show()
    w.dataset.load_folder(kok)
    w.dataset.load_classes()
    if not w.dataset.label_classes:
        w.dataset.auto_detect_classes()
    w.label_panel.refresh(w.dataset.label_classes)
    w._refresh_list()
    w._load(0)
    app.processEvents()
    return w


def sinif_paneli_testi(r, app):
    """Sınıf hiç yokken kutu çizilebiliyor ve sınıf oradan yaratılıyor mu?"""
    kok = _klasor(sinif_dosyasi=False)
    try:
        w = _pencere(app, kok)
        c = w.canvas
        r.kontrol(not w.dataset.label_classes, "başlangıçta sınıf yok",
                  f"{len(w.dataset.label_classes)} sınıf")

        surukle_c(app, c, c._to_canvas(40, 40), c._to_canvas(180, 160))
        kutular = w.dataset.current_image.bboxes
        r.kontrol(len(kutular) == 1,
                  "sınıf yokken de kutu çizilebiliyor (eskiden düşüyordu)",
                  f"{len(kutular)} kutu")
        r.kontrol(w.popup.isVisible(), "kutu çizilince sınıf paneli açılıyor")
        r.kontrol(w.popup.alan.hasFocus(),
                  "sınıf zorunluyken imleç alana gidiyor")

        w.popup.alan.setEditText("forklift")
        w.popup.onayla()
        app.processEvents()
        adlar = [lc.name for lc in w.dataset.label_classes]
        r.kontrol(adlar == ["forklift"], "olmayan ad yazılınca sınıf yaratılıyor",
                  str(adlar))
        r.kontrol(kutular and kutular[0].class_id == 0,
                  "kutu yeni sınıfa bağlanıyor")
        r.kontrol(not w.popup.isVisible(), "uygulayınca panel kapanıyor")

        # yapışkan sınıf: ikinci kutu aynı sınıfla gelmeli
        surukle_c(app, c, c._to_canvas(220, 40), c._to_canvas(320, 150))
        kutular = w.dataset.current_image.bboxes
        r.kontrol(len(kutular) == 2 and kutular[1].class_id == 0,
                  "sonraki kutu yapışkan sınıfla geliyor")

        # panel kapatılırsa sınıfsız kalan taze kutu temizlenmeli
        w2 = _pencere(app, _klasor(sinif_dosyasi=False))
        c2 = w2.canvas
        surukle_c(app, c2, c2._to_canvas(40, 40), c2._to_canvas(180, 160))
        w2._popup_kapat()
        app.processEvents()
        r.kontrol(not w2.dataset.current_image.bboxes,
                  "vazgeçilince sınıfsız kutu bırakılmıyor",
                  f"{len(w2.dataset.current_image.bboxes)} kutu")
        w2.close()
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def kisayol_testi(r, app):
    """1-9: sınıf seçme ve seçili kutunun sınıfını değiştirme."""
    kok = _klasor()
    try:
        w = _pencere(app, kok)
        c = w.canvas
        surukle_c(app, c, c._to_canvas(40, 40), c._to_canvas(180, 160))
        app.processEvents()
        kutu = w.dataset.current_image.bboxes[0]
        r.kontrol(kutu.class_id == 0, "ilk kutu ilk sınıfla geliyor")

        c.sec(0)
        w._sinif_sec(2)          # 3 tuşu
        app.processEvents()
        r.kontrol(w.dataset.current_image.bboxes[0].class_id == 2,
                  "1-9 seçili kutunun sınıfını değiştiriyor",
                  f"class_id {w.dataset.current_image.bboxes[0].class_id}")
        r.kontrol(w._yapiskan_sinif == 2, "kısayol yapışkan sınıfı da günceller")

        # geri alınabilir olmalı
        w._geri_al()
        app.processEvents()
        r.kontrol(w.dataset.current_image.bboxes[0].class_id == 0,
                  "kısayolla yapılan sınıf değişimi geri alınabiliyor")

        # sınıf sayısının ötesindeki tuş bir şey bozmamalı
        onceki = w._yapiskan_sinif
        w._sinif_sec(8)
        r.kontrol(w._yapiskan_sinif == onceki,
                  "olmayan sınıf numarası yok sayılıyor")
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def gorsel_silme_testi(r, app):
    """Görseli sil: dosya gerçekten gidiyor mu, liste tutarlı kalıyor mu?"""
    kok = _klasor(kare_sayisi=3)
    try:
        w = _pencere(app, kok)
        c = w.canvas
        surukle_c(app, c, c._to_canvas(40, 40), c._to_canvas(180, 160))
        w._save_current()
        app.processEvents()

        yol = w.dataset.current_image.image_path
        etiket = w.dataset.current_image.label_path()
        r.kontrol(os.path.exists(etiket), "etiket dosyası yazılmış")

        QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
        w._gorseli_sil()
        app.processEvents()

        r.kontrol(not os.path.exists(yol), "görsel diskten silindi")
        r.kontrol(not os.path.exists(etiket), "etiket de silindi")
        r.kontrol(len(w.dataset.images) == 2, "liste bir kısaldı",
                  f"{len(w.dataset.images)} kayıt")
        r.kontrol(w.img_list.count() == 2, "arayüz listesi de kısaldı")
        r.kontrol(w.dataset.current_image is not None,
                  "silmeden sonra bir sonraki kareye geçildi")

        # hepsi silinince çökmemeli
        w._gorseli_sil()
        w._gorseli_sil()
        app.processEvents()
        r.kontrol(len(w.dataset.images) == 0 and w.img_list.count() == 0,
                  "son görsel de silinebiliyor, çökme yok")
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def kucuk_resim_testi(r, app):
    """Küçük resimler arka planda üretilip önbelleğe giriyor mu?"""
    import time
    kok = _klasor(kare_sayisi=6)
    try:
        w = _pencere(app, kok)
        w._kucuk_resimleri_baslat()
        t0 = time.time()
        while time.time() - t0 < 20 and len(w._kucuk_onbellek) < 6:
            app.processEvents()
            time.sleep(0.02)
        r.kontrol(len(w._kucuk_onbellek) == 6,
                  "küçük resimler arka planda üretiliyor",
                  f"{len(w._kucuk_onbellek)} / 6")
        r.kontrol(not w.img_list.item(0).icon().isNull(),
                  "üretilen küçük resim listeye işleniyor")

        # liste kipine geçince çökmemeli, geri dönünce önbellek kullanılmalı
        w.izgara_btn.setChecked(False)
        w._gorunumu_degistir()
        app.processEvents()
        r.kontrol(w.img_list.count() == 6, "liste kipinde kayıtlar duruyor")
        w.izgara_btn.setChecked(True)
        w._gorunumu_degistir()
        app.processEvents()
        r.kontrol(not w.img_list.item(0).icon().isNull(),
                  "ızgaraya dönünce önbellekten anında geliyor")
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def main() -> int:
    r = Rapor("Labelapp editörü")
    app = QApplication.instance() or QApplication([])
    for ad in ("warning", "critical", "information"):
        setattr(QMessageBox, ad, staticmethod(lambda *a, **k: QMessageBox.Ok))
    sinif_paneli_testi(r, app)
    kisayol_testi(r, app)
    gorsel_silme_testi(r, app)
    kucuk_resim_testi(r, app)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
