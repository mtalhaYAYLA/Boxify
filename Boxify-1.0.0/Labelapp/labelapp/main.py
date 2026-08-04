import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

STYLE = """
QWidget {
    background-color: #2b2b2b;
    color: #d4d4d4;
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}
QPushButton {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 11px;
}
QPushButton:hover  { background-color: #484848; }
QPushButton:pressed { background-color: #555; }
QPushButton:disabled { color: #555; background-color: #2f2f2f; border-color: #444; }
QListWidget {
    background-color: #232323;
    border: 1px solid #3a3a3a;
    outline: none;
}
QListWidget::item:selected { background-color: #0d7acc; color: white; }
QListWidget::item:hover { background-color: #333; }
QComboBox, QSpinBox {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 6px;
}
QComboBox::drop-down { border: none; }
QGroupBox {
    border: 1px solid #4a4a4a;
    border-radius: 5px;
    margin-top: 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTextEdit {
    background-color: #1a1a1a;
    color: #ccc;
    border: 1px solid #3a3a3a;
}
QProgressBar {
    border: 1px solid #555;
    border-radius: 3px;
    background-color: #333;
    text-align: center;
    color: white;
    height: 18px;
}
QProgressBar::chunk { background-color: #0d7acc; border-radius: 2px; }
QMenuBar { background-color: #1e1e1e; color: #ccc; border-bottom: 1px solid #3a3a3a; }
QMenuBar::item:selected { background-color: #3c3c3c; }
QMenu { background-color: #252525; color: #ccc; border: 1px solid #444; }
QMenu::item:selected { background-color: #0d7acc; color: white; }
QStatusBar { background-color: #1e1e1e; color: #888; border-top: 1px solid #3a3a3a; }
QScrollBar:vertical {
    background: #252525; width: 8px; border: none;
}
QScrollBar::handle:vertical { background: #555; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QSplitter::handle { background: #3a3a3a; }
QDialog { background-color: #2b2b2b; }
"""


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("YOLOLabel")

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
