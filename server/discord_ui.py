"""Discord's soundboard, driven through the Discord window the user already has open.

Discord only lets bots play sounds through its API, and using a user account for that is against its
rules, so StreamDesk never touches the account. Instead it does what the user does: Windows UI
Automation reads the soundboard panel of the Discord window (every sound is a button named
"Reproducir <nombre>") and presses the right one. Nothing is sent to Discord's servers by StreamDesk,
and the mouse and the focused window are left alone.

Limits: Discord must be open (it can be behind other windows, but not minimized or closed to the tray),
the user must be in a voice channel, and the labels are read in Spanish ("Reproducir", "Abrir panel de
sonidos"). A Discord redesign can break it, and the errors say what could not be found.
"""

import ctypes
import re
import time
from ctypes import wintypes
from typing import Any, Dict, List, Optional, Tuple

import psutil

from server.com_worker import ComWorker

# Discord's own words, as read from its window. Change them here for another language.
PLAY_PREFIX = "Reproducir "
OPEN_PANEL = "Abrir panel de sonidos"
PANEL_ANCHOR = "Volumen del panel de sonidos"
# Sections that repeat sounds already listed under their server.
ALIAS_SECTIONS = ("Favoritos", "Usados frecuentemente")
ALIAS_PREFIX = "Sonidos más usados"

UIA_BUTTON, UIA_IMAGE, UIA_LISTITEM, UIA_TEXT = 50000, 50006, 50007, 50020
INVOKE_PATTERN, SCROLL_PATTERN = 10000, 10004

# Its own thread: reading the panel takes a few seconds and must not stall the volume faders.
ui_worker = ComWorker()


class DiscordUiError(Exception):
    """Something the user can fix or should know, in Spanish."""


Rect = Tuple[int, int, int, int]


def _inside(inner: Rect, outer: Rect, slack: int = 4) -> bool:
    return (inner[0] >= outer[0] - slack and inner[2] <= outer[2] + slack
            and inner[1] >= outer[1] - slack and inner[3] <= outer[3] + slack)


def _find_window() -> int:
    """Handle of Discord's main window, or an error saying why there is none."""
    user32 = ctypes.windll.user32
    pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == "discord.exe"}
    if not pids:
        raise DiscordUiError("Discord no está abierto.")
    found: List[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value not in pids or not user32.IsWindowVisible(hwnd):
            return True
        title, cls = ctypes.create_unicode_buffer(200), ctypes.create_unicode_buffer(80)
        user32.GetWindowTextW(hwnd, title, 200)
        user32.GetClassNameW(hwnd, cls, 80)
        if cls.value == "Chrome_WidgetWin_1" and title.value.endswith("Discord"):
            found.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        raise DiscordUiError("No encuentro la ventana de Discord. Ábrela (puede quedar detrás de otras ventanas).")
    if user32.IsIconic(found[0]):
        raise DiscordUiError("Discord está minimizado. Ábrelo (puede quedar detrás de otras ventanas).")
    return found[0]


class _Panel:
    """One session with the soundboard panel. Create and use it on the ui_worker thread only."""

    def __init__(self) -> None:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA
        self.UIA = UIA
        self.auto = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation)
        self.root = self.auto.ElementFromHandle(_find_window())
        self.cache = self.auto.CreateCacheRequest()
        for prop in (UIA.UIA_NamePropertyId, UIA.UIA_BoundingRectanglePropertyId, UIA.UIA_ControlTypePropertyId):
            self.cache.AddProperty(prop)
        self.rect: Rect = (0, 0, 0, 0)
        self.scroll = None
        self._wait_for_tree()
        self._open_panel()

    # ---- reading the window
    def _all(self, control_type: int, root=None) -> List[Tuple[Any, str, Rect]]:
        condition = self.auto.CreatePropertyCondition(self.UIA.UIA_ControlTypePropertyId, control_type)
        found = (root or self.root).FindAllBuildCache(self.UIA.TreeScope_Descendants, condition, self.cache)
        items = []
        for index in range(found.Length):
            try:
                element = found.GetElement(index)
                r = element.CachedBoundingRectangle
                items.append((element, element.CachedName or "", (r.left, r.top, r.right, r.bottom)))
            except Exception:
                continue  # Discord redrew that element while we were reading: it will be there on the next look
        return items

    def _named(self, name: str, control_type: int = UIA_BUTTON) -> Optional[Any]:
        return next((e for e, n, _ in self._all(control_type) if n == name), None)

    def _wait_for_tree(self) -> None:
        # Chromium builds its accessibility tree only after the first client asks for it.
        for _ in range(24):
            if len(self._all(UIA_BUTTON)) > 5:
                return
            time.sleep(0.25)
        raise DiscordUiError("Discord no muestra su interfaz a Windows. Si está minimizado, ábrelo; si sigue igual, reinícialo.")

    def _invoke(self, element) -> None:
        pattern = element.GetCurrentPattern(INVOKE_PATTERN)
        if not pattern:
            raise DiscordUiError("Discord no deja pulsar ese botón.")
        pattern.QueryInterface(self.UIA.IUIAutomationInvokePattern).Invoke()

    # ---- the panel
    def _open_panel(self) -> None:
        anchor = self._named(PANEL_ANCHOR)
        if anchor is None:
            # Two buttons carry this name (the call bar and the full-screen view): press whichever can be pressed.
            openers = [e for e, n, _ in self._all(UIA_BUTTON) if n == OPEN_PANEL and e.GetCurrentPattern(INVOKE_PATTERN)]
            if not openers:
                raise DiscordUiError("No veo el panel de sonidos. Entra en un canal de voz de un servidor y vuelve a probar.")
            self._invoke(openers[0])
            for _ in range(16):
                time.sleep(0.25)
                anchor = self._named(PANEL_ANCHOR)
                if anchor is not None:
                    break
            else:
                raise DiscordUiError("El panel de sonidos no se abrió. Ábrelo tú una vez y vuelve a probar.")
        walker = self.auto.ControlViewWalker
        node = anchor
        for _ in range(10):  # the panel is the first ancestor that is big enough to hold a list of sounds
            node = walker.GetParentElement(node)
            r = node.CurrentBoundingRectangle
            if r.right - r.left >= 400 and r.bottom - r.top >= 300:
                self.rect = (r.left, r.top, r.right, r.bottom)
                break
        else:
            raise DiscordUiError("No reconozco el panel de sonidos de esta versión de Discord.")
        condition = self.auto.CreatePropertyCondition(self.UIA.UIA_IsScrollPatternAvailablePropertyId, True)
        holder = node if node.GetCurrentPattern(SCROLL_PATTERN) else node.FindFirst(self.UIA.TreeScope_Descendants, condition)
        if holder:
            self.scroll = holder.GetCurrentPattern(SCROLL_PATTERN).QueryInterface(self.UIA.IUIAutomationScrollPattern)

    def rail(self) -> List[Tuple[str, Any]]:
        """(section name, tab) for every tab on the left of the panel, top to bottom."""
        left = self.rect[0]
        tabs = [(e, r) for e, _, r in self._all(UIA_LISTITEM)
                if _inside(r, self.rect) and r[2] - r[0] <= 48 and r[0] - left < 48]
        images = [(n, r) for _, n, r in self._all(UIA_IMAGE) if n and _inside(r, self.rect) and r[2] - r[0] >= 28]  # the icon, not a badge on it
        labels = [(n, r) for _, n, r in self._all(UIA_TEXT) if n and _inside(r, self.rect)]
        named = []
        for element, r in sorted(tabs, key=lambda tab: tab[1][1]):
            # A server's tab carries its icon, named after the server. The other tabs (Discord's own sounds,
            # favourites...) have a text label right under them instead.
            name = next((n for n, ir in images if _inside(ir, r)), "")
            if not name:
                name = next((n for n, lr in labels if abs(lr[0] - r[0]) <= 2 and abs(lr[1] - (r[1] + 37)) <= 4), "")
            named.append((name, element))
        return named

    def view(self) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str, Any]]]:
        """(headers, sounds) on screen, top to bottom: headers as (top, name), sounds as (top, label, button)."""
        content_left = self.rect[0] + 56
        headers, sounds = [], []
        for element, name, r in self._all(UIA_BUTTON):
            if not _inside(r, self.rect) or r[0] < content_left - 8:
                continue
            if name.startswith(PLAY_PREFIX):
                sounds.append((r[1], name[len(PLAY_PREFIX):], element))
            elif abs(r[0] - content_left) <= 8 and 12 <= r[3] - r[1] <= 26 and name:
                headers.append((r[1], name))
        return sorted(headers), sorted(sounds, key=lambda s: (s[0], s[2].CachedBoundingRectangle.left))

    @staticmethod
    def section_of(top: int, headers: List[Tuple[int, str]], section: str) -> str:
        """Which section a sound at `top` belongs to. Sounds above the first visible header continue the
        section that was just opened, unless its own header is on screen (then they belong to the one before)."""
        own_header_visible = any(name == section for _, name in headers)
        current = "" if own_header_visible else section
        for header_top, name in headers:
            if header_top <= top:
                current = name
        return current

    def pages(self, section: str):
        """Selects a section's tab and yields (headers, sounds) for each screen of the panel, top to bottom."""
        tabs = self.rail()
        element = next((e for label, e in tabs if label == section), None)
        if element is None:
            raise DiscordUiError(f"No encuentro «{section}» en el panel de sonidos.")
        self._invoke(element)
        time.sleep(0.6)
        last = -1.0
        for _ in range(14):
            yield self.view()
            if self.scroll is None:
                return
            try:
                percent = self.scroll.CurrentVerticalScrollPercent
                if percent < 0 or percent >= 99.5 or percent == last:
                    return
                last = percent
                self.scroll.Scroll(self.UIA.ScrollAmount_NoAmount, self.UIA.ScrollAmount_LargeIncrement)
            except Exception:
                return  # Discord refuses to scroll further: that was the end of the list
            time.sleep(0.3)


def _is_alias(name: str) -> bool:
    return name in ALIAS_SECTIONS or name.startswith(ALIAS_PREFIX)


def _scan() -> List[Dict[str, Any]]:
    panel = _Panel()
    found: List[Dict[str, Any]] = []
    tabs = panel.rail()
    # "Sonidos más usados en <servidor>" names the server of the voice channel the user is in.
    current = next((label[len(ALIAS_PREFIX):].strip().removeprefix("en ").strip() for label, _ in tabs if label.startswith(ALIAS_PREFIX)), "")
    for section, _ in tabs:
        if not section or _is_alias(section):
            continue
        seen = set()
        for headers, sounds in panel.pages(section):
            for top, label, _button in sounds:
                if panel.section_of(top, headers, section) == section and label.strip() not in seen:
                    seen.add(label.strip())
                    found.append({"section": section, "label": label.strip(), "current": section == current})
            if any(name != section and not _is_alias(name) for _, name in headers):
                break  # the next server's header is on screen: this section is complete
    if not found:
        raise DiscordUiError("No encontré sonidos en el panel. ¿Tienes sonidos en tus servidores?")
    return found


def _locate(panel: _Panel, section: str, label: str):
    wanted = label.strip()

    def match(headers, sounds):
        for top, text, button in sounds:
            if text.strip() == wanted and panel.section_of(top, headers, section) == section:
                return button
        return None

    headers, sounds = panel.view()
    # Already on screen? Only trust the current view when the section's own header is visible in it.
    button = match(headers, sounds) if any(name == section for _, name in headers) else None
    if button is None:
        for headers, sounds in panel.pages(section):
            button = match(headers, sounds)
            if button is not None:
                break
    if button is None:
        raise DiscordUiError(f"No encuentro el sonido «{wanted}» en «{section}». ¿Lo borraron o lo cambiaron de nombre?")
    return button


def _play(section: str, label: str) -> None:
    panel = _Panel()
    panel._invoke(_locate(panel, section, label))


def list_sounds() -> List[Dict[str, Any]]:
    """Every sound of every server in the panel, as {"section", "label", "current"}. Takes a few seconds."""
    return ui_worker.call(_scan, timeout=90)


def play(section: str, label: str) -> None:
    ui_worker.call(_play, section, label, timeout=40)


def split_label(label: str) -> Tuple[str, str]:
    """"🚪 Tocar Puerta" -> ("🚪", "Tocar Puerta"); names without an emoji come back as ("", name)."""
    match = re.match(r"^(\S+) (.+)$", label)
    if match and not re.match(r"^[\w¿¡'\"(\[]", match.group(1), re.UNICODE):
        return match.group(1), match.group(2)
    return "", label
