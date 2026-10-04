"""A retraced map step is not the same encounter roll forever.

`move_player` seeded the travel-encounter RNG from the map seed, the from/to
coordinates and len(visited). Once the surrounding tiles were revealed that
expression stopped moving, so walking the same step again replayed the
identical natural, kind, count and awareness d20: one extreme roll made a
road step a permanent ambush or permanently quiet, while the danger model
still moved with night, weather and fatigue. The pacing turn is now part of
the seed and reaches `roll_encounter`; the same turn still seeds the same
roll, which is what rewind needs.

Run:  python -m unittest tests.test_travel_encounter_turn_seed
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-travel-seed-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import db, rng, tile_world, world  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world():
    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _set_turn(turn: int) -> None:
    with db.connect() as conn:
        world._pacing_set(conn, "turn", int(turn))


_BLOCKED = {"void", "water", "lava", "cliff"}


def _walkable_neighbour(data: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    grid = tile_world._rebuild_grid(data)
    px = int((data.get("player") or {}).get("x") or 0)
    py = int((data.get("player") or {}).get("y") or 0)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        x, y = px + dx, py + dy
        if 0 <= y < len(grid) and 0 <= x < len(grid[y]):
            cell = grid[y][x]
            if bool(cell.get("walkable", True)) and str(cell.get("state") or "") not in _BLOCKED:
                return (px, py), (x, y)
    raise AssertionError("the generated map left the player with no walkable neighbour")


class TestTravelEncounterSeedCarriesTheTurn(unittest.TestCase):
    def test_roll_travel_encounter_moves_with_the_turn_and_holds_within_it(self):
        _fresh_world()
        cell = {"state": "road", "x": 10, "y": 4}
        same_a = tile_world.roll_travel_encounter(cell, minutes=20, seed=11, turn=3)
        same_b = tile_world.roll_travel_encounter(cell, minutes=20, seed=11, turn=3)
        later = tile_world.roll_travel_encounter(cell, minutes=20, seed=11, turn=4)
        self.assertIn("roll", same_a, "the assessed danger path must be the one under test")
        self.assertEqual(same_a["roll"], same_b["roll"], "the same turn seeds the same roll")
        self.assertNotEqual(same_a["roll"], later["roll"], "a later turn is a fresh roll of the same step")

    def test_move_player_passes_the_pacing_turn_and_retraces_differ_across_turns(self):
        _fresh_world()
        data = tile_world.generate_map(preset_id="forest_march", seed=7, width=12, height=12, assign_images=False)
        map_id = str(data["id"])
        start, step = _walkable_neighbour(tile_world.get_map(map_id))
        seen_turns: list[int] = []
        real = tile_world.roll_travel_encounter

        def spy(*args, **kwargs):
            seen_turns.append(int(kwargs.get("turn", -1)))
            return real(*args, **kwargs)

        def forth_and_back() -> dict:
            tile_world.move_player(map_id, *step)
            tile_world.move_player(map_id, *start)
            return tile_world.move_player(map_id, *step)["travel"]["encounter"]

        with mock.patch.object(tile_world, "roll_travel_encounter", side_effect=spy):
            _set_turn(3)
            forth_and_back()  # reveal the surroundings so len(visited) stops moving
            tile_world.move_player(map_id, *start)
            first = forth_and_back()
            tile_world.move_player(map_id, *start)
            again = forth_and_back()
            _set_turn(4)
            tile_world.move_player(map_id, *start)
            later = forth_and_back()

        self.assertTrue(seen_turns, "move_player must roll through roll_travel_encounter")
        self.assertEqual(sorted(set(seen_turns)), [3, 4], f"the pacing turn must reach the roll, got {seen_turns}")
        self.assertIn("roll", first)
        self.assertEqual(first["roll"], again["roll"], "the same step on the same turn reproduces (rewind)")
        self.assertNotEqual(first["roll"], later["roll"], "the same step on a later turn is a new roll")


if __name__ == "__main__":
    unittest.main()
