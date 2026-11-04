"""Long press, double tap, confirmation, disabled buttons and the "open a folder" action."""

import asyncio
import copy
import json
import unittest
from unittest import mock

import support
import websockets
from server import actions, main
from server.action_catalog import validate_action, validate_deck_config
from server.config_manager import DEFAULT_CONFIG


def profile_with(slot_changes):
    profile = copy.deepcopy(DEFAULT_CONFIG)
    slot = next(s for s in profile["pages"][0]["slots"] if s["type"] == "button")
    slot.update(slot_changes)
    return validate_deck_config(profile), slot["id"]


class GestureValidationTests(unittest.TestCase):
    def test_a_button_can_carry_a_long_press_and_a_double_tap(self):
        config, slot_id = profile_with({
            "long_press": {"action_type": "hotkey", "target": "ctrl+shift+m"},
            "double_tap": {"action_type": "url", "target": "https://example.com"},
        })
        slot = next(s for s in config["pages"][0]["slots"] if s.get("id") == slot_id)
        self.assertEqual(slot["long_press"], {"action_type": "hotkey", "target": "CTRL+SHIFT+M", "extra": {}})
        self.assertEqual(slot["double_tap"]["action_type"], "url")

    def test_a_gesture_action_is_validated_like_any_other(self):
        for bad in ({"action_type": "powershell", "target": "calc"}, {"action_type": "url", "target": "javascript:alert(1)"},
                    "hotkey", ["hotkey"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                profile_with({"long_press": bad})

    def test_confirm_and_disabled_are_kept_only_when_set(self):
        config, slot_id = profile_with({"confirm": True, "disabled": True})
        slot = next(s for s in config["pages"][0]["slots"] if s.get("id") == slot_id)
        self.assertIs(slot["confirm"], True)
        self.assertIs(slot["disabled"], True)
        config, slot_id = profile_with({"confirm": False, "disabled": 0})
        slot = next(s for s in config["pages"][0]["slots"] if s.get("id") == slot_id)
        self.assertNotIn("confirm", slot)
        self.assertNotIn("disabled", slot)


class FolderActionTests(unittest.TestCase):
    def test_only_local_drive_paths_are_accepted(self):
        self.assertEqual(validate_action("folder", "D:/Proyectos/Web")["target"], "D:\\Proyectos\\Web")
        for bad in ("\\\\servidor\\recurso", "//servidor/recurso", "notepad.exe", "C:\\a\\..\\b", "C:\\a|b", "relativa\\ruta", ""):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                validate_action("folder", bad)

    def test_it_opens_a_folder_that_exists_and_says_so_when_it_does_not(self):
        with mock.patch.object(actions.os, "startfile", create=True) as startfile, \
                mock.patch.object(actions.os.path, "isdir", return_value=True):
            self.assertTrue(actions.execute_action("folder", "C:\\Users", {})["success"])
        startfile.assert_called_once_with("C:\\Users")
        with mock.patch.object(actions.os, "startfile", create=True) as startfile, \
                mock.patch.object(actions.os.path, "isdir", return_value=False):
            result = actions.execute_action("folder", "C:\\NoExiste", {})
        self.assertFalse(result["success"])
        self.assertIn("no existe", result["error"])
        startfile.assert_not_called()

    def test_a_folder_can_be_a_macro_step(self):
        validate_action("multi", "m", {"actions": [{"action_type": "folder", "target": "C:\\Users", "extra": {}}]})


class GestureTriggerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def setUp(self):
        main.button_states.clear()
        main._running_actions.clear()
        config = main.config_manager.get_config()
        self.slot = next(s for s in config["slots"] if s["type"] == "button")
        self.slot_id = self.slot["id"]

    def install(self, **changes):
        profile = copy.deepcopy(main.config_manager.get_config())
        slot = next(s for s in profile["pages"][profile["current_page"]]["slots"] if s.get("id") == self.slot_id)
        for leftover in ("long_press", "double_tap", "confirm", "disabled"):
            slot.pop(leftover, None)  # the config persists between tests
        slot.update({"action_type": "sound", "target": "beep", "extra": {}})
        slot.update(changes)
        main.config_manager.save_config(validate_deck_config(profile))

    def press(self, gesture=None):
        message = {"type": "trigger_button", "id": self.slot_id}
        if gesture:
            message["gesture"] = gesture

        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                await ws.recv()
                await ws.send(json.dumps(message))
                while True:
                    reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    if reply["type"] == "action_result":
                        return reply

        runner = mock.Mock(return_value={"success": True})
        with mock.patch.object(main, "execute_action", runner):
            reply = asyncio.run(scenario())
        return reply, runner

    def test_a_plain_tap_runs_the_normal_action(self):
        self.install(long_press={"action_type": "sound", "target": "asterisk"})
        reply, runner = self.press()
        self.assertTrue(reply["success"])
        self.assertEqual(runner.call_args.args[:2], ("sound", "beep"))

    def test_a_long_press_runs_its_own_action_instead(self):
        self.install(long_press={"action_type": "sound", "target": "asterisk"})
        reply, runner = self.press("long_press")
        self.assertTrue(reply["success"])
        self.assertEqual(runner.call_args.args[:2], ("sound", "asterisk"))

    def test_a_double_tap_runs_its_own_action_instead(self):
        self.install(double_tap={"action_type": "url", "target": "https://example.com"})
        reply, runner = self.press("double_tap")
        self.assertTrue(reply["success"])
        self.assertEqual(runner.call_args.args[:2], ("url", "https://example.com"))

    def test_a_gesture_the_button_does_not_have_says_so_and_runs_nothing(self):
        self.install()
        reply, runner = self.press("long_press")
        self.assertFalse(reply["success"])
        self.assertIn("gesto", reply["message"])
        runner.assert_not_called()

    def test_an_unknown_gesture_is_refused(self):
        self.install()
        reply, runner = self.press("triple_tap")
        self.assertFalse(reply["success"])
        runner.assert_not_called()

    def test_a_disabled_button_runs_nothing_even_if_the_phone_sends_the_press(self):
        self.install(disabled=True)
        reply, runner = self.press()
        self.assertFalse(reply["success"])
        self.assertIn("desactivado", reply["message"])
        runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
