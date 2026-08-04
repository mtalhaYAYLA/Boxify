# Boxify'i Windows masaustune ve Baslat Menusune kisayol olarak kaydeder.
# Kullanim (kur.bat uzerinden):  kur.bat          - kur
#                                 kur.bat kaldir   - kaldir

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

$py = Get-Command pythonw -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python -ErrorAction SilentlyContinue }
if (-not $py) {
    Write-Host "HATA: PATH icinde python bulunamadi."
    Write-Host "Once Python kurup PATH'e ekle: https://www.python.org/downloads/"
    exit 1
}
Write-Host "Python: $($py.Source)"

& $py.Source -c "import PyQt5" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "HATA: PyQt5 bulunamadi. Once sunu calistir:"
    Write-Host "  pip install -r `"$Dizin\requirements.txt`""
    exit 1
}

if (-not (Test-Path $IkonIco)) {
    Write-Host "Ikon donusturuluyor..."
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
}

$ws = New-Object -ComObject WScript.Shell
foreach ($hedef in @($Masaustu, $BaslatMenu)) {
    $sc = $ws.CreateShortcut($hedef)
    $sc.TargetPath = $py.Source
    $sc.Arguments = "`"$Dizin\boxify.py`""
    $sc.WorkingDirectory = $Dizin
    $sc.IconLocation = $IkonIco
    $sc.Description = "Boxify - Nesne Tespiti Veri ve Model Atolyesi"
    $sc.Save()
}

Write-Host "Tamam: Boxify masaustune ve Baslat Menusune eklendi."
Write-Host "Kaldirmak icin: kur.bat kaldir"
