"""A short in-memory log of what phones tried to do, to explain "it does not connect".

Kept in memory only (last 40 events, gone on restart). It stores the phone's address
and a coarse device label, never the PIN, the token or the full browser string.
"""

import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

_events: Deque[Dict[str, Any]] = deque(maxlen=40)


def device_label(user_agent: Optional[str]) -> str:
    agent = user_agent or ""
    if "iPhone" in agent or "iPad" in agent:
        return "iPhone/iPad"
    if "Android" in agent:
        return "Android"
    return "Navegador"


def record(kind: str, message: str, ip: str = "", user_agent: Optional[str] = None) -> None:
    _events.appendleft({
        "time": time.strftime("%H:%M:%S"),
        "kind": kind,
        "message": message,
        "ip": ip or "",
        "device": device_label(user_agent),
    })


def recent() -> List[Dict[str, Any]]:
    return list(_events)


def clear() -> None:
    _events.clear()
