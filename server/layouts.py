"""Grid sizes of the deck and the conversion of a profile from one size to another.

Slots are stored row by row: the index of a slot is row * columns + column. A fader always takes the
first two rows of its column: the slider sits at index `column` and the cell under it
(`column + columns`) is marked `occupied_by_slider`. Rows below those two are plain buttons.
"""

from __future__ import annotations

import copy
import re
import uuid
from typing import Any, Dict, List, Tuple

# Quick picks, name -> (rows, columns). Names read "<columns>x<rows>". Any size inside LIMITS is also allowed.
LAYOUTS: Dict[str, Tuple[int, int]] = {
    "6x2": (2, 6),
    "5x3": (3, 5),
    "4x3": (3, 4),
    "3x3": (3, 3),
    "4x2": (2, 4),
}
DEFAULT_LAYOUT = "6x2"

# A fader needs two rows, so a grid has at least two. The phone is small: keep the total reasonable.
LIMITS = {"min_columns": 2, "max_columns": 10, "min_rows": 2, "max_rows": 8, "max_total": 64}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def valid_size(rows: Any, columns: Any) -> bool:
    return (_is_int(rows) and _is_int(columns)
            and LIMITS["min_rows"] <= rows <= LIMITS["max_rows"]
            and LIMITS["min_columns"] <= columns <= LIMITS["max_columns"]
            and rows * columns <= LIMITS["max_total"])


def parse_layout(spec: Any) -> Tuple[int, int]:
    """(rows, columns) from "<columns>x<rows>" (e.g. "4x8") or {"columns": 4, "rows": 8}. Raises ValueError."""
    rows = columns = None
    if isinstance(spec, str):
        match = re.fullmatch(r"\s*([0-9]{1,2})\s*[xX]\s*([0-9]{1,2})\s*", spec, re.ASCII)
        if match:
            columns, rows = int(match.group(1)), int(match.group(2))
    elif isinstance(spec, dict):
        rows, columns = spec.get("rows"), spec.get("columns")
    if not valid_size(rows, columns):
        raise ValueError(
            f"La cuadrícula debe tener entre {LIMITS['min_columns']} y {LIMITS['max_columns']} columnas, "
            f"entre {LIMITS['min_rows']} y {LIMITS['max_rows']} filas y como máximo {LIMITS['max_total']} casillas")
    return rows, columns


def layout_name(rows: int, columns: int) -> str:
    if not valid_size(rows, columns):
        raise ValueError("Esa cuadrícula no está disponible")
    return f"{columns}x{rows}"


def layout_dict(spec: Any) -> Dict[str, int]:
    rows, columns = LAYOUTS[spec] if isinstance(spec, str) and spec in LAYOUTS else parse_layout(spec)
    return {"rows": rows, "columns": columns, "total_slots": rows * columns}


def size_of(raw: Any) -> Tuple[int, int]:
    """(rows, columns) of a stored `layout`, defaulting to the original 6x2. Raises for unknown sizes."""
    if not raw:
        return LAYOUTS[DEFAULT_LAYOUT]
    if not isinstance(raw, dict):
        raise ValueError("La cuadrícula no es válida")
    return parse_layout(raw)


def _occupied(column: int, columns: int) -> Dict[str, Any]:
    return {"index": column + columns, "type": "occupied_by_slider",
            "id": f"occ_{column}_{uuid.uuid4().hex[:6]}", "parent_slot": column}


def _holds_fader(cell: Any) -> bool:
    return cell is not None and cell.get("type") in ("slider", "occupied_by_slider")


def convert_slots(slots: List[Dict[str, Any]], old: Tuple[int, int], new: Tuple[int, int]) -> Tuple[List[Dict[str, Any]], int]:
    """Re-seat the slots of one page in a grid of another size.

    Every item keeps its row and column when that cell exists in the new grid. A fader whose column is gone
    takes the rightmost column that has no fader, and the buttons that were there move to free cells. Returns
    the new slots and how many items had no room (and so were left out).
    """
    old_rows, old_columns = old
    new_rows, new_columns = new
    total = new_rows * new_columns
    placed: List[Any] = [None] * total
    sliders: List[Tuple[int, Dict[str, Any]]] = []
    buttons: List[Tuple[int, int, Dict[str, Any]]] = []
    for index, slot in enumerate(slots):
        kind = slot.get("type")
        row, column = divmod(index, old_columns)
        if kind == "slider":
            sliders.append((column, slot))
        elif kind == "button":
            buttons.append((row, column, slot))

    dropped = 0
    misplaced: List[Dict[str, Any]] = []
    # Faders keep their columns only when all of them still fit. If one does not, they all move to the rightmost
    # columns together, so they stay in the same left-to-right order.
    all_fit = all(column < new_columns for column, _ in sliders)
    for column, slot in sliders:
        if all_fit:
            placed[column] = {**copy.deepcopy(slot), "index": column}
            placed[column + new_columns] = _occupied(column, new_columns)
        else:
            misplaced.append(slot)

    leftovers: List[Dict[str, Any]] = []
    for row, column, slot in buttons:  # buttons keep their cell when it exists and is free
        index = row * new_columns + column
        if row < new_rows and column < new_columns and placed[index] is None:
            placed[index] = {**copy.deepcopy(slot), "index": index}
        else:
            leftovers.append(slot)

    for slot in reversed(misplaced):  # the last fader takes the rightmost column, so they keep their order
        column = next((c for c in range(new_columns - 1, -1, -1)
                       if not _holds_fader(placed[c]) and not _holds_fader(placed[c + new_columns])), None)
        if column is None:
            dropped += 1
            continue
        for index in (column, column + new_columns):
            if placed[index] is not None:
                leftovers.append(placed[index])
        placed[column] = {**copy.deepcopy(slot), "index": column}
        placed[column + new_columns] = _occupied(column, new_columns)

    for slot in leftovers:  # whatever is left goes to the first free cells
        index = next((i for i, cell in enumerate(placed) if cell is None), None)
        if index is None:
            dropped += 1
        else:
            placed[index] = {**copy.deepcopy(slot), "index": index}

    return [cell if cell is not None else {"index": i, "type": "empty"} for i, cell in enumerate(placed)], dropped


def convert_config(config: Dict[str, Any], spec: Any) -> Tuple[Dict[str, Any], int]:
    """A copy of the whole profile in another grid size, and the number of items that did not fit.

    `spec` is a quick-pick name or "<columns>x<rows>" or {"columns": n, "rows": n}."""
    new_layout = layout_dict(spec)
    old = size_of(config.get("layout"))
    new = (new_layout["rows"], new_layout["columns"])
    converted = copy.deepcopy(config)
    dropped = 0
    if old != new:
        for page in converted["pages"]:
            page["slots"], lost = convert_slots(page["slots"], old, new)
            dropped += lost
    converted["layout"] = new_layout
    converted["slots"] = copy.deepcopy(converted["pages"][converted.get("current_page", 0)]["slots"])
    return converted, dropped
