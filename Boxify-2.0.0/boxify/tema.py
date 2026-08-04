"""Boxify ortak teması.

Tek koyu tema, tüm araçlar bunu paylaşır. Renk seçimi kırmızı-yeşil ayrımına
dayanmaz: ana vurgu MAVİ, ikincil vurgu SARI; durumlar ayrıca metin ve
desenle verilir.
"""

# ── Palet ────────────────────────────────────────────────────────────────────
ARKA        = "#2b2b2b"   # içerik zemini
ARKA_KOYU   = "#1d1d1d"   # kenar çubuğu / barlar
PANEL       = "#232323"   # liste, tablo, log zeminleri
GIRDI       = "#3c3c3c"   # buton / girdi zemini
KENARLIK    = "#4a4a4a"
METIN       = "#d4d4d4"
METIN_SOLUK = "#8a8a8a"
MAVI        = "#0d7acc"   # ana vurgu
MAVI_ACIK   = "#1b8ce0"
SARI        = "#e6c34a"   # ikincil vurgu (rozet, sürüm, uyarı)

STYLE = f"""
/* ── Genel ─────────────────────────────────────────────────────────────── */
QWidget {{
    background-color: {ARKA};
    color: {METIN};
    font-family: "Segoe UI", "Ubuntu", Arial, sans-serif;
    font-size: 12px;
}}
QToolTip {{
    background-color: {ARKA_KOYU};
    color: {METIN};
    border: 1px solid {KENARLIK};
    padding: 4px 6px;
}}

/* ── Buton / girdi ─────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {GIRDI};
    color: {METIN};
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 11px;
}}
QPushButton:hover    {{ background-color: #484848; }}
QPushButton:pressed  {{ background-color: #555; }}
QPushButton:disabled {{ color: #555; background-color: #2f2f2f; border-color: #444; }}
QPushButton:default  {{ border-color: {MAVI}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {GIRDI};
    color: {METIN};
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: {MAVI};
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {PANEL};
    border: 1px solid {KENARLIK};
    selection-background-color: {MAVI};
    selection-color: white;
}}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; }}

/* ── Liste / tablo / metin ─────────────────────────────────────────────── */
QListWidget, QTreeWidget, QTableWidget, QTableView {{
    background-color: {PANEL};
    border: 1px solid #3a3a3a;
    outline: none;
    alternate-background-color: #262626;
}}
QListWidget::item:selected, QTreeWidget::item:selected,
QTableWidget::item:selected {{ background-color: {MAVI}; color: white; }}
QListWidget::item:hover {{ background-color: #333; }}
QHeaderView::section {{
    background-color: {ARKA_KOYU};
    color: {METIN};
    border: none;
    border-right: 1px solid #3a3a3a;
    border-bottom: 1px solid #3a3a3a;
    padding: 4px 6px;
    font-weight: bold;
}}
QTableCornerButton::section {{ background-color: {ARKA_KOYU}; border: none; }}
QTextEdit, QPlainTextEdit {{
    background-color: #1a1a1a;
    color: #ccc;
    border: 1px solid #3a3a3a;
    selection-background-color: {MAVI};
}}

/* ── Grup / sekme ──────────────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {KENARLIK};
    border-radius: 5px;
    margin-top: 12px;
    font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QTabWidget::pane {{ border: 1px solid #3a3a3a; top: -1px; }}
QTabBar::tab {{
    background: {ARKA_KOYU};
    color: {METIN_SOLUK};
    border: 1px solid #3a3a3a;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 14px;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {ARKA};
    color: {METIN};
    border-top: 2px solid {MAVI};
}}
QTabBar::tab:hover:!selected {{ background: #2f2f2f; }}

/* ── İlerleme / kaydırma / ayraç ───────────────────────────────────────── */
QProgressBar {{
    border: 1px solid #555;
    border-radius: 3px;
    background-color: #333;
    text-align: center;
    color: white;
    height: 18px;
}}
QProgressBar::chunk {{ background-color: {MAVI}; border-radius: 2px; }}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; border: none; }}
QScrollBar:horizontal {{ background: {PANEL}; height: 10px; border: none; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: #555; border-radius: 4px; min-height: 20px; min-width: 20px;
}}
QScrollBar::handle:hover {{ background: #6a6a6a; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QSplitter::handle {{ background: #3a3a3a; }}
QSlider::groove:horizontal {{ height: 5px; background: #444; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; margin: -5px 0; border-radius: 7px; background: {MAVI_ACIK};
}}

/* ── Menü / durum çubuğu / diyalog ─────────────────────────────────────── */
QMenuBar {{ background-color: {ARKA_KOYU}; color: #ccc; border-bottom: 1px solid #3a3a3a; }}
QMenuBar::item:selected {{ background-color: {GIRDI}; }}
QMenu {{ background-color: #252525; color: #ccc; border: 1px solid #444; }}
QMenu::item:selected {{ background-color: {MAVI}; color: white; }}
QStatusBar {{ background-color: {ARKA_KOYU}; color: {METIN_SOLUK}; border-top: 1px solid #3a3a3a; }}
QDialog {{ background-color: {ARKA}; }}

/* ── Boxify kabuğu ─────────────────────────────────────────────────────── */
#KenarCubuk {{
    background-color: {ARKA_KOYU};
    border-right: 1px solid #3a3a3a;
}}
#KenarCubuk QLabel {{ background: transparent; }}
#LogoAd {{
    color: {METIN};
    font-size: 21px;
    font-weight: bold;
    letter-spacing: 1px;
}}
#Surum {{ color: {SARI}; font-size: 11px; }}
#KenarBaslik {{
    color: {METIN_SOLUK};
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 2px;
    padding: 6px 14px 2px 14px;
}}
#NavDugme {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    color: #b8b8b8;
    text-align: left;
    padding: 9px 12px;
    font-size: 13px;
}}
#NavDugme:hover {{ background-color: #262626; color: {METIN}; }}
#NavDugme:checked {{
    background-color: #26343f;
    border-left: 3px solid {MAVI};
    color: white;
    font-weight: bold;
}}
#KenarDip {{ color: #6a6a6a; font-size: 10px; padding: 8px 14px; }}

/* ── Ana sayfa kartları ────────────────────────────────────────────────── */
#Kart {{
    background-color: {PANEL};
    border: 1px solid #3a3a3a;
    border-radius: 8px;
}}
#Kart:hover {{ border-color: {MAVI}; background-color: #27313a; }}
#Kart QLabel {{ background: transparent; }}
#KartRozet {{
    color: {ARKA_KOYU};
    background-color: {SARI};
    border-radius: 13px;
    font-size: 13px;
    font-weight: bold;
}}
#KartBaslik {{ color: {METIN}; font-size: 15px; font-weight: bold; }}
#KartOzet {{ color: {METIN_SOLUK}; font-size: 12px; }}
#KartAciklama {{ color: #a8a8a8; font-size: 11px; }}
#AnaBaslik {{ color: {METIN}; font-size: 26px; font-weight: bold; }}
#AnaAltBaslik {{ color: {METIN_SOLUK}; font-size: 13px; }}
#ZincirSatir {{
    color: {METIN_SOLUK};
    font-family: monospace;
    font-size: 12px;
    background-color: {ARKA_KOYU};
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 10px 14px;
}}
"""
