"""Dosya yöneticisinde klasör açma — işletim sistemine göre doğru komutu seçer."""

import subprocess
import sys


def klasoru_ac(yol: str) -> None:
    if sys.platform.startswith("win"):
        import os
        os.startfile(yol)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", yol])
    else:
        subprocess.Popen(["xdg-open", yol])
