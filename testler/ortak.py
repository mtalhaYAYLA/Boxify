"""Testlerin ortak altyapısı: yol kurulumu, sahte veri üretimi, küçük yardımcılar.

Testler depoyla birlikte gelir ve dış veri istemez — ihtiyaç duydukları video,
kare ve etiketleri kendileri üretir. Gerçek model gerektiren ölçümler (eğitim,
çıkarım) `sahte/ultralytics` yığınıyla koşar; niyet modelin doğruluğunu değil,
Boxify'ın o modelle doğru konuşup konuşmadığını sınamaktır.
"""

import os
import shutil
import sys
import tempfile

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAHTE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sahte")


def yolu_kur(sahte_ultralytics: bool = False):
    """Depo kökünü (ve istenirse sahte ultralytics'i) import yoluna ekler."""
    if sahte_ultralytics and SAHTE not in sys.path:
        sys.path.insert(0, SAHTE)
    if KOK not in sys.path:
        sys.path.insert(0, KOK)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def gecici(ad: str) -> str:
    """Test için geçici klasör (çağıran temizler)."""
    return tempfile.mkdtemp(prefix=f"boxify_{ad}_")


def gecici_ayar():
    """Ayar dosyasını geçici bir yola çevir — testler kullanıcınınkine dokunmasın.

    Dil, tema ve yol hafızası hepsi ~/.config/boxify4/ayarlar.json dosyasını
    kullanıyor. Testler bunu yedekleyip geri koyarak deniyordu; bir test ortada
    çökerse kullanıcının ayarı bozulmuş kalıyordu — ve bir kez gerçekten oldu:
    tema "koyu"da, yol hafızası silinmiş geçici klasörlerle dolu kaldı.

    Artık üç modülün yol sabitleri geçici bir klasöre çevriliyor; testin gerçek
    dosyaya erişimi yok. Dönen fonksiyon çağrılınca eski hâl geri yüklenir.
    """
    from boxify import dil, proje, tema

    dizin = tempfile.mkdtemp(prefix="boxify_ayar_")
    dosya = os.path.join(dizin, "ayarlar.json")
    onceki = []
    for modul in (dil, tema, proje):
        onceki.append((modul, getattr(modul, "AYAR_DIZIN", None),
                       getattr(modul, "AYAR_DOSYA", None)))
        if hasattr(modul, "AYAR_DIZIN"):
            modul.AYAR_DIZIN = dizin
        if hasattr(modul, "AYAR_DOSYA"):
            modul.AYAR_DOSYA = dosya

    def geri_al():
        for modul, eski_dizin, eski_dosya in onceki:
            if eski_dizin is not None:
                modul.AYAR_DIZIN = eski_dizin
            if eski_dosya is not None:
                modul.AYAR_DOSYA = eski_dosya
        shutil.rmtree(dizin, ignore_errors=True)

    return dosya, geri_al


# ── Sahte veri üretimi ───────────────────────────────────────────────────────

def sahne_kareleri(kok: str, sahne: int = 4, kare: int = 6,
                   boyut=(320, 240)) -> dict:
    """Video benzeri kareler üretir: {dosya_adi: sahne_no}.

    Gerçek video karelerini taklit etmek önemli, iki yönden birden:

    * **Aynı sahnenin kareleri birbirine çok yakın olmalı.** Rastgele
      gürültüden kare üretmek yanıltıcıdır — komşu gürültü kareleri dHash'e
      göre birbirinden UZAK düşer, oysa gerçek videoda çok yakındırlar.
    * **Farklı sahneler birbirinden uzak olmalı.** Sahneleri yalnızca
      parlaklıkla ayırmak da yetmez: dHash yatay komşu piksellerin
      karşılaştırmasıdır, düz bir renk geçişi hangi tonda olursa olsun aynı
      deseni verir. Ayrım YAPISAL olmalı.

    Bu yüzden her sahne, kendine özgü yerlere serpiştirilmiş bloklardan oluşur
    (yapısal parmak izi) ve üzerinde yavaşça ilerleyen bir nesne bulunur
    (kareler arası küçük fark).
    """
    import cv2
    import numpy as np

    os.makedirs(kok, exist_ok=True)
    w, h = boyut
    esleme = {}
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    for s in range(sahne):
        # Sahneye özgü yapısal desen — tohum sahneden türetiliyor ki her
        # sahnenin yerleşimi farklı ama tekrarlanabilir olsun.
        srng = np.random.default_rng(1000 + s)

        # Zemin DOKULU olmalı. dHash görüntüyü 9x8'e indirip yatay komşuları
        # karşılaştırır; düz renkli geniş alanlarda komşu hücreler neredeyse
        # eşit çıkar ve karşılaştırmayı en küçük gürültü bile rastgele çevirir.
        # Gerçek fotoğrafta her yerde doku olduğu için bu olmaz — testin de
        # o koşulu taklit etmesi gerekiyor.
        fa, fb = 0.9 + 0.5 * s, 0.7 + 0.4 * s
        doku = (60 + 55 * np.sin(xx / (9 + 2 * s) * fa)
                + 45 * np.cos(yy / (7 + 2 * s) * fb)
                + 30 * np.sin((xx + yy) / (13 + s)))
        taban = np.repeat(doku[:, :, None], 3, axis=2).astype(np.float32)

        for _ in range(10):
            bx, by = srng.integers(0, w - 40), srng.integers(0, h - 40)
            bw, bh = srng.integers(18, 40), srng.integers(18, 40)
            ton = float(srng.integers(70, 230))
            taban[by:by + bh, bx:bx + bw] = ton + 18 * np.sin(
                xx[by:by + bh, bx:bx + bw] / 5)[:, :, None]

        krng = np.random.default_rng(2000 + s)
        for k in range(kare):
            f = taban.copy()
            # Yavaş ilerleyen nesne. Adım bilerek küçük (kare başına 1 px):
            # 25 fps'lik gerçek videoda ardışık kareler arasındaki fark bu
            # ölçektedir. Büyük adım atmak sahne içi kareleri birbirinden
            # uzaklaştırır ve testi gerçekliğinden koparır.
            x = min(w - 32, 40 + k)
            y = min(h - 32, 60 + k)
            f[y:y + 30, x:x + 30] = 250
            f += krng.normal(0, 0.8, f.shape)         # hafif sensör gürültüsü
            ad = f"s{s}_k{k}.jpg"
            cv2.imwrite(os.path.join(kok, ad),
                        np.clip(f, 0, 255).astype(np.uint8))
            esleme[ad] = s
    return esleme


def veri_seti(kok: str, siniflar: list, gorsel: int = 8,
              sinif_uret=None) -> str:
    """images/ + labels/ + data.yaml içeren küçük bir YOLO veri seti kurar."""
    import cv2
    import numpy as np

    img_d = os.path.join(kok, "images")
    lbl_d = os.path.join(kok, "labels")
    os.makedirs(img_d, exist_ok=True)
    os.makedirs(lbl_d, exist_ok=True)
    rng = np.random.default_rng(5)
    if sinif_uret is None:
        def sinif_uret(i):
            return i % len(siniflar)

    for i in range(gorsel):
        cv2.imwrite(os.path.join(img_d, f"kare_{i:03d}.jpg"),
                    rng.integers(60, 200, (120, 160, 3), dtype=np.uint8))
        with open(os.path.join(lbl_d, f"kare_{i:03d}.txt"), "w") as f:
            for _ in range(rng.integers(1, 3)):
                x, y = rng.uniform(.3, .7), rng.uniform(.3, .7)
                f.write(f"{sinif_uret(i)} {x:.5f} {y:.5f} "
                        f"{rng.uniform(.1, .2):.5f} {rng.uniform(.1, .2):.5f}\n")

    yaml_yolu = os.path.join(kok, "data.yaml")
    with open(yaml_yolu, "w", encoding="utf-8") as f:
        f.write(f"path: {os.path.abspath(kok)}\n")
        f.write("train: images\nval: images\n")
        f.write(f"nc: {len(siniflar)}\nnames:\n")
        for i, ad in enumerate(siniflar):
            f.write(f"  {i}: {ad}\n")
    return yaml_yolu


def video_uret(yol: str, saniye: int = 3, fps: int = 25,
               boyut=(320, 240)) -> str:
    """Küçük bir mp4 üretir (Video Kırpıcı / Kare Alıcı testleri için)."""
    import cv2
    import numpy as np

    w, h = boyut
    yazici = cv2.VideoWriter(yol, cv2.VideoWriter_fourcc(*"mp4v"),
                             float(fps), (w, h))
    for i in range(saniye * fps):
        f = np.zeros((h, w, 3), dtype=np.uint8)
        f[:, :] = (30 + i % 60, 60, 120)
        x = 20 + (i * 3) % max(1, w - 60)
        f[80:130, x:x + 40] = (240, 240, 240)
        yazici.write(f)
    yazici.release()
    return yol


# ── Sonuç bildirimi ──────────────────────────────────────────────────────────

class Rapor:
    """Basit test toplayıcı: her testin sonunda tek satır özet basar."""

    def __init__(self, baslik: str):
        self.baslik = baslik
        self.hatalar = []
        print(f"── {baslik} " + "─" * max(0, 56 - len(baslik)))

    def kontrol(self, kosul: bool, aciklama: str, ayrinti: str = ""):
        if kosul:
            print(f"  ✓ {aciklama}")
        else:
            print(f"  ✗ {aciklama}" + (f"  ({ayrinti})" if ayrinti else ""))
            self.hatalar.append(aciklama + (f" — {ayrinti}" if ayrinti else ""))
        return kosul

    def bilgi(self, metin: str):
        print(f"    {metin}")

    def bitir(self) -> int:
        print()
        if self.hatalar:
            print(f"SONUC: BASARISIZ — {len(self.hatalar)} sorun")
            for h in self.hatalar:
                print(f"  - {h}")
            return 1
        print("SONUC: GECTI")
        return 0


def bekle(app, saniye: float, kosul=None) -> bool:
    """Qt olay döngüsünü döndürerek koşulu bekler."""
    import time
    t0 = time.time()
    while time.time() - t0 < saniye:
        app.processEvents()
        if kosul is not None and kosul():
            return True
        time.sleep(0.02)
    return kosul is None


def sil(*yollar):
    for y in yollar:
        shutil.rmtree(y, ignore_errors=True)
