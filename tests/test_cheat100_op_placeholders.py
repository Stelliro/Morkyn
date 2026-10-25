"""op-placeholders: the op list's slot words written back as values (cheat100, Hermes 3 8B).

cheat100 T93 (trace turn-630e10cc-000095-player.json, model_trace phase
draft_dsl, raw_content), 2026-10-25: the draft wrote every op on the list with
the words that name its parts in place of values. The save got an event
"EVENT_TITLE", a GM note "NOTE", a journal fact "FACT", a conversation about
"WHAT", a claim "CLAIM_TITLE" and dice rolled for "item:ITEM NAME" (twice) and
"skill:SKILL_NAME". Only MOVE refused its slot word. The OPS block below is the
draft's own, line for line.

The repair is one place, ops_to_turn, before any op is applied: a part made
only of the op list's words for parts (read from DSL_SYSTEM_PROMPT itself) and
written as a slot is no value. The op is dropped with one ledger note,
op_value_is_slot_word. A slot word with its value after it is a label
('QUEST: TITLE "Kitchen Helper"') and stays for the parser.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-cheat100-op-placeholders-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)
    from app.db import init_db

    init_db()


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


T93_NARRATION = (
    "You strike at Bartholomew with all your strength. Your blade thuds against his chest and he "
    "staggers back, clutching at the wound. Blood stains the front of his smock.\n\n"
    '"Thief!" he gasps out. "You\'ll pay for this!"'
)
# The draft's OPS block, as written.
T93_OPS = """SUMMARY: "You wound Bartholomew in a fight and continue to defend yourself against his attacks."
SCENE: action
GOAL: "Defend yourself against Bartholomew's attacks after wounding him."
FOCUS: risk
NPC_NEW: NAME, ROLE, LOC
NPC_NOTE: NPC_CODE
TALK: NPC_CODE, WHAT
GRANT: ITEM_NAME, QTY, BAND
TAKE: ITEM_NAME, QTY, BAND
GOLD: GOLD_AMOUNT
XP: BAND
HP: BAND
KARMA: BAND, VIS, REASON
MOVE: PLACE_NAME
WALK: DIRECTION, STEPS
LOC_NEW: PLACE_NAME, DESCRIPTION
EVENT: EVENT_TITLE, LOC, NPC, SUMMARY
GM: TRIGGER, NOTE
REL: RELATIONSHIP_CODE, KNOWN_CODE, REASON
SKILL: SKILL_NAME, DELTA, BAND
CLAIM: CLAIM_TITLE, VERDICT, UNVERIFIED, SKILL, NOTES
JOURNAL: KIND, ENTRY
INDEX: KIND, CODE, SUMMARY
NOTE: FACT
CAST: PRESENCE, NPC_CODE
QUEST: QUEST_TITLE, GIVER, STEP, AT, REWARD
QUEST_DONE: QUEST_CODE, ACCEPT, STEP_DONE, COMPLETE, FAIL, ABANDON
LEAD: LEAD_CODE, TO"""


def _turn(ops: str, narration: str = T93_NARRATION) -> tuple[dict, list[dict]]:
    from app.turn_dsl import parse_dsl_turn

    with mock.patch("app.turn_ledger.note") as note:
        turn = parse_dsl_turn(f"===NAR===\n{narration}\n\n===OPS===\n{ops}\n")
    return turn, [call.kwargs | {"_kind": call.args[1]} for call in note.call_args_list if len(call.args) > 1]


class T93SlotWordsAreNoValues(unittest.TestCase):
    def setUp(self):
        self.turn, self.notes = _turn(T93_OPS)

    def test_no_rows_from_slot_words(self):
        turn = self.turn
        self.assertEqual(turn["events"], [])
        self.assertEqual(turn["gm_events"], [])
        self.assertEqual(turn["inventory_changes"], [])
        self.assertEqual(turn["skill_changes"], [])
        self.assertEqual(turn["npcs"], [])
        self.assertEqual(turn["locations"], [])
        self.assertEqual(turn["relationships"], [])
        self.assertEqual(turn["journal"], [])
        self.assertEqual(turn["index_updates"], [])
        self.assertEqual(turn["conversations"], [])
        self.assertEqual(turn["response_drafts"], [])
        self.assertNotIn("leads", turn["_dsl"])
        self.assertIsNone(turn["player"]["move_to_location"])
        for key in ("xp_band", "health_band", "karma_band", "gold_band"):
            self.assertNotIn(key, turn["player"])

    def test_the_real_lines_are_kept(self):
        turn = self.turn
        self.assertIn("You wound Bartholomew", turn["turn_summary"])
        self.assertEqual(turn["scene_focus"], "action")
        self.assertIn("Defend yourself", turn["scene_plan"]["goal"])
        self.assertEqual([p["kind"] for p in turn["scene_plan"]["focus_points"]], ["risk"])

    def test_one_ledger_note_per_dropped_op(self):
        slot = [n for n in self.notes if n["_kind"] == "op_value_is_slot_word"]
        by_op = {n["op"]: n for n in slot}
        self.assertEqual(len(slot), len(by_op))
        self.assertEqual(by_op["EVENT"]["word"], "EVENT_TITLE")
        self.assertEqual(by_op["GM"]["word"], "TRIGGER")
        self.assertIn("part=NOTE", by_op["GM"]["words"])
        self.assertEqual(by_op["GRANT"]["word"], "ITEM_NAME")
        self.assertEqual(by_op["SKILL"]["word"], "SKILL_NAME")
        self.assertEqual(by_op["QUEST_DONE"]["word"], "QUEST_CODE")
        self.assertEqual(by_op["NOTE"]["word"], "FACT")
        self.assertTrue(all(n["dropped"] == "op" for n in slot))
        self.assertNotIn("SUMMARY", by_op)
        self.assertNotIn("SCENE", by_op)
        self.assertNotIn("FOCUS", by_op)

    def test_no_dice_for_the_slot_words(self):
        from app.db import connect
        from app.world import resolve_turn_bands

        with connect().closing() as conn:
            report = resolve_turn_bands(conn, self.turn, turn=93, options={})
        tags = [str(roll.get("tag") or "") for roll in report["rolls"]]
        self.assertFalse([t for t in tags if t.startswith(("item:", "skill:"))], tags)
        self.assertEqual(self.turn["player"].get("xp_delta", 0), 0)
        self.assertEqual(self.turn["player"].get("health_delta", 0), 0)
        self.assertEqual(self.turn["player"].get("gold_delta", 0), 0)


class SlotWordShape(unittest.TestCase):
    def test_slot_words_by_shape(self):
        from app.turn_dsl import op_slot_word

        for op, value in (
            ("EVENT", "EVENT_TITLE"), ("GM", "NOTE"), ("GRANT", "ITEM NAME"), ("GRANT", "item_name"),
            ("SKILL", "SKILL_NAME"), ("GOLD", "GOLD_AMOUNT"), ("REL", "RELATIONSHIP_CODE"),
            ("EVENT", "<title>"), ("NOTE", "[FACT]"), ("LOC_NEW", "{place name}"),
        ):
            self.assertTrue(op_slot_word(op, value), (op, value))

    def test_real_values_and_choice_words_stay(self):
        from app.turn_dsl import op_slot_word

        for op, value in (
            ("EVENT", "The Tide Turns"), ("GRANT", "rope_ladder"), ("SKILL", "SIGIL READING"),
            ("GM", "Note"), ("QUEST_DONE", "step_done"), ("QUEST_DONE", "ACCEPT"), ("CLAIM", "UNVERIFIED"),
            ("JOURNAL", "fact"), ("SCENE", "action"), ("XP", "SMALL"), ("XP", "-moderate"),
            ("REL", "PLAYER"), ("CAST", "AA"), ("TALK", "L1"), ("EVENT", "Old Mill"),
        ):
            self.assertEqual(op_slot_word(op, value), "", (op, value))


class RealOpsStillFile(unittest.TestCase):
    def test_a_real_event_files(self):
        turn, notes = _turn('EVENT: "The Inn Brawl" LOC L1 SUMMARY "Bartholomew draws a knife."')
        self.assertEqual([e["title"] for e in turn["events"]], ["The Inn Brawl"])
        self.assertFalse([n for n in notes if n["_kind"] == "op_value_is_slot_word"])

    def test_labels_before_their_values_are_not_slot_words(self):
        # Recorded lines from sonnet100 T26/T80 and cheat100 T11, T65, T72.
        turn, notes = _turn(
            'QUEST: TITLE "Kitchen Helper" GIVER "Dunstan" STEP "Show up for work at dawn"\n'
            "WALK: south, STEPS 1\n"
            'SKILL: "deception", DELTA "up", BAND "large"\n'
            "GOLD: -1 GOLD"
        )
        self.assertFalse([n for n in notes if n["_kind"] == "op_value_is_slot_word"])
        self.assertEqual([c["name"] for c in turn["skill_changes"]], ["deception"])

    def test_a_slot_word_in_a_flag_drops_only_that_flag(self):
        turn, notes = _turn('GRANT: "Iron Key" QTY BAND')
        self.assertEqual([c["name"] for c in turn["inventory_changes"]], ["Iron Key"])
        slot = [n for n in notes if n["_kind"] == "op_value_is_slot_word"]
        self.assertEqual([(n["op"], n["dropped"]) for n in slot], [("GRANT", "field")])


if __name__ == "__main__":
    unittest.main()
