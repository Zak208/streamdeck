"""Tests for the 2.19 improvements: secrets on disk, limited phones, idle tokens, the action log, the connection
checks, the profile copy folder, the page security headers and the report for support."""

import asyncio
import copy
import gzip
import json
import os
import re
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock

import websockets

import support
from server import audit, firewall, main, permissions
from server import settings_store
from server.auth import AuthManager, TOKEN_IDLE_DAYS
from server.config_manager import config_manager
from server.paths import BASE_DIR, VERSION
from server.settings_store import SettingsStore, settings


def request(url, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})},
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


class SecretsOnDiskTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(prefix="sd-secrets-"), "settings.json")
        self.store = SettingsStore(self.path)

    def test_a_secret_is_encrypted_on_disk_and_read_back_whole(self):
        self.store.update("obs", {"host": "localhost", "password": "contraseña-ñ-123"})
        raw = open(self.path, encoding="utf-8").read()
        self.assertNotIn("contraseña", raw)
        self.assertIn("dpapi:", raw)
        self.assertIn("localhost", raw)  # what is not a secret stays readable
        self.assertEqual(self.store.get("obs")["password"], "contraseña-ñ-123")
        self.assertNotIn("password", self.store.public("obs"))
        self.assertTrue(self.store.public("obs")["password_set"])

    def test_a_file_from_an_older_version_with_plain_secrets_still_works(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"spotify": {"access_token": "plain-token"}}, handle)
        self.assertEqual(self.store.get("spotify")["access_token"], "plain-token")
        self.store.update("spotify", {"x": 1})  # the next save encrypts it
        self.assertNotIn("plain-token", open(self.path, encoding="utf-8").read())

    def test_a_secret_from_another_pc_comes_back_empty_instead_of_failing(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"obs": {"password": "dpapi:AAAAAAAA"}}, handle)
        self.assertEqual(self.store.get("obs")["password"], "")


class IdleTokenAndLimitTests(unittest.TestCase):
    def setUp(self):
        self.auth = AuthManager()
        self.addCleanup(self.auth.revoke_token, self.token())

    def token(self):
        if not hasattr(self, "_token"):
            self._token = self.auth.verify_pin_and_issue_token(self.auth.current_pin, "Móvil de prueba", "10.0.0.5")["token"]
        return self._token

    def test_a_phone_unused_for_months_is_unpaired(self):
        token = self.token()
        self.assertTrue(self.auth.is_token_authorized(token))
        self.auth.paired_devices[token]["last_seen"] = time.time() - (TOKEN_IDLE_DAYS + 1) * 86400
        self.assertFalse(self.auth.is_token_authorized(token))
        self.assertNotIn(token, self.auth.authorized_tokens)  # removed, not just refused

    def test_connecting_again_restarts_the_idle_clock(self):
        token = self.token()
        self.auth.paired_devices[token]["last_seen"] = time.time() - 40 * 86400
        self.auth.touch(token)
        self.assertGreater(self.auth.paired_devices[token]["last_seen"], time.time() - 60)

    def test_a_phone_paired_before_this_existed_gets_a_fresh_clock(self):
        token = self.token()
        del self.auth.paired_devices[token]["last_seen"]
        self.auth._save_tokens()
        reloaded = AuthManager()
        self.assertTrue(reloaded.is_token_authorized(token))
        self.assertGreater(reloaded.paired_devices[token]["last_seen"], time.time() - 60)

    def test_a_phone_can_be_limited_and_the_limit_lifted(self):
        token = self.token()
        device = AuthManager.device_id(token)
        self.assertFalse(self.auth.is_restricted(token))
        self.assertTrue(self.auth.set_restricted(device, True))
        self.assertTrue(self.auth.is_restricted(token))
        self.assertTrue(next(d for d in self.auth.list_devices() if d["id"] == device)["restricted"])
        self.assertFalse(self.auth.set_restricted("0" * 12, True))  # not a paired phone

    def test_pairing_tells_whoever_listens(self):
        heard = []
        self.auth.on_paired = heard.append
        second = self.auth.verify_pin_and_issue_token(self.auth.current_pin, "Tablet", "10.0.0.6")["token"]
        self.addCleanup(self.auth.revoke_token, second)
        self.assertEqual(heard, ["Tablet"])
        self.auth.on_paired = mock.Mock(side_effect=RuntimeError("no tray"))
        third = self.auth.verify_pin_and_issue_token(self.auth.current_pin, "Otro", "10.0.0.7")
        self.addCleanup(self.auth.revoke_token, third["token"])
        self.assertTrue(third["success"])  # a notification that fails does not undo the pairing


class PermissionTests(unittest.TestCase):
    def test_shutdown_and_console_commands_are_dangerous_but_cancelling_is_not(self):
        cases = [
            (("command", "x", {}), True),
            (("windows", "power", {"mode": "shutdown"}), True),
            (("windows", "power", {"mode": "sleep"}), True),
            (("windows", "power", {"mode": "cancel"}), False),
            (("windows", "mic_mute", {}), False),
            (("hotkey", "ctrl+c", {}), False),
            (("multi", "", {"actions": [{"action_type": "hotkey", "target": "a", "extra": {}},
                                        {"action_type": "command", "target": "x", "extra": {}}]}), True),
            (("multi", "", {"actions": [{"action_type": "hotkey", "target": "a", "extra": {}}]}), False),
            ((None, None, None), False),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.assertIs(permissions.is_dangerous(*args), expected)


class ActionLogTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp(prefix="sd-audit-")
        patcher = mock.patch.object(audit, "LOG_FILE", os.path.join(folder, "actions.log"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_it_records_who_pressed_what_and_newest_comes_first(self):
        audit.record("Móvil de Ana", "Apagar", "windows", False)
        audit.record("Móvil de Ana", "Silenciar", "windows", True, "long_press")
        entries = audit.recent()
        self.assertEqual([e["button"] for e in entries], ["Silenciar", "Apagar"])
        self.assertEqual(entries[0]["gesture"], "long_press")
        self.assertFalse(entries[1]["ok"])

    def test_it_never_stores_what_the_button_does(self):
        audit.record("Móvil", "Lanzar", "command", True)
        self.assertEqual(set(audit.recent()[0]), {"time", "device", "button", "action", "gesture", "ok"})

    def test_a_long_log_is_rotated_and_an_unreadable_one_is_empty(self):
        with mock.patch.object(audit, "MAX_BYTES", 200):
            for number in range(20):
                audit.record("Móvil", f"Botón {number}", "hotkey", True)
        self.assertTrue(os.path.exists(audit.LOG_FILE + ".bak"))
        self.assertEqual(audit.recent()[0]["button"], "Botón 19")
        with mock.patch.object(audit, "LOG_FILE", os.path.join(tempfile.gettempdir(), "no-such-folder-xyz", "a.log")):
            self.assertEqual(audit.recent(), [])


class ConnectionCheckTests(unittest.TestCase):
    def checks(self, **kw):
        values = {"rule": False, "profiles": [], "phone": False, "ip": "192.168.1.20"}
        values.update(kw)
        with mock.patch.object(firewall, "rule_exists", return_value=values["rule"]), \
                mock.patch.object(firewall, "network_categories", return_value=values["profiles"]):
            return {c["id"]: c for c in firewall.connection_checks(values["ip"], 48291, values["phone"])}

    def test_a_missing_rule_is_the_failure_and_offers_the_fix(self):
        checks = self.checks()
        self.assertEqual(checks["firewall"]["status"], "fail")
        self.assertEqual(checks["firewall"]["action"], "firewall")

    def test_a_phone_that_got_through_proves_the_way_is_open(self):
        checks = self.checks(phone=True)
        self.assertEqual(checks["firewall"]["status"], "ok")
        self.assertNotIn("phone", checks)

    def test_a_public_network_is_a_warning_not_a_failure(self):
        self.assertEqual(self.checks(rule=True, profiles=["Public"])["profile"]["status"], "warn")
        self.assertNotIn("profile", self.checks(rule=True, profiles=["Private"]))

    def test_no_network_is_reported(self):
        self.assertEqual(self.checks(ip="127.0.0.1")["network"]["status"], "fail")


class ProfileCopyTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="sd-copy-")
        self.addCleanup(settings.clear, "app")

    def test_every_save_is_copied_to_the_chosen_folder_and_old_daily_copies_go(self):
        settings.update("app", {"backup_dir": self.folder})
        keep = os.path.join(self.folder, "streamdesk-perfil-20261110-123456.json")  # a copy the user saved by hand
        open(keep, "w").close()
        for day in range(10):
            open(os.path.join(self.folder, f"streamdesk-perfil-2026010{day}.json"), "w").close()
        self.assertTrue(config_manager.save_config(config_manager.get_config()))
        names = os.listdir(self.folder)
        self.assertIn("streamdesk-perfil.json", names)
        self.assertEqual(len([n for n in names if re.fullmatch(r"streamdesk-perfil-\d{8}\.json", n)]), config_manager.MIRROR_DAILY_KEPT)
        self.assertIn(os.path.basename(keep), names)  # never touched
        self.assertEqual(json.load(open(os.path.join(self.folder, "streamdesk-perfil.json"), encoding="utf-8"))["layout"]["columns"],
                         config_manager.get_config()["layout"]["columns"])

    def test_a_folder_that_is_gone_does_not_stop_the_save(self):
        settings.update("app", {"backup_dir": os.path.join(self.folder, "unplugged")})
        self.assertTrue(config_manager.save_config(config_manager.get_config()))


class PageAndApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()
        cls.addClassCleanup(cls.live.__exit__, None, None, None)

    def url(self, path):
        return self.live.base_url + path

    def test_pages_carry_a_policy_that_allows_only_their_own_script(self):
        for path, page in (("/studio", "studio.html"), ("/", "index.html"), ("/library", "library.html")):
            with self.subTest(path=path):
                _, headers, body = request(self.url(path))
                policy = headers["Content-Security-Policy"]
                self.assertNotIn("unsafe-eval", policy)
                self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)
                self.assertIn("frame-ancestors 'none'", policy)
                inline = re.findall(r"<script>(.*?)</script>", body.decode("utf-8"), re.S)
                for script in inline:  # the page's own inline script must be allowed by its hash
                    import base64, hashlib
                    script = script.replace("\r\n", "\n")  # the HTML parser turns CRLF into LF before the browser hashes it
                    digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
                    self.assertIn(f"'sha256-{digest}'", policy)
                self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_big_files_are_compressed_for_browsers_that_accept_it(self):
        _, headers, body = request(self.url("/static/js/studio.js"), headers={"Accept-Encoding": "gzip"})
        self.assertEqual(headers.get("Content-Encoding"), "gzip")
        self.assertIn(b"function", gzip.decompress(body))

    def test_the_report_for_support_has_facts_and_no_secrets(self):
        auth = main.auth_manager
        token = auth.verify_pin_and_issue_token(auth.current_pin, "Móvil", "10.0.0.9")["token"]
        self.addCleanup(auth.revoke_token, token)
        _, _, body = request(self.url("/api/diagnostics/report"))
        report = json.loads(body)["report"]
        self.assertIn(f"StreamDesk Pro {VERSION}", report)
        self.assertIn("Móviles emparejados", report)
        self.assertNotIn(token, report)
        self.assertNotIn(auth.current_pin, report)

    def test_limiting_a_phone_from_studio(self):
        auth = main.auth_manager
        token = auth.verify_pin_and_issue_token(auth.current_pin, "Tablet", "10.0.0.8")["token"]
        self.addCleanup(auth.revoke_token, token)
        device = AuthManager.device_id(token)
        status, _, body = request(self.url("/api/auth/devices/restrict"), {"id": device, "restricted": True})
        self.assertEqual(status, 200)
        self.assertTrue(next(d for d in json.loads(body)["devices"] if d["id"] == device)["restricted"])
        self.assertEqual(request(self.url("/api/auth/devices/restrict"), {"id": "0" * 12, "restricted": True})[0], 404)
        self.assertEqual(request(self.url("/api/auth/devices/restrict"), {"id": device, "restricted": "yes"})[0], 422)

    def test_a_limited_phone_cannot_run_a_dangerous_button_but_a_normal_one_can(self):
        auth = main.auth_manager
        token = auth.verify_pin_and_issue_token(auth.current_pin, "Tablet de Ana", "10.0.0.10")["token"]
        self.addCleanup(auth.revoke_token, token)
        auth.set_restricted(AuthManager.device_id(token), True)
        base = config_manager.get_config()

        def config_with_risky_slot():
            config = copy.deepcopy(base)
            config["slots"].append({"id": "btn_risky", "type": "button", "label": "Apagar", "action_type": "windows",
                                    "target": "power", "extra": {"mode": "shutdown"}})
            return config

        calls = []

        async def press(button):
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws?token={token}") as ws:
                while json.loads(await ws.recv())["type"] != "init_state":
                    pass
                await ws.send(json.dumps({"type": "trigger_button", "id": button}))
                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), 5))
                    if message["type"] == "action_result":
                        return message

        folder = tempfile.mkdtemp(prefix="sd-audit-")
        with mock.patch.object(audit, "LOG_FILE", os.path.join(folder, "a.log")), \
                mock.patch.object(main.config_manager, "get_config", side_effect=config_with_risky_slot), \
                mock.patch.object(main, "execute_action", side_effect=lambda *a: calls.append(a) or {"success": True}):
            refused = asyncio.run(press("btn_risky"))
            allowed = asyncio.run(press("btn_play"))
            log = audit.recent()
        self.assertFalse(refused["success"])
        self.assertEqual(refused["message"], permissions.LIMITED_MESSAGE)
        self.assertTrue(allowed["success"])
        self.assertEqual(len(calls), 1)  # only the normal button ran
        self.assertTrue(all(e["device"] == "Tablet de Ana" for e in log))
        self.assertEqual([(e["button"], e["ok"]) for e in reversed(log)][0], ("Apagar", False))  # refused one logged first
        self.assertEqual([e["ok"] for e in reversed(log)], [False, True])

    def test_the_connection_check_endpoint_answers(self):
        with mock.patch.object(firewall, "network_categories", return_value=[]), \
                mock.patch.object(firewall, "rule_exists", return_value=True):
            status, _, body = request(self.url("/api/system/connection-check"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["checks"][0]["id"], "server")

    def test_desktop_settings_take_the_new_options(self):
        self.addCleanup(settings.clear, "app")
        folder = tempfile.mkdtemp(prefix="sd-copy-")
        status, _, body = request(self.url("/api/settings/desktop"), {"keep_awake": True, "backup_dir": folder})
        data = json.loads(body)
        self.assertEqual((status, data["keep_awake"], data["backup_dir"]), (200, True, os.path.abspath(folder)))
        self.assertTrue(os.path.exists(os.path.join(folder, "streamdesk-perfil.json")))  # copied at once
        self.assertEqual(request(self.url("/api/settings/desktop"), {"backup_dir": os.path.join(folder, "nope")})[0], 422)
        self.assertEqual(request(self.url("/api/settings/desktop"), {"backup_dir": ""})[0], 200)
        self.assertEqual(request(self.url("/api/desktop/pick-folder"), {})[0], 409)  # no window in the tests


class AppUpdateCheckTests(unittest.TestCase):
    """The phone page offers a newer Android app. The JavaScript is run by Node in eleven situations."""

    HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const source = fs.readFileSync(process.argv[2], "utf8");
const block = source.split("// --- app update check ---")[1].split("// --- end app update check ---")[0];
const APK = "https://example.test/StreamDesk.apk";

async function run({ app, pc, stored = "", answer = true, overlay = false, failFetch = false }) {
  const out = { asked: false, message: "", labels: null, navigated: "", stored: stored, fetched: false };
  const storage = { v: stored };
  const context = vm.createContext({
    nativeApp: app === null ? null : (app === "old" ? {} : { getVersion: () => app }),
    ANDROID_APK_URL: APK,
    window: { location: {} },
    document: { querySelector: () => (overlay ? {} : null) },
    localStorage: { getItem: () => storage.v, setItem: (k, v) => { storage.v = v; } },
    fetch: async () => { out.fetched = true; if (failFetch) throw new Error("offline"); return { json: async () => ({ version: pc }) }; },
    askConfirm: async (message, labels) => { out.asked = true; out.message = message; out.labels = labels; return answer; },
    console,
  });
  vm.runInContext(block, context);
  await vm.runInContext("checkAppUpdate()", context);
  out.navigated = context.window.location.href || "";
  out.stored = storage.v;
  return out;
}

(async () => {
  const cases = [
    { app: "old", pc: "2.19.0" },
    { app: "2.19.0", pc: "2.19.0" },
    { app: "2.18.1", pc: "2.19.0", answer: false },
    { app: "2.18.1", pc: "2.19.0", stored: "2.19.0" },
    { app: "2.18.1", pc: "2.19.1", stored: "2.19.0" },
    { app: "2.19.1", pc: "2.19.0" },
    { app: null, pc: "2.19.0" },
    { app: "old", pc: "2.19.0", failFetch: true },
    { app: "2.9.0", pc: "2.10.0" },
    { app: "old", pc: "dev" },
    { app: "old", pc: "2.19.0", overlay: true },
  ];
  console.log(JSON.stringify(await Promise.all(cases.map(run))));
})();
"""

    def test_it_offers_the_newer_app_only_when_the_phone_app_is_older(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("Node is not installed")
        folder = tempfile.mkdtemp(prefix="sd-appupdate-")
        harness = os.path.join(folder, "harness.js")
        with open(harness, "w", encoding="utf-8") as handle:
            handle.write(self.HARNESS)
        script = os.path.join(BASE_DIR, "static", "js", "streamdeck.js")
        result = subprocess.run([node, harness, script], capture_output=True, encoding="utf-8", timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        old, same, older, dismissed, new_pc, newer_app, browser, offline, numeric, junk, busy = json.loads(result.stdout)
        self.assertTrue(old["asked"])  # an app before 2.19 has no getVersion(): older than this PC by definition
        self.assertEqual(old["labels"], {"yes": "Descargar", "no": "Más tarde"})
        self.assertIn("2.19.0", old["message"])
        self.assertEqual(old["navigated"], "https://example.test/StreamDesk.apk")  # "Descargar" opens the download
        self.assertFalse(same["asked"])
        self.assertTrue(older["asked"])
        self.assertEqual((older["navigated"], older["stored"]), ("", "2.19.0"))  # "Más tarde" is remembered for this PC version
        self.assertFalse(dismissed["asked"])
        self.assertTrue(new_pc["asked"])  # asks again once the PC has moved on
        self.assertFalse(newer_app["asked"])
        self.assertFalse(browser["fetched"])  # outside the app there is nothing to offer, and nothing is requested
        self.assertFalse(offline["asked"])
        self.assertTrue(numeric["asked"])  # 2.9.0 is older than 2.10.0: compared as numbers, not as text
        self.assertFalse(junk["asked"])
        self.assertFalse(busy["asked"])  # another question is open: do not stack one on top

    def test_the_android_app_exposes_its_version_to_the_page(self):
        with open(os.path.join(BASE_DIR, "android", "app", "src", "main", "java", "com", "zak208", "streamdesk", "MainActivity.java"),
                  encoding="utf-8") as handle:
            java = handle.read()
        self.assertRegex(java, r"@JavascriptInterface\s+public String getVersion\(\)")
        self.assertIn("getPackageInfo(getPackageName(), 0).versionName", java)


class VersionConsistencyTests(unittest.TestCase):
    def test_the_pc_the_installer_and_the_android_app_say_the_same_version(self):
        with open(os.path.join(BASE_DIR, "installer", "setup.iss"), encoding="utf-8") as handle:
            installer = re.search(r'#define MyAppVersion "([^"]+)"', handle.read()).group(1)
        with open(os.path.join(BASE_DIR, "android", "app", "build.gradle"), encoding="utf-8") as handle:
            android = re.search(r'versionName "([^"]+)"', handle.read()).group(1)
        self.assertEqual({VERSION, installer, android}, {VERSION})


if __name__ == "__main__":
    unittest.main()
