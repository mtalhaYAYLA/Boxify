"""Ortak model seçici — hangi ağırlıkla çalışılacağını iki adımda sorar.

Neden ayrı bir modül: aynı soru iki yerde soruluyordu (Eğitim aracı ve
Labelapp'in eğitim penceresi) ve iki yerde de ayrı, elle yazılmış listeler
vardı. Biri güncellenince diğeri eskiyor, kullanıcı da aynı uygulamada iki
farklı model listesi görüyordu.

Neden iki kademe: ultralytics'in indirebildiği 165 ağırlık tek bir açılır
listeye sığmıyor — kaydırarak aramak işkence. Önce aile (yolo11, yolo26,
rtdetr…), sonra o ailenin sürümü seçiliyor. Sürüm alanı yazılabilir olduğu
için listede olmayan bir ad ya da doğrudan bir dosya yolu da verilebiliyor.
"""

import os
import re

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QComboBox, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from ..dil import tr


# Tespit dışı görevler. Listede kalırlar ama ne oldukları yazılır — Boxify'ın
# veri biçimi tespit kutusudur, bunları bilmeden seçmek şaşırtır.
GOREV_EKLERI = {
    "-cls": "sınıflandırma", "-pose": "poz", "-seg": "segmentasyon",
    "-obb": "yönlü kutu", "-worldv2": "metinle tespit", "-world": "metinle tespit",
    "-oiv7": "Open Images", "-depth": "derinlik", "-sem": "anlamsal",
    "-grayscale": "gri tonlama",
}

# Ailelerin gösterim sırası: yaygın ve güncel olanlar üstte.
AILE_SIRASI = ["yolo11", "yolo12", "yolo26", "yolov8", "yolov10", "yolov9",
               "yolov5", "yolov3", "rtdetr", "yolo_nas", "yoloe"]

AILE_ACIKLAMA = {
    "yolo11": "güncel, dengeli — ilk tur için iyi başlangıç",
    "yolo12": "yeni nesil",
    "yolo26": "en yeni aile, en çok varyant",
    "yolov8": "olgun ve yaygın; metinle tespit (world) varyantları burada",
    "yolov10": "NMS'siz, hızlı",
    "yolov9": "doğruluk odaklı",
    "yolov5": "eski ama hâlâ sağlam (u = güncellenmiş sürüm)",
    "yolov3": "çok eski; yalnızca kıyas için",
    "rtdetr": "transformer tabanlı, küçük nesnede iyi",
    "yolo_nas": "arama ile üretilmiş mimari",
    "yoloe": "metinle tespit / açık sözlük",
}

_AILE_KALIBI = re.compile(r"^(rtdetr|yolo_nas|yoloe|yolov\d+|yolo\d+)")
_BOYUT_SIRASI = {"n": 0, "t": 0, "s": 1, "m": 2, "b": 3, "l": 4, "c": 4, "x": 5, "e": 6}


def model_gorevi(ad: str) -> str:
    for ek, gorev in GOREV_EKLERI.items():
        if ek in ad:
            return gorev
    return ""


def model_listesi() -> list:
    """ultralytics'in indirebildiği bütün ağırlıklar (SAM ailesi hariç).

    SAM istem tabanlı segmentasyondur; tespit eğitiminde başlangıç ağırlığı
    olamaz. ultralytics kurulu değilse gömülü kopya kullanılır — kısa bir
    yedek liste, kurulumu eksik bir makinede kısıtın kendisini geri getiriyordu.
    """
    try:
        from ultralytics.utils.downloads import GITHUB_ASSETS_NAMES
        adlar = [a for a in GITHUB_ASSETS_NAMES
                 if a.endswith(".pt") and "sam" not in a.lower()]
    except Exception:
        adlar = []
    return sorted(adlar) if adlar else list(GOMULU_MODELLER)


def aile_adi(ad: str) -> str:
    m = _AILE_KALIBI.match(ad)
    return m.group(1) if m else "diger"


def _varyant_sirasi(ad: str):
    """Aile içinde sıra: önce tespit, sonra boyut (n < s < m < l < x), sonra sade.

    "Sade" ölçütü şart: yolo26 ailesinde `yolo26n-objv1-150.pt` alfabetik olarak
    `yolo26n.pt`'den önce geliyor ve varsayılan o oluyordu. Aileyi seçen kişinin
    beklediği şey, o ailenin özel amaçlı bir türevi değil, düz modelidir.
    """
    govde = os.path.splitext(ad)[0]
    aile = aile_adi(ad)
    kalan = govde[len(aile):].lstrip("-_")
    harf = kalan[:1].lower()
    ek_var = 1 if kalan[1:].strip("-_") else 0
    return (0 if not model_gorevi(ad) else 1,
            _BOYUT_SIRASI.get(harf, 9), ek_var, ad)


def ailelere_ayir(adlar=None) -> dict:
    """{aile: [ağırlık adları]} — aileler ve içerikleri anlamlı sırada."""
    adlar = adlar if adlar is not None else model_listesi()
    gruplar = {}
    for ad in adlar:
        gruplar.setdefault(aile_adi(ad), []).append(ad)
    for aile in gruplar:
        gruplar[aile].sort(key=_varyant_sirasi)
    sirali = {}
    for aile in AILE_SIRASI:
        if aile in gruplar:
            sirali[aile] = gruplar.pop(aile)
    for aile in sorted(gruplar):
        sirali[aile] = gruplar[aile]
    return sirali


class ModelSecici(QWidget):
    """Aile + sürüm ikilisi. Sürüm alanı yazılabilir (özel ad ya da yol)."""

    degisti = pyqtSignal(str)

    def __init__(self, parent=None, varsayilan="yolo11n.pt"):
        super().__init__(parent)
        self._gruplar = ailelere_ayir()

        kok = QHBoxLayout(self)
        kok.setContentsMargins(0, 0, 0, 0)
        kok.setSpacing(6)

        self.aile_combo = QComboBox()
        for aile, adlar in self._gruplar.items():
            aciklama = AILE_ACIKLAMA.get(aile, "")
            etiket = f"{aile}  ({len(adlar)})"
            self.aile_combo.addItem(etiket, aile)
            if aciklama:
                self.aile_combo.setItemData(
                    self.aile_combo.count() - 1, tr(aciklama), Qt.ToolTipRole)
        self.aile_combo.setMaxVisibleItems(16)
        self.aile_combo.currentIndexChanged.connect(self._aile_degisti)
        kok.addWidget(self.aile_combo, 2)

        self.surum_combo = QComboBox()
        self.surum_combo.setEditable(True)
        self.surum_combo.setInsertPolicy(QComboBox.NoInsert)
        self.surum_combo.setMaxVisibleItems(24)
        tamamlayici = self.surum_combo.completer()
        if tamamlayici is not None:
            tamamlayici.setCaseSensitivity(Qt.CaseInsensitive)
            tamamlayici.setFilterMode(Qt.MatchContains)
        self.surum_combo.currentTextChanged.connect(
            lambda _t: self.degisti.emit(self.model_adi()))
        kok.addWidget(self.surum_combo, 3)

        self.set_model(varsayilan)

    # ------------------------------------------------------------------ public

    def model_adi(self) -> str:
        """Seçili ya da elle yazılan ağırlık adı (uzantısı yoksa .pt eklenir)."""
        idx = self.surum_combo.currentIndex()
        if idx >= 0 and self.surum_combo.itemText(idx) == self.surum_combo.currentText():
            veri = self.surum_combo.itemData(idx)
            if veri:
                return veri
        metin = self.surum_combo.currentText().strip().split("   (")[0].strip()
        if metin and not os.path.splitext(metin)[1]:
            metin += ".pt"
        return metin

    def set_model(self, ad: str):
        aile = aile_adi(ad)
        i = self.aile_combo.findData(aile)
        self.aile_combo.blockSignals(True)
        self.aile_combo.setCurrentIndex(i if i >= 0 else 0)
        self.aile_combo.blockSignals(False)
        self._surumleri_doldur()
        j = self.surum_combo.findData(ad)
        if j >= 0:
            self.surum_combo.setCurrentIndex(j)
        else:
            self.surum_combo.setEditText(ad)

    def setEnabled(self, acik: bool):
        self.aile_combo.setEnabled(acik)
        self.surum_combo.setEnabled(acik)
        super().setEnabled(acik)

    # ------------------------------------------------------------------ iç

    def _aile_degisti(self, _i):
        self._surumleri_doldur()
        if self.surum_combo.count():
            self.surum_combo.setCurrentIndex(0)
        self.degisti.emit(self.model_adi())

    def _surumleri_doldur(self):
        aile = self.aile_combo.currentData()
        self.surum_combo.blockSignals(True)
        self.surum_combo.clear()
        for ad in self._gruplar.get(aile, []):
            gorev = model_gorevi(ad)
            self.surum_combo.addItem(f"{ad}   ({tr(gorev)})" if gorev else ad, ad)
        self.surum_combo.blockSignals(False)


GOMULU_MODELLER = [
    # rtdetr (2)
    "rtdetr-l.pt", "rtdetr-x.pt",
    # yolo11 (26)
    "yolo11l-cls.pt", "yolo11l-obb.pt", "yolo11l-pose.pt", "yolo11l-seg.pt",
    "yolo11l.pt", "yolo11m-cls.pt", "yolo11m-obb.pt", "yolo11m-pose.pt",
    "yolo11m-seg.pt", "yolo11m.pt", "yolo11n-cls.pt", "yolo11n-grayscale.pt",
    "yolo11n-obb.pt", "yolo11n-pose.pt", "yolo11n-seg.pt", "yolo11n.pt",
    "yolo11s-cls.pt", "yolo11s-obb.pt", "yolo11s-pose.pt", "yolo11s-seg.pt",
    "yolo11s.pt", "yolo11x-cls.pt", "yolo11x-obb.pt", "yolo11x-pose.pt",
    "yolo11x-seg.pt", "yolo11x.pt",
    # yolo12 (5)
    "yolo12l.pt", "yolo12m.pt", "yolo12n.pt", "yolo12s.pt", "yolo12x.pt",
    # yolo26 (45)
    "yolo26l-cls.pt", "yolo26l-depth.pt", "yolo26l-obb.pt",
    "yolo26l-objv1-150.pt", "yolo26l-objv1-seg.pt", "yolo26l-pose.pt",
    "yolo26l-seg.pt", "yolo26l-sem.pt", "yolo26l.pt", "yolo26m-cls.pt",
    "yolo26m-depth.pt", "yolo26m-obb.pt", "yolo26m-objv1-150.pt",
    "yolo26m-objv1-seg.pt", "yolo26m-pose.pt", "yolo26m-seg.pt",
    "yolo26m-sem.pt", "yolo26m.pt", "yolo26n-cls.pt", "yolo26n-depth.pt",
    "yolo26n-obb.pt", "yolo26n-objv1-150.pt", "yolo26n-objv1-seg.pt",
    "yolo26n-pose.pt", "yolo26n-seg.pt", "yolo26n-sem.pt", "yolo26n.pt",
    "yolo26s-cls.pt", "yolo26s-depth.pt", "yolo26s-obb.pt",
    "yolo26s-objv1-150.pt", "yolo26s-objv1-seg.pt", "yolo26s-pose.pt",
    "yolo26s-seg.pt", "yolo26s-sem.pt", "yolo26s.pt", "yolo26x-cls.pt",
    "yolo26x-depth.pt", "yolo26x-obb.pt", "yolo26x-objv1-150.pt",
    "yolo26x-objv1-seg.pt", "yolo26x-pose.pt", "yolo26x-seg.pt",
    "yolo26x-sem.pt", "yolo26x.pt",
    # yolo_nas (3)
    "yolo_nas_l.pt", "yolo_nas_m.pt", "yolo_nas_s.pt",
    # yoloe (22)
    "yoloe-11l-seg-pf.pt", "yoloe-11l-seg.pt", "yoloe-11m-seg-pf.pt",
    "yoloe-11m-seg.pt", "yoloe-11s-seg-pf.pt", "yoloe-11s-seg.pt",
    "yoloe-26l-seg-pf.pt", "yoloe-26l-seg.pt", "yoloe-26m-seg-pf.pt",
    "yoloe-26m-seg.pt", "yoloe-26n-seg-pf.pt", "yoloe-26n-seg.pt",
    "yoloe-26s-seg-pf.pt", "yoloe-26s-seg.pt", "yoloe-26x-seg-pf.pt",
    "yoloe-26x-seg.pt", "yoloe-v8l-seg-pf.pt", "yoloe-v8l-seg.pt",
    "yoloe-v8m-seg-pf.pt", "yoloe-v8m-seg.pt", "yoloe-v8s-seg-pf.pt",
    "yoloe-v8s-seg.pt",
    # yolov10 (6)
    "yolov10b.pt", "yolov10l.pt", "yolov10m.pt", "yolov10n.pt", "yolov10s.pt",
    "yolov10x.pt",
    # yolov3 (3)
    "yolov3-sppu.pt", "yolov3-tinyu.pt", "yolov3u.pt",
    # yolov5 (10)
    "yolov5l6u.pt", "yolov5lu.pt", "yolov5m6u.pt", "yolov5mu.pt",
    "yolov5n6u.pt", "yolov5nu.pt", "yolov5s6u.pt", "yolov5su.pt",
    "yolov5x6u.pt", "yolov5xu.pt",
    # yolov8 (38)
    "yolov8l-cls.pt", "yolov8l-obb.pt", "yolov8l-oiv7.pt", "yolov8l-pose.pt",
    "yolov8l-seg.pt", "yolov8l-world.pt", "yolov8l-worldv2.pt", "yolov8l.pt",
    "yolov8m-cls.pt", "yolov8m-obb.pt", "yolov8m-oiv7.pt", "yolov8m-pose.pt",
    "yolov8m-seg.pt", "yolov8m-world.pt", "yolov8m-worldv2.pt", "yolov8m.pt",
    "yolov8n-cls.pt", "yolov8n-obb.pt", "yolov8n-oiv7.pt", "yolov8n-pose.pt",
    "yolov8n-seg.pt", "yolov8n.pt", "yolov8s-cls.pt", "yolov8s-obb.pt",
    "yolov8s-oiv7.pt", "yolov8s-pose.pt", "yolov8s-seg.pt",
    "yolov8s-world.pt", "yolov8s-worldv2.pt", "yolov8s.pt", "yolov8x-cls.pt",
    "yolov8x-obb.pt", "yolov8x-oiv7.pt", "yolov8x-pose.pt", "yolov8x-seg.pt",
    "yolov8x-world.pt", "yolov8x-worldv2.pt", "yolov8x.pt",
    # yolov9 (5)
    "yolov9c.pt", "yolov9e.pt", "yolov9m.pt", "yolov9s.pt", "yolov9t.pt",
]
