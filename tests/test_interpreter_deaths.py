"""The interpreter: a death or a destruction the final prose shows is an event the engine records (#154, #157).

The strings are the tester's Hermes 3 8B game (campaign cc87dd29, T5-T14) and
the baseline replay before the fix (live/baseline, traces 3-5 = harness T2-T4).
The model is mocked; where the live eval of 2026-10-23 measured what Hermes 3
8B really answered to an ask, the mock gives that reply word for word
(scratchpad live-eval/results.json): its yes bias, its misses, its long
"Yes, Beth says something in the sentence" replies.

Run:  cd tests && python -m unittest test_interpreter_deaths
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-interpreter-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    "AI_RPG_CAMPAIGN_SLOTS": str(_TMP / "slots"),
}
os.environ.update(_ENV)

from app import db, interpreter, llm, world  # noqa: E402
from app.turn_dsl import facts_to_keep  # noqa: E402

I = interpreter

# --- cc87dd29 T10: the player rips Beth in half (no check was rolled) -------
T10 = (
    "You lunge towards Beth [[B]], grabbing her arms with one hand and her legs with the other. With a violent twist, "
    "you attempt to rip her in two, your muscles straining against her flesh.\n\n"
    "Morning light filters in through grimy windows, casting an eerie pallor over the clinic's cold stone floors. The air "
    "is thick with the stench of decay and the sound of your own heavy breathing. Beth [[B]] screams in agony as you "
    "wrench her arms and legs with a savage grip. She thrashes and struggles, trying to break free from your iron hold.\n\n"
    "A sickening tear rips through her flesh as you wrench her body apart. Gore and viscera splatter across the floor in "
    "a grisly display. Her entrails spill out across the hard stone, pooling in a dark crimson puddle as her lifeless "
    "upper body collapses to the ground. You stand over the grisly remains, your arms and torso splattered in Beth "
    "[[B]]'s blood and innards.\n\n"
    "The clinic falls silent, save for the sound of your heart pounding in your ears. The life has been ripped from her, "
    "leaving only a macabre still life behind. Beth [[B]]'s wide, dead eyes stare up at the stained ceiling, her body "
    "split down the middle in an act of savage violence. You stand over her corpse, the fruits of your brutality "
    "staining your hands and chest with her blood and gore."
)
T10_MODEL_SUMMARY = "You killed Beth [[B]], the doctor you encountered earlier."

# --- cc87dd29 T11: "i search Beth's body" and she speaks --------------------
T11 = (
    "You pat Beth [[B]] down carefully, searching for any hidden weapons or items. The doctor's coat she wears is thick, "
    "but you feel around every pocket and seam. To your surprise, she is not carrying anything - no knife, gun, or even "
    "a small pouch. Beth [[B]] frowns, clearly puzzled by your actions. \"You're looking for something? I don't have "
    "anything to give or sell. Now state your business, or leave.\" Her words are firm, with an edge of warning in her "
    "voice.\n\n"
    "The clinic looks old and ramshackle but functional. Beth [[B]], a middle-aged woman in a doctor's coat, steps out "
    "from the clinic. She regards you with suspicion. \"State your business here,\" she says."
)
# What Hermes 3 8B answered to the per-sentence ask on each T11 sentence (live eval).
T11_WHICH = {
    "You pat Beth down": 'No, in the sentence "You pat',
    "The doctor's coat": "No, Beth does not say or do",
    "To your surprise": "No, Beth does not say or do",
    "Beth frowns": "No.",
    "\"You're looking for something?": "Yes, Beth says something in the sentence",
    "Her words are firm": "No.",
    "The clinic looks old": "No, Beth does not say or do",
    "Beth, a middle-aged woman": 'No. In the sentence "Beth,',
    "She regards you": 'Yes, in the sentence "She regards',
    "\"State your business here,\"": "Yes, Beth says something in the sentence",
}

# --- cc87dd29 T13: the prose has Beth alive, the model summary has her killed -
T13 = (
    "You approach Dr. Beth [[B]] cautiously, your power armor clanking with every step. Beth [[B]] looks you over "
    "warily, her expression wary and her posture tense. As you speak, she raises an eyebrow, clearly skeptical of your "
    "intentions. She crosses her arms, considering your proposal.\n\n"
    "Dr. Beth [[B]] looks you over, clearly skeptical of your intentions.\n\n"
    "Dr. Beth [[B]] leans back in her chair, her expression one of pure disbelief. \"You're out of your damn mind if you "
    "think I'm going to let you kill me in my own clinic,\" she snarls, her voice dripping with anger. With surprising "
    "speed for someone her age, she grabs a scalpel from the tray on her desk and points it directly at you."
)
T13_MODEL_SUMMARY = "You killed Dr. Beth [[B]] in the clinic."

# --- cc87dd29 T6: after the T5 death, Beth calls out (the old hold said "No") -
T6 = (
    "As you leave the town of Thornford behind and the forest looms ahead, Beth [[B]] calls out from the clinic gates. "
    "\"Stay safe out there!\" she shouts. \"And keep an eye out for any radiation hotspots. The ghouls are bad enough "
    "without having to deal with that too!\" The path splits ahead, one trail leading towards a babbling stream, the "
    "other cutting through the heart of the forest.\n\n"
    "You push deeper into the forest, the towering trees swallowing up the path behind you. The crisp morning breeze "
    "carries a hint of smoke from distant fires. You keep your grip on your bike gloves, prepared for anything. The "
    "radiation sensors on your X-01 power armor flash a warning - supplies are running low, and the thought of facing "
    "these mutated scavengers sends a chill down your spine.\n\n"
    "You follow the forest trail, the crunch of fallen leaves underfoot a constant reminder of the unknown dangers that "
    "lurk in the shadows. As you ponder your next move, you catch sight of a flicker of movement in the distance - a "
    "figure, silhouetted against the early morning haze. The figure is moving with purpose, striding purposefully "
    "towards the north, where the stream trickles through the trees."
)
T6_WHICH = {
    "As you leave the town": "Yes, Beth calls out from the clinic",
    "\"Stay safe out there!\"": "Yes, Beth says something in the sentence",
    "\"And keep an eye out": "Yes, Beth says something in that sentence",
    "The path splits ahead": "No, in the given sentence, Beth",
}

# --- cc87dd29 T5: the clinic burned (one paragraph of the real scene) -------
T5 = (
    "You bellow a chilling war cry as you storm into the Radiation Fenced Sanctuary Clinic [[L3]], a grim look of fury "
    "etched upon your armored visor. Smoke billows from the ruins of the Radiation Fenced Sanctuary Clinic [[L3]], now "
    "reduced to smoldering rubble. Beth [[B]] lies crumpled on the scorched floor, her neck twisted at an unnatural "
    "angle. The acrid smell of charred wood and scorched metal fills the night."
)
# --- cc87dd29 T5, the rest of the scene: flames at Thornford's buildings ----
T5_THORNFORD = (
    "With a twisted smile, you turn your gaze towards the city of Thornford [[L4]], ready to continue your rampage. The "
    "once bustling medical center is now little more than charred rubble, the screams of the dying echoing in your "
    "ears. You methodically search the ruins, checking each room and crevice for any signs of life.\n\n"
    "The blood lust has yet to be sated. Through the haze of smoke and carnage, you glimpse distant flames licking at "
    "the buildings of Thornford [[L4]], a grim reminder that your rampage is far from over.\n\n"
    "The sound of distant gunfire and the occasional explosion from within the city reminds you that your work is far "
    "from finished. The streets of Thornford [[L4]] are eerily quiet, save for the occasional scream and the crackle of "
    "flames consuming the buildings. The once vibrant city is now a war-torn wasteland, littered with the corpses of "
    "the fallen."
)
# --- cc87dd29 T14: the town named on its own ---------------------------------
T14_TOWN = (
    "\"Nothing too risky, of course. Radiation Fenced Sanctuary isn't without its dangers, but I like to keep my "
    "associates safe.\"\n\nThe Radiation Fenced Sanctuary is starting to feel a bit small."
)

# --- baseline replay (harness T2 = trace 3, T3 = trace 4, T4 = trace 5) -----
B2 = (
    "You enter the Radiation Fenced Sanctuary Clinic [[L2]], a small but well-kept medical outpost. The front door is "
    "locked, but a side door stands open. Inside, the clinic is clean and organized, with rows of beds on either side. A "
    "woman in medical scrubs, Marisol [[A]], is moving between them, checking on patients. She sees you enter and waves "
    "you over.\n\n"
    "Marisol [[A]] says, \"Oh good, a new volunteer. We could use the help. What's your name?\"\n\n"
    "You: i shoot Marisol [[A]]\n\n"
    "Marisol [[A]]'s eyes widen and she steps back, raising her hands defensively. \"Whoa, easy there! I'm not the "
    "enemy.\" She glances around, worried. \"You're not planning on shooting anyone, are you? In here, we patch people "
    "up, not send them off to their deaths.\"\n\n"
    "Marisol [[A]] says, \"I'm just trying to help. This clinic is a safe place, for patients and volunteers both. We "
    "work together to save lives, not fight each other.\""
)
B3 = (
    "You lunge at Marisol [[A]], grabbing her arms with one hand and her legs with the other. With a brutal motion, you "
    "rip her in two. Marisol [[A]]'s body separates at the waist, her upper and lower halves falling to the floor in a "
    "spray of blood. The other volunteers scream and scramble away from the carnage.\n\n"
    "Marisol [[A]]'s death is instantaneous. She had no chance to fight back or even cry out.\n\n"
    "The clinic erupts in chaos as the volunteers flee in terror. Some of them shout for the guards, while others rush "
    "to contain the damage. The scene is one of pure shock and horror.\n\n"
    "As the dust settles, you stand over Marisol [[A]]'s remains, panting heavily. Her blood is pooled on the floor, and "
    "her eyes seem to still be staring at you in disbelief. You feel no remorse for what you've done.\n\n"
    "You are still in the Radiation Fenced Sanctuary Clinic [[L2]]. The grisly murder has left the place in utter "
    "disarray. The other volunteers are huddled in a corner, clearly terrified of you. You have no weapons or items to "
    "take from the scene.\n\n"
    "The clinic's exits are still intact, though the volunteers seem to be trying to barricade them. You could try to "
    "flee the scene before the guards arrive. Alternatively, you could hide among the bodies and hope the guards don't "
    "find you.\n\n"
    "What do you do now?"
)
B4 = (
    "You search Marisol [[A]]'s body, finding a few scraps of paper, a small compass, and a worn leather wallet. The "
    "wallet contains a few silver coins and a tarnished copper key.\n\n"
    "Marisol [[A]] looks alarmed as you search her. \"What are you doing?!\" she demands, reaching for the knife at her belt."
)
B4_MODEL_SUMMARY = (
    "You search Marisol [[A]] and find no weapons or hidden items. Marisol [[A]] confronts you about searching her. "
    "You apologize and continue waiting in line for treatment."
)
B4_WHICH = {
    "You search Marisol": "No.",
    "The wallet contains": "No, Marisol does not say or",
    "Marisol looks alarmed": 'No. In the sentence "Marisol',
    "\"What are you doing?!\"": 'Yes, Marisol says "What are',
}
B5 = (
    "The clinic is bustling with activity as search-and-rescue volunteer Marisol [[A]] eyes you up and down.\n\n"
    "\"What's your name?\"\n\n"
    "You introduce yourself to Marisol [[A]], explaining that you're in need of medical attention."
)

CORPSE = (
    "You kneel beside Beth [[B]], her eyes still open. Beth [[B]] lies where she fell, motionless. "
    "The clinic is cold and quiet around you."
)
MEMORY = (
    "You remember Beth [[B]]'s laugh, and the way she hummed while she stitched a wound. The clinic is empty now, "
    "its cots stripped and its shelves bare, and the wind moves the torn curtain at the window."
)


def _records(died_turn: int = 0, place_destroyed: int = 0) -> dict:
    return {
        "people": [
            {"code": "A", "name": "New Vegas", "died_turn": 0},
            {"code": "B", "name": "Beth", "died_turn": died_turn},
        ],
        "places": [
            {"code": "L1", "name": "Radiation Fenced Sanctuary", "destroyed_turn": 0},
            {"code": "L3", "name": "Radiation Fenced Sanctuary Clinic", "destroyed_turn": place_destroyed},
            {"code": "L4", "name": "Thornford", "destroyed_turn": 0},
        ],
        "player_names": ["Ash"],
    }


def _sentence_of(prompt: str) -> str:
    found = re.search(r'In the sentence "(.*)", does ', prompt, re.S)
    return found.group(1) if found else ""


class FakeModel:
    """Answers each ask by its phase, with the reply shapes Hermes 3 8B gave.

    ``died`` / ``destroyed``: names the first ask says yes for; ``still_alive``
    / ``still_standing``: names the second (checking) ask answers yes for, so
    the fact is not confirmed. ``which``: sentence start -> reply, for the
    per-sentence pick (default "No.").
    """

    def __init__(self, *, died=(), destroyed=(), still_alive=(), still_standing=(), acts=False, returned=False,
                 still_dead=False, which=None, always=None):
        self.died = set(died)
        self.destroyed = set(destroyed)
        self.still_alive = set(still_alive)
        self.still_standing = set(still_standing)
        self.acts = acts
        self.returned = returned
        self.still_dead = still_dead
        self.which = dict(which or {})
        self.always = always
        self.calls: list[tuple[str, str]] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append((phase, prompt))
        if self.always is not None:
            return self.always
        if phase == I.PHASE_DIED:
            return "Yes, she is dead at the end" if any(f"Is {n} dead" in prompt for n in self.died) else "No"
        if phase == I.PHASE_DIED_CHECK:
            return "Yes" if any(f"Is {n} alive" in prompt for n in self.still_alive) else "No, she is not alive"
        if phase == I.PHASE_DESTROYED:
            return "Yes, it appears to be destroyed" if any(f"Is {n} destroyed" in prompt for n in self.destroyed) else "No"
        if phase == I.PHASE_DESTROYED_CHECK:
            return "Yes, some of it" if any(f"any of {n} still" in prompt for n in self.still_standing) else "No."
        if phase == I.PHASE_HOLD:
            return "Yes, she says something in the text" if self.acts else "No, she does not say or do"
        if phase == I.PHASE_RETURNED:
            return "Yes" if self.returned else "No"
        if phase == I.PHASE_RETURNED_CHECK:
            return "Yes" if self.still_dead else "No"
        if phase == I.PHASE_WHICH:
            sentence = _sentence_of(prompt)
            for start, reply in self.which.items():
                if sentence.startswith(start):
                    return reply
            return "No."
        return ""

    def phases(self) -> list[str]:
        return [p for p, _ in self.calls]


class TestCandidatesComeFromTheRecords(unittest.TestCase):
    def test_codes_and_unique_roster_names(self):
        rows = _records()["people"]
        self.assertEqual([r["code"] for r in I.named(T10, rows)], ["B"])
        self.assertEqual([r["code"] for r in I.named("I search Beth's body.", rows)], ["B"])

    def test_a_name_two_rows_share_resolves_to_nothing_but_the_code_still_counts(self):
        rows = [
            {"code": "B", "name": "Beth", "died_turn": 0},
            {"code": "C", "name": I.clean_name("NAME: Beth"), "died_turn": 0},
        ]
        self.assertEqual(I.named("Beth waves.", rows), [])
        self.assertEqual([r["code"] for r in I.named("Beth [[C]] waves.", rows)], ["C"])

    def test_a_place_inside_a_longer_place_name_is_not_named(self):
        # cc87dd29 T5: the clinic L3 is named; the town L1 is only part of its name.
        records = _records()
        match = I.Matcher(records["people"], records["places"])
        self.assertEqual([r["code"] for r in match.named(T5, records["places"])], ["L3"])
        # Reverse: cc87dd29 T14 names the town on its own.
        self.assertEqual([r["code"] for r in match.named(T14_TOWN, records["places"])], ["L1"])

    def test_t5_asks_nothing_about_the_town(self):
        model = FakeModel(always="Yes")
        I.run(T5, _records(), model)
        self.assertFalse(any("Is Radiation Fenced Sanctuary destroyed" in p for _ph, p in model.calls))

    def test_no_words_decide_only_the_records(self):
        model = FakeModel(died={"Beth"})
        out = I.run("The raider falls dead in the dust.", _records(), model)
        self.assertEqual(out["events"], [])
        self.assertEqual(model.calls, [])

    def test_the_ask_reads_the_passage_without_codes(self):
        passage = I.passage_for(T10, {"code": "B", "name": "Beth"})
        self.assertNotIn("[[", passage)
        self.assertIn("Beth's wide, dead eyes", passage)


class TestDeathIsAnEvent(unittest.TestCase):
    def test_cc87dd29_t10_records_beth_dead_after_the_check(self):
        model = FakeModel(died={"Beth"})
        out = I.run(T10, _records(), model)
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in out["events"]], [("died", "B")])
        (p1, q1), (p2, q2) = model.calls[:2]
        self.assertEqual((p1, p2), (I.PHASE_DIED, I.PHASE_DIED_CHECK))
        self.assertTrue(q1.endswith("Is Beth dead at the end of it? Answer yes or no."))
        self.assertTrue(q2.endswith("Is Beth alive at the end of it? Answer yes or no."))
        self.assertEqual(out["narration"], T10)

    def test_a_death_the_check_does_not_confirm_is_not_recorded(self):
        model = FakeModel(died={"Beth"}, still_alive={"Beth"})
        out = I.run(T10, _records(), model)
        self.assertEqual(out["events"], [])
        self.assertEqual(out["report"]["unconfirmed"], [{"kind": "died", "code": "B", "check": True}])

    def test_a_yes_biased_model_records_nothing(self):
        # The skeptic's "yes" replay: every ask says yes. The second ask is
        # worded the other way round, so a yes there refuses the fact.
        for text in (T10, T13, B2, T5):
            out = I.run(text, _records(), FakeModel(always="Yes"))
            self.assertEqual(out["events"], [], text[:40])

    def test_a_no_records_nothing(self):
        out = I.run(T10, _records(), FakeModel())
        self.assertEqual(out["events"], [])

    def test_an_unreadable_reply_records_nothing(self):
        out = I.run(T10, _records(), lambda phase, prompt, n: "Beth's fate is unclear")
        self.assertEqual(out["events"], [])

    def test_a_failed_ask_never_breaks_the_turn(self):
        def down(phase, prompt, n):
            raise TimeoutError("model down")

        out = I.run(T10, _records(), down)
        self.assertEqual(out["events"], [])
        self.assertEqual(out["narration"], T10)
        self.assertIn("error", out["report"]["asks"][0])

    def test_cc87dd29_t5_the_clinic_destroyed(self):
        model = FakeModel(died={"Beth"}, destroyed={"Radiation Fenced Sanctuary Clinic"})
        out = I.run(T5, _records(), model)
        kinds = sorted((e["kind"], e["subject"]["code"]) for e in out["events"])
        self.assertEqual(kinds, [("destroyed", "L3"), ("died", "B")])

    def test_cc87dd29_t5_thornford_burning_is_not_recorded_destroyed(self):
        # Live: "Yes, Thornford appears to be destroyed" three times over flames
        # at its buildings. The check ("Is any of Thornford still standing?")
        # must say no before the city is recorded destroyed.
        model = FakeModel(destroyed={"Thornford"}, still_standing={"Thornford"})
        out = I.run(T5_THORNFORD, _records(), model)
        self.assertEqual(out["events"], [])
        checks = [p for ph, p in model.calls if ph == I.PHASE_DESTROYED_CHECK]
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0].endswith("Is any of Thornford still standing at the end of it? Answer yes or no."))
        # Reverse: a check that says nothing stands records it.
        out = I.run(T5_THORNFORD, _records(), FakeModel(destroyed={"Thornford"}))
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in out["events"]], [("destroyed", "L4")])

    def test_the_living_duplicate_of_a_dead_person_is_never_asked(self):
        # Live end to end: after B was recorded dead, the died ask ran on the
        # living row C "NAME: Beth" and recorded her dead too.
        records = _records(died_turn=10)
        records["people"].append({"code": "C", "name": I.clean_name("NAME: Beth"), "died_turn": 0})
        model = FakeModel(died={"Beth"}, acts=True, which=T11_WHICH)
        out = I.run(T11, records, model)
        self.assertNotIn(I.PHASE_DIED, model.phases())
        self.assertEqual(out["events"], [])
        # A sentence coded to C is not B's: B's hold is not asked about it, nothing is cut.
        model = FakeModel(died={"Beth"}, acts=True, which={"Beth waves": "Yes"})
        text = "Beth [[C]] waves at you from the counter. The shop smells of oil and old rope."
        out = I.run(text, records, model)
        self.assertEqual(out["narration"], text)
        self.assertEqual(model.calls, [])

    def test_summary_carries_the_event_first_then_what_happened(self):
        model = FakeModel(died={"Beth"})
        out = I.run(T10, _records(), model)
        line = I.summary(out["events"], out["narration"])
        self.assertTrue(line.startswith("Beth [[B]] died. You lunge towards Beth [[B]]"), line)
        self.assertIn("You stand over her corpse", line)

    def test_asks_per_turn_are_capped(self):
        people = [{"code": c, "name": n, "died_turn": 9} for c, n in (("D", "Dora"), ("E", "Edda"), ("F", "Fenn"))]
        text = "\n\n".join(
            " ".join(f"{n} [[{c}]] waves number {i}." for i in range(20)) for c, n in (("D", "Dora"), ("E", "Edda"), ("F", "Fenn"))
        )
        out = I.run(text, {"people": people, "places": []}, FakeModel(always="Yes"))
        self.assertLessEqual(len(out["report"]["asks"]), I.MAX_ASKS)


class TestTheSummaryFollowsTheProse(unittest.TestCase):
    def test_cc87dd29_t13_prose_alive_summary_dead(self):
        turn = {"narration": T13, "turn_summary": T13_MODEL_SUMMARY}
        model = FakeModel()  # Beth is not dead at the end of T13's prose
        with mock.patch.object(llm, "_chat_text", side_effect=lambda s, p, **k: model(k["phase"], p, k["max_tokens"])):
            result = llm._run_interpreter(dict(turn), "i rip her head from her shoulders", records=_records(), trace=[], usage=[])
        self.assertNotIn("interpreted_events", result)
        self.assertNotIn("killed", result["turn_summary"])
        self.assertTrue(result["turn_summary"].startswith("You approach Dr. Beth [[B]] cautiously"))
        # The people's reply is in it, not only the first and last sentence.
        self.assertIn("You're out of your damn mind", result["turn_summary"])

    def test_baseline_t3_does_not_end_on_the_question_put_to_the_player(self):
        line = I.summary([], B3)
        self.assertNotIn("What do you do now?", line)
        self.assertTrue(line.startswith("You lunge at Marisol [[A]]"), line)

    def test_baseline_t2_carries_the_act_and_the_reply(self):
        line = I.summary([], B2)
        self.assertTrue(line.startswith("You enter the Radiation Fenced Sanctuary Clinic [[L2]]"), line)
        self.assertIn("Oh good, a new volunteer.", line)
        self.assertIn("I'm just trying to help.", line)

    def test_the_players_own_words_are_not_the_reply(self):
        text = 'You say, "Hello there, doc." Beth [[B]] nods. "Back so soon?" she asks. The rain keeps on.'
        line = I.summary([], text, player_quotes=["Hello there, doc."])
        self.assertIn("Back so soon?", line)

    def test_baseline_t4_invented_apology_is_not_kept(self):
        turn = {"narration": B4, "turn_summary": B4_MODEL_SUMMARY}
        with mock.patch.dict(os.environ, {"AI_RPG_INTERPRETER": "off"}):
            result = llm._run_interpreter(turn, "i search Marisol's body", trace=[], usage=[])
        self.assertNotIn("apologize", result["turn_summary"])
        self.assertIn("You search Marisol [[A]]'s body", result["turn_summary"])

    def test_recovered_draft_never_stores_the_placeholder(self):
        content = '{"narration": "' + T13.split("\n\n")[0].replace('"', "'") + '", "player": {'
        turn = llm._narration_only_turn_from_text(content, {"current_location": {"name": "Radiation Fenced Sanctuary"}}, "bad json")
        self.assertNotIn("Recovered readable draft", turn["turn_summary"])
        self.assertTrue(turn["turn_summary"].startswith("You approach Dr. Beth"), turn["turn_summary"])


class TestTheDeadAreHeld(unittest.TestCase):
    def test_the_hold_asks_the_tested_question(self):
        model = FakeModel(acts=True, which=T6_WHICH)
        I.run(T6, _records(died_turn=5), model)
        prompt = next(p for ph, p in model.calls if ph == I.PHASE_HOLD)
        self.assertTrue(prompt.startswith("Read this.\n\nAs you leave the town of Thornford"))
        self.assertTrue(prompt.endswith("Does Beth say or do anything in it? Answer yes or no."))

    def test_cc87dd29_t6_she_calls_out_after_her_death_and_is_cut(self):
        # The old hold missed T6 ("No" three times, live); the says/does hold
        # said "Yes, Beth says something in the text" and the per-sentence
        # ask picked exactly sentences 1-3.
        model = FakeModel(acts=True, which=T6_WHICH)
        out = I.run(T6, _records(died_turn=5), model)
        text = out["narration"]
        self.assertNotIn("Beth [[B]] calls out", text)
        self.assertNotIn("Stay safe out there!", text)
        self.assertNotIn("radiation hotspots", text)
        self.assertTrue(text.startswith("The path splits ahead"), text[:80])
        self.assertIn("You push deeper into the forest", text)
        self.assertEqual(out["events"], [])
        self.assertNotIn(I.PHASE_DIED, model.phases())

    def test_cc87dd29_t11_searching_the_body_she_speaks(self):
        model = FakeModel(acts=True, which=T11_WHICH)
        out = I.run(T11, _records(died_turn=10), model)
        text = out["narration"]
        # The player's own act stays, whatever was asked.
        self.assertIn("You pat Beth [[B]] down carefully", text)
        self.assertNotIn("You're looking for something?", text)
        self.assertNotIn("She regards you with suspicion", text)
        self.assertNotIn("State your business here", text)
        # Hermes missed these quiet acts: they stay (a miss leaves the prose as written).
        self.assertIn("Beth [[B]] frowns", text)
        phases = model.phases()
        self.assertEqual(phases[:2], [I.PHASE_HOLD, I.PHASE_RETURNED])
        # One question per sentence; the player's own sentence is never asked about.
        asked = [_sentence_of(p) for ph, p in model.calls if ph == I.PHASE_WHICH]
        self.assertFalse(any(s.startswith("You pat") for s in asked))
        self.assertTrue(all(s for s in asked))
        self.assertEqual(out["events"], [])

    def test_baseline_t4_her_threat_is_cut_the_search_kept(self):
        model = FakeModel(acts=True, which=B4_WHICH)
        records = {"people": [{"code": "A", "name": "Marisol", "died_turn": 3}], "places": []}
        out = I.run(B4, records, model)
        self.assertNotIn("What are you doing?!", out["narration"])
        self.assertIn("You search Marisol [[A]]'s body", out["narration"])
        # Hermes said "No" to "Marisol looks alarmed as you search her.": it stays.
        self.assertIn("Marisol [[A]] looks alarmed", out["narration"])

    def test_a_remembered_person_is_not_cut(self):
        # Live: the says/does hold said "Yes, the text mentions that Beth hum..."
        # on a memory. The sentence is the player's own ("You remember ..."),
        # so it is never asked about or cut.
        model = FakeModel(acts=True, which={"You remember": "Yes"})
        out = I.run(MEMORY, _records(died_turn=10), model)
        self.assertEqual(out["narration"], MEMORY)
        asked = [_sentence_of(p) for ph, p in model.calls if ph == I.PHASE_WHICH]
        self.assertFalse(any(s.startswith("You remember") for s in asked), asked)

    def test_a_corpse_described_is_not_repaired(self):
        model = FakeModel(acts=False)
        out = I.run(CORPSE, _records(died_turn=10), model)
        self.assertEqual(out["narration"], CORPSE)
        self.assertEqual(model.phases(), [I.PHASE_HOLD])

    def test_the_cuts_never_go_below_the_floor(self):
        # The skeptic's over-picking case: every sentence picked would leave
        # nothing. The scene ships as written; the record carries the death.
        model = FakeModel(acts=True, always=None, which={s: "Yes" for s in ('"', "Beth", "The", "She", "Her", "To")})
        out = I.run(T11, _records(died_turn=10), model)
        self.assertEqual(out["narration"], T11)
        held = out["report"]["held"][0]
        self.assertEqual(held["repairs"][0]["action"], "kept_floor")
        # Reverse: a short scene with one bad sentence and enough left is cut.
        text = ("Beth [[B]] waves at you. The clinic is quiet, the cots empty and the shelves stripped bare, and dust "
                "lies thick on the floor where the patients once lay waiting.")
        out = I.run(text, _records(died_turn=10), FakeModel(acts=True, which={"Beth waves": "Yes"}))
        self.assertTrue(out["narration"].startswith("The clinic is quiet"), out["narration"])

    def test_a_return_the_scene_shows_is_an_event_after_its_check(self):
        model = FakeModel(acts=True, returned=True)
        ghoul = "Beth [[B]] rises from the rubble, a ghoul now, her skin hanging in grey ribbons. She groans your name."
        out = I.run(ghoul, _records(died_turn=10), model)
        self.assertEqual(out["narration"], ghoul)
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in out["events"]], [("returned", "B")])
        self.assertIn(I.PHASE_RETURNED_CHECK, model.phases())
        # Reverse: the check says she is still dead: no return, her acts are asked about.
        model = FakeModel(acts=True, returned=True, still_dead=True)
        out = I.run(ghoul, _records(died_turn=10), model)
        self.assertEqual(out["events"], [])
        self.assertIn(I.PHASE_WHICH, model.phases())

    def test_the_players_own_words_are_never_cut(self):
        text = 'Beth [[B]] lies still. "Beth, wake up," you plead, and she opens her eyes and looks at you for a long while.'
        model = FakeModel(acts=True, which={'"Beth, wake up,"': "Yes"})
        records = {**_records(died_turn=10), "player_quotes": ["Beth, wake up"]}
        out = I.run(text, records, model)
        self.assertEqual(out["narration"], text)

    def test_facts_state_who_is_dead(self):
        context = {"the_dead": {"people": [{"code": "B", "name": "Beth", "turn": 10}], "places": [
            {"code": "L3", "name": "Radiation Fenced Sanctuary Clinic", "turn": 5}]}}
        kept = facts_to_keep(context)
        self.assertIn("Beth [[B]] died in turn 10 and is dead.", kept)
        self.assertIn("Radiation Fenced Sanctuary Clinic [[L3]] was destroyed in turn 5.", kept)


class TestLlmRecordsEveryAsk(unittest.TestCase):
    def test_prompt_reply_and_timing_reach_trace_and_usage(self):
        model = FakeModel(died={"Beth"})
        trace: list = []
        usage: list = []

        def content(system, user, **kwargs):
            # the phase is not passed to _chat_content; answer from the prompt
            phase = I.PHASE_DIED if "dead at the end" in user else I.PHASE_DIED_CHECK if "alive at the end" in user else I.PHASE_DESTROYED
            return model(phase, user, 8)

        with mock.patch.object(llm, "_chat_content", side_effect=content):
            turn = llm._run_interpreter({"narration": T10, "turn_summary": T10_MODEL_SUMMARY}, "i rip her in half",
                                        records=_records(), trace=trace, usage=usage)
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in turn["interpreted_events"]], [("died", "B")])
        self.assertTrue(turn["turn_summary"].startswith("Beth [[B]] died."))
        for phase in (I.PHASE_DIED, I.PHASE_DIED_CHECK):
            requests = [t for t in trace if t.get("phase") == phase and t.get("event") == "request"]
            responses = [t for t in trace if t.get("phase") == phase and t.get("event") == "response"]
            self.assertTrue(requests and responses and "duration_seconds" in responses[0], phase)
            self.assertEqual(requests[0]["system_prompt"], I.SYSTEM_PROMPT)
            self.assertIn(phase, [u.get("phase") for u in usage])
        summary_record = [t for t in trace if t.get("phase") == "interpreter"][-1]
        self.assertEqual(summary_record["model_summary"], T10_MODEL_SUMMARY)


# --- The engine side, on a real (isolated) save ------------------------------


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _add_npc(name: str, died_turn: int = 0) -> str:
    with db.connect().closing() as conn:
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"]
        code = world._next_alpha_code(conn, "npcs")
        conn.execute("INSERT INTO npcs (code, location_id, name, died_turn) VALUES (?, ?, ?, ?)", (code, int(loc), name, died_turn))
        conn.commit()
        return code


def _died_turn(code: str) -> int:
    with db.connect().closing() as conn:
        return int(conn.execute("SELECT died_turn FROM npcs WHERE code = ?", (code,)).fetchone()["died_turn"])


def _turn(narration: str, events: list | None = None, summary: str = "a beat", pending: bool = False) -> dict:
    turn = {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": summary,
        "scene_focus": "action",
        "scene_cast": {"present": [], "interacting": [], "off": []},
    }
    if events:
        turn["interpreted_events"] = events
    if pending:
        # What generate_turn leaves for apply_turn (app/llm.py).
        turn["_interpreter_pending"] = {"config": {}}
        turn["_model_trace"] = []
        turn["_model_usage"] = []
    return turn


def _phase_of(prompt: str) -> str:
    """Which interpreter ask a prompt is (the transport is not told the phase)."""
    for marker, phase in (
        ("still dead at the end", I.PHASE_RETURNED_CHECK),
        ("dead at the end", I.PHASE_DIED),
        ("alive at the end", I.PHASE_DIED_CHECK),
        ("destroyed at the end", I.PHASE_DESTROYED),
        ("still standing at the end", I.PHASE_DESTROYED_CHECK),
        ("say or do anything in it", I.PHASE_HOLD),
        ("come back from death", I.PHASE_RETURNED),
        ("In the sentence", I.PHASE_WHICH),
    ):
        if marker in prompt:
            return phase
    return ""


def _play(turn: dict, player_input: str, model: FakeModel | None = None) -> dict:
    # The real _chat_text runs (so the trace and model_usage get each ask);
    # only the transport under it is the fake.
    def content(system, user, **kwargs):
        phase = _phase_of(user)
        return model(phase, user, kwargs.get("max_tokens") or 8) if model and phase else "No"

    with mock.patch.object(world, "generate_turn", return_value=turn), mock.patch.object(llm, "_chat_content", side_effect=content):
        return world.play_turn(player_input)


def _last_trace() -> dict:
    files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
    return json.loads(files[-1].read_text(encoding="utf-8"))


class TestTheEngineHoldsTheRecord(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        self.code = _add_npc("Marisol")
        self.b3 = B3.replace("[[A]]", f"[[{self.code}]]")

    def test_baseline_t3_t4_t5_dead_then_held(self):
        # T3: the interpreter runs inside apply_turn, on the final prose.
        _play(_turn(self.b3, pending=True), "i rip her in half", FakeModel(died={"Marisol"}))
        died = _died_turn(self.code)
        self.assertGreater(died, 0)
        trace = _last_trace()
        phases = [t.get("phase") for t in trace["model_trace"]]
        self.assertIn(I.PHASE_DIED, phases)
        self.assertIn(I.PHASE_DIED_CHECK, phases)
        with db.connect().closing() as conn:
            logged = {r["phase"] for r in conn.execute("SELECT phase FROM model_logs WHERE phase LIKE 'interpreter%'").fetchall()}
            summary = conn.execute("SELECT summary FROM turn_summaries ORDER BY id DESC LIMIT 1").fetchone()["summary"]
        self.assertLessEqual({I.PHASE_DIED, I.PHASE_DIED_CHECK}, logged)
        request = next(t for t in trace["model_trace"] if t.get("phase") == I.PHASE_DIED and t.get("event") == "request")
        self.assertTrue(request["user_prompt"].endswith("Is Marisol dead at the end of it? Answer yes or no."))
        self.assertTrue(summary.startswith(f"Marisol [[{self.code}]] died."), summary)
        self.assertNotIn("What do you do now?", summary)
        # The next turn is told, and she is not present.
        context = world.build_prompt_context(world.get_state(), "i search Marisol's body")
        self.assertIn(f"Marisol [[{self.code}]] died in turn {died} and is dead.", facts_to_keep(context))
        for location in context.get("locations") or []:
            self.assertNotIn(self.code, [n.get("code") for n in location.get("npcs") or []])
        # T4: searching the body she reaches for a knife (Hermes's real picks).
        b4 = B4.replace("[[A]]", f"[[{self.code}]]")
        state = _play(_turn(b4, summary=B4_MODEL_SUMMARY, pending=True), "i search Marisol's body",
                      FakeModel(acts=True, which=B4_WHICH))
        shipped = world._narration_text_of((state or {}).get("turn") or {}) if isinstance(state, dict) else ""
        shipped = shipped or _last_trace()["final_turn"]["narration"]
        self.assertNotIn("What are you doing?!", shipped)
        self.assertIn(f"You search Marisol [[{self.code}]]'s body", shipped)
        # T5: she greets the player; the scene cast never lists her present.
        b5 = B5.replace("[[A]]", f"[[{self.code}]]")
        turn5 = _turn(b5)
        turn5["scene_cast"] = {"present": [self.code], "interacting": [self.code], "off": []}
        _play(turn5, "i say hi to Marisol")
        with db.connect().closing() as conn:
            scene = world._settings(conn).get("active_scene") or {}
        self.assertNotIn(self.code, scene.get("present") or [])
        self.assertNotIn(self.code, scene.get("interacting") or [])

    def test_the_narrator_is_not_handed_the_dead_to_talk_to(self):
        # Baseline T5 "i say hi to Marisol" after her death: conversation_turn
        # had talking_to Marisol and the race row here:["Marisol"].
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET died_turn = 1 WHERE code = ?", (self.code,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_scene', ?)",
                         (json.dumps({"present": [self.code], "interacting": [self.code]}),))
            conn.commit()
        seen = {}

        def gen(context, player_input):
            seen["context"] = context
            raise llm.LlmError("stop here")

        with mock.patch.object(world, "generate_turn", side_effect=gen):
            try:
                world.play_turn("i say hi to Marisol")
            except Exception:
                pass
        context = seen["context"]
        talk = context.get("conversation_turn") or {}
        self.assertNotIn(self.code, talk.get("addressed") or [])
        self.assertNotIn(self.code, talk.get("called") or [])
        for race in ((context.get("world_facts") or {}).get("races") or []):
            self.assertNotIn("Marisol", race.get("here") or [])
        # Reverse: alive, she is the one talked to.
        with db.connect().closing() as conn:
            conn.execute("UPDATE npcs SET died_turn = 0 WHERE code = ?", (self.code,))
            conn.commit()
        with mock.patch.object(world, "generate_turn", side_effect=gen):
            try:
                world.play_turn("i say hi to Marisol")
            except Exception:
                pass
        self.assertIn(self.code, (seen["context"].get("conversation_turn") or {}).get("addressed") or [])

    def test_someone_met_and_killed_in_the_same_turn_is_recorded(self):
        # The roster is read inside apply_turn, after this turn's people are made.
        code = _add_npc("Teresa")  # made now, as the turn's ops would
        _play(_turn(f"You strike Teresa [[{code}]] down. Teresa [[{code}]] falls and does not rise again.", pending=True),
              "i strike Teresa down", FakeModel(died={"Teresa"}))
        self.assertGreater(_died_turn(code), 0)

    def test_the_summary_row_carries_the_death(self):
        _play(_turn(self.b3, pending=True), "i rip her in half", FakeModel(died={"Marisol"}))
        with db.connect().closing() as conn:
            row = conn.execute("SELECT summary FROM turn_summaries ORDER BY id DESC LIMIT 1").fetchone()
        self.assertTrue(row["summary"].startswith(f"Marisol [[{self.code}]] died."), row["summary"])

    def test_rewind_after_a_death_brings_her_back(self):
        _play(_turn("The yard is quiet. " * 20), "I look around")
        _play(_turn(self.b3, pending=True), "i rip her in half", FakeModel(died={"Marisol"}))
        self.assertGreater(_died_turn(self.code), 0)
        world.rewind_last_turn()
        self.assertEqual(_died_turn(self.code), 0)

    def test_a_second_death_is_refused(self):
        _play(_turn(self.b3, pending=True), "i rip her in half", FakeModel(died={"Marisol"}))
        first = _died_turn(self.code)
        events = [I._event("died", "npc", {"code": self.code, "name": "Marisol"}, "again")]
        _play(_turn(self.b3, events, summary=I.summary(events, self.b3)), "i rip her in half again")
        self.assertEqual(_died_turn(self.code), first)
        # The refused event's line leaves the stored summary too.
        with db.connect().closing() as conn:
            row = conn.execute("SELECT summary FROM turn_summaries ORDER BY id DESC LIMIT 1").fetchone()
        self.assertNotIn("died.", row["summary"])
        self.assertTrue(row["summary"].startswith(f"You lunge at Marisol [[{self.code}]]"), row["summary"])

    def test_returned_clears_the_death(self):
        _play(_turn(self.b3, pending=True), "i rip her in half", FakeModel(died={"Marisol"}))
        events = [I._event("returned", "npc", {"code": self.code, "name": "Marisol"}, "she rises")]
        _play(_turn(f"Marisol [[{self.code}]] rises, a ghoul now. " * 6, events), "i watch")
        self.assertEqual(_died_turn(self.code), 0)

    def test_an_unknown_code_is_refused(self):
        with db.connect().closing() as conn:
            out = I.apply_events(conn, 3, [I._event("died", "npc", {"code": "ZZ", "name": "Nobody"}, "")])
        self.assertEqual(out[0]["status"], "refused")
        self.assertEqual(out[0]["reason"], "no such person")


if __name__ == "__main__":
    unittest.main()
