import os
import sys
import time
import threading
import json
import urllib.request
import urllib.error

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.chdir(PROJECT_ROOT)

# 1. Test None sys.stdout / sys.stderr safe handling
print("=== 1. Testing safe stdout/stderr handling ===")
saved_stdout = sys.stdout
saved_stderr = sys.stderr
sys.stdout = None
sys.stderr = None

try:
    import app_desktop
    import server.main
    assert sys.stdout is not None, "sys.stdout should be initialized when None"
    assert sys.stderr is not None, "sys.stderr should be initialized when None"
    assert hasattr(sys.stdout, 'encoding'), "sys.stdout should have encoding attribute"
except Exception as e:
    sys.stdout = saved_stdout
    sys.stderr = saved_stderr
    print(f"[FAIL] Error during safe stdout test: {e}")
    raise
finally:
    sys.stdout = saved_stdout
    sys.stderr = saved_stderr

print("[PASS] Safe stdout/stderr handling verified for windowed mode.")

# 2. Test deck_config.json 6x2 grid (12 slots)
print("\n=== 2. Testing config/deck_config.json 6x2 grid (12 slots) ===")
config_path = os.path.join(PROJECT_ROOT, "config", "deck_config.json")
with open(config_path, "r", encoding="utf-8") as f:
    deck_cfg = json.load(f)

layout = deck_cfg.get("layout", {})
slots = deck_cfg.get("slots", [])
assert layout.get("rows") == 2, f"Expected 2 rows, got {layout.get('rows')}"
assert layout.get("columns") == 6, f"Expected 6 columns, got {layout.get('columns')}"
assert layout.get("total_slots") == 12, f"Expected 12 total slots, got {layout.get('total_slots')}"
assert len(slots) == 12, f"Expected exactly 12 slots, got {len(slots)}"
for i, s in enumerate(slots):
    assert s.get("index") == i, f"Slot {i} index mismatch"
    assert "type" in s, f"Slot {i} missing type"
    assert "id" in s, f"Slot {i} missing id"
print(f"[PASS] deck_config.json verified: 2 rows x 6 columns = {len(slots)} valid slots.")

# 3. Test binary and installer existence and size
print("\n=== 3. Testing dist/StreamDesk/StreamDesk.exe and instalador_streamdeck.exe ===")
exe_path = os.path.join(PROJECT_ROOT, "dist", "StreamDesk", "StreamDesk.exe")
assert os.path.exists(exe_path), f"Binary not found: {exe_path}"
exe_size = os.path.getsize(exe_path)
assert exe_size > 1_000_000, f"Binary size suspicious: {exe_size} bytes"
print(f"[PASS] Desktop Binary verified: {exe_path} ({exe_size:,} bytes)")

installer_path = os.path.join(PROJECT_ROOT, "instalador_streamdeck.exe")
assert os.path.exists(installer_path), f"Installer not found: {installer_path}"
installer_size = os.path.getsize(installer_path)
assert installer_size > 10_000_000, f"Installer size suspicious: {installer_size} bytes"
print(f"[PASS] Installer verified: {installer_path} ({installer_size:,} bytes)")

# 4. Test manifest.json and service-worker.js
print("\n=== 4. Testing manifest.json and service-worker.js files ===")
manifest_path = os.path.join(PROJECT_ROOT, "static", "manifest.json")
with open(manifest_path, "r", encoding="utf-8") as f:
    manifest_data = json.load(f)

icons = manifest_data.get("icons", [])
icon_sizes = {icon.get("sizes"): icon.get("src") for icon in icons}
assert "192x192" in icon_sizes, "Manifest missing 192x192 icon"
assert "512x512" in icon_sizes, "Manifest missing 512x512 icon"
print(f"[PASS] manifest.json contains 192x192 ({icon_sizes['192x192']}) and 512x512 ({icon_sizes['512x512']}).")

sw_path = os.path.join(PROJECT_ROOT, "static", "service-worker.js")
with open(sw_path, "r", encoding="utf-8") as f:
    sw_content = f.read()
assert "icon-192.png" in sw_content, "Service Worker missing icon-192.png caching"
assert "icon-512.png" in sw_content, "Service Worker missing icon-512.png caching"
print("[PASS] service-worker.js contains both PNG icon references in cache assets.")

# 5. Start Server on port 48291 and test API endpoints
print("\n=== 5. Testing FastAPI Server and Endpoints on port 48291 ===")
import uvicorn
from server.main import app, PORT

server_config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
server = uvicorn.Server(server_config)

server_thread = threading.Thread(target=server.run, daemon=True)
server_thread.start()

# Wait for server to bind
time.sleep(1.5)

base_url = f"http://127.0.0.1:{PORT}"
endpoints = [
    ("/api/info", "GET", 200, ["version", "server_ip", "port", "direct_url", "studio_url"]),
    ("/api/auth/pin", "GET", 200, ["pin", "qr_code", "ip", "port"]),
    ("/api/config", "GET", 200, ["deck_name", "layout", "slots"]),
    ("/api/deck/config", "GET", 200, ["deck_name", "layout", "slots"]),
    ("/api/audio/sessions", "GET", 200, ["master", "sessions"]),
    ("/api/system/apps", "GET", 200, ["apps"]),
    ("/manifest.json", "GET", 200, ["icons", "start_url", "display"]),
    ("/service-worker.js", "GET", 200, None),
    ("/studio", "GET", 200, None),
    ("/", "GET", 200, None),
    ("/static/icons/icon-192.png", "GET", 200, None),
    ("/static/icons/icon-512.png", "GET", 200, None),
]

passed_endpoints = 0
for path, method, expected_code, expected_keys in endpoints:
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            code = resp.status
            body = resp.read()
            assert code == expected_code, f"Expected {expected_code}, got {code} for {path}"
            if expected_keys:
                data = json.loads(body.decode("utf-8"))
                for k in expected_keys:
                    assert k in data, f"Key '{k}' not found in response from {path}"
                if path in ("/api/config", "/api/deck/config"):
                    layout_resp = data.get("layout", {})
                    slots_resp = data.get("slots", [])
                    assert layout_resp.get("rows") == 2, f"Expected rows 2, got {layout_resp.get('rows')}"
                    assert layout_resp.get("columns") == 6, f"Expected columns 6, got {layout_resp.get('columns')}"
                    assert layout_resp.get("total_slots") == 12, f"Expected 12 slots, got {layout_resp.get('total_slots')}"
                    assert len(slots_resp) == 12, f"Expected 12 slots list, got {len(slots_resp)}"
                    print(f"       -> Confirmed {path} returns 6x2 grid ({len(slots_resp)} slots)")
            content_type = resp.headers.get("Content-Type", "")
            print(f"[PASS] {method} {path} -> HTTP {code} ({content_type[:30]})")
            passed_endpoints += 1
    except Exception as e:
        print(f"[FAIL] {method} {path} -> {e}")
        raise

print(f"\nAll {passed_endpoints}/{len(endpoints)} endpoints responded with HTTP 200 OK.")

# Stop server cleanly
server.should_exit = True
server_thread.join(timeout=2.0)
print("\n[SUCCESS] All verification tests passed successfully!")
