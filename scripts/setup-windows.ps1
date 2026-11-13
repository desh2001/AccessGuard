# AccessGuard: run from any directory. Requires Docker Desktop, Python 3.11+ and Node.js.
# Does not stop or delete any existing PostgreSQL container or volume.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
if (-not (Test-Path (Join-Path $backend '.env'))) {
    Copy-Item (Join-Path $backend '.env.example') (Join-Path $backend '.env')
    Write-Host 'Created backend/.env with local DEMO credentials (port 5434).'
}
Write-Host 'Starting NEW PostgreSQL container on Windows host port 5434...'
& docker compose -f (Join-Path $root 'docker-compose.yml') up -d
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose could not start. If 5434 is busy, stop only the old accessguard-phase2-postgres container (do not delete volumes).' }
Push-Location $backend
try {
    if (-not (Test-Path '.venv\Scripts\python.exe')) { & py -m venv .venv }
    $py = Join-Path $backend '.venv\Scripts\python.exe'
    & $py -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
    & $py -m check_db
    if ($LASTEXITCODE -ne 0) { throw 'Database not ready or password mismatch' }
    & $py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed' }
    & $py -m seed_demo
    if ($LASTEXITCODE -ne 0) { throw 'Demo seed failed' }
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
} finally { Pop-Location }
Push-Location $frontend
try {
    & npm install
    if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
} finally { Pop-Location }
Write-Host 'SETUP COMPLETE. Use scripts/start-backend.ps1 and scripts/start-frontend.ps1 in separate PowerShell terminals.' -ForegroundColor Green
