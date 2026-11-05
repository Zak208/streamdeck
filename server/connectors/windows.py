"""Windows audio controls that work with any app, no setup needed."""

import ctypes
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, DEVICE_STATE, EDataFlow, IAudioEndpointVolume

import threading
import time

from server.audio_controller import audio_controller
from server.com_worker import com_worker
from server.settings_store import settings

INFO = {
    "id": "windows",
    "name": "Windows",
    "icon": "/static/icons/volume_up.svg",
    "color": "#0ea5e9",
    "description": "Micrófono, salida de audio y mute por aplicación. No necesita configuración.",
}

DEVICE_ID = re.compile(r"^\{[0-9A-Fa-f.]{1,40}\}\.\{[0-9A-Fa-f-]{36}\}$")


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PLAN_LINE = re.compile(r"([0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12})\s+\((.+)\)\s*\*?\s*$")
SHUTDOWN_ARGS = {"shutdown": ["/s"], "restart": ["/r"], "logoff": ["/l"], "hibernate": ["/h"], "cancel": ["/a"]}


def _decode(raw: bytes) -> str:
    """What a console tool printed: UTF-8 when it is valid, otherwise in the PC's OEM code page (accents in plan names)."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        page = ctypes.windll.kernel32.GetOEMCP()
        return raw.decode(f"cp{page}" if page != 65001 else "cp1252", errors="replace")


def _run(command: List[str]) -> subprocess.CompletedProcess:
    """A Windows tool by its name and a list of arguments: never a shell, never text from the profile."""
    done = subprocess.run(command, capture_output=True, timeout=20, creationflags=NO_WINDOW)
    done.stdout, done.stderr = _decode(done.stdout or b""), _decode(done.stderr or b"")
    return done


POWER_DISABLED = "Apagar, reiniciar, suspender y cerrar sesión están desactivados. Actívalos en Ajustes de Studio."
MIN_POWER_DELAY = 10  # seconds: time to cancel a shutdown or restart that was not meant
SCREENSHOT_GAP = 2.0
_last_screenshot = 0.0
_screenshot_lock = threading.Lock()


def power_enabled() -> bool:
    return settings.get("power").get("enabled") is True


def set_power_enabled(value: bool) -> None:
    settings.update("power", {"enabled": bool(value)})


def power(extra: Dict[str, Any]) -> Dict[str, Any]:
    mode, delay = extra.get("mode", "sleep"), int(extra.get("delay", 15))
    # Off until the user switches it on in Studio: the confirmation of a button lives on the phone, so the PC must
    # not depend on it (a paired phone, or a profile from someone else, could otherwise switch the PC off).
    if mode != "cancel" and not power_enabled():
        return {"success": False, "error": POWER_DISABLED}
    if mode in ("shutdown", "restart"):
        delay = max(delay, MIN_POWER_DELAY)
    if mode == "sleep":
        # SetSuspendState(hibernate=False, force=True, wakeupEventsDisabled=False)
        ok = bool(ctypes.windll.powrprof.SetSuspendState(False, True, False))
        return {"success": ok} if ok else {"success": False, "error": "Windows no pudo suspender el PC"}
    command = ["shutdown", *SHUTDOWN_ARGS[mode]]
    if mode in ("shutdown", "restart"):
        command += ["/t", str(delay)]  # a pause long enough to cancel it from another button
    done = _run(command)
    if done.returncode != 0:
        return {"success": False, "error": (done.stderr or done.stdout or "Windows rechazó la orden").strip()[:200]}
    return {"success": True, "action": f"windows_power_{mode}"}


def list_power_plans() -> List[Dict[str, Any]]:
    done = _run(["powercfg", "/l"])
    return [{"name": name.strip(), "id": guid.lower(), "active": "*" in line.split(")")[-1]}
            for line in done.stdout.splitlines() for guid, name in [m.groups() for m in PLAN_LINE.finditer(line)]]


def set_power_plan(plan: str) -> Dict[str, Any]:
    wanted = next((p for p in list_power_plans() if p["name"].lower() == (plan or "").strip().lower()), None)
    if wanted is None:
        return {"success": False, "error": f"No existe el plan de energía «{plan}» en este PC"}
    done = _run(["powercfg", "/setactive", wanted["id"]])  # the id comes from powercfg itself
    if done.returncode != 0:
        return {"success": False, "error": (done.stderr or "Windows no cambió el plan de energía").strip()[:200]}
    return {"success": True, "action": "windows_power_plan", "plan": wanted["name"]}


def display_mode(mode: str) -> Dict[str, Any]:
    done = _run([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "DisplaySwitch.exe"), f"/{mode}"])
    return {"success": True, "action": "windows_display_mode", "mode": mode} if done.returncode == 0 else \
        {"success": False, "error": "Windows no cambió el modo de pantalla"}


def screenshot() -> Dict[str, Any]:
    global _last_screenshot
    from PIL import ImageGrab
    with _screenshot_lock:
        now = time.monotonic()
        if now - _last_screenshot < SCREENSHOT_GAP:
            return {"success": False, "error": "Espera un par de segundos entre capturas"}
        _last_screenshot = now
    folder = os.path.join(os.path.expanduser("~"), "Pictures", "StreamDesk")
    os.makedirs(folder, exist_ok=True)
    name = f"captura_{datetime.now():%Y%m%d_%H%M%S_%f}"[:-3] + ".png"  # built here (with milliseconds), never from the profile
    ImageGrab.grab(all_screens=True).save(os.path.join(folder, name))
    return {"success": True, "action": "windows_screenshot", "file": name}


def master_volume(extra: Dict[str, Any]) -> Dict[str, Any]:
    if extra.get("mode") == "set":
        target = int(extra["value"])
    else:
        current = com_worker.call(audio_controller.get_master_volume)
        if current.get("error"):
            return {"success": False, "error": "No se pudo leer el volumen de Windows"}
        target = int(current["volume"]) + int(extra["value"])
    target = max(0, min(100, target))
    result = com_worker.call(audio_controller.set_master_volume, target)
    return {"success": True, "action": "windows_master_volume", "volume": target} if result.get("success") else \
        {"success": False, "error": result.get("error") or "No se pudo cambiar el volumen"}


def _com() -> None:
    try:
        comtypes.CoInitialize()
    except Exception:
        pass


def _mic_endpoint():
    mic = AudioUtilities.GetMicrophone()
    interface = mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    # QueryInterface, never ctypes.cast: cast wraps the same COM pointer a second time without
    # adding a reference, so both wrappers release it and Windows crashes the whole process
    # (reproduced: microphone + device list in a loop, access violation within seconds).
    return interface.QueryInterface(IAudioEndpointVolume)


def _get_mic_muted() -> Optional[bool]:
    """Mute state of the default microphone, or None when the PC has no usable one."""
    _com()
    try:
        return bool(_mic_endpoint().GetMute())
    except Exception:
        return None


def _toggle_mic_mute() -> Dict[str, Any]:
    _com()
    try:
        endpoint = _mic_endpoint()
        muted = not bool(endpoint.GetMute())
        endpoint.SetMute(muted, None)
        return {"success": True, "action": "windows_mic_mute", "muted": muted, "active": muted}
    except Exception:
        return {"success": False, "error": "No se encontró un micrófono predeterminado en Windows"}


def _list_output_devices() -> List[Dict[str, Any]]:
    _com()
    default_id = AudioUtilities.GetSpeakers().id
    devices = AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value)
    return [{"id": d.id, "name": d.FriendlyName, "default": d.id == default_id} for d in devices]


def _set_output_device(device_id: str) -> Dict[str, Any]:
    if not DEVICE_ID.fullmatch(device_id or ""):
        return {"success": False, "error": "Dispositivo de audio no válido"}
    _com()
    known = {d["id"]: d["name"] for d in _list_output_devices()}
    if device_id not in known:
        return {"success": False, "error": "Ese dispositivo de audio ya no está conectado"}
    try:
        AudioUtilities.SetDefaultDevice(device_id)
    except Exception as exc:
        return {"success": False, "error": f"Windows no permitió cambiar la salida: {exc}"}
    return {"success": True, "action": "windows_output_device", "device": known[device_id]}


def get_mic_muted() -> Optional[bool]:
    return com_worker.call(_get_mic_muted)


def toggle_mic_mute() -> Dict[str, Any]:
    return com_worker.call(_toggle_mic_mute)


def list_output_devices() -> List[Dict[str, Any]]:
    return com_worker.call(_list_output_devices)


def set_output_device(device_id: str) -> Dict[str, Any]:
    return com_worker.call(_set_output_device, device_id)


def execute(target: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    if target == "mic_mute":
        return toggle_mic_mute()
    if target == "app_mute":
        result = com_worker.call(audio_controller.toggle_app_mute, extra.get("process", ""))
        if result.get("success"):
            result.update({"action": "windows_app_mute", "active": result["muted"]})
        else:
            result["error"] = "Esa aplicación no está reproduciendo audio ahora mismo"
        return result
    if target == "output_device":
        return set_output_device(extra.get("device_id", ""))
    if target == "lock_pc":
        # LockWorkStation returns 0 when Windows refuses (for example, when it is already locked).
        locked = bool(ctypes.windll.user32.LockWorkStation())
        return {"success": locked} if locked else {"success": False, "error": "Windows no pudo bloquear el PC"}
    if target == "power":
        return power(extra)
    if target == "power_plan":
        return set_power_plan(extra.get("plan", ""))
    if target == "display_mode":
        return display_mode(extra.get("mode", "extend"))
    if target == "screenshot":
        return screenshot()
    if target == "master_volume":
        return master_volume(extra)
    return {"success": False, "error": "Acción de Windows no válida"}


def status() -> Dict[str, Any]:
    muted = get_mic_muted()
    if muted is None:
        return {"state": "offline", "detail": "Windows no tiene un micrófono predeterminado"}
    return {"state": "ready", "detail": "Micrófono silenciado" if muted else "Listo"}


def actions() -> List[Dict[str, Any]]:
    return [
        {"id": "mic_mute", "label": "Mute micrófono", "sublabel": "Windows", "icon": "/static/icons/mic.svg",
         "color": "#ef4444", "action_type": "windows", "target": "mic_mute", "extra": {},
         "description": "Silencia el micrófono de Windows. Sirve para Discord, juegos y cualquier app."},
        {"id": "lock_pc", "label": "Bloquear PC", "sublabel": "Windows", "icon": "/static/icons/lock.svg",
         "color": "#f8c700", "action_type": "windows", "target": "lock_pc", "extra": {},
         "description": "Bloquea la sesión de Windows, como Win+L."},
        {"id": "command", "label": "Comandos de consola", "sublabel": "PowerShell o cmd", "icon": "/static/icons/sliders.svg",
         "color": "#a855f7", "action_type": "command", "target": "powershell", "extra": {"commands": ["Get-Date"]},
         "configure": True, "confirm_default": True,
         "description": "Ejecuta uno o varios comandos de PowerShell o cmd, en orden. Hay que activarlos antes en Ajustes."},
        _win("screenshot", "Captura a archivo", "Pictures\\StreamDesk", "video", "#38bdf8", "screenshot"),
        _win("vol_up", "Subir volumen", "Windows, +10", "volume_up", "#0ea5e9", "master_volume", {"mode": "step", "value": 10}),
        _win("vol_down", "Bajar volumen", "Windows, -10", "mute", "#0ea5e9", "master_volume", {"mode": "step", "value": -10}),
        _win("display_extend", "Extender pantallas", "Windows", "video", "#38bdf8", "display_mode", {"mode": "extend"}),
        _win("display_clone", "Duplicar pantallas", "Windows", "video", "#38bdf8", "display_mode", {"mode": "clone"}),
        _win("display_internal", "Solo pantalla del PC", "Windows", "video", "#38bdf8", "display_mode", {"mode": "internal"}),
        _win("display_external", "Solo segunda pantalla", "Windows", "video", "#38bdf8", "display_mode", {"mode": "external"}),
        _win("power_plan", "Plan de energía", "Windows", "power", "#f59e0b", "power_plan", {"plan": "Elige"}, fields=[
            {"name": "plan", "label": "Plan de energía", "options": "powerplans", "filter_by": None, "required": True}]),
        _win("sleep", "Suspender el PC", "Windows", "power", "#f59e0b", "power", {"mode": "sleep", "delay": 0}, confirm=True),
        _win("restart", "Reiniciar el PC", "Windows, en 15 s", "power", "#ef4444", "power", {"mode": "restart", "delay": 15}, confirm=True),
        _win("shutdown", "Apagar el PC", "Windows, en 15 s", "power", "#ef4444", "power", {"mode": "shutdown", "delay": 15}, confirm=True),
        _win("logoff", "Cerrar sesión", "Windows", "lock", "#ef4444", "power", {"mode": "logoff", "delay": 0}, confirm=True),
        _win("cancel_power", "Cancelar apagado", "Windows", "trash", "#10b981", "power", {"mode": "cancel", "delay": 0}),
    ]


def _win(action_id: str, label: str, sub: str, icon: str, color: str, target: str, extra: Optional[Dict[str, Any]] = None,
         fields: Optional[List[Dict[str, Any]]] = None, confirm: bool = False) -> Dict[str, Any]:
    action: Dict[str, Any] = {"id": action_id, "label": label, "sublabel": sub, "icon": f"/static/icons/{icon}.svg", "color": color,
                              "action_type": "windows", "target": target, "extra": extra or {}}
    if fields:
        action.update({"fields": fields, "configure": True})
    if confirm:
        action["confirm_default"] = True  # the phone asks first: these end the session or switch the PC off
    return action


def options(name: str) -> List[Dict[str, Any]]:
    if name == "outputs":
        return list_output_devices()
    if name == "powerplans":
        return [{"name": plan["name"], "active": plan["active"]} for plan in list_power_plans()]
    return []
