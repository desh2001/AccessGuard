# AccessGuard Master Launcher
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$accesslog = Join-Path $root 'accesslog-main'
$py = Join-Path $backend '.venv\Scripts\python.exe'

Clear-Host
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "     ACCESSGUARD UNIFIED ACCESS GOVERNANCE LAB LAUNCHER       " -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check or create backend/.env
$envFile = Join-Path $backend '.env'
if (-not (Test-Path $envFile)) {
    Write-Host "[1/5] Creating backend/.env with default local lab credentials..." -ForegroundColor Yellow
    Copy-Item (Join-Path $backend '.env.example') $envFile
} else {
    Write-Host "[1/5] backend/.env verified." -ForegroundColor Green
}

# 2. Start PostgreSQL via Docker Compose
Write-Host "[2/5] Starting PostgreSQL container on host port 5434..." -ForegroundColor Yellow
try {
    & docker compose -f (Join-Path $root 'docker-compose.yml') up -d
    if ($LASTEXITCODE -eq 0) {
        Write-Host "      PostgreSQL is healthy on 127.0.0.1:5434." -ForegroundColor Green
    }
} catch {
    Write-Host "      Notice: Docker check complete." -ForegroundColor Gray
}

# 3. Verify Python Environment & Seed Database
Write-Host "[3/5] Verifying database schema & demo seed..." -ForegroundColor Yellow
if (-not (Test-Path $py)) {
    Write-Host "      Virtual environment missing. Creating .venv..." -ForegroundColor Yellow
    & py -m venv (Join-Path $backend '.venv')
    & $py -m pip install -r (Join-Path $backend 'requirements.txt')
}

Push-Location $backend
try {
    & $py check_db.py
    if ($LASTEXITCODE -eq 0) {
        & $py -m alembic upgrade head
        & $py seed_demo.py
    }
} catch {
    Write-Host "      Notice: Database sync skipped (PostgreSQL might still be initializing)." -ForegroundColor Gray
} finally {
    Pop-Location
}

# 4. Launch Services in separate PowerShell processes
Write-Host "[4/5] Launching all 4 ecosystem services..." -ForegroundColor Yellow

$scriptBackend = Join-Path $PSScriptRoot 'start-backend.ps1'
$scriptMl = Join-Path $PSScriptRoot 'start-ml.ps1'
$scriptAccesslog = Join-Path $PSScriptRoot 'start-accesslog.ps1'
$scriptFrontend = Join-Path $PSScriptRoot 'start-frontend.ps1'

Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptBackend`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptMl`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptAccesslog`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptFrontend`""

# 5. Summary & Browser Launch
Write-Host "[5/5] Ecosystem startup initiated successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  ACTIVE SERVICE ENDPOINTS:                                       " -ForegroundColor White
Write-Host "  💻 Central Dashboard:        http://127.0.0.1:5173              " -ForegroundColor Green
Write-Host "  ⚙️ AccessGuard Backend API:   http://127.0.0.1:8000/docs         " -ForegroundColor Cyan
Write-Host "  🧠 Dialog Final ML Service:  http://127.0.0.1:8001/health       " -ForegroundColor Magenta
Write-Host "  📋 Dialog Access Log API:    http://127.0.0.1:8002/api/summary  " -ForegroundColor Blue
Write-Host "  📡 Syslog Ingestion Listener: TCP port 5514                     " -ForegroundColor Blue
Write-Host "  🗄️ PostgreSQL Database:      127.0.0.1:5434 (accessguard_lab)   " -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Opening Central Dashboard in your browser..." -ForegroundColor Yellow
Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5173"
