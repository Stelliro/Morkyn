"""Regression tests: a promised explanation has to actually appear.

From the 100-turn continuity probe, turn 66. The player line was

    Someone suggests crossing deep water. I explain why that is a problem for
    me in particular.

and the narration described kneeling at a marked spot while an NPC watched. It
even mentioned the river without engaging. Same family as the naming dodge: the
model writes around the thing it owes.

The bar for flagging is deliberately high. A broader "did the narration respond
to the action at all?" detector was built and rejected: scored against these
same 100 turns, a category-overlap version flagged five, of which at least three
were plainly responsive -- one narration answered "I listen for rumors" with
"You ask about..." and another with "They mention a reward for a sealed letter".
Firing a rewrite on responsive prose makes a turn worse, so only a total miss on
an explicit answer act counts.

Run:  python -m unittest tests.test_answer_acts
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-answer-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.db import db_path  # noqa: E402
from app.world import check_answer_act  # noqa: E402


def _assert_isolated() -> None:
    if not str(db_path()).startswith(str(_TMP)):
        raise AssertionError(f"test isolation failed: AI_RPG_DB resolves to {db_path()!r}")


def setUpModule() -> None:
    """Re-pin paths: unittest imports every test module before running any test."""
    os.environ.update(_ENV)
    _assert_isolated()


_assert_isolated()

# Verbatim from the run.
TURN_66_ACTION = (
    "Someone suggests crossing deep water. I explain why that is a problem for me in particular."
)
TURN_66_NARRATION = (
    "You step toward the marked spot in the earth, the ground still warm from the fire that "
    "passed through here. Jetcoil watches from the edge of the clearing, their stance tense, "
    "eyes narrowing as you approach. The air feels heavier than before, thick with an unspoken "
    "tension. You pause, glancing back at the river, its surface still and unbroken. A ripple "
    "of unease runs through you. The marked spot is a shallow depression, the earth slightly "
    "raised around it like a ring. You kneel, fingers brushing the soil."
)
ANSWERED = (
    "You tell them plainly that you never learned to swim, that deep water has frightened you "
    "since you were small, and that crossing it is not something you will do. Jetcoil listens "
    "without comment, then nods once toward the shallows further down."
)


class TestDetectsTheAnswerAct(unittest.TestCase):
    def test_turn_66_is_flagged(self):
        report = check_answer_act(TURN_66_ACTION, TURN_66_NARRATION)
        self.assertTrue(report["answer_act"])
        self.assertTrue(report["unanswered"])
        self.assertIn("water", report["topics"])

    def test_the_same_turn_answered_is_not_flagged(self):
        report = check_answer_act(TURN_66_ACTION, ANSWERED)
        self.assertTrue(report["answer_act"])
        self.assertFalse(report["unanswered"])
        self.assertTrue(report["hits"])

    def test_partial_coverage_counts_as_answered(self):
        # One topic word is enough. A partial answer is prose to improve, not a
        # dodge to rewrite.
        partial = "You mention the water, and leave the rest unsaid." + " padding." * 30
        self.assertFalse(check_answer_act(TURN_66_ACTION, partial)["unanswered"])


class TestLeavesOrdinaryTurnsAlone(unittest.TestCase):
    def test_non_answer_actions_are_never_flagged(self):
        for line in (
            "I survey where I am, noting exits, cover, and who is watching me.",
            "I listen for rumors about the roads, debts, or sealed letters.",
            "I walk a short way along the most promising path, staying alert.",
            "I take stock of my injuries and how tired I am.",
            "I look for honest work a courier could take.",
        ):
            with self.subTest(line=line):
                report = check_answer_act(line, TURN_66_NARRATION)
                self.assertFalse(report["answer_act"], line)
                self.assertFalse(report["unanswered"], line)

    def test_short_narration_is_not_judged(self):
        # Too little prose to call it a dodge; other guards handle short turns.
        self.assertFalse(check_answer_act(TURN_66_ACTION, "You hesitate.")["unanswered"])

    def test_empty_inputs_are_safe(self):
        self.assertFalse(check_answer_act("", "")["answer_act"])
        self.assertFalse(check_answer_act(TURN_66_ACTION, "")["unanswered"])

    def test_an_answer_act_with_no_topic_words_is_not_flagged(self):
        report = check_answer_act("I explain.", "x" * 400)
        self.assertTrue(report["answer_act"])
        self.assertFalse(report["unanswered"], "nothing to check means nothing to flag")


class TestAgainstTheRecordedRun(unittest.TestCase):
    """The shipped detector must stay quiet on real prose.

    Scored over the 100 recorded turns it fires exactly once, on turn 66.
    """

    def test_known_responsive_turns_stay_unflagged(self):
        cases = [
            (
                "I admit out loud that I owe eleven silver to a lender called Hask, "
                "and that the debt comes due at the next full moon.",
                "You admit the debt aloud: eleven silver owed to Hask, due when the moon comes "
                "full again. The words sit badly in the cold air of the camp." + " More prose." * 20,
            ),
            (
                "I confess that I am deathly afraid of deep water and have never learned to swim.",
                "You confess it: deep water frightens you, and you never learned to swim."
                + " The fire crackles on." * 20,
            ),
        ]
        for action, narration in cases:
            with self.subTest(action=action[:40]):
                self.assertFalse(check_answer_act(action, narration)["unanswered"])


if __name__ == "__main__":
    unittest.main()
