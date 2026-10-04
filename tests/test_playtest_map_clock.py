"""
Playtest #18 and #19, game 2 ("Eldoria's Edge").

#18: pacing held world_day 1 and world_minute 507 (08:27), but the only clock
in the play UI sat in the "This place" card under the map, so the player saw
no time at all. The engine now names the part of the day, and the Scene
header carries "Day 1 · 08:27 · morning".

#19: the player stood in Ashcrown, a three-tile city whose tiles each hold
an internal ward grid, and the map could only show the world lens. The map
now has a World / Settlement switch backed by GET /api/tiles/map/settlement,
which draws a known settlement's grid and nothing the player has not seen.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-map-clock-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import main  # noqa: E402
from app.db import connect, init_db  # noqa: E402
from app.tile_world import _save_map_payload, generate_scaled_world, get_map, remember_place, settlement_view  # noqa: E402
from app.world import format_world_time, get_world_time, part_of_day  # noqa: E402
from app.world_scale import cell_raster, tiles_in_cell  # noqa: E402

STATIC = ROOT / "static"


class WorldClockTests(unittest.TestCase):
    def test_game2_clock_reads_morning(self):
        wt = format_world_time(1, 507)
        self.assertEqual((wt["day"], wt["hour"], wt["minute_of_hour"]), (1, 8, 27))
        self.assertEqual(wt["part_of_day"], "morning")
        self.assertEqual(wt["label"], "Day 1 · 08:27")

    def test_part_of_day_bands(self):
        expected = {0: "night", 4: "night", 5: "morning", 11: "morning", 12: "afternoon",
                    16: "afternoon", 17: "evening", 20: "evening", 21: "night", 23: "night"}
        for hour, word in expected.items():
            with self.subTest(hour=hour):
                self.assertEqual(part_of_day(hour), word)

    def test_stored_clock_carries_the_word(self):
        init_db()
        with connect() as conn:
            for key, value in (("world_day", "1"), ("world_minute", "507"), ("world_epoch_label", "frontier dark fantasy")):
                conn.execute(
                    "INSERT INTO pacing (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            conn.commit()
            wt = get_world_time(conn)
        self.assertEqual(wt["part_of_day"], "morning")
        self.assertEqual(wt["label"], "frontier dark fantasy · Day 1 · 08:27")

    def test_scene_header_shows_the_clock(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        header = html.split('id="chatColumn"', 1)[1].split('class="sceneScroll"', 1)[0]
        self.assertIn('id="sceneClock"', header)
        update = js.split("function updateWorldTimeLine(", 1)[1].split("\nfunction ", 1)[0]
        self.assertIn("sceneClock.textContent = formatSceneClock(wt)", update)
        # The no-clock guard must not return before the header is painted.
        self.assertLess(update.index("sceneClock"), update.index("if (!worldTimeLine) return"))


class SettlementViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        generate_scaled_world(preset_id="ash_plain", seed=4, density_percent=20, notice_percent=0)

    def _chart(self):
        chart = get_map(None)
        self.assertEqual(chart["scale"], "world")
        return chart

    def _here_city(self, chart):
        px, py = int(chart["player"]["x"]), int(chart["player"]["y"])
        for city in chart["cities"]:
            if any(int(c["x"]) == px and int(c["y"]) == py for c in city["cells"]):
                return city
        self.fail("generated world did not start the player in a city")

    def test_raster_is_the_ward_grid(self):
        city = self._here_city(self._chart())
        cell = min(city["cells"], key=lambda c: int(c["side"]))
        side = int(cell["side"])
        names = [d.get("name") for d in cell["districts"]]
        full = cell_raster(cell, side)
        for tile in tiles_in_cell(cell):
            self.assertEqual(names[full[tile["y"]][tile["x"]]], tile["name"])
        small = cell_raster(cell, 8)
        self.assertEqual((len(small), len(small[0])), (min(8, side), min(8, side)))

    def test_route_draws_the_city_you_stand_in(self):
        chart = self._chart()
        city = self._here_city(chart)
        visited_before = list(chart["visited"])
        out = main.api_tile_settlement()
        self.assertTrue(out["available"])
        self.assertEqual(out["selected"], city["id"])
        self.assertEqual(out["here"], city["id"])
        self.assertIn(city["id"], [s["id"] for s in out["settlements"]])
        drawn = out["settlement"]
        self.assertEqual(len(drawn["cells"]), len(city["cells"]))
        here = [c for c in drawn["cells"] if c["here"]]
        self.assertEqual(len(here), 1)
        self.assertTrue(here[0]["known"])
        self.assertEqual(len(here[0]["raster"]), here[0]["res"])
        self.assertTrue(here[0]["districts"])
        self.assertIsNotNone(drawn["player"])
        # Looking is read-only.
        self.assertEqual(get_map(None)["visited"], visited_before)

    def test_unseen_tiles_are_outline_only(self):
        chart = self._chart()
        city = self._here_city(chart)
        px, py = int(chart["player"]["x"]), int(chart["player"]["y"])
        chart["visited"] = [f"{px},{py}"]
        chart["revealed"] = []
        out = settlement_view(chart)
        for cell in out["settlement"]["cells"]:
            with self.subTest(cell=(cell["x"], cell["y"])):
                if cell["here"]:
                    self.assertIn("raster", cell)
                else:
                    self.assertFalse(cell["known"])
                    self.assertNotIn("raster", cell)
                    self.assertNotIn("districts", cell)
        self.assertEqual(out["settlement"]["known_cells"], 1)
        self.assertEqual(len(out["settlement"]["cells"]), len(city["cells"]))

    def test_unknown_settlement_cannot_be_asked_for(self):
        chart = self._chart()
        here = self._here_city(chart)
        other = next(c for c in chart["cities"] if c["id"] != here["id"])
        chart["knowledge"] = {"settlements": [], "danger": [], "notes": [], "sources": []}
        out = settlement_view(chart, city_id=other["id"])
        self.assertNotIn(other["id"], [s["id"] for s in out["settlements"]])
        self.assertEqual(out["selected"], here["id"])
        # Told of it, it can be drawn: listed, but every tile is outline.
        chart["knowledge"]["settlements"] = [other["id"]]
        told = settlement_view(chart, city_id=other["id"])
        self.assertEqual(told["selected"], other["id"])
        self.assertIsNone(told["settlement"]["player"])
        self.assertTrue(all(not c["known"] for c in told["settlement"]["cells"]))

    def test_known_places_and_venues_sit_on_their_tile(self):
        chart = self._chart()
        px, py = int(chart["player"]["x"]), int(chart["player"]["y"])
        with connect() as conn:
            root = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()[0]
            conn.execute("UPDATE locations SET name = ?, code = 'L1' WHERE id = ?", ("Eldoria's Edge", root))
            conn.execute(
                "INSERT INTO locations (code, name, parent_id, kind, open_minute, close_minute) VALUES ('L2', ?, ?, 'apothecary', 480, 1080)",
                ("Herb Shop", root),
            )
            conn.execute(
                "INSERT INTO locations (code, name, parent_id) VALUES ('L3', 'Far Road', 0)",
            )
            conn.commit()
        # A pinned outdoor place elsewhere in the world is not this city's.
        remember_place(chart, code="L3", name="Far Road", x=1, y=1)
        _save_map_payload(chart)
        out = main.api_tile_settlement()
        places = out["settlement"]["places"]
        self.assertEqual([p["name"] for p in places], ["Eldoria's Edge"])
        self.assertEqual((places[0]["x"], places[0]["y"]), (px, py))
        self.assertTrue(places[0]["here"])
        venue = places[0]["venues"][0]
        self.assertEqual((venue["name"], venue["label"]), ("Herb Shop", "apothecary"))
        self.assertIn("08:00-18:00", venue["hours"])


class SettlementViewUiTests(unittest.TestCase):
    def test_map_panel_has_the_switch(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="mapViewBar"', html)
        self.assertIn('data-map-view="world"', html)
        self.assertIn('data-map-view="settlement"', html)
        self.assertIn('id="settlementCanvas"', html)
        js = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertIn("/api/tiles/map/settlement", js)


if __name__ == "__main__":
    unittest.main()
