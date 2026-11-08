"""Spotify: play a chosen playlist, album, artist or track from a button.

Two levels, so the button always does something useful:
  1. Not connected: opens the item in the Spotify app (no account needed).
  2. Connected (Authorization Code + PKCE, no client secret): starts playback
     through the Web API. Spotify only allows that for Premium accounts.

The user creates their own Spotify developer app and pastes its Client ID once.
"""

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional

from server import spotify_ui
from server.action_catalog import normalize_spotify_uri
from server.paths import PORT
from server.settings_store import settings

INFO = {
    "id": "spotify",
    "name": "Spotify",
    "icon": "/static/icons/spotify.svg",
    "color": "#1db954",
    "description": "Reproduce una playlist, álbum o canción al pulsar un botón.",
}

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
SCOPES = "user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative user-library-read user-library-modify"
# Spotify requires the literal loopback address, not "localhost".
REDIRECT_URI = f"http://127.0.0.1:{PORT}/api/connectors/spotify/callback"
CLIENT_ID_LENGTH = 32
PENDING_TTL_SECONDS = 600
DEVICE_WAIT_SECONDS = 8

_pending: Dict[str, Dict[str, Any]] = {}  # state -> {verifier, expires}
_token_lock = threading.Lock()


class SpotifyError(Exception):
    def __init__(self, message: str, status: int = 0, reason: str = ""):
        super().__init__(message)
        self.status = status
        self.reason = reason


# --- Settings ---

def configure(values: Dict[str, Any]) -> Dict[str, Any]:
    client_id = (values.get("client_id") or "").strip().lower()
    if len(client_id) != CLIENT_ID_LENGTH or any(c not in "0123456789abcdef" for c in client_id):
        raise ValueError("El Client ID de Spotify tiene 32 caracteres (letras a-f y números)")
    previous = settings.get("spotify").get("client_id")
    # A different app means the old tokens do not belong to it.
    removed = () if previous == client_id else ("access_token", "refresh_token", "expires_at")
    settings.update("spotify", {"client_id": client_id}, remove=removed)
    return public_settings()


def public_settings() -> Dict[str, Any]:
    visible = settings.public("spotify")
    visible.pop("expires_at", None)
    visible["redirect_uri"] = REDIRECT_URI
    visible["connected"] = bool(visible.get("refresh_token_set"))
    return visible


def disconnect() -> Dict[str, Any]:
    settings.update("spotify", {}, remove=("access_token", "refresh_token", "expires_at"))
    return public_settings()


# --- OAuth (PKCE) ---

def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def begin_login() -> Dict[str, Any]:
    client_id = settings.get("spotify").get("client_id")
    if not client_id:
        raise ValueError("Primero guarda el Client ID de Spotify")
    now = time.time()
    for key in [k for k, v in _pending.items() if v["expires"] < now]:
        _pending.pop(key, None)
    verifier = secrets.token_urlsafe(64)
    state = secrets.token_urlsafe(24)
    _pending[state] = {"verifier": verifier, "expires": now + PENDING_TTL_SECONDS}
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": REDIRECT_URI,
        "scope": SCOPES, "state": state, "code_challenge_method": "S256", "code_challenge": _challenge(verifier),
    })
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return {"url": url}


def finish_login(code: str, state: str) -> None:
    pending = _pending.pop(state or "", None)
    if not pending or pending["expires"] < time.time():
        raise SpotifyError("La sesión de conexión caducó. Vuelve a pulsar Conectar.")
    client_id = settings.get("spotify").get("client_id")
    _store_tokens(_token_request({
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
        "client_id": client_id, "code_verifier": pending["verifier"],
    }))


def _token_request(form: Dict[str, str]) -> Dict[str, Any]:
    request = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(form).encode(), method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise SpotifyError("Spotify rechazó la conexión. Revisa el Client ID y la Redirect URI.", exc.code) from exc
    except OSError as exc:
        raise SpotifyError("No se pudo contactar con Spotify") from exc


def _store_tokens(tokens: Dict[str, Any]) -> None:
    values = {"access_token": tokens["access_token"], "expires_at": time.time() + int(tokens.get("expires_in", 3600))}
    if tokens.get("refresh_token"):
        values["refresh_token"] = tokens["refresh_token"]
    settings.update("spotify", values)


def _access_token() -> str:
    with _token_lock:
        saved = settings.get("spotify")
        if not saved.get("refresh_token"):
            raise SpotifyError("Spotify no está conectado", reason="NOT_CONNECTED")
        if saved.get("access_token") and saved.get("expires_at", 0) - 60 > time.time():
            return saved["access_token"]
        _store_tokens(_token_request({
            "grant_type": "refresh_token", "refresh_token": saved["refresh_token"], "client_id": saved["client_id"],
        }))
        return settings.get("spotify")["access_token"]


# --- Web API ---

def _api(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        API_URL + path, data=data, method=method,
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read()
            return json.loads(raw.decode()) if raw else None
    except urllib.error.HTTPError as exc:
        reason = ""
        try:
            reason = json.loads(exc.read().decode()).get("error", {}).get("reason", "")
        except Exception:
            pass
        raise SpotifyError(f"Spotify respondió {exc.code}", exc.code, reason) from exc
    except OSError as exc:
        raise SpotifyError("No se pudo contactar con Spotify") from exc


def _play_body(uri: str) -> Dict[str, Any]:
    kind = uri.split(":")[1]
    return {"uris": [uri]} if kind == "track" else {"context_uri": uri}


def _wait_for_device() -> Optional[str]:
    deadline = time.time() + DEVICE_WAIT_SECONDS
    while time.time() < deadline:
        devices = (_api("GET", "/me/player/devices") or {}).get("devices", [])
        computers = [d for d in devices if d.get("type") == "Computer"] or devices
        if computers:
            return computers[0]["id"]
        time.sleep(1)
    return None


def _open_in_app(uri: str) -> None:
    os.startfile(uri)


def _play_in_app(uri: str, note: str = "") -> Dict[str, Any]:
    """No Web API playback (no account connected, or not Premium): press play in the Spotify desktop window."""
    try:
        spotify_ui.play(uri)
    except spotify_ui.SpotifyUiError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:  # Windows UI Automation failed in a way we cannot explain better
        return {"success": False, "error": "No se pudo pulsar Reproducir en la app de Spotify. Comprueba que está abierta y a la vista."}
    result: Dict[str, Any] = {"success": True, "action": "spotify_uri", "mode": "ui"}
    if note:
        result["note"] = note
    return result


def play(value: str) -> Dict[str, Any]:
    """Play the item, or open it in the Spotify app when playback is not possible."""
    uri = normalize_spotify_uri(value)
    if not settings.get("spotify").get("refresh_token"):
        return _play_in_app(uri)

    body = _play_body(uri)
    try:
        try:
            _api("PUT", "/me/player/play", body)
        except SpotifyError as exc:
            if exc.reason != "NO_ACTIVE_DEVICE":
                raise
            # Spotify is closed or idle: start the app, wait for it to appear as a device, then play there.
            _open_in_app("spotify:")
            device_id = _wait_for_device()
            if not device_id:
                return _play_in_app(uri)
            _api("PUT", f"/me/player/play?device_id={urllib.parse.quote(device_id)}", body)
        return {"success": True, "action": "spotify_uri", "mode": "play"}
    except SpotifyError as exc:
        if exc.reason == "PREMIUM_REQUIRED":
            return _play_in_app(uri, "Tu cuenta no es Premium: se pulsó Reproducir en la app de Spotify.")
        if exc.status in (401, 403) or exc.reason == "NOT_CONNECTED":
            return {"success": False, "error": "Spotify pide volver a conectar la cuenta en Conectores."}
        return {"success": False, "error": str(exc)}


# --- Studio card ---

def status() -> Dict[str, Any]:
    saved = settings.get("spotify")
    if not saved.get("client_id"):
        return {"state": "needs_setup", "detail": "Los botones abren la lista en la app de Spotify y pulsan Reproducir (no hace falta cuenta ni Premium). Conecta tu cuenta si tienes Premium para reproducir sin abrir la app."}
    if not saved.get("refresh_token"):
        return {"state": "needs_setup", "detail": "Los botones pulsan Reproducir en la app de Spotify. Conecta tu cuenta solo si tienes Premium."}
    try:
        me = _api("GET", "/me") or {}
    except SpotifyError as exc:
        if exc.status in (401, 403):
            return {"state": "needs_setup", "detail": "Spotify rechazó el acceso. Vuelve a conectar la cuenta."}
        return {"state": "offline", "detail": str(exc)}
    name = me.get("display_name") or me.get("id") or "tu cuenta"
    if me.get("product") != "premium":
        return {"state": "limited", "detail": f"Conectado como {name}. Sin Premium los botones pulsan Reproducir en la app de Spotify, que debe estar abierta y a la vista."}
    return {"state": "ready", "detail": f"Conectado como {name}"}


def toggle_like() -> Dict[str, Any]:
    """Like or unlike the currently playing track via Web API or background UI automation."""
    if settings.get("spotify").get("refresh_token"):
        try:
            current = _api("GET", "/me/player/currently-playing")
            if current and current.get("item") and current["item"].get("id"):
                track_id = current["item"]["id"]
                track_name = current["item"].get("name", "Canción")
                contains = _api("GET", f"/me/tracks/contains?ids={track_id}")
                is_liked = bool(contains and contains[0]) if isinstance(contains, list) else False
                if is_liked:
                    _api("DELETE", f"/me/tracks?ids={track_id}")
                    return {"success": True, "action": "spotify_action", "liked": False, "track": track_name,
                            "note": f"Quitada de favoritos: {track_name}"}
                else:
                    _api("PUT", f"/me/tracks?ids={track_id}")
                    return {"success": True, "action": "spotify_action", "liked": True, "track": track_name,
                            "note": f"Añadida a canciones que te gustan: {track_name}"}
        except SpotifyError:
            pass  # Fall back to UI automation

    try:
        spotify_ui.toggle_like()
        return {"success": True, "action": "spotify_action", "mode": "ui"}
    except spotify_ui.SpotifyUiError as exc:
        return {"success": False, "error": str(exc)}
    except Exception:
        return {"success": False, "error": "No se pudo pulsar Me gusta en Spotify. Comprueba que la app está abierta."}


def actions() -> List[Dict[str, Any]]:
    return [
        {"id": "like", "label": "Me gusta", "sublabel": "Spotify", "icon": "/static/icons/plus.svg", "color": "#1db954",
         "action_type": "spotify_action", "target": "like", "extra": {}},
        {"id": "play_pause", "label": "Play/Pausa", "sublabel": "Spotify", "icon": "/static/icons/play_pause.svg", "color": "#1db954",
         "action_type": "media", "target": "play_pause", "extra": {}},
        {"id": "next", "label": "Siguiente", "sublabel": "Spotify", "icon": "/static/icons/next.svg", "color": "#1db954",
         "action_type": "media", "target": "next", "extra": {}},
        {"id": "prev", "label": "Anterior", "sublabel": "Spotify", "icon": "/static/icons/prev.svg", "color": "#1db954",
         "action_type": "media", "target": "prev", "extra": {}},
    ]


def options(name: str) -> List[Dict[str, Any]]:
    if name != "playlists":
        return []
    try:
        data = _api("GET", "/me/playlists?limit=50") or {}
    except SpotifyError as exc:
        if exc.reason == "NOT_CONNECTED":
            raise RuntimeError("Conecta tu cuenta de Spotify para ver tus playlists") from exc
        raise RuntimeError(str(exc)) from exc
    playlists = []
    for item in data.get("items") or []:
        if not item:
            continue
        try:
            uri = normalize_spotify_uri(item.get("uri"))
        except ValueError:
            continue
        images = item.get("images") or []
        image = images[-1].get("url", "") if images else ""
        playlists.append({"uri": uri, "name": item.get("name") or "Playlist",
                          "image": image if image.startswith("https://") else ""})
    return playlists
