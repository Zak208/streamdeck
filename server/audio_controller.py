import psutil
import comtypes
from typing import List, Dict, Any
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

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    volume_control = session._ctl.QueryInterface(ISimpleAudioVolume)
                    proc = session.Process
                    if proc:
                        try:
                            name = proc.name()
                            pid = proc.pid
                        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                            continue
                    else:
                        name = "System Sounds"
                        pid = 0

                    # Filter or clean process name for display
                    display_name = name.replace(".exe", "").capitalize()
                    vol = round(volume_control.GetMasterVolume() * 100)
                    muted = bool(volume_control.GetMute())

                    key = f"{name}_{pid}"
                    sessions_data.append({
                        "id": key,
                        "process_name": name,
                        "display_name": display_name,
                        "pid": pid,
                        "volume": vol,
                        "muted": muted
                    })
                except Exception:
                    # Individual session error (stale COM pointer, dead process, etc)
                    # Must NOT crash the loop for other sessions!
                    continue
        except Exception as e:
            print(f"Error fetching audio sessions: {e}")

        return sessions_data

    def set_app_volume(self, process_name: str, volume_percent: int) -> Dict[str, Any]:
        """Sets volume for an application by process name (case-insensitive) or PID."""
        self._init_com()
        clamped = max(0, min(100, volume_percent)) / 100.0
        success = False
        target = (process_name or "").strip().lower()
        target_no_ext = target[:-4] if target.endswith(".exe") else target

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    proc = session.Process
                    if not proc:
                        continue
                    try:
                        pname = proc.name().lower()
                        pid_str = str(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        continue

                    pname_no_ext = pname[:-4] if pname.endswith(".exe") else pname

                    # Match by exact name, name without .exe, or PID
                    if pname == target or pname_no_ext == target_no_ext or pid_str == target:
                        vol_ctrl = session._ctl.QueryInterface(ISimpleAudioVolume)
                        vol_ctrl.SetMasterVolume(clamped, None)
                        success = True
                except Exception:
                    continue
            return {"success": success, "process": process_name, "volume": volume_percent}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def toggle_app_mute(self, process_name: str) -> Dict[str, Any]:
        """Toggles mute for an application by process name or PID."""
        self._init_com()
        target = (process_name or "").strip().lower()
        target_no_ext = target[:-4] if target.endswith(".exe") else target
        matching_sessions = []

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                try:
                    proc = session.Process
                    if not proc:
                        continue
                    try:
                        pname = proc.name().lower()
                        pid_str = str(proc.pid)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        continue

                    pname_no_ext = pname[:-4] if pname.endswith(".exe") else pname
                    if pname == target or pname_no_ext == target_no_ext or pid_str == target:
                        matching_sessions.append(session)
                except Exception:
                    continue

            if not matching_sessions:
                return {"success": False, "error": "Process not found"}

            # Determine target mute state (invert the state of the first session)
            first_ctrl = matching_sessions[0]._ctl.QueryInterface(ISimpleAudioVolume)
            new_mute = not bool(first_ctrl.GetMute())

            # Apply new state to ALL matching sessions
            for s in matching_sessions:
                try:
                    vol_ctrl = s._ctl.QueryInterface(ISimpleAudioVolume)
                    vol_ctrl.SetMute(new_mute, None)
                except Exception:
                    pass

            return {"success": True, "process": process_name, "muted": new_mute}
        except Exception as e:
            return {"success": False, "error": str(e)}

audio_controller = AudioController()

