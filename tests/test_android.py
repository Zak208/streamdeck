"""The Android app: what the PC offers it (identity, proof of pairing, download link) and that its project builds.

The APK build was broken for three releases because the manifest named launcher icons that did not exist, and
nobody noticed until a phone could not download the app. The file checks below catch that class of mistake here.
"""

import hashlib
import hmac
import json
import os
import re
import unittest
import urllib.error
import urllib.request

import support
from server.auth import SERVER_ID_FILE, auth_manager
from server.paths import ANDROID_APK_URL, VERSION

ANDROID = os.path.join(support.PROJECT_ROOT, "android")
RES = os.path.join(ANDROID, "app", "src", "main", "res")


def read(*parts: str) -> str:
    with open(os.path.join(support.PROJECT_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode())


class AndroidProjectTests(unittest.TestCase):
    def test_every_resource_the_manifest_names_exists(self):
        manifest = read("android", "app", "src", "main", "AndroidManifest.xml")
        for kind, name in re.findall(r"@(mipmap|drawable|style|string)/([A-Za-z0-9_.]+)", manifest):
            if kind in ("mipmap", "drawable"):
                found = [
                    f for folder in os.listdir(RES) if folder.startswith(kind)
                    for f in os.listdir(os.path.join(RES, folder)) if os.path.splitext(f)[0] == name
                ]
                self.assertTrue(found, f"@{kind}/{name} is named in the manifest but missing in res/")
            elif kind == "string":
                self.assertIn(f'name="{name}"', read("android", "app", "src", "main", "res", "values", "strings.xml"))
            elif kind == "style":
                self.assertIn(f'name="{name}"', read("android", "app", "src", "main", "res", "values", "styles.xml"))

    def test_launcher_icons_exist_in_every_density(self):
        for density in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
            for name in ("ic_launcher.png", "ic_launcher_round.png"):
                self.assertTrue(os.path.exists(os.path.join(RES, f"mipmap-{density}", name)), f"{density}/{name}")

    def test_the_layout_ids_the_activity_uses_are_declared(self):
        layout = read("android", "app", "src", "main", "res", "layout", "activity_main.xml")
        code = read("android", "app", "src", "main", "java", "com", "zak208", "streamdesk", "MainActivity.java")
        for view_id in re.findall(r"R\.id\.(\w+)", code):
            self.assertIn(f'@+id/{view_id}"', layout, view_id)

    def test_the_app_version_follows_the_pc_version(self):
        gradle = read("android", "app", "build.gradle")
        self.assertIn(f'versionName "{VERSION}"', gradle)
        major, minor, patch = (int(part) for part in VERSION.split("."))
        self.assertIn(f"versionCode {major * 10000 + minor * 100 + patch}", gradle)

    def test_the_signing_key_comes_from_secrets_and_never_from_the_repository(self):
        gradle = read("android", "app", "build.gradle")
        self.assertIn("System.getenv('STREAMDESK_KEYSTORE')", gradle)
        self.assertIn("System.getenv('STREAMDESK_KEYSTORE_PASSWORD')", gradle)
        self.assertNotIn("storePassword '", gradle)  # no password written in the file
        workflow = read(".github", "workflows", "build-apk.yml")
        for secret in ("ANDROID_KEYSTORE_BASE64", "ANDROID_KEYSTORE_PASSWORD"):
            self.assertIn(f"secrets.{secret}", workflow)
        self.assertIn("*.keystore", read(".gitignore"))
        tracked = [f for _, _, files in os.walk(ANDROID) for f in files if f.endswith((".keystore", ".jks"))]
        self.assertEqual(tracked, [], "a signing key must not sit in the project folder")

    def test_download_link_matches_the_file_the_workflow_publishes(self):
        self.assertTrue(ANDROID_APK_URL.endswith("/releases/latest/download/StreamDesk.apk"))
        self.assertIn(f'ANDROID_APK_URL = "{ANDROID_APK_URL}"', read("static", "js", "phone-settings.js"))
        self.assertIn("StreamDesk.apk", read(".github", "workflows", "build-apk.yml"))


class IdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def test_identity_is_public_and_stable(self):
        first = get_json(self.live.base_url + "/api/identity")
        self.assertEqual(first["app"], "streamdesk")
        self.assertEqual(first["version"], VERSION)
        self.assertEqual(first["id"], auth_manager.server_id)
        self.assertEqual(first["id"], get_json(self.live.base_url + "/api/identity")["id"])
        self.assertTrue(os.path.exists(SERVER_ID_FILE))
        self.assertNotIn("proof", first)
        self.assertNotIn("token", json.dumps(first).lower())

    def test_a_new_manager_keeps_the_id_of_the_profile(self):
        from server.auth import AuthManager
        self.assertEqual(AuthManager().server_id, auth_manager.server_id)

    def test_pairing_returns_the_id_and_the_pc_proves_it_knows_the_token(self):
        paired = auth_manager.verify_pin_and_issue_token(auth_manager.current_pin, "Test phone", "10.0.0.5")
        self.assertEqual(paired["server_id"], auth_manager.server_id)
        token = paired["token"]
        device = hashlib.sha256(token.encode()).hexdigest()[:12]
        nonce = "ab" * 16
        answer = get_json(f"{self.live.base_url}/api/identity?device={device}&nonce={nonce}")
        expected = hmac.new(token.encode(), nonce.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(answer["proof"], expected)
        self.assertNotIn(token, json.dumps(answer))

    def test_an_unknown_device_or_bad_nonce_gets_no_proof(self):
        for query in ("device=000000000000&nonce=" + "ab" * 16, "device=zz&nonce=ab", "device=" + "a" * 12 + "&nonce=XYZ"):
            self.assertNotIn("proof", get_json(f"{self.live.base_url}/api/identity?{query}"))

    def test_the_download_link_is_only_for_studio(self):
        data = get_json(self.live.base_url + "/api/app/android")
        self.assertEqual(data["url"], ANDROID_APK_URL)
        self.assertTrue(data["qr_code"].startswith("data:image/png;base64,"))
        request = urllib.request.Request(self.live.base_url + "/api/app/android", headers={"Host": "192.168.1.50:48291"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
