import os
from PyQt5.QtWidgets import (QMainWindow, QWidget, QSplitter, QListWidget,
                              QListWidgetItem, QVBoxLayout, QHBoxLayout,
                              QPushButton, QLabel, QFileDialog, QStatusBar,
                              QMessageBox, QFrame, QAction, QShortcut,
                              QInputDialog, QApplication)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QColor, QKeySequence, QIcon, QPixmap

from ..core.dataset import Dataset
from ..core.annotation import BBox
from .canvas import Canvas
from .label_panel import LabelPanel, DEFAULT_COLORS
from .sinif_popup import SinifPopup
from .kucuk_resim import KucukResimIscisi, KUCUK
from .training_dialog import TrainingDialog


GERI_AL_SINIRI = 100   # kare başına saklanan anlık görüntü sayısı


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dataset = Dataset()
        self.setWindowTitle("YOLOLabel")
        self.setMinimumSize(1200, 720)
        # Geri al/yinele yığınları kare başınadır: başka kareye geçince
        # temizlenir. Kareler arası geri alma, diske çoktan yazılmış başka
        # dosyaları da geri sarmak anlamına gelirdi.
        self._geri_yigin = []
        self._yinele_yigin = []
        # Son kullanılan sınıf: yeni kutular bununla gelir, her kutuda
        # yeniden seçmek gerekmesin.
        self._yapiskan_sinif = 0
        self._atanmamis = -1   # sınıfı henüz atanmamış taze kutunun indeksi
        self._izgara = True
        self._kucuk_isci = None
        self._kucuk_onbellek = {}
        self._build_ui()
        self._build_menu()
        self._build_shortcuts()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Horizontal)

        splitter.addWidget(self._build_image_list())
        splitter.addWidget(self._build_canvas_area())

        self.label_panel = LabelPanel()
        self.label_panel.class_added.connect(self._on_class_added)
        self.label_panel.class_removed.connect(self._on_class_removed)
        self.label_panel.class_selected.connect(self._on_class_selected)
        self.label_panel.class_renamed.connect(self._on_class_renamed)
        self.label_panel.class_recolored.connect(self._on_class_recolored)
        splitter.addWidget(self.label_panel)

        # Sol sütun küçük resim ızgarasının iki sütununa göre: 2×104 + boşluklar.
        splitter.setSizes([248, 772, 200])
        vbox.addWidget(splitter)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Hoş geldiniz — Dosya > Klasör Aç ile başlayın")

    def _build_toolbar(self) -> QFrame:
        bar = QFrame()
        bar.setFixedHeight(46)
        bar.setStyleSheet("background:#eceff3; border-bottom:1px solid #c9d1da;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)

        def btn(text, slot, tip="", color=""):
            b = QPushButton(text)
            if tip:
                b.setToolTip(tip)
            if color:
                b.setStyleSheet(f"background:{color}; color:#f5f8fb; font-weight:bold; padding:5px 14px;")
            b.clicked.connect(slot)
            return b

        row.addWidget(btn("Klasör Aç", self._open_folder, "Ctrl+O"))
        row.addWidget(btn("Kaydet", self._save_current, "Ctrl+S"))
        row.addWidget(btn("Tümünü Kaydet", self._save_all, "Ctrl+Shift+S"))
        row.addStretch()

        self.prev_btn = btn("◀  Önceki", self._prev)
        self.prev_btn.setEnabled(False)
        row.addWidget(self.prev_btn)

        self.nav_lbl = QLabel("—")
        self.nav_lbl.setAlignment(Qt.AlignCenter)
        self.nav_lbl.setMinimumWidth(90)
        self.nav_lbl.setStyleSheet("color:#3d4756; font-size:13px;")
        row.addWidget(self.nav_lbl)

        self.next_btn = btn("Sonraki  ▶", self._next)
        self.next_btn.setEnabled(False)
        row.addWidget(self.next_btn)

        self.zoom_lbl = QLabel("%100")
        self.zoom_lbl.setFixedWidth(52)
        self.zoom_lbl.setAlignment(Qt.AlignCenter)
        self.zoom_lbl.setStyleSheet("color:#6b7686; font-size:12px;")
        row.addWidget(self.zoom_lbl)

        row.addStretch()
        row.addWidget(btn("  Eğitimi Başlat  ", self._open_training, color="#2e6da4"))

        return bar

    def _build_rail(self) -> QFrame:
        """Dikey araç rayı.

        Bu düğmeler önce üst bardaydı; on bir denetim tek sıraya dizilince
        "Kaydet" ile "Kutuları Taşı" aynı görsel ağırlığa sahip oluyordu —
        oysa biri geri alınabilir, diğeri sekiz kareye birden yazıyor. Rayda
        eylemler gruplanıyor ve yıkıcı olan en altta, ayrı duruyor.
        """
        ray = QFrame()
        ray.setFixedWidth(132)
        ray.setStyleSheet("background:#eceff3; border-left:1px solid #c9d1da;")
        v = QVBoxLayout(ray)
        v.setContentsMargins(8, 10, 8, 10)
        v.setSpacing(4)
        v.setAlignment(Qt.AlignTop)

        baslik = QLabel("ARAÇLAR")
        baslik.setStyleSheet("color:#6b7686; font-size:10px; letter-spacing:1px;")
        v.addWidget(baslik)

        def arac(glif, metin, slot, tip=""):
            b = QPushButton(f"{glif}   {metin}")
            b.setToolTip(tip or metin)
            b.setMinimumHeight(32)
            b.setStyleSheet("text-align:left; padding:5px 8px;")
            b.clicked.connect(slot)
            v.addWidget(b)
            return b

        def ayirici():
            c = QFrame()
            c.setFrameShape(QFrame.HLine)
            c.setStyleSheet("color:#c9d1da;")
            v.addWidget(c)

        self.geri_btn = arac("↺", "Geri Al", self._geri_al, "Geri al (Ctrl+Z)")
        self.yinele_btn = arac("↻", "Yinele", self._yinele, "Yinele (Ctrl+Y)")
        self.geri_btn.setEnabled(False)
        self.yinele_btn.setEnabled(False)

        ayirici()
        arac("⊕", "Yakınlaştır", lambda: self.canvas.zoom_step(1.25),
             "Yakınlaştır (Ctrl++ veya fare tekerleği)")
        arac("⊖", "Uzaklaştır", lambda: self.canvas.zoom_step(1 / 1.25),
             "Uzaklaştır (Ctrl+- veya fare tekerleği)")
        arac("⤢", "Sığdır", lambda: self.canvas.reset_zoom(),
             "Sığdır (Ctrl+0). Yakınlaşmışken sağ tuşla sürükleyerek kaydır.")

        ayirici()
        arac("⇥", "Kutuları Taşı", self._kutulari_tasi,
             "Bu karedeki kutuları sonraki karelere taşır (optik akışla takip)")

        v.addStretch()
        sil = arac("⌫", "Görseli Sil", self._gorseli_sil,
                   "Bu görseli ve etiketini veri setinden siler")
        sil.setStyleSheet("text-align:left; padding:5px 8px; color:#8c3b3b;")
        return ray

    def _build_image_list(self) -> QWidget:
        w = QWidget()
        w.setMaximumWidth(260)
        w.setMinimumWidth(170)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(4, 6, 4, 4)
        vbox.setSpacing(4)

        ust = QHBoxLayout()
        lbl = QLabel("Resimler")
        lbl.setStyleSheet("font-weight:bold; font-size:13px; padding:2px 4px;")
        ust.addWidget(lbl)
        ust.addStretch()
        self.izgara_btn = QPushButton("☰")
        self.izgara_btn.setCheckable(True)
        self.izgara_btn.setChecked(True)
        self.izgara_btn.setFixedSize(28, 24)
        self.izgara_btn.setStyleSheet("padding:0; font-size:13px;")
        self.izgara_btn.setToolTip("Izgara / liste görünümü")
        self.izgara_btn.clicked.connect(self._gorunumu_degistir)
        ust.addWidget(self.izgara_btn)
        vbox.addLayout(ust)

        self.img_list = QListWidget()
        self.img_list.currentRowChanged.connect(self._on_image_row_changed)
        vbox.addWidget(self.img_list)
        self._izgara_uygula(True)

        self.labeled_lbl = QLabel("Etiketli: 0 / 0")
        self.labeled_lbl.setStyleSheet("color:#6b7686; font-size:11px; padding:2px 4px;")
        vbox.addWidget(self.labeled_lbl)

        return w

    # ------------------------------------------------------------------ küçük resimler

    def _izgara_uygula(self, izgara: bool):
        """Listeyi ızgara ya da düz metin kipine al."""
        self._izgara = izgara
        lw = self.img_list
        if izgara:
            lw.setViewMode(QListWidget.IconMode)
            lw.setIconSize(KUCUK)
            lw.setGridSize(QSize(KUCUK.width() + 14, KUCUK.height() + 30))
            lw.setResizeMode(QListWidget.Adjust)
            lw.setMovement(QListWidget.Static)
            lw.setWordWrap(False)
            lw.setSpacing(3)
        else:
            lw.setViewMode(QListWidget.ListMode)
            lw.setIconSize(QSize(0, 0))
            lw.setGridSize(QSize())
            lw.setSpacing(0)

    def _gorunumu_degistir(self):
        self._izgara_uygula(self.izgara_btn.isChecked())
        self._refresh_list()
        if self._izgara and not self._kucuk_onbellek:
            self._kucuk_resimleri_baslat()

    def _kucuk_resimleri_baslat(self):
        """Görünen klasör için küçük resim üretimini (yeniden) başlat."""
        self._kucuk_durdur()
        self._kucuk_onbellek = {}
        if not (self._izgara and self.dataset.images):
            return
        self._kucuk_isci = KucukResimIscisi(
            [a.image_path for a in self.dataset.images], self)
        self._kucuk_isci.hazir.connect(self._kucuk_hazir)
        self._kucuk_isci.start()

    def _kucuk_durdur(self):
        isci = getattr(self, "_kucuk_isci", None)
        if isci is not None:
            isci.durdur()
            isci.wait(1500)
        self._kucuk_isci = None

    def _kucuk_hazir(self, idx: int, img):
        if idx >= len(self.dataset.images):
            return
        ikon = QIcon(QPixmap.fromImage(img))
        self._kucuk_onbellek[self.dataset.images[idx].image_path] = ikon
        if idx < self.img_list.count():
            self.img_list.item(idx).setIcon(ikon)

    def _build_canvas_area(self) -> QWidget:
        w = QWidget()
        hbox = QHBoxLayout(w)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)

        self.canvas = Canvas()
        self.canvas.bbox_added.connect(self._on_bbox_added)
        self.canvas.bbox_deleted.connect(self._on_bbox_deleted)
        self.canvas.bbox_class_changed.connect(self._on_bbox_class_changed)
        self.canvas.bbox_modified.connect(self._update_status)
        self.canvas.bbox_degisecek.connect(self._anlik_al)
        self.canvas.zoom_degisti.connect(self._on_zoom_changed)
        self.canvas.secim_degisti.connect(self._on_secim_degisti)
        hbox.addWidget(self.canvas, 1)

        # Sınıf paneli tuvalin çocuğu: kutunun yanında yüzmesi gerekiyor.
        self.popup = SinifPopup(self.canvas)
        self.popup.uygulandi.connect(self._popup_uygula)
        self.popup.silindi.connect(self._popup_sil)
        self.popup.kapatildi.connect(self._popup_kapat)

        hbox.addWidget(self._build_rail())
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

        act("Klasör Aç", self._open_folder, "Ctrl+O")
        act("Kaydet", self._save_current, "Ctrl+S")
        act("Tümünü Kaydet", self._save_all, "Ctrl+Shift+S")
        file_m.addSeparator()
        act("Eğitim Başlat...", self._open_training)
        file_m.addSeparator()
        act("Çıkış", self.close, "Ctrl+Q")

        duzen_m = mb.addMenu("Düzen")

        def duzen_act(label, slot, shortcut=""):
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            duzen_m.addAction(a)

        duzen_act("Geri Al", self._geri_al, "Ctrl+Z")
        duzen_act("Yinele", self._yinele, "Ctrl+Y")
        duzen_m.addSeparator()
        duzen_act("Yakınlaştır", lambda: self.canvas.zoom_step(1.25), "Ctrl+=")
        duzen_act("Uzaklaştır", lambda: self.canvas.zoom_step(1 / 1.25), "Ctrl+-")
        duzen_act("Sığdır", lambda: self.canvas.reset_zoom(), "Ctrl+0")

    def _build_shortcuts(self):
        for key in (Qt.Key_Left, Qt.Key_A):
            QShortcut(QKeySequence(key), self, self._prev)
        for key in (Qt.Key_Right, Qt.Key_D):
            QShortcut(QKeySequence(key), self, self._next)
        # Menü Ctrl+= veriyor; klavyede fiilen Ctrl++ da denendiği için ikisi de.
        QShortcut(QKeySequence("Ctrl++"), self, lambda: self.canvas.zoom_step(1.25))
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self._yinele)
        # 1-9: sınıf seç / seçili kutunun sınıfını değiştir
        for i in range(9):
            QShortcut(QKeySequence(str(i + 1)), self,
                      lambda no=i: self._sinif_sec(no))
        for tus in (Qt.Key_Return, Qt.Key_Enter):
            QShortcut(QKeySequence(tus), self, self.popup.onayla)

    # ------------------------------------------------------------------ slots

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Resim Klasörü Seç")
        if not folder:
            return
        self._autosave()
        self.dataset.load_folder(folder)
        self.dataset.load_classes()
        if not self.dataset.label_classes:
            self.dataset.auto_detect_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        self._refresh_list()
        self._kucuk_resimleri_baslat()
        if self.dataset.images:
            self._load(0)
        self.setWindowTitle(f"YOLOLabel — {os.path.basename(folder)}")
        msg = f"{len(self.dataset.images)} resim yüklendi"
        if self.dataset.label_classes:
            msg += f" | Sınıflar: {', '.join(lc.name for lc in self.dataset.label_classes)}"
        self.status.showMessage(msg)

    def _load(self, idx: int):
        self._autosave()
        self.dataset.current_index = idx
        ann = self.dataset.current_image
        if ann is None:
            return

        pix = QPixmap(ann.image_path)
        if pix.isNull():
            self.status.showMessage(f"Yüklenemedi: {ann.image_path}")
            return

        ann.img_width = pix.width()
        ann.img_height = pix.height()
        ann.load()

        self.canvas.set_image(pix)
        self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
        self.canvas.set_current_class(self._yapiskan_sinif)
        self.popup.hide()
        self._atanmamis = -1
        self._yiginlari_temizle()

        self.img_list.blockSignals(True)
        self.img_list.setCurrentRow(idx)
        self.img_list.blockSignals(False)

        self._update_nav()
        self._update_list_item(idx)
        self._update_status()

    # ------------------------------------------------------------------ geri al / yinele

    def _anlik(self):
        """Bu karedeki kutuların kopyası — yığına konulacak anlık görüntü."""
        ann = self.dataset.current_image
        if ann is None:
            return []
        return [BBox(b.x1, b.y1, b.x2, b.y2, b.class_id) for b in ann.bboxes]

    def _anlik_al(self):
        """Değiştirmeden **önce** çağrılır: mevcut hâli geri al yığınına koyar."""
        if self.dataset.current_image is None:
            return
        self._geri_yigin.append(self._anlik())
        del self._geri_yigin[:-GERI_AL_SINIRI]
        self._yinele_yigin.clear()
        self._update_undo_buttons()

    def _yiginlari_temizle(self):
        self._geri_yigin.clear()
        self._yinele_yigin.clear()
        self._update_undo_buttons()

    def _update_undo_buttons(self):
        self.geri_btn.setEnabled(bool(self._geri_yigin))
        self.yinele_btn.setEnabled(bool(self._yinele_yigin))

    def _uygula(self, kutular):
        ann = self.dataset.current_image
        if ann is None:
            return
        ann.bboxes = kutular
        self.canvas._selected = -1
        self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
        self._update_status()
        self._update_undo_buttons()

    def _geri_al(self):
        if not self._geri_yigin:
            self.status.showMessage("Geri alınacak bir değişiklik yok.")
            return
        self._yinele_yigin.append(self._anlik())
        self._uygula(self._geri_yigin.pop())

    def _yinele(self):
        if not self._yinele_yigin:
            self.status.showMessage("Yinelenecek bir değişiklik yok.")
            return
        self._geri_yigin.append(self._anlik())
        self._uygula(self._yinele_yigin.pop())

    def _on_zoom_changed(self, oran: float):
        self.zoom_lbl.setText(f"%{oran * 100:.0f}")
        self._popup_konumla()

    # ------------------------------------------------------------------ inline sınıf paneli

    def _sinif_adlari(self):
        return [lc.name for lc in self.dataset.label_classes]

    def _popup_goster(self, idx: int, odak: bool = False):
        """Paneli seçili kutunun yanında aç."""
        ann = self.dataset.current_image
        if ann is None or not (0 <= idx < len(ann.bboxes)):
            self.popup.hide()
            return
        cid = ann.bboxes[idx].class_id
        adlar = self._sinif_adlari()
        ad = adlar[cid] if 0 <= cid < len(adlar) else ""
        # Sınıf hiç yoksa atama zorunlu; imleç alana kendiliğinden gitsin.
        self.popup.goster(adlar, ad, odak or not adlar)
        self._popup_konumla()

    def _popup_konumla(self):
        if not self.popup.isVisible():
            return
        r = self.canvas.secili_rect()
        if r is None:
            self.popup.hide()
            return
        pw, ph = self.popup.width(), self.popup.sizeHint().height()
        x = r.right() + 10
        if x + pw > self.canvas.width():          # sağa sığmıyorsa sola al
            x = r.left() - pw - 10
        y = r.top()
        x = max(4, min(x, self.canvas.width() - pw - 4))
        y = max(4, min(y, self.canvas.height() - ph - 4))
        self.popup.move(int(x), int(y))

    def _on_secim_degisti(self, idx: int):
        if idx < 0:
            self.popup.hide()
        else:
            self._popup_goster(idx)

    def _popup_uygula(self, ad: str):
        """Panelden gelen sınıf adını uygula; yoksa sınıfı o anda yarat."""
        ann = self.dataset.current_image
        idx = self.canvas._selected
        if ann is None or not (0 <= idx < len(ann.bboxes)):
            self.popup.hide()
            return

        adlar = self._sinif_adlari()
        if ad in adlar:
            cid = adlar.index(ad)
        else:
            renkler = DEFAULT_COLORS
            self.dataset.add_class(ad, renkler[len(adlar) % len(renkler)])
            self.dataset.save_classes()
            self.label_panel.refresh(self.dataset.label_classes)
            cid = len(self.dataset.label_classes) - 1
            self.status.showMessage(f"Yeni sınıf eklendi: {ad}")

        self._anlik_al()
        ann.bboxes[idx].class_id = cid
        self._yapiskan_sinif = cid          # sonraki kutular da bununla gelsin
        self.label_panel.current_class_id = cid
        self.label_panel.list_w.setCurrentRow(cid)
        self.canvas.set_current_class(cid)
        self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
        self.popup.hide()
        self.canvas.setFocus()
        self._update_status()

    def _popup_sil(self):
        idx = self.canvas._selected
        self.popup.hide()
        if idx >= 0:
            self.canvas.sec(-1)
            self._on_bbox_deleted(idx)

    def _popup_kapat(self):
        """Panel kapatıldı. Sınıfsız kalan taze kutu bir işe yaramaz — silinir."""
        idx = self.canvas._selected
        self.popup.hide()
        self.canvas.setFocus()
        if self._atanmamis == idx and idx >= 0:
            self.canvas.sec(-1)
            self._on_bbox_deleted(idx)
        self._atanmamis = -1

    # ------------------------------------------------------------------ sınıf kısayolları

    def _sinif_sec(self, no: int):
        """1-9: sınıfı seç; bir kutu seçiliyse o kutunun sınıfını değiştir."""
        if no >= len(self.dataset.label_classes):
            return
        idx = self.canvas._selected
        ann = self.dataset.current_image
        if ann is not None and 0 <= idx < len(ann.bboxes):
            self._on_bbox_class_changed(idx, no)
        self._yapiskan_sinif = no
        self.label_panel.current_class_id = no
        self.label_panel.list_w.setCurrentRow(no)
        self.canvas.set_current_class(no)
        if self.popup.isVisible():
            self._popup_goster(idx)

    # ------------------------------------------------------------------ görsel silme

    def _gorseli_sil(self):
        ann = self.dataset.current_image
        if ann is None:
            return
        ad = os.path.basename(ann.image_path)
        if QMessageBox.question(
                self, "Görseli sil",
                f"{ad}\n\nBu görsel ve etiketi diskten kalıcı olarak silinecek. "
                f"Geri alınamaz — devam edilsin mi?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return

        idx = self.dataset.current_index
        etiket = ann.label_path()
        silinen = []
        for yol in (ann.image_path, etiket):
            try:
                if yol and os.path.exists(yol):
                    os.remove(yol)
                    silinen.append(os.path.basename(yol))
            except OSError as e:
                QMessageBox.warning(self, "Silinemedi", f"{yol}\n{e}")
                return

        self.dataset.images.pop(idx)
        self._yiginlari_temizle()
        self._refresh_list()
        if self.dataset.images:
            self._load(min(idx, len(self.dataset.images) - 1))
        else:
            self.dataset.current_index = 0
            self.canvas.set_image(QPixmap())
            self.canvas.set_annotations([], self.dataset.label_classes)
            self._update_nav()
        self.status.showMessage("Silindi: " + ", ".join(silinen))

    # ------------------------------------------------------------------ kayıt

    def _autosave(self):
        ann = self.dataset.current_image
        if ann and ann.img_width > 0:
            ann.save()
            self._update_list_item(self.dataset.current_index)

    def _save_current(self):
        self._autosave()
        self._refresh_labeled_count()
        self.status.showMessage("Kaydedildi.")

    def _save_all(self):
        n = 0
        for ann in self.dataset.images:
            if ann.img_width > 0:
                ann.save()
                n += 1
        self._refresh_list()
        self.status.showMessage(f"{n} dosya kaydedildi.")

    def _prev(self):
        if self.dataset.current_index > 0:
            self._load(self.dataset.current_index - 1)

    def _next(self):
        if self.dataset.current_index < len(self.dataset.images) - 1:
            self._load(self.dataset.current_index + 1)

    def _kutulari_tasi(self):
        """Bu karedeki kutuları sonraki N kareye taşı.

        Güvenlik kuralı: yalnızca **hiç kutusu olmayan** karelere yazılır.
        Takip bir tahmindir; kullanıcının elle çizdiği bir kutunun üstüne
        yazmak, yaptığı işi sessizce bozmak olurdu. Zincir, kutusu olan bir
        kareye gelince orada durur.
        """
        from ..core.takip import KutuZinciri

        ann = self.dataset.current_image
        if ann is None or not ann.bboxes:
            QMessageBox.information(
                self, "Kutu yok",
                "Önce bu karede en az bir kutu çiz; taşınacak kutu yok.")
            return

        kalan = len(self.dataset.images) - self.dataset.current_index - 1
        if kalan <= 0:
            QMessageBox.information(self, "Sonraki kare yok",
                                    "Bu son kare; taşınacak yer yok.")
            return

        # Varsayılan 8: gerçek fabrika görüntüsünde ölçüldüğünde kutu ilk
        # ~10 karede nesnenin üstünde kalıyor, sonra kaymaya başlıyor. Zincir
        # zaten kayınca kendiliğinden duruyor ama cömert bir varsayılan
        # vermek, insanı gözden geçirmeden güvenmeye iter.
        adet, tamam = QInputDialog.getInt(
            self, "Kutuları Taşı",
            f"Kaç kareye taşınsın?  (sonrasında {kalan} kare var)\n\n"
            f"Yalnızca hiç kutusu olmayan karelere yazılır; kutusu olan bir\n"
            f"kareye gelinince zincir durur.\n"
            f"Kutu nesneden kaymaya başlarsa zincir kendiliğinden kesilir —\n"
            f"yine de taşınanları gözden geçir.",
            min(8, kalan), 1, kalan)
        if not tamam:
            return

        try:
            import cv2
            import numpy as np
        except ImportError as e:
            QMessageBox.critical(self, "opencv gerekli",
                                 f"Takip için opencv gerekiyor:\n{e}")
            return

        def oku(yol):
            try:
                return cv2.imdecode(np.fromfile(yol, dtype=np.uint8),
                                    cv2.IMREAD_COLOR)
            except Exception:
                return None

        self._autosave()
        baslangic = self.dataset.current_index
        ilk_kare = oku(ann.image_path)
        if ilk_kare is None:
            QMessageBox.warning(self, "Kare okunamadı",
                                "Bu karenin görseli okunamadı.")
            return
        siniflar = [b.class_id for b in ann.bboxes]
        zincir = KutuZinciri(ilk_kare, [(b.x1, b.y1, b.x2, b.y2)
                                        for b in ann.bboxes])

        QApplication.setOverrideCursor(Qt.WaitCursor)
        yazilan = dusen = 0
        durma_sebebi = ""
        try:
            for adim in range(1, adet + 1):
                idx = baslangic + adim
                hedef = self.dataset.images[idx]
                hedef.load()
                if hedef.bboxes:
                    durma_sebebi = (f"{adim}. karede zaten kutu var — "
                                    f"üstüne yazılmadı, zincir durdu")
                    break
                sonraki_kare = oku(hedef.image_path)
                if sonraki_kare is None:
                    durma_sebebi = "kare okunamadı"
                    break

                onceki_canli = len(zincir.canli)
                sonuc = zincir.adim(sonraki_kare)
                dusen += onceki_canli - len(sonuc)
                if not sonuc:
                    durma_sebebi = (f"{adim}. karede durdu: "
                                    f"{zincir.son_sebep or 'takip kayboldu'}")
                    break

                pix = QPixmap(hedef.image_path)
                if pix.isNull():
                    durma_sebebi = "görsel yüklenemedi"
                    break
                hedef.img_width, hedef.img_height = pix.width(), pix.height()
                hedef.bboxes = [BBox(k[0], k[1], k[2], k[3], siniflar[i])
                                for i, k, _g in sonuc]
                hedef.save()
                self._update_list_item(idx)
                yazilan += 1
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        self._refresh_labeled_count()
        mesaj = f"{yazilan} kareye kutu taşındı."
        if dusen:
            mesaj += f" {dusen} kutu takip edilemeyip bırakıldı."
        if durma_sebebi:
            mesaj += f" ({durma_sebebi})"
        self.status.showMessage(mesaj)
        QMessageBox.information(
            self, "Taşıma bitti",
            mesaj + "\n\nTakip bir tahmindir — taşınan kutuları gözden geçir.")

    def _open_training(self):
        if not self.dataset.images:
            QMessageBox.warning(self, "Uyarı", "Önce bir klasör açın.")
            return
        self._save_all()
        TrainingDialog(self.dataset, self).exec_()

    def _on_image_row_changed(self, row: int):
        if row >= 0 and row != self.dataset.current_index:
            self._load(row)

    def _on_bbox_added(self, x1, y1, x2, y2):
        """Yeni kutu: yapışkan sınıfla gelir, sınıf paneli yanında açılır.

        Eskiden sınıf yoksa kutu düşer ve bir uyarı kutusu çıkardı. Artık kutu
        duruyor, sınıf panelden yazılıyor; kullanıcı vazgeçerse (panel
        kapatılırsa) sınıfsız kalan kutu temizleniyor.
        """
        ann = self.dataset.current_image
        if ann is None:
            return
        sinifsiz = not self.dataset.label_classes
        cid = 0 if sinifsiz else min(self._yapiskan_sinif,
                                     len(self.dataset.label_classes) - 1)
        self._anlik_al()
        ann.bboxes.append(BBox(x1, y1, x2, y2, cid))
        yeni = len(ann.bboxes) - 1
        self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
        self.canvas.sec(yeni)
        self._atanmamis = yeni if sinifsiz else -1
        self._popup_goster(yeni, odak=sinifsiz)
        self._update_status()

    def _on_bbox_deleted(self, idx: int):
        ann = self.dataset.current_image
        if ann and 0 <= idx < len(ann.bboxes):
            self._anlik_al()
            ann.bboxes.pop(idx)
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
            self._update_status()

    def _on_class_added(self, name, color):
        self.dataset.add_class(name, color)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    def _on_class_removed(self, idx: int):
        self.dataset.remove_class(idx)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    def _on_class_selected(self, cid: int):
        self._yapiskan_sinif = cid
        self.canvas.set_current_class(cid)

    def _on_bbox_class_changed(self, bbox_idx: int, new_cid: int):
        ann = self.dataset.current_image
        if ann and 0 <= bbox_idx < len(ann.bboxes):
            self._anlik_al()
            ann.bboxes[bbox_idx].class_id = new_cid
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)
            self._update_status()

    def _on_class_renamed(self, idx: int, new_name: str):
        self.dataset.rename_class(idx, new_name)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    def _on_class_recolored(self, idx: int, color):
        self.dataset.recolor_class(idx, color)
        self.dataset.save_classes()
        self.label_panel.refresh(self.dataset.label_classes)
        ann = self.dataset.current_image
        if ann:
            self.canvas.set_annotations(ann.bboxes, self.dataset.label_classes)

    # ------------------------------------------------------------------ ui helpers

    def _img_display_name(self, ann) -> str:
        """Alt klasör varsa göreceli yolu göster, yoksa sadece dosya adı."""
        if self.dataset.folder:
            rel = os.path.relpath(ann.image_path, self.dataset.folder)
            return rel
        return os.path.basename(ann.image_path)

    def _liste_metni(self, ann) -> str:
        """Izgarada kısa ad (uzun göreceli yol kutuya sığmıyor), listede tam yol."""
        if self._izgara:
            return os.path.basename(ann.image_path)
        return self._img_display_name(ann)

    def _refresh_list(self):
        self.img_list.blockSignals(True)
        self.img_list.clear()
        for ann in self.dataset.images:
            item = QListWidgetItem(self._liste_metni(ann))
            item.setToolTip(ann.image_path)
            item.setForeground(QColor(100, 210, 100) if ann.is_labeled
                               else QColor(170, 170, 170))
            if self._izgara:
                item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
                ikon = self._kucuk_onbellek.get(ann.image_path)
                if ikon is not None:
                    item.setIcon(ikon)
            self.img_list.addItem(item)
        self.img_list.blockSignals(False)
        self._refresh_labeled_count()

    def _update_list_item(self, idx: int):
        if 0 <= idx < self.img_list.count():
            ann = self.dataset.images[idx]
            item = self.img_list.item(idx)
            item.setText(self._liste_metni(ann))
            item.setForeground(
                QColor(100, 210, 100) if ann.is_labeled else QColor(170, 170, 170)
            )
        self._refresh_labeled_count()

    def _refresh_labeled_count(self):
        labeled = sum(1 for a in self.dataset.images if a.is_labeled)
        total = len(self.dataset.images)
        self.labeled_lbl.setText(f"Etiketli: {labeled} / {total}")

    def _update_nav(self):
        total = len(self.dataset.images)
        cur = self.dataset.current_index
        self.nav_lbl.setText(f"{cur + 1} / {total}")
        self.prev_btn.setEnabled(cur > 0)
        self.next_btn.setEnabled(cur < total - 1)

    def _update_status(self):
        ann = self.dataset.current_image
        if ann:
            fname = os.path.basename(ann.image_path)
            self.status.showMessage(
                f"{fname}  |  {ann.img_width}×{ann.img_height}  |  {len(ann.bboxes)} bbox"
            )

    def closeEvent(self, event):
        self._autosave()
        self._kucuk_durdur()
        event.accept()
