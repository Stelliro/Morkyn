"""F196: op field text leaked into row names and titles (sonnet100, Hermes 3 8B).

The op lines below are copied from the recorded drafts (model_trace, phase
draft_dsl, raw_content) of the sonnet100 run, 2026-10-25:

- T54: 'NPC_NEW: "NAME = Marcella; ROLE = peddler; LOC = [[L4]]"' filed a person
  "= Marcella" with the job "= peddler" at "= [[L4]]".
- T73: 'EVENT: "NAME: The Search for the Eel Pool Creature"' filed an event with
  the label in its title; 'SKILL: "name: Perception\\ndelta: +1\\nATTITUDE:
  improved"' tagged the dice with all of it; LOC_NEW and QUEST kept their other
  fields in the name and title.
- T88: 'NPC_NEW: NAME="Melisent Ashby" ...' filed a person "NAME=", 'EVENT:
  title="The Tide" ...' an event "title=", 'SKILL: name="perception" ...' a skill
  "name=", and the GM note repeated the QUEST step word for word.
- T97: 'NPC_NEW: "Cully" ROLE="watchmen" LOC=[[L1]]' filed "Cully ROLE=".

The repair is the op form only (the parser, where a part is read); a drop is a
ledger note.
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
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-sonnet100-op-fields-"))
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


def _turn(ops: str, narration: str = "You look around.") -> tuple[dict, list[tuple[tuple, dict]]]:
    from app.turn_dsl import parse_dsl_turn

    with mock.patch("app.turn_ledger.note") as note:
        turn = parse_dsl_turn(f"===NAR===\n{narration}\n\n===OPS===\n{ops}\n")
    return turn, [(call.args, call.kwargs) for call in note.call_args_list]


# T54, the real lines.
T54 = (
    'NPC_NEW: "NAME = Marcella; ROLE = peddler; LOC = [[L4]]"\n'
    "QUEST: \"title = 'Find Supplies'; GIVER = 'D'; STEP = 'Buy something cheap from the peddller.'\"\n"
    "QUEST_DONE: \"quest = 'Find Supplies'; accept\""
)
# T73, the real lines (the backslash-n are in the draft as written).
T73 = (
    r'NPC_NEW: "NAME: Delphine Warrender\nROLE: herb gatherer\nATTITUDE: cautious\nRACE: human"' "\n"
    r'LOC_NEW: "NAME: The Eel Pool\nDESC: \"a wide, murky pool where the marsh seems to open up\"" ' "\n"
    'EVENT: "NAME: The Search for the Eel Pool Creature"\n'
    r'QUEST: "TITLE: Investigate the Eel Pool\nGIVER: \"Delphine Warrender\"\nSTEP: \"Wade out into the Eel Pool and search for the creature.\""' "\n"
    'QUEST_DONE: "quest:Q2 accept"\n'
    r'SKILL: "name: Perception\ndelta: +1\nATTITUDE: improved"'
)
# T88, the real lines.
T88 = (
    'NPC_NEW: NAME="Melisent Ashby" ROLE="town crier" LOC="Saltmarrow" \n'
    'LOC_NEW: name="coast road" desc="The main coastal road runs north and south along the flats between the salt marshes and the ruined lower district."\n'
    'EVENT: title="The Tide" desc="The tide is out and will be receding for a few more hours. The flats are still flooded and not safe to walk yet."\n'
    'GM: "The player has not yet decided which salvage contract to take next.", "Consider the options carefully before making a decision."\n'
    'SKILL: name="perception" DELTA=success degree="barely" for="it works: the work is done"\n'
    'QUEST: title="The Next Salvage Contract" GIVER=F STEP="Consider the options carefully before making a decision." REWARD="A share of the next salvage."\n'
    'QUEST_DONE: title="Marked the Jobs Done", step_done'
)
# T97, the real line.
T97 = 'NPC_NEW: "Cully" ROLE="watchmen" LOC=[[L1]]'


class PairSignAndLabelAreTheOpForm(unittest.TestCase):
    def test_t54_key_equals_value_pairs(self):
        turn, _ = _turn(T54)
        npc = turn["npcs"][0]
        self.assertEqual((npc["name"], npc["role"], npc["location"]), ("Marcella", "peddler", "[[L4]]"))
        quest, done = turn["quest_marks"]
        self.assertEqual((quest["title"], quest["giver"]), ("Find Supplies", "D"))
        self.assertEqual(quest["step"], "Buy something cheap from the peddller.")
        self.assertEqual((done["quest"], done["action"]), ("Find Supplies", "accept"))

    def test_t73_the_label_is_stripped_and_the_value_ends_at_the_next_field(self):
        turn, _ = _turn(T73)
        self.assertEqual(turn["events"][0]["title"], "The Search for the Eel Pool Creature")
        npc = turn["npcs"][0]
        self.assertEqual((npc["name"], npc["role"], npc["attitude"]), ("Delphine Warrender", "herb gatherer", "cautious"))
        self.assertEqual(turn["locations"][0]["name"], "The Eel Pool")
        quest = turn["quest_marks"][0]
        self.assertEqual((quest["title"], quest["giver"]), ("Investigate the Eel Pool", "Delphine Warrender"))
        done = turn["quest_marks"][1]
        self.assertEqual((done["quest"], done["action"]), ("Q2", "accept"))
        # The dice tag is the skill alone, cut at the new line.
        skill = turn["skill_changes"][0]
        self.assertEqual(skill["name"], "Perception")
        self.assertNotIn("\n", skill["name"])

    def test_t88_key_equals_quoted_value(self):
        turn, _ = _turn(T88)
        npc = turn["npcs"][0]
        self.assertEqual((npc["name"], npc["role"]), ("Melisent Ashby", "town crier"))
        self.assertEqual(turn["events"][0]["title"], "The Tide")
        self.assertIn("tide is out", turn["events"][0]["summary"])
        self.assertEqual(turn["locations"][0]["name"], "coast road")
        self.assertEqual(turn["skill_changes"][0]["name"], "perception")
        self.assertEqual(turn["quest_marks"][0]["title"], "The Next Salvage Contract")
        self.assertEqual(turn["quest_marks"][1]["quest"], "Marked the Jobs Done")

    def test_t97_a_label_quoted_apart_from_its_value(self):
        turn, _ = _turn(T97)
        npc = turn["npcs"][0]
        self.assertEqual((npc["name"], npc["role"], npc["location"]), ("Cully", "watchmen", "[[L1]]"))


class AnEmptyOrCopiedValueIsDroppedWithANote(unittest.TestCase):
    def test_a_label_with_no_value_is_no_title(self):
        turn, notes = _turn("EVENT: title=\nNPC_NEW: \"NAME=\"")
        self.assertEqual(turn["events"], [])
        self.assertEqual(turn["npcs"], [])
        decisions = [(args[1], kwargs.get("op")) for args, kwargs in notes]
        self.assertIn(("op_value_is_op_text", "EVENT"), decisions)
        self.assertIn(("op_value_is_op_text", "NPC_NEW"), decisions)

    def test_t88_the_gm_note_that_repeats_the_quest_step_is_dropped(self):
        turn, notes = _turn(T88)
        self.assertEqual(turn["gm_events"], [])
        gm = [kwargs for args, kwargs in notes if kwargs.get("op") == "GM"]
        self.assertEqual(len(gm), 1)
        self.assertEqual(gm[0]["why"], "repeats_QUEST")


class PlainOpsAreUnchanged(unittest.TestCase):
    def test_good_ops_keep_their_values(self):
        turn, notes = _turn(
            'NPC_NEW: NAME "Avelina Ridley" ROLE "peddler" LOC [[L4]]\n'
            'EVENT: "The Search for the Eel Pool Creature"\n'
            'SKILL: "Perception", DELTA: small\n'
            'GM: "The tide turns", "The flats flood at dusk"\n'
            'QUEST_DONE: "Find Supplies" accept\n'
            "SUMMARY: You meet Beth. Role: doctor.\n"
        )
        npc = turn["npcs"][0]
        self.assertEqual((npc["name"], npc["role"]), ("Avelina Ridley", "peddler"))
        self.assertEqual(turn["events"][0]["title"], "The Search for the Eel Pool Creature")
        self.assertEqual(turn["skill_changes"][0]["name"], "Perception")
        self.assertEqual(len(turn["gm_events"]), 1)
        self.assertEqual((turn["quest_marks"][0]["quest"], turn["quest_marks"][0]["action"]), ("Find Supplies", "accept"))
        self.assertEqual(turn["turn_summary"], "You meet Beth. Role: doctor.")
        self.assertEqual([args[1] for args, _ in notes if args[1] == "op_value_is_op_text"], [])


if __name__ == "__main__":
    unittest.main()
