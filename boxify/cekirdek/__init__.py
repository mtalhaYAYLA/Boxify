"""Boxify çekirdeği — arayüzden ve donanımdan bağımsız sözleşmeler.

Bu paket bilerek dar tutuldu: PyQt5, ultralytics, tensorrt ya da kamera SDK'sı
buraya **import edilmez**. Böylece çekirdek hiçbir donanım olmadan test
edilebiliyor ve yeni bir kaynak/motor eklemek mevcut kodu değiştirmiyor.

Kanatlar (adaptörler) `boxify/adaptorler/` altında; her biri buradaki bir
portu uyguluyor.
"""

from .tipler import Kare, Tespit, KaynakBilgi
from .portlar import KareKaynagi, CikarimMotoru

__all__ = ["Kare", "Tespit", "KaynakBilgi", "KareKaynagi", "CikarimMotoru"]
