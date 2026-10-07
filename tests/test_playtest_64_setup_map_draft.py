"""Playtest #64: opening New game must not replace the live game's world map.

The setup screen rolls a map on open (static/app.js rollNewGameMap ->
POST /api/tiles/generate). That roll made itself the active map at once, so a
player who looked at New game and went back continued on a world they never
chose. While a game is live the roll is now a setup draft; Start promotes the
map the screen showed.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-64-setup-draft-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, tile_world, world  # noqa: E402
from app.db import connect  # noqa: E402


def _active() -> str:
    with connect() as conn:
        return tile_world.active_map_id(conn)


def _draft() -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (tile_world.SETUP_DRAFT_MAP_KEY,)).fetchone()
        return str(row[0]) if row else ""


def _start(name: str, map_id: str = "") -> None:
    options = {"player_name": name, "start_location": "Low Gate", "special_ability_origin": "none"}
    if map_id:
        options["world_map_id"] = map_id
    world.start_playthrough(options)


def _roll(seed: int) -> str:
    return tile_world.generate_scaled_world(preset_id="frontier_any", seed=seed)["id"]


class SetupRollIsADraftWhileAGameIsLive(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with connect() as conn:
            conn.execute("DELETE FROM world_maps")
            conn.execute(
                "DELETE FROM settings WHERE key IN ('active_world_map_id', 'setup_complete', ?, ?)",
                (tile_world.CAMPAIGN_MAP_KEY, tile_world.SETUP_DRAFT_MAP_KEY),
            )
        self.game_map = _roll(101)
        _start("Ash")

    def test_first_roll_without_a_live_game_is_active_at_once(self):
        self.assertEqual(_active(), self.game_map)
        self.assertEqual(_draft(), "")

    def test_opening_new_game_and_going_back_keeps_the_live_map(self):
        rolled = _roll(202)
        self.assertEqual(_active(), self.game_map)
        self.assertEqual(_draft(), rolled)
        with connect() as conn:
            self.assertEqual(tile_world.pinned_map_id(conn), self.game_map)
        saved = [r["id"] for r in world.export_world()["tables"]["world_maps"]]
        self.assertIn(self.game_map, saved)
        self.assertNotIn(rolled, saved)

    def test_start_promotes_the_map_the_screen_showed(self):
        first = _roll(303)
        second = _roll(404)
        _start("Bryn", first)
        self.assertEqual(_active(), first)
        self.assertEqual(_draft(), "")
        with connect() as conn:
            self.assertEqual(tile_world.pinned_map_id(conn), first)
        with connect() as conn:
            self.assertNotIn(second, [r[0] for r in conn.execute("SELECT id FROM world_maps")])

    def test_start_without_a_named_map_uses_the_last_draft(self):
        rolled = _roll(505)
        _start("Cato")
        self.assertEqual(_active(), rolled)

    def test_a_named_map_that_is_gone_falls_back_to_the_draft(self):
        rolled = _roll(606)
        _start("Dara", "world-missing")
        self.assertEqual(_active(), rolled)


if __name__ == "__main__":
    unittest.main()
