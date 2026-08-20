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
import sys
import time
from ctypes import cast, POINTER
from typing import Iterator

from ..cekirdek import Kare, KaynakBilgi, KareKaynagi

GORSEL_UZANTI = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
VIDEO_UZANTI = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".flv", ".mpg", ".mpeg"}

ADRES_YARDIMI = (
    "Klasör yolu · video dosyası · kamera:0 (USB) · rtsp://… · "
    "hik:192.168.1.64 (Hikrobot MVS)"
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


def mvs_sdk_yollari() -> list:
    """Hikrobot MVS SDK'sının Python sarmalayıcısının aranacağı yollar.

    SDK bir kurulum paketidir, depoya konulamaz ve pip'te yoktur — makineye
    Hikrobot'un MVS kurulumuyla gelir. Buradaki iş onu bulmak.

    Sıra: MVCAM_SDK_PATH ortam değişkeni → işletim sistemi varsayılanı.
    Linux'ta klasör adı mimariye göre değişiyor (Jetson'da aarch64).
    """
    yollar = []
    ozel = os.environ.get("MVCAM_SDK_PATH")
    if sys.platform.startswith("win"):
        kokler = [ozel, r"C:\Program Files (x86)\MVS", r"C:\Program Files\MVS"]
        for kok in kokler:
            if kok:
                yollar.append(os.path.join(kok, "Development", "Samples",
                                           "Python", "MvImport"))
    else:
        try:
            mimari = os.uname().machine
        except Exception:
            mimari = "x86_64"
        alt = "aarch64" if mimari == "aarch64" else "64"
        for kok in [ozel, "/opt/MVS"]:
            if kok:
                yollar.append(os.path.join(kok, "Samples", alt, "Python", "MvImport"))
                # Bazı kurulumlarda mimari klasörü yok
                yollar.append(os.path.join(kok, "Samples", "Python", "MvImport"))
    return [y for y in yollar if y]


def mvs_yukle():
    """MVS SDK'sını içe aktar. Bulunamazsa nerelere bakıldığını söyleyerek hata ver."""
    for yol in mvs_sdk_yollari():
        if not os.path.isdir(yol):
            continue
        if yol not in sys.path:
            sys.path.insert(0, yol)
        try:
            import MvCameraControl_class as mvs
            return mvs
        except Exception:
            continue
    raise RuntimeError(
        "Hikrobot MVS SDK bulunamadı.\n\n"
        "SDK bir kurulum paketidir; pip ile gelmez ve depoda tutulamaz. "
        "Hikrobot'un MVS kurulumunu yapman gerekiyor.\n\n"
        "Bakılan yollar:\n  " + "\n  ".join(mvs_sdk_yollari()) + "\n\n"
        "Başka bir yere kurduysan MVCAM_SDK_PATH ortam değişkenini ayarla.\n\n"
        "Not: Hikvision'ın güvenlik kameraları MVS istemez — onlar için "
        "rtsp:// adresi kullan.")


class HikrobotKaynagi(KareKaynagi):
    """Hikrobot endüstriyel kamera (MVS SDK).

    İki yol deneniyor: makinede senin `hik_camera` sarmalayıcın varsa o
    kullanılıyor (sahada denenmiş kod), yoksa SDK'ya doğrudan gidiliyor.

    DOĞRULANMADI: bu adaptör MVS SDK'sı ve gerçek kamera gerektirir; bu
    makinede ikisi de yok. İlk kez kamerayla koşarken çıktısını gözle
    doğrula.
    """

    def __init__(self, ip: str = "", poz_sn: float = None):
        self.ip = (ip or "").strip()
        self.poz_sn = poz_sn
        self._kam = None
        self._sarmalayici = False      # senin hik_camera paketin mi kullanıldı
        self._mvs = None
        self._tampon = None

    # ------------------------------------------------------------------ açılış

    def ac(self) -> KaynakBilgi:
        try:
            from hik_camera.hik_camera import HikCamera
        except Exception:
            HikCamera = None

        if HikCamera is not None:
            kameralar = HikCamera.get_cams([self.ip]) if self.ip else HikCamera.get_cams()
            if not kameralar:
                raise RuntimeError(f"Hikrobot kamera bulunamadı: {self.ip or 'otomatik'}")
            self._kam = list(kameralar.values())[0]
            self._kam.__enter__()
            self._sarmalayici = True
            if self.poz_sn:
                try:
                    self._kam.set_exposure_by_second(self.poz_sn)
                except Exception:
                    pass
            return KaynakBilgi(ad=f"hikrobot {self.ip or 'oto'}",
                               adres=f"hik:{self.ip}", canli=True)

        return self._ham_ac()

    def _ham_ac(self) -> KaynakBilgi:
        """SDK'ya doğrudan git: cihazları say, aç, akışı başlat."""
        from ctypes import byref, memset, sizeof, c_ubyte

        mvs = mvs_yukle()
        self._mvs = mvs

        liste = mvs.MV_CC_DEVICE_INFO_LIST()
        memset(byref(liste), 0, sizeof(liste))
        tur = mvs.MV_GIGE_DEVICE | mvs.MV_USB_DEVICE
        if mvs.MvCamera.MV_CC_EnumDevices(tur, liste) != 0:
            raise RuntimeError("MVS cihaz taraması başarısız")
        if liste.nDeviceNum == 0:
            raise RuntimeError("Ağda/USB'de Hikrobot kamera bulunamadı")

        secilen = None
        for i in range(liste.nDeviceNum):
            bilgi = cast(liste.pDeviceInfo[i],
                         POINTER(mvs.MV_CC_DEVICE_INFO)).contents
            if not self.ip:
                secilen = bilgi
                break
            if bilgi.nTLayerType == mvs.MV_GIGE_DEVICE:
                ham = bilgi.SpecialInfo.stGigEInfo.nCurrentIp
                adres = f"{(ham >> 24) & 0xFF}.{(ham >> 16) & 0xFF}." \
                        f"{(ham >> 8) & 0xFF}.{ham & 0xFF}"
                if adres == self.ip:
                    secilen = bilgi
                    break
        if secilen is None:
            raise RuntimeError(f"Belirtilen IP'de kamera yok: {self.ip}")

        kam = mvs.MvCamera()
        if kam.MV_CC_CreateHandle(secilen) != 0:
            raise RuntimeError("Kamera tanıtıcısı oluşturulamadı")
        if kam.MV_CC_OpenDevice(mvs.MV_ACCESS_Exclusive, 0) != 0:
            kam.MV_CC_DestroyHandle()
            raise RuntimeError("Kamera açılamadı (başka bir uygulama kullanıyor olabilir)")

        if self.poz_sn:
            try:
                kam.MV_CC_SetEnumValueByString("ExposureAuto", "Off")
                kam.MV_CC_SetFloatValue("ExposureTime", float(self.poz_sn) * 1e6)
            except Exception:
                pass

        if kam.MV_CC_StartGrabbing() != 0:
            kam.MV_CC_CloseDevice()
            kam.MV_CC_DestroyHandle()
            raise RuntimeError("Akış başlatılamadı")

        self._kam = kam
        self._sarmalayici = False
        return KaynakBilgi(ad=f"hikrobot {self.ip or 'oto'}",
                           adres=f"hik:{self.ip}", canli=True)

    # ------------------------------------------------------------------ kareler

    def kareler(self) -> Iterator[Kare]:
        i = 0
        while self._kam is not None:
            goruntu = None
            try:
                if self._sarmalayici:
                    goruntu = self._kam.robust_get_frame()
                else:
                    goruntu = self._ham_kare()
            except Exception:
                return
            if goruntu is None:
                return
            yield Kare(goruntu=goruntu, indeks=i, zaman=time.time(),
                       kaynak=f"hik:{self.ip}")
            i += 1

    def _ham_kare(self):
        """SDK'dan tek kare al ve BGR'ye çevir."""
        from ctypes import byref, memset, sizeof, cast, POINTER, c_ubyte

        mvs = self._mvs
        cerceve = mvs.MV_FRAME_OUT()
        memset(byref(cerceve), 0, sizeof(cerceve))
        if self._kam.MV_CC_GetImageBuffer(cerceve, 1000) != 0:
            return None
        try:
            bilgi = cerceve.stFrameInfo
            g, y = bilgi.nWidth, bilgi.nHeight
            hedef = (c_ubyte * (g * y * 3))()
            cevir = mvs.MV_CC_PIXEL_CONVERT_PARAM()
            memset(byref(cevir), 0, sizeof(cevir))
            cevir.nWidth, cevir.nHeight = g, y
            cevir.pSrcData = cerceve.pBufAddr
            cevir.nSrcDataLen = bilgi.nFrameLen
            cevir.enSrcPixelType = bilgi.enPixelType
            cevir.enDstPixelType = mvs.PixelType_Gvsp_BGR8_Packed
            cevir.pDstBuffer = hedef
            cevir.nDstBufferSize = g * y * 3
            if self._kam.MV_CC_ConvertPixelType(cevir) != 0:
                return None
            import numpy as np
            return np.frombuffer(hedef, dtype=np.uint8).reshape(y, g, 3).copy()
        finally:
            self._kam.MV_CC_FreeImageBuffer(cerceve)

    def kapat(self) -> None:
        if self._kam is None:
            return
        try:
            if self._sarmalayici:
                self._kam.__exit__(None, None, None)
            else:
                self._kam.MV_CC_StopGrabbing()
                self._kam.MV_CC_CloseDevice()
                self._kam.MV_CC_DestroyHandle()
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
        ("hik", "Hikrobot endüstriyel kamera (MVS SDK) — hik:192.168.1.64"),
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
    if kucuk.startswith(("hik:", "mvs:", "hikrobot:")):
        return HikrobotKaynagi(adres.split(":", 1)[1])
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
