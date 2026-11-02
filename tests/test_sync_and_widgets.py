import asyncio
import json
import os
import re
import unittest
import urllib.request
from unittest import mock

import support
import websockets
from server import actions, main
from server.action_catalog import validate_action
from server.paths import STATIC_DIR


def read(path):
    with open(os.path.join(STATIC_DIR, path), encoding="utf-8") as handle:
        return handle.read()


def session(name, volume, muted=False, pid=1):
    return {"id": f"{name}_{pid}", "process_name": name, "display_name": name, "pid": pid, "volume": volume, "muted": muted}


class SessionMergeTests(unittest.TestCase):
    def test_a_program_with_several_audio_streams_appears_once(self):
        merged = main.merge_sessions([session("Discord.exe", 100, pid=1), session("discord.exe", 40, pid=2), session("Chrome.exe", 70)])
        self.assertEqual([m["process_name"].lower() for m in merged], ["discord.exe", "chrome.exe"])
        self.assertEqual(merged[0]["volume"], 100)

    def test_a_program_counts_as_muted_only_when_every_stream_is(self):
        self.assertFalse(main.merge_sessions([session("a.exe", 50, muted=True), session("a.exe", 50, muted=False)])[0]["muted"])
        self.assertTrue(main.merge_sessions([session("a.exe", 50, muted=True), session("A.exe", 50, muted=True)])[0]["muted"])

    def test_input_is_not_modified(self):
        original = [session("a.exe", 10), session("a.exe", 90)]
        main.merge_sessions(original)
        self.assertEqual([s["volume"] for s in original], [10, 90])


class PendingVolumeTests(unittest.TestCase):
    def setUp(self):
        main._pending_app_volumes.clear()

    def tearDown(self):
        main._pending_app_volumes.clear()

    def fake_controller(self, snapshots):
        controller = mock.Mock()
        controller.get_master_volume.return_value = {"volume": 50, "muted": False}
        controller.get_audio_sessions.side_effect = snapshots
        return controller

    def test_volume_set_for_a_silent_app_is_applied_when_it_starts_playing(self):
        main._pending_app_volumes["spotify.exe"] = 30
        silent = [session("Discord.exe", 100)]
        playing = [session("Discord.exe", 100), session("Spotify.exe", 100)]
        controller = self.fake_controller([silent, playing, [session("Spotify.exe", 30)]])
        with mock.patch.object(main, "audio_controller", controller), mock.patch.object(main.windows, "get_mic_muted", return_value=False):
            first = main.read_audio_state()
            controller.set_app_volume.assert_not_called()
            self.assertIn("spotify.exe", main._pending_app_volumes)
            second = main.read_audio_state()
        controller.set_app_volume.assert_called_once_with("spotify.exe", 30)
        self.assertEqual(main._pending_app_volumes, {})
        self.assertEqual(len(first["sessions"]), 1)
        self.assertEqual(second["sessions"][0]["volume"], 30)  # the state already reflects the applied volume

    def test_phone_moving_the_fader_of_a_silent_app_remembers_the_volume(self):
        controller = mock.Mock()
        controller.set_app_volume.return_value = {"success": False, "error": "no session"}
        controller.get_master_volume.return_value = {"volume": 50, "muted": False}
        controller.get_audio_sessions.return_value = []

        async def scenario(live):
            async with websockets.connect(f"ws://127.0.0.1:{live.port}/ws") as ws:
                await ws.recv()
                await ws.send(json.dumps({"type": "set_app_volume", "process": "Spotify.exe", "volume": 35}))
                for _ in range(50):
                    if main._pending_app_volumes:
                        return
                    await asyncio.sleep(0.05)

        with mock.patch.object(main, "audio_controller", controller), mock.patch.object(main.windows, "get_mic_muted", return_value=False), \
                support.LiveServer() as live:
            asyncio.run(scenario(live))
        self.assertEqual(main._pending_app_volumes, {"spotify.exe": 35})


class DiscordSoundTests(unittest.TestCase):
    def test_a_sound_button_keeps_its_shortcut_and_name(self):
        action = validate_action("discord_hotkey", "sound", {"hotkey": "control+alt+f1", "sound_name": "Aplausos", "junk": 1})
        self.assertEqual(action["extra"], {"hotkey": "CTRL+ALT+F1", "sound_name": "Aplausos"})

    def test_mute_buttons_do_not_gain_a_sound_name(self):
        action = validate_action("discord_hotkey", "mute", {"hotkey": "CTRL+ALT+F9", "sound_name": "x"})
        self.assertEqual(action["extra"], {"hotkey": "CTRL+ALT+F9"})

    def test_bad_sound_buttons_are_refused(self):
        for extra in ({"hotkey": "F1"}, {"hotkey": "CTRL+ALT+F1", "sound_name": "<b>x</b>"}, {"hotkey": "CTRL+ALT+F1", "sound_name": "x" * 60}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_action("discord_hotkey", "sound", extra)

    def test_the_shortcut_is_held_briefly_so_discord_notices_it(self):
        events = []
        user32 = mock.Mock()
        user32.keybd_event.side_effect = lambda vk, scan, flags, extra: events.append(("up" if flags else "down", vk))
        windll = mock.Mock(user32=user32)
        with mock.patch.object(actions.ctypes, "windll", windll), \
                mock.patch.object(actions.time, "sleep", side_effect=lambda seconds: events.append(("hold", seconds))):
            self.assertTrue(actions.send_hotkey("CTRL+ALT+F1"))
        names = [kind for kind, _ in events]
        self.assertEqual(names, ["down", "down", "down", "hold", "up", "up", "up"])
        self.assertGreaterEqual(events[3][1], 0.04)
        self.assertEqual([vk for kind, vk in events if kind == "down"], [vk for kind, vk in reversed([e for e in events if e[0] == "up"])])


class TestEndpoint(unittest.TestCase):
    def post(self, base, payload):
        request = urllib.request.Request(base + "/api/actions/test", data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode())

    def test_studio_can_try_a_button_but_only_with_allowed_actions(self):
        with support.LiveServer() as live:
            with mock.patch.object(main, "execute_action", return_value={"success": True}) as run:
                self.assertEqual(self.post(live.base_url, {"action_type": "discord_hotkey", "target": "sound",
                                                           "extra": {"hotkey": "CTRL+ALT+F1"}}), {"success": True, "error": ""})
            run.assert_called_once()
            refused = self.post(live.base_url, {"action_type": "shell", "target": "whoami"})
        self.assertFalse(refused["success"])
        self.assertTrue(refused["error"])


class PhoneAndStudioMarkupTests(unittest.TestCase):
    def test_master_faders_are_not_treated_as_app_faders(self):
        # Registering the master fader as an app fader painted the first app's volume over it.
        code = read("js/streamdeck.js")
        self.assertIn("if (!isMaster) targetAppMap[slider.id] = targetProcess;", code)
        self.assertIn("masterSliderIds.has(sliderId)", code)

    def test_system_monitors_render_a_big_number_and_a_bar(self):
        code, css = read("js/streamdeck.js"), read("css/style.css")
        for token in ("createMonitorElement", "deck-monitor-value", "deck-monitor-bar", 'dataset.level'):
            self.assertIn(token, code)
        self.assertIn(".deck-monitor-value", css)
        self.assertNotIn("% Uso", code)  # the old tiny caption

    def test_toggles_say_what_they_are_doing(self):
        code = read("js/streamdeck.js")
        for label in ("Grabando", "En directo", "Silenciado"):
            self.assertIn(label, code)

    def test_studio_follows_the_live_feed(self):
        code = read("js/studio.js")
        for token in ("connectStudioSocket", "paintStudioFaders", "paintStudioMonitors", "app_volume_updated"):
            self.assertIn(token, code)

    def test_soundboard_icon_exists_and_can_be_picked(self):
        self.assertTrue(os.path.exists(os.path.join(STATIC_DIR, "icons", "soundboard.svg")))
        self.assertIn('"soundboard"', read("js/studio.js"))

    def test_container_units_are_always_guarded(self):
        # Outside a container cqmin falls back to viewport units, which would make icons huge,
        # so every use must sit inside an @supports block that checks for them.
        for path in ("css/style.css", "css/studio.css"):
            css = read(path)
            for match in re.finditer(r"(?<![\d.])(?!1cqmin\))\d+(?:\.\d+)?cqmin", css):  # the @supports probe itself is "1cqmin)"
                headers, start = [], 0
                for position, char in enumerate(css[: match.start()]):
                    if char == "{":
                        headers.append(css[start:position])
                        start = position + 1
                    elif char in "};":
                        if char == "}" and headers:
                            headers.pop()
                        start = position + 1
                line = css.count(chr(10), 0, match.start()) + 1
                self.assertTrue(any("@supports (width: 1cqmin)" in header for header in headers), f"{path}:{line}")


if __name__ == "__main__":
    unittest.main()
