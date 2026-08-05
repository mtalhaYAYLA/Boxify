"""Araçların panel düzeni birbiriyle tutarlı mı?

Dokuz araç aynı kabuğun içinde ve kullanıcı bir tur boyunca aralarında gidip
geliyor. Bir araçta "ayarlar sağda" öğrenip diğerinde solda bulmak, her geçişte
gözle arama demek.

Bir dönem tam olarak bu vardı: yedi araç ayarları sağa koyarken sonradan yazılan
Model Karşılaştır ve Eğitim sola koymuştu (kaynak listeleri olmadığı için sol
boştaydı). Bu test o ayrışmanın geri gelmesini engeller.

Kural: **başlatma düğmesi ve ayarlar pencerenin sağ yarısında.**
Kaynak listesi (varsa) solda, önizleme ortada.

    python testler/test_duzen.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ortak import yolu_kur, Rapor   # noqa: E402

yolu_kur(sahte_ultralytics=True)

import importlib                                     # noqa: E402
from PyQt5.QtWidgets import QApplication, QPushButton, QStatusBar  # noqa: E402

from boxify.araclar import ARACLAR                   # noqa: E402

# Her aracın "işi başlatan" düğmesi — ayarların yanında olması gereken düğme.
BASLAT = {
    "video_kirpici":     "clip_btn",
    "kare_alici":        "extract_btn",
    "oto_label":         "start_btn",
    "veri_denetci":      "audit_btn",
    "egitim":            "start_btn",
    "hata_analizi":      "active_btn",
    "model_karsilastir": "start_btn",
    "model_export":      "export_btn",
}


def main() -> int:
    r = Rapor("Panel düzeni tutarlılığı")
    app = QApplication.instance() or QApplication([])

    for arac in ARACLAR:
        anahtar = arac["anahtar"]
        if anahtar == "labelapp":
            continue                     # ayrı paket, kendi düzeni var
        ad = BASLAT.get(anahtar)
        if not ad:
            r.kontrol(False, f"{anahtar}: başlat düğmesi tanımlı değil")
            continue

        m = importlib.import_module(arac["modul"])
        w = m.MainWindow()
        w.resize(1400, 880)
        w.show()
        app.processEvents()

        dugme = getattr(w, ad, None)
        if dugme is None:
            # bazı araçlarda düğme adı değişmiş olabilir; ilk büyük düğmeyi al
            adaylar = [b for b in w.findChildren(QPushButton)
                       if b.minimumHeight() >= 34]
            dugme = adaylar[0] if adaylar else None

        if dugme is None:
            r.kontrol(False, f"{anahtar}: başlat düğmesi bulunamadı ({ad})")
            w.close()
            continue

        # Düğmenin pencere içindeki yatay konumu
        merkez = dugme.mapTo(w, dugme.rect().center()).x()
        oran = merkez / max(1, w.width())
        r.kontrol(oran > 0.5,
                  f"{anahtar:<18s} başlat düğmesi sağ yarıda",
                  f"x oranı {oran:.2f} (0.5'ten büyük olmalı)")
        w.close()
        app.processEvents()

    return r.bitir()


if __name__ == "__main__":
    sys.exit(main())
