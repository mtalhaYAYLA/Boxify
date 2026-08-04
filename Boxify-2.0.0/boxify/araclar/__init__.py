"""Araç kaydı — kenar çubuğu ve ana sayfa bu listeden beslenir.

Her araç kendi modülünde bir MainWindow sınıfı sunar; modül ancak araç ilk kez
açıldığında import edilir (ultralytics/cv2 gibi ağır bağımlılıklar açılışı
yavaşlatmasın diye).
"""

ARACLAR = [
    {
        "anahtar": "video_kirpici",
        "ad": "Video Kırpıcı",
        "adim": 1,
        "amblem": "✂",
        "modul": "boxify.araclar.video_kirpici",
        "ozet": "Videodan işe yarayan zaman aralıklarını kes",
        "aciklama": "Uzun hat kayıtlarını oynatıp ilgilendiğin zaman aralıklarını "
                    "işaretler, ffmpeg ile kayıpsız klipler olarak dışa aktarır.",
    },
    {
        "anahtar": "kare_alici",
        "ad": "Kare Alıcı",
        "adim": 2,
        "amblem": "▣",
        "modul": "boxify.araclar.kare_alici",
        "ozet": "Kliplerden kare (fotoğraf) çıkar",
        "aciklama": "Klipleri izleyip tek tek kare yakalar ya da belirli fps ile "
                    "toplu kare çıkarır; eğitim verisinin ham fotoğrafları burada doğar.",
    },
    {
        "anahtar": "oto_label",
        "ad": "Oto Label",
        "adim": 3,
        "amblem": "⚡",
        "modul": "boxify.araclar.oto_label",
        "ozet": "Mevcut modelle kareleri ön etiketle",
        "aciklama": "Eldeki YOLO modeliyle kareleri tarar, YOLO txt etiketleri üretir. "
                    "Düşük güven eşiğiyle çalıştırıp elle düzeltmek en hızlı yoldur.",
    },
    {
        "anahtar": "labelapp",
        "ad": "Labelapp",
        "adim": 4,
        "amblem": "✎",
        "modul": "boxify.araclar.labelapp",
        "ozet": "Etiketleri elle düzelt / tamamla",
        "aciklama": "Kutu çizme, taşıma ve sınıf atama arayüzü. Oto Label'ın "
                    "ürettiklerini düzeltmek ve eksikleri tamamlamak için.",
    },
    {
        "anahtar": "veri_denetci",
        "ad": "Veri Denetçi",
        "adim": 5,
        "amblem": "☰",
        "modul": "boxify.araclar.veri_denetci",
        "ozet": "Veriyi denetle, kopyaları ayıkla, sızıntısız böl",
        "aciklama": "Bozuk etiketleri bulur, dHash ile yakın kopyaları gruplar, "
                    "karantinaya taşır ve sahne sızıntısı olmayan train/val bölmesi üretir.",
    },
    {
        "anahtar": "hata_analizi",
        "ad": "Hata Analizi",
        "adim": 6,
        "amblem": "◔",
        "modul": "boxify.araclar.hata_analizi",
        "ozet": "Model nerede yanılıyor + sırada ne etiketlenmeli",
        "aciklama": "Modeli etiketli sette koşturup kaçırma/uydurma/karışıklık döker; "
                    "aktif öğrenme sekmesi etiketlenecek en öğretici kareleri seçer.",
    },
    {
        "anahtar": "model_export",
        "ad": "Model Export",
        "adim": 7,
        "amblem": "⇥",
        "modul": "boxify.araclar.model_export",
        "ozet": "Dağıtım biçimine çevir, hız ve sapmayı ölç",
        "aciklama": "ONNX / TensorRT / OpenVINO'ya aktarır, ısınmalı hız ölçümü yapar "
                    "(ortalama-medyan-p95), kamera kapasitesini ve dönüşüm sapmasını raporlar.",
    },
]


def arac_bul(anahtar: str) -> dict:
    for a in ARACLAR:
        if a["anahtar"] == anahtar:
            return a
    raise KeyError(anahtar)
