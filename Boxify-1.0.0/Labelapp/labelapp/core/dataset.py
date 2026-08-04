import os
import json
import shutil
import random
import yaml
from typing import List, Optional
from PyQt5.QtGui import QColor
from .annotation import ImageAnnotation, BBox

IMG_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

DEFAULT_COLORS = [
    QColor(255, 80, 80), QColor(80, 200, 80), QColor(80, 120, 255),
    QColor(255, 165, 0), QColor(180, 80, 255), QColor(0, 200, 200),
    QColor(255, 60, 180), QColor(0, 180, 100), QColor(255, 220, 0),
    QColor(100, 180, 255),
]


class LabelClass:
    def __init__(self, name: str, color: QColor):
        self.name = name
        self.color = color


class Dataset:
    def __init__(self):
        self.folder: Optional[str] = None
        self.images: List[ImageAnnotation] = []
        self.label_classes: List[LabelClass] = []
        self.current_index: int = 0

    def load_folder(self, folder: str):
        self.folder = os.path.normpath(folder)
        self.images = []
        skip_dirs = {'labels', '__pycache__', '.git'}
        for root, dirs, files in os.walk(self.folder):
            # Alt klasör listesini filtrele (labels ve gizli klasörler atlanır)
            dirs[:] = sorted(d for d in dirs if d not in skip_dirs and not d.startswith('.'))
            for fname in sorted(files):
                if os.path.splitext(fname)[1].lower() in IMG_EXTS:
                    img_path = os.path.join(root, fname)
                    self.images.append(
                        ImageAnnotation(image_path=img_path, root_folder=self.folder)
                    )
        self.current_index = 0

    @property
    def current_image(self) -> Optional[ImageAnnotation]:
        if 0 <= self.current_index < len(self.images):
            return self.images[self.current_index]
        return None

    def add_class(self, name: str, color: QColor):
        self.label_classes.append(LabelClass(name, color))

    def remove_class(self, index: int):
        if 0 <= index < len(self.label_classes):
            self.label_classes.pop(index)

    def rename_class(self, index: int, new_name: str):
        if 0 <= index < len(self.label_classes):
            self.label_classes[index].name = new_name

    def recolor_class(self, index: int, color):
        if 0 <= index < len(self.label_classes):
            self.label_classes[index].color = color

    def _classes_path(self) -> str:
        # Sınıf bilgisi labels/ klasörünün içine kaydedilir
        return os.path.join(self.folder, 'labels', 'labelapp_classes.json')

    def save_classes(self):
        if not self.folder:
            return
        path = self._classes_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = [
            {'name': lc.name, 'color': [lc.color.red(), lc.color.green(), lc.color.blue()]}
            for lc in self.label_classes
        ]
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_classes(self):
        if not self.folder:
            return
        # Yeni konum dene, sonra eski konuma bak
        candidates = [
            self._classes_path(),
            os.path.join(self.folder, 'labelapp_classes.json'),
        ]
        path = next((c for c in candidates if os.path.exists(c)), None)
        if path is None:
            return
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        self.label_classes = []
        for item in data:
            r, g, b = item['color']
            self.label_classes.append(LabelClass(item['name'], QColor(r, g, b)))

    def export(self, out_dir: str, train_r: float, val_r: float, test_r: float) -> str:
        from PyQt5.QtGui import QImageReader
        for split in ('train', 'val', 'test'):
            os.makedirs(os.path.join(out_dir, 'images', split), exist_ok=True)
            os.makedirs(os.path.join(out_dir, 'labels', split), exist_ok=True)

        # Boyutları bilinmeyen ama label dosyası olan resimleri de dahil et
        labeled = []
        for img in self.images:
            if img.img_width == 0:
                r = QImageReader(img.image_path)
                sz = r.size()
                if sz.isValid():
                    img.img_width = sz.width()
                    img.img_height = sz.height()
            if img.is_labeled and img.img_width > 0:
                labeled.append(img)

        random.shuffle(labeled)
        n = len(labeled)
        n_train = max(1, int(n * train_r))
        n_val   = max(0, int(n * val_r))

        splits = {
            'train': labeled[:n_train],
            'val':   labeled[n_train:n_train + n_val],
            'test':  labeled[n_train + n_val:],
        }

        # YOLO val boş olamaz — train'den al
        if not splits['val'] and splits['train']:
            splits['val'] = splits['train'][:max(1, len(splits['train']) // 2)]

        for split_name, imgs in splits.items():
            for ann in imgs:
                fname = os.path.basename(ann.image_path)
                shutil.copy2(ann.image_path, os.path.join(out_dir, 'images', split_name, fname))
                label_name = os.path.splitext(fname)[0] + '.txt'
                dst = os.path.join(out_dir, 'labels', split_name, label_name)
                with open(dst, 'w') as f:
                    for b in ann.bboxes:
                        xc, yc, w, h = b.to_yolo(ann.img_width, ann.img_height)
                        f.write(f"{b.class_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

        yaml_path = os.path.join(out_dir, 'dataset.yaml')
        with open(yaml_path, 'w') as f:
            yaml.dump({
                'path': os.path.abspath(out_dir),
                'train': 'images/train',
                'val': 'images/val',
                'test': 'images/test',
                'nc': len(self.label_classes),
                'names': [lc.name for lc in self.label_classes],
            }, f, default_flow_style=False, allow_unicode=True)

        return yaml_path
