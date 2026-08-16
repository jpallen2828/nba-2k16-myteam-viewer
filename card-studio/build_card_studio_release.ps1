param()

$ErrorActionPreference = "Stop"
$root = [System.IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
$distRoot = Join-Path $root "dist"
$buildRoot = Join-Path $root "build"
$releaseRoot = Join-Path $root "release"

$modelPath = Join-Path $root "models\player_background_removal.onnx"
if (-not (Test-Path $modelPath)) {
    throw "Missing models\player_background_removal.onnx. Copy it from an official Card Studio release before building the complete portable ZIP."
}

python -m PyInstaller --clean --noconfirm --distpath $distRoot --workpath $buildRoot (Join-Path $root "NBA2K16CardStudio.spec")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed for Card Studio."
}

robocopy (Join-Path $root "models") (Join-Path $distRoot "models") /MIR > $null
if ($LASTEXITCODE -ge 8) {
    throw "Failed to mirror models into dist\models"
}

$version = (Get-Content (Join-Path $root "app\constants.py") | Select-String -Pattern 'APPLICATION_VERSION\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$releaseVersionDir = Join-Path $releaseRoot $version
$zipPath = Join-Path $releaseRoot "NBA2K16CardStudio-v$version-Windows.zip"
$canonicalReleaseZip = Join-Path $releaseRoot "NBA.2K16.Card.Studio.zip"

New-Item -ItemType Directory -Force -Path $releaseVersionDir | Out-Null
Copy-Item (Join-Path $distRoot "NBA2K16CardStudio.exe") (Join-Path $releaseVersionDir "NBA2K16CardStudio.exe") -Force
robocopy (Join-Path $distRoot "models") (Join-Path $releaseVersionDir "models") /MIR > $null
if ($LASTEXITCODE -ge 8) {
    throw "Failed to mirror models into release\$version\models"
}
Copy-Item (Join-Path $root "README.md") (Join-Path $releaseVersionDir "README.txt") -Force

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
tar -a -cf $zipPath -C $releaseRoot $version
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create the Card Studio release ZIP."
}
Copy-Item $zipPath $canonicalReleaseZip -Force
Write-Output $canonicalReleaseZip
