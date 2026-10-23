"""A rewind puts back everything a turn changed in place: the clock, the
weather, the fight record, the map marker (playtest #159), and History can go
back several turns at once (playtest #158).

The Linux .deb playtest (Hermes 3 8B, game cc87dd29) rewound from turn 14 to
turn 4 with ten presses of Undo; the state said turn 4 but the clock read
minute 594 (turn 14's end), not 506 (turn 4's end), and the closed fight with
Beth from turn 13 was still the active_encounter. The turn-5 record held only
pacing.turn: play_turn moves the clock before apply_turn takes the snapshot,
and the clock, the weather and the fight record were never in it.

Run:  cd tests && python -m unittest test_rewind_turn_start_state
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-rewind-start-test-"))
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

from app import db, world  # noqa: E402

# The player's lines of turns 4, 13 and 14 in cc87dd29.
_LINES = ("hi", "i say hi to her", "i say hi to @Cbeth")
# The fight record turn 13 left behind (settings.active_encounter in the
# save after the rewind, trimmed).
_FIGHT = {
    "active": False,
    "updated_turn": 14,
    "closed_turn": 13,
    "outcome": "You left the place where the fight was.",
    "foes": [{"code": "B", "name": "Beth", "side": "theirs", "health": 20, "max_health": 21, "role": "doctor"}],
}
_RAIN = {"kind": "rain", "strength": 0.6, "minutes_active": 4, "label": "Rain", "changed": True}
_SCENE = " ".join(["The clinic is quiet and the morning light lies on the cracked floor."] * 12)


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world():
    db.init_db()
    world.start_playthrough({"player_name": "Will Tanaka", "start_location": "Radiation Fenced Sanctuary", "special_ability_origin": "none"})


def _turn(narration: str) -> dict:
    return {
        "scene_plan": {"goal": "talk", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "dialogue",
    }


def _play(line: str, during=None) -> dict:
    """One turn with the model mocked; ``during`` writes inside the turn, after the snapshot."""
    def generate(*_args, **_kwargs):
        return _turn(_SCENE)

    original = world._write_turn_summary

    def summary_then(conn, *args, **kwargs):
        if during:
            during(conn)
        return original(conn, *args, **kwargs)

    with mock.patch.object(world, "generate_turn", side_effect=generate), mock.patch.object(
        world, "_write_turn_summary", side_effect=summary_then
    ):
        return world.play_turn(line)


def _clock() -> tuple[int, int]:
    with db.connect().closing() as conn:
        now = world.get_world_time(conn)
    return int(now["day"]), int(now["minute"])


def _turn_no() -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()["value"])


def _setting(key: str):
    with db.connect().closing() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _put_setting(conn, key: str, value) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def _point_back_to(turn: int) -> int:
    points = world.get_state().get("rewind_points") or []
    for point in points:
        if int(point.get("back_to_turn")) == turn:
            return int(point["id"])
    raise AssertionError(f"no rewind point back to turn {turn}: {points}")


class TestTheClockGoesBack(unittest.TestCase):
    def test_undo_puts_the_clock_back_to_the_turns_start(self):
        _fresh_world()
        _play(_LINES[0])
        before = _clock()
        _play(_LINES[2])
        self.assertGreater(_clock()[1], before[1], "the turn must spend minutes for this test to mean anything")
        world.rewind_last_turn()
        self.assertEqual(_clock(), before)

    def test_ten_undos_from_turn_14_reach_turn_4s_clock(self):
        # The tester's own path: turn 14 back to turn 4, one press at a time.
        _fresh_world()
        clocks = {}
        for _ in range(14):
            _play(_LINES[0])
            clocks[_turn_no()] = _clock()
        for _ in range(10):
            world.rewind_last_turn()
        self.assertEqual(_turn_no(), 4)
        self.assertEqual(_clock(), clocks[4], "turn 4's clock, not turn 14's")

    def test_a_wait_is_taken_back_with_its_hour(self):
        _fresh_world()
        _play(_LINES[0])
        before = _clock()
        with mock.patch.object(world, "generate_turn", return_value=_turn(_SCENE)):
            world.play_wait_turn(60)
        self.assertNotEqual(_clock(), before)
        world.rewind_last_turn()
        self.assertEqual(_clock(), before)


class TestWhatTheTurnWroteInPlaceGoesBack(unittest.TestCase):
    def test_fight_record_and_weather_written_in_the_turn_go_back(self):
        _fresh_world()
        _play(_LINES[0])
        weather_before = _setting("world_weather")
        # The encounter board writes its record every turn; turn 1 left a quiet one.
        fight_before = _setting("active_encounter")
        self.assertNotIn("Beth", str(fight_before))

        def fight_and_rain(conn):
            _put_setting(conn, "active_encounter", _FIGHT)
            _put_setting(conn, "world_weather", _RAIN)

        _play(_LINES[1], during=fight_and_rain)
        self.assertIn("Beth", str(_setting("active_encounter")))
        world.rewind_last_turn()
        self.assertEqual(_setting("active_encounter"), fight_before, "Beth's fight record from the rewound turn must go")
        self.assertEqual(_setting("world_weather"), weather_before)

    def test_the_players_own_settings_are_not_rewound(self):
        _fresh_world()
        _play(_LINES[0])

        def save_model_settings(conn):
            _put_setting(conn, "model_config", {"temperature": 0.3})

        _play(_LINES[1], during=save_model_settings)
        world.rewind_last_turn()
        self.assertEqual(json.loads(_setting("model_config")), {"temperature": 0.3})

    def test_the_map_marker_goes_back(self):
        _fresh_world()
        with db.connect().closing() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO world_maps (id, player_x, player_y) VALUES ('world-183003828-6ec3dfe7', 1274, 3053)"
            )
        _play(_LINES[0])

        def walk(conn):
            conn.execute("UPDATE world_maps SET player_x = 1280, player_y = 3060")

        _play(_LINES[1], during=walk)
        world.rewind_last_turn()
        with db.connect().closing() as conn:
            row = conn.execute("SELECT player_x, player_y FROM world_maps WHERE id = 'world-183003828-6ec3dfe7'").fetchone()
        self.assertEqual((row["player_x"], row["player_y"]), (1274, 3053))


class TestBackToATurnFromHistory(unittest.TestCase):
    def test_every_kept_turn_is_offered_with_the_turn_it_goes_back_to(self):
        _fresh_world()
        for _ in range(8):
            _play(_LINES[0])
        points = world.get_state().get("rewind_points") or []
        self.assertGreater(len(points), 5, "History needs more than the Rewind card's last five")
        for point in points:
            self.assertEqual(int(point["back_to_turn"]), int(point["turn"]) - 1)

    def test_one_jump_equals_the_presses(self):
        # Turn 14 back to turn 4 in one go: each record holds only its own
        # turn, so a setting only turn 13 changed must go back as well.
        _fresh_world()
        clocks = {}
        fights = {}
        for number in range(1, 15):
            during = (lambda conn: _put_setting(conn, "active_encounter", _FIGHT)) if number == 13 else None
            _play(_LINES[0], during=during)
            clocks[_turn_no()] = _clock()
            fights[_turn_no()] = _setting("active_encounter")
        self.assertIn("Beth", str(fights[13]))
        state = world.rewind_last_turn(_point_back_to(4))
        self.assertEqual(_turn_no(), 4)
        self.assertEqual(state.get("rewound_turn"), 5)
        self.assertEqual(_clock(), clocks[4])
        self.assertEqual(_setting("active_encounter"), fights[4], "turn 13's fight record must go with the jump")
        self.assertNotIn("Beth", str(_setting("active_encounter")))
        points = world.get_state().get("rewind_points") or []
        self.assertTrue(points and max(int(p["turn"]) for p in points) == 4, points)


class TestHistoryOffersTheWayBack(unittest.TestCase):
    """The page side of #158: History and the scene history draw the button, and it asks first."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    def _function(self, name: str) -> str:
        start = self.js.index(f"function {name}(")
        end = self.js.index("\nfunction ", start + 1)
        return self.js[start:end]

    def test_each_history_turn_draws_back_to_this_turn(self):
        self.assertIn("historyRewindButtonHtml(group.turn)", self._function("renderHistory"))
        self.assertIn("historyRewindButtonHtml(group.turn)", self._function("sceneTurnHtml"))
        self.assertIn("back_to_turn", self._function("historyRewindPoint"))
        self.assertIn("Back to this turn", self._function("historyRewindButtonHtml"))

    def test_the_button_confirms_then_uses_the_rewind_endpoint(self):
        start = self.js.index('closest(".historyRewindButton")')
        handler = self.js[start:start + 600]
        self.assertIn("window.confirm(", handler)
        self.assertIn("cannot be undone", handler)
        self.assertIn("rewindTurn(backToTurn.dataset.snapshotId", handler)


if __name__ == "__main__":
    unittest.main()
