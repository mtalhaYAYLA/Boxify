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
from . import ffmpeg_yardim


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

        # ffmpeg yoksa Popen FileNotFoundError atar; bu iş parçacığının
        # içinde patladığı için hiçbir sinyal çıkmaz ve arayüz "işleniyor"
        # hâlinde asılı kalırdı. Hatayı burada yakalayıp bildiriyoruz.
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True
            )
        except FileNotFoundError:
            self.error.emit("ffmpeg bulunamadı. "
                            + ffmpeg_yardim.kurulum_ipucu())
            return
        except Exception as e:
            self.error.emit(f"ffmpeg başlatılamadı: {e}")
            return

        cikti = proc.communicate()[0] or ""
        if proc.returncode != 0:
            son = "\n".join(cikti.strip().splitlines()[-3:])
            self.error.emit("ffmpeg hatası oluştu."
                            + (f"\n\n{son}" if son else ""))
            return

        saved = len([f for f in os.listdir(self.out_dir)
                     if f.startswith("kare_")])
        self.finished.emit(self.out_dir, saved)


class CanliYakalaIscisi(QThread):
    """Canlı bir kaynaktan (kamera/RTSP/SDK) belirli aralıklarla kare yakalar.

    Kaynağın ne olduğunu bilmiyor: `boxify.cekirdek.KareKaynagi` portunu
    uyguluyorsa buradan yakalanabiliyor. Yeni bir kamera türü eklemek bu
    dosyayı değiştirmiyor.
    """

    log = pyqtSignal(str)
    ilerleme = pyqtSignal(int, int)
    bitti = pyqtSignal(int, str)          # yazılan kare sayısı, klasör
    hata = pyqtSignal(str)

    def __init__(self, adres: str, cikti: str, adet: int, aralik_sn: float,
                 bicim: str = "jpg"):
        super().__init__()
        self.adres = adres
        self.cikti = cikti
        self.adet = adet
        self.aralik_sn = aralik_sn
        self.bicim = bicim
        self._iptal = False

    def iptal(self):
        self._iptal = True

    def run(self):
        import time as _t
        import cv2
        import numpy as np
        from ..adaptorler import kaynak_ac

        try:
            kaynak = kaynak_ac(self.adres)
        except Exception as e:
            self.hata.emit(str(e))
            return

        yazilan = 0
        try:
            with kaynak as k:
                bilgi = k.bilgi
                self.log.emit(f"Kaynak açıldı: {bilgi.ad} "
                              f"({'canlı' if bilgi.canli else 'dosya'})")
                os.makedirs(self.cikti, exist_ok=True)
                damga = _t.strftime("%Y%m%d_%H%M%S")
                son_yazim = 0.0
                for kare in k.kareler():
                    if self._iptal:
                        self.log.emit("İptal edildi.")
                        break
                    simdi = _t.perf_counter()
                    # Aralık kuralı canlı kaynakta zamana, dosyada kare
                    # sayısına göre işler; canlıda "her N'inci kare" demek
                    # kamera fps'i değişince farklı sıklık verirdi.
                    if bilgi.canli:
                        if son_yazim and (simdi - son_yazim) < self.aralik_sn:
                            continue
                    elif kare.indeks % max(1, int(self.aralik_sn)) != 0:
                        continue
                    son_yazim = simdi

                    ad = f"{damga}_{yazilan:05d}.{self.bicim}"
                    yol = os.path.join(self.cikti, ad)
                    try:
                        ok, tampon = cv2.imencode("." + self.bicim, kare.goruntu)
                        if ok:
                            # imwrite yerine imencode+tofile: Türkçe/boşluklu
                            # çıktı yollarında imwrite sessizce başarısız oluyor
                            tampon.tofile(yol)
                            yazilan += 1
                    except Exception as e:
                        self.log.emit(f"Kare yazılamadı: {e}")
                    self.ilerleme.emit(yazilan, self.adet)
                    if yazilan >= self.adet:
                        break
        except Exception as e:
            self.hata.emit(f"{type(e).__name__}: {e}")
            return
        self.bitti.emit(yazilan, self.cikti)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Kare Alıcı — Video → Dataset")
        self.setMinimumSize(1200, 720)
        self._current_video = None
        self._duration = 0
        self._slider_pressed = False
        self._worker = None
        self._ffmpeg_eksik = []
        self._build_player()
        self._build_ui()
        self._build_menu()
        self._connect_player()
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """ffmpeg eksikse kare çıkarmayı kapat ve sebebini durum çubuğunda söyle.

        Video Kırpıcı'daki gibi burada bilerek modal kutu açılmıyor: bu metot
        kurucudan, yani pencere daha gösterilmemişken çağrılıyor ve o aşamada
        açılan diyalog kabuğun donduğu izlenimi veriyor.
        """
        self._ffmpeg_eksik = ffmpeg_yardim.eksik_olanlar(("ffmpeg",))
        if not self._ffmpeg_eksik:
            return
        uyari = ffmpeg_yardim.eksik_mesaji(self._ffmpeg_eksik, "kare çıkarma")
        self.extract_btn.setToolTip(uyari)
        self.status.showMessage(uyari)

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

        # ── Canlı kaynak grubu
        grp_canli = QGroupBox("Canlı Kaynaktan Yakala")
        cv_ = QVBoxLayout(grp_canli)
        cv_.setSpacing(6)

        from ..adaptorler import ADRES_YARDIMI
        self.kaynak_edit = QLineEdit()
        self.kaynak_edit.setPlaceholderText("kamera:0  ·  rtsp://…  ·  hik:192.168.1.64")
        self.kaynak_edit.setToolTip(
            "Kare kaynağı adresi.\n" + ADRES_YARDIMI + "\n\n"
            "Kaynak türü adresten anlaşılır; yeni bir kamera türü eklemek bu\n"
            "alanı değiştirmez.")
        cv_.addWidget(self.kaynak_edit)

        satir_c = QHBoxLayout()
        satir_c.addWidget(QLabel("Adet"))
        self.canli_adet = QSpinBox()
        self.canli_adet.setRange(1, 100000)
        self.canli_adet.setValue(50)
        satir_c.addWidget(self.canli_adet)
        satir_c.addWidget(QLabel("Aralık"))
        self.canli_aralik = QDoubleSpinBox()
        self.canli_aralik.setRange(0.05, 600.0)
        self.canli_aralik.setValue(1.0)
        self.canli_aralik.setSuffix(" sn")
        satir_c.addWidget(self.canli_aralik)
        cv_.addLayout(satir_c)

        self.canli_btn = QPushButton("● Canlı Yakala")
        self.canli_btn.setMinimumHeight(32)
        self.canli_btn.clicked.connect(self._canli_yakala)
        cv_.addWidget(self.canli_btn)

        self.canli_lbl = QLabel("Kamera, ağ akışı ya da SDK'dan doğrudan veri seti üret.")
        self.canli_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        self.canli_lbl.setWordWrap(True)
        cv_.addWidget(self.canli_lbl)
        v.addWidget(grp_canli)

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

    def _canli_yakala(self):
        """Canlı kaynaktan kare yakalamayı başlat ya da durdur."""
        isci = getattr(self, "_canli_isci", None)
        if isci is not None and isci.isRunning():
            isci.iptal()
            self.canli_lbl.setText("Durduruluyor…")
            return

        adres = self.kaynak_edit.text().strip()
        if not adres:
            QMessageBox.information(
                self, "Kaynak yok",
                "Bir kaynak adresi yaz: kamera:0, rtsp://… ya da hik:192.168.1.64")
            return

        cikti = QFileDialog.getExistingDirectory(
            self, "Karelerin kaydedileceği klasör", self._last_out_dir or "")
        if not cikti:
            return

        self._canli_isci = CanliYakalaIscisi(
            adres, cikti, int(self.canli_adet.value()),
            float(self.canli_aralik.value()), self.fmt_combo.currentText())
        self._canli_isci.log.connect(self.status.showMessage)
        self._canli_isci.ilerleme.connect(
            lambda a, t: self.canli_lbl.setText(f"{a} / {t} kare yakalandı"))
        self._canli_isci.hata.connect(self._canli_hata)
        self._canli_isci.bitti.connect(self._canli_bitti)
        self._canli_isci.finished.connect(
            lambda: self.canli_btn.setText("● Canlı Yakala"))
        self.canli_btn.setText("■ Durdur")
        self.canli_lbl.setText("Kaynak açılıyor…")
        self._canli_isci.start()

    def _canli_hata(self, mesaj: str):
        self.canli_lbl.setText("Açılamadı.")
        QMessageBox.critical(self, "Kaynak açılamadı", mesaj)

    def _canli_bitti(self, adet: int, klasor: str):
        self._last_out_dir = klasor
        self.canli_lbl.setText(f"{adet} kare yazıldı.")
        self.status.showMessage(f"{adet} kare → {klasor}")

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
        # ffmpeg yoksa çıkarma düğmesi kapalı kalsın; sebebi ipucunda yazıyor
        self._ffmpeg_eksik = ffmpeg_yardim.eksik_olanlar(("ffmpeg",))
        self.extract_btn.setEnabled(not self._ffmpeg_eksik)
        self.setWindowTitle(f"Kare Alıcı — {os.path.basename(path)}")
        if self._ffmpeg_eksik:
            self.status.showMessage(
                ffmpeg_yardim.eksik_mesaji(self._ffmpeg_eksik, "kare çıkarma"))
        else:
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
        # Modal uyarı ancak kullanıcı düğmeye bastığında — kurucuda değil
        if self._ffmpeg_eksik:
            QMessageBox.warning(
                self, "ffmpeg bulunamadı",
                ffmpeg_yardim.eksik_mesaji(self._ffmpeg_eksik, "kare çıkarma"))
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

    def hideEvent(self, ev):
        """Boxify kabuğunda başka bir araca geçilince oynatmayı durdur.

        Sayfa gizlenmiş olsa da QMediaPlayer video çözmeye devam eder; arkada
        boşuna dönen bir akış öndeki aracı gözle görülür şekilde ağırlaştırır.
        """
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        super().hideEvent(ev)

    def closeEvent(self, ev):
        self.player.stop()
        if self._worker is not None and self._worker.isRunning():
            # ffmpeg süreci kendi başına bitmeli; sadece iş parçacığını bekle
            self._worker.wait(3000)
        super().closeEvent(ev)


def main():
    app = QApplication(sys.argv)
    # Tek başına çalıştırıldığında tema ayarını kabuk yüklemez; buradan okunur
    from .. import tema as _tema
    from .. import proje as _proje
    _tema.tema_yukle()
    _tema.yamalari_kur()
    _proje.yukle()
    _proje.yamalari_kur()
    app.setStyleSheet(_tema.stil())
    app.setApplicationName("Kare Alıcı")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
