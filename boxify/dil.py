"""Boxify dil eklentisi — TR/EN arayüz dili desteği.

Eklenti yaklaşımı: araç modüllerinin koduna dokunulmaz. İngilizce seçiliyken
PyQt'nin metin API'leri (QLabel/QPushButton kurucuları, setText, setToolTip,
QMessageBox, dosya diyaloğu başlıkları…) bir kez yamalanır ve her metin
SOZLUK'ten geçirilir. Sözlükte karşılığı olmayan metin olduğu gibi kalır,
bu yüzden yamalar veri taşıyan metinlere (dosya yolları, sınıf adları…)
zarar veremez. Sayaç ve durum mesajları gibi çalışma anında üretilen
metinler KALIPLAR'daki desenlerle çevrilir.

Dil ayarı ~/.config/boxify4/ayarlar.json dosyasında saklanır; değişiklik
uygulama yeniden başlatılınca bütünüyle etkinleşir (kenar çubuğundaki
TR/EN düğmeleri yeniden başlatmayı kendisi yapar).
"""

import json
import os
import re

AYAR_DIZIN = os.path.join(os.path.expanduser("~"), ".config", "boxify4")
AYAR_DOSYA = os.path.join(AYAR_DIZIN, "ayarlar.json")
DILLER = ("tr", "en")

_dil = "tr"
_yamalar_kuruldu = False


def dil_yukle() -> str:
    """Kayıtlı dili oku (yoksa/bozuksa tr)."""
    global _dil
    _dil = "tr"
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            kod = json.load(f).get("dil", "tr")
        if kod in DILLER:
            _dil = kod
    except Exception:
        pass
    return _dil


def dil_kaydet(kod: str):
    if kod not in DILLER:
        raise ValueError(kod)
    os.makedirs(AYAR_DIZIN, exist_ok=True)
    ayar = {}
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            ayar = json.load(f)
    except Exception:
        pass
    ayar["dil"] = kod
    with open(AYAR_DOSYA, "w", encoding="utf-8") as f:
        json.dump(ayar, f, ensure_ascii=False, indent=2)


def aktif_dil() -> str:
    return _dil


def tr(metin):
    """Metni aktif dile çevir; karşılığı yoksa olduğu gibi döndür."""
    if _dil == "tr" or not isinstance(metin, str) or not metin:
        return metin
    ceviri = SOZLUK.get(metin)
    if ceviri is not None:
        return ceviri
    for desen, kalip in KALIPLAR:
        m = desen.match(metin)
        if m:
            parcalar = tuple(tr(g) for g in m.groups())
            return kalip(m, parcalar) if callable(kalip) else kalip.format(*parcalar)
    return metin


def _cogul(sayi: str, tekil: str, cogul: str) -> str:
    return tekil if sayi == "1" else cogul


# ── Çalışma anı desenleri ────────────────────────────────────────────────────
# Sayaçlar ve durum mesajları f-string'le üretilir; birebir sözlük eşleşmesi
# tutmaz. Yakalanan gruplar tr()'den tekrar geçer (araç adları da çevrilir).
KALIPLAR = [(re.compile(d), k) for d, k in [
    (r"^•  (.+)$", "•  {}"),
    (r"^— (.+)$", "— {}"),
    # kenar çubuğu: "amblem + iki boşluk + araç adı" (ör. "✂  Video Kırpıcı")
    (r"^([✂▣⚡✎☰◔⇥⚖])  (.+)$", "{}  {}"),
    (r"^sürüm (.+)$", "version {}"),
    # Model Karşılaştır: yuva adı ipucu ve sınıf/kare sayaçları
    (r"^Panelde görünecek ad \(ör\. YOLOv8n\) — boşsa Model (.+)$",
     "Name shown on the panel (e.g. YOLOv8n) — Model {} if empty"),
    (r"^Tahmini işlenecek kare: ~(\d+)  \((\d+) çıkarım\)$",
     "Estimated frames to process: ~{}  ({} inferences)"),
    (r"^Tüm sınıflar açık \((\d+)\)$", "All classes on ({})"),
    (r"^(\d+)/(\d+) sınıf açık: (.+)$", "{}/{} classes on: {}"),
    (r"^Model (.+) seç$", "Choose model {}"),
    (r"^(.+) yükleniyor…$", "Loading {}…"),
    (r"^(.+) açılamadı$", "{} could not be opened"),
    (r"^(\d+) görsel$",
     lambda m, p: f"{p[0]} {_cogul(p[0], 'image', 'images')}"),
    (r"^(\d+) kayıt$",
     lambda m, p: f"{p[0]} {_cogul(p[0], 'record', 'records')}"),
    (r"^(\d+) klip$",
     lambda m, p: f"{p[0]} {_cogul(p[0], 'clip', 'clips')}"),
    (r"^(\d+) model$",
     lambda m, p: f"{p[0]} {_cogul(p[0], 'model', 'models')}"),
    (r"^(\d+) klip  →  (.+)$", "{} clips  →  {}"),
    (r"^(\d+) video eklendi: (.+)$", "{} videos added: {}"),
    (r"^(\d+) görsel bulundu\.$", "{} images found."),
    (r"^(\d+) görsel bulundu: (.+)$", "{} images found: {}"),
    (r"^(\d+) kare kaydedildi: (.+)$", "{} frames saved: {}"),
    (r"^✅ (\d+) kare kaydedildi\n📁 (.+)$", "✅ {} frames saved\n📁 {}"),
    (r"^(\d+) görsel kopyalandı → (.+)$", "{} images copied → {}"),
    (r"^(\d+) kayıt karantinaya taşındı → (.+)$",
     "{} records moved to quarantine → {}"),
    (r"^(\d+) kayıt taşındı — denetim tazeleniyor…$",
     "{} records moved — re-running inspection…"),
    (r"^(\d+) / (\d+) kayıt$", "{} / {} records"),
    (r"^Etiketli: (\d+) / (\d+)$", "Labeled: {} / {}"),
    (r"^Test: (\d+)%$", "Test: {}%"),
    (r"^(\d+) sınıf: (.+)$", "{} classes: {}"),
    (r"^Model hazır — (\d+) sınıf: (.+)$", "Model ready — {} classes: {}"),
    (r"^Sınıflar: (.+)$", "Classes: {}"),
    (r"^Model: (.+)$", "Model: {}"),
    (r"^Kaydedildi: (.+)$", "Saved: {}"),
    (r"^✔ Kaydedildi: (.+)$", "✔ Saved: {}"),
    (r"^Yüklendi: (.+)$", "Loaded: {}"),
    (r"^Aktarıldı: (.+)$", "Exported: {}"),
    (r"^Silindi: (.+)$", "Deleted: {}"),
    (r"^Gidildi: (.+)$", "Jumped to: {}"),
    (r"^İşleniyor: (\d+)/(\d+)$", "Processing: {}/{}"),
    (r"^Seçili aralık: (.+)$", "Selected range: {}"),
    (r"^Hedef klasör: (.+)$", "Target folder: {}"),
    (r"^Aralık sonu: (.+)$", "End of range: {}"),
    (r"^ÖNİZLEME: (.+)$", "PREVIEW: {}"),
    (r"^Kareler çıkarılıyor → (.+)$", "Extracting frames → {}"),
    (r"^HATA: (.+)$", "ERROR: {}"),
    (r"^klasör açılamadı — (.+)$", "folder could not be opened — {}"),
    (r"^klip bulunamadı — (.+)$", "clip not found — {}"),
    (r"^kırpma başarısız — (.+)$", "trim failed — {}"),
    (r"^Oynatıcı — (.+)$", "Player — {}"),
]]


# ── Sözlük (TR → EN) ─────────────────────────────────────────────────────────
SOZLUK = {
    # ── Kabuk: kenar çubuğu, durum çubuğu ──
    "Nesne Tespiti Veri ve Model Atölyesi":
        "Object Detection Data & Model Workshop",
    "⌂  Ana Sayfa": "⌂  Home",
    "✦  İpuçları": "✦  Tips",
    "ARAÇLAR": "TOOLS",
    "Ana sayfa": "Home",
    "İpuçları": "Tips",
    "İpuçları — genel akış ve araç püf noktaları":
        "Tips — overall workflow and tool pointers",
    "Genel akış ve her aracın püf noktaları":
        "Overall workflow and each tool's key pointers",
    "Hoş geldin — soldaki çubuktan ya da kartlardan bir araç seç.":
        "Welcome — pick a tool from the sidebar or the cards.",
    "Nesne tespiti için veri seti,\netiketleme ve model atölyesi":
        "Dataset, labeling and model\nworkshop for object detection",
    "Araç yüklenirken hata oluştu (eksik bağımlılık olabilir):":
        "An error occurred while loading the tool (a dependency may be missing):",
    "Arayüz dili":
        "Interface language",
    "Dil değişikliği için uygulama yeniden başlatılacak. Devam edilsin mi?":
        "The application will restart to apply the language change. Continue?",
    "Dil değişikliği": "Language change",

    # ── Ana sayfa ──
    "Nesne tespiti için veri seti ve model atölyesi":
        "Dataset and model workshop for object detection",
    "Hangi nesneyle çalışırsan çalış — balon, araç, ürün, kusur — "
    "videodan hazır modele giden her adım tek çatı altında.":
        "Whatever object you work with — balloon, vehicle, product, defect — "
        "every step from video to a ready model, under one roof.",
    "Nereden başlayacağını bilmiyorsan soldaki İpuçları sayfasına göz at: "
    "genel akış ve her aracın püf noktaları orada anlatılıyor.":
        "Not sure where to start? Have a look at the Tips page on the left: "
        "the overall workflow and each tool's key pointers are explained there.",

    # ── Araç kaydı: adlar ──
    "Video Kırpıcı": "Video Trimmer",
    "Kare Alıcı": "Frame Grabber",
    "Oto Label": "Auto Label",
    "Veri Denetçi": "Data Inspector",
    "Hata Analizi": "Error Analysis",
    "Model Karşılaştır": "Model Comparison",

    # ── Araç kaydı: özetler ──
    "Videodan işe yarayan zaman aralıklarını kes":
        "Cut the useful time ranges out of your videos",
    "Kliplerden kare (fotoğraf) çıkar":
        "Extract frames (photos) from clips",
    "Mevcut modelle kareleri ön etiketle":
        "Pre-label frames with an existing model",
    "Etiketleri elle düzelt / tamamla":
        "Fix / complete labels by hand",
    "Veriyi denetle, kopyaları ayıkla, sızıntısız böl":
        "Inspect data, weed out duplicates, split without leakage",
    "Model nerede yanılıyor + sırada ne etiketlenmeli":
        "Where the model fails + what to label next",
    "Aynı videoda 1-3 modeli ve seçilen sınıfları kıyasla":
        "Compare 1-3 models and the selected classes on the same video",
    "Dağıtım biçimine çevir, hız ve sapmayı ölç":
        "Convert to deployment format, measure speed and drift",

    # ── Araç kaydı: açıklamalar ──
    "Uzun video kayıtlarını oynatıp ilgilendiğin zaman aralıklarını "
    "işaretler, ffmpeg ile kayıpsız klipler olarak dışa aktarır.":
        "Play long recordings, mark the time ranges you care about and "
        "export them as lossless clips with ffmpeg.",
    "Klipleri izleyip tek tek kare yakalar ya da belirli fps ile "
    "toplu kare çıkarır; eğitim verisinin ham fotoğrafları burada doğar.":
        "Watch clips and capture single frames, or batch-extract at a given "
        "fps; the raw photos of your training data are born here.",
    "Eldeki YOLO modeliyle kareleri tarar, YOLO txt etiketleri üretir. "
    "Düşük güven eşiğiyle çalıştırıp elle düzeltmek en hızlı yoldur.":
        "Scans frames with your existing YOLO model and produces YOLO txt "
        "labels. Running at a low confidence threshold and fixing by hand "
        "is the fastest route.",
    "Kutu çizme, taşıma ve sınıf atama arayüzü. Oto Label'ın "
    "ürettiklerini düzeltmek ve eksikleri tamamlamak için.":
        "An interface for drawing, moving and classifying boxes. For fixing "
        "what Auto Label produced and filling in the gaps.",
    "Bozuk etiketleri bulur, dHash ile yakın kopyaları gruplar, "
    "karantinaya taşır ve sahne sızıntısı olmayan train/val bölmesi üretir.":
        "Finds broken labels, groups near-duplicates with dHash, moves them "
        "to quarantine and produces a train/val split free of scene leakage.",
    "Modeli etiketli sette koşturup kaçırma/uydurma/karışıklık döker; "
    "aktif öğrenme sekmesi etiketlenecek en öğretici kareleri seçer.":
        "Runs the model on a labeled set and reports misses, hallucinations "
        "and confusions; the active-learning tab picks the most instructive "
        "frames to label next.",
    "Aynı video üzerinde 1-3 YOLO modelini çalıştırır; her modelin "
    "bir veya birden fazla sınıfını ayrı ayrı açıp kapatır, "
    "tespitleri yan yana bindirip karşılaştırma videosu üretir; model başına "
    "tespit sayısı, ortalama güven ve hız özetini raporlar.":
        "Runs 1-3 YOLO models on the same video; turns one or more classes of "
        "each model on and off individually, overlays the detections side by "
        "side into a comparison video, and reports per-model detection count, "
        "average confidence and speed.",
    "ONNX / TensorRT / OpenVINO'ya aktarır, ısınmalı hız ölçümü yapar "
    "(ortalama-medyan-p95), çalıştırma kapasitesini ve dönüşüm sapmasını raporlar.":
        "Exports to ONNX / TensorRT / OpenVINO, benchmarks with warm-up "
        "(mean-median-p95), reports serving capacity and conversion drift.",

    # ── Araç kaydı: ipuçları ──
    "Kaydın tamamını değil, nesnenin gerçekten göründüğü bölümleri kes; "
    "boş sahneler eğitime katkı sağlamaz.":
        "Cut the parts where the object actually appears, not the whole "
        "recording; empty scenes add nothing to training.",
    "Kesim kayıpsızdır (yeniden kodlama yok), bu yüzden uzun videolarda "
    "bile saniyeler sürer — çekinmeden bol parça al.":
        "Cutting is lossless (no re-encoding), so even long videos take "
        "seconds — don't hesitate to grab plenty of segments.",
    "Farklı ışık, açı ve arka plan içeren bölümleri özellikle dahil et; "
    "çeşitlilik modelin genellemesini doğrudan belirler.":
        "Deliberately include segments with different lighting, angles and "
        "backgrounds; variety directly determines how well the model "
        "generalizes.",
    "Toplu çıkarımda fps'i düşük tut (ör. 1-2 fps): ardışık kareler "
    "birbirinin neredeyse kopyasıdır ve veri setini şişirir.":
        "Keep the fps low in batch extraction (e.g. 1-2 fps): consecutive "
        "frames are near-copies of each other and bloat the dataset.",
    "Nadir görülen anlar (kısmi görünme, kesişme, bulanıklık) için tek "
    "kare yakalamayı kullan — bunlar en öğretici örneklerdir.":
        "Use single-frame capture for rare moments (partial visibility, "
        "overlap, blur) — these are the most instructive examples.",
    "Kareleri klip adıyla ilişkili klasörlerde tut; Veri Denetçi'nin "
    "sahne sızıntısız bölmesi bu gruplamadan yararlanır.":
        "Keep frames in folders tied to the clip name; Data Inspector's "
        "leak-free split takes advantage of this grouping.",
    "Güven eşiğini düşük tut (ör. 0.25): fazladan kutuyu silmek, "
    "kaçırılmış nesneyi sıfırdan çizmekten çok daha hızlıdır.":
        "Keep the confidence threshold low (e.g. 0.25): deleting an extra "
        "box is much faster than drawing a missed object from scratch.",
    "İlk turda hazır bir COCO modeli bile işe yarar; kendi modelin "
    "eğitildikçe ön etiketleme her turda daha isabetli olur.":
        "Even an off-the-shelf COCO model helps in the first round; as your "
        "own model trains, pre-labeling gets more accurate every round.",
    "Ön etiketler taslaktır — mutlaka Labelapp'te gözden geçir; "
    "denetlenmemiş oto etiketle eğitmek hataları kalıcılaştırır.":
        "Pre-labels are drafts — always review them in Labelapp; training "
        "on unreviewed auto labels makes the mistakes permanent.",
    "Kutuyu nesneye sıkıca oturt: bol pay bırakılmış kutular modelin "
    "konum hassasiyetini düşürür.":
        "Fit the box tightly to the object: boxes with generous margins "
        "reduce the model's localization accuracy.",
    "Sınıf tanımlarını baştan netleştir ve hep aynı kurala göre "
    "etiketle; tutarsız etiket, az etiketten daha zararlıdır.":
        "Pin down class definitions up front and always label by the same "
        "rule; inconsistent labels hurt more than few labels.",
    "Kısmen görünen nesneyi de etiketle — gerçek kullanımda nesneler "
    "çoğu zaman tam görünmez.":
        "Label partially visible objects too — in real use, objects are "
        "rarely fully visible.",
    "Eğitime başlamadan önce mutlaka buradan geç: bozuk tek bir etiket "
    "dosyası bütün eğitimi düşürebilir.":
        "Always pass through here before training: a single broken label "
        "file can crash the whole run.",
    "Yakın kopyaların aynı anda train ve val'e düşmesi başarıyı yapay "
    "olarak şişirir — sızıntısız bölme bunu engeller.":
        "Near-duplicates landing in both train and val artificially "
        "inflates the score — the leak-free split prevents this.",
    "Hiçbir dosya silinmez, sorunlular karantina klasörüne taşınır; "
    "yanlış ayıklandığını düşündüğünü geri alabilirsin.":
        "No file is ever deleted; problem records are moved to the "
        "quarantine folder, so you can restore anything weeded out by "
        "mistake.",
    "Skora değil hata dökümüne bak: 'hangi sınıf, hangi koşulda "
    "kaçıyor' sorusunun cevabı bir sonraki veri turunu belirler.":
        "Look at the error breakdown, not the score: the answer to 'which "
        "class is missed under which condition' decides the next data "
        "round.",
    "Aktif öğrenme sekmesi, modelin en kararsız kaldığı kareleri öne "
    "çıkarır — rastgele kare etiketlemekten çok daha verimlidir.":
        "The active-learning tab surfaces the frames the model is least "
        "sure about — far more efficient than labeling random frames.",
    "Az örnekli sınıfın hatası yüksekse çözüm çoğu zaman ayar değil, "
    "o sınıfa yeni örnek eklemektir.":
        "If a low-sample class has high error, the fix is usually not "
        "tuning but adding new examples of that class.",
    "Tüm modeller adil kıyaslansın diye kare önce ortak bir yüksekliğe "
    "küçültülür — panel yüksekliğini değiştirmek kıyası etkiler, imgsz'i değil.":
        "So every model is compared fairly, the frame is first downscaled to "
        "a shared height — changing the panel height affects the comparison, "
        "not imgsz.",
    "Uzun videoda örnekleme fps'ini düşük tut (ör. 2-5 fps): N model × "
    "her kare işlemek, tek modelli Oto Label'dan N kat daha yavaştır.":
        "Keep the sampling fps low on long videos (e.g. 2-5 fps): processing "
        "N models × every frame is N times slower than single-model Auto Label.",
    "Rapor sekmesindeki hız rakamları kabaca fikir verir; kesin ölçüm için "
    "Model Export'taki Hız Ölçümü'nü kullan.":
        "The speed numbers in the Report tab are a rough guide; use Model "
        "Export's Benchmark for a precise measurement.",
    "Modeller ortak ayarla koşarsa kıyas adil olur; 'bu modele özel ayar' "
    "sadece her modeli kendi en iyi ayarıyla görmek istediğinde açılmalı — "
    "açtığında rapor bunu ayrıca not eder.":
        "The comparison is fair when the models run with the common settings; "
        "turn on 'settings specific to this model' only when you want to see "
        "each model at its own best settings — the report notes it when you do.",
    "Hedef donanımda ölçüm yap: TensorRT ölçümü ancak dağıtım "
    "yapılacak GPU'da anlamlıdır, OpenVINO CPU'da öne geçer.":
        "Benchmark on the target hardware: a TensorRT measurement is only "
        "meaningful on the deployment GPU, while OpenVINO wins on CPU.",
    "Ortalama yerine p95 süresine bak — gerçek kullanımda seni "
    "yavaşlatan, en kötü kareler olur.":
        "Look at the p95 time rather than the mean — in real use it's the "
        "worst frames that slow you down.",
    "Dönüşüm sapması raporunu atlamadan oku: hız kazancı, çıktılar "
    "orijinal modelden saparsa pahalıya mal olur.":
        "Don't skip the conversion-drift report: the speed gain costs "
        "dearly if outputs drift from the original model.",

    # ── İpuçları sayfası ──
    "Sistemin genel işleyişi ve her aracın püf noktaları.":
        "How the system works overall, plus each tool's key pointers.",
    "Sistem nasıl çalışır?": "How does the system work?",
    "Boxify, bir nesne tespit modelini sıfırdan üretime taşıyan döngünün "
    "araç kutusudur. Akış tipik olarak şöyle işler: videolarından işe yarayan "
    "bölümleri kesersin (Video Kırpıcı), bu kliplerden fotoğraf karesi "
    "çıkarırsın (Kare Alıcı), kareleri mevcut bir modelle ön etiketlersin "
    "(Oto Label), etiketleri elle düzeltip tamamlarsın (Labelapp), veri setini "
    "denetleyip train/val olarak bölersin (Veri Denetçi), YOLO ile eğitirsin, "
    "eğitilen modelin nerede yanıldığına bakarsın (Hata Analizi) ve hazır "
    "olduğunda dağıtım biçimine çevirirsin (Model Export).":
        "Boxify is the toolbox for the loop that takes an object detection "
        "model from zero to production. The flow typically goes like this: "
        "you cut the useful parts out of your videos (Video Trimmer), "
        "extract photo frames from those clips (Frame Grabber), pre-label "
        "the frames with an existing model (Auto Label), fix and complete "
        "the labels by hand (Labelapp), inspect the dataset and split it "
        "into train/val (Data Inspector), train with YOLO, see where the "
        "trained model fails (Error Analysis), and when it's ready, convert "
        "it to a deployment format (Model Export).",
    "Bu bir döngüdür, tek seferlik bir hat değil: Hata Analizi'nin gösterdiği "
    "zayıf noktalara göre yeni veri toplayıp tekrar eğitmek, en büyük sıçramayı "
    "getirir. İyi modeller genellikle 3-4 turda olgunlaşır.":
        "This is a loop, not a one-shot pipeline: collecting new data for "
        "the weak spots Error Analysis reveals and retraining brings the "
        "biggest jump. Good models usually mature in 3-4 rounds.",
    "Her adımı kullanmak zorunda değilsin. Elinde hazır fotoğraflar varsa "
    "doğrudan Oto Label veya Labelapp'ten başlayabilirsin; videoyla "
    "çalışmıyorsan ilk iki araca hiç girmezsin.":
        "You don't have to use every step. If you already have photos, you "
        "can start directly from Auto Label or Labelapp; if you're not "
        "working from video, you never touch the first two tools.",
    "Az ama temiz veri, çok ama kirli veriden iyidir: tutarlı etiketlenmiş "
    "birkaç yüz kare, özensiz binlerce kareden daha iyi model çıkarır.":
        "Less but clean data beats more but dirty data: a few hundred "
        "consistently labeled frames produce a better model than thousands "
        "of sloppy ones.",
    "Her araç ilk tıklamada yüklenir ve sekme değişse bile arka planda "
    "çalışmaya devam eder; uzun bir işlem sürerken başka araca geçebilirsin.":
        "Each tool loads on first click and keeps working in the background "
        "even when you switch tabs; you can move to another tool while a "
        "long job runs.",
    "Hiçbir araç dosya silmez — temizlik daima karantina klasörüne taşımadır, "
    "yanlışlıkla veri kaybetmezsin.":
        "No tool ever deletes files — cleanup always means moving to the "
        "quarantine folder, so you can't lose data by accident.",
    "Eğitim adımı uygulamanın dışındadır: Veri Denetçi'nin ürettiği data.yaml "
    "ile 'yolo train data=.../data.yaml model=yolo11n.pt' komutu yeterlidir.":
        "The training step lives outside the app: with the data.yaml that "
        "Data Inspector produces, the command "
        "'yolo train data=.../data.yaml model=yolo11n.pt' is all you need.",

    # ── Ortak / menüler ──
    "Dosya": "File",
    "Çıkış": "Exit",
    "Kaydet": "Save",
    "Tümünü Kaydet": "Save All",
    "Hata": "Error",
    "Uyarı": "Warning",
    "Bilgi": "Info",
    "İptal": "Cancel",
    "Sil": "Delete",
    "Seç…": "Choose…",
    "Klasör Seç": "Choose Folder",
    "Klasör Seç…": "Choose Folder…",
    "Klasörü Aç": "Open Folder",
    "Klasör Aç": "Open Folder",
    "Log": "Log",
    "Rapor": "Report",
    "Sonuç": "Result",
    "Model": "Model",
    "Model seç": "Choose model",
    "Otomatik": "Automatic",
    "GPU (cuda:0)": "GPU (cuda:0)",
    "CPU": "CPU",
    "Hedef klasör": "Target folder",
    "Hedef Klasör": "Target Folder",
    "Varsayılan": "Default",
    "İşlem sürüyor.": "A job is already running.",
    "İşlem sürüyor — bitmesini bekle.":
        "A job is running — wait for it to finish.",
    "İptal isteniyor…": "Cancelling…",
    "Kaydedildi.": "Saved.",
    "Tüm Dosyalar (*)": "All Files (*)",

    # ── Video Kırpıcı ──
    "Dosya > Video Aç ile başlayın   |   Boşluk: oynat/durdur, ←/→: 1 sn, "
    ",/.: 1 kare, S/E: nokta ayarla, Shift+S / Shift+E: noktaya git":
        "Start with File > Open Video   |   Space: play/pause, ←/→: 1 s, "
        ",/.: 1 frame, S/E: set point, Shift+S / Shift+E: go to point",
    "Video Aç": "Open Video",
    "Klasörden Ekle": "Add from Folder",
    "Videolar": "Videos",
    "▶  Oynat": "▶  Play",
    "⏸  Duraklat": "⏸  Pause",
    "Kırpma Noktaları": "Trim Points",
    "Şimdiki An": "Current Time",
    "Oynatıcının şimdiki konumunu başlangıç yap (S)":
        "Use the player's current position as the start (S)",
    "Oynatıcının şimdiki konumunu bitiş yap (E)":
        "Use the player's current position as the end (E)",
    "⤒ Başlangıca Git": "⤒ Go to Start",
    "Oynatıcıyı başlangıç noktasına al (Shift+S)":
        "Move the player to the start point (Shift+S)",
    "Bitişe Git ⤒": "Go to End ⤒",
    "Oynatıcıyı bitiş noktasına al (Shift+E)":
        "Move the player to the end point (Shift+E)",
    "Seçili aralık: —": "Selected range: —",
    "Sadece seçili aralığı oynat": "Play only the selected range",
    "Açıkken oynatma başlangıç noktasından başlar ve bitişte durur.\n"
    "Noktaları sonradan değiştirirsen yeni aralık hemen geçerli olur.\n"
    "Kapatınca video normal, baştan sona oynar.":
        "When on, playback starts at the start point and stops at the end.\n"
        "If you change the points later, the new range takes effect "
        "immediately.\nWhen off, the video plays normally from start to end.",
    "Hassas (yeniden kodla)": "Precise (re-encode)",
    "Hızlı (kopyala)": "Fast (copy)",
    "✂  Kırp ve Kaydet": "✂  Trim and Save",
    "Kırpma Hatası": "Trim Error",
    "ffmpeg eksik": "ffmpeg missing",
    "Başlangıç (dd:ss.ms)": "Start (mm:ss.ms)",
    "Bitiş (dd:ss.ms)": "End (mm:ss.ms)",
    "Kesim modu": "Cut mode",
    "Tam olarak istenen ms aralığı kesilir (H.264 yeniden kodlama, biraz yavaş).":
        "Cuts exactly the requested ms range (H.264 re-encode, a bit slow).",
    "Yeniden kodlama yok, çok hızlı; ama kesim en yakın keyframe'e kayar — "
    "klip istenenden uzun olabilir.":
        "No re-encoding, very fast; but the cut snaps to the nearest "
        "keyframe — the clip may be longer than requested.",
    "(video seçilince belirlenir)": "(set when a video is chosen)",
    "Kliplerin kaydedileceği klasörü seç":
        "Choose the folder where clips will be saved",
    "Videonun yanında, video adıyla klasör kullan":
        "Use a folder named after the video, next to it",
    "Kaydedilen Klipler": "Saved Clips",
    "Çift tıkla → klibi oynat": "Double-click → play the clip",
    "Seçili klibi diskten sil": "Delete the selected clip from disk",
    "0 klip": "0 clips",
    "Video Seç": "Choose Video",
    "Video Dosyaları (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v);;"
    "Tüm Dosyalar (*)":
        "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v);;"
        "All Files (*)",
    "Kliplerin kaydedileceği klasör": "Folder where clips will be saved",
    "Hedef klasör varsayılana döndü (video adıyla klasör).":
        "Target folder reset to default (folder named after the video).",
    "Dosya yok": "No file",
    "Video akışı yok": "No video stream",
    "Aralık kısıtlaması kapalı — video baştan sona oynar.":
        "Range restriction off — the video plays start to end.",
    "Aralık kısıtlaması açık (geçerli aralık girilince etkin).":
        "Range restriction on (takes effect once a valid range is entered).",
    "Klip önizlemesindesiniz — zaman almak için 'Kaynak Videoya Dön'.":
        "You are in clip preview — use 'Back to Source Video' to take times.",
    "Klip önizlemesindesiniz. Kırpmak için 'Kaynak Videoya Dön'.":
        "You are in clip preview. Use 'Back to Source Video' to trim.",
    "HATA: geçersiz zaman — format dd:ss.ms (örn 00:13.500)":
        "ERROR: invalid time — format mm:ss.ms (e.g. 00:13.500)",
    "Seçili aralık: geçersiz zaman": "Selected range: invalid time",
    "Seçili aralık: bitiş > başlangıç olmalı":
        "Selected range: end must be > start",
    "geçersiz zaman": "invalid time",
    "Önizleme modu": "Preview mode",
    "Başlangıç zamanı geçersiz.\nFormat: dd:ss.ms (örn: 00:13.500)":
        "Start time is invalid.\nFormat: mm:ss.ms (e.g. 00:13.500)",
    "Bitiş zamanı geçersiz.\nFormat: dd:ss.ms (örn: 00:22.000)":
        "End time is invalid.\nFormat: mm:ss.ms (e.g. 00:22.000)",
    "Bitiş zamanı başlangıçtan büyük olmalı.":
        "End time must be greater than the start.",
    "Aralık çok kısa (en az 50 ms).": "Range too short (at least 50 ms).",
    "Silmek için listeden bir klip seçin.":
        "Select a clip from the list to delete.",
    "Klibi sil": "Delete clip",
    "Bitiş, video süresine kısaltıldı.":
        "End was clamped to the video duration.",

    # ── Kare Alıcı ──
    "Kare Alıcı — Video → Dataset": "Frame Grabber — Video → Dataset",
    "Dosya > Video Aç ile başlayın": "Start with File > Open Video",
    "Kare Çıkarma Ayarları": "Frame Extraction Settings",
    "Belirli bir aralık kullan": "Use a specific range",
    "📷  Kareleri Çıkar ve Kaydet": "📷  Extract and Save Frames",
    "Son Çıkarma": "Last Extraction",
    "📁  Klasörü Aç": "📁  Open Folder",
    "Video Dosyaları (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv);;"
    "Tüm Dosyalar (*)":
        "Video Files (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv);;"
        "All Files (*)",
    "Çıkarma başarısız.": "Extraction failed.",
    "Kaç saniyede bir kare?": "One frame every how many seconds?",
    "saniye": "seconds",
    "Görüntü formatı": "Image format",
    "Zaman formatı hatalı. Örnek: 00:13.500":
        "Time format is wrong. Example: 00:13.500",

    # ── Oto Label ──
    "Oto Label — YOLO ile otomatik etiketleme":
        "Auto Label — automatic labeling with YOLO",
    "Model, fotoğraf klasörü ve çıktı klasörünü seçip Başlat'a bas":
        "Choose the model, photo folder and output folder, then press Start",
    "Önizleme — soldaki listeden bir görsel seç":
        "Preview — pick an image from the list on the left",
    "Fotoğraflar": "Photos",
    "0 görsel": "0 images",
    "model.pt seç": "choose model.pt",
    "Sınıflar: —": "Classes: —",
    "Fotoğraf Klasörü": "Photo Folder",
    "Fotoğraf Klasörü…": "Photo Folder…",
    "fotoğrafların olduğu klasör": "folder containing the photos",
    "Alt klasörleri de tara": "Scan subfolders too",
    "Çıktı Klasörü": "Output Folder",
    "Çıktı Klasörü…": "Output Folder…",
    "Çıktı Klasörünü Aç": "Open Output Folder",
    "etiketlerin kaydedileceği klasör": "folder where labels will be saved",
    "Görselleri de kopyala (images/)": "Copy the images too (images/)",
    "Eğitime hazır yapı: images/ + labels/":
        "Training-ready layout: images/ + labels/",
    "data.yaml + classes.txt yaz": "Write data.yaml + classes.txt",
    "Tespit yoksa boş .txt yaz": "Write an empty .txt when nothing is detected",
    "Negatif örnek olarak eğitimde kullanılır":
        "Used in training as a negative example",
    "Çizimli önizlemeleri kaydet (predictions/)":
        "Save annotated previews (predictions/)",
    "Kontrol için kutuları çizili kopyalar":
        "Copies with boxes drawn, for checking",
    "Zaten etiketlenmişleri atla": "Skip already-labeled images",
    "Yarıda kalan işi kaldığı yerden sürdürür":
        "Resumes an interrupted job where it left off",
    "txt'ye güven değerini de yaz": "Also write the confidence to the txt",
    "6. kolon olarak güven; ultralytics eğitimi bunu beklemez, "
    "sadece inceleme için":
        "Confidence as a 6th column; ultralytics training doesn't expect "
        "it, for inspection only",
    "Çıkarım Ayarları": "Inference Settings",
    "İşlerken önizleme göster": "Show preview while processing",
    "Kapatmak işlemi hızlandırır": "Turning it off speeds things up",
    "Kutucuğu işaretlenen sınıflar etiketlenir; hiçbiri işaretli değilse hepsi":
        "Checked classes get labeled; if none is checked, all of them",
    "▶  Etiketlemeyi Başlat": "▶  Start Labeling",
    "Model Seç…": "Choose Model…",
    "YOLO modeli seç": "Choose YOLO model",
    "YOLO modeli (*.pt *.engine *.onnx);;Tüm Dosyalar (*)":
        "YOLO model (*.pt *.engine *.onnx);;All Files (*)",
    "Fotoğrafların olduğu klasör": "Folder containing the photos",
    "Etiketlerin kaydedileceği klasör": "Folder where labels will be saved",
    "Sınıf filtresi (boş = hepsi)": "Class filter (empty = all)",
    "Model yok": "No model",
    "Geçerli bir model (.pt) seç.": "Choose a valid model (.pt).",
    "Fotoğraf yok": "No photos",
    "Fotoğraf klasörü seç (klasörde desteklenen görsel bulunamadı).":
        "Choose a photo folder (no supported images found in the folder).",
    "Çıktı klasörü yok": "No output folder",
    "Etiketlerin kaydedileceği klasörü seç.":
        "Choose the folder where labels will be saved.",
    "İptal isteniyor… (işlenen görsel bitince duracak)":
        "Cancelling… (will stop after the current image)",
    "Sınıflar okunamadı (Başlat'ta tekrar denenecek)":
        "Classes could not be read (will retry on Start)",
    "Aynı klasör": "Same folder",
    "Çıktı klasörü fotoğraf klasörüyle aynı.\n"
    "Görseller images/ altına kopyalanacak. Devam edilsin mi?":
        "The output folder is the same as the photo folder.\n"
        "Images will be copied under images/. Continue?",

    # ── Veri Denetçi ──
    "Veri Denetçi — YOLO veri seti kontrolü ve bölme":
        "Data Inspector — YOLO dataset checking and splitting",
    "Veri seti klasörünü seç → Denetle":
        "Choose the dataset folder → Inspect",
    "0 kayıt": "0 records",
    "Denetle": "Inspect",
    "Seçilenleri Karantinaya Al": "Quarantine Selected",
    "Görsel + etiketi _karantina/ klasörüne taşır (silmez)":
        "Moves image + label to the _karantina/ folder (does not delete)",
    "Kopya Fazlalıklarını Karantinaya Al": "Quarantine Duplicate Extras",
    "Her kopya grubunda ilk görsel kalır, gerisi taşınır":
        "The first image of each duplicate group stays, the rest are moved",
    "Seçili Dosya": "Selected File",
    "Veri Seti": "Dataset",
    "Veri Seti Kökü…": "Dataset Root…",
    "veri seti kökü (images/ + labels/)": "dataset root (images/ + labels/)",
    "görseller": "images",
    "etiketler (.txt)": "labels (.txt)",
    "Denetim": "Inspection",
    "Bundan küçük alanlı kutular şüpheli işaretlenir":
        "Boxes with a smaller area are flagged as suspicious",
    "Görselleri açıp bozuk olanları bul":
        "Open the images and find corrupt ones",
    "Yakın-kopyaları tara": "Scan for near-duplicates",
    "Hamming mesafesi: 0 = birebir aynı, 5 = çok benzer, 10+ = gevşek":
        "Hamming distance: 0 = identical, 5 = very similar, 10+ = loose",
    "🔍  Denetle": "🔍  Inspect",
    "Train / Val / Test Bölmesi": "Train / Val / Test Split",
    "Yakın-kopya grubu (önerilen)": "Near-duplicate group (recommended)",
    "Alt klasör adı": "Subfolder name",
    "Dosya adı: ilk _ öncesi": "File name: before the first _",
    "Gruplama yok (rastgele)": "No grouping (random)",
    "Aynı gruptaki görseller aynı bölüme gider.\nVideo karelerinde bu, "
    "val sızıntısını (aynı sahnenin hem train hem val'de olması) engeller.":
        "Images in the same group go to the same split.\nFor video frames "
        "this prevents val leakage (the same scene in both train and val).",
    "Kopya fazlalıklarını bölmeye alma":
        "Keep duplicate extras out of the split",
    "Her kopya grubundan sadece bir temsilci kullanılır":
        "Only one representative per duplicate group is used",
    "Sadece etiketi olan görseller": "Only images that have a label",
    "Liste dosyaları (train.txt/val.txt)": "List files (train.txt/val.txt)",
    "Klasöre kopyala": "Copy into folders",
    "Sembolik bağ (symlink)": "Symbolic link (symlink)",
    "Liste modu veriyi çoğaltmaz; ultralytics txt listeyi doğrudan okur":
        "List mode doesn't duplicate data; ultralytics reads the txt list "
        "directly",
    "bölme çıktı klasörü": "split output folder",
    "✂  Bölmeyi Oluştur": "✂  Create Split",
    "Raporu Kaydet…": "Save Report…",
    "Veri seti kökü": "Dataset root",
    "Görsel klasörü": "Image folder",
    "Etiket klasörü": "Label folder",
    "Bölme çıktı klasörü": "Split output folder",
    "Raporu kaydet": "Save report",
    "Metin (*.txt)": "Text (*.txt)",
    "Bölme tamam.": "Split done.",
    "Sınıflar: data.yaml/classes.txt bulunamadı (id'ler sayı olarak gösterilir)":
        "Classes: data.yaml/classes.txt not found (ids shown as numbers)",
    "Klasör yok": "No folder",
    "Görsel klasörünü seç.": "Choose the image folder.",
    "Önce denetle.": "Inspect first.",
    "Taşınacak kayıt yok.": "No records to move.",
    "Hiçbir kayıt taşınamadı (loga bak).":
        "No record could be moved (check the log).",
    "Veri yok": "No data",
    "Oran hatası": "Ratio error",
    "Oranların toplamı 0 olamaz.": "The ratios cannot sum to 0.",
    "Bölme çıktı klasörünü seç.": "Choose the split output folder.",
    "Boş": "Empty",
    "Bölünecek görsel kalmadı (filtreler çok sıkı).":
        "No images left to split (filters too strict).",

    # ── Hata Analizi ──
    "Hata Analizi — model nerede yanılıyor?":
        "Error Analysis — where does the model fail?",
    "Model seç → Değerlendirme veya Aktif Öğrenme sekmesinden başlat":
        "Choose a model → start from the Evaluation or Active Learning tab",
    "Referans etiketleri göster": "Show reference labels",
    "Seçilenleri Klasöre Kopyala…": "Copy Selected to Folder…",
    "Düzeltilecek / etiketlenecek görselleri ayrı klasöre çıkarır "
    "(varsa etiketiyle birlikte)":
        "Exports the images to fix / label into a separate folder "
        "(with their labels if present)",
    "İlk N Kaydı Kopyala…": "Copy First N Records…",
    "Listedeki en öncelikli N görseli çıkarır":
        "Exports the N highest-priority images in the list",
    "Seçili Görsel": "Selected Image",
    "eğitilmiş model.pt": "trained model.pt",
    "Çıkarım": "Inference",
    "Değerlendirme": "Evaluation",
    "Aktif Öğrenme": "Active Learning",
    "Bu eşikteki tahminler değerlendirilir (hattaki çalışma eşiğini kullan)":
        "Predictions at this threshold are evaluated (use your production "
        "threshold)",
    "Tahmin ile referansın 'aynı nesne' sayılması için gereken örtüşme":
        "Overlap required for a prediction and a reference to count as "
        "'the same object'",
    "🔍  Değerlendir": "🔍  Evaluate",
    "Tarama eşiği: düşük tut, zayıf tespitleri de görelim":
        "Scan threshold: keep it low so weak detections show up too",
    "Hiç tespit çıkmayan kareye eklenen öncelik puanı (olası kaçırma)":
        "Priority bonus added to frames with no detections (possible miss)",
    "⚡  Havuzu Sırala": "⚡  Rank the Pool",
    "En üstteki kareleri etiketle → yeniden eğit → tekrar sırala. "
    "Rastgele etiketlemeye göre aynı emekle daha çok kazanç.":
        "Label the top frames → retrain → rank again. More gain for the "
        "same effort than random labeling.",
    "Etiketli görsel klasörü": "Labeled image folder",
    "Etiketsiz havuz": "Unlabeled pool",
    "Görseller (etiketli set — genelde val)":
        "Images (labeled set — usually val)",
    "Etiketler": "Labels",
    "Etiketsiz havuz (kare klasörü)": "Unlabeled pool (frame folder)",
    "Geçerli bir model seç.": "Choose a valid model.",
    "Etiketli görsel klasörünü seç.": "Choose the labeled image folder.",
    "Etiket klasörünü seç.": "Choose the label folder.",
    "Görsel yok": "No images",
    "Klasörde görsel bulunamadı.": "No images found in the folder.",
    "Etiketsiz havuz klasörünü seç.": "Choose the unlabeled pool folder.",
    "Havuzda görsel bulunamadı.": "No images found in the pool.",
    "Bant hatası": "Band error",
    "Bandın altı üstünden küçük olmalı.":
        "The band's lower bound must be below its upper bound.",
    "Önce çalıştır.": "Run first.",
    "Kopyalanacak kayıt yok.": "No records to copy.",
    "Liste boş.": "The list is empty.",
    "Sınıflar okunamadı (çalıştırırken tekrar denenecek)":
        "Classes could not be read (will retry when running)",

    # ── Araçlar arası ortak ayar etiketleri ──
    "Güven eşiği (conf)": "Confidence threshold (conf)",
    "Güven eşiği": "Confidence threshold",
    "Görsel boyutu": "Image size",
    "Tahmini işlenecek kare: — (video/aralık seçilince hesaplanır)":
        "Estimated frames to process: — (computed once a video/range is chosen)",

    # ── Video Kırpıcı ──
    "⟵ Kaynak Videoya Dön": "⟵ Back to Source Video",

    # ── Veri Denetçi ──
    "Şüpheli (?)": "Suspicious (?)",
    "Yakın-kopya (»)": "Near-duplicate (»)",
    "Kopya eşiği": "Duplicate threshold",
    "Küçük kutu eşiği": "Small-box threshold",

    # ── Hata Analizi ──
    "En kötüden iyiye": "Worst to best",
    "Kaçırılan var (FN)": "Has misses (FN)",
    "Sınıf karışıklığı": "Class confusion",
    "Hatasız": "No errors",
    "Belirsizlik bandı alt": "Uncertainty band low",
    "Belirsizlik bandı üst": "Uncertainty band high",
    "Boş kare önceliği": "Empty-frame priority",
    "Eşleştirme IoU": "Matching IoU",
    "Tarama eşiği": "Scan threshold",

    # ── Model Export ──
    "Biçim": "Format",
    "CPU iş parçacığı": "CPU threads",
    "Isınma": "Warm-up",
    "Kamera başına fps": "fps per camera",
    "Sapma için kare": "Frames for drift",
    "Ölçüm tekrarı": "Benchmark repeats",

    # ── Model Karşılaştır ──
    "Model Karşılaştır — aynı videoda birden çok YOLO modeli":
        "Model Comparison — multiple YOLO models on the same video",
    "Video seç, 1-3 model ekle, sınıfları ve ayarları düzenleyip Başlat'a bas.":
        "Choose a video, add 1-3 models, adjust the classes and settings and "
        "press Start.",
    "Video ve 1-3 model seçip Başlat'a bas":
        "Choose a video and 1-3 models, then press Start",
    "Video": "Video",
    "karşılaştırılacak video": "video to compare",
    "Süre / fps: —": "Duration / fps: —",
    "Belirli bir aralık kullan (yoksa tüm video)":
        "Use a specific range (otherwise the whole video)",
    "Başl.": "Start",
    "Bitiş": "End",
    "Örnekleme (fps)": "Sampling (fps)",
    "Videonun tamamı yerine saniyede bu kadar kare işlenir; N model × "
    "her kare çok yavaş olacağından uzun videolarda düşük tutmak iyidir":
        "This many frames per second are processed instead of the whole "
        "video; keep it low on long videos since N models × every frame "
        "gets slow fast",
    "Panel yüksekliği (px)": "Panel height (px)",
    "Tüm modeller aynı ölçekteki kareyi görsün diye kare önce bu "
    "yüksekliğe küçültülür (adil kıyas için)":
        "The frame is first downscaled to this height so every model sees "
        "the same scale (for a fair comparison)",
    "Tahmini işlenecek kare: —": "Estimated frames to process: —",
    "+ Model Ekle": "+ Add Model",
    "Karşılaştırmaya bir model daha kat (en fazla 3)":
        "Add one more model to the comparison (3 max)",
    "Bu modeli kaldır": "Remove this model",
    "Sınıflar: —": "Classes: —",
    "Ortak Çıkarım Ayarları": "Common Inference Settings",
    "Kendine özel ayarı olmayan modeller bunları kullanır.":
        "Models without their own settings use these.",
    "Görsel boyutu (imgsz)": "Image size (imgsz)",
    "Yarı hassasiyet (FP16)": "Half precision (FP16)",
    "Sadece GPU'da işe yarar; CPU'da yok sayılır":
        "Only helps on GPU; ignored on CPU",
    "Sınıftan bağımsız NMS": "Class-agnostic NMS",
    "Üst üste binen kutular sınıf farkı gözetmeden elenir":
        "Overlapping boxes are suppressed regardless of class",

    # ── Model Karşılaştır: modele özel ayarlar ve sınıf filtresi ──
    "İşaretli sınıflar çıkarıma katılır; işareti kaldırılan sınıflar bu "
    "model için kapatılır. Bir modelde birden fazla sınıf seçilebilir.":
        "Checked classes take part in inference; unchecked classes are turned "
        "off for this model. More than one class can be selected per model.",
    "Tüm sınıflar": "All classes",
    "Hiçbiri": "None",
    "Model seçilince sınıflar buraya gelir":
        "Classes appear here once a model is chosen",
    "Model açılıyor, lütfen bekle…": "Opening the model, please wait…",
    "Sınıflar okunuyor…": "Reading classes…",
    "Filtre uygulanamaz — tüm sınıflar açık sayılır":
        "No filter can be applied — all classes count as on",
    "Hiçbir sınıf açık değil — bu model hiçbir şey tespit etmez":
        "No class is on — this model will detect nothing",
    "Bu modele özel çıkarım ayarı kullan":
        "Use inference settings specific to this model",
    "Kapalıyken ortak ayarlar geçerlidir (adil kıyas). Açmak, her modeli "
    "kendi en iyi ayarıyla kıyaslamak istediğinde anlamlıdır; seçim "
    "rapora da yazılır.":
        "While off, the common settings apply (fair comparison). Turning it "
        "on makes sense when you want to compare each model at its own best "
        "settings; the choice is written into the report too.",
    "Sınıf seçilmedi": "No class selected",
    "GPU (Apple MPS)": "GPU (Apple MPS)",
    "Model çalışmadı": "Model did not run",
    "Görünüm ve Ek Çıktılar": "Appearance and Extra Outputs",
    "Çıktı klasörü": "Output folder",
    "Bu modeli karşılaştırmadan çıkar": "Drop this model from the comparison",
    "Mozaik düzeni": "Mosaic layout",
    "Yan yana (yatay)": "Side by side (horizontal)",
    "Alt alta (dikey)": "Stacked (vertical)",
    "Dikey video ya da 3 model kıyaslarken alt alta daha okunaklı olur":
        "Stacked reads better for portrait video or when comparing 3 models",
    "Kutu üstünde sınıf adı göster": "Show class name on the box",
    "Kutu üstünde güven değeri göster": "Show confidence on the box",
    "Karşılaştırma videosunu yaz": "Write the comparison video",
    "Kapatırsan sadece canlı önizleme ve rapor üretilir (daha hızlı)":
        "Turn it off to produce only the live preview and the report (faster)",
    "Çıktı": "Output",
    "karşılaştırma videosunun kaydedileceği klasör":
        "folder where the comparison video will be saved",
    "Model başına ayrı video da kaydet": "Also save a separate video per model",
    "karsilastirma.mp4 dışında her model için ayrı bir mp4 yazılır":
        "Besides karsilastirma.mp4, a separate mp4 is written per model",
    "▶ Sonucu Aç": "▶ Open Result",
    "karsilastirma.mp4'ü sistem oynatıcısında açar":
        "Opens karsilastirma.mp4 in the system player",
    "Karşılaştırma Raporu": "Comparison Report",
    "Raporu Kaydet…": "Save Report…",
    "▶  Karşılaştırmayı Başlat": "▶  Start Comparison",
    "Video Seç…": "Choose Video…",
    "Video yok": "No video",
    "Geçerli bir video seç.": "Choose a valid video.",
    "Yetersiz model": "Not enough models",
    "En az bir geçerli model seçmelisin.":
        "You must choose at least one valid model.",
    "Model eksik": "Model missing",
    "Çıktı klasörü yok": "No output folder",
    "Karşılaştırmanın kaydedileceği klasörü seç.":
        "Choose the folder where the comparison will be saved.",
    "Aralık hatalı": "Invalid range",
    "Başlangıç/bitiş zamanı geçersiz (format dd:ss.ms).":
        "The start/end time is invalid (format mm:ss.ms).",
    "Karşılaştırmanın kaydedileceği klasör":
        "Folder where the comparison will be saved",
    "Sonuç videosu henüz yok.": "The result video doesn't exist yet.",
    "Önce çıktı klasörü seç.": "Choose the output folder first.",
    "Önce bir karşılaştırma çalıştır.": "Run a comparison first.",
    "İptal isteniyor… (işlenen kare bitince duracak)":
        "Cancelling… (will stop after the current frame)",

    # ── Model Export ──
    "Model Export & Hız Ölçümü": "Model Export & Benchmark",
    "Model ekle → Dışa Aktar veya Hız Ölçümü":
        "Add a model → Export or Benchmark",
    "Modeller": "Models",
    "Kutucuğu işaretli modeller ölçüme girer.\nListedeki İLK işaretli model "
    "sapma karşılaştırmasında referanstır (genelde .pt).":
        "Checked models enter the benchmark.\nThe FIRST checked model in "
        "the list is the reference for drift comparison (usually the .pt).",
    "Model Ekle…": "Add Model…",
    "Çıkar": "Remove",
    "0 model": "0 models",
    "Ortak": "Common",
    "Eğitimdeki değeri kullan; export ile ölçüm aynı olmalı":
        "Use the training value; export and benchmark must match",
    "Dışa Aktar": "Export",
    "Hız Ölçümü": "Benchmark",
    "Sonucu Kaydet…": "Save Result…",
    "FP16 (half) — GPU'da ~2× hız": "FP16 (half) — ~2× speed on GPU",
    "INT8 — en hızlı, doğruluk düşebilir":
        "INT8 — fastest, accuracy may drop",
    "Dinamik giriş boyutu": "Dynamic input size",
    "ONNX sadeleştir (simplify)": "Simplify ONNX (simplify)",
    "Sadece TensorRT: derleme çalışma alanı":
        "TensorRT only: build workspace",
    "⇩  Dışa Aktar": "⇩  Export",
    "Aktarılan dosya bitince listeye kendiliğinden eklenir; sonra "
    "Hız Ölçümü'nde .pt ile yan yana karşılaştır.":
        "The exported file is added to the list automatically when done; "
        "then compare it side by side with the .pt in Benchmark.",
    "İlk çağrılar yavaştır, ölçüme katılmaz":
        "The first calls are slow and excluded from measurement",
    "0 = dokunma. CPU'da çok kameralı senaryoyu taklit etmek için 1-2 yap":
        "0 = leave as is. Set 1-2 on CPU to mimic a multi-camera scenario",
    "Kamera başına saniyede kaç kare işlenecek? Kapasite tahmini bundan "
    "hesaplanır":
        "How many frames per second per camera? Capacity is estimated "
        "from this",
    "Referansla sapmayı ölç (ilk model referans)":
        "Measure drift against the reference (first model is the reference)",
    "FP16/INT8 dönüşümü tahminleri bozdu mu? Etiket gerektirmez":
        "Did the FP16/INT8 conversion corrupt predictions? Needs no labels",
    "⏱  Hızı Ölç": "⏱  Measure Speed",
    "Model dosyaları": "Model files",
    "Modeller (*.pt *.onnx *.engine *.torchscript *.xml);;Tüm Dosyalar (*)":
        "Models (*.pt *.onnx *.engine *.torchscript *.xml);;All Files (*)",
    "data.yaml seç": "Choose data.yaml",
    "YAML (*.yaml *.yml)": "YAML (*.yaml *.yml)",
    "Ölçüm görselleri klasörü": "Benchmark images folder",
    "Sonucu kaydet": "Save result",
    "Listedeki seçili model dışa aktarılır":
        "The model selected in the list gets exported",
    "INT8 kalibrasyon verisi (data.yaml)":
        "INT8 calibration data (data.yaml)",
    "Ölçüm görselleri (klasör)": "Benchmark images (folder)",
    "Listeden dışa aktarılacak modeli seç.":
        "Select the model to export from the list.",
    "Kaynak biçim": "Source format",
    "Dışa aktarma kaynağı .pt olmalı.": "The export source must be a .pt.",
    "Dışa aktarma başarısız (loga bak).":
        "Export failed (check the log).",
    "Ölçülecek modelleri işaretle.": "Check the models to benchmark.",
    "Ölçüm görselleri klasörünü seç.":
        "Choose the benchmark images folder.",
    "Ölçüm sonucu yok (loga bak).": "No benchmark result (check the log).",
    "Önce ölçüm yap.": "Run a benchmark first.",
    "INT8 kalibrasyonu": "INT8 calibration",
    "INT8 için kalibrasyon verisi (data.yaml) seçilmedi.\nUltralytics kendi "
    "varsayılanını dener ve doğruluk daha çok düşebilir. Devam?":
        "No calibration data (data.yaml) chosen for INT8.\nUltralytics "
        "will try its own default and accuracy may drop further. Continue?",

    # ── Labelapp ──
    "Hoş geldiniz — Dosya > Klasör Aç ile başlayın":
        "Welcome — start with File > Open Folder",
    "Resimler": "Images",
    "Etiketli: 0 / 0": "Labeled: 0 / 0",
    "Resim Klasörü Seç": "Choose Image Folder",
    "Önce bir klasör açın.": "Open a folder first.",
    "Sağ panelden önce bir etiket sınıfı ekleyin.":
        "Add a label class from the right panel first.",
    "Etiket Sınıfları": "Label Classes",
    "+ Ekle": "+ Add",
    "Adını Değiştir": "Rename",
    "Renk": "Color",
    "Sol tık: bbox çiz\nSağ tık: menü (sil/sınıf)\nDel: seçili sil\n"
    "2× tık: adını değiştir\nA / ◀ : önceki\nD / ▶ : sonraki":
        "Left click: draw bbox\nRight click: menu (delete/class)\n"
        "Del: delete selected\nDouble click: rename\nA / ◀ : previous\n"
        "D / ▶ : next",
    "Yeni Sınıf": "New Class",
    "Sınıf adı:": "Class name:",
    "Yeni ad:": "New name:",
    "Eğitim Başlat...": "Start Training...",
    "Model Eğitimi": "Model Training",
    "Eğitim Ayarları": "Training Settings",
    "Veri Bölümü (export modunda)": "Data Split (in export mode)",
    "Test: 10%": "Test: 10%",
    "Çıktı klasörü seçilmedi": "No output folder chosen",
    "Eğitimi Başlat": "Start Training",
    "Durdur": "Stop",
    "Çıktı Klasörü Seç": "Choose Output Folder",
    "Hazır Veri Seti Tespit Edildi": "Existing Dataset Detected",
    "Bu veri setini direkt kullan (yeniden export etme)":
        "Use this dataset directly (don't re-export)",
    "Train:": "Train:",
    "Val:": "Val:",
    "Çıktı:": "Output:",
}


# ── PyQt yamaları ────────────────────────────────────────────────────────────
def yamalari_kur():
    """İngilizce modda Qt metin API'lerini tr() süzgecinden geçirir.

    QApplication oluşturulmadan ve herhangi bir pencere kurulmadan ÖNCE
    çağrılmalıdır. Türkçe modda hiçbir şey yapmaz (sıfır maliyet).
    """
    global _yamalar_kuruldu
    if _dil == "tr" or _yamalar_kuruldu:
        return
    _yamalar_kuruldu = True

    from PyQt5 import QtWidgets

    def suz(deger):
        if isinstance(deger, str):
            return tr(deger)
        if isinstance(deger, (list, tuple)):
            return [tr(x) if isinstance(x, str) else x for x in deger]
        return deger

    def metot_sar(snf, ad):
        orijinal = getattr(snf, ad, None)
        if orijinal is None:
            return
        def sarilmis(self, *args, **kw):
            return orijinal(self, *(suz(a) for a in args), **kw)
        setattr(snf, ad, sarilmis)

    def kurucu_sar(snf):
        orijinal = snf.__init__
        def sarilmis(self, *args, **kw):
            # QAction(ikon, metin, üst) gibi aşırı yüklemeler için tüm
            # string argümanlar süzülür; string olmayanlara dokunulmaz
            orijinal(self, *(tr(a) if isinstance(a, str) else a
                             for a in args), **kw)
        snf.__init__ = sarilmis

    def statik_sar(snf, ad):
        orijinal = getattr(snf, ad, None)
        if orijinal is None:
            return
        def sarilmis(*args, **kw):
            return orijinal(*(suz(a) for a in args), **kw)
        setattr(snf, ad, staticmethod(sarilmis))

    W = QtWidgets
    # Kurucusuna metin alan yaygın öğeler
    for snf in (W.QLabel, W.QPushButton, W.QCheckBox, W.QRadioButton,
                W.QGroupBox, W.QToolButton, W.QMenu, W.QAction):
        kurucu_sar(snf)

    # Metin ayarlayan metotlar (veri taşıyanlar — QLineEdit.setText gibi —
    # bilerek yamalanmaz; sözlük eşleşmese bile onlara hiç dokunulmasın)
    metot_sar(W.QWidget, "setWindowTitle")
    metot_sar(W.QWidget, "setToolTip")
    metot_sar(W.QWidget, "setStatusTip")
    metot_sar(W.QWidget, "setWhatsThis")
    metot_sar(W.QLabel, "setText")
    metot_sar(W.QAbstractButton, "setText")
    metot_sar(W.QAction, "setText")
    metot_sar(W.QGroupBox, "setTitle")
    metot_sar(W.QStatusBar, "showMessage")
    metot_sar(W.QTabWidget, "addTab")
    metot_sar(W.QTabWidget, "setTabText")
    metot_sar(W.QTabWidget, "setTabToolTip")
    metot_sar(W.QComboBox, "addItem")
    metot_sar(W.QComboBox, "addItems")
    metot_sar(W.QComboBox, "setItemText")
    metot_sar(W.QLineEdit, "setPlaceholderText")
    metot_sar(W.QTextEdit, "setPlaceholderText")
    metot_sar(W.QPlainTextEdit, "setPlaceholderText")
    metot_sar(W.QMenu, "addMenu")
    metot_sar(W.QMenu, "addAction")
    metot_sar(W.QMenuBar, "addMenu")
    metot_sar(W.QTableWidget, "setHorizontalHeaderLabels")
    metot_sar(W.QTableWidget, "setVerticalHeaderLabels")
    metot_sar(W.QTreeWidget, "setHeaderLabels")
    metot_sar(W.QProgressBar, "setFormat")
    metot_sar(W.QProgressDialog, "setLabelText")
    metot_sar(W.QProgressDialog, "setCancelButtonText")
    metot_sar(W.QMessageBox, "setText")
    metot_sar(W.QMessageBox, "setInformativeText")
    metot_sar(W.QMessageBox, "setDetailedText")
    metot_sar(W.QDockWidget, "setWindowTitle")

    # Statik diyaloglar (başlık + metin/filtre argümanları)
    for ad in ("information", "warning", "critical", "question", "about"):
        statik_sar(W.QMessageBox, ad)
    for ad in ("getOpenFileName", "getOpenFileNames", "getSaveFileName",
               "getExistingDirectory"):
        statik_sar(W.QFileDialog, ad)
    for ad in ("getText", "getItem", "getInt", "getDouble"):
        statik_sar(W.QInputDialog, ad)
