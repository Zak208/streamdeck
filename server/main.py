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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Body, UploadFile, File
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

from server.audio_controller import audio_controller
from server.actions import execute_action
from server.auth import auth_manager
from server.config_manager import config_manager
from server.system_scanner import system_scanner

PORT = 48291
VERSION = "2.1.0"

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    STATIC_DIR = os.path.join(BASE_DIR, "static")
    UPLOADS_DIR = os.path.join(os.path.expandvars(r"%APPDATA%\StreamDesk"), "uploads")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    STATIC_DIR = os.path.join(BASE_DIR, "static")
    UPLOADS_DIR = os.path.join(STATIC_DIR, "uploads")

os.makedirs(UPLOADS_DIR, exist_ok=True)

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
        dead = []
        payload = json.dumps(message)
        for conn in list(self.active_connections):
            if exclude and conn == exclude:
                continue
            try:
                await conn.send_text(payload)
            except Exception:
                dead.append(conn)
        for d in dead:
            self.disconnect(d)

ws_manager = ConnectionManager()

async def audio_sync_loop():
    last_master = None
    while True:
        try:
            curr_master = audio_controller.get_master_volume()
            if curr_master != last_master:
                last_master = curr_master
                sessions = audio_controller.get_audio_sessions()
                await ws_manager.broadcast({
                    "type": "audio_state",
                    "master": curr_master,
                    "sessions": sessions
                })
        except Exception:
            pass
        await asyncio.sleep(1.2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task = asyncio.create_task(audio_sync_loop())
    yield
    sync_task.cancel()

app = FastAPI(title="StreamDesk Pro Server", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/api/info")
async def get_system_info():
    ip = auth_manager.get_local_ip()
    return {
        "version": VERSION,
        "server_ip": ip,
        "port": PORT,
        "direct_url": f"http://{ip}:{PORT}",
        "studio_url": f"http://localhost:{PORT}/studio"
    }

@app.get("/api/auth/pin")
async def get_pairing_pin():
    return {
        "pin": auth_manager.current_pin,
        "qr_code": auth_manager.generate_qr_base64(PORT),
        "ip": auth_manager.get_local_ip(),
        "port": PORT
    }

@app.post("/api/auth/regenerate-pin")
async def regenerate_pin():
    new_pin = auth_manager.refresh_pin()
    return {
        "pin": new_pin,
        "qr_code": auth_manager.generate_qr_base64(PORT),
        "ip": auth_manager.get_local_ip(),
        "port": PORT
    }

@app.post("/api/auth/verify")
async def verify_pin(payload: Dict[str, Any] = Body(...)):
    pin = str(payload.get("pin", ""))
    device_name = payload.get("device_name", "Smartphone")
    result = auth_manager.verify_pin_and_issue_token(pin, device_name)
    if result.get("valid"):
        return result
    raise HTTPException(status_code=401, detail=result.get("error", "PIN inválido"))

@app.get("/api/config")
async def get_configuration():
    return config_manager.get_config()

@app.post("/api/config")
async def update_configuration(new_config: Dict[str, Any] = Body(...)):
    success = config_manager.save_config(new_config)
    if success:
        await ws_manager.broadcast({
            "type": "config_updated",
            "config": new_config
        })
        return {"success": True, "config": new_config}
    raise HTTPException(status_code=500, detail="No se pudo guardar la configuración")

@app.get("/api/audio/sessions")
async def get_audio_sessions():
    return {
        "master": audio_controller.get_master_volume(),
        "sessions": audio_controller.get_audio_sessions()
    }

@app.get("/api/system/apps")
async def get_system_apps():
    return {
        "apps": system_scanner.get_detected_apps()
    }

@app.post("/api/upload")
async def upload_button_image(file: UploadFile = File(...)):
    try:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"):
            ext = ".png"
        filename = f"btn_{uuid.uuid4().hex[:10]}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"success": True, "url": f"/static/uploads/{filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- GitHub Auto-Update Endpoints ---

@app.get("/api/system/check-update")
async def check_github_update():
    """Checks github repository for new commits/updates."""
    repo_url = "https://api.github.com/repos/Zak208/streamdeck/commits/main"
    try:
        # Get local commit hash
        local_hash = ""
        try:
            res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=BASE_DIR)
            local_hash = res.stdout.strip()
        except Exception:
            pass

        req = urllib.request.Request(repo_url, headers={"User-Agent": "StreamDesk-Updater"})
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                remote_hash = data.get("sha", "")
                commit_msg = data.get("commit", {}).get("message", "")
                has_update = bool(local_hash and remote_hash and local_hash != remote_hash)
                return {
                    "current_version": VERSION,
                    "local_hash": local_hash[:7] if local_hash else "local",
                    "remote_hash": remote_hash[:7] if remote_hash else "latest",
                    "update_available": has_update,
                    "commit_message": commit_msg.split("\n")[0]
                }
    except Exception as e:
        return {
            "current_version": VERSION,
            "update_available": False,
            "status": "up_to_date_or_offline",
            "info": str(e)
        }

@app.post("/api/system/apply-update")
async def apply_github_update():
    """Executes git pull to update to latest commit."""
    try:
        res = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, cwd=BASE_DIR)
        output = res.stdout + res.stderr
        return {"success": res.returncode == 0, "output": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WebSocket Channel ---

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(default=None)):
    client_ip = websocket.client.host if websocket.client else ""
    is_localhost = client_ip in ("127.0.0.1", "::1", "localhost")

    if not is_localhost and not auth_manager.is_token_authorized(token):
        await websocket.close(code=1008, reason="No autorizado. Empareja primero con el PIN.")
        return

    await ws_manager.connect(websocket)

    try:
        init_state = {
            "type": "init_state",
            "config": config_manager.get_config(),
            "master": audio_controller.get_master_volume(),
            "sessions": audio_controller.get_audio_sessions()
        }
        await websocket.send_text(json.dumps(init_state))

        while True:
            raw_data = await websocket.receive_text()
            try:
                data = json.loads(raw_data)
                msg_type = data.get("type")

                if msg_type == "trigger_button":
                    btn_id = data.get("id")
                    config = config_manager.get_config()
                    slots = config.get("slots", [])
                    slot = next((s for s in slots if s.get("id") == btn_id), None)
                    if slot and slot.get("type") == "button":
                        result = execute_action(slot.get("action_type"), slot.get("target"), slot.get("extra"))
                        await websocket.send_text(json.dumps({
                            "type": "action_result",
                            "id": btn_id,
                            "result": result
                        }))

                elif msg_type == "set_master_volume":
                    vol = int(data.get("volume", 0))
                    vol = max(0, min(100, vol))
                    res = audio_controller.set_master_volume(vol)
                    await ws_manager.broadcast({
                        "type": "master_volume_updated",
                        "volume": vol,
                        "muted": res.get("muted", False)
                    }, exclude=websocket)

                elif msg_type == "toggle_master_mute":
                    res = audio_controller.toggle_master_mute()
                    await ws_manager.broadcast({
                        "type": "master_mute_updated",
                        "muted": res.get("muted", False)
                    })

                elif msg_type == "set_app_volume":
                    proc = data.get("process")
                    vol = int(data.get("volume", 0))
                    vol = max(0, min(100, vol))
                    if proc:
                        audio_controller.set_app_volume(proc, vol)
                        await ws_manager.broadcast({
                            "type": "app_volume_updated",
                            "process": proc,
                            "volume": vol
                        }, exclude=websocket)

                elif msg_type == "toggle_app_mute":
                    proc = data.get("process")
                    if proc:
                        res = audio_controller.toggle_app_mute(proc)
                        await ws_manager.broadcast({
                            "type": "app_mute_updated",
                            "process": proc,
                            "muted": res.get("muted", False)
                        })

                elif msg_type == "refresh_sessions":
                    sessions = audio_controller.get_audio_sessions()
                    await websocket.send_text(json.dumps({
                        "type": "sessions_update",
                        "sessions": sessions
                    }))

            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# --- Static Web Pages ---

@app.get("/studio", response_class=HTMLResponse)
async def serve_studio():
    studio_path = os.path.join(STATIC_DIR, "studio.html")
    if os.path.exists(studio_path):
        return FileResponse(studio_path)
    return "<h1>Studio not found</h1>"

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
