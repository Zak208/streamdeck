"""Validation and normalisation for actions stored in a StreamDesk profile.

The mobile client can trigger these actions remotely, so a profile is treated as
untrusted input even when it was created by StreamDesk Studio.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List
from urllib.parse import urlparse

from server.shell_actions import SHELLS, validate_commands
from server.webhooks import validate_extra as validate_webhook_extra, validate_target
from server.layouts import LAYOUTS, layout_dict, layout_name, size_of


ACTION_TYPES = frozenset({
    "preset_app", "launch", "media", "url", "obs_action", "hardware_monitor",
    "sound", "multi", "spotify_uri", "discord_hotkey", "discord_sound", "windows", "hotkey", "text", "page", "folder", "command", "counter", "timer", "webhook",
    "none", "steam",
})
# These need the button they belong to (its own value or timer), so a macro step cannot be one.
SLOT_ONLY_TYPES = frozenset({"counter", "timer", "none"})
COUNTER_TARGETS = frozenset({"inc", "dec", "reset"})
GESTURES = ("long_press", "double_tap")  # extra actions a button can run on a long press or a double tap
WINDOWS_TARGETS = frozenset({"mic_mute", "app_mute", "output_device", "lock_pc", "power", "power_plan", "display_mode", "screenshot", "master_volume"})
POWER_MODES = frozenset({"sleep", "hibernate", "restart", "shutdown", "logoff", "cancel"})
DISPLAY_MODES = frozenset({"internal", "clone", "extend", "external"})
STEAM_APP_ID = re.compile(r"^[0-9]{1,10}$")
PAGE_KEYWORDS = frozenset({"next", "prev", "first", "back"})
MAX_TEXT_LENGTH = 300
HOTKEY_MODIFIERS = frozenset({"CTRL", "ALT", "SHIFT", "WIN"})
HOTKEY_KEYS = frozenset(
    {"SPACE", "TAB", "ENTER", "ESC", "BACKSPACE", "DELETE", "HOME", "END", "UP", "DOWN", "LEFT", "RIGHT",
     "INSERT", "PAGEUP", "PAGEDOWN", "PRINTSCREEN"}
    | {chr(code) for code in range(ord("A"), ord("Z") + 1)}
    | {str(number) for number in range(10)}
    | {f"F{number}" for number in range(1, 25)}
)
WINDOWS_DEVICE_ID = re.compile(r"^\{[0-9A-Fa-f.]{1,40}\}\.\{[0-9A-Fa-f-]{36}\}$")
MEDIA_TARGETS = frozenset({"play_pause", "play", "next", "next_track", "prev", "previous", "prev_track", "stop", "mute", "volume_up", "volume_down"})
OBS_TARGETS = frozenset({
    "record_toggle", "toggle_record", "record", "record_pause", "pause_record", "stream_toggle", "toggle_stream", "stream",
    "next_scene", "prev_scene", "mute_mic", "toggle_mute_mic",
    "record_start", "record_stop", "stream_start", "stream_stop", "studio_mode_toggle", "studio_transition",
    "replay_toggle", "replay_save", "virtualcam_toggle", "record_chapter", "record_split",
})
# OBS actions that need to be told which scene, source, transition or hotkey: target -> the names kept in `extra`.
OBS_TARGETS_WITH_FIELDS = {
    "preview_scene": ("scene_name",),
    "set_transition": ("transition_name",),
    "source_toggle": ("scene_name", "source_name"),
    "input_mute": ("source_name",),
    "hotkey": ("hotkey_name",),
    "filter_toggle": ("source_name", "filter_name"),
    "input_volume_up": ("source_name",),
    "input_volume_down": ("source_name",),
    "source_refresh": ("source_name",),
}
OBS_HOTKEY_NAME = re.compile(r"^[A-Za-z0-9_.:\- ]{1,100}$")
HARDWARE_TARGETS = frozenset({"cpu", "ram", "disk", "gpu", "vram", "net", "disk_speed"})
SOUND_TARGETS = frozenset({"beep", "asterisk", "exclamation"})
DISCORD_TARGETS = frozenset({"mute", "deafen", "sound"})
SLOT_TYPES = frozenset({"button", "slider", "empty", "occupied_by_slider"})
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SAFE_APP_TARGET = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
SAFE_PROCESS = re.compile(r"^[A-Za-z0-9_. -]{1,128}$")
FOLDER_PATH = re.compile(r'^[A-Za-z]:\\[^<>:"/|?*\x00-\x1f]*$')
SAFE_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
SPOTIFY_URI = re.compile(r"^spotify:(playlist|album|artist|track):([A-Za-z0-9]{10,64})$")


def _text(value: Any, field: str, maximum: int, *, allow_empty: bool = True) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{field} debe ser texto")
    value = value.strip()
    if (not allow_empty and not value) or len(value) > maximum:
        raise ValueError(f"{field} no tiene una longitud válida")
    if any(char in value for char in "<>"):
        raise ValueError(f"{field} contiene caracteres no permitidos")
    if any(ord(char) < 32 or 0x7F <= ord(char) <= 0x9F or char in "\u2028\u2029" for char in value):
        raise ValueError(f"{field} contiene caracteres de control no permitidos")
    return value


def normalize_spotify_uri(value: Any) -> str:
    """Accept a Spotify URI or share URL and return a canonical URI."""
    target = _text(value, "enlace de Spotify", 300, allow_empty=False)
    match = SPOTIFY_URI.fullmatch(target)
    if match:
        return target

    parsed = urlparse(target)
    if parsed.scheme != "https" or parsed.netloc not in {"open.spotify.com", "www.open.spotify.com"}:
        raise ValueError("Usa un enlace de Spotify o una URI spotify:playlist")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] not in {"playlist", "album", "artist", "track"}:
        raise ValueError("El enlace de Spotify no apunta a una playlist, álbum, artista o pista")
    if not re.fullmatch(r"[A-Za-z0-9]{10,64}", parts[1]):
        raise ValueError("El identificador de Spotify no es válido")
    return f"spotify:{parts[0]}:{parts[1]}"


def validate_hotkey(value: Any, *, require_modifier: bool = True) -> str:
    """Normalise a key combination such as "ctrl + shift + m" to "CTRL+SHIFT+M".

    Discord shortcuts must include a modifier (a bare letter would type into whatever has focus).
    General hotkey buttons may be a single key such as F5 or a media-style key.
    """
    hotkey = _text(value, "atajo", 80, allow_empty=False).upper().replace(" ", "")
    aliases = {"CONTROL": "CTRL", "OPTION": "ALT", "CMD": "WIN", "COMMAND": "WIN"}
    keys = [aliases.get(part, part) for part in hotkey.split("+") if part]

    if not 1 <= len(keys) <= 4 or len(set(keys)) != len(keys):
        raise ValueError("El atajo debe tener entre una y cuatro teclas distintas, por ejemplo CTRL+SHIFT+M")
    if any(key not in HOTKEY_MODIFIERS and key not in HOTKEY_KEYS for key in keys):
        raise ValueError("El atajo contiene una tecla no compatible")
    if not any(key in HOTKEY_KEYS for key in keys):
        raise ValueError("El atajo necesita una tecla además de los modificadores")
    if require_modifier and not any(key in HOTKEY_MODIFIERS for key in keys):
        raise ValueError("El atajo debe incluir un modificador y una tecla, por ejemplo CTRL+SHIFT+M")
    return "+".join(keys)


def _free_text(value: Any, field: str, maximum: int) -> str:
    """Text that will be typed as is. Unlike labels it may contain < and >, and it keeps its spaces."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} no puede estar vacío")
    if len(value) > maximum:
        raise ValueError(f"{field} no puede superar {maximum} caracteres")
    if any(ord(char) < 32 and char not in "\n\t" for char in value) or "\x7f" in value:
        raise ValueError(f"{field} contiene caracteres de control no permitidos")
    return value


def _image_path(value: Any) -> str:
    path = _text(value, "imagen", 180)
    if not path:
        return ""
    if not path.startswith(("/static/icons/", "/static/uploads/", "/uploads/")) or ".." in path             or not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
        raise ValueError("La imagen debe ser un icono local de StreamDesk")
    return path


def validate_action(action_type: Any, target: Any, extra: Any = None, *, allow_multi: bool = True) -> Dict[str, Any]:
    action_type = _text(action_type, "tipo de acción", 40, allow_empty=False).lower()
    # A macro step cannot be another macro or a page jump (that one needs the live phone connection).
    if action_type not in ACTION_TYPES or (action_type in ({"multi", "page"} | SLOT_ONLY_TYPES) and not allow_multi):
        raise ValueError("Tipo de acción no permitido")

    action_extra = extra if isinstance(extra, dict) else {}
    if action_type == "none":
        # A key that does nothing yet: it can be saved and placed, and tapping it is ignored.
        return {"action_type": "none", "target": "", "extra": {}}
    if action_type == "text":
        return {
            "action_type": "text",
            "target": _free_text(target, "texto", MAX_TEXT_LENGTH),
            "extra": {"press_enter": bool(action_extra.get("press_enter", False))},
        }
    target_text = _text(target, "destino", 300)

    if action_type in {"preset_app", "launch"}:
        if not SAFE_APP_TARGET.fullmatch(target_text):
            raise ValueError("La aplicación debe seleccionarse desde StreamDesk")
        clean_extra: Dict[str, Any] = {}
    elif action_type == "media":
        if target_text.lower() not in MEDIA_TARGETS:
            raise ValueError("Acción multimedia no válida")
        target_text = target_text.lower()
        clean_extra = {}
    elif action_type == "url":
        parsed = urlparse(target_text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(not char.isprintable() or char.isspace() for char in target_text):
            raise ValueError("Solo se permiten enlaces http o https, sin espacios ni saltos de línea")
        clean_extra = {}
    elif action_type == "folder":
        # A local drive path only: a network (UNC) path would make Windows send credentials to another computer.
        folder = target_text.replace("/", "\\").rstrip()
        if not FOLDER_PATH.fullmatch(folder) or ".." in folder.split("\\") or len(folder) > 240:
            raise ValueError("La carpeta debe ser una ruta local de un disco, por ejemplo D:\\Proyectos")
        target_text = folder
        clean_extra = {}
    elif action_type == "counter":
        target_text = target_text.lower()
        if target_text not in COUNTER_TARGETS:
            raise ValueError("El contador solo admite sumar, restar o poner a cero")
        step = action_extra.get("step", 1)
        if not isinstance(step, int) or isinstance(step, bool) or not 1 <= step <= 1000:
            raise ValueError("El paso del contador debe estar entre 1 y 1000")
        clean_extra = {"step": step}
    elif action_type == "timer":
        target_text = "toggle"
        seconds = action_extra.get("seconds", 60)
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 1 <= seconds <= 86400:
            raise ValueError("El temporizador debe durar entre 1 segundo y 24 horas")
        clean_extra = {"seconds": seconds}
    elif action_type == "webhook":
        target_text = validate_target(target_text)
        clean_extra = validate_webhook_extra(action_extra)
    elif action_type == "command":
        # Runs only when the user has switched console commands on (see shell_actions); the lines are validated here.
        if target_text.lower() not in SHELLS:
            raise ValueError("Elige PowerShell o cmd")
        target_text = target_text.lower()
        clean_extra = {"commands": validate_commands(action_extra.get("commands"))}
    elif action_type == "spotify_uri":
        target_text = normalize_spotify_uri(target_text)
        clean_extra = {}
    elif action_type == "discord_hotkey":
        if target_text.lower() not in DISCORD_TARGETS:
            raise ValueError("Acción de Discord no válida")
        target_text = target_text.lower()
        clean_extra = {"hotkey": validate_hotkey(action_extra.get("hotkey", ""))}
        if target_text == "sound" and action_extra.get("sound_name"):
            # Only a label: StreamDesk cannot read Discord's sounds, the shortcut is what plays one.
            clean_extra["sound_name"] = _text(action_extra["sound_name"], "nombre del sonido", 40, allow_empty=False)
    elif action_type == "discord_sound":
        # target is the sound as the soundboard panel names it (emoji included); section is the server's tab.
        target_text = _text(target_text, "sonido de Discord", 80, allow_empty=False)
        clean_extra = {"section": _text(action_extra.get("section"), "servidor de Discord", 80, allow_empty=False)}
        if action_extra.get("hotkey"):
            # A shortcut the user gave to this sound in Discord: pressing it plays the sound without opening the panel.
            clean_extra["hotkey"] = validate_hotkey(action_extra["hotkey"], require_modifier=False)
    elif action_type == "hotkey":
        target_text = validate_hotkey(target_text, require_modifier=False)
        clean_extra = {}
    elif action_type == "page":
        if target_text.lower() in PAGE_KEYWORDS:
            target_text = target_text.lower()
        elif not SAFE_ID.fullmatch(target_text):
            raise ValueError("La página de destino no es válida")
        clean_extra = {}
    elif action_type == "windows":
        target_text = target_text.lower()
        if target_text not in WINDOWS_TARGETS:
            raise ValueError("Acción de Windows no válida")
        clean_extra = {}
        if target_text == "app_mute":
            process = _text(action_extra.get("process"), "aplicación de audio", 128, allow_empty=False)
            if not SAFE_PROCESS.fullmatch(process):
                raise ValueError("Aplicación de audio no válida")
            clean_extra = {"process": process}
        elif target_text == "output_device":
            device_id = _text(action_extra.get("device_id"), "dispositivo de audio", 80, allow_empty=False)
            if not WINDOWS_DEVICE_ID.fullmatch(device_id):
                raise ValueError("Dispositivo de audio no válido")
            clean_extra = {"device_id": device_id}
        elif target_text == "power":
            mode = _text(action_extra.get("mode", "sleep"), "modo de energía", 20, allow_empty=False).lower()
            if mode not in POWER_MODES:
                raise ValueError("Elige suspender, hibernar, reiniciar, apagar, cerrar sesión o cancelar")
            delay = action_extra.get("delay", 15)
            if not isinstance(delay, int) or isinstance(delay, bool) or not 0 <= delay <= 600:
                raise ValueError("La espera debe estar entre 0 y 600 segundos")
            clean_extra = {"mode": mode, "delay": delay}
        elif target_text == "power_plan":
            plan = _text(action_extra.get("plan"), "plan de energía", 80, allow_empty=False)
            if any(not char.isprintable() for char in plan):
                raise ValueError("El nombre del plan de energía no es válido")
            clean_extra = {"plan": plan}
        elif target_text == "display_mode":
            mode = _text(action_extra.get("mode", "extend"), "modo de pantalla", 20, allow_empty=False).lower()
            if mode not in DISPLAY_MODES:
                raise ValueError("Modo de pantalla no válido")
            clean_extra = {"mode": mode}
        elif target_text == "master_volume":
            mode = _text(action_extra.get("mode", "step"), "modo de volumen", 10, allow_empty=False).lower()
            value = action_extra.get("value", 10)
            if mode not in {"set", "step"} or not isinstance(value, int) or isinstance(value, bool):
                raise ValueError("El volumen debe ser fijar o subir/bajar, con un número entero")
            if (mode == "set" and not 0 <= value <= 100) or (mode == "step" and (value == 0 or not -50 <= value <= 50)):
                raise ValueError("El volumen fijo va de 0 a 100 y el cambio, de -50 a 50")
            clean_extra = {"mode": mode, "value": value}
    elif action_type == "obs_action":
        if target_text.lower().startswith("scene_"):
            scene_name = _text(action_extra.get("scene_name", target_text[6:]), "escena de OBS", 80, allow_empty=False)
            clean_extra = {"scene_name": scene_name}
        elif target_text.lower() in OBS_TARGETS_WITH_FIELDS:
            clean_extra = {}
            for field in OBS_TARGETS_WITH_FIELDS[target_text.lower()]:
                clean_extra[field] = _text(action_extra.get(field), field.replace("_", " "), 100, allow_empty=False)
            if "hotkey_name" in clean_extra and not OBS_HOTKEY_NAME.fullmatch(clean_extra["hotkey_name"]):
                raise ValueError("El nombre del atajo de OBS no es válido")
        elif target_text.lower() in OBS_TARGETS:
            clean_extra = {}
            if target_text.lower() in {"mute_mic", "toggle_mute_mic"} and action_extra.get("source_name"):
                clean_extra = {"source_name": _text(action_extra["source_name"], "fuente de OBS", 80, allow_empty=False)}
        else:
            raise ValueError("Acción de OBS no válida")
        target_text = target_text.lower()
    elif action_type == "steam":
        if not STEAM_APP_ID.fullmatch(target_text):
            raise ValueError("El juego de Steam se elige de tu biblioteca (un número de aplicación)")
        clean_extra = {}
    elif action_type == "hardware_monitor":
        if target_text.lower() not in HARDWARE_TARGETS:
            raise ValueError("Monitor no válido")
        target_text = target_text.lower()
        clean_extra = {}
    elif action_type == "sound":
        if target_text.lower() not in SOUND_TARGETS:
            raise ValueError("Sonido no válido")
        target_text = target_text.lower()
        clean_extra = {}
    else:  # multi
        actions = action_extra.get("actions")
        if not isinstance(actions, list) or not 1 <= len(actions) <= 8:
            raise ValueError("Una macro necesita entre una y ocho acciones")
        clean_actions: List[Dict[str, Any]] = []
        for child in actions:
            if not isinstance(child, dict):
                raise ValueError("La macro contiene una acción no válida")
            clean_child = validate_action(child.get("action_type"), child.get("target"), child.get("extra"), allow_multi=False)
            delay = child.get("delay_ms", 150)
            if not isinstance(delay, (int, float)) or not 0 <= delay <= 5000:
                raise ValueError("El retardo de macro no es válido")
            clean_child["delay_ms"] = int(delay)
            clean_actions.append(clean_child)
        target_text = _text(target_text or "macro", "destino", 80) or "macro"
        clean_extra = {"actions": clean_actions}

    return {"action_type": action_type, "target": target_text, "extra": clean_extra}


def validate_deck_config(raw_config: Any) -> Dict[str, Any]:
    if not isinstance(raw_config, dict):
        raise ValueError("La configuración debe ser un objeto")

    # The size a page has when it does not say: the profile's default ("default_layout"; older profiles only have
    # "layout", which then is the size of every page). A page can have its own size ("layout").
    default_rows, default_columns = size_of(raw_config.get("default_layout") or raw_config.get("layout"))

    pages = raw_config.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 20:
        raise ValueError("El perfil necesita entre una y veinte páginas")

    clean_pages: List[Dict[str, Any]] = []
    for page_index, page in enumerate(pages):
        if not isinstance(page, dict):
            raise ValueError("Página no válida")
        page_id = _text(page.get("id", f"page_{page_index}"), "id de página", 64, allow_empty=False)
        if not SAFE_ID.fullmatch(page_id):
            raise ValueError("El id de página no es válido")
        page_name = _text(page.get("name", f"Página {page_index + 1}"), "nombre de página", 40, allow_empty=False)
        auto_app = ""
        if page.get("auto_app"):
            auto_app = _text(page["auto_app"], "aplicación de la página", 128, allow_empty=False)
            if not SAFE_PROCESS.fullmatch(auto_app):
                raise ValueError("La aplicación de la página no es válida")
        auto_discord = ""
        if page.get("auto_discord"):
            auto_discord = _text(page["auto_discord"], "servidor de Discord de la página", 80, allow_empty=False)
        rows, columns = size_of(page["layout"]) if page.get("layout") else (default_rows, default_columns)
        total_slots = rows * columns
        slots = page.get("slots")
        if not isinstance(slots, list) or len(slots) != total_slots:
            raise ValueError(f"Cada página debe tener exactamente {total_slots} casillas")

        clean_slots: List[Dict[str, Any]] = []
        slot_ids = set()
        for slot_index, slot in enumerate(slots):
            if not isinstance(slot, dict):
                raise ValueError("Casilla no válida")
            slot_type = slot.get("type", "empty")
            if slot_type not in SLOT_TYPES:
                raise ValueError("Tipo de casilla no permitido")
            if slot.get("index", slot_index) != slot_index:
                raise ValueError("El índice de una casilla no coincide con su posición")
            clean_slot: Dict[str, Any] = {"index": slot_index, "type": slot_type}

            if slot_type == "empty":
                clean_slots.append(clean_slot)
                continue

            slot_id = _text(slot.get("id", f"slot_{slot_index}"), "id de casilla", 64, allow_empty=False)
            if not SAFE_ID.fullmatch(slot_id) or slot_id in slot_ids:
                raise ValueError("El id de casilla no es válido o está repetido")
            slot_ids.add(slot_id)
            clean_slot["id"] = slot_id

            if slot_type == "slider" and slot_index >= columns:
                raise ValueError("Un fader solo puede ir en la primera fila")
            if slot_type == "occupied_by_slider":
                parent_slot = slot.get("parent_slot")
                if not isinstance(parent_slot, int) or not 0 <= parent_slot < columns:
                    raise ValueError("La casilla ocupada no referencia un fader válido")
                clean_slot["parent_slot"] = parent_slot
                clean_slots.append(clean_slot)
                continue

            clean_slot.update({
                "label": _text(slot.get("label"), "título", 32, allow_empty=False),
                "sublabel": _text(slot.get("sublabel"), "subtítulo", 36),
                "icon": _image_path(slot.get("icon", "")),
                "image": _image_path(slot.get("image", "")),
                "color": _text(slot.get("color", "#0ea5e9"), "color", 7, allow_empty=False),
            })
            if not SAFE_COLOR.fullmatch(clean_slot["color"]):
                raise ValueError("El color debe tener formato #RRGGBB")

            if slot_type == "button":
                clean_slot.update(validate_action(slot.get("action_type"), slot.get("target"), slot.get("extra")))
                for gesture in GESTURES:
                    raw_gesture = slot.get(gesture)
                    if not raw_gesture:
                        continue
                    if not isinstance(raw_gesture, dict):
                        raise ValueError("La acción de toque largo o doble toque no es válida")
                    gesture_action = validate_action(
                        raw_gesture.get("action_type"), raw_gesture.get("target"), raw_gesture.get("extra"))
                    if gesture_action["action_type"] != "none":
                        clean_slot[gesture] = gesture_action
                alt = slot.get("alt")
                if alt:
                    # The look the key takes while it is "on" (a toggle): same limits as the key itself.
                    if not isinstance(alt, dict):
                        raise ValueError("La apariencia alternativa no es válida")
                    alt_color = _text(alt.get("color", clean_slot["color"]), "color alternativo", 7, allow_empty=False)
                    if not SAFE_COLOR.fullmatch(alt_color):
                        raise ValueError("El color alternativo debe tener formato #RRGGBB")
                    clean_slot["alt"] = {
                        "label": _text(alt.get("label", clean_slot["label"]), "título alternativo", 32, allow_empty=False),
                        "sublabel": _text(alt.get("sublabel", ""), "subtítulo alternativo", 36),
                        "image": _image_path(alt.get("image", clean_slot["image"])),
                        "color": alt_color,
                    }
                    alt_action = alt.get("action")
                    if alt_action:
                        # What a tap does while the key is "on". Without it, both states run the key's own action.
                        if not isinstance(alt_action, dict):
                            raise ValueError("La acción del segundo estado no es válida")
                        second = validate_action(alt_action.get("action_type"), alt_action.get("target"), alt_action.get("extra"))
                        if second["action_type"] != "none":
                            clean_slot["alt"]["action"] = second
                for flag in ("confirm", "disabled", "toggle"):
                    value = slot.get(flag)
                    if value not in (None, True, False, 0, 1) or isinstance(value, str):
                        raise ValueError("«confirmar» y «desactivado» deben ser verdadero o falso")
                    if value:
                        clean_slot[flag] = True  # confirm: the phone asks first; disabled: kept, but does nothing
            else:
                slider_type = _text(slot.get("slider_type", "master"), "tipo de fader", 30, allow_empty=False)
                if slider_type not in {"master", "app_dynamic"}:
                    raise ValueError("Tipo de fader no válido")
                target_app = slot.get("target_app")
                if slider_type == "app_dynamic":
                    target_app = _text(target_app, "aplicación de audio", 128, allow_empty=False)
                    if not SAFE_PROCESS.fullmatch(target_app):
                        raise ValueError("Aplicación de audio no válida")
                span = slot.get("row_span", 2)
                if not isinstance(span, int) or isinstance(span, bool) or not 1 <= span <= rows:
                    raise ValueError(f"El alto de un fader debe estar entre 1 y {rows} filas")
                clean_slot.update({"slider_type": slider_type, "target_app": target_app if slider_type == "app_dynamic" else None, "row_span": span})
            clean_slots.append(clean_slot)

        for index, slot in enumerate(clean_slots):
            # The cells a fader covers are the ones right under it, in its own column.
            if slot["type"] == "occupied_by_slider" and (index <= slot["parent_slot"] or (index - slot["parent_slot"]) % columns):
                raise ValueError("Una casilla ocupada tiene que estar justo debajo de su fader")
        for column in range(columns):
            top = clean_slots[column]
            span = top["row_span"] if top["type"] == "slider" else 1
            for row in range(1, rows):
                cell = clean_slots[column + row * columns]
                covered = row < span
                if covered and not (cell["type"] == "occupied_by_slider" and cell.get("parent_slot") == column):
                    raise ValueError("Cada fader debe ocupar todas las casillas de su alto")
                if not covered and cell["type"] == "occupied_by_slider":
                    raise ValueError("Una casilla ocupada necesita un fader encima")
        clean_page: Dict[str, Any] = {"id": page_id, "name": page_name, "layout": layout_dict(layout_name(rows, columns)), "slots": clean_slots}
        if auto_app:
            clean_page["auto_app"] = auto_app  # switch to this page when this program is in the foreground
        if auto_discord:
            clean_page["auto_discord"] = auto_discord  # ...or when the user joins a voice channel of this Discord server
        clean_pages.append(clean_page)

    current_page = raw_config.get("current_page", 0)
    if not isinstance(current_page, int) or isinstance(current_page, bool) or not 0 <= current_page < len(clean_pages):
        raise ValueError("La página activa no es válida")

    return {
        "schema_version": 2,
        "deck_name": _text(raw_config.get("deck_name", "StreamDesk"), "nombre del deck", 48, allow_empty=False),
        # "layout" is the size of the page being shown: what the phone reads. Each page keeps its own.
        "layout": copy.deepcopy(clean_pages[current_page]["layout"]),
        "default_layout": layout_dict(layout_name(default_rows, default_columns)),
        "current_page": current_page,
        "pages": clean_pages,
        "slots": copy.deepcopy(clean_pages[current_page]["slots"]),
    }
