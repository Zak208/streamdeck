import os
import psutil
import comtypes
from typing import List, Dict, Any, Optional
from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

class AudioController:
    """Manages Windows Master Volume and Per-Application Audio Sessions via pycaw."""

    def __init__(self):
        self._init_com()

    def _init_com(self):
        try:
            comtypes.CoInitialize()
        except Exception:
            pass

    def get_master_volume(self) -> Dict[str, Any]:
        """Returns master volume (0-100) and mute status."""
        self._init_com()
        try:
            device = AudioUtilities.GetSpeakers()
            if not device:
                return {"volume": 0, "muted": False}
            vol_endpoint = device.EndpointVolume
            vol = round(vol_endpoint.GetMasterVolumeLevelScalar() * 100)
            muted = bool(vol_endpoint.GetMute())
            return {"volume": vol, "muted": muted}
        except Exception as e:
            return {"volume": 0, "muted": False, "error": str(e)}

    def set_master_volume(self, volume_percent: int) -> Dict[str, Any]:
        """Sets master volume (0-100)."""
        self._init_com()
        try:
            device = AudioUtilities.GetSpeakers()
            if not device:
                return {"success": False, "error": "No audio device"}
            vol_endpoint = device.EndpointVolume
            clamped = max(0, min(100, volume_percent)) / 100.0
            vol_endpoint.SetMasterVolumeLevelScalar(clamped, None)
            return {"success": True, "volume": volume_percent, "muted": bool(vol_endpoint.GetMute())}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_master_mute(self) -> Dict[str, Any]:
        """Toggles master volume mute."""
        self._init_com()
        try:
            device = AudioUtilities.GetSpeakers()
            if not device:
                return {"success": False}
            vol_endpoint = device.EndpointVolume
            curr = bool(vol_endpoint.GetMute())
            vol_endpoint.SetMute(not curr, None)
            return {"success": True, "muted": not curr}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_audio_sessions(self) -> List[Dict[str, Any]]:
        """Returns list of active processes producing or registered for audio."""
        self._init_com()
        sessions_data = []
        seen_names = set()

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                volume_control = session._ctl.QueryInterface(ISimpleAudioVolume)
                proc = session.Process
                if proc:
                    name = proc.name()
                    pid = proc.pid
                else:
                    name = "System Sounds"
                    pid = 0

                # Filter or clean process name for display
                display_name = name.replace(".exe", "").capitalize()
                vol = round(volume_control.GetMasterVolume() * 100)
                muted = bool(volume_control.GetMute())

                # Avoid duplicate names in quick selector, keep newest or distinct
                key = f"{name}_{pid}"
                sessions_data.append({
                    "id": key,
                    "process_name": name,
                    "display_name": display_name,
                    "pid": pid,
                    "volume": vol,
                    "muted": muted
                })
        except Exception as e:
            print(f"Error fetching audio sessions: {e}")

        return sessions_data

    def set_app_volume(self, process_name: str, volume_percent: int) -> Dict[str, Any]:
        """Sets volume for an application by process name (case-insensitive) or PID."""
        self._init_com()
        clamped = max(0, min(100, volume_percent)) / 100.0
        success = False

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                proc = session.Process
                if proc and (proc.name().lower() == process_name.lower() or str(proc.pid) == str(process_name)):
                    vol_ctrl = session._ctl.QueryInterface(ISimpleAudioVolume)
                    vol_ctrl.SetMasterVolume(clamped, None)
                    success = True
            return {"success": success, "process": process_name, "volume": volume_percent}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_app_mute(self, process_name: str) -> Dict[str, Any]:
        """Toggles mute for an application by process name."""
        self._init_com()
        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                proc = session.Process
                if proc and proc.name().lower() == process_name.lower():
                    vol_ctrl = session._ctl.QueryInterface(ISimpleAudioVolume)
                    curr = bool(vol_ctrl.GetMute())
                    vol_ctrl.SetMute(not curr, None)
                    return {"success": True, "process": process_name, "muted": not curr}
            return {"success": False, "error": "Process not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

audio_controller = AudioController()

