# Testler

```bash
./testler/calistir.sh          # hepsi
./testler/calistir.sh hizli    # ekran gerektirenleri atla (CI / ssh)
python testler/test_bolme.py   # tek test
```

Testler dış veri istemez: ihtiyaç duydukları kare, video ve etiketleri kendileri
üretip geçici klasörde tutar, sonunda siler. Depoya hiçbir şey yazmazlar.

Gerçek model gerektiren yerlerde `testler/sahte/ultralytics` devreye girer.
Amaç modelin doğruluğunu ölçmek değil — **Boxify'ın o modelle doğru konuşup
konuşmadığını** sınamak. Ağır indirmeler ve dakikalarca süren koşular olmadan
her değişiklikte çalışabilmeleri bu sayede mümkün.

## Her test neyin nöbetçisi

Bu testlerin çoğu, gerçekten yaşanmış bir hatanın peşinden yazıldı. Aşağıda
"neyi kontrol ediyor"un yanında **hangi hatayı bir daha yaşatmıyor** da var,
çünkü bir testi silmenin ya da gevşetmenin bedeli ancak böyle görülür.

| Test | Neyi korur |
|---|---|
| `test_bolme.py` | **Sızıntısız bölme.** Labelapp'in veri seti dışa aktarımı bir zamanlar `random.shuffle` ile bölüyordu; görseller ardışık video karelerinden geldiği için aynı an hem train'e hem val'e düşüyor, mAP şişiyor ve model ezberlediği hâlde iyi görünüyordu. Test önce gruplamasız bölmenin gerçekten sızdırdığını doğrular (testin kendisi anlamlı mı), sonra gruplamayla sıfır sızıntı olduğunu. |
| `test_birlestir.py` | **Sınıf eşleme.** İki veri setinde `0` farklı şey demek olabilir (`0=kamyon` / `0=tır`). Üst üste kopyalamak etiketleri sessizce bozar. Test çakışan id'lerin doğru yeniden numaralandığını, `(atla)` seçilen sınıfın kutularının düştüğünü ve dosya adı çakışmasının çözüldüğünü sınar. |
| `test_tiklama.py` | **Fare isabeti.** Araçlar üst düzey `QMainWindow` olarak doğuyor; `setWindowFlags(Qt.Widget)` gömmeden önce çağrılırsa yerel pencere ayakta kalıyor ve isabet yüzlerce piksel ötede aranıyordu — hiçbir düğmeye basılamıyordu. Gerçek ekran ister; başsız ortamda kendini atlar. |
| `test_kabuk.py` | **Araç geçişleri.** Dokuz aracın da yüklendiğini, ana pencerenin alt boyut sınırının araçlar yüzünden büyümediğini ve geçişlerin takılmadığını ölçer. |
| `test_asenkron.py` | **Donma.** `from ultralytics import YOLO` arayüz iş parçacığında çağrılırsa pencere saniyelerce kilitleniyordu. Sınıf adlarının hâlâ arka planda okunduğunu doğrular. |
| `test_platform.py` | **macOS / Linux / Windows eşitliği.** Üç platformu taklit ederek cihaz seçeneklerini (Apple'da MPS, ötekilerde CUDA), ffmpeg kurulum ipuçlarını, GStreamer düzeltmesinin yalnızca Linux'ta çalıştığını ve eğitim yükleyici varsayılanını sınar. |
| `test_tema.py` | **Dört kombinasyon:** {TR, EN} × {açık, koyu}. Her birinde sekiz aracın açıldığını, çevrilmemiş metin kalmadığını ve koyu zeminde koyu metin olmadığını denetler. Ayrıca dil/tema/yol ayarlarının aynı dosyada birbirini ezmediğini. |
| `test_yol.py` | **Yol hafızası.** Diyalogların son klasörü hatırladığını, alanların birbirine karışmadığını, çağıranın verdiği başlangıcın ezilmediğini ve silinmiş klasörlerin elendiğini sınar. |
| `test_ceviri.py` | **İngilizce eksiksiz mi.** Araçların görünen metinlerinde Türkçe karakter kalmadığını tarar. |
| `test_karsilastir.py` | **Model Karşılaştır uçtan uca.** Sınıf filtresi, modele özel ayar, tek modelle çalışma, hiç sınıf seçilmeyince uyarı, sınıfsız model. |
| `test_dugmeler.py` | **Erişilebilirlik.** Zorunlu düğmelerin ilk bakışta (kaydırmadan) görünür olduğunu doğrular. |
| `test_gizleme.py` | **Arka planda medya.** Sayfa gizlenince `hideEvent`in kaydırma kutusundan geçip araca ulaştığını — yoksa görünmeyen video çözülmeye devam eder. |

## Yeni test eklerken

`ortak.py` içindekileri kullan:

- `yolu_kur(sahte_ultralytics=True/False)` — import yolunu ayarlar, offscreen'e geçer
- `sahne_kareleri(kok)` — video benzeri kareler üretir (aynı sahne yakın, farklı sahne uzak)
- `veri_seti(kok, siniflar)` — images/ + labels/ + data.yaml
- `video_uret(yol)` — küçük bir mp4
- `Rapor` — `kontrol(kosul, aciklama)` ile satır satır sonuç, `bitir()` çıkış kodu döndürür

`sahne_kareleri` üzerine bir not: sahte kare üretmek göründüğünden inceliklidir.
Rastgele gürültüden kare üretilirse komşu kareler dHash'e göre birbirinden
**uzak** düşer — gerçek videoda ise çok yakındırlar. Düz renkli bloklar da
işe yaramaz: dHash görüntüyü 9x8'e indirip yatay komşuları karşılaştırır, geniş
düz alanlarda komşu hücreler neredeyse eşit çıkar ve en küçük gürültü
karşılaştırmayı rastgele çevirir. Bu yüzden üretilen sahnelerin zemini
**dokuludur** ve sahne kimliği yapısaldır. Ölçülen sonuç gerçek video kareleriyle
aynı ölçekte: aynı sahne 0–1, farklı sahne 30+ Hamming mesafesi.
