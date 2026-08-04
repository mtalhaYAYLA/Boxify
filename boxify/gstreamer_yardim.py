"""GStreamer/glib çakışması düzeltmesi — yalnızca Linux'ta anlamlı.

Sorun: conda ortamının kendi glib'i ile sistemin gstreamer eklentileri
uyuşmadığında eklentiler yüklenemiyor:

    Failed to load plugin '.../libgstlibav.so':
    .../lib/libgio-2.0.so.0: undefined symbol: g_variant_builder_init_static
    Error: "Your GStreamer installation is missing a plug-in."

Sonuç: video/ses çözücü bulunamaz, Video Kırpıcı ve Kare Alıcı'daki oynatıcı
hiç çalışmaz. Çözüm, sistemin glib'ini `LD_PRELOAD` ile öne alıp süreci bir
kez yeniden başlatmak.

Neden burada: düzeltme PyQt (ve dolayısıyla gstreamer) yüklenmeden ÖNCE
uygulanmalı. Hem `boxify.py` başlatıcısı hem de tek başına çalıştırılan
Video Kırpıcı buna ihtiyaç duyduğu için tek kopya burada tutuluyor.

Platform notu: bu sorun yalnızca Linux'a özgüdür — macOS'ta ve Windows'ta
GStreamer bu şekilde kullanılmaz, `LD_PRELOAD` diye bir mekanizma da yoktur.
O sistemlerde fonksiyon hiçbir şey yapmadan döner.

Kapatmak için: VK_NO_GLIB_FIX=1
"""

import glob
import os
import sys

# GStreamer'ın vaapi video sink'i bazı sürücülerde pencereyi kilitliyor.
# Sadece sink kapatılıyor; donanımla çözme etkin kalıyor. Bu da Linux'a özgü.
VAAPI_DEGISKENI = "GST_PLUGIN_FEATURE_RANK"
VAAPI_DEGERI = "vaapisink:0"


def _kutuphane_dizinleri():
    """Sistem glib'inin bulunabileceği dizinler, olasılık sırasına göre.

    Eskiden burada tek bir yol gömülüydü: `/usr/lib/x86_64-linux-gnu`. Bu,
    düzeltmenin yalnızca 64-bit Intel/AMD Linux'ta çalışması demekti; ARM
    Linux'ta (Raspberry Pi, ARM sunucular) dizin adı `aarch64-linux-gnu`
    olduğu için düzeltme sessizce hiç uygulanmıyordu. Artık Debian çoklu-mimari
    dizinleri taranıyor, ayrıca Fedora/openSUSE'nin `lib64` düzeni de dahil.
    """
    adaylar = sorted(glob.glob("/usr/lib/*-linux-gnu*"))
    adaylar += ["/usr/lib64", "/usr/lib"]
    return [d for d in adaylar if os.path.isdir(d)]


def glib_duzeltmesi() -> None:
    """Gerekiyorsa LD_PRELOAD ayarlayıp süreci bir kez yeniden başlatır.

    Dönerse ya gerek yoktu ya da uygulanamadı; her iki durumda da çağıran
    normal akışına devam edebilir.
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("VK_GLIB_FIXED") or os.environ.get("VK_NO_GLIB_FIX"):
        return

    # Ortamın kendi glib'i yoksa çakışma da yoktur
    conda_gio = os.path.join(sys.prefix, "lib", "libgio-2.0.so.0")
    if not os.path.exists(conda_gio):
        return

    for sys_dizin in _kutuphane_dizinleri():
        if not os.path.isdir(os.path.join(sys_dizin, "gstreamer-1.0")):
            continue
        libler = [os.path.join(sys_dizin, f"lib{n}-2.0.so.0")
                  for n in ("glib", "gobject", "gio")]
        if not all(os.path.exists(p) for p in libler):
            continue

        env = dict(os.environ)
        env["VK_GLIB_FIXED"] = "1"
        onyukleme = ":".join(libler)
        if env.get("LD_PRELOAD"):
            onyukleme += ":" + env["LD_PRELOAD"]
        env["LD_PRELOAD"] = onyukleme
        try:
            os.execve(sys.executable, [sys.executable] + sys.argv, env)
        except OSError:
            return      # başarısızsa normal akışa devam et
        return


def vaapi_sink_kapat() -> None:
    """Kilitlenmeye yol açan vaapi video sink'ini devre dışı bırakır (Linux).

    Geri açmak için: VK_KEEP_VAAPI=1
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("VK_KEEP_VAAPI"):
        return
    os.environ.setdefault(VAAPI_DEGISKENI, VAAPI_DEGERI)


def hazirla() -> None:
    """Başlatıcıların çağırdığı tek giriş noktası — PyQt import'undan önce."""
    glib_duzeltmesi()
    vaapi_sink_kapat()
