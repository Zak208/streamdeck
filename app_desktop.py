import os
import sys
import time
import threading

def open_log():
    """PyInstaller --windowed mode has no stdout/stderr. Send them to a log file next to the profile (kept to
    about 1 MB plus one older copy), so a failure leaves something to read, and fall back to nothing."""
    try:
        from server.paths import CONFIG_DIR
        os.makedirs(CONFIG_DIR, exist_ok=True)
        path = os.path.join(CONFIG_DIR, "streamdesk.log")
        if os.path.exists(path) and os.path.getsize(path) > 1024 * 1024:
            os.replace(path, path + ".bak")
        return open(path, "a", encoding="utf-8", buffering=1)
    except Exception:
        return open(os.devnull, "w", encoding="utf-8")


if sys.stdout is None or sys.stderr is None:
    _log = open_log()
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log

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

# One copy only: a second launch (a shortcut, Windows start-up) just brings the running window forward.
from server import desktop
if __name__ == "__main__" and not desktop.acquire_single_instance():
    desktop.ask_running_instance_to_show()
    sys.exit(0)

# Import server
import uvicorn
from server.main import app, PORT, auth_manager
from server.paths import DATA_DIR, CONFIG_DIR, FROZEN, VERSION
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

def port_owner(port):
    """Name of the program that is listening on the port, or "otro programa"."""
    try:
        import psutil
        for conn in psutil.net_connections("tcp"):
            if conn.laddr and conn.laddr.port == port and conn.status == "LISTEN" and conn.pid:
                return psutil.Process(conn.pid).name()
    except Exception:
        pass
    return "otro programa"


def explain_busy_port():
    """The port is taken, so the phone could never reach us: say so and why, instead of a blank window."""
    import socket
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", PORT)) != 0:
            return False
    owner = port_owner(PORT)
    if owner.lower().startswith("streamdesk"):
        text = ("Ya hay otro StreamDesk abierto (puede ser una versión anterior que no se cierra desde la bandeja).\n\n"
                "Ciérralo desde el Administrador de tareas y vuelve a abrir StreamDesk.")
    else:
        text = (f"El puerto {PORT} lo está usando {owner}, y el móvil necesita ese puerto para conectarse.\n\n"
                "Cierra ese programa y vuelve a abrir StreamDesk.")
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "StreamDesk Pro no puede arrancar", 0x30)  # MB_ICONWARNING
    except Exception:
        print(text)
    return True


def wait_for_server(port, seconds=20.0):
    import socket
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.15)
    return False


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


class DesktopShell:
    """The window plus the tray icon. Closing the window hides it (the server, and so the phone, keeps working);
    "Salir" in the tray is what really ends the app."""

    def __init__(self, icon_path):
        self.icon_path = icon_path
        self.window = None
        self.icon = None
        self.tray_ok = False
        self.quitting = False

    # -- tray --

    def start_tray(self):
        try:
            import pystray
            from PIL import Image
            image = Image.open(self.icon_path) if self.icon_path else Image.new("RGBA", (64, 64), "#F8C700")
            menu = pystray.Menu(
                pystray.MenuItem(lambda item: f"Móviles conectados: {desktop.controller.phones()}", None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Abrir StreamDesk", lambda icon, item: self.show(), default=True),
                pystray.MenuItem("Mostrar el QR para emparejar un móvil", lambda icon, item: self.show_pairing()),
                pystray.MenuItem("Copiar la dirección del móvil", lambda icon, item: self.copy_address()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Iniciar con Windows", lambda icon, item: self.toggle_autostart(),
                                 checked=lambda item: desktop.autostart_enabled(),
                                 visible=desktop.autostart_supported()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Salir (el móvil dejará de funcionar)", lambda icon, item: self.quit()),
            )
            self.icon = pystray.Icon("StreamDesk", image, "StreamDesk Pro: activo, el móvil puede conectarse", menu)
            self.icon.run_detached()
            self.tray_ok = True
        except Exception as exc:  # no tray: closing the window then ends the app, as it always did
            print(f"[!] Sin icono de bandeja: {exc}")

    def show_pairing(self):
        self.show()
        try:  # the pairing panel may have been folded away
            self.window.evaluate_js("var p = document.getElementById('pairing-panel'); if (p) p.open = true;")
        except Exception:
            pass

    def copy_address(self):
        ip = auth_manager.get_local_ip()
        if desktop.copy_to_clipboard(f"http://{ip}:{PORT}"):
            self.notify("Dirección copiada", f"http://{ip}:{PORT}  (escríbela en el navegador del móvil)")

    def notify(self, title, text):
        if self.icon and self.tray_ok:
            self.icon.notify(text, title)

    def pick_folder(self):
        """Windows' folder chooser, on top of the Studio window."""
        self.show()
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        chosen = self.window.create_file_dialog(kind)
        return chosen[0] if chosen else ""

    def toggle_autostart(self):
        try:
            desktop.set_autostart(not desktop.autostart_enabled())
        except OSError:
            pass

    # -- window --

    def show(self):
        if self.window is None:
            return
        try:
            self.window.restore()
            self.window.show()
        except Exception:
            pass

    def on_closing(self):
        """Return False to cancel the close. The hide runs in its own thread: this handler is on the window's thread."""
        if self.quitting or not self.tray_ok or not desktop.keep_running():
            return True
        threading.Thread(target=self.window.hide, daemon=True).start()
        self.tell_once()
        return False

    def tell_once(self):
        """The first time the window is hidden, say where it went (otherwise it looks like the app crashed)."""
        try:
            from server.settings_store import settings
            if settings.get("app").get("background_hint_shown"):
                return
            settings.update("app", {"background_hint_shown": True})
            self.notify("StreamDesk Pro", "StreamDesk sigue activo en segundo plano: tu móvil puede seguir usándolo. "
                        "Para abrirlo, pulsa su icono aquí. Para cerrarlo del todo, elige Salir.")
        except Exception:
            pass

    def quit(self):
        self.quitting = True
        threading.Timer(5.0, os._exit, [0]).start()  # if the window does not close in time, do not stay as a ghost
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
        try:
            self.window.destroy()
        except Exception:
            os._exit(0)


def watch_for_updates(shell):
    """Tell the user once per version that a new one is out. With the window hidden nobody would see the banner
    inside it. It only announces: installing is still the user's button (the installer is not code-signed)."""
    from server.settings_store import settings
    from server import updater as updater_module
    time.sleep(90)  # not while Windows is still starting everything else
    while True:
        try:
            info = updater_module.updater.release_info(VERSION)
            latest = info.get("latest_version", "")
            if info.get("update_available") and latest and settings.get("app").get("update_announced") != latest:
                settings.update("app", {"update_announced": latest})
                shell.notify("Hay una versión nueva de StreamDesk", f"La versión {latest} está lista. Abre StreamDesk y pulsa Actualizar.")
        except Exception:
            pass  # offline: try again later
        time.sleep(6 * 3600)


def main():
    background = desktop.BACKGROUND_FLAG in sys.argv[1:]

    if explain_busy_port():
        sys.exit(1)

    if background:
        os.environ.setdefault("STREAMDESK_SCAN_DELAY", "45")  # started by Windows at sign-in: the PC is busy

    # 1. Start FastAPI server in background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait until the server answers (at Windows start-up the PC is busy and it can take a few seconds)
    wait_for_server(PORT)

    use_ssl = os.environ.get("STREAMDESK_HTTPS", "").lower() in ("1", "true", "yes")
    scheme = "https" if use_ssl else "http"
    studio_url = f"{scheme}://localhost:{PORT}/studio"
    webview.settings["IGNORE_SSL_ERRORS"] = True
    icon_path = os.path.join(BASE_DIR, "static", "icons", "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = None

    print(f"[*] StreamDesk Pro Desktop iniciando en {studio_url}")

    refresh_icons_once()
    try:
        desktop.prepare_autostart()
    except Exception as exc:
        print(f"[!] Inicio con Windows: {exc}")

    # Own taskbar identity: without it, running from source groups the window under Python's icon.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Zak208.StreamDesk.Pro")
    except Exception:
        pass

    shell = DesktopShell(icon_path)
    shell.start_tray()

    # 2. Open native Windows desktop window (hidden in the tray when Windows started it at sign-in)
    window = webview.create_window(
        title="StreamDesk Pro",
        url=studio_url,
        width=1280,
        height=780,
        min_size=(960, 620),
        resizable=True,
        confirm_close=False,
        background_color="#070a10",
        hidden=background and shell.tray_ok,
    )
    shell.window = window
    window.events.closing += shell.on_closing
    desktop.controller.show = shell.show
    desktop.controller.quit = shell.quit
    desktop.controller.notify = shell.notify
    desktop.controller.pick_folder = shell.pick_folder
    if FROZEN:
        threading.Thread(target=watch_for_updates, args=(shell,), daemon=True).start()

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
    if shell.icon:
        try:
            shell.icon.stop()
        except Exception:
            pass
    sys.exit(0)

if __name__ == "__main__":
    main()
