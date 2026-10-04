"""The dice_rolls audit table mirrors the turns that actually applied.

Two gaps:

* `play_turn` resolved the player's skill check with an unseeded
  `random.Random()`, so a rewind + regenerate of the same input rolled a
  different d20 (and could apply a different injury) while every band roll
  reproduced exactly; and that d20 was never written to `dice_rolls`, so
  `/api/dice/recent?turn=N` showed the gold and not the check that decided
  the scene.
* `rewind_last_turn` deleted the journal, summaries and model logs for the
  rewound turn but left `dice_rolls` alone, so each regenerate appended the
  same rows again and the per-turn feed showed three identical gold rolls for
  a turn that paid once.

Run:  python -m unittest tests.test_dice_rolls_mirror_applied_turns
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-dice-mirror-test-"))
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

from app import db, rng as rng_mod, skill_checks, world  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world():
    db.init_db()
    rng_mod.reset_seed_cache()
    world.start_playthrough(
        {
            "player_name": "Ash",
            "start_location": "Low Gate",
            "special_ability_origin": "none",
            # Off in the shipped defaults; the check path is what is under test.
            "dice_checks_enabled": True,
        }
    )


_SCENE = " ".join(["The lock is old and the rain keeps falling on the stones."] * 12)


def _turn(narration: str = _SCENE, **extra) -> dict:
    turn = {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
    }
    turn.update(extra)
    return turn


def _play(player_input: str, turn: dict | None = None) -> dict:
    with mock.patch.object(world, "generate_turn", return_value=turn or _turn()):
        return world.play_turn(player_input)


def _regenerate(turn: dict | None = None) -> dict:
    with mock.patch.object(world, "generate_turn", return_value=turn or _turn()):
        return world.regenerate_last_turn()


def _rows(where: str = "1=1", *params) -> list[dict]:
    with db.connect() as conn:
        return [dict(r) for r in conn.execute(f"SELECT * FROM dice_rolls WHERE {where} ORDER BY id", params).fetchall()]


class TestSkillCheckDiceAreSeededAndRecorded(unittest.TestCase):
    """#1: the check d20 comes from the campaign seed and lands in dice_rolls."""

    def test_regenerate_rolls_the_same_natural(self):
        _fresh_world()
        seen: list[object] = []
        real = skill_checks.resolve_check

        def spy(*args, **kwargs):
            rng = kwargs.get("rng")
            seen.append(rng.getstate() if rng is not None else None)
            return real(*args, **kwargs)

        with mock.patch.object(skill_checks, "resolve_check", side_effect=spy):
            first = _play("I pick the lock on the gate")
            self.assertTrue(first.get("skill_checks"), "the action must trigger a server-side check")
            naturals = [first["skill_checks"][0]["natural"]]
            for _ in range(3):
                again = _regenerate()
                self.assertTrue(again.get("skill_checks"))
                naturals.append(again["skill_checks"][0]["natural"])
        self.assertTrue(seen and all(s is not None for s in seen), "resolve_check must receive a seeded rng")
        self.assertEqual(len(set(seen)), 1, "the same turn + input must seed the check identically")
        self.assertEqual(len(set(naturals)), 1, f"a regenerate must reproduce the d20, got {naturals}")

    def test_the_check_is_in_the_dice_audit_for_its_turn(self):
        _fresh_world()
        payload = _play("I pick the lock on the gate")
        check = payload["skill_checks"][0]
        turn = world._current_turn_number()
        rows = _rows("turn = ? AND kind = 'check'", turn)
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["source"], "skill_check")
        self.assertEqual(rows[0]["notation"], f"1{check['dice']}")
        self.assertEqual(rows[0]["raw_total"], int(check["natural"]))
        self.assertEqual(rows[0]["value"], int(check["total"]))
        feed = rng_mod.recent_rolls(turn=turn)
        self.assertTrue(any(r.get("kind") == "check" for r in feed), feed)

    def test_two_checks_on_one_turn_do_not_share_a_stream(self):
        """Index in the salt: a second check on the same turn is its own roll."""
        seed = rng_mod.seed_from("fixed")
        a = rng_mod.rng_for("skill_check", turn=4, seed=seed, salt="0:lockpicking").random()
        b = rng_mod.rng_for("skill_check", turn=4, seed=seed, salt="1:lockpicking").random()
        self.assertNotEqual(a, b)


class TestRewindDropsTheRewoundTurnsDice(unittest.TestCase):
    """#2: regenerating a turn N leaves exactly one set of rows for turn N."""

    def _banded(self) -> dict:
        return _turn(player={"gold_band": "moderate"})

    def test_regenerate_leaves_a_single_pass_of_rows(self):
        _fresh_world()
        _play("I look around", self._banded())
        turn = world._current_turn_number()
        single = _rows("turn = ?", turn)
        self.assertTrue(single, "the banded turn must record its gold roll")
        _regenerate(self._banded())
        _regenerate(self._banded())
        self.assertEqual(world._current_turn_number(), turn)
        after = _rows("turn = ?", turn)
        self.assertEqual(len(after), len(single), f"expected one pass of rows, got {len(after)}")
        self.assertEqual(
            [(r["tag"], r["value"]) for r in after],
            [(r["tag"], r["value"]) for r in single],
            "the regenerated turn rolls the same amounts and records them once",
        )

    def test_rewind_keeps_earlier_turns_dice(self):
        _fresh_world()
        _play("I look around", self._banded())
        first_turn = world._current_turn_number()
        _play("I look again", self._banded())
        second_turn = world._current_turn_number()
        self.assertTrue(_rows("turn = ?", second_turn))
        world.rewind_last_turn()
        self.assertTrue(_rows("turn = ?", first_turn), "rows for the turn that still applied stay")
        self.assertEqual(_rows("turn = ?", second_turn), [], "rows for the rewound turn go")


if __name__ == "__main__":
    unittest.main()
