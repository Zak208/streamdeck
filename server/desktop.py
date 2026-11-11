"""StreamDesk as a normal PC app: it keeps running in the tray, starts with Windows and opens only once.

The phone talks to the server that lives inside this same process, so closing the window must not end the
process or the phone stops working. This module holds the parts that do not need a window (so they can be
tested): the "start with Windows" entry, the single-instance lock, the settings, and the hooks that the
window code in app_desktop.py plugs into.
"""

from __future__ import annotations

import ctypes
import os
import sys
import urllib.request
from typing import Callable, Optional

from server.paths import BASE_DIR, FROZEN, PORT
from server.settings_store import settings

try:
    import winreg
except ImportError:  # not Windows: the app is Windows-only, but importing the server must not fail
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "StreamDesk Pro"
BACKGROUND_FLAG = "--background"  # start hidden in the tray (what "start with Windows" uses)
MUTEX_NAME = "Local\\StreamDeskPro.SingleInstance"
ERROR_ALREADY_EXISTS = 183

_mutex_handle = None  # kept for the life of the process: closing it would release the lock


# --- start with Windows ---

def launch_command() -> str:
    """The command Windows runs at sign-in: this same app, started hidden."""
    if FROZEN:
        return f'"{sys.executable}" {BACKGROUND_FLAG}'
    # Running from source: pythonw has no console window.
    interpreter = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(interpreter):
        interpreter = sys.executable
    return f'"{interpreter}" "{os.path.join(BASE_DIR, "app_desktop.py")}" {BACKGROUND_FLAG}'


def autostart_supported() -> bool:
    return winreg is not None


def _read_run_value() -> Optional[str]:
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE)
            return str(value)
    except OSError:
        return None


def autostart_enabled() -> bool:
    return _read_run_value() is not None


def set_autostart(enabled: bool) -> None:
    if winreg is None:
        return
    if enabled:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, launch_command())
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE)
    except OSError:
        pass  # it was not there


def prepare_autostart() -> None:
    """Run once per start. A fresh install starts with Windows (the whole point is the phone working without
    opening the window; it is one switch to undo). An existing install is never changed behind its back.
    If it is already on, point it at where the app is now (an update or a move can change the path)."""
    if autostart_enabled():
        if _read_run_value() != launch_command():
            set_autostart(True)
        return
    app = settings.get("app")
    if FROZEN and not app.get("first_run_completed") and not app.get("autostart_decided"):
        set_autostart(True)
    if not app.get("autostart_decided"):
        settings.update("app", {"autostart_decided": True})


# --- keep running when the window is closed ---

def keep_running() -> bool:
    """Closing the window hides it to the tray instead of ending the app. On by default."""
    return bool(settings.get("app").get("keep_running", True))


def set_keep_running(enabled: bool) -> None:
    settings.update("app", {"keep_running": bool(enabled)})


# --- keep the PC awake while a phone is connected ---

ES_SYSTEM_REQUIRED = 0x00000001
AWAKE_EVERY = 30  # seconds: Windows sleeps after minutes of idle, so this is far more often than needed


def keep_awake() -> bool:
    """Off by default: stopping a PC from sleeping costs power, so it is the user's choice."""
    return bool(settings.get("app").get("keep_awake", False))


def set_keep_awake(enabled: bool) -> None:
    settings.update("app", {"keep_awake": bool(enabled)})


def hold_awake() -> None:
    """Tell Windows the system is in use (resets its idle timer once). Call again within AWAKE_EVERY seconds."""
    if hasattr(ctypes, "windll"):
        ctypes.windll.kernel32.SetThreadExecutionState(ES_SYSTEM_REQUIRED)


# --- a folder where the profile is copied on every save (OneDrive, a USB drive) ---

def backup_dir() -> str:
    return str(settings.get("app").get("backup_dir") or "")


def set_backup_dir(path: str) -> str:
    """Save the folder (or turn the copy off with ""). Returns the saved folder; ValueError if it is not usable."""
    path = (path or "").strip()
    if path:
        path = os.path.abspath(path)
        if not os.path.isdir(path):
            raise ValueError("Esa carpeta no existe")
        probe = os.path.join(path, ".streamdesk-prueba")
        try:
            with open(probe, "w") as handle:
                handle.write("ok")
            os.remove(probe)
        except OSError:
            raise ValueError("No se puede escribir en esa carpeta")
    settings.update("app", {"backup_dir": path})
    return path


# --- hooks plugged in by the window code ---

class Controller:
    """What the server can ask the window to do. Empty until app_desktop.py attaches it (and when the server
    runs without a window, as in the tests)."""

    def __init__(self) -> None:
        self.show: Optional[Callable[[], None]] = None
        self.quit: Optional[Callable[[], None]] = None
        self.phones: Callable[[], int] = lambda: 0  # how many phones are connected now
        self.notify: Optional[Callable[[str, str], None]] = None  # (title, text) as a Windows notification
        self.pick_folder: Optional[Callable[[], str]] = None  # opens Windows' folder chooser, returns the path or ""

    def tell(self, title: str, text: str) -> None:
        """A Windows notification, if there is a tray to show it (silently nothing otherwise)."""
        if self.notify:
            try:
                self.notify(title, text)
            except Exception:
                pass

    @property
    def attached(self) -> bool:
        return self.show is not None and self.quit is not None


controller = Controller()


# --- clipboard ---

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def copy_to_clipboard(text: str) -> bool:
    """Put text on the Windows clipboard (used by the tray menu, where no web page is in front to do it)."""
    if not hasattr(ctypes, "windll"):
        return False
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    data = (text + "\0").encode("utf-16-le")
    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    finally:
        user32.CloseClipboard()


# --- one copy only ---

def acquire_single_instance() -> bool:
    """True if this is the only copy running. A second copy would find the port busy and show a blank window."""
    global _mutex_handle
    if not hasattr(ctypes, "windll"):
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True  # cannot tell: better to start than to refuse
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def ask_running_instance_to_show(port: int = PORT) -> bool:
    """Tell the copy that is already running to bring its window forward. False if it did not answer."""
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/desktop/show", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=3):
            return True
    except Exception:
        return False

