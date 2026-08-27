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

$ReleaseDir = Join-Path $DistPath "ArduinoPhysicsLab"
$DestDeploy = Join-Path $ReleaseDir "deployment.json"
$LocalDeploy = Join-Path $ProjectRoot "deployment.json"
$ExampleDeploy = Join-Path $ProjectRoot "deployment.example.json"
if (Test-Path $LocalDeploy) {
    Copy-Item $LocalDeploy $DestDeploy -Force
} else {
    Copy-Item $ExampleDeploy $DestDeploy -Force
}
if ($env:APL_SYNC_API_BASE_URL) {
    $cfg = Get-Content $DestDeploy -Raw -Encoding UTF8 | ConvertFrom-Json
    $cfg.sync_api_base_url = $env:APL_SYNC_API_BASE_URL
    $cfg.sync_enabled = $true
    $cfg | ConvertTo-Json | Set-Content $DestDeploy -Encoding utf8
}

$ReadmeSrc = Join-Path $ProjectRoot "build\README-release.txt"
$ReadmePath = Join-Path $ReleaseDir "README.txt"
if (Test-Path $ReadmeSrc) {
    Copy-Item $ReadmeSrc $ReadmePath -Force
}

Write-Host ""
Write-Host "Build OK: $ReleaseDir\ArduinoPhysicsLab.exe" -ForegroundColor Green
Write-Host "Distribute the entire ArduinoPhysicsLab folder, not only the exe." -ForegroundColor Green
