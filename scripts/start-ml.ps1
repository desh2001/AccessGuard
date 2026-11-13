# Start Dialog Final ML Microservice on port 8001
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'

Write-Host "==========================================================" -ForegroundColor Magenta
Write-Host "  Starting Dialog Final ML Microservice (Aegis V8)..." -ForegroundColor Magenta
Write-Host "  URL: http://127.0.0.1:8001" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Magenta

Push-Location $backend
try {
    & $py -m uvicorn mock_ml_service:app --host 127.0.0.1 --port 8001 --reload
} finally { Pop-Location }

