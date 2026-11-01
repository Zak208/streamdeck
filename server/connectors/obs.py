"""OBS Studio through its built-in WebSocket server (OBS 28 or newer)."""

from typing import Any, Dict, List

from server.obs_client import obs_client
from server.settings_store import settings

INFO = {
    "id": "obs",
    "name": "OBS Studio",
    "icon": "/static/icons/obs.svg",
    "color": "#302e31",
    "description": "Grabar, transmitir y cambiar de escena. Usa el servidor WebSocket que ya trae OBS.",
}


def configure(values: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    if "password" in values:
        password = values["password"]
        if not isinstance(password, str) or len(password) > 128:
            raise ValueError("La contraseña de OBS no es válida")
        clean["password"] = password
    if "port" in values:
        port = values["port"]
        if not isinstance(port, int) or isinstance(port, bool) or not 1024 <= port <= 65535:
            raise ValueError("El puerto de OBS debe estar entre 1024 y 65535")
        clean["port"] = port
    settings.update("obs", clean)
    return public_settings()


def public_settings() -> Dict[str, Any]:
    visible = settings.public("obs")
    visible.setdefault("port", 4455)
    return visible


def status() -> Dict[str, Any]:
    return obs_client.status()


def actions() -> List[Dict[str, Any]]:
    return [
        {"id": "record", "label": "Grabar", "sublabel": "OBS", "icon": "/static/icons/video.svg", "color": "#ef4444",
         "action_type": "obs_action", "target": "record_toggle", "extra": {}},
        {"id": "stream", "label": "Transmitir", "sublabel": "OBS", "icon": "/static/icons/broadcast.svg", "color": "#8b5cf6",
         "action_type": "obs_action", "target": "stream_toggle", "extra": {}},
        {"id": "pause", "label": "Pausar grabación", "sublabel": "OBS", "icon": "/static/icons/pause.svg", "color": "#f59e0b",
         "action_type": "obs_action", "target": "record_pause", "extra": {}},
        {"id": "next_scene", "label": "Escena siguiente", "sublabel": "OBS", "icon": "/static/icons/next.svg", "color": "#38bdf8",
         "action_type": "obs_action", "target": "next_scene", "extra": {}},
        {"id": "prev_scene", "label": "Escena anterior", "sublabel": "OBS", "icon": "/static/icons/prev.svg", "color": "#38bdf8",
         "action_type": "obs_action", "target": "prev_scene", "extra": {}},
    ]


def options(name: str) -> List[Dict[str, Any]]:
    """Live lists from the running OBS. Raises RuntimeError with a readable reason."""
    if name == "scenes":
        return [{"name": scene} for scene in obs_client.list_scenes()]
    if name == "inputs":
        return obs_client.list_inputs()
    return []
