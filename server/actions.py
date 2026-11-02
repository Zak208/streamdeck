"""The allow-listed actions that a paired mobile device may trigger."""

import ctypes
import os
import time
import webbrowser
import winsound
from typing import Any, Dict
from urllib.parse import urlparse

from server.action_catalog import (
    DISCORD_TARGETS,
    MEDIA_TARGETS,
    validate_action,
    validate_hotkey,
)
from server.connectors import spotify, windows
from server.system_scanner import system_scanner


VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
KEYEVENTF_KEYUP = 0x0002

HOTKEY_VK = {
    "CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5B,
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESC": 0x1B,
    "BACKSPACE": 0x08, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
}
HOTKEY_VK.update({chr(code): code for code in range(ord("A"), ord("Z") + 1)})
HOTKEY_VK.update({str(number): ord(str(number)) for number in range(10)})
HOTKEY_VK.update({f"F{number}": 0x6F + number for number in range(1, 25)})


def send_vk_key(vk_code: int) -> bool:
    """Simulate a dedicated media key press and release in Windows."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as exc:
        print(f"Error sending virtual key {vk_code}: {exc}")
        return False


def send_hotkey(hotkey: str) -> bool:
    """Send a validated user-configured Discord global key binding."""
    keys = validate_hotkey(hotkey).split("+")
    try:
        user32 = ctypes.windll.user32
        virtual_keys = [HOTKEY_VK[key] for key in keys]
        for virtual_key in virtual_keys:
            user32.keybd_event(virtual_key, 0, 0, 0)
        # Hold the combination briefly: Discord's global shortcuts can miss a press that is released at once.
        time.sleep(0.06)
        for virtual_key in reversed(virtual_keys):
            user32.keybd_event(virtual_key, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as exc:
        print(f"Error sending hotkey {hotkey}: {exc}")
        return False


def launch_smart_app(app_id: str) -> bool:
    """Launch only an installed app selected by StreamDesk's own scanner."""
    app_key = (app_id or "").lower().strip()
    if not app_key:
        return False

    for app in system_scanner.get_detected_apps():
        if app["id"].lower() != app_key:
            continue
        path = app["path"]
        try:
            # Discord's updater needs its documented process argument. It is
            # constructed here, never taken from the remotely editable profile.
            if app_key == "discord" and "Update.exe" in path:
                import subprocess
                updater = path.split(" --", 1)[0]
                subprocess.Popen([updater, "--processStart", "Discord.exe"])
            else:
                os.startfile(path)
            return True
        except OSError as exc:
            print(f"Failed to launch {app_key}: {exc}")
            return False

    known_protocols = {"spotify": "spotify:", "steam": "steam:"}
    if app_key in known_protocols:
        try:
            os.startfile(known_protocols[app_key])
            return True
        except OSError:
            return False
    return False


def execute_single_action(action_type: str, target: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Validate then execute one safe action. Custom shell commands are intentionally unsupported."""
    try:
        action = validate_action(action_type, target, extra, allow_multi=False)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    action_type = action["action_type"]
    target = action["target"]
    extra = action["extra"]
    try:
        if action_type in {"launch", "preset_app"}:
            return {"success": launch_smart_app(target), "action": action_type, "target": target}

        if action_type == "spotify_uri":
            return spotify.play(target)

        if action_type == "windows":
            return windows.execute(target, extra)

        if action_type == "discord_hotkey":
            if target not in DISCORD_TARGETS:
                return {"success": False, "error": "Acción de Discord no válida"}
            return {"success": send_hotkey(extra["hotkey"]), "action": action_type, "target": target}

        if action_type == "media":
            media_key = target.lower()
            media_map = {
                "play_pause": VK_MEDIA_PLAY_PAUSE, "play": VK_MEDIA_PLAY_PAUSE,
                "next": VK_MEDIA_NEXT_TRACK, "next_track": VK_MEDIA_NEXT_TRACK,
                "prev": VK_MEDIA_PREV_TRACK, "previous": VK_MEDIA_PREV_TRACK,
                "prev_track": VK_MEDIA_PREV_TRACK, "stop": VK_MEDIA_STOP, "mute": VK_VOLUME_MUTE,
            }
            if media_key not in MEDIA_TARGETS:
                return {"success": False, "error": "Comando multimedia desconocido"}
            return {"success": send_vk_key(media_map[media_key]), "action": action_type, "target": target}

        if action_type == "url":
            parsed = urlparse(target)
            if parsed.scheme not in {"http", "https"}:
                return {"success": False, "error": "Enlace no permitido"}
            webbrowser.open(target)
            return {"success": True, "action": action_type, "target": target}

        if action_type == "obs_action":
            from server.obs_client import obs_client
            return obs_client.execute_obs_action(target, extra)

        if action_type == "hardware_monitor":
            # These actions render live data on the deck. They do not open or
            # execute anything on the computer when a user taps them.
            return {"success": True, "action": action_type, "target": target, "read_only": True}

        if action_type == "sound":
            if target == "beep":
                winsound.Beep(1000, 200)
            elif target == "asterisk":
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return {"success": True, "action": action_type, "target": target}

        return {"success": False, "error": "Tipo de acción no soportado"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def execute_action(action_type: str, target: str, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run either one action or a small, fully allow-listed macro."""
    if (action_type or "").lower().strip() != "multi":
        return execute_single_action(action_type, target, extra)

    try:
        macro = validate_action(action_type, target, extra)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    results = []
    for child in macro["extra"]["actions"]:
        results.append(execute_single_action(child["action_type"], child["target"], child["extra"]))
        delay = child.get("delay_ms", 150) / 1000.0
        if delay:
            time.sleep(delay)
    return {"success": all(result.get("success") for result in results), "type": "multi", "results": results}
