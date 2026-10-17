"""Quest offers, engine first (app/quest_offers.py): find the line, fill the card, check it.

The one-shot quest parser proposed a job in 355 of its 360 calls over the 8B
runs and a rule was added after it almost every run. The engine now finds the
spoken lines that could offer work, one small ask fills a card from that line
alone, a second small ask checks it against the passage, and the engine still
decides giver, duplicates, rewards and the player's acceptance. Every passage
below is from an archived 8B run (D:/STELLIROS_WORKSHOP/Morkyn-playtest-archive).

Run:  .venv\\Scripts\\python -m unittest tests.test_quest_offers
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-quest-offers-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    for key, value in _ENV.items():
        _SAVED_ENV[key] = os.environ.get(key)
        os.environ[key] = value
    os.environ.pop("AI_RPG_QUEST_PARSER", None)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


from app import quest_offers as qo, quest_parser as qp  # noqa: E402

VEYRA = [{"code": "A", "name": "Veyra", "role": "tallyman"}, {"code": "B", "name": "Hal", "role": "guard"}]
# 8B run 116, T3: the one real offer in the turn.
FISH = (
    "You step up to the desk, your voice a quiet challenge. \"I owe the guild a winter's credit and I want to "
    "work it off,\" you say. Veyra [[A]], the tallyman, lifts his gaze from the ledger. \"You're not the first "
    "to ask,\" he says, his tone dry. \"But the guild has its own way of settling debts.\" She flips a page. "
    "\"There's a job at the docks. A shipment of salted fish needs unloading. It's rough work, but it pays well.\" "
    "\"What job have you got that pays against the ledger?\" you ask, your voice steady."
)
FISH_INPUT = "\"I owe the guild a winter's credit and I want to work it off.\" I stop in front of the desk. \"What job have you got that pays against the ledger?\""
# 8B run 113, T2: debt talk, no task; the old parser filed "Work Against My Debt".
DEBT_TALK = (
    "\"You're late,\" he mutters, not bothering to glance at you. \"The tide's already turned.\"\n\n"
    "You step closer. \"I was hoping to find work against my debt,\" you say.\n\n"
    "The tallyman finally looks up. \"Debt? You owe the guild more than you're worth. You'll have to do "
    "something useful before I consider paying you back.\""
)
# 8B run 120, T3: a question back about what work is wanted; filed "Prove worth through work".
ASKS_BACK = (
    "You stand before Eldric Grimsby [[C]]'s desk. \"A winter's credit,\" he says. \"You're not the first to come "
    "asking for work. But the guild has its own way of settling debts.\" He leans back. \"You'll need to prove "
    "your worth. What kind of job are you looking for?\""
)
ELDRIC = [{"code": "C", "name": "Eldric Grimsby", "role": "tallyman"}]
# 8B run 106, T8: the player paying for a boat; filed "Row with Emmot Bexley" as Emmot's job.
BOAT = (
    "You step closer to Emmot Bexley [[B]], the ropes in his hands still damp. \"You're asking the right "
    "question,\" he says. \"This boat's mine, and I've been out past Blackreach a few times. But the price isn't "
    "just in coin. You're not just paying for the row\u2014you're paying for the risk.\""
)
EMMOT = [{"code": "B", "name": "Emmot Bexley", "role": "lighterman"}]
# 8B run 111, T5: directions to a person, not work.
POINTER = "Davy [[A]] shrugs. \"She's not here,\" he says. \"But if you're after her, you'll find her where the wreckage still floats.\""
DAVY = [{"code": "A", "name": "Davy", "role": "dock hand"}]
# 8B run 103, T4: one speaker's lines in one paragraph are one offer.
GARRICK = [{"code": "A", "name": "Garrick Thorne", "role": "Tallyman"}]
SHEDS = (
    "\u201cI am up for it,\u201d you say. Garrick Thorne [[A]]\u2019s fingers drum a slow rhythm on the counter. "
    "\u201cA job,\u201d he says, his voice gravelly. \u201cYou\u2019ll be fetching salvage from the docks. The storm\u2019s "
    "left a mess\u2014ships grounded, cargo spilled. You\u2019ll be paid in coin, but the real reward is the ledger.\u201d"
)
# 8B run 44, T1: a QUEST mark with no spoken offer behind it made "Salvage Contract".
LATE = "Tilda [[A]] looks up from the ledger. \u201cYou\u2019re late, Flat-runner,\u201d she says. \u201cThe tide\u2019s already turned.\u201d"
TILDA = [{"code": "A", "name": "Tilda", "role": "tallyman"}]


def _fake_ask(fill: dict | None = None, check: dict | None = None, progress: dict | None = None):
    """An ask() that answers each phase from a canned dict and records the calls."""
    calls: list[dict] = []
    fill = fill if fill is not None else {
        "offers_work": True, "task": "A shipment of salted fish needs unloading", "title": "Unload the salted fish",
        "steps": ["Go to the docks", "Unload the shipment"], "place": "the docks", "pay": "it pays well", "gold": 0,
    }
    check = check if check is not None else {"offered": "yes", "specific": "yes", "in_text": "yes", "why": "Veyra names the job."}
    progress = progress if progress is not None else {"finished": "yes", "why": "the last crate is stacked"}

    def ask(system, user, *, max_tokens, phase):
        calls.append({"phase": phase, "max_tokens": max_tokens, "user": json.loads(user)})
        if phase == qo.FILL_PHASE:
            return dict(fill)
        if phase == qo.CHECK_PHASE:
            return dict(check)
        return dict(progress)

    return ask, calls


class TheEngineFindsTheLine(unittest.TestCase):
    def test_the_givers_spoken_offer_is_the_one_candidate(self):
        cands, dropped = qo.find_offer_candidates(FISH, FISH_INPUT, npcs=VEYRA, asked_for_work=True)
        self.assertEqual(len(cands), 1, (cands, dropped))
        self.assertEqual(cands[0]["speaker"]["name"], "Veyra")
        self.assertIn("salted fish needs unloading", cands[0]["line"])
        # The player's own question about jobs is not a candidate.
        self.assertFalse(any("What job have you got" in c["line"] for c in cands))

    def test_debt_talk_reaches_the_fill_and_a_no_there_ends_it(self):
        # "paying you back" is job vocabulary, so the line is a candidate; the
        # fill ask, not a phrase list, says it offers no work.
        ask, calls = _fake_ask(fill={"offers_work": False, "task": "", "title": ""})
        report = qo.run_offer_pass(DEBT_TALK, "I was hoping to find work against my debt", npcs=[], asked_for_work=True, ask=ask)
        self.assertEqual([c["phase"] for c in calls], [qo.FILL_PHASE])
        self.assertEqual(report["new"], [])
        # And the player's own line is never a candidate.
        self.assertFalse(any("hoping to find work" in c["line"] for c in report["candidates"]))

    def test_a_question_back_about_what_work_is_dropped_in_code(self):
        cands, dropped = qo.find_offer_candidates(ASKS_BACK, FISH_INPUT, npcs=ELDRIC, asked_for_work=True)
        self.assertEqual(cands, [], cands)
        self.assertIn("asks_what_work", [d["why"] for d in dropped])

    def test_the_player_paying_for_a_service_is_dropped_in_code(self):
        cands, dropped = qo.find_offer_candidates(BOAT, "What would you want for taking me out there and back?", npcs=EMMOT)
        self.assertEqual(cands, [])
        self.assertIn("player_pays", [d["why"] for d in dropped])

    def test_directions_to_a_person_are_dropped_in_code(self):
        cands, dropped = qo.find_offer_candidates(POINTER, "Where is Ellen?", npcs=DAVY)
        self.assertEqual(cands, [])
        self.assertIn("pointer_to_someone", [d["why"] for d in dropped])

    def test_a_list_to_choose_from_is_no_task_yet(self):
        # 8B run 143, T2: filed "Choose a Task" with the steps "Choose dockside salvage", ...
        prose = ("Alys [[A]], the guard, looks up from her ledger. \"The guild has a list of tasks,\" her finger tapping the "
                 "paper. \"You’ll need to choose one that fits your skills.\" She lists the options—dockside salvage, "
                 "warehouse inventory, or harbor watch—each with its own risk and reward.")
        alys = [{"code": "A", "name": "Alys", "role": "guard"}]
        cands, dropped = qo.find_offer_candidates(prose, FISH_INPUT, npcs=alys, asked_for_work=True)
        self.assertEqual(cands, [], cands)
        self.assertIn("asks_to_choose", [d["why"] for d in dropped])
        # And a card of choosing steps is refused by the engine either way.
        item = {"title": "Choose a Task", "summary": "You'll need to choose one that fits your skills.", "giver": "A",
                "steps": [{"title": "Choose dockside salvage"}, {"title": "Choose warehouse inventory"}],
                "reward": {}, "offer_line": "You’ll need to choose one that fits your skills.",
                "evidence": "You’ll need to choose one that fits your skills.", "_checked": {"why": "yes"}}
        _accepted, rejected = qp.validate_quest_changes({"new": [item]}, narration=prose, player_input=FISH_INPUT, npcs=[{"id": 1, **alys[0]}])
        self.assertIn("no_task_named_yet", rejected[0]["reasons"])

    def test_the_player_needing_help_is_no_offer(self):
        # 8B run 145, T11: filed "Carry the Crate Upstairs" from a crewman's remark.
        prose = ("The crew ties off the rowing craft, and one of them, a man with a scar, nods at you. \"You’re late,\" "
                 "he says. You lift the crate. \"That’s a lot to carry,\" he mutters. \"You’ll need help getting it up the steps.\"")
        cands, _dropped = qo.find_offer_candidates(prose, "I carry the chest up to the tally house.", npcs=[])
        self.assertEqual(cands, [], cands)

    def test_arranging_the_work_is_not_the_work(self):
        # 8B run 145, T36: "The guild holds the salvage rights, but only if you're willing to work for it"
        # filed "Salvage Rights Claim" with the steps Confirm / Discuss / Agree.
        prose = ("Captain Veyra [[B]] looks up. \"The guild holds the salvage rights, but only if you're willing to work for it.\"")
        item = {"title": "Salvage Rights Claim", "summary": "x", "giver": "B",
                "steps": [{"title": "Confirm salvage rights"}, {"title": "Discuss salvage work"}, {"title": "Agree to work terms"}],
                "reward": {}, "offer_line": "The guild holds the salvage rights, but only if you're willing to work for it.",
                "evidence": "The guild holds the salvage rights, but only if you're willing to work for it.", "_checked": {"why": "yes"}}
        _accepted, rejected = qp.validate_quest_changes({"new": [item]}, narration=prose, player_input="Is she here or not?",
                                                        npcs=[{"id": 2, "code": "B", "name": "Veyra", "role": "captain"}])
        self.assertIn("no_task_named_yet", rejected[0]["reasons"])

    def test_one_speakers_lines_in_one_paragraph_are_one_offer(self):
        cands, _ = qo.find_offer_candidates(SHEDS, "\"I am up for it.\"", npcs=GARRICK)
        self.assertEqual(len(cands), 1, cands)
        self.assertIn("A job,", cands[0]["line"])
        self.assertIn("fetching salvage", cands[0]["line"])
        # The grounded quote is one real quotation from the prose.
        self.assertTrue(qp.evidence_found(cands[0]["quote"], SHEDS))
        self.assertIn("fetching salvage", cands[0]["quote"])

    def test_a_known_speakers_lines_across_the_turn_are_one_candidate(self):
        # 8B run 146, T2: two paragraphs by the tallyman cost two fills and two checks.
        prose = ("Wulfstan [[B]] sits behind the desk. \"You'll need to work it off, and the guild has jobs that pay against the ledger.\"\n\n"
                 "\"What job have you got?\" you ask.\n\n"
                 "Wulfstan [[B]] leans back. \"There's the salvage contracts. They pay well if you're lucky. You'll be out on the water, working with the crew.\"")
        wulf = [{"code": "B", "name": "Wulfstan", "role": "guard"}]
        cands, _ = qo.find_offer_candidates(prose, FISH_INPUT, npcs=wulf, asked_for_work=True)
        self.assertEqual(len(cands), 1, cands)
        self.assertIn("work it off", cands[0]["line"])
        self.assertIn("salvage contracts", cands[0]["line"])
        self.assertTrue(qp.evidence_found(cands[0]["quote"], prose))

    def test_a_mark_whose_giver_said_nothing_is_dropped(self):
        prose = "Tilda [[A]] looks up from the ledger and says nothing. The tide is already turning."
        marks = [{"op": "QUEST", "title": "Salvage Contract", "giver": "A", "step": "Discuss work against debt"}]
        cands, dropped = qo.find_offer_candidates(prose, "I walk in.", npcs=TILDA, marks=marks)
        self.assertEqual(cands, [])
        self.assertEqual([d["why"] for d in dropped], ["mark_without_a_spoken_line"])

    def test_a_mark_on_small_talk_is_only_a_hint_the_fill_can_refuse(self):
        # 8B run 44, T1: the mark on "You're late, Flat-runner" made "Salvage Contract".
        marks = [{"op": "QUEST", "title": "Salvage Contract", "giver": "A", "step": "Discuss work against debt"}]
        cands, dropped = qo.find_offer_candidates(LATE, "I walk in.", npcs=TILDA, marks=marks)
        self.assertEqual([c["kind"] for c in cands], ["mark"])
        self.assertEqual(cands[0]["speaker"]["name"], "Tilda")
        ask, calls = _fake_ask(fill={"offers_work": False})
        report = qo.run_offer_pass(LATE, "I walk in.", npcs=TILDA, marks=marks, ask=ask)
        self.assertEqual([c["phase"] for c in calls], [qo.FILL_PHASE])
        self.assertEqual(report["new"], [])

    def test_a_mark_points_at_the_givers_line_when_the_line_has_no_job_words(self):
        prose = "Tilda [[A]] slides a slip across. \u201cThe nets on the east flat want hauling in before dark. The ledger drops a mark for it.\u201d"
        marks = [{"op": "QUEST", "title": "Haul the nets", "giver": "Tilda", "step": "Haul in the nets"}]
        cands, _ = qo.find_offer_candidates(prose, "Any work?", npcs=TILDA, marks=marks)
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["kind"], "mark")
        self.assertEqual(cands[0]["speaker"]["name"], "Tilda")

    def test_a_giver_met_this_turn_is_a_candidate_with_no_speaker(self):
        # 8B run 102, T3: the speaker was minted this turn and is not in the roster yet.
        prose = ("A broad woman behind the counter looks up. \u201cWe have several. The most immediate is a salvage job. "
                 "A wreck was found near the eastern docks, half-submerged.\u201d")
        cands, _ = qo.find_offer_candidates(prose, "What work is there?", npcs=[], asked_for_work=True)
        self.assertEqual(len(cands), 1)
        self.assertIsNone(cands[0]["speaker"])


class TheAsksFillAndCheck(unittest.TestCase):
    def test_find_fill_check_makes_one_checked_proposal(self):
        ask, calls = _fake_ask()
        report = qo.run_offer_pass(FISH, FISH_INPUT, npcs=VEYRA, asked_for_work=True, ask=ask)
        self.assertEqual([c["phase"] for c in calls], [qo.FILL_PHASE, qo.CHECK_PHASE])
        self.assertLessEqual(calls[0]["max_tokens"], qp.PARSER_MAX_TOKENS)
        # The fill sees one line and its paragraph, never the roster or open quests.
        self.assertIn("salted fish", calls[0]["user"]["line"])
        self.assertNotIn("known_npcs", calls[0]["user"])
        self.assertNotIn("open_quests", calls[0]["user"])
        # The check sees the card and the passage.
        self.assertEqual(calls[1]["user"]["card"]["title"], "Unload the salted fish")
        self.assertEqual(len(report["new"]), 1)
        item = report["new"][0]
        self.assertEqual(item["giver"], "A")
        self.assertEqual(item["title"], "Unload the salted fish")
        self.assertTrue(qp.evidence_found(item["evidence"], FISH))
        self.assertTrue(item["_checked"])
        self.assertEqual([s["title"] for s in item["steps"]], ["Go to the docks", "Unload the shipment"])

    def test_a_card_whose_task_is_the_players_own_words_is_dropped(self):
        # 8B run 146, T34: the fill took the task from the player's quoted line in the passage.
        line = "I turn to Hamon at the wheel. \"Then take me out to the wreck and show me what is buried, Captain. Whatever it costs, I will pay it out of what I bring up.\""
        prose = ("\"Then take me out to the wreck and show me what is buried, Captain. Whatever it costs, I will pay it out of what I bring up,\" you say. "
                 "Hamon Lockwood [[I]] smiles. \"You're not the kind of flat-runner I'm used to. Most of them would've asked for a cut of the salvage, not paid for the privilege.\"")
        hamon = [{"code": "I", "name": "Hamon Lockwood", "role": "ferry captain"}]
        ask, calls = _fake_ask(fill={"offers_work": True, "task": "Take me out to the wreck and show me what is buried", "title": "Show Me the Wreck",
                                     "steps": ["Head to the wreck"], "place": "Aegir's Wake", "pay": "", "gold": 0})
        report = qo.run_offer_pass(prose, line, npcs=hamon, ask=ask)
        self.assertEqual(report["new"], [])
        self.assertEqual([c["phase"] for c in calls], [qo.FILL_PHASE])
        self.assertEqual(report["fills"][0].get("dropped"), "task_is_the_players_words")

    def test_a_fill_that_sees_no_work_asks_no_check(self):
        ask, calls = _fake_ask(fill={"offers_work": False, "task": "", "title": ""})
        report = qo.run_offer_pass(FISH, FISH_INPUT, npcs=VEYRA, asked_for_work=True, ask=ask)
        self.assertEqual([c["phase"] for c in calls], [qo.FILL_PHASE])
        self.assertEqual(report["new"], [])

    def test_a_no_from_the_check_drops_the_card(self):
        ask, calls = _fake_ask(check={"offered": "no", "specific": "yes", "in_text": "yes", "why": "the player asked, no one offered"})
        report = qo.run_offer_pass(FISH, FISH_INPUT, npcs=VEYRA, asked_for_work=True, ask=ask)
        self.assertEqual(report["new"], [])
        self.assertFalse(report["checks"][0]["ok"])

    def test_a_failing_ask_never_raises(self):
        def ask(system, user, *, max_tokens, phase):
            raise RuntimeError("model down")

        report = qo.run_offer_pass(FISH, FISH_INPUT, npcs=VEYRA, asked_for_work=True, ask=ask)
        self.assertEqual(report["new"], [])
        self.assertIn("error", report["fills"][0])

    def test_no_ask_means_no_card_from_keywords_alone(self):
        report = qo.run_offer_pass(FISH, FISH_INPUT, npcs=VEYRA, asked_for_work=True, ask=None)
        self.assertEqual(report["new"], [])
        self.assertEqual(len(report["candidates"]), 1)

    def test_a_shape_placeholder_is_an_empty_field(self):
        card = qo.parse_fill({"offers_work": "true", "task": "the work itself, in the speaker's own words", "title": "Unload the fish", "steps": []})
        self.assertEqual(card["task"], "")
        self.assertEqual(card["steps"], ["Unload the fish"])

    def test_yes_and_no_come_in_many_shapes(self):
        self.assertTrue(qo.parse_check({"offered": True, "specific": "Yes", "in_text": "yes."})["ok"])
        self.assertFalse(qo.parse_check({"offered": "yes", "specific": "No", "in_text": "yes"})["ok"])
        self.assertFalse(qo.parse_check("not json at all")["ok"])


class TheEngineStillDecidesTheRest(unittest.TestCase):
    def test_a_checked_card_passes_the_keyword_judge_when_its_words_are_new(self):
        prose = "Tilda [[A]] slides a slip across. \u201cThe nets on the east flat want hauling in before dark. The ledger drops a mark for it.\u201d"
        item = {
            "title": "Haul in the nets", "summary": "The nets on the east flat want hauling in before dark", "giver": "A",
            "steps": [{"title": "Haul in the nets", "description": "", "location": "the east flat"}],
            "reward": {"gold": 0, "text": "The ledger drops a mark for it"},
            "offer_line": "The nets on the east flat want hauling in before dark. The ledger drops a mark for it.",
            "evidence": "The nets on the east flat want hauling in before dark. The ledger drops a mark for it.",
            "_checked": {"why": "Tilda names the work"},
        }
        accepted, rejected = qp.validate_quest_changes({"new": [item]}, narration=prose, player_input="Any work?", npcs=[{"id": 1, **TILDA[0]}])
        self.assertEqual([r["reasons"] for r in rejected], [])
        self.assertEqual(accepted["new"][0]["title"], "Haul in the nets")
        self.assertEqual(accepted["new"][0]["giver_npc_id"], 1)

    def test_a_checked_card_on_a_refusal_is_still_refused(self):
        prose = "Tilda [[A]] shakes her head. \u201cNo one is hiring this week. Try the docks next month.\u201d"
        item = {
            "title": "Try the docks", "summary": "x", "giver": "A", "steps": [{"title": "Try the docks"}],
            "reward": {}, "offer_line": "No one is hiring this week. Try the docks next month.",
            "evidence": "No one is hiring this week. Try the docks next month.", "_checked": {"why": "model said yes"},
        }
        _accepted, rejected = qp.validate_quest_changes({"new": [item]}, narration=prose, player_input="Any work?", npcs=[{"id": 1, **TILDA[0]}])
        self.assertIn("evidence_is_not_an_offer", rejected[0]["reasons"])

    def test_a_quote_not_in_the_text_is_replaced_by_the_givers_own_offer_sentence(self):
        # The engine's existing repair (8B run 104, T2) still runs on a checked card.
        item = {
            "title": "Unload the fish", "summary": "x", "giver": "A", "steps": [{"title": "Unload"}], "reward": {},
            "offer_line": "Words the prose never held, not even close to it.",
            "evidence": "Words the prose never held, not even close to it.", "_checked": {"why": "yes"},
        }
        accepted, rejected = qp.validate_quest_changes({"new": [item]}, narration=FISH, player_input=FISH_INPUT, npcs=[{"id": 1, **VEYRA[0]}])
        self.assertEqual(rejected, [])
        self.assertIn("job at the docks", accepted["new"][0]["evidence"])

    def test_a_quote_not_in_the_text_with_no_offer_sentence_is_refused(self):
        prose = "Veyra [[A]] shrugs. “The tide is turning. Mind the steps on your way out.”"
        item = {
            "title": "Unload the fish", "summary": "x", "giver": "A", "steps": [{"title": "Unload"}], "reward": {},
            "offer_line": "Words the prose never held, not even close to it.",
            "evidence": "Words the prose never held, not even close to it.", "_checked": {"why": "yes"},
        }
        _accepted, rejected = qp.validate_quest_changes({"new": [item]}, narration=prose, player_input="I nod.", npcs=[{"id": 1, **VEYRA[0]}])
        self.assertIn("evidence_not_in_text", rejected[0]["reasons"])


class ProgressIsCheckedTheSameWay(unittest.TestCase):
    ACTIVE = [{"id": 3, "code": "Q3", "title": "Unload the salted fish", "status": "active", "current_objective": "Unload the shipment"}]

    def test_a_result_sentence_about_the_job_is_a_candidate_and_a_yes_is_a_step_done(self):
        prose = "The last crate of salted fish is stacked on the quay and Veyra [[A]] counts out your pay."
        ask, calls = _fake_ask()
        report = qo.run_progress_pass(prose, "I stack the last crates.", active=self.ACTIVE, ask=ask)
        self.assertEqual([c["phase"] for c in calls], [qo.PROGRESS_PHASE])
        self.assertEqual(report["updates"][0]["quest"], "Q3")
        self.assertEqual(report["updates"][0]["action"], "step_done")

    def test_the_gate_opens_on_the_current_steps_words(self):
        # 8B run 142, T4: the title "Dredging the Drowned Town" was nowhere in
        # the prose, the step "Locate the drowned town's wreckage along the coast" was.
        prose = "You step over splintered planks and pull at the remnants of what was once a ship. The wreckage is scattered along the coast."
        active = [{"code": "Q1", "title": "Dredging the Drowned Town", "status": "active",
                   "current_objective": "Locate the drowned town's wreckage along the coast"}]
        self.assertEqual(qp.quest_parse_gate(prose, "I work the wreckage.", active_quests=active), "open_quest_step_named")
        self.assertEqual(qp.quest_parse_gate("Rain runs off the slate roofs.", "I wait.", active_quests=active), "")

    def test_the_players_own_words_said_back_are_no_result(self):
        # 8B run 145, T38: the prose echoed the player's "Done" line and the step was finished on it.
        line = "\"Forty-five gold for the deep dive, paid on the guild's count, and the chest's share settled first. Done.\" I hold out my hand."
        prose = ("“Forty-five gold for the deep dive, paid on the guild's count, and the chest's share settled first. Done,” you say. "
                 "Veyra [[B]] stares at your palm. \"The team goes down at dawn.\"")
        active = [{"code": "Q1", "title": "Deep Site Salvage Dive", "status": "active", "current_objective": "Join a team for a deep dive"}]
        report = qo.run_progress_pass(prose, line, active=active, ask=_fake_ask()[0])
        self.assertEqual(report["candidates"], [])

    def test_setting_out_is_no_candidate(self):
        prose = "You head down to the docks to unload the salted fish before the tide turns."
        report = qo.run_progress_pass(prose, "I go to the docks.", active=self.ACTIVE, ask=_fake_ask()[0])
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["updates"], [])

    def test_a_no_leaves_the_step_open(self):
        prose = "The last crate of salted fish is stacked on the quay and Veyra [[A]] counts out your pay."
        ask, _ = _fake_ask(progress={"finished": "no", "why": "still hauling"})
        report = qo.run_progress_pass(prose, "I stack the last crates.", active=self.ACTIVE, ask=ask)
        self.assertEqual(report["updates"], [])


class ASuggestionIsNoAssignment(unittest.TestCase):
    def test_lets_see_what_else_is_worth_salvaging_offers_no_job(self):
        # 8B run 147, T29: the ferryman's suggestion filed a second wreck job.
        line = ("This'll be a pain to get in, Now, let's see if there's anything else worth salvaging, You might find the "
                "name board or some mark of ownership in there. But be careful—these old wrecks can hide more than you expect.")
        self.assertEqual(qo._code_veto(line, asked_for_work=False), "suggestion_not_task")

    def test_a_suggestion_with_pay_named_is_still_an_offer(self):
        line = "You might take the nets job if you want it. Twenty gold for a day's hauling, paid at dusk."
        self.assertEqual(qo._code_veto(line, asked_for_work=False), "")


class TypedAcceptsStillReachTheEngine(unittest.TestCase):
    OFFERS = [{"id": 2, "code": "Q2", "title": "Retrieve the Captain's Ledger", "status": "offered"}]

    def test_ill_find_it_accepts_the_one_open_offer(self):
        # 8B run 146, T14: the checked flow proposed no updates, so the typed yes was lost.
        line = "\"The captain's ledger from the Aegir's Wake, then. I'll find it.\" I ask Emery where the cabin lay."
        updates = qo.typed_accepts(line, self.OFFERS)
        self.assertEqual([(u["quest"], u["action"]) for u in updates], [("Q2", "accept")])

    def test_two_open_offers_need_the_line_to_name_one(self):
        offers = self.OFFERS + [{"id": 3, "code": "Q3", "title": "Haul the nets", "status": "offered"}]
        self.assertEqual(qo.typed_accepts("\"I'll do it.\"", offers), [])
        self.assertEqual([u["quest"] for u in qo.typed_accepts("\"I'll take the nets job.\"", offers)], ["Q3"])

    def test_a_refusal_or_a_plain_line_proposes_nothing(self):
        self.assertEqual(qo.typed_accepts("\"No deal.\"", self.OFFERS), [])
        self.assertEqual(qo.typed_accepts("I walk down to the dock.", self.OFFERS), [])

    def test_a_yes_that_waits_on_terms_is_no_yes(self):
        # 8B run 146, T62: "before I agree to any of them" accepted Elara's job.
        line = ("\"Then say the risk plainly, Rolf. I came this far on Elara's word and my own two feet. "
                "I will hear your terms before I agree to any of them.\"")
        self.assertEqual(qo.typed_accepts(line, self.OFFERS), [])
        self.assertEqual(qo.typed_accepts("\"If I take it, it's on my terms. Tell me the pay first.\"", self.OFFERS), [])
        # The plain yes still stands.
        self.assertEqual([u["action"] for u in qo.typed_accepts("\"Agreed. I'll find the ledger.\"", self.OFFERS)], ["accept"])


class MarksAreHintsInCheckedMode(unittest.TestCase):
    MARKS = [
        {"op": "QUEST", "title": "Salvage Contract", "giver": "A", "step": "x"},
        {"op": "QUEST_DONE", "quest": "Q1", "action": "step_done", "evidence": "the last crate is stacked"},
    ]

    def test_checked_mode_keeps_only_done_marks_for_both_merge_points(self):
        # 8B run 142, T2: world.apply_turn merged a bare "Salvage Contract" mark
        # after the offer pass had already decided. One rule for both places.
        kept = qo.marks_to_merge(self.MARKS, "checked")
        self.assertEqual([m["op"] for m in kept], ["QUEST_DONE"])

    def test_legacy_and_off_modes_keep_every_mark(self):
        self.assertEqual(len(qo.marks_to_merge(self.MARKS, "legacy")), 2)
        self.assertEqual(len(qo.marks_to_merge(self.MARKS, "off")), 2)

    def test_the_apply_step_drops_a_bare_mark_in_checked_mode(self):
        from app import db, world

        db.init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Tally House", "special_ability_origin": "none"})
        result = {"narration": LATE, "quest_marks": [{"op": "QUEST", "title": "Salvage Contract", "giver": "Tilda", "step": "Discuss work"}]}
        with mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "checked"}):
            world.apply_turn(result, "I walk in.")
        with db.connect() as conn:
            rows = conn.execute("SELECT title FROM quests").fetchall()
        self.assertEqual([r["title"] for r in rows], [])


class TheHookRunsTheCheckedFlow(unittest.TestCase):
    CONTEXT = {
        "current_location": {"code": "L1", "name": "Tally House", "npcs": VEYRA},
        "locations": [{"code": "L1", "name": "Tally House", "npcs": VEYRA}],
        "active_quests": [],
        "open_offers": [],
    }

    def test_checked_mode_fills_then_checks_and_attaches_the_card(self):
        from app import llm

        replies = [
            {"offers_work": True, "task": "A shipment of salted fish needs unloading", "title": "Unload the salted fish",
             "steps": ["Unload the shipment"], "place": "the docks", "pay": "it pays well", "gold": 0},
            {"offered": "yes", "specific": "yes", "in_text": "yes", "why": "Veyra names the job"},
        ]
        trace: list = []
        with mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "checked"}), \
                mock.patch.object(llm, "_chat_json", side_effect=replies) as chat:
            turn = llm._run_quest_parser({"narration": FISH}, self.CONTEXT, FISH_INPUT, trace=trace)
        self.assertEqual([c.kwargs["phase"] for c in chat.call_args_list], [qo.FILL_PHASE, qo.CHECK_PHASE])
        self.assertEqual(turn["quest_changes"]["new"][0]["title"], "Unload the salted fish")
        self.assertEqual(turn["quest_changes"]["source"], "checked")
        record = [r for r in trace if r.get("phase") == qp.PARSER_PHASE][-1]
        self.assertEqual(record["event"], "checked")
        self.assertEqual(record["mode"], "checked")
        self.assertEqual(record["asks"], 2)
        self.assertEqual(len(record["offers"]["candidates"]), 1)

    def test_checked_mode_trusts_no_bare_mark(self):
        from app import llm

        turn = {"narration": LATE, "quest_marks": [{"op": "QUEST", "title": "Salvage Contract", "giver": "A", "step": "Discuss work"}]}
        context = {**self.CONTEXT, "current_location": {"code": "L1", "name": "Tally House", "npcs": TILDA},
                   "locations": [{"code": "L1", "name": "Tally House", "npcs": TILDA}]}
        trace: list = []
        with mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "checked"}), \
                mock.patch.object(llm, "_chat_json", return_value={"offers_work": False}) as chat:
            turn = llm._run_quest_parser(turn, context, "I walk in.", trace=trace)
        # The mark only sent Tilda's line to the fill; the fill's no ends it.
        self.assertEqual([c.kwargs["phase"] for c in chat.call_args_list], [qo.FILL_PHASE])
        self.assertNotIn("quest_changes", turn)
        record = [r for r in trace if r.get("phase") == qp.PARSER_PHASE][-1]
        self.assertEqual(record["offers"]["fills"][0]["card"], None)

    def test_a_turn_with_no_job_words_makes_no_ask(self):
        from app import llm

        with mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "checked"}), \
                mock.patch.object(llm, "_chat_json") as chat:
            turn = llm._run_quest_parser({"narration": "Rain runs off the slate roofs."}, self.CONTEXT, "I wait.")
        chat.assert_not_called()
        self.assertNotIn("quest_changes", turn)

    def test_legacy_mode_is_still_the_one_shot_parser(self):
        from app import llm

        reply = {"new": [{"title": "Unload the salted fish", "giver": "A", "steps": [{"title": "Unload"}],
                          "offer_line": "There's a job at the docks. A shipment of salted fish needs unloading.",
                          "evidence": "A shipment of salted fish needs unloading"}], "updates": []}
        with mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "legacy"}), \
                mock.patch.object(llm, "_chat_json", return_value=reply) as chat:
            turn = llm._run_quest_parser({"narration": FISH}, self.CONTEXT, FISH_INPUT)
        self.assertEqual(chat.call_args.kwargs["phase"], qp.PARSER_PHASE)
        self.assertEqual(chat.call_args.kwargs["max_tokens"], qp.PARSER_MAX_TOKENS)
        self.assertEqual(turn["quest_changes"]["new"][0]["title"], "Unload the salted fish")

    def test_the_default_mode_is_checked(self):
        from app import llm

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AI_RPG_QUEST_PARSER", None)
            self.assertEqual(llm._quest_parser_mode(), "checked")
            self.assertTrue(llm._quest_parser_enabled())
        with mock.patch.dict(os.environ, {"AI_RPG_QUEST_PARSER": "0"}):
            self.assertEqual(llm._quest_parser_mode(), "off")
            self.assertFalse(llm._quest_parser_enabled())


if __name__ == "__main__":
    unittest.main()
