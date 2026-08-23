"""Regression tests: the world the player asked for is the world that gets staffed.

Every playtest in this repo ran one setting -- "frontier dark fantasy" -- so
nothing ever exercised the seeder outside a medieval world. The moment a
futuristic one is tried, the server invents this cast:

    Docking Bay Seven   -> bargeman, boatwright, salt carrier
    Reactor Deck        -> scribe, weaver, tanner
    Neon Market District-> scribe, scribe, well keeper
    Wreck Site Delta    -> roofer, toll keeper, roofer

_SEED_ROLE_POOLS held pre-industrial occupations only, and _seed_role_pool
picked from them using the location's *name* alone. Genre never entered the
function. No model is involved in any of this -- it is the server's own
invention for a face the prose mentioned without naming a job.

The pools are now indexed by era first, place second, with era read from the
campaign's own tech_level (falling back to the style prose the player wrote).
Pre-industrial output is unchanged, so existing campaigns do not shift.

Run:  python -m unittest tests.test_genre_seeding
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-genre-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.db import connect, db_path, init_db  # noqa: E402
from app.world import (  # noqa: E402
    _SEED_ROLE_POOLS,
    _seed_role_pool,
    resolve_world_era,
)


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB is {db_path()!r}")


def setUpModule() -> None:
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()
init_db()

# Occupations that cannot exist in a spacefaring or cyberpunk setting.
_PREINDUSTRIAL_ONLY = {
    "bargeman", "boatwright", "ferryman", "net mender", "eel fisher", "mudlark",
    "salt carrier", "cooper", "chandler", "tanner", "scribe", "weaver",
    "charcoal burner", "goatherd", "toll keeper", "well keeper", "rag picker",
    "wine seller", "roofer", "drover", "stablehand", "woodcutter", "beekeeper",
}


class TestEraResolution(unittest.TestCase):
    def test_the_canonical_tech_levels_all_map(self):
        # The vocabulary the setup UI actually offers.
        for tech, era in (
            ("iron age", "preindustrial"),
            ("medieval", "preindustrial"),
            ("early industrial", "industrial"),
            ("near future", "modern"),
            ("spacefaring salvage", "future"),
        ):
            with self.subTest(tech=tech):
                self.assertEqual(resolve_world_era(tech), era)

    def test_style_prose_is_read_when_tech_level_is_unset(self):
        for style, era in (
            ("far-future interstellar civilisation, faster-than-light travel", "future"),
            ("near-future cyberpunk megacity, corporate rule", "future"),
            ("post-collapse wasteland eighty years after the grid died", "modern"),
            ("1880s frontier west with quiet, unexplained wrongness", "industrial"),
            ("high fantasy with open magic and old empires", "preindustrial"),
            ("grounded medieval realism, no magic", "preindustrial"),
        ):
            with self.subTest(style=style):
                self.assertEqual(resolve_world_era("", style), era)

    def test_near_future_is_not_swallowed_by_modern(self):
        # "near future" contains no marker that should push it to industrial,
        # and "modern" must not claim it first.
        self.assertEqual(resolve_world_era("near future"), "modern")

    def test_an_unknown_world_defaults_to_preindustrial(self):
        # Which is what every world got unconditionally before.
        self.assertEqual(resolve_world_era(""), "preindustrial")
        self.assertEqual(resolve_world_era("", "something nobody anticipated"), "preindustrial")

    def test_every_era_has_every_place(self):
        places = {"indoor", "water", "wilderness", "settlement"}
        for era, pools in _SEED_ROLE_POOLS.items():
            with self.subTest(era=era):
                self.assertEqual(set(pools), places)
                for place, roles in pools.items():
                    self.assertTrue(roles, f"{era}/{place} is empty")


class TestSeededRolesMatchTheWorld(unittest.TestCase):
    LOCATIONS = [
        (1, "Docking Bay Seven", "A cargo bay on the orbital station, loaders humming."),
        (2, "Reactor Deck", "The fusion core level of the colony ship."),
        (3, "Neon Market District", "A rain-slick arcology street of vendors and drones."),
        (4, "Wreck Site Delta", "A crashed shuttle in the ash wastes."),
    ]

    def setUp(self):
        with connect() as conn:
            for loc_id, name, summary in self.LOCATIONS:
                conn.execute(
                    "INSERT OR REPLACE INTO locations (id, code, name, summary) VALUES (?,?,?,?)",
                    (loc_id, f"L{loc_id}", name, summary),
                )

    def _set_world(self, **options) -> None:
        with connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('playthrough_options', ?)",
                (json.dumps(options),),
            )

    def _pools(self):
        with connect() as conn:
            return {name: _seed_role_pool(conn, loc_id) for loc_id, name, _ in self.LOCATIONS}

    def test_a_spacefaring_world_has_no_bargemen(self):
        self._set_world(tech_level="spacefaring salvage")
        for name, pool in self._pools().items():
            with self.subTest(location=name):
                bad = _PREINDUSTRIAL_ONLY & set(pool)
                self.assertFalse(bad, f"{name} staffed with {sorted(bad)}")

    def test_a_cyberpunk_world_has_no_coopers(self):
        self._set_world(world_style="near-future cyberpunk megacity, corporate rule")
        for name, pool in self._pools().items():
            with self.subTest(location=name):
                self.assertFalse(_PREINDUSTRIAL_ONLY & set(pool))

    def test_the_dock_pool_is_still_a_dock_pool(self):
        # The place axis must survive the era axis: a bay is where things
        # arrive, in any century.
        self._set_world(tech_level="spacefaring salvage")
        pool = self._pools()["Docking Bay Seven"]
        self.assertTrue(
            {"cargo loader", "dock tech", "gantry hand"} & set(pool),
            f"docking bay got {pool}",
        )

    def test_the_wastes_read_as_wilderness(self):
        self._set_world(tech_level="spacefaring salvage")
        pool = self._pools()["Wreck Site Delta"]
        self.assertTrue({"salvager", "prospector", "scrapper"} & set(pool), pool)

    def test_a_medieval_world_is_untouched(self):
        # The whole point of defaulting to preindustrial: existing campaigns
        # must not shift under this change.
        self._set_world(tech_level="medieval")
        pools = self._pools()
        self.assertIn("bargeman", pools["Docking Bay Seven"])
        self.assertIn("scribe", pools["Reactor Deck"])

    def test_a_world_with_no_settings_row_still_works(self):
        with connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'playthrough_options'")
        for name, pool in self._pools().items():
            with self.subTest(location=name):
                self.assertTrue(pool, f"{name} produced no pool at all")


if __name__ == "__main__":
    unittest.main()
