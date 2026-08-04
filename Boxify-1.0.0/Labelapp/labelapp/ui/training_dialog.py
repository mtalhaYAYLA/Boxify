import os
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QComboBox, QSpinBox, QPushButton, QTextEdit,
                              QProgressBar, QLabel, QFileDialog, QGroupBox)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
from core.trainer import TrainerThread

YOLO_MODELS = [
    "yolo11n", "yolo11s", "yolo11m", "yolo11l", "yolo11x",
    "yolov8n", "yolov8s", "yolov8m", "yolov8l", "yolov8x",
    "yolov9c", "yolov9e",
    "yolov10n", "yolov10s", "yolov10m", "yolov10l", "yolov10x",
]


class TrainingDialog(QDialog):
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self._thread = None
        self._out_dir = ""
        self.setWindowTitle("Model Eğitimi")
        self.setMinimumWidth(720)
        self.setMinimumHeight(620)
        self._setup()

    def _setup(self):
        root = QVBoxLayout(self)

        # --- Model & hyperparams ---
        cfg = QGroupBox("Eğitim Ayarları")
        form = QFormLayout(cfg)

        self.model_cb = QComboBox()
        self.model_cb.addItems(YOLO_MODELS)
        self.model_cb.setCurrentText("yolo11m")
        form.addRow("YOLO Modeli:", self.model_cb)

        self.epochs_sp = QSpinBox()
        self.epochs_sp.setRange(1, 2000)
        self.epochs_sp.setValue(100)
        form.addRow("Epoch Sayısı:", self.epochs_sp)

        self.batch_sp = QSpinBox()
        self.batch_sp.setRange(1, 512)
        self.batch_sp.setValue(16)
        form.addRow("Batch Size:", self.batch_sp)

        self.imgsz_cb = QComboBox()
        self.imgsz_cb.addItems(["320", "416", "512", "640", "768", "1024", "1280"])
        self.imgsz_cb.setCurrentText("640")
        form.addRow("Görüntü Boyutu:", self.imgsz_cb)

        root.addWidget(cfg)

        # --- Split ---
        split_grp = QGroupBox("Veri Bölümü")
        sh = QHBoxLayout(split_grp)

        self.train_sp = QSpinBox()
        self.train_sp.setRange(10, 95)
        self.train_sp.setValue(70)
        self.train_sp.setSuffix("%")
        self.train_sp.valueChanged.connect(self._sync_test)

        self.val_sp = QSpinBox()
        self.val_sp.setRange(5, 50)
        self.val_sp.setValue(20)
        self.val_sp.setSuffix("%")
        self.val_sp.valueChanged.connect(self._sync_test)

        self.test_lbl = QLabel("Test: 10%")
        self.test_lbl.setStyleSheet("color: #aaa;")

        sh.addWidget(QLabel("Train:"))
        sh.addWidget(self.train_sp)
        sh.addSpacing(16)
        sh.addWidget(QLabel("Val:"))
        sh.addWidget(self.val_sp)
        sh.addSpacing(16)
        sh.addWidget(self.test_lbl)
        sh.addStretch()

        root.addWidget(split_grp)

        # --- Output dir ---
        out_row = QHBoxLayout()
        self.out_label = QLabel("Çıktı klasörü seçilmedi")
        self.out_label.setStyleSheet("color: #888;")
        browse = QPushButton("Klasör Seç")
        browse.setFixedWidth(100)
        browse.clicked.connect(self._browse)
        out_row.addWidget(QLabel("Çıktı:"))
        out_row.addWidget(self.out_label, 1)
        out_row.addWidget(browse)
        root.addLayout(out_row)

        # --- Progress ---
        self.prog = QProgressBar()
        self.prog.setVisible(False)
        self.prog.setTextVisible(True)
        root.addWidget(self.prog)

        # --- Log ---
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Courier New", 9))
        self.log.setStyleSheet("background:#1a1a1a; color:#ccc; border:1px solid #444;")
        root.addWidget(self.log)

        # --- Buttons ---
        brow = QHBoxLayout()
        self.start_btn = QPushButton("Eğitimi Başlat")
        self.start_btn.setStyleSheet(
            "background:#1b5e20; color:white; font-weight:bold; padding:8px 20px;")
        self.start_btn.clicked.connect(self._start)

        self.stop_btn = QPushButton("Durdur")
        self.stop_btn.setStyleSheet("background:#b71c1c; color:white; padding:8px 20px;")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)

        brow.addWidget(self.start_btn)
        brow.addWidget(self.stop_btn)
        brow.addStretch()
        root.addLayout(brow)

    def _sync_test(self):
        t = max(0, 100 - self.train_sp.value() - self.val_sp.value())
        self.test_lbl.setText(f"Test: {t}%")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Çıktı Klasörü Seç")
        if d:
            self._out_dir = d
            self.out_label.setText(d)

    def _append(self, text: str):
        self.log.append(text)
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _start(self):
        if not self._out_dir:
            self._append("⚠  Lütfen önce çıktı klasörü seçin.")
            return
        labeled = [img for img in self.dataset.images if img.is_labeled]
        if not labeled:
            self._append("⚠  Hiç etiketlenmiş resim yok.")
            return
        if not self.dataset.label_classes:
            self._append("⚠  Hiç sınıf tanımlanmamış.")
            return

        labeled_count = len(labeled)
        if labeled_count < 2:
            self._append(f"⚠  Çok az resim ({labeled_count}). Val için train resimleri kullanılacak.")

        self._append("Veri seti dışa aktarılıyor...")
        tr = self.train_sp.value() / 100
        vr = self.val_sp.value() / 100
        ter = max(0, 100 - self.train_sp.value() - self.val_sp.value()) / 100
        try:
            yaml_path = self.dataset.export(self._out_dir, tr, vr, ter)
            self._append(f"dataset.yaml → {yaml_path}")
        except Exception as e:
            self._append(f"✗ Export hatası: {e}")
            return

        model = self.model_cb.currentText()
        epochs = self.epochs_sp.value()
        batch = self.batch_sp.value()
        imgsz = int(self.imgsz_cb.currentText())

        self._append(f"Başlatılıyor: {model} | {epochs} epoch | batch={batch} | imgsz={imgsz}")

        self.prog.setMaximum(epochs)
        self.prog.setValue(0)
        self.prog.setFormat("Epoch 0/" + str(epochs))
        self.prog.setVisible(True)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self._thread = TrainerThread(yaml_path, model, epochs, batch, imgsz, self._out_dir)
        self._thread.log.connect(self._append)
        self._thread.progress.connect(self._on_progress)
        self._thread.finished.connect(self._on_finished)
        self._thread.start()

    def _stop(self):
        if self._thread:
            self._thread.stop()
        self._append("Durduruluyor...")

    def _on_progress(self, cur: int, total: int):
        self.prog.setValue(cur)
        self.prog.setFormat(f"Epoch {cur}/{total}")

    def _on_finished(self, ok: bool, msg: str):
        self._append(("✓ " if ok else "✗ ") + msg)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if ok:
            self.prog.setValue(self.prog.maximum())
