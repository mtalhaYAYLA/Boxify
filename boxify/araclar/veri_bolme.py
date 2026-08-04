"""Sızıntısız (grup bazlı) train/val/test bölmesi — tek doğru kaynak.

Bu atölyedeki görseller ardışık video karelerinden geliyor: komşu kareler
birbirinin neredeyse aynısı. Rastgele bölünürse aynı an hem train'e hem val'e
düşer, val ölçümü şişer ve model ezberlediği hâlde iyi görünür. Buradaki
`bolumlere_dagit`, aynı gruba giren kareleri **asla ikiye ayırmaz**.

Bölme yapan her yer (Veri Denetçi ve Labelapp'in veri seti dışa aktarımı) bu
modülü kullanır; ikinci bir bölme kodu yazılmamalıdır.

Bağımlılık: numpy (+ dHash için opencv). PyQt5 ve ultralytics gerekmez.
"""

import os

import numpy as np

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")


# ── Yakın-kopya bulma ───────────────────────────────────────────────────────

def dhash64(gray) -> int:
    """8x8 fark hash'i (dHash) — yakın-kopya karşılaştırması için."""
    import cv2
    small = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    diff = (small[:, 1:] > small[:, :-1]).flatten().astype(np.uint8)
    return int.from_bytes(np.packbits(diff).tobytes(), "big")


def group_duplicates(hashes: list, thresh: int) -> list:
    """Hamming mesafesi eşiğin altındaki hash'leri gruplar (birleşim-bul).

    Mesafe matrisi BLAS ile hesaplanır: hamming(a,b) = a·(1-b) + (1-a)·b
    Dönen değer: her biri en az 2 elemanlı, indeks listelerinden oluşan gruplar.
    """
    idx = [i for i, h in enumerate(hashes) if h is not None]
    if len(idx) < 2:
        return []
    arr = np.array([hashes[i] for i in idx], dtype=">u8")
    bits = np.unpackbits(arr.view(np.uint8).reshape(-1, 8), axis=1)
    A = bits.astype(np.float32)
    B = 1.0 - A

    parent = list(range(len(idx)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    step = max(64, min(1024, 4_000_000 // max(1, len(idx))))
    for s in range(0, len(idx), step):
        e = min(len(idx), s + step)
        dist = A[s:e] @ B.T + B[s:e] @ A.T          # (e-s) x n
        for r in range(e - s):
            i = s + r
            for j in np.nonzero(dist[r] <= thresh)[0]:
                if int(j) != i:
                    union(i, int(j))

    groups = {}
    for k in range(len(idx)):
        groups.setdefault(find(k), []).append(idx[k])
    return [sorted(v) for v in groups.values() if len(v) > 1]


def kopya_grup_anahtarlari(yollar: list, thresh: int = 5, ilerleme=None) -> list:
    """Görsel yollarını okuyup her birine bir grup anahtarı üretir.

    Aynı sahnenin tekrar eden kareleri aynı anahtarı alır; benzeri olmayan
    görsel kendi başına bir grup olur. Görsel okunamazsa yine tek başına kalır
    — bölme yapılamamasındansa o karenin gruplanmaması yeğdir.

    ilerleme: opsiyonel `callable(okunan, toplam)` geri çağrımı.
    """
    try:
        import cv2
    except ImportError:
        return [f"tek{i}" for i in range(len(yollar))]

    hashes = []
    for i, p in enumerate(yollar):
        h = None
        try:
            gray = cv2.imdecode(np.fromfile(p, dtype=np.uint8),
                                cv2.IMREAD_GRAYSCALE)
            if gray is not None:
                h = dhash64(gray)
        except Exception:
            h = None
        hashes.append(h)
        if ilerleme is not None:
            ilerleme(i + 1, len(yollar))

    anahtarlar = [f"tek{i}" for i in range(len(yollar))]
    for gid, grup in enumerate(group_duplicates(hashes, thresh)):
        for i in grup:
            anahtarlar[i] = f"dup{gid}"
    return anahtarlar


# ── Bölme ───────────────────────────────────────────────────────────────────

def bolumlere_dagit(grup_anahtarlari: list, oranlar, seed: int = 42) -> dict:
    """Grup anahtarlarını train/val/test kovalarına dağıtır.

    grup_anahtarlari : her öğe için bir anahtar (aynı anahtar = aynı gruba ait)
    oranlar          : (train, val, test) — toplamları 1 olmak zorunda değil
    dönüş            : {"train": [indeks…], "val": […], "test": […]}

    Her grup, hedefine en çok uzak düşen bölüme konur; böylece oranlar korunur
    ama bir grup asla bölünmez. Aynı `seed` aynı bölmeyi verir.
    """
    import random

    toplam_oran = float(sum(oranlar)) or 1.0
    oranlar = [r / toplam_oran for r in oranlar]

    gruplar = {}
    for i, k in enumerate(grup_anahtarlari):
        gruplar.setdefault(k, []).append(i)

    keys = sorted(gruplar)
    random.Random(seed).shuffle(keys)

    n = len(grup_anahtarlari)
    hedef = {"train": oranlar[0] * n, "val": oranlar[1] * n, "test": oranlar[2] * n}
    kova = {k: [] for k in hedef}

    for key in keys:
        pick = max(
            (k for k in hedef if hedef[k] > 0),
            key=lambda k: hedef[k] - len(kova[k]),
            default="train",
        )
        kova[pick].extend(gruplar[key])

    # YOLO doğrulama bölümü boş olamaz; oran istendiği hâlde boş kaldıysa
    # (grup sayısı bölüm sayısından az) train'den en küçük grubu ödünç al
    if hedef["val"] > 0 and not kova["val"] and kova["train"]:
        odunc = gruplar[min(
            (k for k in keys if any(i in kova["train"] for i in gruplar[k])),
            key=lambda k: len(gruplar[k]))]
        kova["train"] = [i for i in kova["train"] if i not in odunc]
        kova["val"] = list(odunc)

    return kova


def grup_ozeti(grup_anahtarlari: list) -> str:
    """'40 görsel, 12 grup (en büyük grup 9 kare)' biçiminde tek satır."""
    if not grup_anahtarlari:
        return "0 görsel"
    sayim = {}
    for k in grup_anahtarlari:
        sayim[k] = sayim.get(k, 0) + 1
    return (f"{len(grup_anahtarlari)} görsel, {len(sayim)} grup "
            f"(en büyük grup {max(sayim.values())} kare)")


def gorselleri_listele(kok: str, alt_klasorler: bool = True) -> list:
    """Klasördeki desteklenen görselleri sıralı olarak döndürür."""
    bulunan = []
    if alt_klasorler:
        for dizin, _alt, dosyalar in os.walk(kok):
            for ad in dosyalar:
                if ad.lower().endswith(IMG_EXTS):
                    bulunan.append(os.path.join(dizin, ad))
    else:
        for ad in os.listdir(kok):
            p = os.path.join(kok, ad)
            if os.path.isfile(p) and ad.lower().endswith(IMG_EXTS):
                bulunan.append(p)
    return sorted(bulunan)
