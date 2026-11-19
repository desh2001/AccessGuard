# Start AccessGuard Quarterly ML Microservice (Aegis V9/V10) on port 8001
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$mlBackend = Join-Path $root 'ml\backend'
$py = Join-Path $mlBackend '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    $py = Join-Path $root 'backend\.venv\Scripts\python.exe'
}
if (-not (Test-Path $py)) {
    $py = 'python'
}

$env:ML_SERVICE_TOKEN = if ($env:ML_SERVICE_TOKEN) { $env:ML_SERVICE_TOKEN } else { 'development-token-32-chars-long-minimum-key' }
$env:AEGIS_PLATFORM_MODEL_DIR = Join-Path $mlBackend 'ml_artifacts\platforms'
$env:PYTHONPATH = $mlBackend

Write-Host "==========================================================" -ForegroundColor Magenta
Write-Host "  Starting AccessGuard Quarterly ML Microservice (V9/V10)..." -ForegroundColor Magenta
Write-Host "  URL: http://127.0.0.1:8001" -ForegroundColor Cyan
Write-Host "  Model Dir: $env:AEGIS_PLATFORM_MODEL_DIR" -ForegroundColor DarkGray
Write-Host "==========================================================" -ForegroundColor Magenta

Push-Location $mlBackend
try {
    & $py -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
} finally { Pop-Location }

