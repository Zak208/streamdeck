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

if sys.stderr and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding and sys.stderr.encoding.lower() != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Determine base dir (handles PyInstaller frozen mode)
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    os.chdir(os.path.dirname(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Import server
import uvicorn
from server.main import app, PORT, auth_manager
from server.paths import DATA_DIR, CONFIG_DIR, VERSION
from server.ssl_helper import ensure_ssl_certificates
import webview

def start_server():
    try:
        use_ssl = os.environ.get("STREAMDESK_HTTPS", "").lower() in ("1", "true", "yes")
        ssl_kwargs = {}
        if use_ssl:
            ip = auth_manager.get_local_ip()
            cert_file, key_file = ensure_ssl_certificates(ip)
            if cert_file and key_file and os.path.exists(cert_file) and os.path.exists(key_file):
                ssl_kwargs = {"ssl_certfile": cert_file, "ssl_keyfile": key_file}
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning", **ssl_kwargs)
    except Exception as e:
        print(f"Server error: {e}")

def refresh_icons_once():
    """After an update Windows may keep showing the old icon (it caches them by path): ask Explorer to reload them,
    once per version."""
    try:
        from server.paths import CONFIG_DIR, VERSION
        marker = os.path.join(CONFIG_DIR, f"icons-refreshed-{VERSION}")
        if os.path.exists(marker):
            return
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)  # SHCNE_ASSOCCHANGED
        os.makedirs(CONFIG_DIR, exist_ok=True)
        open(marker, "w").close()
    except Exception:
        pass


def main():
    # 1. Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Give server a brief moment to bind port
    time.sleep(0.6)

    use_ssl = os.environ.get("STREAMDESK_HTTPS", "").lower() in ("1", "true", "yes")
    scheme = "https" if use_ssl else "http"
    studio_url = f"{scheme}://localhost:{PORT}/studio"
    webview.settings["IGNORE_SSL_ERRORS"] = True
    icon_path = os.path.join(BASE_DIR, "static", "icons", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = None

    print(f"[*] StreamDesk Pro Desktop iniciando en {studio_url}")

    refresh_icons_once()

    # Own taskbar identity: without it, running from source groups the window under Python's icon.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Zak208.StreamDesk.Pro")
    except Exception:
        pass

    # 2. Open native Windows desktop window
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

    webview_data_dir = os.path.join(DATA_DIR, "webview_data")
    try:
        os.makedirs(webview_data_dir, exist_ok=True)
    except Exception:
        pass

    webview.start(
        icon=icon_path,
        debug=False,
        private_mode=False,
        storage_path=webview_data_dir,
    )
    sys.exit(0)

if __name__ == "__main__":
    main()

