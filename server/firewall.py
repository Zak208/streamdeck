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
from typing import Any, Dict

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
