"""ffmpeg varlık denetimi ve platforma uygun kurulum ipucu.

Video Kırpıcı ve Kare Alıcı işlerini ffmpeg'e yaptırıyor. ffmpeg bir Python
paketi değil, sistem paketi; requirements.txt onu kuramaz. Kurulu değilse
araçlar `FileNotFoundError` ile sessizce ölüyordu (iş parçacığı içinde
patladığı için hiçbir sinyal çıkmıyor, kullanıcı ilerlemeyen bir çubuğa
bakakalıyordu). Bu modül iki aracın da aynı denetimi ve aynı ipucunu
kullanmasını sağlar.
"""

import shutil
import sys

ARACLAR = ("ffmpeg", "ffprobe")


def eksik_olanlar(gerekli=ARACLAR) -> list:
    """PATH'te bulunamayan ffmpeg araçlarının listesi (boşsa her şey yerinde)."""
    return [ad for ad in gerekli if not shutil.which(ad)]


def kurulum_ipucu() -> str:
    """Bu platformda ffmpeg'in nasıl kurulacağını anlatan tek satır."""
    if sys.platform == "darwin":
        return "Kurulum: brew install ffmpeg"
    if sys.platform.startswith("win"):
        return "Kurulum: winget install ffmpeg"
    return "Kurulum: sudo apt install ffmpeg"


def eksik_mesaji(eksik: list, ne_kapandi: str) -> str:
    """'Eksik: ffmpeg — kare alma devre dışı. Kurulum: …' biçiminde uyarı."""
    return (f"Eksik: {', '.join(eksik)} — {ne_kapandi} devre dışı. "
            + kurulum_ipucu())
