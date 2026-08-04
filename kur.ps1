# Boxify kurulumu (Windows).
#
#   kur.bat              - uygulamayi masaustune ve Baslat Menusune kaydet
#   kur.bat ortam        - Python ortamini kur (conda varsa conda, yoksa venv)
#   kur.bat ortam venv   - ortami zorla venv ile kur
#   kur.bat ortam conda  - ortami zorla conda ile kur
#   kur.bat tam          - once ortam, sonra uygulama kaydi
#   kur.bat kaldir       - uygulama kaydini geri al
#
# macOS ve Linux icin bu dosya degil kur.sh kullanilir.

param(
    [string]$Islem = "",
    [string]$Secenek = ""
)

$OrtamAdi = if ($env:BOXIFY_ENV) { $env:BOXIFY_ENV } else { "boxify" }
$PySurum  = if ($env:BOXIFY_PY)  { $env:BOXIFY_PY }  else { "3.11" }

$Dizin = Split-Path -Parent $MyInvocation.MyCommand.Path
$Masaustu = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Boxify.lnk'
$BaslatMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Boxify.lnk'
$IkonPng = Join-Path $Dizin 'ikon.png'
$IkonIco = Join-Path $Dizin 'ikon.ico'


# ── Ortam kurulumu ───────────────────────────────────────────────────────────
# conda oncelikli: ultralytics/torch gibi paketlerin ikili bagimliliklarini
# conda daha temiz cozuyor. conda yoksa ayni isi venv yapar.
function Get-Conda {
    $c = Get-Command conda -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($aday in @("$env:USERPROFILE\anaconda3\Scripts\conda.exe",
                        "$env:USERPROFILE\miniconda3\Scripts\conda.exe",
                        "$env:USERPROFILE\miniforge3\Scripts\conda.exe",
                        "C:\ProgramData\anaconda3\Scripts\conda.exe")) {
        if (Test-Path $aday) { return $aday }
    }
    return $null
}

function Install-Conda-Env {
    $conda = Get-Conda
    if (-not $conda) { return $false }
    Write-Host "conda: $conda"
    $kok = & $conda info --base
    $py  = Join-Path $kok "envs\$OrtamAdi\python.exe"

    if (Test-Path $py) {
        Write-Host "Ortam zaten var: $OrtamAdi"
    } else {
        Write-Host "conda ortami olusturuluyor: $OrtamAdi (python $PySurum)"
        & $conda create -y -n $OrtamAdi "python=$PySurum"
        if ($LASTEXITCODE -ne 0) { return $false }
    }
    if (-not (Test-Path $py)) { Write-Host "HATA: python bulunamadi: $py"; return $false }

    Write-Host "Bagimliliklar kuruluyor..."
    & $py -m pip install --upgrade pip | Out-Null
    & $py -m pip install -r (Join-Path $Dizin "requirements.txt")
    if ($LASTEXITCODE -ne 0) { return $false }

    Write-Host ""
    Write-Host "Tamam: conda ortami hazir -> $OrtamAdi"
    Write-Host "  Elle kullanmak icin:  conda activate $OrtamAdi; python `"$Dizin\boxify.py`""
    Set-Content -Path (Join-Path $Dizin ".boxify_python") -Value $py -NoNewline
    return $true
}

function Install-Venv-Env {
    $venv = Join-Path $Dizin ".venv"
    $py = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path $py)) {
        $taban = Get-Command python -ErrorAction SilentlyContinue
        if (-not $taban) { Write-Host "HATA: python bulunamadi."; return $false }
        Write-Host "venv olusturuluyor: $venv"
        & $taban.Source -m venv $venv
        if ($LASTEXITCODE -ne 0) { return $false }
    } else {
        Write-Host "venv zaten var: $venv"
    }
    Write-Host "Bagimliliklar kuruluyor..."
    & $py -m pip install --upgrade pip | Out-Null
    & $py -m pip install -r (Join-Path $Dizin "requirements.txt")
    if ($LASTEXITCODE -ne 0) { return $false }
    Write-Host ""
    Write-Host "Tamam: venv hazir -> $venv"
    Write-Host "  Elle kullanmak icin:  $venv\Scripts\activate; python `"$Dizin\boxify.py`""
    Set-Content -Path (Join-Path $Dizin ".boxify_python") -Value $py -NoNewline
    return $true
}

function Install-Env {
    switch ($Secenek) {
        "conda" { if (-not (Install-Conda-Env)) { Write-Host "HATA: conda ile kurulum basarisiz."; exit 1 } }
        "venv"  { if (-not (Install-Venv-Env))  { Write-Host "HATA: venv ile kurulum basarisiz.";  exit 1 } }
        ""      {
            if (Get-Conda) {
                Write-Host "conda bulundu, onunla kuruluyor (venv istersen: kur.bat ortam venv)"
                if (-not (Install-Conda-Env)) {
                    Write-Host "conda basarisiz, venv deneniyor..."
                    if (-not (Install-Venv-Env)) { exit 1 }
                }
            } else {
                Write-Host "conda yok, venv ile kuruluyor"
                if (-not (Install-Venv-Env)) { exit 1 }
            }
        }
        default { Write-Host "Bilinmeyen secenek: $Secenek (conda | venv)"; exit 1 }
    }
    Write-Host ""
    Write-Host "Sirada: kur.bat   - uygulamayi masaustune ve Baslat Menusune kaydeder"
}

if ($Islem -eq 'ortam') { Install-Env; exit 0 }
if ($Islem -eq 'tam')   { Install-Env; Write-Host ""; $Islem = '' }

if ($Islem -eq 'kaldir') {
    Remove-Item -ErrorAction SilentlyContinue $Masaustu, $BaslatMenu
    Write-Host "Boxify kisayollari kaldirildi."
    exit 0
}

# ── Python bul ───────────────────────────────────────────────────────────────
# Iki turlu arama: once PyQt5 VE ultralytics olan yorumlayici, bulunamazsa
# sadece PyQt5 olan (uyariyla). Sadece PyQt5'i olan bir ortamda Boxify acilir
# ama sekiz aractan besi ilk tiklamada eksik bagimlilik hatasi verir.
function Get-Adaylar {
    if ($env:BOXIFY_PYTHON) { $env:BOXIFY_PYTHON }
    # 'kur.bat ortam' kurdugu yorumlayiciyi buraya yazar
    $isaret = Join-Path $Dizin ".boxify_python"
    if (Test-Path $isaret) { (Get-Content $isaret -Raw).Trim() }
    if ($env:VIRTUAL_ENV)   { Join-Path $env:VIRTUAL_ENV 'Scripts\python.exe' }
    Join-Path $Dizin '.venv\Scripts\python.exe'
    if ($env:CONDA_PREFIX)  { Join-Path $env:CONDA_PREFIX 'python.exe' }

    # conda ortamlari
    foreach ($kok in @("$env:USERPROFILE\anaconda3\envs", "$env:USERPROFILE\miniconda3\envs",
                       "$env:USERPROFILE\miniforge3\envs", "C:\ProgramData\anaconda3\envs")) {
        if (Test-Path $kok) {
            Get-ChildItem -Directory $kok -ErrorAction SilentlyContinue |
                ForEach-Object { Join-Path $_.FullName 'python.exe' }
        }
    }
    foreach ($ad in @('pythonw', 'python')) {
        $c = Get-Command $ad -ErrorAction SilentlyContinue
        if ($c) { $c.Source }
    }
}

function Test-Modul($py, $kod) {
    if (-not (Test-Path $py)) { return $false }
    & $py -c $kod 2>$null
    return $LASTEXITCODE -eq 0
}

$py = $null
$eksikUltralytics = $false
foreach ($aday in Get-Adaylar) {
    if (Test-Modul $aday "import PyQt5, ultralytics") { $py = $aday; break }
}
if (-not $py) {
    foreach ($aday in Get-Adaylar) {
        if (Test-Modul $aday "import PyQt5") { $py = $aday; $eksikUltralytics = $true; break }
    }
}
if (-not $py) {
    Write-Host "HATA: PyQt5 iceren bir python bulunamadi."
    Write-Host "  Once Python kur (https://www.python.org/downloads/), sonra:"
    Write-Host "    pip install -r `"$Dizin\requirements.txt`""
    Write-Host "  Ya da kullanmak istedigin yorumlayiciyi elle goster:"
    Write-Host "    `$env:BOXIFY_PYTHON='C:\yol\python.exe'; .\kur.bat"
    exit 1
}
Write-Host "Python: $py"

# Konsol penceresi acilmasin diye pythonw varsa onu tercih et
$pyw = $py -replace 'python\.exe$', 'pythonw.exe'
$calistirici = if (Test-Path $pyw) { $pyw } else { $py }

if ($eksikUltralytics) {
    Write-Host ""
    Write-Host "UYARI: Bu yorumlayicida ultralytics yok."
    Write-Host "  Boxify acilir ama Oto Label, Egitim, Hata Analizi, Model Karsilastir"
    Write-Host "  ve Model Export calismaz. Sununla tamamla:"
    Write-Host "    $py -m pip install -r `"$Dizin\requirements.txt`""
    Write-Host ""
}

if (-not (Test-Path $IkonIco)) {
    Write-Host "Ikon donusturuluyor..."
    try {
        Add-Type -AssemblyName System.Drawing
        $src = [System.Drawing.Image]::FromFile($IkonPng)
        $boyut = [Math]::Max($src.Width, $src.Height)
        $kare = New-Object System.Drawing.Bitmap($boyut, $boyut)
        $g = [System.Drawing.Graphics]::FromImage($kare)
        $g.Clear([System.Drawing.Color]::Transparent)
        $g.DrawImage($src, [int](($boyut - $src.Width) / 2), [int](($boyut - $src.Height) / 2), $src.Width, $src.Height)
        $icon = [System.Drawing.Icon]::FromHandle($kare.GetHicon())
        $fs = [System.IO.File]::Create($IkonIco)
        $icon.Save($fs)
        $fs.Close()
        $g.Dispose(); $kare.Dispose(); $src.Dispose()
    } catch {
        Write-Host "Not: ikon donusturulemedi, varsayilan ikon kullanilacak."
    }
}

$ws = New-Object -ComObject WScript.Shell
foreach ($hedef in @($Masaustu, $BaslatMenu)) {
    $sc = $ws.CreateShortcut($hedef)
    $sc.TargetPath = $calistirici
    $sc.Arguments = "`"$Dizin\boxify.py`""
    $sc.WorkingDirectory = $Dizin
    if (Test-Path $IkonIco) { $sc.IconLocation = $IkonIco }
    $sc.Description = "Boxify - Nesne Tespiti Veri ve Model Atolyesi"
    $sc.Save()
}

Write-Host "Tamam: Boxify masaustune ve Baslat Menusune eklendi."
Write-Host "Kaldirmak icin: kur.bat kaldir"
