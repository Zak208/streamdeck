# 🎛️ StreamDesk Pro — Controlador Táctil 6x2 para PC desde Móvil

**StreamDesk Pro** es una solución integral y moderna para transformar cualquier smartphone o tablet en una Stream Deck profesional táctil e inalámbrica para Windows, con una **cuadrícula de 6x2 (12 casillas con faders verticales de 2 espacios)**, faders de volumen vertical analógicos, autodescubrimiento inteligente de aplicaciones y sistema de auto-actualización directa con GitHub.

Cuenta con una **aplicación nativa de escritorio (estilo Spotify)** desarrollada con FastAPI y WebView2, sin necesidad de mantener consolas abiertas ni depender de navegadores externos.

🔗 **Repositorio Oficial:** [https://github.com/Zak208/streamdeck](https://github.com/Zak208/streamdeck)

---

## 🌟 Características Principales

### 1. 🖥️ Aplicación Nativa de Escritorio (Estilo Spotify)
- **Ventana Dedicada e Integrada:** Olvídate de abrir pestañas del navegador o ver ventanas negras de comandos. StreamDesk Pro arranca directamente en una ventana nativa de escritorio moderna acelerada por hardware (WebView2) con tema oscuro profesional (`#070a10`).
- **Servidor Integrado en Segundo Plano:** El núcleo FastAPI y el controlador de audio para Windows corren de forma silenciosa y asíncrona dentro del proceso de la aplicación.
- **Modo Portátil o Instalable:** Puedes ejecutarlo directamente desde el binario compilado o mediante los scripts de inicio rápido.

### 2. 📱 Conexión PWA para Móvil con Cuadrícula 6x2
- **12 Casillas Táctiles (2 Filas x 6 Columnas):** Diseñado especialmente para aprovechar el formato panorámico de los teléfonos móviles en horizontal (o adaptable en vertical), ofreciendo hasta 16 accesos directos simultáneos y faders analógicos con botones grandes y cómodos.
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
  - `🟢 v2.11.0 · al día`: Tu instalación coincide con el último commit del repositorio oficial.
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

## 📲 Instalar StreamDesk en el móvil como app

Abre la dirección que muestra Studio (o escanea el QR) y pulsa el engranaje: **Ajustes > Instalar como app** te da los pasos exactos para tu móvil.

- **iPhone (Safari):** Compartir > *Añadir a pantalla de inicio*. Funciona sin más. La app instalada guarda sus datos aparte de Safari, así que pedirá el PIN una vez.
- **Android (Chrome):** Chrome solo ofrece *Instalar app* en webs **https**, y StreamDesk se sirve por `http` dentro de tu red. Para activarlo una vez: abre `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, pega la dirección de StreamDesk (por ejemplo `http://192.168.2.81:48291`), pon *Enabled* y pulsa *Relaunch*. Si la IP de tu PC cambia, repite el paso con la nueva (conviene fijarla en el router).
- **Si no se instala:** en los ajustes del móvil, el botón *Comprobar por qué no se instala* revisa dirección segura, service worker, manifiesto e iconos y genera un informe que puedes copiar. Las causas habituales son no tener internet (Android genera la app a través de los servidores de Google), Chrome desactualizado o sin Google Play Services.
- **Sin instalar:** menú ⋮ > *Añadir a la pantalla de inicio* crea un acceso directo, y el botón de **pantalla completa** quita las barras. En `http` Chrome no permite mantener la pantalla encendida.

**Móvil en vertical u horizontal:** en vertical los botones se reorganizan en 3 columnas; en horizontal se aprovecha toda la altura. El menú de ajustes del móvil permite saltar de página, ver el estado de la conexión y vincular con otro PC.

## 🧩 Acciones al estilo Stream Deck

Inspirado en la aplicación oficial de Elgato:

- **Biblioteca de acciones** en el panel lateral, con buscador y categorías. Arrastra una acción a una casilla, o pulsa la acción con una casilla elegida.
- **Multiacción:** varias acciones en un botón, con espera entre pasos (hasta 8). Los pasos pueden pulsar atajos, escribir texto, abrir webs y apps, o usar cualquier acción de la biblioteca.
- **Atajo de teclado** (con botón "Grabar"), **Escribir texto** (acentos, emojis y varias líneas, con Enter opcional), **Abrir una web** y **Bloquear PC**.
- **Páginas y carpetas:** botones "Página siguiente / anterior / primera / ir a una página" para montar carpetas.
- **Páginas inteligentes:** en los ajustes de una página (⚙ junto a las pestañas) eliges un programa, y el móvil salta a esa página cuando ese programa pasa a primer plano. Si la cambias tú a mano no te la deshace hasta que cambies de programa.
- **Duplicar páginas** y **guardar o cargar una copia del perfil** (Ajustes > Perfil). La copia no incluye contraseñas, móviles emparejados ni las imágenes que hayas subido; al cargar una se guarda antes una copia del perfil actual.

## 📊 Monitores del sistema

Las casillas de monitor muestran en vivo: **CPU**, **RAM**, **GPU** y **VRAM** (tarjetas NVIDIA, leídas con su librería `nvml.dll`; con otras marcas muestran *N/D*), **Red** (descarga y subida de la tarjeta que usa tu red local) y **Disco** (velocidad de lectura y escritura). El porcentaje de disco ocupado sigue disponible como acción, pero ya no está en la página Sistema por defecto.

## 🧰 Detalles que conviene saber

- **Panel derecho de Studio:** se ensancha arrastrando su borde izquierdo (doble clic para volver al ancho normal, o con las flechas del teclado) o con el botón ⤢ de su esquina. Recuerda la anchura. Las listas de opciones (escenas, playlists, sonidos...) aprovechan la altura de la ventana.
- **Monitores en el móvil:** tocar un monitor (CPU, RAM, GPU, VRAM, Red, Disco) abre una hoja «Estado del PC» con todas las lecturas en vivo. No toca nada en el PC, así que no te saca del programa que estés usando.
- **Programas que abre StreamDesk** (OBS, Steam, Discord...) se arrancan desde su propia carpeta. Antes OBS fallaba con «no encuentra en-US» porque se lanzaba desde otra carpeta, algo que no depende del idioma en que lo tengas.

## 🎨 Interfaz y primeros pasos

- **Dos temas:** negro y amarillo (por defecto) o azul noche y cian. Se cambia en Ajustes y se aplica también en el móvil al instante.
- **Plantillas:** `+ Página` ofrece Streamer, Gamer, Trabajo o una página en blanco. Cada plantilla usa tus atajos de Discord guardados.
- **Guardado automático:** no hay botón de guardar; el indicador de la barra superior muestra "Guardando", "Guardado" o el error.
- **Ajustes:** tema, móviles emparejados (se pueden quitar, y el móvil se desconecta en el acto), versión y la guía de bienvenida.
- **Móvil en vertical:** funciona, pero el panel de 6x2 se ve mejor en horizontal; la app avisa.

## 🔌 Conectores (OBS, Spotify, Discord y Windows)

En Studio, selecciona una casilla y abre la pestaña **Conectores**. Cada servicio se configura una vez y sus acciones se asignan con un clic:

- **Windows:** mute del micrófono (funciona con Discord, juegos y cualquier app), mute de una app concreta y cambio de salida de audio. No necesita configuración.
- **OBS Studio:** grabar, transmitir, cambiar de escena y mutear una fuente, con las escenas y fuentes reales de tu OBS. Soporta la contraseña del servidor WebSocket. Los botones de grabar y transmitir se marcan en rojo mientras están activos.
- **Spotify:** elige una de tus playlists (o pega un enlace) y el botón la reproduce. Hay dos caminos. **Sin cuenta conectada, o con cuenta gratuita:** StreamDesk abre la lista en la app de Spotify de tu PC y pulsa su botón de *Reproducir* (con la accesibilidad de Windows, sin usar tu cuenta ni enviar nada a Spotify); la app debe estar abierta y a la vista (no minimizada), mientras actúa no te quita el foco, y una cuenta gratuita suena en modo aleatorio y con anuncios, como la propia app. Solo lee Spotify en español («Reproducir»). **Con Premium:** crea una app gratuita en el panel de desarrolladores de Spotify, pega su Client ID, conecta la cuenta y el botón reproduce directamente por la API, sin abrir la app.
- **Discord:**
  - **Silenciar y ensordecer** pulsan los atajos globales que tú defines una vez (por defecto `CTRL+ALT+F9` y `CTRL+ALT+F10`) y creas también en Discord.
  - **Soundboard de tus servidores:** en Studio pulsa *Buscar mis sonidos*. StreamDesk lee el panel de sonidos de **tu** Discord (con la accesibilidad de Windows, UI Automation), lista los sonidos de cada servidor (se preselecciona el del canal de voz en el que estés) y al pulsar el botón pulsa ese sonido en el panel, igual que harías con el ratón, sin mover el cursor ni quitarte el foco. No usa tu cuenta, ni su token, ni bots, ni envía nada a Discord.
  - **Una página por servidor:** en la lista de sonidos de un servidor marca los que quieras (hasta 12) y pulsa *Crear página*. Esa página se abre sola en el móvil cuando entras a un canal de voz de ese servidor (lee el nombre del servidor en la barra de voz de Discord cada pocos segundos, y solo mientras exista alguna página así). Si mueves tú el móvil a otra página, no te lo deshace hasta que cambies de servidor o salgas y vuelvas a entrar. También se puede asignar a mano en los ajustes de cualquier página (⚙).
  - **No te quita el foco:** pulsar o leer algo en Discord con las herramientas de accesibilidad de Windows hace que Discord se ponga en primer plano (medido: cada acción lo hacía). Mientras StreamDesk actúa, marca la ventana de Discord como «no activable» y la deja como estaba al terminar, así que tu juego o tu programa principal siguen con el foco. Lo ideal es tener Discord en tu otra pantalla.
  - **Si un botón no hace nada:** el móvil avisa con un mensaje (sin conexión con el PC, botón que no está en la página activa, Discord minimizado...) y el motivo queda en Ajustes > Diagnóstico de Studio.
  - **Requisitos y límites:** Discord abierto y visible (puede estar detrás de otras ventanas o en otra pantalla, pero no minimizado ni cerrado a la bandeja: StreamDesk no restaura ventanas porque eso podría quitarte el foco) y tú dentro de un canal de voz. Lee los textos de Discord en **español** («Reproducir…», «Abrir panel de sonidos»); en otro idioma habría que cambiarlos en `server/discord_ui.py`. Un rediseño de Discord puede romperlo: los errores dicen qué no encuentra. Los sonidos se buscan por su nombre, así que si los renombras hay que volver a buscarlos.

Las contraseñas y tokens se guardan en `config/settings.json` dentro de tu carpeta de datos y nunca se envían al navegador ni al móvil.

---

## 📲 Conectar tu Móvil al StreamDesk

1. Asegúrate de que tu PC y tu teléfono móvil estén conectados a la **misma red Wi-Fi**.
2. En la ventana de escritorio de StreamDesk Pro en tu PC, haz clic en el botón de ajustes/enlace para visualizar la IP local y el **código PIN de 6 dígitos** (o el código QR).
3. Abre la cámara de tu móvil para escanear el QR o ingresa manualmente la dirección IP mostrada (por ejemplo: `http://192.168.1.XX:48291`).
4. Introduce el código PIN una única vez.
5. Pulsa el botón **📲 Instalar App** para añadir StreamDesk Pro a la pantalla de inicio de tu smartphone y úsalo a pantalla completa como un periférico táctil físico de 6x2.

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
│   └── deck_config.json       # Configuración guardada de las 12 casillas (cuadrícula 6x2)
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
│   ├── discord_ui.py          # Lee y pulsa el panel de sonidos de Discord (UI Automation)
│   ├── spotify_ui.py          # Pulsa Reproducir en la app de Spotify (cuentas gratuitas o sin conectar)
│   ├── telemetry.py           # CPU, RAM, GPU/VRAM (NVML), red y velocidad de disco
│   ├── main.py                # Servidor FastAPI, WebSockets y auto-actualizador de GitHub
│   └── system_scanner.py      # Escáner automático de ejecutables y rutas de apps instaladas
│
├── dist/StreamDesk/           # Binarios empaquetados listos para distribución independiente
└── static/
    ├── css/
    │   ├── style.css          # Estilos de la interfaz móvil (cuadrícula 6x2)
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
