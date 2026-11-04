import asyncio
import copy
import ctypes
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import support
import websockets
from server import actions, main
from server.action_catalog import validate_action, validate_deck_config, validate_hotkey
from server.config_manager import DEFAULT_CONFIG
from server.connectors import windows
from server.paths import CONFIG_DIR, STATIC_DIR


def clean_profile():
    return validate_deck_config(copy.deepcopy(DEFAULT_CONFIG))


class HotkeyTests(unittest.TestCase):
    def test_general_hotkeys_can_be_a_single_key(self):
        self.assertEqual(validate_hotkey("f5", require_modifier=False), "F5")
        self.assertEqual(validate_hotkey("control + c", require_modifier=False), "CTRL+C")
        self.assertEqual(validate_action("hotkey", "ctrl+shift+esc")["target"], "CTRL+SHIFT+ESC")
        self.assertEqual(validate_action("hotkey", "printscreen")["target"], "PRINTSCREEN")

    def test_discord_shortcuts_still_need_a_modifier(self):
        with self.assertRaises(ValueError):
            validate_hotkey("M")
        with self.assertRaises(ValueError):
            validate_action("discord_hotkey", "mute", {"hotkey": "M"})

    def test_bad_hotkeys_are_refused(self):
        for bad in ("CTRL", "CTRL+SHIFT", "", "CTRL+CTRL+A", "A+B+C+D+E", "CTRL+;", "ctrl+alt+supr"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_action("hotkey", bad)

    def test_arrow_keys_are_sent_as_extended_keys(self):
        events = []
        user32 = mock.Mock()
        user32.keybd_event.side_effect = lambda vk, scan, flags, extra: events.append((vk, flags))
        with mock.patch.object(actions.ctypes, "windll", mock.Mock(user32=user32)), mock.patch.object(actions.time, "sleep"):
            self.assertTrue(actions.send_hotkey("ALT+LEFT", require_modifier=False))
        left = [flags for vk, flags in events if vk == actions.HOTKEY_VK["LEFT"]]
        self.assertTrue(all(flags & actions.KEYEVENTF_EXTENDEDKEY for flags in left))
        alt = [flags for vk, flags in events if vk == actions.HOTKEY_VK["ALT"]]
        self.assertFalse(any(flags & actions.KEYEVENTF_EXTENDEDKEY for flags in alt))


class TextActionTests(unittest.TestCase):
    def test_text_keeps_spaces_symbols_and_enter_flag(self):
        action = validate_action("text", "  a < b & c  ", {"press_enter": 1, "junk": True})
        self.assertEqual(action, {"action_type": "text", "target": "  a < b & c  ", "extra": {"press_enter": True}})

    def test_bad_text_is_refused(self):
        for bad in ("", "   ", "x" * 301, "hola\x00", "a\x1bb", None, 5):
            with self.subTest(bad=repr(bad)[:20]), self.assertRaises(ValueError):
                validate_action("text", bad)

    def test_newlines_and_tabs_are_allowed(self):
        self.assertEqual(validate_action("text", "línea 1\nlínea 2\tfin")["target"], "línea 1\nlínea 2\tfin")

    def test_struct_matches_the_windows_input_size(self):
        self.assertEqual(ctypes.sizeof(actions._Input), 40 if sys.maxsize > 2 ** 32 else 28)

    def test_characters_become_unicode_key_events(self):
        events = actions.text_to_inputs("aé")
        self.assertEqual(len(events), 4)  # down and up for each character
        scans = [e.union.ki.wScan for e in events]
        self.assertEqual(scans, [ord("a"), ord("a"), ord("é"), ord("é")])
        self.assertTrue(all(e.union.ki.dwFlags & actions.KEYEVENTF_UNICODE for e in events))
        self.assertTrue(events[1].union.ki.dwFlags & actions.KEYEVENTF_KEYUP)
        self.assertFalse(events[0].union.ki.dwFlags & actions.KEYEVENTF_KEYUP)

    def test_emoji_use_a_surrogate_pair(self):
        scans = [e.union.ki.wScan for e in actions.text_to_inputs("😀")]
        self.assertEqual(scans, [0xD83D, 0xD83D, 0xDE00, 0xDE00])

    def test_newline_is_the_enter_key_and_press_enter_adds_one(self):
        events = actions.text_to_inputs("a\n", press_enter=True)
        keys = [e.union.ki.wVk for e in events]
        self.assertEqual(keys, [0, 0, actions.VK_RETURN, actions.VK_RETURN, actions.VK_RETURN, actions.VK_RETURN])

    def test_typing_reports_whether_windows_accepted_every_key(self):
        windll = mock.Mock()
        windll.user32.SendInput.side_effect = lambda count, batch, size: count
        with mock.patch.object(actions.ctypes, "windll", windll):
            self.assertTrue(actions.type_text("hola", press_enter=True))
        windll.user32.SendInput.side_effect = lambda count, batch, size: 0
        with mock.patch.object(actions.ctypes, "windll", windll):
            self.assertFalse(actions.type_text("hola"))

    def test_text_button_runs_through_the_action_path(self):
        with mock.patch.object(actions, "type_text", return_value=True) as typed:
            result = actions.execute_action("text", "Hola <mundo>", {"press_enter": True})
        typed.assert_called_once_with("Hola <mundo>", True)
        self.assertTrue(result["success"])


class PageAndLockActionTests(unittest.TestCase):
    def test_page_targets(self):
        for target in ("next", "PREV", "first", "page_abc123"):
            with self.subTest(target=target):
                self.assertIn(validate_action("page", target)["target"], {"next", "prev", "first", "page_abc123"})
        for bad in ("", "a b", "../x", "page;x"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_action("page", bad)

    def test_macros_cannot_contain_page_jumps_or_other_macros(self):
        for child in ({"action_type": "page", "target": "next"},
                      {"action_type": "multi", "target": "x", "extra": {"actions": [{"action_type": "sound", "target": "beep"}]}}):
            with self.subTest(child=child["action_type"]), self.assertRaises(ValueError):
                validate_action("multi", "macro", {"actions": [child]})

    def test_macros_may_press_keys_and_type(self):
        macro = validate_action("multi", "macro", {"actions": [
            {"action_type": "hotkey", "target": "ctrl+c", "delay_ms": 100},
            {"action_type": "text", "target": "hola", "extra": {"press_enter": True}, "delay_ms": 0},
        ]})
        self.assertEqual([a["action_type"] for a in macro["extra"]["actions"]], ["hotkey", "text"])

    def test_a_failed_macro_step_is_reported_with_its_reason(self):
        steps = [{"action_type": "sound", "target": "beep", "extra": {}, "delay_ms": 0},
                 {"action_type": "sound", "target": "beep", "extra": {}, "delay_ms": 0}]
        outcomes = [{"success": True}, {"success": False, "error": "Enlace no permitido"}]
        with mock.patch.object(actions, "validate_action", return_value={"extra": {"actions": steps}}),              mock.patch.object(actions, "execute_single_action", side_effect=outcomes):
            result = actions.execute_action("multi", "m", {})
        self.assertFalse(result["success"])
        self.assertIn("paso 2 de 2", result["error"])
        self.assertIn("Enlace no permitido", result["error"])

    def test_a_page_button_cannot_run_outside_the_phone_connection(self):
        self.assertFalse(actions.execute_action("page", "next")["success"])

    def test_lock_pc_asks_windows_and_never_locks_during_tests(self):
        self.assertEqual(validate_action("windows", "lock_pc")["target"], "lock_pc")
        windll = mock.Mock()
        windll.user32.LockWorkStation.return_value = 1
        with mock.patch.object(windows.ctypes, "windll", windll):
            self.assertTrue(windows.execute("lock_pc", {})["success"])
        windll.user32.LockWorkStation.return_value = 0
        with mock.patch.object(windows.ctypes, "windll", windll):
            self.assertFalse(windows.execute("lock_pc", {})["success"])

    def test_pages_can_name_the_program_that_opens_them(self):
        profile = clean_profile()
        profile["pages"][1]["auto_app"] = "OBS64.exe"
        self.assertEqual(validate_deck_config(profile)["pages"][1]["auto_app"], "OBS64.exe")
        self.assertNotIn("auto_app", validate_deck_config(profile)["pages"][0])
        profile["pages"][1]["auto_app"] = "obs;calc"
        with self.assertRaises(ValueError):
            validate_deck_config(profile)

    def test_page_for_app_matching(self):
        pages = [{"id": "a"}, {"id": "b", "auto_app": "OBS64.exe"}, {"id": "c", "auto_app": "chrome.exe"}]
        self.assertEqual(main.page_for_app(pages, "obs64.exe"), 1)
        self.assertEqual(main.page_for_app(pages, "Chrome.EXE"), 2)
        self.assertIsNone(main.page_for_app(pages, "notepad.exe"))
        self.assertIsNone(main.page_for_app(pages, ""))


class LiveBehaviourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def call(self, path, payload=None, raw=False):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.live.base_url + path, data=data, method="POST" if data is not None else "GET",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode()
                return response.status, (body if raw else json.loads(body)), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode()), dict(error.headers)

    def setUp(self):
        self.original = self.call("/api/config")[1]
        # Three pages, with a page-jump button on the first one.
        profile = copy.deepcopy(self.original)
        profile["current_page"] = 0
        profile["pages"] = profile["pages"][:3]
        self.button_id = None
        for slot in profile["pages"][0]["slots"]:
            if slot["type"] == "button":
                slot.update({"action_type": "page", "target": "next", "extra": {}})
                self.button_id = slot["id"]
                break
        self.assertEqual(self.call("/api/config", profile)[0], 200)
        self.page_ids = [p["id"] for p in profile["pages"]]

    def tearDown(self):
        self.call("/api/config", self.original)

    def current_page(self):
        return self.call("/api/config")[1]["current_page"]

    def trigger(self):
        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                await ws.recv()
                await ws.send(json.dumps({"type": "trigger_button", "id": self.button_id}))
                seen = {}
                for _ in range(10):
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    seen[message["type"]] = message
                    if "action_result" in seen:
                        return seen
        return asyncio.run(scenario())

    def test_a_page_button_moves_the_phone_to_the_next_page(self):
        seen = self.trigger()
        self.assertTrue(seen["action_result"]["success"])
        self.assertEqual(seen["config_sync"]["config"]["current_page"], 1)
        self.assertEqual(self.current_page(), 1)

    def test_a_page_button_to_a_deleted_page_says_so(self):
        profile = self.call("/api/config")[1]
        profile["current_page"] = 0
        for slot in profile["pages"][0]["slots"]:
            if slot.get("id") == self.button_id:
                slot["target"] = "page_gone99"
        self.call("/api/config", profile)
        seen = self.trigger()
        self.assertFalse(seen["action_result"]["success"])
        self.assertIn("ya no existe", seen["action_result"]["message"])

    def test_the_page_for_the_program_in_the_foreground_opens_by_itself(self):
        profile = self.call("/api/config")[1]
        profile["current_page"] = 0
        profile["pages"][2]["auto_app"] = "obs64.exe"
        self.call("/api/config", profile)
        with mock.patch.object(main, "foreground_process", return_value="obs64.exe"):
            for _ in range(40):
                if self.current_page() == 2:
                    break
                time.sleep(0.1)
            self.assertEqual(self.current_page(), 2)
            # The user moves back by hand: the same foreground program must not drag them away again.
            self.call("/api/deck/page/switch", {"page_index": 0})
            time.sleep(2.3)
            self.assertEqual(self.current_page(), 0)

    def test_export_is_a_download_without_secrets(self):
        status, body, headers = self.call("/api/profile/export", raw=True)
        self.assertEqual(status, 200)
        disposition = {key.lower(): value for key, value in headers.items()}.get("content-disposition", "")
        self.assertIn("attachment", disposition)
        for secret in ("password", "access_token", "refresh_token", "authorized_tokens"):
            self.assertNotIn(secret, body)
        self.assertEqual(len(json.loads(body)["pages"]), 3)

    def test_import_replaces_the_profile_and_keeps_a_backup(self):
        exported = self.call("/api/profile/export")[1]
        exported["pages"] = exported["pages"][:1]
        exported["pages"][0]["name"] = "Importada"
        exported["current_page"] = 0
        before = set(glob.glob(os.path.join(CONFIG_DIR, "deck_config.backup-*.json")))
        status, body, _ = self.call("/api/profile/import", exported)
        self.assertEqual((status, body["pages"], body["backup"]), (200, 1, True))
        self.assertEqual([p["name"] for p in self.call("/api/config")[1]["pages"]], ["Importada"])
        self.assertTrue(set(glob.glob(os.path.join(CONFIG_DIR, "deck_config.backup-*.json"))) - before)

    def test_import_refuses_an_unsafe_file_and_changes_nothing(self):
        evil = self.call("/api/profile/export")[1]
        evil["pages"][0]["slots"][0].update({"type": "button", "action_type": "script", "target": "whoami"})
        status, body, _ = self.call("/api/profile/import", evil)
        self.assertEqual(status, 422)
        self.assertIn("perfil", body["detail"])
        self.assertEqual(len(self.call("/api/config")[1]["pages"]), 3)

    def test_duplicating_a_page(self):
        profile = self.call("/api/config")[1]
        profile["pages"][0]["auto_app"] = "chrome.exe"
        self.call("/api/config", profile)
        status, body, _ = self.call("/api/deck/page/duplicate", {"page_index": 0})
        pages = self.call("/api/config")[1]["pages"]
        self.assertEqual((status, body["index"], len(pages)), (200, 1, 4))
        self.assertNotEqual(pages[0]["id"], pages[1]["id"])
        self.assertTrue(pages[1]["name"].endswith("(copia)"))
        self.assertNotIn("auto_app", pages[1])  # two pages for one program would be ambiguous
        self.assertEqual(pages[0]["auto_app"], "chrome.exe")
        self.assertEqual(self.call("/api/deck/page/duplicate", {"page_index": 99})[0], 404)

    def test_connector_catalog_lists_ready_made_buttons_without_probing_services(self):
        started = time.time()
        status, body, _ = self.call("/api/connectors/catalog")
        self.assertEqual(status, 200)
        self.assertLess(time.time() - started, 1.5)  # no OBS or Spotify status checks
        by_id = {c["id"]: c for c in body["connectors"]}
        self.assertEqual(set(by_id), {"windows", "obs", "spotify", "discord"})
        self.assertIn("lock_pc", [a["id"] for a in by_id["windows"]["actions"]])


class SaveCopyAndLibraryTests(unittest.TestCase):
    def test_saving_a_copy_writes_a_profile_the_importer_accepts(self):
        folder = tempfile.mkdtemp()
        with support.LiveServer() as live, mock.patch("os.path.expanduser", return_value=folder):
            request = urllib.request.Request(live.base_url + "/api/profile/save-copy", data=b"{}",
                                             headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=10) as response:
                path = json.loads(response.read().decode())["path"]
        self.assertTrue(path.startswith(folder))
        with open(path, encoding="utf-8") as handle:
            validate_deck_config(json.load(handle))  # raises if the copy is not a valid profile

    @unittest.skipUnless(shutil.which("node"), "needs Node to run the browser code")
    def test_every_library_action_is_accepted_by_the_server(self):
        # Runs the real studio.js and studio-library.js against a stub DOM and reads the library.
        script = r"""
const fs = require("fs"), vm = require("vm");
const fake = new Proxy(function () {}, {
  get: (t, p) => (p === Symbol.toPrimitive ? () => "" : p === "then" ? undefined : fake),
  apply: () => fake, construct: () => fake,
});
const sandbox = { document: fake, window: fake, localStorage: fake, location: { host: "x" }, navigator: fake,
  fetch: () => new Promise(() => {}), WebSocket: function () { return fake; }, setInterval: () => 0, setTimeout: () => 0,
  console, JSON, Promise, Map, Set, Math, Date, Number, String, Array, Object, Event: function () {}, FormData: function () {} };
vm.createContext(sandbox);
for (const file of process.argv.slice(1)) vm.runInContext(fs.readFileSync(file, "utf8"), sandbox, { filename: file });
process.stdout.write(vm.runInContext("JSON.stringify(builtInLibrary())", sandbox));
"""
        result = subprocess.run(
            ["node", "-e", script, os.path.join(STATIC_DIR, "js", "studio.js"), os.path.join(STATIC_DIR, "js", "studio-library.js")],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-600:])
        categories = json.loads(result.stdout)
        items = [item for category in categories for item in category["items"]]
        self.assertGreater(len(items), 15)
        ids = [item["id"] for item in items]
        self.assertEqual(len(ids), len(set(ids)), "library ids must be unique")
        for item in items:
            with self.subTest(item=item["id"]):
                self.assertLessEqual(len(item["label"]), 32)  # the button title limit
                self.assertLessEqual(len(item["sub"]), 36)
                validate_action(item["action_type"], item["target"], item.get("extra"))
                self.assertTrue(os.path.exists(os.path.join(STATIC_DIR, item["icon"].lstrip("/").replace("static/", "", 1))), item["icon"])

    def test_the_interface_has_what_the_library_needs(self):
        html = open(os.path.join(STATIC_DIR, "studio.html"), encoding="utf-8").read()
        for element in ("library-search", "library-list", "btn-page-settings", "pairing-panel"):
            self.assertIn(f'id="{element}"', html)
        self.assertIn("studio-library.js", html)
        studio = open(os.path.join(STATIC_DIR, "js", "studio.js"), encoding="utf-8").read()
        self.assertIn('["action", "Acción"]', studio)
        self.assertNotIn('["controls", "Controles"]', studio)  # media and monitors live in the library now
        self.assertIn('dragSourceType === "library"', studio)


class IconTests(unittest.TestCase):
    def test_new_icons_exist(self):
        for name in ("keyboard", "lock", "mic", "mic_off"):
            self.assertTrue(os.path.exists(os.path.join(STATIC_DIR, "icons", f"{name}.svg")), name)


if __name__ == "__main__":
    unittest.main()
