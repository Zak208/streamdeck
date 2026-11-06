# StreamDesk Pro Launcher for PowerShell
Set-Location $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "       STREAMDESK PRO - CONTROL DESDE TU MOVIL          " -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

if (-Not (Test-Path ".venv")) {
    Write-Host "[*] Configurando entorno virtual..." -ForegroundColor Gray
    python -m venv .venv
    & ".\.venv\Scripts\Activate.ps1"
    pip install -r requirements.txt
} else {
    & ".\.venv\Scripts\Activate.ps1"
}

Start-Process "https://localhost:48291/studio"
Write-Host "[*] Servidor activo en puerto 48291 (HTTPS)." -ForegroundColor Green
& ".\.venv\Scripts\python.exe" -m server.main
