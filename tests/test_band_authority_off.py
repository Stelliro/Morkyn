"""Band authority "off" still turns a band into an amount.

The prompt and the DSL only emit bands now (GOLD small, GRANT rope QTY small,
SKILL Climbing DELTA small). With `band_authority` set to "off",
`resolve_turn_bands` returned before translating any of them, so every band
was silently dropped: the prose said the player was paid and found rope, and
the record showed nothing. Off mode now maps each band to its fixed minimum
(no dice), consumes the band key, and still records the mapping.

Run:  python -m unittest tests.test_band_authority_off
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-band-off-test-"))
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

from app import db, rng, world  # noqa: E402
from app.turn_dsl import parse_dsl_turn  # noqa: E402


def setUpModule():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()


def _fresh_world():
    db.init_db()
    rng.reset_seed_cache()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


_SCENE = " ".join(["The merchant counts out your pay and hands over the rope."] * 12)
_DSL = f"===NAR===\n{_SCENE}\n===OPS===\nGOLD small\nGRANT rope QTY small\nSKILL Climbing DELTA small\n"


def _player() -> dict:
    with db.connect() as conn:
        return dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone())


def _skill_value(name: str):
    with db.connect() as conn:
        row = conn.execute("SELECT value FROM player_skills WHERE lower(name) = lower(?)", (name,)).fetchone()
    return int(row["value"]) if row else None


def _rope_qty():
    with db.connect() as conn:
        row = conn.execute("SELECT quantity FROM inventory WHERE lower(name) = 'rope'").fetchone()
    return int(row["quantity"]) if row else None


class TestFixedMagnitude(unittest.TestCase):
    def test_minimum_of_a_notation(self):
        self.assertEqual(rng.notation_minimum("2d6+3"), 5)
        self.assertEqual(rng.notation_minimum("1d4"), 1)
        self.assertEqual(rng.notation_minimum("4d6kh3"), 3)
        self.assertEqual(rng.notation_minimum("0"), 0)

    def test_fixed_is_deterministic_and_conservative(self):
        a = rng.fixed_magnitude("gold", "small")
        b = rng.fixed_magnitude("gold", "small")
        self.assertEqual(a["value"], b["value"])
        self.assertTrue(a["fixed"])
        self.assertEqual(a["rolls"], [])
        rolled_floor = rng.notation_minimum(rng.magnitude_table("gold")["bands"]["small"])
        self.assertEqual(a["value"], rolled_floor)
        self.assertGreater(a["value"], 0)
        self.assertLess(rng.fixed_magnitude("gold", "small", negative=True)["value"], 0)
        self.assertEqual(rng.fixed_magnitude("xp", "none")["value"], 0)
        self.assertIn("fixed", rng.explain(a))


class TestOffModeTranslatesBands(unittest.TestCase):
    def test_resolve_turn_bands_off_maps_every_band(self):
        _fresh_world()
        turn = parse_dsl_turn(_DSL, player_input="I collect my pay")
        self.assertEqual(turn["player"].get("gold_band"), "small")
        self.assertFalse(turn["player"].get("gold_delta"), "the DSL emits the band only")
        with db.connect() as conn:
            report = world.resolve_turn_bands(conn, turn, turn=1, options={"band_authority": "off"})
        self.assertEqual(report["mode"], "off")
        self.assertGreater(turn["player"]["gold_delta"], 0)
        self.assertNotIn("gold_band", turn["player"])
        self.assertGreater(turn["inventory_changes"][0]["quantity_delta"], 0)
        self.assertNotIn("quantity_band", turn["inventory_changes"][0])
        self.assertGreater(turn["skill_changes"][0]["delta"], 0)
        self.assertNotIn("delta_band", turn["skill_changes"][0])
        self.assertEqual(len(report["rolls"]), 3)
        self.assertTrue(all(r.get("fixed") for r in report["rolls"]))
        self.assertEqual(len(report["lines"]), 3)

    def test_off_keeps_explicit_numbers_and_negative_bands(self):
        _fresh_world()
        turn = {"player": {"gold_delta": 7, "health_band": "-small"}}
        with db.connect() as conn:
            world.resolve_turn_bands(conn, turn, turn=1, options={"band_authority": "off"})
        self.assertEqual(turn["player"]["gold_delta"], 7, "a bare number still passes through untouched")
        self.assertLess(turn["player"]["health_delta"], 0)

    def test_apply_turn_in_off_mode_pays_grants_and_teaches(self):
        _fresh_world()
        before = _player()
        # A new skill inserts at max(delta, 1), which cannot tell a dropped
        # delta from an applied one; an existing rank can.
        with db.connect() as conn:
            conn.execute("INSERT INTO player_skills (name, value, notes) VALUES ('Climbing', 3, '')")
        turn = parse_dsl_turn(_DSL, player_input="I collect my pay")
        turn["self_check"] = {"passed": True, "issues_found": [], "corrections_made": []}
        turn["turn_summary"] = "paid"
        with mock.patch.dict(os.environ, {"AI_RPG_BAND_AUTHORITY": "off"}):
            state = world.apply_turn(turn, "I collect my pay")
        after = _player()
        self.assertGreater(int(after["gold"]), int(before["gold"]), "GOLD small must pay something")
        self.assertIsNotNone(_rope_qty(), "GRANT rope must create the row")
        self.assertGreaterEqual(_rope_qty(), 1)
        self.assertGreater(_skill_value("Climbing"), 3, "SKILL Climbing DELTA small must raise the rank")
        dice = state.get("dice_rolls") or {}
        self.assertEqual(dice.get("mode"), "off")
        self.assertTrue(dice.get("rolls"), "the fixed mapping is still reported on the state")
        with db.connect() as conn:
            rows = conn.execute("SELECT COUNT(*) AS n FROM dice_rolls WHERE turn = ?", (dice.get("turn"),)).fetchone()
        self.assertEqual(int(rows["n"]), 3, "and recorded in the audit table")


if __name__ == "__main__":
    unittest.main()
