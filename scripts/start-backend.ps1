$ErrorActionPreference = 'Stop'
$backend = (Resolve-Path (Join-Path $PSScriptRoot '..\backend')).Path
Push-Location $backend
try {
    & (Join-Path $backend '.venv\Scripts\python.exe') -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
} finally { Pop-Location }
