"""A record of the buttons phones pressed, kept on disk so it survives a restart.

It answers "who switched that off, and when" for a PC that more than one phone can control. It stores which phone,
which button (its label), what kind of action and whether it worked, never the target or the command text, which
can hold a password or a private address.
"""

import json
import os
import threading
import time
from typing import Any, Dict, List

from server.paths import CONFIG_DIR

LOG_FILE = os.path.join(CONFIG_DIR, "actions.log")
MAX_BYTES = 256 * 1024  # about 1,500 lines; one older copy is kept
_lock = threading.Lock()


def record(device: str, label: str, action_type: str, success: bool, gesture: str = "tap") -> None:
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "device": str(device or "")[:48],
        "button": str(label or "")[:60],
        "action": str(action_type or "")[:24],
        "gesture": gesture if gesture in ("tap", "long_press", "double_tap") else "tap",
        "ok": bool(success),
    }
    try:
        with _lock:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_BYTES:
                os.replace(LOG_FILE, LOG_FILE + ".bak")
            with open(LOG_FILE, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # a full disk must not stop a button from working


def recent(limit: int = 30) -> List[Dict[str, Any]]:
    """The newest entries first."""
    try:
        with _lock, open(LOG_FILE, "r", encoding="utf-8") as handle:
            lines = handle.readlines()[-limit:]
    except OSError:
        return []
    entries = []
    for line in reversed(lines):
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries
