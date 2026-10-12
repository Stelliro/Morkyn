"""Offers, leads and quests from the Saltmarrow API-bridge run (playtest #114-#117).

Each case pins one finding from docs/showcase/saltmarrow-findings.md (Q1-Q4).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-saltmarrow-quests-"))
_ENV = isolated_data_env(str(_TMP))
os.environ.update(_ENV)

from app import local_intel, quest_parser, quests, turn_prompts  # noqa: E402

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


def _fresh():
    from app.db import connect, init_db

    init_db()
    conn = connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("quest_steps", "quests", "journal"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("DELETE FROM settings WHERE key IN ('turn_prompts', 'scene_thread')")
    return conn


BELL = {"title": "Raise the customs-house bell", "giver": ""}
TOWER = {"title": "Keep the tide tower", "giver": "Una Rendle"}
BREAD = {"title": "A debt of bread", "giver": "Una Rendle"}


class TypedAcceptance(unittest.TestCase):
    """#114: signing, writing a name in the book and "we'll take it" were not read as taking the job."""

    def test_signing_takes_the_one_offer(self):
        for line in (
            "I ring the hand bell on the sill and wait at the window to sign for the bell.",
            'I take the pen and write my name in the book: Isk Tarrow. "Has anyone else signed?"',
        ):
            self.assertIs(local_intel.typed_offer_choice([BELL], line), BELL, line)

    def test_we_take_it_names_one_of_two(self):
        line = 'I look at Mam. She writes her name, and I write mine under it. "We\'ll take it, Una. The tower and the bell."'
        self.assertIs(local_intel.typed_offer_choice([TOWER, BREAD], line), TOWER)

    def test_job_words_still_work(self):
        self.assertIs(local_intel.typed_offer_choice([BELL], "I'll take the job."), BELL)

    def test_not_an_acceptance(self):
        self.assertIsNone(local_intel.typed_offer_choice([BELL], "I'll take the rope."))
        self.assertIsNone(local_intel.typed_offer_choice([BELL], "I'll take it. Here's three coin."))
        self.assertIsNone(local_intel.typed_offer_choice([BELL], "I deal with the rats first."))
        self.assertIsNone(local_intel.typed_offer_choice([TOWER, BREAD], "We'll take it."))
        self.assertFalse(local_intel.typed_accept("We're in the tower now."))

    def test_parser_reads_the_same_words(self):
        self.assertTrue(quest_parser.player_accepts("I take the pen and write my name in the book."))

    def test_draft_status_names_match(self):
        from app import turn_dsl

        src = Path(turn_dsl.__file__).read_text(encoding="utf-8")
        self.assertNotIn("marked accepted_now", src)
        self.assertIn("player_takes_it_now", src)


class SigningIsTheFirstStep(unittest.TestCase):
    """#116: accepting and signing in one turn left step 1 current for the whole quest."""

    STEPS = [
        {"title": "Sign for the contract", "description": "Ring at the tally-house window and have your name put in the book."},
        {"title": "Reach the old customs house", "description": "Cross the flats to the customs house."},
        {"title": "Bring the bell back whole", "description": "Get the bronze bell back uncracked."},
    ]

    def _offer(self, conn):
        return quests.create_quest(conn, title=BELL["title"], steps=self.STEPS, status="offered")

    def test_signing_now_finishes_the_signing_step(self):
        with _fresh() as conn:
            qid = self._offer(conn)
            got = quests.accept_offered(conn, qid, turn=6, player_line="I take the pen and write my name in the book: Isk Tarrow.")
            self.assertEqual(got["status"], "active")
            self.assertEqual(int(got["current_step"]), 2)

    def test_waiting_to_sign_does_not(self):
        with _fresh() as conn:
            qid = self._offer(conn)
            got = quests.accept_offered(conn, qid, turn=5, player_line="I wait at the window to sign for the bell.")
            self.assertEqual(int(got["current_step"]), 1)

    def test_button_accept_has_no_line(self):
        with _fresh() as conn:
            qid = self._offer(conn)
            self.assertEqual(int(quests.accept_offered(conn, qid, turn=5)["current_step"]), 1)

    def test_typed_accept_path(self):
        with _fresh() as conn:
            qid = self._offer(conn)
            local_intel.accept_offered_quest(conn, "I take the pen and write my name in the book.", turn=6)
            row = conn.execute("SELECT status, current_step FROM quests WHERE id = ?", (qid,)).fetchone()
            self.assertEqual((row["status"], int(row["current_step"])), ("active", 2))


class AnotherGiversJob(unittest.TestCase):
    """#117: Mara's "Ring the customs bell" was rejected as a duplicate of the guild's bell job."""

    def test_other_giver_other_verb_is_not_a_duplicate(self):
        existing = [{"id": 1, "code": "Q1", "title": "Raise the customs-house bell", "status": "active", "giver_npc_id": None}]
        self.assertIsNone(quest_parser._is_duplicate({"title": "Ring the customs bell"}, existing, 11, ""))

    def test_rewording_is_still_a_duplicate(self):
        existing = [{"id": 1, "code": "Q1", "title": "Raise the customs-house bell", "status": "active", "giver_npc_id": 11}]
        self.assertIsNotNone(quest_parser._is_duplicate({"title": "Raise the customs bell"}, existing, 11, ""))
        self.assertIsNotNone(quest_parser._is_duplicate({"title": "Raise the customs bell"}, existing, 4, ""))
        nobody = [dict(existing[0], giver_npc_id=None)]
        self.assertIsNotNone(quest_parser._is_duplicate({"title": "Ring the customs bell"}, nobody, None, ""))


class ClockOffersAreNotVoiced(unittest.TestCase):
    """#114: an engine-posted offer read to the draft as the giver's offer waiting for an answer."""

    def test_not_raised_until_voiced(self):
        with _fresh() as conn:
            qid = quests.create_quest(
                conn, title=BREAD["title"], steps=[{"title": "A debt of bread"}], status="offered", notes="clock:npc:4"
            )
            conn.commit()
        rows = [r for r in local_intel.list_open_offers() if r["id"] == qid]
        self.assertIs(rows[0]["voiced"], False)
        with _fresh() as conn:
            pass  # _fresh clears; re-create and mark voiced the way the parser does
        with _fresh() as conn:
            qid = quests.create_quest(
                conn, title=BREAD["title"], steps=[{"title": "A debt of bread"}], status="offered", notes="clock:npc:4"
            )
            conn.execute(
                "UPDATE quests SET notes = notes || '; voiced' WHERE (code = ? OR CAST(id AS TEXT) = ?) "
                "AND notes LIKE 'clock:%' AND notes NOT LIKE '%voiced%'",
                (f"Q{qid}", f"Q{qid}"),
            )
            conn.commit()
        rows = [r for r in local_intel.list_open_offers() if r["id"] == qid]
        self.assertIs(rows[0]["voiced"], True)


class GoWithIsRead(unittest.TestCase):
    """#115: "I go with Jocosa, behind her" (the Go with button's words) left the lead waiting."""

    def _lead(self, conn, to=None, to_label="the Lantern Wives' lamp"):
        record = {"turn": 19, "items": [{"id": "t19-1", "kind": "walk_with", "npc_code": "F", "npc_name": "Jocosa Kettle",
                                         "to": to, "to_label": to_label, "source": "lead_op", "turn": 19}], "stayed": []}
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('turn_prompts', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(record),),
        )

    def test_typed_go_with(self):
        with _fresh() as conn:
            self._lead(conn)
            for line in (
                "I go with Jocosa, behind her, putting my feet where she puts hers, out toward the lamp.",
                "I follow her across the mud.",
                "Lead on.",
            ):
                self.assertIsNotNone(turn_prompts.typed_go_with(conn, line), line)
            for line in ("I don't go with her.", "I ask Jocosa about the lamp.", "I stay here."):
                self.assertIsNone(turn_prompts.typed_go_with(conn, line), line)

    def test_lead_keeps_the_place_words(self):
        with _fresh() as conn:
            leads = turn_prompts._leads(
                conn, {}, {"leads": [{"npc": "F", "to": "the Lantern Wives' lamp"}]},
                [{"code": "F", "name": "Jocosa Kettle"}], {}, [],
            )
            self.assertEqual(leads[0]["to_label"], "the Lantern Wives' lamp")

    def test_gate_joins_the_leader_up(self):
        with _fresh() as conn:
            self._lead(conn)
            trace = turn_prompts.gate_after_turn(
                conn, narration="", movement_report={}, quest_report={}, prompt_context={}, dsl={},
                direction_hint=None, player_input="I go with Jocosa, behind her.", turn=20,
            )
            self.assertIn("typed_go_with:F", trace["notes"])
            thread = json.loads(conn.execute("SELECT value FROM settings WHERE key = 'scene_thread'").fetchone()[0])
            self.assertEqual([row["name"] for row in thread["with"]], ["Jocosa Kettle"])


if __name__ == "__main__":
    unittest.main()
