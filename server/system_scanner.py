import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import winreg
from typing import List, Dict, Any, Optional

GENERIC_ICON = "/static/icons/power.svg"
CREATE_NO_WINDOW = 0x08000000

# One short list of groups, in the order Studio shows them. Every app ends in one of these.
CATEGORIES = ["Juegos", "Música y audio", "Vídeo y foto", "Comunicación", "Navegadores", "Oficina", "Desarrollo", "Sistema y utilidades", "Otras apps"]
_CATEGORY_ALIASES = {
    "Comunicaciones": "Comunicación", "Música": "Música y audio", "Audio": "Música y audio", "Streaming": "Vídeo y foto",
    "Multimedia": "Vídeo y foto", "Diseño": "Vídeo y foto", "Productividad": "Oficina", "Utilidades": "Sistema y utilidades",
    "Sistema": "Sistema y utilidades",
}
# First match wins, so the more specific groups come first.
_CATEGORY_HINTS = [
    ("Navegadores", ("chrome", "firefox", "edge", "brave", "opera", "vivaldi", "navegador")),
    ("Juegos", ("steam", "epic games", "riot", "valorant", "league of", "minecraft", "roblox", "xbox", "battle.net", "blizzard",
                "ubisoft", "gog galaxy", "ea app", "launcher", "game", "juego", "curseforge", "overwolf")),
    ("Comunicación", ("discord", "telegram", "whatsapp", "teams", "zoom", "skype", "slack", "outlook", "correo", "mail",
                      "messenger", "instagram", "linkedin", "anydesk", "teamviewer")),
    ("Música y audio", ("spotify", "music", "música", "musica", "audio", "sonido", "sound", "voicemeeter", "audacity", "reaper",
                        "fl studio", "grabadora", "g hub", "mixline", "equalizer")),
    ("Vídeo y foto", ("video", "vídeo", "photo", "foto", "premiere", "capcut", "clipchamp", "cámara", "camara", "davinci", "obs",
                      "photoshop", "gimp", "blender", "paint", "recortes", "after effects", "lightroom", "canva", "crunchyroll", "netflix")),
    ("Oficina", ("word", "excel", "powerpoint", "onenote", "access", "office", "acrobat", "pdf", "notion", "obsidian",
                 "bloc de notas", "notepad", "calculadora", "to do", "onedrive", "dropbox", "winrar", "7-zip")),
    ("Desarrollo", ("visual studio", "code", "git", "python", "node", "docker", "terminal", "powershell", "símbolo del sistema",
                    "java", "sql", "xampp", "antigravity", "pycharm", "intellij", "android studio", "inno setup", "heidi", "mobaxterm")),
    ("Sistema y utilidades", ("windows", "configuración", "panel de control", "administrador", "explorador", "registro", "msconfig",
                              "información del sistema", "task", "defender", "seguridad", "monitor", "cpu", "gpu", "aida", "nvidia", "amd")),
]
# Start Menu entries that are not programs: help files, websites, uninstallers, logs, folders.
_NOISE_NAME = re.compile(
    r"\b(uninstall\w*|desinstal\w*|readme|l[eé]eme|licen[sc]e|licencia|documentation|documentaci[oó]n|manual|release notes|"
    r"notas de la versi[oó]n|faq|help|ayuda|website|sitio web|en la web|homepage|support|soporte|check for updates|"
    r"comprobar actualizaciones|buscar actualizaciones|error log|directory|aviso legal|privacidad|privacy|bug report|redeem|"
    r"examples?|samples?|tutorial|streamdesk|module docs|acerca de|about|installer|instalador|telemetr\w*|"
    r"preferencias de idioma|install additional tools)\b|command prompt \(|^add .* components$|\(dark\)|\(wow\)",
    re.IGNORECASE,
)
_NOISE_EXE = re.compile(r"(unins|setup|install|update|redeem)", re.IGNORECASE)
# The folder codes that Get-StartApps puts at the front of a program's id, mapped to the real folder.
_KNOWN_FOLDERS = {
    "6D809377-6AF0-444B-8957-A3773F02200E": "%ProgramW6432%",
    "7C5A40EF-A0FB-4BFC-874A-C0F2E0B9FA8E": "%ProgramFiles(x86)%",
    "1AC14E77-02E7-4E5D-B744-2EB1AE5198B7": r"%SystemRoot%\System32",
    "D65231B0-B2F1-4857-A4CE-A8E7C6EA7D27": r"%SystemRoot%\SysWOW64",
    "F38BF404-1D43-42F2-9305-67DE0B28FC23": "%SystemRoot%",
    "F1B32785-6FBA-4FCF-9D55-7B8E7F157091": "%LOCALAPPDATA%",
    "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D": "%APPDATA%",
    "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97": "%ProgramData%",
}


def _plain(text: str) -> str:
    """Lower case letters and digits only, to tell that two names are the same program."""
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower())


def normalize_category(name: str) -> str:
    name = _CATEGORY_ALIASES.get(name, name)
    return name if name in CATEGORIES else "Otras apps"


_CATEGORY_PATTERNS = [(category, re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in words) + r")s?(?![a-z0-9])"))
                      for category, words in _CATEGORY_HINTS]


def guess_category(name: str) -> str:
    # Whole words only: "obs" must not match "Obsidian".
    low = name.lower()
    for category, pattern in _CATEGORY_PATTERNS:
        if pattern.search(low):
            return category
    return "Otras apps"



def resolve_app_icon(name_lower: str, fuzzy: bool = True) -> str:
    """One of StreamDesk's drawn icons for a well-known brand, else the generic one.

    Short names are matched as whole words ("obs" is not "Obsidian"). `fuzzy` keeps the old guess by theme
    ("game", "music"...) for the curated list; the apps found on the PC skip it, and get their own icon instead.
    """
    words = set(re.findall(r"[a-z0-9]+", name_lower))
    if "valorant" in name_lower or "riot" in name_lower:
        return "/static/icons/valorant.svg"
    if "cs2" in name_lower or "counter-strike" in name_lower or "cs:go" in name_lower:
        return "/static/icons/cs2.svg"
    if "league of legends" in name_lower or "lol" in words:
        return "/static/icons/league.svg"
    if "fortnite" in name_lower:
        return "/static/icons/fortnite.svg"
    if "minecraft" in name_lower:
        return "/static/icons/minecraft.svg"
    if "roblox" in name_lower:
        return "/static/icons/roblox.svg"
    if "photoshop" in name_lower:
        return "/static/icons/photoshop.svg"
    if "premiere" in name_lower:
        return "/static/icons/premiere.svg"
    if "blender" in name_lower:
        return "/static/icons/blender.svg"
    if "vscode" in name_lower or "visual studio code" in name_lower:
        return "/static/icons/vscode.svg"
    if "firefox" in name_lower:
        return "/static/icons/firefox.svg"
    if "edge" in words:
        return "/static/icons/edge.svg"
    if "opera" in name_lower:
        return "/static/icons/opera.svg"
    if "netflix" in name_lower:
        return "/static/icons/netflix.svg"
    if "tiktok" in name_lower:
        return "/static/icons/tiktok.svg"
    if "telegram" in name_lower:
        return "/static/icons/telegram.svg"
    if "whatsapp" in name_lower:
        return "/static/icons/whatsapp.svg"
    if "battle.net" in name_lower or "blizzard" in name_lower:
        return "/static/icons/battlenet.svg"
    if "epic" in words:
        return "/static/icons/epic.svg"
    if "steam" in name_lower:
        return "/static/icons/steam.svg"
    if "discord" in name_lower:
        return "/static/icons/discord.svg"
    if "spotify" in name_lower:
        return "/static/icons/spotify.svg"
    if "obs" in words:
        return "/static/icons/obs.svg"
    if "twitch" in name_lower:
        return "/static/icons/twitch.svg"
    if "youtube" in name_lower:
        return "/static/icons/youtube.svg"
    if not fuzzy:
        return GENERIC_ICON
    if any(k in name_lower for k in ("game", "play", "war", "craft", "rpg", "simul")):
        return "/static/icons/gamepad.svg"
    if any(k in name_lower for k in ("music", "audio", "sound", "player", "tune")):
        return "/static/icons/music.svg"
    if any(k in name_lower for k in ("video", "cam", "media", "film", "stream")):
        return "/static/icons/video.svg"
    if any(k in name_lower for k in ("code", "develop", "git", "studio", "terminal")):
        return "/static/icons/code.svg"
    return "/static/icons/power.svg"


class SystemScanner:
    """Scans Windows for installed applications, focusing on creator, gamer, and productivity tools."""

    POPULAR_APPS = [
        {
            "id": "discord",
            "name": "Discord",
            "icon": "/static/icons/discord.svg",
            "color": "#5865F2",
            "category": "Comunicaciones",
            "exe_names": ["Discord.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Discord\app-*\Discord.exe")
            ]
        },
        {
            "id": "spotify",
            "name": "Spotify",
            "icon": "/static/icons/spotify.svg",
            "color": "#1DB954",
            "category": "Música",
            "exe_names": ["Spotify.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
                os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
            ]
        },
        {
            "id": "obs",
            "name": "OBS Studio",
            "icon": "/static/icons/obs.svg",
            "color": "#302E31",
            "category": "Streaming",
            "exe_names": ["obs64.exe", "obs32.exe"],
            "paths": [
                r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                r"C:\Program Files (x86)\obs-studio\bin\32bit\obs32.exe"
            ]
        },
        {
            "id": "steam",
            "name": "Steam",
            "icon": "/static/icons/steam.svg",
            "color": "#171A21",
            "category": "Juegos",
            "exe_names": ["steam.exe"],
            "paths": [
                r"C:\Program Files (x86)\Steam\steam.exe",
                r"C:\Program Files\Steam\steam.exe"
            ]
        },
        {
            "id": "chrome",
            "name": "Google Chrome",
            "icon": "/static/icons/chrome.svg",
            "color": "#EA4335",
            "category": "Navegadores",
            "exe_names": ["chrome.exe"],
            "paths": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
        },
        {
            "id": "vscode",
            "name": "Visual Studio Code",
            "icon": "/static/icons/vscode.svg",
            "color": "#007ACC",
            "category": "Desarrollo",
            "exe_names": ["Code.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                r"C:\Program Files\Microsoft VS Code\Code.exe"
            ]
        },
        {
            "id": "riot",
            "name": "Valorant / Riot Client",
            "icon": "/static/icons/valorant.svg",
            "color": "#D13639",
            "category": "Juegos",
            "exe_names": ["RiotClientServices.exe", "VALORANT-Win64-Shipping.exe", "VALORANT.exe"],
            "paths": [
                r"C:\Riot Games\Riot Client\RiotClientServices.exe",
                r"C:\Riot Games\VALORANT\live\VALORANT.exe"
            ]
        },
        {
            "id": "cs2",
            "name": "Counter-Strike 2",
            "icon": "/static/icons/cs2.svg",
            "color": "#DE9B35",
            "category": "Juegos",
            "exe_names": ["cs2.exe"],
            "paths": [
                r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe",
                r"C:\Program Files\Steam\steamapps\common\Counter-Strike Global Offensive\game\bin\win64\cs2.exe"
            ]
        },
        {
            "id": "league",
            "name": "League of Legends",
            "icon": "/static/icons/league.svg",
            "color": "#C8AA6E",
            "category": "Juegos",
            "exe_names": ["LeagueClient.exe", "League of Legends.exe"],
            "paths": [
                r"C:\Riot Games\League of Legends\LeagueClient.exe"
            ]
        },
        {
            "id": "battlenet",
            "name": "Battle.net",
            "icon": "/static/icons/battlenet.svg",
            "color": "#00AEFF",
            "category": "Juegos",
            "exe_names": ["Battle.net.exe"],
            "paths": [
                r"C:\Program Files (x86)\Battle.net\Battle.net.exe",
                r"C:\Program Files\Battle.net\Battle.net.exe"
            ]
        },
        {
            "id": "epicgames",
            "name": "Epic Games",
            "icon": "/static/icons/epic.svg",
            "color": "#2A2A2A",
            "category": "Juegos",
            "exe_names": ["EpicGamesLauncher.exe"],
            "paths": [
                r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
                r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"
            ]
        },
        {
            "id": "vlc",
            "name": "VLC Media Player",
            "icon": "/static/icons/video.svg",
            "color": "#FF8800",
            "category": "Multimedia",
            "exe_names": ["vlc.exe"],
            "paths": [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe"
            ]
        },
        {
            "id": "obsidian",
            "name": "Obsidian",
            "icon": "/static/icons/notes.svg",
            "color": "#7C3AED",
            "category": "Productividad",
            "exe_names": ["Obsidian.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe")
            ]
        },
        {
            "id": "edge",
            "name": "Microsoft Edge",
            "icon": "/static/icons/edge.svg",
            "color": "#0078D7",
            "category": "Navegadores",
            "exe_names": ["msedge.exe"],
            "paths": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
            ]
        },
        {
            "id": "firefox",
            "name": "Mozilla Firefox",
            "icon": "/static/icons/firefox.svg",
            "color": "#FF7139",
            "category": "Navegadores",
            "exe_names": ["firefox.exe"],
            "paths": [
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"
            ]
        },
        {
            "id": "calc",
            "name": "Calculadora",
            "icon": "/static/icons/calc.svg",
            "color": "#F59E0B",
            "category": "Utilidades",
            "exe_names": ["calc.exe"],
            "paths": ["calc.exe"]
        },
        {
            "id": "notepad",
            "name": "Bloc de Notas",
            "icon": "/static/icons/notes.svg",
            "color": "#06B6D4",
            "category": "Utilidades",
            "exe_names": ["notepad.exe"],
            "paths": ["notepad.exe"]
        },
        {
            "id": "taskmgr",
            "name": "Administrador de Tareas",
            "icon": "/static/icons/sliders.svg",
            "color": "#8B5CF6",
            "category": "Sistema",
            "exe_names": ["taskmgr.exe"],
            "paths": ["taskmgr.exe"]
        },
        {
            "id": "voicemeeter",
            "name": "Voicemeeter",
            "icon": "/static/icons/sliders.svg",
            "color": "#E67E22",
            "category": "Audio",
            "exe_names": ["voicemeeter8x64.exe", "voicemeeter8.exe", "voicemeeterpro.exe", "Voicemeeter.exe"],
            "paths": [
                r"C:\Program Files (x86)\VB\Voicemeeter\voicemeeter8x64.exe",
                r"C:\Program Files (x86)\VB\Voicemeeter\voicemeeterpro.exe",
                r"C:\Program Files (x86)\VB\Voicemeeter\Voicemeeter.exe"
            ]
        },
        {
            "id": "capcut",
            "name": "CapCut PC",
            "icon": "/static/icons/video.svg",
            "color": "#00E5FF",
            "category": "Multimedia",
            "exe_names": ["CapCut.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\CapCut\Apps\*\CapCut.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\CapCut\CapCut.exe")
            ]
        },
        {
            "id": "gimp",
            "name": "GIMP",
            "icon": "/static/icons/brush.svg",
            "color": "#5C5543",
            "category": "Diseño",
            "exe_names": ["gimp-2.10.exe", "gimp-3.0.exe", "gimp.exe"],
            "paths": [
                r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe",
                r"C:\Program Files\GIMP 3\bin\gimp-3.0.exe"
            ]
        },
        {
            "id": "photoshop",
            "name": "Adobe Photoshop",
            "icon": "/static/icons/photoshop.svg",
            "color": "#31A8FF",
            "category": "Diseño",
            "exe_names": ["Photoshop.exe"],
            "paths": [
                r"C:\Program Files\Adobe\Adobe Photoshop *\Photoshop.exe",
                r"C:\Program Files\Adobe\Photoshop *\Photoshop.exe"
            ]
        },
        {
            "id": "premiere",
            "name": "Adobe Premiere Pro",
            "icon": "/static/icons/premiere.svg",
            "color": "#9999FF",
            "category": "Multimedia",
            "exe_names": ["Adobe Premiere Pro.exe"],
            "paths": [
                r"C:\Program Files\Adobe\Adobe Premiere Pro *\Adobe Premiere Pro.exe"
            ]
        },
        {
            "id": "brave",
            "name": "Brave Browser",
            "icon": "/static/icons/chrome.svg",
            "color": "#FB542B",
            "category": "Navegadores",
            "exe_names": ["brave.exe"],
            "paths": [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe")
            ]
        },
        {
            "id": "operagx",
            "name": "Opera GX",
            "icon": "/static/icons/opera.svg",
            "color": "#FA1E4E",
            "category": "Navegadores",
            "exe_names": ["opera.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\opera.exe"),
                r"C:\Program Files\Opera GX\opera.exe"
            ]
        },
        {
            "id": "telegram",
            "name": "Telegram Desktop",
            "icon": "/static/icons/telegram.svg",
            "color": "#24A1DE",
            "category": "Comunicaciones",
            "exe_names": ["Telegram.exe"],
            "paths": [
                os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Telegram Desktop\Telegram.exe")
            ]
        },
        {
            "id": "whatsapp",
            "name": "WhatsApp",
            "icon": "/static/icons/whatsapp.svg",
            "color": "#25D366",
            "category": "Comunicaciones",
            "exe_names": ["WhatsApp.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\WhatsApp\WhatsApp.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\WhatsApp.exe")
            ]
        },
        {
            "id": "github_desktop",
            "name": "GitHub Desktop",
            "icon": "/static/icons/github.svg",
            "color": "#9B51E0",
            "category": "Desarrollo",
            "exe_names": ["GitHubDesktop.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\app-*\GitHubDesktop.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\GitHubDesktop.exe")
            ]
        },
        {
            "id": "terminal",
            "name": "Windows Terminal",
            "icon": "/static/icons/terminal.svg",
            "color": "#4CC2FF",
            "category": "Desarrollo",
            "exe_names": ["wt.exe"],
            "paths": [
                "wt.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe")
            ]
        },
        {
            "id": "audacity",
            "name": "Audacity",
            "icon": "/static/icons/mic.svg",
            "color": "#0066CC",
            "category": "Multimedia",
            "exe_names": ["audacity.exe"],
            "paths": [
                r"C:\Program Files\Audacity\audacity.exe",
                r"C:\Program Files (x86)\Audacity\audacity.exe"
            ]
        },
        {
            "id": "blender",
            "name": "Blender",
            "icon": "/static/icons/blender.svg",
            "color": "#EA7600",
            "category": "Diseño",
            "exe_names": ["blender.exe"],
            "paths": [
                r"C:\Program Files\Blender Foundation\Blender *\blender.exe"
            ]
        },
        {
            "id": "minecraft",
            "name": "Minecraft",
            "icon": "/static/icons/minecraft.svg",
            "color": "#5B8731",
            "category": "Juegos",
            "exe_names": ["MinecraftLauncher.exe", "Minecraft.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Packages\Microsoft.4297127D64C94_8wekyb3d8bbwe\LocalCache\Local\Microsoft\WritablePackageRoot\Minecraft.exe"),
                r"C:\Program Files (x86)\Minecraft Launcher\MinecraftLauncher.exe"
            ]
        },
        {
            "id": "roblox",
            "name": "Roblox",
            "icon": "/static/icons/roblox.svg",
            "color": "#000000",
            "category": "Juegos",
            "exe_names": ["RobloxPlayerLauncher.exe", "RobloxPlayerBeta.exe"],
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Roblox\Versions\*\RobloxPlayerBeta.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Roblox\Versions\*\RobloxPlayerLauncher.exe")
            ]
        },
    ]

    _cache: List[Dict[str, Any]] = []
    _cache_time = 0.0
    _lock = threading.Lock()
    CACHE_SECONDS = 600

    @classmethod
    def get_detected_apps(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """The apps installed on this PC, from a cache (10 minutes). Only one scan runs at a time."""
        if not force_refresh and cls._cache and time.time() - cls._cache_time < cls.CACHE_SECONDS:
            return cls._cache
        with cls._lock:
            # Someone else may have finished the scan while this call waited for the lock.
            if not force_refresh and cls._cache and time.time() - cls._cache_time < cls.CACHE_SECONDS:
                return cls._cache
            apps = cls._scan()
            cls._cache = apps
            cls._cache_time = time.time()
            return apps

    @classmethod
    def warm_up(cls) -> None:
        """Scan in the background at startup, so the list is ready when the apps tab is first opened."""
        threading.Thread(target=cls.get_detected_apps, name="app-scan", daemon=True).start()

    @classmethod
    def public_apps(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """What Studio is told: no launch details and no local paths, only what it needs to draw a card."""
        return [{key: app[key] for key in ("id", "name", "icon", "color", "category", "exe_name")}
                for app in cls.get_detected_apps(force_refresh)]

    @classmethod
    def find(cls, app_id: str) -> Optional[Dict[str, Any]]:
        key = (app_id or "").lower().strip()
        return next((app for app in cls.get_detected_apps() if app["id"].lower() == key), None)

    @classmethod
    def _scan(cls) -> List[Dict[str, Any]]:
        curated = cls._scan_curated()
        found = cls._scan_start_menu(curated)
        if not found:
            found = cls._scan_registry(curated)  # PowerShell blocked or missing: the old way still finds the common programs
        apps = curated + found
        for app in apps:
            app["category"] = normalize_category(app.get("category", ""))
        order = {name: position for position, name in enumerate(CATEGORIES)}
        apps.sort(key=lambda app: (order[app["category"]], app["name"].lower()))
        return apps

    @classmethod
    def _scan_curated(cls) -> List[Dict[str, Any]]:
        """The well-known programs, with their own icon and colour, when they are installed where they usually are."""
        detected = []
        for app in cls.POPULAR_APPS:
            found_path = None
            for p in app["paths"]:
                if p in ("calc.exe", "notepad.exe", "taskmgr.exe", "wt.exe") or shutil.which(p):
                    found_path = p
                    break
                raw_path = p.split(" --")[0] if " --" in p else p
                if "*" in raw_path:
                    matches = glob.glob(raw_path)
                    if matches and os.path.exists(matches[0]):
                        found_path = matches[0]
                        break
                elif os.path.exists(raw_path):
                    found_path = p
                    break
            if found_path:
                detected.append({
                    "id": app["id"], "name": app["name"], "icon": app["icon"], "color": app["color"],
                    "category": app.get("category", "General"), "path": found_path, "exe_name": app["exe_names"][0],
                    "exe_names": [name.lower() for name in app["exe_names"]],
                    "icon_source": found_path.split(" --")[0] if os.path.isabs(found_path.split(" --")[0]) else "",
                })
        return detected

    @staticmethod
    def _start_apps() -> List[Dict[str, str]]:
        """Windows' own list of what the Start menu shows: classic programs, Store apps and Steam games."""
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                  "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
        shell = shutil.which("powershell.exe") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        try:
            result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                                    stdin=subprocess.DEVNULL, timeout=30, creationflags=CREATE_NO_WINDOW)
            data = json.loads(result.stdout.decode("utf-8", errors="replace") or "[]")
        except Exception as exc:
            print(f"Could not read the Start menu apps: {exc}")
            return []
        data = [data] if isinstance(data, dict) else data
        return [{"name": str(item.get("Name") or "").strip(), "appid": str(item.get("AppID") or "").strip()}
                for item in data if isinstance(item, dict)]

    @staticmethod
    def _resolve_appid_path(appid: str) -> str:
        """The .exe file behind a Start entry, when its id is a path (with or without a folder code in front)."""
        match = re.match(r"^\{([0-9A-Fa-f-]{36})\}\\(.+)$", appid)
        if match:
            base = _KNOWN_FOLDERS.get(match.group(1).upper())
            return os.path.join(os.path.expandvars(base), match.group(2)) if base else ""
        return appid if re.match(r"^[A-Za-z]:\\", appid) else ""

    @staticmethod
    def _make_id(name: str, unique_source: str, used: set) -> str:
        """A short id made of the name (letters, digits, underscore). A repeated name gets a few characters of a hash."""
        base = re.sub(r"[^a-z0-9]+", "_", unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()).strip("_")[:30] or "app"
        app_id = base if base not in used else f"{base}_{hashlib.sha1(unique_source.encode('utf-8')).hexdigest()[:4]}"
        used.add(app_id)
        return app_id

    @classmethod
    def _scan_start_menu(cls, curated: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        known_names = {_plain(app["name"]) for app in curated}
        known_exes = {exe for app in curated for exe in app["exe_names"]}
        used_ids = {app["id"] for app in curated}
        seen_names = set()
        found = []
        for entry in sorted(cls._start_apps(), key=lambda e: (e["name"].lower(), e["appid"])):
            name, appid = entry["name"], entry["appid"]
            if len(name) < 2 or not appid or _NOISE_NAME.search(name):
                continue
            plain = _plain(name)
            if not plain or plain in seen_names:
                continue
            # The same program as one of the well-known ones ("Epic Games Launcher" is "Epic Games"): theirs wins.
            if plain in known_names or any(len(k) >= 5 and (k in plain or plain in k) for k in known_names):
                continue

            exe_path = cls._resolve_appid_path(appid)
            steam = re.fullmatch(r"steam://rungameid/\d+", appid, re.IGNORECASE)
            if steam:
                launch = {"type": "steam", "url": appid}
            elif exe_path:
                exe_name = os.path.basename(exe_path).lower()
                if not exe_name.endswith(".exe") or _NOISE_EXE.search(exe_name) or exe_name in known_exes:
                    continue  # a document, a folder, an uninstaller, or something already listed
                launch = {"type": "appsfolder", "appid": appid}
            elif "://" in appid or appid.lower().endswith((".url", ".lnk", ".chm", ".txt", ".html", ".htm")):
                continue  # a web link or a help file
            else:
                launch = {"type": "appsfolder", "appid": appid}  # a Store app or a shortcut: Windows opens it by this id

            seen_names.add(plain)
            found.append({
                "id": cls._make_id(name, appid, used_ids), "name": name[:64],
                "icon": GENERIC_ICON if steam else resolve_app_icon(name.lower(), fuzzy=False),
                "color": "#f8c700", "category": "Juegos" if steam else guess_category(name),
                "path": exe_path or appid, "exe_name": os.path.basename(exe_path) if exe_path else "",
                "launch": launch, "icon_source": exe_path,
            })
        return found

    @classmethod
    def _scan_registry(cls, curated: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fallback: programs that registered an uninstaller. Only real .exe files, never folders or uninstallers."""
        known_names = {_plain(app["name"]) for app in curated}
        used_ids = {app["id"] for app in curated}
        found = []
        for hkey, subkey in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ):
            try:
                key = winreg.OpenKey(hkey, subkey)
            except OSError:
                continue
            with key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, i)) as app_key:
                            name = str(winreg.QueryValueEx(app_key, "DisplayName")[0] or "").strip()
                            icon = str(winreg.QueryValueEx(app_key, "DisplayIcon")[0] or "").split(",")[0].strip('"')
                    except OSError:
                        continue
                    plain = _plain(name)
                    if (len(name) < 3 or not plain or plain in known_names or _NOISE_NAME.search(name)
                            or not icon.lower().endswith(".exe") or _NOISE_EXE.search(os.path.basename(icon))
                            or not os.path.isfile(icon)):
                        continue
                    known_names.add(plain)
                    found.append({
                        "id": cls._make_id(name, icon, used_ids), "name": name[:64], "icon": resolve_app_icon(name.lower(), fuzzy=False),
                        "color": "#f8c700", "category": guess_category(name), "path": icon, "exe_name": os.path.basename(icon),
                        "launch": {"type": "file", "path": icon}, "icon_source": icon,
                    })
        return found


system_scanner = SystemScanner()
