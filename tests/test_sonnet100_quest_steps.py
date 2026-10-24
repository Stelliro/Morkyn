"""F195: quest steps are task phrases; a job said done binds by reference (sonnet100, 2026-10-25).

The Hermes 3 8B run played by Sonnet (docs/showcase/hermes-sonnet100-2026-10-25)
filed 14 quest step rows and 12 of them were a sentence of the scene or the
player's own question: the progress pass wrote the keyword sentence it found
as the deed ("Who wants what, and what it pays?" T22, "The rain soaks into
your cloak as you start searching ..." T24, "He looks at you, his eyes
glinting in the candlelight." T37, "Elric calls down to you again as you
finish," T66). A walk away from the Guild Yard finished and paid "Deliver
Exposed Salvage" (T79), while Eadric's "Second job's complete too" was a
mark on the quest "complete" and refused as unknown_quest (T84).

Now: one small ask names the work in a few words and the engine keeps it only
when it is a task phrase the text holds; a spoken "the job's done" binds to an
open job by reference (@Q1, "second job", the giver, the job named, the only
job) before any text match; a trip's job is not finished by walking somewhere
else.

Run:  cd tests; ../.venv/bin/python -m unittest test_sonnet100_quest_steps
"""
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-sonnet100-quest-steps-"))
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


from app import quest_offers as qo, quest_parser as qp, quests, turn_ledger  # noqa: E402

# --- The recorded turns (sonnet100 turns/NNN.json, player_line and narration) ---
T22_LINE = "I ask @E about the job he mentioned: who wants what, and what it pays."
T22 = (
    'Behind the counter, Stephen [[E]] raises an eyebrow. "Another early riser? Or did you get lost on the flats this '
    'time of night?" You clear your throat. "I was wondering about that salvage job you mentioned. Who wants what, and '
    'what it pays?"\n\nStephen [[E]]\'s expression turns businesslike. "I\'ve got a client looking for a brass '
    "tide-reckoner, and I'll pay well for it.\""
)
T24_LINE = ("I leave the store without selling and head to #L4, the drowned lower district, to look for more salvage "
            "before the tide turns.")
T24 = (
    "You leave the store without selling and head to the drowned lower district [[L4]] to look for salvage before the "
    "tide turns. The storm outside is steady, but you have a hooded cloak to keep the worst of the rain off. The path is "
    "slippery underfoot. There is no one else around in the storm, just the sound of the rain and the waves lapping "
    "against the seawall. The rain soaks into your cloak as you start searching through the debris and wreckage for "
    "anything valuable that the tide hasn't yet carried away."
)
T24_STEP = ("The rain soaks into your cloak as you start searching through the debris and wreckage for anything "
            "valuable that the tide hasn't yet carried away.")
T37_LINE = "I tell @D I am going out onto the flats tonight to wait for the dead, and ask what I should watch for."
T37 = (
    'You are sitting with Elric [[D]] in the Old Lighthouse [[L3]]. He looks at you, his eyes glinting in the '
    'candlelight. "The exposed ones wash up on the saltflats. You\'ll know them when you see them. They\'re usually... '
    'not whole. Watch out for the scavengers."'
)
T37_STEP = "He looks at you, his eyes glinting in the candlelight."
T66_LINE = "The tide has gone out now. I head to #L4 and pick through the exposed flats for salvage to take to the guild."
T66 = (
    "You head out into the pale morning light and make your way down to the drowned lower district [[L4]]. The flats are "
    "bleak but you start picking through the mud and rocks, searching for any treasures the sea may have left behind.\n\n"
    "You keep sorting through the mudflats, searching for anything of value. The work is slow but the sea has left some "
    "small haul scattered across the flats. You gather what you can and pack it all into a burlap sack.\n\n"
    "Elric [[D]] calls down to you again as you finish, \"Third times you've dug graves this cycle already. You'll need "
    "more than a few coins to settle your debts.\""
)
T66_STEP = "Elric [[D]] calls down to you again as you finish,"
T79_LINE = "I give up on hauling it, shoulder my pack and head to #L1, Saltmarrow, to find the tallyman."
T79 = (
    "You trudged out of the Guild Yard [[L10]], leaving the hard work behind. The sun hung low over the Salt Marsh, "
    "casting long shadows over the exposed flats. You clutched your pack, the weight of the salvaged goods making you "
    "pause. The tallyman would be in Saltmarrow [[L1]]. Time to settle up. You followed the winding path towards the "
    "distant town, the mud sucking at your boots with each step. \"Good day to be out, traveler,\" he called out. "
    "\"The flats are generous this tide.\" You grunted in acknowledgment and kept walking, the cobbled streets of "
    "Saltmarrow [[L1]] looming ahead. The Guild Yard [[L10]] would still be there when you returned. For now, you had "
    "business with the tallyman."
)
T79_EVIDENCE = "The Guild Yard [[L10]] would still be there when you returned."
T84_LINE = ("I hold out my hand and say: Eadric, I heard you say the job is done. Hand me the coin you owe, and mark the "
            "second job, the delivery, complete too.")
T84 = (
    'The salvage yard is quiet at this early hour, the fog just beginning to lift. Eadric [[F]] watches you warily from '
    'across the yard.\n\n"Alright Isk," he says, "I said the job\'s done. Here\'s the coin for the first job, and the '
    'mark that it\'s delivered."\n\nHe tosses a leather pouch into your hand and moves to the ledger, making a quick X '
    'next to your name.\n\n"Second job\'s complete too," he calls over his shoulder. "Another fifty in the pouch."'
)

Q1_ROW = {"id": 1, "code": "Q1", "title": "Salvage Flats After Tide", "status": "active",
          "current_objective": "find exposed flats, salvage what's there"}


def _fresh():
    from app.db import connect, init_db

    init_db()
    conn = connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("quest_steps", "quests", "journal", "npcs"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("UPDATE player SET gold = 11, xp = 0 WHERE id = 1")
    return conn


def _npc(conn, code: str, name: str, role: str) -> int:
    conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (code, name, role))
    return int(conn.execute("SELECT id FROM npcs WHERE code = ?", (code,)).fetchone()["id"])


def _place(conn, code: str, name: str) -> None:
    if not conn.execute("SELECT 1 FROM locations WHERE name = ?", (name,)).fetchone():
        conn.execute("INSERT INTO locations (code, name) VALUES (?, ?)", (code, name))


def _gold(conn) -> int:
    return int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"])


def _status(conn, qid: int) -> str:
    return str(conn.execute("SELECT status FROM quests WHERE id = ?", (qid,)).fetchone()["status"])


def _salvage_world(conn):
    """sonnet100 at T79-T84: Q1 from Elric, Q2 (deliver to the Guild) from Lettice, Eadric the guild tallyman."""
    lettice = _npc(conn, "B", "Lettice Orme", "message runner")
    elric = _npc(conn, "D", "Elric", "reeve's deputy")
    _npc(conn, "F", "Eadric", "guild tallymen")
    _place(conn, "L10", "The Guild Yard")
    _place(conn, "L12", "to Saltmarrow")
    q1 = quests.create_quest(conn, title="Salvage Flats After Tide", steps=[{"title": "find exposed flats, salvage what's there"}],
                             reward_gold=15, reward_xp=25, giver_npc_id=elric, notes=quests.STEPS_FROM_PLAY_NOTE)
    q2 = quests.create_quest(conn, title="Deliver Exposed Salvage", steps=[{"title": "Bring exposed salvaged goods to the Guild"}],
                             reward_gold=15, reward_xp=25, giver_npc_id=lettice, notes=quests.STEPS_FROM_PLAY_NOTE)
    return q1, q2


def _ask(progress: dict, deed: dict | None):
    calls: list[str] = []

    def ask(system, user, *, max_tokens, phase):
        calls.append(phase)
        if phase == qo.DEED_PHASE:
            return dict(deed or {})
        return dict(progress)

    return ask, calls


class AStepIsATaskPhrase(unittest.TestCase):
    def test_the_recorded_step_rows_are_refused(self):
        # T22: the player's own question, inside its closing quote.
        self.assertEqual(qp.task_phrase_problem('Who wants what, and what it pays?"', T22, T22_LINE), "question")
        # T24, T37, T66: sentences of the scene.
        self.assertTrue(qp.task_phrase_problem(T24_STEP, T24, T24_LINE))
        self.assertEqual(qp.task_phrase_problem(T37_STEP, T37, T37_LINE), "scene_sentence")
        self.assertTrue(qp.task_phrase_problem(T66_STEP, T66, T66_LINE))
        # The player's voice and talk about the job.
        self.assertEqual(qp.task_phrase_problem("I was wondering about that salvage job", T22, T22_LINE), "players_voice")
        self.assertEqual(qp.task_phrase_problem("asked about the salvage job", T22, T22_LINE, quest=Q1_ROW),
                         "talk_is_not_work")
        self.assertEqual(qp.task_phrase_problem("none", T37, T37_LINE), "no_work")

    def test_a_task_phrase_the_text_holds_is_kept(self):
        self.assertEqual(qp.task_phrase_problem("search the debris and wreckage for salvage", T24, T24_LINE, quest=Q1_ROW), "")
        self.assertEqual(qp.task_phrase_problem("You gather the haul into a burlap sack.", T66, T66_LINE, quest=Q1_ROW), "")
        self.assertEqual(qp.task_phrase("You gather the haul into a burlap sack."), "Gather the haul into a burlap sack")
        # Words the text never held are no deed.
        self.assertEqual(qp.task_phrase_problem("repair the lighthouse lamp", T24, T24_LINE), "not_in_text")

    def test_the_t22_question_is_no_progress_candidate(self):
        self.assertEqual(qo.find_progress_candidates(T22, T22_LINE, active=[Q1_ROW]), [])


class TheProgressPassWritesTheDeedNotTheSentence(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def _run(self, narration, line, deed):
        q1 = quests.create_quest(self.conn, title="Salvage Flats After Tide",
                                 steps=[{"title": "find exposed flats, salvage what's there"}],
                                 reward_gold=15, notes=quests.STEPS_FROM_PLAY_NOTE)
        active = [{**Q1_ROW, "id": q1, "code": f"Q{q1}"}]
        ask, calls = _ask({"finished": "no", "why": "the work is still going on"}, deed)
        report = qo.run_progress_pass(narration, line, active=active, ask=ask)
        changes = {"new": [], "updates": [], "worked": report["worked"], "source": "checked"}
        qp.apply_quest_changes(self.conn, changes, narration=narration, player_input=line, turn=25)
        steps = [s["title"] for s in quests.get_quest(self.conn, q1)["steps"]]
        return report, calls, steps

    def test_t24_a_model_echoing_the_sentence_writes_no_step(self):
        report, calls, steps = self._run(T24, T24_LINE, {"work": T24_STEP})
        self.assertIn(qo.DEED_PHASE, calls)
        self.assertEqual(report["worked"], [])
        self.assertEqual(steps, ["find exposed flats, salvage what's there"])

    def test_t24_a_task_phrase_is_the_step(self):
        report, _calls, steps = self._run(T24, T24_LINE, {"work": "search the debris and wreckage for salvage"})
        self.assertEqual(report["worked"][0]["deed"], "Search the debris and wreckage for salvage")
        self.assertEqual(steps, ["Search the debris and wreckage for salvage", "find exposed flats, salvage what's there"])

    def test_t66_the_scene_sentence_is_refused_and_the_gathering_kept(self):
        _r, _c, refused = self._run(T66, T66_LINE, {"work": T66_STEP})
        self.assertEqual(refused, ["find exposed flats, salvage what's there"])

    def test_a_worked_row_with_no_deed_writes_nothing(self):
        q1 = quests.create_quest(self.conn, title="Salvage Flats After Tide",
                                 steps=[{"title": "find exposed flats, salvage what's there"}], notes=quests.STEPS_FROM_PLAY_NOTE)
        changes = {"new": [], "updates": [], "worked": [{"quest": f"Q{q1}", "evidence": T37_STEP}]}
        qp.apply_quest_changes(self.conn, changes, narration=T37, player_input=T37_LINE, turn=38)
        self.assertEqual(int(quests.get_quest(self.conn, q1)["total_steps"]), 1)


class AJobSaidDoneBindsByReference(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_t84_second_job_complete_too_completes_q2_and_pays(self):
        q1, q2 = _salvage_world(self.conn)
        quests.complete_quest_step(self.conn, q1, turn=85, to_end=True, source="test")  # T83 closed Q1
        gold = _gold(self.conn)
        # The narrator's mark named the quest "complete" (turns/084.json: payout_refused unknown_quest).
        changes = {"new": [], "updates": [{"quest": "complete", "action": "step_done", "evidence": "", "_from_mark": True}],
                   "source": "parser+marks"}
        report = qp.apply_quest_changes(self.conn, changes, narration=T84, player_input=T84_LINE, turn=86)
        self.assertEqual(_status(self.conn, q2), "completed", report)
        self.assertEqual(_gold(self.conn), gold + 15)
        self.assertEqual([u["code"] for u in report["updated"]], [f"Q{q2}"])

    def test_t84_with_no_proposal_at_all_still_completes_q2(self):
        q1, q2 = _salvage_world(self.conn)
        quests.complete_quest_step(self.conn, q1, turn=85, to_end=True, source="test")
        report = qp.apply_quest_changes(self.conn, {}, narration=T84, player_input=T84_LINE, turn=86)
        self.assertEqual(_status(self.conn, q2), "completed", report)

    def test_t84_with_both_jobs_open_the_second_job_is_q2(self):
        q1, q2 = _salvage_world(self.conn)
        ctx = qp.load_quest_context(self.conn, 86)
        bound = qp.bind_said_done(T84, T84_LINE, npcs=ctx["npcs"], existing=ctx["existing"])
        # "the second job, the delivery" in the player's line and Eadric's "Second job's complete too":
        # Q2 only; Q1 is not finished by a line that never names it.
        self.assertEqual([b["quest"] for b in bound], [f"Q{q2}"])
        self.assertIn(bound[0]["_bound"], {"ordinal", "named"})

    def test_a_quest_code_in_the_players_line_binds_first(self):
        q1, q2 = _salvage_world(self.conn)
        ctx = qp.load_quest_context(self.conn, 86)
        prose = 'Eadric [[F]] nods at the ledger. "The work is done," he says.'
        bound = qp.bind_said_done(prose, "I ask @F to mark @Q1 done.", npcs=ctx["npcs"], existing=ctx["existing"])
        self.assertEqual([b["quest"] for b in bound], [f"Q{q1}"])
        # Two open jobs, no reference, a speaker who gave neither: nothing is bound.
        self.assertEqual(qp.bind_said_done(prose, "I wait.", npcs=ctx["npcs"], existing=ctx["existing"]), [])

    def test_done_not_yet_said_binds_nothing(self):
        _salvage_world(self.conn)
        ctx = qp.load_quest_context(self.conn, 86)
        prose = 'Eadric [[F]] taps the ledger. "Once the job\'s done, come back and I\'ll pay."'
        self.assertEqual(qp.bind_said_done(prose, "I ask about the job.", npcs=ctx["npcs"], existing=ctx["existing"]), [])
        prose = 'Eadric [[F]] shakes his head. "Is the job done?"'
        self.assertEqual(qp.bind_said_done(prose, "I ask about the job.", npcs=ctx["npcs"], existing=ctx["existing"]), [])

    def test_the_players_own_words_are_not_the_giver_saying_it(self):
        _q1, q2 = _salvage_world(self.conn)
        quests.complete_quest_step(self.conn, _q1, turn=85, to_end=True, source="test")
        prose = 'You lean on the counter. "The job\'s done," you say. Eadric [[F]] does not look up.'
        report = qp.apply_quest_changes(self.conn, {}, narration=prose, player_input='"The job\'s done," I say.', turn=86)
        self.assertEqual(_status(self.conn, q2), "active", report)


class AWalkElsewhereFinishesNoTrip(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_t79_the_travel_sentence_completes_nothing(self):
        q1, q2 = _salvage_world(self.conn)
        gold = _gold(self.conn)
        # turns/079.json: the progress check said yes on this sentence and Q2 was paid +15.
        changes = {"new": [], "updates": [{"quest": f"Q{q2}", "action": "step_done", "evidence": T79_EVIDENCE}],
                   "source": "checked"}
        report = qp.apply_quest_changes(self.conn, changes, narration=T79, player_input=T79_LINE, turn=81,
                                        moved_to="to Saltmarrow")
        self.assertEqual(_status(self.conn, q2), "active", report)
        self.assertEqual(_gold(self.conn), gold)
        self.assertIn("travel_not_to_the_job", report["rejected"][0]["reasons"])
        # Nobody in T79 says a job is done.
        ctx = qp.load_quest_context(self.conn, 81)
        self.assertEqual(qp.bind_said_done(T79, T79_LINE, npcs=ctx["npcs"], existing=ctx["existing"]), [])

    def test_arriving_where_the_trip_goes_still_finishes_it(self):
        _q1, q2 = _salvage_world(self.conn)
        prose = "You set the sack down in the Guild Yard [[L10]] and the guild's clerk takes it in. The salvage is delivered."
        changes = {"new": [], "updates": [{"quest": f"Q{q2}", "action": "step_done", "evidence": "The salvage is delivered."}],
                   "source": "checked"}
        report = qp.apply_quest_changes(self.conn, changes, narration=prose, player_input="I carry the sack to #L10.",
                                        turn=81, moved_to="The Guild Yard")
        self.assertEqual(_status(self.conn, q2), "completed", report)


if __name__ == "__main__":
    unittest.main()
