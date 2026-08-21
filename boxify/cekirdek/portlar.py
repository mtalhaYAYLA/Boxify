"""Portlar — çekirdeğin dış dünyadan beklediği sözleşmeler.

İki port var, çünkü Boxify'ın dışarıya bağlandığı iki yer var: kareyi
nereden aldığı ve çıkarımı neyin yaptığı. Geri kalan her şey (etiket
dosyaları, veri seti düzeni, rapor) zaten kendi içinde.

Sözleşmeler bilerek küçük: bir kaynak yalnızca "aç, kare ver, kapat"
bilmek zorunda. Kamera SDK'sının onlarca ayarı adaptörün kendi işi;
çekirdeğe sızarsa yeni bir kaynak eklemek çekirdeği değiştirmek olur.
"""

from abc import ABC, abstractmethod
from typing import Iterator, List

from .tipler import Kare, Tespit, KaynakBilgi


class KareKaynagi(ABC):
    """Kare üreten her şey: klasör, video dosyası, USB kamera, RTSP, SDK."""

    @abstractmethod
    def ac(self) -> KaynakBilgi:
        """Kaynağı hazırla ve kendini tanıt. Açılamazsa istisna fırlat."""

    @abstractmethod
    def kareler(self) -> Iterator[Kare]:
        """Kareleri sırayla üret. Canlı kaynakta bu üreteç bitmeyebilir."""

    @abstractmethod
    def kapat(self) -> None:
        """Kaynağı bırak. Çağrılmamış olsa bile yıkımda güvenli olmalı."""

    # Sözleşmenin bir parçası: `with` ile kullanılabilmesi. Canlı bir kamerayı
    # açık bırakmak, bir dosyayı açık bırakmakla aynı şey değil.
    def __enter__(self):
        self.bilgi = self.ac()
        return self

    def __exit__(self, *_):
        self.kapat()
        return False


class CikarimMotoru(ABC):
    """Kareden tespit üreten her şey: ultralytics, ham TensorRT, sahte motor."""

    @abstractmethod
    def yukle(self) -> List[str]:
        """Modeli hazırla, sınıf adlarını döndür."""

    @abstractmethod
    def calistir(self, kare: Kare) -> List[Tespit]:
        """Tek kare için tespitleri döndür."""

    def kapat(self) -> None:
        """İsteğe bağlı: GPU belleğini bırak."""

    def __enter__(self):
        self.siniflar = self.yukle()
        return self

    def __exit__(self, *_):
        self.kapat()
        return False
