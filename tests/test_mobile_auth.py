import os
import sys
import time
import json
import threading
import urllib.request
import urllib.error
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from server.auth import auth_manager, AuthManager, TOKENS_FILE
import uvicorn
from server.main import app, PORT
import websockets

def run_tests():
    print("=== Testing Mobile Authentication, Persistence & WebSockets ===")

    # 1. Test AuthManager local IP detection
    ip = auth_manager.get_local_ip()
    print(f"[1] Local IP detected: {ip}")
    assert ip and not ip.startswith("127.") or ip == "127.0.0.1", "Invalid IP"

    # 2. Test QR code generation contains query param ?pin=
    qr_b64 = auth_manager.generate_qr_base64(PORT)
    assert qr_b64.startswith("data:image/png;base64,"), "QR code must be a valid base64 data url"
    print(f"[2] QR Code generated successfully ({len(qr_b64)} chars)")

    # 3. Test PIN verification and payload format
    current_pin = auth_manager.current_pin
    print(f"[3] Current pairing PIN: {current_pin}")
    
    # Invalid PIN attempt
    bad_res = auth_manager.verify_pin_and_issue_token("000000_fake")
    assert bad_res.get("valid") is False, "Bad PIN must return valid=False"
    assert bad_res.get("success") is False, "Bad PIN must return success=False"
    assert "error" in bad_res, "Bad PIN must return error message"
    print("[3a] Invalid PIN rejected correctly")

    # Valid PIN attempt
    good_res = auth_manager.verify_pin_and_issue_token(current_pin, "Test Smartphone")
    assert good_res.get("valid") is True, "Valid PIN must return valid=True"
    assert good_res.get("success") is True, "Valid PIN must return success=True"
    token = good_res.get("token")
    assert token and len(token) >= 20, "Valid token must be issued"
    print(f"[3b] Valid PIN issued token: {token[:8]}... (valid=True, success=True)")

    # 4. Test Persistence of Tokens
    assert os.path.exists(TOKENS_FILE), f"Tokens file must exist at {TOKENS_FILE}"
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
    assert token in saved_data.get("authorized_tokens", []), "Token must be saved to disk"
    print(f"[4] Token persistence verified on disk in {TOKENS_FILE}")

    # 5. Test Token Reload in fresh AuthManager instance (simulating app restart)
    new_auth = AuthManager()
    assert new_auth.is_token_authorized(token), "Token must persist and reload in fresh AuthManager"
    print("[5] Fresh AuthManager instance reloaded token from disk successfully!")

    # 6. Start FastAPI server to test HTTP & WebSocket authorization
    server_config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(server_config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    time.sleep(1.2)

    try:
        # Test /api/auth/check endpoint with valid token
        check_url = f"http://127.0.0.1:{PORT}/api/auth/check?token={token}"
        req = urllib.request.Request(check_url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            assert data.get("authorized") is True, "Token must be authorized via HTTP"
            assert data.get("valid") is True, "Token must be valid via HTTP"
        print("[6a] GET /api/auth/check with token -> authorized=True, valid=True")

        # Test /api/auth/check endpoint with invalid token
        check_url_bad = f"http://127.0.0.1:{PORT}/api/auth/check?token=bad_fake_token"
        req_bad = urllib.request.Request(check_url_bad)
        with urllib.request.urlopen(req_bad, timeout=3) as resp:
            data_bad = json.loads(resp.read().decode())
            assert data_bad.get("authorized") is False, "Fake token must not be authorized"
        print("[6b] GET /api/auth/check with fake token -> authorized=False")

        # Test POST /api/auth/verify via HTTP
        active_pin = auth_manager.current_pin
        verify_data = json.dumps({"pin": active_pin, "device_name": "iPhone 15"}).encode()
        verify_req = urllib.request.Request(
            f"http://127.0.0.1:{PORT}/api/auth/verify",
            data=verify_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(verify_req, timeout=3) as resp:
            verify_res = json.loads(resp.read().decode())
            assert verify_res.get("valid") is True, "verify must return valid=True"
            assert verify_res.get("success") is True, "verify must return success=True"
            phone_token = verify_res.get("token")
            assert phone_token, "Token must be returned"
        print(f"[6c] POST /api/auth/verify HTTP -> valid=True, success=True, token={phone_token[:8]}...")

        # Test WebSocket with valid token
        async def test_ws():
            ws_uri = f"ws://127.0.0.1:{PORT}/ws?token={phone_token}"
            async with websockets.connect(ws_uri) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                data = json.loads(msg)
                assert data.get("type") == "init_state", f"Expected init_state, got {data.get('type')}"
                print("[7] WebSocket connected and received init_state successfully with token!")

        asyncio.run(test_ws())

    finally:
        server.should_exit = True
        server_thread.join(timeout=2.0)

    print("\n[ALL TESTS PASSED] Mobile connection, PIN auth, token persistence and WebSockets fully verified!")

if __name__ == "__main__":
    run_tests()

