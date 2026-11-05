import asyncio
import base64
import hashlib
import json
from typing import Dict, Any, List, Optional

from server.settings_store import settings

OBS_WS_HOST = "127.0.0.1"
OBS_WS_PORT = 4455

OBS_UNREACHABLE = "OBS no responde. Ábrelo y activa el servidor WebSocket en Herramientas > Ajustes del servidor WebSocket."
OBS_NEEDS_PASSWORD = "OBS pide contraseña. Guárdala en StreamDesk > Conectores > OBS."
OBS_WRONG_PASSWORD = "La contraseña de OBS no es correcta."
OBS_AUTH_FAILED_CODE = 4009


def _request_ok(response: Dict[str, Any]) -> bool:
    return bool(response.get("requestStatus", {}).get("result"))


def _auth_string(password: str, salt: str, challenge: str) -> str:
    """OBS WebSocket 5 authentication: base64(sha256(base64(sha256(password + salt)) + challenge))."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class OBSClient:
    """Lightweight OBS Studio WebSocket v5 client. One short connection per request.

    Every public method blocks, so call them from a worker thread, never from
    the event loop.
    """

    def __init__(self, host: str = OBS_WS_HOST, port: Optional[int] = None, password: Optional[str] = None):
        self.host = host
        # None means "read it from the saved settings each time", so changes apply at once.
        self._port = port
        self._password = password
        self.is_recording = False
        self.is_streaming = False
        self.current_scene = ""

    @property
    def port(self) -> int:
        return self._port or int(settings.get("obs").get("port") or OBS_WS_PORT)

    @property
    def password(self) -> str:
        return self._password if self._password is not None else settings.get("obs").get("password", "")

    async def _send_request(self, request_type: str, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import websockets
        uri = f"ws://{self.host}:{self.port}"
        try:
            async with websockets.connect(uri, open_timeout=1.0, close_timeout=1.0) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=1.0))

                identify: Dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}  # no events: only our answer
                challenge = hello.get("d", {}).get("authentication")
                if challenge:
                    if not self.password:
                        return {"requestStatus": {"result": False, "comment": OBS_NEEDS_PASSWORD}, "auth_error": True}
                    identify["authentication"] = _auth_string(self.password, challenge["salt"], challenge["challenge"])
                await ws.send(json.dumps({"op": 1, "d": identify}))

                try:
                    await asyncio.wait_for(ws.recv(), timeout=1.0)  # Identified (op 2)
                except Exception as exc:
                    if getattr(getattr(exc, "rcvd", None), "code", None) == OBS_AUTH_FAILED_CODE:
                        return {"requestStatus": {"result": False, "comment": OBS_WRONG_PASSWORD}, "auth_error": True}
                    raise

                req_id = f"req_{request_type}_{int(asyncio.get_event_loop().time() * 1000)}"
                await ws.send(json.dumps({"op": 6, "d": {
                    "requestType": request_type,
                    "requestId": req_id,
                    "requestData": request_data or {},
                }}))

                deadline = asyncio.get_event_loop().time() + 1.5
                while True:
                    resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=max(0.05, deadline - asyncio.get_event_loop().time())))
                    if resp.get("op") == 7 and resp.get("d", {}).get("requestId") == req_id:
                        return resp.get("d", {})  # anything else (an event) is not the answer
        except Exception as e:
            return {"requestStatus": {"result": False, "comment": str(e)}, "unreachable": True}

    def request(self, request_type: str, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return asyncio.run(self._send_request(request_type, request_data))

    @staticmethod
    def failure(res: Dict[str, Any]) -> Dict[str, Any]:
        if res.get("auth_error"):
            return {"success": False, "error": res["requestStatus"]["comment"]}
        if res.get("unreachable"):
            return {"success": False, "error": OBS_UNREACHABLE}
        return {"success": False, "error": res.get("requestStatus", {}).get("comment") or "OBS rechazó la acción"}

    # --- Information for the Studio connector card ---

    def status(self) -> Dict[str, Any]:
        res = self.request("GetVersion")
        if _request_ok(res):
            return {"state": "ready", "detail": f"OBS {res.get('responseData', {}).get('obsVersion', '')}".strip()}
        failed = self.failure(res)["error"]
        state = "needs_setup" if res.get("auth_error") else "offline"
        return {"state": state, "detail": failed}

    def list_scenes(self) -> List[str]:
        res = self.request("GetSceneList")
        if not _request_ok(res):
            raise RuntimeError(self.failure(res)["error"])
        return [s["sceneName"] for s in res.get("responseData", {}).get("scenes", [])]

    def list_inputs(self) -> List[Dict[str, Any]]:
        """Audio-capable sources first: those are the ones that make sense to mute."""
        res = self.request("GetInputList")
        if not _request_ok(res):
            raise RuntimeError(self.failure(res)["error"])
        inputs = res.get("responseData", {}).get("inputs", [])
        return [{"name": i["inputName"], "kind": i.get("inputKind", "")} for i in inputs]

    def list_transitions(self) -> List[Dict[str, Any]]:
        res = self.request("GetSceneTransitionList")
        if not _request_ok(res):
            raise RuntimeError(self.failure(res)["error"])
        return [{"name": t["transitionName"]} for t in res.get("responseData", {}).get("transitions", [])]

    def list_filters(self) -> List[Dict[str, Any]]:
        """The filters of every source, as {"name": filter, "scene": source} (Studio filters them by the source chosen)."""
        found: List[Dict[str, Any]] = []
        for source in self.list_inputs():
            res = self.request("GetSourceFilterList", {"sourceName": source["name"]})
            if not _request_ok(res):
                raise RuntimeError(self.failure(res)["error"])
            for item in res.get("responseData", {}).get("filters", []):
                found.append({"name": item.get("filterName", ""), "scene": source["name"]})
        return found

    def list_scene_items(self) -> List[Dict[str, Any]]:
        """Every source of every scene, as {"name": source, "scene": scene}: what 'show or hide a source' needs."""
        items: List[Dict[str, Any]] = []
        for scene in self.list_scenes():
            res = self.request("GetSceneItemList", {"sceneName": scene})
            if not _request_ok(res):
                raise RuntimeError(self.failure(res)["error"])
            for item in res.get("responseData", {}).get("sceneItems", []):
                items.append({"name": item.get("sourceName", ""), "scene": scene})
        return items

    # --- Actions ---

    def execute_obs_action(self, target: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run one OBS action from a worker thread."""
        extra = extra or {}
        cmd = (target or "").lower().strip()
        call, failure = self.request, self.failure

        try:
            if cmd in ("record_toggle", "toggle_record", "record"):
                res = call("ToggleRecord")
                if not _request_ok(res):
                    return failure(res)
                active = res.get("responseData", {}).get("outputActive", False)
                self.is_recording = active
                return {"success": True, "action": "obs_record_toggle", "outputActive": active, "active": active}

            elif cmd in ("record_pause", "pause_record"):
                res = call("ToggleRecordPause")
                return {"success": True, "action": "obs_record_pause", "data": res} if _request_ok(res) else failure(res)

            elif cmd in ("stream_toggle", "toggle_stream", "stream"):
                res = call("ToggleStream")
                if not _request_ok(res):
                    return failure(res)
                active = res.get("responseData", {}).get("outputActive", False)
                self.is_streaming = active
                return {"success": True, "action": "obs_stream_toggle", "outputActive": active, "active": active}

            elif cmd.startswith("scene_"):
                scene_name = extra.get("scene_name") or cmd.replace("scene_", "")
                res = call("SetCurrentProgramScene", {"sceneName": scene_name})
                if not _request_ok(res):
                    return failure(res)
                return {"success": True, "action": "obs_set_scene", "scene": scene_name}

            elif cmd in ("next_scene", "prev_scene"):
                scenes_res = call("GetSceneList")
                if not _request_ok(scenes_res):
                    return failure(scenes_res)
                scenes = scenes_res.get("responseData", {}).get("scenes", [])
                curr = scenes_res.get("responseData", {}).get("currentProgramSceneName", "")
                if not scenes:
                    return {"success": False, "error": "OBS no tiene escenas"}
                names = [s.get("sceneName") for s in scenes]
                idx = names.index(curr) if curr in names else 0
                next_idx = (idx + 1) % len(names) if cmd == "next_scene" else (idx - 1) % len(names)
                res = call("SetCurrentProgramScene", {"sceneName": names[next_idx]})
                if not _request_ok(res):
                    return failure(res)
                return {"success": True, "action": "obs_scene", "scene": names[next_idx]}

            elif cmd in ("mute_mic", "toggle_mute_mic"):
                mic_name = extra.get("source_name", "Mic/Aux")
                res = call("ToggleInputMute", {"inputName": mic_name})
                if not _request_ok(res):
                    return failure(res)
                muted = res.get("responseData", {}).get("inputMuted")
                result = {"success": True, "action": "obs_mute_mic", "data": res}
                if muted is not None:
                    result.update({"muted": bool(muted), "active": bool(muted)})
                return result

            elif cmd in ("record_start", "record_stop", "stream_start", "stream_stop"):
                kind = "Record" if cmd.startswith("record") else "Stream"
                starting = cmd.endswith("start")
                res = call(("Start" if starting else "Stop") + kind)
                if not _request_ok(res):
                    return failure(res)
                if kind == "Record":
                    self.is_recording = starting
                else:
                    self.is_streaming = starting
                return {"success": True, "action": f"obs_{cmd}", "active": starting}

            elif cmd == "studio_mode_toggle":
                state = call("GetStudioModeEnabled")
                if not _request_ok(state):
                    return failure(state)
                enabled = not state.get("responseData", {}).get("studioModeEnabled", False)
                res = call("SetStudioModeEnabled", {"studioModeEnabled": enabled})
                return {"success": True, "action": "obs_studio_mode", "active": enabled} if _request_ok(res) else failure(res)

            elif cmd == "studio_transition":
                res = call("TriggerStudioModeTransition")
                return {"success": True, "action": "obs_studio_transition"} if _request_ok(res) else failure(res)

            elif cmd == "preview_scene":
                res = call("SetCurrentPreviewScene", {"sceneName": extra.get("scene_name", "")})
                return {"success": True, "action": "obs_preview_scene", "scene": extra.get("scene_name")} if _request_ok(res) else failure(res)

            elif cmd == "set_transition":
                res = call("SetCurrentSceneTransition", {"transitionName": extra.get("transition_name", "")})
                return {"success": True, "action": "obs_set_transition", "transition": extra.get("transition_name")} if _request_ok(res) else failure(res)

            elif cmd in ("replay_toggle", "virtualcam_toggle"):
                res = call("ToggleReplayBuffer" if cmd == "replay_toggle" else "ToggleVirtualCam")
                if not _request_ok(res):
                    return failure(res)
                active = bool(res.get("responseData", {}).get("outputActive", False))
                return {"success": True, "action": f"obs_{cmd}", "active": active}

            elif cmd == "replay_save":
                res = call("SaveReplayBuffer")
                return {"success": True, "action": "obs_replay_save"} if _request_ok(res) else failure(res)

            elif cmd == "record_chapter":
                res = call("CreateRecordChapter")  # OBS 30.2 or newer, recording in Hybrid MP4
                return {"success": True, "action": "obs_record_chapter"} if _request_ok(res) else failure(res)

            elif cmd == "record_split":
                res = call("SplitRecordFile")  # OBS 30.2 or newer
                return {"success": True, "action": "obs_record_split"} if _request_ok(res) else failure(res)

            elif cmd == "source_toggle":
                scene, source = extra.get("scene_name", ""), extra.get("source_name", "")
                found = call("GetSceneItemId", {"sceneName": scene, "sourceName": source})
                if not _request_ok(found):
                    return failure(found)
                item_id = found.get("responseData", {}).get("sceneItemId")
                current = call("GetSceneItemEnabled", {"sceneName": scene, "sceneItemId": item_id})
                if not _request_ok(current):
                    return failure(current)
                visible = not current.get("responseData", {}).get("sceneItemEnabled", False)
                res = call("SetSceneItemEnabled", {"sceneName": scene, "sceneItemId": item_id, "sceneItemEnabled": visible})
                return {"success": True, "action": "obs_source_toggle", "active": visible} if _request_ok(res) else failure(res)

            elif cmd == "input_mute":
                res = call("ToggleInputMute", {"inputName": extra.get("source_name", "")})
                if not _request_ok(res):
                    return failure(res)
                muted = bool(res.get("responseData", {}).get("inputMuted", False))
                return {"success": True, "action": "obs_input_mute", "muted": muted, "active": muted}

            elif cmd == "hotkey":
                res = call("TriggerHotkeyByName", {"hotkeyName": extra.get("hotkey_name", "")})
                return {"success": True, "action": "obs_hotkey"} if _request_ok(res) else failure(res)

            elif cmd == "filter_toggle":
                source, name = extra.get("source_name", ""), extra.get("filter_name", "")
                current = call("GetSourceFilter", {"sourceName": source, "filterName": name})
                if not _request_ok(current):
                    return failure(current)
                enabled = not current.get("responseData", {}).get("filterEnabled", False)
                res = call("SetSourceFilterEnabled", {"sourceName": source, "filterName": name, "filterEnabled": enabled})
                return {"success": True, "action": "obs_filter_toggle", "active": enabled} if _request_ok(res) else failure(res)

            elif cmd in ("input_volume_up", "input_volume_down"):
                source = extra.get("source_name", "")
                current = call("GetInputVolume", {"inputName": source})
                if not _request_ok(current):
                    return failure(current)
                db = float(current.get("responseData", {}).get("inputVolumeDb", 0.0))
                db = max(-100.0, min(26.0, db + (3.0 if cmd.endswith("up") else -3.0)))  # 3 dB a press, inside OBS's own range
                res = call("SetInputVolume", {"inputName": source, "inputVolumeDb": db})
                return {"success": True, "action": f"obs_{cmd}", "db": db} if _request_ok(res) else failure(res)

            elif cmd == "source_refresh":
                res = call("PressInputPropertiesButton", {"inputName": extra.get("source_name", ""), "propertyName": "refreshnocache"})
                return {"success": True, "action": "obs_source_refresh"} if _request_ok(res) else failure(res)

            return {"success": False, "error": f"Acción OBS desconocida: {cmd}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


obs_client = OBSClient()
