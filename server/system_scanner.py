import os
import shutil
import glob
import winreg
from typing import List, Dict, Any

def resolve_app_icon(name_lower: str) -> str:
    if "valorant" in name_lower or "riot" in name_lower:
        return "/static/icons/valorant.svg"
    if "cs2" in name_lower or "counter-strike" in name_lower or "cs:go" in name_lower:
        return "/static/icons/cs2.svg"
    if "league of legends" in name_lower or "lol" in name_lower:
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
    if "edge" in name_lower:
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
    if "epic" in name_lower:
        return "/static/icons/epic.svg"
    if "steam" in name_lower:
        return "/static/icons/steam.svg"
    if "discord" in name_lower:
        return "/static/icons/discord.svg"
    if "spotify" in name_lower:
        return "/static/icons/spotify.svg"
    if "obs" in name_lower:
        return "/static/icons/obs.svg"
    if "twitch" in name_lower:
        return "/static/icons/twitch.svg"
    if "youtube" in name_lower:
        return "/static/icons/youtube.svg"
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

    _cache = []
    _cache_time = 0

    @classmethod
    def get_detected_apps(cls, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Returns verified list of apps installed on this PC with 60s memory cache."""
        import time
        now = time.time()
        if not force_refresh and cls._cache and (now - cls._cache_time < 60):
            return cls._cache
        detected = []
        seen_names = set()

        # 1. Scan popular curated list
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
                    "id": app["id"],
                    "name": app["name"],
                    "icon": app["icon"],
                    "color": app["color"],
                    "category": app.get("category", "General"),
                    "path": found_path,
                    "exe_name": app["exe_names"][0]
                })
                seen_names.add(app["name"].lower())

        # 2. Scan Windows Registry for additional user programs
        registry_keys = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
        ]

        # Ignore helper/system noise
        ignore_words = ["driver", "redistributable", "update", "service", "framework", "directx", "vulkan", "runtime", "uninstall", "setup", "helper", "patch"]

        for hkey, subkey in registry_keys:
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    for i in range(min(winreg.QueryInfoKey(key)[0], 200)):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as app_key:
                                disp_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                if not disp_name or not isinstance(disp_name, str):
                                    continue
                                clean_name = disp_name.strip()
                                low = clean_name.lower()
                                if any(w in low for w in ignore_words) or len(clean_name) < 3 or low in seen_names:
                                    continue

                                # Get path or display icon
                                icon_path = ""
                                try:
                                    icon_path, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                    if icon_path:
                                        icon_path = icon_path.split(",")[0].strip('"')
                                except Exception:
                                    pass

                                install_dir = ""
                                try:
                                    install_dir, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                except Exception:
                                    pass

                                exec_path = icon_path if (icon_path and icon_path.lower().endswith(".exe") and os.path.exists(icon_path)) else install_dir
                                if not exec_path:
                                    continue

                                seen_names.add(low)
                                safe_id = "".join(c for c in clean_name if c.isalnum() or c == "_").lower()[:32]
                                detected.append({
                                    "id": safe_id,
                                    "name": clean_name[:64],
                                    "icon": resolve_app_icon(low),
                                    "color": "#0ea5e9",
                                    "category": "Programas Instalados",
                                    "path": exec_path,
                                    "exe_name": os.path.basename(exec_path) if exec_path.endswith(".exe") else f"{safe_id}.exe"
                                })
                        except Exception:
                            pass
            except Exception:
                pass

        cls._cache = detected
        cls._cache_time = time.time()
        return detected

system_scanner = SystemScanner()
