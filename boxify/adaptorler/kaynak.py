"""Kare kaynağı adaptörleri ve adresten kaynak seçen fabrika.

Adres biçimi bilerek tek satırlık: kullanıcı bir metin yazıyor, hangi
adaptörün açılacağına o metin karar veriyor. Böylece "kaynak seç" arayüzü
her araçta tek bir alan oluyor ve yeni bir kaynak türü eklemek arayüzü
değiştirmeyi gerektirmiyor.

    /yol/klasor          → klasördeki görseller
    /yol/video.mp4       → video dosyası
    kamera:0             → yerel kamera (USB), 0. cihaz
    rtsp://…             → ağ kamerası
    hik:192.168.1.64     → Hikvision (MVS SDK)
"""

import os
import time
from typing import Iterator

from ..cekirdek import Kare, KaynakBilgi, KareKaynagi

GORSEL_UZANTI = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_UZANTI = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg"}

ADRES_YARDIMI = (
    "Klasör yolu · video dosyası · kamera:0 (USB) · rtsp://… · hik:192.168.1.64"
)


class KlasorKaynagi(KareKaynagi):
    """Klasördeki görseller — sonlu, sıralı."""

    def __init__(self, klasor: str, alt_klasorler: bool = False):
        self.klasor = klasor
        self.alt_klasorler = alt_klasorler
        self._yollar = []

    def ac(self) -> KaynakBilgi:
        if not os.path.isdir(self.klasor):
            raise FileNotFoundError(f"Klasör yok: {self.klasor}")
        yollar = []
        if self.alt_klasorler:
            for kok, _d, dosyalar in os.walk(self.klasor):
                yollar += [os.path.join(kok, d) for d in dosyalar
                           if os.path.splitext(d)[1].lower() in GORSEL_UZANTI]
        else:
            yollar = [os.path.join(self.klasor, d) for d in os.listdir(self.klasor)
                      if os.path.splitext(d)[1].lower() in GORSEL_UZANTI]
        self._yollar = sorted(yollar)
        return KaynakBilgi(ad=os.path.basename(self.klasor.rstrip(os.sep)) or "klasör",
                           adres=self.klasor, canli=False,
                           kare_sayisi=len(self._yollar))

    def kareler(self) -> Iterator[Kare]:
        import cv2
        import numpy as np
        for i, yol in enumerate(self._yollar):
            try:
                # imdecode: Türkçe/boşluklu yollarda imread sessizce None döner
                goruntu = cv2.imdecode(np.fromfile(yol, dtype=np.uint8),
                                       cv2.IMREAD_COLOR)
            except Exception:
                goruntu = None
            if goruntu is None:
                continue
            yield Kare(goruntu=goruntu, indeks=i, zaman=time.time(),
                       kaynak=yol, ustveri={"dosya": yol})

    def kapat(self) -> None:
        self._yollar = []


class _OpenCVKaynagi(KareKaynagi):
    """cv2.VideoCapture ile açılan her şeyin ortak gövdesi."""

    def __init__(self, hedef, adres: str, canli: bool, ad: str):
        self._hedef = hedef
        self.adres = adres
        self.canli = canli
        self.ad = ad
        self._cap = None

    def ac(self) -> KaynakBilgi:
        import cv2
        self._cap = cv2.VideoCapture(self._hedef)
        if not self._cap.isOpened():
            self._cap = None
            raise RuntimeError(f"Kaynak açılamadı: {self.adres}")
        fps = self._cap.get(cv2.CAP_PROP_FPS) or 0.0
        sayi = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        return KaynakBilgi(
            ad=self.ad, adres=self.adres, canli=self.canli,
            kare_sayisi=None if self.canli or sayi <= 0 else sayi,
            fps=fps if fps > 0 else None,
            genislik=int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0) or None,
            yukseklik=int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0) or None)

    def kareler(self) -> Iterator[Kare]:
        if self._cap is None:
            return
        i = 0
        bos_okuma = 0
        while True:
            ok, goruntu = self._cap.read()
            if not ok or goruntu is None:
                # Canlı akışta tek bir başarısız okuma akışın bittiği anlamına
                # gelmez (ağ tıkanması, kare düşmesi). Dosyada ise bittiğidir.
                if not self.canli:
                    return
                bos_okuma += 1
                if bos_okuma > 30:
                    return
                time.sleep(0.05)
                continue
            bos_okuma = 0
            yield Kare(goruntu=goruntu, indeks=i, zaman=time.time(),
                       kaynak=self.adres)
            i += 1

    def kapat(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


class VideoKaynagi(_OpenCVKaynagi):
    def __init__(self, yol: str):
        super().__init__(yol, yol, canli=False, ad=os.path.basename(yol))


class KameraKaynagi(_OpenCVKaynagi):
    """USB/dahili kamera (indeks) ya da ağ akışı (rtsp/http)."""

    def __init__(self, adres: str):
        if adres.startswith("kamera:"):
            hedef = int(adres.split(":", 1)[1] or 0)
            ad = f"kamera {hedef}"
        else:
            hedef = adres
            ad = adres.split("//")[-1].split("/")[0] or adres
        super().__init__(hedef, adres, canli=True, ad=ad)


class HikvisionKaynagi(KareKaynagi):
    """Hikvision (MVS SDK) endüstriyel kamera.

    SDK yalnızca kurulu olduğu makinede import edilir; yoksa açıkça söyler.
    Bu makinede donanım olmadığı için doğrulanamadı — kod jetson_test_pack'teki
    çalışan sürücünün port karşılığıdır.
    """

    def __init__(self, ip: str, poz_sn: float = None):
        self.ip = ip
        self.poz_sn = poz_sn
        self._kam = None

    def ac(self) -> KaynakBilgi:
        try:
            from hik_camera.hik_camera import HikCamera
        except Exception as e:
            raise RuntimeError(
                "Hikvision SDK bulunamadı (hik_camera / MvCameraControl_class).\n"
                "Kamera yalnızca MVS SDK kurulu makinelerde açılabilir.\n"
                f"Ayrıntı: {e}")
        kameralar = HikCamera.get_cams([self.ip]) if self.ip else HikCamera.get_cams()
        if not kameralar:
            raise RuntimeError(f"Hikvision kamera bulunamadı: {self.ip or 'otomatik'}")
        self._kam = list(kameralar.values())[0]
        self._kam.__enter__()
        if self.poz_sn:
            try:
                self._kam.set_exposure_by_second(self.poz_sn)
            except Exception:
                pass
        return KaynakBilgi(ad=f"hik {self.ip}", adres=f"hik:{self.ip}", canli=True)

    def kareler(self) -> Iterator[Kare]:
        i = 0
        while self._kam is not None:
            try:
                goruntu = self._kam.robust_get_frame()
            except Exception:
                return
            if goruntu is None:
                return
            yield Kare(goruntu=goruntu, indeks=i, zaman=time.time(),
                       kaynak=f"hik:{self.ip}")
            i += 1

    def kapat(self) -> None:
        if self._kam is not None:
            try:
                self._kam.__exit__(None, None, None)
            except Exception:
                pass
            self._kam = None


def kaynak_turleri() -> list:
    """(anahtar, açıklama) — arayüzde kullanıcıya gösterilecek liste."""
    return [
        ("klasor", "Görsel klasörü"),
        ("video", "Video dosyası"),
        ("kamera", "Yerel kamera (USB) — kamera:0"),
        ("rtsp", "Ağ kamerası — rtsp://kullanici:sifre@ip/stream"),
        ("hik", "Hikvision (MVS SDK) — hik:192.168.1.64"),
    ]


def kaynak_ac(adres: str, alt_klasorler: bool = False) -> KareKaynagi:
    """Adrese bakıp doğru adaptörü kur (henüz açmaz).

    Kural sırası önemli: önce açık ön ekler, sonra dosya sisteminde ne olduğu.
    Böylece "kamera:0" diye bir klasör olsa bile kamera kazanır.
    """
    adres = (adres or "").strip()
    if not adres:
        raise ValueError("Kaynak adresi boş")

    kucuk = adres.lower()
    if kucuk.startswith("hik:"):
        return HikvisionKaynagi(adres.split(":", 1)[1])
    if kucuk.startswith("kamera:") or kucuk.startswith(("rtsp://", "http://", "https://")):
        return KameraKaynagi(adres)
    if adres.isdigit():                       # sade "0" da kamera sayılır
        return KameraKaynagi(f"kamera:{adres}")
    if os.path.isdir(adres):
        return KlasorKaynagi(adres, alt_klasorler)
    if os.path.isfile(adres):
        if os.path.splitext(adres)[1].lower() in VIDEO_UZANTI:
            return VideoKaynagi(adres)
        raise ValueError(f"Desteklenmeyen dosya türü: {adres}")
    raise FileNotFoundError(f"Kaynak bulunamadı: {adres}")
