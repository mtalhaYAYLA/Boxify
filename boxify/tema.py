"""Boxify ortak teması — açık (light) tema.

Tasarım dili (göz yormayan, düşük parlamalı):
- Sayfa zemini yumuşak gri (#EFF1F5); kart/girdi zeminleri kırık beyaz
  (#FBFCFD) — saf beyaz kullanılmaz, parlamayı azaltır.
- Vurgu: yumuşatılmış profesyonel mavi (#2E6DA4); hover biraz açılır,
  basılıda koyulaşır. Neon/doygun tonlardan kaçınılır.
- Metin: yumuşak antrasit (#2B3442), ikincil metin gri (#6B7686).
- Köşeler yumuşak (6-10px), tüm tıklanabilir öğelerde hover/pressed efekti,
  girdilerde odak (focus) mavi çerçevesi.
- Renk körlüğü kuralı korunur: kırmızı-yeşil ayrımına dayanılmaz; durumlar
  mavi tonları + metin + desenle verilir.
"""

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
