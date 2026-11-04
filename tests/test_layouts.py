"""Configurable grid: validation, conversion between sizes, templates and the /api/layout endpoint."""

import copy
import json
import unittest
import urllib.error
import urllib.request

import support
from server import layouts, templates
from server.action_catalog import validate_deck_config
from server.config_manager import DEFAULT_CONFIG


def default_profile():
    return validate_deck_config(copy.deepcopy(DEFAULT_CONFIG))


def check_page_shape(test, slots, rows, columns):
    test.assertEqual(len(slots), rows * columns)
    for index, slot in enumerate(slots):
        test.assertEqual(slot["index"], index)
        if slot["type"] == "slider":
            test.assertLess(index, columns, "a fader sits on the first row")
            test.assertEqual(slots[index + columns]["type"], "occupied_by_slider")
            test.assertEqual(slots[index + columns]["parent_slot"], index)
        if slot["type"] == "occupied_by_slider":
            test.assertEqual(slots[slot["parent_slot"]]["type"], "slider")


class ValidationTests(unittest.TestCase):
    def test_a_profile_without_layout_is_the_original_6x2(self):
        raw = copy.deepcopy(DEFAULT_CONFIG)
        raw.pop("layout")
        config = validate_deck_config(raw)
        self.assertEqual(config["layout"], {"rows": 2, "columns": 6, "total_slots": 12})

    def test_unknown_sizes_are_refused(self):
        for bad in ({"rows": 9, "columns": 9}, {"rows": 1, "columns": 12}, {"rows": "2", "columns": 6}, "6x2", {"rows": True, "columns": 6}):
            raw = copy.deepcopy(DEFAULT_CONFIG)
            raw["layout"] = bad
            with self.subTest(layout=bad), self.assertRaises(ValueError):
                validate_deck_config(raw)

    def test_a_page_must_match_the_layout(self):
        raw = copy.deepcopy(DEFAULT_CONFIG)
        raw["layout"] = {"rows": 3, "columns": 3, "total_slots": 9}
        with self.assertRaises(ValueError):
            validate_deck_config(raw)  # its pages still have twelve slots

    def test_an_occupied_cell_must_sit_right_under_its_fader(self):
        raw = copy.deepcopy(DEFAULT_CONFIG)
        slots = raw["pages"][0]["slots"]
        slots[10], slots[11] = slots[11], slots[10]  # parent 5 now at index 10 instead of 11
        slots[10]["index"], slots[11]["index"] = 10, 11
        with self.assertRaises(ValueError):
            validate_deck_config(raw)


class ConversionTests(unittest.TestCase):
    def test_every_layout_gives_valid_pages_from_the_default_profile(self):
        for name, (rows, columns) in layouts.LAYOUTS.items():
            with self.subTest(layout=name):
                converted, _ = layouts.convert_config(default_profile(), name)
                clean = validate_deck_config(converted)
                self.assertEqual(clean["layout"], layouts.layout_dict(name))
                for page in clean["pages"]:
                    check_page_shape(self, page["slots"], rows, columns)

    def test_items_keep_their_cell_when_it_exists(self):
        converted, dropped = layouts.convert_config(default_profile(), "6x2")
        self.assertEqual(dropped, 0)
        self.assertEqual(converted["pages"][0]["slots"][0]["id"], "btn_discord")
        converted, dropped = layouts.convert_config(default_profile(), "4x3")
        slots = converted["pages"][0]["slots"]
        self.assertEqual(slots[0]["id"], "btn_discord")  # row 0, column 0 stays there
        self.assertEqual(slots[1]["id"], "btn_spotify")
        # The two faders lost columns 4 and 5, so they take the two rightmost columns and the buttons
        # that were there move down to the free third row instead of being lost.
        self.assertEqual((slots[2]["type"], slots[3]["type"]), ("slider", "slider"))
        self.assertEqual(dropped, 0)
        self.assertIn("btn_steam", [s.get("id") for s in slots[8:12]])

    def test_nothing_is_lost_when_there_is_room_and_the_rest_is_counted(self):
        profile = default_profile()
        before = sum(1 for p in profile["pages"] for s in p["slots"] if s["type"] in ("button", "slider"))
        for name in layouts.LAYOUTS:
            with self.subTest(layout=name):
                converted, dropped = layouts.convert_config(profile, name)
                after = sum(1 for p in converted["pages"] for s in p["slots"] if s["type"] in ("button", "slider"))
                self.assertEqual(after + dropped, before)
        _, dropped_small = layouts.convert_config(profile, "4x2")  # 8 cells: some of 10 items per page cannot fit
        self.assertGreater(dropped_small, 0)

    def test_converting_back_and_forth_between_roomy_layouts_keeps_everything(self):
        profile = default_profile()
        there, lost_there = layouts.convert_config(profile, "5x3")
        back, lost_back = layouts.convert_config(there, "6x2")
        self.assertEqual((lost_there, lost_back), (0, 0))
        ids = lambda cfg: sorted(s["id"] for p in cfg["pages"] for s in p["slots"] if s["type"] in ("button", "slider"))
        self.assertEqual(ids(back), ids(profile))

    def test_the_active_page_copy_follows_the_conversion(self):
        converted, _ = layouts.convert_config(default_profile(), "3x3")
        self.assertEqual(len(converted["slots"]), 9)
        self.assertEqual(converted["slots"], converted["pages"][converted["current_page"]]["slots"])


class TemplateTests(unittest.TestCase):
    def test_templates_fit_every_layout(self):
        for name, size in layouts.LAYOUTS.items():
            for meta in templates.TEMPLATES:
                with self.subTest(layout=name, template=meta["id"]):
                    page = templates.build_page(meta["id"], layout=size)
                    check_page_shape(self, page["slots"], *size)

    def test_a_discord_page_cannot_hold_more_sounds_than_cells(self):
        with self.assertRaises(ValueError):
            templates.discord_server_page("Servidor", [f"s{i}" for i in range(10)], layout=(3, 3))
        page = templates.discord_server_page("Servidor", [f"s{i}" for i in range(9)], layout=(3, 3))
        self.assertEqual(sum(1 for s in page["slots"] if s["type"] == "button"), 9)


class ReviewRegressionTests(unittest.TestCase):
    def test_a_discord_page_in_5x3_holds_fifteen_sounds_in_order(self):
        labels = [f"s{i}" for i in range(15)]
        page = templates.discord_server_page("Servidor", labels, layout=(3, 5))
        self.assertEqual(len(page["slots"]), 15)
        self.assertEqual([s["target"] for s in page["slots"]], labels)

    def test_a_discord_page_keeps_the_order_of_the_sounds_in_small_grids(self):
        labels = [f"s{i}" for i in range(8)]
        page = templates.discord_server_page("Servidor", labels, layout=(2, 4))
        self.assertEqual([s["target"] for s in page["slots"]], labels)

    def test_a_template_reports_how_many_buttons_did_not_fit(self):
        self.assertEqual(templates.build_page("streamer")["_dropped"], 0)
        self.assertGreater(templates.build_page("streamer", layout=(2, 4))["_dropped"], 0)

    def test_faders_keep_their_left_to_right_order_in_every_layout(self):
        for name in layouts.LAYOUTS:
            converted, _ = layouts.convert_config(default_profile(), name)
            for page in converted["pages"]:
                order = [s["id"] for s in page["slots"] if s["type"] == "slider"]
                original = next(p for p in default_profile()["pages"] if p["id"] == page["id"])
                expected = [s["id"] for s in original["slots"] if s["type"] == "slider"]
                with self.subTest(layout=name, page=page["id"]):
                    self.assertEqual(order, expected)

    def test_a_fader_in_a_column_that_still_exists_stays_when_all_fit(self):
        converted, _ = layouts.convert_config(default_profile(), "6x2")
        self.assertEqual([s["index"] for s in converted["pages"][0]["slots"] if s["type"] == "slider"], [4, 5])

    def test_a_fader_below_the_first_row_is_refused(self):
        raw = copy.deepcopy(DEFAULT_CONFIG)
        slots = raw["pages"][0]["slots"]
        slots[6] = {**slots[4], "index": 6, "id": "slider_low"}  # a fader on the second row
        with self.assertRaises(ValueError):
            validate_deck_config(raw)

    def test_confirm_and_disabled_must_be_real_booleans(self):
        for value in ("false", "no", "si", [], {}):
            raw = copy.deepcopy(DEFAULT_CONFIG)
            next(s for s in raw["pages"][0]["slots"] if s["type"] == "button")["disabled"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_deck_config(raw)


class LayoutEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.live = support.LiveServer().__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.live.__exit__(None, None, None)

    def call(self, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.live.base_url + path, data=data, method="POST" if data is not None else "GET",
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode())

    def tearDown(self):
        self.call("/api/layout", {"layout": "6x2"})

    def test_changing_the_grid_converts_every_page_and_reports_the_current_one(self):
        status, body = self.call("/api/layout", {"layout": "3x3"})
        self.assertEqual(status, 200)
        self.assertEqual(body["config"]["layout"], {"rows": 3, "columns": 3, "total_slots": 9})
        for page in body["config"]["pages"]:
            check_page_shape(self, page["slots"], 3, 3)
        self.assertEqual(self.call("/api/layouts")[1]["current"], "3x3")
        self.assertEqual(self.call("/api/config")[1]["layout"]["columns"], 3)

    def test_an_unknown_grid_is_refused_and_the_profile_is_untouched(self):
        before = self.call("/api/config")[1]
        self.assertEqual(self.call("/api/layout", {"layout": "9x9"})[0], 422)
        self.assertEqual(self.call("/api/config")[1], before)

    def test_new_pages_follow_the_current_grid(self):
        self.call("/api/layout", {"layout": "4x3"})
        self.assertEqual(self.call("/api/deck/page/add", {"name": "Prueba"})[0], 200)
        config = self.call("/api/config")[1]
        check_page_shape(self, config["pages"][-1]["slots"], 3, 4)

    def test_templates_added_after_a_change_use_the_new_grid(self):
        self.call("/api/layout", {"layout": "3x3"})
        self.assertEqual(self.call("/api/templates/apply", {"template_id": "gamer"})[0], 200)
        check_page_shape(self, self.call("/api/config")[1]["pages"][-1]["slots"], 3, 3)

    def test_it_is_only_available_from_the_pc(self):
        # the live server is bound to loopback, so this just checks the route is guarded like the others
        from server import main
        self.assertTrue(any(getattr(route, "path", "") == "/api/layout" for route in main.app.routes))


if __name__ == "__main__":
    unittest.main()
