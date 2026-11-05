"""Counters, timers, two-state keys, "Volver" and webhooks."""

import asyncio
import copy
import http.server
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

import support
import websockets
from server import live_buttons, main, webhooks
from server.action_catalog import validate_action, validate_deck_config
from server.config_manager import DEFAULT_CONFIG


def profile_with(**changes):
    profile = copy.deepcopy(DEFAULT_CONFIG)
    slot = next(s for s in profile["pages"][0]["slots"] if s["type"] == "button")
    slot.update(changes)
    return validate_deck_config(profile), slot["id"]


class ValidationTests(unittest.TestCase):
    def test_counter_timer_and_webhook(self):
        self.assertEqual(validate_action("counter", "INC", {"step": 5})["extra"], {"step": 5})
        self.assertEqual(validate_action("counter", "reset")["extra"], {"step": 1})
        self.assertEqual(validate_action("timer", "x", {"seconds": 90}), {"action_type": "timer", "target": "toggle", "extra": {"seconds": 90}})
        hook = validate_action("webhook", "http://192.168.1.20:8123/api/x", {"method": "post", "body": "{}"})
        self.assertEqual(hook["extra"], {"method": "POST", "body": "{}"})
        self.assertEqual(validate_action("webhook", "https://a.b/c", {"method": "GET", "body": "ignored"})["extra"], {"method": "GET", "body": ""})

    def test_what_is_refused(self):
        for action, target, extra in (
            ("counter", "mul", {}), ("counter", "inc", {"step": 0}), ("counter", "inc", {"step": True}), ("counter", "inc", {"step": 1001}),
            ("timer", "toggle", {"seconds": 0}), ("timer", "toggle", {"seconds": 86401}), ("timer", "toggle", {"seconds": "5"}),
            ("webhook", "ftp://x/y", {}), ("webhook", "http://u:p@x/y", {}), ("webhook", "http://x/y z", {}), ("webhook", "javascript:1", {}),
            ("webhook", "https://a.b", {"method": "DELETE"}), ("webhook", "https://a.b", {"method": "POST", "body": "x" * 1001}),
        ):
            with self.subTest(action=action, target=target, extra=extra), self.assertRaises(ValueError):
                validate_action(action, target, extra)

    def test_counters_and_timers_cannot_be_macro_steps_but_can_be_gestures(self):
        for action in ("counter", "timer"):
            with self.assertRaises(ValueError):
                validate_action("multi", "m", {"actions": [{"action_type": action, "target": "inc", "extra": {}}]})
        config, slot_id = profile_with(long_press={"action_type": "counter", "target": "reset"})
        slot = next(s for s in config["pages"][0]["slots"] if s.get("id") == slot_id)
        self.assertEqual(slot["long_press"]["action_type"], "counter")

    def test_page_back_is_a_page_target(self):
        self.assertEqual(validate_action("page", "BACK")["target"], "back")

    def test_two_state_keys(self):
        config, slot_id = profile_with(toggle=True, alt={"label": "Grabando", "sublabel": "pulsa para parar", "color": "#ef4444"})
        slot = next(s for s in config["pages"][0]["slots"] if s.get("id") == slot_id)
        self.assertIs(slot["toggle"], True)
        self.assertEqual((slot["alt"]["label"], slot["alt"]["color"]), ("Grabando", "#ef4444"))
        self.assertEqual(slot["alt"]["image"], slot["image"])  # unchanged parts fall back to the key's own
        for bad in ({"label": ""}, {"color": "red"}, {"image": "http://evil/x.png"}, {"label": "<b>"}, "texto", ["x"]):
            with self.subTest(alt=bad), self.assertRaises(ValueError):
                profile_with(toggle=True, alt=bad)
        with self.assertRaises(ValueError):
            profile_with(toggle="yes")


class CounterTests(unittest.TestCase):
    def test_it_adds_subtracts_resets_and_remembers(self):
        key = "counter_test_key"
        live_buttons.change_counter(key, "reset", 1)
        self.assertEqual(live_buttons.change_counter(key, "inc", 5), 5)
        self.assertEqual(live_buttons.change_counter(key, "dec", 2), 3)
        self.assertEqual(live_buttons.counter_value(key), 3)
        self.assertEqual(live_buttons.change_counter(key, "reset", 1), 0)

    def test_countdown_text(self):
        self.assertEqual(live_buttons.format_countdown(59), "00:59")
        self.assertEqual(live_buttons.format_countdown(600), "10:00")
        self.assertEqual(live_buttons.format_countdown(3661), "1:01:01")
        self.assertEqual(live_buttons.format_countdown(-3), "00:00")


class PhoneFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def setUp(self):
        main.button_states.clear()
        main.button_labels.clear()
        main._running_actions.clear()
        main._page_history.clear()

    def install(self, **changes):
        config = main.config_manager.get_config()
        profile = copy.deepcopy(config)
        self.slot = next(s for s in profile["pages"][profile["current_page"]]["slots"] if s["type"] == "button")
        for leftover in ("long_press", "double_tap", "confirm", "disabled", "toggle", "alt", "extra"):
            self.slot.pop(leftover, None)
        self.slot.update(changes)
        self.assertTrue(main.config_manager.save_config(validate_deck_config(profile)), main.config_manager.last_error)
        return self.slot["id"]

    def press(self, slot_id, wanted, count=1, timeout=6):
        """Press the key `count` times and collect the messages until a message of type `wanted` arrives."""
        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                init = json.loads(await ws.recv())
                seen = [init]
                for _ in range(count):
                    await ws.send(json.dumps({"type": "trigger_button", "id": slot_id}))
                    while True:
                        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
                        seen.append(message)
                        if message["type"] == "action_result":
                            break
                while not any(m["type"] == wanted for m in seen[1:]):
                    seen.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout)))
                return seen
        return asyncio.run(scenario())

    def test_a_counter_key_shows_and_keeps_its_value(self):
        slot_id = self.install(action_type="counter", target="inc", extra={"step": 2})
        live_buttons.change_counter(slot_id, "reset", 1)
        seen = self.press(slot_id, "button_label", count=2)
        labels = [m["sublabel"] for m in seen if m["type"] == "button_label"]
        self.assertEqual(labels[:2], ["2", "4"])
        results = [m for m in seen if m["type"] == "action_result"]
        self.assertTrue(all(r["success"] for r in results))
        init = self.press(slot_id, "action_result")[0]
        self.assertEqual(init["button_labels"][slot_id], "4")  # a phone that connects later still sees the value

    def test_a_timer_counts_down_lights_the_key_and_stops_on_a_second_tap(self):
        slot_id = self.install(action_type="timer", target="toggle", extra={"seconds": 30})

        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                await ws.recv()
                await ws.send(json.dumps({"type": "trigger_button", "id": slot_id}))
                seen = []
                while not (any(m["type"] == "button_label" and m["sublabel"] == "00:30" for m in seen) and any(m["type"] == "action_result" for m in seen)):
                    seen.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=5)))
                main._running_actions.discard(slot_id)
                await ws.send(json.dumps({"type": "trigger_button", "id": slot_id}))
                while not (any(m["type"] == "button_label" and m["sublabel"] is None for m in seen)
                           and any(m["type"] == "button_state" and not m["active"] for m in seen)):
                    seen.append(json.loads(await asyncio.wait_for(ws.recv(), timeout=5)))
                return seen
        seen = asyncio.run(scenario())
        self.assertTrue(any(m["type"] == "button_state" and m["active"] for m in seen))
        self.assertTrue(any(m["type"] == "button_state" and not m["active"] for m in seen))
        self.assertNotIn(slot_id, main._timers)

    def test_a_two_state_key_flips_on_every_successful_tap(self):
        slot_id = self.install(action_type="sound", target="beep", extra={}, toggle=True, alt={"label": "Encendido"})
        with mock.patch.object(main, "execute_action", return_value={"success": True}):
            first = self.press(slot_id, "button_state")
            main._running_actions.clear()
            second = self.press(slot_id, "button_state")
        self.assertTrue([m for m in first if m["type"] == "button_state"][-1]["active"])
        self.assertFalse([m for m in second if m["type"] == "button_state"][-1]["active"])

    def test_a_failed_tap_does_not_flip_it(self):
        slot_id = self.install(action_type="sound", target="beep", extra={}, toggle=True)
        with mock.patch.object(main, "execute_action", return_value={"success": False, "error": "no"}):
            seen = self.press(slot_id, "action_result")
        self.assertFalse(any(m["type"] == "button_state" for m in seen))

    def test_a_timer_whose_key_is_gone_from_the_profile_is_stopped(self):
        slot_id = self.install(action_type="timer", target="toggle", extra={"seconds": 30})

        async def scenario():
            with mock.patch.object(main.ws_manager, "broadcast", mock.AsyncMock()):
                await main.run_timer(slot_id, 30)
                self.assertIn(slot_id, main._timers)
                await main.prune_timers()
                self.assertIn(slot_id, main._timers)  # its key is still in the profile
                profile = copy.deepcopy(main.config_manager.get_config())
                for page in profile["pages"]:
                    for slot in page["slots"]:
                        if slot.get("id") == slot_id:
                            slot.update({"action_type": "sound", "target": "beep", "extra": {}})
                self.assertTrue(main.config_manager.save_config(validate_deck_config(profile)))
                await main.prune_timers()
                await asyncio.sleep(0.05)
                self.assertNotIn(slot_id, main._timers)
        asyncio.run(scenario())

    def test_back_returns_to_the_page_you_left(self):
        async def scenario():
            main.config_manager.set_active_page(0)
            with mock.patch.object(main.ws_manager, "broadcast", mock.AsyncMock()):
                await main.navigate_pages("next")
                self.assertEqual(main.config_manager.get_config()["current_page"], 1)
                await main.navigate_pages("next")
                self.assertEqual(main.config_manager.get_config()["current_page"], 2)
                self.assertTrue((await main.navigate_pages("back"))["success"])
                self.assertEqual(main.config_manager.get_config()["current_page"], 1)
                self.assertTrue((await main.navigate_pages("back"))["success"])
                self.assertEqual(main.config_manager.get_config()["current_page"], 0)
                self.assertFalse((await main.navigate_pages("back"))["success"])  # nothing left to go back to
        asyncio.run(scenario())


class _Hook(http.server.BaseHTTPRequestHandler):
    seen = []

    def do_GET(self):
        _Hook.seen.append(("GET", self.path, ""))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://evil.invalid/")
            self.end_headers()
        elif self.path == "/boom":
            self.send_response(500)
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _Hook.seen.append(("POST", self.path, self.rfile.read(length).decode()))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass


class WebhookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Hook)
        cls.host = f"127.0.0.1:{cls.server.server_port}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        webhooks.set_allowed_hosts([])

    def setUp(self):
        _Hook.seen.clear()
        webhooks.set_allowed_hosts([])

    def test_nothing_is_called_until_the_host_is_allowed(self):
        result = webhooks.run(f"http://{self.host}/x", {"method": "GET"})
        self.assertFalse(result["success"])
        self.assertIn("destinos permitidos", result["error"])
        self.assertEqual(_Hook.seen, [])

    def test_an_allowed_host_gets_the_call(self):
        webhooks.set_allowed_hosts([self.host.upper()])
        self.assertTrue(webhooks.run(f"http://{self.host}/luz?on=1", {"method": "GET"})["success"])
        result = webhooks.run(f"http://{self.host}/escena", {"method": "POST", "body": '{"a": 1}'})
        self.assertTrue(result["success"])
        self.assertEqual(_Hook.seen, [("GET", "/luz?on=1", ""), ("POST", "/escena", '{"a": 1}')])

    def test_another_port_or_host_is_not_the_allowed_one(self):
        webhooks.set_allowed_hosts([self.host])
        for url in (f"http://127.0.0.1:{self.server.server_port + 1}/x", "http://localhost:%d/x" % self.server.server_port):
            with self.subTest(url=url):
                self.assertFalse(webhooks.run(url, {"method": "GET"})["success"])
        self.assertEqual(_Hook.seen, [])

    def test_redirects_are_not_followed(self):
        webhooks.set_allowed_hosts([self.host])
        result = webhooks.run(f"http://{self.host}/redirect", {"method": "GET"})
        self.assertFalse(result["success"])
        self.assertIn("302", result["error"])

    def test_an_error_status_and_a_dead_host_are_reported(self):
        webhooks.set_allowed_hosts([self.host, "127.0.0.1:9"])
        self.assertIn("500", webhooks.run(f"http://{self.host}/boom", {"method": "GET"})["error"])
        self.assertFalse(webhooks.run("http://127.0.0.1:9/x", {"method": "GET"})["success"])

    def test_a_webhook_cannot_call_streamdesk_itself(self):
        from server.paths import PORT
        webhooks.set_allowed_hosts([f"localhost:{PORT}", f"127.0.0.1:{PORT}"])
        for host in (f"localhost:{PORT}", f"127.0.0.1:{PORT}"):
            result = webhooks.run(f"http://{host}/api/settings/webhooks", {"method": "POST", "body": "{}"})
            self.assertFalse(result["success"])
            self.assertIn("propio StreamDesk", result["error"])

    def test_ports_must_be_real(self):
        for bad in ("x:0", "x:65536", "x:99999"):
            with self.subTest(host=bad), self.assertRaises(ValueError):
                webhooks.set_allowed_hosts([bad])

    def test_the_allow_list_is_validated(self):
        self.assertEqual(webhooks.set_allowed_hosts([" Casa.Local:8123 ", "casa.local:8123", "192.168.1.5"]), ["casa.local:8123", "192.168.1.5"])
        for bad in ("nota-lista", [5], ["http://x"], ["a b"], ["x/y"], ["@x"], [""], ["a" * 300], ["x"] * 21, ["x:99999999"], [["x"]]):
            with self.subTest(bad=str(bad)[:20]), self.assertRaises(ValueError):
                webhooks.set_allowed_hosts(bad)


class SettingsEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        webhooks.set_allowed_hosts([])
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

    def test_the_list_starts_empty_and_only_valid_lists_are_saved(self):
        webhooks.set_allowed_hosts([])
        self.assertEqual(self.call("/api/settings/webhooks"), (200, {"hosts": []}))
        self.assertEqual(self.call("/api/settings/webhooks", {"hosts": ["casa.local:8123"]}), (200, {"hosts": ["casa.local:8123"]}))
        self.assertEqual(self.call("/api/settings/webhooks", {"hosts": ["http://x"]})[0], 422)
        self.assertEqual(self.call("/api/settings/webhooks", {})[0], 422)
        self.assertEqual(self.call("/api/settings/webhooks")[1], {"hosts": ["casa.local:8123"]})

    def test_the_list_is_not_part_of_an_exported_profile_or_changeable_through_it(self):
        webhooks.set_allowed_hosts(["casa.local"])
        self.assertNotIn("casa.local", json.dumps(self.call("/api/profile/export")[1]))
        profile = self.call("/api/config")[1]
        profile["webhooks"] = {"hosts": ["evil.example"]}
        self.call("/api/config", profile)
        self.assertEqual(webhooks.allowed_hosts(), ["casa.local"])

    def test_the_routes_are_guarded_like_the_others(self):
        paths = {route.path: route for route in main.app.routes if hasattr(route, "path")}
        for path in ("/api/settings/webhooks",):
            deps = [d.call.__name__ for d in paths[path].dependant.dependencies]
            self.assertIn("require_local_request", deps)


if __name__ == "__main__":
    unittest.main()
