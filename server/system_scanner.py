import os
import winreg
from typing import List, Dict, Any

class SystemScanner:
    """Scans Windows for installed applications, focusing on creator/gamer tools."""

    COMMON_APPS = [
        {
            "id": "discord",
            "name": "Discord",
            "icon": "💬",
            "color": "#5865F2",
            "exe_names": ["Discord.exe"],
            "protocol": "discord://",
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Discord\app-*\Discord.exe")
            ]
        },
        {
            "id": "spotify",
            "name": "Spotify",
            "icon": "🎵",
            "color": "#1DB954",
            "exe_names": ["Spotify.exe"],
            "protocol": "spotify:",
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
                os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")
            ]
        },
        {
            "id": "obs",
            "name": "OBS Studio",
            "icon": "🎥",
            "color": "#302E31",
            "exe_names": ["obs64.exe", "obs32.exe"],
            "protocol": None,
            "paths": [
                r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
                r"C:\Program Files (x86)\obs-studio\bin\32bit\obs32.exe"
            ]
        },
        {
            "id": "steam",
            "name": "Steam",
            "icon": "🎮",
            "color": "#171A21",
            "exe_names": ["steam.exe"],
            "protocol": "steam://",
            "paths": [
                r"C:\Program Files (x86)\Steam\steam.exe",
                r"C:\Program Files\Steam\steam.exe"
            ]
        },
        {
            "id": "chrome",
            "name": "Google Chrome",
            "icon": "🌐",
            "color": "#EA4335",
            "exe_names": ["chrome.exe"],
            "protocol": "chrome://",
            "paths": [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
        },
        {
            "id": "opera",
            "name": "Opera GX",
            "icon": "🔴",
            "color": "#FA1E4E",
            "exe_names": ["launcher.exe"],
            "protocol": None,
            "paths": [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Opera GX\launcher.exe")
            ]
        },
        {
            "id": "voicemod",
            "name": "Voicemod",
            "icon": "🎙️",
            "color": "#00E5FF",
            "exe_names": ["VoicemodDesktop.exe"],
            "protocol": None,
            "paths": [
                r"C:\Program Files\Voicemod Desktop\VoicemodDesktop.exe"
            ]
        },
        {
            "id": "riot",
            "name": "Riot Client / Valorant",
            "icon": "⚔️",
            "color": "#D13639",
            "exe_names": ["RiotClientServices.exe"],
            "protocol": None,
            "paths": [
                r"C:\Riot Games\Riot Client\RiotClientServices.exe"
            ]
        }
    ]

    @classmethod
    def get_detected_apps(cls) -> List[Dict[str, Any]]:
        detected = []
        for app in cls.COMMON_APPS:
            found_path = None
            for p in app["paths"]:
                # Check direct or base path before arguments
                raw_path = p.split(" --")[0] if " --" in p else p
                if "*" in raw_path:
                    # Glob if needed
                    import glob
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
                    "path": found_path,
                    "exe_name": app["exe_names"][0]
                })

        return detected

system_scanner = SystemScanner()

