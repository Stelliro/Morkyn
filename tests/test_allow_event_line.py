"""A death the roll did not allow is refused when the player's own line names the person (#129).

Final live replay, 2026-10-24 (Hermes 3 8B, scratchpad live/final T3): 'i shoot Nate' rolled
ranged critical_failure with no attack target, because the roster placed Nate in the town while
the prose had him in the clinic, so attack_intent found nobody here to ask about. The prose killed
him, the died pair confirmed it, and allow_event let it stand: no roll carried his code.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import interpreter as I  # noqa: E402

NATE = {"kind": I.KIND_DIED, "subject": {"type": "npc", "code": "A", "name": "Nate"}, "status": "proposed"}


def _check(skill: str, outcome: str, attack: str = "") -> dict:
    check = {"skill": {"code": skill}, "outcome": outcome, "natural": 1 if "fail" in outcome else 15}
    if attack:
        check["attack"] = {"code": attack, "name": attack}
    return check


class TheLineNamesTheDead(unittest.TestCase):
    def test_final_replay_t3_a_failed_unaimed_shot_refuses_the_death(self):
        turn = {"skill_checks": [_check("ranged", "critical_failure")]}
        self.assertEqual(I.allow_event(NATE, turn, "i shoot Nate"), "attack roll critical_failure")

    def test_by_code_and_reference_too(self):
        turn = {"skill_checks": [_check("melee", "failure")]}
        self.assertTrue(I.allow_event(NATE, turn, "i stab @A"))
        self.assertTrue(I.allow_event(NATE, turn, "i stab [[A]] in the back"))

    def test_a_line_that_does_not_name_him_changes_nothing(self):
        turn = {"skill_checks": [_check("ranged", "failure")]}
        self.assertEqual(I.allow_event(NATE, turn, "i shoot the raider"), "")
        self.assertEqual(I.allow_event(NATE, turn, ""), "")
        # A name inside another word is not the name.
        self.assertEqual(I.allow_event(NATE, turn, "i shoot at the Natera sign"), "")

    def test_a_success_stands(self):
        turn = {"skill_checks": [_check("ranged", "success")]}
        self.assertEqual(I.allow_event(NATE, turn, "i shoot Nate"), "")

    def test_a_roll_aimed_at_someone_else_is_not_his(self):
        turn = {"skill_checks": [_check("melee", "failure", attack="C")]}
        self.assertEqual(I.allow_event(NATE, turn, "i shove Nate aside and stab Kim"), "")

    def test_a_non_combat_roll_is_not_an_attack(self):
        turn = {"skill_checks": [_check("persuasion", "failure")]}
        self.assertEqual(I.allow_event(NATE, turn, "i tell Nate to back off"), "")

    def test_an_aimed_roll_still_decides_first(self):
        turn = {"skill_checks": [_check("ranged", "success", attack="A"), _check("melee", "failure")]}
        self.assertEqual(I.allow_event(NATE, turn, "i shoot Nate"), "")


if __name__ == "__main__":
    unittest.main()
