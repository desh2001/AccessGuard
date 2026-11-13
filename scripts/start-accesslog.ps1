# Start Dialog Access Log Ingestion Service on port 8002
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$accesslog = Join-Path $root 'accesslog-main'
$backend = Join-Path $root 'backend'
$py = Join-Path $backend '.venv\Scripts\python.exe'

Write-Host "==========================================================" -ForegroundColor Blue
Write-Host "  Starting Dialog Access Log & Syslog Service..." -ForegroundColor Blue
Write-Host "  API URL: http://127.0.0.1:8002" -ForegroundColor Cyan
Write-Host "  Syslog TCP Listener: port 5514" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Blue

Push-Location $accesslog
try {
    & $py standalone_api.py
} finally { Pop-Location }

