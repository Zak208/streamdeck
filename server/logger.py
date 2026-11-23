"""System logging for StreamDesk Pro.

Keeps detailed timestamps, severity levels (INFO, WARNING, ERROR, DEBUG),
sources, and structured context for all button presses, actions, connections,
and system errors.
Writes to streamdesk.log (with rotation at 1 MB) and maintains an in-memory
circular buffer for real-time inspection in Studio and mobile devices.
"""

import json
import os
import threading
import time
import traceback
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from server.paths import CONFIG_DIR

LOG_FILE = os.path.join(CONFIG_DIR, "streamdesk.log")
MAX_BYTES = 1024 * 1024  # 1 MB
MAX_MEMORY_LOGS = 500

_lock = threading.Lock()
_recent_logs: Deque[Dict[str, Any]] = deque(maxlen=MAX_MEMORY_LOGS)
_id_counter = 0


def _rotate_if_needed() -> None:
    """Rotate streamdesk.log to streamdesk.log.bak when it exceeds MAX_BYTES."""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > MAX_BYTES:
            bak = LOG_FILE + ".bak"
            if os.path.exists(bak):
                try:
                    os.remove(bak)
                except OSError:
                    pass
            os.replace(LOG_FILE, bak)
    except OSError:
        pass


def log(
    level: str,
    source: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    exc: Optional[BaseException] = None,
) -> Dict[str, Any]:
    """Append a structured log entry in memory and write to streamdesk.log."""
    global _id_counter
    level = (level or "INFO").upper()
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    entry: Dict[str, Any] = {
        "time": now_str,
        "level": level,
        "source": str(source or "SISTEMA")[:30],
        "message": str(message or "")[:500],
    }

    if details:
        clean_details = {}
        for k, v in details.items():
            if v is not None:
                clean_details[k] = str(v)[:300]
        if clean_details:
            entry["details"] = clean_details

    if exc:
        entry["error"] = str(exc)[:300]
        entry["stack"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-1000:]

    formatted_line = f"[{entry['time']}] [{entry['level']}] [{entry['source']}] {entry['message']}"
    if "details" in entry:
        try:
            formatted_line += f" | {json.dumps(entry['details'], ensure_ascii=False)}"
        except Exception:
            formatted_line += f" | {entry['details']}"
    if "error" in entry:
        formatted_line += f" | ERROR: {entry['error']}"
    if "stack" in entry:
        formatted_line += f"\n{entry['stack']}"

    with _lock:
        _id_counter += 1
        entry["id"] = _id_counter
        _recent_logs.appendleft(entry)

        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            _rotate_if_needed()
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(formatted_line.strip() + "\n")
        except OSError:
            pass

    return entry


def info(source: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return log("INFO", source, message, details)


def warning(source: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return log("WARNING", source, message, details)


def error(
    source: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    exc: Optional[BaseException] = None,
) -> Dict[str, Any]:
    return log("ERROR", source, message, details, exc=exc)


def debug(source: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return log("DEBUG", source, message, details)


def log_button_trigger(
    device: str,
    btn_id: str,
    label: str,
    action_type: str,
    page_name: str = "",
    gesture: str = "tap",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    details = {
        "device": device or "Móvil/Web",
        "btn_id": btn_id,
        "label": label or btn_id,
        "action": action_type or "none",
        "page": page_name or "Desconocida",
        "gesture": gesture,
    }
    if extra:
        for k in ("target", "target_app", "process", "hotkey"):
            if k in extra:
                details[k] = extra[k]
    msg = f"Botón pulsado: «{label or btn_id}» ({action_type}) desde {device or 'móvil'}"
    if page_name:
        msg += f" en pág «{page_name}»"
    if gesture != "tap":
        msg += f" [{gesture}]"
    return info("BOTON", msg, details)


def log_button_success(
    device: str,
    btn_id: str,
    label: str,
    action_type: str,
    page_name: str = "",
    duration_ms: Optional[float] = None,
) -> Dict[str, Any]:
    details = {
        "device": device or "Móvil/Web",
        "btn_id": btn_id,
        "label": label or btn_id,
        "action": action_type or "none",
        "page": page_name or "",
    }
    if duration_ms is not None:
        details["duration_ms"] = round(duration_ms, 1)
    return info("ACCION", f"Acción completada con éxito: «{label or btn_id}» ({action_type})", details)


def log_button_error(
    device: str,
    btn_id: str,
    label: str,
    action_type: str,
    page_name: str = "",
    error_msg: str = "",
    gesture: str = "tap",
    exc: Optional[BaseException] = None,
) -> Dict[str, Any]:
    details = {
        "device": device or "Móvil/Web",
        "btn_id": btn_id,
        "label": label or btn_id,
        "action": action_type or "none",
        "page": page_name or "",
        "gesture": gesture,
        "error": error_msg or "Error desconocido",
    }
    return error(
        "BOTON",
        f"Fallo en botón «{label or btn_id}» ({action_type}): {error_msg}",
        details,
        exc=exc,
    )


def recent_logs(
    level: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return the newest log entries first, optionally filtered by level and source."""
    with _lock:
        entries = list(_recent_logs)

    if level:
        lvl = level.upper()
        if lvl == "ERROR":
            entries = [e for e in entries if e["level"] == "ERROR"]
        elif lvl in ("WARN", "WARNING"):
            entries = [e for e in entries if e["level"] in ("WARNING", "ERROR")]
        elif lvl == "INFO":
            entries = [e for e in entries if e["level"] in ("INFO", "WARNING", "ERROR")]

    if source:
        src = source.upper()
        entries = [e for e in entries if src in e.get("source", "").upper()]

    return entries[:limit]


def get_log_text(lines: int = 300) -> str:
    """Return the last lines of streamdesk.log as a string."""
    with _lock:
        if not os.path.exists(LOG_FILE):
            return ""
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except OSError:
            return ""


def clear() -> None:
    """Clear in-memory logs and reset streamdesk.log."""
    with _lock:
        _recent_logs.clear()
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [INFO] [SISTEMA] Registro reiniciado.\n")
        except OSError:
            pass
