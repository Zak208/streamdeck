"""Starts a Spotify playlist, album or track by pressing its play button in the Spotify desktop window.

Spotify's Web API only plays music for Premium accounts, and a free account (or none connected) was left
with a button that just opened the list. The desktop app lets anyone press play, so StreamDesk does what
the user does: opens the link in the app, waits for that page, and presses its big play button through
Windows UI Automation. It uses neither the account nor any Spotify server, and, like the Discord
soundboard, it marks the window "cannot be activated" while it acts so the focus stays where it was.

Limits: the Spotify desktop app must be open and visible (not minimized), and its labels are read in
Spanish ("Reproducir"). Free accounts play a playlist in shuffle, as the app does by itself.
"""

import os
import time
from typing import Any, Optional, Tuple

import psutil

from server.discord_ui import AppSpec, DiscordUiError, Rect, _Window, _find_window, ui_worker

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
