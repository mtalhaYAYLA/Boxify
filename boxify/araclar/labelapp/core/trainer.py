import re
import sys
import subprocess
from PyQt5.QtCore import QThread, pyqtSignal


class TrainerThread(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(bool, str)

    def __init__(self, yaml_path, model, epochs, batch, imgsz, out_dir):
        super().__init__()
        self.yaml_path = yaml_path
        self.model = model
        self.epochs = epochs
        self.batch = batch
        self.imgsz = imgsz
        self.out_dir = out_dir
        self._process = None

    def run(self):
        script = f"""
from ultralytics import YOLO
model = YOLO('{self.model}.pt')
model.train(
    data=r'{self.yaml_path}',
    epochs={self.epochs},
    batch={self.batch},
    imgsz={self.imgsz},
    project=r'{self.out_dir}',
    name='train',
    exist_ok=True,
    verbose=True,
)
"""
        try:
            self._process = subprocess.Popen(
                [sys.executable, '-c', script],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in self._process.stdout:
                line = line.rstrip()
                if line:
                    self.log.emit(line)
                    m = re.search(r'\b(\d+)/' + str(self.epochs) + r'\b', line)
                    if m:
                        self.progress.emit(int(m.group(1)), self.epochs)

            self._process.wait()
            ok = self._process.returncode == 0
            self.finished.emit(ok, "Eğitim tamamlandı!" if ok else f"Hata: kod {self._process.returncode}")
        except Exception as e:
            self.finished.emit(False, str(e))

    def stop(self):
        if self._process:
            self._process.terminate()
