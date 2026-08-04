"""Araç kaydı — kenar çubuğu, ana sayfa ve ipuçları sayfası bu listeden beslenir.

Her araç kendi modülünde bir MainWindow sınıfı sunar; modül ancak araç ilk kez
açıldığında import edilir (ultralytics/cv2 gibi ağır bağımlılıklar açılışı
yavaşlatmasın diye).

Araçlar belirli bir alana bağlı değildir: balon, araç, ürün, kusur…
hangi nesneyi tespit etmek istersen aynı akış geçerlidir.
"""

ARACLAR = [
    {
        "anahtar": "video_kirpici",
        "ad": "Video Kırpıcı",
        "amblem": "✂",
        "modul": "boxify.araclar.video_kirpici",
        "ozet": "Videodan işe yarayan zaman aralıklarını kes",
        "aciklama": "Uzun video kayıtlarını oynatıp ilgilendiğin zaman aralıklarını "
                    "işaretler, ffmpeg ile kayıpsız klipler olarak dışa aktarır.",
        "ipuclari": [
            "Kaydın tamamını değil, nesnenin gerçekten göründüğü bölümleri kes; "
            "boş sahneler eğitime katkı sağlamaz.",
            "Kesim kayıpsızdır (yeniden kodlama yok), bu yüzden uzun videolarda "
            "bile saniyeler sürer — çekinmeden bol parça al.",
            "Farklı ışık, açı ve arka plan içeren bölümleri özellikle dahil et; "
            "çeşitlilik modelin genellemesini doğrudan belirler.",
        ],
    },
    {
        "anahtar": "kare_alici",
        "ad": "Kare Alıcı",
        "amblem": "▣",
        "modul": "boxify.araclar.kare_alici",
        "ozet": "Kliplerden kare (fotoğraf) çıkar",
        "aciklama": "Klipleri izleyip tek tek kare yakalar ya da belirli fps ile "
                    "toplu kare çıkarır; eğitim verisinin ham fotoğrafları burada doğar.",
        "ipuclari": [
            "Toplu çıkarımda fps'i düşük tut (ör. 1-2 fps): ardışık kareler "
            "birbirinin neredeyse kopyasıdır ve veri setini şişirir.",
            "Nadir görülen anlar (kısmi görünme, kesişme, bulanıklık) için tek "
            "kare yakalamayı kullan — bunlar en öğretici örneklerdir.",
            "Kareleri klip adıyla ilişkili klasörlerde tut; Veri Denetçi'nin "
            "sahne sızıntısız bölmesi bu gruplamadan yararlanır.",
        ],
    },
    {
        "anahtar": "oto_label",
        "ad": "Oto Label",
        "amblem": "⚡",
        "modul": "boxify.araclar.oto_label",
        "ozet": "Mevcut modelle kareleri ön etiketle",
        "aciklama": "Eldeki YOLO modeliyle kareleri tarar, YOLO txt etiketleri üretir. "
                    "Düşük güven eşiğiyle çalıştırıp elle düzeltmek en hızlı yoldur.",
        "ipuclari": [
            "Güven eşiğini düşük tut (ör. 0.25): fazladan kutuyu silmek, "
            "kaçırılmış nesneyi sıfırdan çizmekten çok daha hızlıdır.",
            "İlk turda hazır bir COCO modeli bile işe yarar; kendi modelin "
            "eğitildikçe ön etiketleme her turda daha isabetli olur.",
            "Ön etiketler taslaktır — mutlaka Labelapp'te gözden geçir; "
            "denetlenmemiş oto etiketle eğitmek hataları kalıcılaştırır.",
        ],
    },
    {
        "anahtar": "labelapp",
        "ad": "Labelapp",
        "amblem": "✎",
        "modul": "boxify.araclar.labelapp",
        "ozet": "Etiketleri elle düzelt / tamamla",
        "aciklama": "Kutu çizme, taşıma ve sınıf atama arayüzü. Oto Label'ın "
                    "ürettiklerini düzeltmek ve eksikleri tamamlamak için.",
        "ipuclari": [
            "Kutuyu nesneye sıkıca oturt: bol pay bırakılmış kutular modelin "
            "konum hassasiyetini düşürür.",
            "Sınıf tanımlarını baştan netleştir ve hep aynı kurala göre "
            "etiketle; tutarsız etiket, az etiketten daha zararlıdır.",
            "Kısmen görünen nesneyi de etiketle — gerçek kullanımda nesneler "
            "çoğu zaman tam görünmez.",
        ],
    },
    {
        "anahtar": "veri_denetci",
        "ad": "Veri Denetçi",
        "amblem": "☰",
        "modul": "boxify.araclar.veri_denetci",
        "ozet": "Veriyi denetle, kopyaları ayıkla, sızıntısız böl",
        "aciklama": "Bozuk etiketleri bulur, dHash ile yakın kopyaları gruplar, "
                    "karantinaya taşır ve sahne sızıntısı olmayan train/val bölmesi üretir.",
        "ipuclari": [
            "Eğitime başlamadan önce mutlaka buradan geç: bozuk tek bir etiket "
            "dosyası bütün eğitimi düşürebilir.",
            "Yakın kopyaların aynı anda train ve val'e düşmesi başarıyı yapay "
            "olarak şişirir — sızıntısız bölme bunu engeller.",
            "Hiçbir dosya silinmez, sorunlular karantina klasörüne taşınır; "
            "yanlış ayıklandığını düşündüğünü geri alabilirsin.",
        ],
    },
    {
        "anahtar": "egitim",
        "ad": "Eğitim",
        "amblem": "◈",
        "modul": "boxify.araclar.egitim",
        "ozet": "Veri setini modele dönüştür, kendi modelinin üstüne devam et",
        "aciklama": "Veri Denetçi'nin ürettiği data.yaml'ı eğitir. Hazır bir ağırlıktan "
                    "ya da kendi best.pt'nden devam eder; cihaz, erken durdurma ve katman "
                    "dondurma ayarlanabilir, kayıp ve mAP eğrisi epoch epoch çizilir. "
                    "Başlamadan önce train/val sızıntısını denetler.",
        "ipuclari": [
            "İkinci turdan itibaren 'kendi modelimden devam et' ile önceki turun "
            "best.pt'sini seç; sıfırdan eğitmek hem zaman kaybı hem de öğrenileni atmaktır.",
            "Sızıntı uyarısını ciddiye al: train ve val aynı sahnenin karelerini "
            "paylaşıyorsa mAP gerçekte olduğundan yüksek çıkar ve model sahada seni yanıltır.",
            "Az veriyle ince ayarda ilk katmanları dondurmayı dene (10 civarı) — "
            "hazır modelin öğrendiği genel özellikler korunur.",
            "Erken durdurma açıkken epoch'u cömert ver: eğitim iyileşme durunca "
            "kendiliğinden biter, boşuna beklemezsin.",
        ],
    },
    {
        "anahtar": "hata_analizi",
        "ad": "Hata Analizi",
        "amblem": "◔",
        "modul": "boxify.araclar.hata_analizi",
        "ozet": "Model nerede yanılıyor + sırada ne etiketlenmeli",
        "aciklama": "Modeli etiketli sette koşturup kaçırma/uydurma/karışıklık döker; "
                    "aktif öğrenme sekmesi etiketlenecek en öğretici kareleri seçer.",
        "ipuclari": [
            "Skora değil hata dökümüne bak: 'hangi sınıf, hangi koşulda "
            "kaçıyor' sorusunun cevabı bir sonraki veri turunu belirler.",
            "Aktif öğrenme sekmesi, modelin en kararsız kaldığı kareleri öne "
            "çıkarır — rastgele kare etiketlemekten çok daha verimlidir.",
            "Az örnekli sınıfın hatası yüksekse çözüm çoğu zaman ayar değil, "
            "o sınıfa yeni örnek eklemektir.",
        ],
    },
    {
        "anahtar": "model_karsilastir",
        "ad": "Model Karşılaştır",
        "amblem": "⚖",
        "modul": "boxify.araclar.model_karsilastir",
        "ozet": "Aynı videoda 1-3 modeli ve seçilen sınıfları kıyasla",
        "aciklama": "Aynı video üzerinde 1-3 YOLO modelini çalıştırır; her modelin "
                    "bir veya birden fazla sınıfını ayrı ayrı açıp kapatır, "
                    "tespitleri yan yana bindirip karşılaştırma videosu üretir; model başına "
                    "tespit sayısı, ortalama güven ve hız özetini raporlar.",
        "ipuclari": [
            "Tüm modeller adil kıyaslansın diye kare önce ortak bir yüksekliğe "
            "küçültülür — panel yüksekliğini değiştirmek kıyası etkiler, imgsz'i değil.",
            "Uzun videoda örnekleme fps'ini düşük tut (ör. 2-5 fps): N model × "
            "her kare işlemek, tek modelli Oto Label'dan N kat daha yavaştır.",
            "Rapor sekmesindeki hız rakamları kabaca fikir verir; kesin ölçüm için "
            "Model Export'taki Hız Ölçümü'nü kullan.",
            "Modeller ortak ayarla koşarsa kıyas adil olur; 'bu modele özel ayar' "
            "sadece her modeli kendi en iyi ayarıyla görmek istediğinde açılmalı — "
            "açtığında rapor bunu ayrıca not eder.",
        ],
    },
    {
        "anahtar": "model_export",
        "ad": "Model Export",
        "amblem": "⇥",
        "modul": "boxify.araclar.model_export",
        "ozet": "Dağıtım biçimine çevir, hız ve sapmayı ölç",
        "aciklama": "ONNX / TensorRT / OpenVINO'ya aktarır, ısınmalı hız ölçümü yapar "
                    "(ortalama-medyan-p95), çalıştırma kapasitesini ve dönüşüm sapmasını raporlar.",
        "ipuclari": [
            "Hedef donanımda ölçüm yap: TensorRT ölçümü ancak dağıtım "
            "yapılacak GPU'da anlamlıdır, OpenVINO CPU'da öne geçer.",
            "Ortalama yerine p95 süresine bak — gerçek kullanımda seni "
            "yavaşlatan, en kötü kareler olur.",
            "Dönüşüm sapması raporunu atlamadan oku: hız kazancı, çıktılar "
            "orijinal modelden saparsa pahalıya mal olur.",
        ],
    },
]


def arac_bul(anahtar: str) -> dict:
    for a in ARACLAR:
        if a["anahtar"] == anahtar:
            return a
    raise KeyError(anahtar)
