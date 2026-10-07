"""Review of playtest #25: a save never loses the map its campaign started on.

Opening New game rolls a fresh world map and makes it the active one at once,
before Start (static/app.js showSetupWizard -> rollNewGameMap ->
POST /api/tiles/generate). A player who then goes back and keeps playing the
live game is saved with that active pointer. With saves cut down to "only the
active map", that save would have carried the unused setup roll and not the
campaign's own map, and the next Start would have pruned the real one from the
live database. The map is pinned at Start; saves and pruning keep it.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-map-pin-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, tile_world, world  # noqa: E402
from app.db import connect  # noqa: E402


def _add_map(conn, map_id: str, created: str) -> None:
    conn.execute(
        "INSERT INTO world_maps (id, seed, width, height, tiles_json, created_at) VALUES (?, 7, 16383, 16383, '[]', ?)",
        (map_id, created),
    )


def _activate(conn, map_id: str) -> None:
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_world_map_id', ?)", (map_id,))


def _ids() -> list[str]:
    with connect() as conn:
        return sorted(r[0] for r in conn.execute("SELECT id FROM world_maps"))


def _start(name: str) -> None:
    world.start_playthrough({"player_name": name, "start_location": "Low Gate", "special_ability_origin": "none"})


class TheCampaignMapIsPinned(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with connect() as conn:
            conn.execute("DELETE FROM world_maps")
            conn.execute("DELETE FROM settings WHERE key IN ('active_world_map_id', ?)", (tile_world.CAMPAIGN_MAP_KEY,))
            _add_map(conn, "world-game-a", "2026-10-01 10:00:00")
            _add_map(conn, "world-old-reroll", "2026-07-01 10:00:00")
            _activate(conn, "world-game-a")
        _start("Ash")

    def _open_new_game_and_go_back(self) -> None:
        # What the setup screen does on open: a fresh map, active at once.
        with connect() as conn:
            _add_map(conn, "world-setup-roll", "2026-10-02 10:00:00")
            _activate(conn, "world-setup-roll")

    def test_start_pins_the_map_and_prunes_the_rest(self):
        self.assertEqual(_ids(), ["world-game-a"])
        with connect() as conn:
            self.assertEqual(tile_world.pinned_map_id(conn), "world-game-a")

    def test_a_save_after_a_stray_setup_roll_still_carries_the_campaign_map(self):
        self._open_new_game_and_go_back()
        saved = [r["id"] for r in world.export_world()["tables"]["world_maps"]]
        self.assertIn("world-game-a", saved)
        self.assertIn("world-setup-roll", saved)

    def test_the_saved_slot_restores_the_campaign_map_after_the_next_game(self):
        self._open_new_game_and_go_back()
        world.save_campaign_slot("game-a")
        _start("Bryn")  # the setup roll is now game B's map
        self.assertEqual(_ids(), ["world-setup-roll"])
        world.load_campaign_slot("game-a")
        self.assertIn("world-game-a", _ids())

    def test_a_game_from_before_pins_keeps_its_map_through_a_real_setup_roll(self):
        # Game 2 was started before maps were pinned.
        with connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = ?", (tile_world.CAMPAIGN_MAP_KEY,))
        rolled = tile_world.generate_scaled_world(preset_id="frontier_any", seed=4321)
        with connect() as conn:
            # The roll is a setup draft while the game is live (playtest #64).
            self.assertEqual(tile_world.active_map_id(conn), "world-game-a")
            self.assertNotEqual(rolled["id"], "world-game-a")
            self.assertEqual(tile_world.pinned_map_id(conn), "world-game-a")
        saved = [r["id"] for r in world.export_world()["tables"]["world_maps"]]
        self.assertIn("world-game-a", saved)

    def test_a_start_without_a_map_drops_the_last_games_pin(self):
        with connect() as conn:
            conn.execute("DELETE FROM world_maps")
        _start("Cato")
        with connect() as conn:
            self.assertEqual(tile_world.pinned_map_id(conn), "")


if __name__ == "__main__":
    unittest.main()
