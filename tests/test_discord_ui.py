"""The Discord soundboard read from, and pressed in, Discord's own window.

Windows UI Automation cannot run here, so a fake panel stands in for it: it scrolls a list of
sections like Discord's, shows only the rows in view, and records the buttons that get pressed.
The real window was checked by hand (see the commit message), not by these tests.
"""

import json
import unittest
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest import mock

import support
from server import action_catalog, actions, discord_ui
from server.connectors import discord
from server.discord_ui import DiscordUiError

ROW = 40
VIEWPORT = 5  # rows on screen at once


class FakeButton:
    def __init__(self, label, row):
        self.label, self.row = label, row


class FakePanel(discord_ui._Panel):
    """Same logic as the real panel, over an in-memory list. `content` is [(section, [labels])]."""
    pressed = []
    content = []
    tabs = []

    def __init__(self):  # no window, no UI Automation
        self.UIA = SimpleNamespace(ScrollAmount_NoAmount=0, ScrollAmount_LargeIncrement=1, ScrollAmount_SmallIncrement=2)
        self.rows = []  # ("H", name) or ("S", label)
        for section, labels in self.content:
            self.rows.append(("H", section))
            self.rows.extend(("S", label) for label in labels)
        self.offset = 0
        self.scroll = SimpleNamespace(CurrentVerticalScrollPercent=0.0, Scroll=self._scroll)
        self._sync()

    def _max_offset(self):
        return max(0, len(self.rows) - VIEWPORT)

    def _sync(self):
        self.scroll.CurrentVerticalScrollPercent = 100.0 if self._max_offset() == 0 else 100.0 * self.offset / self._max_offset()

    def _scroll(self, horizontal, vertical):
        self.offset = min(self._max_offset(), self.offset + VIEWPORT - 1)  # one page, keeping one row of overlap
        self._sync()

    def rail(self):
        return [(name, name) for name in self.tabs]

    def _invoke(self, element):
        if isinstance(element, FakeButton):
            type(self).pressed.append((element.label, element.row))
            return
        # a tab: its header goes to the top of the list, or as near as the end of the list allows
        index = next(i for i, row in enumerate(self.rows) if row == ("H", element))
        self.offset = min(self._max_offset(), index)
        self._sync()

    def view(self):
        headers, sounds = [], []
        for i in range(self.offset, min(len(self.rows), self.offset + VIEWPORT)):
            kind, text = self.rows[i]
            (headers if kind == "H" else sounds).append((i * ROW, text) if kind == "H" else (i * ROW, text, FakeButton(text, i)))
        return headers, sounds


ALIASES = ["Sonidos más usados en Casa", "Favoritos", "Usados frecuentemente"]
CONTENT = [
    ("Casa", ["🚪 Puerta", "bonk", "Ohana", "🌺 Aloha", "Stitchs", "Sida", "defuse"]),  # longer than the viewport
    ("Sonidos de Discord", ["🦆 quack", "🔊 airhorn"]),
    ("Servidor B", ["Error", "bonk", "Aplausos", "Metal pipe"]),                               # "bonk" also exists in Casa
    ("Servidor C", ["Viva rusia", "Metal pipe"]),                                           # last: cannot reach the top, so the
                                                                                            # screen still shows Servidor B's "Metal pipe"
]


def with_panel(content=CONTENT, tabs=None):
    FakePanel.content = content
    FakePanel.tabs = tabs if tabs is not None else ALIASES + [section for section, _ in content]
    FakePanel.pressed = []
    return mock.patch.object(discord_ui, "_Panel", FakePanel), mock.patch.object(discord_ui.time, "sleep", lambda _s: None)


class ScanTests(unittest.TestCase):
    def scan(self, **kwargs):
        a, b = with_panel(**kwargs)
        with a, b:
            return discord_ui._scan()

    def test_every_sound_of_every_server_is_found_once(self):
        found = self.scan()
        by_section = {}
        for sound in found:
            by_section.setdefault(sound["section"], []).append(sound["label"])
        self.assertEqual(by_section["Casa"], ["🚪 Puerta", "bonk", "Ohana", "🌺 Aloha", "Stitchs", "Sida", "defuse"])
        self.assertEqual(by_section["Sonidos de Discord"], ["🦆 quack", "🔊 airhorn"])
        self.assertEqual(by_section["Servidor B"], ["Error", "bonk", "Aplausos", "Metal pipe"])
        self.assertEqual(by_section["Servidor C"], ["Viva rusia", "Metal pipe"])  # a short section at the very end
        self.assertEqual(len(found), 15)

    def test_favourites_and_frequent_are_not_servers(self):
        sections = {sound["section"] for sound in self.scan()}
        self.assertFalse(sections & set(ALIASES))

    def test_the_voice_channels_server_is_marked_as_current(self):
        found = self.scan()
        self.assertEqual({s["section"] for s in found if s["current"]}, {"Casa"})

    def test_a_name_repeated_inside_a_server_is_listed_once(self):
        found = self.scan(content=[("Casa", ["bonk", "bonk", "Ohana"])])
        self.assertEqual([s["label"] for s in found], ["bonk", "Ohana"])

    def test_nothing_to_list_is_explained(self):
        with self.assertRaises(DiscordUiError):
            self.scan(content=[("Casa", [])])


class PlayTests(unittest.TestCase):
    def press(self, section, label):
        a, b = with_panel()
        with a, b:
            discord_ui._play(section, label)
        return [label for label, _row in FakePanel.pressed]

    def test_presses_the_named_sound(self):
        self.assertEqual(self.press("Sonidos de Discord", "🦆 quack"), ["🦆 quack"])

    def test_equal_names_are_pressed_in_the_server_asked_for(self):
        for section, wanted in (("Casa", "bonk"), ("Servidor B", "bonk"), ("Servidor B", "Metal pipe"), ("Servidor C", "Metal pipe")):
            with self.subTest(section=section, sound=wanted):
                a, b = with_panel()
                with a, b:
                    discord_ui._play(section, wanted)
                (label, row), = FakePanel.pressed
                owner = next(name for name, _ in reversed(CONTENT) if self._header_row(name) <= row)
                self.assertEqual((label, owner), (wanted, section))

    @staticmethod
    def _header_row(section):
        row = 0
        for name, labels in CONTENT:
            if name == section:
                return row
            row += 1 + len(labels)

    def test_labels_are_compared_ignoring_stray_spaces(self):
        self.assertEqual(self.press("Casa", "  Ohana "), ["Ohana"])

    def test_the_last_server_can_be_reached(self):
        self.assertEqual(self.press("Servidor C", "Metal pipe"), ["Metal pipe"])

    def test_a_missing_sound_or_server_says_which(self):
        with self.assertRaises(DiscordUiError) as sound:
            self.press("Casa", "no existe")
        self.assertIn("no existe", str(sound.exception))
        with self.assertRaises(DiscordUiError) as server:
            self.press("Otro servidor", "bonk")
        self.assertIn("Otro servidor", str(server.exception))


class HelperTests(unittest.TestCase):
    def test_labels_split_into_emoji_and_name(self):
        for label, expected in (("🚪 Tocar Puerta", ("🚪", "Tocar Puerta")), ("bonk", ("", "bonk")),
                                ("5 min con ella", ("", "5 min con ella")), ("¿Qué mirás, bobo?", ("", "¿Qué mirás, bobo?")),
                                ("⚠️ Decime que tenes puertos", ("⚠️", "Decime que tenes puertos"))):
            with self.subTest(label=label):
                self.assertEqual(discord_ui.split_label(label), expected)

    def test_no_discord_is_a_readable_failure(self):
        with mock.patch.object(discord_ui.psutil, "process_iter", return_value=[]):
            with self.assertRaises(DiscordUiError) as caught:
                discord_ui._find_window()
        self.assertIn("no está abierto", str(caught.exception))


class ActionAndConnectorTests(unittest.TestCase):
    def test_the_action_keeps_the_sound_and_its_server(self):
        action = action_catalog.validate_action("discord_sound", "🚪 Tocar Puerta", {"section": "Servidor A", "junk": 1})
        self.assertEqual(action, {"action_type": "discord_sound", "target": "🚪 Tocar Puerta", "extra": {"section": "Servidor A"}})

    def test_incomplete_or_unsafe_actions_are_refused(self):
        for target, extra in (("", {"section": "A"}), ("bonk", {}), ("bonk", {"section": ""}), ("<b>", {"section": "A"}),
                              ("x" * 81, {"section": "A"}), ("bonk", {"section": "<i>"})):
            with self.subTest(target=target, extra=extra), self.assertRaises(ValueError):
                action_catalog.validate_action("discord_sound", target, extra)

    def test_it_can_be_a_macro_step(self):
        step = {"action_type": "discord_sound", "target": "bonk", "extra": {"section": "Casa"}}
        macro = action_catalog.validate_action("multi", "m", {"actions": [step]})
        self.assertEqual(macro["extra"]["actions"][0]["extra"], {"section": "Casa"})

    def test_pressing_the_button_plays_through_the_panel(self):
        with mock.patch.object(discord_ui, "play") as play:
            result = actions.execute_action("discord_sound", "bonk", {"section": "Casa"})
        play.assert_called_once_with("Casa", "bonk")
        self.assertIs(result["success"], True)

    def test_a_failure_reaches_the_button_as_a_reason(self):
        with mock.patch.object(discord_ui, "play", side_effect=DiscordUiError("Discord está minimizado.")):
            result = actions.execute_action("discord_sound", "bonk", {"section": "Casa"})
        self.assertEqual((result["success"], result["error"]), (False, "Discord está minimizado."))

    def test_sounds_come_with_emoji_and_name_separated(self):
        listed = [{"section": "Casa", "label": "🚪 Puerta", "current": True}, {"section": "Casa", "label": "bonk", "current": True}]
        with mock.patch.object(discord_ui, "list_sounds", return_value=listed):
            options = discord.options("sounds")
        self.assertEqual([(o["emoji"], o["name"], o["label"]) for o in options], [("🚪", "Puerta", "🚪 Puerta"), ("", "bonk", "bonk")])

    def test_a_reading_failure_becomes_a_reason(self):
        with mock.patch.object(discord_ui, "list_sounds", side_effect=DiscordUiError("No veo el panel de sonidos.")):
            with self.assertRaises(RuntimeError) as caught:
                discord.options("sounds")
        self.assertIn("panel de sonidos", str(caught.exception))
        with mock.patch.object(discord_ui, "list_sounds", side_effect=OSError("boom")):
            with self.assertRaises(RuntimeError):
                discord.options("sounds")


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def get(self, path):
        try:
            with urllib.request.urlopen(self.live.base_url + path, timeout=15) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def test_studio_can_list_sounds_through_the_connector_endpoint(self):
        with mock.patch.object(discord_ui, "list_sounds", return_value=[{"section": "Casa", "label": "bonk", "current": False}]):
            status, body = self.get("/api/connectors/discord/options/sounds")
        self.assertEqual(status, 200)
        self.assertEqual(body["options"][0]["name"], "bonk")

    def test_the_reason_reaches_studio_when_discord_cannot_be_read(self):
        with mock.patch.object(discord_ui, "list_sounds", side_effect=DiscordUiError("Discord está minimizado.")):
            status, body = self.get("/api/connectors/discord/options/sounds")
        self.assertEqual((status, body["detail"]), (409, "Discord está minimizado."))


class FakeWindow:
    """Stands in for the Discord window: `buttons` and `links` are (name, rect) lists."""
    buttons, links = [], []

    def __init__(self):
        pass

    def _all(self, control_type):
        items = self.buttons if control_type == discord_ui.UIA_BUTTON else self.links
        return [(object(), name, rect) for name, rect in items]


VOICE_BAR = [("Detalles de voz Voz conectada", (-1215, 1227, -1026, 1247))]
FILLER = [(f"botón {i}", (0, 0, 10, 10)) for i in range(8)]


class VoiceServerTests(unittest.TestCase):
    def server(self, buttons, links):
        FakeWindow.buttons, FakeWindow.links = buttons, links
        with mock.patch.object(discord_ui, "_Window", FakeWindow):
            return discord_ui._voice_server()

    def test_the_link_names_channel_and_server(self):
        link = [("🌸・Luany 🦋 / Servidor A 02:20:32", (-1215, 1246, -1026, 1279))]
        self.assertEqual(self.server(FILLER + VOICE_BAR, link), "Servidor A")

    def test_parsing_the_link(self):
        for name, expected in (("Sala / Servidor A 02:20:32", "Servidor A"), ("Sala / Servidor A 0:05", "Servidor A"),
                               ("Sala 2 / Mi / otro servidor 12:00:01", "otro servidor"), ("Sala / Servidor A", "Servidor A"),
                               ("sin separador 01:02", None), ("", None)):
            with self.subTest(name=name):
                self.assertEqual(discord_ui.parse_voice_link(name), expected)

    def test_not_in_voice_is_none(self):
        self.assertIsNone(self.server(FILLER, [("Sala / Servidor A 02:20:32", (-1215, 1246, -1026, 1279))]))

    def test_a_link_that_is_not_under_the_voice_button_is_ignored(self):
        elsewhere = [("Otra / Cosa 01:00", (-500, 100, -300, 140))]
        self.assertIsNone(self.server(FILLER + VOICE_BAR, elsewhere))

    def test_a_tree_still_being_built_is_none(self):
        self.assertIsNone(self.server(VOICE_BAR, [("Sala / Servidor A 01:00", (-1215, 1246, -1026, 1279))]))

    def test_discord_closed_or_minimized_is_none(self):
        with mock.patch.object(discord_ui, "_Window", side_effect=DiscordUiError("minimizado")):
            self.assertIsNone(discord_ui._voice_server())


class FakeConfig:
    def __init__(self, pages):
        self.config = {"pages": pages, "current_page": 0}
        self.opened = []

    def get_config(self):
        return self.config

    def set_active_page(self, index):
        self.config["current_page"] = index
        self.opened.append(index)
        return True


class ServerPageLoopTests(unittest.TestCase):
    PAGES = [{"id": "main"}, {"id": "a", "auto_discord": "Servidor A"}, {"id": "b", "auto_discord": "servidor b "}]

    def run_loop(self, pages, servers, ticks=10, user_moves_back=False):
        import asyncio
        from server import main

        config = FakeConfig(pages)
        answers = iter(servers)
        looks = []
        count = [0]

        def look():
            looks.append(1)
            if user_moves_back:
                config.config["current_page"] = 0  # the user took the phone back to the first page between two looks
            return next(answers)

        async def sleep(_seconds):
            count[0] += 1
            if count[0] >= ticks:
                raise asyncio.CancelledError

        async def broadcast(_message):
            pass

        with mock.patch.object(main, "config_manager", config), mock.patch.object(main.ws_manager, "broadcast", broadcast), \
                mock.patch.object(main.discord_ui, "current_voice_server", look), mock.patch.object(main.asyncio, "sleep", sleep):
            try:
                asyncio.run(main.smart_page_loop())
            except asyncio.CancelledError:
                pass
        return config.opened, len(looks)

    def test_the_page_follows_the_server_you_join(self):
        opened, looks = self.run_loop(self.PAGES, ["Servidor A", "Servidor B", None, "Servidor A"])
        self.assertEqual(opened, [1, 2, 1])  # A, then B (names match ignoring case and stray spaces), then A again after leaving
        self.assertEqual(looks, 4)

    def test_staying_in_the_same_server_does_not_undo_a_manual_page_change(self):
        opened, _ = self.run_loop(self.PAGES, ["Servidor A", "Servidor A", "Servidor A"], user_moves_back=True)
        self.assertEqual(opened, [1])  # opened once; the later looks see the same server and leave the user's choice alone

    def test_a_server_without_a_page_changes_nothing(self):
        opened, _ = self.run_loop(self.PAGES, ["Servidor Z", None, "Servidor Z"])
        self.assertEqual(opened, [])

    def test_discord_is_not_looked_at_when_no_page_asks_for_it(self):
        opened, looks = self.run_loop([{"id": "main"}, {"id": "x", "auto_app": "obs64.exe"}], [])
        self.assertEqual((opened, looks), ([], 0))

    def test_page_for_discord_matching(self):
        from server import main
        self.assertEqual(main.page_for_discord(self.PAGES, "SERVIDOR a"), 1)
        self.assertIsNone(main.page_for_discord(self.PAGES, ""))
        self.assertIsNone(main.page_for_discord(self.PAGES, "otro"))


class ServerPageEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def setUp(self):
        import copy
        from server.config_manager import config_manager
        self.config_manager = config_manager
        self.original = copy.deepcopy(config_manager.get_config())
        self.addCleanup(lambda: config_manager.save_config(self.original))

    def post(self, path, payload):
        request = urllib.request.Request(self.live.base_url + path, data=json.dumps(payload).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def test_chosen_sounds_become_a_page_that_opens_by_itself(self):
        status, body = self.post("/api/discord/server-page", {"server": "Servidor A", "sounds": ["🚪 Puerta", "bonk"]})
        self.assertEqual((status, body["replaced"]), (200, False))
        page = self.config_manager.get_config()["pages"][body["index"]]
        self.assertEqual((page["name"], page["auto_discord"]), ("Servidor A", "Servidor A"))
        buttons = [s for s in page["slots"] if s["type"] == "button"]
        self.assertEqual([(b["label"], b["target"], b["extra"]) for b in buttons],
                         [("Puerta", "🚪 Puerta", {"section": "Servidor A"}), ("bonk", "bonk", {"section": "Servidor A"})])
        self.assertTrue(all(b["action_type"] == "discord_sound" and b["sublabel"] == "Servidor A" for b in buttons))

    def test_a_second_page_for_the_same_server_needs_a_yes_and_keeps_the_name(self):
        _, first = self.post("/api/discord/server-page", {"server": "Servidor A", "sounds": ["bonk"]})
        config = self.config_manager.get_config()
        config["pages"][first["index"]]["name"] = "Mis sonidos"
        self.config_manager.save_config(config)
        status, _ = self.post("/api/discord/server-page", {"server": "servidor a", "sounds": ["Ohana"]})
        self.assertEqual(status, 409)
        status, body = self.post("/api/discord/server-page", {"server": "Servidor A", "sounds": ["Ohana"], "replace": True})
        self.assertEqual((status, body["replaced"], body["index"]), (200, True, first["index"]))
        page = self.config_manager.get_config()["pages"][first["index"]]
        self.assertEqual((page["name"], page["slots"][0]["target"]), ("Mis sonidos", "Ohana"))

    def test_bad_requests_are_refused(self):
        for payload in ({"server": "", "sounds": ["bonk"]}, {"server": "A", "sounds": []}, {"server": "A", "sounds": ["x"] * 13},
                        {"server": "A", "sounds": [1]}, {"server": "A"}, {"server": "<b>", "sounds": ["bonk"]}):
            with self.subTest(payload=payload):
                self.assertEqual(self.post("/api/discord/server-page", payload)[0], 422)
        self.assertEqual(len(self.config_manager.get_config()["pages"]), len(self.original["pages"]))

    def test_twelve_sounds_fit_a_page(self):
        status, _ = self.post("/api/discord/server-page", {"server": "Grande", "sounds": [f"s{i}" for i in range(12)]})
        self.assertEqual(status, 200)

    def test_duplicating_such_a_page_does_not_copy_the_server(self):
        _, made = self.post("/api/discord/server-page", {"server": "Servidor A", "sounds": ["bonk"]})
        status, result = self.post("/api/deck/page/duplicate", {"page_index": made["index"]})
        pages = self.config_manager.get_config()["pages"]
        self.assertEqual(status, 200)
        self.assertNotIn("auto_discord", pages[result["index"]])
        self.assertEqual(pages[made["index"]]["auto_discord"], "Servidor A")

    def test_the_server_of_a_page_is_validated_with_the_profile(self):
        profile = json.loads(json.dumps(self.original))
        profile["pages"][0]["auto_discord"] = "Servidor A"
        self.assertEqual(action_catalog.validate_deck_config(profile)["pages"][0]["auto_discord"], "Servidor A")
        profile["pages"][0]["auto_discord"] = "<script>"
        with self.assertRaises(ValueError):
            action_catalog.validate_deck_config(profile)

    def test_studio_asks_which_server_you_are_in(self):
        with mock.patch.object(discord_ui, "current_voice_server", return_value="Servidor A"):
            self.assertEqual(discord.options("voice"), [{"server": "Servidor A"}])
        with mock.patch.object(discord_ui, "current_voice_server", return_value=None):
            self.assertEqual(discord.options("voice"), [])


if __name__ == "__main__":
    unittest.main()
