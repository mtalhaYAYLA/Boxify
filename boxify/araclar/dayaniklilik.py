"""Dayanıklılık (soak) ölçümü — "hızlı mı" değil, "uzun koşuda ayakta mı".

Hız ölçümü birkaç yüz karede ne kadar sürdüğünü söyler. Sahaya giden bir
sistemde asıl soru başkadır: dört saat sonra hâlâ aynı hızda mı, bellek
sızdırıyor mu, ısınıp kısıtlanıyor mu, arada bir çıkarım hata verip
sessizce atlanıyor mu. Bu dosya o soruyu ölçüyor.

Örnekleme ek paket istemez: bellek üç işletim sisteminde de kendi yolundan
okunur, sıcaklık okunabildiği yerde okunur. Okunamayan eksen "bilinmiyor"
olarak raporlanır — yokmuş gibi davranmak, ölçümü olduğundan iyi gösterir.

Eşikler jetson_test_pack/freeze_diag'daki ölçütlerden alındı; oradaki
deneyimin bu araca taşınmış hâli.
"""

import os
import subprocess
import time

ORNEK_ARALIGI_SN = 5.0      # sağlık örnekleme sıklığı

# Değerlendirme eşikleri
RAM_DUSUS_FAIL_MB = 500     # bu kadar düştüyse sızıntı var say
RAM_DUSUS_UYARI_MB = 150
SWAP_ARTIS_FAIL_MB = 200
SICAKLIK_FAIL_C = 90
SICAKLIK_UYARI_C = 80
SURUKLENME_FAIL = 25.0      # % — son çeyrek ilk çeyrekten bu kadar yavaşsa
SURUKLENME_UYARI = 10.0

GECER, UYARI, KALDI = "GEÇTİ", "UYARI", "KALDI"


def _linux_bellek():
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            bilgi = {}
            for satir in f:
                parca = satir.split(":")
                if len(parca) == 2:
                    bilgi[parca[0]] = float(parca[1].strip().split()[0]) / 1024.0
        return (bilgi.get("MemAvailable", 0.0),
                bilgi.get("SwapTotal", 0.0) - bilgi.get("SwapFree", 0.0))
    except Exception:
        return None


def _macos_bellek():
    try:
        cikti = subprocess.run(["vm_stat"], capture_output=True, text=True,
                               timeout=5).stdout
        sayfa = 4096
        for satir in cikti.splitlines():
            if "page size of" in satir:
                sayfa = int(satir.split("page size of")[1].split()[0])
                break
        serbest = spekulatif = 0.0
        for satir in cikti.splitlines():
            if satir.startswith("Pages free:"):
                serbest = float(satir.split(":")[1].strip().rstrip(".")) * sayfa
            elif satir.startswith("Pages inactive:"):
                spekulatif = float(satir.split(":")[1].strip().rstrip(".")) * sayfa
        kullanilabilir = (serbest + spekulatif) / (1024 * 1024)

        # vm.swapusage biçimi:  total = 3072,00M  used = 1234,50M  free = ...
        # Alanı "used =" etiketinden yakalamak şart: sırayla ilk M'yi almak
        # toplam takası "kullanılan" sanıyordu ve takas değerlendirmesini
        # tamamen anlamsız yapıyordu.
        takas = 0.0
        try:
            import re
            sw = subprocess.run(["sysctl", "-n", "vm.swapusage"],
                                capture_output=True, text=True, timeout=5).stdout
            m = re.search(r"used\s*=\s*([\d.,]+)M", sw)
            if m:
                takas = float(m.group(1).replace(",", "."))
        except Exception:
            pass
        return kullanilabilir, takas
    except Exception:
        return None


def _windows_bellek():
    try:
        import ctypes

        class Durum(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        d = Durum()
        d.dwLength = ctypes.sizeof(Durum)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(d))
        mb = 1024 * 1024
        takas = (d.ullTotalPageFile - d.ullAvailPageFile
                 - (d.ullTotalPhys - d.ullAvailPhys)) / mb
        return d.ullAvailPhys / mb, max(0.0, takas)
    except Exception:
        return None


def bellek_ornegi():
    """(kullanılabilir_MB, takas_MB) ya da okunamazsa (None, None)."""
    for okuyucu in (_linux_bellek, _macos_bellek, _windows_bellek):
        sonuc = okuyucu()
        if sonuc is not None:
            return sonuc
    return None, None


def sicaklik_c():
    """CPU/GPU sıcaklığı (°C) ya da okunamazsa None.

    Linux ve Jetson'da /sys/class/thermal doludur. macOS ve Windows'ta ek
    yazılım olmadan okunamıyor; orada None dönüyor ve rapor bunu "sensör
    okunamadı" diye yazıyor.
    """
    kok = "/sys/class/thermal"
    if not os.path.isdir(kok):
        return None
    en_yuksek = None
    try:
        for ad in os.listdir(kok):
            if not ad.startswith("thermal_zone"):
                continue
            try:
                with open(os.path.join(kok, ad, "temp"), encoding="utf-8") as f:
                    deger = float(f.read().strip()) / 1000.0
            except Exception:
                continue
            if 0 < deger < 150:            # saçma değerleri ele
                en_yuksek = deger if en_yuksek is None else max(en_yuksek, deger)
    except Exception:
        return None
    return en_yuksek


def saglik_ornegi(t_rel: float, gecikme_ms: float = None) -> dict:
    ram, takas = bellek_ornegi()
    return {
        "t_sn": round(t_rel, 1),
        "ram_mb": ram,
        "takas_mb": takas,
        "sicaklik_c": sicaklik_c(),
        "gecikme_ms": gecikme_ms,
    }


def _ceyrek_ortalama(degerler, bas: bool):
    if not degerler:
        return None
    n = max(1, len(degerler) // 4)
    dilim = degerler[:n] if bas else degerler[-n:]
    return sum(dilim) / len(dilim)


def degerlendir(ornekler, hata_sayisi: int = 0, son_hata: str = "") -> list:
    """Her eksen için (eksen, durum, açıklama) döndür.

    "Bilinmiyor" ile "sorun yok" ayrı tutuluyor: okunamayan bir eksen UYARI
    olarak raporlanıyor, GEÇTİ olarak değil. Ölçemediğin şeyi geçmiş saymak,
    raporu olduğundan güvenli gösterir.
    """
    if not ornekler:
        return [("genel", UYARI, "örnek toplanmadı")]

    sonuc = []

    ramler = [o["ram_mb"] for o in ornekler if o.get("ram_mb") is not None]
    if len(ramler) >= 2:
        dusus = ramler[0] - ramler[-1]
        if dusus > RAM_DUSUS_FAIL_MB:
            sonuc.append(("bellek sızıntısı", KALDI,
                          f"kullanılabilir {ramler[0]:.0f}→{ramler[-1]:.0f} MB "
                          f"({dusus:.0f} MB düştü)"))
        elif dusus > RAM_DUSUS_UYARI_MB:
            sonuc.append(("bellek sızıntısı", UYARI,
                          f"{dusus:.0f} MB düştü — daha uzun koşuda izle"))
        else:
            sonuc.append(("bellek sızıntısı", GECER,
                          f"kullanılabilir ~sabit ({ramler[0]:.0f}→{ramler[-1]:.0f} MB)"))
    else:
        sonuc.append(("bellek sızıntısı", UYARI, "bellek okunamadı"))

    takaslar = [o["takas_mb"] for o in ornekler if o.get("takas_mb") is not None]
    if len(takaslar) >= 2:
        artis = takaslar[-1] - takaslar[0]
        durum = KALDI if artis > SWAP_ARTIS_FAIL_MB else GECER
        sonuc.append(("takas (swap)", durum,
                      f"{takaslar[0]:.0f}→{takaslar[-1]:.0f} MB"))
    else:
        sonuc.append(("takas (swap)", UYARI, "takas okunamadı"))

    sicakliklar = [o["sicaklik_c"] for o in ornekler if o.get("sicaklik_c") is not None]
    if sicakliklar:
        en_yuksek = max(sicakliklar)
        if en_yuksek >= SICAKLIK_FAIL_C:
            sonuc.append(("sıcaklık", KALDI, f"en yüksek {en_yuksek:.0f}°C — kısıtlama riski"))
        elif en_yuksek >= SICAKLIK_UYARI_C:
            sonuc.append(("sıcaklık", UYARI, f"en yüksek {en_yuksek:.0f}°C"))
        else:
            sonuc.append(("sıcaklık", GECER, f"en yüksek {en_yuksek:.0f}°C"))
    else:
        sonuc.append(("sıcaklık", UYARI,
                      "sensör okunamadı (macOS/Windows'ta normal; "
                      "Linux ve Jetson'da dolu olur)"))

    gecikmeler = [o["gecikme_ms"] for o in ornekler if o.get("gecikme_ms") is not None]
    bas = _ceyrek_ortalama(gecikmeler, True)
    son = _ceyrek_ortalama(gecikmeler, False)
    if bas and son and bas > 0:
        suruklenme = (son / bas - 1.0) * 100.0
        if suruklenme > SURUKLENME_FAIL:
            durum = KALDI
        elif suruklenme > SURUKLENME_UYARI:
            durum = UYARI
        else:
            durum = GECER
        sonuc.append(("hız sürüklenmesi", durum,
                      f"ilk çeyrek {bas:.1f} ms → son çeyrek {son:.1f} ms "
                      f"(%{suruklenme:+.1f})"))
    else:
        sonuc.append(("hız sürüklenmesi", UYARI, "gecikme örneklenmedi"))

    if hata_sayisi:
        sonuc.append(("çıkarım hataları", KALDI,
                      f"{hata_sayisi} hata — son: {son_hata[:80]}"))
    else:
        sonuc.append(("çıkarım hataları", GECER, "0 hata"))

    return sonuc


def ozet_durum(degerlendirme) -> str:
    durumlar = [d for _e, d, _a in degerlendirme]
    if KALDI in durumlar:
        return KALDI
    if UYARI in durumlar:
        return UYARI
    return GECER


def csv_yaz(yol: str, ornekler) -> str:
    """Örnekleri CSV'ye yaz; dönen değer yazılan yol ('' = yazılamadı)."""
    if not ornekler:
        return ""
    import csv as _csv
    try:
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        with open(yol, "w", newline="", encoding="utf-8") as f:
            yazici = _csv.DictWriter(f, fieldnames=list(ornekler[0].keys()))
            yazici.writeheader()
            yazici.writerows(ornekler)
        return yol
    except Exception:
        return ""
