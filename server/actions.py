import os
import time
import subprocess
import webbrowser
import ctypes
import winsound
from typing import Dict, Any, List
from server.system_scanner import system_scanner

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
KEYEVENTF_KEYUP = 0x0002

def send_vk_key(vk_code: int):
    """Simulates a media key press and release in Windows."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        print(f"Error sending virtual key {vk_code}: {e}")
        return False

def launch_smart_app(app_id_or_path: str) -> bool:
    """Launches an application intelligently using detected system paths, protocols, or direct execution."""
    app_key = (app_id_or_path or "").lower().strip()

    # Check detected apps from scanner first
    detected_apps = system_scanner.get_detected_apps()
    for app in detected_apps:
        if app["id"] == app_key or app["exe_name"].lower() == app_key or app_key in app["name"].lower():
            target_path = app["path"]
            try:
                if " " in target_path and not os.path.exists(target_path):
                    subprocess.Popen(target_path, shell=True)
                else:
                    os.startfile(target_path)
                return True
            except Exception:
                subprocess.Popen(target_path, shell=True)
                return True

    # Standard Windows App Aliases & Protocols
    known_aliases = {
        "discord": os.path.expandvars(r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"),
        "spotify": "spotify:",
        "steam": "steam:",
        "obs": r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        "chrome": "chrome",
        "calc": "calc",
        "calculator": "calc",
        "notepad": "notepad",
        "valorant": r"C:\Riot Games\Riot Client\RiotClientServices.exe",
        "riot": r"C:\Riot Games\Riot Client\RiotClientServices.exe"
    }

    cmd = known_aliases.get(app_key, app_id_or_path)
    try:
        if cmd.startswith("http://") or cmd.startswith("https://"):
            webbrowser.open(cmd)
            return True
        if ":" in cmd and "\\" not in cmd and "/" not in cmd:
            # Protocol like spotify: or steam:
            os.system(f"start {cmd}")
            return True
        if " " in cmd and not os.path.exists(cmd):
            subprocess.Popen(cmd, shell=True)
        else:
            os.startfile(cmd)
        return True
    except Exception:
        try:
            subprocess.Popen(cmd, shell=True)
            return True
        except Exception as e:
            print(f"Failed to launch {cmd}: {e}")
            return False

def execute_single_action(action_type: str, target: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
    extra = extra or {}
    action_type = (action_type or "").lower().strip()
    target_str = (target or "").strip()

    try:
        if action_type in ("launch", "preset_app", "app"):
            success = launch_smart_app(target_str)
            return {"success": success, "action": action_type, "target": target_str}

        elif action_type == "media":
            media_cmd = target_str.lower()
            if media_cmd in ("play_pause", "playpause", "play"):
                send_vk_key(VK_MEDIA_PLAY_PAUSE)
            elif media_cmd in ("next", "next_track"):
                send_vk_key(VK_MEDIA_NEXT_TRACK)
            elif media_cmd in ("prev", "previous", "prev_track"):
                send_vk_key(VK_MEDIA_PREV_TRACK)
            elif media_cmd in ("stop",):
                send_vk_key(VK_MEDIA_STOP)
            elif media_cmd in ("mute",):
                send_vk_key(VK_VOLUME_MUTE)
            else:
                return {"success": False, "error": f"Comando multimedia desconocido: {media_cmd}"}
            return {"success": True, "action": action_type, "target": target_str}

        elif action_type == "url":
            webbrowser.open(target_str)
            return {"success": True, "action": action_type, "target": target_str}

        elif action_type in ("command", "script"):
            subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", target_str], shell=True)
            return {"success": True, "action": action_type, "target": target_str}

        elif action_type == "obs_action":
            from server.obs_client import obs_client
            return obs_client.execute_obs_action(target_str, extra)

        elif action_type == "hardware_monitor":
            subprocess.Popen("taskmgr.exe")
            return {"success": True, "action": "open_taskmgr"}

        elif action_type == "sound":
            sound_type = target_str.lower()
            if sound_type == "beep":
                winsound.Beep(1000, 200)
            elif sound_type == "asterisk":
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            elif sound_type == "exclamation":
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            else:
                winsound.MessageBeep(winsound.MB_OK)
            return {"success": True, "action": action_type, "target": target_str}

        return {"success": False, "error": f"Tipo no soportado: {action_type}"}

    except Exception as e:
        return {"success": False, "error": str(e)}

def execute_action(action_type: str, target: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
    extra = extra or {}
    action_type = (action_type or "").lower().strip()

    if action_type == "multi":
        actions_list = extra.get("actions", [])
        results = []
        for act in actions_list:
            res = execute_single_action(act.get("action_type"), act.get("target"), act.get("extra"))
            results.append(res)
            delay = act.get("delay_ms", 150) / 1000.0
            if delay > 0:
                time.sleep(delay)
        return {"success": True, "type": "multi", "results": results}

    return execute_single_action(action_type, target, extra)
