import copy
import faulthandler
import os
import sys
import shutil
import asyncio
import json
import uuid
import subprocess
import urllib.request
from contextlib import asynccontextmanager
from typing import Set, Dict, Any, Optional
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
from server import diagnostics, firewall, templates
from server.config_manager import config_manager
from server.connectors import spotify, windows
from server.settings_store import settings
from server.system_scanner import system_scanner

from server.paths import BASE_DIR, CONFIG_DIR, FROZEN, PORT, STATIC_DIR, UPLOADS_DIR, VERSION

MAX_ICON_UPLOAD_BYTES = 2 * 1024 * 1024
ICON_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

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


def read_audio_state() -> Dict[str, Any]:
    return {
        "master": audio_controller.get_master_volume(),
        "sessions": audio_controller.get_audio_sessions(),
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
        await asyncio.sleep(1.0)

async def telemetry_sync_loop():
    import psutil
    while True:
        try:
            if ws_manager.active_connections:
                cpu = int(psutil.cpu_percent())
                ram = int(psutil.virtual_memory().percent)
                disk = int(psutil.disk_usage("C:").percent) if os.path.exists("C:") else 0
                await ws_manager.broadcast({
                    "type": "telemetry_update",
                    "cpu": cpu,
                    "ram": ram,
                    "disk": disk
                })
        except Exception:
            pass
        await asyncio.sleep(1.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task = asyncio.create_task(audio_sync_loop())
    telemetry_task = asyncio.create_task(telemetry_sync_loop())
    yield
    sync_task.cancel()
    telemetry_task.cancel()

app = FastAPI(title="StreamDesk Pro Server", version=VERSION, lifespan=lifespan)

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
    if request.url.path.startswith(("/static/", "/studio")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache"
    return response


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"}


async def require_local_request(request: Request) -> None:
    """Keep configuration and system administration on the desktop computer."""
    client_host = request.client.host if request.client else ""
    if not _is_loopback(client_host):
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

THEMES = ("ctma", "cian")


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


@app.get("/api/templates")
def list_templates(_: None = Depends(require_local_request)):
    return {"templates": templates.TEMPLATES}


@app.post("/api/templates/apply")
async def apply_template(values: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    try:
        page = templates.build_page(str(values.get("template_id", "")), str(values.get("name") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    cfg = copy.deepcopy(config_manager.get_config())
    cfg["pages"].append(page)
    if not config_manager.save_config(cfg):
        raise HTTPException(status_code=422, detail=config_manager.last_error or "No se pudo crear la página")
    await ws_manager.broadcast({"type": "config_sync", "config": config_manager.get_config()})
    return {"success": True, "index": len(config_manager.get_config()["pages"]) - 1}


@app.get("/api/config")
@app.get("/api/deck/config")
async def get_configuration(_: None = Depends(require_local_request)):
    return config_manager.get_config()

@app.post("/api/config")
@app.post("/api/deck/config")
async def update_configuration(new_config: Dict[str, Any] = Body(...), _: None = Depends(require_local_request)):
    success = config_manager.save_config(new_config)
    if success:
        await ws_manager.broadcast({
            "type": "config_updated",
            "config": new_config
        })
        return {"success": True, "config": new_config}
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
    cfg = config_manager.get_config()
    pages = cfg.setdefault("pages", [])
    page_name = name or f"Página {len(pages) + 1}"
    new_slots = [{"index": i, "type": "empty", "id": f"slot_{i}_{uuid.uuid4().hex[:4]}", "label": "Vacío"} for i in range(12)]
    new_slots[4] = {"index": 4, "type": "slider", "id": f"slider_master_{uuid.uuid4().hex[:4]}", "label": "Master", "sublabel": "PC", "slider_type": "master", "color": "#0ea5e9", "row_span": 2, "icon": "/static/icons/volume_up.svg", "image": "/static/icons/volume_up.svg"}
    new_slots[5] = {"index": 5, "type": "slider", "id": f"slider_app_{uuid.uuid4().hex[:4]}", "label": "App", "sublabel": "Audio", "slider_type": "app_dynamic", "target_app": "Spotify.exe", "color": "#a855f7", "row_span": 2, "icon": "/static/icons/spotify.svg", "image": "/static/icons/spotify.svg"}
    new_slots[10] = {"index": 10, "type": "occupied_by_slider", "id": f"slot_10_{uuid.uuid4().hex[:4]}", "parent_slot": 4}
    new_slots[11] = {"index": 11, "type": "occupied_by_slider", "id": f"slot_11_{uuid.uuid4().hex[:4]}", "parent_slot": 5}
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
        ext = ICON_CONTENT_TYPES.get((file.content_type or "").lower())
        if not ext:
            raise HTTPException(status_code=415, detail="El icono debe ser PNG, JPG o WEBP")
        content = await file.read(MAX_ICON_UPLOAD_BYTES + 1)
        if len(content) > MAX_ICON_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="El icono no puede superar 2 MB")
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
    """Compares this checkout with the latest commit on GitHub."""
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
    """Fast-forwards this checkout to the latest commit on GitHub."""
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

# --- WebSocket Channel ---

async def run_button_action(websocket: WebSocket, slot: Dict[str, Any]) -> None:
    """Execute a button off the event loop and tell every phone how it went."""
    btn_id = slot.get("id")
    _running_actions.add(btn_id)
    try:
        try:
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
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception:
            pass  # the phone went away while the action was running

        # Actions with a lasting on/off state (recording, streaming, a muted mic) report it as "active".
        if success and "active" in result:
            button_states[btn_id] = bool(result["active"])
            await ws_manager.broadcast({"type": "button_state", "id": btn_id, "active": button_states[btn_id]})
    finally:
        _running_actions.discard(btn_id)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default=None)):
    client_ip = websocket.client.host if websocket.client else ""
    is_localhost = _is_loopback(client_ip)

    user_agent = websocket.headers.get("user-agent")
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
                    if slot and slot.get("type") == "button" and btn_id not in _running_actions:
                        # Run it as its own task: a macro or a slow OBS call must not
                        # hold up this phone's faders or anyone else's messages.
                        task = asyncio.create_task(run_button_action(websocket, slot))
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
                        await run_audio(audio_controller.set_app_volume, proc, vol)
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
