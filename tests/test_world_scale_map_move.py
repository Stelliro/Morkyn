"""A map move on a world-scale map is checked against the map's own size (playtest #160).

A world-scale map (16383 x 16383) stores no grid: its cells are generated from
the seed. ``move_player`` and ``restore_player_position`` read the bounds from
``_rebuild_grid``, which is empty for such a map, so width = height = 0 and
every POST /api/tiles/map/move answered 400 "Destination out of bounds"
(cc87dd29, server.log 1339-1343, five moves in a row with the player at
(1274, 3053)). The bounds now come from the map's width and height and the
cell from ``_cell_at`` (world_scale.world_cell), the reading walk_steps and
local_map_view already used.

Run:  cd tests && python -m unittest test_world_scale_map_move
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-world-move-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import db, tile_world  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()


def _walkable_step(chart: dict) -> tuple[int, int]:
    px, py = int(chart["player"]["x"]), int(chart["player"]["y"])
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        if tile_world.tile_walkable(tile_world._cell_at(chart, px + dx, py + dy)):
            return px + dx, py + dy
    raise AssertionError("the generated world left the player with no walkable neighbour")


class WorldScaleMapMoveTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        tile_world.generate_scaled_world(preset_id="ash_plain", seed=4, density_percent=20, notice_percent=0)
        self.chart = tile_world.get_map(None)
        self.assertEqual(self.chart.get("scale"), "world")
        self.assertEqual(tile_world._rebuild_grid(self.chart), [], "the fixture must store no grid, as in the playtest")

    def test_a_step_to_a_walkable_neighbour_moves_the_player(self):
        tx, ty = _walkable_step(self.chart)
        view = tile_world.move_player(None, tx, ty)
        self.assertEqual(view["travel"]["to"], [tx, ty])
        after = tile_world.get_map(None)
        self.assertEqual((int(after["player"]["x"]), int(after["player"]["y"])), (tx, ty))
        self.assertFalse(after.get("tiles"), "a world-scale map still stores no tiles after a move")

    def test_the_playtest_position_is_in_bounds(self):
        # cc87dd29: the player stood at (1274, 3053) on the 16383-wide map.
        chart = dict(self.chart)
        chart["player"] = {"x": 1274, "y": 3053}
        tile_world._save_map_payload(chart)
        chart = tile_world.get_map(None)
        tx, ty = _walkable_step(chart)
        try:
            tile_world.move_player(None, tx, ty)
        except ValueError as exc:
            self.assertNotIn("out of bounds", str(exc))
            raise
        after = tile_world.get_map(None)
        self.assertEqual((int(after["player"]["x"]), int(after["player"]["y"])), (tx, ty))

    def test_restore_puts_the_marker_back(self):
        px, py = int(self.chart["player"]["x"]), int(self.chart["player"]["y"])
        tx, ty = _walkable_step(self.chart)
        tile_world.move_player(None, tx, ty)
        tile_world.restore_player_position(None, px, py)
        after = tile_world.get_map(None)
        self.assertEqual((int(after["player"]["x"]), int(after["player"]["y"])), (px, py))

    def test_the_move_route_takes_an_arrow_step(self):
        # The playtest path: POST /api/tiles/map/move with a one-step delta.
        from app import main

        px, py = int(self.chart["player"]["x"]), int(self.chart["player"]["y"])
        tx, ty = _walkable_step(self.chart)
        out = main.api_tile_map_move(main.MapMoveRequest(dx=tx - px, dy=ty - py))
        self.assertTrue(out.get("ok", True))
        after = tile_world.get_map(None)
        self.assertEqual((int(after["player"]["x"]), int(after["player"]["y"])), (tx, ty))

    def test_off_the_map_is_still_out_of_bounds(self):
        width = int(self.chart["width"])
        with self.assertRaisesRegex(ValueError, "out of bounds"):
            tile_world.move_player(None, width, 0)
        with self.assertRaisesRegex(ValueError, "out of bounds"):
            tile_world.restore_player_position(None, -1, 0)


if __name__ == "__main__":
    unittest.main()
