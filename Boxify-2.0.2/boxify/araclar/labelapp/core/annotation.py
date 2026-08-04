import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BBox:
    x1: int
    y1: int
    x2: int
    y2: int
    class_id: int

    def to_yolo(self, img_w: int, img_h: int):
        xc = (self.x1 + self.x2) / 2 / img_w
        yc = (self.y1 + self.y2) / 2 / img_h
        w  = abs(self.x2 - self.x1) / img_w
        h  = abs(self.y2 - self.y1) / img_h
        return xc, yc, w, h

    @classmethod
    def from_yolo(cls, class_id, xc, yc, w, h, img_w, img_h):
        x1 = int((xc - w / 2) * img_w)
        y1 = int((yc - h / 2) * img_h)
        x2 = int((xc + w / 2) * img_w)
        y2 = int((yc + h / 2) * img_h)
        return cls(x1, y1, x2, y2, class_id)


@dataclass
class ImageAnnotation:
    image_path: str
    root_folder: str = ""
    img_width: int = 0
    img_height: int = 0
    bboxes: List[BBox] = field(default_factory=list)

    def label_path(self) -> str:
        """Birincil kayıt yolu: root_folder/labels/... """
        if self.root_folder:
            rel     = os.path.relpath(self.image_path, self.root_folder)
            rel_txt = os.path.splitext(rel)[0] + '.txt'
            return os.path.join(self.root_folder, 'labels', rel_txt)
        img_dir = os.path.dirname(self.image_path)
        fname   = os.path.splitext(os.path.basename(self.image_path))[0] + '.txt'
        return os.path.join(img_dir, 'labels', fname)

    def _candidate_paths(self) -> List[str]:
        """
        Label dosyası için olası tüm konumlar.
        Dış araçlarla (Roboflow, LabelImg, CVAT vb.) labellanmış klasörler
        farklı yapılarda olabilir — hepsini dene.
        """
        img_dir  = os.path.dirname(self.image_path)
        fname    = os.path.basename(self.image_path)
        name_txt = os.path.splitext(fname)[0] + '.txt'

        paths = []

        # 1. Bizim birincil format: root/labels/...
        paths.append(self.label_path())

        # 2. Resimle aynı klasörde (LabelImg inline)
        paths.append(os.path.join(img_dir, name_txt))

        # 3. Resim klasörünün içindeki labels/ (YOLO standart)
        paths.append(os.path.join(img_dir, 'labels', name_txt))

        # 4. Resim klasörünün kardeşi olan labels/ (Roboflow / ultralytics)
        parent = os.path.dirname(img_dir)
        paths.append(os.path.join(parent, 'labels', name_txt))

        # 5. root_folder'ın üstündeki labels/
        if self.root_folder:
            rel     = os.path.relpath(self.image_path, self.root_folder)
            rel_txt = os.path.splitext(rel)[0] + '.txt'
            above   = os.path.join(
                os.path.dirname(os.path.normpath(self.root_folder)),
                'labels', rel_txt
            )
            paths.append(above)

        # Tekrar edenleri çıkar, sırayı koru
        seen, unique = set(), []
        for p in paths:
            np_ = os.path.normpath(p)
            if np_ not in seen:
                seen.add(np_)
                unique.append(p)
        return unique

    def _find_label_file(self) -> Optional[str]:
        """Var olan ve boş olmayan ilk label dosyasını döner."""
        for c in self._candidate_paths():
            if os.path.exists(c) and os.path.getsize(c) > 0:
                return c
        return None

    def save(self):
        path = self.label_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            for b in self.bboxes:
                xc, yc, w, h = b.to_yolo(self.img_width, self.img_height)
                f.write(f"{b.class_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

    def load(self):
        self.bboxes = []
        path = self._find_label_file()
        if path is None:
            return
        with open(path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    cid = int(parts[0])
                    xc, yc, w, h = map(float, parts[1:])
                    self.bboxes.append(
                        BBox.from_yolo(cid, xc, yc, w, h, self.img_width, self.img_height)
                    )

    @property
    def is_labeled(self) -> bool:
        if self.bboxes:
            return True
        return self._find_label_file() is not None
