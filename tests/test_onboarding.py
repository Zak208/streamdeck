import json
import unittest
import urllib.request
import support

from server.main import app
from server.paths import VERSION
from server.settings_store import settings


class OnboardingApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = support.LiveServer()
        cls.server.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.server.__exit__(None, None, None)

    def setUp(self):
        # Clear app settings section for fresh test state
        settings.clear("app")

    def tearDown(self):
        settings.clear("app")

    def _get(self, path):
        req = urllib.request.Request(f"{self.server.base_url}{path}")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def _post(self, path, payload):
        req = urllib.request.Request(
            f"{self.server.base_url}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())

    def test_first_run_onboarding_status_and_completion(self):
        # On fresh start with no saved version and no first_run
        data = self._get("/api/system/onboarding")
        self.assertEqual(data["version"], VERSION)
        self.assertTrue(data["show_welcome"])
        self.assertFalse(data["show_update_tour"])
        self.assertIn("tour", data)
        self.assertEqual(len(data["tour"]["steps"]), 3)

        # Complete first run welcome
        res = self._post("/api/system/onboarding/complete", {"action": "welcome"})
        self.assertTrue(res["success"])
        self.assertEqual(res["version"], VERSION)

        # Subsequent check should not show welcome or update tour
        data2 = self._get("/api/system/onboarding")
        self.assertTrue(data2["first_run_completed"])
        self.assertEqual(data2["last_seen_version"], VERSION)
        self.assertFalse(data2["show_welcome"])
        self.assertFalse(data2["show_update_tour"])

    def test_update_tour_triggers_when_version_changed(self):
        # Simulate an existing user who completed first run on an older version
        settings.update("app", {
            "first_run_completed": True,
            "last_seen_version": "2.15.0",
        })

        data = self._get("/api/system/onboarding")
        self.assertFalse(data["show_welcome"])
        self.assertTrue(data["show_update_tour"])
        self.assertEqual(data["last_seen_version"], "2.15.0")
        self.assertEqual(data["version"], VERSION)

        # Complete tour
        res = self._post("/api/system/onboarding/complete", {"action": "update_tour"})
        self.assertTrue(res["success"])

        # Subsequent check should not show tour anymore
        data2 = self._get("/api/system/onboarding")
        self.assertFalse(data2["show_welcome"])
        self.assertFalse(data2["show_update_tour"])
        self.assertEqual(data2["last_seen_version"], VERSION)


if __name__ == "__main__":
    unittest.main()
