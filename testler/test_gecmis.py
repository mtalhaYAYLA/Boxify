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
        # SQLite: dosya tabanlı depo MLflow 3.x'te bakım modunda ve kayıt
        # açmaya çalışınca istisna fırlatıyor.
        r.kontrol(os.environ.get("MLFLOW_TRACKING_URI", "").startswith("sqlite:///")
                  and depo in os.environ.get("MLFLOW_TRACKING_URI", ""),
                  "yerel SQLite deposu kuruluyor (sunucu gerekmiyor)",
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


def mlflow_yayilim_testi(r, app):
    """Ölçüm üreten dört aracın hepsinde kayıt var mı, ve gerçekten yazıyor mu?"""
    from boxify.araclar.mlflow_kayit import (kaydet, mlflow_var, depo_yolu,
                                             izleme_adresi, onay_kutusu)

    # 1) Kutu her araçta olmalı
    import importlib
    eksik = []
    for modul in ("model_karsilastir", "hata_analizi", "model_export", "egitim"):
        m = importlib.import_module(f"boxify.araclar.{modul}")
        w = m.MainWindow()
        if getattr(w, "mlflow_chk", None) is None:
            eksik.append(modul)
        w.close()
    r.kontrol(not eksik, "ölçüm üreten dört araçta da MLflow kutusu var",
              "eksik: " + ", ".join(eksik) if eksik else "hepsi tamam")

    kutu = onay_kutusu()
    r.kontrol(kutu.isEnabled() == mlflow_var(),
              "mlflow yoksa kutu kapalı, varsa açık",
              f"mlflow kurulu: {mlflow_var()}")
    r.kontrol(not kutu.isChecked(),
              "kutu varsayılan kapalı — sessiz kayıt yok")

    # 2) Depo adresi SQLite olmalı (dosya deposu MLflow 3.x'te bakım modunda)
    kok = tempfile.mkdtemp(prefix="boxify_mlf2_")
    try:
        r.kontrol(izleme_adresi(kok).startswith("sqlite:///"),
                  "depo SQLite (file: deposu 3.x'te istisna fırlatıyor)",
                  izleme_adresi(kok))

        # 3) Gerçekten yazıp geri okunabiliyor mu
        notu = kaydet(kok, "boxify-test", "tur_1",
                      parametreler={"model": "yolo11n.pt"},
                      metrikler={"fps": 31.5, "tp": 12, "sinif/person": 4},
                      etiketler={"arac": "test"})
        if not mlflow_var():
            r.kontrol(notu == "", "mlflow yokken sessizce atlanıyor")
            r.bilgi("mlflow kurulu değil — yazma turu atlandı")
            return
        r.kontrol("kaydedildi" in notu, "kayıt başarılı", notu[:70])
        r.kontrol(os.path.exists(os.path.join(depo_yolu(kok), "mlflow.db")),
                  "SQLite deposu oluşuyor")

        import mlflow
        mlflow.set_tracking_uri(izleme_adresi(kok))
        turlar = mlflow.search_runs(experiment_names=["boxify-test"])
        r.kontrol(len(turlar) == 1, "yazılan tur geri okunuyor", f"{len(turlar)} tur")
        r.kontrol(abs(float(turlar["metrics.fps"][0]) - 31.5) < 1e-6,
                  "metrikler doğru kaydediliyor")
        r.kontrol("metrics.sinif/person" in turlar.columns,
                  "sınıf bazlı metrikler de yazılıyor")

        # 4) Hata hâlinde araç düşmemeli
        notu2 = kaydet("/erisilemeyen/\x00/yol", "boxify-test", "t2",
                       metrikler={"x": 1})
        r.kontrol(isinstance(notu2, str),
                  "yazılamadığında istisna değil, açıklama dönüyor", notu2[:60])
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def kararlilik_testi(r, app):
    """Hız ölçümünün kuyruk ve sürüklenme ölçüleri doğru mu?

    Bu ölçüler kendi jetson_test_pack deposundaki yöntemden alındı: pasif
    soğutmalı kartlarda sorun ortalamada değil, arada gelen sivrilmelerde ve
    ısındıkça yavaşlamada çıkıyor.
    """
    from boxify.araclar.model_export import kararlilik, yuzdelik

    r.kontrol(yuzdelik([], 95) == 0.0 and kararlilik([]) == {},
              "boş ölçüm çökertmiyor")
    r.kontrol(abs(yuzdelik([1, 2, 3, 4, 5], 50) - 3.0) < 1e-9,
              "yüzdelik medyanı doğru veriyor")
    r.kontrol(abs(yuzdelik([1, 2, 3, 4, 5], 100) - 5.0) < 1e-9,
              "en üst yüzdelik en büyük değer")

    # sabit hızlı cihaz: sürüklenme ~0, sivrilme yok
    sabit = [10.0 + (i % 3) * 0.1 for i in range(300)]
    k = kararlilik(sabit)
    r.kontrol(abs(k["suruklenme"]) < 2.0,
              "kararlı cihazda sürüklenme yok", f"%{k['suruklenme']:.1f}")
    r.kontrol(k["sivrilme"] == 0, "kararlı cihazda sivrilme yok")

    # ısınan cihaz: süre zamanla artıyor + iki sivrilme
    isinan = [10.0 + i * 0.03 for i in range(300)]
    isinan[50] = 45.0
    isinan[180] = 60.0
    k2 = kararlilik(isinan)
    r.kontrol(k2["suruklenme"] > 15.0,
              "ısınan cihazda sürüklenme yakalanıyor", f"%{k2['suruklenme']:.1f}")
    r.kontrol(k2["sivrilme"] == 2, "sivrilmeler sayılıyor", str(k2["sivrilme"]))
    r.kontrol(k2["en_kotu"] == 60.0, "en kötü kare bildiriliyor")
    r.kontrol(len(k2["pencereler"]) == 6 and
              k2["pencereler"][-1] > k2["pencereler"][0],
              "pencereler zaman sırasında ve yavaşlamayı gösteriyor")
    r.kontrol(k2["p99"] < k2["en_kotu"],
              "p99 en kötüden küçük (kuyruk ayrıştırılıyor)")

    # "sapma" adı dönüşüm sapmasına ait; standart sapma ayrı anahtarda olmalı
    r.kontrol("sapma" not in k2 and "standart_sapma" in k2,
              "standart sapma dönüşüm sapmasıyla çakışmıyor")


def dayaniklilik_olcum_testi(r, app):
    """Uzun koşu değerlendirmesi: sızıntı, ısınma ve yavaşlama yakalanıyor mu?

    Ölçüt kümesi jetson_test_pack/freeze_diag'dan alındı. Buradaki asıl
    tasarım kararı şu: okunamayan bir eksen GEÇTİ değil UYARI sayılıyor —
    ölçemediğini geçmiş saymak raporu olduğundan güvenli gösterir.
    """
    from boxify.araclar import dayaniklilik as dyn

    ram, takas = dyn.bellek_ornegi()
    r.kontrol(ram is not None and ram > 0,
              "bellek üç işletim sisteminde de okunabiliyor",
              f"{ram:.0f} MB kullanılabilir" if ram else "okunamadı")
    r.kontrol(takas is None or takas >= 0, "takas değeri anlamlı",
              f"{takas:.0f} MB" if takas is not None else "yok")
    r.kontrol(dyn.sicaklik_c() is None or 0 < dyn.sicaklik_c() < 150,
              "sıcaklık ya okunuyor ya da None (uydurulmuyor)")

    ornek = dyn.saglik_ornegi(1.0, 12.3)
    r.kontrol(set(ornek) == {"t_sn", "ram_mb", "takas_mb", "sicaklik_c", "gecikme_ms"},
              "sağlık örneği beklenen alanları taşıyor")

    def kosu(ram_dusus=0, gecikme_artis=0.0, sicaklik=None, n=12):
        return [{"t_sn": i * 5, "ram_mb": 4000 - i * ram_dusus, "takas_mb": 10.0,
                 "sicaklik_c": sicaklik, "gecikme_ms": 10.0 + i * gecikme_artis}
                for i in range(n)]

    def eksen(sonuc, ad):
        return next((d for e, d, _a in sonuc if e == ad), None)

    saglikli = dyn.degerlendir(kosu(), 0)
    r.kontrol(eksen(saglikli, "bellek sızıntısı") == dyn.GECER,
              "sabit bellekte sızıntı raporlanmıyor")
    r.kontrol(eksen(saglikli, "hız sürüklenmesi") == dyn.GECER,
              "sabit hızda sürüklenme raporlanmıyor")
    r.kontrol(eksen(saglikli, "sıcaklık") == dyn.UYARI,
              "okunamayan sensör GEÇTİ değil UYARI")

    sizan = dyn.degerlendir(kosu(ram_dusus=80), 0)
    r.kontrol(eksen(sizan, "bellek sızıntısı") == dyn.KALDI,
              "bellek düşüşü sızıntı olarak yakalanıyor")

    yavaslayan = dyn.degerlendir(kosu(gecikme_artis=1.5), 0)
    r.kontrol(eksen(yavaslayan, "hız sürüklenmesi") == dyn.KALDI,
              "koşu boyunca yavaşlama yakalanıyor")

    sicak = dyn.degerlendir(kosu(sicaklik=95.0), 0)
    r.kontrol(eksen(sicak, "sıcaklık") == dyn.KALDI, "aşırı sıcaklık yakalanıyor")

    hatali = dyn.degerlendir(kosu(), 4, "CUDA error")
    r.kontrol(eksen(hatali, "çıkarım hataları") == dyn.KALDI,
              "arada gelen çıkarım hataları raporlanıyor")
    r.kontrol(dyn.ozet_durum(hatali) == dyn.KALDI,
              "tek bir KALDI özeti KALDI yapıyor")
    r.kontrol(dyn.ozet_durum(saglikli) == dyn.UYARI,
              "sensör okunamayınca özet GEÇTİ değil UYARI")

    r.kontrol(dyn.degerlendir([], 0)[0][1] == dyn.UYARI,
              "örnek yoksa geçmiş sayılmıyor")

    kok = tempfile.mkdtemp(prefix="boxify_soak_")
    try:
        yol = dyn.csv_yaz(os.path.join(kok, "alt", "saglik.csv"), kosu())
        r.kontrol(bool(yol) and os.path.exists(yol),
                  "sağlık örnekleri CSV olarak yazılıyor")
        with open(yol, encoding="utf-8") as f:
            r.kontrol(len(f.read().strip().splitlines()) == 13,
                      "CSV başlık + bütün örnekleri içeriyor")
    finally:
        shutil.rmtree(kok, ignore_errors=True)

    # araçtaki alan
    from boxify.araclar.model_export import MainWindow
    w = MainWindow()
    r.kontrol(getattr(w, "soak_spin", None) is not None
              and w.soak_spin.value() == 0,
              "Model Export'ta dayanıklılık alanı var ve varsayılan kapalı")
    w.close()


def roi_testi(r, app):
    """İlgi alanı: geometri, kalıcılık ve Oto Label süzgeci."""
    from boxify.araclar import roi as R
    from PyQt5.QtGui import QPixmap

    kare = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    r.kontrol(R.icinde_mi([kare], 0.5, 0.5), "poligon içindeki nokta bulunuyor")
    r.kontrol(not R.icinde_mi([kare], 0.05, 0.05), "dışardaki nokta eleniyor")
    r.kontrol(R.icinde_mi([], 0.01, 0.99),
              "ROI yokken kısıt uygulanmıyor (bütün kare geçerli)")

    ucgen = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    r.kontrol(R.nokta_icinde(ucgen, 0.2, 0.2) and not R.nokta_icinde(ucgen, 0.9, 0.9),
              "dikdörtgen olmayan poligon da doğru çalışıyor")
    r.kontrol(not R.nokta_icinde([(0, 0), (1, 1)], 0.5, 0.5),
              "üç noktadan az poligon geçersiz")

    iki = [kare, [(0.0, 0.9), (0.1, 0.9), (0.1, 1.0), (0.0, 1.0)]]
    r.kontrol(R.icinde_mi(iki, 0.05, 0.95),
              "birden çok bölgeden herhangi biri yeterli")

    # piksel kutusu → merkez ölçütü
    r.kontrol(R.kutu_gecerli([kare], (300, 300, 500, 500), 1000, 1000),
              "merkezi içeride olan kutu geçiyor")
    r.kontrol(not R.kutu_gecerli([kare], (0, 0, 100, 100), 1000, 1000),
              "merkezi dışarıda olan kutu eleniyor")

    kok = tempfile.mkdtemp(prefix="boxify_roi_")
    try:
        yol = R.kaydet(kok, [kare])
        r.kontrol(bool(yol) and os.path.exists(yol), "ROI diske yazılıyor")
        geri = R.yukle(kok)
        r.kontrol(len(geri) == 1 and len(geri[0]) == 4,
                  "ROI geri okunuyor", R.ozet(geri))
        with open(os.path.join(kok, "roi.json"), "w") as f:
            f.write("{bozuk")
        r.kontrol(R.yukle(kok) == [],
                  "bozuk ROI dosyası çökertmiyor, kısıtsız sayılıyor")
        r.kontrol(R.yukle(tempfile.mkdtemp()) == [], "ROI yoksa boş liste")
    finally:
        shutil.rmtree(kok, ignore_errors=True)

    # Oto Label bağlantısı
    from boxify.araclar.oto_label import MainWindow
    from boxify.araclar.roi_dialog import RoiDialog
    w = MainWindow()
    w.show()
    r.kontrol(getattr(w, "roi_chk", None) is not None and not w.roi_chk.isChecked(),
              "Oto Label'da ROI kutusu var ve varsayılan kapalı")
    r.kontrol(w._roi_poligonlari() == [],
              "kutu kapalıyken süzgeç boş")

    kok2 = tempfile.mkdtemp(prefix="boxify_roi2_")
    try:
        R.kaydet(kok2, [kare])
        w._img_dir = kok2
        w.roi_chk.setChecked(True)
        r.kontrol(len(w._roi_poligonlari()) == 1,
                  "kutu açıkken klasördeki ROI okunuyor")
        w._roi_ozeti_tazele()
        r.kontrol("bölge" in w.roi_lbl.text(), "özet arayüzde gösteriliyor",
                  w.roi_lbl.text()[:40])

        d = RoiDialog(kok2, QPixmap(640, 480), None)
        r.kontrol(len(d.tuval.poligonlar) == 1,
                  "çizim penceresi mevcut ROI'yi yüklüyor")
        d.tuval.hepsini_temizle()
        d.tuval._acik = [(0.1, 0.1), (0.5, 0.1), (0.5, 0.5)]
        d.tuval.bolgeyi_kapat()
        r.kontrol(len(d.tuval.poligonlar) == 1 and len(d.tuval.poligonlar[0]) == 3,
                  "üç noktalı bölge kapatılabiliyor")
        d.tuval.son_noktayi_geri_al()
        r.kontrol(not d.tuval.poligonlar,
                  "geri al kapatılmış bölgeyi düzenlemeye açıyor")
    finally:
        shutil.rmtree(kok2, ignore_errors=True)
    w.close()


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
    mlflow_yayilim_testi(r, app)
    kararlilik_testi(r, app)
    dayaniklilik_olcum_testi(r, app)
    roi_testi(r, app)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
