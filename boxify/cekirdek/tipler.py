"""Katmanlar arasında dolaşan veri tipleri.

Hepsi sade veri: ne Qt tipi, ne torch tensörü, ne SDK nesnesi. Bir kaynağın
ürettiği kare, onu kimin ürettiğinden bağımsız olarak aynı biçimde geziyor.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Kare:
    """Tek bir görüntü karesi.

    `goruntu` BGR düzeninde bir numpy dizisi (opencv'nin verdiği biçim).
    Çekirdek numpy'ı tip olarak kullanmıyor, yalnızca taşıyor — böylece
    numpy'sız bir sahte kaynak da test edilebiliyor.
    """
    goruntu: Any
    indeks: int = 0
    zaman: float = 0.0            # saniye; canlı kaynakta yakalama anı
    kaynak: str = ""              # hangi adresten geldiği (izlenebilirlik)
    ustveri: dict = field(default_factory=dict)

    @property
    def boyut(self):
        """(genişlik, yükseklik) — görüntü okunamıyorsa (0, 0)."""
        try:
            y, g = self.goruntu.shape[:2]
            return g, y
        except Exception:
            return 0, 0


@dataclass
class Tespit:
    """Tek bir tespit kutusu — piksel koordinatında."""
    x1: float
    y1: float
    x2: float
    y2: float
    sinif: int
    guven: float
    sinif_adi: str = ""

    @property
    def merkez(self):
        return (self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0

    def yolo(self, genislik: int, yukseklik: int):
        """(cx, cy, w, h) — 0-1 normalize, YOLO txt biçimi."""
        g = max(1, genislik)
        y = max(1, yukseklik)
        return ((self.x1 + self.x2) / 2.0 / g, (self.y1 + self.y2) / 2.0 / y,
                abs(self.x2 - self.x1) / g, abs(self.y2 - self.y1) / y)


@dataclass
class KaynakBilgi:
    """Bir kare kaynağının kendini tanıtması."""
    ad: str
    adres: str
    canli: bool = False           # canlı akış mı, sonlu bir dosya mı
    kare_sayisi: Optional[int] = None    # canlıda None
    fps: Optional[float] = None
    genislik: Optional[int] = None
    yukseklik: Optional[int] = None
