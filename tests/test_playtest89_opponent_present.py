"""Playtest #89, reopened twice: a check's opponent is someone the engine places in the scene.

The stale opponent was fixed by phrasing three times (left behind, walked
away from, asked past). The engine already decides who is here this turn
(conversation.resolve: "present" and "addressed"), so the roll's other side
is drawn from that record and from nowhere else. Without a record (a fresh
game, a harness) the location's roster stands in, as before.

Run:  .venv\\Scripts\\python -m unittest tests.test_playtest89_opponent_present
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.skill_checks import infer_check_from_action  # noqa: E402

BRIDA = {"id": 1, "code": "A", "name": "Brida Marsh", "role": "flat-runner", "attitude": "warm", "stat_profile": {"charisma": 10}}
CLERK = {"id": 2, "code": "B", "name": "Oswin Pell", "role": "guild clerk", "attitude": "neutral", "stat_profile": {"charisma": 12}}
WARIN = {"id": 3, "code": "C", "name": "Warin Hale", "role": "dock hand", "attitude": "cold", "stat_profile": {"strength": 14}}


def _context(present: list[str] | None, addressed: list[str] | None = None, *, record: bool = True) -> dict:
    ctx = {
        "current_location": {"id": 7, "code": "L2", "name": "Guild Hall", "npcs": [BRIDA, CLERK, WARIN]},
        "locations": [{"id": 7, "code": "L2", "name": "Guild Hall", "npcs": [BRIDA, CLERK, WARIN]}],
        "settings": {"playthrough_options": {}},
    }
    if record:
        ctx["conversation_turn"] = {
            "addressed": list(addressed or []),
            "present": list(present or []),
            "listening": [c for c in (present or []) if c not in (addressed or [])],
            "rule": "name" if addressed else "none",
            "names": {"A": "Brida Marsh", "B": "Oswin Pell", "C": "Warin Hale"},
        }
    return ctx


class TheOtherSideIsSomeoneHere(unittest.TestCase):
    def test_the_partner_left_at_the_gate_is_not_the_opponent(self):
        # 7B Saltmarrow T14 / 8B run 5 T5: the roster still held Brida; the scene did not.
        line = "I leave Brida at the gate and walk to the guild hall and ask the clerk about the boats"
        check = infer_check_from_action(line, _context(present=["B"], addressed=["B"]))
        self.assertIsNotNone(check)
        self.assertEqual((check.get("opposition") or {}).get("name"), "Oswin Pell")

    def test_someone_named_but_elsewhere_rolls_against_nobody(self):
        # 7B run 5: Bryony (T23, T28), Warin (T41, T53, T84), Verity (T70), Abel (T76) were absent.
        line = "I ask Warin where he put the ledger"
        check = infer_check_from_action(line, _context(present=["B"], addressed=[]))
        self.assertIsNotNone(check)
        self.assertIsNone(check.get("opposition"))
        self.assertIsNone(check.get("npc_ref"))

    def test_a_shove_at_someone_absent_is_uncontested(self):
        line = "I shove Warin against the wall and demand he talk"
        check = infer_check_from_action(line, _context(present=["A", "B"], addressed=[]))
        self.assertIsNotNone(check)
        self.assertIsNone(check.get("opposition"))

    def test_the_companion_listening_is_not_the_one_asked(self):
        # Saltmarrow T72: the go-with companion rolled when the line asked someone else.
        line = "I ask the clerk what the salvage pays this week"
        check = infer_check_from_action(line, _context(present=["A", "B"], addressed=["B"]))
        self.assertIsNotNone(check)
        self.assertEqual((check.get("opposition") or {}).get("name"), "Oswin Pell")

    def test_someone_here_and_named_is_still_the_opponent(self):
        line = "I try to convince Warin to let me past"
        check = infer_check_from_action(line, _context(present=["B", "C"], addressed=["C"]))
        self.assertEqual((check.get("opposition") or {}).get("name"), "Warin Hale")

    def test_without_a_scene_record_the_roster_stands_in(self):
        line = "I try to convince Warin to let me past"
        check = infer_check_from_action(line, _context(present=None, record=False))
        self.assertEqual((check.get("opposition") or {}).get("name"), "Warin Hale")

    def test_an_empty_scene_record_also_falls_back_to_the_roster(self):
        # A fresh game before the first scene is recorded: the roster is the best the engine has.
        line = "I try to convince Warin to let me past"
        check = infer_check_from_action(line, _context(present=[], addressed=[]))
        self.assertEqual((check.get("opposition") or {}).get("name"), "Warin Hale")


if __name__ == "__main__":
    unittest.main()
