"""Sızıntısız bölme — projenin en pahalıya mal olabilecek hatasının nöbetçisi.

Boxify'da görseller ardışık video karelerinden gelir; komşu kareler birbirinin
neredeyse aynısıdır. Bölme rastgele yapılırsa aynı an hem train'e hem val'e
düşer, doğrulama skoru şişer ve model ezberlediği hâlde iyi görünür.

Bir zamanlar tam olarak bu oluyordu: Veri Denetçi gruplu bölme yaparken
Labelapp'in veri seti dışa aktarımı `random.shuffle` kullanıyordu ve eğitim
düğmesi ona bağlıydı. Bu test o hatanın geri gelmesini engeller.

    python testler/test_bolme.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, gecici, sahne_kareleri, sil, Rapor   # noqa: E402

yolu_kur()

from boxify.araclar.veri_bolme import (        # noqa: E402
    kopya_grup_anahtarlari, bolumlere_dagit, grup_ozeti, dhash64,
    group_duplicates, gorselleri_listele,
)


def bolunmus_sahneler(yollar, anahtarlar, kare_sahne, oranlar=(0.6, 0.2, 0.2)):
    """Kaç sahne birden fazla bölüme dağıldı?"""
    kova = bolumlere_dagit(anahtarlar, oranlar, seed=42)
    yer = {}
    for bolum, idxs in kova.items():
        for i in idxs:
            yer[os.path.basename(yollar[i])] = bolum
    bolunen = []
    for s in set(kare_sahne.values()):
        bolumler = {yer[a] for a in kare_sahne if kare_sahne[a] == s}
        if len(bolumler) > 1:
            bolunen.append((s, sorted(bolumler)))
    return kova, bolunen


def main() -> int:
    r = Rapor("Sızıntısız bölme")
    kok = gecici("bolme")
    try:
        kare_sahne = sahne_kareleri(kok, sahne=4, kare=6)
        yollar = gorselleri_listele(kok)
        SAHNE = len(set(kare_sahne.values()))
        r.bilgi(f"{len(yollar)} kare, {SAHNE} sahne (sahne içi kareler ardışık)")

        # 1) Gruplama yokken sızıntı OLMALI — testin kendisi anlamlı mı?
        tek = [f"tek{i}" for i in range(len(yollar))]
        _kova, bolunen_eski = bolunmus_sahneler(yollar, tek, kare_sahne)
        r.kontrol(len(bolunen_eski) > 0,
                  "gruplamasız bölme sızdırıyor (testin kendisi anlamlı)",
                  f"{len(bolunen_eski)}/{SAHNE} sahne bölündü")

        # 2) Gruplamayla sızıntı OLMAMALI
        anahtarlar = kopya_grup_anahtarlari(yollar, thresh=5)
        r.bilgi(grup_ozeti(anahtarlar))
        kova, bolunen = bolunmus_sahneler(yollar, anahtarlar, kare_sahne)
        r.kontrol(not bolunen, "yakın-kopya gruplaması sızıntıyı kapatıyor",
                  "; ".join(f"sahne {s} → {b}" for s, b in bolunen))

        # 3) Farklı sahneler yanlışlıkla birleştirilmemeli
        yanlis = 0
        for k in set(anahtarlar):
            sahneler = {kare_sahne[os.path.basename(yollar[i])]
                        for i, a in enumerate(anahtarlar) if a == k}
            if len(sahneler) > 1:
                yanlis += 1
        r.kontrol(yanlis == 0, "farklı sahneler birleştirilmiyor",
                  f"{yanlis} grup birden çok sahne içeriyor")

        # 4) Oranlar korunuyor mu (gruplar bölünmediği hâlde)
        toplam = sum(len(v) for v in kova.values())
        r.bilgi("dağılım: " + ", ".join(f"{k}={len(v)}" for k, v in kova.items()))
        r.kontrol(toplam == len(yollar), "her görsel tam bir bölüme gitti",
                  f"{toplam} != {len(yollar)}")
        r.kontrol(len(kova["train"]) >= len(kova["val"]),
                  "train en büyük bölüm")

        # 5) Aynı tohum aynı bölmeyi vermeli (yeniden üretilebilirlik)
        a = bolumlere_dagit(anahtarlar, (0.6, 0.2, 0.2), seed=7)
        b = bolumlere_dagit(anahtarlar, (0.6, 0.2, 0.2), seed=7)
        r.kontrol(a == b, "aynı tohum aynı bölmeyi veriyor")

        # 6) val istendiği hâlde boş kalmamalı (YOLO buna izin vermez)
        az = bolumlere_dagit(["g0", "g0", "g1"], (0.9, 0.1, 0.0), seed=1)
        r.kontrol(bool(az["val"]), "az grupta bile val boş kalmıyor", str(az))

        # 7) dHash: aynı görselin kopyası birebir eşleşmeli
        import cv2
        g = cv2.imread(yollar[0], cv2.IMREAD_GRAYSCALE)
        r.kontrol(dhash64(g) == dhash64(g.copy()), "dHash kararlı")
        gruplar = group_duplicates([dhash64(g), dhash64(g), None], 5)
        r.kontrol(gruplar == [[0, 1]], "birebir kopyalar gruplanıyor",
                  str(gruplar))
    finally:
        sil(kok)
    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
