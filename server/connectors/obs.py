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


def _action(action_id, label, sublabel, icon, color, target, fields=None):
    """One OBS button template. `fields` lists what the user must choose (a scene, a source...) and is
    kept in the button's `extra` under each field's name."""
    action = {"id": action_id, "label": label, "sublabel": sublabel, "icon": icon, "color": color,
              "action_type": "obs_action", "target": target, "extra": {}}
    if fields:
        action["fields"] = fields
        action["configure"] = True
        # Valid until the user chooses: OBS answers "not found" if the button is pressed before that.
        action["extra"] = {field["name"]: PLACEHOLDER for field in fields}
    return action


PLACEHOLDER = "Elige"
SCENE = {"name": "scene_name", "label": "Escena", "options": "scenes", "filter_by": None, "required": True}


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
        _action("record_start", "Iniciar grabación", "OBS", "/static/icons/video.svg", "#ef4444", "record_start"),
        _action("record_stop", "Parar grabación", "OBS", "/static/icons/video.svg", "#ef4444", "record_stop"),
        _action("record_chapter", "Marcar capítulo", "OBS 30.2 o más", "/static/icons/notes.svg", "#f59e0b", "record_chapter"),
        _action("record_split", "Partir grabación", "OBS 30.2 o más", "/static/icons/macro.svg", "#f59e0b", "record_split"),
        _action("stream_start", "Iniciar directo", "OBS", "/static/icons/broadcast.svg", "#8b5cf6", "stream_start"),
        _action("stream_stop", "Terminar directo", "OBS", "/static/icons/broadcast.svg", "#8b5cf6", "stream_stop"),
        _action("studio_mode", "Modo estudio", "OBS", "/static/icons/sliders.svg", "#38bdf8", "studio_mode_toggle"),
        _action("studio_transition", "Hacer la transición", "OBS (modo estudio)", "/static/icons/play.svg", "#38bdf8", "studio_transition"),
        _action("preview_scene", "Escena en previsualización", "OBS (modo estudio)", "/static/icons/gamepad.svg", "#38bdf8", "preview_scene", [SCENE]),
        _action("set_transition", "Elegir transición", "OBS", "/static/icons/next.svg", "#38bdf8", "set_transition",
                [{"name": "transition_name", "label": "Transición", "options": "transitions", "filter_by": None, "required": True}]),
        _action("source_toggle", "Mostrar u ocultar fuente", "OBS", "/static/icons/video.svg", "#10b981", "source_toggle",
                [SCENE, {"name": "source_name", "label": "Fuente", "options": "scene_items", "filter_by": "scene_name", "required": True}]),
        _action("input_mute", "Silenciar una fuente de audio", "OBS", "/static/icons/mute.svg", "#ef4444", "input_mute",
                [{"name": "source_name", "label": "Fuente de audio", "options": "inputs", "filter_by": None, "required": True}]),
        _action("replay_toggle", "Búfer de repetición", "OBS", "/static/icons/pause.svg", "#f59e0b", "replay_toggle"),
        _action("replay_save", "Guardar repetición", "OBS", "/static/icons/play.svg", "#f59e0b", "replay_save"),
        _action("virtualcam", "Cámara virtual", "OBS", "/static/icons/video.svg", "#10b981", "virtualcam_toggle"),
        _action("hotkey", "Atajo de OBS por nombre", "OBS", "/static/icons/keyboard.svg", "#a855f7", "hotkey",
                [{"name": "hotkey_name", "label": "Nombre del atajo (por ejemplo OBSBasic.StartRecording)", "options": None, "filter_by": None, "required": True}]),
    ]


def options(name: str) -> List[Dict[str, Any]]:
    """Live lists from the running OBS. Raises RuntimeError with a readable reason."""
    if name == "scenes":
        return [{"name": scene} for scene in obs_client.list_scenes()]
    if name == "inputs":
        return obs_client.list_inputs()
    if name == "transitions":
        return obs_client.list_transitions()
    if name == "scene_items":
        return obs_client.list_scene_items()
    return []
