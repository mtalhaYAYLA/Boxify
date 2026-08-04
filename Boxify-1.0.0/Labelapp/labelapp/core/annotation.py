import os
from dataclasses import dataclass, field
from typing import List


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
    root_folder: str = ""   # kullanıcının açtığı ana klasör
    img_width: int = 0
    img_height: int = 0
    bboxes: List[BBox] = field(default_factory=list)

    def label_path(self) -> str:
        """
        Labellar açılan klasörün içindeki 'labels/' alt klasörüne kaydedilir.
        Örnek:
          açılan klasör : /proje/fotograflar/
          resim         : /proje/fotograflar/kediler/img.jpg
          label         : /proje/fotograflar/labels/kediler/img.txt
        """
        if self.root_folder:
            rel     = os.path.relpath(self.image_path, self.root_folder)
            rel_txt = os.path.splitext(rel)[0] + '.txt'
            return os.path.join(self.root_folder, 'labels', rel_txt)
        # root_folder bilinmiyorsa eski davranış
        img_dir = os.path.dirname(self.image_path)
        fname   = os.path.splitext(os.path.basename(self.image_path))[0] + '.txt'
        return os.path.join(img_dir, 'labels', fname)

    def save(self):
        path = self.label_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            for b in self.bboxes:
                xc, yc, w, h = b.to_yolo(self.img_width, self.img_height)
                f.write(f"{b.class_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")

    def load(self):
        self.bboxes = []
        candidates = [self.label_path()]
        # Geriye dönük uyumluluk: eski konumlara da bak
        if self.root_folder:
            old_sib = os.path.join(
                os.path.dirname(os.path.normpath(self.root_folder)), 'labels',
                os.path.splitext(os.path.relpath(self.image_path, self.root_folder))[0] + '.txt'
            )
            candidates.append(old_sib)
        candidates.append(os.path.splitext(self.image_path)[0] + '.txt')

        path = next((c for c in candidates if os.path.exists(c)), None)
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
        """Bellekte bbox varsa veya diskte label dosyası varsa True döner."""
        if self.bboxes:
            return True
        path = self.label_path()
        return os.path.exists(path) and os.path.getsize(path) > 0
