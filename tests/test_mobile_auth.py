import asyncio
import json
import os
import unittest
import urllib.request

import support
from server.auth import AuthManager, PIN_TTL_SECONDS, TOKENS_FILE, auth_manager
import websockets


def post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode())


class MobileAuthTests(unittest.TestCase):
    def test_tokens_live_in_the_isolated_data_dir(self):
        self.assertTrue(TOKENS_FILE.startswith(os.environ["STREAMDESK_DATA_DIR"]))

    def test_wrong_pin_is_rejected_and_right_pin_persists_a_token(self):
        bad = auth_manager.verify_pin_and_issue_token("000000_fake", client_ip="10.0.0.9")
        self.assertIs(bad["valid"], False)
        self.assertIn("error", bad)

        good = auth_manager.verify_pin_and_issue_token(auth_manager.current_pin, "Test Smartphone", "10.0.0.8")
        self.assertIs(good["valid"], True)
        token = good["token"]
        self.assertGreaterEqual(len(token), 20)

        with open(TOKENS_FILE, "r", encoding="utf-8") as saved:
            self.assertIn(token, json.load(saved)["authorized_tokens"])
        self.assertTrue(AuthManager().is_token_authorized(token), "a restart must keep the pairing")

    def test_a_pin_that_just_rotated_still_works_for_a_minute(self):
        manager = AuthManager()
        old = manager.current_pin
        manager.refresh_pin()
        self.assertNotEqual(old, manager.current_pin)
        self.assertTrue(manager.verify_pin_and_issue_token(old, "Typing during rotation", "10.1.1.1")["valid"])

    def test_an_old_pin_stops_working_after_the_grace_period(self):
        manager = AuthManager()
        old = manager.current_pin
        manager.refresh_pin()
        manager.previous_pin_until = 0  # grace period over
        result = manager.verify_pin_and_issue_token(old, "Too late", "10.1.1.2")
        self.assertIs(result["valid"], False)
        self.assertIn("caducado", result["error"])  # the phone is told to read the current PIN

    def test_pin_reports_its_remaining_life_and_rotates_when_it_runs_out(self):
        manager = AuthManager()
        self.assertTrue(0 < manager.pin_expires_in() <= PIN_TTL_SECONDS)
        before = manager.current_pin
        manager.pin_issued_at -= PIN_TTL_SECONDS + 1
        self.assertNotEqual(before, manager.get_current_pin())
        self.assertGreater(manager.pin_expires_in(), PIN_TTL_SECONDS - 5)

    def test_qr_code_is_a_png_data_url(self):
        self.assertTrue(auth_manager.generate_qr_base64(48291).startswith("data:image/png;base64,"))

    def test_http_pairing_then_websocket(self):
        with support.LiveServer() as server:
            result = post_json(f"{server.base_url}/api/auth/verify", {"pin": auth_manager.current_pin, "device_name": "iPhone"})
            self.assertTrue(result["success"])
            token = result["token"]

            with urllib.request.urlopen(f"{server.base_url}/api/auth/check?token={token}", timeout=3) as response:
                self.assertTrue(json.loads(response.read())["authorized"])
            with urllib.request.urlopen(f"{server.base_url}/api/auth/check?token=bad_fake_token", timeout=3) as response:
                self.assertFalse(json.loads(response.read())["authorized"])

            async def first_message():
                async with websockets.connect(f"ws://127.0.0.1:{server.port}/ws?token={token}") as ws:
                    return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))

            message = asyncio.run(first_message())
            self.assertEqual(message["type"], "init_state")
            self.assertIn("button_states", message)


if __name__ == "__main__":
    unittest.main()
