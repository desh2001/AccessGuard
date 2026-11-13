<#
.SYNOPSIS
  AccessGuard Stop Script - Cleanly stops all ecosystem background services.
#>
$ErrorActionPreference = 'SilentlyContinue'

Write-Host "Stopping AccessGuard ecosystem services..." -ForegroundColor Yellow

$ports = @(8000, 8001, 8002, 5173)
$stoppedCount = 0

foreach ($port in $ports) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($conn in $conns) {
            $procId = $conn.OwningProcess
            if ($procId -and $procId -ne 0) {
                $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                if ($proc) {
                    Write-Host "  Stopping $($proc.ProcessName) (PID: $procId) on port $port..." -ForegroundColor Gray
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    $stoppedCount++
                }
            }
        }
    } catch {}
}

Write-Host "Stopped $stoppedCount process(es) listening on ports 8000, 8001, 8002, 5173." -ForegroundColor Green
Write-Host "To also stop the PostgreSQL Docker container, run: docker compose down" -ForegroundColor Cyan

