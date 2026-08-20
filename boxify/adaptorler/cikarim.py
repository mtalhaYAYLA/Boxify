"""Çıkarım motoru adaptörleri.

İki motor var ve ikisi aynı portu uyguluyor: aracın kodu hangisinin çalıştığını
bilmiyor. Ultralytics her yerde çalışır ve varsayılan olan odur; ham TensorRT
yolu yalnızca NVIDIA donanımında anlamlıdır ve orada gecikmeyi düşürür.
"""

import os
from typing import List

from ..cekirdek import Kare, Tespit, CikarimMotoru


class UltralyticsMotoru(CikarimMotoru):
    """Her platformda çalışan varsayılan motor."""

    def __init__(self, model_yolu: str, conf: float = 0.25, iou: float = 0.45,
                 imgsz: int = 640, cihaz=None, istem: List[str] = None):
        self.model_yolu = model_yolu
        self.conf = conf
        self.iou = iou
        self.imgsz = imgsz
        self.cihaz = cihaz
        self.istem = list(istem or [])
        self._model = None
        self.siniflar: List[str] = []

    def yukle(self) -> List[str]:
        from ultralytics import YOLO
        if self.istem:
            ad = os.path.basename(self.model_yolu).lower()
            if "yoloe" in ad:
                from ultralytics import YOLOE
                self._model = YOLOE(self.model_yolu)
                try:
                    self._model.set_classes(self.istem,
                                            self._model.get_text_pe(self.istem))
                except Exception:
                    self._model.set_classes(self.istem)
            else:
                from ultralytics import YOLOWorld
                self._model = YOLOWorld(self.model_yolu)
                self._model.set_classes(self.istem)
            self.siniflar = list(self.istem)
        else:
            self._model = YOLO(self.model_yolu)
            adlar = dict(self._model.names)
            self.siniflar = [adlar[i] for i in sorted(adlar)]
        return self.siniflar

    def calistir(self, kare: Kare) -> List[Tespit]:
        if self._model is None:
            self.yukle()
        sonuc = self._model.predict(
            source=kare.goruntu, conf=self.conf, iou=self.iou,
            imgsz=self.imgsz, device=self.cihaz, verbose=False)[0]
        kutular = sonuc.boxes
        if kutular is None or not len(kutular):
            return []
        xyxy = kutular.xyxy.cpu().numpy()
        sinif = kutular.cls.cpu().numpy().astype(int)
        guven = kutular.conf.cpu().numpy()
        return [Tespit(float(a), float(b), float(c), float(d), int(s), float(g),
                       self.siniflar[s] if 0 <= s < len(self.siniflar) else str(s))
                for (a, b, c, d), s, g in zip(xyxy, sinif, guven)]

    def kapat(self) -> None:
        self._model = None


class TensorRTMotoru(CikarimMotoru):
    """Ham TensorRT motoru — ultralytics katmanı olmadan.

    Bütün GPU tamponları bir kez ayrılır, döngüde yeni ayırma yapılmaz;
    execute_async_v3 + tek stream ile çalışır. Gecikme dalgalanmasını (jitter)
    düşük tutmanın yolu bu.

    UYARI: bu adaptör NVIDIA donanımı olmadan çalıştırılamaz ve bu makinede
    doğrulanamadı. Kod jetson_test_pack/rt_pipeline/trt_engine.py'deki çalışan
    sürümün port karşılığıdır; ilk kez gerçek kartta koşarken çıktısını
    ultralytics motoruyla kıyaslayın.
    """

    def __init__(self, motor_yolu: str, imgsz: int = 640, conf: float = 0.25,
                 cihaz: int = 0, siniflar: List[str] = None):
        self.motor_yolu = motor_yolu
        self.imgsz = imgsz
        self.conf = conf
        self.cihaz = cihaz
        self.siniflar = list(siniflar or [])
        self._motor = None
        self._torch = None

    @staticmethod
    def kullanilabilir() -> bool:
        import importlib.util
        return (importlib.util.find_spec("tensorrt") is not None
                and importlib.util.find_spec("torch") is not None)

    def yukle(self) -> List[str]:
        if not self.kullanilabilir():
            raise RuntimeError(
                "TensorRT motoru için tensorrt ve torch gerekiyor.\n"
                "Bu yol yalnızca NVIDIA donanımında kullanılabilir; diğer "
                "platformlarda ultralytics motorunu kullanın.")
        import tensorrt as trt
        import torch

        self._torch = torch
        cihaz = torch.device(f"cuda:{self.cihaz}")
        torch.cuda.init()

        kayitci = trt.Logger(trt.Logger.WARNING)
        with open(self.motor_yolu, "rb") as f, trt.Runtime(kayitci) as runtime:
            # ultralytics .engine biçimi: [4B meta uzunluğu][JSON meta][motor]
            meta_uzunluk = int.from_bytes(f.read(4), byteorder="little")
            meta_ham = f.read(meta_uzunluk)
            motor = runtime.deserialize_cuda_engine(f.read())
        if motor is None:
            raise RuntimeError(f"Motor çözülemedi: {self.motor_yolu}")

        if not self.siniflar:
            try:
                import json
                meta = json.loads(meta_ham.decode("utf-8"))
                adlar = meta.get("names") or {}
                self.siniflar = [adlar[k] for k in sorted(adlar, key=int)]
            except Exception:
                self.siniflar = []

        tip_esleme = {
            trt.DataType.FLOAT: torch.float32, trt.DataType.HALF: torch.float16,
            trt.DataType.INT8: torch.int8, trt.DataType.INT32: torch.int32,
        }
        baglam = motor.create_execution_context()
        tamponlar, girdi_adi, cikti_adi = {}, None, None
        for i in range(motor.num_io_tensors):
            ad = motor.get_tensor_name(i)
            tip = tip_esleme[motor.get_tensor_dtype(ad)]
            bicim = tuple(motor.get_tensor_shape(ad))
            if motor.get_tensor_mode(ad) == trt.TensorIOMode.INPUT:
                baglam.set_input_shape(ad, bicim)
                girdi_adi = ad
            else:
                cikti_adi = ad
            t = torch.empty(bicim, dtype=tip, device=cihaz)
            tamponlar[ad] = t
            baglam.set_tensor_address(ad, t.data_ptr())

        self._motor = {
            "motor": motor, "baglam": baglam, "tamponlar": tamponlar,
            "girdi": girdi_adi, "cikti": cikti_adi, "cihaz": cihaz,
            "stream": torch.cuda.Stream(device=cihaz),
        }
        return self.siniflar

    def calistir(self, kare: Kare) -> List[Tespit]:
        if self._motor is None:
            self.yukle()
        import cv2
        torch = self._torch
        m = self._motor

        y0, g0 = kare.goruntu.shape[:2]
        girdi = m["tamponlar"][m["girdi"]]
        _b, _c, yh, gh = girdi.shape
        kucuk = cv2.resize(kare.goruntu, (gh, yh))
        rgb = cv2.cvtColor(kucuk, cv2.COLOR_BGR2RGB)
        t = torch.from_numpy(rgb).to(m["cihaz"]).permute(2, 0, 1).float() / 255.0
        girdi.copy_(t.unsqueeze(0).to(girdi.dtype))

        with torch.cuda.stream(m["stream"]):
            m["baglam"].execute_async_v3(m["stream"].cuda_stream)
        m["stream"].synchronize()

        ham = m["tamponlar"][m["cikti"]]
        return self._coz(ham, g0 / gh, y0 / yh)

    def _coz(self, ham, olcek_x: float, olcek_y: float) -> List[Tespit]:
        """(1, 4+sınıf, N) biçimindeki YOLO çıktısını tespitlere çevir."""
        t = ham[0] if ham.ndim == 3 else ham
        if t.shape[0] < t.shape[1]:
            t = t.transpose(0, 1)          # (N, 4+sınıf)
        kutu = t[:, :4]
        skor = t[:, 4:]
        en_iyi = skor.max(dim=1)
        secim = en_iyi.values > self.conf
        kutu = kutu[secim].float().cpu().numpy()
        guven = en_iyi.values[secim].float().cpu().numpy()
        sinif = en_iyi.indices[secim].cpu().numpy()
        tespitler = []
        for (cx, cy, g, y), s, c in zip(kutu, sinif, guven):
            tespitler.append(Tespit(
                float((cx - g / 2) * olcek_x), float((cy - y / 2) * olcek_y),
                float((cx + g / 2) * olcek_x), float((cy + y / 2) * olcek_y),
                int(s), float(c),
                self.siniflar[int(s)] if int(s) < len(self.siniflar) else str(int(s))))
        return tespitler

    def kapat(self) -> None:
        self._motor = None


def motor_ac(model_yolu: str, **kw) -> CikarimMotoru:
    """Dosya uzantısına bakıp motoru seç.

    .engine dosyası TensorRT'nin kendi biçimi; ultralytics onu da açabiliyor
    ama araya bir katman koyuyor. Donanım uygunsa ham yol tercih ediliyor,
    değilse sessizce ultralytics'e düşülüyor — kullanıcı bir şey kaybetmiyor.
    """
    if os.path.splitext(model_yolu)[1].lower() == ".engine" \
            and TensorRTMotoru.kullanilabilir():
        return TensorRTMotoru(model_yolu, imgsz=kw.get("imgsz", 640),
                              conf=kw.get("conf", 0.25),
                              siniflar=kw.get("siniflar"))
    return UltralyticsMotoru(model_yolu, **{k: v for k, v in kw.items()
                                            if k != "siniflar"})
