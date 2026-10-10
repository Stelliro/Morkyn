"""Tests for app/economy.py, the settlement market simulation (TODO n1, built but not wired).

Pure rules first (profile, season, production, multiplier, scarcity, drift), then the writers against a
temporary database, then the leaf and no-foreign-writes checks that keep the module unwired.

Run:  python -m unittest tests.test_economy
"""
from __future__ import annotations

import json
import gc
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-economy-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_CONSOLIDATED_FACTS": str(_TMP / "facts.jsonl"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_IDEA_BANK": str(_TMP / "idea_bank"),
    "AI_RPG_LAUNCHER_PREFS": str(_TMP / "launcher_prefs.json"),
}
os.environ.update(_ENV)

from app import economy  # noqa: E402
from app import tile_world  # noqa: E402
from app import town_grid  # noqa: E402
from app import venues  # noqa: E402
from app import world  # noqa: E402
from app.db import connect, db_path, init_db  # noqa: E402

SEED = 4242

BOARD_TOWN = {"id": "S3", "x": 10, "y": 12, "state": "town", "class": "town", "tile_count": 14,
              "population_band": "medium", "name": "Ashbarrow"}
BOARD_FARM = {"id": "S9", "x": 3, "y": 4, "state": "farm", "class": "farm", "population_band": "tiny",
              "name": "Weir Farm"}
WORLD_CITY = {"id": "C7", "name": "Varnholt", "band": "large_city", "population": 48000, "x": 900, "y": 900}
LIST_ROW_VILLAGE = {"id": "S5", "state": "village", "name": "Hollow", "population_band": "small",
                    "kind": "settlement"}


def setUpModule():
    os.environ.update(_ENV)
    init_db()
    with connect() as conn:
        economy.ensure_schema(conn)


def _fresh_db() -> None:
    path = db_path()
    if path.exists():
        gc.collect()  # Windows will not unlink a db a leaked connection still holds
        path.unlink()
    init_db()
    with connect() as conn:
        economy.ensure_schema(conn)
        # init_db seeds a player row already; the template insert stands for the DBs where it does not.
        conn.execute(
            "INSERT OR IGNORE INTO player (id, name, health, max_health, level, xp, gold, current_location_id) "
            "VALUES (1, 'T', 20, 20, 1, 0, 12, NULL)"
        )
    conn.close()


def _table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    names = [
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    ]
    return {name: int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) for name in names}


def _setting_rows(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM settings")}


def _spring_row(profile: dict, category: str, *, stock: float = economy.EQUILIBRIUM_DAYS) -> dict:
    consumption = economy.consumption_for(profile, category)
    return {
        "settlement_id": profile["settlement_id"],
        "category": category,
        "stock": stock,
        "demand": consumption,
        "production": economy.production_for(profile, category),
        "consumption": consumption,
        "price_mult": 1.0,
        "updated_day": 1,
        "seeded_day": 1,
        "size": profile["size"],
        "type": profile["type"],
        "name": profile["name"],
    }


def _assert_price_multiplier_shape(test: unittest.TestCase, mult: dict) -> None:
    expected = {
        "settlement_id": str, "category": str, "day": int, "mult": float, "supply": float, "demand": float,
        "season": str, "season_mult": float, "scarcity_mult": float, "drift_mult": float,
        "flavour_mult": float, "events": list, "reason": str,
    }
    test.assertEqual(set(mult.keys()), set(expected.keys()))
    for key, kind in expected.items():
        test.assertIsInstance(mult[key], kind, f"{key} should be {kind.__name__}")
    test.assertGreaterEqual(mult["mult"], economy.MULT_MIN)
    test.assertLessEqual(mult["mult"], economy.MULT_MAX)
    test.assertIn(mult["reason"], ("ok", "unknown_settlement", "unknown_category", "disabled"))
    for event in mult["events"]:
        test.assertIsInstance(event, str)


def _assert_settlement_ref_shape(test: unittest.TestCase, ref: dict) -> None:
    expected = {
        "settlement_id": str, "name": str, "size": str, "type": str, "band_raw": str,
        "population_band": str, "population_factor": float, "location_id": int,
    }
    test.assertEqual(set(ref.keys()), set(expected.keys()))
    for key, kind in expected.items():
        test.assertIsInstance(ref[key], kind, f"{key} should be {kind.__name__}")
    test.assertIn(ref["size"], ("hamlet", "village", "town", "city"))
    test.assertIn(ref["type"], economy.SETTLEMENT_TYPES + ("",))
    test.assertIn(ref["population_band"], economy.POPULATION_BANDS)
    test.assertIn(ref["population_factor"], (1.0, 3.0, 10.0, 30.0))


def _assert_event_proposal_shape(test: unittest.TestCase, proposal: dict) -> None:
    test.assertEqual(
        set(proposal.keys()), {"kind", "summary", "trigger", "due_turn", "force", "priority", "payload"}
    )
    test.assertEqual(proposal["kind"], "custom")
    test.assertIsInstance(proposal["summary"], str)
    test.assertTrue(proposal["summary"])
    test.assertTrue(proposal["trigger"].startswith("economy:"))
    test.assertIsNone(proposal["due_turn"])
    test.assertIs(proposal["force"], False)
    test.assertEqual(proposal["priority"], 4)
    test.assertIsInstance(proposal["payload"], dict)
    test.assertIn("economy_event", proposal["payload"])
    test.assertIn("settlement_id", proposal["payload"])


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------


class SettlementProfileTests(unittest.TestCase):
    def test_settlement_profile_from_board_meta_and_world_meta(self):
        board = economy.settlement_profile(BOARD_TOWN)
        _assert_settlement_ref_shape(self, board)
        self.assertEqual(board["settlement_id"], "S3")
        self.assertEqual(board["type"], "town")
        self.assertEqual(board["band_raw"], "medium")
        self.assertEqual(board["population_band"], "medium")
        self.assertEqual(board["size"], "town")
        self.assertEqual(board["population_factor"], 10.0)

        city = economy.settlement_profile(WORLD_CITY)
        _assert_settlement_ref_shape(self, city)
        self.assertEqual(city["settlement_id"], "C7")
        self.assertEqual(city["name"], "Varnholt")
        self.assertEqual(city["type"], "")  # a world city record carries no state word
        self.assertEqual(city["band_raw"], "large_city")
        self.assertEqual(city["population_band"], "large")
        self.assertEqual(city["size"], "city")
        self.assertEqual(city["population_factor"], 30.0)

        with_row = economy.settlement_profile(BOARD_TOWN, {"id": 31, "settlement_size": "city"})
        self.assertEqual(with_row["size"], "city")
        self.assertEqual(with_row["location_id"], 31)
        self.assertEqual(with_row["population_band"], "medium")  # the row changes size only

        ruins = economy.settlement_profile({"id": "L2", "state": "ruins", "population_band": "small"})
        self.assertEqual(ruins["type"], "")
        self.assertEqual(ruins["size"], "village")

        list_row = economy.settlement_profile(LIST_ROW_VILLAGE)
        self.assertEqual(list_row["type"], "village")
        self.assertEqual(list_row["size"], "village")

        typed_only = economy.settlement_profile({"id": "S8", "state": "colony"})
        self.assertEqual(typed_only["population_band"], "large")
        self.assertEqual(typed_only["size"], "city")

    def test_settlement_profile_none_is_village(self):
        ref = economy.settlement_profile(None)
        _assert_settlement_ref_shape(self, ref)
        self.assertEqual(ref["settlement_id"], "")
        self.assertEqual(ref["size"], "village")
        self.assertEqual(ref["type"], "")
        self.assertEqual(ref["band_raw"], "")
        self.assertEqual(ref["population_band"], "small")
        self.assertEqual(ref["population_factor"], 3.0)
        self.assertEqual(ref["location_id"], 0)

    def test_population_factor_table(self):
        self.assertEqual(economy.population_factor("tiny"), 1.0)
        self.assertEqual(economy.population_factor("small"), 3.0)
        self.assertEqual(economy.population_factor("medium"), 10.0)
        self.assertEqual(economy.population_factor("large"), 30.0)
        self.assertEqual(economy.population_factor("enormous"), 3.0)
        self.assertEqual(economy.population_factor(""), 3.0)

    def test_vocabularies_agree_with_existing_code(self):
        # Every ruler-role class is a settlement type; hamlet is a board meta word with no ruler role.
        for word in world._RULER_ROLE_BY_CLASS:
            self.assertIn(word, economy.SETTLEMENT_TYPES, word)
        settlement_words = {s for s in tile_world.SETTLEMENT_STATES if s not in {"ruins", "dungeon", "gate"}}
        self.assertEqual(set(economy.SETTLEMENT_TYPES), settlement_words | {"farm", "hamlet"})
        settlement_states = {s for s in venues.SETTLEMENT_ORDER if s != "wilds"}
        self.assertEqual(set(economy.SIZE_BY_POPULATION.values()), settlement_states)
        for band in economy.WORLD_BAND_WORDS:
            expected = town_grid.settlement_size_for_band(band)
            self.assertEqual(economy.SIZE_BY_POPULATION[economy.BAND_TO_POPULATION[band]], expected, band)
        for state in ("ruins", "dungeon", "gate"):
            self.assertNotIn(state, economy.SETTLEMENT_TYPES)


class SeasonTests(unittest.TestCase):
    def test_season_for_day_cycle_and_year(self):
        day1 = economy.season_for_day(1)
        self.assertEqual(day1["season"], "spring")
        self.assertEqual(day1["index"], 0)
        self.assertEqual(day1["day_in_season"], 1)
        self.assertEqual(day1["progress"], 0.0)
        self.assertEqual(day1["year"], 1)
        self.assertEqual(economy.season_for_day(30)["season"], "spring")
        self.assertEqual(economy.season_for_day(31)["season"], "summer")
        self.assertEqual(economy.season_for_day(61)["season"], "autumn")
        self.assertEqual(economy.season_for_day(91)["season"], "winter")
        day121 = economy.season_for_day(121)
        self.assertEqual(day121["season"], "spring")
        self.assertEqual(day121["year"], 2)
        shifted = economy.season_for_day(1, first_season="winter")
        self.assertEqual(shifted["season"], "winter")
        self.assertEqual(shifted["index"], 3)
        self.assertEqual(economy.season_for_day(31, first_season="winter")["season"], "spring")
        short = economy.season_for_day(8, season_days=7)
        self.assertEqual(short["season"], "summer")
        self.assertEqual(short["day_in_season"], 1)
        with self.assertRaises(ValueError):
            economy.season_for_day(0)
        with self.assertRaises(ValueError):
            economy.season_for_day(5, first_season="monsoon")

    def test_season_effect_winter_food(self):
        self.assertEqual(economy.season_effect("winter", "food"), 1.25)
        self.assertEqual(economy.season_effect("summer", "fuel"), 0.70)
        self.assertEqual(economy.season_effect("spring", "weapons"), 1.0)
        with self.assertRaises(ValueError):
            economy.season_effect("monsoon", "food")
        town = economy.settlement_profile(BOARD_TOWN)
        row = _spring_row(town, "food")
        mult = economy.price_multiplier(
            row, events=[], season=economy.season_for_day(100), day=100, seed=SEED, drift=0.0
        )
        self.assertEqual(mult["season"], "winter")
        self.assertEqual(mult["season_mult"], 1.25)
        self.assertGreater(mult["mult"], 1.25)


class ProductionTests(unittest.TestCase):
    def test_consumption_scales_with_population_factor(self):
        farm = economy.settlement_profile(BOARD_FARM)
        town = economy.settlement_profile(BOARD_TOWN)
        city = economy.settlement_profile(WORLD_CITY)
        self.assertEqual(economy.consumption_for(farm, "food"), 1.0 * 1.00)
        self.assertEqual(economy.consumption_for(town, "food"), 10.0 * 1.00)
        self.assertEqual(economy.consumption_for(city, "food"), 30.0 * 1.00)
        self.assertAlmostEqual(economy.consumption_for(town, "fuel"), 10.0 * 0.60)
        self.assertAlmostEqual(economy.consumption_for(city, "magic"), 30.0 * 0.03)
        with self.assertRaises(ValueError):
            economy.consumption_for(town, "spices")

    def test_production_profile_farm_overproduces_food_city_underproduces(self):
        farm = economy.settlement_profile(BOARD_FARM)
        city = economy.settlement_profile(WORLD_CITY)
        self.assertAlmostEqual(economy.production_for(farm, "food"), economy.consumption_for(farm, "food") * 2.0)
        self.assertAlmostEqual(economy.production_for(city, "food"), economy.consumption_for(city, "food") * 0.6)
        self.assertAlmostEqual(economy.production_for(farm, "armor"), 0.0)
        self.assertAlmostEqual(economy.production_for(city, "luxury"), economy.consumption_for(city, "luxury") * 1.6)
        # misc is on no profile row, so it takes the default share.
        self.assertAlmostEqual(economy.production_for(city, "misc"), economy.consumption_for(city, "misc") * 0.9)
        # An unknown type uses its size row: a city-sized record with no state word reads the city row.
        self.assertEqual(city["type"], "")
        harbor = economy.settlement_profile({"id": "S4", "state": "harbor", "population_band": "medium"})
        self.assertAlmostEqual(economy.production_for(harbor, "transport"), economy.consumption_for(harbor, "transport") * 1.8)
        station = economy.settlement_profile({"id": "S6", "state": "station"})
        self.assertAlmostEqual(economy.production_for(station, "food"), economy.consumption_for(station, "food") * 0.5)

    def test_venue_kinds_add_production(self):
        town = economy.settlement_profile(BOARD_TOWN)
        base = economy.production_for(town, "food")
        with_inn = economy.production_for(town, "food", ["inn"])
        self.assertAlmostEqual(with_inn - base, economy.consumption_for(town, "food") * 0.15)
        two = economy.production_for(town, "food", ["inn", "bakery", "inn", "smithy"])
        self.assertAlmostEqual(two - base, economy.consumption_for(town, "food") * 0.30)
        self.assertAlmostEqual(economy.production_for(town, "armor", ["inn"]), economy.production_for(town, "armor"))

    def test_venue_categories_keys_are_venue_kinds_and_values_are_categories(self):
        self.assertEqual(set(economy.VENUE_CATEGORIES.keys()), set(venues.VENUE_KINDS.keys()))
        for kind, cats in economy.VENUE_CATEGORIES.items():
            self.assertIsInstance(cats, tuple, kind)
            for cat in cats:
                self.assertIn(cat, economy.GOODS_CATEGORIES, f"{kind} sells {cat}")
        self.assertEqual(economy.VENUE_CATEGORIES["inn"], ("lodging", "food", "drink"))
        self.assertEqual(economy.VENUE_CATEGORIES["counting_house"], ())

    def test_rules_tables_cover_every_category(self):
        self.assertEqual(len(economy.GOODS_CATEGORIES), 16)
        self.assertEqual(set(economy.CONSUMPTION_BASE), set(economy.GOODS_CATEGORIES))
        self.assertEqual(economy.CONSUMPTION_BASE["food"], 1.00)
        self.assertEqual(economy.CONSUMPTION_BASE["misc"], 0.20)
        for key, row in economy.PRODUCTION_PROFILE.items():
            self.assertEqual(len(row), 15, key)
            self.assertNotIn("misc", row)
        self.assertEqual(economy.PRODUCTION_PROFILE["town"]["weapons"], 1.0)
        self.assertEqual(economy.PRODUCTION_PROFILE["station"]["knowledge"], 1.4)
        for season in economy.SEASONS:
            self.assertIn(season, economy.SEASON_EFFECTS)
        for kind, spec in economy.SCARCITY_EVENTS.items():
            for cat in spec["categories"]:
                self.assertIn(cat, economy.GOODS_CATEGORIES, kind)
            self.assertIn("{name}", spec["news"])
            self.assertLessEqual(spec["duration"][0], spec["duration"][1])
        self.assertEqual(economy.SCARCITY_EVENTS["blight"]["price_delta"], 0.60)
        self.assertEqual(economy.SCARCITY_EVENTS["glut"]["price_delta"], -0.35)
        self.assertEqual(economy.SCARCITY_EVENTS["war_levy"]["duration"], (10, 30))
        self.assertEqual(economy.IMPORT_PULL, 0.15)
        self.assertEqual(economy.EQUILIBRIUM_DAYS, 5.0)

    def test_initial_rows_cover_categories_and_drop_magic_when_no_magic(self):
        town = economy.settlement_profile(BOARD_TOWN)
        rows = economy.initial_rows(town, day=3, seed=SEED)
        self.assertEqual([row["category"] for row in rows], list(economy.GOODS_CATEGORIES))
        for row in rows:
            self.assertEqual(row["settlement_id"], "S3")
            self.assertEqual(row["stock"], economy.EQUILIBRIUM_DAYS)
            self.assertEqual(row["seeded_day"], 3)
            self.assertEqual(row["price_mult"], 1.0)
            self.assertEqual(row["size"], "town")
            self.assertEqual(row["name"], "Ashbarrow")
            consumption = row["consumption"]
            self.assertGreaterEqual(row["demand"], consumption * 0.9 - 1e-9)
            self.assertLessEqual(row["demand"], consumption * 1.1 + 1e-9)
        self.assertEqual(economy.initial_rows(town, day=3, seed=SEED), rows)  # same seed, same nudge
        self.assertNotEqual(
            [r["demand"] for r in economy.initial_rows(town, day=3, seed=SEED + 1)],
            [r["demand"] for r in rows],
        )
        no_magic = economy.categories_for({"magic_level": "none"})
        self.assertNotIn("magic", no_magic)
        self.assertEqual(len(no_magic), 15)
        self.assertIn("magic", economy.categories_for({"magic_level": "rare"}))
        self.assertIn("magic", economy.categories_for(None))
        rows_no_magic = economy.initial_rows(town, day=3, seed=SEED, categories=no_magic)
        self.assertNotIn("magic", {row["category"] for row in rows_no_magic})


class MultiplierTests(unittest.TestCase):
    def setUp(self):
        self.town = economy.settlement_profile(BOARD_TOWN)
        self.spring = economy.season_for_day(1)

    def test_price_multiplier_is_one_at_equilibrium_without_drift(self):
        for elasticity in (0.1, 0.5, 1.0):
            mult = economy.price_multiplier(
                _spring_row(self.town, "tools"), events=[], season=self.spring, day=1, seed=SEED,
                elasticity=elasticity, drift=0.0,
            )
            _assert_price_multiplier_shape(self, mult)
            self.assertAlmostEqual(mult["mult"], 1.0, places=4)
            self.assertEqual(mult["season_mult"], 1.0)
            self.assertEqual(mult["scarcity_mult"], 1.0)
            self.assertEqual(mult["drift_mult"], 1.0)
            self.assertEqual(mult["events"], [])
            self.assertEqual(mult["reason"], "ok")
        # A category with a season effect scales with the season only.
        food = economy.price_multiplier(
            _spring_row(self.town, "food"), events=[], season=self.spring, day=1, seed=SEED, drift=0.0
        )
        self.assertEqual(food["season_mult"], 1.10)
        self.assertAlmostEqual(food["mult"], 1.10 ** 0.5 * 1.10, places=3)
        misc = economy.price_multiplier(
            _spring_row(self.town, "misc", stock=0.1), events=[], season=self.spring, day=1, seed=SEED
        )
        self.assertEqual(misc["mult"], 1.0)

    def test_price_multiplier_rises_when_stock_low_and_falls_when_high(self):
        low = economy.price_multiplier(
            _spring_row(self.town, "tools", stock=1.0), events=[], season=self.spring, day=1, seed=SEED, drift=0.0
        )
        high = economy.price_multiplier(
            _spring_row(self.town, "tools", stock=15.0), events=[], season=self.spring, day=1, seed=SEED, drift=0.0
        )
        self.assertGreater(low["mult"], 1.0)
        self.assertLess(high["mult"], 1.0)
        self.assertAlmostEqual(low["mult"], (1 / 0.2) ** 0.5, places=3)
        self.assertAlmostEqual(high["mult"], (1 / 3.0) ** 0.5, places=3)
        self.assertAlmostEqual(low["supply"], 0.2)
        self.assertAlmostEqual(high["supply"], 3.0)

    def test_price_multiplier_clamped_040_300(self):
        row = _spring_row(self.town, "tools", stock=0.1)
        row["demand"] = row["consumption"] * 4
        high = economy.price_multiplier(row, events=[], season=self.spring, day=1, seed=SEED, elasticity=1.0, drift=0.0)
        self.assertEqual(high["mult"], 3.0)
        row = _spring_row(self.town, "tools", stock=30.0)
        row["demand"] = row["consumption"] * 0.1
        low = economy.price_multiplier(row, events=[], season=self.spring, day=1, seed=SEED, elasticity=1.0, drift=0.0)
        self.assertEqual(low["mult"], 0.4)

    def test_scarcity_event_adds_delta_and_blocks_imports(self):
        blight = {"id": 1, "settlement_id": "S3", "kind": "blight", "category": "food", "strength": 1.0,
                  "start_day": 1, "end_day": 30, "status": "active"}
        plain = economy.price_multiplier(
            _spring_row(self.town, "food"), events=[], season=self.spring, day=5, seed=SEED, drift=0.0
        )
        hit = economy.price_multiplier(
            _spring_row(self.town, "food"), events=[blight], season=self.spring, day=5, seed=SEED, drift=0.0
        )
        self.assertEqual(hit["events"], ["blight"])
        self.assertAlmostEqual(hit["scarcity_mult"], 1.60)
        self.assertAlmostEqual(hit["mult"], plain["mult"] * 1.60, places=3)
        # Strength scales the delta; an ended or out-of-window event does nothing.
        strong = dict(blight, strength=1.3)
        self.assertAlmostEqual(
            economy.price_multiplier(_spring_row(self.town, "food"), events=[strong], season=self.spring, day=5, seed=SEED, drift=0.0)["scarcity_mult"],
            1.78,
        )
        ended = dict(blight, status="ended")
        self.assertEqual(
            economy.price_multiplier(_spring_row(self.town, "food"), events=[ended], season=self.spring, day=5, seed=SEED, drift=0.0)["events"],
            [],
        )
        self.assertEqual(
            economy.price_multiplier(_spring_row(self.town, "food"), events=[blight], season=self.spring, day=40, seed=SEED, drift=0.0)["events"],
            [],
        )
        # The '' category hits everything; a two-category event hits both and nothing else.
        bandits = dict(blight, kind="road_bandits", category="")
        self.assertEqual(
            economy.price_multiplier(_spring_row(self.town, "tools"), events=[bandits], season=self.spring, day=5, seed=SEED, drift=0.0)["events"],
            ["road_bandits"],
        )
        drought = dict(blight, kind="drought", category="food,drink")
        self.assertEqual(economy.price_multiplier(_spring_row(self.town, "drink"), events=[drought], season=self.spring, day=5, seed=SEED, drift=0.0)["events"], ["drought"])
        self.assertEqual(economy.price_multiplier(_spring_row(self.town, "tools"), events=[drought], season=self.spring, day=5, seed=SEED, drift=0.0)["events"], [])

        # Imports: a short town recovers toward equilibrium without the blight and stays short with it.
        short = _spring_row(self.town, "food", stock=2.0)
        recovered = economy.advance_market_row(short, season=self.spring, events=[], day=6)
        blocked = economy.advance_market_row(short, season=self.spring, events=[blight], day=6)
        self.assertGreater(recovered["stock"], blocked["stock"])
        # The import pull is pinned, not just bounded: 1.9 + (5.0 - 1.9) x 0.15 = 2.365.
        self.assertAlmostEqual(recovered["stock"], 1.9 + (economy.EQUILIBRIUM_DAYS - 1.9) * economy.IMPORT_PULL, places=6)
        self.assertGreater(recovered["stock"], 2.0)
        self.assertEqual(recovered["updated_day"], 6)
        self.assertEqual(short["stock"], 2.0)  # the input row is not changed
        # A town makes exactly what it eats in spring except the 10 percent season demand bump.
        self.assertAlmostEqual(blocked["stock"], max(0.1, 2.0 + (1.0 - 1.10)), places=6)
        # Glut does not block imports.
        glut = dict(blight, kind="glut")
        self.assertAlmostEqual(
            economy.advance_market_row(short, season=self.spring, events=[glut], day=6)["stock"], recovered["stock"]
        )
        # Stock stays inside its bounds.
        starving = _spring_row(self.town, "food", stock=0.1)
        starving["production"] = 0.0
        self.assertGreaterEqual(economy.advance_market_row(starving, season=self.spring, events=[blight], day=6)["stock"], 0.1)
        full = _spring_row(self.town, "food", stock=30.0)
        full["production"] = full["consumption"] * 10
        self.assertLessEqual(economy.advance_market_row(full, season=self.spring, events=[blight], day=6)["stock"], 30.0)

    def test_weather_nudge_storm_transport(self):
        row = _spring_row(self.town, "transport")
        calm = economy.price_multiplier(row, events=[], season=self.spring, day=2, seed=SEED, drift=0.0)
        storm = economy.price_multiplier(row, events=[], season=self.spring, day=2, seed=SEED, drift=0.0, weather_kind="storm")
        self.assertEqual(storm["events"], ["weather:storm"])
        self.assertAlmostEqual(storm["scarcity_mult"], 1.15)
        self.assertAlmostEqual(storm["mult"], calm["mult"] * 1.15, places=3)
        fuel = economy.price_multiplier(_spring_row(self.town, "fuel"), events=[], season=self.spring, day=2, seed=SEED, drift=0.0, weather_kind="snow")
        self.assertAlmostEqual(fuel["scarcity_mult"], 1.10)
        fog = economy.price_multiplier(row, events=[], season=self.spring, day=2, seed=SEED, drift=0.0, weather_kind="fog")
        self.assertAlmostEqual(fog["scarcity_mult"], 1.05)
        rain = economy.price_multiplier(row, events=[], season=self.spring, day=2, seed=SEED, drift=0.0, weather_kind="rain")
        self.assertEqual(rain["events"], [])
        food_storm = economy.price_multiplier(_spring_row(self.town, "food"), events=[], season=self.spring, day=2, seed=SEED, drift=0.0, weather_kind="storm")
        self.assertEqual(food_storm["events"], [])

    def test_flavour_multiplier_table(self):
        self.assertEqual(economy.flavour_multiplier("scarce"), 1.15)
        self.assertEqual(economy.flavour_multiplier("barter-heavy"), 1.05)
        self.assertEqual(economy.flavour_multiplier("coin-driven"), 0.95)
        self.assertEqual(economy.flavour_multiplier("guild-controlled"), 1.05)
        self.assertEqual(economy.flavour_multiplier("prosperous trade hub"), 0.90)
        self.assertEqual(economy.flavour_multiplier("rich"), 0.90)
        self.assertEqual(economy.flavour_multiplier(""), 1.0)
        self.assertEqual(economy.flavour_multiplier("ordinary"), 1.0)
        row = _spring_row(self.town, "tools")
        flavoured = economy.price_multiplier(row, events=[], season=self.spring, day=1, seed=SEED, drift=0.0, flavour_mult=1.15)
        self.assertAlmostEqual(flavoured["mult"], 1.15, places=4)
        self.assertEqual(flavoured["flavour_mult"], 1.15)

    def test_drift_is_deterministic_for_seed_day_settlement_category(self):
        a = economy.drift_multiplier("S3", "food", day=7, seed=SEED)
        b = economy.drift_multiplier("S3", "food", day=7, seed=SEED)
        self.assertEqual(a, b)
        self.assertGreaterEqual(a, 0.96)
        self.assertLessEqual(a, 1.04)
        self.assertNotEqual(a, economy.drift_multiplier("S3", "food", day=7, seed=SEED + 1))
        self.assertNotEqual(a, economy.drift_multiplier("S4", "food", day=7, seed=SEED))
        self.assertNotEqual(a, economy.drift_multiplier("S3", "drink", day=7, seed=SEED))
        self.assertEqual(economy.drift_multiplier("S3", "food", day=7, seed=SEED, drift=0.0), 1.0)
        wide = economy.drift_multiplier("S3", "food", day=7, seed=SEED, drift=0.25)
        self.assertAlmostEqual((wide - 1.0) / 0.25, (a - 1.0) / 0.04, places=9)

    def test_drift_differs_between_days(self):
        values = {economy.drift_multiplier("S3", "food", day=day, seed=SEED) for day in range(1, 11)}
        self.assertGreater(len(values), 5)


class ScarcityRollTests(unittest.TestCase):
    def _scan(self, profile: dict, *, day: int = 3, limit: int = 600, active=None, flavour: str = ""):
        hits = []
        for seed in range(limit):
            event = economy.roll_scarcity(profile, day=day, seed=seed, active=list(active or []), flavour=flavour)
            if event is not None:
                hits.append((seed, event))
        return hits

    def test_roll_scarcity_deterministic_and_respects_cap_and_size_rules(self):
        town = economy.settlement_profile(BOARD_TOWN)
        hits = self._scan(town)
        self.assertTrue(hits, "no seed in the scan fired an event at a 3 percent chance")
        # About 3 percent of seeds fire; well inside 0.5 .. 8 percent for 600 seeds.
        self.assertGreater(len(hits), 3)
        self.assertLess(len(hits), 48)
        seed, event = hits[0]
        again = economy.roll_scarcity(town, day=3, seed=seed, active=[])
        self.assertEqual(again, event)
        self.assertEqual(event["settlement_id"], "S3")
        self.assertEqual(event["start_day"], 3)
        self.assertIn(event["kind"], economy.SCARCITY_EVENTS)
        spec = economy.SCARCITY_EVENTS[event["kind"]]
        self.assertGreaterEqual(event["end_day"] - event["start_day"], spec["duration"][0])
        self.assertLessEqual(event["end_day"] - event["start_day"], spec["duration"][1])
        self.assertGreaterEqual(event["strength"], 0.7)
        self.assertLessEqual(event["strength"], 1.3)
        self.assertEqual(event["category"], ",".join(spec["categories"]))
        self.assertIn("Ashbarrow", event["news"])
        self.assertEqual(event["status"], "active")
        self.assertEqual(event["id"], 0)
        for key in ("kind", "category", "strength", "start_day", "end_day", "label", "news"):
            self.assertIn(key, event)
        # The cap: two running events and the same seed starts nothing.
        running = [
            {"kind": "glut", "category": "food", "start_day": 1, "end_day": 20, "status": "active"},
            {"kind": "caravan", "category": "luxury,cloth,knowledge", "start_day": 1, "end_day": 20, "status": "active"},
        ]
        self.assertIsNone(economy.roll_scarcity(town, day=3, seed=seed, active=running))
        # An ended event does not count toward the cap.
        self.assertIsNotNone(economy.roll_scarcity(town, day=3, seed=seed, active=[dict(running[0], status="ended"), running[1]]))
        # Size rules: a hamlet never gets war_levy, plague or a festival; a town can get all three.
        farm = economy.settlement_profile(BOARD_FARM)
        self.assertEqual(farm["size"], "hamlet")
        farm_kinds = {event["kind"] for _, event in self._scan(farm, limit=2000)}
        self.assertTrue(farm_kinds)
        self.assertFalse(farm_kinds & {"war_levy", "plague", "festival"}, farm_kinds)
        town_kinds = {event["kind"] for _, event in self._scan(town, limit=4000)}
        self.assertIn("festival", town_kinds)
        self.assertTrue(town_kinds & {"war_levy", "plague"}, town_kinds)
        village = economy.settlement_profile(LIST_ROW_VILLAGE)
        village_kinds = {event["kind"] for _, event in self._scan(village, limit=2000)}
        self.assertIn("festival", village_kinds)
        self.assertFalse(village_kinds & {"war_levy", "plague"}, village_kinds)
        # Chance 0 never fires; chance 1 always does.
        self.assertIsNone(economy.roll_scarcity(town, day=3, seed=seed, active=[], event_chance=0.0))
        self.assertIsNotNone(economy.roll_scarcity(town, day=3, seed=1, active=[], event_chance=1.0))
        with self.assertRaises(ValueError):
            economy.roll_scarcity(town, day=0, seed=1, active=[])

    def test_event_proposal_shape(self):
        town = economy.settlement_profile(BOARD_TOWN)
        event = economy.roll_scarcity(town, day=3, seed=1, active=[], event_chance=1.0)
        proposal = economy.event_proposal(event)
        _assert_event_proposal_shape(self, proposal)
        self.assertEqual(proposal["summary"], event["news"])
        self.assertEqual(proposal["trigger"], f"economy:{event['kind']}")
        self.assertEqual(proposal["payload"]["settlement_id"], "S3")


class TickProposalTests(unittest.TestCase):
    def setUp(self):
        self.town = economy.settlement_profile(BOARD_TOWN)
        self.rows = economy.initial_rows(self.town, day=1, seed=SEED)

    def test_tick_day_proposal_multiple_days_ends_events_and_reports_lines(self):
        blight = {"id": 4, "settlement_id": "S3", "kind": "blight", "category": "food", "strength": 1.0,
                  "start_day": 1, "end_day": 6, "status": "active"}
        out = economy.tick_day_proposal(
            self.rows, [blight], profile=self.town, from_day=1, to_day=10, seed=SEED,
            config={"event_chance": 0.0}
        )
        self.assertEqual(set(out.keys()), {"rows", "events", "new_events", "multipliers", "lines", "event_proposals"})
        self.assertEqual(len(out["rows"]), len(self.rows))
        self.assertEqual(out["new_events"], [])
        self.assertEqual(out["event_proposals"], [])
        self.assertEqual(len(out["events"]), 1)
        self.assertEqual(out["events"][0]["status"], "ended")
        self.assertEqual(out["events"][0]["id"], 4)
        self.assertEqual(blight["status"], "active")  # the input is not changed
        self.assertEqual(self.rows[0]["updated_day"], 1)
        for row in out["rows"]:
            self.assertEqual(row["updated_day"], 10)
            self.assertIn(row["category"], out["multipliers"])
            self.assertEqual(row["price_mult"], out["multipliers"][row["category"]]["mult"])
        for mult in out["multipliers"].values():
            _assert_price_multiplier_shape(self, mult)
            self.assertEqual(mult["day"], 10)
            self.assertEqual(mult["season"], "spring")
            self.assertEqual(mult["events"], [])  # the blight ended on day 6
        self.assertIsInstance(out["lines"], list)
        for line in out["lines"]:
            self.assertIsInstance(line, str)
            self.assertIn("Ashbarrow", line)
        # Food stayed short while the blight ran, so its stock is below equilibrium at the end.
        food = next(row for row in out["rows"] if row["category"] == "food")
        self.assertLess(food["stock"], economy.EQUILIBRIUM_DAYS)
        # At the highest allowed chance some seed starts at least two events over forty days; each new
        # event is proposed, start days ascend and no more than two ever run at once.
        forced = None
        for seed in range(60):
            candidate = economy.tick_day_proposal(
                self.rows, [], profile=self.town, from_day=1, to_day=41, seed=seed, config={"event_chance": 0.2}
            )
            if len(candidate["new_events"]) >= 2:
                forced = candidate
                forced_seed = seed
                break
        self.assertIsNotNone(forced, "no seed under 60 started two events at a 20 percent daily chance")
        self.assertEqual(len(forced["event_proposals"]), len(forced["new_events"]))
        for proposal in forced["event_proposals"]:
            _assert_event_proposal_shape(self, proposal)
        starts = [e["start_day"] for e in forced["new_events"]]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(2 <= day <= 41 for day in starts))
        for day in range(2, 42):
            running = [e for e in forced["events"] if e["start_day"] <= day <= e["end_day"]]
            self.assertLessEqual(len(running), economy.MAX_ACTIVE_EVENTS, day)
        for event in forced["events"]:
            self.assertEqual(event["status"], "ended" if event["end_day"] < 41 else "active")
        # Replay: the same inputs give the same output.
        self.assertEqual(
            economy.tick_day_proposal(self.rows, [], profile=self.town, from_day=1, to_day=41, seed=forced_seed, config={"event_chance": 0.2}),
            forced,
        )
        # A chance outside the allowed range is not honoured: the config falls back to its default.
        self.assertEqual(economy.tick_day_proposal(self.rows, [], profile=self.town, from_day=1, to_day=3, seed=SEED, config={"event_chance": 1.0}),
                         economy.tick_day_proposal(self.rows, [], profile=self.town, from_day=1, to_day=3, seed=SEED, config={"event_chance": 0.03}))
        # Weather reaches the final multipliers.
        stormy = economy.tick_day_proposal(
            self.rows, [], profile=self.town, from_day=1, to_day=2, seed=SEED, config={"event_chance": 0.0}, weather_kind="storm"
        )
        self.assertEqual(stormy["multipliers"]["transport"]["events"], ["weather:storm"])

    def test_tick_day_proposal_no_op_when_to_day_not_after_from_day(self):
        for to_day in (1, 0, -3):
            out = economy.tick_day_proposal(self.rows, [], profile=self.town, from_day=1, to_day=to_day, seed=SEED)
            self.assertEqual(out["rows"], self.rows)
            self.assertEqual(out["events"], [])
            self.assertEqual(out["new_events"], [])
            self.assertEqual(out["multipliers"], {})
            self.assertEqual(out["lines"], [])
            self.assertEqual(out["event_proposals"], [])

    def test_market_lines_only_for_large_deviations(self):
        def mult(category, value, events=(), season="winter"):
            out = economy.neutral_multiplier("S3", category, day=12, reason="ok", season=season)
            out["mult"] = value
            out["events"] = list(events)
            return out

        near = {"food": mult("food", 1.1), "tools": mult("tools", 0.9), "fuel": mult("fuel", 1.24)}
        self.assertEqual(economy.market_lines(near, self.town), [])
        far = {
            "food": mult("food", 1.6, ["blight"]),
            "fuel": mult("fuel", 1.3),
            "cloth": mult("cloth", 0.7),
            "tools": mult("tools", 1.0),
        }
        lines = economy.market_lines(far, self.town)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "Grain is dear in Ashbarrow this winter (blight).")
        self.assertEqual(lines[1], "Cloth is cheap in Ashbarrow this winter.")
        self.assertEqual(len(economy.market_lines(far, self.town, limit=3)), 3)
        self.assertEqual(economy.market_lines(far, self.town, limit=0), [])
        self.assertIn("Fuel is dear in Ashbarrow this winter.", economy.market_lines(far, self.town, limit=3))
        # A neutral multiplier with a reason other than ok is never reported; an unnamed profile reads "the market".
        unknown = {"food": dict(mult("food", 1.6), reason="unknown_settlement")}
        self.assertEqual(economy.market_lines(unknown, self.town), [])
        nameless = economy.market_lines({"food": mult("food", 0.5, [], season="")}, economy.settlement_profile(None))
        self.assertEqual(nameless, ["Grain is cheap in the market."])
        for line in lines:
            self.assertLess(len(line), 160)
            self.assertNotIn("*", line)


# ---------------------------------------------------------------------------
# Writers against a temporary database
# ---------------------------------------------------------------------------


class EconomyDbTests(unittest.TestCase):
    def setUp(self):
        os.environ.update(_ENV)
        _fresh_db()

    def test_schema_is_idempotent_and_not_in_world_tables(self):
        with connect() as conn:
            economy.ensure_schema(conn)
            economy.ensure_schema(conn)
            names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertIn("market_state", names)
            self.assertIn("market_events", names)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(market_state)")}
            self.assertEqual(columns, {
                "settlement_id", "category", "stock", "demand", "production", "consumption", "price_mult",
                "updated_day", "seeded_day", "size", "type", "name",
            })
            event_columns = {row["name"] for row in conn.execute("PRAGMA table_info(market_events)")}
            self.assertEqual(event_columns, {
                "id", "settlement_id", "category", "kind", "strength", "start_day", "end_day", "status", "note",
            })
        for name in ("market_state", "market_events"):
            self.assertNotIn(name, world.WORLD_TABLES)
            self.assertNotIn(name, world.AUTOINC_TABLES)
            self.assertNotIn(name, world.RESTORE_ORDER)
        self.assertNotIn(economy.CONFIG_KEY, world.SNAPSHOT_SETTING_KEYS)
        # init_db alone does not create the tables: the schema is the module's own.
        conn.close()
        path = db_path()
        gc.collect()  # Windows will not unlink a db a leaked connection still holds
        path.unlink()
        init_db()
        with connect() as conn:
            names = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertNotIn("market_state", names)
        self.assertNotIn("market_events", names)

    def test_ensure_settlement_inserts_once(self):
        with connect() as conn:
            rows = economy.ensure_settlement(conn, BOARD_TOWN, day=2, seed=SEED)
            self.assertEqual(len(rows), 16)
            self.assertEqual({row["settlement_id"] for row in rows}, {"S3"})
            self.assertEqual(rows[0]["seeded_day"], 2)
            # A second call on a later day keeps the first rows.
            again = economy.ensure_settlement(conn, BOARD_TOWN, day=9, seed=SEED)
            self.assertEqual(again, rows)
            count = conn.execute("SELECT COUNT(*) FROM market_state").fetchone()[0]
            self.assertEqual(count, 16)
            # No magic rows for a world without magic; venue kinds raise production.
            no_magic = economy.ensure_settlement(
                conn, LIST_ROW_VILLAGE, day=2, seed=SEED, options={"magic_level": "none"}, venue_kinds=["inn", "bakery"]
            )
            self.assertEqual(len(no_magic), 15)
            self.assertNotIn("magic", {row["category"] for row in no_magic})
            food = next(row for row in no_magic if row["category"] == "food")
            self.assertAlmostEqual(food["production"], food["consumption"] * (1.4 + 0.30))
            # A record with no id is not a settlement.
            self.assertEqual(economy.ensure_settlement(conn, {"state": "town"}, day=2, seed=SEED), [])
            self.assertEqual(economy.ensure_settlement(conn, None, day=2, seed=SEED), [])
            with self.assertRaises(ValueError):
                economy.ensure_settlement(conn, BOARD_TOWN, day=0, seed=SEED)

    def test_tick_day_skips_hidden_base_and_landmark_rows(self):
        # tile_world.list_settlements hands a discovered hidden camp in twice: as a landmark row whose
        # state is farm (or ruins) and as a hidden_base row. Neither is a settlement and neither gets a market.
        camp_as_farm = {"id": "hb:3", "x": 5, "y": 6, "state": "farm", "name": "Hidden camp",
                        "summary": "Discovered camp hideout.", "kind": "hidden_base", "discovered": True}
        camp = {"id": "hb:3", "x": 5, "y": 6, "state": "hidden_base", "name": "Hidden camp",
                "summary": "Discovered camp hideout.", "kind": "hidden_base", "discovered": True}
        shrine = {"id": "lm:1", "x": 1, "y": 1, "state": "shrine", "name": "Old shrine", "summary": "",
                  "kind": "landmark", "discovered": True}
        with connect() as conn:
            economy.update_economy_config(conn, {"event_chance": 0.2})
            self.assertEqual(economy.ensure_settlement(conn, camp_as_farm, day=1, seed=SEED), [])
            out = economy.tick_day(conn, from_day=1, to_day=30, settlements=[camp_as_farm, camp, shrine], seed=SEED)
            self.assertEqual(out["ticked"], 0)
            self.assertEqual(out["new_events"], [])
            self.assertEqual(out["lines"], [])
            self.assertEqual(out["event_proposals"], [])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM market_state").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM market_events").fetchone()[0], 0)
            # A real list_settlements blob row beside them still ticks.
            out = economy.tick_day(conn, from_day=1, to_day=3, settlements=[camp_as_farm, LIST_ROW_VILLAGE], seed=SEED)
            self.assertEqual(out["ticked"], 1)
            ids = {row["settlement_id"] for row in conn.execute("SELECT settlement_id FROM market_state")}
            self.assertEqual(ids, {"S5"})

    def test_tick_day_writes_rows_and_events_and_is_replayable(self):
        settlements = [BOARD_TOWN, BOARD_FARM, WORLD_CITY]

        def run(path: Path) -> tuple[list[tuple], list[tuple], dict]:
            os.environ["AI_RPG_DB"] = str(path)
            init_db()
            with connect() as conn:
                economy.ensure_schema(conn)
                economy.update_economy_config(conn, {"event_chance": 0.2})
                out = economy.tick_day(conn, from_day=1, to_day=11, settlements=settlements, seed=SEED)
                rows = [tuple(dict(r).items()) for r in conn.execute(
                    "SELECT * FROM market_state ORDER BY settlement_id, category"
                )]
                events = [tuple(dict(r).items()) for r in conn.execute(
                    "SELECT settlement_id, category, kind, strength, start_day, end_day, status, note FROM market_events ORDER BY id"
                )]
            conn.close()
            return rows, events, out

        try:
            rows_a, events_a, out_a = run(_TMP / "replay_a.db")
            rows_b, events_b, out_b = run(_TMP / "replay_b.db")
        finally:
            os.environ.update(_ENV)
        self.assertEqual(rows_a, rows_b)
        self.assertEqual(events_a, events_b)
        self.assertEqual(out_a, out_b)
        self.assertEqual(out_a["ticked"], 3)
        self.assertEqual(out_a["days"], 10)
        self.assertEqual(set(out_a.keys()), {"ticked", "days", "new_events", "lines", "event_proposals"})
        self.assertEqual(len(rows_a), 48)
        self.assertTrue(all(dict(row)["updated_day"] == 11 for row in rows_a))
        self.assertTrue(events_a, "a 20 percent daily chance over 30 settlement-days started no event")
        self.assertEqual(len(out_a["event_proposals"]), len(out_a["new_events"]))
        self.assertEqual(len(events_a), len(out_a["new_events"]))
        for proposal in out_a["event_proposals"]:
            _assert_event_proposal_shape(self, proposal)
        for event in out_a["new_events"]:
            self.assertNotEqual(event["id"], 0)  # the stored id is written back
        # No-op tick and a disabled config.
        with connect() as conn:
            self.assertEqual(
                economy.tick_day(conn, from_day=5, to_day=5, settlements=settlements, seed=SEED),
                {"ticked": 0, "days": 0, "new_events": [], "lines": [], "event_proposals": []},
            )
            economy.update_economy_config(conn, {"enabled": False})
            off = economy.tick_day(conn, from_day=1, to_day=3, settlements=settlements, seed=SEED)
            self.assertEqual(off["ticked"], 0)
            self.assertTrue(off.get("disabled"))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM market_state").fetchone()[0], 0)

    def test_tick_day_ends_events_and_market_snapshot_reads_them(self):
        with connect() as conn:
            economy.ensure_settlement(conn, BOARD_TOWN, day=1, seed=SEED)
            conn.execute(
                "INSERT INTO market_events (settlement_id, category, kind, strength, start_day, end_day, status, note) "
                "VALUES ('S3', 'food', 'blight', 1.0, 1, 4, 'active', 'A blight has taken the grain around Ashbarrow.')"
            )
            self.assertEqual(len(economy.active_events(conn, "S3", day=2)), 1)
            self.assertEqual(economy.active_events(conn, "S3", day=5), [])
            snap = economy.market_snapshot(conn, "S3", day=2, seed=SEED)
            self.assertEqual(set(snap.keys()), {"settlement_id", "rows", "events", "multipliers"})
            self.assertEqual(snap["settlement_id"], "S3")
            self.assertEqual(len(snap["rows"]), 16)
            self.assertEqual(len(snap["events"]), 1)
            self.assertEqual(snap["multipliers"]["food"]["events"], ["blight"])
            for mult in snap["multipliers"].values():
                _assert_price_multiplier_shape(self, mult)
            out = economy.tick_day(conn, from_day=2, to_day=6, settlements=[BOARD_TOWN], seed=SEED)
            self.assertEqual(out["ticked"], 1)
            status = conn.execute("SELECT status FROM market_events WHERE kind = 'blight'").fetchone()["status"]
            self.assertEqual(status, "ended")
            self.assertEqual(economy.active_events(conn, "S3", day=6), [])
            empty = economy.market_snapshot(conn, "nowhere", day=2, seed=SEED)
            self.assertEqual(empty, {"settlement_id": "nowhere", "rows": [], "events": [], "multipliers": {}})

    def test_settlement_multiplier_neutral_for_unknown(self):
        with connect() as conn:
            unknown = economy.settlement_multiplier(conn, "S99", "food", day=3, seed=SEED)
            _assert_price_multiplier_shape(self, unknown)
            self.assertEqual(unknown["mult"], 1.0)
            self.assertEqual(unknown["reason"], "unknown_settlement")
            self.assertEqual(unknown["settlement_id"], "S99")
            self.assertEqual(unknown["category"], "food")
            self.assertEqual(unknown["day"], 3)
            self.assertEqual(unknown["season"], "spring")
            economy.ensure_settlement(conn, BOARD_TOWN, day=1, seed=SEED)
            bad_cat = economy.settlement_multiplier(conn, "S3", "spices", day=3, seed=SEED)
            self.assertEqual(bad_cat["reason"], "unknown_category")
            self.assertEqual(bad_cat["mult"], 1.0)
            known = economy.settlement_multiplier(conn, "S3", "food", day=3, seed=SEED)
            _assert_price_multiplier_shape(self, known)
            self.assertEqual(known["reason"], "ok")
            self.assertEqual(known["settlement_id"], "S3")
            self.assertEqual(known["season_mult"], 1.10)
            # Options carry the flavour; weather carries the nudge.
            scarce = economy.settlement_multiplier(conn, "S3", "food", day=3, seed=SEED, options={"economy": "scarce"})
            self.assertEqual(scarce["flavour_mult"], 1.15)
            self.assertAlmostEqual(scarce["mult"], min(3.0, known["mult"] * 1.15), places=3)
            storm = economy.settlement_multiplier(conn, "S3", "transport", day=3, seed=SEED, weather_kind="storm")
            self.assertEqual(storm["events"], ["weather:storm"])
            economy.update_economy_config(conn, {"enabled": False})
            off = economy.settlement_multiplier(conn, "S3", "food", day=3, seed=SEED)
            self.assertEqual(off["reason"], "disabled")
            self.assertEqual(off["mult"], 1.0)
            with self.assertRaises(ValueError):
                economy.settlement_multiplier(conn, "S3", "food", day=0, seed=SEED)

    def test_config_row_defaults_update_and_validation(self):
        with connect() as conn:
            defaults = economy.get_economy_config(conn)
            self.assertEqual(defaults, {
                "season_days": 30, "first_season": "spring", "drift": 0.04, "elasticity": 0.5,
                "event_chance": 0.03, "enabled": True,
            })
            updated = economy.update_economy_config(conn, {"season_days": 45, "first_season": "Winter", "enabled": "off", "junk": 1})
            self.assertEqual(updated["season_days"], 45)
            self.assertEqual(updated["first_season"], "winter")
            self.assertIs(updated["enabled"], False)
            self.assertNotIn("junk", updated)
            self.assertEqual(updated["drift"], 0.04)
            stored = json.loads(conn.execute("SELECT value FROM settings WHERE key = ?", (economy.CONFIG_KEY,)).fetchone()["value"])
            self.assertEqual(stored, updated)
            self.assertEqual(economy.get_economy_config(conn), updated)
            for bad in (
                {"season_days": 6}, {"season_days": 121}, {"drift": -0.1}, {"drift": 0.3},
                {"elasticity": 0.05}, {"elasticity": 1.5}, {"event_chance": 0.25}, {"event_chance": "soon"},
                {"first_season": "monsoon"},
            ):
                with self.assertRaises(ValueError, msg=str(bad)):
                    economy.update_economy_config(conn, bad)
            with self.assertRaises(ValueError):
                economy.update_economy_config(conn, "not a dict")  # type: ignore[arg-type]
            self.assertEqual(economy.get_economy_config(conn), updated)  # a refused update writes nothing
            # Bad JSON and out-of-range stored values fall back to the defaults.
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", ("{not json", economy.CONFIG_KEY))
            self.assertEqual(economy.get_economy_config(conn), defaults)
            conn.execute("UPDATE settings SET value = ? WHERE key = ?", (json.dumps({"drift": 9, "season_days": 60}), economy.CONFIG_KEY))
            partly = economy.get_economy_config(conn)
            self.assertEqual(partly["drift"], 0.04)
            self.assertEqual(partly["season_days"], 60)
            # The season config reaches the tick and the multiplier.
            economy.update_economy_config(conn, {"first_season": "winter", "season_days": 10})
            economy.ensure_settlement(conn, BOARD_TOWN, day=1, seed=SEED)
            self.assertEqual(economy.settlement_multiplier(conn, "S3", "food", day=5, seed=SEED)["season"], "winter")
            self.assertEqual(economy.settlement_multiplier(conn, "S3", "food", day=15, seed=SEED)["season"], "spring")

    def test_writers_touch_no_foreign_tables(self):
        own_tables = {"market_state", "market_events"}
        with connect() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?)",
                (json.dumps({"economy": "scarce", "magic_level": "none"}),),
            )
            before_counts = _table_counts(conn)
            before_settings = _setting_rows(conn)
            before_player = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
            economy.ensure_settlement(conn, BOARD_TOWN, day=1, seed=SEED)
            economy.ensure_settlement(conn, WORLD_CITY, day=1, seed=SEED, options={"economy": "scarce"})
            economy.update_economy_config(conn, {"event_chance": 0.2})
            economy.tick_day(conn, from_day=1, to_day=15, settlements=[BOARD_TOWN, WORLD_CITY, BOARD_FARM],
                             options={"economy": "scarce"}, seed=SEED, weather_kind="storm")
            economy.settlement_multiplier(conn, "S3", "food", day=15, seed=SEED)
            economy.market_snapshot(conn, "S3", day=15, seed=SEED)
            economy.active_events(conn, "S3", day=15)
            after_counts = _table_counts(conn)
            after_settings = _setting_rows(conn)
            after_player = dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())
        self.assertEqual(set(after_counts) - set(before_counts), set())
        changed = {name for name in after_counts if after_counts[name] != before_counts.get(name)}
        self.assertEqual(changed - own_tables - {"settings"}, set(), changed)
        self.assertGreater(after_counts["market_state"], 0)
        self.assertGreater(after_counts["market_events"], 0)
        # Every foreign settings row keeps its value (an UPDATE of playthrough_options would show here).
        self.assertEqual({k: v for k, v in after_settings.items() if k != economy.CONFIG_KEY}, before_settings)
        self.assertIn(economy.CONFIG_KEY, after_settings)
        self.assertNotIn("campaign_rng_seed", after_settings)  # an explicit seed never asks for the campaign seed
        self.assertEqual(after_player, before_player)
        for name in ("player", "inventory", "npcs", "journal", "gm_events", "locations", "pacing"):
            self.assertEqual(after_counts[name], before_counts[name], name)


# ---------------------------------------------------------------------------
# The module stays a leaf
# ---------------------------------------------------------------------------


class LeafTests(unittest.TestCase):
    # New modules of this same pass that the contracts allow to import economy (trade in-cluster,
    # settlement_visits lazily). Each must itself be an unwired leaf of the pass.
    _ALLOWED_IMPORTERS = {"app/trade.py", "app/agreements.py", "app/settlement_visits.py"}

    def test_module_is_a_leaf(self):
        pattern = re.compile(r"app\.economy\b|from app import economy\b|import economy\b|app/economy")
        offenders = []
        for folder in ("app", "static"):
            for path in sorted((ROOT / folder).rglob("*")):
                if not path.is_file() or path.suffix not in {".py", ".js", ".html", ".css"}:
                    continue
                rel = path.relative_to(ROOT).as_posix()
                if rel == "app/economy.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if not pattern.search(text):
                    continue
                if rel in self._ALLOWED_IMPORTERS:
                    self.assertIn("Status: built, not wired", text, f"{rel} imports economy but is not an unwired leaf")
                    continue
                offenders.append(rel)
        self.assertEqual(offenders, [], f"existing code refers to app.economy: {offenders}")
        doc = economy.__doc__ or ""
        self.assertIn("Status: built, not wired (TODO n1).", doc)
        self.assertIn("Wiring (not done):", doc)
        self.assertIn("Turn on:", doc)
        self.assertIn("Tests: tests/test_economy.py", doc)
        source = (ROOT / "app" / "economy.py").read_text(encoding="utf-8")
        self.assertNotIn("executescript", source)
        self.assertNotIn("gm_events", source.split('"""', 2)[2])  # the body never names the event table
        self.assertNotIn("INSERT INTO journal", source)
        self.assertNotIn("UPDATE player", source)

    def test_hook_functions_named_in_docstring_exist(self):
        doc = economy.__doc__ or ""
        for name in ("advance_world_time", "apply_map_travel_step", "queue_world_event", "build_prompt_context",
                     "get_weather", "get_world_time", "tick_weather", "ensure_settlement_ruler", "_clear_playthrough",
                     "_save_snapshot", "_restore_snapshot_rows", "_play_system_enabled", "_settings",
                     "play_wait_turn", "apply_turn", "export_world"):
            self.assertIn(name, doc)
            self.assertTrue(callable(getattr(world, name)), name)
        # The build_prompt_context line reads these state keys; get_state sets both.
        for name in ("world_time", "settlement_meta", "event_proposals"):
            self.assertIn(name, doc)
        for name in ("WORLD_TABLES", "RESTORE_ORDER", "AUTOINC_TABLES", "_REPLACE_ONLY_WHEN_EXPORTED"):
            self.assertIn(name, doc)
            self.assertTrue(hasattr(world, name), name)
        from app import db as app_db
        from app import tile_world
        self.assertTrue(callable(app_db._migrate_columns))
        self.assertTrue(callable(tile_world.list_settlements))
        self.assertTrue(callable(tile_world.get_map))
        self.assertIn("economy_sim_enabled", doc)


if __name__ == "__main__":
    unittest.main()
