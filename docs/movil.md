# Usar StreamDesk en el móvil

## Instalar StreamDesk en el móvil como app

Abre la dirección que muestra Studio (o escanea el QR) y pulsa el engranaje: **Ajustes > Instalar como app** te da los pasos exactos para tu móvil.

- **iPhone (Safari):** Compartir > *Añadir a pantalla de inicio*. Funciona sin más. La app instalada guarda sus datos aparte de Safari, así que pedirá el PIN una vez.
- **Android, la forma recomendada: la app de StreamDesk (APK).** Descárgala de la última [Release](https://github.com/Zak208/streamdeck/releases/latest) (`StreamDesk.apk`) o escanea el QR de Studio, en *Enlazar móvil > ¿No tienes la app en el móvil?*. Ábrela, permite «instalar apps desconocidas» a quien la descargó y escanea el QR de Studio. La app recuerda tu PC (con su identificador, no con su IP): si cambias de Wi-Fi o el PC cambia de dirección, lo busca sola en la red actual y entra sin pedir el PIN; si no lo encuentra, te deja escanear el QR, elegir un PC de la lista o escribir su IP. Un acceso directo del navegador no puede hacer esto: apunta a una IP concreta y, si esa IP no responde, Chrome muestra su página de error. Las actualizaciones se instalan encima porque todas las versiones se firman con la misma clave. Requiere StreamDesk 2.18 o posterior en el PC. **Si la app del móvil es más antigua que tu PC, te lo dice al conectarse** (por ejemplo, app 2.18 y PC 2.19) y te ofrece descargar la nueva; si eliges *Más tarde*, no vuelve a preguntar hasta que el PC se actualice otra vez. Lo decide la página que sirve el PC, así que también avisa a las apps 2.18 que ya tienes instaladas, y la nueva se instala encima porque lleva la misma firma.
- **Android (Chrome, como web):** Chrome solo ofrece *Instalar app* en webs **https**, y StreamDesk se sirve por `http` dentro de tu red. Para activarlo una vez: abre `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, pega la dirección de StreamDesk (por ejemplo `http://192.168.2.81:48291`), pon *Enabled* y pulsa *Relaunch*. Si la IP de tu PC cambia, repite el paso con la nueva (conviene fijarla en el router).
- **Sin instalar:** menú ⋮ > *Añadir a la pantalla de inicio* crea un acceso directo (que deja de funcionar al cambiar de red: por eso se recomienda la app). En `http` Chrome no permite mantener la pantalla encendida.

**Móvil en vertical u horizontal:** en vertical los botones se reorganizan en 3 columnas; en horizontal se aprovecha toda la altura. El menú de ajustes del móvil permite saltar de página, ver el estado de la conexión y vincular con otro PC. En los ajustes del móvil puedes activar o desactivar el cambio de página deslizando el dedo a los lados, y elegir la intensidad de la vibración.

## Usarlo fuera de casa (Tailscale)

Esta guía no está probada en el proyecto; son los pasos esperables. StreamDesk solo acepta conexiones de tu red local, así que fuera de casa hace falta una red privada. Con [Tailscale](https://tailscale.com) (gratis para uso personal): instálalo en el PC y en el móvil con la misma cuenta; en el PC, permite el puerto a la red de Tailscale con una consola de administrador:
```powershell
netsh advfirewall firewall add rule name="StreamDesk Pro Tailscale" dir=in action=allow protocol=TCP localport=48291 remoteip=100.64.0.0/10
```
y en la app del móvil escribe la dirección Tailscale del PC (empieza por `100.`) con el puerto `48291`. La conexión va cifrada por Tailscale y no se abre nada a internet.
