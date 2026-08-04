#!/usr/bin/env python
"""Boxify başlatıcı.

Kullanım (üç işletim sisteminde de aynı):
    python boxify.py

Linux'ta gereken GStreamer/glib düzeltmesi PyQt yüklenmeden önce uygulanır;
macOS ve Windows'ta bu adım kendiliğinden atlanır (bkz. boxify/gstreamer_yardim.py).
Kapatmak için: VK_NO_GLIB_FIX=1 python boxify.py
"""

import os
import sys

KOK = os.path.dirname(os.path.abspath(__file__))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

# PyQt/gstreamer yüklenmeden ÖNCE çalışmalı — bu yüzden import'ların başında.
# Linux dışında hiçbir şey yapmaz.
from boxify import gstreamer_yardim              # noqa: E402
gstreamer_yardim.hazirla()

from PyQt5.QtWidgets import QApplication          # noqa: E402
from PyQt5.QtGui import QIcon                     # noqa: E402

from boxify import SURUM                          # noqa: E402
from boxify import dil                            # noqa: E402
from boxify import tema                           # noqa: E402

# Dil ve tema yamaları her pencereden önce kurulmalı: ikisi de Qt API'lerini
# sarmalıyor (dil metinleri, tema stil renklerini çevirir). Varsayılan durumda
# — Türkçe + açık tema — hiçbir yama kurulmaz, dolayısıyla maliyeti de yoktur.
dil.dil_yukle()
dil.yamalari_kur()
tema.tema_yukle()
tema.yamalari_kur()

from boxify.ana_pencere import AnaPencere         # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Boxify")
    app.setApplicationVersion(SURUM)
    app.setStyleSheet(tema.stil())

    ikon = os.path.join(KOK, "ikon.png")
    if os.path.exists(ikon):
        app.setWindowIcon(QIcon(ikon))

    pencere = AnaPencere()
    pencere.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
