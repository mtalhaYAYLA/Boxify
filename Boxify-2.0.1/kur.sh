#!/usr/bin/env bash
# Boxify'ı uygulama menüsüne (Apps) kaydeder.
# Kullanım:  ./kur.sh          — kur
#            ./kur.sh kaldir   — menüden kaldır
set -euo pipefail

DIZIN="$(cd "$(dirname "$0")" && pwd)"
MASAUSTU_DOSYA="$HOME/.local/share/applications/boxify3.desktop"
IKON_HEDEF="$HOME/.local/share/icons/hicolor/512x512/apps/boxify3.png"

if [[ "${1:-}" == "kaldir" ]]; then
    rm -f "$MASAUSTU_DOSYA" "$IKON_HEDEF"
    command -v update-desktop-database >/dev/null && \
        update-desktop-database "$HOME/.local/share/applications" || true
    echo "Boxify menüden kaldırıldı."
    exit 0
fi

# Uygun python ortamını bul (öncelik: truck_detect, sonra a1b2, sonra sistem)
PY=""
for aday in \
    "$HOME/anaconda3/envs/truck_detect/bin/python" \
    "$HOME/anaconda3/envs/a1b2/bin/python" \
    "$(command -v python3 || true)"; do
    if [[ -n "$aday" && -x "$aday" ]] && "$aday" -c "import PyQt5" 2>/dev/null; then
        PY="$aday"
        break
    fi
done
if [[ -z "$PY" ]]; then
    echo "HATA: PyQt5 içeren bir python bulunamadı." >&2
    echo "Şununla kurabilirsin: pip install -r $DIZIN/requirements.txt" >&2
    exit 1
fi
echo "Python: $PY"

# İkonu kare 512x512 yapıp hicolor temasına kur — Show Apps önbelleği ancak
# temalı ikonla güvenilir tazeleniyor (tam yol verilirse GNOME eskisini tutabiliyor)
mkdir -p "$(dirname "$IKON_HEDEF")"
"$PY" - "$DIZIN/ikon.png" "$IKON_HEDEF" <<'PYEOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGBA")
k = max(im.size)
kare = Image.new("RGBA", (k, k), (0, 0, 0, 0))
kare.paste(im, ((k - im.width) // 2, (k - im.height) // 2))
kare.resize((512, 512), Image.LANCZOS).save(sys.argv[2])
PYEOF
command -v gtk-update-icon-cache >/dev/null && \
    gtk-update-icon-cache -f -t --ignore-theme-index \
        "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

mkdir -p "$(dirname "$MASAUSTU_DOSYA")"
cat > "$MASAUSTU_DOSYA" <<EOF
[Desktop Entry]
Type=Application
Name=Boxify 3
GenericName=Nesne Tespiti Veri ve Model Atölyesi
Comment=Video kırpma, kare alma, oto/elle etiketleme, veri denetimi, hata analizi ve model export — tek uygulama
Exec=$PY $DIZIN/boxify.py
Path=$DIZIN
Icon=boxify3
Terminal=false
Categories=Development;Graphics;Science;
Keywords=yolo;etiket;label;dataset;export;boxify;
StartupNotify=true
EOF
chmod +x "$MASAUSTU_DOSYA"

command -v update-desktop-database >/dev/null && \
    update-desktop-database "$HOME/.local/share/applications" || true

echo "Tamam: Boxify uygulama menüsüne kaydedildi → $MASAUSTU_DOSYA"
echo "Menüde görünmezse oturumu yenilemen yeterli."
