"""The soundboard sounds Studio last read from the user's Discord window, kept on disk.

Reading them needs Discord open on a voice channel, but picking a sound for a button should not:
after one successful scan the list is served from here. Playing a sound still needs the voice
channel, because Discord only offers the panel there.
"""

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from server.paths import CONFIG_DIR

CACHE_FILE = os.path.join(CONFIG_DIR, "discord_sounds.json")
_lock = threading.Lock()


def _read() -> Dict[str, Any]:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def load() -> Dict[str, Any]:
    """{"scanned_at": str, "sounds": [{"section", "label"}]}; empty when nothing was saved yet."""
    with _lock:
        data = _read()
    sounds = [
        {"section": str(item["section"]), "label": str(item["label"])}
        for item in data.get("sounds", [])
        if isinstance(item, dict) and item.get("section") and item.get("label")
    ]
    return {"scanned_at": str(data.get("scanned_at") or ""), "sounds": sounds}


def save(found: List[Dict[str, Any]]) -> None:
    """Keeps the servers that were just read and the ones that were not (Discord shows only the servers you are in)."""
    seen = {sound["section"] for sound in found}
    with _lock:
        kept = [s for s in _read().get("sounds", []) if isinstance(s, dict) and s.get("section") not in seen]
        merged = [{"section": s["section"], "label": s["label"]} for s in kept if s.get("section") and s.get("label")]
        merged += [{"section": s["section"], "label": s["label"]} for s in found]
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        temporary = CACHE_FILE + ".tmp"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "scanned_at": datetime.now().isoformat(timespec="seconds"), "sounds": merged}, handle, ensure_ascii=False, indent=1)
        os.replace(temporary, CACHE_FILE)


def count() -> int:
    return len(load()["sounds"])


def describe_age(scanned_at: str) -> Optional[str]:
    """"05/11/2026 21:00" for the banner; None when the time is unknown."""
    try:
        return datetime.fromisoformat(scanned_at).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return None
