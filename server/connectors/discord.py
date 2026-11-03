"""Discord: mute and deafen through the global keybinds the user sets once in Discord, and the
soundboard of any server through a bot the user creates (see server/discord_bot.py).

Discord offers no supported way for another app to toggle mute or deafen, so StreamDesk presses
the shortcut the user chose. The soundboard needs a bot token, kept like the OBS password and never
sent back to Studio.
"""

import re
from typing import Any, Dict, List

import psutil

from server.action_catalog import validate_hotkey
from server.discord_bot import DiscordError, bot
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
SNOWFLAKE = re.compile(r"^\d{15,25}$")
GUILD_OPTION = re.compile(r"^(\d{15,25}|default)$")


def hotkeys() -> Dict[str, str]:
    saved = settings.get("discord")
    return {key: saved.get(key) or default for key, default in DEFAULT_HOTKEYS.items()}


def _discord_running() -> bool:
    return any((p.info["name"] or "").lower() == "discord.exe" for p in psutil.process_iter(["name"]))


def configure(values: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key in DEFAULT_HOTKEYS:
        if key in values:
            clean[key] = validate_hotkey(values[key])
    merged = {**hotkeys(), **clean}
    if merged["mute_hotkey"] == merged["deafen_hotkey"]:
        raise ValueError("Silenciar y ensordecer necesitan atajos distintos")

    bot_changed = False
    if values.get("remove_bot"):
        settings.update("discord", {}, remove=("bot_token", "bot_id", "bot_name", "user_id"))
        bot_changed = True
    if "user_id" in values:
        user_id = str(values["user_id"]).strip()
        if not SNOWFLAKE.fullmatch(user_id):
            raise ValueError("El ID de usuario son solo números (15 a 25). Actívalo en Discord > Ajustes > Avanzado > Modo desarrollador.")
        clean["user_id"] = user_id
        bot_changed = True
    if "bot_token" in values:
        token = str(values["bot_token"]).strip()
        if token.lower().startswith("bot "):
            token = token[4:].strip()
        if not 40 <= len(token) <= 120 or any(char.isspace() for char in token):
            raise ValueError("Ese no parece un token de bot. Cópialo entero desde la pestaña Bot del portal de desarrolladores.")
        try:
            identity = bot.check(token)
        except DiscordError as exc:
            raise ValueError(str(exc)) from exc
        clean.update({"bot_token": token, "bot_id": identity["id"], "bot_name": identity["name"]})
        bot_changed = True

    settings.update("discord", clean)
    if bot_changed:
        bot.reload()
    return public_settings()


def public_settings() -> Dict[str, Any]:
    saved = settings.public("discord")
    visible = {**hotkeys(), "user_id": saved.get("user_id", ""), "bot_token_set": saved.get("bot_token_set", False),
               "bot_name": saved.get("bot_name", "")}
    if saved.get("bot_id"):
        visible["invite_url"] = bot.invite_url(saved["bot_id"])
    return visible


def status() -> Dict[str, Any]:
    soundboard = bot.summary()
    if not _discord_running():
        return {"state": "offline", "detail": f"Discord no está abierto. {soundboard}."}
    return {"state": "ready", "detail": f"Discord abierto. {soundboard}."}


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
    try:
        if name == "guilds":
            return [{"id": "default", "name": "Sonidos de Discord"}] + bot.list_guilds()
        if name == "voice":
            bot.refresh_config()
            here = bot.where_is_user()
            return [here] if here else []
        if name.startswith("sounds:"):
            guild_id = name.split(":", 1)[1]
            if not GUILD_OPTION.fullmatch(guild_id):
                raise RuntimeError("Servidor no válido")
            return bot.list_sounds(guild_id)
    except DiscordError as exc:
        raise RuntimeError(str(exc)) from exc
    return []
