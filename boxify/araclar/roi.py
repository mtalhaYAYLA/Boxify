"""İlgi alanı (ROI) — karenin yalnızca işe yarayan bölgesiyle çalış.

Fabrika kamerasının gördüğü alanın çoğu zaman yarısı alakasızdır: komşu hat,
koridor, tavan. Bütün kareyi etiketlemek iki şeye mal oluyor — orada çıkan
tespitler gürültü olarak veri setine giriyor, ve model ilgilenmediğin bölgede
yaptığı hatalarla değerlendiriliyor.

Tasarım kararları:

* **Poligon, dikdörtgen değil.** Hat çoğu zaman çapraz geçiyor; dikdörtgen ya
  komşu hattı içeri alıyor ya kendi hattının ucunu kesiyor.
* **Koordinatlar 0-1 normalize.** ROI 1080p önizlemede çizilip 4K kayıtta
  kullanılabiliyor; piksel saklasaydık her çözünürlük için yeniden çizmek
  gerekirdi.
* **Ölçüt kutunun merkezi.** "Tamamı içinde" kuralı sınırdaki nesneyi
  eliyor, "herhangi bir köşesi içinde" kuralı komşu hattı içeri alıyor.
  Merkez, ikisinin arasında ve tahmin edilebilir olanı.
* **ROI dosyası veri setinin yanında durur.** Aynı kamera için bir kez
  çizilir, bütün araçlar aynı dosyayı okur.
"""

import json
import os

ROI_DOSYA_ADI = "roi.json"


def roi_dosyasi(klasor: str) -> str:
    return os.path.join(klasor or ".", ROI_DOSYA_ADI)


def kaydet(klasor: str, poligonlar) -> str:
    """Poligonları klasörün yanına yaz; dönen değer yazılan yol ('' = olmadı)."""
    yol = roi_dosyasi(klasor)
    try:
        os.makedirs(os.path.dirname(yol) or ".", exist_ok=True)
        with open(yol, "w", encoding="utf-8") as f:
            json.dump({"surum": 1, "poligonlar": [list(map(list, p))
                                                  for p in poligonlar]},
                      f, ensure_ascii=False, indent=2)
        return yol
    except Exception:
        return ""


def yukle(klasor: str) -> list:
    """Klasördeki ROI'yi oku. Yoksa ya da bozuksa boş liste (= kısıt yok)."""
    yol = roi_dosyasi(klasor)
    if not os.path.exists(yol):
        return []
    try:
        with open(yol, encoding="utf-8") as f:
            veri = json.load(f)
        poligonlar = []
        for p in veri.get("poligonlar", []):
            nokta = [(float(x), float(y)) for x, y in p if len(p) >= 3]
            if len(nokta) >= 3:
                poligonlar.append(nokta)
        return poligonlar
    except Exception:
        return []


def nokta_icinde(poligon, x: float, y: float) -> bool:
    """Işın atma (ray casting) ile nokta-poligon testi.

    cv2.pointPolygonTest yerine saf Python: bu işlev hem işçi iş parçacığında
    hem testlerde çağrılıyor ve opencv'siz de çalışması gerekiyor.
    """
    icinde = False
    n = len(poligon)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = poligon[i]
        xj, yj = poligon[j]
        if (yi > y) != (yj > y):
            kesisim = (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            if x < kesisim:
                icinde = not icinde
        j = i
    return icinde


def icinde_mi(poligonlar, x: float, y: float) -> bool:
    """Nokta poligonlardan herhangi birinin içinde mi? ROI yoksa her yer geçerli."""
    if not poligonlar:
        return True
    return any(nokta_icinde(p, x, y) for p in poligonlar)


def kutu_gecerli(poligonlar, xyxy, genislik: int, yukseklik: int) -> bool:
    """Piksel kutusunun merkezi ROI içinde mi?"""
    if not poligonlar:
        return True
    x1, y1, x2, y2 = xyxy
    mx = ((x1 + x2) / 2.0) / max(1, genislik)
    my = ((y1 + y2) / 2.0) / max(1, yukseklik)
    return icinde_mi(poligonlar, mx, my)


def kutu_gecerli_normal(poligonlar, cx: float, cy: float) -> bool:
    """Zaten normalize merkezi olan kutu için (YOLO xywhn)."""
    return icinde_mi(poligonlar, cx, cy)


def ozet(poligonlar) -> str:
    if not poligonlar:
        return "ROI yok — bütün kare kullanılıyor"
    nokta = sum(len(p) for p in poligonlar)
    return f"{len(poligonlar)} bölge, {nokta} nokta"
