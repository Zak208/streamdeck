"""Connectors: one module per service StreamDesk can control.

Each module provides:
  INFO              id, name, icon, color, description
  status()          {"state": ready | needs_setup | limited | offline, "detail": text}
  actions()         ready-made button templates (label, icon, action_type, target, extra)
  options(name)     live lists from the service (OBS scenes, Spotify playlists, ...)
  configure(values) optional: save settings, raises ValueError on bad input
"""

from concurrent.futures import ThreadPoolExecutor
from types import ModuleType
from typing import Any, Dict, List

from server.connectors import discord, obs, spotify, windows

REGISTRY: Dict[str, ModuleType] = {
    module.INFO["id"]: module for module in (windows, obs, spotify, discord)
}


def get(connector_id: str) -> ModuleType:
    try:
        return REGISTRY[connector_id]
    except KeyError:
        raise KeyError("Conector desconocido") from None


def describe(connector_id: str) -> Dict[str, Any]:
    """Card data for Studio. Runs status(), which may talk to the network: call from a thread."""
    module = get(connector_id)
    try:
        status = module.status()
    except Exception as exc:  # a broken connector must not break the whole gallery
        status = {"state": "offline", "detail": str(exc)}
    card = {**module.INFO, "status": status, "actions": module.actions()}
    if hasattr(module, "public_settings"):
        card["settings"] = module.public_settings()
    return card


def describe_all() -> List[Dict[str, Any]]:
    # Offline OBS or a slow Spotify call must not make the whole gallery wait for them one by one.
    with ThreadPoolExecutor(max_workers=len(REGISTRY)) as pool:
        return list(pool.map(describe, REGISTRY))
