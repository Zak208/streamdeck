# Guía de uso: Studio, acciones y páginas

Todo lo que se puede hacer en Studio (el editor de la aplicación de escritorio) y en el móvil. Si empiezas, basta con el [README](../README.md); esto es la referencia.

## Acciones y editor Studio

Studio es el editor de la aplicación de escritorio: lo que puedes añadir a un lado, la cuadrícula en el centro y las propiedades de la casilla elegida al otro.

- **Botones vacíos y elegir acción:** un botón arrastrado desde «Añadir» nace vacío (no hace nada) y un fader nuevo controla el volumen general de Windows. «Elegir acción» abre una ventana con apps, acciones de cada programa, atajos y sistema, con buscador.
- **Multiacción:** varias acciones en un botón, con espera entre pasos (hasta 8). Los pasos pueden pulsar atajos, escribir texto, abrir webs y apps, o usar cualquier acción de la ventana «Elegir acción».
- **Atajo de teclado** (con botón "Grabar"), **Escribir texto** (acentos, emojis y varias líneas, con Enter opcional), **Abrir una web** y **Bloquear PC**.
- **Páginas y carpetas:** botones "Página siguiente / anterior / primera / ir a una página" para montar carpetas.
- **Páginas inteligentes:** en los ajustes de una página (⚙ junto a las pestañas) eliges un programa, y el móvil salta a esa página cuando ese programa pasa a primer plano. Si la cambias tú a mano no te la deshace hasta que cambies de programa.
- **Duplicar páginas** y **guardar o cargar una copia del perfil** (Ajustes > Perfil). La copia no incluye contraseñas, móviles emparejados ni las imágenes que hayas subido; al cargar una se guarda antes una copia del perfil actual.

## Estados, gestos y faders a medida

- **Botón de dos estados** (sección 4 del editor del botón): cada estado tiene su título, subtítulo, color, icono y, si quieres, su propia acción. El estado 2 sin acción propia hace lo mismo que el 1. Si la acción informa de su estado (grabar en OBS, silenciar el micro), el botón sigue a esa acción.
- **Pulsación larga y doble toque con cualquier acción:** al marcar el gesto se abre la misma ventana «Elegir acción» del botón (escenas de OBS, páginas, sonidos, multiacciones...). Nada se guarda hasta que eliges una.
- **Alto del fader:** de 1 fila hasta todas las de la cuadrícula. Se cambia con + y − en el panel del fader, arrastrando su borde inferior en la vista previa o con las flechas arriba y abajo sobre ese borde. Para crecer necesita libres las casillas de debajo: no se borra nada para hacer sitio. Los perfiles guardados siguen valiendo; una versión anterior de la app rechazaría un perfil con faders de otro alto.

## Biblioteca de páginas

El botón **Biblioteca** de la barra superior abre una página con 57 páginas ya montadas, con buscador y categorías (Para empezar, Diseños, Música, Directo y voz, Comunicación, Vídeo y audio, Foto y diseño, Navegador y Google, Oficina, Desarrollo, Windows y sistema): Streamer, Spotify, OBS, Discord, Zoom, Teams, VLC, DaVinci Resolve, Premiere, Photoshop, Excel, Word, Figma, VS Code, atajos de Windows y muchas más. Cada miniatura muestra la página tal como se verá, con su propio tamaño de cuadrícula (hay diseños de 6x3 con faders altos, de 4x3 sin faders, de 3x2 con teclas grandes...). Las de un programa se abren solas en el móvil cuando ese programa está a la vista (si ya tienes una página para ese programa, la nueva no se abre sola, para que no se pisen). «+ Página» solo crea una página en blanco o lleva a la biblioteca. Los atajos de cada programa son los que trae por defecto y van a la ventana que tenga el foco. Los de Photoshop, Illustrator, Premiere, After Effects, Figma, Blender, Firefox y VS Code no los pude comprobar en la documentación oficial: son los estándar que conozco, pero revísalos.

## Acciones añadidas

- **Windows:** suspender, reiniciar, apagar (con 15 s para cancelarlo con «Cancelar apagado») y cerrar sesión, todos con confirmación; plan de energía; modo de pantalla (duplicar, extender, solo una); subir y bajar el volumen; captura de pantalla a `Imágenes\StreamDesk`. Se lanzan como órdenes fijas de Windows, nunca con texto del perfil.
- **OBS:** activar o desactivar un filtro, subir o bajar 3 dB el volumen de una fuente y refrescar una fuente de navegador.
- **Steam:** lanzar un juego instalado, elegido de tu biblioteca.
- **Webhooks:** además de GET y POST, ahora PUT (por ejemplo para una luz Elgato Key Light). Sigue limitado a los destinos que permitas.
- **Discord, silenciar y ensordecer:** por defecto StreamDesk pulsa los botones de Discord (los de abajo a la izquierda), sin que tengas que crear ningún atajo, y la tecla se ilumina cuando estás silenciado. Discord tiene que estar abierto y a la vista (puede quedar detrás de otras ventanas, no minimizado). En el conector de Discord puedes cambiar a un atajo global que creas tú en Discord, que funciona con Discord minimizado.
- **Discord, sonidos:** Discord solo ofrece su panel de sonidos dentro de un canal de voz y no permite reproducirlos desde fuera, así que StreamDesk abre ese panel y pulsa el sonido, y por eso tienes que estar en una llamada. Si en Discord (Ajustes > Atajos de teclado) puedes asignar un atajo a un sonido, pégalo en el botón del sonido («Atajo de este sonido»): se reproduce pulsando solo esa tecla, con Discord en segundo plano (no he podido comprobar que tu versión de Discord ofrezca ese atajo). La lista de sonidos se guarda tras la primera lectura, así que puedes elegirlos sin estar en voz. Se muestran por servidor, en desplegables, como fichas.

## Gestos, confirmación y cuadrícula

- **Pulsación larga y doble toque:** en la pestaña *Acción* de una casilla marcas «Pulsación larga» o «Doble toque» y eliges qué hace cada uno (atajo, texto, web, carpeta, aplicación, multiacción...). El móvil lo avisa con dos puntitos en la casilla. Un botón con gestos espera unas décimas de segundo (280 ms para el doble toque, 500 ms para la pulsación larga) para saber cuál haces; los botones sin gestos actúan al levantar el dedo, siempre que no lo hayas deslizado (así un deslizamiento para cambiar de página no pulsa la tecla que estaba debajo).
- **Pedir confirmación:** el móvil pregunta «¿Ejecutar...?» antes de lanzar el botón (útil para bloquear el PC o cerrar un directo).
- **Desactivar un botón** sin borrarlo: se ve apagado en el móvil y el servidor rechaza la pulsación aunque llegue.
- **Abrir una carpeta:** en «Elegir acción» (Sistema). Solo rutas con letra de unidad (`D:\Proyectos`); se rechazan las rutas de red de tipo `\servidor\recurso` y las que contienen `..`. Una unidad de red mapeada con letra sí se aceptaría.
- **Atajos por aplicación:** en «Elegir acción» hay paquetes para Zoom, Teams, Meet, VLC, PowerPoint, DaVinci Resolve, Photoshop, Audacity y el navegador, además de atajos de Windows (captura, escritorios virtuales, Alt+Tab...) y de edición (copiar, pegar, deshacer...). Son atajos de teclado que van a la ventana que tenga el foco, así que **la aplicación tiene que estar a la vista** en el PC; si cambias los atajos en la propia aplicación, edítalos en la casilla. Los atajos son los que cada programa trae por defecto, no los he probado dentro de cada uno.
- **Tamaño propio por página:** cada página puede tener su cuadrícula (botón con el tamaño sobre la vista previa). Ajustes > Cuadrícula cambia todas a la vez y fija con qué tamaño empiezan las páginas nuevas. Una versión anterior a la 2.15 no abre un perfil con páginas de tamaños distintos.
- **Cuadrícula a tu medida** (Ajustes > Cuadrícula): elige una de las rápidas (6x2 por defecto, 5x3, 4x3, 3x3, 4x2) o escribe tus columnas y filas, de 2 a 10 columnas y de 2 a 8 filas, con un máximo de 64 casillas (por ejemplo 4 columnas x 8 filas). Al cambiar, cada botón conserva su fila y columna si existen en la nueva cuadrícula; si no, pasa a la primera casilla libre. Los faders ocupan desde la primera fila de su columna tantas filas como tengan de alto (2 por defecto) y, si pierden su columna, pasan a las de más a la derecha manteniendo su orden. Si algo no cabe, Studio te dice cuántos elementos se han quedado fuera. Antes de convertir se guarda una copia del perfil junto a `deck_config.json`.
- **Quitar y deshacer:** arrastra un botón o un fader de la vista previa y suéltalo fuera del marco para eliminarlo (o usa Supr o la papelera). `Ctrl+Z` recupera el último que quitaste.
- **Arrastre con su forma:** las fichas de «Añadir» son un botón y un fader con el aspecto que tendrán, y lo que sigue al cursor al arrastrar mide lo mismo que una casilla de tu cuadrícula.

## Monitores del sistema

Las casillas de monitor muestran en vivo: **CPU**, **RAM**, **GPU** y **VRAM** (tarjetas NVIDIA, leídas con su librería `nvml.dll`; con otras marcas muestran *N/D*), **Red** (descarga y subida de la tarjeta que usa tu red local) y **Disco** (velocidad de lectura y escritura). El porcentaje de disco ocupado sigue disponible como acción, pero ya no está en la página Sistema por defecto.

## Detalles que conviene saber

- **Panel derecho de Studio:** se ensancha arrastrando su borde izquierdo (doble clic para volver al ancho normal, o con las flechas del teclado) o con el botón ⤢ de su esquina. Recuerda la anchura. Las listas de opciones (escenas, playlists, sonidos...) aprovechan la altura de la ventana.
- **Monitores en el móvil:** tocar un monitor (CPU, RAM, GPU, VRAM, Red, Disco) abre una hoja «Estado del PC» con todas las lecturas en vivo. No toca nada en el PC, así que no te saca del programa que estés usando.
- **Programas que abre StreamDesk** (OBS, Steam, Discord...) se arrancan desde su propia carpeta. Antes OBS fallaba con «no encuentra en-US» porque se lanzaba desde otra carpeta, algo que no depende del idioma en que lo tengas.

## Interfaz y primeros pasos

- **Siete temas:** negro y amarillo (por defecto), azul noche y cian, violeta, verde, rojo, rosa y naranja. Se cambia en Ajustes y se aplica también en el móvil al instante. Los botones tienen 42 colores a elegir, más un selector libre.
- **Plantillas:** `+ Página` ofrece Streamer, Gamer, Trabajo o una página en blanco. Cada plantilla usa tus atajos de Discord guardados.
- **Guardado automático:** no hay botón de guardar; el indicador de la barra superior muestra "Guardando", "Guardado" o el error.
- **Ajustes:** tema, móviles emparejados (se pueden quitar, y el móvil se desconecta en el acto), versión y la guía de bienvenida.
- **Pensado para quien empieza:** pulsa una casilla vacía, «Poner un botón y elegir qué hace» y elige. Las pestañas hablan en llano («Abrir una app», «Controlar programa», «Teclas y webs», «Windows y volumen») y el botón «▶ Probar aquí en el PC» ejecuta el botón sin coger el móvil (solo acciones seguras: abrir apps, webs, carpetas, multimedia, OBS, Spotify y Discord; nunca apagar ni bloquear).
- **Todas tus apps, no solo las famosas:** «Abrir una app» usa la lista del menú Inicio de Windows (programas clásicos, apps de la Tienda y juegos de Steam), agrupada por temas y con buscador. «Actualizar» vuelve a buscar si acabas de instalar algo. Cada botón recibe el icono real del programa o, si Windows no lo da, un cuadrado con su inicial.
- **Móvil en vertical:** funciona, pero el panel de 6x2 se ve mejor en horizontal; la app avisa.
