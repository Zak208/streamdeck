"""Ready-made pages a user can add in one click.

Templates are built from the connector button templates, so they use the user's
saved Discord shortcuts, and every page is checked by the same validator as a
hand-made profile before it is saved.
"""

import uuid
from typing import Any, Dict, List, Optional

from server import page_library
from server.connectors import discord, obs, windows
from server.layouts import LAYOUTS, convert_slots

BASE = LAYOUTS["6x2"]  # the pages below are drawn on the original grid and converted to the profile's one


def _fit(slots: List[Dict[str, Any]], layout: Optional[tuple]) -> tuple:
    """The 6x2 page in the profile's grid, and how many items did not fit."""
    if not layout or tuple(layout) == BASE:
        return slots, 0
    return convert_slots(slots, BASE, tuple(layout))

ACCENT = "#f8c700"

# Cells of the original 6x2 deck for the keys and the faders of a library page.
BUTTON_CELLS = [0, 1, 2, 3, 6, 7, 8, 9]
FADER_COLUMNS = [4, 5]

TEMPLATES: List[Dict[str, Any]] = [
    {"id": entry["id"], "name": entry["name"], "icon": entry["icon"], "description": entry["description"],
     "category": entry["category"], "app": entry["app"],
     # the size the page is drawn at (the original deck is 2 rows x 6 columns)
     "layout": {"rows": (entry["grid"] or (2, 6))[0], "columns": (entry["grid"] or (2, 6))[1]}}
    for entry in page_library.LIBRARY
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
    page = {"id": f"page_{uuid.uuid4().hex[:6]}", "name": server[:40], "auto_discord": server, "slots": _page(slots, [], capacity)}
    if layout:
        page["layout"] = {"rows": layout[0], "columns": layout[1]}
    return page


def _by_id(templates: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {t["id"]: t for t in templates}


def _connector_buttons() -> Dict[str, Dict[str, Any]]:
    """Buttons of the connectors by "connector:id", read now so they carry the user's saved Discord shortcuts."""
    found: Dict[str, Dict[str, Any]] = {}
    for name, module in (("obs", obs), ("discord", discord), ("windows", windows)):
        for action in module.actions():
            found[f"{name}:{action['id']}"] = action
    return found


def _tall_fader(column: int, columns: int, span: int, prefix: str, f: Dict[str, Any]) -> List[Dict[str, Any]]:
    """A fader on the first row of `column`, `span` rows tall: the cells under it are marked as taken."""
    top = {"index": column, "type": "slider", "id": f"{prefix}_{column}", "label": f["label"], "sublabel": f["sublabel"],
           "slider_type": f["slider_type"], "target_app": f["target_app"], "color": f["color"], "row_span": span,
           "icon": f["icon"], "image": f["icon"]}
    below = [{"index": column + row * columns, "type": "occupied_by_slider", "id": f"{prefix}_{column + row * columns}", "parent_slot": column}
             for row in range(1, span)]
    return [top] + below


def _native_slots(entry: Dict[str, Any], prefix: str) -> List[Dict[str, Any]]:
    """A page drawn at its own size: faders in the last columns, the keys filling the other cells row by row."""
    rows, columns = entry["grid"]
    connector = _connector_buttons()
    slots = [_empty(i) for i in range(rows * columns)]
    taken = set()
    span = max(1, min(entry.get("fader_span") or rows, rows))
    first = columns - len(entry["faders"])
    for offset, f in enumerate(entry["faders"]):
        for slot in _tall_fader(first + offset, columns, span, prefix, f):
            slots[slot["index"]] = slot
            taken.add(slot["index"])
    specs = iter(entry["buttons"])
    for index in range(rows * columns):
        if index in taken:
            continue
        spec = next(specs, None)
        if spec is None:
            break
        slots[index] = _from_connector(index, prefix, connector[spec] if isinstance(spec, str) else spec)
    return slots


def _slots(template_id: str, prefix: str) -> List[Dict[str, Any]]:
    entry = page_library.by_id().get(template_id)
    if entry is None:
        raise ValueError("Plantilla desconocida")
    if entry.get("grid"):
        return _native_slots(entry, prefix)
    connector = _connector_buttons()
    buttons: Dict[int, Dict[str, Any]] = {}
    for cell, spec in zip(BUTTON_CELLS, entry["buttons"]):
        spec = connector[spec] if isinstance(spec, str) else spec
        buttons[cell] = _from_connector(cell, prefix, spec)
    faders = [
        _fader(column, prefix, f["label"], f["sublabel"], f["icon"], f["color"], f["slider_type"], f["target_app"])
        for column, f in zip(FADER_COLUMNS if len(entry["faders"]) > 1 else [5], entry["faders"])
    ]
    return _page(buttons, faders)


def preview(template_id: str) -> List[Dict[str, str]]:
    """The icons and colours of a page's keys and faders, so Studio can draw a thumbnail of it."""
    slots = _slots(template_id, "preview")
    return [{"index": slot["index"], "image": slot.get("image") or slot.get("icon") or "", "color": slot.get("color", ""),
             "kind": slot["type"], "label": slot.get("label", ""), "span": slot.get("row_span", 1)}
            for slot in slots if slot["type"] in ("button", "slider")]


def build_page(template_id: str, name: Optional[str] = None, layout: Optional[tuple] = None, auto_app: bool = True) -> Dict[str, Any]:
    """A new page ready to append to a profile. Ids are fresh so pages never clash.

    A page of a program opens by itself when that program is in front (`auto_app`), unless the caller says no."""
    meta = next((t for t in TEMPLATES if t["id"] == template_id), None)
    if meta is None:
        raise ValueError("Plantilla desconocida")
    suffix = uuid.uuid4().hex[:6]
    own = page_library.by_id()[template_id].get("grid")
    if own:
        # A page with a size of its own keeps it, whatever size new pages start with.
        layout = tuple(own)
        slots, dropped = _slots(template_id, f"t{suffix}"), 0
    else:
        slots, dropped = _fit(_slots(template_id, f"t{suffix}"), layout)
    # "_dropped" tells the caller how many template buttons had no room; the caller removes it before saving.
    page: Dict[str, Any] = {"id": f"page_{suffix}", "name": (name or "").strip() or meta["name"], "slots": slots, "_dropped": dropped}
    if layout:
        page["layout"] = {"rows": layout[0], "columns": layout[1]}
    if auto_app and meta["app"]:
        page["auto_app"] = meta["app"]
    return page
