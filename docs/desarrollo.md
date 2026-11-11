# Desarrollo

## Ejecutar desde el código fuente

Si prefieres ejecutar el proyecto desde el código fuente o los scripts auxiliares:

1. **Clonar el repositorio:**
   ```powershell
   git clone https://github.com/Zak208/streamdeck.git
   cd streamdeck
   ```
2. **Iniciar la aplicación:**
   - Haz doble clic en **`start.bat`** (o ejecuta `.\start.ps1` en PowerShell).
   - El script detecta automáticamente si existe el ejecutable compilado `dist\StreamDesk\StreamDesk.exe` para lanzarlo directamente, o configurará el entorno virtual `.venv` instalando los requisitos de `requirements.txt`.
3. **Probar la ventana y la bandeja desde el código:** `.venv\Scripts\python.exe app_desktop.py` (con `--background` arranca oculta, como lo hace Windows al iniciar sesión). `start.ps1` solo arranca el servidor y abre Studio en el navegador, sin ventana ni bandeja.
4. **Acceso manual:**
   - La ventana de escritorio se abrirá de forma automática.
   - También puedes acceder al panel de configuración Studio desde cualquier navegador en el PC visitando:
     👉 `http://localhost:48291/studio`

## Estructura del proyecto

```text
streamdeck/
├── app_desktop.py             # Ventana de escritorio (PyWebView) y arranque del servidor
├── StreamDesk.spec            # Empaquetado PyInstaller
├── start.bat / start.ps1      # Arranque rápido en Windows
├── requirements.txt           # Dependencias Python
│
├── .github/workflows/         # tests.yml (pruebas), build-pc.yml (instalador), build-apk.yml (app de Android)
├── android/                   # App nativa de Android (WebView que encuentra el PC en la red)
├── config/                    # Valores por defecto; tu perfil y ajustes se guardan en tu carpeta de datos
├── docs/                      # Documentación detallada (esta carpeta) e imágenes del README
├── installer/                 # setup.iss (Inno Setup) y license.txt
├── scripts/                   # Compilar PC y APK, iconos, y check_desktop.py (prueba de la ventana y la bandeja)
├── tests/                     # Pruebas de API, autenticación, conectores, Discord, Spotify, PWA y Studio
│
├── server/                    # main.py (FastAPI y WebSocket), auth.py, actions.py, audio_controller.py,
│                              # config_manager.py, connectors, discord_ui.py, spotify_ui.py,
│                              # telemetry.py, system_scanner.py, paths.py (versión y rutas),
│                              # desktop.py (bandeja, inicio con Windows, instancia única),
│                              # permissions.py (móviles limitados), audit.py (historial de botones),
│                              # settings_store.py (ajustes con secretos cifrados), firewall.py, diagnostics.py
└── static/
    ├── css/                   # tokens.css (tema), style.css (móvil), studio.css (Studio)
    ├── js/                    # streamdeck.js (móvil), studio*.js (editor), monitors.js, phone-settings.js
    ├── icons/                 # Iconos SVG y PNG (PWA 192/512)
    ├── manifest.json          # Manifiesto PWA
    ├── service-worker.js      # Caché de la interfaz (las acciones necesitan conexión con el PC)
    ├── index.html             # Interfaz del móvil
    └── studio.html            # Editor Studio
```

Generados y no versionados: `dist/`, `build/`, `instalador_streamdeck.exe`.

## Pruebas

```powershell
python -m unittest discover -s tests
Get-ChildItem static\js\*.js | ForEach-Object { node --check $_.FullName }
python scripts\check_desktop.py
```

- Las pruebas usan una carpeta de datos temporal (`STREAMDESK_DATA_DIR`): nunca tocan tu perfil ni tus móviles emparejados. Corren en Windows porque el servidor usa APIs de Windows.
- `scripts\check_desktop.py` abre la aplicación de verdad con un perfil temporal y comprueba el arranque oculto, la X que oculta la ventana en la bandeja y el segundo lanzamiento. Acepta la ruta de un `StreamDesk.exe` compilado. Necesita una sesión de escritorio y WebView2.

## Compilar

```powershell
scripts\build_pc.ps1    # PyInstaller + Inno Setup 6: genera instalador_streamdeck.exe y su .sha256
scripts\build_apk.ps1   # la app de Android (necesita el SDK de Android)
```

Las Releases se compilan solas en GitHub: ver [Actualizaciones y publicación](actualizaciones-y-publicacion.md).

## Tecnologías

- **Backend:** Python 3.12, FastAPI, Uvicorn, WebSockets.
- **Desktop Wrapper:** PyWebView con motor Microsoft Edge WebView2.
- **Audio API:** Core Audio APIs de Windows (`pycaw`, `comtypes`).
- **Frontend:** HTML5 semántico, CSS3 Flexbox/Grid con diseño responsivo, JavaScript ES6+ asíncrono.
- **PWA:** Web App Manifest v3, Service Workers, Touch Events API.
- **Empaquetado:** PyInstaller y Inno Setup Compiler 6.
