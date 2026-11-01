import asyncio
import json
import threading
from typing import Dict, Any, Optional

OBS_WS_HOST = "127.0.0.1"
OBS_WS_PORT = 4455

OBS_UNREACHABLE = "OBS no responde. Ábrelo y activa el servidor WebSocket en Herramientas > Ajustes del servidor WebSocket."


def _request_ok(response: Dict[str, Any]) -> bool:
    return bool(response.get("requestStatus", {}).get("result"))


class OBSClient:
    """Lightweight asynchronous OBS Studio WebSocket v5 client."""

    def __init__(self, host: str = OBS_WS_HOST, port: int = OBS_WS_PORT):
        self.host = host
        self.port = port
        self.is_recording = False
        self.is_streaming = False
        self.current_scene = ""
        self._lock = threading.Lock()

    async def _send_request(self, request_type: str, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        import websockets
        uri = f"ws://{self.host}:{self.port}"
        try:
            async with websockets.connect(uri, open_timeout=1.0, close_timeout=1.0) as ws:
                # Receive Hello (op 0)
                hello_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                hello = json.loads(hello_raw)

                # Send Identify (op 1)
                identify = {
                    "op": 1,
                    "d": {
                        "rpcVersion": 1
                    }
                }
                await ws.send(json.dumps(identify))

                # Receive Identified (op 2)
                identified_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)

                # Send Request (op 6)
                req_id = f"req_{request_type}_{int(asyncio.get_event_loop().time() * 1000)}"
                req = {
                    "op": 6,
                    "d": {
                        "requestType": request_type,
                        "requestId": req_id,
                        "requestData": request_data or {}
                    }
                }
                await ws.send(json.dumps(req))

                # Receive Response (op 7)
                resp_raw = await asyncio.wait_for(ws.recv(), timeout=1.5)
                resp = json.loads(resp_raw)
                return resp.get("d", {})
        except Exception as e:
            return {"requestStatus": {"result": False, "comment": str(e)}, "unreachable": True}

    def execute_obs_action(self, target: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
        """Run one OBS action. Blocking: call it from a worker thread, never from the event loop."""
        extra = extra or {}
        cmd = (target or "").lower().strip()

        def call(request_type: str, request_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            return asyncio.run(self._send_request(request_type, request_data))

        def failure(res: Dict[str, Any]) -> Dict[str, Any]:
            if res.get("unreachable"):
                return {"success": False, "error": OBS_UNREACHABLE}
            return {"success": False, "error": res.get("requestStatus", {}).get("comment") or "OBS rechazó la acción"}

        try:
            if cmd in ("record_toggle", "toggle_record", "record"):
                res = call("ToggleRecord")
                if not _request_ok(res):
                    return failure(res)
                active = res.get("responseData", {}).get("outputActive", False)
                self.is_recording = active
                return {"success": True, "action": "obs_record_toggle", "outputActive": active}

            elif cmd in ("record_pause", "pause_record"):
                res = call("ToggleRecordPause")
                return {"success": True, "action": "obs_record_pause", "data": res} if _request_ok(res) else failure(res)

            elif cmd in ("stream_toggle", "toggle_stream", "stream"):
                res = call("ToggleStream")
                if not _request_ok(res):
                    return failure(res)
                active = res.get("responseData", {}).get("outputActive", False)
                self.is_streaming = active
                return {"success": True, "action": "obs_stream_toggle", "outputActive": active}

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
                return {"success": True, "action": "obs_mute_mic", "data": res} if _request_ok(res) else failure(res)

            return {"success": False, "error": f"Acción OBS desconocida: {cmd}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

obs_client = OBSClient()

