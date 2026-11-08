@echo off
title StreamDesk Pro - Compilador Android APK
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_apk.ps1"
pause
