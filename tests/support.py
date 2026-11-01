"""Shared test setup. Import it before any `server` module.

It points StreamDesk at a throwaway data directory, so tests never read or
change the real deck profile or the paired-device tokens, and it provides a
live server on a free port for the HTTP/WebSocket tests.
"""

import os
import socket
import sys
import tempfile
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if "STREAMDESK_DATA_DIR" not in os.environ:
    os.environ["STREAMDESK_DATA_DIR"] = tempfile.mkdtemp(prefix="streamdesk-test-")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiveServer:
    """Runs the FastAPI app in a background thread, bound to loopback."""

    def __init__(self):
        import uvicorn
        from server.main import app

        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="error"))
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self):
        self._thread.start()
        deadline = time.time() + 10
        while not self._server.started and time.time() < deadline:
            time.sleep(0.05)
        if not self._server.started:
            raise RuntimeError("test server did not start")
        return self

    def __exit__(self, *exc):
        self._server.should_exit = True
        self._thread.join(timeout=5)
