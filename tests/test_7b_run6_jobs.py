"""Jobs in the sixth Saltmarrow run on Qwen2.5 7B: a finished pile, agreed pay, pay handed over, who offered it."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run6-jobs-"))
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


SORT_JOB = {"id": 1, "code": "Q1", "title": "Sort salvaged goods", "status": "active", "current_step": 1,
            "total_steps": 1, "current_step_text": "Sort salvaged goods Sort the salvaged goods by type"}

T3_NARRATION = (
    "You nod to Simon Pennick [[A]] and head down to the salvage yard. The overseer, a grizzled man named "
    "Oldfield, is scribbling something on a ledger.\n\n"
    "\"Good mornin',\" Oldfield [[B]] says without looking up. \"What can I get you to do today?\"\n\n"
    "Oldfield [[B]] glances up, his eyes narrowing. \"Aye, there's some light work. I need you to help with the "
    "sorting of salvaged goods. There's a pile of metal and some rags that need to be sorted by type. You'll find "
    "the details on the board there.\""
)
T6_LINE = ("\"Three hundred is what's in the sacks, not what you're paying me.\" I fold my arms. "
           "\"Two gold for the whole pile, sorted by noon. Yes or no?\"")
T6_NARRATION = (
    "The fog hangs heavy over Saltmarrow [[L1]]. \"Three hundred is what's in the sacks, not what you're paying "
    "me,\" you say firmly, folding your arms. \"Two gold for the whole pile, sorted by noon. Yes or no?\"\n\n"
    "Oldfield [[B]]'s expression shifts. \"You're pushing the limits,\" he says slowly. \"But... I suppose we can "
    "agree to that. If the job is done by noon, the gold is yours.\"\n\n"
    "The deal is struck, and the fog seems to thin slightly."
)
T8_LINE = ("I finish the last of the pile and carry the few pieces I set aside over to Oldfield. \"That's the lot "
           "sorted. These looked better than scrap - have a look before they go in the metal heap.\"")
T9_NARRATION = (
    "Oldfield [[B]] gives you a nod of approval. \"Well, you've earned this.\" He hands you a small pouch "
    "containing two gold coins."
)


class AQuoteIsNotWhatThePlayerDoes(unittest.TestCase):
    """T8: 'have a look' inside Isk's own words made the turn look-only and the finished pile went unpaid."""

    def test_speech_is_not_the_act(self):
        from app.world import _quest_passive_turn

        self.assertFalse(_quest_passive_turn("player", T8_LINE))
        self.assertFalse(_quest_passive_turn("player", "\"That's the lot sorted, Oldfield.\""))
        self.assertTrue(_quest_passive_turn("player", "I look around the yard."))
        self.assertTrue(_quest_passive_turn("wait", T8_LINE))

    def test_the_finished_pile_is_done(self):
        from app import quest_parser
        from app.world import _quest_passive_turn

        evidence = ("You finish the last of the piles and carry the few pieces you set aside over to Oldfield [[B]]. "
                    "\"That's the lot sorted. These looked better than scrap - have a look before they go in the metal heap.\"")
        accepted, rejected = quest_parser.validate_quest_changes(
            {"updates": [{"quest": "Q1", "action": "step_done", "evidence": evidence}]},
            narration=evidence, player_input=T8_LINE, existing=[SORT_JOB],
            passive=_quest_passive_turn("player", T8_LINE),
        )
        self.assertEqual([u["code"] for u in accepted["updates"]], ["Q1"], rejected)


class SortingIsTheSortJob(unittest.TestCase):
    def test_word_forms_match(self):
        from app import quest_parser

        self.assertTrue(quest_parser._quote_names_the_job("You sorted the metal into heaps.", SORT_JOB))
        self.assertEqual(quest_parser.done_check("You finish sorting the last of the scrap.", SORT_JOB), [])

    def test_work_under_way_is_not_done(self):
        from app import quest_parser

        for quote in (
            "You continue sorting, your hands moving methodically through the debris.",  # T7
            "You start sorting the goods, the fog making the task harder.",  # T5
        ):
            self.assertEqual(quest_parser.done_check(quote, SORT_JOB), ["evidence_is_work_in_progress"], quote)
        # T9: progress that names no job is not about it at all.
        self.assertTrue(quest_parser.done_check(
            "By the time the shed door creaks open, you've managed to make significant progress.", SORT_JOB))


class TheAgreedPay(unittest.TestCase):
    """T6: 'Two gold for the whole pile' was agreed; the job kept its rolled 11 gold."""

    def test_player_terms_agreed(self):
        from app.quest_parser import agreed_job_price

        self.assertEqual(agreed_job_price(T6_NARRATION, T6_LINE), (2, "player_terms_agreed"))

    def test_refused_terms_set_nothing(self):
        from app.quest_parser import agreed_job_price

        refused = T6_NARRATION.replace("I suppose we can agree to that.", "No deal, Isk.")
        self.assertEqual(agreed_job_price(refused, T6_LINE), (None, ""))
        unanswered = "Oldfield [[B]] grunts and turns back to his ledger."
        self.assertEqual(agreed_job_price(unanswered, T6_LINE), (None, ""))

    def test_giver_terms(self):
        from app.quest_parser import agreed_job_price

        text = "Roger [[C]] scratches his chin. \"I'll pay you five gold for the haul, no more.\""
        self.assertEqual(agreed_job_price(text, "What does it pay?"), (5, "giver_terms"))


def _save_with_job(reward_gold: int = 11, status: str = "active"):
    from app.db import connect, init_db
    from app.quests import create_quest

    init_db()
    with connect() as conn:
        for table in ("quest_steps", "quests", "npcs"):
            conn.execute(f"DELETE FROM {table}")
        if not conn.execute("SELECT 1 FROM player WHERE id = 1").fetchone():
            conn.execute("INSERT INTO player (id, name) VALUES (1, 'Isk')")
        conn.execute("UPDATE player SET gold = 14, xp = 0 WHERE id = 1")
        conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('A', 1, 'Simon Pennick', 'wheelwright')")
        conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Oldfield', 'overseer')")
        oldfield = conn.execute("SELECT id FROM npcs WHERE code = 'B'").fetchone()[0]
        qid = create_quest(
            conn, title="Sort salvaged goods", description="Help with sorting metal and rags by type Promised: None",
            steps=[{"title": "Sort salvaged goods", "description": "Sort the salvaged goods by type"}],
            reward_gold=reward_gold, reward_xp=18, giver_npc_id=oldfield, status=status,
        )
        conn.execute("UPDATE quests SET code = 'Q1' WHERE id = ?", (qid,))
        conn.commit()
    return qid


class AgreedPayBecomesTheReward(unittest.TestCase):
    def test_settled_on_the_job_taken_this_turn(self):
        from app.db import connect
        from app.quest_parser import settle_agreed_price

        qid = _save_with_job(11, status="offered")
        with connect() as conn:
            change = settle_agreed_price(conn, narration=T6_NARRATION, player_input=T6_LINE, turn=7, touched_codes={"Q1"})
            row = conn.execute("SELECT reward_gold, description FROM quests WHERE id = ?", (qid,)).fetchone()
        self.assertEqual((change["from"], change["to"]), (11, 2))
        self.assertEqual(row["reward_gold"], 2)
        self.assertTrue(row["description"].endswith("Promised: 2 gold"), row["description"])


class PayHandedOverFinishesTheJob(unittest.TestCase):
    """T9: Oldfield handed over the two gold for the sorting; the job stayed open with 11 gold still owed."""

    def test_paid_once(self):
        from app.db import connect
        from app.quest_parser import job_paid_in_prose
        from app.quests import complete_quest_step

        qid = _save_with_job(2)
        with connect() as conn:
            job = job_paid_in_prose(conn, narration=T9_NARRATION, coin_in=2)
            self.assertIsNotNone(job)
            self.assertEqual(int(job["id"]), qid)
            done = complete_quest_step(conn, qid, turn=10, to_end=True, source="story_pay", gold_paid_in_story=2)
            player = conn.execute("SELECT gold, xp FROM player WHERE id = 1").fetchone()
            status = conn.execute("SELECT status FROM quests WHERE id = ?", (qid,)).fetchone()[0]
        self.assertTrue(done["completed"])
        self.assertEqual(done["paid"]["gold"], 0)
        self.assertEqual(player["gold"], 14)  # the story's two gold already reached the purse
        self.assertGreater(player["xp"], 0)
        self.assertEqual(status, "completed")

    def test_needs_the_giver_and_the_work(self):
        from app.db import connect
        from app.quest_parser import job_paid_in_prose

        _save_with_job(11)
        with connect() as conn:
            # The giver is not in the scene.
            self.assertIsNone(job_paid_in_prose(conn, narration="Isolde hands you two gold coins for the candles.", coin_in=2))
            # The giver is here, but the coin is for something else and is not the job's pay.
            self.assertIsNone(job_paid_in_prose(
                conn, narration="Oldfield [[B]] counts out two gold coins for the brass fitting you sold him.", coin_in=2))
            # The giver says it is for the work.
            self.assertIsNotNone(job_paid_in_prose(conn, narration=T9_NARRATION, coin_in=2))

    def test_a_model_gold_op_alone_pays_no_job(self):
        from app.db import connect
        from app.world import _settle_story_terms_and_pay

        qid = _save_with_job(2)
        with connect() as conn:
            result = {"player": {"gold_delta": 2}}
            report = _settle_story_terms_and_pay(
                conn, result, {"status": "empty", "created": [], "updated": [], "rejected": []},
                narration=T9_NARRATION, player_input="I wait.", turn=10, skip_ids=set(),
                gold_note={"source": "stated", "gold_delta": 2},
            )
            self.assertEqual(report["updated"], [])
            report = _settle_story_terms_and_pay(
                conn, result, {"status": "empty", "created": [], "updated": [], "rejected": []},
                narration=T9_NARRATION, player_input="Two gold, by noon, we said.", turn=10, skip_ids=set(),
                gold_note={"source": "prose_received", "gold_delta": 2},
            )
            status = conn.execute("SELECT status FROM quests WHERE id = ?", (qid,)).fetchone()[0]
        self.assertEqual(report["updated"][0]["source"], "story_pay")
        self.assertEqual(status, "completed")


class TheGiverIsWhoOffersIt(unittest.TestCase):
    """T3: Oldfield spoke the offer; the parser named Simon, who was only standing by."""

    def test_speaker_wins(self):
        from app import quest_parser

        npcs = [{"id": 1, "code": "A", "name": "Simon Pennick"}, {"id": 2, "code": "B", "name": "Oldfield"}]
        offer = ("\"I need you to help with the sorting of salvaged goods. There's a pile of metal and some rags that "
                 "need to be sorted by type. You'll find the details on the board there.\"")
        accepted, rejected = quest_parser.validate_quest_changes(
            {"new": [{"title": "Sort salvaged goods", "summary": "Help with sorting metal and rags by type",
                      "giver": "A", "steps": [{"title": "Sort salvaged goods"}], "offer_line": offer, "evidence": offer}]},
            narration=T3_NARRATION, player_input="I head down to the salvage yard.", npcs=npcs, existing=[],
        )
        self.assertEqual(len(accepted["new"]), 1, rejected)
        self.assertEqual(accepted["new"][0]["giver_npc_id"], 2)
        self.assertEqual(accepted["new"][0]["giver_name"], "Oldfield")

    def test_two_people_named_keeps_the_parser_giver(self):
        from app.quest_parser import _offer_speaker

        npcs = [{"id": 1, "code": "A", "name": "Simon Pennick"}, {"id": 2, "code": "B", "name": "Oldfield"}]
        text = "Oldfield [[B]] nods at Simon. \"I need you to help with the sorting of salvaged goods today.\""
        self.assertIsNone(_offer_speaker(text, "I need you to help with the sorting of salvaged goods today.", npcs))


if __name__ == "__main__":
    unittest.main()
