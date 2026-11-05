"""Values that belong to a key: counters and the format of a countdown."""

import threading

from server.settings_store import settings

_lock = threading.Lock()
SECTION = "counters"
LIMIT = 1_000_000


def counter_value(btn_id: str) -> int:
    value = settings.get(SECTION).get(btn_id, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def change_counter(btn_id: str, target: str, step: int) -> int:
    """Add, subtract or reset the counter of a key and return the new value (kept between runs)."""
    with _lock:
        value = counter_value(btn_id)
        if target == "inc":
            value = min(value + step, LIMIT)
        elif target == "dec":
            value = max(value - step, -LIMIT)
        else:
            value = 0
        settings.update(SECTION, {btn_id: value})
        return value


def format_countdown(seconds: int) -> str:
    hours, rest = divmod(max(seconds, 0), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
