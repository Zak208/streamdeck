"""Console commands (opt-in), the extra OBS actions, and grids of any size."""

import copy
import json
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import support
from server import layouts, shell_actions
from server.action_catalog import validate_action, validate_deck_config
from server.config_manager import DEFAULT_CONFIG
from server.connectors import obs as obs_connector
from server.connectors import windows as windows_connector
from server.obs_client import obs_client


def default_profile():
    return validate_deck_config(copy.deepcopy(DEFAULT_CONFIG))


class CustomGridTests(unittest.TestCase):
    def test_the_formats_that_are_accepted(self):
        self.assertEqual(layouts.parse_layout("4x8"), (8, 4))   # "<columns>x<rows>"
        self.assertEqual(layouts.parse_layout(" 6 X 2 "), (2, 6))
        self.assertEqual(layouts.parse_layout({"columns": 10, "rows": 6}), (6, 10))

    def test_the_sizes_that_are_refused(self):
        for bad in ("11x2", "1x4", "4x1", "4x9", "10x8", "0x0", "x", "", "4*8", {"columns": 4}, {"columns": "4", "rows": 2},
                    {"columns": True, "rows": 2}, None, 48, ["4", "8"]):
            with self.subTest(spec=bad), self.assertRaises(ValueError):
                layouts.parse_layout(bad)

    def test_a_4_by_8_grid_converts_and_validates(self):
        converted, dropped = layouts.convert_config(default_profile(), "4x8")
        clean = validate_deck_config(converted)
        self.assertEqual(clean["layout"], {"rows": 8, "columns": 4, "total_slots": 32})
        self.assertEqual(dropped, 0)
        for page in clean["pages"]:
            self.assertEqual(len(page["slots"]), 32)
            for index, slot in enumerate(page["slots"]):
                if slot["type"] == "slider":
                    self.assertLess(index, 4)
                    self.assertEqual(page["slots"][index + 4]["type"], "occupied_by_slider")

    def test_every_allowed_size_gives_valid_pages(self):
        for columns in range(2, 11):
            for rows in range(2, 9):
                if columns * rows > layouts.LIMITS["max_total"]:
                    continue
                with self.subTest(size=f"{columns}x{rows}"):
                    converted, _ = layouts.convert_config(default_profile(), {"columns": columns, "rows": rows})
                    validate_deck_config(converted)

    def test_a_profile_file_with_a_custom_size_is_valid_on_its_own(self):
        profile, _ = layouts.convert_config(default_profile(), "7x3")
        self.assertEqual(validate_deck_config(profile)["layout"]["total_slots"], 21)


class GridEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def call(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.live.base_url + path, data=data, method="POST" if data is not None else "GET",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def tearDown(self):
        self.call("/api/layout", {"layout": "6x2"})

    def test_it_accepts_a_name_or_columns_and_rows(self):
        status, body = self.call("/api/layout", {"layout": "4x8"})
        self.assertEqual((status, body["config"]["layout"]["total_slots"]), (200, 32))
        status, body = self.call("/api/layout", {"columns": 8, "rows": 4})
        self.assertEqual((status, body["config"]["layout"]), (200, {"rows": 4, "columns": 8, "total_slots": 32}))
        self.assertEqual(self.call("/api/layouts")[1]["current"], "8x4")

    def test_the_listing_tells_the_limits_and_the_quick_picks(self):
        body = self.call("/api/layouts")[1]
        self.assertEqual(body["limits"]["max_columns"], 10)
        self.assertIn("6x2", [p["id"] for p in body["presets"]])
        self.assertEqual(body["layout"], {"rows": 2, "columns": 6, "total_slots": 12})

    def test_a_bad_size_is_refused_and_nothing_changes(self):
        before = self.call("/api/config")[1]
        for bad in ({"layout": "11x2"}, {"columns": 4}, {"columns": 12, "rows": 2}, {"layout": "4x8x2"}, {"layout": 5}):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("/api/layout", bad)[0], 422)
        self.assertEqual(self.call("/api/config")[1], before)


class CommandActionTests(unittest.TestCase):
    def setUp(self):
        shell_actions.set_enabled(False)

    def tearDown(self):
        shell_actions.set_enabled(False)

    def test_the_validation_of_the_lines(self):
        action = validate_action("command", "PowerShell", {"commands": ["Get-Date", "  Write-Output hi  "]})
        self.assertEqual(action, {"action_type": "command", "target": "powershell", "extra": {"commands": ["Get-Date", "Write-Output hi"]}})
        for bad in ({"commands": []}, {"commands": ["x"] * 9}, {"commands": ["a\nb"]}, {"commands": [""]}, {"commands": "dir"},
                    {"commands": [5]}, {"commands": ["x" * 501]}, {"commands": ["a\x00b"]}, {}):
            with self.subTest(extra=str(bad)[:30]), self.assertRaises(ValueError):
                validate_action("command", "cmd", bad)
        with self.assertRaises(ValueError):
            validate_action("command", "bash", {"commands": ["ls"]})

    def test_it_does_nothing_until_it_is_switched_on(self):
        with mock.patch.object(shell_actions, "_execute") as run:
            result = shell_actions.run("cmd", ["echo hola"])
        self.assertFalse(result["success"])
        self.assertIn("desactivados", result["error"])
        run.assert_not_called()

    def test_the_lines_run_in_order_and_stop_at_the_first_failure(self):
        shell_actions.set_enabled(True)
        calls = []

        def fake_run(command):
            calls.append(command)
            code = 3 if len(calls) == 2 else 0
            return code, b"salida", b"fallo" if code else b""

        with mock.patch.object(shell_actions, "_execute", fake_run):
            result = shell_actions.run("cmd", ["uno", "dos", "tres"])
        self.assertEqual(len(calls), 2)  # the third never ran
        self.assertFalse(result["success"])
        self.assertIn("comando 2 de 3", result["error"])
        self.assertIn("código 3", result["error"])
        self.assertEqual([r["exit_code"] for r in result["results"]], [0, 3])

    def test_powershell_gets_the_line_encoded_and_cmd_gets_it_quoted(self):
        shell_actions.set_enabled(True)
        seen = []
        ok = lambda command: (seen.append(command), (0, b"", b""))[1]
        with mock.patch.object(shell_actions, "_execute", ok):
            shell_actions.run("powershell", ['Write-Output "a; b"'])
            shell_actions.run("cmd", ["echo a & echo b"])
        self.assertEqual(seen[0][-2], "-EncodedCommand")
        self.assertNotIn("Write-Output", " ".join(seen[0]))  # nothing of the line is on the command line in the clear
        self.assertEqual(seen[1], 'cmd.exe /d /s /c "echo a & echo b"')

    def test_a_command_that_takes_too_long_is_stopped_and_reported(self):
        shell_actions.set_enabled(True)

        def slow(command):
            raise subprocess.TimeoutExpired(command, 60)

        with mock.patch.object(shell_actions, "_execute", slow):
            result = shell_actions.run("cmd", ["ping -t localhost"])
        self.assertFalse(result["success"])
        self.assertIn("60 segundos", result["error"])

    def test_a_real_command_that_outlives_the_timeout_is_killed_with_its_children(self):
        shell_actions.set_enabled(True)
        with mock.patch.object(shell_actions, "TIMEOUT_SECONDS", 2):
            started = time.monotonic()
            result = shell_actions.run("cmd", ["ping -n 30 127.0.0.1 > nul"])  # harmless: pings this PC for 30 s
            elapsed = time.monotonic() - started
        self.assertFalse(result["success"])
        self.assertIn("se detuvo", result["error"])
        self.assertLess(elapsed, 12)

    def test_two_real_harmless_lines_in_each_shell(self):
        shell_actions.set_enabled(True)
        for shell, lines in (("cmd", ["echo uno", "echo dos"]), ("powershell", ["Write-Output uno", "Write-Output dos"])):
            with self.subTest(shell=shell):
                result = shell_actions.run(shell, lines)
                self.assertTrue(result["success"], result)
                self.assertEqual([r["output"] for r in result["results"]], ["uno", "dos"])

    def test_a_failing_real_line_reports_what_it_printed(self):
        shell_actions.set_enabled(True)
        result = shell_actions.run("cmd", ["echo antes", "exit 7", "echo nunca"])
        self.assertFalse(result["success"])
        self.assertIn("código 7", result["error"])
        self.assertEqual(len(result["results"]), 2)

    def test_the_windows_connector_offers_it_with_a_confirmation_by_default(self):
        item = next(a for a in windows_connector.actions() if a["id"] == "command")
        validate_action(item["action_type"], item["target"], item["extra"])
        self.assertTrue(item["configure"] and item["confirm_default"])


class CommandSettingEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        shell_actions.set_enabled(False)
        cls.live.__exit__(None, None, None)

    def call(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.live.base_url + path, data=data, method="POST" if data is not None else "GET",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def test_it_is_off_by_default_and_only_real_booleans_change_it(self):
        shell_actions.set_enabled(False)
        self.assertEqual(self.call("/api/settings/commands")[1], {"enabled": False})
        self.assertEqual(self.call("/api/settings/commands", {"enabled": True})[1], {"enabled": True})
        self.assertEqual(self.call("/api/settings/commands")[1], {"enabled": True})
        for bad in ("true", 1, None, "yes", [True]):
            with self.subTest(value=bad):
                self.assertEqual(self.call("/api/settings/commands", {"enabled": bad})[0], 422)
        self.assertEqual(self.call("/api/settings/commands")[1], {"enabled": True})
        self.assertEqual(self.call("/api/settings/commands", {"enabled": False})[1], {"enabled": False})

    def test_the_switch_is_not_part_of_an_exported_profile(self):
        shell_actions.set_enabled(True)
        exported = json.dumps(self.call("/api/profile/export")[1])
        self.assertNotIn("enabled", exported.replace("is_enabled", ""))
        shell_actions.set_enabled(False)


class FakeObs:
    """Answers OBS WebSocket requests and remembers them."""

    def __init__(self, data=None):
        self.calls = []
        self.data = data or {}

    def __call__(self, request_type, request_data=None):
        self.calls.append((request_type, request_data or {}))
        return {"requestStatus": {"result": True}, "responseData": self.data.get(request_type, {})}


class ObsActionTests(unittest.TestCase):
    def run_action(self, target, extra=None, data=None):
        fake = FakeObs(data)
        with mock.patch.object(obs_client, "request", fake):
            result = obs_client.execute_obs_action(target, extra or {})
        return result, fake.calls

    def test_start_and_stop_are_separate_buttons(self):
        for target, request, active in (("record_start", "StartRecord", True), ("record_stop", "StopRecord", False),
                                        ("stream_start", "StartStream", True), ("stream_stop", "StopStream", False)):
            with self.subTest(target=target):
                result, calls = self.run_action(target)
                self.assertEqual((result["success"], result["active"], calls), (True, active, [(request, {})]))

    def test_studio_mode_flips_what_obs_reports(self):
        result, calls = self.run_action("studio_mode_toggle", data={"GetStudioModeEnabled": {"studioModeEnabled": False}})
        self.assertTrue(result["active"])
        self.assertEqual(calls[-1], ("SetStudioModeEnabled", {"studioModeEnabled": True}))
        result, calls = self.run_action("studio_mode_toggle", data={"GetStudioModeEnabled": {"studioModeEnabled": True}})
        self.assertFalse(result["active"])

    def test_the_single_request_actions(self):
        for target, extra, request, payload in (
            ("studio_transition", {}, "TriggerStudioModeTransition", {}),
            ("set_scene", {"scene_name": "Juego"}, "SetCurrentProgramScene", {"sceneName": "Juego"}),
            ("set_scene_collection", {"collection_name": "Podcast"}, "SetCurrentSceneCollection", {"sceneCollectionName": "Podcast"}),
            ("set_profile", {"profile_name": "1080p"}, "SetCurrentProfile", {"profileName": "1080p"}),
            ("preview_scene", {"scene_name": "Juego"}, "SetCurrentPreviewScene", {"sceneName": "Juego"}),
            ("set_transition", {"transition_name": "Fundido"}, "SetCurrentSceneTransition", {"transitionName": "Fundido"}),
            ("replay_save", {}, "SaveReplayBuffer", {}),
            ("record_chapter", {}, "CreateRecordChapter", {}),
            ("record_split", {}, "SplitRecordFile", {}),
            ("hotkey", {"hotkey_name": "OBSBasic.StartRecording"}, "TriggerHotkeyByName", {"hotkeyName": "OBSBasic.StartRecording"}),
        ):
            with self.subTest(target=target):
                result, calls = self.run_action(target, extra)
                self.assertEqual((result["success"], calls), (True, [(request, payload)]))

    def test_replay_buffer_and_virtual_camera_report_their_state(self):
        for target, request in (("replay_toggle", "ToggleReplayBuffer"), ("virtualcam_toggle", "ToggleVirtualCam")):
            with self.subTest(target=target):
                result, calls = self.run_action(target, data={request: {"outputActive": True}})
                self.assertEqual((result["success"], result["active"], calls), (True, True, [(request, {})]))

    def test_showing_and_hiding_a_source_looks_up_its_id_first(self):
        result, calls = self.run_action("source_toggle", {"scene_name": "Juego", "source_name": "Cámara"}, data={
            "GetSceneItemId": {"sceneItemId": 7}, "GetSceneItemEnabled": {"sceneItemEnabled": True}})
        self.assertEqual((result["success"], result["active"]), (True, False))
        self.assertEqual([c[0] for c in calls], ["GetSceneItemId", "GetSceneItemEnabled", "SetSceneItemEnabled"])
        self.assertEqual(calls[-1][1], {"sceneName": "Juego", "sceneItemId": 7, "sceneItemEnabled": False})

    def test_muting_any_source_reports_whether_it_is_now_muted(self):
        result, calls = self.run_action("input_mute", {"source_name": "Mic"}, data={"ToggleInputMute": {"inputMuted": True}})
        self.assertEqual((result["success"], result["muted"], result["active"]), (True, True, True))
        self.assertEqual(calls, [("ToggleInputMute", {"inputName": "Mic"})])

    def test_a_refusal_from_obs_becomes_the_error_of_the_button(self):
        def refuse(request_type, request_data=None):
            return {"requestStatus": {"result": False, "code": 500, "comment": "Studio mode is not active"}}
        with mock.patch.object(obs_client, "request", refuse):
            result = obs_client.execute_obs_action("studio_transition", {})
        self.assertFalse(result["success"])
        self.assertIn("Studio mode is not active", result["error"])

    def test_obs_closed_says_so(self):
        def unreachable(request_type, request_data=None):
            return {"unreachable": True, "requestStatus": {"result": False}}
        with mock.patch.object(obs_client, "request", unreachable):
            for target in ("replay_save", "virtualcam_toggle", "record_start", "studio_mode_toggle"):
                with self.subTest(target=target):
                    self.assertFalse(obs_client.execute_obs_action(target, {})["success"])

    def test_sync_obs_scene_state(self):
        import asyncio
        from server.main import sync_obs_scene_state, button_states
        from server.config_manager import config_manager

        cfg = default_profile()
        cfg["pages"][0]["slots"][0] = {
            "index": 0, "type": "button", "id": "btn_scene_a", "action_type": "obs_action", "target": "set_scene", "extra": {"scene_name": "Juego"}
        }
        cfg["pages"][0]["slots"][1] = {
            "index": 1, "type": "button", "id": "btn_scene_b", "action_type": "obs_action", "target": "set_scene", "extra": {"scene_name": "Charla"}
        }
        with mock.patch.object(config_manager, "load_config", return_value=cfg):
            asyncio.run(sync_obs_scene_state("Juego"))
            self.assertTrue(button_states.get("btn_scene_a"))
            self.assertFalse(button_states.get("btn_scene_b"))

            asyncio.run(sync_obs_scene_state("Charla"))
            self.assertFalse(button_states.get("btn_scene_a"))
            self.assertTrue(button_states.get("btn_scene_b"))


class ObsValidationTests(unittest.TestCase):
    def test_what_needs_a_name_must_have_it(self):
        for target, extra in (("preview_scene", {}), ("set_transition", {}), ("source_toggle", {"scene_name": "x"}),
                              ("input_mute", {}), ("hotkey", {"hotkey_name": "a;b"}), ("hotkey", {"hotkey_name": "<b>"})):
            with self.subTest(target=target, extra=extra), self.assertRaises(ValueError):
                validate_action("obs_action", target, extra)
        self.assertEqual(validate_action("obs_action", "source_toggle", {"scene_name": "A", "source_name": "B", "junk": 1})["extra"],
                         {"scene_name": "A", "source_name": "B"})

    def test_every_template_of_the_connector_validates_and_fields_have_placeholders(self):
        actions = obs_connector.actions()
        self.assertGreaterEqual(len(actions), 20)
        for action in actions:
            with self.subTest(action=action["id"]):
                validate_action(action["action_type"], action["target"], action["extra"])
                for field in action.get("fields", []):
                    self.assertIn(field["name"], action["extra"])
                    self.assertTrue({"name", "label", "options", "filter_by", "required"} <= set(field))
                self.assertLessEqual(len(action["label"]), 32)
                self.assertLessEqual(len(action["sublabel"]), 36)

    def test_the_new_option_lists_exist(self):
        fake = FakeObs({
            "GetSceneTransitionList": {"transitions": [{"transitionName": "Corte"}, {"transitionName": "Fundido"}]},
            "GetSceneList": {"scenes": [{"sceneName": "A"}, {"sceneName": "B"}]},
            "GetSceneItemList": {"sceneItems": [{"sourceName": "Cámara"}]},
            "GetSceneCollectionList": {"sceneCollections": ["Principal", "Vertical"]},
            "GetProfileList": {"profiles": ["Directo", "Grabación"]},
        })
        with mock.patch.object(obs_client, "request", fake):
            self.assertEqual(obs_connector.options("transitions"), [{"name": "Corte"}, {"name": "Fundido"}])
            self.assertEqual(obs_connector.options("scene_items"), [{"name": "Cámara", "scene": "A"}, {"name": "Cámara", "scene": "B"}])
            self.assertEqual(obs_connector.options("collections"), [{"name": "Principal"}, {"name": "Vertical"}])
            self.assertEqual(obs_connector.options("profiles"), [{"name": "Directo"}, {"name": "Grabación"}])


if __name__ == "__main__":
    unittest.main()
