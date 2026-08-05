"""COCO / Pascal VOC içe aktarma — kutu dönüşümü doğru mu?

Üç biçimin kutu tanımı birbirinden farklı:

    COCO : [x, y, w, h]            sol-üst köşe + boyut, MUTLAK piksel
    VOC  : xmin, ymin, xmax, ymax  iki köşe,            MUTLAK piksel
    YOLO : cx, cy, w, h            merkez + boyut,      NORMALİZE (0-1)

Dönüşümde bir işaret ya da bölme hatası kutuları sessizce kaydırır; etiket
dosyası geçerli görünür ama nesneler yanlış yerdedir. Bu test dönüşümü elde
hesaplanmış değerlerle karşılaştırır.

    python testler/test_ice_aktar.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, gecici, sil, Rapor   # noqa: E402

yolu_kur()

import numpy as np                                              # noqa: E402
import cv2                                                      # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox           # noqa: E402

from boxify.araclar.veri_ice_aktar import (                     # noqa: E402
    coco_oku, voc_oku, bicim_tahmin, AktarIscisi,
)

W, H = 200, 100          # test görselinin boyutu — hesapları kolaylaştırsın


def gorsel_yaz(klasor, ad):
    os.makedirs(klasor, exist_ok=True)
    cv2.imwrite(os.path.join(klasor, ad),
                np.full((H, W, 3), 128, dtype=np.uint8))


def etiketleri_oku(out):
    sonuc = {}
    lbl = os.path.join(out, "labels")
    for ad in sorted(os.listdir(lbl)):
        with open(os.path.join(lbl, ad), encoding="utf-8") as f:
            sonuc[ad] = [ln.split() for ln in f.read().splitlines() if ln.strip()]
    return sonuc


def aktar(app, kayitlar, hedef, esleme, out, **kw):
    cfg = {"kayitlar": kayitlar, "hedef_adlar": hedef, "esleme": esleme,
           "out_dir": out, "mode": "copy", "isaretli_atla": kw.get("isaretli_atla", True),
           "bos_atla": kw.get("bos_atla", False)}
    w = AktarIscisi(cfg)
    bitti = {}
    w.done.connect(lambda r: bitti.update(r))
    w.start()
    import time
    t0 = time.time()
    while w.isRunning() and time.time() - t0 < 60:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return bitti


def main() -> int:
    r = Rapor("COCO / VOC içe aktarma")
    app = QApplication.instance() or QApplication([])
    for ad in ("warning", "critical", "information", "question"):
        setattr(QMessageBox, ad, staticmethod(
            lambda p, t, x="", *a, **k: QMessageBox.Yes))

    kok = gecici("aktar")
    try:
        img_dir = os.path.join(kok, "gorseller")
        gorsel_yaz(img_dir, "a.jpg")
        gorsel_yaz(img_dir, "b.jpg")

        # ── COCO ────────────────────────────────────────────────────────
        # a.jpg: kutu (x=50, y=25, w=100, h=50) → merkez (100, 50) = (0.5, 0.5)
        #        normalize boyut (100/200, 50/100) = (0.5, 0.5)
        coco = {
            "images": [{"id": 1, "file_name": "a.jpg", "width": W, "height": H},
                       {"id": 2, "file_name": "b.jpg", "width": W, "height": H}],
            "categories": [{"id": 7, "name": "kamyon"}, {"id": 9, "name": "tir"}],
            "annotations": [
                {"id": 1, "image_id": 1, "category_id": 7,
                 "bbox": [50, 25, 100, 50], "iscrowd": 0},
                {"id": 2, "image_id": 2, "category_id": 9,
                 "bbox": [0, 0, 40, 20], "iscrowd": 0},
                {"id": 3, "image_id": 2, "category_id": 7,
                 "bbox": [10, 10, 20, 20], "iscrowd": 1},     # atlanmalı
                {"id": 4, "image_id": 1, "category_id": 9,
                 "bbox": [180, 80, 60, 60], "iscrowd": 0},    # taşıyor → kırpılmalı
            ],
        }
        cjson = os.path.join(kok, "instances.json")
        with open(cjson, "w", encoding="utf-8") as f:
            json.dump(coco, f)

        r.kontrol(bicim_tahmin(cjson) == "coco", "COCO biçimi tanınıyor")
        v = coco_oku(cjson, img_dir)
        r.kontrol(not v["hata"], "COCO okundu", v.get("hata", ""))
        r.kontrol(v["siniflar"] == {7: "kamyon", 9: "tir"},
                  "COCO sınıfları okundu", str(v["siniflar"]))

        out = os.path.join(kok, "cikti_coco")
        s = aktar(app, v["kayitlar"], ["kamyon", "tir"], {7: 0, 9: 1}, out)
        etiket = etiketleri_oku(out)
        r.bilgi(f"yazılan: {list(etiket)}")

        a = etiket.get("a.txt", [])
        merkez = next((x for x in a if x[0] == "0"), None)
        r.kontrol(merkez is not None and
                  abs(float(merkez[1]) - 0.5) < 1e-4 and
                  abs(float(merkez[2]) - 0.5) < 1e-4 and
                  abs(float(merkez[3]) - 0.5) < 1e-4 and
                  abs(float(merkez[4]) - 0.5) < 1e-4,
                  "COCO kutusu doğru normalize edildi (0.5 0.5 0.5 0.5)",
                  str(merkez))

        # taşan kutu: (180,80)-(240,140) → kırpılıp (180,80)-(200,100)
        # merkez (190,90) → (0.95, 0.90), boyut (20/200, 20/100) = (0.1, 0.2)
        tasan = next((x for x in a if x[0] == "1"), None)
        r.kontrol(tasan is not None and
                  abs(float(tasan[1]) - 0.95) < 1e-4 and
                  abs(float(tasan[2]) - 0.90) < 1e-4 and
                  abs(float(tasan[3]) - 0.10) < 1e-4 and
                  abs(float(tasan[4]) - 0.20) < 1e-4,
                  "sınır dışına taşan kutu kırpıldı", str(tasan))
        r.kontrol(s["sayac"]["kirpilan"] == 1, "kırpılan kutu sayıldı",
                  str(s["sayac"]))
        r.kontrol(s["sayac"]["kalabalik"] == 1, "iscrowd kutusu atlandı",
                  str(s["sayac"]))
        r.kontrol(all(x[0] != "0" for x in etiket.get("b.txt", [])),
                  "iscrowd kutusu etikete yazılmadı")

        # ── sınıf eşleme: 'tir' atlansın ────────────────────────────────
        out2 = os.path.join(kok, "cikti_atla")
        aktar(app, v["kayitlar"], ["kamyon"], {7: 0, 9: None}, out2)
        e2 = etiketleri_oku(out2)
        r.kontrol(all(x[0] == "0" for satirlar in e2.values() for x in satirlar),
                  "'(atla)' seçilen sınıfın kutuları düştü", str(e2))

        # ── VOC ─────────────────────────────────────────────────────────
        voc_dir = os.path.join(kok, "voc")
        os.makedirs(voc_dir)
        with open(os.path.join(voc_dir, "a.xml"), "w", encoding="utf-8") as f:
            f.write(f"""<annotation>
  <filename>a.jpg</filename>
  <size><width>{W}</width><height>{H}</height><depth>3</depth></size>
  <object><name>dorse</name><difficult>0</difficult>
    <bndbox><xmin>50</xmin><ymin>25</ymin><xmax>150</xmax><ymax>75</ymax></bndbox>
  </object>
  <object><name>kamyon</name><difficult>1</difficult>
    <bndbox><xmin>0</xmin><ymin>0</ymin><xmax>20</xmax><ymax>20</ymax></bndbox>
  </object>
</annotation>""")
        r.kontrol(bicim_tahmin(voc_dir) == "voc", "VOC biçimi tanınıyor")
        vv = voc_oku(voc_dir, img_dir)
        r.kontrol(not vv["hata"], "VOC okundu", vv.get("hata", ""))
        r.kontrol(set(vv["siniflar"].values()) == {"dorse", "kamyon"},
                  "VOC sınıfları okundu", str(vv["siniflar"]))

        out3 = os.path.join(kok, "cikti_voc")
        adlar = [vv["siniflar"][i] for i in sorted(vv["siniflar"])]
        s3 = aktar(app, vv["kayitlar"], adlar,
                   {i: i for i in vv["siniflar"]}, out3)
        e3 = etiketleri_oku(out3)
        # (50,25)-(150,75) → merkez (100,50)=(0.5,0.5), boyut (100/200,50/100)
        satir = e3.get("a.txt", [[]])[0]
        r.kontrol(len(satir) == 5 and
                  abs(float(satir[1]) - 0.5) < 1e-4 and
                  abs(float(satir[2]) - 0.5) < 1e-4 and
                  abs(float(satir[3]) - 0.5) < 1e-4 and
                  abs(float(satir[4]) - 0.5) < 1e-4,
                  "VOC köşe kutusu doğru çevrildi", str(satir))
        r.kontrol(s3["sayac"]["kalabalik"] == 1, "difficult kutusu atlandı",
                  str(s3["sayac"]))

        # ── bozuk girdi çökertmemeli ────────────────────────────────────
        bos = os.path.join(kok, "bos.json")
        with open(bos, "w") as f:
            f.write("{}")
        r.kontrol(bool(coco_oku(bos, img_dir).get("hata")),
                  "COCO olmayan JSON anlaşılır hata veriyor")
        with open(bos, "w") as f:
            f.write("{ bozuk json")
        r.kontrol(bool(coco_oku(bos, img_dir).get("hata")),
                  "bozuk JSON çökertmiyor")
        r.kontrol(bool(voc_oku(os.path.join(kok, "gorseller"), img_dir).get("hata")),
                  "XML'siz klasör anlaşılır hata veriyor")

        # görsel yoksa: kayıt atlanır, süreç devam eder
        eksik = [{"gorsel": os.path.join(img_dir, "yok.jpg"), "w": W, "h": H,
                  "kutular": [(7, 10, 10, 20, 20, False)]}]
        s4 = aktar(app, eksik, ["kamyon"], {7: 0}, os.path.join(kok, "cikti_eksik"))
        r.kontrol(s4["sayac"]["gorsel_yok"] == 1 and s4["sayac"]["gorsel"] == 0,
                  "bulunamayan görsel sayılıp atlanıyor", str(s4["sayac"]))

        # üstveride boyut yoksa diskten okunmalı
        boyutsuz = [{"gorsel": os.path.join(img_dir, "a.jpg"), "w": 0, "h": 0,
                     "kutular": [(7, 50, 25, 100, 50, False)]}]
        out5 = os.path.join(kok, "cikti_boyutsuz")
        aktar(app, boyutsuz, ["kamyon"], {7: 0}, out5)
        e5 = etiketleri_oku(out5).get("a.txt", [[]])[0]
        r.kontrol(len(e5) == 5 and abs(float(e5[3]) - 0.5) < 1e-4,
                  "boyut üstveride yoksa görselden okunuyor", str(e5))

        # data.yaml
        yaml_yolu = os.path.join(out, "data.yaml")
        icerik = open(yaml_yolu, encoding="utf-8").read()
        r.kontrol("nc: 2" in icerik and "0: kamyon" in icerik,
                  "data.yaml yazıldı", icerik.replace("\n", " ")[:70])
    finally:
        sil(kok)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
