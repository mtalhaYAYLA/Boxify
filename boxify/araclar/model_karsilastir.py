"""Model Karşılaştır — aynı video üzerinde 1-3 YOLO modelinin
çıktısını yan yana (ya da alt alta) kıyaslar.

Video + 1-3 model (.pt) seçilir → Başlat. Her model için kullanılacak bir veya
birden fazla sınıf ayrı ayrı açılıp kapatılabilir; istenirse her model kendi
conf / IoU / imgsz / maks-tespit ayarıyla da koşturulabilir. Video örnekleme
fps'ine göre kare kare okunur; her kare önce ortak bir panel yüksekliğine
ölçeklenir (tüm modeller birebir aynı pikselleri görsün diye — adil kıyas için
önemli), sonra sırayla her modelden geçirilir. Tespitler çizilip model adı/renk
etiketiyle bindirilir; bu mozaik hem canlı önizlenir hem de tek bir
karşılaştırma videosuna (istenirse ayrıca model başına ayrı videoya) yazılır.
İş bitince model başına tespit sayısı / ortalama güven / hız özeti bir
metin rapor olarak çıkar.

Varsayılan olarak her model ortak ayarları kullanır — kıyasın adil kalması
için doğru olan budur; modele özel ayar açmak bilinçli bir tercihtir ve
rapora ayrıca yazılır.

Tek model seçildiğinde de çalışır: o zaman çıktı bir kıyas değil, tek modelin
video üzerindeki davranışının dökümüdür.

Kullanım: video + model A (+ model B/C) seç, sınıfları işaretle → Başlat.

Bağımlılık: PyQt5, ultralytics, opencv-python, numpy.
"""
import os
import sys
import time

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QFrame, QStatusBar, QGroupBox,
    QMessageBox, QLineEdit, QAction, QSizePolicy, QComboBox, QProgressBar,
    QCheckBox, QDoubleSpinBox, QSpinBox, QTextEdit, QTabWidget, QScrollArea,
    QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QImage, QPixmap

from ..tema import STYLE, MAVI  # ortak açık tema — bkz. boxify/tema.py
from .model_bilgi import SinifYukleyici, sinif_ozeti, cihaz_combo_doldur

MAX_MODELS = 3
HARFLER = ["A", "B", "C"]
# Renk körlüğü dostu palet: mavi / kehribar (koyu metinle) / yumuşak mor
RENKLER = [MAVI, "#d9a62e", "#8e6bbf"]
BAR_METIN = ["#f5f8fb", "#2b3442", "#f5f8fb"]   # her renge göre okunaklı metin


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
        total = float(parts[-1])
        if total < 0:
            return -1
        if len(parts) >= 2:
            total += int(parts[-2]) * 60
        if len(parts) == 3:
            total += int(parts[0]) * 3600
        return int(round(total * 1000))
    except Exception:
        return -1


def hex_to_bgr(h: str):
    h = h.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (b, g, r)


def safe_name(text: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_ " else "_" for c in text.strip())
    keep = "_".join(keep.split())
    return keep or "model"


def unique_labels(raw: list) -> list:
    """Aynı etiketi ikinci kez görürse ' (2)' gibi ayırt edici ek ekler."""
    seen = {}
    out = []
    for lbl in raw:
        lbl = lbl.strip() or "Model"
        if lbl in seen:
            seen[lbl] += 1
            out.append(f"{lbl} ({seen[lbl]})")
        else:
            seen[lbl] = 1
            out.append(lbl)
    return out


class CompareWorker(QThread):
    """Modelleri yükler, videoyu örnekleyerek okur, mozaik üretir/yazar."""
    models_ready = pyqtSignal(dict)      # {etiket: {id: isim}}
    preview = pyqtSignal(object)         # QImage — canlı mozaik
    progress = pyqtSignal(int, int)      # işlenen, tahmini toplam
    log = pyqtSignal(str)
    failed = pyqtSignal(str)
    summary = pyqtSignal(dict, dict)     # {etiket: istatistik}, cfg_ozeti

    def __init__(self, cfg: dict):
        super().__init__()
        self.cfg = cfg
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _make_mosaic(self, cv2, np, frames, labels, colors_hex, counts, dikey=False):
        bar_h = 30
        sep_kalinlik = 3
        h, w = frames[0].shape[:2]
        panels = []
        for frame, label, color_hex, n in zip(frames, labels, colors_hex, counts):
            # Bir model hata verip farklı ölçüde kare döndürürse yığma
            # işlemi patlamasın diye ilk panelin ölçüsüne getirilir
            if frame.shape[:2] != (h, w):
                frame = cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
            canvas = np.full((h + bar_h, w, 3), 235, dtype=np.uint8)
            bgr = hex_to_bgr(color_hex)
            cv2.rectangle(canvas, (0, 0), (w, bar_h), bgr, -1)
            idx = RENKLER.index(color_hex) if color_hex in RENKLER else 0
            txt_col = hex_to_bgr(BAR_METIN[idx])
            cv2.putText(canvas, f"{label}   |   {n} tespit", (10, bar_h - 9),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.55, txt_col, 1, cv2.LINE_AA)
            canvas[bar_h:, :, :] = frame
            panels.append(canvas)

        out = panels[0]
        for p in panels[1:]:
            if dikey:
                sep = np.full((sep_kalinlik, out.shape[1], 3), 60, dtype=np.uint8)
                out = np.vstack([out, sep, p])
            else:
                sep = np.full((out.shape[0], sep_kalinlik, 3), 60, dtype=np.uint8)
                out = np.hstack([out, sep, p])

        # mp4v tek sayılı en/boyda kare yazamıyor — kırpıp çift sayıya indir
        oh, ow = out.shape[:2]
        if oh % 2 or ow % 2:
            out = out[:oh - (oh % 2), :ow - (ow % 2)]
        return out

    def run(self):
        cfg = self.cfg
        try:
            import cv2
            import numpy as np
            from ultralytics import YOLO
        except Exception as e:
            self.failed.emit(f"opencv/ultralytics/numpy içe aktarılamadı:\n{e}")
            return

        models = []
        for slot in cfg["models"]:
            if self._cancel:
                self.log.emit("İptal edildi.")
                return
            try:
                self.log.emit(f"{slot['label']} yükleniyor: {slot['path']}")
                m = YOLO(slot["path"])
                names = {int(k): str(v) for k, v in m.names.items()}
                models.append({"model": m, "label": slot["label"],
                               "color": slot["color"], "names": names,
                               "classes": slot.get("classes"),
                               "conf": slot["conf"], "iou": slot["iou"],
                               "imgsz": slot["imgsz"], "max_det": slot["max_det"],
                               "ozel": slot["ozel"]})
            except Exception as e:
                self.failed.emit(f"{slot['label']} yüklenemedi:\n{e}")
                return
        self.models_ready.emit({m["label"]: m["names"] for m in models})

        # Sınıf filtresindeki kimlik modelde yoksa ultralytics sessizce boş
        # sonuç üretir; sebebini aramak yerine baştan söylemek daha iyi
        for m in models:
            if m["classes"]:
                gecersiz = [c for c in m["classes"] if c not in m["names"]]
                if gecersiz:
                    self.log.emit(
                        f"UYARI — {m['label']}: sınıf filtresindeki {gecersiz} "
                        "kimlikleri bu modelde yok, yok sayılıyor.")
                    m["classes"] = [c for c in m["classes"] if c in m["names"]] or None
        self.log.emit("Modeller hazır — video açılıyor…")

        cap = cv2.VideoCapture(cfg["video_path"])
        if not cap.isOpened():
            cap.release()
            self.failed.emit("Video açılamadı.")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if fps <= 0:
            fps = 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

        SONSUZ = 1 << 30
        start_frame = 0
        end_frame = total_frames if total_frames > 0 else SONSUZ
        if cfg["start_ms"] is not None and cfg["end_ms"] is not None:
            sf = max(0, int(cfg["start_ms"] / 1000.0 * fps))
            ef = int(cfg["end_ms"] / 1000.0 * fps)
            if total_frames > 0:
                ef = min(total_frames, ef)
            if ef > sf:
                start_frame, end_frame = sf, ef

        stride = max(1, round(fps / cfg["sample_fps"])) if cfg["sample_fps"] > 0 else 1
        out_fps = max(1.0, fps / stride)

        if start_frame:
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        out_dir = cfg["out_dir"]
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            self.failed.emit(f"Çıktı klasörü oluşturulamadı:\n{e}")
            cap.release()
            return

        combined_path = os.path.join(out_dir, "karsilastirma.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = None
        indiv_writers = {}
        yazicilar_kuruldu = False

        panel_h = cfg["panel_h"]
        stats = {m["label"]: {"kare": 0, "tespit": 0, "sinif": {},
                              "conf_toplam": 0.0, "conf_sayi": 0,
                              "kare_tespitli": 0, "hata": 0,
                              "sure_toplam": 0.0} for m in models}

        # Kare sayısı okunamayan kaynaklarda tahmin verilemez; ilerleme
        # çubuğu o durumda belirsiz moda düşsün diye 0 gönderilir
        if end_frame >= SONSUZ or end_frame <= start_frame:
            est_total = 0
        else:
            est_total = max(1, (end_frame - start_frame + stride - 1) // stride)

        processed = 0
        idx = start_frame
        hata_bildirildi = set()

        while idx < end_frame:
            if self._cancel:
                self.log.emit("İptal edildi.")
                break

            if (idx - start_frame) % stride != 0:
                if not cap.grab():
                    break
                idx += 1
                continue

            ok, frame = cap.read()
            if not ok:
                break

            h0, w0 = frame.shape[:2]
            if h0 != panel_h and h0 > 0:
                scale = panel_h / h0
                frame = cv2.resize(frame, (max(1, int(round(w0 * scale))), panel_h),
                                   interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)

            drawn_frames, labels, colors, counts = [], [], [], []
            for m in models:
                if self._cancel:
                    break
                t0 = time.time()
                try:
                    # half yalnızca işaretliyse gönderiliyor: ultralytics 8.4
                    # bu argümanı her geçişinde "deprecated" uyarısı basıyor
                    # ve kare başına iki satırla günlüğü boğuyor.
                    ek = {"half": True} if cfg["half"] else {}
                    res = m["model"].predict(
                        source=frame, conf=m["conf"], iou=m["iou"],
                        imgsz=m["imgsz"], device=cfg["device"],
                        max_det=m["max_det"], classes=m["classes"],
                        agnostic_nms=cfg["agnostic_nms"],
                        verbose=False, **ek)[0]
                except Exception as e:
                    stats[m["label"]]["hata"] += 1
                    if m["label"] not in hata_bildirildi:
                        hata_bildirildi.add(m["label"])
                        self.log.emit(f"HATA — {m['label']}: {e}")
                    drawn_frames.append(frame.copy())
                    labels.append(m["label"]); colors.append(m["color"]); counts.append(0)
                    continue
                dt = time.time() - t0

                boxes = res.boxes
                n = 0 if boxes is None else len(boxes)
                st = stats[m["label"]]
                st["kare"] += 1
                st["sure_toplam"] += dt
                if n:
                    st["tespit"] += n
                    st["kare_tespitli"] += 1
                    clss = boxes.cls.cpu().numpy().astype(int)
                    confs = boxes.conf.cpu().numpy()
                    for c, cf in zip(clss, confs):
                        cname = m["names"].get(int(c), str(c))
                        st["sinif"][cname] = st["sinif"].get(cname, 0) + 1
                        st["conf_toplam"] += float(cf)
                        st["conf_sayi"] += 1

                drawn_frames.append(res.plot(labels=cfg["draw_labels"],
                                             conf=cfg["draw_conf"]))
                labels.append(m["label"]); colors.append(m["color"]); counts.append(n)

            if self._cancel:
                self.log.emit("İptal edildi.")
                break

            mosaic = self._make_mosaic(cv2, np, drawn_frames, labels, colors,
                                       counts, cfg["dikey"])

            if not yazicilar_kuruldu:
                yazicilar_kuruldu = True
                if cfg["write_video"]:
                    mh, mw = mosaic.shape[:2]
                    writer = cv2.VideoWriter(combined_path, fourcc, out_fps, (mw, mh))
                    if not writer.isOpened():
                        self.log.emit(
                            "UYARI: karşılaştırma videosu açılamadı (kodek eksik olabilir); "
                            "canlı önizleme yine de çalışacak ama dosya kaydedilmeyecek.")
                        writer.release()
                        writer = None
                    if cfg["save_individual"]:
                        fh, fw = frame.shape[:2]
                        fw -= fw % 2
                        fh -= fh % 2
                        for m in models:
                            p = os.path.join(out_dir, f"{safe_name(m['label'])}.mp4")
                            iw = cv2.VideoWriter(p, fourcc, out_fps, (fw, fh))
                            if iw.isOpened():
                                indiv_writers[m["label"]] = iw
                            else:
                                iw.release()
                                self.log.emit(f"UYARI: ayrı video açılamadı: {p}")

            if writer is not None:
                writer.write(mosaic)
            for lbl, dframe in zip(labels, drawn_frames):
                iw = indiv_writers.get(lbl)
                if iw is not None:
                    dh, dw = dframe.shape[:2]
                    iw.write(dframe[:dh - (dh % 2), :dw - (dw % 2)])

            if cfg["show_preview"]:
                rgb = mosaic[:, :, ::-1].copy()
                hh, ww = rgb.shape[:2]
                self.preview.emit(
                    QImage(rgb.data, ww, hh, 3 * ww, QImage.Format_RGB888).copy())

            processed += 1
            self.progress.emit(processed, est_total)
            idx += 1

        cap.release()
        if writer is not None:
            writer.release()
        for w in indiv_writers.values():
            w.release()

        if processed == 0:
            self.failed.emit(
                "Hiç kare işlenmedi — video/aralık boş olabilir ya da "
                "kaynak açılamadı.")
            return

        summary = {}
        for m in models:
            st = stats[m["label"]]
            kare = max(1, st["kare"])
            ort_ms = (st["sure_toplam"] / kare) * 1000.0
            summary[m["label"]] = {
                "kare": st["kare"],
                "tespit": st["tespit"],
                "kare_basi": st["tespit"] / kare,
                "bos_oran": 1.0 - (st["kare_tespitli"] / kare),
                "ort_conf": (st["conf_toplam"] / st["conf_sayi"]) if st["conf_sayi"] else 0.0,
                "ort_ms": ort_ms,
                "fps": 1000.0 / ort_ms if ort_ms > 0 else 0.0,
                "sinif": st["sinif"],
                "hata": st["hata"],
                "model_siniflari": m["names"],
                "ayar": {
                    "conf": m["conf"], "iou": m["iou"], "imgsz": m["imgsz"],
                    "max_det": m["max_det"], "ozel": m["ozel"],
                    "classes": ([m["names"].get(c, str(c)) for c in m["classes"]]
                                if m["classes"] else None),
                },
            }

        cfg_ozet = {
            "video_path": cfg["video_path"],
            "out_dir": out_dir,
            "combined_path": combined_path if writer is not None else "",
            "sample_fps": cfg["sample_fps"],
            "panel_h": panel_h,
            "conf": cfg["conf"], "iou": cfg["iou"], "imgsz": cfg["imgsz"],
            "half": cfg["half"], "agnostic_nms": cfg["agnostic_nms"],
            "device_text": cfg["device_text"],
            "range_text": cfg["range_text"],
            "islenen_kare": processed,
            "iptal": self._cancel,
        }
        if writer is not None:
            self.log.emit(f"Bitti — {processed} kare işlendi → {combined_path}")
        else:
            self.log.emit(f"Bitti — {processed} kare işlendi (video yazılmadı).")
        self.summary.emit(summary, cfg_ozet)


class PreviewLabel(QLabel):
    """Mozaik önizlemeyi oranını koruyarak pencereye sığdırır."""

    def __init__(self):
        super().__init__("Video ve 1-3 model seçip Başlat'a bas")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background:#1c1f24; color:#9aa5b1; border:1px dashed #b4bfcb; "
                           "border-radius:8px; font-size:13px;")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setMinimumSize(220, 240)
        self._img = None

    # QLabel, pixmap atanınca boyut talebini pixmap'in ölçüsü yapar. Önizleme
    # kaydırma alanı içindeyken bu bir geri besleme döngüsü kurar: büyük
    # pixmap -> araç genişler -> daha büyük pixmap… Araç görünür alanı aşar,
    # yatay kaydırma çıkar ve mozaiğin sağ yarısı (yani ikinci/üçüncü model)
    # ekran dışında kalır. Önizleme kendisine verilen yere sığar; bu yüzden
    # boyut talebi pixmap'ten bağımsız ve küçük tutuluyor.
    def minimumSizeHint(self):
        return QSize(220, 240)

    def sizeHint(self):
        return QSize(480, 240)

    def set_image(self, img: QImage):
        self._img = img
        self._redraw()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._redraw()

    def _redraw(self):
        if self._img is None:
            return
        pix = QPixmap.fromImage(self._img).scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(pix)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Model Karşılaştır — aynı videoda birden çok YOLO modeli")
        self.setMinimumSize(1100, 700)
        self._video_path = ""
        self._video_dur_ms = 0
        self._out_dir = ""
        self._worker = None
        self._slot_rows = []            # her yuva için widget referansları
        self._sinif_yukleyiciler = {}   # yuva indeksi -> SinifYukleyici
        self._build_ui()
        self._build_menu()
        self._tazele_yuvalar()

    # ─────────────────────────────── UI

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_center())
        splitter.setSizes([400, 900])
        vbox.addWidget(splitter, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage(
            "Video seç, 1-3 model ekle, sınıfları ve ayarları düzenleyip Başlat'a bas.")

    def _build_left(self) -> QWidget:
        """Sol panel: kaydırılan ayarlar + dibe sabitlenmiş çalıştırma satırı.

        Başlat/ilerleme/iptal bilerek kaydırma alanının DIŞINDA duruyor. Bu
        araçta ayar sayısı diğerlerinden fazla; hepsi tek bir kaydırma alanına
        konursa panel görünür alanı aşıyor ve en çok kullanılan düğme kıvrımın
        altında kalıyor — macOS'ta ince kaydırma çubuğu belli olmadığı için
        kullanıcı düğmenin orada olduğunu göremiyor.
        """
        dis = QWidget()
        dis_v = QVBoxLayout(dis)
        dis_v.setContentsMargins(0, 0, 0, 0)
        dis_v.setSpacing(6)
        dis.setMinimumWidth(350)
        dis.setMaximumWidth(470)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # macOS'ta kaydırma çubuğu varsayılan olarak ancak kaydırırken beliriyor;
        # sürekli görünür yapmak "aşağıda daha var" bilgisini kaybettirmiyor
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(10)

        v.addWidget(self._build_video_group())
        for i in range(MAX_MODELS):
            v.addWidget(self._build_model_group(i))
        self._add_model_btn = QPushButton("+ Model Ekle")
        self._add_model_btn.setToolTip("Karşılaştırmaya bir model daha kat (en fazla 3)")
        self._add_model_btn.clicked.connect(self._model_ekle)
        v.addWidget(self._add_model_btn)

        # Çıkarım ayarlarının makul varsayılanları var, kapalı başlayabilir.
        # Çıktı grubu ZORUNLU olan klasör seçimini taşıdığı için hep açık —
        # zorunlu bir denetimi katlanmış bir grubun ardına saklamak, düğmeyi
        # bulunamaz hale getirir.
        v.addWidget(self._build_infer_group())
        v.addWidget(self._build_output_group())
        v.addStretch()
        scroll.setWidget(w)
        dis_v.addWidget(scroll, 1)

        # ── kaydırmayan çalıştırma şeridi
        serit = QFrame()
        serit.setFrameShape(QFrame.NoFrame)
        sv = QVBoxLayout(serit)
        sv.setContentsMargins(8, 6, 8, 8)
        sv.setSpacing(6)

        cikti_lbl = QLabel("Çıktı klasörü")
        cikti_lbl.setStyleSheet("font-weight:normal; font-size:11px;")
        sv.addWidget(cikti_lbl)
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("karşılaştırma videosunun kaydedileceği klasör")
        sv.addLayout(self._dir_row(self.out_edit, self._pick_out_dir))

        # Çıktıyla ilgili iki kısayol da burada: iş bitince "Sonucu Aç"ı
        # kaydırıp aramak zorunda kalmamak için şeritte duruyorlar
        hb = QHBoxLayout()
        hb.setSpacing(6)
        self.open_dir_btn = QPushButton("Klasörü Aç")
        self.open_dir_btn.clicked.connect(self._open_out_dir)
        hb.addWidget(self.open_dir_btn)
        self.play_btn = QPushButton("▶ Sonucu Aç")
        self.play_btn.setEnabled(False)
        self.play_btn.setToolTip("karsilastirma.mp4'ü sistem oynatıcısında açar")
        self.play_btn.clicked.connect(self._play_result)
        hb.addWidget(self.play_btn)
        sv.addLayout(hb)

        self.start_btn = QPushButton("▶  Karşılaştırmayı Başlat")
        self.start_btn.setMinimumHeight(38)
        self.start_btn.setStyleSheet(
            "background:#2e6da4; color:#f5f8fb; font-weight:bold; font-size:13px;"
            "border:1px solid #275b8c; border-radius:4px; padding:8px 12px;")
        self.start_btn.clicked.connect(self._start)
        sv.addWidget(self.start_btn)

        h_run = QHBoxLayout()
        h_run.setSpacing(6)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        h_run.addWidget(self.progress, 1)
        self.cancel_btn = QPushButton("İptal")
        self.cancel_btn.setFixedWidth(70)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        h_run.addWidget(self.cancel_btn)
        sv.addLayout(h_run)

        self.stats_lbl = QLabel("—")
        self.stats_lbl.setWordWrap(True)
        self.stats_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        sv.addWidget(self.stats_lbl)

        dis_v.addWidget(serit)
        return dis

    def _dir_row(self, edit: QLineEdit, slot) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        edit.setReadOnly(True)
        edit.setStyleSheet("font-size:11px; font-family:monospace;")
        h.addWidget(edit, 1)
        b = QPushButton("Seç…")
        b.setFixedWidth(60)
        b.clicked.connect(slot)
        h.addWidget(b)
        return h

    def _spin_row(self, text, widget) -> QHBoxLayout:
        h = QHBoxLayout()
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:normal;")
        h.addWidget(lb)
        h.addStretch()
        h.addWidget(widget)
        return h

    def _build_video_group(self) -> QGroupBox:
        grp = QGroupBox("Video")
        g = QVBoxLayout(grp)
        g.setSpacing(6)

        self.video_edit = QLineEdit()
        self.video_edit.setPlaceholderText("karşılaştırılacak video")
        g.addLayout(self._dir_row(self.video_edit, self._pick_video))

        self.video_info_lbl = QLabel("Süre / fps: —")
        self.video_info_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        g.addWidget(self.video_info_lbl)

        self.range_chk = QCheckBox("Belirli bir aralık kullan (yoksa tüm video)")
        self.range_chk.toggled.connect(self._on_range_toggled)
        g.addWidget(self.range_chk)

        # Aralık alanları kapalıyken gizlenir (devre dışı bırakılıp yer
        # kaplamaları yerine): sol panelin görünür alanı aşmaması önemli
        self.range_kutu = QWidget()
        hr = QHBoxLayout(self.range_kutu)
        hr.setContentsMargins(0, 0, 0, 0)
        hr.addWidget(QLabel("Başl."))
        self.start_edit = QLineEdit("00:00.000")
        hr.addWidget(self.start_edit)
        hr.addWidget(QLabel("Bitiş"))
        self.end_edit = QLineEdit("00:00.000")
        hr.addWidget(self.end_edit)
        self.range_kutu.setVisible(False)
        g.addWidget(self.range_kutu)

        self.sample_fps_spin = QDoubleSpinBox()
        self.sample_fps_spin.setRange(0.5, 30.0)
        self.sample_fps_spin.setSingleStep(0.5)
        self.sample_fps_spin.setValue(5.0)
        self.sample_fps_spin.setFixedWidth(90)
        self.sample_fps_spin.setToolTip(
            "Videonun tamamı yerine saniyede bu kadar kare işlenir; N model × "
            "her kare çok yavaş olacağından uzun videolarda düşük tutmak iyidir")
        self.sample_fps_spin.valueChanged.connect(self._update_estimate)
        g.addLayout(self._spin_row("Örnekleme (fps)", self.sample_fps_spin))

        self.panel_h_spin = QSpinBox()
        self.panel_h_spin.setRange(180, 1080)
        self.panel_h_spin.setSingleStep(20)
        self.panel_h_spin.setValue(480)
        self.panel_h_spin.setFixedWidth(90)
        self.panel_h_spin.setToolTip(
            "Tüm modeller aynı ölçekteki kareyi görsün diye kare önce bu "
            "yüksekliğe küçültülür (adil kıyas için)")
        g.addLayout(self._spin_row("Panel yüksekliği (px)", self.panel_h_spin))

        self.estimate_lbl = QLabel("Tahmini işlenecek kare: —")
        self.estimate_lbl.setStyleSheet("color:#2e6da4; font-size:11px;")
        g.addWidget(self.estimate_lbl)

        for e in (self.start_edit, self.end_edit):
            e.textChanged.connect(self._update_estimate)
        return grp

    # ── Model yuvası ────────────────────────────────────────────────────
    def _build_model_group(self, i: int) -> QGroupBox:
        harf = HARFLER[i]
        renk = RENKLER[i]
        grp = QGroupBox(f"Model {harf}")
        grp.setStyleSheet(grp.styleSheet() + f"QGroupBox::title {{ color: {renk}; }}")
        g = QVBoxLayout(grp)
        g.setSpacing(6)

        rozet_row = QHBoxLayout()
        rozet = QLabel(harf)
        rozet.setFixedSize(20, 20)
        rozet.setAlignment(Qt.AlignCenter)
        rozet.setStyleSheet(
            f"background:{renk}; color:{BAR_METIN[i]}; border-radius:10px; "
            "font-weight:bold; font-size:11px;")
        rozet_row.addWidget(rozet)
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("model.pt seç")
        rozet_row.addLayout(self._dir_row(path_edit, lambda _=None, idx=i: self._pick_model(idx)))
        remove_btn = QPushButton("Kaldır")
        remove_btn.setFixedWidth(64)
        remove_btn.setToolTip("Bu modeli karşılaştırmadan çıkar")
        remove_btn.clicked.connect(lambda _=False, idx=i: self._model_kaldir(idx))
        rozet_row.addWidget(remove_btn)
        g.addLayout(rozet_row)

        label_edit = QLineEdit()
        label_edit.setPlaceholderText(f"Panelde görünecek ad (ör. YOLOv8n) — boşsa Model {harf}")
        g.addWidget(label_edit)

        info_lbl = QLabel("Sınıflar: —")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color:#6b7686; font-size:11px;")
        g.addWidget(info_lbl)

        class_list = QListWidget()
        class_list.setMaximumHeight(105)
        class_list.setToolTip(
            "İşaretli sınıflar çıkarıma katılır; işareti kaldırılan sınıflar bu "
            "model için kapatılır. Bir modelde birden fazla sınıf seçilebilir.")
        class_list.setVisible(False)
        class_list.itemChanged.connect(lambda _=None, idx=i: self._sinif_ozet_tazele(idx))
        g.addWidget(class_list)

        # Sınıf düğmeleri ve durum satırı, model seçilene kadar hiçbir işe
        # yaramaz; gizli tutmak hem kafa karıştırmıyor hem panel yüksekliğini
        # görünür alanın altında tutuyor
        sinif_kutu = QWidget()
        sk = QVBoxLayout(sinif_kutu)
        sk.setContentsMargins(0, 0, 0, 0)
        sk.setSpacing(4)

        class_buttons = QHBoxLayout()
        all_btn = QPushButton("Tüm sınıflar")
        none_btn = QPushButton("Hiçbiri")
        all_btn.clicked.connect(lambda _=False, idx=i: self._set_all_classes(idx, True))
        none_btn.clicked.connect(lambda _=False, idx=i: self._set_all_classes(idx, False))
        class_buttons.addWidget(all_btn)
        class_buttons.addWidget(none_btn)
        sk.addLayout(class_buttons)

        sinif_durum = QLabel("Model seçilince sınıflar buraya gelir")
        sinif_durum.setWordWrap(True)
        sinif_durum.setStyleSheet("color:#6b7686; font-size:11px;")
        sk.addWidget(sinif_durum)

        sinif_kutu.setVisible(False)
        g.addWidget(sinif_kutu)

        # ── Modele özel çıkarım ayarları
        ozel_chk = QCheckBox("Bu modele özel çıkarım ayarı kullan")
        ozel_chk.setToolTip(
            "Kapalıyken ortak ayarlar geçerlidir (adil kıyas). Açmak, her modeli "
            "kendi en iyi ayarıyla kıyaslamak istediğinde anlamlıdır; seçim "
            "rapora da yazılır.")
        g.addWidget(ozel_chk)

        ozel_kutu = QWidget()
        ok_v = QVBoxLayout(ozel_kutu)
        ok_v.setContentsMargins(12, 0, 0, 0)
        ok_v.setSpacing(4)

        conf_spin = QDoubleSpinBox()
        conf_spin.setRange(0.01, 0.99); conf_spin.setSingleStep(0.05)
        conf_spin.setValue(0.25); conf_spin.setFixedWidth(90)
        ok_v.addLayout(self._spin_row("Güven eşiği (conf)", conf_spin))

        iou_spin = QDoubleSpinBox()
        iou_spin.setRange(0.1, 0.95); iou_spin.setSingleStep(0.05)
        iou_spin.setValue(0.45); iou_spin.setFixedWidth(90)
        ok_v.addLayout(self._spin_row("NMS IoU", iou_spin))

        imgsz_spin = QSpinBox()
        imgsz_spin.setRange(160, 2048); imgsz_spin.setSingleStep(32)
        imgsz_spin.setValue(640); imgsz_spin.setFixedWidth(90)
        ok_v.addLayout(self._spin_row("Görsel boyutu (imgsz)", imgsz_spin))

        maxdet_spin = QSpinBox()
        maxdet_spin.setRange(1, 1000); maxdet_spin.setValue(300)
        maxdet_spin.setFixedWidth(90)
        ok_v.addLayout(self._spin_row("Maks tespit", maxdet_spin))

        ozel_kutu.setVisible(False)
        ozel_chk.toggled.connect(ozel_kutu.setVisible)
        g.addWidget(ozel_kutu)

        self._slot_rows.append({
            "group": grp, "path_edit": path_edit, "label_edit": label_edit,
            "info_lbl": info_lbl, "class_list": class_list, "names": {},
            "path": "", "harf": harf, "renk": renk,
            "sinif_durum": sinif_durum, "sinif_kutu": sinif_kutu,
            "ozel_chk": ozel_chk,
            "conf": conf_spin, "iou": iou_spin, "imgsz": imgsz_spin,
            "max_det": maxdet_spin, "remove_btn": remove_btn,
            # A ve B varsayılan açık (en sık kullanım ikili kıyas), C isteğe bağlı
            "aktif": i < 2,
        })
        return grp

    def _build_infer_group(self) -> QGroupBox:
        grp = QGroupBox("Ortak Çıkarım Ayarları")
        gp = QVBoxLayout(grp)
        gp.setSpacing(6)

        aciklama = QLabel("Kendine özel ayarı olmayan modeller bunları kullanır.")
        aciklama.setWordWrap(True)
        aciklama.setStyleSheet("color:#6b7686; font-size:11px;")
        gp.addWidget(aciklama)

        self.conf_spin = QDoubleSpinBox()
        self.conf_spin.setRange(0.01, 0.99)
        self.conf_spin.setSingleStep(0.05)
        self.conf_spin.setValue(0.25)
        self.conf_spin.setFixedWidth(90)
        gp.addLayout(self._spin_row("Güven eşiği (conf)", self.conf_spin))

        self.iou_spin = QDoubleSpinBox()
        self.iou_spin.setRange(0.1, 0.95)
        self.iou_spin.setSingleStep(0.05)
        self.iou_spin.setValue(0.45)
        self.iou_spin.setFixedWidth(90)
        gp.addLayout(self._spin_row("NMS IoU", self.iou_spin))

        self.imgsz_spin = QSpinBox()
        self.imgsz_spin.setRange(160, 2048)
        self.imgsz_spin.setSingleStep(32)
        self.imgsz_spin.setValue(640)
        self.imgsz_spin.setFixedWidth(90)
        gp.addLayout(self._spin_row("Görsel boyutu (imgsz)", self.imgsz_spin))

        self.maxdet_spin = QSpinBox()
        self.maxdet_spin.setRange(1, 1000)
        self.maxdet_spin.setValue(300)
        self.maxdet_spin.setFixedWidth(90)
        gp.addLayout(self._spin_row("Maks tespit", self.maxdet_spin))

        self.device_combo = QComboBox()
        cihaz_combo_doldur(self.device_combo)
        self.device_combo.setFixedWidth(140)
        gp.addLayout(self._spin_row("Cihaz", self.device_combo))

        self.half_chk = QCheckBox("Yarı hassasiyet (FP16)")
        self.half_chk.setToolTip("Sadece GPU'da işe yarar; CPU'da yok sayılır")
        gp.addWidget(self.half_chk)

        self.agnostic_chk = QCheckBox("Sınıftan bağımsız NMS")
        self.agnostic_chk.setToolTip(
            "Üst üste binen kutular sınıf farkı gözetmeden elenir")
        gp.addWidget(self.agnostic_chk)

        return grp

    def _build_output_group(self) -> QGroupBox:
        """Görünüm ve isteğe bağlı çıktılar.

        Çıktı klasörü seçimi bilerek burada değil, panelin dibindeki
        kaydırmayan şeritte: zorunlu bir alan, katlanabilir bir grubun ya da
        kıvrımın altında kalmamalı.
        """
        grp = QGroupBox("Görünüm ve Ek Çıktılar")
        go = QVBoxLayout(grp)
        go.setSpacing(6)

        self.layout_combo = QComboBox()
        self.layout_combo.addItem("Yan yana (yatay)", False)
        self.layout_combo.addItem("Alt alta (dikey)", True)
        self.layout_combo.setToolTip(
            "Dikey video ya da 3 model kıyaslarken alt alta daha okunaklı olur")
        self.layout_combo.setFixedWidth(160)
        go.addLayout(self._spin_row("Mozaik düzeni", self.layout_combo))

        self.draw_labels_chk = QCheckBox("Kutu üstünde sınıf adı göster")
        self.draw_labels_chk.setChecked(True)
        go.addWidget(self.draw_labels_chk)

        self.draw_conf_chk = QCheckBox("Kutu üstünde güven değeri göster")
        self.draw_conf_chk.setChecked(True)
        go.addWidget(self.draw_conf_chk)

        self.show_preview_chk = QCheckBox("İşlerken önizleme göster")
        self.show_preview_chk.setChecked(True)
        self.show_preview_chk.setToolTip("Kapatmak işlemi hızlandırır")
        go.addWidget(self.show_preview_chk)

        self.write_video_chk = QCheckBox("Karşılaştırma videosunu yaz")
        self.write_video_chk.setChecked(True)
        self.write_video_chk.setToolTip(
            "Kapatırsan sadece canlı önizleme ve rapor üretilir (daha hızlı)")
        self.write_video_chk.toggled.connect(self._on_write_video_toggled)
        go.addWidget(self.write_video_chk)

        self.indiv_chk = QCheckBox("Model başına ayrı video da kaydet")
        self.indiv_chk.setToolTip("karsilastirma.mp4 dışında her model için ayrı bir mp4 yazılır")
        go.addWidget(self.indiv_chk)

        return grp

    def _build_center(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(6)

        self.preview = PreviewLabel()
        v.addWidget(self.preview, 1)

        self.tabs = QTabWidget()
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs.addTab(self.log_box, "Log")
        self.report_box = QTextEdit()
        self.report_box.setReadOnly(True)
        self.report_box.setLineWrapMode(QTextEdit.NoWrap)
        self.report_box.setStyleSheet("font-family:monospace; font-size:11px;")
        self.tabs.addTab(self.report_box, "Karşılaştırma Raporu")
        self.tabs.setMaximumHeight(240)
        v.addWidget(self.tabs)

        h = QHBoxLayout()
        self.save_report_btn = QPushButton("Raporu Kaydet…")
        self.save_report_btn.clicked.connect(self._save_report)
        h.addWidget(self.save_report_btn)
        h.addStretch()
        v.addLayout(h)
        return w

    def _build_menu(self):
        file_m = self.menuBar().addMenu("Dosya")

        def act(label, slot, shortcut=""):
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            file_m.addAction(a)

        act("Video Seç…", self._pick_video, "Ctrl+O")
        act("Çıktı Klasörü…", self._pick_out_dir, "Ctrl+S")
        file_m.addSeparator()
        act("Çıktı Klasörünü Aç", self._open_out_dir)
        file_m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

    # ─────────────────────────────── model yuvaları

    def _tazele_yuvalar(self):
        """Yuva görünürlüğünü ve ekle/kaldır düğmelerini duruma göre ayarla."""
        aktifler = [s for s in self._slot_rows if s["aktif"]]
        for s in self._slot_rows:
            s["group"].setVisible(s["aktif"])
            # Son kalan modeli de kaldırmak karşılaştırmayı boşa düşürür
            s["remove_btn"].setEnabled(len(aktifler) > 1)
        self._add_model_btn.setVisible(len(aktifler) < MAX_MODELS)
        self._update_estimate()

    def _model_ekle(self):
        for s in self._slot_rows:
            if not s["aktif"]:
                s["aktif"] = True
                break
        self._tazele_yuvalar()

    def _model_kaldir(self, idx: int):
        if sum(1 for s in self._slot_rows if s["aktif"]) <= 1:
            return
        slot = self._slot_rows[idx]
        slot["aktif"] = False
        slot["path"] = ""
        slot["names"] = {}
        slot["path_edit"].clear()
        slot["label_edit"].clear()
        slot["info_lbl"].setText("Sınıflar: —")
        slot["class_list"].clear()
        slot["class_list"].setVisible(False)
        slot["sinif_kutu"].setVisible(False)
        slot["sinif_durum"].setText("Model seçilince sınıflar buraya gelir")
        self._tazele_yuvalar()

    def _pick_model(self, idx: int):
        slot = self._slot_rows[idx]
        p, _ = QFileDialog.getOpenFileName(
            self, f"Model {slot['harf']} seç", slot["path"] or "",
            "YOLO modeli (*.pt *.engine *.onnx);;Tüm Dosyalar (*)")
        if not p:
            return
        slot["path"] = p
        slot["path_edit"].setText(p)
        slot["path_edit"].setToolTip(p)
        slot["path_edit"].setCursorPosition(0)
        if not slot["label_edit"].text().strip():
            slot["label_edit"].setText(os.path.splitext(os.path.basename(p))[0])
        self._load_class_names(idx, p)

    def _load_class_names(self, idx: int, path: str):
        """Sınıf adlarını arka planda oku.

        `from ultralytics import YOLO` ilk çağrıda torch'u da yükler; bunu
        arayüz iş parçacığında yapmak pencereyi saniyelerce dondurur.
        """
        slot = self._slot_rows[idx]
        slot["names"] = {}
        slot["class_list"].clear()
        slot["class_list"].setVisible(False)
        slot["sinif_kutu"].setVisible(False)
        slot["info_lbl"].setText("Sınıflar okunuyor…")
        slot["sinif_durum"].setText("Model açılıyor, lütfen bekle…")

        eski = self._sinif_yukleyiciler.pop(idx, None)
        if eski is not None:
            try:
                eski.tamamlandi.disconnect()
            except TypeError:
                pass

        yukleyici = SinifYukleyici(path, self)
        yukleyici.tamamlandi.connect(
            lambda yol, names, hata, i=idx: self._on_class_names(i, yol, names, hata))
        self._sinif_yukleyiciler[idx] = yukleyici
        yukleyici.start()

    def _on_class_names(self, idx: int, yol: str, names: dict, hata: str):
        slot = self._slot_rows[idx]
        yukleyici = self._sinif_yukleyiciler.pop(idx, None)
        if yukleyici is not None:
            yukleyici.deleteLater()
        # Kullanıcı bu arada başka model seçtiyse geç gelen sonucu yut
        if yol != slot["path"]:
            return
        if hata:
            slot["info_lbl"].setText("Sınıflar okunamadı (Başlat'ta tekrar denenecek)")
            slot["sinif_durum"].setText("Filtre uygulanamaz — tüm sınıflar açık sayılır")
            self._log(f"{slot['harf']}: sınıflar okunamadı — {hata}")
            return

        slot["names"] = names
        lst = slot["class_list"]
        lst.blockSignals(True)
        lst.clear()
        for class_id in sorted(names):
            item = QListWidgetItem(f"{class_id}: {names[class_id]}")
            item.setData(Qt.UserRole, int(class_id))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)      # varsayılan: tüm sınıflar açık
            lst.addItem(item)
        lst.blockSignals(False)
        lst.setVisible(bool(names))
        slot["sinif_kutu"].setVisible(bool(names))
        slot["info_lbl"].setText(
            f"{len(names)} sınıf bulundu — kullanılacakları işaretle")
        self._sinif_ozet_tazele(idx)

    def _set_all_classes(self, idx: int, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        class_list = self._slot_rows[idx]["class_list"]
        if not class_list.count():
            return
        class_list.blockSignals(True)
        for row in range(class_list.count()):
            class_list.item(row).setCheckState(state)
        class_list.blockSignals(False)
        self._sinif_ozet_tazele(idx)

    @staticmethod
    def _selected_classes(slot: dict):
        """Seçili sınıf kimlikleri; hepsi açıksa (ya da liste boşsa) None."""
        class_list = slot["class_list"]
        if not class_list.count():
            return None
        secili = [class_list.item(row).data(Qt.UserRole)
                  for row in range(class_list.count())
                  if class_list.item(row).checkState() == Qt.Checked]
        if len(secili) == class_list.count():
            return None                       # filtre yok = hepsi
        return secili

    def _sinif_ozet_tazele(self, idx: int):
        slot = self._slot_rows[idx]
        lst = slot["class_list"]
        if not lst.count():
            slot["sinif_durum"].setText("Model seçilince sınıflar buraya gelir")
            return
        secili = self._selected_classes(slot)
        if secili is None:
            slot["sinif_durum"].setText(f"Tüm sınıflar açık ({lst.count()})")
        elif not secili:
            slot["sinif_durum"].setText(
                "Hiçbir sınıf açık değil — bu model hiçbir şey tespit etmez")
        else:
            adlar = ", ".join(str(slot["names"].get(c, c)) for c in secili)
            slot["sinif_durum"].setText(
                f"{len(secili)}/{lst.count()} sınıf açık: {adlar}")

    # ─────────────────────────────── video / dizin seçimi

    def _pick_video(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Video Seç", "",
            "Video Dosyaları (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v);;"
            "Tüm Dosyalar (*)")
        if not p:
            return
        self._video_path = p
        self.video_edit.setText(p)
        self.video_edit.setToolTip(p)
        self.video_edit.setCursorPosition(0)
        self._probe_video(p)

    def _probe_video(self, path: str):
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                cap.release()
                raise RuntimeError("açılamadı")
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            cap.release()
            dur_ms = int(total / fps * 1000) if fps and total else 0
            self.video_info_lbl.setText(
                f"Süre / fps: {ms_to_str(dur_ms)} , {fps:.3g} fps"
                if dur_ms else f"fps: {fps:.3g} (süre okunamadı)")
            self.end_edit.setText(ms_to_str(dur_ms) if dur_ms else "00:10.000")
            self._video_dur_ms = dur_ms
        except Exception as e:
            self.video_info_lbl.setText(f"Süre / fps: okunamadı ({e})")
            self._video_dur_ms = 0
        self._update_estimate()

    def _on_range_toggled(self, on: bool):
        self.range_kutu.setVisible(on)
        self._update_estimate()

    def _on_write_video_toggled(self, on: bool):
        self.indiv_chk.setEnabled(on)
        if not on:
            self.indiv_chk.setChecked(False)

    def _update_estimate(self):
        dur_ms = self._video_dur_ms
        if self.range_chk.isChecked():
            s = str_to_ms(self.start_edit.text())
            e = str_to_ms(self.end_edit.text())
            span_ms = max(0, e - s) if s >= 0 and e >= 0 else 0
        else:
            span_ms = dur_ms
        fps = self.sample_fps_spin.value()
        if span_ms > 0:
            n = max(1, int(span_ms / 1000.0 * fps))
            model_sayisi = max(1, sum(1 for s in self._slot_rows if s["aktif"]))
            self.estimate_lbl.setText(
                f"Tahmini işlenecek kare: ~{n}  ({n * model_sayisi} çıkarım)")
        else:
            self.estimate_lbl.setText("Tahmini işlenecek kare: — (video/aralık seçilince hesaplanır)")

    def _pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Karşılaştırmanın kaydedileceği klasör", self._out_dir or "")
        if not d:
            return
        self._out_dir = d
        self.out_edit.setText(d)
        self.out_edit.setToolTip(d)
        self.out_edit.setCursorPosition(0)

    def _open_out_dir(self):
        if not self._out_dir:
            self.status.showMessage("Önce çıktı klasörü seç.")
            return
        try:
            from ..klasor_ac import klasoru_ac
            klasoru_ac(self._out_dir)
        except Exception as e:
            self.status.showMessage(f"HATA: klasör açılamadı — {e}")

    def _play_result(self):
        path = os.path.join(self._out_dir, "karsilastirma.mp4") if self._out_dir else ""
        if not path or not os.path.exists(path):
            self.status.showMessage("Sonuç videosu henüz yok.")
            return
        try:
            from ..klasor_ac import klasoru_ac
            klasoru_ac(path)
        except Exception as e:
            self.status.showMessage(f"HATA: video açılamadı — {e}")

    # ─────────────────────────────── log

    def _log(self, text: str):
        self.log_box.append(text)

    # ─────────────────────────────── çalıştırma

    def _active_slots(self):
        """Açık yuvalar.

        Görünürlük değil açıklık bayrağı kullanılır: araç Boxify kabuğuna
        gömülü çalışırken sayfa öndeki sekme değilse isVisible() False döner.
        """
        return [s for s in self._slot_rows if s["aktif"]]

    def _start(self):
        if self._worker:
            return
        if not self._video_path or not os.path.exists(self._video_path):
            QMessageBox.warning(self, "Video yok", "Geçerli bir video seç.")
            return

        acik = self._active_slots()
        active = [s for s in acik if s["path"] and os.path.exists(s["path"])]
        eksik = [s for s in acik if s["path"] and not os.path.exists(s["path"])]
        if len(active) < 1:
            QMessageBox.warning(self, "Yetersiz model",
                                "En az bir geçerli model seçmelisin.")
            return
        if eksik:
            harfler = ", ".join(s["harf"] for s in eksik)
            QMessageBox.warning(
                self, "Model eksik",
                f"Model {harfler} dosyası artık bulunamıyor; yeniden seç.")
            return

        sinifsiz = [s["harf"] for s in active
                    if s["class_list"].count() and self._selected_classes(s) == []]
        if sinifsiz:
            QMessageBox.warning(
                self, "Sınıf seçilmedi",
                "Model " + ", ".join(sinifsiz)
                + " için en az bir sınıfı aç veya 'Tüm sınıflar'ı seç.")
            return

        if not self._out_dir:
            QMessageBox.warning(self, "Çıktı klasörü yok",
                                "Karşılaştırmanın kaydedileceği klasörü seç.")
            return

        start_ms = end_ms = None
        range_text = "tüm video"
        if self.range_chk.isChecked():
            s = str_to_ms(self.start_edit.text())
            e = str_to_ms(self.end_edit.text())
            if s < 0 or e < 0 or e <= s:
                QMessageBox.warning(self, "Aralık hatalı",
                                    "Başlangıç/bitiş zamanı geçersiz (format dd:ss.ms).")
                return
            start_ms, end_ms = s, e
            range_text = f"{ms_to_str(s)} → {ms_to_str(e)}"

        ortak = {
            "conf": float(self.conf_spin.value()),
            "iou": float(self.iou_spin.value()),
            "imgsz": int(self.imgsz_spin.value()),
            "max_det": int(self.maxdet_spin.value()),
        }

        raw_labels = [s["label_edit"].text().strip() or f"Model {s['harf']}" for s in active]
        labels = unique_labels(raw_labels)
        models_cfg = []
        for s, lbl in zip(active, labels):
            ozel = s["ozel_chk"].isChecked()
            models_cfg.append({
                "path": s["path"], "label": lbl, "color": s["renk"],
                "classes": self._selected_classes(s), "ozel": ozel,
                "conf": float(s["conf"].value()) if ozel else ortak["conf"],
                "iou": float(s["iou"].value()) if ozel else ortak["iou"],
                "imgsz": int(s["imgsz"].value()) if ozel else ortak["imgsz"],
                "max_det": int(s["max_det"].value()) if ozel else ortak["max_det"],
            })

        cfg = {
            "video_path": self._video_path,
            "start_ms": start_ms, "end_ms": end_ms,
            "range_text": range_text,
            "sample_fps": self.sample_fps_spin.value(),
            "panel_h": self.panel_h_spin.value(),
            "models": models_cfg,
            "device": self.device_combo.currentData(),
            "device_text": self.device_combo.currentText(),
            "half": self.half_chk.isChecked(),
            "agnostic_nms": self.agnostic_chk.isChecked(),
            "dikey": bool(self.layout_combo.currentData()),
            "draw_labels": self.draw_labels_chk.isChecked(),
            "draw_conf": self.draw_conf_chk.isChecked(),
            "show_preview": self.show_preview_chk.isChecked(),
            "write_video": self.write_video_chk.isChecked(),
            "out_dir": self._out_dir,
            "save_individual": self.indiv_chk.isChecked() and self.write_video_chk.isChecked(),
            **ortak,
        }

        self.log_box.clear()
        self.report_box.clear()
        self._log(f"Video: {os.path.basename(self._video_path)}  ({range_text})")
        for m in models_cfg:
            satir = f"• {m['label']} ({os.path.basename(m['path'])})"
            if m["ozel"]:
                satir += (f" — özel ayar: conf={m['conf']:.2f} iou={m['iou']:.2f} "
                          f"imgsz={m['imgsz']} maks={m['max_det']}")
            if m["classes"] is not None:
                satir += f" — sınıf filtresi: {len(m['classes'])} sınıf açık"
            self._log(satir)
        self._log(f"Örnekleme: {cfg['sample_fps']:g} fps, panel yüksekliği: {cfg['panel_h']} px")

        self._worker = CompareWorker(cfg)
        self._worker.models_ready.connect(self._on_models_ready)
        self._worker.preview.connect(self.preview.set_image)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._log)
        self._worker.failed.connect(self._on_failed)
        self._worker.summary.connect(self._on_summary)
        self._worker.finished.connect(self._on_worker_finished)

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.play_btn.setEnabled(False)
        self.progress.setValue(0)
        self._worker.start()

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.status.showMessage("İptal isteniyor… (işlenen kare bitince duracak)")

    def _on_models_ready(self, names_by_label: dict):
        for label, names in names_by_label.items():
            self._log(f"{label} hazır — " + sinif_ozeti(names))

    def _on_progress(self, done: int, total: int):
        if total > 0:
            self.progress.setRange(0, total)
            self.progress.setValue(done)
        else:
            self.progress.setRange(0, 0)      # belirsiz ilerleme
        self.status.showMessage(f"İşleniyor: {done}" + (f"/{total}" if total else ""))

    def _on_failed(self, msg: str):
        self._log("HATA: " + msg)
        QMessageBox.critical(self, "Hata", msg)

    def _build_report(self, summary: dict, cfg: dict) -> str:
        L = ["═══ MODEL KARŞILAŞTIRMA RAPORU ═══",
             f"Video: {os.path.basename(cfg['video_path'])}   ({cfg['range_text']})",
             f"Örnekleme: {cfg['sample_fps']:g} fps    Panel yüksekliği: {cfg['panel_h']} px    "
             f"İşlenen kare: {cfg['islenen_kare']}" + ("  (iptal edildi)" if cfg["iptal"] else ""),
             f"Ortak ayar: conf={cfg['conf']:.2f}  iou={cfg['iou']:.2f}  "
             f"imgsz={cfg['imgsz']}  cihaz={cfg['device_text']}"
             + ("  FP16" if cfg["half"] else "")
             + ("  sınıftan-bağımsız-NMS" if cfg["agnostic_nms"] else ""),
             ""]

        labels = list(summary.keys())
        L.append(f"{'model':<16s}{'kare':>7s}{'tespit':>8s}{'kare/tespit':>12s}"
                 f"{'ort.güven':>10s}{'boş kare %':>11s}{'ort.süre(ms)':>13s}{'fps':>7s}")
        for lbl in labels:
            s = summary[lbl]
            L.append(f"{lbl[:15]:<16s}{s['kare']:>7d}{s['tespit']:>8d}"
                     f"{s['kare_basi']:>12.2f}{s['ort_conf']:>10.2f}"
                     f"{s['bos_oran'] * 100:>11.1f}"
                     f"{s['ort_ms']:>13.1f}{s['fps']:>7.1f}")
        L.append("")

        # Modele özel ayar varsa kıyas artık "aynı koşul" değildir; raporda dursun
        L.append("── Model ayarları ──")
        for lbl in labels:
            a = summary[lbl]["ayar"]
            satir = (f"{lbl}: [{'özel' if a['ozel'] else 'ortak'}] "
                     f"conf={a['conf']:.2f} iou={a['iou']:.2f} "
                     f"imgsz={a['imgsz']} maks={a['max_det']}")
            if a["classes"] is None:
                satir += "  |  sınıf filtresi: yok (hepsi açık)"
            else:
                satir += "  |  açık sınıflar: " + (", ".join(a["classes"]) or "(hiçbiri)")
            if summary[lbl]["hata"]:
                satir += f"  |  {summary[lbl]['hata']} karede çıkarım hatası"
            L.append(satir)
        if any(summary[l]["ayar"]["ozel"] for l in labels):
            L.append("  ! En az bir model özel ayarla koştu — sayılar birebir "
                     "aynı koşulun kıyası değildir.")
        L.append("")

        if len(labels) >= 2:
            en_cok = max(labels, key=lambda l: summary[l]["tespit"])
            en_hizli = max(labels, key=lambda l: summary[l]["fps"])
            en_guven = max(labels, key=lambda l: summary[l]["ort_conf"])
            L.append("── Öne çıkanlar ──")
            L.append(f"En çok tespit eden      : {en_cok}  ({summary[en_cok]['tespit']})")
            L.append(f"En hızlı                : {en_hizli}  (~{summary[en_hizli]['fps']:.1f} fps)")
            L.append(f"En yüksek ortalama güven: {en_guven}  ({summary[en_guven]['ort_conf']:.2f})")
            L.append("")

            # Farklı sınıf kümeleri toplam tespit kıyasını yanıltır — açıkça söyle
            kumeler = {l: set(summary[l]["model_siniflari"].values()) for l in labels}
            if len(set(map(frozenset, kumeler.values()))) > 1:
                ortak_k = set.intersection(*kumeler.values())
                L.append("── Sınıf kümeleri farklı ──")
                for lbl in labels:
                    farkli = kumeler[lbl] - ortak_k
                    L.append(f"{lbl}: {len(kumeler[lbl])} sınıf"
                             + (f"  (sadece bunda: {', '.join(sorted(farkli))})" if farkli else ""))
                L.append(f"Ortak sınıflar: {', '.join(sorted(ortak_k)) or '(yok)'}")
                L.append("  ! Modeller aynı sınıfları tanımıyor; toplam tespit "
                         "sayılarını doğrudan kıyaslamak yanıltıcı olabilir.")
                L.append("")
        else:
            L.append("(Tek model çalıştırıldı — bu bir kıyas değil, tek modelin dökümü.)")
            L.append("")

        L.append("── Sınıf dağılımı ──")
        for lbl in labels:
            sinif = summary[lbl]["sinif"]
            parca = (", ".join(f"{k}: {v}" for k, v in
                               sorted(sinif.items(), key=lambda kv: -kv[1]))
                     if sinif else "(tespit yok)")
            L.append(f"{lbl}: {parca}")
        L.append("")

        L.append(f"Çıktı: {cfg['combined_path'] or '(video yazılmadı)'}")
        L.append("(Not: tüm modeller kıyasın adil olması için birebir aynı ölçeklenmiş "
                 "kareyi görür; imgsz sadece modelin iç çıkarım çözünürlüğüdür. "
                 "Örnekleme fps'i düşükse hız rakamları kabaca ipucu niteliğindedir.)")
        return "\n".join(L)

    def _on_summary(self, summary: dict, cfg: dict):
        self.report_box.setPlainText(self._build_report(summary, cfg))
        self.tabs.setCurrentIndex(1)

        # Tek bir kare bile üretemeyen model, "0 tespit" satırıyla sanki bir
        # sonuç vermiş gibi görünür; sebebi (yanlış cihaz, bozuk ağırlık…)
        # yalnızca log sekmesinde kalmasın
        colu = [lbl for lbl, s in summary.items() if s["kare"] == 0 and s["hata"]]
        if colu:
            QMessageBox.warning(
                self, "Model çalışmadı",
                "Şu model(ler) hiçbir karede çıkarım yapamadı:\n  "
                + "\n  ".join(colu)
                + "\n\nSebebi Log sekmesinde yazıyor (sık görülen neden: "
                  "bu makinede olmayan bir cihazın seçilmesi).")
        toplamlar = ", ".join(f"{lbl}: {s['tespit']}" for lbl, s in summary.items())
        self.stats_lbl.setText(
            f"İşlenen {cfg['islenen_kare']} kare | tespitler → {toplamlar}")
        self.status.showMessage("Bitti. " + self.stats_lbl.text())
        self.play_btn.setEnabled(bool(cfg["combined_path"])
                                 and os.path.exists(cfg["combined_path"]))

    def _save_report(self):
        text = self.report_box.toPlainText()
        if not text:
            self.status.showMessage("Önce bir karşılaştırma çalıştır.")
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "Raporu kaydet",
            os.path.join(self._out_dir or "", "karsilastirma_raporu.txt"),
            "Metin (*.txt)")
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            self.status.showMessage(f"Kaydedildi: {p}")
        except OSError as e:
            QMessageBox.critical(self, "Hata", f"Kaydedilemedi:\n{e}")

    def _on_worker_finished(self):
        self._worker = None
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setRange(0, 100)

    def closeEvent(self, ev):
        if self._worker:
            self._worker.cancel()
            self._worker.wait(5000)
        for yukleyici in list(self._sinif_yukleyiciler.values()):
            yukleyici.wait(3000)
        self._sinif_yukleyiciler.clear()
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
    app.setApplicationName("Model Karşılaştır")
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
