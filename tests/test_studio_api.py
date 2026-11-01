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

from server import templates
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
                self.assertEqual(len(checked["pages"][-1]["slots"]), 12)

    def test_blank_page_is_empty_and_named_pages_keep_their_name(self):
        page = templates.build_page("blank", "  Mi página ")
        self.assertEqual(page["name"], "Mi página")
        self.assertTrue(all(slot["type"] == "empty" for slot in page["slots"]))

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

    def test_bad_template_requests_are_refused(self):
        self.assertEqual(self.call("/api/templates/apply", {"template_id": "nope"})[0], 404)
        self.assertEqual(self.call("/api/templates/apply", {"template_id": "blank", "name": "x" * 60})[0], 422)

    def test_template_list_hides_the_slots(self):
        _, body = self.call("/api/templates")
        self.assertEqual({t["id"] for t in body["templates"]}, {"streamer", "gamer", "work", "blank"})
        self.assertTrue(all("slots" not in t for t in body["templates"]))

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

    def test_both_apps_load_the_shared_tokens(self):
        for page in ("studio.html", "index.html"):
            self.assertIn("/static/css/tokens.css", read(page))
        self.assertIn("/static/js/studio-ui.js", read("studio.html"))


if __name__ == "__main__":
    unittest.main()
