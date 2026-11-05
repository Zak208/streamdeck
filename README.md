# 🎛️ StreamDesk Pro: Controlador Táctil 6x2 para PC desde Móvil

**StreamDesk Pro** convierte un smartphone o una tablet en una superficie de control táctil e inalámbrica para un PC con Windows, con una **cuadrícula de 6x2 por defecto (12 casillas; los faders verticales ocupan 2 casillas), configurable en Ajustes**, faders de volumen, detección de las aplicaciones instaladas y conectores para OBS, Spotify y Discord.

🔗 **Repositorio Oficial:** [https://github.com/Zak208/streamdeck](https://github.com/Zak208/streamdeck)

---

## 🌟 Características Principales

### 1. 🖥️ Aplicación de Escritorio
- **Ventana Dedicada e Integrada:** Olvídate de abrir pestañas del navegador o ver ventanas negras de comandos. StreamDesk Pro arranca directamente en una ventana de escritorio (WebView2) con tema oscuro: negro y amarillo `#F8C700` por defecto, o azul noche y cian como alternativa.
- **Servidor Integrado en Segundo Plano:** El núcleo FastAPI y el controlador de audio para Windows corren de forma silenciosa y asíncrona dentro del proceso de la aplicación.
- **Modo Portátil o Instalable:** Puedes ejecutarlo directamente desde el binario compilado o mediante los scripts de inicio rápido.

### 2. 📱 Conexión PWA para Móvil con Cuadrícula 6x2
- **12 Casillas Táctiles (2 Filas x 6 Columnas):** Diseñado especialmente para aprovechar el formato panorámico de los teléfonos móviles en horizontal (o adaptable en vertical), con botones grandes y faders analógicos.
- **PWA 100% Instalable (Progressive Web App):**
  - Incorpora Service Worker y Web App Manifest con iconos de alta resolución (`192x192` y `512x512`).
  - Botón directo en la barra superior: **📲 Instalar App** en Android (Google Chrome/Brave/Edge).
  - En iPhone (Safari): Pulsa *Compartir (⎋) -> "Añadir a la pantalla de inicio" (+)* para disfrutar de la experiencia a pantalla completa sin barras de navegación del navegador.
- **Emparejamiento Seguro con PIN y Código QR:**
  - El Studio en tu PC genera un **código PIN de 6 dígitos** (aleatorio criptográfico) y un **código QR** para vincular el móvil dentro de la misma red local Wi-Fi. Tras 5 intentos fallidos desde una misma IP se bloquea el emparejamiento durante 10 minutos.
  - **Vinculación Persistente:** Una vez emparejado, el token se guarda en el `localStorage` del móvil y la app se reconecta sola sin pedir el PIN. El PC solo guarda una huella del token, y desde Ajustes se puede revocar cualquier móvil emparejado.

### 3. 🎚️ Control Analógico de Audio y Faders
- Control de volumen maestro y control individual por aplicación en tiempo real (Discord, Spotify, OBS, juegos como Valorant, Chrome, etc.).
- Soporte para muteo táctil con feedback visual del estado del micrófono o volumen de Windows.

### 4. 🔄 Actualizaciones desde la propia app
- **Versión instalada:** Studio mira cada vez que se abre (y cada 6 horas) la última *Release* de `https://github.com/Zak208/streamdeck`. Si es más nueva que la tuya, la barra superior muestra «Hay una versión nueva» y un botón **Actualizar**. Al pulsarlo, StreamDesk descarga el instalador de esa Release, comprueba su huella SHA-256, lo ejecuta en silencio sobre tu instalación y se reinicia solo. Tu perfil, tus ajustes y tus móviles emparejados no se tocan (viven en `%APPDATA%\StreamDesk`).
- **Requisito:** la app lee las Releases sin iniciar sesión en GitHub, así que el repositorio (o el que se use para publicar) tiene que ser público. Con un repositorio privado, GitHub responde 404 y la app muestra «sin conexión».
- **Seguridad de la actualización:** solo se descarga desde la dirección de Releases de este repositorio, y si la Release no trae la huella SHA-256 o no coincide, no se instala nada. El instalador no está firmado digitalmente, así que Windows puede mostrar el aviso de SmartScreen.
- **Modo desarrollador:** si ejecutas StreamDesk desde un clon del repositorio, el botón hace `git pull --ff-only` en lugar de descargar el instalador.
- **Publicar una versión nueva (para quien mantiene el proyecto):** sube la versión en `server/paths.py` e `installer/setup.iss`, compila con PyInstaller (`StreamDesk.spec`) y con Inno Setup, y crea una Release con el tag `vX.Y.Z` adjuntando `instalador_streamdeck.exe`. GitHub calcula su huella SHA-256 automáticamente; también se puede adjuntar un `instalador_streamdeck.exe.sha256`.

---

## 📦 Instalación y Puesta en Marcha

### Opción 1: Instalación Guiada con el Instalador Oficial (Recomendado)
El proyecto incluye un instalador moderno creado con Inno Setup:

1. Descarga `instalador_streamdeck.exe` de la última [Release](https://github.com/Zak208/streamdeck/releases/latest) de GitHub. (Para generarlo tú: compila `installer/setup.iss` con Inno Setup 6 a partir de `dist\StreamDesk`.)
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

## 🧩 Acciones y editor Studio

Studio es el editor de la aplicación de escritorio: lo que puedes añadir a un lado, la cuadrícula en el centro y las propiedades de la casilla elegida al otro.

- **Botones vacíos y elegir acción:** un botón arrastrado desde «Añadir» nace vacío (no hace nada) y un fader nuevo controla el volumen general de Windows. «Elegir acción» abre una ventana con apps, acciones de cada programa, atajos y sistema, con buscador.
- **Multiacción:** varias acciones en un botón, con espera entre pasos (hasta 8). Los pasos pueden pulsar atajos, escribir texto, abrir webs y apps, o usar cualquier acción de la ventana «Elegir acción».
- **Atajo de teclado** (con botón "Grabar"), **Escribir texto** (acentos, emojis y varias líneas, con Enter opcional), **Abrir una web** y **Bloquear PC**.
- **Páginas y carpetas:** botones "Página siguiente / anterior / primera / ir a una página" para montar carpetas.
- **Páginas inteligentes:** en los ajustes de una página (⚙ junto a las pestañas) eliges un programa, y el móvil salta a esa página cuando ese programa pasa a primer plano. Si la cambias tú a mano no te la deshace hasta que cambies de programa.
- **Duplicar páginas** y **guardar o cargar una copia del perfil** (Ajustes > Perfil). La copia no incluye contraseñas, móviles emparejados ni las imágenes que hayas subido; al cargar una se guarda antes una copia del perfil actual.

## 🧱 Estados, gestos y faders a medida

- **Botón de dos estados** (sección 4 del editor del botón): cada estado tiene su título, subtítulo, color, icono y, si quieres, su propia acción. El estado 2 sin acción propia hace lo mismo que el 1. Si la acción informa de su estado (grabar en OBS, silenciar el micro), el botón sigue a esa acción.
- **Pulsación larga y doble toque con cualquier acción:** al marcar el gesto se abre la misma ventana «Elegir acción» del botón (escenas de OBS, páginas, sonidos, multiacciones...). Nada se guarda hasta que eliges una.
- **Alto del fader:** de 1 fila hasta todas las de la cuadrícula. Se cambia con + y − en el panel del fader, arrastrando su borde inferior en la vista previa o con las flechas arriba y abajo sobre ese borde. Para crecer necesita libres las casillas de debajo: no se borra nada para hacer sitio. Los perfiles guardados siguen valiendo; una versión anterior de la app rechazaría un perfil con faders de otro alto.

## 📚 Biblioteca de páginas

«+ Página» abre una biblioteca con buscador y categorías (Para empezar, Música, Directo y voz, Reuniones, Vídeo, fotos y audio, Navegador, Windows): Streamer, Gamer, Trabajo, Spotify, OBS, Discord, Zoom, Teams, Meet, VLC, PowerPoint, DaVinci Resolve, Photoshop, Audacity, Chrome, Edge, atajos de Windows, edición y estado del PC. Las de un programa se abren solas en el móvil cuando ese programa está a la vista (si ya tienes una página para ese programa, la nueva no se abre sola, para que no se pisen). Los atajos de cada programa son los que trae por defecto y funcionan sobre la ventana que tenga el foco; no los he probado dentro de cada uno.

## ➕ Acciones añadidas

- **Windows:** suspender, reiniciar, apagar (con 15 s para cancelarlo con «Cancelar apagado») y cerrar sesión, todos con confirmación; plan de energía; modo de pantalla (duplicar, extender, solo una); subir y bajar el volumen; captura de pantalla a `Imágenes\StreamDesk`. Se lanzan como órdenes fijas de Windows, nunca con texto del perfil.
- **OBS:** activar o desactivar un filtro, subir o bajar 3 dB el volumen de una fuente y refrescar una fuente de navegador.
- **Steam:** lanzar un juego instalado, elegido de tu biblioteca.
- **Webhooks:** además de GET y POST, ahora PUT (por ejemplo para una luz Elgato Key Light). Sigue limitado a los destinos que permitas.
- **Discord, sonidos sin voz:** Discord solo ofrece su panel de sonidos dentro de un canal de voz, así que leer los sonidos y reproducirlos siguen necesitando estar en uno. Pero la lista se guarda tras la primera lectura: después puedes elegir sonidos y montar botones sin estar en voz, y la ventana avisa de que muestra la copia guardada.

## 🛡️ Seguridad y fiabilidad

- **Apagar y reiniciar, con interruptor:** suspender, reiniciar, apagar y cerrar sesión no hacen nada hasta que los actives en Ajustes (están desactivados por defecto, como los comandos de consola). El apagado y el reinicio esperan 10 segundos como mínimo para poder cancelarlos. La confirmación «¿Ejecutar...?» vive en el móvil, por eso el PC no depende de ella.
- **Al cargar un perfil de otra persona**, el aviso cuenta también las acciones de apagar, abrir webs, Steam y las del segundo estado de un botón. Teclas y texto equivalen a poder ejecutar programas: carga solo perfiles de confianza.
- **Copias automáticas del perfil:** como mucho una cada media hora, en `%APPDATA%\StreamDesk\config\backups`, conservando las últimas 10.
- **Móvil:** si se corta la conexión (pantalla apagada, cambio de Wi-Fi) se detecta en unos segundos y se reconecta con esperas crecientes; mientras tanto los faders y el mute se atenúan. Un fader no cambia el volumen si lo tocas lejos de su marca sin deslizar el dedo.

## 🖐️ Gestos, confirmación y cuadrícula

- **Pulsación larga y doble toque:** en la pestaña *Acción* de una casilla marcas «Pulsación larga» o «Doble toque» y eliges qué hace cada uno (atajo, texto, web, carpeta, aplicación, multiacción...). El móvil lo avisa con dos puntitos en la casilla. Un botón con gestos espera unas décimas de segundo (280 ms para el doble toque, 500 ms para la pulsación larga) para saber cuál haces; los botones sin gestos actúan al levantar el dedo, siempre que no lo hayas deslizado (así un deslizamiento para cambiar de página no pulsa la tecla que estaba debajo).
- **Pedir confirmación:** el móvil pregunta «¿Ejecutar...?» antes de lanzar el botón (útil para bloquear el PC o cerrar un directo).
- **Desactivar un botón** sin borrarlo: se ve apagado en el móvil y el servidor rechaza la pulsación aunque llegue.
- **Abrir una carpeta:** en «Elegir acción» (Sistema). Solo rutas con letra de unidad (`D:\Proyectos`); se rechazan las rutas de red de tipo `\servidor\recurso` y las que contienen `..`. Una unidad de red mapeada con letra sí se aceptaría.
- **Atajos por aplicación:** en «Elegir acción» hay paquetes para Zoom, Teams, Meet, VLC, PowerPoint, DaVinci Resolve, Photoshop, Audacity y el navegador, además de atajos de Windows (captura, escritorios virtuales, Alt+Tab...) y de edición (copiar, pegar, deshacer...). Son atajos de teclado que van a la ventana que tenga el foco, así que **la aplicación tiene que estar a la vista** en el PC; si cambias los atajos en la propia aplicación, edítalos en la casilla. Los atajos son los que cada programa trae por defecto, no los he probado dentro de cada uno.
- **Cuadrícula a tu medida** (Ajustes > Cuadrícula): elige una de las rápidas (6x2 por defecto, 5x3, 4x3, 3x3, 4x2) o escribe tus columnas y filas, de 2 a 10 columnas y de 2 a 8 filas, con un máximo de 64 casillas (por ejemplo 4 columnas x 8 filas). Al cambiar, cada botón conserva su fila y columna si existen en la nueva cuadrícula; si no, pasa a la primera casilla libre. Los faders ocupan desde la primera fila de su columna tantas filas como tengan de alto (2 por defecto) y, si pierden su columna, pasan a las de más a la derecha manteniendo su orden. Si algo no cabe, Studio te dice cuántos elementos se han quedado fuera. Antes de convertir se guarda una copia del perfil junto a `deck_config.json`.
- **Quitar y deshacer:** arrastra un botón o un fader de la vista previa y suéltalo fuera del marco para eliminarlo (o usa Supr o la papelera). `Ctrl+Z` recupera el último que quitaste.
- **Arrastre con su forma:** las fichas de «Añadir» son un botón y un fader con el aspecto que tendrán, y lo que sigue al cursor al arrastrar mide lo mismo que una casilla de tu cuadrícula.

## 📊 Monitores del sistema

Las casillas de monitor muestran en vivo: **CPU**, **RAM**, **GPU** y **VRAM** (tarjetas NVIDIA, leídas con su librería `nvml.dll`; con otras marcas muestran *N/D*), **Red** (descarga y subida de la tarjeta que usa tu red local) y **Disco** (velocidad de lectura y escritura). El porcentaje de disco ocupado sigue disponible como acción, pero ya no está en la página Sistema por defecto.

## 🧰 Detalles que conviene saber

- **Panel derecho de Studio:** se ensancha arrastrando su borde izquierdo (doble clic para volver al ancho normal, o con las flechas del teclado) o con el botón ⤢ de su esquina. Recuerda la anchura. Las listas de opciones (escenas, playlists, sonidos...) aprovechan la altura de la ventana.
- **Monitores en el móvil:** tocar un monitor (CPU, RAM, GPU, VRAM, Red, Disco) abre una hoja «Estado del PC» con todas las lecturas en vivo. No toca nada en el PC, así que no te saca del programa que estés usando.
- **Programas que abre StreamDesk** (OBS, Steam, Discord...) se arrancan desde su propia carpeta. Antes OBS fallaba con «no encuentra en-US» porque se lanzaba desde otra carpeta, algo que no depende del idioma en que lo tengas.

## 🎨 Interfaz y primeros pasos

- **Siete temas:** negro y amarillo (por defecto), azul noche y cian, violeta, verde, rojo, rosa y naranja. Se cambia en Ajustes y se aplica también en el móvil al instante. Los botones tienen 42 colores a elegir, más un selector libre.
- **Plantillas:** `+ Página` ofrece Streamer, Gamer, Trabajo o una página en blanco. Cada plantilla usa tus atajos de Discord guardados.
- **Guardado automático:** no hay botón de guardar; el indicador de la barra superior muestra "Guardando", "Guardado" o el error.
- **Ajustes:** tema, móviles emparejados (se pueden quitar, y el móvil se desconecta en el acto), versión y la guía de bienvenida.
- **Móvil en vertical:** funciona, pero el panel de 6x2 se ve mejor en horizontal; la app avisa.

## 🔌 Conectores (OBS, Spotify, Discord y Windows)

**Apps** solo abre un programa; **Conectores** son las acciones dentro de un programa. En Studio, selecciona una casilla y abre la pestaña **Conectores**: si el botón abre una aplicación (Discord, Spotify, OBS), solo ves el conector de esa aplicación (con un enlace para ver todos); en un botón que no es una app ves todos. Cada servicio se configura una vez y sus acciones se asignan con un clic:

- **Windows:** mute del micrófono (funciona con Discord, juegos y cualquier app), mute de una app concreta, cambio de salida de audio y bloqueo del PC. No necesita configuración.
- **Comandos de consola (PowerShell o cmd):** un botón puede ejecutar hasta 8 líneas, una detrás de otra; si una falla, se detiene y el móvil muestra qué línea falló y por qué. **Vienen desactivados**: se activan con el interruptor de Ajustes de Studio (o desde el propio editor del botón). El comando corre con los permisos de tu usuario de Windows, y el móvil solo puede pulsar el botón, no elegir qué se ejecuta. Los botones nuevos piden confirmación por defecto. Las líneas guardadas viajan en el perfil exportado, pero el interruptor no, y Studio avisa al importar un perfil que traiga comandos, atajos de teclado o texto.
- **OBS Studio:** grabar, transmitir, cambiar de escena y mutear una fuente, con las escenas y fuentes reales de tu OBS. Soporta la contraseña del servidor WebSocket. Los botones de grabar y transmitir se marcan en rojo mientras están activos. Además: iniciar y parar grabación o directo por separado, modo estudio y botón de transición, escena en previsualización, elegir la transición, mostrar u ocultar una fuente de una escena, silenciar cualquier fuente de audio, búfer de repetición (alternar y guardar), cámara virtual, marcar capítulo y partir la grabación (estos dos necesitan OBS 30.2 o superior) y lanzar un atajo de OBS por su nombre. Las acciones que piden elegir algo (escena, fuente, transición) muestran las listas reales de tu OBS; si OBS está cerrado, las escribes a mano.
- **Spotify:** elige una de tus playlists (o pega un enlace) y el botón la reproduce. Hay dos caminos. **Sin cuenta conectada, o con cuenta gratuita:** StreamDesk abre la lista en la app de Spotify de tu PC y pulsa su botón de *Reproducir* (con la accesibilidad de Windows, sin usar tu cuenta ni enviar nada a Spotify); la app debe estar abierta y a la vista (no minimizada), mientras actúa no te quita el foco, y una cuenta gratuita suena en modo aleatorio y con anuncios, como la propia app. Solo lee Spotify en español («Reproducir»). **Con Premium:** crea una app gratuita en el panel de desarrolladores de Spotify, pega su Client ID, conecta la cuenta y el botón reproduce directamente por la API, sin abrir la app.
- **Discord:**
  - **Silenciar y ensordecer** pulsan los atajos globales que tú defines una vez (por defecto `CTRL+ALT+F9` y `CTRL+ALT+F10`) y creas también en Discord.
  - **Soundboard de tus servidores:** en Studio pulsa *Buscar mis sonidos*. StreamDesk lee el panel de sonidos de **tu** Discord (con la accesibilidad de Windows, UI Automation), lista los sonidos de cada servidor (se preselecciona el del canal de voz en el que estés) y al pulsar el botón pulsa ese sonido en el panel, igual que harías con el ratón, sin mover el cursor ni quitarte el foco. No usa tu cuenta, ni su token, ni bots, ni envía nada a Discord.
  - **Una página por servidor:** en la lista de sonidos de un servidor marca los que quieras y elige qué hacer con ellos: *Crear página con estos sonidos* (hasta los que quepan en tu cuadrícula), *Poner en casillas libres desde la elegida* (un botón por sonido, en orden) o *Un solo botón con todos en orden* (una multiacción de hasta 8 sonidos, 1,5 s entre cada uno). Esa página se abre sola en el móvil cuando entras a un canal de voz de ese servidor (lee el nombre del servidor en la barra de voz de Discord cada pocos segundos, y solo mientras exista alguna página así). Si mueves tú el móvil a otra página, no te lo deshace hasta que cambies de servidor o salgas y vuelvas a entrar. También se puede asignar a mano en los ajustes de cualquier página (⚙).
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

## 🔒 Seguridad

- **Studio y la configuración solo se abren desde el propio PC.** Todas las rutas de administración (configuración, subida de imágenes, PIN, actualización, conectores, perfil) responden `403` a cualquier cliente que no sea `localhost`. El móvil solo usa el WebSocket con su token.
- **Otras webs no pueden usar `localhost`:** las rutas de administración y el WebSocket local comprueban que la petición se dirige a `localhost`, `127.0.0.1` o `::1` y, en el WebSocket, que el `Origin` coincide con el servidor. Así una página abierta en tu navegador no puede pulsar botones ni leer tu perfil (ni siquiera con DNS rebinding).
- **Iconos y subidas:** las rutas de imagen solo admiten `[A-Za-z0-9_./-]`, los textos del perfil se escapan al pintarlos en el móvil, y las subidas se validan por sus primeros bytes (PNG, JPG o WEBP), no por el tipo que declare el navegador. No se publica la documentación interactiva de la API.
- **Perfiles de otra persona:** al cargar un perfil con atajos de teclado, texto o carpetas, Studio avisa antes de importarlo, porque esas acciones se ejecutan en tu PC.
- **CORS limitado** a `http://localhost` y `http://127.0.0.1` en el puerto de StreamDesk.
- **PIN de 6 dígitos** generado con `secrets`, comparado en tiempo constante y con límite de 5 intentos por IP cada 10 minutos.
- **Móviles revocables** desde Ajustes. Contraseñas y tokens de conectores se guardan en `config/settings.json` y no se envían al navegador.
- **El servidor escucha en `0.0.0.0`** para que el móvil lo alcance por Wi-Fi: úsalo en redes de confianza. Cualquiera con el token de un móvil emparejado puede pulsar botones, y los botones pueden abrir programas o pulsar atajos.

## 🏗️ Arquitectura y Estructura del Proyecto

```text
streamdeck/
├── app_desktop.py             # Ventana de escritorio (PyWebView) y arranque del servidor
├── StreamDesk.spec            # Empaquetado PyInstaller (local, no se versiona)
├── start.bat / start.ps1      # Arranque rápido en Windows
├── requirements.txt           # Dependencias Python
│
├── config/                    # Valores por defecto; tu perfil y ajustes se guardan en tu carpeta de datos
├── installer/                 # setup.iss (Inno Setup) y license.txt
├── scripts/                   # Generación de iconos SVG y PWA
├── tests/                     # Pruebas de API, autenticación, conectores, Discord, Spotify, PWA y Studio
│
├── server/                    # main.py (FastAPI y WebSocket), auth.py, actions.py, audio_controller.py,
│                              # config_manager.py, connectors, discord_ui.py, spotify_ui.py,
│                              # telemetry.py, system_scanner.py, paths.py (versión y rutas)
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

Este proyecto está bajo la Licencia MIT. Consulta el archivo [license.txt](installer/license.txt) para más detalles.
