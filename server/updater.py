"""Updates of the installed app from the GitHub Releases of the project.

The release carries the installer (`instalador_streamdeck.exe`). The app asks GitHub for the latest release,
and when its version is newer the user can press "Actualizar" in Studio: the installer is downloaded from the
project's own release address only, checked against the SHA-256 that GitHub publishes for that file, and run
silently over the current installation (same AppId, so the user's profile and settings, which live in
%APPDATA%\\StreamDesk, are untouched). The app closes and the installer starts the new version.

What this does not protect against: a release published from a compromised GitHub account. The installer is not
code-signed, so Windows SmartScreen may also warn the first time.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple

REPO = "Zak208/streamdeck"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALLER_NAME = "instalador_streamdeck.exe"
HASH_ASSET = INSTALLER_NAME + ".sha256"
DOWNLOAD_URL = re.compile(r"https://github\.com/" + re.escape(REPO) + r"/releases/download/[A-Za-z0-9._-]{1,40}/" + re.escape(INSTALLER_NAME))
HASH_URL = re.compile(r"https://github\.com/" + re.escape(REPO) + r"/releases/download/[A-Za-z0-9._-]{1,40}/" + re.escape(HASH_ASSET))
VERSION_TAG = re.compile(r"v?([0-9]{1,4})\.([0-9]{1,4})\.([0-9]{1,4})")
MAX_INSTALLER_BYTES = 400 * 1024 * 1024
CACHE_SECONDS = 600
USER_AGENT = "StreamDesk-Updater"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class UpdateError(Exception):
    """A reason the user can read."""


def parse_version(text: Any) -> Optional[Tuple[int, int, int]]:
    match = VERSION_TAG.fullmatch(str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def _fetch_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.loads(response.read(2_000_000).decode("utf-8"))


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read(10_000).decode("utf-8", errors="replace")


def _download(url: str, destination: str, progress: Callable[[float], None]) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response, open(destination, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        if total > MAX_INSTALLER_BYTES:
            raise UpdateError("El instalador es más grande de lo esperado y no se descargó")
        done = 0
        while True:
            chunk = response.read(256 * 1024)
            if not chunk:
                break
            done += len(chunk)
            if done > MAX_INSTALLER_BYTES:
                raise UpdateError("El instalador es más grande de lo esperado y se detuvo la descarga")
            out.write(chunk)
            if total:
                progress(min(done / total, 1.0))


def _launch(path: str) -> None:
    """Start the installer detached from this process: it replaces the files this process is using."""
    subprocess.Popen(
        [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
        creationflags=DETACHED | NO_WINDOW, close_fds=True,
    )


def _exit_soon() -> None:
    threading.Timer(1.5, os._exit, [0]).start()


class Updater:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache: Optional[Tuple[float, Dict[str, Any]]] = None
        self.state: Dict[str, Any] = {"state": "idle", "progress": 0.0, "message": ""}

    # --- checking ---

    def release_info(self, current_version: str, *, force: bool = False) -> Dict[str, Any]:
        """The latest published release and whether it is newer than this app. Cached for ten minutes."""
        now = time.monotonic()
        if not force and self._cache and now - self._cache[0] < CACHE_SECONDS:
            data = self._cache[1]
        else:
            data = _fetch_json(LATEST_URL)
            self._cache = (now, data)
        latest = parse_version(data.get("tag_name"))
        current = parse_version(current_version)
        assets = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
        installer = assets.get(INSTALLER_NAME)
        info: Dict[str, Any] = {
            "current_version": current_version,
            "latest_version": ".".join(map(str, latest)) if latest else "",
            "update_available": bool(latest and current and latest > current and installer),
            "notes": str(data.get("body") or "")[:600],
            "release_url": str(data.get("html_url") or ""),
            "size": int(installer.get("size") or 0) if installer else 0,
        }
        if latest and current and latest > current and not installer:
            info["status"] = "release_without_installer"
        return info

    def _release_files(self) -> Tuple[str, str, str]:
        """(download url, expected sha256, version) for the latest release, or raises UpdateError."""
        data = self._cache[1] if self._cache else _fetch_json(LATEST_URL)
        assets = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
        installer = assets.get(INSTALLER_NAME)
        if not installer:
            raise UpdateError("La versión publicada no incluye el instalador")
        url = str(installer.get("browser_download_url") or "")
        if not DOWNLOAD_URL.fullmatch(url):
            raise UpdateError("La dirección de descarga no es la del proyecto en GitHub, así que no se usa")
        digest = str(installer.get("digest") or "")
        expected = digest.split(":", 1)[1].lower() if digest.lower().startswith("sha256:") else ""
        if not expected and HASH_ASSET in assets:
            hash_url = str(assets[HASH_ASSET].get("browser_download_url") or "")
            if HASH_URL.fullmatch(hash_url):
                expected = _fetch_text(hash_url).strip().split()[0].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise UpdateError("La versión publicada no trae la huella SHA-256 para comprobar el instalador")
        return url, expected, str(data.get("tag_name") or "")

    # --- installing ---

    def _set(self, **values: Any) -> None:
        with self._lock:
            self.state.update(values)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.state)

    def start(self, current_version: str) -> bool:
        """Download, check and run the installer in the background. False if one is already running."""
        with self._lock:
            if self.state["state"] in ("downloading", "verifying", "installing"):
                return False
            self.state = {"state": "downloading", "progress": 0.0, "message": "Descargando la nueva versión"}
        threading.Thread(target=self._run, args=(current_version,), daemon=True).start()
        return True

    def _run(self, current_version: str) -> None:
        folder = None
        try:
            info = self.release_info(current_version, force=True)
            if not info["update_available"]:
                raise UpdateError("Ya tienes la última versión")
            url, expected, _tag = self._release_files()
            folder = tempfile.mkdtemp(prefix="streamdesk-update-")
            path = os.path.join(folder, INSTALLER_NAME)
            _download(url, path, lambda fraction: self._set(progress=round(fraction, 3)))
            self._set(state="verifying", message="Comprobando la descarga")
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise UpdateError("La descarga no coincide con la huella SHA-256 publicada y se descartó")
            self._set(state="installing", progress=1.0, message="Instalando: StreamDesk se cerrará y se abrirá de nuevo")
            _launch(path)
            _exit_soon()
        except UpdateError as exc:
            self._set(state="error", message=str(exc))
        except Exception as exc:  # no network, GitHub down, disk full...
            self._set(state="error", message=f"No se pudo actualizar: {exc}")


updater = Updater()
