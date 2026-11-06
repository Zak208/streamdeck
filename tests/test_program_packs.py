import json
import os
import re
import unittest

import support  # noqa: F401  (isolates the data directory)
from server.action_catalog import validate_hotkey
from server.paths import STATIC_DIR
from server.program_packs import ALL_CATEGORIES, PACKS, by_id, catalog

HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
PACK_ID = re.compile(r"[a-z0-9_]+")


class ProgramPacksTests(unittest.TestCase):
    def test_enough_programs_and_unique_ids(self):
        self.assertGreaterEqual(len(PACKS), 22)
        ids = [pack["id"] for pack in PACKS]
        self.assertEqual(len(ids), len(set(ids)))
        for pack_id in ids:
            self.assertRegex(pack_id, PACK_ID)
        self.assertEqual(set(by_id()), set(ids))

    def test_required_programs_are_present(self):
        expected = {
            "chrome", "edge", "firefox", "youtube", "gmail", "gdocs", "gsheets", "gdrive", "vlc", "resolve",
            "premiere", "aftereffects", "audacity", "photoshop", "illustrator", "figma", "blender", "word",
            "excel", "powerpoint", "outlook", "onenote", "vscode", "zoom", "teams", "slack", "notion",
            "windows", "editing",
        }
        self.assertTrue(expected <= set(by_id()), expected - set(by_id()))

    def test_program_fields(self):
        icons = {name[:-4] for name in os.listdir(os.path.join(STATIC_DIR, "icons")) if name.endswith(".svg")}
        for pack in PACKS:
            self.assertEqual(
                set(pack), {"id", "name", "category", "exe", "color", "icon", "actions"}, pack["id"]
            )
            self.assertTrue(pack["name"].strip(), pack["id"])
            self.assertIn(pack["category"], ALL_CATEGORIES, pack["id"])
            self.assertIsInstance(pack["exe"], str)
            self.assertTrue(pack["exe"] == "" or pack["exe"].lower().endswith(".exe"), pack["id"])
            self.assertRegex(pack["color"], HEX_COLOR, pack["id"])
            self.assertNotEqual(pack["color"].upper(), "#FFFFFF", pack["id"])
            self.assertIn(pack["icon"], icons, pack["id"])

    def test_categories(self):
        self.assertEqual(len(ALL_CATEGORIES), len(set(ALL_CATEGORIES)))
        self.assertEqual(len(ALL_CATEGORIES), 8)

    def test_actions(self):
        icons = {name[:-4] for name in os.listdir(os.path.join(STATIC_DIR, "icons")) if name.endswith(".svg")}
        for pack in PACKS:
            actions = pack["actions"]
            self.assertTrue(8 <= len(actions) <= 16, f"{pack['id']}: {len(actions)} acciones")
            action_ids = [action["id"] for action in actions]
            self.assertEqual(len(action_ids), len(set(action_ids)), pack["id"])
            for action in actions:
                where = f"{pack['id']}/{action.get('id')}"
                self.assertEqual(set(action), {"id", "label", "sub", "keys", "icon"}, where)
                self.assertTrue(action["id"].strip(), where)
                self.assertTrue(action["label"].strip(), where)
                self.assertLessEqual(len(action["label"]), 32, where)
                self.assertTrue(action["sub"].strip(), where)
                self.assertLessEqual(len(action["sub"]), 36, where)
                self.assertIn(action["icon"], icons, where)

    def test_hotkeys_are_valid_and_normalized(self):
        for pack in PACKS:
            for action in pack["actions"]:
                where = f"{pack['id']}/{action['id']}"
                keys = action["keys"]
                normalized = validate_hotkey(keys, require_modifier=False)
                self.assertEqual(normalized, keys, where)

    def test_no_duplicate_hotkeys_inside_a_program(self):
        for pack in PACKS:
            keys = [action["keys"] for action in pack["actions"]]
            self.assertEqual(len(keys), len(set(keys)), pack["id"])

    def test_catalog_is_a_deep_json_copy(self):
        first = catalog()
        self.assertEqual(first, PACKS)
        json.dumps(first)
        first[0]["actions"][0]["label"] = "cambiado"
        first[0]["name"] = "cambiado"
        self.assertNotEqual(PACKS[0]["name"], "cambiado")
        self.assertNotEqual(PACKS[0]["actions"][0]["label"], "cambiado")
        self.assertNotEqual(catalog()[0]["name"], "cambiado")


if __name__ == "__main__":
    unittest.main()
