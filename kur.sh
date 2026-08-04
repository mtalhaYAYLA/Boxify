#!/usr/bin/env bash
# Boxify'ı işletim sisteminin uygulama listesine kaydeder.
#
#   ./kur.sh          — kur
#   ./kur.sh kaldir   — kaldır
#
# macOS  : ~/Applications/Boxify.app paketi üretir (Spotlight ve Launchpad görür,
#          Dock'a sabitlenebilir).
# Linux  : ~/.local/share/applications/boxify.desktop girdisi ve hicolor ikonu.
#
# Windows için bu dosya değil kur.bat kullanılır.
set -euo pipefail

DIZIN="$(cd "$(dirname "$0")" && pwd)"
ISLEM="${1:-kur}"

# ── Python bul ───────────────────────────────────────────────────────────────
# Sıra: BOXIFY_PYTHON > o an etkin ortam > venv > conda ortamları > sistem.
# Eskiden burada iki ortam adı (truck_detect, a1b2) gömülüydü; başka bir
# makinede o adlar olmadığı için kurulum hiç çalışmıyordu.
#
# İki turlu arama yapılıyor. Birinci tur PyQt5 **ve** ultralytics arar: sadece
# PyQt5'i olan bir yorumlayıcı Boxify'ı açar ama sekiz araçtan beşi ilk
# tıklamada "eksik bağımlılık" hatası verir. Bu, conda kullananlarda tipik bir
# tuzak — `base` ortamında PyQt5 hazır gelir, ultralytics gelmez ve etkin ortam
# olduğu için ilk sırada seçilir. Hiçbiri ikisine birden sahip değilse ikinci
# turda PyQt5 yeterli sayılır, ama kullanıcı uyarılır.
adaylari_listele() {
    [[ -n "${BOXIFY_PYTHON:-}" ]] && echo "$BOXIFY_PYTHON"
    [[ -n "${VIRTUAL_ENV:-}" ]] && echo "$VIRTUAL_ENV/bin/python"
    echo "$DIZIN/.venv/bin/python"
    [[ -n "${CONDA_PREFIX:-}" ]] && echo "$CONDA_PREFIX/bin/python"

    local kok env
    for kok in "$HOME/anaconda3/envs" "$HOME/miniconda3/envs" \
               "$HOME/miniforge3/envs" "/opt/anaconda3/envs" \
               "/opt/miniconda3/envs" "/opt/homebrew/Caskroom/miniforge/base/envs"; do
        [[ -d "$kok" ]] || continue
        for env in "$kok"/*/bin/python; do
            [[ -x "$env" ]] && echo "$env"
        done
    done
    command -v python3 || true
    command -v python || true
}

EKSIK_ULTRALYTICS=0

python_bul() {
    local aday
    while IFS= read -r aday; do
        [[ -n "$aday" && -x "$aday" ]] || continue
        if "$aday" -c "import PyQt5, ultralytics" >/dev/null 2>&1; then
            printf '%s' "$aday"
            return 0
        fi
    done < <(adaylari_listele)

    while IFS= read -r aday; do
        [[ -n "$aday" && -x "$aday" ]] || continue
        if "$aday" -c "import PyQt5" >/dev/null 2>&1; then
            EKSIK_ULTRALYTICS=1
            printf '%s' "$aday"
            return 0
        fi
    done < <(adaylari_listele)
    return 1
}

ultralytics_uyar() {
    [[ "$EKSIK_ULTRALYTICS" == "1" ]] || return 0
    echo
    echo "UYARI: Bu yorumlayıcıda ultralytics yok."
    echo "  Boxify açılır ama Oto Label, Eğitim, Hata Analizi, Model Karşılaştır"
    echo "  ve Model Export çalışmaz. Şununla tamamla:"
    echo "    $1 -m pip install -r \"$DIZIN/requirements.txt\""
}

# ── macOS ────────────────────────────────────────────────────────────────────
mac_kur() {
    local APP="$HOME/Applications/Boxify.app"
    if [[ "$ISLEM" == "kaldir" ]]; then
        rm -rf "$APP"
        echo "Boxify.app kaldırıldı."
        return 0
    fi

    local PY
    PY="$(python_bul)" || {
        echo "HATA: PyQt5 içeren bir python bulunamadı." >&2
        echo "Kur:  pip install -r \"$DIZIN/requirements.txt\"" >&2
        echo "Ya da kullanmak istediğin yorumlayıcıyı elle göster:" >&2
        echo "  BOXIFY_PYTHON=/yol/python ./kur.sh" >&2
        return 1
    }
    echo "Python: $PY"

    rm -rf "$APP"
    mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

    # Başlatıcı: .app içinden çalıştığı için çalışma dizinini kendisi ayarlar
    cat > "$APP/Contents/MacOS/Boxify" <<EOF
#!/bin/bash
cd "$DIZIN"
exec "$PY" "$DIZIN/boxify.py" "\$@"
EOF
    chmod +x "$APP/Contents/MacOS/Boxify"

    cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>              <string>Boxify</string>
    <key>CFBundleDisplayName</key>       <string>Boxify</string>
    <key>CFBundleIdentifier</key>        <string>com.boxify.app</string>
    <key>CFBundleVersion</key>           <string>3.1.0</string>
    <key>CFBundleShortVersionString</key><string>3.1.0</string>
    <key>CFBundlePackageType</key>       <string>APPL</string>
    <key>CFBundleExecutable</key>        <string>Boxify</string>
    <key>CFBundleIconFile</key>          <string>boxify</string>
    <key>NSHighResolutionCapable</key>   <true/>
    <key>LSMinimumSystemVersion</key>    <string>10.13</string>
    <key>NSCameraUsageDescription</key>
    <string>Boxify kamerayı kullanmaz; bu izin yalnızca video okuma kitaplıkları için tanımlıdır.</string>
</dict>
</plist>
EOF

    # İkon: png → kare → .icns (sips ve iconutil macOS'ta hazır gelir)
    if [[ -f "$DIZIN/ikon.png" ]] && command -v sips >/dev/null && command -v iconutil >/dev/null; then
        local GECICI
        GECICI="$(mktemp -d)"
        local SET="$GECICI/boxify.iconset"
        mkdir -p "$SET"
        sips -s format png "$DIZIN/ikon.png" --out "$GECICI/kare.png" >/dev/null 2>&1
        local boyut
        for boyut in 16 32 64 128 256 512; do
            sips -z $boyut $boyut "$GECICI/kare.png" \
                 --out "$SET/icon_${boyut}x${boyut}.png" >/dev/null 2>&1
            sips -z $((boyut * 2)) $((boyut * 2)) "$GECICI/kare.png" \
                 --out "$SET/icon_${boyut}x${boyut}@2x.png" >/dev/null 2>&1
        done
        iconutil -c icns "$SET" -o "$APP/Contents/Resources/boxify.icns" 2>/dev/null \
            || echo "Not: ikon dönüştürülemedi, varsayılan ikon kullanılacak."
        rm -rf "$GECICI"
    fi

    # Finder'ın yeni paketi hemen görmesi için damgayı tazele
    touch "$APP"
    ultralytics_uyar "$PY"
    echo
    echo "Tamam: $APP"
    echo "Launchpad ve Spotlight'ta 'Boxify' diye arayabilirsin."
    echo "Dock'a sabitlemek için uygulamayı açıp Dock ikonuna sağ tıkla → Seçenekler → Dock'ta Tut."
}

# ── Linux ────────────────────────────────────────────────────────────────────
linux_kur() {
    local MASAUSTU_DOSYA="$HOME/.local/share/applications/boxify.desktop"
    local IKON_HEDEF="$HOME/.local/share/icons/hicolor/512x512/apps/boxify.png"

    if [[ "$ISLEM" == "kaldir" ]]; then
        rm -f "$MASAUSTU_DOSYA" "$IKON_HEDEF"
        command -v update-desktop-database >/dev/null && \
            update-desktop-database "$HOME/.local/share/applications" || true
        echo "Boxify menüden kaldırıldı."
        return 0
    fi

    local PY
    PY="$(python_bul)" || {
        echo "HATA: PyQt5 içeren bir python bulunamadı." >&2
        echo "Kur:  pip install -r \"$DIZIN/requirements.txt\"" >&2
        echo "Ya da: BOXIFY_PYTHON=/yol/python ./kur.sh" >&2
        return 1
    }
    echo "Python: $PY"

    # İkonu kare 512x512 yapıp hicolor temasına kur — Show Apps önbelleği ancak
    # temalı ikonla güvenilir tazeleniyor (tam yol verilirse GNOME eskisini tutabiliyor)
    mkdir -p "$(dirname "$IKON_HEDEF")"
    if "$PY" -c "import PIL" >/dev/null 2>&1; then
        "$PY" - "$DIZIN/ikon.png" "$IKON_HEDEF" <<'PYEOF'
import sys
from PIL import Image
im = Image.open(sys.argv[1]).convert("RGBA")
k = max(im.size)
kare = Image.new("RGBA", (k, k), (0, 0, 0, 0))
kare.paste(im, ((k - im.width) // 2, (k - im.height) // 2))
kare.resize((512, 512), Image.LANCZOS).save(sys.argv[2])
PYEOF
    else
        # Pillow yoksa ikonu olduğu gibi kopyala — kurulum bunun için durmasın
        cp "$DIZIN/ikon.png" "$IKON_HEDEF"
        echo "Not: Pillow yok, ikon yeniden boyutlandırılmadı (pip install Pillow)."
    fi
    command -v gtk-update-icon-cache >/dev/null && \
        gtk-update-icon-cache -f -t --ignore-theme-index \
            "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

    mkdir -p "$(dirname "$MASAUSTU_DOSYA")"
    cat > "$MASAUSTU_DOSYA" <<EOF
[Desktop Entry]
Type=Application
Name=Boxify
GenericName=Nesne Tespiti Veri ve Model Atölyesi
Comment=Video kırpma, kare alma, oto/elle etiketleme, veri denetimi, eğitim, hata analizi, model karşılaştırma ve export — tek uygulama (TR/EN)
Exec="$PY" "$DIZIN/boxify.py"
Path=$DIZIN
Icon=boxify
Terminal=false
Categories=Development;Graphics;Science;
Keywords=yolo;etiket;label;dataset;train;export;boxify;
StartupNotify=true
EOF
    chmod +x "$MASAUSTU_DOSYA"

    command -v update-desktop-database >/dev/null && \
        update-desktop-database "$HOME/.local/share/applications" || true

    ultralytics_uyar "$PY"
    echo
    echo "Tamam: Boxify uygulama menüsüne kaydedildi → $MASAUSTU_DOSYA"
    echo "Menüde görünmezse oturumu yenilemen yeterli."
}

case "$(uname -s)" in
    Darwin) mac_kur ;;
    Linux)  linux_kur ;;
    MINGW*|MSYS*|CYGWIN*)
        echo "Windows'ta bu dosya değil kur.bat kullanılmalı:" >&2
        echo "  kur.bat          — kur" >&2
        echo "  kur.bat kaldir   — kaldır" >&2
        exit 1 ;;
    *)
        echo "Bilinmeyen işletim sistemi: $(uname -s)" >&2
        echo "Boxify'ı yine de şöyle çalıştırabilirsin: python \"$DIZIN/boxify.py\"" >&2
        exit 1 ;;
esac
