"""Model üstverisi (sınıf adları) için arka plan yükleyici.

`from ultralytics import YOLO` ilk çağrıldığında torch'u da içeri alır ve bu
saniyeler sürer; `YOLO(path)` ise ağırlıkları diskten okur. Bunlar arayüz
iş parçacığında yapılırsa pencere o süre boyunca kilitlenir (kullanıcı
gözünde "donma"). Araçlar model seçildiğinde sınıf adlarını göstermek için
bu bilgiye ihtiyaç duyduğundan, okuma işi buradaki QThread'e alınır.

Kullanım:

    self._yukleyici = SinifYukleyici(path, self)
    self._yukleyici.tamamlandi.connect(self._on_names)
    self._yukleyici.start()

`tamamlandi(path, names, hata)` — hata boşsa names doludur.
"""

from PyQt5.QtCore import QThread, pyqtSignal


class SinifYukleyici(QThread):
    """Bir model dosyasının sınıf adlarını arka planda okur."""

    tamamlandi = pyqtSignal(str, dict, str)   # yol, {id: ad}, hata

    def __init__(self, yol: str, parent=None):
        super().__init__(parent)
        self.yol = yol

    def run(self):
        try:
            from ultralytics import YOLO
            names = {int(k): str(v) for k, v in YOLO(self.yol).names.items()}
        except Exception as e:
            self.tamamlandi.emit(self.yol, {}, f"{type(e).__name__}: {e}")
            return
        self.tamamlandi.emit(self.yol, names, "")


def sinif_ozeti(names: dict, en_fazla: int = 40) -> str:
    """'3 sınıf: kamyon, tir, dorse' biçiminde kısa özet."""
    if not names:
        return "Sınıflar: —"
    adlar = [str(names[i]) for i in sorted(names)]
    if len(adlar) > en_fazla:
        adlar = adlar[:en_fazla] + [f"… (+{len(names) - en_fazla})"]
    return f"{len(names)} sınıf: " + ", ".join(adlar)
