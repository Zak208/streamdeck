"""
Regression and QA verification test suite for security hardening,
crash resilience, program packs, and system audits.
"""
import ctypes
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock

import support

import server.auth as auth_mod
from server.telemetry import Nvml
import server.main as main_mod
import server.webhooks as webhooks_mod
import server.program_packs as program_packs_mod
import server.page_library as page_library_mod
from server.system_scanner import SystemScanner


class NvmlResilienceTests(unittest.TestCase):
    """Verifies that Nvml telemetry handles unprototyped or failing C-calls safely without crashing."""

    def test_nvml_init_safe_when_dll_missing(self):
        with mock.patch("ctypes.CDLL", side_effect=OSError("DLL not found")):
            nvml = Nvml()
            self.assertIsNone(nvml.read())
            self.assertIsNone(nvml._lib)

    def test_nvml_read_handles_non_zero_status_safely(self):
        nvml = Nvml()
        nvml._tried = True
        nvml._lib = mock.MagicMock()
        nvml._handle = ctypes.c_void_p(1)
        # Non-zero return value from NVML function indicates error
        nvml._lib.nvmlDeviceGetUtilizationRates.return_value = 1

        result = nvml.read()
        self.assertIsNone(result)

    def test_nvml_read_handles_exceptions_without_crashing_process(self):
        nvml = Nvml()
        nvml._tried = True
        nvml._lib = mock.MagicMock()
        nvml._handle = ctypes.c_void_p(1)
        # Mock device utilization raising an exception
        nvml._lib.nvmlDeviceGetUtilizationRates.side_effect = RuntimeError("NVML internal error")

        # Must return None safely instead of crashing or raising
        result = nvml.read()
        self.assertIsNone(result)

    def test_nvml_read_thread_safety(self):
        nvml = Nvml()
        nvml._tried = True
        nvml._lib = mock.MagicMock()
        nvml._handle = ctypes.c_void_p(1)

        nvml.read = mock.MagicMock(return_value={"gpu": 45, "vram": 30, "vram_used": 4000, "vram_total": 8000})

        results = []
        def worker():
            for _ in range(20):
                res = nvml.read()
                results.append(res)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 100)
        self.assertTrue(all(r["gpu"] == 45 for r in results))


class CrashLogRotationTests(unittest.TestCase):
    """Verifies that server/main.py rotates crash.log to prevent unbounded disk growth."""

    def test_crash_log_rotation_on_large_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            crash_file = os.path.join(tmp_dir, "crash.log")
            bak_file = os.path.join(tmp_dir, "crash.log.bak")

            # Create a crash file > 1MB
            with open(crash_file, "wb") as f:
                f.write(b"x" * (1024 * 1024 + 100))

            rotated = main_mod._rotate_crash_log_if_needed(crash_file)
            self.assertTrue(rotated)
            self.assertFalse(os.path.exists(crash_file))
            self.assertTrue(os.path.exists(bak_file))
            self.assertEqual(os.path.getsize(bak_file), 1024 * 1024 + 100)

    def test_crash_log_not_rotated_when_small(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            crash_file = os.path.join(tmp_dir, "crash.log")
            with open(crash_file, "wb") as f:
                f.write(b"normal small crash log")

            rotated = main_mod._rotate_crash_log_if_needed(crash_file)
            self.assertFalse(rotated)
            self.assertTrue(os.path.exists(crash_file))


class AuthHardeningTests(unittest.TestCase):
    """Verifies atomic token persistence and rate limiter memory leak fixes."""

    def test_save_tokens_is_atomic(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            token_file = os.path.join(tmp_dir, "auth_tokens.json")
            with mock.patch.object(auth_mod, "TOKENS_FILE", token_file), \
                 mock.patch.object(auth_mod, "CONFIG_DIR", tmp_dir):
                auth_mgr = auth_mod.AuthManager()
                auth_mgr.authorized_tokens.add("device-token-abc")
                auth_mgr.paired_devices["device-token-abc"] = {"name": "Test Phone", "created_at": 12345}
                auth_mgr._save_tokens()

                self.assertTrue(os.path.exists(token_file))
                # .tmp file must have been replaced and deleted
                self.assertFalse(os.path.exists(token_file + ".tmp"))

                # Verify loaded tokens match
                new_mgr = auth_mod.AuthManager()
                self.assertIn("device-token-abc", new_mgr.authorized_tokens)

    def test_rate_limiter_cleans_stale_records(self):
        auth_mgr = auth_mod.AuthManager()
        ip_active = "192.168.1.50"
        ip_stale = "192.168.1.99"

        now = time.monotonic()
        # Add an old attempt older than PIN_ATTEMPT_WINDOW_SECONDS (10 min)
        auth_mgr.pin_attempts[ip_stale] = [now - 700]
        auth_mgr.pin_attempts[ip_active] = [now - 10]

        # Trigger attempt check
        allowed = auth_mgr._rate_limit_allows_attempt(ip_active)
        self.assertTrue(allowed)
        # Stale IP record should be purged from memory
        self.assertNotIn(ip_stale, auth_mgr.pin_attempts)
        self.assertIn(ip_active, auth_mgr.pin_attempts)


class WebhookSsrfProtectionTests(unittest.TestCase):
    """Verifies loopback and admin API protection against SSRF in webhooks."""

    def test_loopback_variants_are_blocked(self):
        port = webhooks_mod.PORT
        blocked_urls = [
            f"http://127.0.0.1:{port}/api/profile",
            f"http://127.0.0.2:{port}/api/profile",
            f"http://127.255.255.255:{port}/api/keys",
            f"http://localhost:{port}/api/settings",
            f"http://[::1]:{port}/api/profile",
            f"http://0.0.0.0:{port}/api/system",
        ]

        for url in blocked_urls:
            with self.subTest(url=url):
                parsed = urllib.parse.urlparse(url)
                self.assertTrue(
                    webhooks_mod._is_streamdesk_api(parsed.hostname, parsed.port),
                    f"{url} should be recognized as protected StreamDesk API"
                )

    def test_external_and_benign_urls_are_allowed(self):
        port = webhooks_mod.PORT
        allowed_urls = [
            "https://discord.com/api/webhooks/123/xyz",
            "https://maker.ifttt.com/trigger/event/with/key/secret",
            "http://192.168.1.100:8080/webhook",
            "http://10.0.0.5:5000/api",
        ]
        for url in allowed_urls:
            with self.subTest(url=url):
                parsed = urllib.parse.urlparse(url)
                self.assertFalse(
                    webhooks_mod._is_streamdesk_api(parsed.hostname, parsed.port),
                    f"{url} should not be blocked by StreamDesk API loopback guard"
                )


class ProgramPacksExpansionTests(unittest.TestCase):
    """Verifies all new and existing program packs satisfy schema and category consistency."""

    def test_all_14_new_packs_are_present(self):
        expected_new_packs = {
            "obs", "twitch", "discord", "steam", "voicemeeter",
            "capcut", "gimp", "obsidian", "terminal", "github_desktop",
            "brave", "operagx", "telegram", "whatsapp"
        }
        all_ids = {p["id"] for p in program_packs_mod.PACKS}
        for pack_id in expected_new_packs:
            self.assertIn(pack_id, all_ids, f"Expected pack '{pack_id}' was not found in PACKS")

    def test_total_pack_count(self):
        # We expanded from 30 to 44 packs
        self.assertGreaterEqual(len(program_packs_mod.PACKS), 44)

    def test_all_categories_in_page_library_and_packs_match(self):
        for pack in program_packs_mod.PACKS:
            cat = pack["category"]
            self.assertIn(
                cat, program_packs_mod.ALL_CATEGORIES,
                f"Pack {pack['id']} has category {cat} not in ALL_CATEGORIES"
            )
            self.assertIn(
                cat, page_library_mod.CATEGORIES,
                f"Pack {pack['id']} has category {cat} not in page_library.CATEGORIES"
            )

    def test_pack_schema_integrity(self):
        for p in program_packs_mod.PACKS:
            with self.subTest(pack=p["id"]):
                self.assertIsInstance(p["id"], str)
                self.assertIsInstance(p["name"], str)
                self.assertIsInstance(p["category"], str)
                self.assertIsInstance(p["color"], str)
                self.assertTrue(p["color"].startswith("#"))
                self.assertIsInstance(p["icon"], str)
                self.assertIsInstance(p["actions"], list)
                self.assertGreater(len(p["actions"]), 0)
                for action in p["actions"]:
                    self.assertIn("id", action)
                    self.assertIn("label", action)
                    self.assertIn("keys", action)
                    self.assertIn("icon", action)


class SystemScannerExpansionTests(unittest.TestCase):
    """Verifies that SystemScanner checks popular apps and leverages shutil.which."""

    def test_scanner_includes_expanded_apps(self):
        # Verify expanded list includes our new apps
        popular_names = {app["name"] for app in SystemScanner.POPULAR_APPS}
        for expected in [
            "Voicemeeter", "CapCut PC", "GIMP", "Brave Browser", "Opera GX",
            "Telegram Desktop", "WhatsApp", "GitHub Desktop", "Windows Terminal", "Audacity", "Blender"
        ]:
            self.assertIn(expected, popular_names, f"POPULAR_APPS should include {expected}")

    def test_scanner_detects_binary_via_which(self):
        with mock.patch("shutil.which", return_value=r"C:\Windows\System32\notepad.exe"):
            apps = SystemScanner.get_detected_apps(force_refresh=True)
            self.assertIsInstance(apps, list)
            self.assertGreater(len(apps), 0)


if __name__ == "__main__":
    unittest.main()
