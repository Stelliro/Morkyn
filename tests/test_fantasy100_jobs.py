"""F195 cont. 2: jobs filed from chatter and paid off chores, accepted jobs unbound (fantasy100, 2026-10-26).

The Hermes 3 8B run "fantasy100" (Thornhallow, four Sonnet players) filed jobs
from remarks with no offer in them ("There's always need for helping hands"
T5, "Fine job ... Think about staying on" T8, a stranger's "I seek knowledge
hidden here" T29, "plenty of firewood to cut if you're up for it" told into a
sleep T70); the keyword judge said no offer twice and the model check's yes
kept the card anyway (`checked_offer_kept no_offer_in_exchange`). T5's job was
then taken by T7's acceptance and finished and paid its filed 15 gold by T8's
sweep, with no pay in the prose. Deeds that were not work on the job became
its steps (T55 the candle-dipping Ermengarde only offered, T62 reading a coin),
so Q1's step ran 2 -> 4. At T90 the player took "the skilled labor for eight
gold" and Edith agreed, but the eight found no job (Q1 is a notice slip with no
giver on record), so T94 paid Q1's filed 15 where eight was agreed.

Now: a checked card the keyword judge finds no offer in stands only on the
engine's own sign of one (the line names pay, or the player asked for or took
on work); a place alone names no task; praise of work done is no job language;
a wait or sleep files, finishes and pays nothing; words that name every job
find no progress and one word counts once; terms the player's line agrees for
a job it names become that job's pay; an acceptance no job on record can be
reads the giver's answer as the offer.

Run:  cd tests; ../.venv/bin/python -m unittest test_fantasy100_jobs
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-fantasy100-jobs-"))
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

# --- The recorded turns (fantasy100 turns/NNN.json, player_line and narration) ---
T5_LINE = "I tell the barman I am Wren, Hesper's apprentice, and ask if he knows of any paid work, and what the notice for skilled labor pays."
T5 = (
    '"I\'m Wren Ashcombe," you say, "apprentice to Hesper the hedge-mage. I was wondering if there\'s any p'
    'aid labor going around Thornhallow I could take on."\n\nArnulf sets down his rag and considers you for'
    ' a moment. "Well now, an apprentice mage looking to earn some coin, are ye? There\'s always need for '
    'helping hands in a town like this," he says. "Saw a notice posted round here for skilled labor - did'
    ' you have your eye on that?"'
)
T7_LINE = 'I accept the work. I ask Arnulf what I actually have to do today and whether any of the pay comes in advance.'
T7 = (
    'A man behind the bar looks up from polishing a mug.\n\n"Very well," you say with a nod.\n\nArnulf gestur'
    'es around the taproom with an open hand.\n\n"All manner of things! Cleaning, serving drinks, tending t'
    'o patrons - whatever needs done. The pay is fair for hard workers."\n\n"And when do we get paid?"\n\n"Wh'
    'en the day\'s accounts are settled," Arnulf says. "That\'s usually after last light. But you\'ll be ear'
    'ning your keep before then!"\n\nYou give him a smile and nod in agreement.\n\n"Sounds good. I\'ll start r'
    'ight away, then."\n\nArnulf nods back and gives you a wave towards a broom propped against the wall.\n\n'
    '"Aye, sweep the floors first," he says. "Then see to the tables as they\'re emptied. The regulars can'
    ' be a messy bunch!"\n\nHe chuckles heartily at his own joke before turning to serve a customer who jus'
    't called out for another round of ale.'
)
T8_LINE = 'I take the broom and sweep the taproom floor, working around the tables.'
T8 = (
    'You take the broom and set to sweeping the taproom floor, working around the tables. The room soon g'
    'leams as you clear away the dust and grime with swift strokes. Two curious patrons glance over at yo'
    'ur efforts before returning to their drinks. Sunlight streams through the tall windows on the east s'
    'ide of the inn, casting a warm glow across the wooden floorboards. The distant sound of horses clopp'
    'ing along the road outside mingles with the low murmur of conversations inside.\n\nAs you finish up, t'
    'he kitchen hand Roger [[A]] approaches, wiping his hands on his apron.\n"Fine job," he says approving'
    'ly. "You\'ve a knack for this floor-cleaning. Think about staying on. The Shears and Wheel could use '
    'regular help like this."'
)
T29_LINE = "I tell the hooded figure I am Wren, Hesper's apprentice, and I mean no harm; I ask what they are doing in the ruins."
T29 = (
    'You approach the hooded figure, who turns to face you as you speak. "I am Wren," you say, "Hesper\'s '
    'apprentice, and I mean no harm. What brings you to these ruins?"\n\nThe hooded figure lowers their cow'
    'l, revealing a woman with sharp features. "I seek knowledge hidden here, knowledge others have forgo'
    'tten or were not worthy to remember." She eyes your outfit and the staff at your side. "And what of '
    'you? An apprentice wandering alone in the wilds - are you running from something?"'
)
T55_LINE = 'I count five silver onto the counter in front of Ermengarde and say that is a payment toward the debt.'
T55 = (
    'You step forward and place five silver coins on the counter in front of Ermengarde [[Q]]. "That is a'
    ' payment toward the debt," you say, your voice steady.\n\nErmengarde [[Q]] eyes the silver, then looks'
    ' up at you with a slight frown. "Five silvers... That will cover half of what you owe me from last q'
    'uarter." She hesitates for a moment, then nods. "Very well. I\'ll mark it down."\n\nShe reaches beneath'
    ' the counter and brings out your old guild ledger, flipping through the pages until she finds your n'
    "ame. With a quill, she marks an X next to it and writes '5 silvers' below.\n\nThe Chandler sniffs at t"
    'hat. "I\'m sure your studies have taught you more than just how to dodge payments, Master Ash." She c'
    'loses the ledger and sets it aside.\n\nYou let her jab keep going without responding. A little quiet g'
    'oes a ways in this business.\n\nErmengarde [[Q]] waits a moment for you to say something else, but whe'
    'n you don\'t she sighs. "Well then. If there\'s nothing more... I have work." She turns from the count'
    'er and picks up a bundle of candles from a shelf, starting to sort through them.\n\nThe door is right '
    'there by the entrance - no need to walk back through the hall.\n\nAs you reach for it, Ermengarde [[Q]'
    '] calls out one last thing:\n\n"If you\'re looking for more work... I could always use an extra hand wi'
    "th the candle-dipping. It's not easy work, but it pays. Five silvers a day and room to sleep in the "
    'loft." She glances up at you with an appraising look.\n\nYou pause, considering. The silver is good, b'
    "ut sleeping here means no place to call your own and more of Ermengarde [[Q]]'s sharp tongue. Still."
    '..\n\n"Five silvers a day," you repeat, mulling it over.'
)
T62_LINE = 'I use my Old Script skill to try to read the inscription on the coin, then pick the coin up.'
T62 = (
    "You stand on the weathered stones of King's Road, the full moon casting eerie shadows across the anc"
    'ient path. The air is cool and still, carrying an almost tangible sense of history. The inscription '
    'on the coin gleams faintly in the lunar light - "For valor in the King\'s Road quake, 27 years past."'
    ' It seems to whisper tales of bravery from a time long gone.\n\nWith practiced hands, you reach into y'
    'our pouch and retrieve the old coin, its surface worn smooth under your fingertips. The words etched'
    ' upon it tell a story of valor during a tumultuous era when this very road shook beneath the feet of'
    ' its travelers. You tuck the coin away, feeling a sense of connection to those who came before, thei'
    "r deeds now a part of your own journey.\n\nContinuing along King's Road [[L9]], you tread lightly on t"
    'he old stones, your footsteps echoing in the night silence. The path ahead seems to stretch endlessl'
    'y into the darkness, inviting further exploration and discovery.'
)
T70_LINE = '!wait 240 sleep'
T70 = (
    'You wake to the sound of chopping. Gisela [[N]] is still at work, her axe ringing against wood as sh'
    "e splits logs. You stretch and yawn, feeling refreshed after a night's sleep. The ruins around you a"
    're quiet but for the occasional snap of breaking branches underfoot.\n\nGisela [[N]] notices your stir'
    'ring and waves over. "Sleep well? We\'ve got plenty of firewood to cut if you\'re up for it," she says'
    ' with a smile.\n\nGisela [[N]] hands you an axe, the blade gleaming in the morning sun filtering throu'
    'gh the ruins.\n\nGisela [[N]] chats away as you work, telling stories of her travels and the people sh'
    "e's met along the way. She's clearly a talkative soul with plenty of tales to share. You listen with"
    ' half an ear while you chop, focusing on keeping a steady rhythm to your swings.\n\nThe morning passes'
    ' in this way - you and Gisela [[N]] cutting firewood side by side, the sound of axes ringing out acr'
    'oss the ruins. The sun climbs higher in the sky and the temperature warms. You pause for a drink fro'
    'm your waterskin before resuming your work.\n\nGisela [[N]] suddenly stops chopping and looks at you i'
    'ntently. "I have an important question to ask you," she says seriously. "What\'s your name, mage\'s ap'
    'prentice?"'
)
T90_LINE = 'I tell Edith I accept the skilled labor for eight gold, and ask what I must do first.'
T90 = (
    '"I\'ll take that job for eight gold pieces," you say, your voice steady.\n\nEdith [[Y]] looks at you sh'
    'arply from beneath her brow. "Ah, so the rumors were true. You\'re seeking work after all." She pulls'
    ' out a slip of paper from beneath the counter and hands it over. "Very well then. First thing to do '
    'is clean out the stables."\n\nEdith [[Y]] gestures towards the back door with a tilt of her head. "The'
    ' stables are this way. The place could use a good cleaning after last night\'s revels." She hands you'
    ' a broom and a bucket.'
)
T94_LINE = 'I sit down across from Edith and say plainly: the stables are done, please pay me the eight gold we agreed.'
T94 = (
    'You sit down across from Edith [[Y]], who has been watching you with a skeptical expression. She rai'
    'ses an eyebrow as you say plainly "The stables are done; please pay me the eight gold we agreed." He'
    'r gaze flicks towards the stalls and back to you before she sighs.\n\n"You\'ve certainly kept yourself '
    'busy," she says, folding her arms across her chest. "I suppose I can\'t argue with a job well done. E'
    'ight gold it is then." She reaches into a pouch at her belt and pulls out a handful of coins, laying'
    ' them on the table between you with a clink.\n\n"Here you go then," she says as you reach for the pile'
    '. "Make sure to pay your taxes when you get a chance."'
)
# What the engine sent the quest parser on the T70 sleep (trace model_input, first line).
T70_INPUT = "__wait_request__: kind=sleep minutes=240\nworld_time_before: custom · Day 2 · 02:31"

# The fills and checks the 8B answered (traces, phases quest_fill / quest_check).
T5_FILL = {"task": "helping hands", "title": "helping hands", "place": "in a town like this", "pay": "not mentioned", "gold": 0}
T8_FILL = {"task": "clean the floor", "title": "Floor-cleaning", "place": "The Shears and Wheel", "pay": "regular help", "gold": 0}
T29_FILL = {"task": "I seek knowledge hidden here, knowledge others have forgotten or were not worthy to remember.",
            "title": "Seek Hidden Knowledge", "place": "the ruins", "pay": "no pay promised", "gold": 0}
T70_FILL = {"task": "cut firewood", "title": "cut firewood", "place": "Outside Thornhallow", "pay": "empty", "gold": 0}
YES = {"offered": "yes", "in_text": "yes", "why": "the giver offers the task"}

ARNULF = {"code": "B", "name": "Arnulf Bramley", "role": "barkeep"}
ROGER = {"code": "A", "name": "Roger", "role": "kitchen hand"}
GISELA = {"code": "N", "name": "Gisela", "role": "woodcutter"}
ERMENGARDE = {"code": "Q", "name": "Ermengarde", "role": "chandler"}
EDITH = {"code": "Y", "name": "Edith", "role": "wine seller"}
# Q1 as the run filed it at T1 from the notice board: no giver, the notice as its step, 15 gold by default.
Q1_STEP = "Seeking skilled labor! Good pay for honest work."


def _ask(fill: dict, check: dict | None = None, progress: dict | None = None, deed: dict | None = None):
    calls: list[str] = []

    def ask(system, user, *, max_tokens, phase):
        calls.append(phase)
        if phase == qo.FILL_PHASE:
            return dict(fill)
        if phase == qo.CHECK_PHASE:
            return dict(check if check is not None else YES)
        if phase == qo.DEED_PHASE:
            return dict(deed or {"work": "none"})
        return dict(progress or {"finished": "no", "why": "not yet"})

    return ask, calls


def _fresh():
    from app.db import connect, init_db

    init_db()
    conn = connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ("quest_steps", "quests", "journal", "npcs"):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("UPDATE player SET gold = 41, purse_units = 410000, xp = 0 WHERE id = 1")
    return conn


def _npc(conn, row: dict) -> int:
    conn.execute("INSERT INTO npcs (code, location_id, name, role) VALUES (?, 1, ?, ?)", (row["code"], row["name"], row["role"]))
    return int(conn.execute("SELECT id FROM npcs WHERE code = ?", (row["code"],)).fetchone()["id"])


def _gold(conn) -> int:
    return int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"])


def _titles(conn) -> list[str]:
    return [str(r["title"]) for r in conn.execute("SELECT title FROM quests ORDER BY id").fetchall()]


def _file_q1(conn, *, status: str = "active") -> int:
    qid = quests.create_quest(conn, title="skilled labor", description=Q1_STEP, steps=[{"title": Q1_STEP}],
                              reward_gold=15, reward_xp=25, notes=quests.STEPS_FROM_PLAY_NOTE)
    if status == "active":
        quests.accept_offered(conn, qid, turn=8)
    return qid


def _q1_row(conn, qid: int) -> dict:
    quest = quests.get_quest(conn, qid)
    return {"id": qid, "code": quest.get("code") or f"Q{qid}", "title": quest["title"], "status": quest["status"],
            "current_objective": Q1_STEP}


class ARemarkIsNoJob(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def _offer_and_apply(self, narration, line, fill, npcs, *, marks=None, asked=False):
        for row in npcs:
            _npc(self.conn, row)
        ask, calls = _ask(fill)
        offers = qo.run_offer_pass(narration, line, npcs=npcs, marks=marks, asked_for_work=asked, ask=ask)
        report = qp.apply_quest_changes(
            self.conn, {"new": offers["new"], "updates": [], "source": "checked"}, narration=narration,
            player_input=line, turn=9,
        )
        return offers, report, calls

    def test_t5_a_place_alone_names_no_task(self):
        # The fill put "in a town like this" in its place field; the task "helping hands" names nothing the line says.
        offers, _report, calls = self._offer_and_apply(T5, T5_LINE, T5_FILL, [ARNULF], asked=True)
        self.assertEqual(offers["new"], [])
        self.assertEqual(offers["fills"][0].get("dropped"), "no_thing_named")
        self.assertNotIn(qo.CHECK_PHASE, calls)
        self.assertEqual(_titles(self.conn), [])

    def test_t8_praise_and_an_invitation_to_stay_on_file_nothing(self):
        # Recorded: Q3 "Floor-cleaning" filed from Roger's "Fine job ... could use regular help like this".
        # "Fine job" was its only job word: with praise read as praise the line is no candidate, and no model is asked.
        offers, _report, calls = self._offer_and_apply(T8, T8_LINE, T8_FILL, [ROGER, ARNULF])
        self.assertEqual(offers["candidates"], [])
        self.assertEqual(calls, [])
        self.assertEqual(_titles(self.conn), [])
        # Had the 8B's card come through anyway (a mark, another path), the keyword judge refuses it.
        card = qo.card_to_proposal({"line": T8.split("\n")[-1], "quote": T8.split("\n")[-1], "speaker": ROGER,
                                    "kind": "spoken", "why": "job_words"}, {**T8_FILL, "steps": ["clean the floor"]}, YES)
        report = qp.apply_quest_changes(self.conn, {"new": [card], "updates": [], "source": "checked"}, narration=T8,
                                        player_input=T8_LINE, turn=9)
        self.assertEqual(_titles(self.conn), [], report)
        self.assertIn("evidence_is_not_an_offer", report["rejected"][0]["reasons"])
        # Praise of work done is no job language, a real offer after it still is.
        self.assertNotRegex(qp._offer_text('"Fine job," he says.'), r"(?i)\bjob\b")
        self.assertTrue(qp._JOB_RE.search(qp._offer_text("Good work for you at the docks, if you want it.")))

    def test_t29_a_strangers_own_pursuit_files_nothing(self):
        # Recorded: Q4 "Seek Hidden Knowledge" kept on checked_offer_kept, keyword_verdict no_offer_in_exchange.
        offers, report, _calls = self._offer_and_apply(T29, T29_LINE, T29_FILL, [])
        self.assertEqual(len(offers["new"]), 1)
        self.assertEqual(_titles(self.conn), [], report)

    def test_t70_firewood_if_youre_up_for_it_files_nothing_even_off_a_wait(self):
        # The card came from the narrator's mark on Gisela; no pay, no work asked for.
        mark = [{"op": "QUEST", "title": "cut firewood", "giver": "N"}]
        offers, report, _calls = self._offer_and_apply(T70, T70_LINE, T70_FILL, [GISELA], marks=mark)
        self.assertEqual(len(offers["new"]), 1)
        self.assertEqual(_titles(self.conn), [], report)


class AWaitFilesNothing(unittest.TestCase):
    def test_t70_the_sleep_asks_no_quest_model_at_all(self):
        from unittest import mock

        from app import llm

        def boom(*_a, **_k):
            raise AssertionError("no quest ask on a wait turn")

        turn = {"narration": T70, "quest_marks": [{"op": "QUEST", "title": "cut firewood", "giver": "N"}]}
        context = {"current_location": {"code": "L8", "name": "Ruins", "npcs": [GISELA]}}
        trace: list[dict] = []
        with mock.patch.object(llm, "_chat_json", side_effect=boom):
            out = llm._run_quest_parser(turn, context, T70_INPUT, trace=trace)
        self.assertNotIn("quest_changes", out)
        record = [t for t in trace if t.get("phase") == qp.PARSER_PHASE][-1]
        self.assertTrue(record.get("wait_turn"))
        self.assertFalse(record.get("gate"))

    def test_t70_an_offer_proposed_on_a_wait_is_not_filed_by_the_engine(self):
        from app import world

        conn = _fresh()
        _npc(conn, GISELA)
        conn.commit()
        conn.close()
        card = qo.card_to_proposal({"line": "We've got plenty of firewood to cut if you're up for it",
                                    "quote": "Sleep well? We've got plenty of firewood to cut if you're up for it,",
                                    "speaker": GISELA, "kind": "mark", "why": "narrator_mark"},
                                   {**T70_FILL, "steps": ["cut firewood"]}, YES)
        card["_checked"]["asked"] = True  # even a card the engine would keep on a player turn
        result = {
            "narration": T70, "narration_segments": [{"label": "scene", "text": T70}], "player": {},
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []}, "turn_summary": "a sleep",
            "quest_changes": {"new": [card], "updates": [], "source": "checked"},
        }
        world.apply_turn(result, T70_INPUT, input_kind="wait")
        from app.db import connect

        with connect().closing() as conn:
            self.assertEqual(_titles(conn), [])

    def test_a_player_turn_with_the_same_scene_still_reads_it(self):
        from unittest import mock

        from app import llm

        asked: list[str] = []

        def fake(system, user, *, phase, **_k):
            asked.append(phase)
            return dict(T70_FILL) if phase == qo.FILL_PHASE else dict(YES)

        turn = {"narration": T70, "quest_marks": [{"op": "QUEST", "title": "cut firewood", "giver": "N"}]}
        context = {"current_location": {"code": "L8", "name": "Ruins", "npcs": [GISELA]}}
        with mock.patch.object(llm, "_chat_json", side_effect=fake):
            llm._run_quest_parser(turn, context, "I stretch and look around.", trace=[])
        self.assertIn(qo.FILL_PHASE, asked)


class WorkOnAJobIsWorkOnThatJob(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_t55_words_every_job_has_find_no_progress(self):
        # Recorded: "It's not easy work, but it pays." was a candidate on Q1 and the offered candle-dipping its step.
        qid = _file_q1(self.conn)
        self.assertEqual(qo.find_progress_candidates(T55, T55_LINE, active=[_q1_row(self.conn, qid)]), [])

    def test_t62_one_word_counts_once(self):
        # Recorded: "skill" in "my Old Script skill" matched the title's "skilled" and the step's "skill" as two.
        qid = _file_q1(self.conn)
        self.assertEqual(qo.find_progress_candidates(T62, T62_LINE, active=[_q1_row(self.conn, qid)]), [])

    def test_t94_the_giver_saying_job_well_done_is_still_a_candidate(self):
        qid = _file_q1(self.conn)
        found = qo.find_progress_candidates(T94, T94_LINE, active=[_q1_row(self.conn, qid)])
        self.assertEqual([c["title"] for c in found], ["skilled labor"])


class TheAgreedPayIsWhatIsPaid(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_t90_terms_bind_to_the_job_the_line_names_and_t94_pays_them(self):
        _npc(self.conn, EDITH)
        qid = _file_q1(self.conn)
        # T90: "I accept the skilled labor for eight gold" and Edith's "Very well then."
        change = qp.settle_agreed_price(self.conn, narration=T90, player_input=T90_LINE, turn=91)
        self.assertEqual(change and change["to"], 8)
        self.assertEqual(int(quests.get_quest(self.conn, qid)["reward_gold"]), 8)
        # The T90 acceptance is that job's; it reads nothing new.
        jobs = [{"code": f"Q{qid}", "title": "skilled labor", "status": "active"}]
        self.assertFalse(qo.accepts_unrecorded_work(T90_LINE, jobs))
        # T94: the recorded progress check said finished; the payout is the eight agreed, not the filed 15.
        gold = _gold(self.conn)
        ask, _calls = _ask({}, progress={"finished": "yes", "why": "the stables are done"})
        progress = qo.run_progress_pass(T94, T94_LINE, active=[_q1_row(self.conn, qid)], ask=ask)
        self.assertEqual([u["quest"] for u in progress["updates"]], [f"Q{qid}"])
        report = qp.apply_quest_changes(self.conn, {"new": [], "updates": progress["updates"], "source": "checked"},
                                        narration=T94, player_input=T94_LINE, turn=95)
        self.assertEqual(quests.get_quest(self.conn, qid)["status"], "completed", report)
        self.assertEqual(_gold(self.conn), gold + 8)

    def test_terms_with_two_jobs_the_line_names_neither_bind_nowhere(self):
        _npc(self.conn, EDITH)
        _file_q1(self.conn)
        quests.create_quest(self.conn, title="skilled carting", steps=[{"title": "cart the barrels"}], reward_gold=15)
        self.assertIsNone(qp.settle_agreed_price(self.conn, narration=T90, player_input=T90_LINE, turn=91))


class AnAcceptedJobGetsItsRow(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_t7_the_acceptance_takes_the_one_open_offer(self):
        # With no "helping hands" filed at T5, T7's "I accept the work" is Q1's, the job Arnulf said pays 15.
        qid = _file_q1(self.conn, status="offered")
        offers = [{"id": qid, "code": f"Q{qid}", "title": "skilled labor", "status": "offered"}]
        self.assertEqual([u["quest"] for u in qo.typed_accepts(T7_LINE, offers)], [f"Q{qid}"])
        self.assertFalse(qo.accepts_unrecorded_work(T7_LINE, offers))

    def test_t90_with_nothing_on_record_the_givers_answer_is_filed_with_the_pay_said(self):
        # The same acceptance when no job is on record: Edith's answer is read as the offer,
        # the card stands on the player's acceptance, and the eight gold is the job's pay.
        _npc(self.conn, EDITH)
        self.assertTrue(qo.accepts_unrecorded_work(T90_LINE, []))
        fill = {"task": "clean out the stables", "title": "Clean out the stables", "place": "", "pay": "eight gold pieces",
                "gold": 8}
        ask, _calls = _ask(fill)
        offers = qo.run_offer_pass(T90, T90_LINE, npcs=[EDITH], took_on_work=True, ask=ask)
        # Without the acceptance the same answer is no candidate (what the run did: no_candidates).
        self.assertEqual(qo.run_offer_pass(T90, T90_LINE, npcs=[EDITH], ask=ask)["candidates"], [])
        self.assertEqual([p["title"] for p in offers["new"]], ["Clean out the stables"])
        report = qp.apply_quest_changes(self.conn, {"new": offers["new"], "updates": [], "source": "checked"},
                                        narration=T90, player_input=T90_LINE, turn=91)
        self.assertEqual(_titles(self.conn), ["Clean out the stables"], report)
        touched = {str(r.get("code") or "") for r in report.get("created") or []}
        qp.settle_agreed_price(self.conn, narration=T90, player_input=T90_LINE, turn=91, touched_codes=touched)
        row = self.conn.execute("SELECT reward_gold, giver_npc_id FROM quests").fetchone()
        self.assertEqual(int(row["reward_gold"]), 8)
        self.assertTrue(row["giver_npc_id"])


class ARealOfferStillFiles(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh()
        self.addCleanup(self.conn.close)

    def test_t55_candle_dipping_with_its_pay_files(self):
        # Ermengarde's "I could always use an extra hand with the candle-dipping ... Five silvers a day" is an offer.
        _npc(self.conn, ERMENGARDE)
        fill = {"task": "the candle-dipping", "title": "Candle-dipping", "place": "", "pay": "Five silvers a day", "gold": 0}
        ask, _calls = _ask(fill)
        offers = qo.run_offer_pass(T55, T55_LINE, npcs=[ERMENGARDE], ask=ask)
        report = qp.apply_quest_changes(self.conn, {"new": offers["new"], "updates": [], "source": "checked"},
                                        narration=T55, player_input=T55_LINE, turn=56)
        self.assertEqual(_titles(self.conn), ["Candle-dipping"], report)


if __name__ == "__main__":
    unittest.main()
