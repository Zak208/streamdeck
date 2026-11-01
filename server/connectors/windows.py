"""Windows audio controls that work with any app, no setup needed."""

import re
from ctypes import POINTER, cast
from typing import Any, Dict, List, Optional

import comtypes
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, DEVICE_STATE, EDataFlow, IAudioEndpointVolume

from server.audio_controller import audio_controller
from server.com_worker import com_worker

INFO = {
    "id": "windows",
    "name": "Windows",
    "icon": "/static/icons/volume_up.svg",
    "color": "#0ea5e9",
    "description": "Micrófono, salida de audio y mute por aplicación. No necesita configuración.",
}

DEVICE_ID = re.compile(r"^\{[0-9A-Fa-f.]{1,40}\}\.\{[0-9A-Fa-f-]{36}\}$")


def _com() -> None:
    try:
        comtypes.CoInitialize()
    except Exception:
        pass


def _mic_endpoint():
    mic = AudioUtilities.GetMicrophone()
    interface = mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interface, POINTER(IAudioEndpointVolume))


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
    return {"success": False, "error": "Acción de Windows no válida"}


def status() -> Dict[str, Any]:
    muted = get_mic_muted()
    if muted is None:
        return {"state": "offline", "detail": "Windows no tiene un micrófono predeterminado"}
    return {"state": "ready", "detail": "Micrófono silenciado" if muted else "Listo"}


def actions() -> List[Dict[str, Any]]:
    return [
        {"id": "mic_mute", "label": "Mute micrófono", "sublabel": "Windows", "icon": "/static/icons/mute.svg",
         "color": "#ef4444", "action_type": "windows", "target": "mic_mute", "extra": {},
         "description": "Silencia el micrófono de Windows. Sirve para Discord, juegos y cualquier app."},
    ]


def options(name: str) -> List[Dict[str, Any]]:
    if name == "outputs":
        return list_output_devices()
    return []
