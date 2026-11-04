"""Pressing play in the Spotify desktop window, against a fake window.

Windows UI Automation cannot run here, so a fake window stands in: it has a library sidebar (play buttons
on every entry), a main view per page with a big play button and small ones on every track, and a bottom
player. The real window was checked by hand (see the commit message), not by these tests.
"""

import unittest
from unittest import mock

import support  # noqa: F401  (paths and a throwaway data directory)
from server import discord_ui, spotify_ui
from server.spotify_ui import SpotifyUiError

VIEW = (-2163, 58, -1677, 1312)


class Page:
    def __init__(self, title, header_name, header_rect=(-2148, 242, -2103, 287), extra=()):
        self.title, self.header_name, self.header_rect, self.extra = title, header_name, header_rect, list(extra)


PAGES = {
    "spotify:playlist:A": Page("Mi lista - playlist by Zak | Spotify", "Reproducir Mi lista"),
    "spotify:playlist:B": Page("Today’s Top Hits | Spotify Playlist", "Reproducir Today’s Top Hits", (-2148, 629, -2103, 674)),
    "spotify:playlist:PLAYING": Page("Sonando - playlist by Zak | Spotify", "Pausar Sonando"),
    "spotify:playlist:ODD": Page("Otra - playlist by Zak | Spotify", "Reproducir Distinta"),  # button of another page
}


class FakeWindow:
    """Behaves like the Window of discord_ui for one Spotify session. `state` is shared so a test can steer it."""
    state = {}

    def __init__(self, guard=False, app=None):
        self.state["guards"] = self.state.get("guards", 0) + (1 if guard else 0)
        self.state["closed"] = False
        if self.state.get("minimized"):
            raise SpotifyUiError("Spotify está minimizado.")

    def _all(self, control_type):
        page = self.state["page"]
        if page is None:
            return []
        if control_type == spotify_ui.UIA_GROUP:
            return [(object(), page.title, VIEW), (object(), "", (-2553, 58, -2169, 1312))]
        buttons = [
            (self._button("Reproducir Mi lista sidebar"), "Reproducir Mi lista sidebar", (-2539, 260, -2494, 304)),  # library entry, same size
            (self._button("Reproducir"), "Reproducir", (-1935, 1326, -1905, 1356)),                               # bottom player
            (self._button("track"), "Reproducir Una canción de Alguien", (-2131, 401, -2116, 417)),               # a track row
            (self._button(page.header_name), page.header_name, page.header_rect),
        ] + [(self._button(n), n, r) for n, r in page.extra]
        return [item for item in buttons] if control_type == spotify_ui.UIA_BUTTON else []

    def _button(self, label):
        return FakeButton(label)

    def _invoke(self, element):
        self.state.setdefault("pressed", []).append(element.label)

    def _wait_for_tree(self):
        pass

    def close(self):
        self.state["closed"] = True


class FakeButton:
    def __init__(self, label):
        self.label = label


def patched(state):
    FakeWindow.state = state
    return (mock.patch.object(spotify_ui, "_Window", FakeWindow), mock.patch.object(spotify_ui.time, "sleep", lambda _s: None),
            mock.patch.object(spotify_ui, "_running", lambda: state.get("running", True)))


class PagePressTests(unittest.TestCase):
    def run_play(self, uri, state, clock=None):
        opened = []

        def startfile(target):
            opened.append(target)
            if target in PAGES:
                state["page"] = PAGES[target]  # Spotify navigates there

        a, b, c = patched(state)
        extra = [mock.patch.object(spotify_ui.os, "startfile", startfile, create=True)]
        if clock is not None:
            extra.append(mock.patch.object(spotify_ui.time, "time", lambda: next(clock)))
        with a, b, c, extra[0]:
            if len(extra) > 1:
                with extra[1]:
                    spotify_ui._play(uri)
            else:
                spotify_ui._play(uri)
        return opened

    def test_opens_the_link_then_presses_the_pages_own_big_button(self):
        state = {"page": PAGES["spotify:playlist:A"]}
        opened = self.run_play("spotify:playlist:B", state)
        self.assertEqual(opened, ["spotify:playlist:B"])
        self.assertEqual(state["pressed"], ["Reproducir Today’s Top Hits"])  # not the sidebar, the player or a track row
        self.assertTrue(state["closed"])
        self.assertEqual(state["guards"], 1)  # the focus guard was on

    def test_a_page_already_showing_is_pressed_after_a_short_wait(self):
        state = {"page": PAGES["spotify:playlist:A"]}
        clock = iter(x * 0.5 for x in range(1000))
        self.run_play("spotify:playlist:A", state, clock)
        self.assertEqual(state["pressed"], ["Reproducir Mi lista"])

    def test_a_page_that_is_already_playing_is_not_paused_by_pressing_it(self):
        state = {"page": PAGES["spotify:playlist:A"]}
        clock = iter(x * 0.5 for x in range(1000))
        self.run_play("spotify:playlist:PLAYING", state, clock)
        self.assertNotIn("pressed", state)
        self.assertTrue(state["closed"])

    def test_a_button_of_another_page_is_never_pressed(self):
        state = {"page": PAGES["spotify:playlist:A"]}
        clock = iter(x * 0.5 for x in range(1000))
        with self.assertRaises(SpotifyUiError) as caught:
            self.run_play("spotify:playlist:ODD", state, clock)
        self.assertIn("botón de reproducir", str(caught.exception))
        self.assertNotIn("pressed", state)
        self.assertTrue(state["closed"])  # the focus guard is released even when it fails

    def test_a_page_that_never_loads_gives_up_with_a_reason(self):
        state = {"page": None}
        clock = iter(x * 0.5 for x in range(1000))
        with self.assertRaises(SpotifyUiError):
            self.run_play("spotify:playlist:UNKNOWN", state, clock)
        self.assertTrue(state["closed"])

    def test_a_minimized_spotify_is_a_reason_not_a_restore(self):
        state = {"page": PAGES["spotify:playlist:A"], "minimized": True}
        with self.assertRaises(SpotifyUiError) as caught:
            self.run_play("spotify:playlist:A", state)
        self.assertIn("minimizado", str(caught.exception))

    def test_a_closed_spotify_is_launched_on_that_page_then_pressed(self):
        state = {"page": None, "running": False}
        opened = []

        def startfile(target):
            opened.append(target)
            state["page"] = PAGES[target]

        a, b, c = patched(state)
        with a, b, c, mock.patch.object(spotify_ui.os, "startfile", startfile, create=True), \
                mock.patch.object(spotify_ui, "_find_window", return_value=1):
            spotify_ui._play("spotify:playlist:A")
        self.assertEqual(opened, ["spotify:playlist:A"])
        self.assertEqual(state["pressed"], ["Reproducir Mi lista"])

    def test_a_spotify_that_never_opens_gives_up(self):
        state = {"page": None, "running": False}
        clock = iter(x * 3.0 for x in range(1000))
        a, b, c = patched(state)
        with a, b, c, mock.patch.object(spotify_ui.os, "startfile", lambda _t: None, create=True), \
                mock.patch.object(spotify_ui, "_find_window", side_effect=SpotifyUiError("no")), \
                mock.patch.object(spotify_ui.time, "time", lambda: next(clock)):
            with self.assertRaises(SpotifyUiError) as caught:
                spotify_ui._play("spotify:playlist:A")
        self.assertIn("no llegó a abrirse", str(caught.exception))


class PageReadingTests(unittest.TestCase):
    def test_the_page_title_comes_from_the_main_view_not_from_the_song_playing(self):
        # While a song plays the window and document titles become its name; the main view keeps the page title.
        state = {"page": PAGES["spotify:playlist:B"]}
        FakeWindow.state = state
        title, view = spotify_ui._page(FakeWindow())
        self.assertEqual((title, view), ("Today’s Top Hits | Spotify Playlist", VIEW))

    def test_no_page_yet(self):
        FakeWindow.state = {"page": None}
        self.assertEqual(spotify_ui._page(FakeWindow()), ("", None))


class ConnectorStatusTests(unittest.TestCase):
    def test_without_an_account_the_card_says_what_the_button_does(self):
        from server.connectors import spotify
        from server.settings_store import settings
        settings.clear("spotify")
        self.assertIn("pulsan Reproducir", spotify.status()["detail"])
        settings.update("spotify", {"client_id": "a" * 32})
        self.addCleanup(lambda: settings.clear("spotify"))
        self.assertIn("pulsan Reproducir", spotify.status()["detail"])


if __name__ == "__main__":
    unittest.main()
