"""Per-user connector settings (OBS password, Spotify tokens, Discord hotkeys).

Lives next to the deck profile in the user data directory. Secret values are
never returned to the browser (use `public()` for anything that leaves the PC) and are
encrypted on disk with Windows DPAPI, so the file alone does not give them away.
"""

import base64
import ctypes
import json
import os
import threading
from ctypes import wintypes
from typing import Any, Dict, Iterable, Optional

from server.paths import CONFIG_DIR

SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Keys that must never be sent to Studio or a phone.
SECRET_KEYS = frozenset({"password", "access_token", "refresh_token"})


SECRET_PREFIX = "dpapi:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


def _dpapi(data: bytes, encrypt: bool) -> Optional[bytes]:
    """Windows DPAPI: only this Windows user, on this PC, can decrypt what it encrypted. None if it cannot."""
    if not hasattr(ctypes, "windll"):
        return None
    buffer = ctypes.create_string_buffer(data, len(data))  # must outlive the call
    source = _Blob(len(data), ctypes.addressof(buffer))
    result = _Blob()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    function = crypt32.CryptProtectData if encrypt else crypt32.CryptUnprotectData
    # Both take (data in, description, entropy, reserved, prompt, flags, data out).
    if not function(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        return None
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)


def seal(value: str) -> str:
    """The text to write to disk for a secret: encrypted for this Windows user when possible."""
    sealed = _dpapi(value.encode("utf-8"), True)
    return SECRET_PREFIX + base64.b64encode(sealed).decode("ascii") if sealed else value


def unseal(value: str) -> str:
    """The secret behind what is on disk. Plain text (written by an older version) is returned as it is; an
    encrypted value this user cannot open (a profile copied from another PC) comes back empty, so it is asked again."""
    if not value.startswith(SECRET_PREFIX):
        return value
    try:
        opened = _dpapi(base64.b64decode(value[len(SECRET_PREFIX):]), False)
    except ValueError:
        opened = None
    return opened.decode("utf-8") if opened is not None else ""


def _map_secrets(data: Dict[str, Dict[str, Any]], convert) -> Dict[str, Dict[str, Any]]:
    return {
        section: {key: convert(value) if key in SECRET_KEYS and isinstance(value, str) and value else value
                  for key, value in values.items()} if isinstance(values, dict) else values
        for section, values in data.items()
    }


class SettingsStore:
    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return _map_secrets(data, unseal) if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: Dict[str, Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(_map_secrets(data, seal), handle, indent=2)
        os.replace(temporary, self.path)

    def get(self, section: str) -> Dict[str, Any]:
        with self._lock:
            section_data = self._read().get(section, {})
            return dict(section_data) if isinstance(section_data, dict) else {}

    def update(self, section: str, values: Dict[str, Any], remove: Iterable[str] = ()) -> Dict[str, Any]:
        with self._lock:
            data = self._read()
            current = data.get(section) if isinstance(data.get(section), dict) else {}
            current.update(values)
            for key in remove:
                current.pop(key, None)
            data[section] = current
            self._write(data)
            return dict(current)

    def clear(self, section: str) -> None:
        with self._lock:
            data = self._read()
            if data.pop(section, None) is not None:
                self._write(data)

    def public(self, section: str) -> Dict[str, Any]:
        """The section without secrets, plus `<key>_set` flags so the UI can show "saved"."""
        values = self.get(section)
        visible = {key: value for key, value in values.items() if key not in SECRET_KEYS}
        for key in SECRET_KEYS:
            if key in values:
                visible[f"{key}_set"] = bool(values[key])
        return visible


settings = SettingsStore()
