# 🎛️ StreamDesk Pro — Controlador Táctil 2x8 para PC desde Móvil

**StreamDesk Pro** es una solución integral y moderna para transformar cualquier smartphone o tablet en una Stream Deck profesional táctil e inalámbrica para Windows, con una **cuadrícula de 2x8 (16 casillas configurables)**, faders de volumen vertical analógicos, autodescubrimiento inteligente de aplicaciones y sistema de auto-actualización directa con GitHub.

Cuenta con una **aplicación nativa de escritorio (estilo Spotify)** desarrollada con FastAPI y WebView2, sin necesidad de mantener consolas abiertas ni depender de navegadores externos.

🔗 **Repositorio Oficial:** [https://github.com/Zak208/streamdeck](https://github.com/Zak208/streamdeck)

---

## 🌟 Características Principales

### 1. 🖥️ Aplicación Nativa de Escritorio (Estilo Spotify)
- **Ventana Dedicada e Integrada:** Olvídate de abrir pestañas del navegador o ver ventanas negras de comandos. StreamDesk Pro arranca directamente en una ventana nativa de escritorio moderna acelerada por hardware (WebView2) con tema oscuro profesional (`#070a10`).
- **Servidor Integrado en Segundo Plano:** El núcleo FastAPI y el controlador de audio para Windows corren de forma silenciosa y asíncrona dentro del proceso de la aplicación.
- **Modo Portátil o Instalable:** Puedes ejecutarlo directamente desde el binario compilado o mediante los scripts de inicio rápido.

### 2. 📱 Conexión PWA para Móvil con Cuadrícula 2x8
- **16 Casillas Táctiles (2 Filas x 8 Columnas):** Diseñado especialmente para aprovechar el formato panorámico de los teléfonos móviles en horizontal (o adaptable en vertical), ofreciendo hasta 16 accesos directos simultáneos y faders analógicos con botones grandes y cómodos.
- **PWA 100% Instalable (Progressive Web App):**
  - Incorpora Service Worker y Web App Manifest con iconos de alta resolución (`192x192` y `512x512`).
  - Botón directo en la barra superior: **📲 Instalar App** en Android (Google Chrome/Brave/Edge).
  - En iPhone (Safari): Pulsa *Compartir (⎋) -> "Añadir a la pantalla de inicio" (+)* para disfrutar de la experiencia a pantalla completa sin barras de navegación del navegador.
- **Emparejamiento Seguro con PIN y Código QR:**
  - El Studio en tu PC genera un **código PIN de 6 dígitos** y un **código QR** para vincular el móvil en segundos dentro de la misma red local Wi-Fi.
  - **Vinculación Persistente:** Una vez emparejado, el token se almacena de forma segura en `localStorage`; la app se reconecta automáticamente en 0 segundos en futuros inicios sin solicitar PIN nuevamente.

### 3. 🎚️ Control Analógico de Audio y Faders
- Control de volumen maestro y control individual por aplicación en tiempo real (Discord, Spotify, OBS, juegos como Valorant, Chrome, etc.).
- Soporte para muteo táctil con feedback visual del estado del micrófono o volumen de Windows.

### 4. 🔄 Auto-Actualizador Integrado con GitHub
- En la barra superior del PC Studio se encuentra el **cilindro indicador de estado de versión**:
  - `🟢 StreamDesk v2.1.0 (Al día)`: Tu instalación coincide con el último commit del repositorio oficial.
  - `🟡 ¡Actualización en GitHub! [Actualizar 🚀]`: El sistema detecta automáticamente nuevos commits en `https://github.com/Zak208/streamdeck`.
- Al pulsar el botón de actualizar, el sistema ejecuta `/api/system/apply-update` sincronizando el código automáticamente sin necesidad de reinstalar manualmente.

---

## 📦 Instalación y Puesta en Marcha

### Opción 1: Instalación Guiada con el Instalador Oficial (Recomendado)
El proyecto incluye un instalador moderno creado con Inno Setup:

1. Descarga o localiza el archivo ejecutable:
   ```text
   instalador_streamdeck.exe
   ```
2. Ejecuta el archivo con doble clic. El instalador:
   - Configura la aplicación en tu directorio de usuario (`%LOCALAPPDATA%\Programs\StreamDesk Pro`) sin requerir permisos elevados de administrador.
   - Crea automáticamente los accesos directos en el **Escritorio** y en el **Menú Inicio**.
   - Incluye todos los componentes nativos, librerías WebView2, iconos y archivos estáticos listos para producción.
3. Inicia **StreamDesk Pro** desde el acceso directo y la app se abrirá en su ventana nativa de escritorio.

---

### Opción 2: Modo Desarrollador / Portátil
Si prefieres ejecutar el proyecto desde el código fuente o los scripts auxiliares:

1. **Clonar el repositorio:**
   ```powershell
   git clone https://github.com/Zak208/streamdeck.git
   cd streamdeck
   ```
2. **Iniciar la aplicación:**
   - Haz doble clic en **`start.bat`** (o ejecuta `.\start.ps1` en PowerShell).
   - El script detecta automáticamente si existe el ejecutable compilado `dist\StreamDesk\StreamDesk.exe` para lanzarlo directamente, o configurará el entorno virtual `.venv` instalando los requisitos de `requirements.txt`.
3. **Acceso manual:**
   - La ventana de escritorio se abrirá de forma automática.
   - También puedes acceder al panel de configuración Studio desde cualquier navegador en el PC visitando:
     👉 `http://localhost:48291/studio`

---

## 📲 Conectar tu Móvil al StreamDesk

1. Asegúrate de que tu PC y tu teléfono móvil estén conectados a la **misma red Wi-Fi**.
2. En la ventana de escritorio de StreamDesk Pro en tu PC, haz clic en el botón de ajustes/enlace para visualizar la IP local y el **código PIN de 6 dígitos** (o el código QR).
3. Abre la cámara de tu móvil para escanear el QR o ingresa manualmente la dirección IP mostrada (por ejemplo: `http://192.168.1.XX:48291`).
4. Introduce el código PIN una única vez.
5. Pulsa el botón **📲 Instalar App** para añadir StreamDesk Pro a la pantalla de inicio de tu smartphone y úsalo a pantalla completa como un periférico táctil físico de 2x8.

---

## 🏗️ Arquitectura y Estructura del Proyecto

```text
streamdeck/
├── app_desktop.py             # Lanzador de la ventana nativa de escritorio (PyWebView + FastAPI)
├── instalador_streamdeck.exe   # Instalador compilado para Windows (Inno Setup)
├── StreamDesk.spec            # Especificación de empaquetado PyInstaller
├── start.bat                  # Script de inicio rápido inteligente para Windows
├── start.ps1                  # Script PowerShell de inicio rápido
├── requirements.txt           # Dependencias Python (FastAPI, PyWebView, Uvicorn, etc.)
│
├── config/
│   └── deck_config.json       # Configuración guardada de las 16 casillas (cuadrícula 2x8)
│
├── installer/
│   ├── license.txt            # Licencia del instalador
│   └── setup.iss              # Script de compilación de Inno Setup
│
├── server/
│   ├── actions.py             # Ejecución de teclas rápidas, atajos y lanzamiento de apps
│   ├── audio_controller.py    # Control de volumen de Windows y sesiones de audio
│   ├── auth.py                # Sistema de autenticación por PIN, tokens y rate-limiting
│   ├── config_manager.py      # Gestión de lectura y guardado de deck_config.json
│   ├── main.py                # Servidor FastAPI, WebSockets y auto-actualizador de GitHub
│   └── system_scanner.py      # Escáner automático de ejecutables y rutas de apps instaladas
│
├── dist/StreamDesk/           # Binarios empaquetados listos para distribución independiente
└── static/
    ├── css/
    │   ├── style.css          # Estilos de la interfaz móvil (cuadrícula 2x8)
    │   └── studio.css         # Estilos del panel de configuración de PC Studio
    ├── js/
    │   ├── streamdeck.js      # Controlador de eventos táctiles, faders y WebSocket móvil
    │   └── studio.js          # Lógica interactiva del simulador, drag-and-drop y actualizador
    ├── icons/                 # Iconos SVG y PNG de alta resolución (PWA 192/512px e ICO)
    ├── manifest.json          # Manifiesto PWA para instalación móvil
    ├── service-worker.js      # Caché y capacidades offline de la PWA
    ├── index.html             # Interfaz web móvil táctil
    └── studio.html            # Interfaz de edición y configuración para PC
```

---

## 🛠️ Tecnologías Utilizadas

- **Backend:** Python 3.12, FastAPI, Uvicorn, WebSockets.
- **Desktop Wrapper:** PyWebView con motor Microsoft Edge WebView2.
- **Audio API:** Core Audio APIs de Windows (`pycaw`, `comtypes`).
- **Frontend:** HTML5 semántico, CSS3 Flexbox/Grid con diseño responsivo, JavaScript ES6+ asíncrono.
- **PWA:** Web App Manifest v3, Service Workers, Touch Events API.
- **Empaquetado:** PyInstaller y Inno Setup Compiler 6.

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo [license.txt](file:///installer/license.txt) para más detalles.
