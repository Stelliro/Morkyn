"""
Growth speed is applied once.

The Miriam Shaw save: one prayer gave a brand-new "Prayer" skill at 8. The dice
roller rolled a moderate gain (1d2 = 2) and multiplied it by the world's "very
fast" skill growth (x2.2 -> 4); _apply_skills then scaled the 4 by the same
growth speed again (-> 8). XP had the same second scaling.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-growth-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import db, world  # noqa: E402
from app.db import connect  # noqa: E402


class TestGrowthIsAppliedOnce(unittest.TestCase):
    def setUp(self):
        db.init_db()
        world.start_playthrough(
            {
                "player_name": "Tomas Reed",
                "start_location": "Low Gate",
                "special_ability_origin": "none",
                "skill_growth_speed": "very fast",
                "xp_growth_speed": "very fast",
                "world_style": "frontier dark fantasy",
            }
        )

    def _roll_and_apply(self, result):
        with connect() as conn:
            options = world._settings(conn).get("playthrough_options") or {}
            report = world.resolve_turn_bands(conn, result, turn=2, options=options)
            world._apply_skills(conn, result.get("skill_changes") or [])
            conn.commit()
        return report

    def test_a_rolled_skill_gain_lands_at_the_rolled_value(self):
        result = {"skill_changes": [{"name": "prayer", "delta_band": "moderate"}]}
        report = self._roll_and_apply(result)
        rolled = next(r for r in report["rolls"] if r["kind"] == "skill_gain")
        self.assertTrue(rolled.get("growth_applied"))
        with connect() as conn:
            row = conn.execute("SELECT value FROM player_skills WHERE name = 'Prayer' COLLATE NOCASE").fetchone()
        self.assertEqual(int(row["value"]), max(1, int(rolled["value"])))

    def test_an_unrolled_number_is_still_scaled_once(self):
        with connect() as conn:
            world._apply_skills(conn, [{"name": "rope work", "delta": 2}])
            conn.commit()
            row = conn.execute("SELECT value FROM player_skills WHERE name = 'Rope Work' COLLATE NOCASE").fetchone()
        self.assertEqual(int(row["value"]), world._scaled_delta(2, "very fast"))

    def test_rolled_xp_is_flagged_as_already_scaled(self):
        result = {"player": {"xp_band": "small"}}
        with connect() as conn:
            options = world._settings(conn).get("playthrough_options") or {}
            world.resolve_turn_bands(conn, result, turn=2, options=options)
        self.assertTrue(result["player"].get("_xp_delta_growth_applied"))



class TestGainsAreGroundedInTheDraft(unittest.TestCase):
    """The Miriam Shaw save: GRANT "prayer beads" from a draft that never mentioned beads."""

    FINAL = "You walk closer, beads clasped in your hands, and begin to pray."
    DRAFT = "You close the distance to Dockwick and begin your prayer in earnest."

    def setUp(self):
        db.init_db()
        world.start_playthrough({"player_name": "Tomas Reed", "start_location": "Low Gate", "special_ability_origin": "none"})

    def _filter(self, draft):
        with connect() as conn:
            return world._filter_inventory_changes(
                conn,
                [{"name": "prayer beads", "quantity_delta": 2}],
                narration=self.FINAL,
                player_input="i start praying as i move closer",
                draft_narration=draft,
            )

    def test_an_item_the_draft_never_named_is_not_granted(self):
        self.assertEqual(self._filter(self.DRAFT), [])

    def test_an_item_the_draft_names_still_can_be(self):
        kept = self._filter("Dockwick presses a string of prayer beads into your hands.")
        self.assertEqual([c["name"] for c in kept], ["prayer beads"])

if __name__ == "__main__":
    unittest.main()
