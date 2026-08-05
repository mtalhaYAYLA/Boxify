"""Testler icin sahte ultralytics: gercek YOLO API'sinin kullanilan kismi."""
import os
import numpy as np

__version__ = "0.0-fake"


class _Tensor:
    def __init__(self, arr): self._a = np.asarray(arr)
    def cpu(self): return self
    def numpy(self): return self._a
    def tolist(self): return self._a.tolist()
    def argsort(self): return self._a.argsort()
    def __len__(self): return len(self._a)
    def __getitem__(self, i): return self._a[i]


class _Boxes:
    def __init__(self, cls, conf, xyxy):
        self.cls = _Tensor(cls); self.conf = _Tensor(conf); self.xyxy = _Tensor(xyxy)
    def __len__(self): return len(self.cls)


class _Results:
    def __init__(self, frame, boxes, names):
        self._frame = frame; self.boxes = boxes; self.names = names
        self.orig_shape = frame.shape[:2]
    def plot(self, labels=True, conf=True, **kw):
        out = self._frame.copy()
        out[0:4, 0:4] = (0, 255, 0)   # ciziim yapildigini belli eden iz
        return out


class YOLO:
    """Model dosyasinin adina gore farkli sinif kumesi ve tespit sayisi uretir."""

    def __init__(self, path):
        self.path = path
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        taban = os.path.basename(path)
        if "iki" in taban:
            self.names = {0: "kamyon", 1: "tir"}
        elif "bos" in taban:
            self.names = {}
        else:
            self.names = {0: "kamyon", 1: "tir", 2: "dorse"}
        self._sayac = 0

    def predict(self, source=None, conf=0.25, iou=0.45, imgsz=640, device=None,
                max_det=300, classes=None, half=False, agnostic_nms=False,
                verbose=False, **kw):
        frame = source
        h, w = frame.shape[:2]
        self._sayac += 1
        mevcut = sorted(self.names) or [0]
        izin = [c for c in mevcut if classes is None or c in classes]
        n = 0 if not izin else (self._sayac % 3) + 1
        cls, cfs, xyxy = [], [], []
        for k in range(n):
            c = izin[k % len(izin)]
            skor = 0.4 + 0.1 * (k % 5)
            if skor < conf:
                continue
            cls.append(c); cfs.append(skor)
            xyxy.append([10 + k * 5, 10, 10 + k * 5 + w // 4, 10 + h // 4])
        return [_Results(frame, _Boxes(np.array(cls, dtype=float),
                                       np.array(cfs, dtype=float),
                                       np.array(xyxy, dtype=float).reshape(-1, 4)),
                         self.names)]
