import copy
import unittest

import support  # noqa: F401  (isolates the data directory)
from server.action_catalog import normalize_spotify_uri, validate_action, validate_deck_config, validate_hotkey
from server.config_manager import DEFAULT_CONFIG


class ActionCatalogTests(unittest.TestCase):
    def test_normalizes_spotify_share_link(self):
        uri = normalize_spotify_uri("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M?si=test")
        self.assertEqual(uri, "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M")

    def test_validates_discord_global_hotkey(self):
        self.assertEqual(validate_hotkey("control + shift + m"), "CTRL+SHIFT+M")
        action = validate_action("discord_hotkey", "mute", {"hotkey": "CTRL+SHIFT+M"})
        self.assertEqual(action["extra"]["hotkey"], "CTRL+SHIFT+M")

    def test_rejects_shell_actions(self):
        with self.assertRaises(ValueError):
            validate_action("command", "Remove-Item C:\\")

    def test_default_profile_is_valid(self):
        normalized = validate_deck_config(copy.deepcopy(DEFAULT_CONFIG))
        self.assertEqual(normalized["schema_version"], 2)
        self.assertEqual(len(normalized["pages"]), len(DEFAULT_CONFIG["pages"]))
        self.assertEqual(len(normalized["pages"][0]["slots"]), 12)

    def test_rejects_unsafe_profile_action(self):
        unsafe_profile = copy.deepcopy(DEFAULT_CONFIG)
        unsafe_profile["pages"][0]["slots"][0].update({"action_type": "script", "target": "whoami"})
        with self.assertRaises(ValueError):
            validate_deck_config(unsafe_profile)


if __name__ == "__main__":
    unittest.main()
