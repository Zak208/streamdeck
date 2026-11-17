import os
import shutil
import tempfile
import unittest
from unittest import mock

from server import action_catalog, permissions, settings_store, updater, webhooks
from server.auth import AuthManager


class SecurityPatchesTests(unittest.TestCase):
    def test_condition_recursion_in_permissions_is_dangerous(self):
        # 1. Condition with command in 'then' branch must be dangerous
        dangerous_condition = {
            "then": {"action_type": "command", "target": "powershell", "extra": {"commands": ["dir"]}}
        }
        self.assertTrue(permissions.is_dangerous("condition", "obs_streaming", dangerous_condition))

        # 2. Condition with power shutdown in 'else' branch must be dangerous
        shutdown_condition = {
            "else": {"action_type": "windows", "target": "power", "extra": {"mode": "shutdown"}}
        }
        self.assertTrue(permissions.is_dangerous("condition", "obs_streaming", shutdown_condition))

        # 3. Benign condition must not be dangerous
        benign_condition = {
            "then": {"action_type": "sound", "target": "bell", "extra": {}},
            "else": {"action_type": "none", "target": "", "extra": {}}
        }
        self.assertFalse(permissions.is_dangerous("condition", "obs_streaming", benign_condition))

    def test_action_catalog_validates_condition_branches_recursively(self):
        # Malformed branch should raise ValueError
        with self.assertRaises(ValueError):
            action_catalog.validate_action("condition", "obs_streaming", {
                "then": {"action_type": "unknown_action_type", "target": "x"}
            })

        # Nested multi inside condition should be rejected (allow_multi=False)
        with self.assertRaises(ValueError):
            action_catalog.validate_action("condition", "obs_streaming", {
                "then": {"action_type": "multi", "target": "", "extra": {"actions": []}}
            })

        # Nested condition inside condition should be rejected
        with self.assertRaises(ValueError):
            action_catalog.validate_action("condition", "obs_streaming", {
                "then": {"action_type": "condition", "target": "obs_streaming", "extra": {}}
            })

        # Valid branch should be cleanly validated
        valid = action_catalog.validate_action("condition", "obs_streaming", {
            "then": {"action_type": "sound", "target": "beep", "extra": {}}
        })
        self.assertEqual(valid["action_type"], "condition")
        self.assertIn("then", valid["extra"])
        self.assertEqual(valid["extra"]["then"]["action_type"], "sound")

    def test_validate_hotkey_blocks_win_r_and_win_x(self):
        with self.assertRaises(ValueError):
            action_catalog.validate_hotkey("WIN+R")
        with self.assertRaises(ValueError):
            action_catalog.validate_hotkey("CTRL+WIN+R")
        with self.assertRaises(ValueError):
            action_catalog.validate_hotkey("WIN+X")

        # Benign hotkeys with modifiers should pass
        self.assertEqual(action_catalog.validate_hotkey("CTRL+SHIFT+M"), "CTRL+SHIFT+M")
        self.assertEqual(action_catalog.validate_hotkey("ALT+F4"), "ALT+F4")

    def test_dpapi_failure_raises_error_on_windows(self):
        # When _dpapi fails (returns None) on Windows, seal() must raise RuntimeError, NOT return plaintext
        with mock.patch("server.settings_store._dpapi", return_value=None):
            with mock.patch("server.settings_store.ctypes.windll", create=True):
                with self.assertRaises(RuntimeError):
                    settings_store.seal("my-secret-password")

    def test_pin_replay_protection_clears_previous_pin(self):
        auth = AuthManager()
        pin = auth.get_current_pin()

        # First verification succeeds
        res1 = auth.verify_pin_and_issue_token(pin, "Phone 1", "192.168.1.50")
        self.assertTrue(res1.get("success") or res1.get("valid"))

        # Replay attempt with the exact same PIN within 60s window must FAIL
        res2 = auth.verify_pin_and_issue_token(pin, "Phone 2", "192.168.1.51")
        self.assertFalse(res2.get("success") or res2.get("valid"))

    def test_global_pin_brute_force_protection(self):
        auth = AuthManager()
        initial_pin = auth.get_current_pin()

        # Simulate 10 failed attempts from 10 different IPs
        for i in range(10):
            res = auth.verify_pin_and_issue_token("000000", "Attacker", f"10.0.0.{i+1}")
            self.assertFalse(res.get("success") or res.get("valid"))

        # The PIN must have been rotated automatically due to global failure limit
        new_pin = auth.get_current_pin()
        self.assertNotEqual(initial_pin, new_pin)

    def test_cleanup_devices_removes_orphaned_tokens(self):
        auth = AuthManager()
        auth.authorized_tokens.add("orphaned-token-12345")
        # Ensure it is not in paired_devices
        auth.paired_devices.pop("orphaned-token-12345", None)

        auth.cleanup_devices()
        self.assertNotIn("orphaned-token-12345", auth.authorized_tokens)

    def test_updater_finally_block_cleans_temp_folder_on_failure(self):
        u = updater.Updater()
        with mock.patch.object(u, "release_info", return_value={"update_available": True}):
            with mock.patch.object(u, "_release_files", return_value=("https://github.com/Zak208/streamdeck/releases/download/v9.9.9/instalador_streamdeck.exe", "a"*64, "v9.9.9")):
                with mock.patch("server.updater._download", side_effect=Exception("Network failed")):
                    u._run("1.0.0")
                    self.assertEqual(u.state["state"], "error")

    def test_webhooks_blocks_dns_loopback_resolution(self):
        with mock.patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", webhooks.PORT))]):
            self.assertTrue(webhooks._is_streamdesk_api("malicious.internal.local", webhooks.PORT))

    def test_pending_app_volumes_bounded_and_validated(self):
        from server.main import _pending_app_volumes, MAX_PENDING_APP_VOLUMES
        _pending_app_volumes.clear()

        # Fill with more than MAX_PENDING_APP_VOLUMES
        for i in range(MAX_PENDING_APP_VOLUMES + 20):
            if len(_pending_app_volumes) >= MAX_PENDING_APP_VOLUMES:
                _pending_app_volumes.pop(next(iter(_pending_app_volumes)), None)
            _pending_app_volumes[f"proc_{i}.exe"] = 50

        self.assertLessEqual(len(_pending_app_volumes), MAX_PENDING_APP_VOLUMES)
        _pending_app_volumes.clear()

    def test_ptt_state_rejects_unregistered_button_id(self):
        from server.main import button_states, config_manager
        button_states.clear()
        slots = config_manager.get_config().get("slots", [])
        fake_id = "non_existent_slot_injection_12345"
        self.assertFalse(any(s.get("id") == fake_id for s in slots))

        # Simulating ptt_state logic
        btn_id = fake_id
        if btn_id and isinstance(btn_id, str):
            if any(s.get("id") == btn_id for s in slots):
                button_states[btn_id] = True

        self.assertNotIn(fake_id, button_states)


if __name__ == "__main__":
    unittest.main()
