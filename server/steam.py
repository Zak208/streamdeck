"""The games installed in the user's Steam, read from Steam's own files (nothing is sent anywhere)."""

import glob
import os
import re
from typing import Any, Dict, List

LIBRARY_PATH = re.compile(r'"path"\s+"([^"]+)"')
APP_ID = re.compile(r'"appid"\s+"([0-9]+)"')
APP_NAME = re.compile(r'"name"\s+"([^"]+)"')
# Steam's own tools and runtimes show up as installed "apps": they are not games the user launches.
NOT_GAMES = ("Steamworks Common Redistributables", "Steam Linux Runtime", "Proton")
MAX_GAMES = 500


def steam_folder() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            return os.path.normpath(winreg.QueryValueEx(key, "SteamPath")[0])
    except (OSError, ImportError):
        return ""


def library_folders(steam: str) -> List[str]:
    folders = [steam] if steam else []
    try:
        with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as handle:
            for path in LIBRARY_PATH.findall(handle.read()):
                path = os.path.normpath(path.replace("\\\\", "\\"))
                if path not in folders:
                    folders.append(path)
    except OSError:
        pass
    return folders


def installed_games() -> List[Dict[str, Any]]:
    games: Dict[str, str] = {}
    for folder in library_folders(steam_folder()):
        for manifest in glob.glob(os.path.join(folder, "steamapps", "appmanifest_*.acf")):
            try:
                with open(manifest, encoding="utf-8", errors="replace") as handle:
                    text = handle.read(4000)
            except OSError:
                continue
            app_id, name = APP_ID.search(text), APP_NAME.search(text)
            if app_id and name and not name.group(1).startswith(NOT_GAMES):
                games[app_id.group(1)] = name.group(1)
    return [{"appid": app_id, "name": name} for app_id, name in sorted(games.items(), key=lambda item: item[1].lower())][:MAX_GAMES]
