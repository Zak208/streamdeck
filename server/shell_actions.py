"""PowerShell or cmd command lines run by a button, one after another.

This is the one action that runs arbitrary code, so it is off until the user switches it on in Studio
(Ajustes). The command lines are part of the profile, which only Studio on this PC can change: a phone
can press the button but cannot choose what it runs. A command runs with the permissions of the Windows
user that runs StreamDesk and stops the sequence at the first failure.
"""

import base64
import os
import subprocess
from typing import Any, Dict, List

from server.settings_store import settings

MAX_COMMANDS = 8
MAX_COMMAND_LENGTH = 500
TIMEOUT_SECONDS = 60
OUTPUT_SNIPPET = 300
SHELLS = ("powershell", "cmd")
DISABLED_MESSAGE = "Los comandos de consola están desactivados. Actívalos en Ajustes de Studio."
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def enabled() -> bool:
    return settings.get("commands").get("enabled") is True


def set_enabled(value: bool) -> None:
    settings.update("commands", {"enabled": bool(value)})


def validate_commands(value: Any) -> List[str]:
    """The command lines of a button: 1 to 8 non-empty single-purpose strings."""
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_COMMANDS:
        raise ValueError(f"Un botón de comandos necesita entre 1 y {MAX_COMMANDS} comandos")
    clean: List[str] = []
    for command in value:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("Los comandos no pueden estar vacíos")
        if len(command) > MAX_COMMAND_LENGTH:
            raise ValueError(f"Cada comando puede tener como máximo {MAX_COMMAND_LENGTH} caracteres")
        if any(ord(char) < 32 and char != "\t" for char in command) or "\x7f" in command:
            raise ValueError("Un comando no puede tener saltos de línea ni caracteres de control: usa un comando por línea de la lista")
        clean.append(command.strip())
    return clean


def _command_line(shell: str, command: str):
    if shell == "powershell":
        # -EncodedCommand takes the text as UTF-16 base64: no quoting problems and no shell parsing of the line.
        # Without this PowerShell writes a "Preparing modules" progress record (CLIXML) to stderr.
        script = "$ProgressPreference = 'SilentlyContinue'; " + command
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]
    return 'cmd.exe /d /s /c "' + command + '"'


def _printed(code: int, stdout: bytes, stderr: bytes) -> str:
    """What the command printed: its output, plus its error text when it failed (minus PowerShell's XML noise)."""
    text = stdout.decode("oem", errors="replace").strip()
    if code != 0:
        error = stderr.decode("oem", errors="replace").split("#< CLIXML")[0].strip()
        text = (text + " | " + error).strip(" |") if error else text
    return text[:OUTPUT_SNIPPET]


def _execute(command_line):
    """Run one line and return (exit code, stdout, stderr). On a timeout the whole process tree is killed:
    a program the line started could otherwise keep the pipes open and hold StreamDesk past the limit."""
    process = subprocess.Popen(
        command_line, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
        creationflags=NO_WINDOW, cwd=os.path.expanduser("~"),
    )
    try:
        stdout, stderr = process.communicate(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise
    return process.returncode, stdout, stderr


def run(shell: str, commands: List[str]) -> Dict[str, Any]:
    """Run the lines in order. Returns success, and on failure which line failed and what it printed."""
    if not enabled():
        return {"success": False, "error": DISABLED_MESSAGE}
    results: List[Dict[str, Any]] = []
    total = len(commands)
    for number, command in enumerate(commands, 1):
        try:
            code, stdout, stderr = _execute(_command_line(shell, command))
        except subprocess.TimeoutExpired:
            return {"success": False, "results": results,
                    "error": f"El comando {number} de {total} tardó más de {TIMEOUT_SECONDS} segundos y se detuvo"}
        except OSError as exc:
            return {"success": False, "results": results, "error": f"No se pudo ejecutar el comando {number}: {exc}"}
        output = _printed(code, stdout, stderr)
        results.append({"command": command[:80], "exit_code": code, "output": output})
        if code != 0:
            return {"success": False, "results": results,
                    "error": f"El comando {number} de {total} terminó con código {code}: {output or 'sin mensaje'}"}
    return {"success": True, "action": "command", "results": results}
