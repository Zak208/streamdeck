"""Discord: mute and deafen through the global keybinds the user sets once in Discord, and the
soundboard through the Discord window itself (see server/discord_ui.py).

Discord offers no supported way for another app to toggle mute or deafen, so StreamDesk presses
the shortcut the user chose. Sounds are read from, and pressed in, the soundboard panel of the
user's own Discord window. Nothing about the Discord account is stored or used.
"""

from typing import Any, Dict, List

import psutil

from server import discord_ui
from server.action_catalog import validate_hotkey
from server.settings_store import settings

INFO = {
    "id": "discord",
    "name": "Discord",
    "icon": "/static/icons/discord.svg",
    "color": "#5865f2",
    "description": "Silenciar, ensordecer y reproducir sonidos del soundboard de tus servidores.",
}

# Chosen so they rarely clash with other apps (Ctrl+Shift+M is a Chrome shortcut).
DEFAULT_HOTKEYS = {"mute_hotkey": "CTRL+ALT+F9", "deafen_hotkey": "CTRL+ALT+F10"}


def hotkeys() -> Dict[str, str]:
    saved = settings.get("discord")
    return {key: saved.get(key) or default for key, default in DEFAULT_HOTKEYS.items()}


def _discord_running() -> bool:
    return any((p.info["name"] or "").lower() == "discord.exe" for p in psutil.process_iter(["name"]))


def configure(values: Dict[str, Any]) -> Dict[str, Any]:
    clean = {}
    for key in DEFAULT_HOTKEYS:
        if key in values:
            clean[key] = validate_hotkey(values[key])
    merged = {**hotkeys(), **clean}
    if merged["mute_hotkey"] == merged["deafen_hotkey"]:
        raise ValueError("Silenciar y ensordecer necesitan atajos distintos")
    settings.update("discord", clean)
    return public_settings()


def public_settings() -> Dict[str, Any]:
    return hotkeys()


def status() -> Dict[str, Any]:
    if not _discord_running():
        return {"state": "offline", "detail": "Discord no está abierto"}
    return {"state": "ready", "detail": "Discord abierto. Para los sonidos entra en un canal de voz y pulsa Buscar mis sonidos."}


def actions() -> List[Dict[str, Any]]:
    keys = hotkeys()
    return [
        {"id": "mute", "label": "Silenciar", "sublabel": "Discord", "icon": "/static/icons/mute.svg",
         "color": "#5865f2", "action_type": "discord_hotkey", "target": "mute",
         "extra": {"hotkey": keys["mute_hotkey"]}},
        {"id": "deafen", "label": "Ensordecer", "sublabel": "Discord", "icon": "/static/icons/volume_up.svg",
         "color": "#5865f2", "action_type": "discord_hotkey", "target": "deafen",
         "extra": {"hotkey": keys["deafen_hotkey"]}},
    ]


def options(name: str) -> List[Dict[str, Any]]:
    """Live lists from Discord. Raises RuntimeError with a readable reason."""
    if name == "sounds":
        try:
            sounds = discord_ui.list_sounds()
        except discord_ui.DiscordUiError as exc:
            raise RuntimeError(str(exc)) from exc
        except Exception as exc:  # Windows UI Automation failed in a way we cannot explain better
            raise RuntimeError("No se pudo leer el panel de sonidos de Discord. Comprueba que está abierto y a la vista.") from exc
        return [{**sound, "emoji": discord_ui.split_label(sound["label"])[0], "name": discord_ui.split_label(sound["label"])[1]}
                for sound in sounds]
    return []
