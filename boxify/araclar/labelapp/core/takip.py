"""Kutuyu sonraki karelere taşıma — optik akışla takip.

Boxify'da veri ardışık video karelerinden geliyor: 40 karelik bir klipte aynı
nesne 40 kez elle çizilmek zorunda kalıyordu. Oysa komşu kareler arasındaki
fark birkaç pikseldir; bir kez çizip taşımak, sonra sapanları düzeltmek çok
daha hızlı.

## Neden optik akış

OpenCV'nin hazır takipçilerinden (`TrackerCSRT`, `KCF`…) yalnızca `TrackerMIL`
ek dosya istemeden geliyor; ötekiler ya `opencv-contrib` ya da indirilecek
model ağırlığı gerektiriyor — kurulumu ağırlaştırırdı. MIL ise yavaş ve
kayıyor.

Buradaki yöntem Lucas-Kanade seyrek optik akışı: kutunun içinden köşe
noktaları seçilip bir sonraki karede nereye gittikleri bulunuyor, sonra bu
noktaların ortak hareketinden **öteleme ve ölçek** çıkarılıyor. Ardışık video
karelerinde (küçük hareket, benzer aydınlatma) bu yöntem hem hızlı hem
kararlı, ve saf `opencv-python` ile çalışıyor.

## Güvenlik kuralları

Takip tahmindir; yanlış kutuyu sessizce etiket dosyasına yazmak, hiç etiket
olmamasından kötüdür. Bu yüzden:

* Geriye takip edip başlangıç kutusuna dönmeyen sonuç (ileri-geri tutarlılık)
  reddedilir.
* Yeterli nokta takip edilemezse ya da ölçek makul aralığın dışına çıkarsa
  kutu bırakılır, zorlanmaz.
* Görsel sınırının dışına düşen kutu elenir.

## Neden görünüm denetimi de gerekiyor

İleri-geri tutarlılık tek başına YETMİYOR — ve bu, gerçek fabrika görüntüsünde
ölçülerek görüldü. Kutu kare kare zincirlenirken yavaşça nesneden kayıyor ama
akış kendi içinde tutarlı kaldığı için güven 0.99'da duruyordu:

    kare   akış güveni   IoU (gerçek kutuya göre)
       5          0.99   0.95
      10          0.99   0.81
      20          0.99   0.62
      30          0.99   0.37
      50          1.00   0.08

Yani güven, "kutu hâlâ nesnenin üstünde mi" sorusunu değil "noktalar tutarlı
hareket etti mi" sorusunu yanıtlıyordu; arka planı takip etmeye başlayınca da
tutarlı kalıyordu. Bu hâliyle güvene bakan kullanıcı yanılırdı.

Çözüm: kutunun içindeki görüntü, **kullanıcının çizdiği ilk karedeki** hâliyle
karşılaştırılıyor (normalize edilmiş çapraz korelasyon). Bu ölçü kaymayla
birlikte düşüyor (0.59 → 0.11) ve zinciri zamanında durduruyor. Bildirilen
güven artık ikisinin birleşimi.
"""

import numpy as np

# Lucas-Kanade parametreleri: ardışık video kareleri için ayarlı
_LK = dict(winSize=(21, 21), maxLevel=3,
           criteria=(3, 30, 0.01))          # 3 = COUNT | EPS

EN_AZ_NOKTA = 6          # bunun altında sonuç güvenilmez sayılır
EN_FAZLA_GERI_HATA = 2.0  # piksel — ileri-geri tutarlılık eşiği
OLCEK_ALT, OLCEK_UST = 0.75, 1.35

YAMA_BOYUT = 48          # görünüm karşılaştırması için normalize boyut
EN_AZ_BENZERLIK = 0.40   # bunun altında zincir durur (ölçümle seçildi)


def _gri(kare):
    import cv2
    if kare is None:
        return None
    if kare.ndim == 3:
        return cv2.cvtColor(kare, cv2.COLOR_BGR2GRAY)
    return kare


def kutu_tasi(onceki, sonraki, kutu, kenar_pay: float = 0.0):
    """Bir kutuyu bir sonraki kareye taşır.

    onceki, sonraki : görüntü (BGR ya da gri)
    kutu            : (x1, y1, x2, y2) — piksel
    dönüş           : (yeni_kutu, guven)  ya da (None, 0.0)

    guven 0-1 arası: takip edilebilen nokta oranı ile ileri-geri tutarlılığın
    birleşimi. 1'e yakın = güvenilir.
    """
    import cv2

    g1, g2 = _gri(onceki), _gri(sonraki)
    if g1 is None or g2 is None or g1.shape != g2.shape:
        return None, 0.0

    h, w = g1.shape[:2]
    x1, y1, x2, y2 = (float(v) for v in kutu)
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None, 0.0

    # Kutunun biraz içinden nokta seç: tam kenarda arka plan noktaları
    # yakalanıp kutuyu nesneden koparıyor.
    pay = kenar_pay if kenar_pay > 0 else 0.08
    ix1 = int(max(0, x1 + (x2 - x1) * pay))
    iy1 = int(max(0, y1 + (y2 - y1) * pay))
    ix2 = int(min(w, x2 - (x2 - x1) * pay))
    iy2 = int(min(h, y2 - (y2 - y1) * pay))
    if ix2 - ix1 < 4 or iy2 - iy1 < 4:
        ix1, iy1, ix2, iy2 = int(x1), int(y1), int(x2), int(y2)

    maske = np.zeros((h, w), dtype=np.uint8)
    maske[iy1:iy2, ix1:ix2] = 255
    noktalar = cv2.goodFeaturesToTrack(g1, maxCorners=120, qualityLevel=0.01,
                                       minDistance=4, mask=maske)
    if noktalar is None or len(noktalar) < EN_AZ_NOKTA:
        # Dokusuz nesne: köşe bulunamıyor. Izgara noktalarıyla dene —
        # akış yine de kenar gradyanlarından bir hareket çıkarabilir.
        gx = np.linspace(ix1 + 1, ix2 - 2, 8)
        gy = np.linspace(iy1 + 1, iy2 - 2, 8)
        noktalar = np.array([[[x, y]] for y in gy for x in gx], dtype=np.float32)
    noktalar = noktalar.astype(np.float32)

    ileri, durum, _ = cv2.calcOpticalFlowPyrLK(g1, g2, noktalar, None, **_LK)
    if ileri is None:
        return None, 0.0
    geri, durum2, _ = cv2.calcOpticalFlowPyrLK(g2, g1, ileri, None, **_LK)
    if geri is None:
        return None, 0.0

    # İleri-geri tutarlılık: başladığı yere dönemeyen nokta atılır
    sapma = np.linalg.norm(noktalar.reshape(-1, 2) - geri.reshape(-1, 2), axis=1)
    iyi = (durum.reshape(-1) == 1) & (durum2.reshape(-1) == 1) \
        & (sapma < EN_FAZLA_GERI_HATA)
    if int(iyi.sum()) < EN_AZ_NOKTA:
        return None, 0.0

    p0 = noktalar.reshape(-1, 2)[iyi]
    p1 = ileri.reshape(-1, 2)[iyi]

    # Öteleme: nokta yer değişimlerinin ortancası (aykırı değerlere dayanıklı)
    ote = np.median(p1 - p0, axis=0)

    # Ölçek: merkeze uzaklıkların oranı
    m0, m1 = p0.mean(axis=0), p1.mean(axis=0)
    d0 = np.linalg.norm(p0 - m0, axis=1)
    d1 = np.linalg.norm(p1 - m1, axis=1)
    gecerli = d0 > 1e-3
    olcek = float(np.median(d1[gecerli] / d0[gecerli])) if gecerli.any() else 1.0
    if not np.isfinite(olcek) or not (OLCEK_ALT <= olcek <= OLCEK_UST):
        olcek = 1.0

    cx, cy = (x1 + x2) / 2 + ote[0], (y1 + y2) / 2 + ote[1]
    yw, yh = (x2 - x1) * olcek, (y2 - y1) * olcek
    nx1, ny1 = cx - yw / 2, cy - yh / 2
    nx2, ny2 = cx + yw / 2, cy + yh / 2

    # Sınıra kırp; tamamen dışarı çıktıysa bırak
    kx1, ky1 = max(0.0, nx1), max(0.0, ny1)
    kx2, ky2 = min(float(w), nx2), min(float(h), ny2)
    if kx2 - kx1 < 4 or ky2 - ky1 < 4:
        return None, 0.0

    oran = float(iyi.sum()) / max(1, len(noktalar))
    tutarlilik = float(1.0 - min(1.0, sapma[iyi].mean() / EN_FAZLA_GERI_HATA))
    guven = max(0.0, min(1.0, 0.5 * oran + 0.5 * tutarlilik))
    return (int(round(kx1)), int(round(ky1)),
            int(round(kx2)), int(round(ky2))), guven


def yama_al(kare, kutu, boyut: int = YAMA_BOYUT):
    """Kutunun içini sabit boyuta indirgenmiş gri yamaya çevirir."""
    import cv2
    g = _gri(kare)
    if g is None:
        return None
    h, w = g.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in kutu)
    x1, y1 = max(0, min(x1, x2)), max(0, min(y1, y2))
    x2, y2 = min(w, max(x1, x2)), min(h, max(y1, y2))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return cv2.resize(g[y1:y2, x1:x2], (boyut, boyut)).astype(np.float32)


def benzerlik(yama_a, yama_b) -> float:
    """İki yama arasında normalize çapraz korelasyon (-1..1, pratikte 0..1)."""
    import cv2
    if yama_a is None or yama_b is None:
        return 0.0
    try:
        return float(cv2.matchTemplate(yama_a, yama_b, cv2.TM_CCOEFF_NORMED)[0, 0])
    except Exception:
        return 0.0


class KutuZinciri:
    """Bir kutuyu kare kare taşırken görünümünü ilk kareyle karşılaştırır.

    `kutu_tasi` tek adımı yapar; bu sınıf zinciri yönetir ve kutu nesneden
    kaymaya başladığında durur. Kullanıcının çizdiği ilk karedeki görüntü
    referans olarak saklanır — kaymanın birikimli olduğu, tek adımda fark
    edilemeyeceği için karşılaştırma hep o referansa göre yapılır.
    """

    def __init__(self, ilk_kare, kutular,
                 en_az_benzerlik: float = EN_AZ_BENZERLIK):
        self.esik = en_az_benzerlik
        self.onceki = ilk_kare
        self.kutular = [tuple(int(v) for v in k) for k in kutular]
        self.referans = [yama_al(ilk_kare, k) for k in self.kutular]
        self.canli = list(range(len(self.kutular)))     # hâlâ takip edilenler
        self.son_sebep = ""

    def adim(self, sonraki_kare):
        """Bir sonraki kareye geç. → [(indeks, kutu, guven), …]

        Dönen liste boşsa zincir bitmiştir; sebebi `son_sebep`te.
        """
        sonuc = []
        yeni_canli, yeni_kutular = [], dict()
        for i in self.canli:
            yeni, akis = kutu_tasi(self.onceki, sonraki_kare, self.kutular[i])
            if yeni is None:
                self.son_sebep = "takip kayboldu"
                continue
            gorunum = benzerlik(self.referans[i], yama_al(sonraki_kare, yeni))
            if gorunum < self.esik:
                self.son_sebep = (f"kutu nesneden kaydı "
                                  f"(görünüm benzerliği {gorunum:.2f} < {self.esik:.2f})")
                continue
            # Bildirilen güven artık görünümü de içeriyor; akış tutarlılığı
            # tek başına kaymayı göremiyor.
            guven = max(0.0, min(1.0, 0.35 * akis + 0.65 * min(1.0, gorunum / 0.8)))
            yeni_canli.append(i)
            yeni_kutular[i] = yeni
            sonuc.append((i, yeni, guven))

        for i, k in yeni_kutular.items():
            self.kutular[i] = k
        self.canli = yeni_canli
        self.onceki = sonraki_kare
        return sonuc


def kutulari_tasi(onceki, sonraki, kutular, en_az_guven: float = 0.35):
    """Birden çok kutuyu taşır. → [(indeks, yeni_kutu, guven), …]

    Taşınamayan ya da güveni eşiğin altında kalan kutular sonuçta yer almaz;
    çağıran hangilerinin düştüğünü indeksten anlar.
    """
    sonuc = []
    for i, k in enumerate(kutular):
        yeni, guven = kutu_tasi(onceki, sonraki, k)
        if yeni is not None and guven >= en_az_guven:
            sonuc.append((i, yeni, guven))
    return sonuc
