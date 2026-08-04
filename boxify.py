#!/usr/bin/env python
"""Boxify başlatıcı.

Kullanım:
    python boxify.py

Video Kırpıcı'nın ihtiyaç duyduğu GStreamer/glib düzeltmesi PyQt yüklenmeden
önce burada uygulanır (ayrıntı: boxify/araclar/video_kirpici.py başındaki not).
Kapatmak için: VK_NO_GLIB_FIX=1 python boxify.py
"""

import os
import sys


def _glib_duzeltmesi():
    """conda glib'i ile sistem gstreamer eklentileri çakışırsa sistem glib'ini
    LD_PRELOAD ile öne alıp süreci bir kez yeniden başlatır."""
    if os.environ.get("VK_GLIB_FIXED") or os.environ.get("VK_NO_GLIB_FIX"):
        return
    sys_dizin = "/usr/lib/x86_64-linux-gnu"
    libler = [f"{sys_dizin}/lib{n}-2.0.so.0" for n in ("glib", "gobject", "gio")]
    conda_gio = os.path.join(sys.prefix, "lib", "libgio-2.0.so.0")
    if not os.path.exists(conda_gio) or not os.path.isdir(f"{sys_dizin}/gstreamer-1.0"):
        return
    if not all(os.path.exists(p) for p in libler):
        return
    env = dict(os.environ)
    env["VK_GLIB_FIXED"] = "1"
    onyukleme = ":".join(libler)
    if env.get("LD_PRELOAD"):
        onyukleme += ":" + env["LD_PRELOAD"]
    env["LD_PRELOAD"] = onyukleme
    try:
        os.execve(sys.executable, [sys.executable] + sys.argv, env)
    except OSError:
        pass    # başarısızsa normal akışa devam et


# PyQt/gstreamer yüklenmeden önce çalışmalı
if __name__ == "__main__":
    _glib_duzeltmesi()

# gst-vaapi video sink bazı sürücülerde pencereyi kilitliyor; sadece sink kapalı,
# donanımla çözme etkin kalır. Geri açmak için: VK_KEEP_VAAPI=1
if not os.environ.get("VK_KEEP_VAAPI"):
    os.environ.setdefault("GST_PLUGIN_FEATURE_RANK", "vaapisink:0")

KOK = os.path.dirname(os.path.abspath(__file__))
if KOK not in sys.path:
    sys.path.insert(0, KOK)

from PyQt5.QtWidgets import QApplication          # noqa: E402
from PyQt5.QtGui import QIcon                     # noqa: E402

from boxify import SURUM                          # noqa: E402
from boxify import dil                            # noqa: E402

# Dil yamaları her pencereden önce kurulmalı (İngilizce modda Qt metin
# API'leri çeviri süzgecinden geçirilir; Türkçede hiçbir şey değişmez)
dil.dil_yukle()
dil.yamalari_kur()

from boxify.tema import STYLE                     # noqa: E402
from boxify.ana_pencere import AnaPencere         # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Boxify")
    app.setApplicationVersion(SURUM)
    app.setStyleSheet(STYLE)

    ikon = os.path.join(KOK, "ikon.png")
    if os.path.exists(ikon):
        app.setWindowIcon(QIcon(ikon))

    pencere = AnaPencere()
    pencere.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
