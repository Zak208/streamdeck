# Build script for StreamDesk Pro PC (.exe & Installer)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  StreamDesk Pro - Compilador de PC (.exe)" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Localizar Python virtualenv
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "[!] Entorno virtual no encontrado en .venv. Usando Python del sistema..." -ForegroundColor Yellow
    $VenvPython = "python"
}

# 2. Localizar Inno Setup Compiler (ISCC)
$IsccPaths = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

$IsccExe = $null
foreach ($path in $IsccPaths) {
    if (Test-Path $path) {
        $IsccExe = $path
        break
    }
}

if (-not $IsccExe) {
    Write-Error "No se encontró Inno Setup 6 (ISCC.exe). Por favor instálalo para generar el instalador."
}

# 3. Compilar con PyInstaller
Write-Host "`n[1/3] Compilando ejecutable con PyInstaller (StreamDesk.spec)..." -ForegroundColor Green
& $VenvPython -m PyInstaller StreamDesk.spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Error "Error durante la compilación de PyInstaller."
}

# 4. Compilar instalador con Inno Setup
Write-Host "`n[2/3] Generando instalador con Inno Setup..." -ForegroundColor Green
& $IsccExe (Join-Path $ProjectRoot "installer\setup.iss")

if ($LASTEXITCODE -ne 0) {
    Write-Error "Error durante la compilación con Inno Setup."
}

# 5. Generar Checksum SHA-256
$InstallerPath = Join-Path $ProjectRoot "instalador_streamdeck.exe"
if (Test-Path $InstallerPath) {
    Write-Host "`n[3/3] Calculando huella SHA-256..." -ForegroundColor Green
    $Hash = (Get-FileHash -Path $InstallerPath -Algorithm SHA256).Hash.ToLower()
    $ShaFile = Join-Path $ProjectRoot "instalador_streamdeck.exe.sha256"
    "$Hash *instalador_streamdeck.exe" | Out-File -FilePath $ShaFile -Encoding ascii
    Write-Host "Instalador generado con éxito:" -ForegroundColor Green
    Write-Host "  -> $InstallerPath" -ForegroundColor White
    Write-Host "  -> SHA-256: $Hash" -ForegroundColor DarkGray
} else {
    Write-Error "No se encontró instalador_streamdeck.exe tras la compilación."
}

Write-Host "`n¡Compilación de PC completada exitosamente!" -ForegroundColor Cyan
