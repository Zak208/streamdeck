"""Fixes that came out of the black-box security test: other websites reaching localhost, stored XSS,
malformed messages, uploads and the exposed API schema."""

import asyncio
import copy
import http.client
import json
import unittest

import support
import websockets
from server import main
from server.action_catalog import validate_action, validate_deck_config
from server.config_manager import DEFAULT_CONFIG

PNG = bytes.fromhex("89504e470d0a1a0a") + b"\x00" * 32


def default_profile():
    return copy.deepcopy(DEFAULT_CONFIG)


class ValidationTests(unittest.TestCase):
    def test_an_image_path_cannot_break_out_of_an_attribute(self):
        for bad in ('/static/icons/a.svg" onerror="x', "/static/icons/a.svg' onerror='x", "/static/icons/a b.svg",
                    "/static/icons/a.svg>", "/static/icons/..\\x.svg"):
            profile = default_profile()
            profile["pages"][0]["slots"][4]["image"] = bad
            with self.subTest(path=bad), self.assertRaises(ValueError):
                validate_deck_config(profile)

    def test_a_web_address_cannot_hold_control_characters_or_spaces(self):
        for bad in ("http://ok\n.example/", "http://ok .example/", "http://ok.example/\tx", "https://a.b/\x00",
                    "https://a.b/\x7f", "https://a.b/\x85x", "https://a.b/ x"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                validate_action("url", bad)
        self.assertEqual(validate_action("url", "https://example.com/a?b=1")["target"], "https://example.com/a?b=1")

    def test_the_active_page_cannot_be_a_boolean(self):
        profile = default_profile()
        profile["current_page"] = True
        with self.assertRaises(ValueError):
            validate_deck_config(profile)


class HostAndOriginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def request(self, path, host=None, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.live.port, timeout=10)
        connection.putrequest(method, path, skip_host=True)
        connection.putheader("Host", host or f"127.0.0.1:{self.live.port}")
        connection.endheaders()
        response = connection.getresponse()
        body = response.read()
        headers = dict(response.getheaders())
        connection.close()
        return response.status, body, headers

    def test_admin_routes_answer_to_localhost_names_only(self):
        for host in (f"127.0.0.1:{self.live.port}", f"localhost:{self.live.port}"):
            with self.subTest(host=host):
                self.assertEqual(self.request("/api/ui", host)[0], 200)
        for host in ("evil.example", f"evil.example:{self.live.port}", f"192.168.2.81:{self.live.port}"):
            with self.subTest(host=host):
                self.assertEqual(self.request("/api/ui", host)[0], 403)  # DNS rebinding looks like this

    def test_a_websocket_from_another_site_is_refused_and_a_same_origin_one_is_accepted(self):
        async def connect(origin):
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws", origin=origin) as ws:
                return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))["type"]

        self.assertEqual(asyncio.run(connect(f"http://127.0.0.1:{self.live.port}")), "init_state")
        for origin in ("http://evil.example", "http://localhost:1", "null"):
            with self.subTest(origin=origin), self.assertRaises(Exception):
                asyncio.run(connect(origin))

    def test_a_websocket_without_origin_still_works_for_local_tools(self):
        async def connect():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))["type"]
        self.assertEqual(asyncio.run(connect()), "init_state")

    def test_the_api_schema_is_not_published(self):
        for path in ("/docs", "/redoc", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)

    def test_responses_forbid_content_sniffing(self):
        self.assertEqual(self.request("/api/ui")[2].get("x-content-type-options"), "nosniff")
        self.assertEqual(self.request("/")[2].get("x-content-type-options"), "nosniff")


class HostParsingTests(unittest.TestCase):
    def test_only_a_local_name_with_a_numeric_port_counts_as_local(self):
        for good in ("localhost", "LOCALHOST:48291", "127.0.0.1", "127.0.0.1:1", "[::1]:48291"):
            with self.subTest(host=good):
                self.assertNotEqual(main._host_name(good), "")
        for bad in ("localhost:48323.evil.com", "[::1]x", "evil.com", "localhost@evil.com", "localhost:", "localhost:123456",
                    "127.0.0.1.nip.io", "localhost.evil.com", "", " ", "localhost:80:80", "2130706433", "0.0.0.0"):
            with self.subTest(host=bad):
                self.assertEqual(main._host_name(bad), "")

    def test_a_request_the_browser_marks_cross_site_is_refused(self):
        headers = {"host": "127.0.0.1:48291", "sec-fetch-site": "cross-site"}
        self.assertFalse(main._local_browser_request(headers, "127.0.0.1"))
        for site in ("same-origin", "none", "same-site"):
            self.assertTrue(main._local_browser_request({"host": "127.0.0.1:48291", "sec-fetch-site": site}, "127.0.0.1"))
        self.assertTrue(main._local_browser_request({"host": "127.0.0.1:48291"}, "127.0.0.1"))


class TextHardeningTests(unittest.TestCase):
    def test_control_characters_are_refused_in_every_text_of_a_profile(self):
        for bad in ("a\nb", "a\x00b", "a\u2028b", "a\u2029b", "a\x85b", "a\x7fb", "a\x1bb"):
            with self.subTest(text=repr(bad)), self.assertRaises(ValueError):
                validate_action("obs_action", "preview_scene", {"scene_name": bad})
            profile = default_profile()
            profile["pages"][0]["slots"][0]["label"] = bad
            with self.subTest(label=repr(bad)), self.assertRaises(ValueError):
                validate_deck_config(profile)

    def test_emoji_and_accents_still_work(self):
        for text in ("Fuego \U0001F525", "C\u00e1mara", "\U0001F468\u200d\U0001F469\u200d\U0001F467 Familia", "\u65e5\u672c\u8a9e", "a\ufe0fb"):
            with self.subTest(text=ascii(text)):
                validate_action("obs_action", "preview_scene", {"scene_name": text})

    def test_layout_digits_must_be_ascii(self):
        from server import layouts
        for bad in ("\u0664x\u0668", "\uff14x\uff18"):
            with self.subTest(spec=ascii(bad)), self.assertRaises(ValueError):
                layouts.parse_layout(bad)


class BackupTests(unittest.TestCase):
    def test_backups_made_within_the_same_second_do_not_overwrite_each_other(self):
        from server.config_manager import config_manager
        paths = {config_manager.backup_profile("prueba") for _ in range(6)}
        self.assertNotIn("", paths)
        self.assertEqual(len(paths), 6)
        import os
        for path in paths:
            os.remove(path)


class MalformedMessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def test_messages_of_the_wrong_shape_do_not_drop_the_connection(self):
        bad = ["[1, 2, 3]", "42", '"text"', "null",
               json.dumps({"type": "set_master_volume", "volume": "mucho"}),
               json.dumps({"type": "switch_page", "page": ["a"]}),
               json.dumps({"type": "set_app_volume", "process": ["x"], "volume": 5}),
               json.dumps({"type": "trigger_button", "id": {"a": 1}, "gesture": ["x"]}),
               '{"type": "set_master_volume", "volume": 1e999}', '{"type": "switch_page", "page": Infinity}',
               "[" * 100000]

        async def scenario():
            async with websockets.connect(f"ws://127.0.0.1:{self.live.port}/ws") as ws:
                await ws.recv()
                for message in bad:
                    await ws.send(message)
                await ws.send(json.dumps({"type": "refresh_sessions"}))
                while True:  # the connection is still alive and still answers
                    reply = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                    if reply["type"] == "sessions_update":
                        return True
        self.assertTrue(asyncio.run(scenario()))

    def test_a_failure_message_kept_for_diagnostics_is_short(self):
        class Socket:
            client = type("C", (), {"host": "127.0.0.1"})()
            headers = {}
        main.diagnostics.clear() if hasattr(main.diagnostics, "clear") else None
        main._record_button_failure(Socket(), "x" * 100000, "y" * 100000)
        newest = main.diagnostics.snapshot()[-1] if hasattr(main.diagnostics, "snapshot") else None
        if newest is not None:
            self.assertLess(len(json.dumps(newest)), 1000)


class WebpTests(unittest.TestCase):
    def test_webp_icons_are_served_as_images(self):
        import mimetypes
        self.assertEqual(mimetypes.guess_type("icon.webp")[0], "image/webp")


class UploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def upload(self, content, content_type, name="x.png"):
        boundary = "----qa"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: {content_type}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        connection = http.client.HTTPConnection("127.0.0.1", self.live.port, timeout=10)
        connection.request("POST", "/api/upload", body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, data

    def test_a_real_png_is_accepted(self):
        status, body = self.upload(PNG, "image/png")
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["url"].endswith(".png"))

    def test_a_file_that_only_claims_to_be_an_image_is_refused(self):
        for content in (b"<html><script>alert(1)</script></html>", b"MZ\x90\x00 an executable", b"", b"<svg onload=alert(1)>"):
            with self.subTest(content=content[:12]):
                self.assertEqual(self.upload(content, "image/png")[0], 415)

    def test_the_stored_extension_follows_the_content_not_the_claimed_type(self):
        status, body = self.upload(PNG, "image/jpeg")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["url"].endswith(".png"))


if __name__ == "__main__":
    unittest.main()
