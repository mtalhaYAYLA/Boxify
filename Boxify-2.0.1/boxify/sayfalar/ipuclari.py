"""İpuçları sayfası — genel sistemin nasıl çalıştığı ve her aracın püf noktaları.

İçerik araç kaydından (ARACLAR) beslenir; yeni araç eklendiğinde ipuçları
listesi de otomatik burada görünür.
"""

from PyQt5.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QScrollArea,
)
from PyQt5.QtCore import Qt

from ..araclar import ARACLAR

GENEL_AKIS = (
    "Boxify, bir nesne tespit modelini sıfırdan üretime taşıyan döngünün "
    "araç kutusudur. Akış tipik olarak şöyle işler: videolarından işe yarayan "
    "bölümleri kesersin (Video Kırpıcı), bu kliplerden fotoğraf karesi "
    "çıkarırsın (Kare Alıcı), kareleri mevcut bir modelle ön etiketlersin "
    "(Oto Label), etiketleri elle düzeltip tamamlarsın (Labelapp), veri setini "
    "denetleyip train/val olarak bölersin (Veri Denetçi), YOLO ile eğitirsin, "
    "eğitilen modelin nerede yanıldığına bakarsın (Hata Analizi) ve hazır "
    "olduğunda dağıtım biçimine çevirirsin (Model Export)."
)

GENEL_IPUCLARI = [
    "Bu bir döngüdür, tek seferlik bir hat değil: Hata Analizi'nin gösterdiği "
    "zayıf noktalara göre yeni veri toplayıp tekrar eğitmek, en büyük sıçramayı "
    "getirir. İyi modeller genellikle 3-4 turda olgunlaşır.",
    "Her adımı kullanmak zorunda değilsin. Elinde hazır fotoğraflar varsa "
    "doğrudan Oto Label veya Labelapp'ten başlayabilirsin; videoyla "
    "çalışmıyorsan ilk iki araca hiç girmezsin.",
    "Az ama temiz veri, çok ama kirli veriden iyidir: tutarlı etiketlenmiş "
    "birkaç yüz kare, özensiz binlerce kareden daha iyi model çıkarır.",
    "Her araç ilk tıklamada yüklenir ve sekme değişse bile arka planda "
    "çalışmaya devam eder; uzun bir işlem sürerken başka araca geçebilirsin.",
    "Hiçbir araç dosya silmez — temizlik daima karantina klasörüne taşımadır, "
    "yanlışlıkla veri kaybetmezsin.",
    "Eğitim adımı uygulamanın dışındadır: Veri Denetçi'nin ürettiği data.yaml "
    "ile 'yolo train data=.../data.yaml model=yolo11n.pt' komutu yeterlidir.",
]


class IpucuKarti(QFrame):
    """Bir aracın ipuçlarını listeleyen kart."""

    def __init__(self, arac: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("IpucuKart")

        kok = QVBoxLayout(self)
        kok.setContentsMargins(18, 14, 18, 14)
        kok.setSpacing(8)

        ust = QHBoxLayout()
        ust.setSpacing(10)
        rozet = QLabel(arac["amblem"])
        rozet.setObjectName("KartRozet")
        rozet.setFixedSize(30, 30)
        rozet.setAlignment(Qt.AlignCenter)
        ust.addWidget(rozet)
        baslik = QLabel(arac["ad"])
        baslik.setObjectName("IpucuBaslik")
        ust.addWidget(baslik)
        ozet = QLabel("— " + arac["ozet"])
        ozet.setObjectName("KartAciklama")
        ust.addWidget(ozet)
        ust.addStretch()
        kok.addLayout(ust)

        for ipucu in arac.get("ipuclari", []):
            satir = QLabel("•  " + ipucu)
            satir.setObjectName("IpucuMetin")
            satir.setWordWrap(True)
            kok.addWidget(satir)


class IpuclariSayfasi(QScrollArea):
    """Genel akış + araç bazlı ipuçları."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        govde = QWidget()
        kok = QVBoxLayout(govde)
        kok.setContentsMargins(36, 30, 36, 30)
        kok.setSpacing(16)

        baslik = QLabel("İpuçları")
        baslik.setObjectName("AnaBaslik")
        kok.addWidget(baslik)
        alt = QLabel("Sistemin genel işleyişi ve her aracın püf noktaları.")
        alt.setObjectName("AnaAltBaslik")
        kok.addWidget(alt)

        # ── Genel akış kutusu ────────────────────────────────────────────
        genel = QFrame()
        genel.setObjectName("IpucuGenel")
        gk = QVBoxLayout(genel)
        gk.setContentsMargins(18, 14, 18, 14)
        gk.setSpacing(8)

        gb = QLabel("Sistem nasıl çalışır?")
        gb.setObjectName("IpucuBaslik")
        gk.addWidget(gb)
        akis = QLabel(GENEL_AKIS)
        akis.setObjectName("IpucuMetin")
        akis.setWordWrap(True)
        gk.addWidget(akis)
        for ipucu in GENEL_IPUCLARI:
            satir = QLabel("•  " + ipucu)
            satir.setObjectName("IpucuMetin")
            satir.setWordWrap(True)
            gk.addWidget(satir)
        kok.addWidget(genel)

        # ── Araç bazlı ipuçları ──────────────────────────────────────────
        for arac in ARACLAR:
            kok.addWidget(IpucuKarti(arac))

        kok.addStretch()
        self.setWidget(govde)
