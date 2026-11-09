import os
import tempfile
import unittest
from unittest import mock

from server import actions, app_icons
from server.action_catalog import SAFE_APP_TARGET
from server.system_scanner import GENERIC_ICON, SystemScanner, guess_category, resolve_app_icon

PF = "{6D809377-6AF0-444B-8957-A3773F02200E}"  # the code Windows gives "Program Files"

START_MENU = [
    {"name": "Spotify", "appid": "Spotify.exe"},
    {"name": "Calculadora", "appid": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"},
    {"name": "7-Zip File Manager", "appid": PF + r"\7-Zip\7zFM.exe"},
    {"name": "7-Zip Help", "appid": PF + r"\7-Zip\7-zip.chm"},
    {"name": "AIDA64 Extreme en la Web", "appid": PF + r"\FinalWire\aida64.url"},
    {"name": "Incredibuild Support", "appid": "http://support.incredibuild.com"},
    {"name": "Unins Tool", "appid": PF + r"\Thing\unins000.exe"},
    {"name": "Inno Setup Documentation", "appid": r"C:\Users\x\Inno\ISetup.chm"},
    {"name": "Database directory (MariaDB)", "appid": PF + r"\MariaDB\data"},
    {"name": "Sea of Thieves", "appid": "steam://rungameid/1172620"},
    {"name": "Link raro", "appid": "javascript://alert(1)"},
    {"name": "Obsidian", "appid": "md.obsidian"},
    {"name": "Obsidian", "appid": "md.obsidian.copy"},          # the same name twice: one card
    {"name": "Mi Programa", "appid": "Vendor.App.One"},
    {"name": "Mi Programa 2", "appid": "Vendor.App.Two"},
]


def scan(entries=START_MENU, curated=()):
    with mock.patch.object(SystemScanner, "_start_apps", return_value=entries):
        return SystemScanner._scan_start_menu(list(curated))


class StartMenuScanTests(unittest.TestCase):
    def setUp(self):
        self.apps = {app["name"]: app for app in scan()}

    def test_programs_are_listed_and_noise_is_not(self):
        for kept in ("Calculadora", "7-Zip File Manager", "Sea of Thieves", "Obsidian", "Mi Programa"):
            self.assertIn(kept, self.apps)
        for dropped in ("7-Zip Help", "AIDA64 Extreme en la Web", "Incredibuild Support", "Unins Tool",
                        "Inno Setup Documentation", "Database directory (MariaDB)", "Link raro"):
            self.assertNotIn(dropped, self.apps)

    def test_the_same_name_is_listed_once(self):
        self.assertEqual(sum(1 for app in scan() if app["name"] == "Obsidian"), 1)

    def test_every_id_is_valid_for_a_button_and_unique(self):
        ids = [app["id"] for app in scan()]
        self.assertEqual(len(ids), len(set(ids)))
        for app_id in ids:
            self.assertRegex(app_id, SAFE_APP_TARGET)

    def test_ids_do_not_change_between_scans(self):
        self.assertEqual([a["id"] for a in scan()], [a["id"] for a in scan(list(reversed(START_MENU)))])

    def test_a_steam_game_goes_to_games_and_a_store_app_opens_by_its_id(self):
        self.assertEqual(self.apps["Sea of Thieves"]["category"], "Juegos")
        self.assertEqual(self.apps["Sea of Thieves"]["launch"], {"type": "steam", "url": "steam://rungameid/1172620"})
        self.assertEqual(self.apps["Calculadora"]["launch"]["type"], "appsfolder")

    def test_a_folder_code_is_turned_into_the_real_path(self):
        path = self.apps["7-Zip File Manager"]["path"]
        self.assertTrue(path.lower().endswith(r"7-zip\7zfm.exe"), path)
        self.assertNotIn("{", path)

    def test_a_well_known_program_keeps_its_own_entry(self):
        curated = [{"id": "spotify", "name": "Spotify", "exe_names": ["spotify.exe"]}]
        self.assertNotIn("Spotify", {app["name"] for app in scan(curated=curated)})
        curated = [{"id": "epicgames", "name": "Epic Games", "exe_names": ["epicgameslauncher.exe"]}]
        self.assertEqual(scan([{"name": "Epic Games Launcher", "appid": "C:\\Epic\\EpicGamesLauncher.exe"}], curated), [])

    def test_the_browser_is_told_nothing_about_paths_or_launch_details(self):
        fake = [{"id": "a", "name": "A", "icon": GENERIC_ICON, "color": "#f8c700", "category": "Juegos",
                 "exe_name": "a.exe", "path": r"C:\a.exe", "launch": {"type": "file", "path": r"C:\a.exe"}}]
        with mock.patch.object(SystemScanner, "get_detected_apps", return_value=fake):
            public = SystemScanner.public_apps()
        self.assertEqual(set(public[0]), {"id", "name", "icon", "color", "category", "exe_name"})


class CategoryAndIconTests(unittest.TestCase):
    def test_short_words_match_whole_words_only(self):
        self.assertNotEqual(guess_category("Obsidian"), "Vídeo y foto")
        self.assertEqual(guess_category("OBS Studio"), "Vídeo y foto")
        self.assertNotEqual(guess_category("DB Browser (SQLite)"), "Navegadores")
        self.assertEqual(guess_category("Google Chrome"), "Navegadores")

    def test_an_unknown_program_gets_no_guessed_icon(self):
        self.assertEqual(resolve_app_icon("amd software", fuzzy=False), GENERIC_ICON)  # "war" in "software" is not a game
        self.assertEqual(resolve_app_icon("obsidian", fuzzy=False), GENERIC_ICON)
        self.assertEqual(resolve_app_icon("obs studio", fuzzy=False), "/static/icons/obs.svg")


class LaunchStartMenuTests(unittest.TestCase):
    def launch(self, launch, path="x"):
        detected = [{"id": "demo", "path": path, "launch": launch}]
        with mock.patch.object(actions.system_scanner, "get_detected_apps", return_value=detected), \
                mock.patch.object(actions.os, "startfile", create=True) as startfile:
            result = actions.launch_smart_app("demo")
        return result, startfile

    def test_a_start_menu_app_opens_by_its_windows_id(self):
        ok, startfile = self.launch({"type": "appsfolder", "appid": "Microsoft.WindowsCalculator_8wekyb3d8bbwe!App"})
        self.assertTrue(ok)
        startfile.assert_called_once_with("shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App")

    def test_a_steam_game_opens_only_with_a_game_address(self):
        ok, startfile = self.launch({"type": "steam", "url": "steam://rungameid/730"})
        self.assertTrue(ok)
        startfile.assert_called_once_with("steam://rungameid/730")
        ok, startfile = self.launch({"type": "steam", "url": "steam://run/730/ -evil"})
        self.assertFalse(ok)
        startfile.assert_not_called()


class AppIconTests(unittest.TestCase):
    def test_the_lettered_icon_is_a_safe_svg(self):
        svg = app_icons.letter_icon_svg('<b>"Zeta"')
        self.assertIn(">B<", svg)
        self.assertNotIn("<b>", svg)
        self.assertIn("#f8c700", svg)

    def test_an_app_without_its_own_icon_gets_a_file_in_uploads(self):
        app = {"id": "mi_app", "name": "Mi App", "icon": GENERIC_ICON, "icon_source": ""}
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(app_icons.system_scanner, "find", return_value=app):
            url = app_icons.icon_for_app("mi_app", folder)
            self.assertEqual(url, "/uploads/appicon_mi_app.svg")
            self.assertTrue(os.path.isfile(os.path.join(folder, "appicon_mi_app.svg")))

    def test_the_real_icon_is_used_when_windows_has_one(self):
        app = {"id": "mi_app", "name": "Mi App", "icon": GENERIC_ICON, "icon_source": r"C:\x\mi.exe"}

        def fake_extract(source, target):
            with open(target, "wb") as handle:
                handle.write(b"png")
            return True

        with tempfile.TemporaryDirectory() as folder, mock.patch.object(app_icons.system_scanner, "find", return_value=app), \
                mock.patch.object(app_icons, "_extract_real_icon", side_effect=fake_extract):
            self.assertEqual(app_icons.icon_for_app("mi_app", folder), "/uploads/appicon_mi_app.png")

    def test_a_drawn_icon_of_a_known_app_is_kept_and_an_unknown_app_is_refused(self):
        app = {"id": "discord", "name": "Discord", "icon": "/static/icons/discord.svg"}
        with mock.patch.object(app_icons.system_scanner, "find", return_value=app):
            self.assertEqual(app_icons.icon_for_app("discord", "unused"), "/static/icons/discord.svg")
        with mock.patch.object(app_icons.system_scanner, "find", return_value=None):
            self.assertIsNone(app_icons.icon_for_app("no_existe", "unused"))


if __name__ == "__main__":
    unittest.main()
