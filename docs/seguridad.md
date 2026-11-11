# Seguridad

Qué protege StreamDesk, qué no, y los controles que tienes sobre tus móviles.

## Control de los móviles y diagnóstico

- **Móvil limitado:** en *Ajustes > Móviles emparejados* puedes pulsar **Limitar** en un móvil (uno prestado, la tablet de un niño). Ese móvil sigue usando todos sus botones menos apagar, reiniciar, suspender o cerrar sesión el PC y los comandos de consola. La comprobación está en el PC, no en la página del móvil.
- **Confirmación siempre en lo peligroso:** apagar el PC o lanzar un comando desde el móvil pide confirmación aunque el botón no la tenga activada. Cancelar un apagado no la pide.
- **Móviles sin usar:** un móvil que no se conecta durante 90 días se desempareja solo. Volver a conectarse reinicia la cuenta.
- **Historial de botones:** *Ajustes > Botones pulsados desde los móviles* muestra qué móvil pulsó qué botón y cuándo. Solo guarda el nombre del botón y el tipo de acción, nunca lo que hace por dentro (puede tener contraseñas o direcciones privadas). Está en `config\actions.log`.
- **Secretos cifrados:** las contraseñas y tokens de OBS y Spotify se guardan cifrados con Windows (DPAPI), no en texto plano. Solo tu usuario de Windows en este PC puede abrirlos; si copias `settings.json` a otro PC, hay que volver a introducirlos.
- **Cabeceras de seguridad:** las páginas de StreamDesk solo permiten ejecutar sus propios scripts y no pueden incrustarse en otra web.
- **Comprobar la conexión y pedir ayuda:** *Ajustes > Conexión del móvil > Comprobar la conexión* revisa la red y el cortafuegos y dice qué hacer. *Copiar el diagnóstico* junta versión, red, intentos de los móviles y el final del registro (`config\streamdesk.log`), sin PIN, tokens ni contraseñas.
- **Evitar la suspensión:** opcional, en *Ajustes > Segundo plano y arranque*. Mientras haya un móvil conectado, Windows no suspende el PC por inactividad.
- **Copia del perfil fuera del PC:** en el mismo sitio eliges una carpeta (de OneDrive o de un USB). Cada vez que guardas se copia el perfil allí (el último, más uno por día durante una semana). El perfil solo tiene tus páginas y botones, sin contraseñas.

## Fiabilidad y acciones peligrosas

- **Apagar y reiniciar, con interruptor:** suspender, reiniciar, apagar y cerrar sesión no hacen nada hasta que los actives en Ajustes (están desactivados por defecto, como los comandos de consola). El apagado y el reinicio esperan 10 segundos como mínimo para poder cancelarlos. La confirmación «¿Ejecutar...?» vive en el móvil, por eso el PC no depende de ella.
- **Al cargar un perfil de otra persona**, el aviso cuenta también las acciones de apagar, abrir webs, Steam y las del segundo estado de un botón. Teclas y texto equivalen a poder ejecutar programas: carga solo perfiles de confianza.
- **Copias automáticas del perfil:** como mucho una cada media hora, en `%APPDATA%\StreamDesk\config\backups`, conservando las últimas 10.
- **Móvil:** si se corta la conexión (pantalla apagada, cambio de Wi-Fi) se detecta en unos segundos y se reconecta con esperas crecientes; mientras tanto los faders y el mute se atenúan. Un fader no cambia el volumen si lo tocas lejos de su marca sin deslizar el dedo.

## Cómo se protege

- **Studio y la configuración solo se abren desde el propio PC.** Todas las rutas de administración (configuración, subida de imágenes, PIN, actualización, conectores, perfil) responden `403` a cualquier cliente que no sea `localhost`. El móvil solo usa el WebSocket con su token.
- **Otras webs no pueden usar `localhost`:** las rutas de administración y el WebSocket local comprueban que la petición se dirige a `localhost`, `127.0.0.1` o `::1` y, en el WebSocket, que el `Origin` coincide con el servidor. Así una página abierta en tu navegador no puede pulsar botones ni leer tu perfil (ni siquiera con DNS rebinding).
- **Iconos y subidas:** las rutas de imagen solo admiten `[A-Za-z0-9_./-]`, los textos del perfil se escapan al pintarlos en el móvil, y las subidas se validan por sus primeros bytes (PNG, JPG o WEBP), no por el tipo que declare el navegador. No se publica la documentación interactiva de la API.
- **Perfiles de otra persona:** al cargar un perfil con atajos de teclado, texto o carpetas, Studio avisa antes de importarlo, porque esas acciones se ejecutan en tu PC.
- **CORS limitado** a `http://localhost` y `http://127.0.0.1` en el puerto de StreamDesk.
- **PIN de 6 dígitos** generado con `secrets`, comparado en tiempo constante y con límite de 5 intentos por IP cada 10 minutos.
- **Móviles revocables** desde Ajustes. Contraseñas y tokens de conectores se guardan cifrados con Windows en `config/settings.json` y no se envían al navegador.
- **El servidor escucha en `0.0.0.0`** para que el móvil lo alcance por Wi-Fi: úsalo en redes de confianza. Cualquiera con el token de un móvil emparejado puede pulsar botones, y los botones pueden abrir programas o pulsar atajos.

## Límites conocidos

- **El tráfico entre el móvil y el PC va por HTTP, sin cifrar.** Cualquiera que pueda escuchar tu Wi-Fi podría ver el PIN al emparejar y el token después. Úsalo en redes de confianza. HTTPS existe (variable de entorno `STREAMDESK_HTTPS=1`), pero la app de Android todavía no lo usa.
- **El instalador no está firmado** salvo que quien publica la versión configure un certificado de firma de código (ver [Actualizaciones y publicación](actualizaciones-y-publicacion.md)). Windows puede mostrar el aviso de SmartScreen.
- **Una versión publicada desde una cuenta de GitHub comprometida** sería aceptada por la actualización automática, porque la huella SHA-256 sale de la misma Release. Firmar el instalador es lo que lo evita.
