import sys
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QListWidget, QListWidgetItem, QFileDialog,
    QFrame, QStatusBar, QGroupBox, QMessageBox, QLineEdit, QAction,
    QSpinBox, QDoubleSpinBox, QProgressBar, QComboBox, QSizePolicy, QCheckBox
)
from PyQt5.QtCore import Qt, QUrl, QThread, pyqtSignal
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

from ..tema import STYLE  # ortak açık tema — bkz. boxify/tema.py
from ..klasor_ac import klasoru_ac


def ms_to_str(ms: int) -> str:
    ms = max(0, int(ms))
    m = ms // 60000
    s = (ms % 60000) // 1000
    rem = ms % 1000
    return f"{m:02d}:{s:02d}.{rem:03d}"


def str_to_ms(text: str) -> int:
    try:
        text = text.strip()
        left, right = (text.split(':', 1) if ':' in text else ('0', text))
        m = int(left)
        if '.' in right:
            s_part, ms_part = right.split('.', 1)
            ms = int((ms_part + '000')[:3])
        else:
            s_part, ms = right, 0
        return (m * 60 + int(s_part)) * 1000 + ms
    except Exception:
        return -1


def ms_to_ffmpeg(ms: int) -> str:
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    r = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{r:03d}"


class ExtractWorker(QThread):
    progress = pyqtSignal(int, int)   # current, total
    finished = pyqtSignal(str, int)   # out_dir, count
    error    = pyqtSignal(str)

    def __init__(self, video_path, out_dir, fps_val,
                 use_range, start_ms, end_ms, fmt):
        super().__init__()
        self.video_path = video_path
        self.out_dir    = out_dir
        self.fps_val    = fps_val
        self.use_range  = use_range
        self.start_ms   = start_ms
        self.end_ms     = end_ms
        self.fmt        = fmt

    def run(self):
        os.makedirs(self.out_dir, exist_ok=True)
        pattern = os.path.join(self.out_dir, f"kare_%05d.{self.fmt}")

        cmd = ["ffmpeg", "-y"]
        if self.use_range:
            cmd += ["-ss", ms_to_ffmpeg(self.start_ms),
                    "-to", ms_to_ffmpeg(self.end_ms)]
        cmd += ["-i", self.video_path,
                "-vf", f"fps={self.fps_val}",
                "-q:v", "2",
                pattern]

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True
        )
        proc.wait()
        if proc.returncode != 0:
            self.error.emit("ffmpeg hatası oluştu.")
            return

        saved = len([f for f in os.listdir(self.out_dir)
                     if f.startswith("kare_")])
        self.finished.emit(self.out_dir, saved)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kare Alıcı — Video → Dataset")
        self.setMinimumSize(1200, 720)
        self._current_video = None
        self._duration = 0
        self._slider_pressed = False
        self._worker = None
        self._build_player()
        self._build_ui()
        self._build_menu()
        self._connect_player()

    def _build_player(self):
        self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background:#dde1e7;")
        self.player.setVideoOutput(self.video_widget)

    def _connect_player(self):
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.stateChanged.connect(self._on_state)

    # ─────────────────────────── UI

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_video_list())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([200, 740, 260])
        vbox.addWidget(splitter, 1)
        vbox.addWidget(self._build_controls())

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Dosya > Video Aç ile başlayın")

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background:#eceff3; border-bottom:1px solid #c9d1da;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        b = QPushButton("Video Aç")
        b.clicked.connect(self._open_videos)
        row.addWidget(b)
        row.addStretch()
        return bar

    def _build_video_list(self) -> QWidget:
        w = QWidget()
        w.setMaximumWidth(220)
        w.setMinimumWidth(150)
        v = QVBoxLayout(w)
        v.setContentsMargins(4, 6, 4, 4)
        lbl = QLabel("Videolar")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:2px 4px;")
        v.addWidget(lbl)
        self.video_list = QListWidget()
        self.video_list.currentRowChanged.connect(self._on_video_selected)
        v.addWidget(self.video_list)
        return w

    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.video_widget, 1)
        return w

    def _build_controls(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(56)
        bar.setStyleSheet("background:#eceff3; border-top:1px solid #c9d1da;")
        v = QVBoxLayout(bar)
        v.setContentsMargins(10, 4, 10, 4)
        v.setSpacing(4)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, '_slider_pressed', True))
        self.seek_slider.sliderReleased.connect(self._slider_release)
        self.seek_slider.sliderMoved.connect(
            lambda val: self.time_lbl.setText(f"{ms_to_str(val)} / {ms_to_str(self._duration)}"))
        v.addWidget(self.seek_slider)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.play_btn = QPushButton("▶  Oynat")
        self.play_btn.setFixedWidth(100)
        self.play_btn.clicked.connect(self._toggle_play)
        self.play_btn.setEnabled(False)
        row.addWidget(self.play_btn)

        self.time_lbl = QLabel("00:00.000 / 00:00.000")
        self.time_lbl.setStyleSheet("color:#6b7686; font-family:monospace; font-size:12px;")
        row.addWidget(self.time_lbl)
        row.addStretch()
        v.addLayout(row)
        return bar

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(240)
        w.setMaximumWidth(290)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        # ── Ayarlar grubu
        grp = QGroupBox("Kare Çıkarma Ayarları")
        gv = QVBoxLayout(grp)
        gv.setSpacing(6)

        # FPS
        gv.addWidget(QLabel("Kaç saniyede bir kare?"))
        h = QHBoxLayout()
        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0.04, 60.0)
        self.interval_spin.setSingleStep(0.5)
        self.interval_spin.setValue(1.0)
        self.interval_spin.setDecimals(2)
        h.addWidget(self.interval_spin)
        h.addWidget(QLabel("saniye"))
        gv.addLayout(h)

        # Format
        gv.addWidget(QLabel("Görüntü formatı"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.addItems(["jpg", "png"])
        gv.addWidget(self.fmt_combo)

        # Zaman aralığı
        self.range_chk = QCheckBox("Belirli bir aralık kullan")
        self.range_chk.toggled.connect(self._toggle_range)
        gv.addWidget(self.range_chk)

        range_frame = QFrame()
        range_frame.setStyleSheet("QFrame { border: 1px solid #c9d1da; border-radius:4px; }")
        rv = QVBoxLayout(range_frame)
        rv.setContentsMargins(6, 6, 6, 6)
        rv.setSpacing(4)

        rv.addWidget(QLabel("Başlangıç (dd:ss.ms)"))
        h1 = QHBoxLayout()
        self.start_edit = QLineEdit("00:00.000")
        h1.addWidget(self.start_edit)
        self.set_start_btn = QPushButton("Şimdiki An")
        self.set_start_btn.clicked.connect(
            lambda: self.start_edit.setText(ms_to_str(self.player.position())))
        self.set_start_btn.setEnabled(False)
        h1.addWidget(self.set_start_btn)
        rv.addLayout(h1)

        rv.addWidget(QLabel("Bitiş (dd:ss.ms)"))
        h2 = QHBoxLayout()
        self.end_edit = QLineEdit("00:00.000")
        h2.addWidget(self.end_edit)
        self.set_end_btn = QPushButton("Şimdiki An")
        self.set_end_btn.clicked.connect(
            lambda: self.end_edit.setText(ms_to_str(self.player.position())))
        self.set_end_btn.setEnabled(False)
        h2.addWidget(self.set_end_btn)
        rv.addLayout(h2)

        self.range_frame = range_frame
        self.range_frame.setVisible(False)
        gv.addWidget(range_frame)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # belirsiz mod
        gv.addWidget(self.progress_bar)

        # Çıkar butonu
        self.extract_btn = QPushButton("📷  Kareleri Çıkar ve Kaydet")
        self.extract_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; padding:8px;")
        self.extract_btn.clicked.connect(self._do_extract)
        self.extract_btn.setEnabled(False)
        gv.addWidget(self.extract_btn)

        v.addWidget(grp)

        # ── Çıktı bilgisi grubu
        grp2 = QGroupBox("Son Çıkarma")
        gv2 = QVBoxLayout(grp2)
        self.result_lbl = QLabel("—")
        self.result_lbl.setWordWrap(True)
        self.result_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        gv2.addWidget(self.result_lbl)

        self.open_folder_btn = QPushButton("📁  Klasörü Aç")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        self.open_folder_btn.setEnabled(False)
        gv2.addWidget(self.open_folder_btn)

        v.addWidget(grp2)
        v.addStretch()

        self._last_out_dir = None
        return w

    def _build_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("Dosya")
        for label, slot, sc in [
            ("Video Aç", self._open_videos, "Ctrl+O"),
            ("Çıkış",   self.close,         "Ctrl+Q"),
        ]:
            a = QAction(label, self)
            if sc:
                a.setShortcut(sc)
            a.triggered.connect(slot)
            fm.addAction(a)

    # ─────────────────────────── video open / select

    def _open_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Video Seç", "",
            "Video Dosyaları (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv);;Tüm Dosyalar (*)"
        )
        for p in paths:
            if not any(self.video_list.item(i).data(Qt.UserRole) == p
                       for i in range(self.video_list.count())):
                item = QListWidgetItem(os.path.basename(p))
                item.setData(Qt.UserRole, p)
                item.setToolTip(p)
                self.video_list.addItem(item)
        if self.video_list.count() > 0 and self._current_video is None:
            self.video_list.setCurrentRow(0)

    def _on_video_selected(self, row: int):
        if row < 0:
            return
        path = self.video_list.item(row).data(Qt.UserRole)
        self._current_video = path
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.player.pause()
        self.play_btn.setEnabled(True)
        self.set_start_btn.setEnabled(True)
        self.set_end_btn.setEnabled(True)
        self.extract_btn.setEnabled(True)
        self.setWindowTitle(f"Kare Alıcı — {os.path.basename(path)}")
        self.status.showMessage(f"Yüklendi: {path}")
        self.result_lbl.setText("—")
        self.open_folder_btn.setEnabled(False)
        self._last_out_dir = None

    # ─────────────────────────── player

    def _toggle_play(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _slider_release(self):
        self._slider_pressed = False
        self.player.setPosition(self.seek_slider.value())

    def _on_position(self, pos: int):
        if not self._slider_pressed:
            self.seek_slider.setValue(pos)
        self.time_lbl.setText(f"{ms_to_str(pos)} / {ms_to_str(self._duration)}")

    def _on_duration(self, dur: int):
        self._duration = dur
        self.seek_slider.setRange(0, dur)
        self.end_edit.setText(ms_to_str(dur))
        self.time_lbl.setText(f"00:00.000 / {ms_to_str(dur)}")

    def _on_state(self, state):
        self.play_btn.setText(
            "⏸  Duraklat" if state == QMediaPlayer.PlayingState else "▶  Oynat")

    # ─────────────────────────── range toggle

    def _toggle_range(self, checked: bool):
        self.range_frame.setVisible(checked)

    # ─────────────────────────── extract

    def _do_extract(self):
        if not self._current_video:
            return

        interval = self.interval_spin.value()
        fps_val = f"1/{interval}" if interval >= 1 else str(round(1 / interval, 4))

        use_range = self.range_chk.isChecked()
        start_ms = end_ms = 0
        if use_range:
            start_ms = str_to_ms(self.start_edit.text())
            end_ms   = str_to_ms(self.end_edit.text())
            if start_ms < 0 or end_ms < 0:
                QMessageBox.warning(self, "Hata", "Zaman formatı hatalı. Örnek: 00:13.500")
                return
            if end_ms <= start_ms:
                QMessageBox.warning(self, "Hata", "Bitiş zamanı başlangıçtan büyük olmalı.")
                return

        video_dir  = os.path.dirname(self._current_video)
        video_stem = os.path.splitext(os.path.basename(self._current_video))[0]
        out_dir    = os.path.join(video_dir, video_stem)
        fmt        = self.fmt_combo.currentText()

        self.extract_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status.showMessage(f"Kareler çıkarılıyor → {out_dir}")

        self._worker = ExtractWorker(
            self._current_video, out_dir,
            fps_val, use_range, start_ms, end_ms, fmt
        )
        self._worker.finished.connect(self._on_extract_done)
        self._worker.error.connect(self._on_extract_error)
        self._worker.start()

    def _on_extract_done(self, out_dir: str, count: int):
        self.progress_bar.setVisible(False)
        self.extract_btn.setEnabled(True)
        self._last_out_dir = out_dir
        self.open_folder_btn.setEnabled(True)
        self.result_lbl.setText(
            f"✅ {count} kare kaydedildi\n📁 {out_dir}")
        self.status.showMessage(f"{count} kare kaydedildi: {out_dir}")

    def _on_extract_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self.extract_btn.setEnabled(True)
        QMessageBox.critical(self, "Hata", msg)
        self.status.showMessage("Çıkarma başarısız.")

    def _open_output_folder(self):
        if self._last_out_dir and os.path.isdir(self._last_out_dir):
            klasoru_ac(self._last_out_dir)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Kare Alıcı")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
