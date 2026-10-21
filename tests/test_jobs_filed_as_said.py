"""Jobs are filed as said, steps are written as play happens, pay is an engine ledger (2026-10-22).

8B run 150, T39: Rafe's "I've got a job for you, if you're up for it" (no task
named) was filed as "Loading the Cargo Crates" with four steps nobody said
(inspect, assist, load, secure), and the check's "is it specific" question
said yes. The progress check then judged the player against those invented
steps (T41). F156: a job done and paid in the story was left open and unpaid.

The engine now files only what the line says (giver, the task in the line's
own words, pay if named), asks no model whether the task is specific (the
line has to name a thing, place or act the card is about), writes each deed
on the job into its steps as it happens, and keeps the promised pay on the
job's row: owed at filing, settled once on closing, void when the job is
turned down, failed or abandoned.

Run:  cd tests; ..\\.venv\\Scripts\\python -m unittest test_jobs_filed_as_said
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-jobs-as-said-"))
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


from app import quest_offers as qo, quest_parser as qp, quests  # noqa: E402

RAFE = [{"code": "B", "name": "Rafe", "role": "dock foreman"}]
# 8B run 150, T39 (archived trace turn-...-000040): the paragraph mentions
# crates and loading docks; Rafe's line names no task.
DOCK = (
    "The Dock [[L3]] is a tangle of ropes and crates, the smell of brine thick in the early light. You scan the faces "
    "of the men and women working the loading docks, their backs bent under the weight of their tasks.\n\n"
    "Rafe [[B]]'s gaze flicks to the crates stacked nearby, then to the men working them. \"You're not the only "
    "desperate soul around here,\" he mutters. \"But I've got a job for you, if you're up for it.\""
)
DOCK_INPUT = "I walk out of the Tally House onto the wharf and look for anyone hiring hands for the day."
F150_CARD = {
    "task": "I've got a job for you, if you're up for it.", "title": "Loading the Cargo Crates",
    "steps": ["Inspect the crates stacked nearby", "Assist the men working them", "Load the cargo onto the ship",
              "Ensure the crates are secure"],
    "place": "The Dock", "pay": "A fair wage for the day's work", "gold": 0,
}
# The same giver naming the work.
CRATES = (
    "Rafe [[B]] jerks his chin at the stack. \"I've a job for you. The Hesperian's crates want loading before the tide. "
    "Thirty gold when the last one's aboard.\""
)
CRATES_CARD = {
    "task": "The Hesperian's crates want loading before the tide", "title": "Load the Hesperian's crates",
    "steps": ["Inspect the crates", "Load them", "Secure them"], "place": "The Dock",
    "pay": "Thirty gold when the last one's aboard", "gold": 30,
}


def _fake_ask(fill: dict, check: dict | None = None, progress: dict | None = None):
    calls: list[dict] = []
    check = check if check is not None else {"offered": "yes", "in_text": "yes", "why": "Rafe names the work"}
    progress = progress if progress is not None else {"finished": "no", "why": "more crates to go"}

    def ask(system, user, *, max_tokens, phase):
        payload = json.loads(user)
        calls.append({"phase": phase, "user": payload})
        if phase == qo.FILL_PHASE:
            # The narrator's own sentences (the run's second candidate, a
            # "posting read" about the loading docks) the real fill refused.
            if "Rafe" not in str(payload.get("speaker") or ""):
                return {"offers_work": False}
            return dict(fill)
        if phase == qo.CHECK_PHASE:
            return dict(check)
        return dict(progress)

    return ask, calls


def _fresh():
    from app.db import connect, init_db

    init_db()
    conn = connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("quest_steps", "quests", "journal"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("UPDATE player SET gold = 10, xp = 0 WHERE id = 1")
    return conn


def _gold(conn) -> int:
    return int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"])


def _journal(conn) -> list[str]:
    return [str(r["content"]) for r in conn.execute("SELECT content FROM journal ORDER BY id").fetchall()]


class AnOfferThatNamesNothingIsNoJobYet(unittest.TestCase):
    def test_a_bare_offer_of_work_files_nothing_and_asks_no_check(self):
        ask, calls = _fake_ask(F150_CARD)
        report = qo.run_offer_pass(DOCK, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
        self.assertEqual(report["new"], [])
        self.assertNotIn(qo.CHECK_PHASE, [c["phase"] for c in calls])
        self.assertEqual(report["fills"][0].get("dropped"), "no_thing_named")

    def test_the_crates_in_the_narration_do_not_make_the_line_name_them(self):
        candidate = {"line": "You're not the only desperate soul around here, But I've got a job for you, if you're up for it.",
                     "speaker": RAFE[0]}
        self.assertEqual(qo.names_a_task(F150_CARD, candidate), [])

    def test_pay_alone_names_no_task(self):
        candidate = {"line": "You've done well. Good. You'll be paid well for this.", "speaker": {"name": "Nell", "role": "guildmaster"}}
        card = {"task": "You'll be paid well for this.", "title": "Salvage Work with Rafe", "place": ""}
        self.assertEqual(qo.names_a_task(card, candidate), [])

    def test_a_line_that_names_the_work_is_a_job(self):
        ask, calls = _fake_ask(CRATES_CARD)
        report = qo.run_offer_pass(CRATES, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
        self.assertEqual([c["phase"] for c in calls], [qo.FILL_PHASE, qo.CHECK_PHASE])
        self.assertEqual(len(report["new"]), 1)
        self.assertIn("crat", report["fills"][0]["named"])  # quest_parser._stem of "crates"

    def test_a_place_named_is_enough(self):
        candidate = {"line": "There's work at the old dockyard by the rusted piers, if you want it.", "speaker": None}
        card = {"task": "work at the old dockyard", "title": "Work at the Old Dockyard", "place": "the old dockyard"}
        self.assertTrue(qo.names_a_task(card, candidate))

    def test_the_speakers_own_name_and_trade_name_no_task(self):
        candidate = {"line": "Rafe the foreman has a job for you.", "speaker": RAFE[0]}
        card = {"task": "Rafe the foreman has a job for you", "title": "Foreman Rafe's Job", "place": ""}
        self.assertEqual(qo.names_a_task(card, candidate), [])


class AFiledJobHoldsOnlyWhatTheLineSaid(unittest.TestCase):
    def test_the_fill_is_not_asked_for_steps(self):
        self.assertNotIn("steps", qo.FILL_SHAPE)
        ask, calls = _fake_ask(CRATES_CARD)
        qo.run_offer_pass(CRATES, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
        self.assertNotIn("steps", calls[0]["user"]["return"])

    def test_the_check_asks_two_questions_not_whether_it_is_specific(self):
        ask, calls = _fake_ask(CRATES_CARD)
        qo.run_offer_pass(CRATES, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
        self.assertEqual(sorted(calls[1]["user"]["questions"]), ["in_text", "offered"])

    def test_steps_a_reply_still_writes_are_not_filed(self):
        ask, _calls = _fake_ask(CRATES_CARD)
        report = qo.run_offer_pass(CRATES, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
        item = report["new"][0]
        self.assertEqual([s["title"] for s in item["steps"]], ["The Hesperian's crates want loading before the tide"])
        self.assertEqual(item["reward"]["gold"], 30)
        self.assertTrue(item["_steps_from_play"])


def _file_crates_job(conn, turn: int = 1) -> int:
    """The checked card for the crates job, through validate and apply, taken by the player."""
    ask, _calls = _fake_ask(CRATES_CARD)
    report = qo.run_offer_pass(CRATES, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
    conn.execute("DELETE FROM npcs WHERE code = 'B'")
    conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Rafe', 'dock foreman')")
    out = qp.apply_quest_changes(conn, {"new": report["new"], "updates": [], "source": "checked"},
                                 narration=CRATES, player_input=DOCK_INPUT, turn=turn)
    assert out["created"], out
    qid = int(conn.execute("SELECT id FROM quests ORDER BY id DESC LIMIT 1").fetchone()["id"])
    quests.accept_offered(conn, qid, turn=turn)
    return qid


class StepsAreWrittenAsPlayHappens(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_a_filed_job_has_one_open_step_the_task_as_said(self):
        qid = _file_crates_job(self.conn)
        quest = quests.get_quest(self.conn, qid)
        self.assertTrue(quests.steps_from_play(quest))
        self.assertEqual([s["title"] for s in quest["steps"]], ["The Hesperian's crates want loading before the tide"])

    def test_a_deed_on_the_job_becomes_a_done_step_before_the_task(self):
        qid = _file_crates_job(self.conn)
        logged = quests.log_job_progress(self.conn, qid, "I carry the first two crates up the gangplank.", turn=2, source="engine")
        self.assertEqual(logged["step"], 1)
        quest = quests.get_quest(self.conn, qid)
        self.assertEqual(int(quest["current_step"]), 2)
        self.assertEqual(int(quest["total_steps"]), 2)
        self.assertEqual([(s["title"], s["status"]) for s in quest["steps"]], [
            ("I carry the first two crates up the gangplank.", "completed"),
            ("The Hesperian's crates want loading before the tide", "active"),
        ])
        self.assertTrue(any(line.startswith("Job progress: Load the Hesperian's crates:") for line in _journal(self.conn)))

    def test_one_deed_per_job_per_turn(self):
        qid = _file_crates_job(self.conn)
        self.assertIsNotNone(quests.log_job_progress(self.conn, qid, "I carry a crate aboard.", turn=2))
        self.assertIsNone(quests.log_job_progress(self.conn, qid, "I carry another crate aboard.", turn=2))
        self.assertIsNotNone(quests.log_job_progress(self.conn, qid, "I carry another crate aboard.", turn=3))
        self.assertEqual(int(quests.get_quest(self.conn, qid)["total_steps"]), 3)

    def test_a_failed_act_is_journaled_not_a_done_step(self):
        qid = _file_crates_job(self.conn)
        logged = quests.log_job_progress(self.conn, qid, "I try to shoulder a crate.", turn=2, done=False)
        self.assertEqual(logged["step"], 0)
        self.assertEqual(int(quests.get_quest(self.conn, qid)["total_steps"]), 1)
        self.assertTrue(any("(not done yet)" in line for line in _journal(self.conn)))

    def test_a_job_with_written_steps_is_left_as_it_is(self):
        qid = quests.create_quest(self.conn, title="The Sealed Letter", steps=[{"title": "Read the letter"}, {"title": "Deliver it"}])
        self.assertIsNone(quests.log_job_progress(self.conn, qid, "I read the letter by the lamp.", turn=2))
        self.assertEqual(int(quests.get_quest(self.conn, qid)["total_steps"]), 2)

    def test_finishing_the_task_after_deeds_completes_and_pays(self):
        qid = _file_crates_job(self.conn)
        quests.log_job_progress(self.conn, qid, "I carry the first crates aboard.", turn=2)
        done = quests.complete_quest_step(self.conn, qid, turn=3, source="engine")
        self.assertTrue(done["completed"])
        self.assertEqual(done["paid"]["gold"], 30)

    def test_work_the_progress_check_finds_unfinished_is_written_in(self):
        qid = _file_crates_job(self.conn)
        active = [{"id": qid, "code": f"Q{qid}", "title": "Load the Hesperian's crates", "status": "active",
                   "current_objective": "The Hesperian's crates want loading before the tide"}]
        prose = "By noon the first stack of crates is done, stowed in the Hesperian's hold. Rafe [[B]] nods at the rest."
        ask, _calls = _fake_ask(CRATES_CARD, progress={"finished": "no", "why": "half the crates are aboard"})
        progress = qo.run_progress_pass(prose, "I heave the next crate aboard.", active=active, ask=ask)
        self.assertEqual(progress["updates"], [])
        self.assertEqual([w["quest"] for w in progress["worked"]], [f"Q{qid}"])
        changes = qp.merge_marks({"new": [], "updates": [], "worked": progress["worked"], "_parser_ran": True, "source": "checked"}, [])
        report = qp.apply_quest_changes(self.conn, changes, narration=prose, player_input="I heave the next crate aboard.", turn=4)
        self.assertEqual(len(report.get("progress") or []), 1, report)
        self.assertEqual(int(quests.get_quest(self.conn, qid)["total_steps"]), 2)

    def test_work_not_in_the_prose_is_not_written(self):
        qid = _file_crates_job(self.conn)
        changes = {"new": [], "updates": [], "worked": [{"quest": f"Q{qid}", "evidence": "Words the prose never held at all."}]}
        report = qp.apply_quest_changes(self.conn, changes, narration="Rain on the dock.", player_input="I wait.", turn=4)
        self.assertNotIn("progress", report)
        self.assertEqual(int(quests.get_quest(self.conn, qid)["total_steps"]), 1)


class TheEnginesOwnStepMatchWritesTheDeed(unittest.TestCase):
    """apply_turn: the player's act matched the job's task and the roll came up partial."""

    def test_a_partial_act_on_a_from_play_job_is_a_done_step(self):
        from app import db, world

        db.init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "The Dock", "special_ability_origin": "none"})
        with db.connect().closing() as conn:
            qid = _file_crates_job(conn)
        line = "I carry two of the Hesperian's crates up the gangplank."
        attempt = {"quest_id": qid, "code": f"Q{qid}", "outcome": "partial", "done": False, "candidate_ids": [qid]}
        world.apply_turn({"narration": "You get two crates up the gangplank before your arms give out.",
                          "_quest_step_attempt": attempt}, line)
        with db.connect().closing() as conn:
            quest = quests.get_quest(conn, qid)
        self.assertEqual(quest["status"], "active")
        self.assertEqual([s["status"] for s in quest["steps"]], ["completed", "active"])
        self.assertEqual(quest["steps"][0]["title"], line)


class PayIsAnEngineLedger(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_promised_pay_is_owed_from_filing_with_giver_amount_and_code(self):
        qid = _file_crates_job(self.conn)
        quest = quests.get_quest(self.conn, qid)
        self.assertEqual(quest["pay_status"], "owed")
        self.assertEqual(quests.pay_owed(quest), 30)
        self.assertTrue(any(line == f"Pay owed: 30 gold (from Rafe) for Q{qid} Load the Hesperian's crates"
                            for line in _journal(self.conn)), _journal(self.conn))

    def test_no_amount_named_is_no_pay_owed(self):
        # 8B run 152b, T12: "Pay owed: 15 gold (from Verity Cotter)" for a card whose pay was
        # "They'll want to sign for it" and whose gold was 0 (the 15 was create_quest's default).
        card = {**CRATES_CARD, "pay": "They'll want to sign for it", "gold": 0}
        line = "Rafe [[B]] jerks his chin at the stack. \"I've a job for you. The Hesperian's crates want loading before the tide.\""
        ask, _calls = _fake_ask(card)
        report = qo.run_offer_pass(line, DOCK_INPUT, npcs=RAFE, asked_for_work=True, ask=ask)
        self.assertEqual(report["new"][0]["reward"]["text"], "")
        self.conn.execute("DELETE FROM npcs WHERE code = 'B'")
        self.conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES ('B', 1, 'Rafe', 'dock foreman')")
        qp.apply_quest_changes(self.conn, {"new": report["new"], "updates": [], "source": "checked"},
                               narration=line, player_input=DOCK_INPUT, turn=1)
        self.assertFalse(any(entry.startswith("Pay owed") for entry in _journal(self.conn)), _journal(self.conn))

    def test_the_speakers_own_duty_is_no_job_and_a_question_is_no_yes(self):
        # 8B run 152b, T12: Verity's "I've got to see the name on the delivery" was filed and taken on
        # "Who signs for it?".
        self.assertTrue(qo.speakers_own_task("I’ve got to see the name on the delivery."))
        self.assertFalse(qo.speakers_own_task("I need you to see the name on the delivery."))
        self.assertFalse(qo.speakers_own_task("I need someone to haul these crates."))
        self.assertFalse(qo.speakers_own_task("The Hesperian's crates want loading before the tide"))
        self.assertFalse(qp.player_accepts('"It\'s from the guild office. Who signs for it?"'))
        self.assertTrue(qp.player_accepts('"Where do I sign? I\'ll sign for it now."'))

    def test_a_question_for_the_speaker_and_a_list_of_requirements_are_no_job(self):
        # 8B run 152c, T2: Silas's "Got a job for me?" made a candidate, and "You need a name, a record, and a
        # bit of coin to get started" was filed as "Runners for the Guild".
        self.assertEqual(qo._carries_offer("Morning. Got a job for me?", asked_for_work=False), "")
        self.assertTrue(qo._carries_offer("Got a job for you, if you want it?", asked_for_work=False))
        self.assertTrue(qo.requirement_not_task("You need a name, a record, and a bit of coin to get started."))
        self.assertFalse(qo.requirement_not_task("You need to haul the nets in before the tide."))
        self.assertFalse(qo.requirement_not_task("Bring the crate to the shipwrights."))
        # 8B run 152d, T2: "prove they're worth the trouble" filed as "Prove Your Worth".
        self.assertTrue(qo.requirement_not_task("prove they're worth the trouble"))
        self.assertTrue(qo.requirement_not_task("Show me you can swim."))
        self.assertFalse(qo.requirement_not_task("Show the reeve the ledger before noon."))

    def test_work_someone_else_holds_is_no_offer_and_a_reported_question_is_no_yes(self):
        # 8B run 152d, T1: "That's the guild hall. They'll have work for you, if you can prove you're worth the
        # trouble." was filed and taken on "I ... ask the nearest worker where a flat-runner signs on".
        line = "That's the guild hall. They'll have work for you, if you can prove you're worth the trouble."
        self.assertEqual(qo._code_veto(line, asked_for_work=True), "work_held_by_someone_else")
        self.assertEqual(qo._code_veto("The guild has work for you. I've a job for you too: the nets.", asked_for_work=True), "")
        self.assertFalse(qp.player_accepts("I walk down to the dock and ask the nearest worker where a flat-runner signs on for salvage work."))
        self.assertTrue(qp.player_accepts("I sign on for the salvage work."))
        # 8B run 152e, T4: a clause saying where the player would sign on.
        self.assertFalse(qp.player_accepts("\"I'm told this is where I sign on for salvage work. What's on offer?\""))
        self.assertTrue(qp.player_accepts("\"That's what I came for. I'll sign on.\""))

    def test_a_new_figure_speaks_for_themselves_not_for_the_last_one_named(self):
        # 8B run 152d, T2: the scarred man's "New blood?" was credited to Wystan, named a paragraph before.
        from app.conversation import spoken_lines

        prose = ("You nod your thanks to Wystan Lambard [[A]]. Wystan Lambard [[A]] gives a gruff nod back.\n\n"
                 "Inside, a group of workers are gathered around a table. One of them, a tall man with a scar running "
                 "from his temple to his jaw, looks up as you enter.\n\n"
                 "“New blood?” he asks, his voice rough. “The guild’s always looking for someone.”")
        rows = [{"code": "A", "name": "Wystan Lambard"}]
        lines = spoken_lines(prose, rows, "I walk to the guild hall.")
        self.assertTrue(lines and all(entry["code"] == "" for entry in lines), lines)
        kept = "Wystan Lambard [[A]] looks up. “New blood?” he asks."
        self.assertEqual([entry["code"] for entry in spoken_lines(kept, rows, "")], ["A"])

    def test_the_step_is_never_cut_mid_word(self):
        # 8B run 152c, T3: the step "... without a bit of pr" reached the narrator, which then wrote "a reco.".
        task = ("Carry the guild's three crates of salvaged tools down to the shipwrights before the tide turns. "
                "You're not the kind they'd trust without a bit of proof, so mind the crates and mind the tide.")
        step = qo.parse_fill({"task": task, "title": "Carry the crates"})["steps"][0]
        self.assertEqual(step, "Carry the guild's three crates of salvaged tools down to the shipwrights before the tide turns.")
        long_one = "Carry " + " ".join(["the crate"] * 30)
        cut = qo.parse_fill({"task": long_one, "title": "t"})["steps"][0]
        self.assertTrue(long_one.startswith(cut) and long_one[len(cut)] == " ", cut)

    def test_closing_the_job_pays_once_and_settles(self):
        qid = _file_crates_job(self.conn)
        before = _gold(self.conn)
        quests.complete_quest_step(self.conn, qid, turn=3, source="engine")
        self.assertEqual(_gold(self.conn) - before, 30)
        quest = quests.get_quest(self.conn, qid)
        self.assertEqual((quest["pay_status"], int(quest["pay_settled"]), int(quest["pay_turn"])), ("settled", 30, 3))
        self.assertEqual(quests.pay_owed(quest), 0)
        # A second payout, by any path, pays nothing.
        again = quests.pay_quest_reward(self.conn, qid, turn=4, source="parser")
        self.assertTrue(again["already_settled"])
        self.assertEqual(_gold(self.conn) - before, 30)

    def test_coin_handed_over_in_the_story_settles_without_paying_again(self):
        qid = _file_crates_job(self.conn)
        before = _gold(self.conn)
        quests.complete_quest_step(self.conn, qid, turn=3, to_end=True, source="story_pay", gold_paid_in_story=30)
        self.assertEqual(_gold(self.conn), before)
        quest = quests.get_quest(self.conn, qid)
        self.assertEqual((quest["pay_status"], int(quest["pay_settled"])), ("settled", 30))

    def test_pay_handed_over_ahead_counts_in_what_was_settled(self):
        qid = _file_crates_job(self.conn)
        job = quests.get_quest(self.conn, qid)
        qp.record_advance_pay(self.conn, job, coin_in=10, turn=2)
        before = _gold(self.conn)
        quests.complete_quest_step(self.conn, qid, turn=3, source="engine")
        self.assertEqual(_gold(self.conn) - before, 20)
        self.assertEqual(int(quests.get_quest(self.conn, qid)["pay_settled"]), 30)

    def test_a_failed_job_pays_nothing_and_its_pay_is_void(self):
        qid = _file_crates_job(self.conn)
        quests.fail_quest(self.conn, qid, turn=5, reason="the tide took the ship")
        self.assertEqual(quests.get_quest(self.conn, qid)["pay_status"], "void")
        self.assertFalse(quests.complete_quest_step(self.conn, qid, turn=6)["ok"])

    def test_an_offer_turned_down_or_abandoned_voids_its_pay(self):
        offered = quests.create_quest(self.conn, title="Haul the nets", steps=[{"title": "Haul the nets"}], reward_gold=12, status="offered")
        quests.decline_offered(self.conn, offered, turn=2)
        self.assertEqual(quests.get_quest(self.conn, offered)["pay_status"], "void")
        qid = _file_crates_job(self.conn)
        qp.apply_quest_changes(
            self.conn, {"updates": [{"quest": f"Q{qid}", "action": "abandon", "evidence": "I leave the crates where they lie."}]},
            narration="I leave the crates where they lie.", player_input="I leave the crates where they lie.", turn=3,
        )
        self.assertEqual(quests.get_quest(self.conn, qid)["pay_status"], "void")

    def test_terms_agreed_later_put_the_pay_on_the_ledger(self):
        qid = quests.create_quest(self.conn, title="Sort the pile", steps=[{"title": "Sort the pile"}], reward_gold=0, status="active")
        self.assertEqual(quests.get_quest(self.conn, qid)["pay_status"], "")
        self.assertTrue(quests.mark_pay_owed(self.conn, qid))
        self.assertEqual(quests.get_quest(self.conn, qid)["pay_status"], "owed")

    def test_a_job_from_before_the_ledger_still_pays_once(self):
        qid = quests.create_quest(self.conn, title="Old job", steps=[{"title": "Old job"}], reward_gold=15, status="active")
        self.conn.execute("UPDATE quests SET pay_status = '' WHERE id = ?", (qid,))
        before = _gold(self.conn)
        quests.complete_quest_step(self.conn, qid, turn=2)
        self.assertEqual(_gold(self.conn) - before, 15)
        self.assertEqual(quests.get_quest(self.conn, qid)["pay_status"], "settled")


if __name__ == "__main__":
    unittest.main()
