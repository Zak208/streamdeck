"""A short in-memory log of what phones tried to do, to explain "it does not connect".

Kept in memory only (last 40 events, gone on restart). It stores the phone's address
and a coarse device label, never the PIN, the token or the full browser string.
"""

import os
import platform
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

_events: Deque[Dict[str, Any]] = deque(maxlen=40)
# Set once any phone gets through. Kept apart from the log, which forgets old events.
_phone_reached = False


def device_label(user_agent: Optional[str]) -> str:
    agent = user_agent or ""
    if "iPhone" in agent or "iPad" in agent:
        return "iPhone/iPad"
    if "Android" in agent:
        return "Android"
    return "Navegador"


def record(kind: str, message: str, ip: str = "", user_agent: Optional[str] = None) -> None:
    global _phone_reached
    if kind == "ok":
        _phone_reached = True
    _events.appendleft({
        "time": time.strftime("%H:%M:%S"),
        "kind": kind,
        "message": message,
        "ip": ip or "",
        "device": device_label(user_agent),
    })


def recent() -> List[Dict[str, Any]]:
    return list(_events)


def phone_reached() -> bool:
    """True once a phone has paired or connected since StreamDesk started."""
    return _phone_reached


def clear() -> None:
    global _phone_reached
    _events.clear()
    _phone_reached = False


def tail(path: str, lines: int) -> str:
    """The last lines of a text file, or "" if it is not there."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return "".join(handle.readlines()[-lines:]).strip()
    except OSError:
        return ""


def build_report(version: str, facts: Dict[str, Any], log_paths: Dict[str, str]) -> str:
    """One text a user can paste to ask for help: versions, network facts, what phones tried, and the log tails.

    Holds no PIN, token, password or button content. `facts` are plain label/value pairs from the server."""
    out = [f"StreamDesk Pro {version}", f"Windows: {platform.platform()}", f"Fecha: {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    out += [f"{label}: {value}" for label, value in facts.items()]
    out.append("")
    out.append("Últimos intentos de móviles:")
    events = recent()[:15]
    out += [f"  {e['time']} [{e['kind']}] {e['device']} {e['message']}" for e in events] or ["  (ninguno)"]
    for name, path in log_paths.items():
        text = tail(path, 25)
        out += ["", f"{name} (últimas líneas):", text or "  (vacío)"]
    return chr(10).join(out)
