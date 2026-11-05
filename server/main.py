import copy
import ctypes
import faulthandler
import os
import sys
import shutil
import asyncio
import json
import uuid
import subprocess
import time
import urllib.request
import mimetypes
import re
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from typing import Set, Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body, UploadFile, File, Request, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Safe stdout/stderr handling for GUI windowed mode
if sys.stdout is None:
    try:
        sys.stdout = open(os.devnull, 'w', encoding='utf-8')
    except Exception:
        pass
if sys.stderr is None:
    try:
        sys.stderr = open(os.devnull, 'w', encoding='utf-8')
    except Exception:
        pass

if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from server import connectors
from server.audio_controller import audio_controller
from server.com_worker import com_worker
from server.actions import execute_action
from server.auth import auth_manager
from server import diagnostics, discord_ui, firewall, layouts, live_buttons, page_library, shell_actions, steam, templates, updater, webhooks
from server.action_catalog import GESTURES, validate_deck_config
from server.config_manager import CONFIG_FILE, config_manager
from server.connectors import discord as discord_connector, spotify, windows
from server.settings_store import settings
from server.system_scanner import system_scanner
from server.telemetry import Telemetry

from server.paths import BASE_DIR, CONFIG_DIR, FROZEN, PORT, STATIC_DIR, UPLOADS_DIR, VERSION

MAX_ICON_UPLOAD_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")
JPEG_SIGNATURE = bytes.fromhex("ffd8ff")
ICON_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

mimetypes.add_type("image/webp", ".webp")  # Windows has no mapping, so uploaded WEBP icons were served as octet-stream
os.makedirs(UPLOADS_DIR, exist_ok=True)

# A native crash (for example inside a Windows audio call) leaves no Python traceback.
# This writes one to crash.log next to the profile so it can be diagnosed afterwards.
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    _crash_log = open(os.path.join(CONFIG_DIR, "crash.log"), "a", buffering=1)
    faulthandler.enable(_crash_log)
except OSError:
    pass

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any], exclude: Optional[WebSocket] = None):
        targets = [c for c in list(self.active_connections) if not (exclude and c == exclude)]
        if not targets:
            return
        payload = json.dumps(message)
        async def _safe_send(ws):
            try:
                await ws.send_text(payload)
                return None
            except Exception:
                return ws
        dead = await asyncio.gather(*[_safe_send(c) for c in targets], return_exceptions=True)
        for d in dead:
            if isinstance(d, WebSocket):
                self.disconnect(d)

ws_manager = ConnectionManager()

# Buttons whose action is still running, so a second tap does not queue a duplicate.
_running_actions: Set[str] = set()
_background_tasks: Set[asyncio.Task] = set()
# Last known on/off state of toggle buttons (OBS recording and streaming).
button_states: Dict[str, bool] = {}


async def run_audio(fn, *args):
    """Run COM/audio work on the dedicated COM thread. Calls keep their order, so slider drags apply as made."""
    return await asyncio.wait_for(asyncio.wrap_future(com_worker.submit(fn, *args)), timeout=15)


# Volumes asked for an app that makes no sound yet: Windows only has an audio session for an app
# while it is playing, so the volume is remembered and applied the moment the app shows up.
_pending_app_volumes: Dict[str, int] = {}


def merge_sessions(sessions: list) -> list:
    """One entry per program. Windows lists a session per audio stream, so Discord or Chrome
    appear several times; the phone showed whichever came first, which looked like a bad sync."""
    merged: Dict[str, Dict[str, Any]] = {}
    for session in sessions:
        entry = merged.get(session["process_name"].lower())
        if entry is None:
            merged[session["process_name"].lower()] = dict(session)
        else:
            entry["volume"] = max(entry["volume"], session["volume"])
            entry["muted"] = entry["muted"] and session["muted"]
    return list(merged.values())


def read_audio_state() -> Dict[str, Any]:
    sessions = audio_controller.get_audio_sessions()
    for process, volume in list(_pending_app_volumes.items()):
        if any(s["process_name"].lower() == process for s in sessions):
            audio_controller.set_app_volume(process, volume)
            _pending_app_volumes.pop(process, None)
            sessions = audio_controller.get_audio_sessions()
    return {
        "master": audio_controller.get_master_volume(),
        "sessions": merge_sessions(sessions),
        "mic": {"muted": windows.get_mic_muted()},
    }


def audio_signature(state: Dict[str, Any]) -> tuple:
    master = state["master"]
    sessions = tuple(sorted(
        (s["process_name"], s["volume"], s["muted"]) for s in state["sessions"]
    ))
    return master.get("volume"), master.get("muted"), sessions, state["mic"]["muted"]


async def audio_sync_loop():
    """Push master and per-app volume/mute changes made on the PC to every phone."""
    last_signature = None
    while True:
        try:
            if ws_manager.active_connections:
                state = await run_audio(read_audio_state)
                signature = audio_signature(state)
                if signature != last_signature:
                    last_signature = signature
                    await ws_manager.broadcast({"type": "audio_state", **state})
            else:
                last_signature = None
        except Exception:
            pass
        # Four checks a second keep a volume moved on the PC and on the phone within half a second.
        await asyncio.sleep(0.4)

telemetry = Telemetry(auth_manager.get_local_ip)


async def telemetry_sync_loop():
    """Push CPU, RAM, GPU, VRAM, network and disk readings to every connected screen."""
    while True:
        try:
            if ws_manager.active_connections:
                reading = await asyncio.to_thread(telemetry.sample)
                await ws_manager.broadcast({"type": "telemetry_update", **reading})
        except Exception:
            pass
        await asyncio.sleep(1.0)


def foreground_process() -> str:
    """Name of the program whose window has the focus, lower case, or "" when there is none."""
    import psutil
    user32 = ctypes.windll.user32
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), ctypes.byref(pid))
    return psutil.Process(pid.value).name().lower() if pid.value else ""


def page_for_app(pages: list, process_name: str):
    """Index of the page set to open for this program, or None."""
    wanted = (process_name or "").lower()
    return next((i for i, page in enumerate(pages) if wanted and (page.get("auto_app") or "").lower() == wanted), None)


def page_for_discord(pages: list, server: str):
    """Index of the page set to open for this Discord server, or None."""
    wanted = (server or "").strip().lower()
    return next((i for i, page in enumerate(pages) if wanted and (page.get("auto_discord") or "").strip().lower() == wanted), None)


async def _open_page(index: int) -> None:
    if index != config_manager.get_config().get("current_page", 0) and config_manager.set_active_page(index):
        await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})


DISCORD_POLL_EVERY = 3  # loop ticks (seconds) between looks at Discord's voice bar


async def smart_page_loop():
    """Open the page of the program you are using, or of the Discord server you are talking in.

    Like Stream Deck's Smart Profiles. It reacts when the foreground program or the voice server
    changes, not on every tick, so moving the phone to another page by hand is not undone a second
    later. Discord is only looked at while some page asks for it, because reading its window keeps
    Discord's accessibility on.
    """
    last = None
    last_server = None
    tick = 0
    while True:
        try:
            pages = config_manager.get_config().get("pages", [])
            if any(page.get("auto_app") for page in pages):
                name = await asyncio.to_thread(foreground_process)
                if name and name != last:
                    last = name
                    index = page_for_app(pages, name)
                    if index is not None:
                        await _open_page(index)
            if any(page.get("auto_discord") for page in pages):
                if tick % DISCORD_POLL_EVERY == 0:
                    server = await asyncio.to_thread(discord_ui.current_voice_server)
                    if server != last_server:  # joining, moving to another server, or leaving (None)
                        last_server = server
                        index = page_for_discord(pages, server) if server else None
                        if index is not None:
                            await _open_page(index)
            else:
                last_server = None
        except Exception:
            pass
        tick += 1
        await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task = asyncio.create_task(audio_sync_loop())
    telemetry_task = asyncio.create_task(telemetry_sync_loop())
    smart_task = asyncio.create_task(smart_page_loop())
    yield
    sync_task.cancel()
    telemetry_task.cancel()
    smart_task.cancel()

# No interactive API docs: the schema would list every admin route to anyone on the Wi-Fi.
app = FastAPI(title="StreamDesk Pro Server", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    # The desktop Studio is intentionally a localhost-only administration
    # surface. The paired PWA communicates over its authenticated WebSocket.
    allow_origins=[f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def revalidate_app_files(request: Request, call_next):
    """Make the browser check for new Studio/PWA files on every load.

    Without this, a window that cached studio.js keeps running the old version
    after an update, because static files have no explicit cache lifetime.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"  # an uploaded file is never "sniffed" into a page
    if request.url.path.startswith(("/static/", "/studio")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


LOCAL_HOST_NAMES = {"localhost", "127.0.0.1", "::1"}


LOCAL_HOST_HEADER = re.compile(r"(localhost|127\.0\.0\.1|\[::1\])(:[0-9]{1,5})?", re.ASCII)


def _host_name(header: str) -> str:
    """The name in a Host header ("localhost:48291" -> "localhost", "[::1]:48291" -> "::1"), or "" when the
    header is not exactly a local name with an optional numeric port (so "localhost:1.evil.com" is not local)."""
    header = (header or "").strip().lower()
    match = LOCAL_HOST_HEADER.fullmatch(header)
    return match.group(1).strip("[]") if match else ""


def _local_browser_request(headers, client_host: str) -> bool:
    """True when a request that really comes from this PC was also addressed to it.

    A web page open in the user's own browser reaches localhost too, and DNS rebinding can make it do so under
    another name. Such a request carries a different Host (or, for a WebSocket, a foreign Origin), so refusing
    those keeps other websites from driving StreamDesk through the loopback address.
    """
    if not _is_loopback(client_host) or _host_name(headers.get("host", "")) not in LOCAL_HOST_NAMES:
        return False
    if headers.get("sec-fetch-site", "").lower() == "cross-site":
        return False  # the browser itself says another site started this request
    origin = headers.get("origin")
    return not origin or urlparse(origin).netloc.lower() == headers.get("host", "").strip().lower()


async def require_local_request(request: Request) -> None:
    """Keep configuration and system administration on the desktop computer."""
    client_host = request.client.host if request.client else ""
    if not _local_browser_request(request.headers, client_host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta operación solo está disponible desde StreamDesk Studio en el PC.",
        )

# --- Service Worker at Root Scope ---
@app.get("/service-worker.js")
async def serve_sw():
    sw_path = os.path.join(STATIC_DIR, "service-worker.js")
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"}
    )

@app.get("/manifest.json")
async def serve_manifest():
    manifest_path = os.path.join(STATIC_DIR, "manifest.json")
    return FileResponse(manifest_path, media_type="application/manifest+json")

# --- REST API Endpoints ---

# Handlers below that touch the network, COM, the registry or subprocesses are
# plain `def`, so FastAPI runs them in its thread pool instead of the event loop.

@app.get("/api/info")
def get_system_info(_: None = Depends(require_local_request)):
    ip = auth_manager.get_local_ip()
    return {
        "version": VERSION,
        "server_ip": ip,
        "port": PORT,
        "direct_url": f"http://{ip}:{PORT}",
        "studio_url": f"http://localhost:{PORT}/studio"
    }

@app.get("/api/auth/pin")
def get_pairing_pin(_: None = Depends(require_local_request)):
    return {
        "pin": auth_manager.get_current_pin(),
        "expires_in": auth_manager.pin_expires_in(),
        "qr_code": auth_manager.generate_qr_base64(PORT),
        "ip": auth_manager.get_local_ip(),
        "port": PORT
    }

@app.post("/api/auth/regenerate-pin")
def regenerate_pin(_: None = Depends(require_local_request)):
    new_pin = auth_manager.refresh_pin()
    return {
        "pin": new_pin,
        "expires_in": auth_manager.pin_expires_in(),
        "qr_code": auth_manager.generate_qr_base64(PORT),
        "ip": auth_manager.get_local_ip(),
        "port": PORT
    }

@app.post("/api/auth/verify")
async def verify_pin(payload: Dict[str, Any] = Body(...), request: Request = None):
    pin = str(payload.get("pin", ""))
    device_name = payload.get("device_name", "Smartphone")
    client_ip = request.client.host if request and request.client else ""
    user_agent = request.headers.get("user-agent") if request else None
    result = auth_manager.verify_pin_and_issue_token(pin, device_name, client_ip)
    if result.get("valid") or result.get("success"):
        diagnostics.record("ok", "Emparejado correctamente", client_ip, user_agent)
        return result
    diagnostics.record("error", result.get("error", "PIN inválido"), client_ip, user_agent)
    raise HTTPException(status_code=401, detail=result.get("error", "PIN inválido"))

@app.get("/api/auth/check")
async def check_token(token: str = Query(default=None), _: None = Depends(require_local_request)):
    authorized = auth_manager.is_token_authorized(token)
    return {"authorized": authorized, "valid": authorized}

THEMES = ("ctma", "cian", "violeta", "verde", "rojo", "rosa", "naranja")


def current_theme() -> str:
    theme = settings.get("ui").get("theme")
    return theme if theme in THEMES else "ctma"


@app.get("/api/system/firewall")
def firewall_status(_: None = Depends(require_local_request)):
    rule = firewall.rule_exists()
    # Windows may have made its own rule (under another name) when the user accepted its prompt.
    # A phone that already got through proves the way is open, so do not warn in that case.
    return {"allowed": rule or diagnostics.phone_reached(), "rule": rule, "port": PORT}


@app.post("/api/system/firewall/allow")
def firewall_allow(_: None = Depends(require_local_request)):
    """Opens Windows' own permission prompt; nothing changes unless the user accepts it."""
    return firewall.request_rule()


@app.post("/api/actions/test")
async def test_action(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    """Run one button's action once from Studio, to check it works. Same allow-list as a real button."""
    result = await asyncio.to_thread(
        execute_action, str(values.get("action_type", "")), str(values.get("target", "")), values.get("extra")
    )
    return {"success": bool(result.get("success")), "error": result.get("error", "")}


@app.get("/api/diagnostics")
def connection_diagnostics(_: None = Depends(require_local_request)):
    return {"events": diagnostics.recent()}


@app.get("/api/ui")
def get_ui_settings(_: None = Depends(require_local_request)):
    return {"theme": current_theme()}


@app.post("/api/ui")
async def set_ui_settings(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    theme = values.get("theme")
    if theme not in THEMES:
        raise HTTPException(status_code=422, detail="Tema no válido")
    settings.update("ui", {"theme": theme})
    await ws_manager.broadcast({"type": "theme", "theme": theme})
    return {"theme": theme}


@app.get("/api/auth/devices")
def list_paired_devices(_: None = Depends(require_local_request)):
    return {"devices": auth_manager.list_devices()}


@app.post("/api/auth/devices/revoke")
async def revoke_paired_device(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    token = auth_manager.token_for_device(str(values.get("id", "")))
    if not token or not auth_manager.revoke_token(token):
        raise HTTPException(status_code=404, detail="Ese móvil ya no está emparejado")
    # Cut the phone off now, not the next time it reconnects.
    for connection in list(ws_manager.active_connections):
        if getattr(connection.state, "token", None) == token:
            try:
                await connection.close(code=1008, reason="Dispositivo desvinculado")
            except Exception:
                pass
            ws_manager.disconnect(connection)
    return {"success": True}


def _grid() -> tuple:
    """(rows, columns) of the profile in use."""
    return layouts.size_of(config_manager.get_config().get("layout"))


@app.get("/api/layouts")
def list_layouts(_: None = Depends(require_local_request)):
    current = config_manager.get_config().get("layout") or layouts.layout_dict(layouts.DEFAULT_LAYOUT)
    presets = [{"id": name, **layouts.layout_dict(name)} for name in layouts.LAYOUTS]
    return {
        "current": layouts.layout_name(current["rows"], current["columns"]),
        "layout": current,
        "presets": presets,
        "layouts": presets,
        "limits": layouts.LIMITS,
    }


@app.post("/api/layout")
async def set_layout(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    """Change the grid size (a quick pick, "<columns>x<rows>" or columns and rows).

    Every page is converted; the old profile is kept as a backup first."""
    spec = values.get("layout") if "layout" in values else values
    try:
        converted, dropped = layouts.convert_config(config_manager.get_config(), spec)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if converted["layout"] != config_manager.get_config().get("layout"):
        config_manager.backup_profile("antes-de-cambiar-cuadricula")
    if not config_manager.save_config(converted):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo cambiar la cuadrícula")
    await prune_timers()
    await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "config": config_manager.get_config(), "dropped": dropped}


@app.get("/api/settings/commands")
def get_command_settings(_: None = Depends(require_local_request)):
    return {"enabled": shell_actions.enabled()}


@app.post("/api/settings/commands")
async def set_command_settings(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    """Switch console commands (PowerShell and cmd buttons) on or off. They are off until the user turns them on here."""
    enabled = values.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="«enabled» debe ser verdadero o falso")
    shell_actions.set_enabled(enabled)
    diagnostics.record("info", "Comandos de consola " + ("activados" if enabled else "desactivados") + " desde Studio")
    return {"enabled": shell_actions.enabled()}


@app.get("/api/settings/webhooks")
def get_webhook_settings(_: None = Depends(require_local_request)):
    return {"hosts": webhooks.allowed_hosts()}


@app.post("/api/settings/webhooks")
async def set_webhook_settings(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    """The hosts a webhook button may call. Empty by default: no webhook runs until a host is listed here."""
    try:
        hosts = webhooks.set_allowed_hosts(values.get("hosts"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    diagnostics.record("info", f"Destinos de webhook permitidos: {len(hosts)}, cambiados desde Studio")
    return {"hosts": hosts}


@app.get("/api/templates")
def list_templates(_: None = Depends(require_local_request)):
    """The library of pages: each with its category, the program it belongs to (if any) and a thumbnail."""
    listed = [{**template, "preview": templates.preview(template["id"])} for template in templates.TEMPLATES]
    return {"templates": listed, "categories": page_library.CATEGORIES}


@app.post("/api/templates/apply")
async def apply_template(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    cfg = copy.deepcopy(config_manager.get_config())
    try:
        page = templates.build_page(str(values.get("template_id", "")), str(values.get("name") or ""), _grid())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    dropped = page.pop("_dropped", 0)
    # Two pages for the same program would fight over who opens: only the first one opens by itself.
    program = (page.get("auto_app") or "").lower()
    if program and any((existing.get("auto_app") or "").lower() == program for existing in cfg["pages"]):
        page.pop("auto_app")
    cfg["pages"].append(page)
    if not config_manager.save_config(cfg):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo crear la página")
    await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "index": len(config_manager.get_config()["pages"]) - 1, "dropped": dropped,
            "auto_app": page.get("auto_app", "")}


@app.get("/api/steam/games")
def steam_games(_: None = Depends(require_local_request)):
    """The games installed in this PC's Steam, to choose one for a button."""
    return {"games": steam.installed_games()}


@app.get("/api/discord/sounds/cache")
def discord_sounds_cache(_: None = Depends(require_local_request)):
    """The sounds of the last reading, so picking one needs neither Discord nor a voice channel."""
    return {"options": discord_connector.saved_sounds()}


@app.post("/api/discord/server-page")
async def create_discord_server_page(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    """A page with the chosen sounds of one Discord server, opened by itself when the user is talking there."""
    server = str(values.get("server") or "").strip()
    labels = values.get("sounds")
    if not server or not isinstance(labels, list) or not all(isinstance(label, str) and label.strip() for label in labels):
        raise HTTPException(status_code=422, detail="Falta el servidor o los sonidos")
    try:
        page = templates.discord_server_page(server, [label.strip() for label in labels], _grid())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    cfg = copy.deepcopy(config_manager.get_config())
    pages = cfg["pages"]
    existing = page_for_discord(pages, server)
    if existing is not None:
        if not values.get("replace"):
            raise HTTPException(status_code=409, detail=f"Ya hay una página para «{server}»")
        page["id"], page["name"] = pages[existing]["id"], pages[existing]["name"]  # keep what the user may have renamed
        pages[existing] = page
        index = existing
    else:
        pages.append(page)
        index = len(pages) - 1
    if not config_manager.save_config(cfg):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo crear la página")
    await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "index": index, "replaced": existing is not None}


@app.get("/api/profile/export")
def export_profile(_: None = Depends(require_local_request)):
    """The whole profile as a file. It holds layouts only: no passwords, tokens or paired phones."""
    return JSONResponse(config_manager.get_config(), headers={
        "Content-Disposition": 'attachment; filename="streamdesk-perfil.json"',
    })


@app.post("/api/profile/save-copy")
def save_profile_copy(_: None = Depends(require_local_request)):
    """Write the profile to Documents\\StreamDesk. Reliable where a browser download may be blocked."""
    folder = os.path.join(os.path.expanduser("~"), "Documents", "StreamDesk")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, time.strftime("streamdesk-perfil-%Y%m%d-%H%M%S.json"))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config_manager.get_config(), handle, indent=2, ensure_ascii=False)
    return {"path": path}


@app.post("/api/profile/import")
async def import_profile(profile: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    """Replace the profile with one from a file. The file is untrusted, so it goes through the same
    validation as anything a phone could trigger, and the current profile is kept as a backup."""
    try:
        clean = validate_deck_config(profile)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"El archivo no es un perfil válido: {exc}")
    backup = os.path.join(os.path.dirname(CONFIG_FILE), f"deck_config.backup-{int(time.time())}.json")
    try:
        shutil.copy2(CONFIG_FILE, backup)
    except OSError:
        backup = ""
    if not config_manager.save_config(clean):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo importar el perfil")
    await prune_timers()
    await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "pages": len(clean["pages"]), "backup": bool(backup)}


@app.post("/api/deck/page/duplicate")
async def duplicate_deck_page(page_index: int = Body(..., embed=True), _: None = Depends(require_local_request)):
    cfg = copy.deepcopy(config_manager.get_config())
    pages = cfg["pages"]
    if not 0 <= page_index < len(pages):
        raise HTTPException(status_code=404, detail="Esa página no existe")
    clone = copy.deepcopy(pages[page_index])
    clone["id"] = f"page_{uuid.uuid4().hex[:6]}"
    clone["name"] = f"{clone['name']} (copia)"[:40]
    clone.pop("auto_app", None)  # two pages for the same program would be ambiguous
    clone.pop("auto_discord", None)  # and so would two for the same Discord server
    pages.insert(page_index + 1, clone)
    if not config_manager.save_config(cfg):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo duplicar la página")
    await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "index": page_index + 1}


@app.get("/api/config")
@app.get("/api/deck/config")
async def get_configuration(_: None = Depends(require_local_request)):
    return config_manager.get_config()

@app.post("/api/config")
@app.post("/api/deck/config")
async def update_configuration(new_config: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    success = config_manager.save_config(new_config)
    if success:
        # Send what was validated and saved, never the raw payload the caller posted.
        saved = config_manager.get_config()
        await prune_timers()
        await ws_manager.broadcast({
            "type": "config_updated",
            "config": saved
        })
        return {"success": True, "config": saved}
    raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo guardar la configuración")

@app.post("/api/deck/page/switch")
async def switch_deck_page(page_index: int = Body(..., embed=True), _: None = Depends(require_local_request)):
    success = config_manager.set_active_page(page_index)
    if success:
        await ws_manager.broadcast({
            "type": "config_sync",
            "config": config_manager.get_config()
        })
    return {"success": success, "current_page": config_manager.get_config().get("current_page", 0)}

@app.post("/api/deck/page/add")
async def add_deck_page(name: str = Body(default="Nueva Página", embed=True), _: None = Depends(require_local_request)):
    cfg = copy.deepcopy(config_manager.get_config())  # a copy: a refused page must not stay in the live profile
    pages = cfg.setdefault("pages", [])
    page_name = name or f"Página {len(pages) + 1}"
    rows, columns = _grid()
    new_slots: List[Dict[str, Any]] = [{"index": i, "type": "empty"} for i in range(rows * columns)]
    # Two faders in the last two columns, as the original 6x2 page had them.
    master_col, app_col = columns - 2, columns - 1
    new_slots[master_col] = {"index": master_col, "type": "slider", "id": f"slider_master_{uuid.uuid4().hex[:4]}", "label": "Master", "sublabel": "PC", "slider_type": "master", "color": "#0ea5e9", "row_span": 2, "icon": "/static/icons/volume_up.svg", "image": "/static/icons/volume_up.svg"}
    new_slots[app_col] = {"index": app_col, "type": "slider", "id": f"slider_app_{uuid.uuid4().hex[:4]}", "label": "App", "sublabel": "Audio", "slider_type": "app_dynamic", "target_app": "Spotify.exe", "color": "#a855f7", "row_span": 2, "icon": "/static/icons/spotify.svg", "image": "/static/icons/spotify.svg"}
    for col in (master_col, app_col):
        new_slots[col + columns] = {"index": col + columns, "type": "occupied_by_slider", "id": f"slot_{col + columns}_{uuid.uuid4().hex[:4]}", "parent_slot": col}
    pages.append({"id": f"page_{uuid.uuid4().hex[:6]}", "name": page_name, "slots": new_slots})
    if not config_manager.save_config(cfg):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo crear la página")
    await ws_manager.broadcast({
        "type": "config_sync",
        "config": config_manager.get_config()
    })
    return {"success": True, "pages": pages}

@app.post("/api/deck/page/delete")
async def delete_deck_page(page_index: int = Body(..., embed=True), _: None = Depends(require_local_request)):
    cfg = config_manager.get_config()
    pages = cfg.get("pages", [])
    if len(pages) > 1 and 0 <= page_index < len(pages):
        pages.pop(page_index)
        cfg["current_page"] = min(cfg.get("current_page", 0), len(pages) - 1)
        config_manager.save_config(cfg)
        await prune_timers()
        await ws_manager.broadcast({
            "type": "config_sync",
            "config": config_manager.get_config()
        })
        return {"success": True, "pages": pages}
    return {"success": False, "error": "No se puede borrar la única página"}

@app.get("/api/audio/sessions")
async def get_audio_sessions(_: None = Depends(require_local_request)):
    return await run_audio(read_audio_state)

@app.get("/api/system/apps")
def get_system_apps(_: None = Depends(require_local_request)):
    return {
        "apps": system_scanner.get_detected_apps()
    }

@app.post("/api/upload")
async def upload_button_image(file: UploadFile = File(...), _: None = Depends(require_local_request)):
    try:
        if not ICON_CONTENT_TYPES.get((file.content_type or "").lower()):
            raise HTTPException(status_code=415, detail="El icono debe ser PNG, JPG o WEBP")
        content = await file.read(MAX_ICON_UPLOAD_BYTES + 1)
        if len(content) > MAX_ICON_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="El icono no puede superar 2 MB")
        # The declared type is the client's word; the first bytes say what the file really is.
        if content.startswith(PNG_SIGNATURE):
            ext = ".png"
        elif content.startswith(JPEG_SIGNATURE):
            ext = ".jpg"
        elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            ext = ".webp"
        else:
            raise HTTPException(status_code=415, detail="El archivo no es una imagen PNG, JPG o WEBP válida")
        filename = f"btn_{uuid.uuid4().hex[:10]}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as buffer:
            buffer.write(content)
        return {"success": True, "url": f"/uploads/{filename}"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await file.close()

# --- Connectors (OBS, Spotify, Discord, Windows) ---

def _connector(connector_id: str):
    try:
        return connectors.get(connector_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Conector desconocido")


@app.get("/api/connectors")
def list_connectors(_: None = Depends(require_local_request)):
    return {"connectors": connectors.describe_all()}


@app.get("/api/connectors/catalog")
def connectors_catalog(_: None = Depends(require_local_request)):
    """Ready-made buttons of every connector, without checking whether each service is running."""
    return {"connectors": [{**module.INFO, "actions": module.actions()} for module in connectors.REGISTRY.values()]}


@app.get("/api/connectors/{connector_id}/options/{name}")
def connector_options(connector_id: str, name: str, _: None = Depends(require_local_request)):
    module = _connector(connector_id)
    try:
        return {"options": module.options(name)}
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.post("/api/connectors/{connector_id}/configure")
def configure_connector(connector_id: str, values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    module = _connector(connector_id)
    if not hasattr(module, "configure"):
        raise HTTPException(status_code=404, detail="Este conector no tiene ajustes")
    try:
        return {"success": True, "settings": module.configure(values)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/connectors/spotify/connect")
def spotify_connect(_: None = Depends(require_local_request)):
    try:
        return spotify.begin_login()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/connectors/spotify/disconnect")
def spotify_disconnect(_: None = Depends(require_local_request)):
    return {"success": True, "settings": spotify.disconnect()}


@app.get("/api/connectors/spotify/callback", response_class=HTMLResponse)
def spotify_callback(code: str = "", state: str = "", error: str = "", _: None = Depends(require_local_request)):
    """Spotify sends the browser back here after the user accepts. Only reachable from this PC."""
    page = "<!doctype html><meta charset='utf-8'><title>StreamDesk</title><body style='font-family:sans-serif;padding:2rem'><h2>{}</h2><p>{}</p>"
    if error or not code:
        return HTMLResponse(page.format("Spotify no se conectó", "Cancelaste el permiso o Spotify lo rechazó. Cierra esta pestaña e inténtalo de nuevo."), status_code=400)
    try:
        spotify.finish_login(code, state)
    except spotify.SpotifyError as exc:
        return HTMLResponse(page.format("Spotify no se conectó", str(exc)), status_code=400)
    return HTMLResponse(page.format("Spotify conectado", "Ya puedes cerrar esta pestaña y volver a StreamDesk."))


# --- GitHub Auto-Update Endpoints ---

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _git(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=BASE_DIR,
        timeout=timeout, creationflags=NO_WINDOW,
    )


def _is_git_checkout() -> bool:
    return not FROZEN and os.path.isdir(os.path.join(BASE_DIR, ".git"))


@app.get("/api/system/check-update")
def check_github_update(_: None = Depends(require_local_request)):
    """The installed app compares itself with the latest GitHub release; a git checkout, with the latest commit."""
    if FROZEN:
        try:
            info = updater.updater.release_info(VERSION)
        except Exception as exc:
            return {"current_version": VERSION, "update_available": False, "can_update": True, "mode": "release",
                    "status": "offline", "info": str(exc)}
        return {**info, "can_update": True, "mode": "release", "commit_message": f"v{info['latest_version']}"}
    status_info: Dict[str, Any] = {"current_version": VERSION, "update_available": False, "can_update": _is_git_checkout()}
    if not status_info["can_update"]:
        # An installed build has no git history, so there is nothing to pull.
        status_info["status"] = "not_a_git_checkout"
        return status_info

    try:
        local_hash = _git("rev-parse", "HEAD").stdout.strip()
        req = urllib.request.Request(
            "https://api.github.com/repos/Zak208/streamdeck/commits/main",
            headers={"User-Agent": "StreamDesk-Updater"},
        )
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
        remote_hash = data.get("sha", "")
        # If the remote commit is already part of our history we are ahead or equal, not behind.
        already_have_it = bool(remote_hash) and _git("merge-base", "--is-ancestor", remote_hash, "HEAD").returncode == 0
        status_info.update({
            "local_hash": local_hash[:7] or "local",
            "remote_hash": remote_hash[:7] or "latest",
            "update_available": bool(local_hash and remote_hash and not already_have_it),
            "commit_message": data.get("commit", {}).get("message", "").split("\n")[0],
        })
    except Exception as e:
        status_info.update({"status": "offline", "info": str(e)})
    return status_info


@app.post("/api/system/apply-update")
def apply_github_update(_: None = Depends(require_local_request)):
    """The installed app downloads and runs the new installer; a git checkout fast-forwards to the latest commit."""
    if FROZEN:
        started = updater.updater.start(VERSION)
        return {"success": True, "started": started, "mode": "release"}
    if not _is_git_checkout():
        return {
            "success": False,
            "output": "Esta instalación no se actualiza desde Git. Descarga el instalador nuevo desde GitHub.",
        }
    try:
        res = _git("pull", "--ff-only", "origin", "main", timeout=60)
        return {"success": res.returncode == 0, "output": res.stdout + res.stderr}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system/update-status")
def update_status(_: None = Depends(require_local_request)):
    """Progress of an update that is downloading or installing (installed app only)."""
    return updater.updater.status()


# --- WebSocket Channel ---

_page_history: list = []  # pages left through a page button, newest last: what "Volver" goes back to
button_labels: Dict[str, str] = {}  # live text of keys (a counter's value, a timer's countdown)
_timers: Dict[str, "asyncio.Task"] = {}


async def set_button_label(btn_id: str, text: Optional[str]) -> None:
    """Show `text` under the key on every phone; None gives the key its own subtitle back."""
    if text is None:
        button_labels.pop(btn_id, None)
    else:
        button_labels[btn_id] = text
    await ws_manager.broadcast({"type": "button_label", "id": btn_id, "sublabel": text})


def current_labels(config: Dict[str, Any]) -> Dict[str, str]:
    """Counters show their saved value as soon as a phone connects, then any live text on top."""
    labels = {
        slot["id"]: str(live_buttons.counter_value(slot["id"]))
        for slot in config.get("slots", []) if slot.get("type") == "button" and slot.get("action_type") == "counter"
    }
    labels.update(button_labels)
    return labels


async def prune_timers() -> None:
    """Stop the timers of keys that are no longer in the profile (deleted, or lost in a grid change)."""
    config = config_manager.get_config()
    timer_keys = {
        slot["id"] for page in config.get("pages", []) for slot in page.get("slots", [])
        if slot.get("type") == "button" and "timer" in (slot.get("action_type"), (slot.get("long_press") or {}).get("action_type"),
                                                       (slot.get("double_tap") or {}).get("action_type"),
                                                       ((slot.get("alt") or {}).get("action") or {}).get("action_type"))
    }
    for btn_id in [key for key in _timers if key not in timer_keys]:
        task = _timers.pop(btn_id, None)
        if task and not task.done():
            task.cancel()


async def run_timer(btn_id: str, seconds: int) -> Dict[str, Any]:
    """Start a countdown on a key, or stop it if it is running."""
    running = _timers.pop(btn_id, None)
    if running and not running.done():
        running.cancel()
        await set_button_label(btn_id, None)
        button_states[btn_id] = False
        await ws_manager.broadcast({"type": "button_state", "id": btn_id, "active": False})
        return {"success": True, "action": "timer_stop", "active": False}

    async def countdown() -> None:
        try:
            for remaining in range(seconds, 0, -1):
                await set_button_label(btn_id, live_buttons.format_countdown(remaining))
                await asyncio.sleep(1)
            await set_button_label(btn_id, "¡Hecho!")
            await asyncio.to_thread(execute_action, "sound", "exclamation", {})
            await asyncio.sleep(3)
        finally:
            _timers.pop(btn_id, None)
            await set_button_label(btn_id, None)
            button_states[btn_id] = False
            await ws_manager.broadcast({"type": "button_state", "id": btn_id, "active": False})

    task = asyncio.create_task(countdown())
    _timers[btn_id] = task
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"success": True, "action": "timer_start", "active": True}


async def navigate_pages(target: str) -> Dict[str, Any]:
    """A button that moves the phone to another page: next, previous, first, or a specific page id."""
    config = config_manager.get_config()
    pages = config.get("pages", [])
    current = config.get("current_page", 0)
    if target == "back":
        while _page_history and not any(p["id"] == _page_history[-1] for p in pages):
            _page_history.pop()  # that page was deleted
        if not _page_history:
            return {"success": False, "error": "No hay una página anterior a la que volver"}
        wanted = _page_history.pop()
        index = next(i for i, page in enumerate(pages) if page["id"] == wanted)
        if index != current and config_manager.set_active_page(index):
            await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
        return {"success": True, "action": "page"}
    if target == "next":
        index = (current + 1) % len(pages)
    elif target == "prev":
        index = (current - 1) % len(pages)
    elif target == "first":
        index = 0
    else:
        index = next((i for i, page in enumerate(pages) if page["id"] == target), None)
    if index is None:
        return {"success": False, "error": "Esa página ya no existe"}
    if index != current:
        previous = pages[current]["id"] if 0 <= current < len(pages) else None
        if config_manager.set_active_page(index):
            if previous:
                _page_history.append(previous)
                del _page_history[:-20]
            await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "action": "page"}


def _record_button_failure(websocket: WebSocket, label: str, message: str) -> None:
    """Keep why a button did nothing where Studio's diagnostics can show it."""
    ip = websocket.client.host if websocket.client else ""
    diagnostics.record("error", f"Botón «{str(label)[:60]}»: {str(message)[:200]}", ip, websocket.headers.get("user-agent"))


async def run_button_action(websocket: WebSocket, slot: Dict[str, Any], gesture: str = "tap") -> None:
    """Execute a button off the event loop and tell every phone how it went."""
    btn_id = slot.get("id")
    try:
        try:
            if slot.get("action_type") == "page":
                result = await navigate_pages(str(slot.get("target", "")))
            elif slot.get("action_type") == "counter":
                value = await asyncio.to_thread(
                    live_buttons.change_counter, btn_id, slot.get("target"), (slot.get("extra") or {}).get("step", 1))
                await set_button_label(btn_id, str(value))
                result = {"success": True, "action": "counter", "value": value}
            elif slot.get("action_type") == "timer":
                result = await run_timer(btn_id, int((slot.get("extra") or {}).get("seconds", 60)))
            else:
                result = await asyncio.to_thread(
                    execute_action, slot.get("action_type"), slot.get("target"), slot.get("extra")
                )
        except Exception as exc:
            result = {"success": False, "error": str(exc)}

        success = bool(result.get("success"))
        payload: Dict[str, Any] = {
            "type": "action_result",
            "id": btn_id,
            "slot_id": btn_id,
            "success": success,
            "result": result,
        }
        if not success:
            payload["message"] = result.get("error") or "No se pudo ejecutar la acción"
            _record_button_failure(websocket, slot.get("label") or btn_id, payload["message"])
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception:
            pass  # the phone went away while the action was running

        # Actions with a lasting on/off state (recording, streaming, a muted mic) report it as "active".
        # Only the tap sets the lit/unlit state: a long press or double tap may run a different action.
        if success and "active" in result and gesture == "tap":
            button_states[btn_id] = bool(result["active"])
            await ws_manager.broadcast({"type": "button_state", "id": btn_id, "active": button_states[btn_id]})
        elif success and slot.get("toggle") and gesture == "tap":
            # A two-state key: every successful tap flips it, whatever the action reports.
            button_states[btn_id] = not button_states.get(btn_id, False)
            await ws_manager.broadcast({"type": "button_state", "id": btn_id, "active": button_states[btn_id]})
    finally:
        _running_actions.discard(btn_id)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default=None)):
    client_ip = websocket.client.host if websocket.client else ""
    is_localhost = _is_loopback(client_ip)

    user_agent = websocket.headers.get("user-agent")
    if is_localhost and not _local_browser_request(websocket.headers, client_ip):
        # Loopback needs no token, so a page from another site (or another name for localhost) must not get in.
        diagnostics.record("error", "Conexión local rechazada: viene de otra web (Origin o Host no coinciden)", client_ip, user_agent)
        await websocket.close(code=1008, reason="Origen no permitido.")
        return
    if not is_localhost and not auth_manager.is_token_authorized(token):
        diagnostics.record("error", "Conexión rechazada: el móvil no está emparejado (código 1008)", client_ip, user_agent)
        await websocket.close(code=1008, reason="No autorizado. Empareja primero con el PIN.")
        return

    await ws_manager.connect(websocket)
    websocket.state.token = token
    if not is_localhost:
        diagnostics.record("ok", "Móvil conectado", client_ip, user_agent)

    try:
        audio_state = await run_audio(read_audio_state)
        init_state = {
            "type": "init_state",
            "config": config_manager.get_config(),
            "master": audio_state["master"],
            "sessions": audio_state["sessions"],
            "mic": audio_state["mic"],
            "theme": current_theme(),
            "button_states": button_states,
            "button_labels": current_labels(config_manager.get_config()),
        }
        await websocket.send_text(json.dumps(init_state))

        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                msg_type = data.get("type")

                if msg_type == "switch_page":
                    page_idx = int(data.get("page", 0))
                    if config_manager.set_active_page(page_idx):
                        await ws_manager.broadcast({
                            "type": "config_sync",
                            "config": config_manager.get_config()
                        })

                elif msg_type == "trigger_button":
                    btn_id = data.get("id")
                    config = config_manager.get_config()
                    slots = config.get("slots", [])
                    slot = next((s for s in slots if s.get("id") == btn_id), None)
                    gesture = data.get("gesture") or "tap"
                    rejection = None
                    if not slot or slot.get("type") != "button":
                        # The phone shows a page the PC no longer has active (or an old layout). Say so: a tap that
                        # does nothing and says nothing cannot be told apart from a broken button.
                        rejection = "Ese botón no está en la página activa del PC. Cambia de página o espera a que se actualice el móvil."
                    elif slot.get("disabled"):
                        rejection = "Este botón está desactivado. Actívalo en Studio para usarlo."
                    elif gesture != "tap" and (gesture not in GESTURES or not slot.get(gesture)):
                        rejection = "Este botón no tiene ninguna acción para ese gesto."
                    if rejection:
                        _record_button_failure(websocket, str(btn_id), rejection)
                        await websocket.send_text(json.dumps({
                            "type": "action_result", "id": btn_id, "slot_id": btn_id, "success": False,
                            "message": rejection, "result": {"success": False, "error": rejection},
                        }))
                    elif btn_id not in _running_actions:
                        if gesture != "tap":
                            # A long press or a double tap runs its own action in place of the button's usual one.
                            slot = {**slot, **{key: slot[gesture][key] for key in ("action_type", "target", "extra")}}
                        elif slot.get("toggle") and button_states.get(btn_id) and (slot.get("alt") or {}).get("action"):
                            # A two-state key that is "on" runs the action of its second state.
                            slot = {**slot, **{key: slot["alt"]["action"][key] for key in ("action_type", "target", "extra")}}
                        # Mark it busy now, not when the task starts: two quick taps arrive before
                        # the first task gets to run and would both pass the check.
                        _running_actions.add(btn_id)
                        # Run it as its own task: a macro or a slow OBS call must not
                        # hold up this phone's faders or anyone else's messages.
                        task = asyncio.create_task(run_button_action(websocket, slot, gesture))
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)

                elif msg_type == "set_master_volume":
                    vol = int(data.get("volume", 0))
                    vol = max(0, min(100, vol))
                    res = await run_audio(audio_controller.set_master_volume, vol)
                    await ws_manager.broadcast({
                        "type": "master_volume_updated",
                        "volume": vol,
                        "muted": res.get("muted", False)
                    }, exclude=websocket)

                elif msg_type == "toggle_master_mute":
                    res = await run_audio(audio_controller.toggle_master_mute)
                    await ws_manager.broadcast({
                        "type": "master_mute_updated",
                        "muted": res.get("muted", False)
                    })

                elif msg_type == "set_app_volume":
                    proc = data.get("process")
                    vol = int(data.get("volume", 0))
                    vol = max(0, min(100, vol))
                    if proc:
                        applied = await run_audio(audio_controller.set_app_volume, proc, vol)
                        if applied.get("success"):
                            _pending_app_volumes.pop(proc.lower(), None)
                        else:
                            _pending_app_volumes[proc.lower()] = vol
                        await ws_manager.broadcast({
                            "type": "app_volume_updated",
                            "process": proc,
                            "volume": vol
                        }, exclude=websocket)

                elif msg_type == "toggle_app_mute":
                    proc = data.get("process")
                    if proc:
                        res = await run_audio(audio_controller.toggle_app_mute, proc)
                        await ws_manager.broadcast({
                            "type": "app_mute_updated",
                            "process": proc,
                            "muted": res.get("muted", False)
                        })

                elif msg_type == "refresh_sessions":
                    sessions = (await run_audio(read_audio_state))["sessions"]
                    await websocket.send_text(json.dumps({
                        "type": "sessions_update",
                        "sessions": sessions
                    }))

            except json.JSONDecodeError:
                pass
            except (TypeError, ValueError, AttributeError, KeyError, OverflowError, RecursionError):
                # A message of the wrong shape (a list, a volume that is not a number...) is ignored,
                # it must not drop this phone's connection.
                diagnostics.record("error", "Mensaje del móvil con formato inválido, ignorado", client_ip, user_agent)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        if not is_localhost:
            diagnostics.record("info", "Móvil desconectado", client_ip, user_agent)
    except Exception as exc:
        ws_manager.disconnect(websocket)
        if not is_localhost:
            diagnostics.record("error", f"La conexión del móvil falló en el PC: {type(exc).__name__}", client_ip, user_agent)

# --- Static Web Pages ---

@app.get("/studio", response_class=HTMLResponse)
async def serve_studio(_: None = Depends(require_local_request)):
    studio_path = os.path.join(STATIC_DIR, "studio.html")
    if os.path.exists(studio_path):
        return FileResponse(studio_path)
    return "<h1>Studio not found</h1>"

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
async def serve_root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return "<h1>StreamDeck UI not found</h1>"

if __name__ == "__main__":
    import uvicorn
    ip = auth_manager.get_local_ip()
    print("==================================================================")
    print(f"[*] STREAMDESK PRO SERVER v{VERSION} EN PUERTO {PORT}")
    print(f"[*] Panel PC (Studio):      http://localhost:{PORT}/studio")
    print(f"[*] Conexion Movil (Wi-Fi): http://{ip}:{PORT}")
    print(f"[*] Codigo PIN de Enlace:   {auth_manager.current_pin}")
    print("==================================================================")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
