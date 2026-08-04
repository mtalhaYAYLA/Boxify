# Boxify'i Windows masaustune ve Baslat Menusune kisayol olarak kaydeder.
# Kullanim (kur.bat uzerinden):  kur.bat          - kur
#                                 kur.bat kaldir   - kaldir
#
# macOS ve Linux icin bu dosya degil kur.sh kullanilir.

param(
    [string]$Islem = ""
)

$Dizin = Split-Path -Parent $MyInvocation.MyCommand.Path
$Masaustu = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Boxify.lnk'
$BaslatMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Boxify.lnk'
$IkonPng = Join-Path $Dizin 'ikon.png'
$IkonIco = Join-Path $Dizin 'ikon.ico'

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
