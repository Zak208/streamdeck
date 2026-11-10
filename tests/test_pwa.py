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
    """Runs the real phone-settings.js in different phones and reads what the assistant tells them."""

    SCRIPT = r"""
const fs = require("fs"), vm = require("vm");
const fake = new Proxy(function () {}, {
  get: (t, p) => (p === Symbol.toPrimitive ? () => "" : p === "then" ? undefined : fake), apply: () => fake, construct: () => fake });
const scenario = JSON.parse(process.argv[1]);
const sandbox = {
  document: fake, console, JSON, Promise, Map, Set, Math, Date, Number, String, Array, Object,
  window: { isSecureContext: scenario.secure, addEventListener: () => {}, ...(scenario.androidApp ? { AndroidApp: {} } : {}) },
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

    def test_android_in_a_browser_is_offered_the_app(self):
        html = self.html(userAgent=self.ANDROID)
        self.assertIn("sheet-download-apk", html)
        self.assertIn("StreamDesk.apk", html)
        self.assertNotIn("chrome://flags", html)  # the old workaround is gone
        self.assertNotIn("data-copy", html)
        self.assertNotIn("sheet-install-now", html)

    def test_a_browser_that_can_install_gets_the_button(self):
        html = self.html(userAgent=self.ANDROID, prompt=True, secure=True)
        self.assertIn("sheet-install-now", html)
        self.assertNotIn("chrome://flags", html)

    def test_iphone_gets_the_safari_share_steps(self):
        html = self.html(userAgent=self.IPHONE, platform="iPhone")
        self.assertIn("Safari", html)
        self.assertIn("Añadir a pantalla de inicio", html)
        self.assertIn("PIN", html)  # its data is separate from Safari's

    def test_an_installed_app_has_nothing_to_install(self):
        self.assertEqual(self.html(userAgent=self.ANDROID, standalone=True), "")
        self.assertEqual(self.html(userAgent=self.IPHONE, platform="iPhone", iosStandalone=True), "")

    def test_the_android_app_has_nothing_to_install(self):
        self.assertEqual(self.html(userAgent=self.ANDROID, androidApp=True), "")


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

    def test_swiping_between_pages_can_be_switched_off(self):
        code = read("js/streamdeck.js")
        self.assertIn('localStorage.getItem("streamdesk_swipe") !== "0"', code)  # on unless the user turned it off
        self.assertRegex(code, r'touchend", \(e\) => \{\s*if \(!swipeEnabled\(\)')
        self.assertIn('id="sheet-swipe"', read("js/phone-settings.js"))

    def test_there_is_no_fullscreen_control(self):
        everything = read("index.html") + read("js/streamdeck.js") + read("js/phone-settings.js")
        for gone in ("btn-fullscreen", "requestFullscreen", "streamdesk_fullscreen"):
            self.assertNotIn(gone, everything)

    def test_pull_to_refresh_cannot_hijack_a_fader_drag(self):
        self.assertIn("overscroll-behavior: none", read("css/style.css"))


if __name__ == "__main__":
    unittest.main()
