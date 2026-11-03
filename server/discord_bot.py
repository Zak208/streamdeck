"""Discord soundboard through a bot the user creates.

Why a bot: Discord's soundboard API (list a server's sounds, play one) is for bots, and playing a
sound needs the caller to be connected to the voice channel. Using the user's own account for that
is against Discord's rules, so StreamDesk never asks for it. Instead:

  * the user makes a Discord application with a bot and pastes its token (kept like the OBS password);
  * the bot sits in the user's servers and follows the user's voice state over the gateway;
  * when a button is pressed, the bot joins the channel the user is in (self-muted, no audio), has
    Discord play the sound for everyone there, and leaves a little later.

Everything here talks to discord.com only. The token never appears in an error message or log.
"""

import asyncio
import concurrent.futures
import json
import random
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import websockets

from server.settings_store import settings

API = "https://discord.com/api/v10"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"
USER_AGENT = "DiscordBot (https://github.com/Zak208/streamdeck, 1.0)"

INTENTS = (1 << 0) | (1 << 7)  # GUILDS and GUILD_VOICE_STATES: neither is privileged
PERMISSIONS = {  # Discord's permission bits
    "VIEW_CHANNEL": 1 << 10,
    "CONNECT": 1 << 20,
    "SPEAK": 1 << 21,
    "USE_SOUNDBOARD": 1 << 42,
    "USE_EXTERNAL_SOUNDS": 1 << 45,
}
INVITE_PERMISSIONS = sum(PERMISSIONS.values())
# Gateway close codes that mean "retrying will not help": bad token or intents.
FATAL_CLOSE_CODES = {4004, 4010, 4011, 4012, 4013, 4014}


class DiscordError(Exception):
    """A problem worth telling the user about, in Spanish and without secrets."""


class DiscordBot:
    def __init__(self, api_base: str = API, gateway_url: str = GATEWAY, idle_leave_seconds: float = 45.0):
        self.api_base = api_base
        self.gateway_url = gateway_url
        self.idle_leave_seconds = idle_leave_seconds
        self.token = ""
        self.user_id = ""
        self.bot_id = ""
        self.error = ""
        self.guilds: Dict[str, Dict[str, Any]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._task: Optional[asyncio.Task] = None
        self._ws = None
        self._seq: Optional[int] = None
        self._acked = True
        self._pending_guilds: set = set()
        self._connected: Optional[asyncio.Event] = None
        self._leave_handle: Optional[asyncio.TimerHandle] = None

    # ------------------------------------------------------------------ configuration

    def refresh_config(self) -> bool:
        """Reads the saved token and user id. True when there is enough to connect."""
        saved = settings.get("discord")
        self.token = saved.get("bot_token", "")
        self.user_id = saved.get("user_id", "")
        return bool(self.token and self.user_id)

    def summary(self) -> str:
        """One line about the bot, from what is already in memory (no network)."""
        if not self.refresh_config():
            return "Bot del soundboard sin configurar"
        if self.error:
            return self.error
        if self._connected is not None and self._connected.is_set():
            count = len(self.guilds)
            return f"Bot conectado en {count} servidor{'es' if count != 1 else ''}"
        return "Conectando el bot..."

    # ------------------------------------------------------------------ REST (blocking: call from a thread)

    def _api(self, method: str, path: str, body: Optional[Dict[str, Any]] = None,
             errors: Optional[Dict[int, str]] = None, token: str = "") -> Any:
        request = urllib.request.Request(
            self.api_base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bot {token or self.token}", "Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read()
                return json.loads(raw.decode()) if raw else None
        except urllib.error.HTTPError as exc:
            messages = {
                401: "Discord no acepta ese token del bot. Copia uno nuevo en el portal de desarrolladores.",
                403: "El bot no tiene permiso para eso en ese servidor.",
                404: "Discord no encontró eso. ¿Está el bot en ese servidor?",
                429: "Discord pide esperar un momento. Inténtalo otra vez en unos segundos.",
                **(errors or {}),
            }
            raise DiscordError(messages.get(exc.code, f"Discord respondió con el error {exc.code}.")) from exc
        except OSError as exc:
            raise DiscordError("No se pudo contactar con Discord. Comprueba tu conexión a internet.") from exc

    def check(self, token: str = "") -> Dict[str, str]:
        """Validates a token (the saved one by default) and returns the bot's id and name."""
        if not token:
            self.refresh_config()
        if not (token or self.token):
            raise DiscordError("Falta el token del bot.")
        me = self._api("GET", "/users/@me", token=token)
        return {"id": me["id"], "name": me.get("username", "bot")}

    def list_guilds(self) -> List[Dict[str, str]]:
        self.refresh_config()
        return [{"id": g["id"], "name": g.get("name", "")} for g in self._api("GET", "/users/@me/guilds")]

    def list_sounds(self, guild_id: str) -> List[Dict[str, Any]]:
        """Sounds of one server, or Discord's own for guild_id "default"."""
        self.refresh_config()
        if guild_id == "default":
            raw = self._api("GET", "/soundboard-default-sounds") or []
        else:
            raw = (self._api("GET", f"/guilds/{guild_id}/soundboard-sounds") or {}).get("items", [])
        sounds = [{
            "sound_id": s["sound_id"], "name": s.get("name", "Sonido"), "emoji": s.get("emoji_name") or "",
            "guild_id": s.get("guild_id") or "default", "available": s.get("available", True), "volume": s.get("volume", 1),
        } for s in raw]
        return sorted(sounds, key=lambda s: s["name"].lower())

    def invite_url(self, bot_id: str) -> str:
        return f"https://discord.com/oauth2/authorize?client_id={bot_id}&scope=bot&permissions={INVITE_PERMISSIONS}"

    # ------------------------------------------------------------------ lifecycle (event loop thread)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        loop.call_soon_threadsafe(self._restart)

    def reload(self) -> None:
        """The token or user changed: reconnect with the new ones."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._restart)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._cancel)

    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._leave_handle is not None:
            self._leave_handle.cancel()
            self._leave_handle = None

    def _restart(self) -> None:
        self._cancel()
        self.guilds = {}
        self.error = ""
        self._connected = asyncio.Event()
        if self.refresh_config():
            self._task = asyncio.ensure_future(self._run())

    def run(self, coroutine, timeout: float = 25):
        """Run a coroutine on the bot's loop from any other thread and wait for it."""
        if self._loop is None:
            coroutine.close()
            raise DiscordError("El bot de Discord todavía no está listo. Espera unos segundos.")
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            return future.result(timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise DiscordError("Discord tarda demasiado en responder.") from exc

    # ------------------------------------------------------------------ gateway

    async def _run(self) -> None:
        delay = 1.0
        while True:
            try:
                await self._session()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except websockets.ConnectionClosed as exc:
                code = exc.rcvd.code if exc.rcvd else None
                if code in FATAL_CLOSE_CODES:
                    self.error = "Discord rechazó el bot: revisa el token."
                    self._connected.set()  # wake anyone waiting for the connection: they will see the error
                    return
            except Exception:
                pass  # network trouble: try again below
            self._connected.clear()
            await asyncio.sleep(min(delay, 30))
            delay *= 2

    async def _session(self) -> None:
        async with websockets.connect(self.gateway_url, max_size=2 ** 24) as ws:
            self._ws = ws
            hello = json.loads(await ws.recv())
            interval = hello["d"]["heartbeat_interval"] / 1000
            self._seq, self._acked = None, True
            await ws.send(json.dumps({"op": 2, "d": {
                "token": self.token, "intents": INTENTS,
                "properties": {"os": "windows", "browser": "streamdesk", "device": "streamdesk"},
            }}))
            beat = asyncio.ensure_future(self._heartbeat(ws, interval))
            try:
                async for raw in ws:
                    message = json.loads(raw)
                    if message.get("s") is not None:
                        self._seq = message["s"]
                    op = message["op"]
                    if op == 0:
                        self._dispatch(message["t"], message["d"])
                    elif op == 1:
                        await ws.send(json.dumps({"op": 1, "d": self._seq}))
                    elif op == 11:
                        self._acked = True
                    elif op in (7, 9):
                        break  # Discord asks to reconnect: the loop opens a new session
            finally:
                beat.cancel()
                self._ws = None

    async def _heartbeat(self, ws, interval: float) -> None:
        await asyncio.sleep(interval * random.random())
        while True:
            if not self._acked:
                await ws.close(code=4000)  # no answer to the last beat: the connection is dead
                return
            self._acked = False
            await ws.send(json.dumps({"op": 1, "d": self._seq}))
            await asyncio.sleep(interval)

    def _dispatch(self, event: str, data: Dict[str, Any]) -> None:
        if event == "READY":
            self.bot_id = data["user"]["id"]
            self._pending_guilds = {g["id"] for g in data.get("guilds", [])}
            if not self._pending_guilds:
                self._connected.set()
        elif event == "GUILD_CREATE":
            self.guilds[data["id"]] = {
                "name": data.get("name", ""),
                "channels": {c["id"]: c.get("name", "") for c in data.get("channels", [])},
                "voice": {v["user_id"]: v.get("channel_id") for v in data.get("voice_states", []) if v.get("channel_id")},
            }
            self._pending_guilds.discard(data["id"])
            if not self._pending_guilds:
                self._connected.set()
        elif event == "GUILD_DELETE":
            self.guilds.pop(data.get("id"), None)
        elif event == "VOICE_STATE_UPDATE":
            guild = self.guilds.get(data.get("guild_id"))
            if guild is None:
                return
            if data.get("channel_id"):
                guild["voice"][data["user_id"]] = data["channel_id"]
            else:
                guild["voice"].pop(data["user_id"], None)
                if data["user_id"] == self.user_id:
                    asyncio.ensure_future(self._leave(data["guild_id"]))  # the user left: so does the bot

    # ------------------------------------------------------------------ what the user is doing

    def where_is_user(self) -> Optional[Dict[str, str]]:
        for guild_id, guild in list(self.guilds.items()):  # copy: the gateway thread may add servers meanwhile
            channel_id = guild["voice"].get(self.user_id)
            if channel_id:
                return {"guild_id": guild_id, "guild_name": guild["name"], "channel_id": channel_id,
                        "channel_name": guild["channels"].get(channel_id, "")}
        return None

    # ------------------------------------------------------------------ playing a sound

    async def _send_voice_state(self, guild_id: str, channel_id: Optional[str]) -> None:
        await self._ws.send(json.dumps({"op": 4, "d": {
            "guild_id": guild_id, "channel_id": channel_id, "self_mute": True, "self_deaf": False,
        }}))

    async def _join(self, guild_id: str, channel_id: str) -> None:
        if self._ws is None:
            raise DiscordError("El bot de Discord no está conectado todavía.")
        await self._send_voice_state(guild_id, channel_id)
        for _ in range(80):  # up to 4 s for Discord to confirm the bot is in the channel
            if self.guilds[guild_id]["voice"].get(self.bot_id) == channel_id:
                return
            await asyncio.sleep(0.05)
        raise DiscordError("El bot no consiguió entrar en tu canal de voz. ¿Tiene permiso de Conectar?")

    async def _leave(self, guild_id: str) -> None:
        guild = self.guilds.get(guild_id)
        if guild and self._ws is not None and guild["voice"].get(self.bot_id):
            try:
                await self._send_voice_state(guild_id, None)
            except Exception:
                pass

    def _schedule_leave(self, guild_id: str) -> None:
        if self._leave_handle is not None:
            self._leave_handle.cancel()
        loop = asyncio.get_running_loop()
        self._leave_handle = loop.call_later(
            self.idle_leave_seconds, lambda: asyncio.ensure_future(self._leave(guild_id)))

    async def play(self, sound_id: str, source_guild_id: str = "") -> None:
        if not self.refresh_config():
            raise DiscordError("Falta configurar el bot de Discord en Conectores.")
        if self._connected is None or (self._task is None and not self.error):
            self._restart()
        if self.error:
            raise DiscordError(self.error)
        try:
            await asyncio.wait_for(self._connected.wait(), 8)
        except asyncio.TimeoutError:
            raise DiscordError(self.error or "El bot de Discord no consigue conectarse.") from None
        if self.error:
            raise DiscordError(self.error)

        here = self.where_is_user()
        if not here:
            raise DiscordError("No estás en un canal de voz de un servidor donde esté el bot.")
        guild_id, channel_id = here["guild_id"], here["channel_id"]
        if self.guilds[guild_id]["voice"].get(self.bot_id) != channel_id:
            await self._join(guild_id, channel_id)

        body: Dict[str, str] = {"sound_id": sound_id}
        if source_guild_id and source_guild_id not in ("default", guild_id):
            body["source_guild_id"] = source_guild_id  # a sound from another server
        await asyncio.to_thread(
            self._api, "POST", f"/channels/{channel_id}/send-soundboard-sound", body,
            {400: "Discord rechazó el sonido. ¿Sigue el bot en el canal y sin silenciar por el servidor?",
             403: "El bot no puede reproducir sonidos ahí: dale permiso de Conectar, Hablar y Usar soundboard (y sonidos externos si es de otro servidor)."},
        )
        self._schedule_leave(guild_id)


bot = DiscordBot()
