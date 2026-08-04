"""Son kullanılan klasör hafızası — 33 dosya seçim diyalogu için.

Boxify'da bir tur şöyle geçiyor: videoyu kırp → kare çıkar → oto etiketle →
elle düzelt → denetle ve böl → eğit → hataya bak → eksikleri etiketle → yeniden
eğit. Bu turda dokuz araç arasında gidip geliniyor ve her araç kendi
klasörlerini soruyor: toplam 33 seçim diyalogu.

Hafıza olmadan bunların hepsi her seferinde ev dizininden açılıyordu; aynı üç
beş klasöre onlarca kez elle gidiliyordu. Bu modül her diyalogun en son nereyi
açtığını hatırlar ve bir dahakine oradan başlatır.

## Nasıl çalışıyor

`dil.py` ve `tema.py`'deki desenin aynısı: `QFileDialog`'un statik metotları
yamalanıyor. Araç kodlarına hiç dokunulmuyor, sonradan eklenecek araçlar da
kendiliğinden hatırlamaya başlıyor.

İki kural var:

1. **Çağıranın seçimi her zaman kazanır.** Araçlar çoğu yerde zaten akıllı bir
   başlangıç veriyor (ör. modelin bulunduğu klasör). Yama yalnızca çağıran boş
   bir başlangıç verdiğinde devreye girer.
2. **Anahtar diyalogun başlığıdır.** Her çağrı yerinin başlığı ayrı ("Model
   seç", "Fotoğrafların olduğu klasör", "Bölme çıktı klasörü"…), yani her alan
   kendi hafızasını tutar — çıktı klasörü seçerken model klasörü önerilmez.

Yollar ~/.config/boxify4/ayarlar.json içinde, dil ve tema ile aynı dosyada
"yollar" başlığı altında saklanır. Var olmayan klasörler okunurken elenir, yani
harici disk çıkarıldığında diyalog yine de açılır.
"""

import json
import os

AYAR_DIZIN = os.path.join(os.path.expanduser("~"), ".config", "boxify4")
AYAR_DOSYA = os.path.join(AYAR_DIZIN, "ayarlar.json")

# Aynı dosyaya dil ve tema da yazıyor; her kayıtta dosya baştan okunup
# birleştiriliyor ki biri diğerini silmesin.
_yollar = {}
_yamalar_kuruldu = False
_EN_FAZLA = 60          # anahtar sayısı sınırı — ayar dosyası şişmesin


def yukle() -> dict:
    """Kayıtlı yolları oku. Artık var olmayan klasörler elenir."""
    global _yollar
    _yollar = {}
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            ham = json.load(f).get("yollar", {})
        if isinstance(ham, dict):
            _yollar = {k: v for k, v in ham.items()
                       if isinstance(v, str) and os.path.isdir(v)}
    except Exception:
        pass
    return _yollar


def _kaydet():
    try:
        os.makedirs(AYAR_DIZIN, exist_ok=True)
        ayar = {}
        try:
            with open(AYAR_DOSYA, encoding="utf-8") as f:
                ayar = json.load(f)
        except Exception:
            pass
        ayar["yollar"] = _yollar
        with open(AYAR_DOSYA, "w", encoding="utf-8") as f:
            json.dump(ayar, f, ensure_ascii=False, indent=2)
    except OSError:
        pass        # ayar yazılamıyorsa uygulama yine de çalışmalı


def hatirla(anahtar: str, yol: str):
    """Bir diyalogun son kullandığı klasörü kaydet."""
    if not anahtar or not yol:
        return
    klasor = yol if os.path.isdir(yol) else os.path.dirname(yol)
    if not klasor or not os.path.isdir(klasor):
        return
    if _yollar.get(anahtar) == klasor:
        return
    _yollar[anahtar] = klasor
    if len(_yollar) > _EN_FAZLA:
        for k in list(_yollar)[:len(_yollar) - _EN_FAZLA]:
            _yollar.pop(k, None)
    _kaydet()


def son(anahtar: str, varsayilan: str = "") -> str:
    """Bu diyalogun son kullandığı klasör; yoksa varsayılan."""
    yol = _yollar.get(anahtar, "")
    return yol if yol and os.path.isdir(yol) else varsayilan


def unut():
    """Bütün yol hafızasını temizle."""
    global _yollar
    _yollar = {}
    _kaydet()


# ── Yama ─────────────────────────────────────────────────────────────────────

def yamalari_kur():
    """QFileDialog'un statik metotlarını hafızayla sarmala."""
    global _yamalar_kuruldu
    if _yamalar_kuruldu:
        return
    from PyQt5.QtWidgets import QFileDialog

    def sar_tek(ad, cikar):
        """cikar(sonuc) -> hatırlanacak yol (ya da boş)."""
        ozgun = getattr(QFileDialog, ad)

        def sarmal(parent=None, caption="", directory="", *args, **kw):
            anahtar = f"{ad}:{caption}"
            # 1. kural: çağıran bir başlangıç verdiyse ona dokunma
            if not directory:
                directory = son(anahtar)
            sonuc = ozgun(parent, caption, directory, *args, **kw)
            hatirla(anahtar, cikar(sonuc))
            return sonuc

        setattr(QFileDialog, ad, staticmethod(sarmal))

    sar_tek("getOpenFileName", lambda s: s[0] if s and s[0] else "")
    sar_tek("getSaveFileName", lambda s: s[0] if s and s[0] else "")
    sar_tek("getOpenFileNames", lambda s: (s[0][0] if s and s[0] else ""))
    sar_tek("getExistingDirectory", lambda s: s if isinstance(s, str) else "")
    _yamalar_kuruldu = True
