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
    slots = []
    # 2 rows x 8 columns = 16 slots
    presets = [
        # Row 0 (0 to 7)
        {"index": 0, "type": "button", "id": "btn_discord", "label": "Discord", "sublabel": "Voz / Chat", "icon": "", "image": "/static/icons/discord.svg", "color": "#5865f2", "action_type": "preset_app", "target": "discord"},
        {"index": 1, "type": "button", "id": "btn_spotify", "label": "Spotify", "sublabel": "Música", "icon": "", "image": "/static/icons/spotify.svg", "color": "#1db954", "action_type": "preset_app", "target": "spotify"},
        {"index": 2, "type": "button", "id": "btn_obs", "label": "OBS Studio", "sublabel": "Directo", "icon": "", "image": "/static/icons/obs.svg", "color": "#302e31", "action_type": "preset_app", "target": "obs"},
        {"index": 3, "type": "button", "id": "btn_steam", "label": "Steam", "sublabel": "Juegos", "icon": "", "image": "/static/icons/steam.svg", "color": "#171a21", "action_type": "preset_app", "target": "steam"},
        {"index": 4, "type": "button", "id": "btn_chrome", "label": "Chrome", "sublabel": "Navegador", "icon": "", "image": "/static/icons/chrome.svg", "color": "#ea4335", "action_type": "preset_app", "target": "chrome"},
        {"index": 5, "type": "button", "id": "btn_riot", "label": "Valorant", "sublabel": "Riot", "icon": "⚔️", "image": "", "color": "#d13639", "action_type": "preset_app", "target": "valorant"},
        {"index": 6, "type": "slider", "id": "slider_master", "label": "Master", "slider_type": "master", "target_app": None, "color": "#38bdf8"},
        {"index": 7, "type": "slider", "id": "slider_app", "label": "App", "slider_type": "app_dynamic", "target_app": "Spotify.exe", "color": "#a855f7"},

        # Row 1 (8 to 15)
        {"index": 8, "type": "button", "id": "btn_play", "label": "Play/Pausa", "sublabel": "Audio", "icon": "⏯️", "image": "", "color": "#22c55e", "action_type": "media", "target": "play_pause"},
        {"index": 9, "type": "button", "id": "btn_next", "label": "Siguiente", "sublabel": "Pista", "icon": "⏭️", "image": "", "color": "#38bdf8", "action_type": "media", "target": "next"},
        {"index": 10, "type": "button", "id": "btn_prev", "label": "Anterior", "sublabel": "Pista", "icon": "⏮️", "image": "", "color": "#38bdf8", "action_type": "media", "target": "prev"},
        {"index": 11, "type": "button", "id": "btn_mute", "label": "Mute", "sublabel": "Silenciar", "icon": "🔇", "image": "", "color": "#ef4444", "action_type": "media", "target": "mute"},
        {"index": 12, "type": "button", "id": "btn_calc", "label": "Calculadora", "sublabel": "Utilidad", "icon": "🧮", "image": "", "color": "#f59e0b", "action_type": "launch", "target": "calc"},
        {"index": 13, "type": "button", "id": "btn_notes", "label": "Notas", "sublabel": "Editor", "icon": "📝", "image": "", "color": "#06b6d4", "action_type": "launch", "target": "notepad"},
        {"index": 14, "type": "button", "id": "btn_macro", "label": "Modo Stream", "sublabel": "Macro", "icon": "🚀", "image": "", "color": "#a855f7", "action_type": "multi", "target": "stream", "extra": {"actions": [{"action_type": "preset_app", "target": "obs", "delay_ms": 200}, {"action_type": "preset_app", "target": "discord", "delay_ms": 200}, {"action_type": "sound", "target": "asterisk"}]}},
        {"index": 15, "type": "button", "id": "btn_yt", "label": "YouTube", "sublabel": "Web", "icon": "📺", "image": "", "color": "#e11d48", "action_type": "url", "target": "https://www.youtube.com"}
    ]

    preset_dict = {p["index"]: p for p in presets}
    for i in range(16):
        if i in preset_dict:
            slots.append(preset_dict[i])
        else:
            slots.append({
                "index": i,
                "type": "empty",
                "id": f"slot_{i}",
                "label": "Vacío"
            })
    return slots

DEFAULT_CONFIG: Dict[str, Any] = {
    "deck_name": "StreamDesk Pro Elite",
    "layout": {
        "rows": 2,
        "columns": 8,
        "total_slots": 16
    },
    "slots": generate_default_slots()
}

class ConfigManager:
    """Loads, saves, and updates Stream Deck 2x8 grid layout."""

    def __init__(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "slots" in data and len(data.get("slots", [])) == 16:
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
