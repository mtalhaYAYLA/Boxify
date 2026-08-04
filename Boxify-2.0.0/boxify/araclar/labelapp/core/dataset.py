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

    def auto_detect_classes(self) -> bool:
        """
        Klasörde data.yaml, classes.txt vb. varsa sınıfları otomatik yükle.
        Zaten sınıf varsa dokunma. Bulunduysa True döner.
        """
        if self.label_classes or not self.folder:
            return bool(self.label_classes)

        # Klasör + üst klasörde ara
        search_dirs = [self.folder, os.path.dirname(self.folder)]

        for d in search_dirs:
            # data.yaml / data.yml
            for fname in ('data.yaml', 'data.yml'):
                p = os.path.join(d, fname)
                if not os.path.exists(p):
                    continue
                try:
                    with open(p, encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    names = data.get('names', [])
                    if isinstance(names, dict):
                        names = [names[k] for k in sorted(names)]
                    if names:
                        for i, n in enumerate(names):
                            self.label_classes.append(
                                LabelClass(str(n), DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
                            )
                        return True
                except Exception:
                    pass

            # classes.txt / obj.names
            for fname in ('classes.txt', 'obj.names', '_darknet.labels'):
                p = os.path.join(d, fname)
                if not os.path.exists(p):
                    continue
                try:
                    with open(p, encoding='utf-8') as f:
                        names = [ln.strip() for ln in f if ln.strip()]
                    if names:
                        for i, n in enumerate(names):
                            self.label_classes.append(
                                LabelClass(n, DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
                            )
                        return True
                except Exception:
                    pass

        return False

    def auto_detect_classes_from_labels(self) -> bool:
        """
        data.yaml / classes.txt bulunamazsa label dosyalarını tarayarak
        kaç sınıf olduğunu tespit et ve generic isimler ata.
        """
        if self.label_classes:
            return True
        max_cid = -1
        for img in self.images:
            lf = img._find_label_file()
            if not lf:
                continue
            try:
                with open(lf) as f:
                    for line in f:
                        parts = line.strip().split()
                        if parts:
                            max_cid = max(max_cid, int(parts[0]))
            except Exception:
                pass
        if max_cid >= 0:
            for i in range(max_cid + 1):
                self.label_classes.append(
                    LabelClass(f"class_{i}", DEFAULT_COLORS[i % len(DEFAULT_COLORS)])
                )
            return True
        return False

    def find_existing_yaml(self) -> Optional[str]:
        """Klasörde (veya alt klasörlerde) kullanılabilir data.yaml varsa döner."""
        if not self.folder:
            return None
        for root, dirs, files in os.walk(self.folder):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in ('data.yaml', 'data.yml'):
                p = os.path.join(root, fname)
                if os.path.exists(p):
                    return p
        return None

    def build_fixed_yaml(self, src_yaml: str, out_path: str):
        """
        src_yaml'daki göreli / kırık yolları mutlak yola çevirerek out_path'e yazar.
        Roboflow veri setlerinde ../train/images gibi kırık relative path'ler olabilir;
        bunları yaml'ın bulunduğu klasörden de dener, yoksa train yolunu fallback kullanır.
        """
        import re
        yaml_dir = os.path.dirname(os.path.abspath(src_yaml))

        with open(src_yaml, encoding='utf-8') as f:
            data = yaml.safe_load(f)

        def resolve(rel_path: str) -> Optional[str]:
            if not rel_path:
                return None
            if os.path.isabs(rel_path) and os.path.exists(rel_path):
                return rel_path
            candidates = [
                # 1. Standart: yaml_dir + rel_path
                os.path.normpath(os.path.join(yaml_dir, rel_path)),
                # 2. Roboflow: "../train/images" → yaml_dir + "train/images" (.. atla)
                os.path.normpath(os.path.join(yaml_dir, re.sub(r'^(\.\./)+', '', rel_path))),
            ]
            return next((c for c in candidates if os.path.exists(c)), None)

        resolved = {}
        for key in ('train', 'val', 'test'):
            r = resolve(str(data.get(key, '') or ''))
            if r:
                resolved[key] = r

        # val yoksa train'i kullan (YOLO val zorunlu)
        if 'train' in resolved:
            resolved.setdefault('val', resolved['train'])
            resolved.setdefault('test', resolved['train'])

        data.update(resolved)
        data['path'] = yaml_dir  # YOLO'nun base path'i

        if self.label_classes:
            data['nc'] = len(self.label_classes)
            data['names'] = [lc.name for lc in self.label_classes]

        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        return out_path

    def export(self, out_dir: str, train_r: float, val_r: float, test_r: float) -> str:
        from PyQt5.QtGui import QImageReader
        for split in ('train', 'val', 'test'):
            os.makedirs(os.path.join(out_dir, 'images', split), exist_ok=True)
            os.makedirs(os.path.join(out_dir, 'labels', split), exist_ok=True)

        # Boyutları bilinmeyen resimleri disk'ten oku, label dosyasını yükle
        labeled = []
        for img in self.images:
            if img.img_width == 0:
                r = QImageReader(img.image_path)
                sz = r.size()
                if sz.isValid():
                    img.img_width = sz.width()
                    img.img_height = sz.height()

            if img.img_width == 0:
                continue  # resim okunamadı, atla

            # Bboxes belleğe yüklenmemişse disk'ten bul ve yükle
            if not img.bboxes and img.is_labeled:
                img.load()

            if img.bboxes:  # gerçekten bbox var mı kontrol et
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
