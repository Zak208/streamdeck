import asyncio
import base64
import copy
import glob
import io
import json
import os
import re
import unittest
import urllib.error
import urllib.request

import support
import websockets
from PIL import Image

from server import diagnostics, templates
from server.action_catalog import validate_deck_config
from server.auth import auth_manager
from server.config_manager import DEFAULT_CONFIG
from server.connectors import discord
from server.paths import STATIC_DIR
from server.settings_store import settings

BRAND_ICONS = ("discord", "spotify", "obs", "steam", "chrome")


def read(path):
    with open(os.path.join(STATIC_DIR, path), encoding="utf-8") as handle:
        return handle.read()


class TemplateTests(unittest.TestCase):
    def test_every_template_is_a_valid_page_with_fresh_ids(self):
        for meta in templates.TEMPLATES:
            with self.subTest(template=meta["id"]):
                first = templates.build_page(meta["id"])
                second = templates.build_page(meta["id"])
                self.assertNotEqual(first["id"], second["id"])
                profile = copy.deepcopy(DEFAULT_CONFIG)
                profile["pages"] += [first, second]
                checked = validate_deck_config(profile)  # raises on any unsafe or malformed slot
                layout = checked["pages"][-1]["layout"]
                self.assertEqual(len(checked["pages"][-1]["slots"]), layout["rows"] * layout["columns"])  # each page has its own size

    def test_blank_page_has_no_keys_only_the_windows_volume(self):
        page = templates.build_page("blank", "  Mi página ")
        self.assertEqual(page["name"], "Mi página")
        self.assertFalse([slot for slot in page["slots"] if slot["type"] == "button"])
        faders = [slot for slot in page["slots"] if slot["type"] == "slider"]
        self.assertEqual([(f["slider_type"], f["target_app"]) for f in faders], [("master", None)])

    def test_streamer_uses_the_saved_discord_shortcuts(self):
        settings.clear("discord")
        discord.configure({"mute_hotkey": "CTRL+ALT+F7", "deafen_hotkey": "CTRL+ALT+F8"})
        slots = templates.build_page("streamer")["slots"]
        hotkeys = {s["target"]: s["extra"]["hotkey"] for s in slots if s.get("action_type") == "discord_hotkey"}
        self.assertEqual(hotkeys, {"mute": "CTRL+ALT+F7", "deafen": "CTRL+ALT+F8"})
        settings.clear("discord")

    def test_unknown_template_is_rejected(self):
        with self.assertRaises(ValueError):
            templates.build_page("nope")

    def test_the_library_is_well_formed(self):
        ids = [meta["id"] for meta in templates.TEMPLATES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 20)
        for meta in templates.TEMPLATES:
            with self.subTest(template=meta["id"]):
                self.assertTrue(os.path.exists(os.path.join(STATIC_DIR, meta["icon"].lstrip("/").replace("static/", "", 1))), meta["icon"])
                page = templates.build_page(meta["id"])
                for slot in page["slots"]:
                    if slot["type"] == "button":
                        self.assertTrue(os.path.exists(os.path.join(STATIC_DIR, slot["image"].lstrip("/").replace("static/", "", 1))), slot["image"])
                self.assertEqual(bool(page.get("auto_app")), bool(meta["app"]))

    def test_a_page_of_a_program_opens_when_that_program_is_in_front(self):
        page = templates.build_page("spotify")
        self.assertEqual(page["auto_app"], "Spotify.exe")
        self.assertIn("Spotify.exe", [s["target_app"] for s in page["slots"] if s["type"] == "slider"])
        self.assertNotIn("auto_app", templates.build_page("spotify", auto_app=False))
        self.assertNotIn("auto_app", templates.build_page("gamer"))


class StudioApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def call(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.live.base_url + path, data=data, method="POST" if data else "GET",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def test_applying_a_template_appends_a_page(self):
        before = len(self.call("/api/config")[1]["pages"])
        status, body = self.call("/api/templates/apply", {"template_id": "gamer", "name": "Directos"})
        self.assertEqual((status, body["index"]), (200, before))
        pages = self.call("/api/config")[1]["pages"]
        self.assertEqual((len(pages), pages[-1]["name"]), (before + 1, "Directos"))

    def test_a_second_page_for_the_same_program_does_not_steal_the_auto_open(self):
        first = self.call("/api/templates/apply", {"template_id": "obs"})
        second = self.call("/api/templates/apply", {"template_id": "obs"})
        self.assertEqual(first[1]["auto_app"], "obs64.exe")
        self.assertEqual(second[1]["auto_app"], "")
        pages = self.call("/api/config")[1]["pages"]
        self.assertEqual(sum(1 for p in pages if p.get("auto_app") == "obs64.exe"), 1)

    def test_deleting_a_page_before_the_active_one_keeps_you_on_your_page(self):
        from server import config_manager as cm
        self.call("/api/templates/apply", {"template_id": "blank", "name": "Ultima"})
        pages = self.call("/api/config")[1]["pages"]
        last = len(pages) - 1
        cm.config_manager.set_active_page(last)
        wanted = pages[last]["id"]
        self.assertTrue(self.call("/api/deck/page/delete", {"page_index": 0})[1]["success"])
        now = self.call("/api/config")[1]
        self.assertEqual(now["pages"][now["current_page"]]["id"], wanted)

    def test_a_duplicated_page_has_its_own_key_ids(self):
        self.call("/api/templates/apply", {"template_id": "gamer", "name": "Original"})
        pages = self.call("/api/config")[1]["pages"]
        index = len(pages) - 1
        self.call("/api/deck/page/duplicate", {"page_index": index})
        pages = self.call("/api/config")[1]["pages"]
        first = {slot["id"] for slot in pages[index]["slots"] if slot.get("id")}
        copy_ids = {slot["id"] for slot in pages[index + 1]["slots"] if slot.get("id")}
        self.assertTrue(first and copy_ids)
        self.assertFalse(first & copy_ids)

    def test_counters_show_their_value_on_every_page_not_only_the_active_one(self):
        from server import live_buttons, main
        config = copy.deepcopy(DEFAULT_CONFIG)
        slot = next(s for s in config["pages"][1]["slots"] if s["type"] == "button")
        slot.update({"action_type": "none", "target": "", "extra": {}, "long_press": {"action_type": "counter", "target": "inc", "extra": {"step": 1}}})
        config["current_page"] = 0
        live_buttons.change_counter(slot["id"], "reset", 1)
        live_buttons.change_counter(slot["id"], "inc", 7)
        self.assertEqual(main.current_labels(validate_deck_config(config)).get(slot["id"]), "7")

    def test_a_call_that_timed_out_is_not_run_later(self):
        import threading
        from server.com_worker import ComWorker
        worker, ran, release = ComWorker(), [], threading.Event()
        worker.submit(release.wait, 5)  # keeps the thread busy
        with self.assertRaises(TimeoutError):
            worker.call(lambda: ran.append("ghost"), timeout=0.2)
        release.set()
        worker.call(lambda: ran.append("real"), timeout=5)
        self.assertEqual(ran, ["real"])

    def test_the_spotify_return_page_accepts_a_cross_site_navigation_but_admin_pages_do_not(self):
        headers = {"Sec-Fetch-Site": "cross-site"}

        def get(path):
            request = urllib.request.Request(self.live.base_url + path, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status
            except urllib.error.HTTPError as error:
                return error.code
        self.assertEqual(get("/api/connectors/spotify/callback?code=x&state=y"), 400)  # answered: the state is not valid
        self.assertEqual(get("/api/connectors"), 403)

    def test_automatic_backups_are_rolling(self):
        import tempfile
        from server import config_manager as cm
        manager = cm.config_manager
        folder = os.path.join(cm.CONFIG_DIR, "backups")
        os.makedirs(folder, exist_ok=True)
        for old in os.listdir(folder):
            os.remove(os.path.join(folder, old))
        for day in range(1, 13):
            open(os.path.join(folder, f"deck_config-202001{day:02d}-000000.json"), "w").close()
        manager.AUTO_BACKUP_EVERY = 0
        self.addCleanup(setattr, manager, "AUTO_BACKUP_EVERY", 1800)
        manager._auto_backup()
        self.assertLessEqual(len(os.listdir(folder)), manager.AUTO_BACKUPS_KEPT)
        manager.AUTO_BACKUP_EVERY = 1800
        before = set(os.listdir(folder))
        manager._auto_backup()  # a copy was just made: no new one yet
        self.assertEqual(before, set(os.listdir(folder)))

    def test_the_library_page_and_the_program_catalog_are_served(self):
        request = urllib.request.Request(self.live.base_url + "/library")
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("Biblioteca de páginas", response.read().decode())
        programs = self.call("/api/programs")[1]
        self.assertGreaterEqual(len(programs["programs"]), 22)
        self.assertTrue(all(p["actions"] for p in programs["programs"]))
        listed = self.call("/api/templates")[1]["templates"]
        self.assertGreaterEqual(len(listed), 40)
        self.assertTrue(all({"rows", "columns"} <= set(t["layout"]) for t in listed))
        self.assertTrue(any(t["layout"] != {"rows": 2, "columns": 6} for t in listed))  # pages with a size of their own

    def test_a_library_page_with_its_own_size_keeps_it_when_added(self):
        status, body = self.call("/api/templates/apply", {"template_id": "mixer", "name": "Mezclas"})
        self.assertEqual(status, 200)
        page = self.call("/api/config")[1]["pages"][body["index"]]
        self.assertEqual((page["layout"]["rows"], page["layout"]["columns"]), (3, 6))
        self.assertEqual([s["row_span"] for s in page["slots"] if s["type"] == "slider"], [3, 3, 3, 3])

    def test_the_size_of_one_page_changes_without_touching_the_others(self):
        before = self.call("/api/config")[1]
        index = len(before["pages"]) - 1
        status, body = self.call("/api/layout", {"layout": "4x3", "page": index})
        self.assertEqual(status, 200)
        pages = body["config"]["pages"]
        self.assertEqual(pages[index]["layout"]["columns"], 4)
        self.assertEqual(pages[0]["layout"], before["pages"][0]["layout"])
        self.assertEqual(self.call("/api/layout", {"layout": "4x3", "page": 999})[0], 422)

    def test_a_refused_page_does_not_stay_in_the_live_profile(self):
        before = len(self.call("/api/config")[1]["pages"])
        self.assertEqual(self.call("/api/deck/page/add", {"name": "x" * 50})[0], 422)
        self.assertEqual(len(self.call("/api/config")[1]["pages"]), before)

    def test_a_wrong_pin_with_accents_is_a_refusal_not_a_crash(self):
        status, _ = self.call("/api/auth/verify", {"pin": "é12345"})
        self.assertLess(status, 500)

    def test_the_profile_is_saved_whole(self):
        from server import config_manager as cm
        self.assertTrue(os.path.exists(cm.CONFIG_FILE))
        self.assertFalse(os.path.exists(cm.CONFIG_FILE + ".tmp"))
        json.loads(open(cm.CONFIG_FILE, encoding="utf-8").read())

    def test_bad_template_requests_are_refused(self):
        self.assertEqual(self.call("/api/templates/apply", {"template_id": "nope"})[0], 404)
        self.assertEqual(self.call("/api/templates/apply", {"template_id": "blank", "name": "x" * 60})[0], 422)

    def test_template_list_hides_the_slots(self):
        _, body = self.call("/api/templates")
        self.assertTrue({"streamer", "gamer", "work", "blank", "spotify", "obs", "discord"} <= {t["id"] for t in body["templates"]})
        self.assertTrue(all("slots" not in t for t in body["templates"]))
        self.assertTrue(all(t["category"] in body["categories"] and t["preview"] for t in body["templates"]))

    def test_theme_is_saved_validated_and_pushed_to_phones(self):
        self.assertEqual(self.call("/api/ui")[1]["theme"], "ctma")
        self.assertEqual(self.call("/api/ui", {"theme": "neon"})[0], 422)

        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                json.loads(await ws.recv())  # init_state
                self.call("/api/ui", {"theme": "cian"})
                while True:
                    message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    if message["type"] == "theme":
                        return message

        self.assertEqual(asyncio.run(scenario())["theme"], "cian")
        self.assertEqual(self.call("/api/ui")[1]["theme"], "cian")
        self.call("/api/ui", {"theme": "ctma"})

    def test_devices_are_listed_without_tokens_and_can_be_revoked_live(self):
        result = auth_manager.verify_pin_and_issue_token(auth_manager.current_pin, "Pixel de prueba", "10.9.9.9")
        token = result["token"]
        devices = self.call("/api/auth/devices")[1]["devices"]
        device = next(d for d in devices if d["name"] == "Pixel de prueba")
        self.assertNotIn(token, json.dumps(devices))
        self.assertNotEqual(device["id"], token)

        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws?token={token}") as ws:
                await ws.recv()  # init_state
                status, _ = await asyncio.to_thread(self.call, "/api/auth/devices/revoke", {"id": device["id"]})
                self.assertEqual(status, 200)
                with self.assertRaises(websockets.ConnectionClosed) as closed:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                return closed.exception.rcvd.code

        self.assertEqual(asyncio.run(scenario()), 1008)
        self.assertFalse(auth_manager.is_token_authorized(token))
        self.assertNotIn("Pixel de prueba", json.dumps(self.call("/api/auth/devices")[1]))
        self.assertEqual(self.call("/api/auth/devices/revoke", {"id": device["id"]})[0], 404)


class DiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def verify(self, pin, agent):
        request = urllib.request.Request(
            self.live.base_url + "/api/auth/verify", data=json.dumps({"pin": pin, "device_name": "x"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": agent}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode())

    def log(self):
        with urllib.request.urlopen(self.live.base_url + "/api/diagnostics", timeout=10) as response:
            return json.loads(response.read().decode())["events"]

    def test_pairing_attempts_are_logged_without_secrets(self):
        diagnostics.clear()
        android = "Mozilla/5.0 (Linux; Android 14; Pixel 8) Chrome/120 Mobile"
        self.verify("000000", android)
        result = self.verify(auth_manager.current_pin, android)
        events = self.log()
        self.assertEqual([e["kind"] for e in events], ["ok", "error"])  # newest first
        self.assertEqual({e["device"] for e in events}, {"Android"})
        self.assertIn("caducado", events[1]["message"])
        text = json.dumps(events)
        self.assertNotIn(result["token"], text)
        self.assertNotIn(auth_manager.current_pin, text)
        self.assertNotIn("Pixel 8", text)  # only a coarse device label is kept

    def test_device_labels(self):
        self.assertEqual(diagnostics.device_label("Mozilla/5.0 (iPhone; CPU iPhone OS 17)"), "iPhone/iPad")
        self.assertEqual(diagnostics.device_label("Mozilla/5.0 (Windows NT 10.0)"), "Navegador")
        self.assertEqual(diagnostics.device_label(None), "Navegador")

    def test_log_keeps_only_the_latest_events(self):
        diagnostics.clear()
        for number in range(60):
            diagnostics.record("info", f"evento {number}")
        self.assertEqual(len(diagnostics.recent()), 40)
        self.assertEqual(diagnostics.recent()[0]["message"], "evento 59")


class AssetTests(unittest.TestCase):
    def test_qr_is_dark_on_light(self):
        image = Image.open(io.BytesIO(base64.b64decode(auth_manager.generate_qr_base64(48291).split(",", 1)[1]))).convert("RGB")
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        self.assertIn((0, 0, 0), {image.getpixel((x, image.height // 2)) for x in range(image.width)})

    def test_monochrome_icons_are_covered_by_the_white_filter_and_brand_icons_are_not(self):
        for path in glob.glob(os.path.join(STATIC_DIR, "icons", "*.svg")):
            name = os.path.basename(path)[:-4]
            uses_current_color = "currentColor" in open(path, encoding="utf-8").read()
            with self.subTest(icon=name):
                if name in BRAND_ICONS:
                    self.assertFalse(uses_current_color, "a brand icon must keep its own colours")
                else:
                    self.assertFalse(any(brand in name for brand in BRAND_ICONS))
        css = read("css/tokens.css")
        for brand in BRAND_ICONS:
            self.assertIn(f':not([src*="/{brand}."])', css)

    def test_pages_only_look_up_elements_that_exist(self):
        for script, page in (("js/studio.js", "studio.html"), ("js/streamdeck.js", "index.html")):
            html = read(page)
            for name in re.findall(r'^const \w+ = document\.getElementById\("([^"]+)"\)', read(script), re.M):
                with self.subTest(script=script, element=name):
                    self.assertIn(f'id="{name}"', html)

    def test_studio_keeps_the_pin_on_screen_in_step_with_the_server(self):
        # The server rotates the PIN; a Studio that only read it once showed a dead code.
        self.assertIn("setInterval(loadAuthInfo", read("js/studio.js"))
        self.assertIn('id="pin-expiry"', read("studio.html"))

    def test_phone_shows_the_pin_error_above_the_button(self):
        html = read("index.html")
        self.assertLess(html.index('id="pin-error"'), html.index('id="btn-verify-pin"'))

    def test_assets_are_versioned_so_phones_fetch_fixes_instead_of_cached_scripts(self):
        from server.paths import VERSION
        for page in ("studio.html", "index.html"):
            html = read(page)
            assets = re.findall(r'(?:href|src)="(/static/(?:css|js)/[^"]+)"', html)
            self.assertTrue(assets)
            for asset in assets:
                with self.subTest(page=page, asset=asset):
                    self.assertTrue(asset.endswith(f"?v={VERSION}"), "bump ?v= together with VERSION")

    def test_phone_replacing_its_socket_cannot_start_a_reconnect_loop(self):
        # Closing the old socket used to schedule a reconnect that closed the new one, forever.
        code = read("js/streamdeck.js")
        self.assertIn("old.onclose = null", code)
        self.assertIn("if (socket !== ws) return;", code)
        self.assertIn("function scheduleReconnect", code)
        self.assertNotIn("setTimeout(connectWebSocket", code.replace("reconnectTimer = setTimeout(connectWebSocket", ""))

    def test_both_apps_load_the_shared_tokens(self):
        for page in ("studio.html", "index.html"):
            self.assertIn("/static/css/tokens.css", read(page))
        self.assertIn("/static/js/studio-ui.js", read("studio.html"))


if __name__ == "__main__":
    unittest.main()
