"""Discord: mute and deafen through the global keybinds the user sets once in Discord, and the
soundboard through the Discord window itself (see server/discord_ui.py).

Discord offers no supported way for another app to toggle mute or deafen, so StreamDesk presses
the shortcut the user chose. Sounds are read from, and pressed in, the soundboard panel of the
user's own Discord window. Nothing about the Discord account is stored or used.
"""

from typing import Any, Dict, List

import psutil

from server import discord_cache, discord_ui
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


METHODS = ("button", "hotkey")


def method() -> str:
    """How mute and deafen are done: pressing Discord's own buttons (nothing to set up), or its global shortcuts."""
    saved = settings.get("discord").get("method")
    return saved if saved in METHODS else "button"


def hotkeys() -> Dict[str, str]:
    saved = settings.get("discord")
    return {key: saved.get(key) or default for key, default in DEFAULT_HOTKEYS.items()}


def _discord_running() -> bool:
    return any((p.info["name"] or "").lower() == "discord.exe" for p in psutil.process_iter(["name"]))


def configure(values: Dict[str, Any]) -> Dict[str, Any]:
    clean = {}
    if "method" in values:
        if values["method"] not in METHODS:
            raise ValueError("Elige pulsar el botón de Discord o usar un atajo")
        clean["method"] = values["method"]
    for key in DEFAULT_HOTKEYS:
        if key in values:
            clean[key] = validate_hotkey(values[key])
    merged = {**hotkeys(), **clean}
    if merged["mute_hotkey"] == merged["deafen_hotkey"]:
        raise ValueError("Silenciar y ensordecer necesitan atajos distintos")
    settings.update("discord", clean)
    return public_settings()


def public_settings() -> Dict[str, Any]:
    return {**hotkeys(), "method": method()}


def status() -> Dict[str, Any]:
    if not _discord_running():
        return {"state": "offline", "detail": "Discord no está abierto"}
    saved = discord_cache.count()
    kept = f" Tienes {saved} sonidos guardados para elegirlos sin estar en voz." if saved else ""
    return {"state": "ready", "detail": "Discord abierto. Para leer los sonidos la primera vez entra en un canal de voz." + kept}


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


def _decorate(sounds: List[Dict[str, Any]], **extra: Any) -> List[Dict[str, Any]]:
    return [{**sound, "emoji": discord_ui.split_label(sound["label"])[0], "name": discord_ui.split_label(sound["label"])[1], **extra}
            for sound in sounds]


def saved_sounds() -> List[Dict[str, Any]]:
    """The sounds of the last successful reading, marked `cached` so Studio can say where they come from."""
    saved = discord_cache.load()
    return _decorate(saved["sounds"], cached=True, scanned_at=discord_cache.describe_age(saved["scanned_at"]) or "")


def options(name: str) -> List[Dict[str, Any]]:
    """Live lists from Discord. Raises RuntimeError with a readable reason.

    Sounds fall back to the last reading when Discord cannot be read now (no voice channel, minimized...).
    """
    if name == "sounds":
        try:
            return _decorate(discord_ui.list_sounds())
        except Exception as exc:
            reason = str(exc) if isinstance(exc, discord_ui.DiscordUiError) else                 "No se pudo leer el panel de sonidos de Discord. Comprueba que está abierto y a la vista."
            kept = saved_sounds()
            if kept:
                return [{**sound, "reason": reason} for sound in kept]
            raise RuntimeError(reason) from exc
    if name == "voice":
        server = discord_ui.current_voice_server()
        return [{"server": server}] if server else []
    return []
