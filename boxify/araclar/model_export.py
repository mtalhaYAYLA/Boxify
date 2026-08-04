"""Model Export & Hız Ölçümü — modeli dağıtım biçimlerine çevirir, hızını ölçer
ve dönüşümün doğruluğu bozup bozmadığını kontrol eder.

Üç işi var:
  1. Dışa aktarma : .pt → ONNX / TensorRT / OpenVINO / TorchScript (FP16, INT8)
  2. Hız ölçümü   : her modelin ön işlem / çıkarım / son işlem süresi, FPS ve
                    "tek makinede kaç kamera" tahmini
  3. Sapma kontrol: referans modelle aynı görsellerdeki tahminleri karşılaştırır
                    (FP16/INT8 doğruluğu bozdu mu?) — etiket gerektirmez

Bağımlılık: PyQt5, ultralytics, numpy. TensorRT/OpenVINO sadece o biçimler için.
"""
import os
import sys
import time
import statistics

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QListWidgetItem, QFileDialog, QStatusBar,
    QGroupBox, QMessageBox, QLineEdit, QAction, QComboBox, QProgressBar,
    QCheckBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTabWidget, QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from ..tema import STYLE  # ortak açık tema — bkz. boxify/tema.py
from .model_bilgi import cihaz_combo_doldur

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")
MODEL_EXTS = (".pt", ".onnx", ".engine", ".torchscript", ".xml", ".mlpackage")


def list_images(folder: str, limit: int = 0) -> list:
    out = []
    for root, _d, files in os.walk(folder):
        for f in sorted(files):
            if f.lower().endswith(IMG_EXTS):
                out.append(os.path.join(root, f))
                if limit and len(out) >= limit:
                    return out
    return out


def human_size(path: str) -> str:
    try:
        n = os.path.getsize(path)
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return "?"


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


# ─────────────────────────────────────────────── dışa aktarma

class ExportWorker(QThread):
    log = pyqtSignal(str)
    done = pyqtSignal(str)          # üretilen dosya yolu ("" = başarısız)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg

    def run(self):
        cfg = self.cfg
        try:
            from ultralytics import YOLO
        except Exception as e:
            self.log.emit(f"HATA: ultralytics yüklenemedi — {e}")
            self.done.emit("")
            return
        try:
            model = YOLO(cfg["model_path"])
        except Exception as e:
            self.log.emit(f"HATA: model yüklenemedi — {e}")
            self.done.emit("")
            return

        kw = dict(format=cfg["format"], imgsz=cfg["imgsz"], batch=cfg["batch"])
        if cfg["half"]:
            kw["half"] = True
        if cfg["int8"]:
            kw["int8"] = True
            if cfg["data"]:
                kw["data"] = cfg["data"]
        if cfg["dynamic"]:
            kw["dynamic"] = True
        if cfg["simplify"]:
            kw["simplify"] = True
        if cfg["device"] is not None:
            kw["device"] = cfg["device"]
        if cfg["workspace"] and cfg["format"] == "engine":
            kw["workspace"] = cfg["workspace"]

        self.log.emit("Dışa aktarma başlıyor: " + ", ".join(f"{k}={v}" for k, v in kw.items()))
        t0 = time.time()
        try:
            out = model.export(**kw)
        except Exception as e:
            self.log.emit(f"HATA: dışa aktarma başarısız — {e}")
            if cfg["format"] == "engine":
                self.log.emit("TensorRT kurulu mu? (pip install tensorrt) "
                              "ve GPU seçili mi?")
            if cfg["int8"] and not cfg["data"]:
                self.log.emit("INT8 için kalibrasyon verisi (data.yaml) gerekir.")
            self.done.emit("")
            return
        sure = time.time() - t0
        path = str(out) if out else ""
        if path and os.path.exists(path):
            self.log.emit(f"Tamam ({sure:.1f} sn): {path}  [{human_size(path)}]")
        else:
            self.log.emit(f"Bitti ({sure:.1f} sn) ama çıktı dosyası bulunamadı: {out}")
        self.done.emit(path)


# ─────────────────────────────────────────────── hız ölçümü

class BenchWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    result = pyqtSignal(dict)

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _predict(self, model, path):
        return model.predict(source=path, imgsz=self.cfg["imgsz"],
                             conf=self.cfg["conf"], iou=self.cfg["iou_nms"],
                             device=self.cfg["device"], max_det=self.cfg["max_det"],
                             verbose=False)[0]

    def run(self):
        cfg = self.cfg
        try:
            from ultralytics import YOLO
            import torch
        except Exception as e:
            self.log.emit(f"HATA: ultralytics/torch yüklenemedi — {e}")
            self.result.emit({})
            return

        if cfg["cpu_threads"]:
            torch.set_num_threads(cfg["cpu_threads"])
            self.log.emit(f"CPU iş parçacığı: {cfg['cpu_threads']}")

        images = cfg["images"]
        rows = []
        ref_preds = None                    # referans modelin tahminleri (sapma için)
        total_steps = len(cfg["models"]) * (cfg["warmup"] + cfg["iters"])
        step = 0

        for mi, mpath in enumerate(cfg["models"]):
            if self._cancel:
                break
            self.log.emit(f"── {os.path.basename(mpath)} ──")
            try:
                model = YOLO(mpath)
            except Exception as e:
                self.log.emit(f"HATA: yüklenemedi — {e}")
                continue

            # ısınma (ilk çağrılar her zaman yavaştır: bellek, kernel derleme)
            for i in range(cfg["warmup"]):
                if self._cancel:
                    break
                try:
                    self._predict(model, images[i % len(images)])
                except Exception as e:
                    self.log.emit(f"HATA: çıkarım başarısız — {e}")
                    break
                step += 1
                self.progress.emit(step, total_steps)

            pre, inf, post, wall = [], [], [], []
            preds = []
            hata = False
            for i in range(cfg["iters"]):
                if self._cancel:
                    break
                path = images[i % len(images)]
                t0 = time.perf_counter()
                try:
                    res = self._predict(model, path)
                except Exception as e:
                    self.log.emit(f"HATA: çıkarım başarısız — {e}")
                    hata = True
                    break
                wall.append((time.perf_counter() - t0) * 1000.0)
                sp = getattr(res, "speed", None) or {}
                pre.append(float(sp.get("preprocess", 0.0)))
                inf.append(float(sp.get("inference", 0.0)))
                post.append(float(sp.get("postprocess", 0.0)))
                if cfg["compare"] and i < cfg["compare_n"]:
                    preds.append(self._extract(res))
                step += 1
                self.progress.emit(step, total_steps)

            if hata or not wall:
                continue

            row = {
                "model": mpath,
                "boyut": human_size(mpath),
                "pre": statistics.mean(pre) if pre else 0.0,
                "inf": statistics.mean(inf) if inf else 0.0,
                "post": statistics.mean(post) if post else 0.0,
                "toplam": statistics.mean(wall),
                "medyan": statistics.median(wall),
                "p95": sorted(wall)[int(0.95 * (len(wall) - 1))],
                "fps": 1000.0 / statistics.mean(wall),
                "n": len(wall),
            }
            if cfg["compare"]:
                if mi == 0:
                    ref_preds = preds
                    row["sapma"] = None
                elif ref_preds:
                    row["sapma"] = self._compare(ref_preds, preds)
                else:
                    row["sapma"] = None
            rows.append(row)
            self.log.emit(f"{row['toplam']:.1f} ms/kare  →  {row['fps']:.1f} FPS "
                          f"(çıkarım {row['inf']:.1f} ms)")

        self.result.emit({"rows": rows, "iptal": self._cancel})

    @staticmethod
    def _extract(res) -> list:
        """Tahminleri (sınıf, güven, xyxy) listesine çevir."""
        out = []
        if res.boxes is None or not len(res.boxes):
            return out
        xyxy = res.boxes.xyxy.cpu().numpy()
        clss = res.boxes.cls.cpu().numpy().astype(int)
        cfs = res.boxes.conf.cpu().numpy()
        for k in range(len(cfs)):
            out.append((int(clss[k]), float(cfs[k]), tuple(xyxy[k].tolist())))
        return out

    @staticmethod
    def _compare(ref_list: list, cand_list: list) -> dict:
        """Referans ile adayın tahminlerini eşleştirip sapmayı ölç (etiket gerekmez)."""
        n_ref = n_cand = matched = 0
        ious, dconf = [], []
        for ref, cand in zip(ref_list, cand_list):
            n_ref += len(ref)
            n_cand += len(cand)
            used = set()
            for rc, rconf, rbox in ref:
                best_i, best_v = -1, 0.0
                for j, (cc, cconf, cbox) in enumerate(cand):
                    if j in used or cc != rc:
                        continue
                    v = iou(rbox, cbox)
                    if v > best_v:
                        best_i, best_v = j, v
                if best_v >= 0.5:
                    used.add(best_i)
                    matched += 1
                    ious.append(best_v)
                    dconf.append(abs(cand[best_i][1] - rconf))
        return {
            "ref_kutu": n_ref, "aday_kutu": n_cand, "eslesen": matched,
            "oran": matched / n_ref if n_ref else 0.0,
            "ort_iou": statistics.mean(ious) if ious else 0.0,
            "ort_conf_sapma": statistics.mean(dconf) if dconf else 0.0,
        }


# ─────────────────────────────────────────────── ana pencere

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Model Export & Hız Ölçümü")
        self.setMinimumSize(1200, 800)
        self._worker = None
        self._build_ui()
        self._build_menu()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self._build_left())
        sp.addWidget(self._build_center())
        sp.addWidget(self._build_right())
        sp.setSizes([360, 500, 380])
        v.addWidget(sp, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Model ekle → Dışa Aktar veya Hız Ölçümü")

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(300)
        w.setMaximumWidth(460)
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        lbl = QLabel("Modeller")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:2px 4px;")
        v.addWidget(lbl)

        self.model_list = QListWidget()
        self.model_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.model_list.setToolTip("Kutucuğu işaretli modeller ölçüme girer.\n"
                                   "Listedeki İLK işaretli model sapma karşılaştırmasında "
                                   "referanstır (genelde .pt).")
        v.addWidget(self.model_list, 1)

        h = QHBoxLayout()
        h.setSpacing(6)
        b_add = QPushButton("Model Ekle…")
        b_add.clicked.connect(self._add_models)
        h.addWidget(b_add)
        b_del = QPushButton("Çıkar")
        b_del.clicked.connect(self._remove_model)
        h.addWidget(b_del)
        v.addLayout(h)

        self.list_info = QLabel("0 model")
        self.list_info.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(self.list_info)
        return w

    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.tabs_out = QTabWidget()
        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs_out.addTab(self.report_box, "Sonuç")
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs_out.addTab(self.log_box, "Log")
        v.addWidget(self.tabs_out, 1)
        return w

    def _row(self, text, widget) -> QHBoxLayout:
        h = QHBoxLayout()
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:normal;")
        h.addWidget(lb)
        h.addStretch()
        h.addWidget(widget)
        return h

    def _path_row(self, edit: QLineEdit, slot) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        edit.setReadOnly(True)
        edit.setStyleSheet("font-size:11px; font-family:monospace;")
        h.addWidget(edit, 1)
        b = QPushButton("Seç…")
        b.setFixedWidth(58)
        b.clicked.connect(slot)
        h.addWidget(b)
        return h

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(340)
        w.setMaximumWidth(460)
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        grp = QGroupBox("Ortak")
        g = QVBoxLayout(grp)
        g.setSpacing(6)
        self.imgsz_spin = QSpinBox()
        self.imgsz_spin.setRange(160, 2048)
        self.imgsz_spin.setSingleStep(32)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setFixedWidth(90)
        self.imgsz_spin.setToolTip("Eğitimdeki değeri kullan; export ile ölçüm aynı "
                                   "olmalı")
        g.addLayout(self._row("Görsel boyutu", self.imgsz_spin))
        self.device_combo = QComboBox()
        cihaz_combo_doldur(self.device_combo)
        self.device_combo.setFixedWidth(130)
        g.addLayout(self._row("Cihaz", self.device_combo))
        v.addWidget(grp)

        self.tabs_in = QTabWidget()
        self.tabs_in.addTab(self._build_export_tab(), "Dışa Aktar")
        self.tabs_in.addTab(self._build_bench_tab(), "Hız Ölçümü")
        v.addWidget(self.tabs_in)

        h = QHBoxLayout()
        h.setSpacing(6)
        self.progress = QProgressBar()
        h.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setFixedWidth(70)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        h.addWidget(self.cancel_btn)
        v.addLayout(h)

        self.save_btn = QPushButton("Sonucu Kaydet…")
        self.save_btn.clicked.connect(self._save_report)
        v.addWidget(self.save_btn)
        v.addStretch()
        return w

    def _build_export_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 10, 8, 8)
        v.setSpacing(6)

        v.addWidget(QLabel("Listedeki seçili model dışa aktarılır"))
        self.fmt_combo = QComboBox()
        for text, key in (("ONNX", "onnx"), ("TensorRT (.engine)", "engine"),
                          ("OpenVINO", "openvino"), ("TorchScript", "torchscript")):
            self.fmt_combo.addItem(text, key)
        v.addLayout(self._row("Biçim", self.fmt_combo))

        self.half_chk = QCheckBox("FP16 (half) — GPU'da ~2× hız")
        v.addWidget(self.half_chk)
        self.int8_chk = QCheckBox("INT8 — en hızlı, doğruluk düşebilir")
        v.addWidget(self.int8_chk)
        self.dyn_chk = QCheckBox("Dinamik giriş boyutu")
        v.addWidget(self.dyn_chk)
        self.simp_chk = QCheckBox("ONNX sadeleştir (simplify)")
        self.simp_chk.setChecked(True)
        v.addWidget(self.simp_chk)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 64)
        self.batch_spin.setValue(1)
        self.batch_spin.setFixedWidth(90)
        v.addLayout(self._row("Batch", self.batch_spin))

        self.ws_spin = QSpinBox()
        self.ws_spin.setRange(0, 32)
        self.ws_spin.setValue(4)
        self.ws_spin.setSuffix(" GB")
        self.ws_spin.setFixedWidth(90)
        self.ws_spin.setToolTip("Sadece TensorRT: derleme çalışma alanı")
        v.addLayout(self._row("TRT workspace", self.ws_spin))

        v.addWidget(QLabel("INT8 kalibrasyon verisi (data.yaml)"))
        self.data_edit = QLineEdit()
        v.addLayout(self._path_row(self.data_edit, self._pick_data))

        self.export_btn = QPushButton("⇩  Dışa Aktar")
        self.export_btn.setMinimumHeight(36)
        self.export_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.export_btn.clicked.connect(self._start_export)
        v.addWidget(self.export_btn)

        hint = QLabel("Aktarılan dosya bitince listeye kendiliğinden eklenir; "
                      "sonra Hız Ölçümü'nde .pt ile yan yana karşılaştır.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#6b7686; font-size:11px;")
        v.addWidget(hint)
        v.addStretch()
        return w

    def _build_bench_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 10, 8, 8)
        v.setSpacing(6)

        v.addWidget(QLabel("Ölçüm görselleri (klasör)"))
        self.bench_dir_edit = QLineEdit()
        v.addLayout(self._path_row(self.bench_dir_edit, self._pick_bench_dir))

        self.warmup_spin = QSpinBox()
        self.warmup_spin.setRange(0, 100)
        self.warmup_spin.setValue(5)
        self.warmup_spin.setFixedWidth(90)
        self.warmup_spin.setToolTip("İlk çağrılar yavaştır, ölçüme katılmaz")
        v.addLayout(self._row("Isınma", self.warmup_spin))

        self.iters_spin = QSpinBox()
        self.iters_spin.setRange(5, 5000)
        self.iters_spin.setValue(50)
        self.iters_spin.setFixedWidth(90)
        v.addLayout(self._row("Ölçüm tekrarı", self.iters_spin))

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.01, 0.99)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.25)
        self.conf_spin.setFixedWidth(90)
        v.addLayout(self._row("Güven eşiği", self.conf_spin))

        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.1, 0.95)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setValue(0.45)
        self.iou_spin.setFixedWidth(90)
        v.addLayout(self._row("NMS IoU", self.iou_spin))

        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(0, 128)
        self.threads_spin.setValue(0)
        self.threads_spin.setFixedWidth(90)
        self.threads_spin.setToolTip("0 = dokunma. CPU'da çok kameralı senaryoyu "
                                     "taklit etmek için 1-2 yap")
        v.addLayout(self._row("CPU iş parçacığı", self.threads_spin))

        self.cam_fps_spin = QDoubleSpinBox()
        self.cam_fps_spin.setRange(0.1, 60.0)
        self.cam_fps_spin.setSingleStep(0.5)
        self.cam_fps_spin.setValue(2.0)
        self.cam_fps_spin.setFixedWidth(90)
        self.cam_fps_spin.setToolTip("Kamera başına saniyede kaç kare işlenecek? "
                                     "Kapasite tahmini bundan hesaplanır")
        v.addLayout(self._row("Kamera başına fps", self.cam_fps_spin))

        self.compare_chk = QCheckBox("Referansla sapmayı ölç (ilk model referans)")
        self.compare_chk.setChecked(True)
        self.compare_chk.setToolTip("FP16/INT8 dönüşümü tahminleri bozdu mu? "
                                    "Etiket gerektirmez")
        v.addWidget(self.compare_chk)

        self.compare_n_spin = QSpinBox()
        self.compare_n_spin.setRange(1, 500)
        self.compare_n_spin.setValue(25)
        self.compare_n_spin.setFixedWidth(90)
        v.addLayout(self._row("Sapma için kare", self.compare_n_spin))

        self.bench_btn = QPushButton("⏱  Hızı Ölç")
        self.bench_btn.setMinimumHeight(36)
        self.bench_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.bench_btn.clicked.connect(self._start_bench)
        v.addWidget(self.bench_btn)
        v.addStretch()
        return w

    def _build_menu(self):
        m = self.menuBar().addMenu("Dosya")

        def act(label, slot, sc=""):
            a = QAction(label, self)
            if sc:
                a.setShortcut(sc)
            a.triggered.connect(slot)
            m.addAction(a)

        act("Model Ekle…", self._add_models, "Ctrl+O")
        act("Sonucu Kaydet…", self._save_report, "Ctrl+S")
        m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    # ── model listesi
    def _log(self, t: str):
        self.log_box.append(t)

    def _add_models(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Model dosyaları", "",
            "Modeller (*.pt *.onnx *.engine *.torchscript *.xml);;Tüm Dosyalar (*)")
        for p in paths:
            self._add_model_path(p)

    def _add_model_path(self, path: str):
        if not path or not os.path.exists(path):
            return
        for i in range(self.model_list.count()):
            if self.model_list.item(i).data(Qt.UserRole) == path:
                return
        it = QListWidgetItem(f"{os.path.basename(path)}   [{human_size(path)}]")
        it.setData(Qt.UserRole, path)
        it.setToolTip(path)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked)
        self.model_list.addItem(it)
        self.model_list.setCurrentRow(self.model_list.count() - 1)
        self.list_info.setText(f"{self.model_list.count()} model")

    def _remove_model(self):
        row = self.model_list.currentRow()
        if row >= 0:
            self.model_list.takeItem(row)
            self.list_info.setText(f"{self.model_list.count()} model")

    def _checked_models(self) -> list:
        out = []
        for i in range(self.model_list.count()):
            it = self.model_list.item(i)
            if it.checkState() == Qt.Checked:
                out.append(it.data(Qt.UserRole))
        return out

    def _pick_data(self):
        p, _ = QFileDialog.getOpenFileName(self, "data.yaml seç", "",
                                           "YAML (*.yaml *.yml)")
        if p:
            self.data_edit.setText(p)
            self.data_edit.setCursorPosition(0)

    def _pick_bench_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Ölçüm görselleri klasörü",
                                             self.bench_dir_edit.text())
        if d:
            self.bench_dir_edit.setText(d)
            self.bench_dir_edit.setCursorPosition(0)

    # ── işlemler
    def _busy(self) -> bool:
        if self._worker:
            self.status.showMessage("İşlem sürüyor.")
            return True
        return False

    def _start_export(self):
        if self._busy():
            return
        it = self.model_list.currentItem()
        if it is None:
            QMessageBox.warning(self, "Model yok", "Listeden dışa aktarılacak modeli seç.")
            return
        src = it.data(Qt.UserRole)
        if not src.endswith(".pt"):
            QMessageBox.warning(self, "Kaynak biçim",
                                "Dışa aktarma kaynağı .pt olmalı.")
            return
        if self.int8_chk.isChecked() and not self.data_edit.text():
            if QMessageBox.question(
                    self, "INT8 kalibrasyonu",
                    "INT8 için kalibrasyon verisi (data.yaml) seçilmedi.\n"
                    "Ultralytics kendi varsayılanını dener ve doğruluk daha çok "
                    "düşebilir. Devam?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return

        cfg = {
            "model_path": src,
            "format": self.fmt_combo.currentData(),
            "imgsz": int(self.imgsz_spin.value()),
            "half": self.half_chk.isChecked(),
            "int8": self.int8_chk.isChecked(),
            "dynamic": self.dyn_chk.isChecked(),
            "simplify": self.simp_chk.isChecked(),
            "batch": int(self.batch_spin.value()),
            "device": self.device_combo.currentData(),
            "workspace": int(self.ws_spin.value()) or None,
            "data": self.data_edit.text().strip(),
        }
        self._log(f"── dışa aktarma: {os.path.basename(src)} → "
                  f"{cfg['format']} ──")
        self.tabs_out.setCurrentIndex(1)
        self._worker = ExportWorker(cfg)
        self._worker.log.connect(self._log)
        self._worker.done.connect(self._on_export_done)
        self._worker.finished.connect(self._on_finished)
        self._set_busy(True)
        self.progress.setRange(0, 0)          # belirsiz süre
        self._worker.start()

    def _on_export_done(self, path: str):
        self.progress.setRange(0, 100)
        self.progress.setValue(100 if path else 0)
        if path:
            self._add_model_path(path)
            self.status.showMessage(f"Aktarıldı: {path}")
        else:
            self.status.showMessage("Dışa aktarma başarısız (loga bak).")

    def _start_bench(self):
        if self._busy():
            return
        models = self._checked_models()
        if not models:
            QMessageBox.warning(self, "Model yok", "Ölçülecek modelleri işaretle.")
            return
        d = self.bench_dir_edit.text().strip()
        if not os.path.isdir(d):
            QMessageBox.warning(self, "Klasör yok", "Ölçüm görselleri klasörünü seç.")
            return
        images = list_images(d, limit=max(50, self.iters_spin.value()))
        if not images:
            QMessageBox.warning(self, "Görsel yok", "Klasörde görsel bulunamadı.")
            return

        cfg = {
            "models": models, "images": images,
            "imgsz": int(self.imgsz_spin.value()),
            "device": self.device_combo.currentData(),
            "conf": float(self.conf_spin.value()),
            "iou_nms": float(self.iou_spin.value()),
            "max_det": 300,
            "warmup": int(self.warmup_spin.value()),
            "iters": int(self.iters_spin.value()),
            "cpu_threads": int(self.threads_spin.value()),
            "compare": self.compare_chk.isChecked(),
            "compare_n": int(self.compare_n_spin.value()),
        }
        self._log(f"── hız ölçümü: {len(models)} model, {cfg['iters']} tekrar, "
                  f"imgsz {cfg['imgsz']} ──")
        self.tabs_out.setCurrentIndex(1)
        self._worker = BenchWorker(cfg)
        self._worker.log.connect(self._log)
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_bench_result)
        self._worker.finished.connect(self._on_finished)
        self._set_busy(True)
        self._worker.start()

    def _on_progress(self, done: int, total: int):
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.showMessage(f"{done}/{total}")

    def _on_bench_result(self, res: dict):
        rows = res.get("rows", [])
        if not rows:
            self.status.showMessage("Ölçüm sonucu yok (loga bak).")
            return
        self.report_box.setPlainText(self._bench_report(rows))
        self.tabs_out.setCurrentIndex(0)
        self.status.showMessage("Ölçüm bitti." + (" (iptal)" if res.get("iptal") else ""))

    def _bench_report(self, rows: list) -> str:
        cam_fps = self.cam_fps_spin.value()
        dev = self.device_combo.currentText()
        L = ["═══ HIZ ÖLÇÜMÜ ═══",
             f"cihaz: {dev}    görsel boyutu: {self.imgsz_spin.value()}    "
             f"tekrar: {self.iters_spin.value()}",
             f"CPU iş parçacığı: {self.threads_spin.value() or 'dokunulmadı'}",
             ""]
        L.append(f"{'model':<28s}{'boyut':>10s}{'ön':>7s}{'çıkarım':>9s}{'son':>7s}"
                 f"{'toplam':>9s}{'p95':>8s}{'FPS':>8s}")
        for r in rows:
            L.append(f"{os.path.basename(r['model'])[:27]:<28s}{r['boyut']:>10s}"
                     f"{r['pre']:>7.1f}{r['inf']:>9.1f}{r['post']:>7.1f}"
                     f"{r['toplam']:>9.1f}{r['p95']:>8.1f}{r['fps']:>8.1f}")
        L.append("(süreler ms/kare, ortalama; p95 = en yavaş %5'in eşiği)")
        L.append("")

        base = rows[0]
        if len(rows) > 1:
            L.append("── Referansa göre hızlanma ──")
            for r in rows[1:]:
                kat = base["toplam"] / r["toplam"] if r["toplam"] else 0
                L.append(f"{os.path.basename(r['model'])[:34]:<35s} {kat:.2f}× "
                         f"({base['toplam']:.1f} → {r['toplam']:.1f} ms)")
            L.append("")

        L.append("── Kamera kapasitesi tahmini ──")
        L.append(f"(kamera başına {cam_fps:g} kare/sn işlenecek varsayımıyla, "
                 "tek süreç)")
        for r in rows:
            kapasite = r["fps"] / cam_fps
            L.append(f"{os.path.basename(r['model'])[:34]:<35s} "
                     f"{kapasite:.1f} kamera")
        L.append("Not: gerçek sistemde kod çözme (decode), ROI ve I/O da CPU yer; "
                 "bu üst sınırdır.")
        L.append("")

        sapmalar = [r for r in rows if r.get("sapma")]
        if sapmalar:
            L.append("── Referansla sapma (etiketsiz kontrol) ──")
            L.append(f"{'model':<28s}{'kutu (ref/aday)':>18s}{'eşleşen':>9s}"
                     f"{'ort IoU':>9s}{'conf sapma':>12s}")
            for r in sapmalar:
                s = r["sapma"]
                L.append(f"{os.path.basename(r['model'])[:27]:<28s}"
                         f"{str(s['ref_kutu']) + '/' + str(s['aday_kutu']):>18s}"
                         f"{s['oran'] * 100:>8.1f}%{s['ort_iou']:>9.3f}"
                         f"{s['ort_conf_sapma']:>12.3f}")
            for r in sapmalar:
                s = r["sapma"]
                ad = os.path.basename(r["model"])
                if s["oran"] < 0.95:
                    L.append(f"  ! {ad}: kutuların %{(1 - s['oran']) * 100:.1f}'i "
                             "kayboldu/kaydı — doğruluğu etiketli setle doğrula "
                             "(Hata Analizi)")
                elif s["ort_conf_sapma"] > 0.05:
                    L.append(f"  ? {ad}: güven değerleri kayıyor "
                             f"({s['ort_conf_sapma']:.3f}) — eşiğini yeniden ayarla")
                else:
                    L.append(f"  ✓ {ad}: tahminler referansla uyumlu")
        return "\n".join(L)

    def _cancel(self):
        if self._worker and hasattr(self._worker, "cancel"):
            self._worker.cancel()
            self.status.showMessage("İptal isteniyor…")

    def _set_busy(self, busy: bool):
        self.export_btn.setEnabled(not busy)
        self.bench_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)

    def _on_finished(self):
        self._worker = None
        self._set_busy(False)

    def _save_report(self):
        if not self.report_box.toPlainText():
            self.status.showMessage("Önce ölçüm yap.")
            return
        p, _ = QFileDialog.getSaveFileName(self, "Sonucu kaydet",
                                           "hiz_raporu.txt", "Metin (*.txt)")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.report_box.toPlainText())
            self.status.showMessage(f"Kaydedildi: {p}")
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")

    def closeEvent(self, ev):
        if self._worker:
            if hasattr(self._worker, "cancel"):
                self._worker.cancel()
            self._worker.wait(5000)
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
    app.setApplicationName("Model Export & Hız")
    win = MainWindow()
    win.show()
    for a in sys.argv[1:]:
        if a.lower().endswith(MODEL_EXTS):
            win._add_model_path(os.path.abspath(a))
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
