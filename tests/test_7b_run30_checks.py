"""7B run 30 (Qwen2.5 7B on MLE, agent as player): a check's outcome reaches the prose, traps are not mining."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

T10 = ("I carry the two traps to the tunnels by the brine vats and set the first one where the earth is freshest, "
       "then the second a stride further along.")
T10_PROSE = (
    "You carry the two moles' pits to the underground passageways by the brine vats and place the first one where "
    "the ground is freshest. You then place the second one a stride further along. The damp air smells of seaweed "
    "and salt.\n\nDunstan [[A]] watches from a short distance, his brow furrowed in concentration."
)
MISHAP = {
    "enabled": True,
    "skill": {"code": "mining", "name": "Mining"},
    "outcome": "failure",
    "degree": "unskilled_mishap",
    "mishap": True,
    "injury": {"kind": "self_injury", "limb": "leg", "severity": False, "lasting": False, "health_delta": -1,
               "summary": "Botched Mining: you hurt your leg.", "combat_penalty": {}},
    "display_block": "Total: 2 | Result: failure\nBotched Mining: you hurt your leg.",
}


class TrapsAreNotMining(unittest.TestCase):
    """T3, T6, T7, T10: a tunnel named in a trap line rolled mining."""

    def code(self, line):
        from app.skill_checks import infer_check_from_action

        return (infer_check_from_action(line, {}) or {}).get("skill_code")

    def test_trap_setting_is_survival(self):
        self.assertEqual(self.code(T10), "survival")
        self.assertEqual(self.code("I take a trap from the pile and set it at the mouth of the fresh tunnel."), "survival")

    def test_a_named_tunnel_is_no_dig(self):
        self.assertNotEqual(self.code("I push my arm into the soft earth to feel which way the tunnel runs."), "mining")
        self.assertEqual(self.code("I shore up the old tunnel with planks before it caves."), "mining")
        self.assertEqual(self.code("I mine for copper in the cut."), "mining")


class TheRollSaysWhatItWasFor(unittest.TestCase):
    """T10: the narrator saw only 'mining, failure' and an injury label."""

    def test_clause_and_view(self):
        from app import prompts
        from app.skill_checks import check_for_clause

        clause = check_for_clause(T10, "survival")
        self.assertIn("set the first one", clause)
        row = prompts._mechanics_view({"mechanics_context": {"resolved_checks": [{**MISHAP, "for": clause}]}})[
            "resolved_checks"][0]
        self.assertEqual(row["for"], clause)
        self.assertTrue(row["means"])
        self.assertIs(row["mishap"], True)
        self.assertEqual(row["injury"], "Botched Mining: you hurt your leg.")

    def test_the_ask_names_for_and_injury(self):
        source = Path(ROOT / "app" / "prompts.py").read_text(encoding="utf-8")
        self.assertIn("A row's for is the player's own act", source)


class AnUnshownHurtIsNotApplied(unittest.TestCase):
    """T10: -1 HP 'you hurt your leg' while the prose set both traps without trouble."""

    def test_dropped_when_unshown(self):
        from app.world import drop_unshown_check_injuries

        out = drop_unshown_check_injuries([dict(MISHAP)], T10_PROSE)
        self.assertIsNone(out[0]["injury"])
        self.assertEqual(out[0]["injury_unshown"]["limb"], "leg")
        self.assertNotIn("hurt your leg", out[0]["display_block"])
        self.assertEqual(out[0]["outcome"], "failure")

    def test_kept_when_shown(self):
        from app.world import drop_unshown_check_injuries

        shown = T10_PROSE + " The earth gives under you and your leg twists; you wince."
        self.assertIsNotNone(drop_unshown_check_injuries([dict(MISHAP)], shown)[0]["injury"])
        self.assertIsNotNone(drop_unshown_check_injuries([dict(MISHAP)], "")[0]["injury"])

    def test_the_turn_has_no_health_loss(self):
        from app.skill_checks import apply_check_to_turn
        from app.world import drop_unshown_check_injuries

        turn = {"narration": T10_PROSE, "player": {}}
        for check in drop_unshown_check_injuries([dict(MISHAP)], T10_PROSE):
            turn = apply_check_to_turn(turn, check)
        self.assertFalse(int((turn.get("player") or {}).get("health_delta") or 0))
        self.assertFalse([j for j in turn.get("journal") or [] if j.get("kind") == "injury"])


if __name__ == "__main__":
    unittest.main()
