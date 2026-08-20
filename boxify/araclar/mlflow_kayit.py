"""MLflow'a ölçüm kaydı — Boxify'ın ölçüm üreten araçları için ortak katman.

Neden ortak: Eğitim dışında üç araç daha sayı üretiyor (Model Karşılaştır'ın
hız ve tespit istatistikleri, Hata Analizi'nin tp/fp/fn dökümü, Model Export'un
gecikme ve sapma ölçümleri). Bunlar bugün yalnızca ekrandaki rapora yazılıyor;
uygulama kapanınca "geçen hafta hangi ayarla ne çıkmıştı" sorusunun cevabı
kalmıyor. MLflow tam olarak bu boşluğu dolduruyor.

Üç kural:

1. **İsteğe bağlı.** mlflow kurulu değilse hiçbir şey olmaz, hiçbir araç
   engellenmez. Kutu kapalıysa da hiçbir şey yazılmaz.
2. **Sessiz kayıt yok.** Kayıt yalnızca kullanıcı kutuyu işaretlediğinde
   yapılır. (ultralytics'in kendi MLflow geri çağrımı varsayılan olarak
   açıktır ve bu yüzden Eğitim'de ayrıca kapatılıyor — bkz. egitim.py.)
3. **Sunucu gerekmez.** Depo, çıktı klasörünün altındaki `mlflow/` dizinidir;
   projeyle birlikte taşınır. İncelemek isteyen `mlflow ui` çalıştırır.

Depo neden SQLite: MLflow 3.x'te dosya tabanlı depo ("./mlruns") bakım moduna
alındı ve `file:` adresiyle kayıt açmak istisna fırlatıyor. `sqlite:///…mlflow.db`
hem yeni sürümlerde çalışıyor hem eski sürümlerde destekleniyor, hâlâ tek bir
klasörde duruyor ve yine sunucu istemiyor.

Kayıt hiçbir koşulda aracı düşürmez: MLflow tarafındaki bir hata yalnızca
bir uyarı metni olarak döner, iş sonucu etkilenmez.
"""

import os
from datetime import datetime
from pathlib import Path


def _uri(yol: str) -> str:
    """Yerel yolu dosya URI'sine çevirir (boşluklu yollar için)."""
    return Path(os.path.abspath(yol)).as_uri()


def mlflow_var() -> bool:
    """MLflow kurulu mu? (import edilmeden, yalnızca bulunabilirliğe bakılır)"""
    import importlib.util
    return importlib.util.find_spec("mlflow") is not None


def depo_yolu(cikti_klasoru: str) -> str:
    """Ölçümlerin yazılacağı yerel depo klasörü."""
    return os.path.join(cikti_klasoru or os.getcwd(), "mlflow")


def izleme_adresi(cikti_klasoru: str) -> str:
    """MLflow izleme adresi (SQLite; dosya deposu 3.x'te bakım modunda)."""
    return "sqlite:///" + os.path.join(depo_yolu(cikti_klasoru), "mlflow.db")


def urun_yolu(cikti_klasoru: str) -> str:
    """Ağırlık/rapor gibi dosyaların yazılacağı yer."""
    return os.path.join(depo_yolu(cikti_klasoru), "urunler")


def kayit_ipucu(cikti_klasoru: str) -> str:
    return "mlflow ui --backend-store-uri " + izleme_adresi(cikti_klasoru)


def _duzelt(anahtar: str) -> str:
    """MLflow anahtarlarında sınırlı karakter kümesi var; güvenli hâle getir."""
    guvenli = []
    for ch in str(anahtar):
        guvenli.append(ch if (ch.isalnum() or ch in " _-./") else "_")
    return "".join(guvenli)[:250].strip() or "deger"


def kaydet(cikti_klasoru: str, deney: str, tur_adi: str,
           parametreler: dict = None, metrikler: dict = None,
           etiketler: dict = None, dosyalar=None) -> str:
    """Bir ölçüm turunu MLflow'a yaz. Dönen metin: kullanıcıya gösterilecek not.

    Boş metin = kayıt yapılmadı (mlflow yok). Hata olursa hatayı anlatan bir
    metin döner ama istisna fırlatmaz — ölçüm sonucu kaybolmamalı.
    """
    if not mlflow_var():
        return ""

    depo = depo_yolu(cikti_klasoru)
    try:
        os.makedirs(depo, exist_ok=True)
        import mlflow

        os.makedirs(urun_yolu(cikti_klasoru), exist_ok=True)
        mlflow.set_tracking_uri(izleme_adresi(cikti_klasoru))
        # Deney yoksa ürün klasörünü de belirterek yarat: SQLite deposunda
        # ürünlerin nereye yazılacağı deney oluşturulurken belirlenir.
        if mlflow.get_experiment_by_name(deney) is None:
            mlflow.create_experiment(
                deney, artifact_location=_uri(urun_yolu(cikti_klasoru)))
        mlflow.set_experiment(deney)
        ad = tur_adi or datetime.now().strftime("%Y%m%d_%H%M%S")
        with mlflow.start_run(run_name=ad):
            for k, v in (parametreler or {}).items():
                mlflow.log_param(_duzelt(k), str(v)[:500])
            for k, v in (metrikler or {}).items():
                try:
                    mlflow.log_metric(_duzelt(k), float(v))
                except (TypeError, ValueError):
                    continue          # sayıya çevrilemeyen ölçüm atlanır
            for k, v in (etiketler or {}).items():
                mlflow.set_tag(_duzelt(k), str(v)[:500])
            for yol in (dosyalar or []):
                if yol and os.path.exists(yol):
                    mlflow.log_artifact(yol)
        return f"MLflow: '{deney}/{ad}' kaydedildi → {depo}"
    except Exception as e:
        return f"MLflow'a yazılamadı ({type(e).__name__}: {e}). Ölçüm sonucu etkilenmedi."


def onay_kutusu(metin: str = "MLflow'a da kaydet"):
    """Araçlarda aynı görünen onay kutusu; mlflow yoksa kapalı ve açıklamalı."""
    from PyQt5.QtWidgets import QCheckBox

    kutu = QCheckBox(metin)
    if mlflow_var():
        kutu.setToolTip(
            "Ölçüm sonuçları çıktı klasörünün altındaki mlflow/ dizinine\n"
            "yazılır. Sunucu gerekmez; incelemek için:\n"
            "  mlflow ui --backend-store-uri sqlite:///<çıktı>/mlflow/mlflow.db")
    else:
        kutu.setEnabled(False)
        kutu.setToolTip(
            "MLflow kurulu değil. Kurmak için:  pip install mlflow\n"
            "Kurulu olmaması hiçbir aracı engellemez.")
    return kutu
