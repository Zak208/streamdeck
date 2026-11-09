"""The allow-listed actions that a paired mobile device may trigger."""

import ctypes
import os
import re
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
from server import discord_ui, shell_actions, webhooks
from server.connectors import discord as discord_connector, spotify, windows
from server.system_scanner import system_scanner


VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
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
HOTKEY_VK.update({"INSERT": 0x2D, "PAGEUP": 0x21, "PAGEDOWN": 0x22, "PRINTSCREEN": 0x2C})
# These share a scan code with a numpad key unless flagged as extended.
EXTENDED_KEYS = {"UP", "DOWN", "LEFT", "RIGHT", "HOME", "END", "DELETE", "INSERT", "PAGEUP", "PAGEDOWN"}
KEYEVENTF_EXTENDEDKEY = 0x0001


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


def send_hotkey(hotkey: str, require_modifier: bool = True) -> bool:
    """Press a validated key combination (a Discord global shortcut, or any hotkey button)."""
    keys = validate_hotkey(hotkey, require_modifier=require_modifier).split("+")
    try:
        user32 = ctypes.windll.user32
        presses = [(HOTKEY_VK[key], KEYEVENTF_EXTENDEDKEY if key in EXTENDED_KEYS else 0) for key in keys]
        # With the scan code of each key (MapVirtualKey): a program that reads scan codes ignores a key that has none.
        scans = {virtual_key: user32.MapVirtualKeyW(virtual_key, 0) for virtual_key, _ in presses}
        for virtual_key, flags in presses:
            user32.keybd_event(virtual_key, scans[virtual_key], flags, 0)
        # Hold the combination briefly: global shortcuts can miss a press that is released at once.
        time.sleep(0.08)
        for virtual_key, flags in reversed(presses):
            user32.keybd_event(virtual_key, scans[virtual_key], flags | KEYEVENTF_KEYUP, 0)
        return True
    except Exception as exc:
        print(f"Error sending hotkey {hotkey}: {exc}")
        return False


# ---- Typing text: SendInput with Unicode characters, so accents, emoji and any layout work ----

INPUT_KEYBOARD = 1
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_TAB = 0x09


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput), ("ki", _KeyboardInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", _InputUnion)]


def _key_event(virtual_key: int = 0, scan: int = 0, flags: int = 0) -> _Input:
    return _Input(INPUT_KEYBOARD, _InputUnion(ki=_KeyboardInput(virtual_key, scan, flags, 0, 0)))


def text_to_inputs(text: str, press_enter: bool = False) -> list:
    """Key events that type `text`. Newline and tab are real keys; everything else is sent as Unicode."""
    events = []
    for char in text:
        if char in "\n\t":
            key = VK_RETURN if char == "\n" else VK_TAB
            events += [_key_event(key), _key_event(key, flags=KEYEVENTF_KEYUP)]
            continue
        data = char.encode("utf-16-le")
        for offset in range(0, len(data), 2):  # characters outside the BMP are two UTF-16 units
            unit = int.from_bytes(data[offset:offset + 2], "little")
            events += [_key_event(scan=unit, flags=KEYEVENTF_UNICODE),
                       _key_event(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)]
    if press_enter:
        events += [_key_event(VK_RETURN), _key_event(VK_RETURN, flags=KEYEVENTF_KEYUP)]
    return events


def type_text(text: str, press_enter: bool = False) -> bool:
    events = text_to_inputs(text, press_enter)
    if not events:
        return False
    try:
        batch = (_Input * len(events))(*events)
        return ctypes.windll.user32.SendInput(len(events), batch, ctypes.sizeof(_Input)) == len(events)
    except Exception as exc:
        print(f"Error typing text: {exc}")
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
        launch = app.get("launch") or {}
        try:
            # Apps found in the Start menu open the way a click there does. The id and the address come from
            # Windows' own list (the scanner), never from the remotely editable profile.
            if launch.get("type") == "appsfolder":
                os.startfile("shell:AppsFolder\\" + launch["appid"])
                return True
            if launch.get("type") == "steam":
                if not re.fullmatch(r"steam://rungameid/\d+", launch.get("url", ""), re.IGNORECASE):
                    return False
                os.startfile(launch["url"])
                return True
            if launch.get("type") == "file":
                path = launch["path"]
            # Discord's updater needs its documented process argument. It is
            # constructed here, never taken from the remotely editable profile.
            if app_key == "discord" and "Update.exe" in path:
                import subprocess
                updater = path.split(" --", 1)[0]
                subprocess.Popen([updater, "--processStart", "Discord.exe"])
            else:
                # Start it in its own folder, as Explorer does. OBS, for one, looks for locale/en-US.ini relative to
                # where it was started and refuses to open ("no encuentra en-US") when started from another folder.
                folder = os.path.dirname(path) if os.path.isabs(path) else None
                os.startfile(path, cwd=folder) if folder else os.startfile(path)
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


def play_local_sound(target: str) -> None:
    if target == "beep":
        winsound.Beep(1000, 200)
        return
    if target == "asterisk":
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        return
    if target == "exclamation":
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        return

    from server.paths import CONFIG_DIR
    sound_dir = os.path.join(CONFIG_DIR, "sounds")
    candidate = os.path.join(sound_dir, target) if not os.path.isabs(target) else target
    if not os.path.isfile(candidate):
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        return

    ext = os.path.splitext(candidate)[1].lower()
    if ext == ".wav":
        winsound.PlaySound(candidate, winsound.SND_ASYNC | winsound.SND_FILENAME)
        return

    try:
        alias = f"sd_snd_{int(time.time() * 1000) % 10000}"
        ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, 0)
        ret = ctypes.windll.winmm.mciSendStringW(f'open "{candidate}" type mpegvideo alias {alias}', None, 0, 0)
        if ret == 0:
            ctypes.windll.winmm.mciSendStringW(f'play {alias} from 0', None, 0, 0)
        else:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)


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

        if action_type == "spotify_action":
            if target in ("like", "toggle_like"):
                return spotify.toggle_like()
            return {"success": False, "error": "Acción de Spotify no válida"}

        if action_type == "windows":
            return windows.execute(target, extra)

        if action_type == "hotkey":
            return {"success": send_hotkey(target, require_modifier=False), "action": action_type, "target": target}

        if action_type == "text":
            return {"success": type_text(target, bool(extra.get("press_enter"))), "action": action_type}

        if action_type == "page":
            # Changing page needs the live phone connection; the server does it before reaching here.
            return {"success": False, "error": "El cambio de página solo funciona desde un botón del móvil"}

        if action_type == "discord_hotkey":
            if target not in DISCORD_TARGETS:
                return {"success": False, "error": "Acción de Discord no válida"}
            if target in ("mute", "deafen") and discord_connector.method() == "button":
                # Pressing Discord's own button needs no shortcut set up, and tells whether it is now on (the key lights up).
                try:
                    state = discord_ui.toggle_voice(target)
                except discord_ui.DiscordUiError as exc:
                    return {"success": False, "error": str(exc)}
                result = {"success": True, "action": action_type, "target": target}
                if state is not None:
                    result["active"] = state
                return result
            return {"success": send_hotkey(extra["hotkey"]), "action": action_type, "target": target}

        if action_type == "discord_sound":
            if extra.get("hotkey"):
                # The sound has its own shortcut in Discord: no window is touched, so it plays in the background.
                return {"success": send_hotkey(extra["hotkey"], require_modifier=False), "action": action_type, "target": target}
            try:
                discord_ui.play(extra["section"], target)
            except discord_ui.DiscordUiError as exc:
                return {"success": False, "error": str(exc)}
            return {"success": True, "action": action_type, "target": target}

        if action_type == "media":
            media_key = target.lower()
            media_map = {
                "play_pause": VK_MEDIA_PLAY_PAUSE, "play": VK_MEDIA_PLAY_PAUSE,
                "next": VK_MEDIA_NEXT_TRACK, "next_track": VK_MEDIA_NEXT_TRACK,
                "prev": VK_MEDIA_PREV_TRACK, "previous": VK_MEDIA_PREV_TRACK,
                "prev_track": VK_MEDIA_PREV_TRACK, "stop": VK_MEDIA_STOP, "mute": VK_VOLUME_MUTE,
                "volume_up": VK_VOLUME_UP, "volume_down": VK_VOLUME_DOWN,
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

        if action_type == "webhook":
            return webhooks.run(target, extra)

        if action_type == "command":
            return shell_actions.run(target, extra["commands"])

        if action_type == "folder":
            if not os.path.isdir(target):
                return {"success": False, "error": f"La carpeta {target} no existe en este PC"}
            os.startfile(target)  # a directory only opens in Explorer; it never runs anything
            return {"success": True, "action": action_type, "target": target}

        if action_type == "obs_action":
            from server.obs_client import obs_client
            return obs_client.execute_obs_action(target, extra)

        if action_type == "hardware_monitor":
            # These actions render live data on the deck. They do not open or
            # execute anything on the computer when a user taps them.
            return {"success": True, "action": action_type, "target": target, "read_only": True}

        if action_type == "steam":
            # steam:// is Steam's own protocol: the id is digits only (validated above), so nothing else can be passed.
            os.startfile(f"steam://rungameid/{target}")
            return {"success": True, "action": action_type, "target": target}

        if action_type == "none":
            return {"success": True, "action": "none", "noop": True}

        if action_type == "sound":
            play_local_sound(target)
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
    outcome = {"success": all(result.get("success") for result in results), "type": "multi", "results": results}
    if not outcome["success"]:
        # The phone shows this text, so say which step failed and why.
        step, failed = next((n, r) for n, r in enumerate(results, 1) if not r.get("success"))
        outcome["error"] = f"Falló el paso {step} de {len(results)}: {failed.get('error') or 'no se pudo ejecutar'}"
    return outcome
