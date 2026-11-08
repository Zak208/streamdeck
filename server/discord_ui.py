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

import atexit
import concurrent.futures
import ctypes
import re
import time
from ctypes import wintypes
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

import psutil

from server import discord_cache
from server.com_worker import ComWorker

# Discord's own words, as read from its window. Change them here for another language.
PLAY_PREFIX = "Reproducir "
OPEN_PANEL = "Abrir panel de sonidos"
PANEL_ANCHOR = "Volumen del panel de sonidos"
# Sections that repeat sounds already listed under their server.
ALIAS_SECTIONS = ("Favoritos", "Usados frecuentemente")
ALIAS_PREFIX = "Sonidos más usados"
# The voice bar (bottom left): a button "Detalles de voz Voz conectada" with a link "<canal> / <servidor> <tiempo>" under it.
VOICE_STATUS = "Detalles de voz Voz conectada"
VOICE_TIMER = re.compile(r"\s+\d{1,2}(:\d{2}){1,2}$")

UIA_BUTTON, UIA_HYPERLINK, UIA_IMAGE, UIA_LISTITEM, UIA_TEXT = 50000, 50005, 50006, 50007, 50020
INVOKE_PATTERN, SCROLL_PATTERN, TOGGLE_PATTERN = 10000, 10004, 10015
# The user panel (bottom left): [microphone] [headphones] [Ajustes de usuario]. The two buttons just left of the
# settings one are mute and deafen; found by position, because their names change when they are on.
USER_SETTINGS = "Ajustes de usuario"

# Its own thread: reading the panel takes a few seconds and must not stall the volume faders.
ui_worker = ComWorker()

# Any press, tab change or scroll through UI Automation makes Discord (Electron) take the focus, which would pull
# the user out of their game. While StreamDesk acts, the window is marked "cannot be activated"; measured live:
# with the mark the focus never moved, without it every one of those actions took it.
GWL_EXSTYLE, WS_EX_NOACTIVATE = -20, 0x08000000
REACTION_SECONDS = 0.4  # Chromium reacts a moment after the click: keep the mark on until then
# A private copy of user32: setting argument types on the shared one would change it for the whole app.
_user32 = ctypes.WinDLL("user32")
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_marked: set = set()  # windows we marked and have not cleared yet


def _clear_marks() -> None:
    for hwnd in list(_marked):
        _unmark(hwnd)


def _mark(hwnd: int) -> None:
    style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    if not style & WS_EX_NOACTIVATE:  # never touch a mark somebody else set
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
        _marked.add(hwnd)


def _unmark(hwnd: int) -> None:
    if hwnd in _marked:
        _marked.discard(hwnd)
        _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & ~WS_EX_NOACTIVATE)


atexit.register(_clear_marks)  # a crash must not leave Discord unable to take the focus


class DiscordUiError(Exception):
    """Something the user can fix or should know, in Spanish."""


Rect = Tuple[int, int, int, int]


def _inside(inner: Rect, outer: Rect, slack: int = 4) -> bool:
    return (inner[0] >= outer[0] - slack and inner[2] <= outer[2] + slack
            and inner[1] >= outer[1] - slack and inner[3] <= outer[3] + slack)


class AppSpec(NamedTuple):
    """An Electron or Chromium program whose window we read: its process, its name for messages, its window title."""
    process: str
    name: str
    title_ok: Callable[[str], bool]


DISCORD = AppSpec("discord.exe", "Discord", lambda title: title.endswith("Discord"))


def _find_window(app: AppSpec = DISCORD) -> int:
    """Handle of the program's main window (the biggest visible one), or an error saying why there is none."""
    user32 = ctypes.windll.user32
    pids = {p.pid for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == app.process}
    if not pids:
        raise DiscordUiError(f"{app.name} no está abierto.")
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
        if cls.value == "Chrome_WidgetWin_1" and app.title_ok(title.value):
            found.append(hwnd)
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        raise DiscordUiError(f"No encuentro la ventana de {app.name}. Ábrela (puede quedar detrás de otras ventanas).")

    def area(hwnd: int) -> int:
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        return (r.right - r.left) * (r.bottom - r.top)

    main = max(found, key=area)
    if user32.IsIconic(main):
        # Never restored by StreamDesk: showing a minimized window can pull the focus away from the user's game.
        raise DiscordUiError(f"{app.name} está minimizado. Déjalo abierto sin minimizar, por ejemplo en tu otra pantalla o detrás de tu programa, y no te quitará el foco.")
    return main


class _Window:
    """Windows UI Automation over Discord's main window. Create and use it on the ui_worker thread only."""

    def __init__(self, guard: bool = False, app: AppSpec = DISCORD) -> None:
        """With `guard`, the program cannot take the focus until close(). Reading alone never needs it."""
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA
        self.app = app
        self.hwnd = _find_window(app)
        self._guarded = False
        if guard:
            _mark(self.hwnd)
            self._guarded = True
        self.UIA = UIA
        self.auto = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation)
        self.root = self.auto.ElementFromHandle(self.hwnd)
        self.cache = self.auto.CreateCacheRequest()
        for prop in (UIA.UIA_NamePropertyId, UIA.UIA_BoundingRectanglePropertyId, UIA.UIA_ControlTypePropertyId):
            self.cache.AddProperty(prop)

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

    def close(self) -> None:
        """Let Discord take the focus again, after the reaction to our last click has passed."""
        if getattr(self, "_guarded", False):
            self._guarded = False
            time.sleep(REACTION_SECONDS)
            _unmark(self.hwnd)

    def _named(self, name: str, control_type: int = UIA_BUTTON) -> Optional[Any]:
        return next((e for e, n, _ in self._all(control_type) if n == name), None)

    def _wait_for_tree(self) -> None:
        # Chromium builds its accessibility tree only after the first client asks for it.
        for _ in range(24):
            if len(self._all(UIA_BUTTON)) > 5:
                return
            time.sleep(0.25)
        name = getattr(self, "app", DISCORD).name
        raise DiscordUiError(f"{name} no muestra su interfaz a Windows. Si está minimizado, ábrelo; si sigue igual, reinícialo.")

    def _invoke(self, element) -> None:
        pattern = element.GetCurrentPattern(INVOKE_PATTERN)
        if not pattern:
            raise DiscordUiError("Discord no deja pulsar ese botón.")
        pattern.QueryInterface(self.UIA.IUIAutomationInvokePattern).Invoke()


class _Panel(_Window):
    """One session with the soundboard panel."""

    def __init__(self) -> None:
        super().__init__(guard=True)
        self.rect: Rect = (0, 0, 0, 0)
        self.scroll = None
        try:
            self._wait_for_tree()
            self._open_panel()
        except BaseException:
            self.close()
            raise

    # ---- the panel
    def _open_panel(self) -> None:
        anchor = self._named(PANEL_ANCHOR)
        if anchor is None:
            # Two buttons carry this name (the call bar and the full-screen view): press whichever can be pressed.
            openers = [e for e, n, _ in self._all(UIA_BUTTON) if n == OPEN_PANEL and e.GetCurrentPattern(INVOKE_PATTERN)]
            if not openers:
                # If Discord is viewing a text chat or another screen, click the voice bar to switch to the voice view
                voice_btn = next((e for e, n, _ in self._all(UIA_BUTTON) if (n and (VOICE_STATUS in n or "Voz conectada" in n or "Detalles de voz" in n)) and e.GetCurrentPattern(INVOKE_PATTERN)), None)
                if voice_btn:
                    try:
                        self._invoke(voice_btn)
                        time.sleep(0.6)
                        openers = [e for e, n, _ in self._all(UIA_BUTTON) if n == OPEN_PANEL and e.GetCurrentPattern(INVOKE_PATTERN)]
                    except Exception:
                        pass
            if not openers:
                raise DiscordUiError("Discord solo ofrece el panel de sonidos dentro de un canal de voz. Entra en uno de un servidor y vuelve a pulsar.")
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
        def in_rail(r: Rect) -> bool:
            return self.rect[1] <= (r[1] + r[3]) // 2 <= self.rect[3] and left - 4 <= r[0] and r[0] - left < 48

        tabs = [(e, r) for e, _, r in self._all(UIA_LISTITEM) if in_rail(r) and r[2] - r[0] <= 48]
        images = [(n, r) for _, n, r in self._all(UIA_IMAGE) if n and in_rail(r) and r[2] - r[0] >= 28]  # the icon, not a badge on it
        labels = [(n, r) for _, n, r in self._all(UIA_TEXT) if n and in_rail(r)]
        named = []
        for element, r in sorted(tabs, key=lambda tab: tab[1][1]):
            # A server's tab carries its icon, named after the server. The other tabs (Discord's own sounds,
            # favourites...) have a text label right under them instead.
            name = next((n for n, ir in images if abs(ir[1] - r[1]) <= 6 and abs(ir[0] - r[0]) <= 6), "")
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
        element = None
        for _ in range(8):  # the tabs are redrawn after every click: give Discord a moment before giving up
            element = next((e for label, e in self.rail() if label == section), None)
            if element is not None:
                break
            time.sleep(0.25)
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


def parse_voice_link(name: str) -> Optional[str]:
    """The server in the voice bar's link: "Sala / Mi servidor 02:20:32" gives "Mi servidor"."""
    text = VOICE_TIMER.sub("", name.strip())
    if " / " not in text:
        return None
    return text.rsplit(" / ", 1)[1].strip() or None


def _voice_server() -> Optional[str]:
    try:
        window = _Window()
    except DiscordUiError:
        return None  # Discord closed or minimized: nothing to read, and nothing to react to
    if len(window._all(UIA_BUTTON)) <= 5:
        return None  # the accessibility tree is only built after the first look; the next one finds it
    status = next((r for _, n, r in window._all(UIA_BUTTON) if n == VOICE_STATUS), None)
    if status is None:
        return None  # not connected to a voice channel
    for _, name, r in window._all(UIA_HYPERLINK):
        if abs(r[0] - status[0]) <= 8 and 0 <= r[1] - status[1] <= 40:
            return parse_voice_link(name)
    return None


def _is_alias(name: str) -> bool:
    return name in ALIAS_SECTIONS or name.startswith(ALIAS_PREFIX)


def _scan() -> List[Dict[str, Any]]:
    panel = _Panel()
    try:
        return _scan_panel(panel)
    finally:
        panel.close()


def _scan_panel(panel: "_Panel") -> List[Dict[str, Any]]:
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
    try:
        panel._invoke(_locate(panel, section, label))
    finally:
        panel.close()


def list_sounds() -> List[Dict[str, Any]]:
    """Every sound of every server in the panel, as {"section", "label", "current"}. Takes a few seconds.
    A successful reading is also kept on disk, so Studio can list the sounds later without a voice channel."""
    found = ui_worker.call(_scan, timeout=90)
    try:
        discord_cache.save(found)
    except OSError:
        pass  # the list is still returned: only the saved copy is missing
    return found


def _voice_buttons(window: "_Window"):
    """(mute, deafen) of the user panel, each as (element, name, rect)."""
    buttons = window._all(UIA_BUTTON)
    anchor = next((b for b in buttons if b[1] == USER_SETTINGS), None)
    if anchor is None:
        raise DiscordUiError("No veo el panel de usuario de Discord (abajo a la izquierda). Déjalo abierto y a la vista.")
    row = sorted((b for b in buttons if abs(b[2][1] - anchor[2][1]) <= 6 and b[2][2] <= anchor[2][0] + 4 and anchor[2][0] - b[2][0] <= 150),
                 key=lambda b: b[2][0])
    # Between them there can be other buttons (the arrows "Opciones de entrada / salida"): mute and deafen are the
    # ones that are switches, so those are the two that count.
    switches = [b for b in row if _toggle_state(window, b[0]) is not None]
    row = switches if len(switches) >= 2 else row
    if len(row) < 2:
        raise DiscordUiError("No encuentro los botones de silenciar y ensordecer de Discord.")
    return row[-2], row[-1]


def _toggle_state(window: "_Window", element) -> Optional[bool]:
    try:
        pattern = element.GetCurrentPattern(TOGGLE_PATTERN)
        if pattern:
            return bool(pattern.QueryInterface(window.UIA.IUIAutomationTogglePattern).CurrentToggleState == 1)
    except Exception:
        pass
    return None


def _press_voice_button(kind: str) -> Optional[bool]:
    """Presses «mute» or «deafen» in Discord's window, as a click would, and returns whether it is now on."""
    window = _Window(guard=True)  # the window cannot take the focus while we press
    try:
        window._wait_for_tree()
        mute, deafen = _voice_buttons(window)
        element = (mute if kind == "mute" else deafen)[0]
        toggle = None
        try:
            toggle = element.GetCurrentPattern(TOGGLE_PATTERN)
        except Exception:
            pass
        if toggle:
            toggle.QueryInterface(window.UIA.IUIAutomationTogglePattern).Toggle()
        else:
            window._invoke(element)
        time.sleep(0.35)  # Discord redraws the button a moment after the press
        return _toggle_state(window, element)
    finally:
        window.close()


def toggle_voice(kind: str) -> Optional[bool]:
    """Mute or deafen in Discord without any shortcut set up. True or False is the new state (None when it cannot be read)."""
    if kind not in ("mute", "deafen"):
        raise DiscordUiError("Acción de Discord no válida")
    return ui_worker.call(_press_voice_button, kind, timeout=15)


_voice_pending = None


def current_voice_server() -> Optional[str]:
    """Name of the server whose voice channel the user is in, or None (also when Discord cannot be read).

    While a long job (a scan of the sounds) holds the Discord worker, the question is not queued again and again."""
    global _voice_pending
    if _voice_pending is not None and not _voice_pending.done():
        return None
    _voice_pending = ui_worker.submit(_voice_server)
    try:
        return _voice_pending.result(8)
    except concurrent.futures.TimeoutError:
        return None  # it stays queued once: the next question finds it pending


def play(section: str, label: str) -> None:
    ui_worker.call(_play, section, label, timeout=40)


def split_label(label: str) -> Tuple[str, str]:
    """"🚪 Tocar Puerta" -> ("🚪", "Tocar Puerta"); names without an emoji come back as ("", name)."""
    match = re.match(r"^(\S+) (.+)$", label)
    if match and not re.match(r"^[\w¿¡'\"(\[]", match.group(1), re.UNICODE):
        return match.group(1), match.group(2)
    return "", label
