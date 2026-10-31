import os
import sys
import json
from typing import Dict, Any, List

# If running frozen (PyInstaller), store config in %APPDATA%\StreamDesk or app dir
if getattr(sys, 'frozen', False):
    USER_DATA = os.path.expandvars(r"%APPDATA%\StreamDesk")
else:
    USER_DATA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_DIR = os.path.join(USER_DATA, "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "deck_config.json")

def generate_default_slots() -> List[Dict[str, Any]]:
    # 2 rows x 6 columns = 12 slots total
    # Columns 0..3: 8 Action Buttons (2 rows x 4 cols)
    # Columns 4..5: 2 Vertical Faders spanning both rows (row_span: 2)
    return [
        # Column 0
        {
            "index": 0,
            "type": "button",
            "id": "btn_discord",
            "label": "Discord",
            "sublabel": "Voz",
            "icon": "",
            "image": "/static/icons/discord.svg",
            "color": "#5865f2",
            "action_type": "preset_app",
            "target": "discord"
        },
        # Column 1
        {
            "index": 1,
            "type": "button",
            "id": "btn_spotify",
            "label": "Spotify",
            "sublabel": "Música",
            "icon": "",
            "image": "/static/icons/spotify.svg",
            "color": "#1db954",
            "action_type": "preset_app",
            "target": "spotify"
        },
        # Column 2
        {
            "index": 2,
            "type": "button",
            "id": "btn_obs",
            "label": "OBS Studio",
            "sublabel": "Directo",
            "icon": "",
            "image": "/static/icons/obs.svg",
            "color": "#302e31",
            "action_type": "preset_app",
            "target": "obs"
        },
        # Column 3
        {
            "index": 3,
            "type": "button",
            "id": "btn_steam",
            "label": "Steam",
            "sublabel": "Juegos",
            "icon": "",
            "image": "/static/icons/steam.svg",
            "color": "#171a21",
            "action_type": "preset_app",
            "target": "steam"
        },
        # Column 4 (Vertical Slider Master - spans 2 vertical spaces)
        {
            "index": 4,
            "type": "slider",
            "id": "slider_master",
            "label": "Master",
            "sublabel": "PC",
            "slider_type": "master",
            "target_app": None,
            "color": "#0ea5e9",
            "row_span": 2,
            "icon": "/static/icons/volume_up.svg",
            "image": "/static/icons/volume_up.svg"
        },
        # Column 5 (Vertical Slider App - spans 2 vertical spaces)
        {
            "index": 5,
            "type": "slider",
            "id": "slider_app",
            "label": "Spotify",
            "sublabel": "App",
            "slider_type": "app_dynamic",
            "target_app": "Spotify.exe",
            "color": "#a855f7",
            "row_span": 2,
            "icon": "/static/icons/spotify.svg",
            "image": "/static/icons/spotify.svg"
        },
        # Row 1, Column 0
        {
            "index": 6,
            "type": "button",
            "id": "btn_play",
            "label": "Play/Pausa",
            "sublabel": "Media",
            "icon": "",
            "image": "/static/icons/play_pause.svg",
            "color": "#22c55e",
            "action_type": "media",
            "target": "play_pause"
        },
        # Row 1, Column 1
        {
            "index": 7,
            "type": "button",
            "id": "btn_next",
            "label": "Siguiente",
            "sublabel": "Pista",
            "icon": "",
            "image": "/static/icons/next.svg",
            "color": "#38bdf8",
            "action_type": "media",
            "target": "next"
        },
        # Row 1, Column 2
        {
            "index": 8,
            "type": "button",
            "id": "btn_prev",
            "label": "Anterior",
            "sublabel": "Pista",
            "icon": "",
            "image": "/static/icons/prev.svg",
            "color": "#38bdf8",
            "action_type": "media",
            "target": "prev"
        },
        # Row 1, Column 3
        {
            "index": 9,
            "type": "button",
            "id": "btn_mute",
            "label": "Mute",
            "sublabel": "Audio",
            "icon": "",
            "image": "/static/icons/mute.svg",
            "color": "#ef4444",
            "action_type": "media",
            "target": "mute"
        },
        # Row 1, Column 4 (Occupied by vertical slider in column 4)
        {
            "index": 10,
            "type": "occupied_by_slider",
            "id": "slot_10",
            "label": "Ocupado por Master",
            "parent_slot": 4
        },
        # Row 1, Column 5 (Occupied by vertical slider in column 5)
        {
            "index": 11,
            "type": "occupied_by_slider",
            "id": "slot_11",
            "label": "Ocupado por App",
            "parent_slot": 5
        }
    ]

DEFAULT_CONFIG: Dict[str, Any] = {
    "deck_name": "StreamDesk Pro Elite",
    "layout": {
        "rows": 2,
        "columns": 6,
        "total_slots": 12
    },
    "slots": generate_default_slots()
}

class ConfigManager:
    """Loads, saves, and updates Stream Deck 6x2 grid layout."""

    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "slots" in data and len(data.get("slots", [])) == 12:
                        return data
            except Exception as e:
                print(f"Error loading deck_config.json: {e}")
        self.save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    def save_config(self, new_config: Dict[str, Any]) -> bool:
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=2, ensure_ascii=False)
            self.config = new_config
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get_config(self) -> Dict[str, Any]:
        return self.config

config_manager = ConfigManager()
