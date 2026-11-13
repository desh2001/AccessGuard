$ErrorActionPreference = 'Stop'
$frontend = (Resolve-Path (Join-Path $PSScriptRoot '..\frontend')).Path
Push-Location $frontend
try { & npm run dev } finally { Pop-Location }
