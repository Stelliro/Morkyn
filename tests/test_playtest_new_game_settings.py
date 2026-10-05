"""Smoke test after #1-#27: a new game must not inherit the last game's live scene state.

Game 1 (Overpowered) ended inside a pursuit, settings.scene_thread =
{"doing": "follow the trail of whoever set", "where": "Spindle at Edge"}.
Start on the same database for game 2 (Frontier) cleared the tables but not
the per-turn settings rows, so the opening draft got that thread as its GOAL
and moved the new player to "The Spindle at Edge", a place from game 1.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-new-game-settings-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402


def _start(name: str) -> None:
    world.start_playthrough({"player_name": name, "start_location": "Low Gate", "special_ability_origin": "none"})


def _settings() -> dict[str, str]:
    with connect() as conn:
        return {r[0]: r[1] for r in conn.execute("SELECT key, value FROM settings")}


class ANewGameStartsWithoutTheLastGamesScene(unittest.TestCase):
    def setUp(self):
        db.init_db()
        _start("First Player")
        thread = {
            "version": 1,
            "doing": "follow the trail of whoever set",
            "target": "the trail of whoever set",
            "target_code": "",
            "with": [],
            "quest": {},
            "source": "player",
            "started_turn": 5,
            "touched_turn": 5,
            "where": "Spindle at Edge",
        }
        with connect() as conn:
            for key, value in (
                ("scene_thread", thread),
                ("last_social", {"npc": "A"}),
                ("player_conditions", [{"name": "bruised"}]),
                ("association_heat", {"A": 3}),
                ("area_reputation", {"L4": 2}),
            ):
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value))
                )

    def test_the_pursuit_and_scene_rows_are_gone(self):
        _start("Second Player")
        rows = _settings()
        self.assertNotIn("scene_thread", rows)
        for key in ("last_social", "player_conditions", "association_heat", "area_reputation"):
            self.assertNotIn(key, rows, key)

    def test_the_old_place_is_not_in_the_new_game(self):
        _start("Second Player")
        self.assertNotIn("Spindle at Edge", json.dumps(world.get_state().get("scene_thread") or {}))


if __name__ == "__main__":
    unittest.main()
