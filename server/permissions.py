"""Which button actions a limited phone is not allowed to run.

A phone marked as limited in Studio (a borrowed phone, a child's tablet) can still use every other button, but
never the ones that shut the PC down or run console commands. The check is on the PC, not in the phone's page,
because a phone is the part that cannot be trusted.
"""

from typing import Any, Dict, Optional

LIMITED_MESSAGE = "Este móvil está limitado: no puede apagar el PC ni lanzar comandos de consola. Cámbialo en Ajustes de Studio."


def is_dangerous(action_type: Any, target: Any = "", extra: Optional[Dict[str, Any]] = None) -> bool:
    """True for console commands and for shutting down, restarting, sleeping or logging off (not for cancelling)."""
    kind = str(action_type or "").lower().strip()
    extra = extra if isinstance(extra, dict) else {}
    if kind == "command":
        return True
    if kind == "windows" and str(target or "").lower().strip() == "power":
        return extra.get("mode") != "cancel"
    if kind == "multi":
        children = extra.get("actions")
        return isinstance(children, list) and any(
            isinstance(child, dict) and is_dangerous(child.get("action_type"), child.get("target"), child.get("extra"))
            for child in children)
    return False
