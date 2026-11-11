# Actualizaciones y publicación de versiones

## Cómo se actualiza la app

- **Versión instalada:** Studio mira cada vez que se abre (y cada 6 horas) la última *Release* de `https://github.com/Zak208/streamdeck`. Si es más nueva que la tuya, la barra superior muestra «Hay una versión nueva» y un botón **Actualizar**. Al pulsarlo, StreamDesk descarga el instalador de esa Release, comprueba su huella SHA-256, lo ejecuta en silencio sobre tu instalación y se reinicia solo. Tu perfil, tus ajustes y tus móviles emparejados no se tocan (viven en `%APPDATA%\StreamDesk`).
- **Requisito:** la app lee las Releases sin iniciar sesión en GitHub, así que el repositorio (o el que se use para publicar) tiene que ser público. Con un repositorio privado, GitHub responde 404 y la app muestra «sin conexión».
- **Seguridad de la actualización:** solo se descarga desde la dirección de Releases de este repositorio, y si la Release no trae la huella SHA-256 o no coincide, no se instala nada. El instalador no está firmado digitalmente, así que Windows puede mostrar el aviso de SmartScreen.
- **Modo desarrollador:** si ejecutas StreamDesk desde un clon del repositorio, el botón hace `git pull --ff-only` en lugar de descargar el instalador.

## Publicar una versión nueva

Para quien mantiene el proyecto.

1. Sube la versión en `server/paths.py`, `installer/setup.iss` y `android/app/build.gradle` (`versionName` y `versionCode`). Un test comprueba que las tres coinciden.
2. Crea una Release en GitHub con el tag `vX.Y.Z`.
3. Al publicarla, dos workflows trabajan solos:
   - `build-pc.yml` compila la app y el instalador y adjunta `instalador_streamdeck.exe` con su huella SHA-256. Si la versión del tag no coincide con la de `server/paths.py`, se detiene antes de publicar nada.
   - `build-apk.yml` compila la app de Android y adjunta `StreamDesk.apk`.
4. Los dos se pueden lanzar a mano con el tag de una Release anterior. Para compilar en tu PC sirve `scripts\build_pc.ps1`.

### Firma del instalador (opcional, recomendada)

Si añades estos secretos al repositorio, la app y el instalador salen firmados, Windows muestra el editor y desaparece el aviso de SmartScreen:

- `WINDOWS_CERT_BASE64`: un certificado `.pfx` de firma de código, en base64.
- `WINDOWS_CERT_PASSWORD`: su contraseña.

Sin ellos se compila sin firmar, como hasta ahora. El certificado hay que comprarlo.

### Clave de la app de Android

El APK se firma con una clave que vive solo en los secretos del repositorio (`ANDROID_KEYSTORE_BASE64` y `ANDROID_KEYSTORE_PASSWORD`); si falta, el workflow se niega a publicar el APK en una Release. Guarda una copia de la clave: con otra distinta, los móviles no actualizan la app y hay que desinstalarla.
