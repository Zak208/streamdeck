import asyncio
import json
import os
import time
import unittest
import urllib.request
from unittest import mock

import support
import websockets
from server import main
from server.obs_client import OBS_UNREACHABLE, OBSClient
from server.paths import STATIC_DIR, VERSION

STATIC_ENDPOINTS = [
    ("/api/info", ["version", "server_ip", "port", "direct_url", "studio_url"]),
    ("/api/auth/pin", ["pin", "qr_code", "ip", "port"]),
    ("/api/config", ["deck_name", "layout", "slots", "pages"]),
    ("/api/deck/config", ["deck_name", "layout", "slots", "pages"]),
    ("/api/audio/sessions", ["master", "sessions"]),
    ("/api/system/apps", ["apps"]),
    ("/manifest.json", ["icons", "start_url", "display"]),
    ("/service-worker.js", None),
    ("/studio", None),
    ("/", None),
    ("/static/icons/icon-192.png", None),
    ("/static/icons/icon-512.png", None),
]


def get(url: str):
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read()


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


async def receive_until(ws, predicate, timeout: float = 5.0):
    """Read messages until one satisfies the predicate; fail the test on timeout."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError("expected message never arrived")
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
        if predicate(message):
            return message


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def setUp(self):
        main.button_states.clear()
        main._running_actions.clear()

    def ws_url(self):
        return f"ws://127.0.0.1:{self.live.port}/ws"

    def test_endpoints_respond_and_expose_the_6x2_grid(self):
        for path, keys in STATIC_ENDPOINTS:
            with self.subTest(path=path):
                status, body = get(self.live.base_url + path)
                self.assertEqual(status, 200)
                if keys:
                    data = json.loads(body)
                    for key in keys:
                        self.assertIn(key, data)
                    if path in ("/api/config", "/api/deck/config"):
                        self.assertEqual(data["layout"], {"rows": 2, "columns": 6, "total_slots": 12})
                        self.assertEqual(len(data["slots"]), 12)

    def test_version_comes_from_one_place(self):
        _, body = get(self.live.base_url + "/api/info")
        self.assertEqual(json.loads(body)["version"], VERSION)
        with open(os.path.join(os.path.dirname(STATIC_DIR), "installer", "setup.iss"), encoding="utf-8") as iss:
            self.assertIn(f'#define MyAppVersion "{VERSION}"', iss.read())

    def test_pwa_assets_cache_the_icons(self):
        with open(os.path.join(STATIC_DIR, "service-worker.js"), encoding="utf-8") as worker:
            content = worker.read()
        self.assertIn("icon-192.png", content)
        self.assertIn("icon-512.png", content)

    def test_page_switch_round_trip(self):
        result = post_json(f"{self.live.base_url}/api/deck/page/switch", {"page_index": 1})
        self.assertEqual(result["current_page"], 1)
        result = post_json(f"{self.live.base_url}/api/deck/page/switch", {"page_index": 0})
        self.assertEqual(result["current_page"], 0)

    def test_check_update_never_claims_an_update_without_a_git_checkout(self):
        with mock.patch.object(main, "_is_git_checkout", return_value=False):
            _, body = get(self.live.base_url + "/api/system/check-update")
        data = json.loads(body)
        self.assertFalse(data["update_available"])
        self.assertFalse(data["can_update"])

    def test_slow_action_does_not_block_other_messages(self):
        def slow_action(*_args):
            time.sleep(1.5)
            return {"success": True}

        async def scenario():
            async with websockets.connect(self.ws_url()) as ws:
                await receive_until(ws, lambda m: m["type"] == "init_state")
                await ws.send(json.dumps({"type": "trigger_button", "id": "btn_play"}))
                started = time.monotonic()
                await ws.send(json.dumps({"type": "refresh_sessions"}))
                await receive_until(ws, lambda m: m["type"] == "sessions_update", timeout=1.2)
                self.assertLess(time.monotonic() - started, 1.2)
                result = await receive_until(ws, lambda m: m["type"] == "action_result")
                self.assertTrue(result["success"])
                self.assertEqual(result["slot_id"], "btn_play")

        with mock.patch.object(main, "execute_action", slow_action):
            asyncio.run(scenario())

    def test_failed_action_reports_the_reason_to_the_phone(self):
        async def scenario():
            async with websockets.connect(self.ws_url()) as ws:
                await receive_until(ws, lambda m: m["type"] == "init_state")
                await ws.send(json.dumps({"type": "trigger_button", "id": "btn_play"}))
                return await receive_until(ws, lambda m: m["type"] == "action_result")

        failing = mock.Mock(return_value={"success": False, "error": "OBS no responde"})
        with mock.patch.object(main, "execute_action", failing):
            result = asyncio.run(scenario())
        self.assertIs(result["success"], False)
        self.assertEqual(result["message"], "OBS no responde")

    def test_double_tap_runs_the_action_once(self):
        calls = []

        def counting_action(*_args):
            calls.append(1)
            time.sleep(0.6)
            return {"success": True}

        async def scenario():
            async with websockets.connect(self.ws_url()) as ws:
                await receive_until(ws, lambda m: m["type"] == "init_state")
                for _ in range(3):
                    await ws.send(json.dumps({"type": "trigger_button", "id": "btn_play"}))
                await receive_until(ws, lambda m: m["type"] == "action_result")
                await asyncio.sleep(0.2)

        with mock.patch.object(main, "execute_action", counting_action):
            asyncio.run(scenario())
        self.assertEqual(len(calls), 1)

    def test_toggle_state_is_broadcast_and_remembered_for_new_phones(self):
        toggle = mock.Mock(return_value={"success": True, "action": "obs_record_toggle", "outputActive": True})

        async def scenario():
            async with websockets.connect(self.ws_url()) as ws:
                await receive_until(ws, lambda m: m["type"] == "init_state")
                await ws.send(json.dumps({"type": "trigger_button", "id": "btn_play"}))
                state = await receive_until(ws, lambda m: m["type"] == "button_state")
            async with websockets.connect(self.ws_url()) as late_ws:
                init = await receive_until(late_ws, lambda m: m["type"] == "init_state")
            return state, init

        with mock.patch.object(main, "execute_action", toggle):
            state, init = asyncio.run(scenario())
        self.assertEqual((state["id"], state["active"]), ("btn_play", True))
        self.assertEqual(init["button_states"], {"btn_play": True})

    def test_per_app_volume_changes_on_the_pc_reach_the_phone(self):
        def audio(volume):
            return {
                "master": {"volume": 50, "muted": False},
                "sessions": [{"id": "x_1", "process_name": "Spotify.exe", "display_name": "Spotify",
                              "pid": 1, "volume": volume, "muted": False}],
            }

        current = {"state": audio(40)}

        async def scenario():
            async with websockets.connect(self.ws_url()) as ws:
                await receive_until(ws, lambda m: m["type"] == "init_state")
                current["state"] = audio(80)  # master untouched: only the app fader moved
                return await receive_until(
                    ws,
                    lambda m: m["type"] == "audio_state" and m["sessions"][0]["volume"] == 80,
                    timeout=4,
                )

        with mock.patch.object(main, "read_audio_state", lambda: current["state"]):
            message = asyncio.run(scenario())
        self.assertEqual(message["master"]["volume"], 50)


class AudioSignatureTests(unittest.TestCase):
    def state(self, app_volume, muted=False):
        return {
            "master": {"volume": 50, "muted": False},
            "sessions": [{"process_name": "Discord.exe", "volume": app_volume, "muted": muted}],
        }

    def test_signature_changes_for_app_volume_and_mute_but_not_for_noise(self):
        base = main.audio_signature(self.state(30))
        self.assertEqual(base, main.audio_signature(self.state(30)))
        self.assertNotEqual(base, main.audio_signature(self.state(31)))
        self.assertNotEqual(base, main.audio_signature(self.state(30, muted=True)))


class OBSClientTests(unittest.TestCase):
    def test_unreachable_obs_is_reported_as_a_failure_with_a_clear_reason(self):
        client = OBSClient(port=support.free_port())

        async def run_in_worker_thread():
            return await asyncio.to_thread(client.execute_obs_action, "record_toggle")

        result = asyncio.run(run_in_worker_thread())
        self.assertIs(result["success"], False)
        self.assertEqual(result["error"], OBS_UNREACHABLE)

    def test_unknown_action_is_rejected(self):
        self.assertIs(OBSClient(port=support.free_port()).execute_obs_action("explode")["success"], False)


if __name__ == "__main__":
    unittest.main()
