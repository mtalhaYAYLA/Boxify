#!/usr/bin/env bash
# Bütün testleri koştur.
#
#   ./testler/calistir.sh          — hepsi
#   ./testler/calistir.sh hizli    — ekran gerektirenleri atla
#
# Python seçimi: BOXIFY_PYTHON > .boxify_python > etkin ortam > python3
set -uo pipefail

DIZIN="$(cd "$(dirname "$0")" && pwd)"
KOK="$(dirname "$DIZIN")"
MOD="${1:-tam}"

py_bul() {
    [[ -n "${BOXIFY_PYTHON:-}" && -x "${BOXIFY_PYTHON}" ]] && { echo "$BOXIFY_PYTHON"; return; }
    [[ -f "$KOK/.boxify_python" ]] && {
        p="$(cat "$KOK/.boxify_python")"
        [[ -x "$p" ]] && { echo "$p"; return; }
    }
    [[ -n "${CONDA_PREFIX:-}" && -x "$CONDA_PREFIX/bin/python" ]] && { echo "$CONDA_PREFIX/bin/python"; return; }
    [[ -x "$KOK/.venv/bin/python" ]] && { echo "$KOK/.venv/bin/python"; return; }
    command -v python3 || command -v python
}

PY="$(py_bul)"
[[ -n "$PY" ]] || { echo "HATA: python bulunamadı." >&2; exit 1; }
echo "Python: $PY"
"$PY" -c "import PyQt5" 2>/dev/null || {
    echo "HATA: PyQt5 yok. Önce: ./kur.sh ortam" >&2; exit 1; }
echo

# Ekran gerektirenler en sona: ötekiler offscreen koşar
EKRANLI=(test_tiklama.py)
GECEN=0; KALAN=0; ATLANAN=0
BASARISIZ=()

kostur() {
    local ad="$1"
    printf "%-22s " "$ad"
    local cikti
    cikti="$("$PY" "$DIZIN/$ad" 2>&1)"
    local kod=$?
    local son
    son="$(echo "$cikti" | grep -E "^(SONUC|HATALAR|ATLANDI)" | tail -1)"
    [[ -z "$son" ]] && son="$(echo "$cikti" | tail -1)"
    if [[ "$son" == ATLANDI* ]]; then
        echo "ATLANDI"; ATLANAN=$((ATLANAN + 1)); return
    fi
    if [[ $kod -eq 0 ]] && ! echo "$son" | grep -qiE "BASARISIZ|!!|HALA SORUN"; then
        echo "GECTI   ${son:0:46}"
        GECEN=$((GECEN + 1))
    else
        echo "BASARISIZ"
        echo "$cikti" | tail -12 | sed 's/^/    /'
        KALAN=$((KALAN + 1)); BASARISIZ+=("$ad")
    fi
}

for t in "$DIZIN"/test_*.py; do
    ad="$(basename "$t")"
    [[ " ${EKRANLI[*]} " == *" $ad "* ]] && continue
    kostur "$ad"
done

if [[ "$MOD" != "hizli" ]]; then
    echo
    echo "── ekran gerektirenler ──"
    for ad in "${EKRANLI[@]}"; do
        [[ -f "$DIZIN/$ad" ]] && kostur "$ad"
    done
fi

echo
echo "═══════════════════════════════════════════"
echo "geçen: $GECEN   başarısız: $KALAN   atlanan: $ATLANAN"
if [[ $KALAN -gt 0 ]]; then
    echo "başarısız olanlar: ${BASARISIZ[*]}"
    exit 1
fi
echo "TÜM TESTLER GEÇTİ"
