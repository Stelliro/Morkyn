"""
Ask answers only from what the game recorded.

The Miriam Shaw save: "where did the prayer beads come from?" was answered
with the prompt's own sample sentence, and the follow-up "i can see they were
added to my inventory though" (no item named) with "The packet you received
includes a voice recording" -- invented, and in the prompt's internal words.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_TMP = Path(tempfile.mkdtemp(prefix="morkyn-ask-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    }
)

from app import ask, db, world  # noqa: E402
from app.db import connect  # noqa: E402


class TestAskIsGrounded(unittest.TestCase):
    def setUp(self):
        db.init_db()
        world.start_playthrough({"player_name": "Tomas Reed", "start_location": "Low Gate", "special_ability_origin": "none"})
        with connect() as conn:
            conn.execute(
                "INSERT INTO inventory (code, name, description, quantity) VALUES ('I9', 'prayer beads', '', 2)"
            )
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (3, 'dice', 'item_count (small): 1d2 [2] = 2 for prayer beads')"
            )
            conn.commit()
        ask._LAST_SUBJECT.clear()
        self.calls = []
        self._original = ask._chat_json

        def fake(system, user, **kwargs):
            self.calls.append((system, user))
            return {"answer": "They arrived on turn 3.", "remember": "", "edit": ""}

        ask._chat_json = fake

    def tearDown(self):
        ask._chat_json = self._original

    def test_the_prompt_has_no_internal_words_or_sample_answer(self):
        self.assertNotIn("packet", ask.ASK_SYSTEM.lower())
        self.assertNotIn("The sheet only has", ask.ASK_SYSTEM)

    def test_an_item_record_carries_its_history(self):
        ask.ask_about("where did the prayer beads come from?")
        system, user = self.calls[-1]
        self.assertIn("turn 3", user)
        self.assertIn('"addressed_to": "dm"', user)

    def test_a_follow_up_uses_the_last_subject(self):
        ask.ask_about("where did the prayer beads come from?")
        ask.ask_about("i can see they were added to my inventory though")
        self.assertEqual(len(self.calls), 2)
        self.assertIn("prayer beads", self.calls[-1][1])

    def test_no_subject_means_no_model_call(self):
        out = ask.ask_about("what happened to the other thing")
        self.assertEqual(self.calls, [])
        self.assertIn("can't tell which thing", out["answer"])


if __name__ == "__main__":
    unittest.main()
