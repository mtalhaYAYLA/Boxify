"""Boxify ortak teması — açık ve koyu tema.

Tasarım dili (göz yormayan, düşük parlamalı):
- Saf beyaz ve saf siyah kullanılmaz; ikisi de parlama/kontrast yorgunluğu yapar.
- Vurgu: yumuşatılmış profesyonel mavi; hover biraz açılır, basılıda koyulaşır.
  Neon/doygun tonlardan kaçınılır.
- Köşeler yumuşak (6-10px), tüm tıklanabilir öğelerde hover/pressed efekti,
  girdilerde odak (focus) mavi çerçevesi.
- Renk körlüğü kuralı korunur: kırmızı-yeşil ayrımına dayanılmaz; durumlar
  mavi tonları + metin + desenle verilir.

## Koyu tema nasıl çalışıyor

Araç modülleri kendi ayrıntı stillerini `setStyleSheet` ile, renkleri de
doğrudan yazarak veriyor (119 çağrı, ~15 ayrı ton). Koyu temayı bu çağrıların
hepsini elle düzenleyerek yapmak hem çok riskliydi hem de sonradan yazılacak
her araçta aynı işi tekrar gerektirirdi.

Onun yerine `dil.py`'nin dil için kullandığı desen uygulanıyor: `setStyleSheet`
yamalanıyor ve koyu tema etkinken stil metnindeki açık palet renkleri koyu
karşılıklarıyla değiştiriliyor. Araç kodlarına hiç dokunulmuyor; bundan sonra
eklenecek araçlar da paletteki tonları kullandığı sürece kendiliğinden uyumlu
olur.

Tuvaller (görüntü/video önizlemeleri) bunun dışındadır: onlar iki temada da
koyu kalır, çünkü kutu renkleri koyu zeminde daha iyi seçilir.

Tema ayarı dil ile aynı dosyada saklanır: ~/.config/boxify4/ayarlar.json
"""

import json
import os

TEMALAR = ("acik", "koyu")
_tema = "acik"

AYAR_DIZIN = os.path.join(os.path.expanduser("~"), ".config", "boxify4")
AYAR_DOSYA = os.path.join(AYAR_DIZIN, "ayarlar.json")


def tema_yukle() -> str:
    """Kayıtlı temayı oku (yoksa/bozuksa açık)."""
    global _tema
    _tema = "acik"
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            kod = json.load(f).get("tema", "acik")
        if kod in TEMALAR:
            _tema = kod
    except Exception:
        pass
    return _tema


def tema_kaydet(kod: str):
    if kod not in TEMALAR:
        raise ValueError(kod)
    os.makedirs(AYAR_DIZIN, exist_ok=True)
    ayar = {}
    try:
        with open(AYAR_DOSYA, encoding="utf-8") as f:
            ayar = json.load(f)
    except Exception:
        pass
    ayar["tema"] = kod
    with open(AYAR_DOSYA, "w", encoding="utf-8") as f:
        json.dump(ayar, f, ensure_ascii=False, indent=2)


def aktif_tema() -> str:
    return _tema


def koyu_mu() -> bool:
    return _tema == "koyu"


# ── Palet ────────────────────────────────────────────────────────────────────
ARKA        = "#e6e9ee"   # sayfa zemini (yumuşak gri)
PANEL       = "#eceff3"   # bar / grup zeminleri
PANEL_KOYU  = "#dde1e7"   # önizleme zeminleri, ilerleme çubuğu zemini
KENAR_ZEMIN = "#d2d8e0"   # sol kenar çubuğu — içerikten net ayrılır, daha koyu
GIRDI       = "#f5f7f9"   # kart / buton / girdi / liste zemini (kırık beyaz)
KENARLIK    = "#c9d1da"
KENARLIK_K  = "#b4bfcb"   # biraz daha belirgin kenarlık (girdi, tutamaç)
METIN       = "#2b3442"
METIN_ORTA  = "#3d4756"
METIN_SOLUK = "#6b7686"
MAVI        = "#2e6da4"   # ana vurgu (yumuşatılmış mavi)
MAVI_PARLAK = "#3a7cb6"   # hover
MAVI_BASILI = "#275b8c"   # pressed
MAVI_ZEMIN  = "#dde8f2"   # seçili / vurgulu zemin
SARI        = "#d9a62e"   # ikincil vurgu (nadiren, daima koyu metinle)

# Eski ad uyumlulukları (araç modülleri import edebiliyor)
ARKA_KOYU = PANEL_KOYU
MAVI_ACIK = MAVI_PARLAK
MAVI_KOYU = MAVI_BASILI

STYLE = f"""
/* ── Genel ─────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {ARKA};
    color: {METIN};
    font-family: "Segoe UI", "Inter", "Roboto", "Ubuntu", sans-serif;
    font-size: 13px;
}}
QToolTip {{
    background-color: {METIN_ORTA};
    color: #f2f4f7;
    border: none;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 12px;
}}

/* ── Buton ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {GIRDI};
    color: {METIN_ORTA};
    border: 1px solid {KENARLIK_K};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: #e4e8ee;
    border-color: {MAVI_PARLAK};
    color: {METIN};
}}
QPushButton:pressed {{
    background-color: {KENARLIK};
    border-color: {MAVI};
}}
QPushButton:disabled {{
    color: #9aa5b1;
    background-color: {PANEL};
    border-color: {KENARLIK};
}}
QPushButton:default {{
    background-color: {MAVI};
    color: #f5f8fb;
    border: 1px solid {MAVI};
    font-weight: bold;
}}
QPushButton:default:hover   {{ background-color: {MAVI_PARLAK}; border-color: {MAVI_PARLAK}; }}
QPushButton:default:pressed {{ background-color: {MAVI_BASILI}; border-color: {MAVI_BASILI}; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox:hover, QRadioButton:hover {{ color: {MAVI}; }}

/* ── Girdi alanları ────────────────────────────────────────────────────── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {GIRDI};
    color: {METIN};
    border: 1px solid {KENARLIK_K};
    border-radius: 6px;
    padding: 5px 9px;
    selection-background-color: {MAVI};
    selection-color: #f5f8fb;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: #9aa7b6;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {MAVI};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background-color: {GIRDI};
    border: 1px solid {KENARLIK};
    border-radius: 6px;
    selection-background-color: {MAVI};
    selection-color: #f5f8fb;
}}

/* ── Liste / tablo / metin ─────────────────────────────────────────────── */
QListWidget, QTreeWidget, QTableWidget, QTableView {{
    background-color: {GIRDI};
    border: 1px solid {KENARLIK};
    border-radius: 8px;
    outline: none;
    alternate-background-color: {PANEL};
}}
QListWidget::item {{ padding: 3px 4px; border-radius: 4px; }}
QListWidget::item:hover, QTreeWidget::item:hover {{ background-color: {MAVI_ZEMIN}; }}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {{ background-color: {MAVI}; color: #f5f8fb; }}
QHeaderView::section {{
    background-color: {PANEL};
    color: {METIN_ORTA};
    border: none;
    border-right: 1px solid {KENARLIK};
    border-bottom: 1px solid {KENARLIK};
    padding: 6px 8px;
    font-weight: bold;
}}
QTableCornerButton::section {{ background-color: {PANEL}; border: none; }}
QTextEdit, QPlainTextEdit {{
    background-color: {GIRDI};
    color: {METIN_ORTA};
    border: 1px solid {KENARLIK};
    border-radius: 8px;
    selection-background-color: {MAVI};
    selection-color: #f5f8fb;
}}

/* ── Grup / sekme ──────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {PANEL};
    border: 1px solid {KENARLIK};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 4px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {MAVI};
}}
QTabWidget::pane {{
    background-color: {GIRDI};
    border: 1px solid {KENARLIK};
    border-radius: 8px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {METIN_SOLUK};
    border: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 18px;
    margin-right: 2px;
}}
QTabBar::tab:hover:!selected {{ background: #d8dde4; color: {METIN_ORTA}; }}
QTabBar::tab:selected {{
    background: {GIRDI};
    color: {MAVI};
    border: 1px solid {KENARLIK};
    border-bottom: none;
    border-top: 2px solid {MAVI};
    font-weight: bold;
}}

/* ── İlerleme / kaydırma / ayraç / slider ──────────────────────────────── */
QProgressBar {{
    border: 1px solid {KENARLIK};
    border-radius: 6px;
    background-color: {PANEL_KOYU};
    text-align: center;
    color: {METIN_ORTA};
    height: 18px;
}}
QProgressBar::chunk {{ background-color: {MAVI}; border-radius: 5px; }}
QScrollBar:vertical {{ background: transparent; width: 11px; border: none; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; border: none; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {KENARLIK_K}; border-radius: 5px; min-height: 24px; min-width: 24px;
}}
QScrollBar::handle:hover {{ background: {MAVI_PARLAK}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {KENARLIK}; }}
QSlider::groove:horizontal {{ height: 5px; background: {KENARLIK}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {MAVI_PARLAK}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 16px; margin: -6px 0; border-radius: 8px;
    background: {MAVI};
    border: 2px solid {GIRDI};
}}
QSlider::handle:horizontal:hover {{ background: {MAVI_PARLAK}; }}

/* ── Menü / durum çubuğu / diyalog ─────────────────────────────────────── */
QMenuBar {{ background-color: {PANEL}; color: {METIN_ORTA}; border-bottom: 1px solid {KENARLIK}; }}
QMenuBar::item {{ padding: 5px 11px; border-radius: 5px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {MAVI_ZEMIN}; color: {MAVI}; }}
QMenu {{
    background-color: {GIRDI};
    color: {METIN_ORTA};
    border: 1px solid {KENARLIK};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{ padding: 6px 24px; border-radius: 5px; }}
QMenu::item:selected {{ background-color: {MAVI}; color: #f5f8fb; }}
QMenu::separator {{ height: 1px; background: {KENARLIK}; margin: 4px 2px; }}
QStatusBar {{
    background-color: {PANEL};
    color: {METIN_SOLUK};
    border-top: 1px solid {KENARLIK};
}}
QDialog {{ background-color: {ARKA}; }}

/* ── Boxify kabuğu: kenar çubuğu ───────────────────────────────────────── */
#KenarCubuk {{
    background-color: {KENAR_ZEMIN};
    border-right: 1px solid #b6c0cc;
}}
#KenarCubuk QLabel {{ background: transparent; }}
#LogoAd {{
    color: {METIN};
    font-size: 21px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
#Surum {{
    color: {METIN_SOLUK};
    font-size: 11px;
    letter-spacing: 0.6px;
}}
#KenarBaslik {{
    color: #76818f;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 2px;
    padding: 10px 18px 4px 18px;
}}
#NavDugme {{
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #4d5765;
    text-align: left;
    padding: 9px 14px;
    margin: 1px 10px;
    font-size: 13px;
}}
#NavDugme:hover {{ background-color: #c4ccd6; color: {METIN}; }}
#NavDugme:checked {{
    background-color: #b3c8dc;
    color: {MAVI_BASILI};
    font-weight: bold;
}}
#KenarDip {{ color: #76818f; font-size: 10px; padding: 10px 18px; }}
#DilEtiket {{ color: #76818f; font-size: 10px; letter-spacing: 1px; }}
#DilDugme {{
    background-color: transparent;
    border: 1px solid {KENARLIK_K};
    border-radius: 6px;
    color: #4d5765;
    font-size: 11px;
    font-weight: bold;
    padding: 3px 0;
}}
#DilDugme:hover {{ background-color: #c4ccd6; color: {METIN}; }}
#DilDugme:checked {{
    background-color: {MAVI};
    border-color: {MAVI};
    color: #f5f8fb;
}}

/* ── Ana sayfa kartları ────────────────────────────────────────────────── */
#Kart {{
    background-color: {GIRDI};
    border: 1px solid {KENARLIK};
    border-radius: 10px;
}}
#Kart:hover {{ border: 1px solid {MAVI_PARLAK}; background-color: #edf1f6; }}
#Kart QLabel {{ background: transparent; }}
#KartRozet {{
    color: {MAVI_BASILI};
    background-color: {MAVI_ZEMIN};
    border-radius: 16px;
    font-size: 15px;
}}
#KartBaslik {{ color: {METIN}; font-size: 15px; font-weight: bold; }}
#KartOzet {{ color: {MAVI}; font-size: 12px; font-weight: 600; }}
#KartAciklama {{ color: {METIN_SOLUK}; font-size: 12px; }}
#AnaBaslik {{ color: {METIN}; font-size: 28px; font-weight: bold; }}
#AnaAltBaslik {{ color: {METIN_SOLUK}; font-size: 13px; }}

/* ── İpuçları sayfası ──────────────────────────────────────────────────── */
#IpucuKart {{
    background-color: {GIRDI};
    border: 1px solid {KENARLIK};
    border-radius: 10px;
}}
#IpucuKart:hover {{ border-color: {KENARLIK_K}; }}
#IpucuKart QLabel {{ background: transparent; }}
#IpucuBaslik {{ color: {METIN}; font-size: 15px; font-weight: bold; }}
#IpucuMetin {{ color: {METIN_ORTA}; font-size: 12px; }}
#IpucuGenel {{
    background-color: #d6e2ee;
    border: 1px solid #b7c9da;
    border-radius: 10px;
}}
#IpucuGenel QLabel {{ background: transparent; }}
"""


# ── Koyu tema ────────────────────────────────────────────────────────────────
#
# Açık palet tonu -> koyu karşılığı. Burada YALNIZCA arayüz kromu var:
# zeminler, kenarlıklar, metin ve vurgu tonları.
#
# Veri renkleri (tespit kutuları, sınıf renkleri, eğri renkleri: #f5c518,
# #00bcd4, #b39ddb, #9e9e9e, #8e6bbf, #d9a62e…) bilerek DIŞARIDA bırakıldı.
# Onlar renk körlüğü gözetilerek seçildi ve koyu tuval üzerinde okunuyorlar;
# temaya göre değiştirmek o dengeyi bozardı. Zaten yalnızca QPainter/QColor
# ile kullanılıyorlar, aşağıdaki dönüşüm ise sadece stil metinlerine bakıyor.
KOYU_HARITA = {
    ARKA:        "#1b1f26",   # sayfa zemini
    PANEL:       "#232830",   # bar / grup zeminleri
    PANEL_KOYU:  "#2b313a",   # önizleme / ilerleme zemini
    KENAR_ZEMIN: "#161a20",   # sol kenar çubuğu
    GIRDI:       "#2b313a",   # kart / buton / girdi / liste zemini
    KENARLIK:    "#3a4149",
    KENARLIK_K:  "#49515b",
    METIN:       "#e3e8ef",
    METIN_ORTA:  "#c6cdd6",
    METIN_SOLUK: "#98a3b0",
    MAVI:        "#4a90d9",   # koyu zeminde okunması için biraz açıldı
    MAVI_PARLAK: "#5ba0e6",
    MAVI_BASILI: "#3d82c4",
    MAVI_ZEMIN:  "#23374a",
    # araç modüllerinde doğrudan yazılmış tonlar
    "#f5f8fb":   "#f0f6fc",   # vurgu düğmesi üstündeki metin — açık kalmalı
    "#f2f4f7":   "#e3e8ef",
    "#42505f":   "#b9c2cd",
    "#4d5765":   "#aeb8c4",
    "#76818f":   "#8e99a7",
    "#8b95a3":   "#7f8a98",
    "#9aa5b1":   "#79848f",
    "#9aa7b6":   "#7c8794",
    "#c4ccd6":   "#49515b",
    "#b6c0cc":   "#525b66",
    "#d4dae2":   "#3a4149",
    "#d8dde4":   "#333a43",
    "#e3e8ee":   "#2b313a",
    "#e4e8ee":   "#2b313a",
    "#edf1f6":   "#2a313b",   # kart hover
    "#f2f5f8":   "#262c35",   # eğitimdeki sabit şerit
    "#b3c8dc":   "#2f5375",   # kaydırma çubuğu tutamacı
    "#b7c9da":   "#3d82c4",
    "#d6e2ee":   "#23374a",
    "#ffffff":   "#232830",   # beyaz zeminler (grafik tuvali vb.)
}

_KOYU_ARAMA = {k.lower(): v for k, v in KOYU_HARITA.items()}


def koyulastir(stil_metni: str) -> str:
    """Bir stil metnindeki açık palet renklerini koyu karşılıklarıyla değiştirir.

    Bilinmeyen renkler olduğu gibi kalır — veri renklerinin korunması bu
    sayede oluyor.
    """
    if not stil_metni:
        return stil_metni
    import re as _re

    def _degistir(m):
        return _KOYU_ARAMA.get(m.group(0).lower(), m.group(0))

    return _re.sub(r"#[0-9a-fA-F]{6}\b", _degistir, stil_metni)


STYLE_KOYU = koyulastir(STYLE)


def stil() -> str:
    """Aktif temanın uygulama geneli stil metni."""
    return STYLE_KOYU if koyu_mu() else STYLE


def renk(acik_ton: str) -> str:
    """Elle çizen (QPainter) widget'lar için tek renk çevirisi.

    Stil metni yamalaması yalnızca `setStyleSheet` çağrılarını yakalar; kendi
    boyamasını yapan widget'lar (ör. Eğitim'deki eğri) rengi buradan ister.
    """
    if not koyu_mu():
        return acik_ton
    return _KOYU_ARAMA.get(acik_ton.lower(), acik_ton)


# ── Yamalar ──────────────────────────────────────────────────────────────────

_yamalar_kuruldu = False


def yamalari_kur():
    """`setStyleSheet` çağrılarını koyu temaya çevir.

    Araç modülleri kendi ayrıntı stillerini renkleri doğrudan yazarak veriyor.
    Bunları tek tek düzenlemek yerine — dil desteğinde olduğu gibi — Qt API'si
    yamalanıyor. Araç kodları temadan habersiz kalıyor, sonradan eklenecek
    araçlar da paletteki tonları kullandıkça kendiliğinden uyumlu oluyor.

    Açık temada yama kurulmaz; hiçbir maliyeti olmasın diye.
    """
    global _yamalar_kuruldu
    if _yamalar_kuruldu or not koyu_mu():
        return
    from PyQt5 import QtWidgets as W

    for sinif in (W.QWidget, W.QApplication):
        ozgun = sinif.setStyleSheet

        def sarmal(self, metin, _ozgun=ozgun):
            return _ozgun(self, koyulastir(metin))

        sinif.setStyleSheet = sarmal
    _yamalar_kuruldu = True
