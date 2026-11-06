@echo off
title StreamDesk Pro Launcher
cd /d "%~dp0"

echo ========================================================
echo        STREAMDESK PRO - CONTROL DESDE TU MOVIL
echo ========================================================
echo.

if exist "StreamDesk.exe" (
    start "" "StreamDesk.exe"
    exit /b
)

if exist "dist\StreamDesk\StreamDesk.exe" (
    start "" "dist\StreamDesk\StreamDesk.exe"
    exit /b
)

if exist ".venv\Scripts\python.exe" (
    start "" "http://localhost:48291/studio"
    ".venv\Scripts\python.exe" -m server.main
    exit /b
)

echo [*] Configurando entorno virtual...
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
start "" "http://localhost:48291/studio"
python -m server.main
pause
