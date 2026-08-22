"""Regression tests: answering a question the world can already answer.

From turn 88 of the 20260823 continuity probe. Turn 17 planted

    I owe eleven silver to a lender called Hask, and the debt comes due at
    the next full moon.

Turn 55 recalled it correctly. Turn 88 asked the identical question and wrote

    You're asked what debts you carry. You answer honestly: who you owe, how
    much, and when.

...and never named Hask or the amount. It was the run's only recall miss.

This was NOT a retrieval failure -- the record was in that turn's prompt six
times over, plus a claims entry. The model had it and wrote around it, which is
the same dodge the naming contract exists to stop, so it gets the same remedy:
state the specifics as server truth, then verify the prose and repair once.

Scope discipline: only proper nouns and amounts are demanded back. Requiring
topic words would fire on prose that answered in its own words, and rewriting a
good scene is a loss. Scored against all 100 turns of that run this selects
exactly one turn -- the real failure -- at every threshold from 0.3 to 0.5.

Run:  python -m unittest tests.test_recall_specifics
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-recall-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.world import (  # noqa: E402
    check_recall_specifics,
    recall_contract,
    recall_specifics,
)

DEBT = "You owe eleven silver to a lender called Hask, and that the debt comes due at the next full moon."
PROBE = "I am asked what debts I carry. I answer honestly: who I owe, how much, and when."

# The prose that actually shipped on turn 88.
DODGE = (
    "You're asked what debts you carry. You answer honestly: who you owe, how much, "
    "and when. The fishmonger, Eldrin, already knows the weight of names and debts. "
    "He nods, the scar on his wrist a silent testament to past reckonings. The market "
    "square hums with tension, and the air feels heavier, as if the weight of the letter "
    "you carry has settled into the space between your ribs."
)

# The prose that shipped on turn 55, which passed.
ANSWERED = (
    "You tell them plainly: eleven silver, owed to a lender called Hask, due at the next "
    "full moon. The words land flat in the noise of the square. Eldrin does not look up "
    "from his stall, but his hands slow over the fish, and you know he heard every word "
    "of it. Nobody offers to help, and nobody offers to forget."
)


def _state(*records: str) -> dict:
    return {"conversations": [{"topic": r, "summary": r} for r in records], "response_drafts": []}


class TestSpecificsExtraction(unittest.TestCase):
    def test_names_and_amounts_are_the_specifics(self):
        found = [s.lower() for s in recall_specifics(DEBT)]
        self.assertIn("hask", found)
        self.assertIn("eleven", found)

    def test_sentence_openers_are_not_names(self):
        # "You" and "The" start most sentences; demanding them back is noise.
        found = recall_specifics("You owe money. The lender waits. They are patient.")
        self.assertEqual(found, [])

    def test_digits_count_as_amounts(self):
        self.assertIn("11", recall_specifics("You owe 11 silver."))

    def test_prose_without_specifics_yields_nothing(self):
        self.assertEqual(recall_specifics("you owe a little money to someone in town"), [])


class TestContractFires(unittest.TestCase):
    def test_the_recorded_failure_is_caught(self):
        contract = recall_contract(_state(DEBT), PROBE)
        self.assertTrue(contract["required"])
        self.assertIn("Hask", contract["specifics"])
        report = check_recall_specifics(contract, DODGE)
        self.assertTrue(report["missing"])

    def test_prose_that_answered_is_left_alone(self):
        contract = recall_contract(_state(DEBT), PROBE)
        report = check_recall_specifics(contract, ANSWERED)
        self.assertFalse(report["missing"])
        self.assertIn("Hask", report["stated"])

    def test_one_specific_is_enough(self):
        # Naming the lender without the amount is a real answer, not a dodge.
        partial = (
            "You tell them you owe a lender called Hask, and that the reckoning is not far "
            "off. You do not say the figure aloud, and nobody in the square presses you for "
            "it. The noise of the market closes back over the moment."
        )
        contract = recall_contract(_state(DEBT), PROBE)
        self.assertFalse(check_recall_specifics(contract, partial)["missing"])


class TestContractStaysQuiet(unittest.TestCase):
    def test_a_line_that_is_not_an_answer_act_never_fires(self):
        for line in (
            "I walk to the river and look for a ferry.",
            "I ask the scribe about the roads.",
            "I count my coins.",
        ):
            with self.subTest(line=line):
                self.assertFalse(recall_contract(_state(DEBT), line)["required"])

    def test_an_unrelated_record_does_not_qualify(self):
        contract = recall_contract(
            _state("The mill downstream flooded last spring and has not reopened."), PROBE
        )
        self.assertFalse(contract["required"])

    def test_no_records_means_no_contract(self):
        self.assertFalse(recall_contract({}, PROBE)["required"])

    def test_a_record_with_no_specifics_does_not_qualify(self):
        # Nothing concrete to demand back, so there is nothing to enforce.
        contract = recall_contract(_state("you owe a little money and it worries you"), PROBE)
        self.assertFalse(contract["required"])

    def test_short_prose_is_not_judged(self):
        # A stub or an error string is not a dodge.
        contract = recall_contract(_state(DEBT), PROBE)
        self.assertFalse(check_recall_specifics(contract, "You answer.")["missing"])

    def test_no_contract_means_no_report(self):
        self.assertFalse(check_recall_specifics(None, DODGE)["required"])
        self.assertFalse(check_recall_specifics({"required": False}, DODGE)["missing"])


class TestSelfEchoDoesNotWin(unittest.TestCase):
    """The world records the player's own line every turn.

    Those echoes score 1.0 against the question and carry no name and no number,
    so the best-scoring record is routinely the question itself. Taking it would
    silently disable the contract on exactly the turns it exists for.
    """

    ECHO = "player: I am asked what debts I carry. I answer honestly: who I owe, how much, and when."

    def test_the_answer_wins_over_the_echo(self):
        contract = recall_contract(
            _state(self.ECHO, DEBT), PROBE, sources=[{"text": self.ECHO}]
        )
        self.assertTrue(contract["required"])
        self.assertIn("Hask", contract["specifics"])

    def test_an_echo_alone_sets_no_contract(self):
        self.assertFalse(recall_contract(_state(self.ECHO), PROBE)["required"])

    def test_retrieved_sources_are_searched_too(self):
        # The conversation window is bounded; the plant that failed was 71 turns
        # old, and source_index retrieval is what reaches that far back.
        contract = recall_contract({}, PROBE, sources=[{"text": DEBT}])
        self.assertTrue(contract["required"])
        self.assertIn("Hask", contract["specifics"])


class TestPacketPlumbing(unittest.TestCase):
    """Four allowlists in this codebase silently drop unlisted keys."""

    CTX = {
        "recall_contract": {
            "required": True,
            "specifics": ["Hask", "eleven"],
            "record": DEBT,
            "overlap": 0.6,
            "rule": "state these",
        }
    }

    def test_it_reaches_the_json_prompt(self):
        from app.prompts import build_user_prompt

        rendered = build_user_prompt(self.CTX, PROBE)
        self.assertIn("recall_contract", rendered)
        self.assertIn("Hask", rendered)

    def test_it_reaches_the_dsl_prompt(self):
        from app.turn_dsl import build_dsl_user_prompt

        self.assertIn("Hask", build_dsl_user_prompt(self.CTX, PROBE))

    def test_it_is_on_the_handoff_allowlist(self):
        from app.llm import HANDOFF_BASE_CONTEXT_KEYS

        self.assertIn("recall_contract", HANDOFF_BASE_CONTEXT_KEYS)


if __name__ == "__main__":
    unittest.main()
