import asyncio
import copy
import json
import os
import time
import unittest
import urllib.request
from unittest import mock

import support
import websockets
from server import audit, logger, main
from server.config_manager import config_manager
from server.main import find_slot_in_deck


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
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError("expected message never arrived")
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=remaining))
        if predicate(message):
            return message


def _make_12_slots(button_slot: dict) -> list:
    slots = [button_slot]
    for i in range(1, 12):
        slots.append({"index": i, "type": "empty", "id": f"slot_{i}_{button_slot['id']}"})
    return slots


class TestLogsAndMultiPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def setUp(self):
        logger.clear()
        main.button_states.clear()
        main._running_actions.clear()

    def ws_url(self):
        return f"ws://127.0.0.1:{self.live.port}/ws"

    def test_logger_records_and_filters_levels(self):
        logger.clear()
        logger.info("TEST", "Información general", {"clave": "valor"})
        logger.warning("TEST", "Advertencia de prueba")
        logger.error("TEST", "Error crítico", {"codigo": 500})

        all_logs = logger.recent_logs(level="ALL")
        self.assertGreaterEqual(len(all_logs), 3)

        error_logs = logger.recent_logs(level="ERROR")
        self.assertTrue(all(e["level"] == "ERROR" for e in error_logs))
        self.assertTrue(any("Error crítico" in e["message"] for e in error_logs))

        warn_logs = logger.recent_logs(level="WARNING")
        self.assertTrue(all(e["level"] in ("WARNING", "ERROR") for e in warn_logs))

        info_logs = logger.recent_logs(level="INFO")
        self.assertTrue(any("Información general" in e["message"] for e in info_logs))

    def test_logger_file_and_clear(self):
        logger.clear()
        logger.error("TEST", "Fallo para probar archivo de log")
        text = logger.get_log_text(50)
        self.assertIn("Fallo para probar archivo de log", text)

        logger.clear()
        cleared_logs = logger.recent_logs(level="ALL")
        self.assertEqual(len(cleared_logs), 0)

    def test_find_slot_across_pages(self):
        original = copy.deepcopy(config_manager.get_config())
        self.addCleanup(lambda: config_manager.save_config(original))

        btn_p0 = {"index": 0, "type": "button", "id": "btn_discord_mute", "label": "Mute", "action_type": "discord_hotkey", "target": "mute", "extra": {"hotkey": "CTRL+SHIFT+M"}}
        btn_p1 = {"index": 0, "type": "button", "id": "btn_spotify_play", "label": "Play/Pausa", "action_type": "media", "target": "play_pause", "extra": {"app": "spotify"}}

        slots_0 = _make_12_slots(btn_p0)
        slots_1 = _make_12_slots(btn_p1)

        test_config = {
            "schema_version": 2,
            "deck_name": "Test Deck",
            "layout": {"rows": 2, "columns": 6, "total_slots": 12},
            "current_page": 0,
            "pages": [
                {"id": "page_0", "name": "Discord", "slots": slots_0},
                {"id": "page_1", "name": "Spotify", "slots": slots_1}
            ],
            "slots": slots_0
        }
        self.assertTrue(config_manager.save_config(test_config), config_manager.last_error)
        config_manager.set_active_page(0)  # PC is on page 0 (Discord)

        # 1. Looking for page 0 button
        slot, p_idx, p_name = find_slot_in_deck("btn_discord_mute")
        self.assertIsNotNone(slot)
        self.assertEqual(slot["id"], "btn_discord_mute")
        self.assertEqual(p_idx, 0)
        self.assertEqual(p_name, "Discord")

        # 2. Looking for page 1 button (Spotify) WITHOUT specifying page: finds it on page 1!
        slot, p_idx, p_name = find_slot_in_deck("btn_spotify_play")
        self.assertIsNotNone(slot)
        self.assertEqual(slot["id"], "btn_spotify_play")
        self.assertEqual(p_idx, 1)
        self.assertEqual(p_name, "Spotify")

        # 3. Looking for page 1 button specifying page=1
        slot, p_idx, p_name = find_slot_in_deck("btn_spotify_play", requested_page=1)
        self.assertIsNotNone(slot)
        self.assertEqual(slot["id"], "btn_spotify_play")
        self.assertEqual(p_idx, 1)

        # 4. Button that does not exist anywhere
        slot, p_idx, p_name = find_slot_in_deck("btn_ghost")
        self.assertIsNone(slot)

    def test_api_logs_endpoints(self):
        logger.clear()
        logger.error("TEST_API", "Error visible en endpoint")

        status, body = get(self.live.base_url + "/api/logs?level=ERROR")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("logs", data)
        self.assertTrue(any("Error visible en endpoint" in l["message"] for l in data["logs"]))

        status, body_text = get(self.live.base_url + "/api/logs/file")
        self.assertEqual(status, 200)
        self.assertIn("Error visible en endpoint", body_text.decode("utf-8"))

        clear_res = post_json(self.live.base_url + "/api/logs/clear", {})
        self.assertTrue(clear_res.get("success"))

        status, body_after = get(self.live.base_url + "/api/logs")
        self.assertEqual(len(json.loads(body_after)["logs"]), 0)

    def test_websocket_executes_button_from_another_page(self):
        original = copy.deepcopy(config_manager.get_config())
        self.addCleanup(lambda: config_manager.save_config(original))

        btn_p0 = {"index": 0, "type": "button", "id": "btn_pc_active", "label": "PC Key", "action_type": "text", "target": "hola"}
        btn_p1 = {"index": 0, "type": "button", "id": "btn_mobile_spotify", "label": "Play Music", "action_type": "media", "target": "play_pause", "extra": {"app": "spotify"}}

        slots_0 = _make_12_slots(btn_p0)
        slots_1 = _make_12_slots(btn_p1)

        test_config = {
            "schema_version": 2,
            "deck_name": "Test MultiPage Deck",
            "layout": {"rows": 2, "columns": 6, "total_slots": 12},
            "current_page": 0,
            "pages": [
                {"id": "page_pc", "name": "PC Discord", "slots": slots_0},
                {"id": "page_mobile", "name": "Mobile Spotify", "slots": slots_1}
            ],
            "slots": slots_0
        }
        self.assertTrue(config_manager.save_config(test_config), config_manager.last_error)
        config_manager.set_active_page(0)  # PC active page is 0 (Discord)

        async def scenario():
            with mock.patch("server.main.execute_action", return_value={"success": True, "action": "media", "target": "play_pause"}):
                async with websockets.connect(self.ws_url()) as ws:
                    init_msg = await receive_until(ws, lambda m: m["type"] == "init_state")
                    self.assertIsNotNone(init_msg)

                    # Send trigger_button for btn_mobile_spotify (which is on page 1, while PC is on page 0!)
                    await ws.send(json.dumps({"type": "trigger_button", "id": "btn_mobile_spotify", "page": 1}))
                    result_msg = await receive_until(ws, lambda m: m["type"] == "action_result")

                    self.assertTrue(result_msg["success"], f"Action failed: {result_msg}")
                    self.assertEqual(result_msg["id"], "btn_mobile_spotify")

        asyncio.run(scenario())

        # Verify logger logged the button press and success
        recent = logger.recent_logs(level="INFO")
        self.assertTrue(any("Play Music" in l["message"] for l in recent))

        # Verify audit logged the success and page
        audit_entries = audit.recent(5)
        self.assertTrue(any(e["button"] == "Play Music" and e["ok"] and e.get("page") == "Mobile Spotify" for e in audit_entries))


if __name__ == "__main__":
    unittest.main()
