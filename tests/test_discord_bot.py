"""The Discord soundboard, against a fake Discord (REST and gateway on this PC).

None of this proves the real Discord accepts the same messages: it proves StreamDesk sends what
Discord's documentation says, and handles the answers (and the failures) it describes.
"""

import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from websockets.exceptions import ConnectionClosed

import support
from server import action_catalog, actions, discord_bot
from server.connectors import discord
from server.discord_bot import DiscordBot, DiscordError
from server.settings_store import settings

GOOD_TOKEN = "good-token-" + "x" * 50
BOT_ID = "900000000000000001"
USER_ID = "700000000000000007"
G1, G2 = "111111111111111111", "222222222222222222"
C1, C2, C3 = "211111111111111111", "211111111111111112", "322222222222222222"
SOUND_A, SOUND_B, SOUND_OTHER = "411111111111111112", "411111111111111111", "422222222222222222"


class FakeDiscord:
    """REST on one port and the gateway on another, both answering like Discord's documentation says."""

    def __init__(self):
        self.rest_port, self.gateway_port = support.free_port(), support.free_port()
        self.user_voice = {G1: C1}  # where the user is when the bot connects
        self.rest_status = {}       # path suffix -> forced status code
        self.sent = []              # (channel_id, body) of every send-soundboard-sound
        self.rest_calls = []
        self.identifies, self.voice_requests = [], []
        self.sockets = []
        self._seq = 0
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._stop = None
        self._thread = threading.Thread(target=self._run_gateway, daemon=True)
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, status, payload=None):
                body = json.dumps(payload).encode() if payload is not None else b""
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def _route(self, method):
                fake.rest_calls.append((method, self.path))
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None  # read first: an unread body resets the connection
                if self.headers.get("Authorization") != f"Bot {GOOD_TOKEN}":
                    return self._reply(401, {"message": "401: Unauthorized"})
                for suffix, status in fake.rest_status.items():
                    if self.path.endswith(suffix):
                        return self._reply(status, {"message": "forced"})
                if method == "GET" and self.path == "/users/@me":
                    return self._reply(200, {"id": BOT_ID, "username": "streambot"})
                if method == "GET" and self.path == "/users/@me/guilds":
                    return self._reply(200, [{"id": G1, "name": "Servidor A"}, {"id": G2, "name": "Servidor B"}])
                if method == "GET" and self.path == f"/guilds/{G1}/soundboard-sounds":
                    return self._reply(200, {"items": [
                        {"sound_id": SOUND_A, "name": "Zeta", "emoji_name": "🔔", "guild_id": G1, "available": True, "volume": 1.0},
                        {"sound_id": SOUND_B, "name": "aplausos", "emoji_name": None, "guild_id": G1, "available": True, "volume": 1.0}]})
                if method == "GET" and self.path == f"/guilds/{G2}/soundboard-sounds":
                    return self._reply(200, {"items": [{"sound_id": SOUND_OTHER, "name": "Bocina", "guild_id": G2}]})
                if method == "GET" and self.path == "/soundboard-default-sounds":
                    return self._reply(200, [{"sound_id": "1", "name": "Quack", "emoji_name": "🦆", "available": True, "volume": 1.0}])
                if method == "POST" and self.path.startswith("/channels/") and self.path.endswith("/send-soundboard-sound"):
                    fake.sent.append((self.path.split("/")[2], body))
                    return self._reply(204)
                return self._reply(404, {"message": "unknown"})

            def do_GET(self):
                self._route("GET")

            def do_POST(self):
                self._route("POST")

        self._http = ThreadingHTTPServer(("127.0.0.1", self.rest_port), Handler)
        self._http_thread = threading.Thread(target=self._http.serve_forever, daemon=True)

    # ---- gateway
    def _run_gateway(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self):
        from websockets.asyncio.server import serve
        self._stop = asyncio.Event()
        async with serve(self._handler, "127.0.0.1", self.gateway_port):
            self._ready.set()
            await self._stop.wait()

    async def _send(self, ws, event, data):
        self._seq += 1
        await ws.send(json.dumps({"op": 0, "t": event, "s": self._seq, "d": data}))

    async def _handler(self, ws):
        self.sockets.append(ws)
        try:
            await ws.send(json.dumps({"op": 10, "d": {"heartbeat_interval": 300}}))
            async for raw in ws:
                message = json.loads(raw)
                if message["op"] == 1:
                    await ws.send(json.dumps({"op": 11}))
                elif message["op"] == 2:
                    self.identifies.append(message["d"])
                    if message["d"]["token"] != GOOD_TOKEN:
                        await ws.close(4004, "Authentication failed.")
                        return
                    await self._send(ws, "READY", {"user": {"id": BOT_ID}, "guilds": [{"id": G1}, {"id": G2}]})
                    await self._send(ws, "GUILD_CREATE", {
                        "id": G1, "name": "Servidor A",
                        "channels": [{"id": C1, "name": "Sala 1"}, {"id": C2, "name": "Sala 2"}],
                        "voice_states": [{"user_id": u, "channel_id": c} for g, c in self.user_voice.items() if g == G1 for u in [USER_ID]]})
                    await self._send(ws, "GUILD_CREATE", {
                        "id": G2, "name": "Servidor B", "channels": [{"id": C3, "name": "Charla"}],
                        "voice_states": [{"user_id": USER_ID, "channel_id": C3}] if G2 in self.user_voice else []})
                elif message["op"] == 4:
                    self.voice_requests.append(message["d"])
                    await self._send(ws, "VOICE_STATE_UPDATE", {
                        "guild_id": message["d"]["guild_id"], "channel_id": message["d"]["channel_id"], "user_id": BOT_ID})
        except ConnectionClosed:
            pass  # the bot was stopped mid-session
        finally:
            self.sockets.remove(ws)

    def push(self, event, data):
        async def go():
            for ws in list(self.sockets):
                await self._send(ws, event, data)
        asyncio.run_coroutine_threadsafe(go(), self._loop).result(5)

    def __enter__(self):
        self._thread.start()
        self._http_thread.start()
        self._ready.wait(5)
        return self

    def __exit__(self, *exc):
        self._http.shutdown()
        self._http.server_close()
        self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(5)


def wait_until(condition, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


class DiscordBotTests(unittest.TestCase):
    token = GOOD_TOKEN
    idle_leave = 45.0

    def setUp(self):
        self.fake = FakeDiscord().__enter__()
        settings.clear("discord")
        settings.update("discord", {"bot_token": self.token, "user_id": USER_ID})
        self.bot = DiscordBot(api_base=f"http://127.0.0.1:{self.fake.rest_port}",
                              gateway_url=f"ws://127.0.0.1:{self.fake.gateway_port}", idle_leave_seconds=self.idle_leave)
        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.loop_thread.start()
        self.bot.start(self.loop)

    def tearDown(self):
        self.bot.stop()
        time.sleep(0.05)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.loop_thread.join(5)
        self.fake.__exit__(None, None, None)
        settings.clear("discord")

    def play(self, sound=SOUND_A, guild=G1):
        return self.bot.run(self.bot.play(sound, guild))


class PlayingSoundsTests(DiscordBotTests):
    def test_joins_the_users_channel_muted_and_plays_the_sound(self):
        self.play()
        self.assertEqual(self.fake.voice_requests, [{"guild_id": G1, "channel_id": C1, "self_mute": True, "self_deaf": False}])
        self.assertEqual(self.fake.sent, [(C1, {"sound_id": SOUND_A})])
        identify = self.fake.identifies[0]
        self.assertEqual(identify["token"], GOOD_TOKEN)
        self.assertEqual(identify["intents"], (1 << 0) | (1 << 7))  # GUILDS and GUILD_VOICE_STATES: nothing privileged

    def test_second_press_reuses_the_channel(self):
        self.play()
        self.play(SOUND_B)
        self.assertEqual(len(self.fake.voice_requests), 1)
        self.assertEqual([body["sound_id"] for _, body in self.fake.sent], [SOUND_A, SOUND_B])

    def test_a_sound_from_another_server_names_its_source(self):
        self.play(SOUND_OTHER, G2)
        self.assertEqual(self.fake.sent, [(C1, {"sound_id": SOUND_OTHER, "source_guild_id": G2})])

    def test_discord_default_sounds_need_no_source(self):
        self.play("1", "default")
        self.assertEqual(self.fake.sent, [(C1, {"sound_id": "1"})])

    def test_it_follows_the_user_to_another_channel(self):
        self.play()
        self.fake.push("VOICE_STATE_UPDATE", {"guild_id": G1, "channel_id": C2, "user_id": USER_ID})
        self.assertTrue(wait_until(lambda: self.bot.where_is_user()["channel_id"] == C2))
        self.play(SOUND_B)
        self.assertEqual(self.fake.voice_requests[-1]["channel_id"], C2)
        self.assertEqual(self.fake.sent[-1][0], C2)
        self.assertEqual(self.bot.where_is_user()["channel_name"], "Sala 2")

    def test_it_follows_the_user_to_another_server(self):
        self.fake.user_voice = {G2: C3}
        self.bot.reload()
        self.assertTrue(wait_until(lambda: (self.bot.where_is_user() or {}).get("guild_id") == G2))
        self.play(SOUND_OTHER, G2)
        self.assertEqual(self.fake.sent[-1], (C3, {"sound_id": SOUND_OTHER}))

    def test_bot_leaves_when_the_user_leaves(self):
        self.play()
        self.fake.push("VOICE_STATE_UPDATE", {"guild_id": G1, "channel_id": None, "user_id": USER_ID})
        self.assertTrue(wait_until(lambda: self.fake.voice_requests[-1]["channel_id"] is None))
        self.assertIsNone(self.bot.where_is_user())

    def test_not_being_in_a_voice_channel_is_a_readable_failure(self):
        self.fake.user_voice = {}
        self.bot.reload()
        with self.assertRaises(DiscordError) as caught:
            self.play()
        self.assertIn("No estás en un canal de voz", str(caught.exception))
        self.assertEqual(self.fake.sent, [])
        self.assertEqual(self.fake.voice_requests, [])

    def test_a_rejected_send_says_what_to_check(self):
        self.fake.rest_status["send-soundboard-sound"] = 403
        with self.assertRaises(DiscordError) as caught:
            self.play()
        self.assertIn("Usar soundboard", str(caught.exception))

    def test_the_action_runs_through_the_normal_executor(self):
        with mock.patch.object(discord_bot, "bot", self.bot):
            ok = actions.execute_action("discord_sound", SOUND_A, {"guild_id": G1, "sound_name": "Zeta"})
            self.fake.user_voice = {}
            self.bot.reload()
            self.assertTrue(wait_until(lambda: self.bot.where_is_user() is None))
            failed = actions.execute_action("discord_sound", SOUND_A, {"guild_id": G1})
        self.assertEqual(ok["success"], True)
        self.assertIs(failed["success"], False)
        self.assertIn("canal de voz", failed["error"])


class IdleLeaveTests(DiscordBotTests):
    idle_leave = 0.2

    def test_bot_leaves_after_a_quiet_moment(self):
        self.play()
        self.assertTrue(wait_until(lambda: self.fake.voice_requests[-1]["channel_id"] is None))


class RejectedBotTests(DiscordBotTests):
    token = "bad-token-" + "x" * 50

    def test_a_refused_gateway_login_says_to_check_the_token(self):
        started = time.time()
        with self.assertRaises(DiscordError) as caught:
            self.play()
        self.assertIn("revisa el token", str(caught.exception))
        self.assertLess(time.time() - started, 4)  # does not sit out the connection timeout
        self.assertNotIn(self.token, str(caught.exception))
        self.assertEqual(self.bot.summary(), "Discord rechazó el bot: revisa el token.")


class RestTests(DiscordBotTests):
    def test_servers_and_sounds(self):
        self.assertEqual([g["name"] for g in self.bot.list_guilds()], ["Servidor A", "Servidor B"])
        sounds = self.bot.list_sounds(G1)
        self.assertEqual([s["name"] for s in sounds], ["aplausos", "Zeta"])  # alphabetical, ignoring case
        self.assertEqual(sounds[1]["emoji"], "🔔")
        self.assertEqual(sounds[0]["emoji"], "")
        self.assertEqual(self.bot.list_sounds("default")[0]["guild_id"], "default")

    def test_check_names_the_bot(self):
        self.assertEqual(self.bot.check(), {"id": BOT_ID, "name": "streambot"})

    def test_a_bad_token_is_explained_without_repeating_it(self):
        bad = "wrong-" + "y" * 50
        with self.assertRaises(DiscordError) as caught:
            self.bot.check(bad)
        self.assertIn("token", str(caught.exception))
        self.assertNotIn(bad, str(caught.exception))

    def test_discord_being_unreachable_is_a_readable_failure(self):
        offline = DiscordBot(api_base=f"http://127.0.0.1:{support.free_port()}")
        with self.assertRaises(DiscordError) as caught:
            offline.check(GOOD_TOKEN)
        self.assertIn("conexión", str(caught.exception))

    def test_invite_link_asks_only_for_what_the_soundboard_needs(self):
        permissions = int(self.bot.invite_url(BOT_ID).split("permissions=")[1])
        for bit in (10, 20, 21, 42, 45):  # view, connect, speak, use soundboard, use external sounds
            self.assertTrue(permissions & (1 << bit), bit)
        self.assertEqual(permissions & (1 << 3), 0)  # not Administrator
        self.assertIn(f"client_id={BOT_ID}", self.bot.invite_url(BOT_ID))


class ConnectorTests(DiscordBotTests):
    def setUp(self):
        super().setUp()
        settings.clear("discord")
        patcher = mock.patch.object(discord, "bot", self.bot)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_saving_a_token_checks_it_and_keeps_it_secret(self):
        saved = discord.configure({"bot_token": f"Bot {GOOD_TOKEN}", "user_id": USER_ID})
        self.assertEqual(settings.get("discord")["bot_token"], GOOD_TOKEN)  # "Bot " prefix dropped
        self.assertEqual((saved["bot_name"], saved["user_id"], saved["bot_token_set"]), ("streambot", USER_ID, True))
        self.assertIn(f"client_id={BOT_ID}", saved["invite_url"])
        self.assertNotIn(GOOD_TOKEN, json.dumps(saved))
        self.assertNotIn(GOOD_TOKEN, json.dumps(discord.status()))
        self.assertNotIn("bot_token", saved)

    def test_a_wrong_token_is_refused_and_not_saved(self):
        bad = "wrong-" + "y" * 50
        with self.assertRaises(ValueError):
            discord.configure({"bot_token": bad})
        self.assertNotIn("bot_token", settings.get("discord"))
        for junk in ("short", "has a space " + "x" * 50, "x" * 200):
            with self.subTest(junk=junk), self.assertRaises(ValueError):
                discord.configure({"bot_token": junk})

    def test_user_id_must_be_a_number(self):
        for junk in ("zak", "123", "12345678901234567890123456789", "7000000000000000a7"):
            with self.subTest(junk=junk), self.assertRaises(ValueError):
                discord.configure({"user_id": junk})
        self.assertEqual(discord.configure({"user_id": f" {USER_ID} "})["user_id"], USER_ID)

    def test_removing_the_bot_forgets_everything_about_it(self):
        discord.configure({"bot_token": GOOD_TOKEN, "user_id": USER_ID})
        public = discord.configure({"remove_bot": True})
        self.assertEqual(settings.get("discord").get("bot_token"), None)
        self.assertEqual((public["bot_token_set"], public["user_id"], public["bot_name"]), (False, "", ""))
        self.assertNotIn("invite_url", public)
        self.assertEqual(discord.actions()[0]["id"], "mute")  # hotkeys keep working

    def test_options_list_servers_voice_and_sounds(self):
        discord.configure({"bot_token": GOOD_TOKEN, "user_id": USER_ID})
        servers = discord.options("guilds")
        self.assertEqual([s["id"] for s in servers], ["default", G1, G2])
        self.assertTrue(wait_until(lambda: discord.options("voice") != []))
        here = discord.options("voice")[0]
        self.assertEqual((here["guild_id"], here["guild_name"], here["channel_name"]), (G1, "Servidor A", "Sala 1"))
        self.assertEqual(len(discord.options(f"sounds:{G1}")), 2)
        self.assertEqual(len(discord.options("sounds:default")), 1)

    def test_a_server_id_cannot_smuggle_a_path(self):
        discord.configure({"bot_token": GOOD_TOKEN, "user_id": USER_ID})
        calls_before = len(self.fake.rest_calls)
        for junk in ("sounds:../../users/@me", "sounds:123", "sounds:", f"sounds:{G1}/x"):
            with self.subTest(junk=junk), self.assertRaises(RuntimeError):
                discord.options(junk)
        self.assertEqual(len(self.fake.rest_calls), calls_before)

    def test_failures_come_out_as_a_reason(self):
        with self.assertRaises(RuntimeError) as caught:
            discord.options("guilds")  # nothing saved yet
        self.assertIn("token", str(caught.exception))

    def test_status_describes_the_bot(self):
        with mock.patch.object(discord, "_discord_running", return_value=True):
            self.assertIn("sin configurar", discord.status()["detail"])
            discord.configure({"bot_token": GOOD_TOKEN, "user_id": USER_ID})
            self.assertTrue(wait_until(lambda: "conectado en 2 servidores" in discord.status()["detail"]))
        with mock.patch.object(discord, "_discord_running", return_value=False):
            self.assertEqual(discord.status()["state"], "offline")


class DiscordSoundActionTests(unittest.TestCase):
    def test_a_sound_action_keeps_only_what_it_needs(self):
        action = action_catalog.validate_action("discord_sound", SOUND_A, {"guild_id": G1, "sound_name": "Zeta", "junk": 1})
        self.assertEqual(action, {"action_type": "discord_sound", "target": SOUND_A,
                                  "extra": {"guild_id": G1, "sound_name": "Zeta"}})
        self.assertEqual(action_catalog.validate_action("discord_sound", "1", {"guild_id": "default"})["extra"], {"guild_id": "default"})
        self.assertEqual(action_catalog.validate_action("discord_sound", SOUND_A)["extra"], {"guild_id": ""})

    def test_bad_ids_are_refused(self):
        for target, extra in (("abc", {}), ("", {}), ("1; calc", {}), ("9" * 40, {}),
                              (SOUND_A, {"guild_id": "../x"}), (SOUND_A, {"guild_id": "12"}), (SOUND_A, {"sound_name": "<b>"})):
            with self.subTest(target=target, extra=extra), self.assertRaises(ValueError):
                action_catalog.validate_action("discord_sound", target, extra)

    def test_it_can_be_a_macro_step_and_lives_in_a_profile(self):
        step = {"action_type": "discord_sound", "target": SOUND_A, "extra": {"guild_id": G1}}
        macro = action_catalog.validate_action("multi", "m", {"actions": [step]})
        self.assertEqual(macro["extra"]["actions"][0]["target"], SOUND_A)

    def test_without_a_configured_bot_it_explains_what_is_missing(self):
        settings.clear("discord")
        result = actions.execute_action("discord_sound", SOUND_A, {"guild_id": G1})
        self.assertIs(result["success"], False)
        self.assertTrue(result["error"])


if __name__ == "__main__":
    unittest.main()
