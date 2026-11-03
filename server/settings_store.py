"""Per-user connector settings (OBS password, Spotify tokens, Discord hotkeys).

Lives next to the deck profile in the user data directory. Secret values are
never returned to the browser: use `public()` for anything that leaves the PC.
"""

import json
import os
import threading
from typing import Any, Dict, Iterable

from server.paths import CONFIG_DIR

SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

# Keys that must never be sent to Studio or a phone.
SECRET_KEYS = frozenset({"password", "access_token", "refresh_token"})


class SettingsStore:
    def __init__(self, path: str = SETTINGS_FILE):
        self.path = path
        self._lock = threading.Lock()

    def _read(self) -> Dict[str, Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: Dict[str, Dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = self.path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
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
