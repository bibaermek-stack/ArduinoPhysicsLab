# Arduino Physics Lab — Windows .exe жинау скрипті (Phase 9,
# Production Deployment & Release Readiness, Part A/N).
#
# Пайдалану (жоба түбірінен):
#   pwsh build/build.ps1
#
# Талап етеді: белсенді Python ортасында requirements.txt +
# requirements-build.txt орнатылған болуы керек (§ "PyInstaller — build-
# time-only dependency, requirements.txt-тен бөлек").

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

Write-Host "=== Arduino Physics Lab — production build ===" -ForegroundColor Cyan

$PyInstaller = Get-Command pyinstaller -ErrorAction SilentlyContinue
if (-not $PyInstaller) {
    Write-Host "PyInstaller табылмады — orнату: pip install -r requirements-build.txt" -ForegroundColor Yellow
    pip install -r (Join-Path $ProjectRoot "requirements-build.txt")
}

# § "keep generated release artifacts OUT of Git" — .gitignore-де
# ``release/``/``build/work/`` бұрыннан бар (§ Phase 9 .gitignore
# жаңартуы).
$DistPath = Join-Path $ProjectRoot "release"
$WorkPath = Join-Path $ProjectRoot "build\work"

pyinstaller (Join-Path $ProjectRoot "build\app.spec") `
    --distpath $DistPath `
    --workpath $WorkPath `
    --noconfirm

Write-Host ""
Write-Host "Дайын: $DistPath\ArduinoPhysicsLab\ArduinoPhysicsLab.exe" -ForegroundColor Green
