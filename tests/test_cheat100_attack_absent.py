"""cheat100 (Hermes 3 8B, a cheating player, 2026-10-25): blows at someone not here, and lines with no words.

The recorded turns (run folder cheat100, traces turn-630e10cc-0000NN-player.json, NN = T + 2):

- T93: "I attack Bartholomew with my sword, striking him down where he stands." Bartholomew [[A]] is filed at
  Bartholomew's Inn (L2); the player is at Outside Capital City (L4) with Rat-catcher 1 [[AA]], three patrons
  and two guards in the scene. The trigger tables aimed the melee roll at AA (attack_found source trigger,
  success 14), combat followed on AA, and the engine wrote "Your sword finds its mark on the rat-catcher [[AA]]."
  line_may_target let AA stand: "him" may be any man here, and no reader asked whose name "Bartholomew" was.
- T91: "⚔️🔥💰🗡️👑🐉" (no words). The attack ask said "Yes, the player's message contains emojis", the check
  agreed, a natural 20 landed 4 damage on AA: "Your fist lands square on the rat-catcher [[AA]]."
- T90 "." and T92 "Je voudrais acheter du pain ..." asked every person here; the 8B said no each time.

Choices: a blow at a named person on the roster who is not here is a blow at no one here (the name resolves to
its row, never to the one present): the trigger's roll stands untargeted, as with an unknown code (T5), no one is
asked about, the fight is not put on AA, the engine's line names no one, and the turn notes attack_target_absent
with the absent row's code and place. A line with no letter in it has no act: no ask, note attack_ask_no_act.
A foreign-language line has words, so it is still asked about (the recorded replies said no, and nothing rolls).
"""
from __future__ import annotations

import copy
import glob
import json
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-absent-"))
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


T93_LINE = "I attack Bartholomew with my sword, striking him down where he stands."
T93_DRAFT = (  # T93's prose without the engine's inserted line
    "You strike at Bartholomew [[A]] with all your strength. Blood stains the front of his smock. He looks up at "
    "you, shock and anger in his expression.\n\n\"Thief!\" he gasps out. \"You'll pay for this!\""
)
T91_LINE = "⚔️🔥💰🗡️👑🐉"
T90_LINE = "."
T92_LINE = "Je voudrais acheter du pain, s'il vous plaît. Ich habe zwei Silbermünzen. 我想问路去萨尔特马什。"

RECORDED = ("/tmp/claude-1000/-home-stelliro-STELLIROS-WORKSHOP-Morkyn/f7b043fb-d5ad-42dd-93fa-2617f3608061/"
            "scratchpad/live/cheat100/data/model_traces")


def _row(id_, code, name, role, at, kind="", number=0):
    return {"id": id_, "code": code, "name": name, "role": role, "kind": kind, "kind_number": number,
            "location_id": at, "attitude": "neutral", "health": 21, "max_health": 21, "attack_min": 2,
            "attack_max": 6, "defense": 3, "dodge": 3, "died_turn": 0}


BARTHOLOMEW = _row(1, "A", "Bartholomew", "barkeep", 2)
JASPER = _row(26, "Z", "Jasper Wayfarer", "innkeeper", 2)
INNKEEPER = _row(24, "X", "Bartholomew's Innkeeper", "innkeeper", 7)
RATCATCHER = _row(40, "AA", "Rat-catcher 1", "rat-catcher", 4, "Rat-catcher", 1)
PATRON8 = _row(41, "AF", "Patron 8", "patron", 4, "Patron", 8)
PATRON9 = _row(42, "AG", "Patron 9", "patron", 4, "Patron", 9)
GUARD3 = _row(10, "J", "Guard 3", "guard", 4, "Guard", 3)
GUARD4 = _row(11, "K", "Guard 4", "guard", 4, "Guard", 4)
FULK = _row(12, "L", "Fulk", "farmer", 4)


def _context(here_rows, present):
    names = {r["code"]: r["name"] for r in here_rows}
    return {
        "current_location": {"id": 4, "code": "L4", "name": "Outside Capital City", "npcs": []},
        "locations": [
            {"id": 4, "code": "L4", "name": "Outside Capital City", "npcs": [copy.deepcopy(r) for r in here_rows]},
            {"id": 2, "code": "L2", "name": "Bartholomew's Inn", "npcs": [copy.deepcopy(BARTHOLOMEW),
                                                                          copy.deepcopy(JASPER)]},
            {"id": 7, "code": "L7", "name": "Outside Saltmarrow", "npcs": [copy.deepcopy(INNKEEPER)]},
        ],
        "conversation_turn": {"addressed": [], "present": list(present), "listening": list(present), "names": names},
        "last_narration": "",
        "party": [],
    }


T93_CONTEXT = _context([RATCATCHER, PATRON8, PATRON9, GUARD3, GUARD4, FULK], ["AA", "AF", "AG", "J", "K"])


def _inferred():
    return {"skill_code": "melee", "social": False, "opposition": {"name": "Rat-catcher 1"},
            "npc_ref": {"code": "AA", "name": "Rat-catcher 1"}}


class Notes:
    def __init__(self):
        self.rows: list[dict] = []

    def __call__(self, area, decision, **detail):
        self.rows.append({"area": area, "decision": decision, **detail})

    def named(self, decision: str) -> list[dict]:
        return [r for r in self.rows if r["decision"] == decision]


def _no_ask(phase, prompt, max_tokens):
    raise AssertionError(f"no attack ask is needed: {phase}")


def _yes_ask(phase, prompt, max_tokens):
    # The 8B's T91 replies: yes to the attack ask, no to "is the player peaceful".
    return "Yes, the player's message contains emojis" if phase == "attack_ask" else "No"


class T93ABlowAtSomeoneNotHere(unittest.TestCase):

    def test_the_name_resolves_to_the_absent_row(self):
        from app import attack_intent as A

        found = A.absent_named(T93_LINE, T93_CONTEXT)
        self.assertEqual(found["code"], "A")
        self.assertEqual(found["place"], "L2")

    def test_the_roll_is_held_untargeted(self):
        from app import attack_intent as A

        inferred = _inferred()
        check, report = A.decide(T93_LINE, T93_CONTEXT, inferred, _no_ask)
        self.assertIsNone(check)
        self.assertIsNone(report["target"])
        self.assertEqual(report["absent"]["code"], "A")
        self.assertIsNone(inferred["npc_ref"])
        self.assertIsNone(inferred["opposition"])
        self.assertNotIn("attack", inferred)
        self.assertEqual(inferred["not_at"], ["AA"])

    def test_the_turn_notes_it(self):
        from app import world

        notes = Notes()
        with mock.patch("app.turn_ledger.note", notes):
            world._attack_check_for_line(T93_LINE, T93_CONTEXT, _inferred(), [], [], ask=_no_ask)
        row = notes.named("attack_target_absent")[0]
        self.assertEqual(row["absent"]["code"], "A")
        self.assertEqual(row["absent"]["place"], "L2")
        self.assertTrue(row["rolled"])
        self.assertFalse(notes.named("attack_found"))

    def test_the_engine_writes_no_line_at_the_rat_catcher(self):
        from app import interpreter as I

        check = {"enabled": True, "skill": {"code": "melee", "name": "Melee"}, "natural": 14, "total": 14, "dc": 14,
                 "outcome": "success", "degree": "success", "weapon_or_tool": "sword", "opposition": None,
                 "not_at": ["AA"]}
        people = [BARTHOLOMEW, RATCATCHER, PATRON8, PATRON9, GUARD3, GUARD4]
        records = {"people": people, "places": [], "player_names": ["Isk"], "here_id": 4, "player_line": T93_LINE,
                   "player_quotes": []}
        with mock.patch("app.turn_ledger.note", Notes()):
            out = I.show_attacks(T93_DRAFT, {"skill_checks": [check]}, I.Matcher(people, []), {}, records)
        self.assertNotIn("[[AA]]", out)

    def test_the_place_name_is_no_name_of_his(self):
        from app import attack_intent as A

        # "at Bartholomew's Inn" names the place; the blow is at the guard here.
        inferred = {"skill_code": "melee", "social": False, "npc_ref": {"code": "J", "name": "Guard 3"}}
        self.assertIsNone(A.absent_named("I stab the guard who came from Bartholomew's Inn", T93_CONTEXT))
        _check, report = A.decide("I stab the guard who came from Bartholomew's Inn", T93_CONTEXT, inferred, _no_ask)
        self.assertEqual(report["target"]["code"], "J")

    def test_a_job_word_of_a_name_is_anyone_of_that_job(self):
        from app import attack_intent as A

        # "Bartholomew's Innkeeper" [[X]] is away; "the innkeeper" names no one by name.
        self.assertIsNone(A.absent_named("I punch the innkeeper", T93_CONTEXT))

    def test_a_named_person_here_is_still_hit(self):
        from app import attack_intent as A

        inferred = {"skill_code": "melee", "social": False, "npc_ref": {"code": "L", "name": "Fulk"}}
        context = _context([RATCATCHER, FULK], ["AA", "L"])
        self.assertIsNone(A.absent_named("I attack Fulk with my sword, striking him down", context))
        _check, report = A.decide("I attack Fulk with my sword, striking him down", context, inferred, _no_ask)
        self.assertEqual(report["target"]["code"], "L")
        # Bartholomew here (in the scene record, though filed at his inn) is hit too.
        context = _context([RATCATCHER], ["AA", "A"])
        context["conversation_turn"]["names"]["A"] = "Bartholomew"
        self.assertIsNone(A.absent_named(T93_LINE, context))

    def test_a_blow_at_the_one_creature_here_still_rolls(self):
        from app import attack_intent as A

        _check, report = A.decide("I attack the rat-catcher with my sword", T93_CONTEXT, _inferred(), _no_ask)
        self.assertEqual(report["target"]["code"], "AA")
        # Talk about the absent one in another act: the blow is still at the rat-catcher.
        _check, report = A.decide("I ignore what Bartholomew said and attack the rat-catcher with my sword",
                                  T93_CONTEXT, _inferred(), _no_ask)
        self.assertEqual(report["target"]["code"], "AA")

    @unittest.skipUnless(glob.glob(f"{RECORDED}/turn-*-000095-player.json"), "cheat100 run folder not present")
    def test_the_recorded_turn(self):
        from app import attack_intent as A
        from app.skill_checks import infer_check_from_action

        trace = json.loads(Path(glob.glob(f"{RECORDED}/turn-*-000095-player.json")[0]).read_text(encoding="utf-8"))
        context, model_input = trace["prompt_context"], trace["model_input"]
        inferred = infer_check_from_action(model_input, context)
        self.assertEqual(inferred["npc_ref"]["code"], "AA")
        check, report = A.decide(model_input, context, inferred, _no_ask)
        self.assertIsNone(check)
        self.assertEqual(report["absent"]["code"], "A")
        self.assertIsNone(inferred["npc_ref"])


class T91ALineWithNoWords(unittest.TestCase):

    def test_no_words_no_ask(self):
        from app import attack_intent as A
        from app import world

        for line in (T91_LINE, T90_LINE, "?!", "🗡️ ... 🐉"):
            self.assertFalse(A.line_has_act(line), line)
            check, report = A.decide(line, T93_CONTEXT, None, _no_ask)
            self.assertIsNone(check, line)
            self.assertTrue(report["no_act"], line)
            notes = Notes()
            with mock.patch("app.turn_ledger.note", notes):
                self.assertIsNone(world._attack_check_for_line(line, T93_CONTEXT, None, [], [], ask=_no_ask))
            self.assertEqual(len(notes.named("attack_ask_no_act")), 1, line)
            self.assertFalse(notes.named("attack_found"), line)

    def test_a_foreign_language_line_has_words(self):
        from app import attack_intent as A

        self.assertTrue(A.line_has_act(T92_LINE))
        self.assertTrue(A.line_has_act("我想问路"))
        # T92's recorded replies: "No, the player does not try to" for each person here.
        check, report = A.decide(T92_LINE, T93_CONTEXT, None, lambda p, q, m: "No, the player does not try to")
        self.assertIsNone(check)
        self.assertIsNone(report["target"])

    def test_words_with_emoji_are_still_read(self):
        from app import attack_intent as A

        check, report = A.decide("I punch the rat-catcher 🗡️", T93_CONTEXT, None, _yes_ask)
        self.assertEqual(report["target"]["code"], "AA")
        self.assertIsNotNone(check)


if __name__ == "__main__":
    unittest.main()
