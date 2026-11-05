"""Buttons that call a web address (a webhook): home automation, a local service, a notification.

Off by default and limited to hosts the user lists in Studio (Ajustes): the address of a button comes from the
profile, and a profile can come from someone else, so no host is called unless the user allowed it. Redirects are
not followed (they could lead to a host that is not on the list).
"""

import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

from server.paths import PORT
from server.settings_store import settings

MAX_HOSTS = 20
TIMEOUT_SECONDS = 8
MAX_BODY = 1000
METHODS = ("GET", "POST", "PUT")
WITH_BODY = ("POST", "PUT")
HOST_RULE = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?(:[0-9]{1,5})?", re.ASCII)
NOT_ALLOWED = "Esa dirección no está en la lista de destinos permitidos (Ajustes de Studio > Webhooks)."


def allowed_hosts() -> List[str]:
    hosts = settings.get("webhooks").get("hosts", [])
    return [h for h in hosts if isinstance(h, str)] if isinstance(hosts, list) else []


def set_allowed_hosts(values: Any) -> List[str]:
    """Save the list of hosts ("homeassistant.local:8123", "192.168.1.20"). Raises ValueError."""
    if not isinstance(values, list):
        raise ValueError("Los destinos deben ser una lista")
    if len(values) > MAX_HOSTS:
        raise ValueError(f"La lista admite como máximo {MAX_HOSTS} destinos")
    clean: List[str] = []
    for value in values:
        if not isinstance(value, str) or not HOST_RULE.fullmatch(value.strip().lower()):
            raise ValueError("Cada destino debe ser un nombre o una IP, con puerto opcional (por ejemplo 192.168.1.20:8123)")
        host = value.strip().lower()
        port = host.rpartition(":")[2] if ":" in host else ""
        if port and not 1 <= int(port) <= 65535:
            raise ValueError("El puerto debe estar entre 1 y 65535")
        if host not in clean:
            clean.append(host)
    settings.update("webhooks", {"hosts": clean})
    return clean


def validate_target(url: Any) -> str:
    if not isinstance(url, str) or any(not c.isprintable() or c.isspace() for c in url) or len(url) > 300:
        raise ValueError("La dirección del webhook no es válida")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("El webhook necesita una dirección http o https, sin usuario ni contraseña")
    return url


def validate_extra(extra: Any) -> Dict[str, Any]:
    extra = extra if isinstance(extra, dict) else {}
    method = str(extra.get("method", "GET")).upper()
    if method not in METHODS:
        raise ValueError("El método del webhook debe ser GET, POST o PUT")
    body = extra.get("body", "")
    if not isinstance(body, str) or len(body) > MAX_BODY or any(ord(c) < 32 and c not in "\n\t\r" for c in body):
        raise ValueError(f"El cuerpo del webhook admite como máximo {MAX_BODY} caracteres de texto")
    return {"method": method, "body": body if method in WITH_BODY else ""}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run(url: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if host not in allowed_hosts():
        return {"success": False, "error": NOT_ALLOWED}
    if (parsed.hostname or "") in ("localhost", "127.0.0.1", "::1") and parsed.port == PORT:
        # A button must not call StreamDesk's own admin API: that request would come from this PC.
        return {"success": False, "error": "Un webhook no puede llamar al propio StreamDesk"}
    data = extra.get("body", "").encode("utf-8") if extra.get("method") in WITH_BODY else None
    headers = {"User-Agent": "StreamDesk-Webhook"}
    if data is not None:
        headers["Content-Type"] = "application/json" if extra["body"].lstrip().startswith(("{", "[")) else "text/plain; charset=utf-8"
    request = urllib.request.Request(url, data=data, method=extra.get("method", "GET"), headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (urllib.error.URLError, OSError) as exc:
        return {"success": False, "error": f"No se pudo llamar al webhook: {getattr(exc, 'reason', exc)}"}
    if 200 <= status < 300:
        return {"success": True, "action": "webhook", "status": status}
    return {"success": False, "error": f"El webhook respondió con el código {status}"}
