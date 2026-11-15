"""Every action offered in Studio's library: valid, with its icon, and able to run without crashing.

The built-in actions live in the browser code, so a small Node script lifts them out of studio.js and
studio-library.js exactly as they are written there. The ones from connectors come from their modules.
Anything that would touch the PC (keys, programs, sound, OBS, Spotify, Discord, Windows) is replaced
by a recorder, so this checks the plumbing and the validation, not what each program does.
"""

import json
import os
import re
import shutil
import subprocess
import unittest
from contextlib import ExitStack
from unittest import mock

import support  # noqa: F401  (paths and a throwaway data directory)
from server import actions, discord_ui, main
from server.action_catalog import validate_action
from server.connectors import REGISTRY
from server.paths import STATIC_DIR

NODE = shutil.which("node")

EXTRACT = r"""
const fs = require("fs"), vm = require("vm");
const read = (name) => fs.readFileSync(process.argv[1] + "/js/" + name, "utf8");
const studio = read("studio.js"), library = read("studio-library.js");
const grab = (source, pattern) => { const m = pattern.exec(source); if (!m) throw new Error("not found: " + pattern); return m[0]; };
const code = [
  grab(studio, /const MEDIA_PRESETS = \[[\s\S]*?\r?\n\];/),
  grab(studio, /const TELEMETRY_PRESETS = \[[\s\S]*?\r?\n\];/),
  grab(library, /const LIBRARY_ACCENT = [^\r\n]*;/),
  grab(library, /function appKey\([\s\S]*?\r?\n\}\r?\n/),
  grab(library, /function builtInLibrary\(\) \{[\s\S]*?\r?\n\}\r?\n/),
  "JSON.stringify(builtInLibrary())",
].join("\n");
console.log(vm.runInNewContext(code, {}));
"""


def builtin_library():
    result = subprocess.run([NODE, "-e", EXTRACT, STATIC_DIR], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def connector_items():
    """What loadLibrary() builds from /api/connectors/catalog: only connectors that have ready-made actions."""
    categories = []
    for module in REGISTRY.values():
        offered = module.actions()
        if offered:
            categories.append({"category": module.INFO["name"], "items": [
                {"id": f"{module.INFO['id']}_{a['id']}", "label": a["label"], "sub": a["sublabel"], "icon": a["icon"],
                 "color": a["color"], "action_type": a["action_type"], "target": a["target"], "extra": a.get("extra")}
                for a in offered]})
    return categories


@unittest.skipUnless(NODE, "needs Node to read the browser code")
class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.categories = builtin_library() + connector_items()
        cls.items = [(cat["category"], item) for cat in cls.categories for item in cat["items"]]

    def test_the_library_is_not_empty_and_has_the_expected_groups(self):
        names = {cat["category"] for cat in self.categories}
        self.assertTrue({"Sistema", "Páginas", "Multimedia", "Monitores del PC", "Aplicaciones", "Windows", "OBS Studio", "Discord"} <= names, names)
        self.assertGreater(len(self.items), 25)

    def test_every_item_is_valid_for_the_server(self):
        for category, item in self.items:
            with self.subTest(item=f"{category}/{item['id']}"):
                action = validate_action(item["action_type"], item["target"], item.get("extra"))
                self.assertEqual(action["action_type"], item["action_type"])

    def test_every_icon_exists_and_labels_fit_a_key(self):
        for category, item in self.items:
            with self.subTest(item=f"{category}/{item['id']}"):
                self.assertTrue(item["icon"].startswith("/static/icons/"), item["icon"])
                self.assertTrue(os.path.exists(os.path.join(STATIC_DIR, item["icon"][len("/static/"):])), item["icon"])
                self.assertTrue(re.fullmatch(r"#[0-9a-fA-F]{6}", item["color"]), item["color"])
                self.assertLessEqual(len(item["label"]), 32)   # the key's title is cut to 32 characters
                self.assertLessEqual(len(item.get("sub") or ""), 36)

    def test_ids_are_unique(self):
        ids = [item["id"] for _, item in self.items]
        self.assertEqual(len(ids), len(set(ids)), sorted({i for i in ids if ids.count(i) > 1}))

    def test_every_item_runs_without_crashing_and_says_how_it_went(self):
        recorder = mock.Mock(return_value=True)
        with ExitStack() as stack:
            for name in ("send_hotkey", "send_vk_key", "type_text", "launch_smart_app"):
                stack.enter_context(mock.patch.object(actions, name, recorder))
            stack.enter_context(mock.patch.object(actions.webbrowser, "open", recorder))
            stack.enter_context(mock.patch.object(actions.os, "startfile", recorder, create=True))
            stack.enter_context(mock.patch.object(actions.os.path, "isdir", return_value=True))
            stack.enter_context(mock.patch.object(actions.shell_actions, "run", return_value={"success": True}))
            stack.enter_context(mock.patch.object(actions.webhooks, "run", return_value={"success": True}))
            stack.enter_context(mock.patch.object(actions.winsound, "Beep", recorder))
            stack.enter_context(mock.patch.object(actions.winsound, "MessageBeep", recorder))
            stack.enter_context(mock.patch.object(actions.windows, "execute", return_value={"success": True}))
            stack.enter_context(mock.patch.object(actions.spotify, "play", return_value={"success": True}))
            stack.enter_context(mock.patch.object(actions.spotify, "toggle_like", return_value={"success": True}))
            stack.enter_context(mock.patch.object(actions.spotify, "toggle_shuffle", return_value={"success": True}))
            stack.enter_context(mock.patch.object(actions.spotify, "cycle_repeat", return_value={"success": True}))
            stack.enter_context(mock.patch.object(discord_ui, "play"))
            stack.enter_context(mock.patch.object(discord_ui, "toggle_voice", return_value=True))
            stack.enter_context(mock.patch("server.obs_client.obs_client.execute_obs_action", return_value={"success": True}))
            for category, item in self.items:
                with self.subTest(item=f"{category}/{item['id']}"):
                    result = actions.execute_action(item["action_type"], item["target"], item.get("extra"))  # also runs macros
                    if item["action_type"] in ("page", "counter", "timer"):
                        # these need the live phone connection (and the key they belong to): the server answers them before the executor
                        self.assertIs(result["success"], False)
                        continue
                    self.assertIs(result["success"], True, result)

    def test_the_same_items_work_as_steps_of_a_macro(self):
        steps = [{"action_type": item["action_type"], "target": item["target"], "extra": item.get("extra") or {}, "delay_ms": 0}
                 for _, item in self.items if item["action_type"] not in ("multi", "page", "counter", "timer")]
        for start in range(0, len(steps), 8):
            with self.subTest(first=start):
                validate_action("multi", "macro", {"actions": steps[start:start + 8]})

    def test_placeholders_that_need_a_choice_are_harmless_until_it_is_made(self):
        # "Abrir una aplicación", the Spotify picker and the Discord sound only open a tab: placed alone they must not do harm.
        for category, item in self.items:
            if item.get("opensTab"):
                with self.subTest(item=item["id"]):
                    self.assertEqual((item["action_type"], item["target"]), ("sound", "beep"))


class LaunchTests(unittest.TestCase):
    """OBS refuses to open ("no encuentra en-US") when it is started from a folder that is not its own."""

    def launch(self, app_id, path):
        detected = [{"id": app_id, "path": path}]
        with mock.patch.object(actions.system_scanner, "get_detected_apps", return_value=detected), \
                mock.patch.object(actions, "_find_running_app_window", return_value=0), \
                mock.patch.object(actions.os, "startfile", create=True) as startfile:
            self.assertTrue(actions.launch_smart_app(app_id))
        return startfile

    def test_a_program_is_started_in_its_own_folder(self):
        path = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
        self.launch("obs", path).assert_called_once_with(path, cwd=r"C:\Program Files\obs-studio\bin\64bit")

    def test_windows_tools_without_a_folder_are_started_by_name(self):
        for app_id, exe in (("calc", "calc.exe"), ("notepad", "notepad.exe"), ("taskmgr", "taskmgr.exe")):
            with self.subTest(app=app_id):
                self.launch(app_id, exe).assert_called_once_with(exe)

    def test_discord_keeps_its_own_updater_launch(self):
        updater = r"C:\Users\x\AppData\Local\Discord\Update.exe"
        detected = [{"id": "discord", "path": updater + " --processStart Discord.exe"}]
        with mock.patch.object(actions.system_scanner, "get_detected_apps", return_value=detected), \
                mock.patch.object(actions, "_find_running_app_window", return_value=0), \
                mock.patch("subprocess.Popen") as popen:
            self.assertTrue(actions.launch_smart_app("discord"))
        self.assertEqual(popen.call_args.args[0], [updater, "--processStart", "Discord.exe"])

    def test_running_app_is_brought_to_front_instead_of_launched(self):
        detected = [{"id": "discord", "path": r"C:\path\to\Discord.exe"}]
        with mock.patch.object(actions.system_scanner, "get_detected_apps", return_value=detected), \
                mock.patch.object(actions, "_find_running_app_window", return_value=12345), \
                mock.patch.object(actions, "bring_window_to_front", return_value=True) as mock_bring, \
                mock.patch("subprocess.Popen") as popen:
            self.assertTrue(actions.launch_smart_app("discord"))
            mock_bring.assert_called_once_with(12345)
            popen.assert_not_called()


class PageJumpTests(unittest.TestCase):
    """The page actions are answered by the server, not by the executor."""

    def test_next_previous_first_and_a_given_page(self):
        import asyncio
        pages = [{"id": "a"}, {"id": "b"}, {"id": "c"}]

        class Config:
            config = {"pages": pages, "current_page": 1}
            opened = []

            def get_config(self):
                return self.config

            def set_active_page(self, index):
                self.config["current_page"] = index
                self.opened.append(index)
                return True

        async def broadcast(_message):
            pass

        fake = Config()
        with mock.patch.object(main, "config_manager", fake), mock.patch.object(main.ws_manager, "broadcast", broadcast):
            for target, expected in (("next", 2), ("next", 0), ("prev", 2), ("first", 0), ("b", 1)):
                with self.subTest(target=target):
                    result = asyncio.run(main.navigate_pages(target))
                    self.assertIs(result["success"], True)
                    self.assertEqual(fake.config["current_page"], expected)
            self.assertIs(asyncio.run(main.navigate_pages("nope"))["success"], False)


class SoundSecurityTests(unittest.TestCase):
    def test_play_sound_rejects_quotes(self):
        with mock.patch("winsound.PlaySound") as mock_play, \
                mock.patch("ctypes.windll.winmm.mciSendStringW") as mock_mci:
            actions.play_local_sound('test"file.mp3')
            mock_play.assert_not_called()
            mock_mci.assert_not_called()

    def test_play_sound_rejects_dot_dot(self):
        with mock.patch("winsound.PlaySound") as mock_play, \
                mock.patch("ctypes.windll.winmm.mciSendStringW") as mock_mci:
            actions.play_local_sound('../../windows/system32/cmd.exe')
            mock_play.assert_not_called()
            mock_mci.assert_not_called()

    def test_play_sound_rejects_absolute_path(self):
        with mock.patch("winsound.PlaySound") as mock_play, \
                mock.patch("ctypes.windll.winmm.mciSendStringW") as mock_mci:
            actions.play_local_sound(r'C:\Windows\Media\tada.wav')
            mock_play.assert_not_called()
            mock_mci.assert_not_called()

    def test_play_sound_closes_previous_mci(self):
        from server.paths import CONFIG_DIR
        sound_dir = os.path.join(CONFIG_DIR, "sounds")
        os.makedirs(sound_dir, exist_ok=True)
        dummy_mp3 = os.path.join(sound_dir, "test_mci.mp3")
        try:
            with open(dummy_mp3, "wb") as f:
                f.write(b"ID3dummy")
            calls = []
            def fake_mci(cmd, _, __, ___):
                calls.append(cmd)
                return 0
            with mock.patch("ctypes.windll.winmm.mciSendStringW", side_effect=fake_mci):
                actions.play_local_sound("test_mci.mp3")
                actions.play_local_sound("test_mci.mp3")
            closes = [c for c in calls if c.startswith("close sd_snd_")]
            self.assertGreaterEqual(len(closes), 2)
        finally:
            if os.path.exists(dummy_mp3):
                os.remove(dummy_mp3)


if __name__ == "__main__":
    unittest.main()
