@echo off
title StreamDesk Pro Launcher
cd /d "%~dp0"

echo ========================================================
echo        STREAMDESK PRO - CONTROL DESDE TU MOVIL
echo ========================================================
echo.

if not exist ".venv" (
    echo [*] Creando entorno virtual e instalando dependencias...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo [*] Abriendo Panel Studio en el navegador...
start http://localhost:48291/studio

echo [*] Iniciando servidor en puerto 48291...
python -m server.main

pause

