"""Ready-made pages a user can add in one click.

Templates are built from the connector button templates, so they use the user's
saved Discord shortcuts, and every page is checked by the same validator as a
hand-made profile before it is saved.
"""

import uuid
from typing import Any, Dict, List, Optional

from server.connectors import discord, obs, windows
from server.layouts import LAYOUTS, convert_slots

BASE = LAYOUTS["6x2"]  # the pages below are drawn on the original grid and converted to the profile's one


def _fit(slots: List[Dict[str, Any]], layout: Optional[tuple]) -> tuple:
    """The 6x2 page in the profile's grid, and how many items did not fit."""
    if not layout or tuple(layout) == BASE:
        return slots, 0
    return convert_slots(slots, BASE, tuple(layout))

ACCENT = "#f8c700"

TEMPLATES: List[Dict[str, str]] = [
    {"id": "streamer", "name": "Streamer", "icon": "/static/icons/broadcast.svg",
     "description": "OBS (grabar, directo, escenas), micrófono, Discord y volumen."},
    {"id": "gamer", "name": "Gamer", "icon": "/static/icons/gamepad.svg",
     "description": "Discord, micrófono, música y Steam a mano mientras juegas."},
    {"id": "work", "name": "Trabajo", "icon": "/static/icons/sliders.svg",
     "description": "Navegador, notas, calculadora y el estado de tu PC en vivo."},
    {"id": "blank", "name": "En blanco", "icon": "/static/icons/plus.svg",
     "description": "Una página vacía para montarla a tu manera."},
]


def _empty(index: int) -> Dict[str, Any]:
    return {"index": index, "type": "empty"}


def _button(index: int, prefix: str, label: str, sublabel: str, icon: str, color: str,
            action_type: str, target: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    slot: Dict[str, Any] = {
        "index": index, "type": "button", "id": f"{prefix}_{index}", "label": label, "sublabel": sublabel,
        "icon": "", "image": icon, "color": color, "action_type": action_type, "target": target,
    }
    if extra:
        slot["extra"] = extra
    return slot


def _from_connector(index: int, prefix: str, template: Dict[str, Any]) -> Dict[str, Any]:
    return _button(index, prefix, template["label"], template["sublabel"], template["icon"], template["color"],
                   template["action_type"], template["target"], template.get("extra"))


def _fader(index: int, prefix: str, label: str, sublabel: str, icon: str, color: str,
           slider_type: str, target_app: Optional[str] = None) -> List[Dict[str, Any]]:
    """A fader takes its column on both rows: the top slot holds it, the bottom one is marked occupied."""
    return [{
        "index": index, "type": "slider", "id": f"{prefix}_{index}", "label": label, "sublabel": sublabel,
        "slider_type": slider_type, "target_app": target_app, "color": color, "row_span": 2,
        "icon": icon, "image": icon,
    }, {"index": index + 6, "type": "occupied_by_slider", "id": f"{prefix}_{index + 6}", "parent_slot": index}]


def _page(slots: Dict[int, Dict[str, Any]], faders: List[List[Dict[str, Any]]], total: int = 12) -> List[Dict[str, Any]]:
    layout = [_empty(i) for i in range(total)]
    for index, slot in slots.items():
        layout[index] = slot
    for fader in faders:
        layout[fader[0]["index"]] = fader[0]
        layout[fader[1]["index"]] = fader[1]
    return layout


def discord_server_page(server: str, labels: List[str], layout: Optional[tuple] = None) -> Dict[str, Any]:
    """A page of Discord sounds that opens by itself when the user is in a voice channel of `server`."""
    from server.discord_ui import split_label
    capacity = (layout[0] * layout[1]) if layout else 12
    if not 1 <= len(labels) <= capacity:
        raise ValueError(f"Elige entre 1 y {capacity} sonidos para la página")
    prefix = f"dc_{uuid.uuid4().hex[:6]}"
    slots = {}
    for index, label in enumerate(labels):
        emoji, name = split_label(label)
        slots[index] = _button(index, prefix, (name or label)[:32], server[:36], "/static/icons/soundboard.svg", "#5865f2",
                               "discord_sound", label, {"section": server})
    return {"id": f"page_{uuid.uuid4().hex[:6]}", "name": server[:40], "auto_discord": server, "slots": _page(slots, [], capacity)}


def _by_id(templates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in templates}


def _slots(template_id: str, prefix: str) -> List[Dict[str, Any]]:
    obs_actions, discord_actions, windows_actions = _by_id(obs.actions()), _by_id(discord.actions()), _by_id(windows.actions())
    mic = windows_actions["mic_mute"]

    if template_id == "streamer":
        return _page({
            0: _from_connector(0, prefix, obs_actions["record"]),
            1: _from_connector(1, prefix, obs_actions["stream"]),
            2: _from_connector(2, prefix, obs_actions["next_scene"]),
            3: _from_connector(3, prefix, mic),
            6: _from_connector(6, prefix, discord_actions["mute"]),
            7: _from_connector(7, prefix, discord_actions["deafen"]),
            8: _from_connector(8, prefix, obs_actions["prev_scene"]),
            9: _button(9, prefix, "Spotify", "Música", "/static/icons/spotify.svg", "#1db954", "preset_app", "spotify"),
        }, [
            _fader(4, prefix, "Master", "PC", "/static/icons/volume_up.svg", ACCENT, "master"),
            _fader(5, prefix, "Discord", "Voz", "/static/icons/discord.svg", "#5865f2", "app_dynamic", "Discord.exe"),
        ])

    if template_id == "gamer":
        return _page({
            0: _from_connector(0, prefix, discord_actions["mute"]),
            1: _from_connector(1, prefix, discord_actions["deafen"]),
            2: _from_connector(2, prefix, mic),
            3: _button(3, prefix, "Steam", "Juegos", "/static/icons/steam.svg", "#171a21", "preset_app", "steam"),
            6: _button(6, prefix, "Play/Pausa", "Multimedia", "/static/icons/play_pause.svg", ACCENT, "media", "play_pause"),
            7: _button(7, prefix, "Siguiente", "Multimedia", "/static/icons/next.svg", ACCENT, "media", "next"),
            8: _button(8, prefix, "Anterior", "Multimedia", "/static/icons/prev.svg", ACCENT, "media", "prev"),
            9: _button(9, prefix, "Discord", "Abrir", "/static/icons/discord.svg", "#5865f2", "preset_app", "discord"),
        }, [
            _fader(4, prefix, "Master", "PC", "/static/icons/volume_up.svg", ACCENT, "master"),
            _fader(5, prefix, "Spotify", "App", "/static/icons/spotify.svg", "#1db954", "app_dynamic", "Spotify.exe"),
        ])

    if template_id == "work":
        return _page({
            0: _button(0, prefix, "Edge", "Navegador", "/static/icons/chrome.svg", "#0078d7", "preset_app", "edge"),
            1: _button(1, prefix, "Notas", "Bloc de notas", "/static/icons/notes.svg", ACCENT, "preset_app", "notepad"),
            2: _button(2, prefix, "Calculadora", "Utilidad", "/static/icons/calc.svg", ACCENT, "preset_app", "calc"),
            3: _button(3, prefix, "Tareas", "Administrador", "/static/icons/sliders.svg", ACCENT, "preset_app", "taskmgr"),
            6: _button(6, prefix, "CPU", "En vivo", "/static/icons/cpu.svg", ACCENT, "hardware_monitor", "cpu"),
            7: _button(7, prefix, "RAM", "En vivo", "/static/icons/ram.svg", ACCENT, "hardware_monitor", "ram"),
            8: _button(8, prefix, "GPU", "En vivo", "/static/icons/gpu.svg", ACCENT, "hardware_monitor", "gpu"),
            9: _from_connector(9, prefix, mic),
        }, [
            _fader(4, prefix, "Master", "PC", "/static/icons/volume_up.svg", ACCENT, "master"),
            _fader(5, prefix, "Edge", "Web", "/static/icons/chrome.svg", "#0078d7", "app_dynamic", "msedge.exe"),
        ])

    if template_id == "blank":
        return _page({}, [])
    raise ValueError("Plantilla desconocida")


def build_page(template_id: str, name: Optional[str] = None, layout: Optional[tuple] = None) -> Dict[str, Any]:
    """A new page ready to append to a profile. Ids are fresh so pages never clash."""
    meta = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if meta is None:
        raise ValueError("Plantilla desconocida")
    suffix = uuid.uuid4().hex[:6]
    slots, dropped = _fit(_slots(template_id, f"t{suffix}"), layout)
    # "_dropped" tells the caller how many template buttons had no room; the caller removes it before saving.
    return {"id": f"page_{suffix}", "name": (name or "").strip() or meta["name"], "slots": slots, "_dropped": dropped}
