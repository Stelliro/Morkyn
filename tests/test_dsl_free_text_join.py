"""Unquoted and quote-only DSL facts must keep every word.

JOURNAL, NPC_NOTE, and GM took only args[1] when more tokens existed, so
`JOURNAL rumor the well is poisoned` stored content "the". A quote with no
kind token (`JOURNAL "the well is poisoned"`) was stored as the kind and the
content was empty.

Run: python -m unittest tests.test_dsl_free_text_join
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.turn_dsl import parse_dsl_turn  # noqa: E402

NAR = "You listen while the rain ticks on the shutter and nobody names the well."


def _draft(ops: str) -> str:
    return f"===NAR===\n{NAR}\n\n===OPS===\n{ops.strip()}\n"


class TestFreeTextOpsKeepTheSentence(unittest.TestCase):
    def test_unquoted_journal_keeps_every_word(self):
        turn = parse_dsl_turn(_draft("JOURNAL rumor the well is poisoned"))
        self.assertEqual(turn["journal"], [{"kind": "rumor", "content": "the well is poisoned"}])

    def test_quoted_journal_without_kind_is_a_fact(self):
        turn = parse_dsl_turn(_draft('JOURNAL "the well is poisoned"'))
        self.assertEqual(turn["journal"], [{"kind": "fact", "content": "the well is poisoned"}])

    def test_quoted_journal_kind_still_splits(self):
        turn = parse_dsl_turn(_draft('JOURNAL fact "The scribe kept the ledger open."'))
        self.assertEqual(
            turn["journal"],
            [{"kind": "fact", "content": "The scribe kept the ledger open."}],
        )

    def test_unquoted_npc_note_keeps_the_fact(self):
        turn = parse_dsl_turn(_draft("NPC_NOTE A the merchant lies about the toll"))
        update = turn["index_updates"][0]
        self.assertEqual(update["code"], "A")
        self.assertEqual(update["known_fact"], "the merchant lies about the toll")
        self.assertEqual(update["summary_append"], "the merchant lies about the toll")

    def test_unquoted_talk_keeps_the_topic(self):
        turn = parse_dsl_turn(_draft("TALK F mind the step"))
        self.assertEqual(turn["conversations"][0]["topic"], "mind the step")
        self.assertEqual(turn["conversations"][0]["summary"], "mind the step")

    def test_unquoted_gm_note_keeps_the_sentence(self):
        turn = parse_dsl_turn(_draft("GM offscreen the merchant leaves at dusk"))
        self.assertEqual(turn["gm_events"][0]["trigger"], "offscreen")
        self.assertEqual(turn["gm_events"][0]["summary"], "the merchant leaves at dusk")


if __name__ == "__main__":
    unittest.main()
