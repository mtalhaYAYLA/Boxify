"""Adaptörler — çekirdekteki portların somut karşılıkları.

Her adaptör kendi ağır bağımlılığını **kendi içinde, geç** import eder:
tensorrt kurulu olmayan bir makinede Boxify'ın açılmaması ya da Hikvision
SDK'sı yokken kamera listesinin patlaması kabul edilemez. Kurulu olmayan
adaptör "yok" der, uygulama çalışmaya devam eder.
"""

from .kaynak import kaynak_ac, kaynak_turleri, ADRES_YARDIMI

__all__ = ["kaynak_ac", "kaynak_turleri", "ADRES_YARDIMI"]
