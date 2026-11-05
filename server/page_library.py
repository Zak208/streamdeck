"""The library of ready-made pages: general ones, and one per program (Spotify, OBS, Discord, Zoom...).

Each page is declared as data: up to eight keys (cells 0-3 and 6-9 of the original 6x2 deck) and up to two faders
(columns 5 and 6). A page that belongs to a program also names it (`app`): when added, the phone jumps to that page
by itself whenever the program is in front. `templates.build_page` turns an entry into a real page, so every one is
checked by the same validator as a hand-made profile.

A key is either a reference to a connector button ("obs:record", "discord:mute", "windows:mic_mute") or one of
the helpers below. Shortcuts of a program go to the window that has the focus: the program is in front when its
page is the one showing, which is exactly what `app` arranges.
"""

from typing import Any, Dict, List, Optional, Union

ACCENT = "#f8c700"
ICON = "/static/icons/"

KeySpec = Union[str, Dict[str, Any]]


def key(label: str, sub: str, icon: str, color: str, action_type: str, target: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"label": label, "sublabel": sub, "icon": f"{ICON}{icon}.svg", "color": color,
            "action_type": action_type, "target": target, "extra": extra or {}}


def hotkey(label: str, sub: str, keys: str, icon: str, color: str = ACCENT) -> Dict[str, Any]:
    return key(label, sub, icon, color, "hotkey", keys)


def media(label: str, target: str, icon: str, color: str = ACCENT) -> Dict[str, Any]:
    return key(label, "Multimedia", icon, color, "media", target)


def app(label: str, sub: str, icon: str, color: str, target: str) -> Dict[str, Any]:
    return key(label, sub, icon, color, "preset_app", target)


def monitor(label: str, target: str, icon: str) -> Dict[str, Any]:
    return key(label, "En vivo", icon, ACCENT, "hardware_monitor", target)


def fader(label: str, sub: str, icon: str, color: str, slider_type: str = "app_dynamic", target_app: Optional[str] = None) -> Dict[str, Any]:
    return {"label": label, "sublabel": sub, "icon": f"{ICON}{icon}.svg", "color": color,
            "slider_type": slider_type, "target_app": target_app}


MASTER = fader("Master", "PC", "volume_up", ACCENT, "master")

CATEGORIES = ["Para empezar", "Música", "Directo y voz", "Reuniones", "Vídeo, fotos y audio", "Navegador", "Windows"]


def page(id: str, name: str, category: str, icon: str, description: str, buttons: List[KeySpec], faders: List[Dict[str, Any]],
         app_exe: Optional[str] = None) -> Dict[str, Any]:
    return {"id": id, "name": name, "category": category, "icon": f"{ICON}{icon}.svg", "description": description,
            "buttons": buttons, "faders": faders, "app": app_exe}


LIBRARY: List[Dict[str, Any]] = [
    # ---- to start with
    page("streamer", "Streamer", "Para empezar", "broadcast",
         "OBS (grabar, directo, escenas), micrófono, Discord y volumen.",
         ["obs:record", "obs:stream", "obs:next_scene", "windows:mic_mute", "discord:mute", "discord:deafen", "obs:prev_scene",
          app("Spotify", "Música", "spotify", "#1db954", "spotify")],
         [MASTER, fader("Discord", "Voz", "discord", "#5865f2", target_app="Discord.exe")]),
    page("gamer", "Gamer", "Para empezar", "gamepad",
         "Discord, micrófono, música y Steam a mano mientras juegas.",
         ["discord:mute", "discord:deafen", "windows:mic_mute", app("Steam", "Juegos", "steam", "#171a21", "steam"),
          media("Play/Pausa", "play_pause", "play_pause"), media("Siguiente", "next", "next"), media("Anterior", "prev", "prev"),
          app("Discord", "Abrir", "discord", "#5865f2", "discord")],
         [MASTER, fader("Spotify", "App", "spotify", "#1db954", target_app="Spotify.exe")]),
    page("work", "Trabajo", "Para empezar", "sliders",
         "Navegador, notas, calculadora y el estado de tu PC en vivo.",
         [app("Edge", "Navegador", "chrome", "#0078d7", "edge"), app("Notas", "Bloc de notas", "notes", ACCENT, "notepad"),
          app("Calculadora", "Utilidad", "calc", ACCENT, "calc"), app("Tareas", "Administrador", "sliders", ACCENT, "taskmgr"),
          monitor("CPU", "cpu", "cpu"), monitor("RAM", "ram", "ram"), monitor("GPU", "gpu", "gpu"), "windows:mic_mute"],
         [MASTER, fader("Edge", "Web", "chrome", "#0078d7", target_app="msedge.exe")]),
    page("blank", "En blanco", "Para empezar", "plus",
         "Una página vacía con el volumen de Windows, para montarla a tu manera.",
         [], [MASTER]),

    # ---- music
    page("spotify", "Spotify", "Música", "spotify",
         "Reproducir, siguiente, me gusta, aleatorio y repetir. Se abre sola cuando Spotify está a la vista.",
         [media("Play/Pausa", "play_pause", "play_pause", "#1db954"), media("Anterior", "prev", "prev", "#1db954"),
          media("Siguiente", "next", "next", "#1db954"),
          hotkey("Me gusta", "Spotify a la vista", "ALT+SHIFT+B", "plus", "#1db954"),
          hotkey("Aleatorio", "Spotify a la vista", "CTRL+S", "macro", "#1db954"),
          hotkey("Repetir", "Spotify a la vista", "CTRL+R", "next", "#1db954"),
          app("Spotify", "Abrir", "spotify", "#1db954", "spotify"),
          key("Silenciar", "Solo Spotify", "mute", "#ef4444", "windows", "app_mute", {"process": "Spotify.exe"})],
         [fader("Spotify", "App", "spotify", "#1db954", target_app="Spotify.exe"), MASTER], "Spotify.exe"),
    page("player", "Reproductor", "Música", "play_pause",
         "Teclas multimedia que valen para cualquier reproductor, y el volumen de Windows.",
         [media("Play/Pausa", "play_pause", "play_pause"), media("Anterior", "prev", "prev"), media("Siguiente", "next", "next"),
          media("Parar", "stop", "pause"), media("Silenciar", "mute", "mute"),
          hotkey("Adelantar", "Flecha derecha", "RIGHT", "chevron_right"), hotkey("Atrasar", "Flecha izquierda", "LEFT", "chevron_left"),
          app("YouTube Music", "Web", "youtube", "#ef4444", "chrome")],
         [MASTER]),

    # ---- stream and voice
    page("obs", "OBS Studio", "Directo y voz", "obs",
         "Grabar, emitir, pausar, cambiar de escena, cámara virtual y repetición. Se abre sola con OBS a la vista.",
         ["obs:record", "obs:stream", "obs:pause", "obs:virtualcam", "obs:prev_scene", "obs:next_scene", "obs:replay_save", "windows:mic_mute"],
         [MASTER, fader("OBS", "App", "obs", "#302e31", target_app="obs64.exe")], "obs64.exe"),
    page("discord", "Discord", "Directo y voz", "discord",
         "Silenciar, ensordecer, micrófono de Windows y el volumen de Discord. Se abre sola con Discord a la vista.",
         ["discord:mute", "discord:deafen", "windows:mic_mute", app("Discord", "Abrir", "discord", "#5865f2", "discord"),
          media("Silenciar PC", "mute", "mute", "#5865f2"),
          media("Play/Pausa", "play_pause", "play_pause", "#5865f2"), media("Siguiente", "next", "next", "#5865f2"),
          media("Anterior", "prev", "prev", "#5865f2")],
         [fader("Discord", "Voz", "discord", "#5865f2", target_app="Discord.exe"), MASTER], "Discord.exe"),
    page("mic", "Micrófono y salida", "Directo y voz", "mic",
         "Micrófono, volumen general, silenciar y bloquear el PC con un toque.",
         ["windows:mic_mute", media("Silenciar PC", "mute", "mute"), "windows:lock_pc", media("Play/Pausa", "play_pause", "play_pause")],
         [MASTER, fader("Discord", "Voz", "discord", "#5865f2", target_app="Discord.exe")]),

    # ---- meetings
    page("zoom", "Zoom", "Reuniones", "video",
         "Micrófono, cámara y compartir pantalla de Zoom. Se abre sola con Zoom a la vista.",
         [hotkey("Micrófono", "Alt+A", "ALT+A", "mic_off", "#2d8cff"), hotkey("Cámara", "Alt+V", "ALT+V", "video", "#2d8cff"),
          hotkey("Compartir", "Alt+S", "ALT+S", "broadcast", "#2d8cff"), hotkey("Grabar", "Alt+R", "ALT+R", "video", "#ef4444"),
          hotkey("Levantar mano", "Alt+Y", "ALT+Y", "gamepad", "#2d8cff"), hotkey("Chat", "Alt+H", "ALT+H", "notes", "#2d8cff"),
          hotkey("Pantalla completa", "Alt+F", "ALT+F", "video", "#2d8cff"), "windows:mic_mute"],
         [MASTER, fader("Zoom", "App", "video", "#2d8cff", target_app="Zoom.exe")], "Zoom.exe"),
    page("teams", "Microsoft Teams", "Reuniones", "video",
         "Micrófono, cámara, compartir, levantar la mano y colgar. Se abre sola con Teams a la vista.",
         [hotkey("Micrófono", "Ctrl+Mayús+M", "CTRL+SHIFT+M", "mic_off", "#6264a7"), hotkey("Cámara", "Ctrl+Mayús+O", "CTRL+SHIFT+O", "video", "#6264a7"),
          hotkey("Compartir", "Ctrl+Mayús+E", "CTRL+SHIFT+E", "broadcast", "#6264a7"), hotkey("Levantar mano", "Ctrl+Mayús+K", "CTRL+SHIFT+K", "gamepad", "#6264a7"),
          hotkey("Colgar", "Ctrl+Mayús+H", "CTRL+SHIFT+H", "power", "#ef4444"), hotkey("Aceptar", "Ctrl+Mayús+A", "CTRL+SHIFT+A", "play", "#10b981"),
          hotkey("Rechazar", "Ctrl+Mayús+D", "CTRL+SHIFT+D", "trash", "#ef4444"), "windows:mic_mute"],
         [MASTER], "ms-teams.exe"),
    page("meet", "Google Meet", "Reuniones", "video",
         "Micrófono y cámara de Meet en el navegador. Se abre sola con Chrome a la vista.",
         [hotkey("Micrófono", "Ctrl+D", "CTRL+D", "mic_off", "#00897b"), hotkey("Cámara", "Ctrl+E", "CTRL+E", "video", "#00897b"),
          hotkey("Levantar mano", "Ctrl+Alt+H", "CTRL+ALT+H", "gamepad", "#00897b"), hotkey("Chat", "Ctrl+Alt+C", "CTRL+ALT+C", "notes", "#00897b"),
          "windows:mic_mute", "windows:lock_pc"],
         [MASTER], "chrome.exe"),

    # ---- video, photos and audio
    page("vlc", "VLC", "Vídeo, fotos y audio", "play_pause",
         "Play, siguiente, anterior, pantalla completa y volumen de VLC. Se abre sola con VLC a la vista.",
         [hotkey("Play/Pausa", "Espacio", "SPACE", "play_pause", "#ff8800"), hotkey("Siguiente", "N", "N", "next", "#ff8800"),
          hotkey("Anterior", "P", "P", "prev", "#ff8800"), hotkey("Pantalla completa", "F", "F", "video", "#ff8800"),
          hotkey("Subir volumen", "Ctrl+Flecha arriba", "CTRL+UP", "volume_up", "#ff8800"),
          hotkey("Bajar volumen", "Ctrl+Flecha abajo", "CTRL+DOWN", "mute", "#ff8800"),
          hotkey("Adelantar", "Mayús+Derecha", "SHIFT+RIGHT", "chevron_right", "#ff8800"),
          hotkey("Atrasar", "Mayús+Izquierda", "SHIFT+LEFT", "chevron_left", "#ff8800")],
         [fader("VLC", "App", "play_pause", "#ff8800", target_app="vlc.exe"), MASTER], "vlc.exe"),
    page("powerpoint", "PowerPoint", "Vídeo, fotos y audio", "notes",
         "Iniciar, avanzar, retroceder, pantalla negra y salir. Se abre sola con PowerPoint a la vista.",
         [hotkey("Iniciar", "F5", "F5", "play", "#d24726"), hotkey("Siguiente", "Flecha derecha", "RIGHT", "chevron_right", "#d24726"),
          hotkey("Anterior", "Flecha izquierda", "LEFT", "chevron_left", "#d24726"), hotkey("Pantalla negra", "B", "B", "pause", "#d24726"),
          hotkey("Pantalla blanca", "W", "W", "pause", "#d24726"), hotkey("Salir", "Esc", "ESC", "power", "#ef4444"),
          hotkey("Desde esta diapositiva", "Mayús+F5", "SHIFT+F5", "play", "#d24726"), hotkey("Guardar", "Ctrl+S", "CTRL+S", "notes", "#d24726")],
         [MASTER], "POWERPNT.EXE"),
    page("resolve", "DaVinci Resolve", "Vídeo, fotos y audio", "video",
         "Play, cortar, guardar y deshacer en el montaje. Se abre sola con Resolve a la vista.",
         [hotkey("Play/Pausa", "Espacio", "SPACE", "play_pause", "#e11d48"), hotkey("Cortar clip", "Ctrl+B", "CTRL+B", "macro", "#e11d48"),
          hotkey("Guardar", "Ctrl+S", "CTRL+S", "notes", "#e11d48"), hotkey("Deshacer", "Ctrl+Z", "CTRL+Z", "prev", "#e11d48"),
          hotkey("Rehacer", "Ctrl+Mayús+Z", "CTRL+SHIFT+Z", "next", "#e11d48"), hotkey("Marcar entrada", "I", "I", "chevron_right", "#e11d48"),
          hotkey("Marcar salida", "O", "O", "chevron_left", "#e11d48"), hotkey("Cuchilla", "B", "B", "macro", "#e11d48")],
         [MASTER], "Resolve.exe"),
    page("photoshop", "Photoshop", "Vídeo, fotos y audio", "sliders",
         "Pincel, borrador, deshacer y guardar. Se abre sola con Photoshop a la vista.",
         [hotkey("Pincel", "B", "B", "sliders", "#31a8ff"), hotkey("Borrador", "E", "E", "trash", "#31a8ff"),
          hotkey("Deshacer", "Ctrl+Z", "CTRL+Z", "prev", "#31a8ff"), hotkey("Guardar", "Ctrl+S", "CTRL+S", "notes", "#31a8ff"),
          hotkey("Mover", "V", "V", "macro", "#31a8ff"), hotkey("Selección", "M", "M", "folder", "#31a8ff"),
          hotkey("Capa nueva", "Ctrl+Mayús+N", "CTRL+SHIFT+N", "plus", "#31a8ff"), hotkey("Texto", "T", "T", "notes", "#31a8ff")],
         [MASTER], "Photoshop.exe"),
    page("audacity", "Audacity", "Vídeo, fotos y audio", "mic",
         "Grabar, reproducir, pausar y guardar. Se abre sola con Audacity a la vista.",
         [hotkey("Grabar", "R", "R", "mic", "#ef4444"), hotkey("Play/Parar", "Espacio", "SPACE", "play_pause", "#0000cc"),
          hotkey("Pausa", "P", "P", "pause", "#0000cc"), hotkey("Parar", "S", "S", "power", "#0000cc"),
          hotkey("Deshacer", "Ctrl+Z", "CTRL+Z", "prev", "#0000cc"), hotkey("Guardar proyecto", "Ctrl+S", "CTRL+S", "notes", "#0000cc"),
          hotkey("Ir al inicio", "Inicio", "HOME", "chevron_left", "#0000cc"), hotkey("Ir al final", "Fin", "END", "chevron_right", "#0000cc")],
         [MASTER], "Audacity.exe"),

    # ---- browser
    page("chrome", "Chrome", "Navegador", "chrome",
         "Pestañas, recargar y buscar en Chrome. Se abre sola con Chrome a la vista.",
         [hotkey("Pestaña nueva", "Ctrl+T", "CTRL+T", "plus", "#ea4335"), hotkey("Cerrar pestaña", "Ctrl+W", "CTRL+W", "trash", "#ea4335"),
          hotkey("Pestaña siguiente", "Ctrl+Tab", "CTRL+TAB", "chevron_right", "#ea4335"),
          hotkey("Pestaña anterior", "Ctrl+Mayús+Tab", "CTRL+SHIFT+TAB", "chevron_left", "#ea4335"),
          hotkey("Recargar", "F5", "F5", "play", "#ea4335"), hotkey("Buscar", "Ctrl+F", "CTRL+F", "link", "#ea4335"),
          hotkey("Incógnito", "Ctrl+Mayús+N", "CTRL+SHIFT+N", "lock", "#ea4335"),
          hotkey("Reabrir pestaña", "Ctrl+Mayús+T", "CTRL+SHIFT+T", "prev", "#ea4335")],
         [MASTER, fader("Chrome", "Web", "chrome", "#ea4335", target_app="chrome.exe")], "chrome.exe"),
    page("edge", "Microsoft Edge", "Navegador", "chrome",
         "Pestañas, recargar y buscar en Edge. Se abre sola con Edge a la vista.",
         [hotkey("Pestaña nueva", "Ctrl+T", "CTRL+T", "plus", "#0078d7"), hotkey("Cerrar pestaña", "Ctrl+W", "CTRL+W", "trash", "#0078d7"),
          hotkey("Pestaña siguiente", "Ctrl+Tab", "CTRL+TAB", "chevron_right", "#0078d7"),
          hotkey("Pestaña anterior", "Ctrl+Mayús+Tab", "CTRL+SHIFT+TAB", "chevron_left", "#0078d7"),
          hotkey("Recargar", "F5", "F5", "play", "#0078d7"), hotkey("Buscar", "Ctrl+F", "CTRL+F", "link", "#0078d7"),
          hotkey("InPrivate", "Ctrl+Mayús+N", "CTRL+SHIFT+N", "lock", "#0078d7"),
          hotkey("Reabrir pestaña", "Ctrl+Mayús+T", "CTRL+SHIFT+T", "prev", "#0078d7")],
         [MASTER, fader("Edge", "Web", "chrome", "#0078d7", target_app="msedge.exe")], "msedge.exe"),

    # ---- Windows
    page("windows", "Windows", "Windows", "gear",
         "Captura, escritorio, explorador, ajustes, escritorios virtuales y cambiar de ventana.",
         [hotkey("Captura", "Win+Mayús+S", "WIN+SHIFT+S", "video"), hotkey("Escritorio", "Win+D", "WIN+D", "folder"),
          hotkey("Explorador", "Win+E", "WIN+E", "folder"), hotkey("Ajustes", "Win+I", "WIN+I", "gear"),
          hotkey("Vista de tareas", "Win+Tab", "WIN+TAB", "sliders"), hotkey("Cambiar ventana", "Alt+Tab", "ALT+TAB", "next"),
          hotkey("Escritorio siguiente", "Win+Ctrl+Der.", "WIN+CTRL+RIGHT", "chevron_right"),
          hotkey("Escritorio anterior", "Win+Ctrl+Izq.", "WIN+CTRL+LEFT", "chevron_left")],
         [MASTER]),
    page("editing", "Edición", "Windows", "notes",
         "Copiar, cortar, pegar, deshacer, rehacer, seleccionar todo, guardar y buscar en cualquier programa.",
         [hotkey("Copiar", "Ctrl+C", "CTRL+C", "notes"), hotkey("Cortar", "Ctrl+X", "CTRL+X", "trash"),
          hotkey("Pegar", "Ctrl+V", "CTRL+V", "plus"), hotkey("Deshacer", "Ctrl+Z", "CTRL+Z", "prev"),
          hotkey("Rehacer", "Ctrl+Y", "CTRL+Y", "next"), hotkey("Seleccionar todo", "Ctrl+A", "CTRL+A", "macro"),
          hotkey("Guardar", "Ctrl+S", "CTRL+S", "notes"), hotkey("Buscar", "Ctrl+F", "CTRL+F", "link")],
         []),
    page("monitors", "Estado del PC", "Windows", "cpu",
         "CPU, RAM, GPU, VRAM, red y disco en vivo, y el administrador de tareas.",
         [monitor("CPU", "cpu", "cpu"), monitor("RAM", "ram", "ram"), monitor("GPU", "gpu", "gpu"), monitor("VRAM", "vram", "gpu"),
          monitor("Red", "net", "network"), monitor("Disco", "disk_speed", "disk"), monitor("Disco usado", "disk", "disk"),
          app("Tareas", "Administrador", "sliders", ACCENT, "taskmgr")],
         [MASTER]),
]


def by_id() -> Dict[str, Dict[str, Any]]:
    return {entry["id"]: entry for entry in LIBRARY}
