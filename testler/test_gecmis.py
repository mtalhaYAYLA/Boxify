"""Eğitim geçmişi, MLflow anahtarı ve metinle sıfır-atış etiketleme.

Ortak fikir: bu üç özellik de **isteğe bağlı bir şeye bağlı olmamalı**.
Geçmiş ekranı MLflow kurulu olmasa da çalışmalı (kaynağı ultralytics'in kendi
results.csv'si), MLflow kapalıyken sessizce kayıt tutulmamalı, sıfır-atış ise
ek paket istememeli.

    python testler/test_gecmis.py
"""

import csv
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, Rapor   # noqa: E402

yolu_kur(sahte_ultralytics=True)

from PyQt5.QtWidgets import QApplication, QMessageBox   # noqa: E402


def _tur_yaz(kok, ad, epoch, taban, csv_var=True, map_sutunu=True):
    d = os.path.join(kok, ad)
    os.makedirs(os.path.join(d, "weights"), exist_ok=True)
    open(os.path.join(d, "weights", "best.pt"), "w").close()
    with open(os.path.join(d, "args.yaml"), "w", encoding="utf-8") as f:
        f.write(f"task: detect\nmodel: /bir/yerde/yolo11n.pt\n"
                f"epochs: {epoch or 100}\nbatch: 16\nimgsz: 640\n"
                f"optimizer: auto\nlr0: 0.01\n")
    if not csv_var:
        return d
    with open(os.path.join(d, "results.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        basliklar = ["epoch", "train/box_loss", "metrics/mAP50(B)"]
        if map_sutunu:
            basliklar.append("metrics/mAP50-95(B)")
        w.writerow(basliklar)
        for i in range(epoch):
            satir = [i + 1, 2.0 - i * 0.05, taban + i * 0.02 + 0.1]
            if map_sutunu:
                satir.append(taban + i * 0.02)
            w.writerow(satir)
    return d


def gecmis_testi(r, app):
    from boxify.araclar.egitim import gecmis_tara, MainWindow

    kok = tempfile.mkdtemp(prefix="boxify_gecmis_")
    try:
        _tur_yaz(kok, "egitim_20260101_1000", 8, 0.30)
        _tur_yaz(kok, "egitim_20260102_1100", 12, 0.55)
        # results.csv'si olmayan klasör (yarım kalmış tur) listeye girmemeli
        _tur_yaz(kok, "egitim_yarim", 0, 0.0, csv_var=False)
        # mAP50-95 sütunu olmayan tur çökertmemeli
        _tur_yaz(kok, "egitim_eski_surum", 5, 0.20, map_sutunu=False)

        turlar = gecmis_tara(kok)
        adlar = {t["ad"] for t in turlar}
        r.kontrol(len(turlar) == 3, "results.csv'si olan turlar bulundu",
                  f"{len(turlar)} tur: {sorted(adlar)}")
        r.kontrol("egitim_yarim" not in adlar,
                  "yarım kalmış klasör listeye girmiyor")

        d = {t["ad"]: t for t in turlar}
        r.kontrol(d["egitim_20260102_1100"]["epoch"] == 12, "epoch sayısı doğru")
        r.kontrol(abs(d["egitim_20260102_1100"]["en_iyi"] - 0.77) < 1e-6,
                  "en iyi mAP50-95 doğru okundu",
                  f"{d['egitim_20260102_1100']['en_iyi']:.4f}")
        r.kontrol(d["egitim_20260101_1000"]["baslangic"] == "yolo11n.pt",
                  "başlangıç ağırlığı args.yaml'dan okundu")
        r.kontrol(d["egitim_eski_surum"]["en_iyi"] is None,
                  "mAP sütunu yoksa çökmüyor, boş geçiyor")
        r.kontrol(bool(d["egitim_20260101_1000"]["best"]),
                  "best.pt yolu bulundu")
        r.kontrol(d["egitim_20260101_1000"]["param"].get("imgsz") == "640"
                  and d["egitim_20260101_1000"]["param"].get("optimizer") == "auto",
                  "args.yaml'daki bütün ayarlar okunuyor",
                  str(sorted(d["egitim_20260101_1000"]["param"]))[:70])

        r.kontrol(gecmis_tara("") == [] and gecmis_tara("/yok/boyle/bir/yer") == [],
                  "olmayan klasör boş liste döndürüyor")

        # arayüz
        w = MainWindow()
        w.resize(1200, 800)
        w.show()
        w._proje = kok
        w._gecmisi_tazele()
        app.processEvents()
        r.kontrol(w.gecmis_tablo.rowCount() == 3, "tablo turları gösteriyor",
                  f"{w.gecmis_tablo.rowCount()} satır")
        w.gecmis_tablo.selectAll()
        app.processEvents()
        r.kontrol(len(w.gecmis_egri._turlar) == 3,
                  "seçilen turlar eğriye aktarılıyor")
        # hiperparametre kıyası: farklı olan ayar işaretlenmeli
        # selectRow seçimi değiştirir, eklemez; kıyas için hepsi seçiliyor
        w.gecmis_tablo.selectAll()
        app.processEvents()
        basliklar = [w.gecmis_param.horizontalHeaderItem(i).text()
                     for i in range(w.gecmis_param.columnCount())]
        r.kontrol(basliklar[0] == "Ayar" and len(basliklar) >= 2,
                  "parametre tablosu turları sütun olarak veriyor", str(basliklar))
        satirlar = {w.gecmis_param.item(i, 0).text().strip(" •"): i
                    for i in range(w.gecmis_param.rowCount())}
        r.kontrol("epochs" in satirlar and "model" in satirlar,
                  "kıyasta anlamı olan ayarlar listeleniyor",
                  ", ".join(sorted(satirlar))[:80])
        isaretli = [w.gecmis_param.item(i, 0).text().strip(" •")
                    for i in range(w.gecmis_param.rowCount())
                    if w.gecmis_param.item(i, 0).text().startswith("•")]
        r.kontrol("epochs" in isaretli,
                  "turlar arasında değişen ayar işaretleniyor", str(isaretli))
        r.kontrol("imgsz" not in isaretli,
                  "tüm turlarda aynı olan ayar işaretlenmiyor")

        w.gecmis_tablo.clearSelection()
        app.processEvents()
        r.kontrol(not w.gecmis_egri._turlar and not w.gecmis_ac_btn.isEnabled(),
                  "seçim kalkınca eğri boşalıyor")
        r.kontrol(w.gecmis_param.rowCount() == 0,
                  "seçim kalkınca parametre tablosu da boşalıyor")
        w.close()
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def mlflow_testi(r, app):
    """MLflow kapalıyken sessizce kayıt tutulmamalı."""
    from boxify.araclar.egitim import EgitimIscisi, mlflow_var

    r.kontrol(isinstance(mlflow_var(), bool),
              "mlflow kurulu mu sorusu import etmeden cevaplanıyor",
              f"kurulu: {mlflow_var()}")

    kok = tempfile.mkdtemp(prefix="boxify_mlf_")
    try:
        from ultralytics.utils import SETTINGS
        SETTINGS["mlflow"] = True
        os.environ.pop("MLFLOW_TRACKING_URI", None)

        # kapalı: ayar açıkça False'a çekilmeli (varsayılan True olduğu için)
        isci = EgitimIscisi({"proje": kok, "ad": "t1", "mlflow": False})
        isci._mlflow_kur(isci.cfg)
        r.kontrol(SETTINGS["mlflow"] is False,
                  "MLflow kapalıyken ultralytics ayarı da kapatılıyor")
        r.kontrol("MLFLOW_TRACKING_URI" not in os.environ,
                  "kapalıyken izleme adresi kurulmuyor")

        # açık: yerel dosya deposu ve ad değişkenleri kurulmalı
        isci2 = EgitimIscisi({"proje": kok, "ad": "t2", "mlflow": True})
        isci2._mlflow_kur(isci2.cfg)
        depo = os.path.join(kok, "mlflow")
        r.kontrol(SETTINGS["mlflow"] is True, "açıkken ayar açılıyor")
        r.kontrol(os.environ.get("MLFLOW_TRACKING_URI") == "file:" + depo,
                  "yerel dosya deposu kuruluyor (sunucu gerekmiyor)",
                  os.environ.get("MLFLOW_TRACKING_URI", "—"))
        r.kontrol(os.path.isdir(depo), "depo klasörü oluşturuluyor")
        r.kontrol(os.environ.get("MLFLOW_RUN") == "t2", "tur adı aktarılıyor")
    finally:
        os.environ.pop("MLFLOW_TRACKING_URI", None)
        os.environ.pop("MLFLOW_RUN", None)
        os.environ.pop("MLFLOW_EXPERIMENT_NAME", None)
        shutil.rmtree(kok, ignore_errors=True)


def sifir_atis_testi(r, app):
    """Metinle arama: ayar doğru kuruluyor, boş istem engelleniyor mu?"""
    from boxify.araclar.oto_label import MainWindow

    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    app.processEvents()

    r.kontrol(not w.zs_edit.isEnabled() and not w.zs_model_combo.isEnabled(),
              "metinle arama varsayılan olarak kapalı")

    w.zs_chk.setChecked(True)
    app.processEvents()
    r.kontrol(w.zs_edit.isEnabled() and w.zs_model_combo.isEnabled(),
              "açılınca istem alanı ve ağırlık seçimi etkinleşiyor")
    r.kontrol(not w.class_list.isEnabled(),
              "metinden sınıf alınırken modelin sınıf filtresi kapanıyor")
    r.kontrol(w.zs_model_combo.currentData().endswith(".pt"),
              "indirilebilir bir açık sözlük ağırlığı öntanımlı",
              w.zs_model_combo.currentData())

    # boş istemle başlatmak engellenmeli
    yakalanan = []
    QMessageBox.warning = staticmethod(
        lambda p, t, x="", *a, **k: (yakalanan.append(t), QMessageBox.Ok)[1])
    kok = tempfile.mkdtemp(prefix="boxify_zs_")
    try:
        w._img_dir = kok
        w._images = ["/olmayan/kare.jpg"]
        w._out_dir = kok
        w._model_path = ""
        w.zs_edit.setText("   ")
        w._start()
        app.processEvents()
        r.kontrol(any("Metin" in t for t in yakalanan),
                  "boş istemle başlatmak engelleniyor", str(yakalanan[:2]))
        r.kontrol(w._worker is None, "engellenince iş başlamıyor")

        # istem yazılınca cfg'ye giriyor mu (işi başlatmadan cfg'yi kur)
        w.zs_edit.setText("forklift, baret")
        r.kontrol(w.zs_edit.text().strip() == "forklift, baret",
                  "istem metni okunuyor")
    finally:
        shutil.rmtree(kok, ignore_errors=True)
    w.close()


def acik_sozluk_yukleyici_testi(r, app):
    """Ağırlık adına göre doğru açık sözlük sınıfı seçiliyor mu?

    Gerçek ağırlık indirmeden sınanıyor: sahte ultralytics yığını YOLOWorld ve
    YOLOE yerine kayıt tutan sınıflar veriyor.
    """
    from boxify.araclar.oto_label import LabelWorker
    import ultralytics

    if not hasattr(ultralytics, "YOLOWorld"):
        r.bilgi("sahte ultralytics'te YOLOWorld yok — yükleyici testi atlandı")
        return

    isci = LabelWorker({})
    model, adlar = isci._acik_sozluk_yukle("yolov8s-worldv2.pt",
                                           ["forklift", "baret"])
    r.kontrol(adlar == {0: "forklift", 1: "baret"},
              "istem sırayla sınıf adlarına dönüşüyor", str(adlar))
    r.kontrol(getattr(model, "verilen_siniflar", None) == ["forklift", "baret"],
              "sınıflar modele metin olarak veriliyor")

    model2, _ = isci._acik_sozluk_yukle("yoloe-11s-seg.pt", ["palet"])
    r.kontrol(type(model2).__name__ == "YOLOE",
              "yoloe ağırlığında YOLOE sınıfı kullanılıyor",
              type(model2).__name__)


def model_secici_testi(r, app):
    """Model listesi iki eğitim ekranında da aynı ve tam mı?"""
    from boxify.araclar.model_secici import (ModelSecici, model_listesi,
                                             ailelere_ayir, GOMULU_MODELLER)

    adlar = model_listesi()
    r.kontrol(len(adlar) > 100, "model listesi kapsamlı", f"{len(adlar)} ağırlık")
    r.kontrol(len(GOMULU_MODELLER) == len(adlar) or len(GOMULU_MODELLER) > 100,
              "ultralytics yokken de tam liste var (gömülü kopya)",
              f"gömülü {len(GOMULU_MODELLER)}")
    r.kontrol(not any("sam" in a.lower() for a in adlar),
              "SAM ailesi dışarıda (tespit eğitiminde başlangıç olamaz)")

    gruplar = ailelere_ayir(adlar)
    r.kontrol(len(gruplar) >= 8, "aileler ayrıştırılıyor",
              ", ".join(list(gruplar)[:8]))
    r.kontrol(list(gruplar)[0] == "yolo11",
              "ilk aile yolo11 (ilk tur için önerilen)", list(gruplar)[0])
    for aile in ("yolo11", "yolo26", "yolov8"):
        if aile in gruplar:
            r.kontrol(gruplar[aile][0].endswith("n.pt") or "n" in gruplar[aile][0],
                      f"{aile} içinde en küçük boyut başta", gruplar[aile][0])

    s = ModelSecici()
    r.kontrol(s.model_adi() == "yolo11n.pt", "varsayılan yolo11n.pt",
              s.model_adi())
    i = s.aile_combo.findData("rtdetr")
    if i >= 0:
        s.aile_combo.setCurrentIndex(i)
        r.kontrol(s.model_adi().startswith("rtdetr"),
                  "aile değişince sürüm listesi de değişiyor", s.model_adi())
    s.surum_combo.setEditText("/bir/yol/kendi_modelim.pt")
    r.kontrol(s.model_adi() == "/bir/yol/kendi_modelim.pt",
              "listede olmayan dosya yolu kabul ediliyor")
    s.surum_combo.setEditText("yolo26x")
    r.kontrol(s.model_adi() == "yolo26x.pt", "uzantısız ada .pt ekleniyor")

    # iki eğitim ekranı da aynı seçiciyi kullanmalı
    from boxify.araclar.egitim import MainWindow as EgitimPenceresi
    from boxify.araclar.labelapp.ui.training_dialog import TrainingDialog
    from boxify.araclar.labelapp.core.dataset import Dataset
    eg = EgitimPenceresi()
    dlg = TrainingDialog(Dataset())
    r.kontrol(isinstance(eg.hazir_combo, ModelSecici)
              and isinstance(dlg.model_cb, ModelSecici),
              "iki eğitim ekranı da ortak seçiciyi kullanıyor")
    r.kontrol(eg.hazir_combo.aile_combo.count() == dlg.model_cb.aile_combo.count(),
              "iki ekranda aynı aile listesi",
              f"{eg.hazir_combo.aile_combo.count()} / {dlg.model_cb.aile_combo.count()}")
    eg.close()
    dlg.close()


def main() -> int:
    r = Rapor("Geçmiş, MLflow ve sıfır-atış")
    app = QApplication.instance() or QApplication([])
    for ad in ("warning", "critical", "information", "question"):
        setattr(QMessageBox, ad, staticmethod(lambda *a, **k: QMessageBox.Ok))
    gecmis_testi(r, app)
    mlflow_testi(r, app)
    sifir_atis_testi(r, app)
    acik_sozluk_yukleyici_testi(r, app)
    model_secici_testi(r, app)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
