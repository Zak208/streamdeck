import os
import sys
import time
import threading

# Crucial fix for PyInstaller --windowed mode where sys.stdout and sys.stderr are None
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

# Determine base dir (handles PyInstaller frozen mode)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    os.chdir(os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Import server
from server.main import app, PORT, auth_manager
import webview

def start_server():
    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
    except Exception as e:
        print(f"Server error: {e}")

def main():
    # 1. Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Give server a brief moment to bind port
    time.sleep(0.6)

    studio_url = f"http://localhost:{PORT}/studio"
    icon_path = os.path.join(BASE_DIR, "static", "icons", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = None

    print(f"[*] StreamDesk Pro Desktop iniciando en {studio_url}")

    # 2. Open native Windows desktop window (like Spotify)
    window = webview.create_window(
        title="StreamDesk Pro",
        url=studio_url,
        width=1280,
        height=780,
        min_size=(960, 620),
        resizable=True,
        confirm_close=False,
        background_color="#070a10"
    )

    webview.start(icon=icon_path, debug=False)
    sys.exit(0)

if __name__ == "__main__":
    main()

