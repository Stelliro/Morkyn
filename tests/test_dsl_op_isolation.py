"""Regression tests: one fumbled op line must not cost the turn its state.

From the second 100-turn continuity probe. Three of the four failed self-checks
were the same line, verbatim in shape:

    INDEX npc F "Hearthpost, the scribe, watches you closely"

"NPC" is a flag key (EVENT ... NPC <code>), so the entity type "npc" swallowed
the code "F" as flags={NPC: F} and left a single positional. That failed INDEX's
own arity check, which raised, which discarded *every* op in the turn -- the
MOVEs, the TALKs, the JOURNAL lines, all of it -- and the run recorded
"Ignored unparseable model-proposed state changes."

Two rules under test, because either alone leaves a hole:
  1. INDEX's leading tokens are positional by definition (type, code).
  2. A malformed op line is skipped and reported, never fatal to its neighbours.

parse_ops already dropped unknown *opcodes* this way and said so in a comment.
The arity checks in ops_to_turn simply bypassed that intent.

Run:  python -m unittest tests.test_dsl_op_isolation
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.turn_dsl import (  # noqa: E402
    TurnDslError,
    _tokenize_line,
    parse_dsl_turn,
    parse_ops,
)

NAR = (
    "The scribe looks up from the ledger as you step in out of the rain. "
    "Dust hangs in the lamplight and nobody hurries you along."
)


def _draft(ops: str) -> str:
    return f"===NAR===\n{NAR}\n\n===OPS===\n{ops.strip()}\n"


class TestIndexTokenizing(unittest.TestCase):
    def test_npc_type_is_not_eaten_as_a_flag(self):
        op, pos, flags = _tokenize_line('INDEX npc F "watches you closely"')
        self.assertEqual(op, "INDEX")
        self.assertEqual(pos, ["npc", "F", "watches you closely"])
        self.assertEqual(flags, {}, "npc/F are positional here, not a flag pair")

    def test_other_entity_types_still_parse(self):
        for kind, code in (("location", "L1"), ("item", "I2"), ("event", "E3")):
            with self.subTest(kind=kind):
                _op, pos, _flags = _tokenize_line(f'INDEX {kind} {code} "a summary"')
                self.assertEqual(pos, [kind, code, "a summary"])

    def test_npc_is_still_a_flag_key_where_it_is_one(self):
        # The collision is INDEX-specific. EVENT must keep reading NPC as a flag.
        op, pos, flags = _tokenize_line(
            'EVENT "Ledger opened" LOC L1 NPC F SUMMARY "he reads the debt aloud"'
        )
        self.assertEqual(op, "EVENT")
        self.assertEqual(pos, ["Ledger opened"])
        self.assertEqual(flags["NPC"], "F")
        self.assertEqual(flags["LOC"], "L1")

    def test_focus_kind_still_positional(self):
        _op, pos, flags = _tokenize_line('FOCUS npc "the scribe hesitates"')
        self.assertEqual(pos, ["npc", "the scribe hesitates"])
        self.assertEqual(flags, {})

    def test_index_op_reaches_the_turn(self):
        turn = parse_dsl_turn(_draft('INDEX npc F "watches you closely"'))
        self.assertEqual(len(turn["index_updates"]), 1)
        update = turn["index_updates"][0]
        self.assertEqual(update["entity_type"], "npc")
        self.assertEqual(update["code"], "F")
        self.assertEqual(update["summary_append"], "watches you closely")


class TestMalformedOpsAreIsolated(unittest.TestCase):
    def test_a_bad_line_does_not_discard_its_neighbours(self):
        turn = parse_dsl_turn(
            _draft(
                """
                MOVE L2
                INDEX npc
                TALK F "Mind the step."
                JOURNAL fact "The scribe kept the ledger open."
                """
            )
        )
        self.assertEqual(turn["player"]["move_to_location_code"], "L2")
        self.assertEqual(len(turn["conversations"]), 1)
        self.assertEqual(len(turn["journal"]), 1)

    def test_the_skip_is_reported_not_silent(self):
        turn = parse_dsl_turn(_draft('MOVE L2\nINDEX npc\nTALK F "Mind the step."'))
        self.assertEqual(turn["_dsl"]["malformed_ops"], 1)
        self.assertTrue(
            any("INDEX" in str(i) for i in turn["self_check"]["issues_found"]),
            "a dropped op has to show up in the self-check, or it is invisible",
        )
        self.assertTrue(
            any("Skipped" in str(c) for c in turn["self_check"]["corrections_made"])
        )

    def test_a_clean_turn_reports_nothing(self):
        turn = parse_dsl_turn(_draft('MOVE L2\nTALK F "Mind the step."'))
        self.assertNotIn("malformed_ops", turn["_dsl"])
        self.assertEqual(turn["self_check"]["issues_found"], [])

    def test_every_line_malformed_still_yields_a_playable_turn(self):
        turn = parse_dsl_turn(_draft("INDEX npc\nNPC_NEW\nREL A"))
        self.assertEqual(turn["_dsl"]["malformed_ops"], 3)
        self.assertTrue(turn["narration"].strip())

    def test_missing_narration_is_still_fatal(self):
        # Isolation is for ops. A draft with no prose has nothing to salvage.
        with self.assertRaises(TurnDslError):
            parse_dsl_turn("===NAR===\n\n===OPS===\nMOVE L2\n")

    def test_wrong_format_entirely_is_still_fatal(self):
        # parse_ops' own rule: nothing recognizable means the wrong format,
        # not a typo, and the caller needs to know rather than get an empty turn.
        with self.assertRaises(TurnDslError):
            parse_ops("this is prose\nso is this\nand this")


class TestTheRecordedFailure(unittest.TestCase):
    """The exact ops block from turn 84 of the 20260823 run."""

    OPS = """
SCENE investigation
FOCUS event "rumors about the roads, debts, or sealed letters"
TALK F "You're looking for honest work, aren't you?"
TALK A "Bandits took a cart of grain, and the roads are getting rough."
TALK I "The weight of names and debts is never far from here."
CLAIM "The ledger contains details of old debts" VERDICT unverified
INDEX npc F "Hearthpost, the scribe, watches you closely"
INDEX npc A "Eldrin, the fishmonger, speaks of trouble in the valley"
INDEX npc I "Kiteline, the baker, mentions the weight of names and debts"
"""

    def test_the_whole_turn_survives(self):
        turn = parse_dsl_turn(_draft(self.OPS))
        self.assertEqual(turn["_dsl"]["ops_count"], 9)
        self.assertEqual(turn["_dsl"].get("malformed_ops", 0), 0)
        self.assertEqual(len(turn["index_updates"]), 3)
        self.assertEqual(len(turn["conversations"]), 3)
        self.assertEqual(
            [u["code"] for u in turn["index_updates"]], ["F", "A", "I"]
        )


if __name__ == "__main__":
    unittest.main()
