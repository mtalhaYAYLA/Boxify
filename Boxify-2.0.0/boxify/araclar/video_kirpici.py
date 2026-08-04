import sys
import os
import re
import json
import shutil
import subprocess

from boxify.klasor_ac import klasoru_ac


def _fix_gstreamer_glib():
    """conda ortamının glib'i ile sistem gstreamer eklentileri uyuşmadığında
    eklentiler yüklenemiyor:
        Failed to load plugin '.../libgstlibav.so':
        .../lib/libgio-2.0.so.0: undefined symbol: g_variant_builder_init_static
        Error: "Your GStreamer installation is missing a plug-in."
    Sonuç: video/ses çözücü bulunamaz, oynatıcı hiç çalışmaz. Sistem glib'ini
    LD_PRELOAD ile öne alıp süreci bir kez yeniden başlatarak düzeltiyoruz.
    Kapatmak için: VK_NO_GLIB_FIX=1 python main.py
    """
    if os.environ.get("VK_GLIB_FIXED") or os.environ.get("VK_NO_GLIB_FIX"):
        return
    sys_dir = "/usr/lib/x86_64-linux-gnu"
    libs = [f"{sys_dir}/lib{n}-2.0.so.0" for n in ("glib", "gobject", "gio")]
    conda_gio = os.path.join(sys.prefix, "lib", "libgio-2.0.so.0")
    # Sadece ortamın kendi glib'i varsa ve eklentiler sistemden geliyorsa gerekli
    if not os.path.exists(conda_gio) or not os.path.isdir(f"{sys_dir}/gstreamer-1.0"):
        return
    if not all(os.path.exists(p) for p in libs):
        return
    env = dict(os.environ)
    env["VK_GLIB_FIXED"] = "1"
    preload = ":".join(libs)
    if env.get("LD_PRELOAD"):
        preload += ":" + env["LD_PRELOAD"]
    env["LD_PRELOAD"] = preload
    try:
        os.execve(sys.executable, [sys.executable] + sys.argv, env)
    except OSError:
        pass        # başarısızsa normal akışa devam et


# PyQt/gstreamer yüklenmeden önce çalışmalı
if __name__ == "__main__":
    _fix_gstreamer_glib()

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QListWidget, QListWidgetItem, QFileDialog,
    QFrame, QStatusBar, QGroupBox, QMessageBox, QLineEdit, QAction, QSizePolicy,
    QComboBox, QProgressBar, QCheckBox
)
from PyQt5.QtCore import Qt, QUrl, QTimer, QThread, pyqtSignal, QRectF
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

# gst-vaapi video sink bazı sürücülerde pencere alamıyor ve boru hattını
# kilitliyor: görüntü donuyor, seek/kare atlama çalışmıyor. Sadece SINK'i
# devre dışı bırakıyoruz (donanımla çözme etkin kalır).
# Donanım sink'ini geri istersen: VK_KEEP_VAAPI=1 python main.py
if not os.environ.get("VK_KEEP_VAAPI"):
    os.environ.setdefault("GST_PLUGIN_FEATURE_RANK", "vaapisink:0")

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
QLineEdit, QComboBox {
    background-color: #1a1a1a;
    color: #d4d4d4;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 14px;
    font-family: monospace;
}
QComboBox { font-size: 12px; font-family: "Segoe UI", Arial, sans-serif; }
QComboBox::drop-down { border: none; width: 20px; }
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
QProgressBar {
    border: 1px solid #555; border-radius: 3px;
    background-color: #333; text-align: center; color: white; height: 16px;
}
QProgressBar::chunk { background-color: #0d7acc; border-radius: 2px; }
QSlider::groove:horizontal {
    height: 4px;
    background: #444;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #0d7acc;
    border: none;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal { background: #0d7acc; border-radius: 2px; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #555; border-radius: 3px; background: #1a1a1a;
}
QCheckBox::indicator:checked { background: #0d7acc; border-color: #0d7acc; }
QMenuBar { background-color: #1e1e1e; color: #ccc; border-bottom: 1px solid #3a3a3a; }
QMenuBar::item:selected { background-color: #3c3c3c; }
QMenu { background-color: #252525; color: #ccc; border: 1px solid #444; }
QMenu::item:selected { background-color: #0d7acc; color: white; }
QStatusBar { background-color: #1e1e1e; color: #888; border-top: 1px solid #3a3a3a; }
QSplitter::handle { background: #3a3a3a; }
QDialog { background-color: #2b2b2b; }
"""

VIDEO_EXTS = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv", ".m4v", ".mpg", ".mpeg")


def ms_to_str(ms: int) -> str:
    ms = max(0, int(ms))
    m = ms // 60000
    s = (ms % 60000) // 1000
    rem = ms % 1000
    return f"{m:02d}:{s:02d}.{rem:03d}"


def str_to_ms(text: str) -> int:
    """'13.5', '00:13.500', '1:02:03.250' → ms. Geçersizse -1."""
    try:
        text = text.strip().replace(',', '.')
        if not text:
            return -1
        parts = text.split(':')
        if len(parts) > 3:
            return -1
        total = float(parts[-1])          # saniye (+ ondalık)
        if total < 0:
            return -1
        if len(parts) >= 2:
            total += int(parts[-2]) * 60
        if len(parts) == 3:
            total += int(parts[0]) * 3600
        return int(round(total * 1000))
    except Exception:
        return -1


def ms_to_ffmpeg(ms: int) -> str:
    ms = max(0, int(ms))
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms_rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"


def probe_video(path: str) -> dict:
    """ffprobe ile süre / fps / akış bilgisi. Okunamazsa boş dict."""
    cmd = ["ffprobe", "-v", "error", "-of", "json",
           "-show_entries", "format=duration",
           "-show_entries", "stream=codec_type,avg_frame_rate", path]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            return {}
        data = json.loads(out.stdout or "{}")
    except Exception:
        return {}

    info = {"duration_ms": 0, "fps": 0.0, "has_video": False, "has_audio": False}
    try:
        info["duration_ms"] = int(round(float(data["format"]["duration"]) * 1000))
    except Exception:
        pass
    for st in data.get("streams", []):
        kind = st.get("codec_type")
        if kind == "video":
            info["has_video"] = True
            if not info["fps"]:
                try:
                    num, den = st.get("avg_frame_rate", "0/0").split('/')
                    if float(den):
                        info["fps"] = float(num) / float(den)
                except Exception:
                    pass
        elif kind == "audio":
            info["has_audio"] = True
    return info


class ClipWorker(QThread):
    """ffmpeg'i arka planda çalıştırır; UI donmaz."""
    progress = pyqtSignal(int)          # 0-100
    done = pyqtSignal(str, int)         # out_file, gerçek süre (ms)
    error = pyqtSignal(str)

    def __init__(self, src, out_file, start_ms, end_ms, precise):
        super().__init__()
        self.src = src
        self.out_file = out_file
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.precise = precise
        self._proc = None
        self._cancelled = False

    def run(self):
        dur_ms = max(1, self.end_ms - self.start_ms)

        # -ss MUTLAKA -i'den ÖNCE: giriş tarafında arama yapılır, kesim doğru
        # yerden başlar. -ss girişten sonra + "-c copy" olursa GOP ortasından
        # kopyalanır ve video akışı bozulur / hiç yazılmaz.
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats",
               "-progress", "pipe:1", "-y",
               "-ss", ms_to_ffmpeg(self.start_ms),
               "-i", self.src,
               "-t", ms_to_ffmpeg(dur_ms)]
        if self.precise:
            cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart"]
        else:
            cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
        cmd.append(self.out_file)

        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1
            )
        except FileNotFoundError:
            self.error.emit("ffmpeg bulunamadı. Kurulum: sudo apt install ffmpeg")
            return
        except Exception as e:
            self.error.emit(f"ffmpeg başlatılamadı: {e}")
            return

        for line in self._proc.stdout:
            key, _, val = line.strip().partition('=')
            if key == "out_time_us" and val.strip().lstrip('-').isdigit():
                done_ms = max(0, int(val) // 1000)
                self.progress.emit(min(99, int(done_ms * 100 / dur_ms)))
        self._proc.wait()
        err_text = (self._proc.stderr.read() or "").strip()

        if self._cancelled:
            self._remove_partial()
            self.error.emit("İptal edildi.")
            return

        if self._proc.returncode != 0:
            self._remove_partial()
            self.error.emit(err_text[-1500:] or
                            f"ffmpeg {self._proc.returncode} kodu ile çıktı.")
            return

        # Çıktıyı doğrula: video akışı gerçekten yazıldı mı?
        info = probe_video(self.out_file)
        if not info.get("has_video"):
            self._remove_partial()
            self.error.emit(
                "Çıktıda video akışı yok, dosya silindi.\n"
                "Kesim modunu 'Hassas (yeniden kodla)' yapıp tekrar deneyin.\n\n"
                + err_text[-800:]
            )
            return

        self.progress.emit(100)
        self.done.emit(self.out_file, info.get("duration_ms", 0))

    def cancel(self):
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def _remove_partial(self):
        try:
            if os.path.exists(self.out_file):
                os.remove(self.out_file)
        except OSError:
            pass


class SeekSlider(QSlider):
    """Groove'a tıklayınca o konuma atlar (sayfa-sayfa kaydırma yerine).

    Aralık kısıtlaması açıkken mavi ilerleme çizgisi sadece seçili aralıkta
    görünür: aralık dışı gri kalır, aralığın oynanmamış kısmı açık gri olur.
    """
    clickedValue = pyqtSignal(int)

    HANDLE = 14          # stylesheet'teki handle genişliği
    GROOVE = 4           # stylesheet'teki groove yüksekliği

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._r_start = 0
        self._r_end = 0
        self._r_active = False

    def set_range_view(self, start_ms: int, end_ms: int, active: bool):
        self._r_start = int(start_ms)
        self._r_end = int(end_ms)
        self._r_active = bool(active) and end_ms > start_ms
        self.update()

    def _val_to_x(self, val: int) -> float:
        span = max(1, self.maximum() - self.minimum())
        frac = min(1.0, max(0.0, (val - self.minimum()) / span))
        return self.HANDLE / 2.0 + frac * max(1, self.width() - self.HANDLE)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if not self._r_active or self.maximum() <= self.minimum():
            return
        xs = self._val_to_x(self._r_start)
        xe = self._val_to_x(self._r_end)
        xv = min(max(self._val_to_x(self.value()), xs), xe)
        y = (self.height() - self.GROOVE) / 2.0

        p = QPainter(self)
        p.setPen(Qt.NoPen)
        # aralık dışı: normal groove rengi (varsayılan mavi dolguyu gizler)
        p.setBrush(QColor("#444"))
        p.drawRect(QRectF(0, y, xs, self.GROOVE))
        p.drawRect(QRectF(xe, y, self.width() - xe, self.GROOVE))
        # aralığın oynanmamış kısmı: hafif daha açık gri
        p.setBrush(QColor("#5f5f5f"))
        p.drawRect(QRectF(xs, y, xe - xs, self.GROOVE))
        # aralık içindeki ilerleme
        p.setBrush(QColor("#0d7acc"))
        if xv > xs:
            p.drawRect(QRectF(xs, y, xv - xs, self.GROOVE))
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.maximum() > self.minimum():
            span = self.maximum() - self.minimum()
            frac = min(1.0, max(0.0, ev.x() / max(1, self.width())))
            val = self.minimum() + int(round(frac * span))
            self.setValue(val)
            self.clickedValue.emit(val)
        super().mousePressEvent(ev)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Kırpıcı")
        self.setMinimumSize(1200, 720)
        self._current_video = None       # kaynak video (kırpma bunun üzerinde)
        self._previewing = None          # önizlenen klip yolu (varsa)
        self._duration = 0               # oynatıcıdaki medyanın süresi
        self._source_duration = 0        # kaynak videonun süresi (ffprobe)
        self._fps = 0.0
        self._slider_pressed = False
        self._pause_pending = False
        self._worker = None
        self._out_dir_override = ""       # boş → videonun yanında video adıyla klasör
        self._build_player()
        self._build_ui()
        self._build_menu()
        self._connect_player()
        self._check_ffmpeg()

    # ─────────────────────────────── player setup

    def _build_player(self):
        self.player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background:#000;")
        self.player.setVideoOutput(self.video_widget)

    def _connect_player(self):
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.stateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.error.connect(self._on_player_error)

    def _check_ffmpeg(self):
        missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
        if missing:
            self.clip_btn.setEnabled(False)
            QMessageBox.warning(
                self, "ffmpeg eksik",
                f"Bulunamadı: {', '.join(missing)}\n\n"
                "Kırpma için gerekli. Kurulum:\n  sudo apt install ffmpeg"
            )

    # ─────────────────────────────── UI build

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
        splitter.setSizes([200, 760, 260])
        vbox.addWidget(splitter, 1)

        vbox.addWidget(self._build_controls())

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Dosya > Video Aç ile başlayın   |   "
                                "Boşluk: oynat/durdur, ←/→: 1 sn, ,/.: 1 kare, "
                                "S/E: nokta ayarla, Shift+S / Shift+E: noktaya git")

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background:#222; border-bottom:1px solid #3a3a3a;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)

        def btn(text, slot, tip="", color=""):
            b = QPushButton(text)
            if tip:
                b.setToolTip(tip)
            if color:
                b.setStyleSheet(
                    f"background:{color}; color:white; font-weight:bold; padding:5px 14px;")
            b.clicked.connect(slot)
            return b

        row.addWidget(btn("Video Aç", self._open_videos, "Ctrl+O"))
        row.addWidget(btn("Klasörden Ekle", self._open_folder,
                          "Bir klasördeki tüm videoları listeye ekle"))
        row.addStretch()

        self.back_btn = btn("⟵ Kaynak Videoya Dön", self._back_to_source,
                            "Klip önizlemesinden kaynak videoya geri dön")
        self.back_btn.setVisible(False)
        row.addWidget(self.back_btn)
        return bar

    def _build_video_list(self) -> QWidget:
        w = QWidget()
        w.setMaximumWidth(230)
        w.setMinimumWidth(160)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(4, 6, 4, 4)

        lbl = QLabel("Videolar")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:2px 4px;")
        vbox.addWidget(lbl)

        self.video_list = QListWidget()
        self.video_list.currentRowChanged.connect(self._on_video_selected)
        vbox.addWidget(self.video_list)

        return w

    def _build_center(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vbox.addWidget(self.video_widget, 1)
        return w

    def _build_controls(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(60)
        bar.setStyleSheet("background:#1e1e1e; border-top:1px solid #3a3a3a;")
        vbox = QVBoxLayout(bar)
        vbox.setContentsMargins(10, 4, 10, 4)
        vbox.setSpacing(4)

        # Slider
        self.seek_slider = SeekSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self._slider_press)
        self.seek_slider.sliderReleased.connect(self._slider_release)
        self.seek_slider.sliderMoved.connect(self._slider_moved)
        self.seek_slider.clickedValue.connect(self.player.setPosition)
        vbox.addWidget(self.seek_slider)

        # Buttons row
        row = QHBoxLayout()
        row.setSpacing(6)

        self.play_btn = QPushButton("▶  Oynat")
        self.play_btn.setFixedWidth(100)
        self.play_btn.clicked.connect(self._toggle_play)
        self.play_btn.setEnabled(False)
        row.addWidget(self.play_btn)

        for text, delta, tip in (("⏮ -1sn", -1000, "1 saniye geri (←)"),
                                 ("◀|", "frame-", "1 kare geri (,)"),
                                 ("|▶", "frame+", "1 kare ileri (.)"),
                                 ("+1sn ⏭", 1000, "1 saniye ileri (→)")):
            b = QPushButton(text)
            b.setFixedWidth(64)
            b.setToolTip(tip)
            if delta == "frame-":
                b.clicked.connect(lambda: self._nudge(-self._frame_ms()))
            elif delta == "frame+":
                b.clicked.connect(lambda: self._nudge(self._frame_ms()))
            else:
                b.clicked.connect(lambda _, d=delta: self._nudge(d))
            b.setEnabled(False)
            row.addWidget(b)
            if not hasattr(self, "_nav_btns"):
                self._nav_btns = []
            self._nav_btns.append(b)

        self.time_lbl = QLabel("00:00.000 / 00:00.000")
        self.time_lbl.setStyleSheet("color:#aaa; font-family:monospace; font-size:12px;")
        row.addWidget(self.time_lbl)

        row.addStretch()

        self.preview_lbl = QLabel("")
        self.preview_lbl.setStyleSheet("color:#7ec8ff; font-size:11px;")
        row.addWidget(self.preview_lbl)
        vbox.addLayout(row)

        return bar

    def _build_right_panel(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(240)
        w.setMaximumWidth(320)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(10)

        # ── Kırpma grubu
        grp = QGroupBox("Kırpma Noktaları")
        g_vbox = QVBoxLayout(grp)
        g_vbox.setSpacing(6)

        # Başlangıç
        g_vbox.addWidget(QLabel("Başlangıç (dd:ss.ms)"))
        h1 = QHBoxLayout()
        self.start_edit = QLineEdit("00:00.000")
        self.start_edit.setPlaceholderText("00:00.000")
        self.start_edit.textChanged.connect(self._update_range_lbl)
        self.start_edit.returnPressed.connect(lambda: self._goto_field(self.start_edit))
        h1.addWidget(self.start_edit)
        self.set_start_btn = QPushButton("Şimdiki An")
        self.set_start_btn.setToolTip("Oynatıcının şimdiki konumunu başlangıç yap (S)")
        self.set_start_btn.clicked.connect(self._set_start_now)
        self.set_start_btn.setEnabled(False)
        h1.addWidget(self.set_start_btn)
        g_vbox.addLayout(h1)

        # Bitiş
        g_vbox.addWidget(QLabel("Bitiş (dd:ss.ms)"))
        h2 = QHBoxLayout()
        self.end_edit = QLineEdit("00:00.000")
        self.end_edit.setPlaceholderText("00:00.000")
        self.end_edit.textChanged.connect(self._update_range_lbl)
        self.end_edit.returnPressed.connect(lambda: self._goto_field(self.end_edit))
        h2.addWidget(self.end_edit)
        self.set_end_btn = QPushButton("Şimdiki An")
        self.set_end_btn.setToolTip("Oynatıcının şimdiki konumunu bitiş yap (E)")
        self.set_end_btn.clicked.connect(self._set_end_now)
        self.set_end_btn.setEnabled(False)
        h2.addWidget(self.set_end_btn)
        g_vbox.addLayout(h2)

        # Ayarlanan noktalara gitme
        h_go = QHBoxLayout()
        self.go_start_btn = QPushButton("⤒ Başlangıca Git")
        self.go_start_btn.setToolTip("Oynatıcıyı başlangıç noktasına al (Shift+S)")
        self.go_start_btn.clicked.connect(lambda: self._goto_field(self.start_edit))
        self.go_start_btn.setEnabled(False)
        h_go.addWidget(self.go_start_btn)
        self.go_end_btn = QPushButton("Bitişe Git ⤒")
        self.go_end_btn.setToolTip("Oynatıcıyı bitiş noktasına al (Shift+E)")
        self.go_end_btn.clicked.connect(lambda: self._goto_field(self.end_edit))
        self.go_end_btn.setEnabled(False)
        h_go.addWidget(self.go_end_btn)
        g_vbox.addLayout(h_go)

        self.range_lbl = QLabel("Seçili aralık: —")
        self.range_lbl.setStyleSheet("color:#8ab4d8; font-family:monospace; font-size:11px;")
        g_vbox.addWidget(self.range_lbl)

        # Oynatmayı seçili aralığa kısıtla (istediğin an aç/kapat)
        self.limit_range_chk = QCheckBox("Sadece seçili aralığı oynat")
        self.limit_range_chk.setChecked(True)
        self.limit_range_chk.setToolTip(
            "Açıkken oynatma başlangıç noktasından başlar ve bitişte durur.\n"
            "Noktaları sonradan değiştirirsen yeni aralık hemen geçerli olur.\n"
            "Kapatınca video normal, baştan sona oynar.")
        self.limit_range_chk.toggled.connect(self._on_limit_toggled)
        g_vbox.addWidget(self.limit_range_chk)

        # Kesim modu
        g_vbox.addWidget(QLabel("Kesim modu"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Hassas (yeniden kodla)", True)
        self.mode_combo.addItem("Hızlı (kopyala)", False)
        self.mode_combo.currentIndexChanged.connect(self._update_mode_hint)
        g_vbox.addWidget(self.mode_combo)

        self.mode_hint = QLabel("")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setStyleSheet("color:#999; font-size:10px;")
        g_vbox.addWidget(self.mode_hint)
        self._update_mode_hint()

        # Kırp butonu
        self.clip_btn = QPushButton("✂  Kırp ve Kaydet")
        self.clip_btn.setMinimumHeight(38)      # yazı alttan kırpılmasın
        self.clip_btn.setStyleSheet(
            "background:#0d47a1; color:white; font-weight:bold; font-size:13px;"
            "border:1px solid #1565c0; border-radius:4px; padding:8px 12px;")
        self.clip_btn.setToolTip("Ctrl+Return")
        self.clip_btn.setShortcut("Ctrl+Return")
        self.clip_btn.clicked.connect(self._do_clip)
        self.clip_btn.setEnabled(False)
        g_vbox.addWidget(self.clip_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        g_vbox.addWidget(self.progress)

        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.clicked.connect(self._cancel_clip)
        self.cancel_btn.setVisible(False)
        g_vbox.addWidget(self.cancel_btn)

        vbox.addWidget(grp)

        # ── Hedef klasör
        grp_dir = QGroupBox("Hedef Klasör")
        gd_vbox = QVBoxLayout(grp_dir)
        gd_vbox.setSpacing(6)

        self.out_dir_edit = QLineEdit()
        self.out_dir_edit.setReadOnly(True)
        self.out_dir_edit.setStyleSheet("font-size:11px;")
        self.out_dir_edit.setPlaceholderText("(video seçilince belirlenir)")
        gd_vbox.addWidget(self.out_dir_edit)

        hd = QHBoxLayout()
        self.pick_dir_btn = QPushButton("Klasör Seç…")
        self.pick_dir_btn.setToolTip("Kliplerin kaydedileceği klasörü seç")
        self.pick_dir_btn.clicked.connect(self._pick_out_dir)
        hd.addWidget(self.pick_dir_btn)
        self.reset_dir_btn = QPushButton("Varsayılan")
        self.reset_dir_btn.setToolTip("Videonun yanında, video adıyla klasör kullan")
        self.reset_dir_btn.clicked.connect(self._reset_out_dir)
        hd.addWidget(self.reset_dir_btn)
        gd_vbox.addLayout(hd)

        vbox.addWidget(grp_dir)

        # ── Kaydedilen klipler
        grp2 = QGroupBox("Kaydedilen Klipler")
        g2_vbox = QVBoxLayout(grp2)

        self.clip_list = QListWidget()
        self.clip_list.setToolTip("Çift tıkla → klibi oynat")
        self.clip_list.itemDoubleClicked.connect(self._play_clip)
        g2_vbox.addWidget(self.clip_list)

        h3 = QHBoxLayout()
        self.del_clip_btn = QPushButton("Sil")
        self.del_clip_btn.setToolTip("Seçili klibi diskten sil")
        self.del_clip_btn.clicked.connect(self._delete_clip)
        h3.addWidget(self.del_clip_btn)
        self.open_dir_btn = QPushButton("Klasörü Aç")
        self.open_dir_btn.clicked.connect(self._open_out_dir)
        h3.addWidget(self.open_dir_btn)
        g2_vbox.addLayout(h3)

        self.clip_count_lbl = QLabel("0 klip")
        self.clip_count_lbl.setStyleSheet("color:#777; font-size:11px;")
        g2_vbox.addWidget(self.clip_count_lbl)

        vbox.addWidget(grp2, 1)

        return w

    def _build_menu(self):
        mb = self.menuBar()
        file_m = mb.addMenu("Dosya")

        def act(label, slot, shortcut=""):
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            file_m.addAction(a)

        act("Video Aç", self._open_videos, "Ctrl+O")
        act("Klasörden Ekle", self._open_folder, "Ctrl+Shift+O")
        file_m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    def _update_mode_hint(self):
        if self.mode_combo.currentData():
            self.mode_hint.setText(
                "Tam olarak istenen ms aralığı kesilir (H.264 yeniden kodlama, biraz yavaş).")
        else:
            self.mode_hint.setText(
                "Yeniden kodlama yok, çok hızlı; ama kesim en yakın keyframe'e "
                "kayar — klip istenenden uzun olabilir.")

    # ─────────────────────────────── video open / select

    def _add_paths(self, paths):
        existing = {self.video_list.item(i).data(Qt.UserRole)
                    for i in range(self.video_list.count())}
        added = 0
        for p in paths:
            if p in existing:
                continue
            item = QListWidgetItem(os.path.basename(p))
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            self.video_list.addItem(item)
            existing.add(p)
            added += 1
        if self.video_list.count() > 0 and self._current_video is None:
            self.video_list.setCurrentRow(0)
        return added

    def _open_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Video Seç", "",
            "Video Dosyaları (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v);;Tüm Dosyalar (*)"
        )
        if paths:
            self._add_paths(paths)

    def _open_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Klasör Seç", "")
        if not d:
            return
        files = sorted(os.path.join(d, f) for f in os.listdir(d)
                       if f.lower().endswith(VIDEO_EXTS))
        n = self._add_paths(files)
        self.status.showMessage(f"{n} video eklendi: {d}")

    def _on_video_selected(self, row: int):
        if row < 0:
            return
        path = self.video_list.item(row).data(Qt.UserRole)
        if not os.path.exists(path):
            QMessageBox.warning(self, "Dosya yok", f"Bulunamadı:\n{path}")
            return
        self._load_source(path)

    def _load_source(self, path: str, reset_range=True):
        self._current_video = path
        self._previewing = None
        self.back_btn.setVisible(False)
        self.preview_lbl.setText("")

        info = probe_video(path)
        if info and not info.get("has_video"):
            QMessageBox.warning(self, "Video akışı yok",
                                f"Bu dosyada video akışı yok:\n{os.path.basename(path)}")
        self._source_duration = info.get("duration_ms", 0)
        self._fps = info.get("fps", 0.0) or 0.0

        # İlk kareyi göstermek için kısa süre oynatıp duraklatıyoruz; bazı
        # backend'ler LoadedMedia'yı atladığı için ayrıca zaman aşımı ağı var.
        self._pause_pending = True
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.player.play()
        QTimer.singleShot(1200, self._pause_fallback)

        self.play_btn.setEnabled(True)
        for b in self._nav_btns:
            b.setEnabled(True)
        self.set_start_btn.setEnabled(True)
        self.set_end_btn.setEnabled(True)
        self.go_start_btn.setEnabled(True)
        self.go_end_btn.setEnabled(True)
        self.clip_btn.setEnabled(bool(shutil.which("ffmpeg")))

        if self._source_duration:
            self._duration = self._source_duration
            self.seek_slider.setRange(0, self._source_duration)
        if reset_range:
            self.start_edit.setText("00:00.000")
            self.end_edit.setText(ms_to_str(self._source_duration))

        fps_txt = f", {self._fps:.3g} fps" if self._fps else ""
        self.setWindowTitle(f"Video Kırpıcı — {os.path.basename(path)}")
        self.status.showMessage(
            f"Yüklendi: {os.path.basename(path)} "
            f"({ms_to_str(self._source_duration)}{fps_txt})")
        self._refresh_clip_list()
        self._update_range_lbl()
        self._update_out_dir_ui()
        self.video_widget.setFocus()

    # ─────────────────────────────── player controls

    def _frame_ms(self) -> int:
        return int(round(1000.0 / self._fps)) if self._fps else 40

    def _nudge(self, delta_ms: int):
        if self._duration <= 0:
            return
        pos = min(self._duration, max(0, self.player.position() + delta_ms))
        self.player.pause()
        self.player.setPosition(pos)

    def _range_limits(self):
        """Kısıtlama aktif ve aralık geçerliyse (başlangıç, bitiş); değilse None."""
        if self._previewing or not self.limit_range_chk.isChecked():
            return None
        s = str_to_ms(self.start_edit.text())
        e = str_to_ms(self.end_edit.text())
        if s < 0 or e < 0 or e <= s:
            return None
        return s, e

    def _sync_range_view(self):
        """Çubuktaki mavi çizginin sadece aralıkta görünmesini güncelle."""
        lim = self._range_limits()
        if lim:
            self.seek_slider.set_range_view(lim[0], lim[1], True)
        else:
            self.seek_slider.set_range_view(0, 0, False)

    def _on_limit_toggled(self, on: bool):
        self._sync_range_view()
        if on:
            lim = self._range_limits()
            if lim:
                self.status.showMessage(
                    f"Oynatma aralığa kısıtlandı: {ms_to_str(lim[0])} → {ms_to_str(lim[1])}")
            else:
                self.status.showMessage("Aralık kısıtlaması açık (geçerli aralık girilince etkin).")
        else:
            self.status.showMessage("Aralık kısıtlaması kapalı — video baştan sona oynar.")

    def _toggle_play(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            return
        lim = self._range_limits()
        if lim:
            s, e = lim
            pos = self.player.position()
            if pos < s or pos >= e - 20:      # aralık dışındaysa başlangıçtan başlat
                self.player.setPosition(s)
        self.player.play()

    def _slider_press(self):
        self._slider_pressed = True

    def _slider_release(self):
        self._slider_pressed = False
        self.player.setPosition(self.seek_slider.value())

    def _slider_moved(self, val: int):
        self.time_lbl.setText(f"{ms_to_str(val)} / {ms_to_str(self._duration)}")

    def _on_position(self, pos: int):
        if not self._slider_pressed:
            self.seek_slider.setValue(pos)
        self.time_lbl.setText(f"{ms_to_str(pos)} / {ms_to_str(self._duration)}")
        # Aralık kısıtlaması: bitişe gelince duraklat
        lim = self._range_limits()
        if lim and pos >= lim[1] and self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.player.setPosition(lim[1])
            self.status.showMessage(f"Aralık sonu: {ms_to_str(lim[1])}")

    def _on_duration(self, dur: int):
        # Oynatıcı süresi; kaynak için ffprobe değeri daha güvenilir.
        if dur <= 0:
            return
        if self._previewing or not self._source_duration:
            self._duration = dur
            self.seek_slider.setRange(0, dur)
            if not self._previewing and not self._source_duration:
                self._source_duration = dur
                self.end_edit.setText(ms_to_str(dur))
        self.time_lbl.setText(
            f"{ms_to_str(self.player.position())} / {ms_to_str(self._duration)}")

    def _on_media_status(self, status):
        if (status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia)
                and self._pause_pending):
            self._pause_pending = False
            QTimer.singleShot(180, self._pause_at_start)
        elif status == QMediaPlayer.InvalidMedia:
            self.status.showMessage(
                "HATA: Medya açılamadı (kodek eksik olabilir): "
                f"{self.player.errorString()}")

    def _pause_fallback(self):
        if self._pause_pending:
            self._pause_pending = False
            self._pause_at_start()

    def _pause_at_start(self):
        if not self._previewing:
            self.player.pause()
            self.player.setPosition(0)
            # Yavaş backend'lerde ilk seek yutulabiliyor; bir kez daha zorla
            QTimer.singleShot(250, self._ensure_at_start)

    def _ensure_at_start(self):
        if not self._previewing and self.player.position() > 200:
            self.player.pause()
            self.player.setPosition(0)

    def _on_state(self, state):
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("⏸  Duraklat")
        else:
            self.play_btn.setText("▶  Oynat")

    def _on_player_error(self):
        err = self.player.errorString()
        if err:
            self.status.showMessage(f"HATA: Oynatıcı — {err}")

    def keyPressEvent(self, ev):
        step = 5000 if ev.modifiers() & Qt.ShiftModifier else 1000
        k = ev.key()
        if k == Qt.Key_Space:
            self._toggle_play()
        elif k == Qt.Key_Left:
            self._nudge(-step)
        elif k == Qt.Key_Right:
            self._nudge(step)
        elif k == Qt.Key_Comma:
            self._nudge(-self._frame_ms())
        elif k == Qt.Key_Period:
            self._nudge(self._frame_ms())
        elif k == Qt.Key_S:
            # S: noktayı ayarla, Shift+S: ayarlanan noktaya git
            if ev.modifiers() & Qt.ShiftModifier:
                self._goto_field(self.start_edit)
            else:
                self._set_start_now()
        elif k == Qt.Key_E:
            if ev.modifiers() & Qt.ShiftModifier:
                self._goto_field(self.end_edit)
            else:
                self._set_end_now()
        elif k == Qt.Key_Home:
            self.player.setPosition(0)
        else:
            super().keyPressEvent(ev)
            return
        ev.accept()

    # ─────────────────────────────── set start / end

    def _in_preview(self) -> bool:
        """Klip önizlemesindeyken oynatıcı konumu kaynak videoya ait değildir."""
        if self._previewing:
            self.status.showMessage(
                "Klip önizlemesindesiniz — zaman almak için 'Kaynak Videoya Dön'.")
            return True
        return False

    def _goto_field(self, edit: QLineEdit):
        """Alandaki zamana git: oynatıcıyı duraklatıp o kareyi göster."""
        if not self._current_video or self._in_preview():
            return
        ms = str_to_ms(edit.text())
        if ms < 0:
            self.status.showMessage("HATA: geçersiz zaman — format dd:ss.ms (örn 00:13.500)")
            return
        edit.setText(ms_to_str(ms))          # "13.5" → "00:13.500"
        if self._duration:
            ms = min(ms, self._duration)
        self.player.pause()
        self.player.setPosition(ms)
        self.status.showMessage(f"Gidildi: {ms_to_str(ms)}")

    def _set_start_now(self):
        if not self._current_video or self._in_preview():
            return
        self.start_edit.setText(ms_to_str(self.player.position()))

    def _set_end_now(self):
        if not self._current_video or self._in_preview():
            return
        self.end_edit.setText(ms_to_str(self.player.position()))

    def _update_range_lbl(self):
        s = str_to_ms(self.start_edit.text())
        e = str_to_ms(self.end_edit.text())
        if s < 0 or e < 0:
            self.range_lbl.setText("Seçili aralık: geçersiz zaman")
        elif e <= s:
            self.range_lbl.setText("Seçili aralık: bitiş > başlangıç olmalı")
        else:
            self.range_lbl.setText(f"Seçili aralık: {ms_to_str(e - s)}")
        self._sync_range_view()

    # ─────────────────────────────── clip

    def _out_dir(self) -> str:
        """Seçili hedef klasör varsa o, yoksa videonun yanında video adıyla klasör."""
        if self._out_dir_override:
            return self._out_dir_override
        video_dir = os.path.dirname(self._current_video)
        video_stem = os.path.splitext(os.path.basename(self._current_video))[0]
        return os.path.join(video_dir, video_stem)

    def _clip_prefix(self) -> str:
        """Ortak hedef klasörde farklı videoların klipleri karışmasın diye ön ek."""
        if not self._out_dir_override or not self._current_video:
            return ""
        stem = os.path.splitext(os.path.basename(self._current_video))[0]
        return f"{stem}_"

    def _clip_re(self):
        return re.compile(re.escape(self._clip_prefix()) + r"clip_(\d+)")

    def _update_out_dir_ui(self):
        self.out_dir_edit.setText(self._out_dir() if self._current_video else "")
        self.out_dir_edit.setToolTip(self.out_dir_edit.text())
        self.out_dir_edit.setCursorPosition(0)

    def _pick_out_dir(self):
        start = self._out_dir() if self._current_video else ""
        d = QFileDialog.getExistingDirectory(self, "Kliplerin kaydedileceği klasör", start)
        if not d:
            return
        self._out_dir_override = d
        self._update_out_dir_ui()
        self._refresh_clip_list()
        self.status.showMessage(f"Hedef klasör: {d}")

    def _reset_out_dir(self):
        self._out_dir_override = ""
        self._update_out_dir_ui()
        self._refresh_clip_list()
        self.status.showMessage("Hedef klasör varsayılana döndü (video adıyla klasör).")

    def _next_clip_index(self, out_dir: str) -> int:
        """Var olan en büyük numaranın bir fazlası — dosya ezmez."""
        biggest = 0
        pat = self._clip_re()
        if os.path.isdir(out_dir):
            for f in os.listdir(out_dir):
                m = pat.match(f)
                if m:
                    biggest = max(biggest, int(m.group(1)))
        return biggest + 1

    def _do_clip(self):
        if not self._current_video or self._worker:
            return
        if self._previewing:
            QMessageBox.information(
                self, "Önizleme modu",
                "Klip önizlemesindesiniz. Kırpmak için 'Kaynak Videoya Dön'.")
            return

        start_ms = str_to_ms(self.start_edit.text())
        end_ms = str_to_ms(self.end_edit.text())

        if start_ms < 0:
            QMessageBox.warning(self, "Hata", "Başlangıç zamanı geçersiz.\nFormat: dd:ss.ms (örn: 00:13.500)")
            return
        if end_ms < 0:
            QMessageBox.warning(self, "Hata", "Bitiş zamanı geçersiz.\nFormat: dd:ss.ms (örn: 00:22.000)")
            return
        if end_ms <= start_ms:
            QMessageBox.warning(self, "Hata", "Bitiş zamanı başlangıçtan büyük olmalı.")
            return
        if end_ms - start_ms < 50:
            QMessageBox.warning(self, "Hata", "Aralık çok kısa (en az 50 ms).")
            return
        if self._source_duration:
            if start_ms >= self._source_duration:
                QMessageBox.warning(
                    self, "Hata",
                    f"Başlangıç video süresini aşıyor ({ms_to_str(self._source_duration)}).")
                return
            if end_ms > self._source_duration:
                end_ms = self._source_duration
                self.end_edit.setText(ms_to_str(end_ms))
                self.status.showMessage("Bitiş, video süresine kısaltıldı.")

        out_dir = self._out_dir()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Klasör oluşturulamadı:\n{e}")
            return

        precise = bool(self.mode_combo.currentData())
        ext = ".mp4" if precise else (os.path.splitext(self._current_video)[1] or ".mp4")
        out_file = os.path.join(
            out_dir,
            f"{self._clip_prefix()}clip_{self._next_clip_index(out_dir):03d}{ext}")

        self._worker = ClipWorker(self._current_video, out_file, start_ms, end_ms, precise)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.done.connect(self._on_clip_done)
        self._worker.error.connect(self._on_clip_error)
        self._worker.finished.connect(self._on_worker_finished)

        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.clip_btn.setEnabled(False)
        self.status.showMessage(
            f"Kırpılıyor: {ms_to_str(start_ms)} → {ms_to_str(end_ms)} "
            f"({'hassas' if precise else 'hızlı'}) → {os.path.basename(out_file)}")
        self._worker.start()

    def _cancel_clip(self):
        if self._worker:
            self._worker.cancel()

    def _on_clip_done(self, out_file: str, actual_ms: int):
        istenen = str_to_ms(self.end_edit.text()) - str_to_ms(self.start_edit.text())
        note = ""
        if actual_ms and istenen > 0 and abs(actual_ms - istenen) > 150:
            note = (f"  (süre {ms_to_str(actual_ms)}, istenen {ms_to_str(istenen)} — "
                    "keyframe kayması; 'Hassas' modu tam kesim yapar)")
        self.status.showMessage(f"✔ Kaydedildi: {out_file}{note}")
        self._refresh_clip_list()

    def _on_clip_error(self, msg: str):
        self.status.showMessage(f"HATA: kırpma başarısız — {msg.splitlines()[0][:120]}")
        QMessageBox.critical(self, "Kırpma Hatası", msg[-1500:])

    def _on_worker_finished(self):
        self._worker = None
        self.progress.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.clip_btn.setEnabled(bool(self._current_video) and bool(shutil.which("ffmpeg")))

    def _refresh_clip_list(self):
        self.clip_list.clear()
        if not self._current_video:
            self.clip_count_lbl.setText("0 klip")
            return
        out_dir = self._out_dir()
        if not os.path.isdir(out_dir):
            self.clip_count_lbl.setText("0 klip")
            return
        pat = self._clip_re()
        clips = [f for f in os.listdir(out_dir)
                 if pat.match(f) and f.lower().endswith(VIDEO_EXTS)]
        clips.sort(key=lambda f: int(pat.match(f).group(1)))
        for c in clips:
            full = os.path.join(out_dir, c)
            item = QListWidgetItem(c)
            item.setData(Qt.UserRole, full)
            item.setToolTip(full)
            self.clip_list.addItem(item)
        self.clip_count_lbl.setText(f"{len(clips)} klip  →  {out_dir}")

    def _play_clip(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not os.path.exists(path):
            self.status.showMessage(f"HATA: klip bulunamadı — {path}")
            self._refresh_clip_list()
            return
        self._previewing = path
        self._pause_pending = False
        self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
        self.player.play()
        self._sync_range_view()      # önizlemede kısıtlama yok → normal çubuk
        self.back_btn.setVisible(True)
        self.preview_lbl.setText(f"ÖNİZLEME: {os.path.basename(path)}")
        self.status.showMessage(
            f"Klip oynatılıyor: {os.path.basename(path)} — kırpma için kaynağa dönün.")

    def _back_to_source(self):
        if self._current_video:
            self._load_source(self._current_video, reset_range=False)

    def _delete_clip(self):
        item = self.clip_list.currentItem()
        if not item:
            self.status.showMessage("Silmek için listeden bir klip seçin.")
            return
        path = item.data(Qt.UserRole)
        if QMessageBox.question(
                self, "Klibi sil",
                f"Diskten silinsin mi?\n{path}",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        if self._previewing == path:
            self._back_to_source()
        try:
            os.remove(path)
            self.status.showMessage(f"Silindi: {os.path.basename(path)}")
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Silinemedi:\n{e}")
        self._refresh_clip_list()

    def _open_out_dir(self):
        if not self._current_video:
            return
        out_dir = self._out_dir()
        os.makedirs(out_dir, exist_ok=True)
        try:
            klasoru_ac(out_dir)
        except Exception as e:
            self.status.showMessage(f"HATA: klasör açılamadı — {e}")

    def closeEvent(self, ev):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setApplicationName("Video Kırpıcı")
    win = MainWindow()
    win.show()
    # python main.py video1.mp4 video2.mp4  → doğrudan listeye al
    files = [os.path.abspath(a) for a in sys.argv[1:]
             if a.lower().endswith(VIDEO_EXTS) and os.path.exists(a)]
    if files:
        win._add_paths(files)
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
