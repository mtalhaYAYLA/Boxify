"""Çekirdek + adaptör mimarisi — portlar gerçekten değiştirilebilir mi?

Hexagonal mimarinin tek somut vaadi şudur: çekirdek dış dünyayı bilmez ve bir
adaptörü diğeriyle değiştirmek çekirdeği (ve araçları) değiştirmeyi
gerektirmez. Bu dosya o vaadi sınıyor — mimariyi anlatan yorumlara değil,
davranışa bakarak.

    python testler/test_mimari.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, Rapor   # noqa: E402

yolu_kur()

import numpy as np      # noqa: E402
import cv2              # noqa: E402


def cekirdek_yalitimi_testi(r):
    """Çekirdek, arayüz ve donanım paketlerini import ETMEMELİ.

    Bu kural yazılı olarak durmaz — kod okunarak korunmaz. Bir gün biri
    çekirdeğe `from PyQt5...` yazdığında bu test düşer.
    """
    import boxify.cekirdek as cekirdek

    kok = os.path.dirname(cekirdek.__file__)
    yasak = ("PyQt5", "ultralytics", "tensorrt", "torch", "cv2", "hik_camera")
    ihlal = []
    for ad in sorted(os.listdir(kok)):
        if not ad.endswith(".py"):
            continue
        with open(os.path.join(kok, ad), encoding="utf-8") as f:
            for no, satir in enumerate(f, 1):
                kirp = satir.strip()
                if not (kirp.startswith("import ") or kirp.startswith("from ")):
                    continue
                for paket in yasak:
                    if paket in kirp:
                        ihlal.append(f"{ad}:{no} {kirp}")
    r.kontrol(not ihlal, "çekirdek arayüz/donanım paketlerine bağlı değil",
              "; ".join(ihlal) if ihlal else "temiz")

    # Çekirdek tek başına import edilebilmeli
    import subprocess
    kod = ("import sys; sys.path.insert(0, %r);"
           "import boxify.cekirdek as c;"
           "print(c.Kare, c.Tespit, c.KareKaynagi, c.CikarimMotoru)"
           % os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = subprocess.run([sys.executable, "-c", kod], capture_output=True, text=True)
    r.kontrol(p.returncode == 0, "çekirdek tek başına import edilebiliyor",
              (p.stderr or p.stdout).strip()[:80])


def port_sozlesmesi_testi(r):
    """Sahte bir adaptör, gerçek olanla aynı yerde kullanılabiliyor mu?"""
    from boxify.cekirdek import Kare, Tespit, KareKaynagi, CikarimMotoru, KaynakBilgi

    class SahteKaynak(KareKaynagi):
        """Ne dosya ne kamera — yalnızca portu uygulayan bir şey."""

        def __init__(self, adet=3):
            self.adet = adet
            self.acildi = False
            self.kapandi = False

        def ac(self):
            self.acildi = True
            return KaynakBilgi(ad="sahte", adres="sahte://", canli=False,
                               kare_sayisi=self.adet)

        def kareler(self):
            for i in range(self.adet):
                yield Kare(goruntu=np.zeros((8, 8, 3), np.uint8), indeks=i,
                           kaynak="sahte://")

        def kapat(self):
            self.kapandi = True

    k = SahteKaynak(4)
    with k as acik:
        r.kontrol(k.acildi and acik.bilgi.kare_sayisi == 4,
                  "port `with` ile açılıyor ve kendini tanıtıyor")
        r.kontrol(len(list(acik.kareler())) == 4, "sahte kaynak kare üretiyor")
    r.kontrol(k.kapandi, "`with` çıkışında kaynak kapatılıyor")

    class SahteMotor(CikarimMotoru):
        def yukle(self):
            return ["nesne"]

        def calistir(self, kare):
            g, y = kare.boyut
            return [Tespit(0, 0, g / 2, y / 2, 0, 0.9, "nesne")]

    with SahteMotor() as m:
        r.kontrol(m.siniflar == ["nesne"], "motor portu sınıf listesi veriyor")
        tespitler = m.calistir(Kare(goruntu=np.zeros((100, 200, 3), np.uint8)))
        r.kontrol(len(tespitler) == 1 and tespitler[0].merkez == (50.0, 25.0),
                  "motor portu tespit üretiyor")

    # eksik uygulama: soyut sınıf örneklenememeli
    class Eksik(KareKaynagi):
        pass

    try:
        Eksik()
        olmadi = True
    except TypeError:
        olmadi = False
    r.kontrol(not olmadi, "portu eksik uygulayan sınıf örneklenemiyor")


def adres_cozumleme_testi(r):
    """Adres metninden doğru adaptör seçiliyor mu?"""
    from boxify.adaptorler import kaynak_ac, kaynak_turleri
    from boxify.adaptorler.kaynak import (KlasorKaynagi, VideoKaynagi,
                                          KameraKaynagi, HikrobotKaynagi)

    kok = tempfile.mkdtemp(prefix="boxify_mim_")
    try:
        for i in range(3):
            cv2.imwrite(os.path.join(kok, f"k{i}.jpg"),
                        np.full((60, 80, 3), i * 50, np.uint8))
        video = os.path.join(kok, "v.mp4")
        yaz = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 10, (80, 60))
        for i in range(12):
            yaz.write(np.full((60, 80, 3), i * 10, np.uint8))
        yaz.release()

        esleme = [
            (kok, KlasorKaynagi, "klasör"),
            (video, VideoKaynagi, "video dosyası"),
            ("kamera:0", KameraKaynagi, "USB kamera"),
            ("0", KameraKaynagi, "sade indeks"),
            ("rtsp://a/b", KameraKaynagi, "RTSP"),
            ("hik:192.168.1.64", HikrobotKaynagi, "Hikrobot"),
        ]
        for adres, tur, ad in esleme:
            r.kontrol(isinstance(kaynak_ac(adres), tur),
                      f"{ad} adresi doğru adaptöre gidiyor")

        for adres, hata in (("", ValueError), ("/yok/boyle/yer", FileNotFoundError)):
            try:
                kaynak_ac(adres)
                oldu = True
            except hata:
                oldu = False
            except Exception:
                oldu = True
            r.kontrol(not oldu, f"geçersiz adres {hata.__name__} veriyor")

        # gerçekten okuyor mu
        with kaynak_ac(kok) as k:
            kareler = list(k.kareler())
            r.kontrol(len(kareler) == 3 and kareler[0].boyut == (80, 60),
                      "klasör adaptörü kareleri okuyor",
                      f"{len(kareler)} kare, {kareler[0].boyut}")
            r.kontrol(not k.bilgi.canli and k.bilgi.kare_sayisi == 3,
                      "klasör canlı değil, kare sayısı biliniyor")
        with kaynak_ac(video) as k:
            r.kontrol(len(list(k.kareler())) == 12,
                      "video adaptörü bütün kareleri okuyor")
            r.kontrol(k.bilgi.fps == 10.0, "video fps'i okunuyor")

        r.kontrol(len(kaynak_turleri()) >= 5,
                  "arayüz için kaynak türü listesi var")
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def motor_secimi_testi(r):
    """Model uzantısına göre motor seçimi ve donanımsız makinede davranış."""
    from boxify.adaptorler.cikarim import (UltralyticsMotoru, TensorRTMotoru,
                                           motor_ac)

    r.kontrol(isinstance(motor_ac("model.pt"), UltralyticsMotoru),
              ".pt ultralytics motoruna gidiyor")
    r.kontrol(isinstance(TensorRTMotoru.kullanilabilir(), bool),
              "TensorRT kullanılabilirliği sorulabiliyor",
              f"kullanılabilir: {TensorRTMotoru.kullanilabilir()}")
    if not TensorRTMotoru.kullanilabilir():
        r.kontrol(isinstance(motor_ac("model.engine"), UltralyticsMotoru),
                  "TensorRT yokken .engine sessizce ultralytics'e düşüyor")
        m = TensorRTMotoru("model.engine")
        try:
            m.yukle()
            anlatti = False
        except RuntimeError as e:
            anlatti = "tensorrt" in str(e).lower()
        r.kontrol(anlatti, "TensorRT yokken açık bir hata anlatılıyor")


def canli_yakalama_testi(r, app):
    """Canlı yakalama işçisi portu üzerinden kare yazıyor mu?"""
    from boxify.araclar.kare_alici import CanliYakalaIscisi
    import time

    kok = tempfile.mkdtemp(prefix="boxify_canli_")
    try:
        video = os.path.join(kok, "v.mp4")
        yaz = cv2.VideoWriter(video, cv2.VideoWriter_fourcc(*"mp4v"), 10, (80, 60))
        for i in range(20):
            yaz.write(np.full((60, 80, 3), i * 12, np.uint8))
        yaz.release()
        cikti = os.path.join(kok, "kareler")

        isci = CanliYakalaIscisi(video, cikti, adet=5, aralik_sn=1, bicim="jpg")
        sonuc = {}
        isci.bitti.connect(lambda a, k: sonuc.update(adet=a, klasor=k))
        isci.hata.connect(lambda m: sonuc.update(hata=m))
        isci.start()
        t0 = time.time()
        while isci.isRunning() and time.time() - t0 < 30:
            app.processEvents()
            time.sleep(0.02)
        isci.wait(2000)
        app.processEvents()

        r.kontrol("hata" not in sonuc, "yakalama hatasız bitti",
                  sonuc.get("hata", ""))
        r.kontrol(sonuc.get("adet") == 5, "istenen sayıda kare yazıldı",
                  str(sonuc.get("adet")))
        yazilanlar = os.listdir(cikti) if os.path.isdir(cikti) else []
        r.kontrol(len(yazilanlar) == 5, "kareler diske gerçekten yazıldı",
                  f"{len(yazilanlar)} dosya")
        if yazilanlar:
            ornek = cv2.imdecode(
                np.fromfile(os.path.join(cikti, sorted(yazilanlar)[0]), np.uint8),
                cv2.IMREAD_COLOR)
            r.kontrol(ornek is not None and ornek.shape[:2] == (60, 80),
                      "yazılan kare okunabilir ve doğru boyutta")

        # olmayan kaynak: çökmeden hata vermeli
        isci2 = CanliYakalaIscisi("/yok/kaynak", cikti, 3, 1)
        sonuc2 = {}
        isci2.hata.connect(lambda m: sonuc2.update(hata=m))
        isci2.start()
        t0 = time.time()
        while isci2.isRunning() and time.time() - t0 < 15:
            app.processEvents()
            time.sleep(0.02)
        isci2.wait(2000)
        app.processEvents()
        r.kontrol("hata" in sonuc2, "olmayan kaynak açık hata veriyor",
                  sonuc2.get("hata", "")[:60])
    finally:
        shutil.rmtree(kok, ignore_errors=True)


def hikrobot_sdk_testi(r):
    """MVS SDK bulma mantığı ve SDK yokken davranış.

    SDK bir kurulum paketi: pip'te yok, depoda tutulamaz. Yapılabilecek tek
    doğru şey onu bulmak ve bulamayınca nereye baktığını söylemek.
    """
    from boxify.adaptorler.kaynak import (mvs_sdk_yollari, mvs_yukle,
                                          HikrobotKaynagi, kaynak_ac)

    yollar = mvs_sdk_yollari()
    r.kontrol(len(yollar) >= 1, "SDK için aranacak yollar üretiliyor",
              " · ".join(yollar))
    r.kontrol(all("MvImport" in y for y in yollar),
              "yollar SDK'nın Python sarmalayıcı klasörünü gösteriyor")

    eski = os.environ.get("MVCAM_SDK_PATH")
    os.environ["MVCAM_SDK_PATH"] = "/ozel/mvs/yolu"
    try:
        ozel = mvs_sdk_yollari()
        r.kontrol(any("/ozel/mvs/yolu" in y for y in ozel),
                  "MVCAM_SDK_PATH ortam değişkeni dikkate alınıyor")
        r.kontrol(ozel[0].startswith("/ozel/mvs/yolu"),
                  "özel yol varsayılanın önüne geçiyor")
    finally:
        if eski is None:
            os.environ.pop("MVCAM_SDK_PATH", None)
        else:
            os.environ["MVCAM_SDK_PATH"] = eski

    try:
        mvs_yukle()
        yuklendi = True
        mesaj = ""
    except RuntimeError as e:
        yuklendi = False
        mesaj = str(e)

    if yuklendi:
        r.bilgi("MVS SDK bu makinede kurulu — gerçek kamera testi elle yapılmalı")
    else:
        r.kontrol("Bakılan yollar" in mesaj,
                  "SDK yokken nereye bakıldığı söyleniyor")
        r.kontrol("MVCAM_SDK_PATH" in mesaj,
                  "kullanıcıya çözüm yolu veriliyor")
        r.kontrol("rtsp" in mesaj.lower(),
                  "güvenlik kamerası için MVS gerekmediği hatırlatılıyor")

    for adres in ("hik:192.168.1.64", "mvs:192.168.1.64", "hikrobot:10.0.0.5"):
        r.kontrol(isinstance(kaynak_ac(adres), HikrobotKaynagi),
                  f"{adres.split(':')[0]}: ön eki Hikrobot adaptörüne gidiyor")

    k = HikrobotKaynagi("192.168.1.64")
    r.kontrol(k.ip == "192.168.1.64" and k._kam is None,
              "adaptör kurulurken donanıma dokunmuyor (tembel açılış)")
    k.kapat()
    r.kontrol(True, "açılmamış kaynağı kapatmak güvenli")


def main() -> int:
    from PyQt5.QtWidgets import QApplication
    r = Rapor("Çekirdek ve adaptör mimarisi")
    app = QApplication.instance() or QApplication([])
    cekirdek_yalitimi_testi(r)
    port_sozlesmesi_testi(r)
    adres_cozumleme_testi(r)
    motor_secimi_testi(r)
    hikrobot_sdk_testi(r)
    canli_yakalama_testi(r, app)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
