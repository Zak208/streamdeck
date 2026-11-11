"""Checks the real desktop app end to end: hidden start, the X button, the tray behaviour and a second launch.

Starts StreamDesk with a throwaway profile (it never touches yours), looks at its real window with the Windows API,
and ends it. Needs a Windows desktop session and the WebView2 runtime.

    python scripts/check_desktop.py                      # runs app_desktop.py from this checkout
    python scripts/check_desktop.py path\\to\\StreamDesk.exe # runs a compiled build

Exit code 0 if every step passed.
"""

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from ctypes import wintypes

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = 48291
URL = f"http://127.0.0.1:{PORT}"
WM_CLOSE = 0x0010
user32 = ctypes.windll.user32


def command(*flags):
    if len(sys.argv) > 1:
        return [sys.argv[1], *flags]
    return [sys.executable, os.path.join(ROOT, "app_desktop.py"), *flags]


def call(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data=data, headers={"Content-Type": "application/json"},
                                 method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode())


def studio_windows(pid):
    """(handle, visible) of the app's window."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if title.value == "StreamDesk Pro":
                found.append((hwnd, bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumWindows(visit, 0)
    return found


def wait_for(condition, seconds=40):
    end = time.time() + seconds
    while time.time() < end:
        try:
            value = condition()
            if value:
                return value
        except Exception:
            pass
        time.sleep(0.3)
    return None


def listening_pid():
    return next(c.pid for c in psutil.net_connections("tcp") if c.laddr.port == PORT and c.status == "LISTEN")


def step(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name, flush=True)
    if not ok:
        raise SystemExit(1)


def main():
    data_dir = tempfile.mkdtemp(prefix="streamdesk-check-")
    # A compiled build treats an empty profile as a fresh install and registers "start with Windows" for itself. This
    # profile says that was already decided, so the check never touches the real Windows start-up list.
    os.makedirs(os.path.join(data_dir, "config"))
    with open(os.path.join(data_dir, "config", "settings.json"), "w", encoding="utf-8") as handle:
        json.dump({"app": {"first_run_completed": True, "autostart_decided": True}}, handle)
    env = dict(os.environ, STREAMDESK_DATA_DIR=data_dir)
    launcher = subprocess.Popen(command("--background"), env=env, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        state = wait_for(lambda: (lambda s: s if s["window"] else None)(call("/api/settings/desktop")))
        step("the server is up and the window is attached", bool(state))
        pid = listening_pid()  # a venv python.exe starts the real process as a child, so the launcher's pid is not the app's
        windows = wait_for(lambda: studio_windows(pid))
        step("started with --background: the window exists and is hidden", bool(windows) and not windows[0][1])

        call("/api/desktop/show", {})
        time.sleep(1)
        windows = studio_windows(pid)
        step("asking it to show makes the window visible", bool(windows) and windows[0][1])

        user32.PostMessageW(windows[0][0], WM_CLOSE, 0, 0)  # the X button
        time.sleep(2)
        windows = studio_windows(pid)
        step("the X hides the window and does not close it", bool(windows) and not windows[0][1] and psutil.pid_exists(pid))
        step("the server still answers (the phone keeps working)", bool(call("/api/identity")))

        second = subprocess.run(command(), env=env, cwd=ROOT, timeout=60, capture_output=True)
        time.sleep(1)
        windows = studio_windows(pid)
        step("a second launch ends and brings the first window forward", second.returncode == 0 and bool(windows) and windows[0][1])

        call("/api/settings/desktop", {"keep_running": False})
        user32.PostMessageW(windows[0][0], WM_CLOSE, 0, 0)
        step("with keep running off, the X ends the app", bool(wait_for(lambda: not psutil.pid_exists(pid), 15)))
        print("ALL OK")
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(launcher.pid)], capture_output=True)


if __name__ == "__main__":
    main()
