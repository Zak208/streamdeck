"""Starts a Spotify playlist, album or track by pressing its play button in the Spotify desktop window.

Spotify's Web API only plays music for Premium accounts, and a free account (or none connected) was left
with a button that just opened the list. The desktop app lets anyone press play, so StreamDesk does what
the user does: opens the link in the app, waits for that page, and presses its big play button through
Windows UI Automation. It uses neither the account nor any Spotify server, and, like the Discord
soundboard, it marks the window "cannot be activated" while it acts so the focus stays where it was.

Limits: the Spotify desktop app must be open and visible (not minimized), and its labels are read in
Spanish ("Reproducir"). Free accounts play a playlist in shuffle, as the app does by itself.
"""

import ctypes
import os
import time
from typing import Any, Optional, Tuple

import psutil

from server.discord_ui import AppSpec, DiscordUiError, Rect, TOGGLE_PATTERN, _Window, _find_window, ui_worker

SpotifyUiError = DiscordUiError  # same kind of problem: a message for the user, in Spanish

# The main window's title is "Spotify Free" or the song playing, so any visible Chromium window counts; the biggest wins.
SPOTIFY = AppSpec("spotify.exe", "Spotify", lambda title: bool(title))
PLAY_PREFIX = "Reproducir "
PAUSE_PREFIXES = ("Pausar ", "Pausa ")  # the same big button once that page's music is playing: do not press it then
PAGE_MARK = "| Spotify"  # pages are titled "<name> - playlist by <owner> | Spotify" or "<name> | Spotify Playlist"
UIA_BUTTON, UIA_GROUP = 50000, 50026
BIG_BUTTON = 36  # the header's play button is about 45 px; the ones on each track row are 16 px
PAGE_WAIT_SECONDS = 10
LAUNCH_WAIT_SECONDS = 20


def _running() -> bool:
    return any((p.info["name"] or "").lower() == SPOTIFY.process for p in psutil.process_iter(["name"]))


def _page(window: _Window) -> Tuple[str, Optional[Rect]]:
    """(title, area) of the page on screen. The main view carries the page's title as its name; the document's
    own title turns into the song's name while something plays, so it cannot be used."""
    for _, name, r in window._all(UIA_GROUP):
        if PAGE_MARK in name and r[2] - r[0] >= 300 and r[3] - r[1] >= 300:
            return name, r
    return "", None


def _header_play(window: _Window, title: str, view: Rect) -> Optional[Tuple[Any, bool]]:
    """(button, already_playing) for the big play button of the page that is showing, or None while it loads."""
    candidates = [(r, element, name) for element, name, r in window._all(UIA_BUTTON)
                  if name.startswith((PLAY_PREFIX,) + PAUSE_PREFIXES) and r[2] - r[0] >= BIG_BUTTON and r[3] - r[1] >= BIG_BUTTON
                  and r[0] >= view[0] - 4 and r[2] <= view[2] + 4 and r[1] >= view[1] - 4 and r[3] <= view[3] + 4]
    if not candidates:
        return None
    r, element, name = min(candidates, key=lambda c: (c[0][1], c[0][0]))  # top-left first: the page's own button
    playing = name.startswith(PAUSE_PREFIXES)
    prefix = next(p for p in (PLAY_PREFIX,) + PAUSE_PREFIXES if name.startswith(p))
    shown = name[len(prefix):].strip().casefold()[:24]
    if not title.casefold().startswith(shown):
        return None  # a button of some other page, still on screen while this one loads
    return element, playing


def _wait_for_page(window: _Window, before: str) -> Tuple[Any, bool]:
    started = time.time()
    while time.time() - started < PAGE_WAIT_SECONDS:
        title, view = _page(window)
        # a page that did not change the title (we were already on it) is ready after a short wait
        if view is not None and (title != before or time.time() - started > 3):
            button = _header_play(window, title, view)
            if button is not None:
                return button
        time.sleep(0.3)
    raise SpotifyUiError("No encontré el botón de reproducir de esa lista en Spotify. Comprueba que la app está abierta y a la vista.")


def _wait_for_window() -> None:
    started = time.time()
    while time.time() - started < LAUNCH_WAIT_SECONDS:
        try:
            _find_window(SPOTIFY)
            return
        except SpotifyUiError:
            time.sleep(0.5)
    raise SpotifyUiError("Spotify no llegó a abrirse. Ábrelo y vuelve a probar.")


def _press(window: _Window, before: str) -> None:
    button, playing = _wait_for_page(window, before)
    if not playing:  # a page that is already playing would be paused by its own button
        window._invoke(button)


def _play(uri: str) -> None:
    if _running():
        window = _Window(guard=True, app=SPOTIFY)  # raises if the window is minimized or cannot be found
        try:
            before = _page(window)[0]
            os.startfile(uri)  # Spotify navigates to the page; the mark keeps it from taking the focus
            window._wait_for_tree()
            _press(window, before)
        finally:
            window.close()
        return
    os.startfile(uri)  # closed: launching it on that page is the only way, and it will take the focus
    _wait_for_window()
    window = _Window(guard=True, app=SPOTIFY)
    try:
        window._wait_for_tree()
        _press(window, "")
    finally:
        window.close()


def play(uri: str) -> None:
    """Open a spotify: link and press its play button. Raises SpotifyUiError with the reason."""
    ui_worker.call(_play, uri, timeout=60)


def _post_click(hwnd: int, r: Rect) -> None:
    """Sends background left click without activating window or stealing focus."""
    cx = (r[0] + r[2]) // 2
    cy = (r[1] + r[3]) // 2
    pt = (ctypes.c_long * 2)(cx, cy)
    ctypes.windll.user32.ScreenToClient(hwnd, pt)
    lparam = (pt[1] << 16) | (pt[0] & 0xFFFF)
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    ctypes.windll.user32.PostMessageW(hwnd, WM_LBUTTONDOWN, 1, lparam)
    time.sleep(0.04)
    ctypes.windll.user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)


def _toggle_like() -> bool:
    if not _running():
        raise SpotifyUiError("Spotify no está abierto.")
    window = _Window(guard=True, app=SPOTIFY)
    try:
        window._wait_for_tree()
        rect = (ctypes.c_long * 4)()
        ctypes.windll.user32.GetWindowRect(window.hwnd, rect)
        bar_y = rect[3] - 140
        center_x = (rect[0] + rect[2]) // 2

        cb_targets = (
            "canciones que te gustan", "canciones favoritas", "liked songs", "favorite songs"
        )
        hecho_targets = (
            "hecho", "done", "guardar", "listo", "save"
        )

        # 1. Check if the playlist picker popup is already open
        cb_liked = None
        for elem, name, r in window._all(50002):
            low = (name or "").strip().lower()
            if any(t in low for t in cb_targets):
                cb_liked = (elem, name, r)
                break

        # 2. If not already open, click the bottom bar button to open the playlist picker
        if not cb_liked:
            like_targets_bottom = (
                "añadir a lista", "añadir a la lista", "añadir a canciones que te gustan",
                "eliminar de canciones que te gustan", "quitar de canciones que te gustan",
                "añadir a tu biblioteca", "eliminar de tu biblioteca", "quitar de tu biblioteca",
                "guardar en tu biblioteca", "guardada en tu biblioteca", "guardado en tu biblioteca",
                "guardar en canciones que te gustan", "guardada en canciones que te gustan",
                "save to your library", "remove from your library", "add to liked songs", "add to playlist"
            )
            bottom_btn = None
            for elem, name, r in window._all(UIA_BUTTON):
                low = (name or "").strip().lower()
                if r[1] >= bar_y and r[0] < center_x:
                    if any(t in low for t in like_targets_bottom):
                        bottom_btn = (elem, name, r)
                        break

            if not bottom_btn:
                like_targets_global = (
                    "guardar en tu biblioteca", "añadir a canciones que te gustan", "añadir a tu biblioteca",
                    "eliminar de canciones que te gustan", "eliminar de tu biblioteca", "quitar de tu biblioteca",
                    "save to your library", "remove from your library", "add to liked songs"
                )
                for elem, name, r in window._all(UIA_BUTTON):
                    low = (name or "").strip().lower()
                    if any(t in low for t in like_targets_global):
                        bottom_btn = (elem, name, r)
                        break

            if not bottom_btn:
                raise SpotifyUiError("No encuentro el botón de Me gusta en la app de Spotify.")

            # Trigger bottom button via post_click (background message without stealing focus)
            _post_click(window.hwnd, bottom_btn[2])

            # Wait up to 1.5s for the playlist picker to appear
            for _ in range(15):
                time.sleep(0.1)
                for elem, name, r in window._all(50002):
                    low = (name or "").strip().lower()
                    if any(t in low for t in cb_targets):
                        cb_liked = (elem, name, r)
                        break
                if cb_liked:
                    break

        # 3. If playlist picker is open, toggle "Canciones que te gustan"
        if cb_liked:
            elem, name, r = cb_liked
            t_unk = elem.GetCurrentPattern(TOGGLE_PATTERN)
            if t_unk:
                try:
                    toggle = t_unk.QueryInterface(window.UIA.IUIAutomationTogglePattern)
                    toggle.Toggle()
                except Exception:
                    window._invoke(elem)
            else:
                window._invoke(elem)

            time.sleep(0.2)

            # Find and click "Hecho" / "Done" to save and close the popup
            hecho_btn = None
            for _ in range(10):
                for b_elem, b_name, b_r in window._all(UIA_BUTTON):
                    if b_name.strip().lower() in hecho_targets:
                        hecho_btn = (b_elem, b_name, b_r)
                        break
                if hecho_btn:
                    break
                time.sleep(0.1)

            if hecho_btn:
                try:
                    window._invoke(hecho_btn[0])
                except Exception:
                    _post_click(window.hwnd, hecho_btn[2])
                time.sleep(0.2)
            return True

        # 4. Fallback for older 1-click heart icon Spotify versions
        return True
    finally:
        window.close()


def toggle_like() -> bool:
    """Toggles like/favorite on the currently playing track in Spotify desktop without taking window focus."""
    return ui_worker.call(_toggle_like, timeout=15)


def _toggle_shuffle() -> bool:
    if not _running():
        raise SpotifyUiError("Spotify no está abierto.")
    window = _Window(guard=True, app=SPOTIFY)
    try:
        window._wait_for_tree()
        shuffle_targets = (
            "reproducción aleatoria", "aleatorio", "aleatoria", "shuffle"
        )
        for ct in (UIA_BUTTON, 50002):
            for element, name, _ in window._all(ct):
                low = (name or "").strip().lower()
                if any(t in low for t in shuffle_targets):
                    window._invoke(element)
                    return True
        raise SpotifyUiError("No encuentro el botón de Aleatorio en la app de Spotify.")
    finally:
        window.close()


def toggle_shuffle() -> bool:
    """Toggles shuffle mode in Spotify desktop without taking window focus."""
    return ui_worker.call(_toggle_shuffle, timeout=15)


def _cycle_repeat() -> bool:
    if not _running():
        raise SpotifyUiError("Spotify no está abierto.")
    window = _Window(guard=True, app=SPOTIFY)
    try:
        window._wait_for_tree()
        repeat_targets = (
            "activar repetir", "desactivar repetir", "repetir una", "repetir", "repeat"
        )
        for ct in (50002, UIA_BUTTON):
            for element, name, _ in window._all(ct):
                low = (name or "").strip().lower()
                if any(t in low for t in repeat_targets):
                    window._invoke(element)
                    return True
        raise SpotifyUiError("No encuentro el botón de Repetir en la app de Spotify.")
    finally:
        window.close()


def cycle_repeat() -> bool:
    """Cycles repeat mode in Spotify desktop without taking window focus."""
    return ui_worker.call(_cycle_repeat, timeout=15)

