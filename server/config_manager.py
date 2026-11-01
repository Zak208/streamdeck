import os
import sys
import json
from typing import Dict, Any, List
from server.action_catalog import validate_deck_config
from server.paths import CONFIG_DIR

CONFIG_FILE = os.path.join(CONFIG_DIR, "deck_config.json")

def generate_default_pages() -> List[Dict[str, Any]]:
    # Page 1: Principal (Apps & Faders)
    page_main_slots = [
        # Col 0
        {"index": 0, "type": "button", "id": "btn_discord", "label": "Discord", "sublabel": "Voz", "icon": "", "image": "/static/icons/discord.svg", "color": "#5865f2", "action_type": "preset_app", "target": "discord"},
        # Col 1
        {"index": 1, "type": "button", "id": "btn_spotify", "label": "Spotify", "sublabel": "Música", "icon": "", "image": "/static/icons/spotify.svg", "color": "#1db954", "action_type": "preset_app", "target": "spotify"},
        # Col 2
        {"index": 2, "type": "button", "id": "btn_obs", "label": "OBS Studio", "sublabel": "Directo", "icon": "", "image": "/static/icons/obs.svg", "color": "#302e31", "action_type": "preset_app", "target": "obs"},
        # Col 3
        {"index": 3, "type": "button", "id": "btn_steam", "label": "Steam", "sublabel": "Juegos", "icon": "", "image": "/static/icons/steam.svg", "color": "#171a21", "action_type": "preset_app", "target": "steam"},
        # Col 4 (Vertical Slider Master - 2 vertical spaces)
        {"index": 4, "type": "slider", "id": "slider_master", "label": "Master", "sublabel": "PC", "slider_type": "master", "target_app": None, "color": "#0ea5e9", "row_span": 2, "icon": "/static/icons/volume_up.svg", "image": "/static/icons/volume_up.svg"},
        # Col 5 (Vertical Slider App - 2 vertical spaces)
        {"index": 5, "type": "slider", "id": "slider_app", "label": "Spotify", "sublabel": "App", "slider_type": "app_dynamic", "target_app": "Spotify.exe", "color": "#a855f7", "row_span": 2, "icon": "/static/icons/spotify.svg", "image": "/static/icons/spotify.svg"},
        # Row 1, Col 0
        {"index": 6, "type": "button", "id": "btn_play", "label": "Play/Pausa", "sublabel": "Media", "icon": "", "image": "/static/icons/play_pause.svg", "color": "#22c55e", "action_type": "media", "target": "play_pause"},
        # Row 1, Col 1
        {"index": 7, "type": "button", "id": "btn_next", "label": "Siguiente", "sublabel": "Pista", "icon": "", "image": "/static/icons/next.svg", "color": "#38bdf8", "action_type": "media", "target": "next"},
        # Row 1, Col 2
        {"index": 8, "type": "button", "id": "btn_prev", "label": "Anterior", "sublabel": "Pista", "icon": "", "image": "/static/icons/prev.svg", "color": "#38bdf8", "action_type": "media", "target": "prev"},
        # Row 1, Col 3
        {"index": 9, "type": "button", "id": "btn_mute", "label": "Mute", "sublabel": "Audio", "icon": "", "image": "/static/icons/mute.svg", "color": "#ef4444", "action_type": "media", "target": "mute"},
        # Row 1, Col 4 (Occupied by Master Slider)
        {"index": 10, "type": "occupied_by_slider", "id": "slot_10", "parent_slot": 4},
        # Row 1, Col 5 (Occupied by App Slider)
        {"index": 11, "type": "occupied_by_slider", "id": "slot_11", "parent_slot": 5}
    ]

    # Page 2: OBS Studio & Streaming
    page_obs_slots = [
        {"index": 0, "type": "button", "id": "btn_obs_rec", "label": "Grabar", "sublabel": "OBS", "icon": "", "image": "/static/icons/video.svg", "color": "#ef4444", "action_type": "obs_action", "target": "record_toggle"},
        {"index": 1, "type": "button", "id": "btn_obs_stream", "label": "Transmitir", "sublabel": "En Vivo", "icon": "", "image": "/static/icons/broadcast.svg", "color": "#8b5cf6", "action_type": "obs_action", "target": "stream_toggle"},
        {"index": 2, "type": "button", "id": "btn_obs_scene1", "label": "Juego", "sublabel": "Escena", "icon": "", "image": "/static/icons/gamepad.svg", "color": "#10b981", "action_type": "obs_action", "target": "scene_juego", "extra": {"scene_name": "Juego"}},
        {"index": 3, "type": "button", "id": "btn_stream_macro", "label": "Setup Live", "sublabel": "Macro", "icon": "", "image": "/static/icons/macro.svg", "color": "#a855f7", "action_type": "multi", "target": "stream", "extra": {"actions": [{"action_type": "preset_app", "target": "obs", "delay_ms": 200}, {"action_type": "preset_app", "target": "discord", "delay_ms": 200}]}},
        {"index": 4, "type": "slider", "id": "slider_master_p2", "label": "Master", "sublabel": "PC", "slider_type": "master", "target_app": None, "color": "#0ea5e9", "row_span": 2, "icon": "/static/icons/volume_up.svg", "image": "/static/icons/volume_up.svg"},
        {"index": 5, "type": "slider", "id": "slider_discord_p2", "label": "Discord", "sublabel": "Voz", "slider_type": "app_dynamic", "target_app": "Discord.exe", "color": "#5865f2", "row_span": 2, "icon": "/static/icons/discord.svg", "image": "/static/icons/discord.svg"},
        {"index": 6, "type": "button", "id": "btn_obs_pause", "label": "Pausa Rec", "sublabel": "OBS", "icon": "", "image": "/static/icons/pause.svg", "color": "#f59e0b", "action_type": "obs_action", "target": "record_pause"},
        {"index": 7, "type": "button", "id": "btn_obs_next_scene", "label": "Escena +", "sublabel": "Siguiente", "icon": "", "image": "/static/icons/next.svg", "color": "#38bdf8", "action_type": "obs_action", "target": "next_scene"},
        {"index": 8, "type": "button", "id": "btn_obs_scene2", "label": "Charla", "sublabel": "Escena", "icon": "", "image": "/static/icons/notes.svg", "color": "#06b6d4", "action_type": "obs_action", "target": "scene_charla", "extra": {"scene_name": "Charla"}},
        {"index": 9, "type": "button", "id": "btn_obs_mute_mic", "label": "Mute Mic", "sublabel": "OBS", "icon": "", "image": "/static/icons/mute.svg", "color": "#ef4444", "action_type": "obs_action", "target": "mute_mic"},
        {"index": 10, "type": "occupied_by_slider", "id": "slot_10_p2", "parent_slot": 4},
        {"index": 11, "type": "occupied_by_slider", "id": "slot_11_p2", "parent_slot": 5}
    ]

    # Page 3: Sistema & Telemetría
    page_system_slots = [
        {"index": 0, "type": "button", "id": "widget_cpu", "label": "CPU", "sublabel": "Carga", "icon": "", "image": "/static/icons/cpu.svg", "color": "#0ea5e9", "action_type": "hardware_monitor", "target": "cpu"},
        {"index": 1, "type": "button", "id": "widget_disk", "label": "SSD C:", "sublabel": "Espacio", "icon": "", "image": "/static/icons/disk.svg", "color": "#10b981", "action_type": "hardware_monitor", "target": "disk"},
        {"index": 2, "type": "button", "id": "btn_calc_p3", "label": "Calc", "sublabel": "Utilidad", "icon": "", "image": "/static/icons/calc.svg", "color": "#f59e0b", "action_type": "launch", "target": "calc"},
        {"index": 3, "type": "button", "id": "btn_chrome_p3", "label": "Chrome", "sublabel": "Web", "icon": "", "image": "/static/icons/chrome.svg", "color": "#ea4335", "action_type": "preset_app", "target": "chrome"},
        {"index": 4, "type": "slider", "id": "slider_master_p3", "label": "Master", "sublabel": "PC", "slider_type": "master", "target_app": None, "color": "#0ea5e9", "row_span": 2, "icon": "/static/icons/volume_up.svg", "image": "/static/icons/volume_up.svg"},
        {"index": 5, "type": "slider", "id": "slider_chrome_p3", "label": "Chrome", "sublabel": "Web", "slider_type": "app_dynamic", "target_app": "chrome.exe", "color": "#ea4335", "row_span": 2, "icon": "/static/icons/chrome.svg", "image": "/static/icons/chrome.svg"},
        {"index": 6, "type": "button", "id": "widget_ram", "label": "RAM", "sublabel": "Memoria", "icon": "", "image": "/static/icons/ram.svg", "color": "#8b5cf6", "action_type": "hardware_monitor", "target": "ram"},
        {"index": 7, "type": "button", "id": "btn_taskmgr", "label": "Tareas", "sublabel": "Monitor", "icon": "", "image": "/static/icons/sliders.svg", "color": "#f59e0b", "action_type": "launch", "target": "taskmgr"},
        {"index": 8, "type": "button", "id": "btn_notes_p3", "label": "Notas", "sublabel": "Editor", "icon": "", "image": "/static/icons/notes.svg", "color": "#06b6d4", "action_type": "launch", "target": "notepad"},
        {"index": 9, "type": "button", "id": "btn_yt_p3", "label": "YouTube", "sublabel": "Vídeo", "icon": "", "image": "/static/icons/youtube.svg", "color": "#e11d48", "action_type": "url", "target": "https://www.youtube.com"},
        {"index": 10, "type": "occupied_by_slider", "id": "slot_10_p3", "parent_slot": 4},
        {"index": 11, "type": "occupied_by_slider", "id": "slot_11_p3", "parent_slot": 5}
    ]

    return [
        {"id": "page_main", "name": "Principal", "slots": page_main_slots},
        {"id": "page_obs", "name": "OBS & Stream", "slots": page_obs_slots},
        {"id": "page_system", "name": "Sistema & PC", "slots": page_system_slots}
    ]

PAGES = generate_default_pages()

DEFAULT_CONFIG: Dict[str, Any] = {
    "schema_version": 2,
    "deck_name": "StreamDesk Pro Elite",
    "layout": {
        "rows": 2,
        "columns": 6,
        "total_slots": 12
    },
    "current_page": 0,
    "pages": PAGES,
    "slots": PAGES[0]["slots"]
}

class ConfigManager:
    """Loads, saves, and updates Stream Deck 6x2 multi-page layout."""

    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.last_error = ""
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # If config has pages structure, normalise it before exposing it
                    # to the mobile client. Profiles are also received over HTTP, so
                    # this is an important security boundary.
                    if "pages" in data and len(data.get("pages", [])) > 0:
                        return validate_deck_config(data)
                    elif "slots" in data and len(data.get("slots", [])) == 12:
                        # Migrate single page to multi-page format
                        migrated = dict(DEFAULT_CONFIG)
                        migrated["pages"][0]["slots"] = data["slots"]
                        migrated["slots"] = data["slots"]
                        migrated = validate_deck_config(migrated)
                        self.save_config(migrated)
                        return migrated
            except Exception as e:
                print(f"Error loading deck_config.json: {e}")
        self.save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    def save_config(self, new_config: Dict[str, Any]) -> bool:
        try:
            new_config = validate_deck_config(new_config)
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=2, ensure_ascii=False)
            self.config = new_config
            self.last_error = ""
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            self.last_error = str(e)
            return False

    def set_active_page(self, page_index: int) -> bool:
        pages = self.config.get("pages", [])
        if 0 <= page_index < len(pages):
            self.config["current_page"] = page_index
            self.config["slots"] = pages[page_index]["slots"]
            self.save_config(self.config)
            return True
        return False

    def get_config(self) -> Dict[str, Any]:
        return self.config

config_manager = ConfigManager()
