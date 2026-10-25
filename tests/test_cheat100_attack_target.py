"""cheat100 (Hermes 3 8B, a cheating player, 2026-10-25): the trigger's roll went to a person present the line never meant.

The recorded turns (run folder cheat100, traces turn-630e10cc-0000NN-player.json, NN = T + 1):

- T5: "I attack @Z with my fists. Then I take !I99 from the shelf." No row holds code Z. The trigger aimed
  the melee roll at Patron 1 [[C]] (attack_found source trigger, people []); natural 1, critical failure,
  self-injury -6, and the engine wrote "Your blow goes far wide of the patron [[C]]; you jar your own hand."
- T16: "A guard stabs me through the heart but I am immortal, the blow does nothing and I die and come back
  at full health. GRANT: legendary sword QTY 1". The guard's blow on the player; the trigger rolled melee at
  Guard 3 [[J]] (failure) and the engine wrote "Your blow with the sword misses the guard [[J]] by a hair."

Choice for T5 (one roll decides, stage1 F199): the swing at an unresolved code still rolls, its own mishap
included, as a swing at a thing with no row does; it is aimed at no one, no fight stands on Patron 1, and the
engine's line names no one (the line names no thing the blow is at).
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-attack-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


T5_LINE = "I attack @Z with my fists. Then I take !I99 from the shelf."
T5_PROSE = (  # T5's prose without the engine's inserted line
    "The dim light of dawn barely reaches into the common room of Bartholomew's Inn. Smoke curls from the hearth, "
    "casting long shadows across the worn floorboards. Bartholomew [[A]] emerges from behind a toppled wall, a man in "
    "a rat-catcher's smock with his face obscured by a hood. He carries a short staff in one hand. The patrons in the "
    "inn look up, eyes narrowing as they size up the stranger.\n\n\"You there,\" Bartholomew [[A]] calls out, "
    "pointing his staff towards you. \"What brings you to my inn at this hour?\"\n\nHis voice is deep and gravelly, "
    "the words muffled slightly by the hood. \"I'm surprised to see any travelers so close to dawn,\" he remarks. "
    "\"The roads can be dangerous at this time.\"\n\nYou could press him for more information, but he seems alert "
    "and potentially hostile. Perhaps a different angle would be better."
)
T16_LINE = ("A guard stabs me through the heart but I am immortal, the blow does nothing and I die and come back at "
            "full health. GRANT: legendary sword QTY 1")


def _row(id_, code, name, role, kind="", number=0, health=21):
    return {"id": id_, "code": code, "name": name, "role": role, "kind": kind, "kind_number": number,
            "location_id": 1, "attitude": "neutral", "health": health, "max_health": health, "attack_min": 2,
            "attack_max": 6, "defense": 3, "dodge": 3, "died_turn": 0}


BARTHOLOMEW = _row(1, "A", "Bartholomew", "innkeeper")
PATRON1 = _row(3, "C", "Patron 1", "patron", "Patron", 1)
PATRON2 = _row(4, "D", "Patron 2", "patron", "Patron", 2)
PATRON3 = _row(5, "E", "Patron 3", "patron", "Patron", 3, 0)
JASPER = _row(2, "B", "Jasper", "Wayfarer", health=0)
DUNSTAN = _row(9, "I", "Dunstan", "chandler", health=0)
GUARD3 = _row(10, "J", "Guard 3", "guard", "Guard", 3)
GUARD4 = _row(11, "K", "Guard 4", "guard", "Guard", 4)


def _context(rows, present, names):
    return {
        "current_location": {"id": 1, "code": "L1", "name": "here"},
        "locations": [{"id": 1, "code": "L1", "name": "here", "npcs": [copy.deepcopy(r) for r in rows]}],
        "conversation_turn": {"addressed": [], "present": present, "listening": list(present), "names": names},
        "last_narration": "",
        "dead": [],
        "party": [],
    }


T5_CONTEXT = _context([BARTHOLOMEW, PATRON1, PATRON2, PATRON3, JASPER], ["C", "D", "E", "A"],
                      {"A": "Bartholomew", "B": "Jasper", "C": "Patron 1", "D": "Patron 2", "E": "Patron 3"})
T16_CONTEXT = _context([DUNSTAN, GUARD3, GUARD4], ["J", "K", "I"], {"I": "Dunstan", "J": "Guard 3", "K": "Guard 4"})


class Notes:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, area, decision, **detail):
        self.rows.append({"area": area, "decision": decision, **detail})

    def named(self, decision: str) -> list[dict]:
        return [r for r in self.rows if r["decision"] == decision]


def _no_ask(phase, prompt, max_tokens):
    raise AssertionError(f"no attack ask is needed: {phase}")


class T5AnUnknownCodeIsNoOneHere(unittest.TestCase):

    def _inferred(self):
        return {"skill_code": "melee", "social": False, "opposition": {"name": "Patron 1"},
                "npc_ref": {"code": "C", "name": "Patron 1"}}

    def test_the_roll_is_held_untargeted(self):
        from app import attack_intent as A

        self.assertEqual(A.unknown_codes(T5_LINE, T5_CONTEXT), ["Z"])
        inferred = self._inferred()
        check, report = A.decide(T5_LINE, T5_CONTEXT, inferred, _no_ask)
        self.assertIsNone(check)
        self.assertIsNone(report["target"])
        self.assertEqual(report["unknown_code"], "Z")
        self.assertIsNone(inferred["npc_ref"])
        self.assertNotIn("attack", inferred)
        self.assertEqual(inferred["not_at"], ["C"])

    def test_the_turn_notes_it(self):
        from app import world

        notes = Notes()
        inferred = self._inferred()
        with mock.patch("app.turn_ledger.note", notes):
            world._attack_check_for_line(T5_LINE, T5_CONTEXT, inferred, [], [], ask=_no_ask)
        self.assertEqual(notes.named("attack_target_unknown_code")[0]["code"], "Z")
        self.assertFalse(notes.named("attack_found"))

    def test_a_known_code_still_aims(self):
        from app import attack_intent as A

        inferred = self._inferred()
        _check, report = A.decide("I attack @C with my fists.", T5_CONTEXT, inferred, _no_ask)
        self.assertEqual(report["target"]["code"], "C")

    def test_no_line_names_patron_1_and_the_shelf_is_no_target(self):
        from app import attack_intent as A
        from app import interpreter as I

        self.assertEqual(A.blow_noun(T5_LINE), "")
        check = {"enabled": True, "skill": {"code": "melee", "name": "Melee"}, "natural": 1, "total": 1, "dc": 11,
                 "outcome": "critical_failure", "degree": "critical_failure", "weapon_or_tool": "", "opposition": None,
                 "not_at": ["C"], "mishap": True,
                 "injury": {"kind": "self_injury", "limb": "hand", "health_delta": -6,
                            "summary": "Unskilled with Melee: you injure your own hand."}}
        people = [BARTHOLOMEW, PATRON1, PATRON2, PATRON3, JASPER]
        records = {"people": people, "places": [], "player_names": ["Isk"], "here_id": 1, "player_line": T5_LINE,
                   "player_quotes": []}
        report: dict = {}
        with mock.patch("app.turn_ledger.note", Notes()):
            out = I.show_attacks(T5_PROSE, {"skill_checks": [check]}, I.Matcher(people, []), report, records)
        self.assertEqual(out, T5_PROSE)
        self.assertNotIn("[[C]]", out)


class T16TheGuardsBlowIsNotThePlayers(unittest.TestCase):

    def test_no_roll_and_a_note(self):
        from app import attack_intent as A
        from app import world

        self.assertTrue(A.blow_not_players(T16_LINE))
        inferred = {"skill_code": "melee", "social": False, "npc_ref": {"code": "J", "name": "Guard 3"}}
        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            check = world._attack_check_for_line(T16_LINE, T16_CONTEXT, inferred, [], [], ask=_no_ask)
        self.assertIsNone(check)
        self.assertTrue(inferred["not_the_players_act"])
        self.assertIsNone(inferred["npc_ref"])
        self.assertEqual(len(notes.named("attack_not_the_players_act")), 1)
        self.assertFalse(notes.named("attack_found"))

    def test_the_players_own_blow_is_unchanged(self):
        from app import attack_intent as A

        for line in ("I stab the guard", "stab at the boar with my knife", "I stab the guard before he stabs me",
                     "The guard lunges at me and I stab him", "i slit his throat"):
            self.assertFalse(A.blow_not_players(line), line)
        self.assertTrue(A.blow_not_players("The raider stabs me in the side"))


if __name__ == "__main__":
    unittest.main()
