"""Labelapp tuvali ve dayanıklılık — fare ile kutu çizme gerçekten çalışıyor mu?

Labelapp'in tuvali uzun süre "başsız test edilemez" diye kenarda kaldı. Oysa
Qt olayları doğrudan gönderilerek sınanabiliyor — ve burada sınanan şey, elle
etiketlemenin tamamı: çizim, ters yönde çizim, kazara tıklama, görüntü dışına
taşma, kaydet/yükle turu ve silme.

Ayrıca araçların dayanıklılığı: iş sürerken kapatma, aynı işi iki kez
başlatma, boş klasör, çıktının kaynağın kendisi olması.

    python testler/test_dayaniklilik.py
"""

import os
import sys
import shutil
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, Rapor   # noqa: E402

yolu_kur()

import numpy as np                                                  # noqa: E402
import cv2                                                          # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog  # noqa: E402
from PyQt5.QtCore import Qt, QPoint, QEvent                         # noqa: E402
from PyQt5.QtGui import QMouseEvent                                 # noqa: E402
from PyQt5.QtTest import QTest                                      # noqa: E402


def _kutular_yakala():
    yakalanan = []
    for ad in ("warning", "critical", "information", "question"):
        setattr(QMessageBox, ad, staticmethod(
            lambda p, t, x="", *a, _y=yakalanan, **k:
                (_y.append((t, str(x)[:100])), QMessageBox.Yes)[1]))
    return yakalanan


def tuval_testi(r, app):
    """Fare olaylarını doğrudan göndererek elle etiketlemeyi sına."""
    kok = tempfile.mkdtemp(prefix="boxify_tuval_")
    try:
        for i in range(3):
            cv2.imwrite(os.path.join(kok, f"k{i}.jpg"),
                        np.random.default_rng(i).integers(
                            0, 255, (300, 400, 3), dtype=np.uint8))
        with open(os.path.join(kok, "classes.txt"), "w") as f:
            f.write("nesne\nikinci\n")

        from boxify.araclar.labelapp import MainWindow
        w = MainWindow()
        w.resize(1200, 800)
        w.show()
        w.dataset.load_folder(kok)
        w.dataset.load_classes()
        if not w.dataset.label_classes:
            w.dataset.auto_detect_classes()
        w.label_panel.refresh(w.dataset.label_classes)
        w._refresh_list()
        w._load(0)
        app.processEvents()
        c = w.canvas
        r.bilgi(f"tuval {c.width()}x{c.height()}, görüntü "
                f"{c.pixmap.width()}x{c.pixmap.height()}, ölçek {c._scale:.2f}")

        def surukle(p1, p2):
            # QTest.mouseMove düğme basılıyken hareketi offscreen'de iletmiyor;
            # olaylar doğrudan gönderiliyor.
            def olay(tur, pos, dugme, dugmeler):
                return QMouseEvent(tur, pos, dugme, dugmeler, Qt.NoModifier)
            app.sendEvent(c, olay(QEvent.MouseButtonPress, p1,
                                  Qt.LeftButton, Qt.LeftButton))
            for t in (0.34, 0.67, 1.0):
                ara = QPoint(int(p1.x() + (p2.x() - p1.x()) * t),
                             int(p1.y() + (p2.y() - p1.y()) * t))
                app.sendEvent(c, olay(QEvent.MouseMove, ara,
                                      Qt.NoButton, Qt.LeftButton))
            app.processEvents()
            app.sendEvent(c, olay(QEvent.MouseButtonRelease, p2,
                                  Qt.LeftButton, Qt.NoButton))
            app.processEvents()

        # 1) fare ile kutu çiz
        once = len(w.dataset.current_image.bboxes)
        surukle(c._to_canvas(50, 40), c._to_canvas(200, 180))
        kutular = w.dataset.current_image.bboxes
        r.kontrol(len(kutular) == once + 1, "fare ile kutu çizilebiliyor",
                  f"{once} -> {len(kutular)}")
        if len(kutular) == once + 1:
            k = kutular[-1]
            sapma = max(abs(k.x1 - 50), abs(k.y1 - 40),
                        abs(k.x2 - 200), abs(k.y2 - 180))
            r.kontrol(sapma <= 3, "çizilen kutu doğru koordinatta",
                      f"({k.x1},{k.y1})-({k.x2},{k.y2}), sapma {sapma}")

        # 2) kazara tıklama kutu üretmemeli
        once = len(w.dataset.current_image.bboxes)
        p = c._to_canvas(300, 250)
        surukle(p, QPoint(p.x() + 2, p.y() + 2))
        r.kontrol(len(w.dataset.current_image.bboxes) == once,
                  "kazara tıklama kutu üretmiyor")

        # 3) ters yönde çizim normalleşmeli
        once = len(w.dataset.current_image.bboxes)
        surukle(c._to_canvas(350, 280), c._to_canvas(250, 200))
        kutular = w.dataset.current_image.bboxes
        if r.kontrol(len(kutular) == once + 1, "ters yönde çizim de kutu üretiyor"):
            k = kutular[-1]
            r.kontrol(k.x1 < k.x2 and k.y1 < k.y2,
                      "ters çizimde köşeler normalleşiyor",
                      f"({k.x1},{k.y1})-({k.x2},{k.y2})")

        # 4) görüntü dışına taşan çizim kırpılmalı
        once = len(w.dataset.current_image.bboxes)
        surukle(c._to_canvas(380, 280), QPoint(c.width() - 1, c.height() - 1))
        kutular = w.dataset.current_image.bboxes
        if len(kutular) == once + 1:
            k = kutular[-1]
            r.kontrol(0 <= k.x1 and 0 <= k.y1 and k.x2 <= 400 and k.y2 <= 300,
                      "taşan çizim görüntü sınırına kırpılıyor",
                      f"({k.x1},{k.y1})-({k.x2},{k.y2}) / 400x300")

        # 5) kaydet + yeniden yükle turu
        n = len(w.dataset.current_image.bboxes)
        w._save_current()
        app.processEvents()
        w._load(1)
        w._load(0)
        app.processEvents()
        m = len(w.dataset.current_image.bboxes)
        r.kontrol(m == n, "kaydet/yükle turunda kutular korunuyor", f"{n} -> {m}")

        # 6) Delete tuşu
        if m:
            c._selected = 0
            QTest.keyClick(c, Qt.Key_Delete)
            app.processEvents()
            r.kontrol(len(w.dataset.current_image.bboxes) == m - 1,
                      "Delete tuşu kutuyu siliyor")
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def dayaniklilik_testi(r, app):
    """İş sürerken kapatma, çift başlatma, boş klasör, çıktı = kaynak."""
    yakalanan = _kutular_yakala()
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
    QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))

    kok = tempfile.mkdtemp(prefix="boxify_day_")
    try:
        img = os.path.join(kok, "images")
        lbl = os.path.join(kok, "labels")
        os.makedirs(img)
        os.makedirs(lbl)
        for i in range(40):
            cv2.imwrite(os.path.join(img, f"k{i:03d}.jpg"),
                        np.random.default_rng(i).integers(
                            0, 255, (240, 320, 3), dtype=np.uint8))
            with open(os.path.join(lbl, f"k{i:03d}.txt"), "w") as f:
                f.write("0 0.5 0.5 0.2 0.2\n")

        def bekle(kosul, sn=60):
            t0 = time.time()
            while time.time() - t0 < sn:
                app.processEvents()
                if kosul():
                    return True
                time.sleep(0.02)
            return False

        from boxify.araclar.veri_denetci import MainWindow as VD

        # aynı işi üç kez başlat — tek koşu olmalı
        w = VD()
        w._set_dirs(img, lbl)
        w._start_audit()
        w._start_audit()
        w._start_audit()
        bekle(lambda: getattr(w, "_worker", None) is None)
        r.kontrol(len(w._items) == 40, "çift başlatma işi bozmuyor",
                  f"{len(w._items)} kayıt (40 olmalı)")
        w.close()

        # iş sürerken kapat — işçi arkada kalmamalı
        w2 = VD()
        w2._set_dirs(img, lbl)
        w2._start_audit()
        app.processEvents()
        w2.close()
        app.processEvents()
        time.sleep(0.6)
        app.processEvents()
        kaldi = (getattr(w2, "_worker", None) is not None
                 and w2._worker.isRunning())
        r.kontrol(not kaldi, "iş sürerken kapatınca işçi arkada kalmıyor")

        # boş klasör çökertmemeli
        bos = os.path.join(kok, "bos")
        os.makedirs(bos)
        w3 = VD()
        w3._set_dirs(bos, bos)
        w3._start_audit()
        bekle(lambda: getattr(w3, "_worker", None) is None, 30)
        r.kontrol(len(w3._items) == 0, "boş klasör çökertmiyor")
        w3.close()

        # çıktı klasörü kaynağın KENDİSİ olamamalı
        import json
        cj = os.path.join(kok, "c.json")
        with open(cj, "w") as f:
            json.dump({"images": [{"id": 1, "file_name": "k000.jpg",
                                   "width": 320, "height": 240}],
                       "categories": [{"id": 1, "name": "n"}],
                       "annotations": [{"id": 1, "image_id": 1, "category_id": 1,
                                        "bbox": [5, 5, 20, 20], "iscrowd": 0}]}, f)
        from boxify.araclar.veri_ice_aktar import IceAktarDialog
        d = IceAktarDialog()
        d.coco_rb.setChecked(True)
        d._kaynak = cj
        d.kaynak_edit.setText(cj)
        d.gorsel_edit.setText(img)
        d._oku()
        yakalanan.clear()
        d.out_edit.setText(img)          # çıktı = kaynak görsel klasörü
        d._start()
        app.processEvents()
        engellendi = any("Geçersiz" in t for t, _ in yakalanan)
        r.kontrol(engellendi, "çıktı kaynağın kendisi olamıyor",
                  str(yakalanan[:1]))
        r.kontrol(d._worker is None, "engellenince iş başlamıyor")
        d.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def main() -> int:
    r = Rapor("Tuval ve dayanıklılık")
    app = QApplication.instance() or QApplication([])
    _kutular_yakala()
    tuval_testi(r, app)
    dayaniklilik_testi(r, app)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
