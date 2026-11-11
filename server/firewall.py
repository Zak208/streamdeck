"""Let the phone reach StreamDesk through the Windows firewall.

Windows blocks inbound connections from other devices unless a rule allows them.
The usual "Allow access" prompt is easy to miss, and a network marked "Public" is
stricter still, so a phone on the same Wi-Fi can fail to connect with no message.

StreamDesk never changes the firewall by itself. It checks whether the rule exists
and, when the user presses the button, asks Windows to run the one command that adds
it. Windows shows its own confirmation (UAC) and the user decides.
"""

import ctypes
import subprocess
from typing import Any, Dict, List

from server.paths import PORT

# ASCII only: the name travels through a command line whose code page we do not control.
RULE_NAME = "StreamDesk Pro Movil"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
SE_ERR_ACCESSDENIED = 5  # what ShellExecute reports when the user declines the UAC prompt


def rule_arguments() -> str:
    # Any profile, because a home network is often classed as Public; but only from the local
    # subnet, so nothing outside the user's own network can even reach the port.
    return (
        f'advfirewall firewall add rule name="{RULE_NAME}" dir=in action=allow protocol=TCP '
        f"localport={PORT} remoteip=localsubnet profile=any"
    )


def rule_exists() -> bool:
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_NAME}"],
            capture_output=True, timeout=10, creationflags=NO_WINDOW,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def request_rule() -> Dict[str, Any]:
    """Ask Windows to add the rule. The user answers the confirmation; we only report what happened."""
    if rule_exists():
        return {"requested": False, "already": True}
    outcome = ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", rule_arguments(), None, 0)
    if outcome > 32:
        return {"requested": True}
    if outcome == SE_ERR_ACCESSDENIED:
        return {"requested": False, "error": "Cancelaste el aviso de Windows. Pulsa el botón otra vez y elige Sí."}
    return {"requested": False, "error": "Windows no pudo abrir el aviso de permisos."}


def network_categories() -> List[str]:
    """"Public" / "Private" for each network this PC is connected to ([] if Windows does not say)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "(Get-NetConnectionProfile | ForEach-Object { $_.NetworkCategory }) -join ','"],
            capture_output=True, timeout=10, creationflags=NO_WINDOW,
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        return [part for part in text.split(",") if part] if result.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


def connection_checks(ip: str, port: int, phone_reached: bool) -> List[Dict[str, Any]]:
    """The usual reasons a phone cannot connect, each with what to do about it.

    `status` is "ok", "warn" (may be the cause) or "fail" (will be the cause); `action` names a button Studio can offer.
    """
    checks: List[Dict[str, Any]] = [
        {"id": "server", "status": "ok", "title": "StreamDesk está activo",
         "detail": f"Escucha en el puerto {port}.", "action": ""},
    ]
    if ip.startswith("127."):
        checks.append({"id": "network", "status": "fail", "title": "El PC no parece estar conectado a una red",
                       "detail": "Conéctalo a la misma Wi-Fi o red por cable que el móvil.", "action": ""})
    else:
        checks.append({"id": "network", "status": "ok", "title": f"Dirección del PC: {ip}",
                       "detail": "El móvil debe estar en la misma Wi-Fi (no en datos móviles ni en una red de invitados).", "action": ""})
    if rule_exists():
        checks.append({"id": "firewall", "status": "ok", "title": "Windows deja pasar al móvil",
                       "detail": "La regla de StreamDesk está creada.", "action": ""})
    elif phone_reached:
        checks.append({"id": "firewall", "status": "ok", "title": "Windows deja pasar al móvil",
                       "detail": "Un móvil ya se ha conectado, así que el camino está abierto.", "action": ""})
    else:
        checks.append({"id": "firewall", "status": "fail", "title": "Windows puede estar bloqueando al móvil",
                       "detail": "Es la causa más habitual. Permite la conexión y Windows te pedirá confirmación.", "action": "firewall"})
    if "Public" in network_categories():
        checks.append({"id": "profile", "status": "warn", "title": "Windows trata tu red como Pública",
                       "detail": "La regla de StreamDesk funciona igualmente. Si aun así falla, cambia la red a Privada en Configuración > Red e Internet.",
                       "action": ""})
    if not phone_reached:
        checks.append({"id": "phone", "status": "warn", "title": "Todavía no se ha conectado ningún móvil",
                       "detail": "Escanea el QR del panel izquierdo con la cámara del móvil o con la app de StreamDesk.", "action": ""})
    return checks
