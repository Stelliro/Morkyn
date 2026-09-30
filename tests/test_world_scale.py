"""The world grid is 16,383 cells. Cities are clumps with an internal grid, not a stored planet."""

import os
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from app.db import init_db
from app.tile_world import generate_scaled_world, get_map, spatial_contract, walk_steps
from app.world_scale import (
    CITY_CELL_MAX,
    CITY_FINE_MAX,
    CITY_SPAN_MAX,
    WORLD_SIDE,
    _connected,
    build_city,
    build_world,
    choose_box,
    clump_shape_ok,
    layout_districts,
    min_city_thickness,
    population_of,
    rim_gap_budget,
    roll_large_city_count,
    shops_for_density,
    theme_key,
    tiles_in_cell,
)


def _post_apoc():
    return {"id": "ash_plain", "age": "post_collapse", "environment": "volcanic"}


class WorldScaleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="morkyn-world-scale-")
        root = Path(self._tmp.name)
        self._saved = {key: os.environ.get(key) for key in (
            "AI_RPG_DB",
            "AI_RPG_CAMPAIGN_SLOTS",
            "AI_RPG_MODEL_TRACE_DIR",
            "AI_RPG_HISTORY_SUMMARY",
            "AI_RPG_SOURCE_INDEX",
            "AI_RPG_CONSOLIDATED_FACTS",
        )}
        os.environ["AI_RPG_DB"] = str(root / "world.db")
        os.environ["AI_RPG_CAMPAIGN_SLOTS"] = str(root / "slots")
        os.environ["AI_RPG_MODEL_TRACE_DIR"] = str(root / "traces")
        os.environ["AI_RPG_HISTORY_SUMMARY"] = str(root / "history.jsonl")
        os.environ["AI_RPG_SOURCE_INDEX"] = str(root / "source")
        os.environ["AI_RPG_CONSOLIDATED_FACTS"] = str(root / "facts.jsonl")

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def test_shop_count_follows_the_tens(self):
        rng = random.Random(1)
        for _ in range(30):
            self.assertEqual(shops_for_density(50, rng), 5)
            self.assertEqual(shops_for_density(0.50, rng), 5)
        extras = 0
        trials = 400
        roll = random.Random(2)
        for _ in range(trials):
            count = shops_for_density(58, roll)
            self.assertIn(count, (5, 6))
            extras += count - 5
        self.assertGreater(extras, 250)
        self.assertLess(extras, 380)
        slim = random.Random(3)
        ones = sum(shops_for_density(51, slim) - 5 for _ in range(400))
        self.assertGreater(ones, 15)
        self.assertLess(ones, 80)

    def test_sparse_theme_rolls_zero_one_or_two_large_cities(self):
        counts = Counter(
            roll_large_city_count(8, "post_collapse", random.Random(seed))
            for seed in range(240)
        )
        self.assertTrue(set(counts) <= {0, 1, 2})
        self.assertGreater(counts[0], 140)
        self.assertGreater(counts[1], 10)
        self.assertLess(counts[2], counts[1])

    def test_clump_keeps_its_center_and_is_not_a_filled_square(self):
        from app.world_scale import grow_connected

        holes = 0
        for seed in range(12):
            cells = grow_connected(random.Random(seed), 9, 9)
            self.assertIn((4, 4), cells)
            self.assertTrue(_connected(cells))
            self.assertLessEqual(len(cells), 81)
            if len(cells) < 81:
                holes += 1
        self.assertEqual(holes, 12)
        skinny = grow_connected(random.Random(4), 2, 8)
        self.assertIn((1, 4), skinny)
        self.assertTrue(_connected(skinny))
        self.assertLess(len(skinny), 16)
        self.assertTrue(clump_shape_ok(skinny, 2, 8))

    def test_a_city_cannot_be_a_line_or_a_solid_block(self):
        from app.world_scale import grow_connected

        for width, height in ((4, 4), (5, 3), (2, 8), (3, 7), (6, 6), (9, 9), (8, 3)):
            for seed in range(16):
                cells = grow_connected(random.Random(seed), width, height)
                self.assertTrue(
                    clump_shape_ok(cells, width, height),
                    f"{width}x{height} seed {seed} footprint {len(cells)}",
                )
                self.assertIn((width // 2, height // 2), cells)
                self.assertLess(len(cells), width * height)
        self.assertEqual(min_city_thickness(1), 1)
        self.assertEqual(min_city_thickness(5), 2)
        self.assertEqual(min_city_thickness(9), 3)
        self.assertEqual(rim_gap_budget(4, 4), 2)
        self.assertEqual(rim_gap_budget(9, 9), 4)
        self.assertEqual(grow_connected(random.Random(1), 1, 1), {(0, 0)})
        for seed in range(30):
            rng = random.Random(seed)
            for large, target in ((False, 400), (True, 900)):
                box_w, box_h, single = choose_box(
                    rng, large=large, max_ordinary=6, target_fine=target,
                )
                if single is not None:
                    self.assertEqual((box_w, box_h), (1, 1))
                    continue
                long_side = max(box_w, box_h)
                self.assertGreaterEqual(min(box_w, box_h), min_city_thickness(long_side))
                self.assertLessEqual(long_side, CITY_SPAN_MAX)
                self.assertLessEqual(long_side, 9)

    def test_a_city_past_one_cell_uses_more_grids(self):
        box = choose_box(random.Random(1), large=False, max_ordinary=6, target_fine=200)
        self.assertIsNone(box[2])
        self.assertGreater(max(box[0], box[1]), 1)
        single = choose_box(random.Random(1), large=False, max_ordinary=6, target_fine=64)
        self.assertEqual(single, (1, 1, 64))

    def test_city_clump_districts_and_permissions(self):
        city = build_city(
            random.Random(7),
            origin=(10, 20),
            box_w=2,
            box_h=8,
            single_side=None,
            slavery=True,
            city_id="C9",
        )
        cells = {(item["x"], item["y"]) for item in city["cells"]}
        self.assertIn((city["x"], city["y"]), cells)
        self.assertTrue(_connected(cells))
        self.assertEqual(city["span"], [2, 8])
        self.assertLessEqual(max(city["span"]), CITY_SPAN_MAX)
        self.assertLessEqual(city["fine_span"], CITY_FINE_MAX)
        self.assertLessEqual(city["peak_density"], 92)
        center = next(item for item in city["cells"] if item["x"] == city["x"] and item["y"] == city["y"])
        self.assertEqual(center["side"], CITY_CELL_MAX)
        self.assertTrue(all(item["side"] <= CITY_CELL_MAX for item in city["cells"]))
        self.assertTrue(all(item["side"] < CITY_CELL_MAX for item in city["cells"] if item is not center))
        self.assertEqual(center["density"], city["peak_density"])
        self.assertEqual(center["density"], max(item["density"] for item in city["cells"]))
        self.assertTrue(all(item["density"] < center["density"] for item in city["cells"] if item is not center))
        kinds = {item["type"] for item in center["districts"]}
        self.assertTrue({"residential", "shopping", "food", "government", "military", "black_market"} <= kinds)
        government = next(item for item in center["districts"] if item["type"] == "government")
        military = next(item for item in center["districts"] if item["type"] == "military")
        self.assertTrue(government["requires_entry"])
        self.assertTrue(military["requires_entry"])
        self.assertGreaterEqual(government["tile_count"], 80)
        self.assertTrue(government["entrances"])
        market = next(item for item in center["districts"] if item["type"] == "black_market")
        self.assertTrue({"black_market", "weapons", "food", "drugs", "slavery"} <= set(market["permissions"]))
        housing = next(item for item in center["districts"] if item["type"] == "residential")
        self.assertEqual(housing["label"], "housing")
        shop = next(item for item in center["districts"] if item["type"] == "shopping")
        self.assertIn(shop["shop_count"], {shop["density"] // 10, shop["density"] // 10 + 1})
        named = tiles_in_cell(center)
        self.assertEqual(len(named), CITY_CELL_MAX * CITY_CELL_MAX)
        self.assertTrue(all(tile["name"] and tile["type"] for tile in named))

    def test_future_black_market_has_no_slave_trade(self):
        districts = layout_districts(
            random.Random(5), side=64, seed=5, cell_density_value=40, slavery=False,
        )
        market = next(item for item in districts if item["type"] == "black_market")
        self.assertIn("drugs", market["permissions"])
        self.assertNotIn("slavery", market["permissions"])

    def test_full_metropolis_is_in_the_hundreds_of_millions(self):
        cells = [{"side": 128, "density": 90} for _ in range(81)]
        self.assertGreaterEqual(population_of(cells), 100_000_000)

    def test_world_is_the_14_bit_grid_and_cities_do_not_overlap(self):
        world = build_world(_post_apoc(), 11, density_percent=8)
        self.assertEqual(world["width"], WORLD_SIDE)
        self.assertEqual(world["height"], WORLD_SIDE)
        self.assertEqual(world["density_percent"], 8)
        self.assertEqual(world["density_source"], "given")
        self.assertLessEqual(world["stats"]["large_city_count"], 2)
        seen = set()
        for city in world["cities"]:
            self.assertLessEqual(max(city["span"]), CITY_SPAN_MAX)
            self.assertLessEqual(city["fine_span"], CITY_FINE_MAX)
            footprint = {(item["x"], item["y"]) for item in city["cells"]}
            self.assertIn((city["x"], city["y"]), footprint)
            self.assertTrue(_connected(footprint))
            local = {tuple(item["local"]) for item in city["cells"]}
            span_w, span_h = city["span"]
            self.assertTrue(clump_shape_ok(local, span_w, span_h))
            self.assertTrue(seen.isdisjoint(footprint))
            seen.update(footprint)
        self.assertEqual(theme_key(_post_apoc()), "post_collapse")
        contract = spatial_contract(world)
        self.assertEqual(contract["width"], WORLD_SIDE)
        self.assertIn("128", contract["rule"])
        self.assertIn("9 by 9", contract["rule"])
        self.assertIn("not a one-cell-wide line", contract["rule"])
        report = walk_steps(world, "east", 4, save=False)
        self.assertLessEqual(report["steps_taken"], 4)
        self.assertIn(f"{report['from'][0]},{report['from'][1]}", world["visited"])

    def test_generate_roundtrip_keeps_cities_and_does_not_store_the_grid(self):
        init_db()
        made = generate_scaled_world(preset_id="ash_plain", seed=11, density_percent=8)
        self.assertEqual(made["width"], WORLD_SIDE)
        self.assertEqual(made["tiles"], [])
        self.assertLessEqual(made["preview"]["width"], 65)
        self.assertEqual(len(made["preview"]["tiles"]), made["preview"]["width"] * made["preview"]["height"])
        loaded = get_map(made["id"])
        self.assertEqual(loaded["scale"], "world")
        self.assertEqual(loaded["tiles"], [])
        self.assertEqual(len(loaded["cities"]), len(made["cities"]))
        self.assertEqual(loaded["cities"][0]["name"], made["cities"][0]["name"])
        before = (loaded["player"]["x"], loaded["player"]["y"])
        walk_steps(loaded, "north", 1, save=True)
        again = get_map(made["id"])
        self.assertEqual(len(again["cities"]), len(made["cities"]))
        self.assertIn(f"{before[0]},{before[1]}", again["visited"])
