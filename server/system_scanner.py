import os
import glob
import winreg
from typing import List, Dict, Any

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
            "icon": "/static/icons/sliders.svg",
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
            "name": "Riot Client / Valorant",
            "icon": "/static/icons/gamepad.svg",
            "color": "#D13639",
            "category": "Juegos",
            "exe_names": ["RiotClientServices.exe"],
            "paths": [
                r"C:\Riot Games\Riot Client\RiotClientServices.exe"
            ]
        },
        {
            "id": "epicgames",
            "name": "Epic Games",
            "icon": "/static/icons/gamepad.svg",
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
            "icon": "/static/icons/chrome.svg",
            "color": "#0078D7",
            "category": "Navegadores",
            "exe_names": ["msedge.exe"],
            "paths": [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
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
        }
    ]

    @classmethod
    def get_detected_apps(cls) -> List[Dict[str, Any]]:
        """Returns verified list of apps installed on this PC."""
        detected = []
        seen_names = set()

        # 1. Scan popular curated list
        for app in cls.POPULAR_APPS:
            found_path = None
            for p in app["paths"]:
                if p in ("calc.exe", "notepad.exe", "taskmgr.exe"):
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
                                safe_id = "".join(c for c in clean_name if c.isalnum() or c == "_").lower()[:16]
                                detected.append({
                                    "id": safe_id,
                                    "name": clean_name[:24],
                                    "icon": "/static/icons/gamepad.svg" if ("game" in low or "play" in low or "war" in low) else "/static/icons/power.svg",
                                    "color": "#0ea5e9",
                                    "category": "Programas Instalados",
                                    "path": exec_path,
                                    "exe_name": os.path.basename(exec_path) if exec_path.endswith(".exe") else f"{safe_id}.exe"
                                })
                        except Exception:
                            pass
            except Exception:
                pass

        return detected

system_scanner = SystemScanner()
