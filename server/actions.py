"""The allow-listed actions that a paired mobile device may trigger."""

import ctypes
import os
import re
import time
import webbrowser
import winsound
from typing import Any, Dict
from urllib.parse import urlparse

import psutil

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


WM_APPCOMMAND = 0x0319
SPOTIFY_APPCOMMANDS = {
    "play_pause": 14,
    "play": 14,
    "pause": 14,
    "next": 11,
    "next_track": 11,
    "prev": 12,
    "previous": 12,
    "prev_track": 12,
    "stop": 13,
}


def _find_spotify_hwnds() -> list:
    """Find top-level Spotify windows to deliver media commands directly."""
    try:
        user32 = ctypes.windll.user32
        pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "spotify.exe"}
        if not pids:
            return []
        found: list = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_proc(hwnd, _):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids:
                cls_buff = ctypes.create_unicode_buffer(80)
                user32.GetClassNameW(hwnd, cls_buff, 80)
                if "Chrome_WidgetWin" in cls_buff.value:
                    found.append(hwnd)
            return True

        user32.EnumWindows(enum_proc, 0)
        return found
    except Exception:
        return []


def _post_spotify_media_command(media_key: str) -> None:
    cmd = SPOTIFY_APPCOMMANDS.get(media_key)
    if cmd is None:
        return
    try:
        user32 = ctypes.windll.user32
        lParam = cmd << 16
        for hwnd in _find_spotify_hwnds():
            user32.PostMessageW(hwnd, WM_APPCOMMAND, 0, lParam)
    except Exception:
        pass


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


def bring_window_to_front(hwnd: int) -> bool:
    """Bring a window to the foreground even if another app is currently in foreground."""
    if not hwnd:
        return False
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return False
    try:
        user32.AllowSetForegroundWindow(-1)
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)

        if fg_thread and fg_thread != target_thread:
            user32.AttachThreadInput(fg_thread, target_thread, True)
        if cur_thread != target_thread:
            user32.AttachThreadInput(cur_thread, target_thread, True)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

        if fg_thread and fg_thread != target_thread:
            user32.AttachThreadInput(fg_thread, target_thread, False)
        if cur_thread != target_thread:
            user32.AttachThreadInput(cur_thread, target_thread, False)
        return True
    except Exception:
        return False


def _find_running_app_window(exe_names: list) -> int:
    """Find the main top-level visible window for given executable name(s)."""
    try:
        user32 = ctypes.windll.user32
        names = {name.lower() for name in exe_names}
        pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() in names}
        if not pids:
            return 0
        candidates = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_proc(hwnd, _):
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and (user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd)):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    rect = (ctypes.c_long * 4)()
                    user32.GetWindowRect(hwnd, rect)
                    area = (rect[2] - rect[0]) * (rect[3] - rect[1])
                    candidates.append((area, hwnd))
            return True

        user32.EnumWindows(enum_proc, 0)
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
    except Exception:
        pass
    return 0


def launch_smart_app(app_id: str) -> bool:
    """Launch or focus an installed app selected by StreamDesk's own scanner."""
    app_key = (app_id or "").lower().strip()
    if not app_key:
        return False

    # If the app is already running, attempt to bring its window to the foreground first
    candidates_exe = [f"{app_key}.exe", app_key]
    for app in system_scanner.get_detected_apps():
        if app["id"].lower() == app_key:
            if app.get("exe_names"):
                candidates_exe.extend(app["exe_names"])
            if app.get("exe_name"):
                candidates_exe.append(app["exe_name"])
            break

    existing_hwnd = _find_running_app_window(candidates_exe)
    if existing_hwnd and bring_window_to_front(existing_hwnd):
        return True

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


def _is_current_process_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _is_foreground_window_elevated() -> bool:
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        advapi32 = ctypes.windll.advapi32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        from ctypes import wintypes
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == os.getpid():
            return False

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        hProcess = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hProcess:
            return kernel32.GetLastError() == 5  # ERROR_ACCESS_DENIED

        try:
            TOKEN_QUERY = 0x0008
            hToken = wintypes.HANDLE()
            if not advapi32.OpenProcessToken(hProcess, TOKEN_QUERY, ctypes.byref(hToken)):
                return kernel32.GetLastError() == 5

            try:
                TokenElevation = 20
                class TOKEN_ELEVATION(ctypes.Structure):
                    _fields_ = [("TokenIsElevated", wintypes.DWORD)]

                elevation = TOKEN_ELEVATION()
                ret_len = wintypes.DWORD()
                if advapi32.GetTokenInformation(
                    hToken, TokenElevation, ctypes.byref(elevation),
                    ctypes.sizeof(elevation), ctypes.byref(ret_len)
                ):
                    return bool(elevation.TokenIsElevated)
                return False
            finally:
                kernel32.CloseHandle(hToken)
        finally:
            kernel32.CloseHandle(hProcess)
    except Exception:
        return False


def check_elevated_foreground() -> str | None:
    if not _is_current_process_elevated() and _is_foreground_window_elevated():
        return "La ventana activa se ejecuta como administrador. Para controlarla, inicia StreamDesk como administrador."
    return None


_last_mci_alias: str | None = None


def play_local_sound(target: str) -> bool:
    global _last_mci_alias
    if not target or not isinstance(target, str):
        return False
    if target == "beep":
        winsound.Beep(1000, 200)
        return True
    if target == "asterisk":
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        return True
    if target == "exclamation":
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        return True

    # Reject quotes, directory traversal (..), path separators, and absolute paths
    if '"' in target or ".." in target or os.path.isabs(target) or "\\" in target or "/" in target:
        return False

    clean_name = os.path.basename(target)
    if not clean_name or clean_name != target:
        return False

    from server.paths import CONFIG_DIR
    sound_dir = os.path.abspath(os.path.join(CONFIG_DIR, "sounds"))
    candidate = os.path.abspath(os.path.join(sound_dir, clean_name))

    try:
        if os.path.commonpath([sound_dir, candidate]) != sound_dir or candidate == sound_dir:
            return False
    except Exception:
        return False

    if not os.path.isfile(candidate):
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        return False

    ext = os.path.splitext(candidate)[1].lower()
    if ext == ".wav":
        winsound.PlaySound(candidate, winsound.SND_ASYNC | winsound.SND_FILENAME)
        return True

    try:
        if _last_mci_alias:
            ctypes.windll.winmm.mciSendStringW(f'close {_last_mci_alias}', None, 0, 0)
        alias = f"sd_snd_{int(time.time() * 1000) % 10000}"
        _last_mci_alias = alias
        ctypes.windll.winmm.mciSendStringW(f'close {alias}', None, 0, 0)
        ret = ctypes.windll.winmm.mciSendStringW(f'open "{candidate}" type mpegvideo alias {alias}', None, 0, 0)
        if ret == 0:
            ctypes.windll.winmm.mciSendStringW(f'play {alias} from 0', None, 0, 0)
            return True
        else:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return False
    except Exception:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
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
            ok = launch_smart_app(target)
            if not ok:
                return {"success": False, "error": f"No encuentro «{target}» en este PC", "action": action_type, "target": target}
            return {"success": True, "action": action_type, "target": target}

        if action_type == "spotify_uri":
            return spotify.play(target)

        if action_type == "spotify_action":
            if target in ("like", "toggle_like"):
                return spotify.toggle_like()
            if target in ("shuffle", "toggle_shuffle"):
                return spotify.toggle_shuffle()
            if target in ("repeat", "cycle_repeat"):
                return spotify.cycle_repeat()
            return {"success": False, "error": "Acción de Spotify no válida"}

        if action_type == "windows":
            return windows.execute(target, extra)

        if action_type == "hotkey":
            parts = [p.strip().upper() for p in (target or "").split("+") if p.strip()]
            if sorted(parts) == ["ALT", "B", "SHIFT"] and extra and (extra.get("pack") == "spotify" or extra.get("app") == "spotify"):
                # Intercept Spotify Like shortcut only if it belongs to Spotify pack
                return spotify.toggle_like()
            admin_err = check_elevated_foreground()
            if admin_err:
                return {"success": False, "error": admin_err, "action": action_type, "target": target}
            return {"success": send_hotkey(target, require_modifier=False), "action": action_type, "target": target}

        if action_type == "text":
            admin_err = check_elevated_foreground()
            if admin_err:
                return {"success": False, "error": admin_err, "action": action_type, "target": target}
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
            if extra and (extra.get("app") == "spotify" or extra.get("player") == "spotify"):
                _post_spotify_media_command(media_key)
                ok = True
            else:
                ok = send_vk_key(media_map[media_key])
            return {"success": ok, "action": action_type, "target": target}

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
            ok = play_local_sound(target)
            if not ok:
                return {"success": False, "error": f"El archivo de sonido «{target}» no existe en este PC", "action": action_type, "target": target}
            return {"success": True, "action": action_type, "target": target}

        if action_type == "twitch":
            channel = str((extra or {}).get("channel", "")).strip().lstrip("@")
            cmd = str(target).lower()
            if cmd == "chat":
                url = f"https://www.twitch.tv/popout/{channel}/chat" if channel else "https://www.twitch.tv"
                webbrowser.open(url)
                return {"success": True, "action": "twitch", "target": cmd}
            elif cmd == "dashboard":
                webbrowser.open("https://dashboard.twitch.tv/stream-manager")
                return {"success": True, "action": "twitch", "target": cmd}
            elif cmd == "clip":
                url = f"https://www.twitch.tv/{channel}/clip" if channel else "https://dashboard.twitch.tv"
                webbrowser.open(url)
                return {"success": True, "action": "twitch", "target": cmd}
            elif cmd in ("emote_only", "sub_only", "clear_chat", "marker"):
                return {"success": True, "action": "twitch", "target": cmd}

        if action_type == "condition":
            from server.obs_client import obs_client
            from server.audio_controller import audio_controller
            is_true = False
            cond = str(target).lower()
            if cond == "obs_streaming":
                is_true = bool(obs_client.is_streaming)
            elif cond == "obs_recording":
                is_true = bool(obs_client.is_recording)
            elif cond == "mic_muted":
                is_true = bool(windows.get_mic_muted())
            elif cond == "process_running":
                proc = str((extra or {}).get("process", "")).lower()
                sessions = audio_controller.get_audio_sessions()
                is_true = any(s.get("process_name", "").lower() == proc for s in sessions)
            branch = (extra or {}).get("then" if is_true else "else")
            if not branch or not isinstance(branch, dict):
                return {"success": True, "action": "condition", "branch": is_true, "noop": True}
            b_type = str(branch.get("action_type", ""))
            b_target = str(branch.get("target", ""))
            b_extra = branch.get("extra") or {}
            return execute_action(b_type, b_target, b_extra)

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

    actions = macro["extra"]["actions"]
    results = []
    for i, child in enumerate(actions):
        res = execute_single_action(child["action_type"], child["target"], child["extra"])
        results.append(res)
        if not res.get("success"):
            break
        if i < len(actions) - 1:
            delay = child.get("delay_ms", 150) / 1000.0
            if delay > 0:
                time.sleep(delay)
    outcome = {"success": all(result.get("success") for result in results), "type": "multi", "results": results}
    if not outcome["success"]:
        # The phone shows this text, so say which step failed and why.
        step, failed = next((n, r) for n, r in enumerate(results, 1) if not r.get("success"))
        outcome["error"] = f"Falló el paso {step} de {len(actions)}: {failed.get('error') or 'no se pudo ejecutar'}"
    return outcome
