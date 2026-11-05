import asyncio
import json
import os
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

import support
from server import action_catalog
from server.connectors import discord, obs, spotify, windows
from server.obs_client import (
    OBS_NEEDS_PASSWORD,
    OBS_UNREACHABLE,
    OBS_WRONG_PASSWORD,
    OBSClient,
    _auth_string,
)
from server.settings_store import SettingsStore, settings


class FakeOBS:
    """A minimal OBS WebSocket 5 server: Hello, optional authentication, then canned responses."""

    SALT = "lM1GncleQOaCu9lT1yeUZhFYnqhsLLP1G5lAGo3ixaI="
    CHALLENGE = "+IxH4CnCiqpX1rM9scsNynZzbOe4KhDeYcTNS3PDaeY="

    def __init__(self, password=None, responses=None):
        self.password = password
        self.responses = responses or {}
        self.requests = []
        self.port = support.free_port()
        self._loop = None
        self._stop = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=lambda: asyncio.run(self._main()), daemon=True)

    async def _handler(self, ws):
        hello = {"op": 0, "d": {"obsWebSocketVersion": "5.5.0", "rpcVersion": 1}}
        if self.password:
            hello["d"]["authentication"] = {"challenge": self.CHALLENGE, "salt": self.SALT}
        await ws.send(json.dumps(hello))
        identify = json.loads(await ws.recv())
        if self.password and identify["d"].get("authentication") != _auth_string(self.password, self.SALT, self.CHALLENGE):
            await ws.close(4009, "Authentication failed.")
            return
        await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        async for raw in ws:
            request = json.loads(raw)["d"]
            self.requests.append((request["requestType"], request.get("requestData")))
            status, data = self.responses.get(request["requestType"], (True, {}))
            await ws.send(json.dumps({"op": 7, "d": {
                "requestType": request["requestType"], "requestId": request["requestId"],
                "requestStatus": {"result": status, "code": 100 if status else 600},
                "responseData": data,
            }}))

    async def _main(self):
        from websockets.asyncio.server import serve
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        async with serve(self._handler, "127.0.0.1", self.port):
            self._ready.set()
            await self._stop.wait()

    def __enter__(self):
        self._thread.start()
        self._ready.wait(5)
        return self

    def __exit__(self, *exc):
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(5)


class SettingsStoreTests(unittest.TestCase):
    def test_secrets_never_leave_through_public(self):
        store = SettingsStore(support.os.path.join(support.tempfile.mkdtemp(), "settings.json"))
        store.update("obs", {"port": 4455, "password": "hunter2"})
        self.assertEqual(store.public("obs"), {"port": 4455, "password_set": True})
        self.assertEqual(store.get("obs")["password"], "hunter2")
        store.update("obs", {}, remove=("password",))
        self.assertEqual(store.public("obs"), {"port": 4455})


class OBSProtocolTests(unittest.TestCase):
    def test_authentication_string_matches_the_protocol_documentation(self):
        self.assertEqual(
            _auth_string("supersecretpassword", FakeOBS.SALT, FakeOBS.CHALLENGE),
            "1Ct943GAT+6YQUUX47Ia/ncufilbe6+oD6lY+5kaCu4=",
        )

    def test_toggle_record_reports_the_real_state(self):
        with FakeOBS(responses={"ToggleRecord": (True, {"outputActive": True})}) as fake:
            result = OBSClient(port=fake.port, password="").execute_obs_action("record_toggle")
        self.assertEqual((result["success"], result["active"]), (True, True))

    def test_password_is_sent_and_accepted(self):
        with FakeOBS(password="secret", responses={"GetVersion": (True, {"obsVersion": "31.0.0"})}) as fake:
            status = OBSClient(port=fake.port, password="secret").status()
        self.assertEqual(status, {"state": "ready", "detail": "OBS 31.0.0"})

    def test_missing_and_wrong_passwords_have_their_own_messages(self):
        with FakeOBS(password="secret") as fake:
            missing = OBSClient(port=fake.port, password="").status()
            wrong = OBSClient(port=fake.port, password="nope").status()
        self.assertEqual((missing["state"], missing["detail"]), ("needs_setup", OBS_NEEDS_PASSWORD))
        self.assertEqual((wrong["state"], wrong["detail"]), ("needs_setup", OBS_WRONG_PASSWORD))

    def test_scenes_and_inputs_come_from_obs(self):
        responses = {
            "GetSceneList": (True, {"scenes": [{"sceneName": "Juego"}, {"sceneName": "Charla"}]}),
            "GetInputList": (True, {"inputs": [{"inputName": "Mic/Aux", "inputKind": "wasapi_input_capture"}]}),
        }
        with FakeOBS(responses=responses) as fake:
            client = OBSClient(port=fake.port, password="")
            self.assertEqual(client.list_scenes(), ["Juego", "Charla"])
            self.assertEqual(client.list_inputs(), [{"name": "Mic/Aux", "kind": "wasapi_input_capture"}])

    def test_mute_uses_the_chosen_source_and_reports_the_mute_state(self):
        with FakeOBS(responses={"ToggleInputMute": (True, {"inputMuted": True})}) as fake:
            result = OBSClient(port=fake.port, password="").execute_obs_action("mute_mic", {"source_name": "Micro USB"})
            requests = list(fake.requests)
        self.assertEqual(requests, [("ToggleInputMute", {"inputName": "Micro USB"})])
        self.assertEqual((result["success"], result["active"]), (True, True))

    def test_obs_refusing_a_request_is_a_failure(self):
        with FakeOBS(responses={"SetCurrentProgramScene": (False, {})}) as fake:
            result = OBSClient(port=fake.port, password="").execute_obs_action("scene_x", {"scene_name": "x"})
        self.assertIs(result["success"], False)

    def test_closed_obs_gives_the_setup_hint(self):
        result = OBSClient(port=support.free_port(), password="").execute_obs_action("stream_toggle")
        self.assertEqual(result["error"], OBS_UNREACHABLE)

    def test_connector_validates_its_settings(self):
        with self.assertRaises(ValueError):
            obs.configure({"port": 80})
        with self.assertRaises(ValueError):
            obs.configure({"password": 123})


class SpotifyTests(unittest.TestCase):
    CLIENT_ID = "0123456789abcdef0123456789abcdef"
    PLAYLIST = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
    TRACK = "spotify:track:4uLU6hMCjMI75M1A2tKUQC"

    def setUp(self):
        settings.clear("spotify")
        spotify._pending.clear()

    def connect(self, premium=True):
        spotify.configure({"client_id": self.CLIENT_ID})
        settings.update("spotify", {"refresh_token": "r", "access_token": "a", "expires_at": 9e12})

    def test_client_id_is_validated(self):
        for bad in ("", "short", "z" * 32):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                spotify.configure({"client_id": bad})

    def test_changing_the_app_forgets_the_old_tokens(self):
        self.connect()
        spotify.configure({"client_id": "f" * 32})
        self.assertFalse(spotify.public_settings()["connected"])

    def test_login_uses_pkce_and_checks_state(self):
        spotify.configure({"client_id": self.CLIENT_ID})
        with mock.patch.object(spotify.webbrowser, "open"):
            url = spotify.begin_login()["url"]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["redirect_uri"], [spotify.REDIRECT_URI])
        self.assertTrue(spotify.REDIRECT_URI.startswith("http://127.0.0.1:"))
        state = query["state"][0]

        with self.assertRaises(spotify.SpotifyError):
            spotify.finish_login("code", "forged-state")

        captured = {}

        def fake_token(form):
            captured.update(form)
            return {"access_token": "ACCESS-SECRET", "refresh_token": "REFRESH-SECRET", "expires_in": 3600}

        with mock.patch.object(spotify, "_token_request", fake_token):
            spotify.finish_login("the-code", state)
        self.assertEqual(spotify._challenge(captured["code_verifier"]), query["code_challenge"][0])
        self.assertEqual(captured["code"], "the-code")
        self.assertTrue(spotify.public_settings()["connected"])
        public = json.dumps(spotify.public_settings())
        self.assertNotIn("ACCESS-SECRET", public)
        self.assertNotIn("REFRESH-SECRET", public)
        self.assertEqual(settings.get("spotify")["refresh_token"], "REFRESH-SECRET")

    def test_state_cannot_be_reused(self):
        spotify.configure({"client_id": self.CLIENT_ID})
        with mock.patch.object(spotify.webbrowser, "open"):
            state = urllib.parse.parse_qs(urllib.parse.urlparse(spotify.begin_login()["url"]).query)["state"][0]
        with mock.patch.object(spotify, "_token_request", return_value={"access_token": "a", "refresh_token": "r"}):
            spotify.finish_login("c", state)
            with self.assertRaises(spotify.SpotifyError):
                spotify.finish_login("c", state)

    def test_without_an_account_the_button_presses_play_in_the_app(self):
        with mock.patch.object(spotify.spotify_ui, "play") as pressed:
            result = spotify.play("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=x")
        pressed.assert_called_once_with(self.PLAYLIST)
        self.assertEqual((result["success"], result["mode"]), (True, "ui"))

    def test_a_failure_pressing_play_reaches_the_button_as_a_reason(self):
        with mock.patch.object(spotify.spotify_ui, "play", side_effect=spotify.spotify_ui.SpotifyUiError("Spotify está minimizado.")), \
                mock.patch.object(spotify, "_open_in_app") as opened:
            result = spotify.play(self.PLAYLIST)
        self.assertEqual((result["success"], result["error"]), (False, "Spotify está minimizado."))
        opened.assert_not_called()  # opening the list could pull the focus away from the user's program
        with mock.patch.object(spotify.spotify_ui, "play", side_effect=OSError("boom")):
            self.assertIs(spotify.play(self.PLAYLIST)["success"], False)

    def test_connected_playlist_and_track_use_the_right_body(self):
        self.connect()
        with mock.patch.object(spotify, "_api") as api:
            self.assertEqual(spotify.play(self.PLAYLIST)["mode"], "play")
            spotify.play(self.TRACK)
        self.assertEqual(api.call_args_list[0].args, ("PUT", "/me/player/play", {"context_uri": self.PLAYLIST}))
        self.assertEqual(api.call_args_list[1].args, ("PUT", "/me/player/play", {"uris": [self.TRACK]}))

    def test_closed_spotify_is_launched_then_played_on_its_device(self):
        self.connect()

        def api(method, path, body=None):
            if path == "/me/player/play":
                raise spotify.SpotifyError("no device", 404, "NO_ACTIVE_DEVICE")
            if path == "/me/player/devices":
                return {"devices": [{"id": "phone", "type": "Smartphone"}, {"id": "pc", "type": "Computer"}]}

        with mock.patch.object(spotify, "_api", side_effect=api) as mocked, \
                mock.patch.object(spotify, "_open_in_app") as opened, mock.patch.object(spotify.time, "sleep"):
            result = spotify.play(self.PLAYLIST)
        opened.assert_called_once_with("spotify:")
        self.assertEqual(result["mode"], "play")
        self.assertEqual(mocked.call_args.args[1], "/me/player/play?device_id=pc")

    def test_no_device_ever_appearing_falls_back_to_pressing_play_in_the_app(self):
        self.connect()

        def api(method, path, body=None):
            if path == "/me/player/play":
                raise spotify.SpotifyError("no device", 404, "NO_ACTIVE_DEVICE")
            return {"devices": []}

        clock = iter(range(0, 1000, 3))
        with mock.patch.object(spotify, "_api", side_effect=api), mock.patch.object(spotify, "_open_in_app"), \
                mock.patch.object(spotify.spotify_ui, "play") as pressed, \
                mock.patch.object(spotify.time, "sleep"), mock.patch.object(spotify.time, "time", lambda: next(clock)):
            result = spotify.play(self.PLAYLIST)
        self.assertEqual(result["mode"], "ui")
        pressed.assert_called_once_with(self.PLAYLIST)

    def test_free_accounts_get_play_pressed_in_the_app_with_an_explanation(self):
        self.connect()
        with mock.patch.object(spotify, "_api", side_effect=spotify.SpotifyError("x", 403, "PREMIUM_REQUIRED")), \
                mock.patch.object(spotify.spotify_ui, "play") as pressed:
            result = spotify.play(self.PLAYLIST)
        self.assertEqual(result["mode"], "ui")
        self.assertIn("Premium", result["note"])
        pressed.assert_called_once_with(self.PLAYLIST)

    def test_revoked_access_asks_to_reconnect(self):
        self.connect()
        with mock.patch.object(spotify, "_api", side_effect=spotify.SpotifyError("x", 401)):
            result = spotify.play(self.PLAYLIST)
        self.assertIs(result["success"], False)
        self.assertIn("volver a conectar", result["error"])

    def test_playlist_picker_drops_bad_uris_and_non_https_images(self):
        self.connect()
        items = {"items": [
            {"uri": self.PLAYLIST, "name": "Focus", "images": [{"url": "https://i.scdn.co/image/a"}]},
            {"uri": "spotify:playlist:37i9dQZF1DXcBWIGoYBM5N", "name": "Tracking", "images": [{"url": "http://evil/x"}]},
            {"uri": "javascript:alert(1)", "name": "Bad"},
            None,
        ]}
        with mock.patch.object(spotify, "_api", return_value=items):
            playlists = spotify.options("playlists")
        self.assertEqual([p["name"] for p in playlists], ["Focus", "Tracking"])
        self.assertEqual(playlists[1]["image"], "")

    def test_status_explains_each_level(self):
        self.assertEqual(spotify.status()["state"], "needs_setup")
        self.connect()
        with mock.patch.object(spotify, "_api", return_value={"display_name": "Zak", "product": "premium"}):
            self.assertEqual(spotify.status(), {"state": "ready", "detail": "Conectado como Zak"})
        with mock.patch.object(spotify, "_api", return_value={"display_name": "Zak", "product": "free"}):
            self.assertEqual(spotify.status()["state"], "limited")


class WindowsAndDiscordTests(unittest.TestCase):
    DEVICE = "{0.0.0.00000000}.{85bed6a9-4717-4072-8eb1-f2d4943a5d40}"

    def test_windows_actions_are_validated(self):
        ok = action_catalog.validate_action("windows", "output_device", {"device_id": self.DEVICE, "junk": 1})
        self.assertEqual(ok["extra"], {"device_id": self.DEVICE})
        self.assertEqual(action_catalog.validate_action("windows", "mic_mute")["extra"], {})
        self.assertEqual(action_catalog.validate_action("windows", "app_mute", {"process": "Discord.exe"})["extra"], {"process": "Discord.exe"})
        for target, extra in (("format_c", {}), ("output_device", {"device_id": "x; calc"}), ("app_mute", {"process": "a;b"})):
            with self.subTest(target=target), self.assertRaises(ValueError):
                action_catalog.validate_action("windows", target, extra)

    def test_obs_mic_source_survives_validation(self):
        action = action_catalog.validate_action("obs_action", "mute_mic", {"source_name": "Micro USB"})
        self.assertEqual(action["extra"], {"source_name": "Micro USB"})

    def test_mic_toggle_reports_the_new_state(self):
        endpoint = mock.Mock()
        endpoint.GetMute.return_value = 0
        with mock.patch.object(windows, "_mic_endpoint", return_value=endpoint):
            result = windows.toggle_mic_mute()
        endpoint.SetMute.assert_called_once_with(True, None)
        self.assertEqual((result["success"], result["muted"], result["active"]), (True, True, True))

    def test_no_microphone_is_a_readable_failure(self):
        with mock.patch.object(windows, "_mic_endpoint", side_effect=OSError):
            self.assertIs(windows.toggle_mic_mute()["success"], False)
            self.assertIsNone(windows.get_mic_muted())

    def test_output_device_switch_only_touches_known_devices(self):
        devices = [{"id": self.DEVICE, "name": "Auriculares", "default": False}]
        with mock.patch.object(windows, "_list_output_devices", return_value=devices), \
                mock.patch.object(windows.AudioUtilities, "SetDefaultDevice") as switch:
            self.assertEqual(windows.set_output_device(self.DEVICE)["device"], "Auriculares")
            switch.assert_called_once_with(self.DEVICE)
            switch.reset_mock()
            self.assertIs(windows.set_output_device("{0.0.0.00000000}.{00000000-0000-0000-0000-000000000000}")["success"], False)
            self.assertIs(windows.set_output_device("; calc")["success"], False)
            switch.assert_not_called()

    def test_discord_hotkeys_are_saved_and_used_by_the_templates(self):
        settings.clear("discord")
        discord.configure({"mute_hotkey": "control+alt+f7", "deafen_hotkey": "CTRL+ALT+F8"})
        templates = {a["id"]: a for a in discord.actions()}
        self.assertEqual(templates["mute"]["extra"], {"hotkey": "CTRL+ALT+F7"})
        self.assertEqual(templates["deafen"]["extra"], {"hotkey": "CTRL+ALT+F8"})
        for template in templates.values():
            action_catalog.validate_action(template["action_type"], template["target"], template["extra"])

    def test_discord_rejects_clashing_or_invalid_hotkeys(self):
        settings.clear("discord")
        with self.assertRaises(ValueError):
            discord.configure({"mute_hotkey": "CTRL+ALT+F7", "deafen_hotkey": "CTRL+ALT+F7"})
        with self.assertRaises(ValueError):
            discord.configure({"mute_hotkey": "M"})


class ComSafetyTests(unittest.TestCase):
    """A bad COM pointer takes the whole process down with no Python traceback, so guard it twice."""

    def test_server_code_never_uses_ctypes_cast_on_com_pointers(self):
        import glob
        for path in glob.glob(os.path.join(support.PROJECT_ROOT, "server", "**", "*.py"), recursive=True):
            with self.subTest(file=os.path.relpath(path, support.PROJECT_ROOT)):
                code = "".join(line.split("#")[0] for line in open(path, encoding="utf-8"))
                self.assertNotRegex(code, r"(?<![A-Za-z_])cast\(", "use QueryInterface: cast releases the same pointer twice")

    def test_microphone_and_device_list_in_a_loop_do_not_crash_the_process(self):
        # With ctypes.cast this loop died with an access violation within seconds.
        script = "\n".join([
            "import gc, sys, time",
            f"sys.path.insert(0, {support.PROJECT_ROOT!r})",
            "from server.connectors import windows",
            "end = time.time() + 12",
            "while time.time() < end:",
            "    for call in (windows._get_mic_muted, windows._list_output_devices):",
            "        try: call()",
            "        except Exception: pass",
            "    gc.collect(1)",
        ])
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr[-500:])


class ConnectorEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()
        # Point OBS at a closed port so the "OBS is closed" paths are deterministic.
        settings.update("obs", {"port": support.free_port()}, remove=("password",))

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def call(self, path, payload=None, method=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.live.base_url + path, data=data, method=method or ("POST" if data else "GET"),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, error.read().decode()

    def test_gallery_lists_every_connector_with_a_status(self):
        status, body = self.call("/api/connectors")
        self.assertEqual(status, 200)
        cards = {c["id"]: c for c in json.loads(body)["connectors"]}
        self.assertEqual(set(cards), {"windows", "obs", "spotify", "discord"})
        self.assertEqual(cards["obs"]["status"]["detail"], OBS_UNREACHABLE)
        self.assertIn(cards["spotify"]["status"]["state"], {"needs_setup"})
        self.assertTrue(all(c["status"]["state"] in {"ready", "needs_setup", "limited", "offline"} for c in cards.values()))
        self.assertEqual([a["id"] for a in cards["discord"]["actions"]], ["mute", "deafen"])

    def test_saved_obs_password_is_never_sent_back(self):
        status, body = self.call("/api/connectors/obs/configure", {"password": "do-not-leak"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["settings"]["password_set"])
        self.assertNotIn("do-not-leak", body)
        self.assertNotIn("do-not-leak", self.call("/api/connectors")[1])
        self.assertEqual(settings.get("obs")["password"], "do-not-leak")

    def test_bad_settings_and_unknown_connectors(self):
        self.assertEqual(self.call("/api/connectors/spotify/configure", {"client_id": "nope"})[0], 422)
        self.assertEqual(self.call("/api/connectors/windows/configure", {"x": 1})[0], 404)
        self.assertEqual(self.call("/api/connectors/missing/options/x")[0], 404)

    def test_obs_lists_explain_why_they_are_empty(self):
        status, body = self.call("/api/connectors/obs/options/scenes")
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(body)["detail"], OBS_UNREACHABLE)

    def test_spotify_login_cannot_be_started_without_a_client_id_and_callback_checks_state(self):
        settings.clear("spotify")
        self.assertEqual(self.call("/api/connectors/spotify/connect", {})[0], 422)
        status, body = self.call("/api/connectors/spotify/callback?code=x&state=forged")
        self.assertEqual(status, 400)
        self.assertNotIn("forged", body)
        self.assertEqual(self.call("/api/connectors/spotify/callback?error=access_denied")[0], 400)

    def test_windows_output_options_do_not_change_anything(self):
        with mock.patch.object(windows, "list_output_devices", return_value=[{"id": "x", "name": "N", "default": True}]):
            status, body = self.call("/api/connectors/windows/options/outputs")
        self.assertEqual((status, json.loads(body)["options"][0]["name"]), (200, "N"))


if __name__ == "__main__":
    unittest.main()


class NewActionTests(unittest.TestCase):
    """Power, display, volume, screenshot, Steam, OBS filters and webhook PUT: what is accepted, and what runs."""

    def test_valid_and_refused_windows_actions(self):
        from server.action_catalog import validate_action
        good = [("power", {"mode": "restart", "delay": 30}), ("power", {"mode": "sleep"}), ("display_mode", {"mode": "clone"}),
                ("master_volume", {"mode": "set", "value": 40}), ("master_volume", {"mode": "step", "value": -10}),
                ("power_plan", {"plan": "Alto rendimiento"}), ("screenshot", {})]
        for target, extra in good:
            with self.subTest(target=target, extra=extra):
                self.assertEqual(validate_action("windows", target, extra)["target"], target)
        bad = [("power", {"mode": "format"}), ("power", {"mode": "restart", "delay": 601}), ("power", {"mode": "restart", "delay": True}),
               ("display_mode", {"mode": "rotate"}), ("master_volume", {"mode": "set", "value": 101}), ("master_volume", {"mode": "step", "value": 0}),
               ("master_volume", {"mode": "step", "value": "5"}), ("power_plan", {}), ("power_plan", {"plan": "a\nb"})]
        for target, extra in bad:
            with self.subTest(target=target, extra=extra), self.assertRaises(ValueError):
                validate_action("windows", target, extra)

    def test_power_runs_fixed_commands_never_text_from_the_profile(self):
        from server.connectors import windows
        calls = []

        def fake_run(command):
            calls.append(command)
            return mock.Mock(returncode=0, stdout="", stderr="")
        windows.set_power_enabled(True)
        self.addCleanup(windows.set_power_enabled, False)
        with mock.patch.object(windows, "_run", fake_run):
            windows.execute("power", {"mode": "restart", "delay": 20})
            windows.execute("power", {"mode": "cancel", "delay": 0})
            windows.execute("display_mode", {"mode": "extend"})
        self.assertEqual(calls[0], ["shutdown", "/r", "/t", "20"])
        self.assertEqual(calls[1], ["shutdown", "/a"])
        self.assertTrue(calls[2][0].lower().endswith("displayswitch.exe") and calls[2][1] == "/extend")

    def test_a_power_plan_is_found_by_name_and_its_id_comes_from_powercfg(self):
        from server.connectors import windows
        plans = [{"name": "Equilibrado", "id": "381b4222-f694-41f0-9685-ff5bb260df2e", "active": True}]
        calls = []
        with mock.patch.object(windows, "list_power_plans", return_value=plans), \
                mock.patch.object(windows, "_run", lambda c: calls.append(c) or mock.Mock(returncode=0, stdout="", stderr="")):
            self.assertTrue(windows.execute("power_plan", {"plan": "equilibrado"})["success"])
            self.assertFalse(windows.execute("power_plan", {"plan": "../../evil"})["success"])
        self.assertEqual(calls, [["powercfg", "/setactive", "381b4222-f694-41f0-9685-ff5bb260df2e"]])

    def test_master_volume_steps_and_clamps(self):
        from server.connectors import windows
        with mock.patch.object(windows.audio_controller, "get_master_volume", return_value={"volume": 95, "muted": False}), \
                mock.patch.object(windows.audio_controller, "set_master_volume", return_value={"success": True}) as setter:
            result = windows.master_volume({"mode": "step", "value": 10})
        self.assertEqual((result["volume"], setter.call_args.args[0]), (100, 100))

    def test_steam_games_only_take_an_application_number(self):
        from server.action_catalog import validate_action
        self.assertEqual(validate_action("steam", "730")["target"], "730")
        for bad in ("", "abc", "730;calc", "../x", "12345678901"):
            with self.subTest(target=bad), self.assertRaises(ValueError):
                validate_action("steam", bad)
        from server import actions
        with mock.patch.object(actions.os, "startfile") as start:
            self.assertTrue(actions.execute_action("steam", "730")["success"])
        start.assert_called_once_with("steam://rungameid/730")

    def test_obs_filter_volume_and_refresh(self):
        from server.action_catalog import validate_action
        from server.obs_client import obs_client
        for target, extra in (("filter_toggle", {"source_name": "Cam", "filter_name": "Color"}), ("input_volume_up", {"source_name": "Mic"}),
                              ("source_refresh", {"source_name": "Alertas"})):
            self.assertEqual(validate_action("obs_action", target, extra)["extra"], extra)
        with self.assertRaises(ValueError):
            validate_action("obs_action", "filter_toggle", {"source_name": "Cam"})
        sent = []

        def fake(kind, data=None):
            sent.append((kind, data))
            ok = {"requestStatus": {"result": True}}
            if kind == "GetSourceFilter":
                return {**ok, "responseData": {"filterEnabled": False}}
            if kind == "GetInputVolume":
                return {**ok, "responseData": {"inputVolumeDb": -1.0}}
            return ok
        with mock.patch.object(obs_client, "request", fake):
            toggled = obs_client.execute_obs_action("filter_toggle", {"source_name": "Cam", "filter_name": "Color"})
            louder = obs_client.execute_obs_action("input_volume_up", {"source_name": "Mic"})
            refreshed = obs_client.execute_obs_action("source_refresh", {"source_name": "Alertas"})
        self.assertEqual((toggled["active"], louder["db"], refreshed["success"]), (True, 2.0, True))  # -1 dB + 3: OBS allows above 0
        self.assertIn(("SetSourceFilterEnabled", {"sourceName": "Cam", "filterName": "Color", "filterEnabled": True}), sent)
        self.assertIn(("PressInputPropertiesButton", {"inputName": "Alertas", "propertyName": "refreshnocache"}), sent)

    def test_a_webhook_can_use_put_with_a_body(self):
        from server import webhooks
        self.assertEqual(webhooks.validate_extra({"method": "put", "body": '{"on": 1}'}), {"method": "PUT", "body": '{"on": 1}'})
        with self.assertRaises(ValueError):
            webhooks.validate_extra({"method": "DELETE"})

    def test_media_volume_keys_are_allowed(self):
        from server.action_catalog import validate_action
        for key in ("volume_up", "volume_down"):
            self.assertEqual(validate_action("media", key)["target"], key)


    def test_power_is_off_until_the_user_switches_it_on(self):
        from server.connectors import windows
        windows.set_power_enabled(False)
        calls = []
        with mock.patch.object(windows, "_run", lambda c: calls.append(c) or mock.Mock(returncode=0, stdout="", stderr="")):
            for mode in ("shutdown", "restart", "logoff", "hibernate"):
                result = windows.execute("power", {"mode": mode, "delay": 15})
                self.assertFalse(result["success"], mode)
                self.assertIn("Ajustes", result["error"])
            self.assertFalse(windows.execute("power", {"mode": "sleep", "delay": 0})["success"])
            self.assertTrue(windows.execute("power", {"mode": "cancel", "delay": 0})["success"])  # cancelling is always allowed
        self.assertEqual(calls, [["shutdown", "/a"]])

    def test_a_shutdown_always_leaves_time_to_cancel_it(self):
        from server.connectors import windows
        windows.set_power_enabled(True)
        self.addCleanup(windows.set_power_enabled, False)
        calls = []
        with mock.patch.object(windows, "_run", lambda c: calls.append(c) or mock.Mock(returncode=0, stdout="", stderr="")):
            windows.execute("power", {"mode": "shutdown", "delay": 0})
        self.assertEqual(calls, [["shutdown", "/s", "/t", "10"]])

    def test_power_plan_names_with_parentheses_inside_are_whole(self):
        from server.connectors import windows
        line = "GUID de plan de energía: 381b4222-f694-41f0-9685-ff5bb260df2e  (Alto rendimiento (AMD)) *"
        with mock.patch.object(windows, "_run", return_value=mock.Mock(returncode=0, stdout=line + chr(10), stderr="")):
            plans = windows.list_power_plans()
        self.assertEqual([(p["name"], p["active"]) for p in plans], [("Alto rendimiento (AMD)", True)])

    def test_screenshots_have_a_cooldown(self):
        from server.connectors import windows
        windows._last_screenshot = 0.0
        fake = mock.MagicMock()
        with mock.patch.dict("sys.modules", {"PIL.ImageGrab": fake}), mock.patch("PIL.ImageGrab.grab", create=True) as grab,                 mock.patch.object(windows.os, "makedirs"):
            first = windows.screenshot()
            second = windows.screenshot()
        self.assertTrue(first["success"])
        self.assertFalse(second["success"])
        self.assertEqual(grab.call_count, 1)

    def test_obs_volume_steps_stay_inside_obs_range_and_events_are_not_answers(self):
        from server.obs_client import obs_client
        sent = []

        def fake(kind, data=None):
            sent.append((kind, data))
            ok = {"requestStatus": {"result": True}}
            return {**ok, "responseData": {"inputVolumeDb": 6.0}} if kind == "GetInputVolume" else ok
        with mock.patch.object(obs_client, "request", fake):
            result = obs_client.execute_obs_action("input_volume_up", {"source_name": "Mic"})
        self.assertEqual(result["db"], 9.0)  # from +6 dB up, never down to 0
