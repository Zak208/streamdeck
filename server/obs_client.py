import asyncio
import json
import threading
from typing import Dict, Any, Optional

OBS_WS_HOST = "127.0.0.1"
OBS_WS_PORT = 4455

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
            return {"requestStatus": {"result": False, "comment": str(e)}}

    def execute_obs_action(self, target: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
        extra = extra or {}
        cmd = (target or "").lower().strip()

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            if cmd in ("record_toggle", "toggle_record", "record"):
                res = loop.run_until_complete(self._send_request("ToggleRecord"))
                active = res.get("responseData", {}).get("outputActive", False)
                self.is_recording = active
                return {"success": True, "action": "obs_record_toggle", "outputActive": active}

            elif cmd in ("record_pause", "pause_record"):
                res = loop.run_until_complete(self._send_request("ToggleRecordPause"))
                return {"success": True, "action": "obs_record_pause", "data": res}

            elif cmd in ("stream_toggle", "toggle_stream", "stream"):
                res = loop.run_until_complete(self._send_request("ToggleStream"))
                active = res.get("responseData", {}).get("outputActive", False)
                self.is_streaming = active
                return {"success": True, "action": "obs_stream_toggle", "outputActive": active}

            elif cmd.startswith("scene_"):
                scene_name = extra.get("scene_name") or cmd.replace("scene_", "")
                res = loop.run_until_complete(self._send_request("SetCurrentProgramScene", {"sceneName": scene_name}))
                return {"success": True, "action": "obs_set_scene", "scene": scene_name}

            elif cmd in ("next_scene", "prev_scene"):
                # Get scene list and advance
                scenes_res = loop.run_until_complete(self._send_request("GetSceneList"))
                scenes = scenes_res.get("responseData", {}).get("scenes", [])
                curr = scenes_res.get("responseData", {}).get("currentProgramSceneName", "")
                if scenes:
                    names = [s.get("sceneName") for s in scenes]
                    idx = names.index(curr) if curr in names else 0
                    next_idx = (idx + 1) % len(names) if cmd == "next_scene" else (idx - 1) % len(names)
                    loop.run_until_complete(self._send_request("SetCurrentProgramScene", {"sceneName": names[next_idx]}))
                    return {"success": True, "action": "obs_scene", "scene": names[next_idx]}

            elif cmd in ("mute_mic", "toggle_mute_mic"):
                mic_name = extra.get("source_name", "Mic/Aux")
                res = loop.run_until_complete(self._send_request("ToggleInputMute", {"inputName": mic_name}))
                return {"success": True, "action": "obs_mute_mic", "data": res}

            return {"success": False, "error": f"Acción OBS desconocida: {cmd}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            loop.close()

obs_client = OBSClient()

