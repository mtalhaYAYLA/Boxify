"""Takip destekli etiketleme — kutu doğru yere mi taşınıyor?

Takip bir tahmindir ve yanlış kutuyu sessizce etiket dosyasına yazmak, hiç
etiket olmamasından kötüdür: veri bozulur, kimse fark etmez. Bu yüzden test
yalnızca "taşıyor mu"ya değil, **taşıyamadığında bırakıyor mu**ya da bakar.

    python testler/test_takip.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, Rapor   # noqa: E402

yolu_kur()

import numpy as np                                                  # noqa: E402
import cv2                                                          # noqa: E402

from boxify.araclar.labelapp.core.takip import (                    # noqa: E402
    kutu_tasi, kutulari_tasi,
)

W, H = 320, 240


def sahne(nesne_xy, nesne_boyut=(60, 50), doku_kay=0):
    """Dokulu arka plan + belirgin desenli bir nesne."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    zemin = (90 + 40 * np.sin((xx + doku_kay) / 11)
             + 30 * np.cos(yy / 9) + 20 * np.sin((xx + yy) / 17))
    kare = np.repeat(zemin[:, :, None], 3, axis=2)

    x, y = nesne_xy
    nw, nh = nesne_boyut
    # Nesne: takip edilebilir köşeleri olsun diye damalı desen
    for i in range(nh):
        for j in range(nw):
            if ((i // 8) + (j // 8)) % 2 == 0:
                kare[y + i, x + j] = 235
            else:
                kare[y + i, x + j] = 45
    return np.clip(kare, 0, 255).astype(np.uint8)


def ortusme(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    kesisim = (ix2 - ix1) * (iy2 - iy1)
    birlesim = ((ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - kesisim)
    return kesisim / max(1e-6, birlesim)


def arayuz_testi(r):
    """Labelapp üzerinden uçtan uca: kutu gerçekten sonraki karelere yazılıyor mu?"""
    import shutil
    import tempfile
    import cv2
    from PyQt5.QtWidgets import QApplication, QMessageBox, QInputDialog

    app = QApplication.instance() or QApplication([])
    for ad in ("warning", "critical", "information", "question"):
        setattr(QMessageBox, ad, staticmethod(
            lambda p, t, x="", *a, **k: QMessageBox.Yes))

    kok = tempfile.mkdtemp(prefix="boxify_takip_")
    try:
        # 10 kare: nesne her karede 5 px sağa kayıyor
        for i in range(10):
            cv2.imwrite(os.path.join(kok, f"kare_{i:03d}.jpg"),
                        sahne((60 + i * 5, 90), doku_kay=i))
        with open(os.path.join(kok, "classes.txt"), "w") as f:
            f.write("nesne\n")

        from boxify.araclar.labelapp import MainWindow
        from boxify.araclar.labelapp.core.annotation import BBox

        w = MainWindow()
        w.dataset.load_folder(kok)
        w.dataset.load_classes()
        if not w.dataset.label_classes:
            w.dataset.auto_detect_classes()
        w._refresh_list()
        w._load(0)

        ilk = w.dataset.current_image
        ilk.bboxes = [BBox(60, 90, 120, 140, 0)]
        w.canvas.set_annotations(ilk.bboxes, w.dataset.label_classes)

        # diyalog: 6 kareye taşı
        QInputDialog.getInt = staticmethod(lambda *a, **k: (6, True))
        w._kutulari_tasi()
        app.processEvents()

        yazilan = []
        for i in range(1, 10):
            ann = w.dataset.images[i]
            ann.load()
            if ann.bboxes:
                yazilan.append((i, ann.bboxes[0].x1))
        r.bilgi(f"yazılan kareler (indeks, x1): {yazilan}")
        r.kontrol(len(yazilan) == 6, "istenen sayıda kareye yazıldı",
                  f"{len(yazilan)} != 6")
        if yazilan:
            beklenen = [60 + i * 5 for i, _ in yazilan]
            gercek = [x for _i, x in yazilan]
            sapma = max(abs(b - g) for b, g in zip(beklenen, gercek))
            r.kontrol(sapma <= 4, "taşınan kutular doğru yerde (sapma <= 4 px)",
                      f"beklenen {beklenen}, gerçek {gercek}")
        r.kontrol(all(os.path.exists(w.dataset.images[i].label_path())
                      for i, _ in yazilan),
                  "etiket dosyaları diske yazıldı")

        # ── kutusu olan kareye YAZILMAMALI ──────────────────────────────
        hedef = w.dataset.images[8]
        hedef.img_width, hedef.img_height = 320, 240
        hedef.bboxes = [BBox(1, 2, 33, 44, 0)]
        hedef.save()
        w._load(7)
        yedi = w.dataset.current_image
        yedi.bboxes = [BBox(95, 90, 155, 140, 0)]
        QInputDialog.getInt = staticmethod(lambda *a, **k: (2, True))
        w._kutulari_tasi()
        app.processEvents()
        hedef.bboxes = []
        hedef.load()
        # Kutu YOLO'ya normalize edilip geri okunduğu için birkaç piksel
        # yuvarlanabilir; önemli olan ORİJİNAL kutunun durması. Taşıma olsaydı
        # kutu x1 ~ 95+ olurdu (7. karedeki kutu oradan geliyor).
        korundu = (len(hedef.bboxes) == 1 and hedef.bboxes[0].x1 < 10
                   and hedef.bboxes[0].x2 < 60)
        r.kontrol(bool(korundu),
                  "var olan kutunun üstüne YAZILMIYOR",
                  str([(b.x1, b.y1, b.x2, b.y2) for b in hedef.bboxes]))
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def kayma_testi(r):
    """Kutu nesneden kayınca zincir duruyor mu?

    Bu, gerçek fabrika görüntüsünde bulunmuş bir kusurun nöbetçisi: ileri-geri
    tutarlılık tek başına kaymayı görmüyordu, güven 0.99'da kalırken kutu
    nesneden tamamen ayrılıyordu (50. karede IoU 0.08). Görünüm denetimi
    eklendi; bu test onun devrede kaldığını doğrular.
    """
    from boxify.araclar.labelapp.core.takip import KutuZinciri, benzerlik, yama_al

    # Nesne bir süre sonra sahneden çıkıp yerine BAŞKA bir şey geliyor.
    kutu = (100, 90, 160, 140)
    ilk = sahne((100, 90))
    zincir = KutuZinciri(ilk, [kutu])

    adim_sayisi = 0
    for i in range(1, 16):
        if i <= 5:
            kare = sahne((100 + i * 3, 90), doku_kay=i)      # normal hareket
        else:
            # nesne kayboldu: kutunun olduğu yerde artık düz arka plan var
            kare = sahne((100 + i * 3, 90), doku_kay=i)
            kare[80:150, 90:170] = 120
        sonuc = zincir.adim(kare)
        if not sonuc:
            break
        adim_sayisi += 1

    r.bilgi(f"nesne kaybolunca {adim_sayisi}. adımda durdu — {zincir.son_sebep}")
    r.kontrol(adim_sayisi < 12, "nesne kaybolunca zincir duruyor",
              f"{adim_sayisi} adım sürdü")
    r.kontrol("kaydı" in zincir.son_sebep or "kayboldu" in zincir.son_sebep,
              "durma sebebi bildiriliyor", zincir.son_sebep)

    # Görünüm ölçüsü kendisi doğru mu: aynı yama 1.0, alakasız yama düşük
    y1 = yama_al(ilk, kutu)
    r.kontrol(benzerlik(y1, y1) > 0.99, "aynı yamanın benzerliği 1")
    rng2 = np.random.default_rng(9)
    alakasiz = rng2.integers(0, 255, (H, W, 3), dtype=np.uint8)
    r.kontrol(benzerlik(y1, yama_al(alakasiz, kutu)) < 0.4,
              "alakasız yamanın benzerliği düşük",
              f"{benzerlik(y1, yama_al(alakasiz, kutu)):.2f}")

    # Zincir hareketsiz sahnede uzun süre dayanmalı (yanlış alarm olmasın)
    sabit = sahne((100, 90))
    z2 = KutuZinciri(sabit, [kutu])
    dayanan = sum(1 for _ in range(12) if z2.adim(sabit.copy()))
    r.kontrol(dayanan == 12, "hareketsiz sahnede yanlış alarm yok",
              f"{dayanan}/12")


def main() -> int:
    r = Rapor("Takip destekli etiketleme")

    # ── 1. Öteleme: nesne 6 px sağa kaysın ──────────────────────────────
    k1 = sahne((100, 90))
    k2 = sahne((106, 90))
    kutu = (100, 90, 160, 140)
    yeni, guven = kutu_tasi(k1, k2, kutu)
    r.bilgi(f"öteleme sonucu: {yeni}  güven {guven:.2f}")
    r.kontrol(yeni is not None, "yatay öteleme takip edildi")
    if yeni:
        beklenen = (106, 90, 166, 140)
        r.kontrol(ortusme(yeni, beklenen) > 0.8,
                  "taşınan kutu beklenen yerde (IoU > 0.8)",
                  f"IoU {ortusme(yeni, beklenen):.2f}, beklenen {beklenen}")
        r.kontrol(guven > 0.5, "güven makul", f"{guven:.2f}")

    # ── 2. Çapraz hareket ───────────────────────────────────────────────
    k3 = sahne((100, 90))
    k4 = sahne((105, 96))
    yeni2, _ = kutu_tasi(k3, k4, (100, 90, 160, 140))
    r.kontrol(yeni2 is not None and ortusme(yeni2, (105, 96, 165, 146)) > 0.75,
              "çapraz hareket takip edildi",
              f"{yeni2}, IoU {ortusme(yeni2 or (0,0,0,0), (105,96,165,146)):.2f}")

    # ── 3. Hareket yoksa kutu yerinde kalmalı ───────────────────────────
    ayni = sahne((100, 90))
    yeni3, guven3 = kutu_tasi(ayni, ayni.copy(), (100, 90, 160, 140))
    r.kontrol(yeni3 is not None and ortusme(yeni3, (100, 90, 160, 140)) > 0.95,
              "hareket yokken kutu kaymıyor", str(yeni3))

    # ── 4. Sahne tamamen değişirse BIRAKMALI ────────────────────────────
    # Yanlış kutu yazmaktansa hiç yazmamak yeğdir.
    rng = np.random.default_rng(3)
    alakasiz = rng.integers(0, 255, (H, W, 3), dtype=np.uint8)
    yeni4, guven4 = kutu_tasi(sahne((100, 90)), alakasiz, (100, 90, 160, 140))
    r.kontrol(yeni4 is None or guven4 < 0.35,
              "alakasız kareye takip zorlanmıyor",
              f"sonuç {yeni4}, güven {guven4:.2f}")

    # ── 5. Nesne kareden çıkarsa elenmeli ───────────────────────────────
    kenar1 = sahne((250, 90))
    kenar2 = sahne((250, 90))       # aynı; kutu bilerek dışarıda veriliyor
    yeni5, _ = kutu_tasi(kenar1, kenar2, (W - 3, 90, W + 60, 140))
    r.kontrol(yeni5 is None, "sınır dışındaki kutu elenir", str(yeni5))

    # ── 6. Bozuk girdi çökertmemeli ─────────────────────────────────────
    r.kontrol(kutu_tasi(None, k2, kutu) == (None, 0.0), "None kare güvenli")
    r.kontrol(kutu_tasi(k1, k2, (10, 10, 11, 11))[0] is None,
              "çok küçük kutu reddediliyor")
    farkli = np.zeros((100, 100, 3), dtype=np.uint8)
    r.kontrol(kutu_tasi(k1, farkli, kutu) == (None, 0.0),
              "boyutu uyuşmayan kareler güvenli")

    # ── 7. Çoklu kutu ───────────────────────────────────────────────────
    c1 = sahne((60, 60))
    c1[30:70, 220:270] = np.tile(
        np.array([[30, 220]], dtype=np.uint8).repeat(25, 1), (40, 1))[:, :, None]
    c2 = sahne((66, 60))
    c2[30:70, 226:276] = np.tile(
        np.array([[30, 220]], dtype=np.uint8).repeat(25, 1), (40, 1))[:, :, None]
    sonuc = kutulari_tasi(c1, c2, [(60, 60, 120, 110), (220, 30, 270, 70)])
    r.bilgi(f"çoklu kutu sonucu: {[(i, k) for i, k, _ in sonuc]}")
    r.kontrol(len(sonuc) >= 1, "en az bir kutu taşındı")
    r.kontrol(all(0 <= i < 2 for i, _, _ in sonuc),
              "dönen indeksler girdiyle eşleşiyor")

    # ── 8. Gri görüntü de kabul edilmeli ────────────────────────────────
    g1 = cv2.cvtColor(sahne((100, 90)), cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(sahne((105, 90)), cv2.COLOR_BGR2GRAY)
    yeni8, _ = kutu_tasi(g1, g2, (100, 90, 160, 140))
    r.kontrol(yeni8 is not None, "gri görüntüyle de çalışıyor", str(yeni8))

    # ── 9. Zincirleme: 8 kare boyunca kayma birikmemeli ─────────────────
    kutu_z = (100, 90, 160, 140)
    onceki = sahne((100, 90))
    for adim in range(1, 9):
        sonrakii = sahne((100 + adim * 4, 90), doku_kay=adim)
        yeni_z, g = kutu_tasi(onceki, sonrakii, kutu_z)
        if yeni_z is None:
            break
        kutu_z, onceki = yeni_z, sonrakii
    beklenen_son = (100 + 8 * 4, 90, 160 + 8 * 4, 140)
    iou = ortusme(kutu_z, beklenen_son)
    r.bilgi(f"8 kare sonunda: {kutu_z}, beklenen {beklenen_son}")
    r.kontrol(iou > 0.7, "8 kare zincirinde sapma birikmiyor (IoU > 0.7)",
              f"IoU {iou:.2f}")

    kayma_testi(r)
    arayuz_testi(r)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
