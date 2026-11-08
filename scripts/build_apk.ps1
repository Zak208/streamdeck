# Build script for StreamDesk Pro Android APK
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AndroidDir = Join-Path $ProjectRoot "android"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  StreamDesk Pro - Compilador Android APK" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Set-Location $AndroidDir

# Verificar Gradle o Gradle wrapper
$GradleCmd = Get-Command gradle -ErrorAction SilentlyContinue
if (-not $GradleCmd) {
    if (Test-Path "gradlew.bat") {
        $GradleCmd = ".\gradlew.bat"
    } else {
        Write-Host "[!] Gradle local no encontrado. Puedes compilar el APK en GitHub Actions con el workflow recién creado o instalar el Android SDK." -ForegroundColor Yellow
        exit 0
    }
} else {
    $GradleCmd = "gradle"
}

Write-Host "`nIniciando compilación del APK con Gradle..." -ForegroundColor Green
& $GradleCmd assembleDebug

if ($LASTEXITCODE -eq 0) {
    $ApkPath = Join-Path $AndroidDir "app\build\outputs\apk\debug\app-debug.apk"
    if (Test-Path $ApkPath) {
        $DestPath = Join-Path $ProjectRoot "StreamDesk.apk"
        Copy-Item -Path $ApkPath -Destination $DestPath -Force
        Write-Host "`n¡APK generado exitosamente en la raíz del proyecto!" -ForegroundColor Green
        Write-Host "  -> $DestPath" -ForegroundColor White
    }
} else {
    Write-Host "`nNota: Si no tienes el Android SDK instalado en tu PC, el workflow de GitHub Actions (.github/workflows/build-apk.yml) compilará el archivo .apk automáticamente en la nube." -ForegroundColor Yellow
}
