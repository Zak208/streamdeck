import json
import math
import os
import re
import shutil
import subprocess
import unittest
import urllib.request

import support
from PIL import Image

from server.paths import STATIC_DIR

NODE = shutil.which("node")


def read(path):
    with open(os.path.join(STATIC_DIR, path), encoding="utf-8") as handle:
        return handle.read()


def icon(path):
    return Image.open(os.path.join(STATIC_DIR, path.lstrip("/").replace("static/", "", 1)))


class InstallabilityChecklistTests(unittest.TestCase):
    """What Chrome requires before it offers "Install app", checked in the files we ship.

    The one requirement a test here cannot meet is HTTPS: that depends on how the phone opens the page.
    """

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(read("manifest.json"))

    def test_identity_and_start(self):
        m = self.manifest
        self.assertTrue(m["name"] and m["short_name"])
        self.assertLessEqual(len(m["short_name"]), 12)  # longer names get cut under the icon
        self.assertEqual((m["id"], m["start_url"], m["scope"]), ("/", "/", "/"))
        self.assertIn(m["display"], {"standalone", "fullscreen", "minimal-ui"})
        self.assertEqual(m["display_override"][0], "fullscreen")  # a deck needs no system bars

    def test_colours_follow_the_default_theme(self):
        self.assertEqual((self.manifest["theme_color"], self.manifest["background_color"]), ("#0a0a0a", "#0a0a0a"))

    def test_icons_are_real_and_correctly_declared(self):
        by_purpose = {}
        for entry in self.manifest["icons"]:
            image = icon(entry["src"])
            size = int(entry["sizes"].split("x")[0])
            self.assertEqual(image.size, (size, size), entry["src"])  # the declared size is the real size
            self.assertEqual(entry["type"], "image/png")
            self.assertNotIn(" ", entry["purpose"], "keep 'any' and 'maskable' as separate icons")
            by_purpose.setdefault(entry["purpose"], set()).add(size)
        self.assertTrue({192, 512} <= by_purpose["any"])
        self.assertTrue({192, 512} <= by_purpose["maskable"])

    def test_maskable_icons_are_opaque_and_keep_the_symbol_in_the_safe_zone(self):
        for entry in (e for e in self.manifest["icons"] if e["purpose"] == "maskable"):
            image = icon(entry["src"]).convert("RGBA")
            size = image.size[0]
            self.assertEqual(image.getchannel("A").getextrema(), (255, 255), "Android fills nothing around a maskable icon")
            background = image.getpixel((0, 0))
            pixels = image.load()
            xs, ys = [], []
            for y in range(size):
                for x in range(size):
                    if pixels[x, y] != background:
                        xs.append(x)
                        ys.append(y)
            corners = [(min(xs), min(ys)), (max(xs), min(ys)), (min(xs), max(ys)), (max(xs), max(ys))]
            farthest = max(math.hypot(x - size / 2, y - size / 2) for x, y in corners)
            self.assertLessEqual(farthest, size * 0.4, f"{entry['src']} would be cropped by a circular mask")

    def test_any_icons_have_rounded_transparent_corners_and_the_apple_icon_is_opaque(self):
        for entry in (e for e in self.manifest["icons"] if e["purpose"] == "any"):
            self.assertEqual(icon(entry["src"]).convert("RGBA").getpixel((0, 0))[3], 0)
        apple = icon("/static/icons/apple-touch-icon.png")
        self.assertEqual((apple.size, apple.mode), ((180, 180), "RGB"))  # iOS paints transparency black

    def test_the_page_points_at_everything_the_phone_needs(self):
        html = read("index.html")
        for needle in ('rel="manifest" href="/manifest.json"', 'name="theme-color"', 'rel="apple-touch-icon" href="/static/icons/apple-touch-icon.png"',
                       'name="apple-mobile-web-app-capable"', 'name="viewport"', "viewport-fit=cover"):
            self.assertIn(needle, html)

    def test_manifest_and_service_worker_are_served_the_way_browsers_expect(self):
        with support.LiveServer() as live:
            def fetch(path):
                with urllib.request.urlopen(live.base_url + path, timeout=10) as response:
                    return response.status, response.headers, response.read()

            status, headers, body = fetch("/manifest.json")
            self.assertEqual((status, headers["Content-Type"]), (200, "application/manifest+json"))
            self.assertEqual(json.loads(body)["start_url"], "/")
            status, headers, _ = fetch("/service-worker.js")
            self.assertEqual((status, headers["Service-Worker-Allowed"]), (200, "/"))
            self.assertIn("javascript", headers["Content-Type"])
            for entry in self.manifest["icons"]:
                self.assertEqual(fetch(entry["src"])[0], 200)
            self.assertEqual(fetch("/")[0], 200)  # start_url must work


@unittest.skipUnless(NODE, "needs Node to run the browser code")
class ServiceWorkerBehaviourTests(unittest.TestCase):
    def test_service_worker_logic(self):
        script = r"""
const fs = require("fs"), vm = require("vm");
const handlers = {}, calls = [], stores = {};
const key = (r) => (typeof r === "string" ? new URL(r, "http://phone/").href : r.url);
const caches = {
  open: async (name) => ({
    addAll: async (urls) => calls.push(["addAll", name, urls.length]),
    put: async (request, response) => { (stores[name] ||= new Map()).set(key(request), response); },
  }),
  keys: async () => ["streamdesk-old-1", "streamdesk-old-2", process.argv[2]],
  delete: async (name) => { calls.push(["delete", name]); return true; },
  match: async (request) => { for (const store of Object.values(stores)) if (store.has(key(request))) return store.get(key(request)); },
};
const self = { addEventListener: (type, fn) => { handlers[type] = fn; }, skipWaiting: () => calls.push(["skipWaiting"]), clients: { claim: () => calls.push(["claim"]) } };
const sandbox = { self, caches, fetch: async () => { throw new Error("offline"); }, Response: { error: () => ({ networkError: true }) }, console, URL, Promise };
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const cacheName = vm.runInContext("CACHE_NAME", sandbox);

(async () => {
  const result = { cacheName };
  const waits = [];
  handlers.install({ waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
  result.installed = calls.filter((c) => c[0] === "addAll").map((c) => c[1]);
  result.skipWaiting = calls.some((c) => c[0] === "skipWaiting");

  waits.length = 0;
  handlers.activate({ waitUntil: (p) => waits.push(p) });
  await Promise.all(waits);
  result.deleted = calls.filter((c) => c[0] === "delete").map((c) => c[1]);
  result.claimed = calls.some((c) => c[0] === "claim");

  const run = async (request) => {
    let answer, intercepted = false;
    handlers.fetch({ request, respondWith: (p) => { intercepted = true; answer = p; } });
    return { intercepted, value: intercepted ? await answer : undefined };
  };
  result.api = (await run({ url: "http://phone/api/info", method: "GET", mode: "cors" })).intercepted;
  result.websocket = (await run({ url: "http://phone/ws", method: "GET", mode: "websocket" })).intercepted;
  result.post = (await run({ url: "http://phone/static/x.js", method: "POST", mode: "cors" })).intercepted;

  stores[cacheName] = new Map([["http://phone/", { cachedStartPage: true }]]);
  result.offlineNavigation = (await run({ url: "http://phone/?pin=123", method: "GET", mode: "navigate" })).value;
  result.offlineMissingAsset = (await run({ url: "http://phone/static/js/none.js", method: "GET", mode: "no-cors" })).value;
  process.stdout.write(JSON.stringify(result));
})();
"""
        worker = os.path.join(STATIC_DIR, "service-worker.js")
        name = re.search(r"CACHE_NAME = '([^']+)'", read("service-worker.js")).group(1)
        probe = subprocess.run(["node", "-e", script, worker, name], capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr[-500:])
        result = json.loads(probe.stdout)
        self.assertEqual(result["cacheName"], name)
        self.assertEqual(result["installed"], [name])
        self.assertTrue(result["skipWaiting"] and result["claimed"])
        self.assertEqual(sorted(result["deleted"]), ["streamdesk-old-1", "streamdesk-old-2"])  # old versions go, the current stays
        self.assertFalse(result["api"], "API calls must go straight to the PC")
        self.assertFalse(result["websocket"])
        self.assertFalse(result["post"])
        self.assertEqual(result["offlineNavigation"], {"cachedStartPage": True})  # the app still opens without the PC
        self.assertEqual(result["offlineMissingAsset"], {"networkError": True})


@unittest.skipUnless(NODE, "needs Node to run the browser code")
class InstallAssistantTests(unittest.TestCase):
    """Runs the real phone-settings.js in five different phones and reads what the assistant tells them."""

    SCRIPT = r"""
const fs = require("fs"), vm = require("vm");
const fake = new Proxy(function () {}, {
  get: (t, p) => (p === Symbol.toPrimitive ? () => "" : p === "then" ? undefined : fake), apply: () => fake, construct: () => fake });
const scenario = JSON.parse(process.argv[1]);
const sandbox = {
  document: fake, console, JSON, Promise, Map, Set, Math, Date, Number, String, Array, Object,
  window: { isSecureContext: scenario.secure, addEventListener: () => {} },
  navigator: { userAgent: scenario.userAgent, platform: scenario.platform || "Linux armv8l", maxTouchPoints: 5, standalone: scenario.iosStandalone },
  matchMedia: (query) => ({ matches: scenario.standalone && query.includes("standalone") }),
  location: { origin: "http://192.168.2.81:48291", host: "192.168.2.81:48291" },
  localStorage: { getItem: () => null, setItem: () => {} },
  currentConfig: null, deferredInstallPrompt: scenario.prompt ? {} : null,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
process.stdout.write(vm.runInContext("installSectionHtml()", sandbox));
"""

    def html(self, **scenario):
        scenario.setdefault("secure", False)
        scenario.setdefault("standalone", False)
        scenario.setdefault("prompt", False)
        probe = subprocess.run(["node", "-e", self.SCRIPT, json.dumps(scenario), os.path.join(STATIC_DIR, "js", "phone-settings.js")],
                               capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr[-500:])
        return probe.stdout

    ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"

    def test_android_on_plain_http_is_told_why_and_given_the_exact_steps(self):
        html = self.html(userAgent=self.ANDROID)
        self.assertIn("https", html)  # the reason it cannot install
        self.assertIn("chrome://flags/#unsafely-treat-insecure-origin-as-secure", html)
        self.assertIn("http://192.168.2.81:48291", html)  # the address to paste into the flag
        self.assertIn("Relaunch", html)
        self.assertEqual(html.count("data-copy="), 2)
        self.assertNotIn("sheet-install-now", html)

    def test_a_browser_that_can_install_gets_the_button(self):
        html = self.html(userAgent=self.ANDROID, prompt=True, secure=True)
        self.assertIn("sheet-install-now", html)
        self.assertNotIn("chrome://flags", html)

    def test_iphone_gets_the_safari_share_steps(self):
        html = self.html(userAgent=self.IPHONE, platform="iPhone")
        self.assertIn("Safari", html)
        self.assertIn("Añadir a pantalla de inicio", html)
        self.assertNotIn("chrome://flags", html)
        self.assertIn("PIN", html)  # its data is separate from Safari's

    def test_android_over_https_is_just_pointed_to_the_menu(self):
        html = self.html(userAgent=self.ANDROID, secure=True)
        self.assertIn("Instalar app", html)
        self.assertNotIn("chrome://flags", html)

    def test_an_installed_app_says_so_and_offers_nothing_else(self):
        html = self.html(userAgent=self.ANDROID, standalone=True)
        self.assertIn("instalada", html)
        self.assertNotIn("data-copy", html)
        self.assertNotIn("sheet-install-now", html)

    def test_ios_home_screen_app_counts_as_installed(self):
        self.assertIn("instalada", self.html(userAgent=self.IPHONE, platform="iPhone", iosStandalone=True))


@unittest.skipUnless(NODE, "needs Node to run the browser code")
class InstallCheckTests(unittest.TestCase):
    """The "why does it not install" report, run in four phone situations."""

    SCRIPT = r"""
const fs = require("fs"), vm = require("vm");
const fake = new Proxy(function () {}, {
  get: (t, p) => (p === Symbol.toPrimitive ? () => "" : p === "then" ? undefined : fake), apply: () => fake, construct: () => fake });
const scenario = JSON.parse(process.argv[1]);
const document = new Proxy(fake, { get: (t, p) => (p === "querySelector" ? () => ({ href: "/manifest.json" }) : fake) });
const manifest = { name: "StreamDesk", display: "standalone", icons: [{ src: "/a.png" }, { src: "/b.png" }] };
const sandbox = {
  document, console, JSON, Promise, Map, Set, Math, Date, Number, String, Array, Object, Error,
  window: { isSecureContext: scenario.secure, addEventListener: () => {} },
  navigator: { userAgent: "Mozilla/5.0 (Linux; Android 14) Chrome/120 Mobile", platform: "Linux armv8l", maxTouchPoints: 5,
    ...(scenario.serviceWorker ? { serviceWorker: { getRegistration: async () => scenario.registration } } : {}) },
  matchMedia: () => ({ matches: false }),
  location: { origin: "http://192.168.2.81:48291", host: "192.168.2.81:48291" },
  localStorage: { getItem: () => null, setItem: () => {} },
  currentConfig: null, deferredInstallPrompt: scenario.prompt ? {} : null, swState: scenario.swState || null,
  fetch: async () => { if (scenario.manifestBroken) throw new Error("boom"); return { json: async () => manifest }; },
  Image: class { set src(value) { setTimeout(() => (value.startsWith("/a") || !scenario.iconBroken ? this.onload() : this.onerror()), 0); } },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
vm.runInContext("runInstallChecks()", sandbox).then((checks) => {
  sandbox.checks = checks;
  process.stdout.write(JSON.stringify({ checks, report: vm.runInContext("installReportText(checks)", sandbox), html: vm.runInContext("installReportHtml(checks)", sandbox) }));
});
"""

    def checks(self, **scenario):
        probe = subprocess.run(["node", "-e", self.SCRIPT, json.dumps(scenario), os.path.join(STATIC_DIR, "js", "phone-settings.js")],
                               capture_output=True, encoding="utf-8", timeout=30)
        self.assertEqual(probe.returncode, 0, probe.stderr[-500:])
        result = json.loads(probe.stdout)
        result["by_label"] = {c["label"]: c for c in result["checks"]}
        return result

    def test_plain_http_phone_shows_exactly_what_is_missing(self):
        result = self.checks(secure=False)
        got = result["by_label"]
        self.assertFalse(got["Dirección segura"]["ok"])
        self.assertIn("http", got["Dirección segura"]["detail"])
        self.assertFalse(got["Service worker"]["ok"])
        self.assertIn("no lo ofrece", got["Service worker"]["detail"])
        self.assertTrue(got["Manifiesto"]["ok"])
        self.assertFalse(got["Chrome ofrece instalar"]["ok"])
        self.assertIn("FALLA Dirección segura", result["report"])
        self.assertIn("Android 14", result["report"])  # the browser is in the report, so it can be diagnosed remotely

    def test_an_installable_phone_passes_everything_but_being_open_as_an_app(self):
        result = self.checks(secure=True, serviceWorker=True, registration={"active": {}}, prompt=True)
        failed = [c["label"] for c in result["checks"] if not c["ok"]]
        self.assertEqual(failed, ["Abierta como app"])

    def test_the_reason_a_service_worker_failed_is_reported(self):
        result = self.checks(secure=True, serviceWorker=True, registration=None,
                             swState={"ok": False, "message": "SecurityError: certificate"})
        self.assertIn("SecurityError: certificate", result["by_label"]["Service worker"]["detail"])

    def test_unreadable_manifest_and_missing_icons_are_flagged(self):
        broken = self.checks(secure=True, manifestBroken=True)
        self.assertFalse(broken["by_label"]["Manifiesto"]["ok"])
        self.assertNotIn("Iconos", broken["by_label"])  # nothing to load without a manifest
        icons = self.checks(secure=True, iconBroken=True)
        self.assertFalse(icons["by_label"]["Iconos"]["ok"])
        self.assertEqual(icons["by_label"]["Iconos"]["detail"], "1 de 2 cargan")

    def test_report_markup_escapes_what_it_shows(self):
        result = self.checks(secure=True, serviceWorker=True, registration=None,
                             swState={"ok": False, "message": "<img src=x onerror=alert(1)>"})
        self.assertNotIn("<img src=x", result["html"])


class PhoneLayoutTests(unittest.TestCase):
    def test_portrait_flows_the_same_cells_into_three_columns(self):
        css = read("css/style.css")
        self.assertRegex(css, r"@media \(orientation: portrait\)\s*\{[^@]*grid-template-columns: repeat\(3,")
        self.assertIn("var(--span", css)
        code = read("js/streamdeck.js")
        for variable in ('"--col"', '"--row"', '"--span"'):
            self.assertIn(f"setProperty({variable}", code)
        self.assertNotIn(".style.gridColumn", code)  # inline grid styles would beat the portrait layout

    def test_short_screens_get_a_compact_header(self):
        self.assertRegex(read("css/style.css"), r"@media \(max-height: 520px\)\s*\{[^@]*header \{ height: 40px")

    def test_settings_sheet_has_every_section(self):
        html = read("index.html")
        for section in ("sheet-pages", "sheet-screen", "sheet-install", "sheet-connection", "settings-sheet"):
            self.assertIn(f'id="{section}"', html)
        self.assertNotIn("rotate-hint", html + read("css/style.css"))
        self.assertNotIn("ios-install-modal", html)

    def test_pull_to_refresh_cannot_hijack_a_fader_drag(self):
        self.assertIn("overscroll-behavior: none", read("css/style.css"))


if __name__ == "__main__":
    unittest.main()
