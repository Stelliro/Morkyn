"""The interpreter: a death or a destruction the final prose shows is an event the engine records (#154, #157).

The strings are the tester's Hermes 3 8B game (campaign cc87dd29, T10-T13) and
the baseline replay before the fix (live/baseline, traces 4-6 = harness T3-T5).
The model is mocked: each fake ask answers the one question it is given.

Run:  cd tests && python -m unittest test_interpreter_deaths
"""
from __future__ import annotations

import os
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

# --- cc87dd29 T5: the clinic burned (one paragraph of the real scene) -------
T5 = (
    "You bellow a chilling war cry as you storm into the Radiation Fenced Sanctuary Clinic [[L3]], a grim look of fury "
    "etched upon your armored visor. Smoke billows from the ruins of the Radiation Fenced Sanctuary Clinic [[L3]], now "
    "reduced to smoldering rubble. Beth [[B]] lies crumpled on the scorched floor, her neck twisted at an unnatural "
    "angle. The acrid smell of charred wood and scorched metal fills the night."
)

# --- baseline replay (harness T3 = trace 4, T4 = trace 5, T5 = trace 6) -----
B3 = (
    "You lunge at Marisol [[A]], grabbing her arms with one hand and her legs with the other. With a brutal motion, you "
    "rip her in two. Marisol [[A]]'s body separates at the waist, her upper and lower halves falling to the floor in a "
    "spray of blood. The other volunteers scream and scramble away from the carnage.\n\n"
    "Marisol [[A]]'s death is instantaneous. She had no chance to fight back or even cry out.\n\n"
    "As the dust settles, you stand over Marisol [[A]]'s remains, panting heavily. Her blood is pooled on the floor, and "
    "her eyes seem to still be staring at you in disbelief. You feel no remorse for what you've done."
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
B5 = (
    "The clinic is bustling with activity as search-and-rescue volunteer Marisol [[A]] eyes you up and down.\n\n"
    "\"What's your name?\"\n\n"
    "You introduce yourself to Marisol [[A]], explaining that you're in need of medical attention."
)

CORPSE = (
    "You kneel beside Beth [[B]], her eyes still open. Beth [[B]] lies where she fell, motionless. "
    "The clinic is cold and quiet around you."
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
        ],
        "player_names": ["Ash"],
    }


class FakeModel:
    """Answers each ask by its phase; ``alive`` picks the sentences a reader would call Beth alive."""

    def __init__(self, *, died=(), destroyed=(), alive=False, returned=False, alive_words=(), rewrite=None, still_alive=False):
        self.died = set(died)
        self.destroyed = set(destroyed)
        self.alive = alive
        self.returned = returned
        self.alive_words = alive_words
        self.rewrite = rewrite
        self.still_alive = still_alive
        self.calls: list[tuple[str, str]] = []

    def __call__(self, phase: str, prompt: str, max_tokens: int) -> str:
        self.calls.append((phase, prompt))
        if phase == interpreter.PHASE_DIED:
            return "Yes" if any(f"Is {n} dead" in prompt for n in self.died) else "No"
        if phase == interpreter.PHASE_DESTROYED:
            return "yes." if any(f"Is {n} destroyed" in prompt for n in self.destroyed) else "no"
        if phase == interpreter.PHASE_HOLD:
            if not self._is_recheck():
                return "Yes" if self.alive else "No"
            return "Yes" if self.still_alive else "No"
        if phase == interpreter.PHASE_RETURNED:
            return "Yes" if self.returned else "No"
        if phase == interpreter.PHASE_WHICH:
            lines = [line for line in prompt.splitlines() if line[:1].isdigit()]
            picked = [line.split(".", 1)[0] for line in lines if any(w in line for w in self.alive_words)]
            return ", ".join(picked) if picked else "none"
        if phase == interpreter.PHASE_REWRITE:
            return self.rewrite if self.rewrite is not None else ""
        return ""

    def _is_recheck(self) -> bool:
        return any(p == interpreter.PHASE_REWRITE for p, _ in self.calls)


class TestCandidatesComeFromTheRecords(unittest.TestCase):
    def test_codes_and_unique_roster_names(self):
        rows = _records()["people"]
        self.assertEqual([r["code"] for r in interpreter.named(T10, rows)], ["B"])
        self.assertEqual([r["code"] for r in interpreter.named("I search Beth's body.", rows)], ["B"])

    def test_a_name_two_rows_share_resolves_to_nothing_but_the_code_still_counts(self):
        rows = [
            {"code": "B", "name": "Beth", "died_turn": 0},
            {"code": "C", "name": interpreter.clean_name("NAME: Beth"), "died_turn": 0},
        ]
        self.assertEqual(interpreter.named("Beth waves.", rows), [])
        self.assertEqual([r["code"] for r in interpreter.named("Beth [[C]] waves.", rows)], ["C"])

    def test_no_words_decide_only_the_records(self):
        # A death described of nobody on the roster asks nothing.
        model = FakeModel(died={"Beth"})
        out = interpreter.run("The raider falls dead in the dust.", _records(), model)
        self.assertEqual(out["events"], [])
        self.assertEqual(model.calls, [])

    def test_the_ask_reads_the_passage_without_codes(self):
        passage = interpreter.passage_for(T10, {"code": "B", "name": "Beth"})
        self.assertNotIn("[[", passage)
        self.assertIn("Beth's wide, dead eyes", passage)


class TestDeathIsAnEvent(unittest.TestCase):
    def test_cc87dd29_t10_records_beth_dead(self):
        model = FakeModel(died={"Beth"})
        out = interpreter.run(T10, _records(), model)
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in out["events"]], [("died", "B")])
        phase, prompt = model.calls[0]
        self.assertEqual(phase, interpreter.PHASE_DIED)
        self.assertTrue(prompt.endswith("Is Beth dead at the end of it? Answer yes or no."))
        self.assertEqual(out["narration"], T10)

    def test_a_no_records_nothing(self):
        out = interpreter.run(T10, _records(), FakeModel())
        self.assertEqual(out["events"], [])

    def test_an_unreadable_reply_records_nothing(self):
        out = interpreter.run(T10, _records(), lambda phase, prompt, n: "Beth's fate is unclear")
        self.assertEqual(out["events"], [])

    def test_a_failed_ask_never_breaks_the_turn(self):
        def down(phase, prompt, n):
            raise TimeoutError("model down")

        out = interpreter.run(T10, _records(), down)
        self.assertEqual(out["events"], [])
        self.assertEqual(out["narration"], T10)
        self.assertIn("error", out["report"]["asks"][0])

    def test_cc87dd29_t5_the_clinic_destroyed(self):
        model = FakeModel(died={"Beth"}, destroyed={"Radiation Fenced Sanctuary Clinic"})
        out = interpreter.run(T5, _records(), model)
        kinds = sorted((e["kind"], e["subject"]["code"]) for e in out["events"])
        self.assertEqual(kinds, [("destroyed", "L3"), ("died", "B")])

    def test_summary_carries_the_event_first_then_a_line_of_prose(self):
        model = FakeModel(died={"Beth"})
        out = interpreter.run(T10, _records(), model)
        line = interpreter.summary(out["events"], out["narration"])
        self.assertTrue(line.startswith("Beth [[B]] died. You lunge towards Beth [[B]]"), line)
        self.assertIn("You stand over her corpse", line)


class TestTheSummaryFollowsTheProse(unittest.TestCase):
    def test_cc87dd29_t13_prose_alive_summary_dead(self):
        turn = {"narration": T13, "turn_summary": T13_MODEL_SUMMARY}
        model = FakeModel()  # Beth is not dead at the end of T13's prose
        with mock.patch.object(llm, "_chat_text", side_effect=lambda s, p, **k: model(k["phase"], p, k["max_tokens"])):
            result = llm._run_interpreter(dict(turn), "i rip her head from her shoulders", records=_records(), trace=[], usage=[])
        self.assertNotIn("interpreted_events", result)
        self.assertNotIn("killed", result["turn_summary"])
        self.assertTrue(result["turn_summary"].startswith("You approach Dr. Beth [[B]] cautiously"))

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
    def test_cc87dd29_t11_searching_the_body_she_speaks(self):
        model = FakeModel(
            alive=True,
            alive_words=("frowns", "steps out", "regards you", "State your business here"),
            rewrite="Beth [[B]]'s still face gives no answer to your search.",
        )
        out = interpreter.run(T11, _records(died_turn=10), model)
        text = out["narration"]
        self.assertIn("You pat Beth [[B]] down carefully", text)
        self.assertNotIn("Beth [[B]] frowns", text)
        self.assertNotIn("steps out from the clinic", text)
        self.assertIn("Beth [[B]]'s still face gives no answer to your search.", text)
        phases = [p for p, _ in model.calls]
        self.assertEqual(phases[:3], [interpreter.PHASE_HOLD, interpreter.PHASE_RETURNED, interpreter.PHASE_WHICH])
        hold_prompt = model.calls[0][1]
        self.assertTrue(hold_prompt.startswith("Beth died in turn 10. Read this."))
        self.assertTrue(hold_prompt.endswith("does Beth speak, move or act as a living person? Answer yes or no."))
        # She is already dead: nobody asks whether she died again.
        self.assertNotIn(interpreter.PHASE_DIED, phases)
        self.assertEqual(out["events"], [])

    def test_a_quote_over_several_sentences_is_one_unit(self):
        found = [u[2] for u in interpreter.units(T11)]
        self.assertTrue(any(u.startswith('Beth [[B]] frowns') for u in found) or any(
            u.startswith('"You\'re looking for something?') and u.endswith('or leave."') for u in found
        ), found)
        self.assertIn('"You\'re looking for something? I don\'t have anything to give or sell. Now state your business, or leave."', found)

    def test_a_rewrite_that_fails_is_cut(self):
        model = FakeModel(alive=True, alive_words=("frowns",), rewrite="")
        out = interpreter.run(T11, _records(died_turn=10), model)
        self.assertNotIn("frowns", out["narration"])
        self.assertIn("You pat Beth [[B]] down carefully", out["narration"])

    def test_a_rewrite_that_still_shows_her_alive_is_cut(self):
        model = FakeModel(alive=True, alive_words=("frowns",), rewrite="Beth [[B]] frowns again.", still_alive=True)
        out = interpreter.run(T11, _records(died_turn=10), model)
        self.assertNotIn("frowns", out["narration"])

    def test_a_corpse_described_is_not_repaired(self):
        model = FakeModel(alive=False)
        out = interpreter.run(CORPSE, _records(died_turn=10), model)
        self.assertEqual(out["narration"], CORPSE)
        self.assertEqual([p for p, _ in model.calls], [interpreter.PHASE_HOLD])

    def test_cc87dd29_t13_after_her_death_her_threat_is_rewritten(self):
        model = FakeModel(alive=True, alive_words=("snarls", "leans back"), rewrite="Dr. Beth [[B]] is gone; only her empty chair remains.")
        out = interpreter.run(T13, _records(died_turn=10), model)
        self.assertNotIn("snarls", out["narration"])

    def test_a_return_the_scene_shows_is_an_event_not_a_repair(self):
        model = FakeModel(alive=True, returned=True)
        ghoul = "Beth [[B]] rises from the rubble, a ghoul now, her skin hanging in grey ribbons. She groans your name."
        out = interpreter.run(ghoul, _records(died_turn=10), model)
        self.assertEqual(out["narration"], ghoul)
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in out["events"]], [("returned", "B")])

    def test_the_players_own_words_are_never_rewritten(self):
        text = 'Beth [[B]] lies still. You say "Beth, wake up" and she opens her eyes.'
        model = FakeModel(alive=True, alive_words=("wake up",), rewrite="x")
        records = {**_records(died_turn=10), "player_quotes": ["Beth, wake up"]}
        out = interpreter.run(text, records, model)
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
            phase = interpreter.PHASE_DIED if "dead at the end" in user else interpreter.PHASE_DESTROYED
            return model(phase, user, 8)

        with mock.patch.object(llm, "_chat_content", side_effect=content):
            turn = llm._run_interpreter({"narration": T10, "turn_summary": T10_MODEL_SUMMARY}, "i rip her in half",
                                        records=_records(), trace=trace, usage=usage)
        self.assertEqual([(e["kind"], e["subject"]["code"]) for e in turn["interpreted_events"]], [("died", "B")])
        self.assertTrue(turn["turn_summary"].startswith("Beth [[B]] died."))
        requests = [t for t in trace if t.get("phase") == interpreter.PHASE_DIED and t.get("event") == "request"]
        responses = [t for t in trace if t.get("phase") == interpreter.PHASE_DIED and t.get("event") == "response"]
        self.assertTrue(requests and "Is Beth dead at the end of it?" in requests[0]["user_prompt"])
        self.assertEqual(requests[0]["system_prompt"], interpreter.SYSTEM_PROMPT)
        self.assertTrue(responses and responses[0]["raw_content"] == "Yes" and "duration_seconds" in responses[0])
        self.assertIn(interpreter.PHASE_DIED, [u.get("phase") for u in usage])
        summary_record = [t for t in trace if t.get("phase") == "interpreter"][-1]
        self.assertEqual(summary_record["model_summary"], T10_MODEL_SUMMARY)


# --- The engine side, on a real (isolated) save ------------------------------


def _fresh_world():
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    world.start_playthrough({"player_name": "Ash", "start_location": "Low Gate", "special_ability_origin": "none"})


def _add_npc(name: str) -> str:
    with db.connect() as conn:
        loc = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"]
        code = world._next_alpha_code(conn, "npcs")
        conn.execute("INSERT INTO npcs (code, location_id, name) VALUES (?, ?, ?)", (code, int(loc), name))
        return code


def _died_turn(code: str) -> int:
    with db.connect() as conn:
        return int(conn.execute("SELECT died_turn FROM npcs WHERE code = ?", (code,)).fetchone()["died_turn"])


def _turn(narration: str, events: list | None = None, summary: str = "a beat") -> dict:
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
    return turn


def _play(turn: dict, player_input: str) -> dict:
    with mock.patch.object(world, "generate_turn", return_value=turn):
        return world.play_turn(player_input)


class TestTheEngineHoldsTheRecord(unittest.TestCase):
    def setUp(self):
        _fresh_world()
        self.code = _add_npc("Marisol")
        self.b3 = B3.replace("[[A]]", f"[[{self.code}]]")

    def _death_events(self, text: str) -> list:
        records = {"people": [{"code": self.code, "name": "Marisol", "died_turn": _died_turn(self.code)}], "places": []}
        return interpreter.run(text, records, FakeModel(died={"Marisol"}))["events"]

    def test_baseline_t3_t4_t5_dead_then_held(self):
        _play(_turn(self.b3, self._death_events(self.b3)), "i rip her in half")
        died = _died_turn(self.code)
        self.assertGreater(died, 0)
        # The next turn is told, and she is not present.
        context = world.build_prompt_context(world.get_state(), "i search Marisol's body")
        self.assertIn(f"Marisol [[{self.code}]] died in turn {died} and is dead.", facts_to_keep(context))
        for location in context.get("locations") or []:
            self.assertNotIn(self.code, [n.get("code") for n in location.get("npcs") or []])
        # T4: searching the body she reaches for a knife: the hold reads her row from the save.
        b4 = B4.replace("[[A]]", f"[[{self.code}]]")
        model = FakeModel(alive=True, alive_words=("looks alarmed", "What are you doing"),
                          rewrite=f"Marisol [[{self.code}]] lies still as you search her.")

        def chat_text(system, prompt, **kwargs):
            return model(kwargs["phase"], prompt, kwargs.get("max_tokens") or 8)

        with mock.patch.object(llm, "_chat_text", side_effect=chat_text):
            held = llm._run_interpreter({"narration": b4, "turn_summary": B4_MODEL_SUMMARY}, "i search Marisol's body",
                                        trace=[], usage=[])
        self.assertNotIn("reaching for the knife", held["narration"])
        self.assertIn(f"You search Marisol [[{self.code}]]'s body", held["narration"])
        self.assertNotIn("apologize", held["turn_summary"])
        # T5: she greets the player; the scene cast never lists her present.
        b5 = B5.replace("[[A]]", f"[[{self.code}]]")
        turn5 = _turn(b5)
        turn5["scene_cast"] = {"present": [self.code], "interacting": [self.code], "off": []}
        _play(turn5, "i say hi to Marisol")
        with db.connect() as conn:
            scene = world._settings(conn).get("active_scene") or {}
        self.assertNotIn(self.code, scene.get("present") or [])
        self.assertNotIn(self.code, scene.get("interacting") or [])

    def test_the_summary_row_carries_the_death(self):
        events = self._death_events(self.b3)
        turn = _turn(self.b3, events, summary=interpreter.summary(events, self.b3))
        _play(turn, "i rip her in half")
        with db.connect() as conn:
            row = conn.execute("SELECT summary FROM turn_summaries ORDER BY id DESC LIMIT 1").fetchone()
        self.assertTrue(row["summary"].startswith(f"Marisol [[{self.code}]] died."), row["summary"])

    def test_rewind_after_a_death_brings_her_back(self):
        _play(_turn("The yard is quiet. " * 20), "I look around")
        _play(_turn(self.b3, self._death_events(self.b3)), "i rip her in half")
        self.assertGreater(_died_turn(self.code), 0)
        world.rewind_last_turn()
        self.assertEqual(_died_turn(self.code), 0)

    def test_a_second_death_is_refused(self):
        _play(_turn(self.b3, self._death_events(self.b3)), "i rip her in half")
        first = _died_turn(self.code)
        events = [interpreter._event("died", "npc", {"code": self.code, "name": "Marisol"}, "again")]
        _play(_turn(self.b3, events, summary=interpreter.summary(events, self.b3)), "i rip her in half again")
        self.assertEqual(_died_turn(self.code), first)
        # The refused event's line leaves the stored summary too.
        with db.connect() as conn:
            row = conn.execute("SELECT summary FROM turn_summaries ORDER BY id DESC LIMIT 1").fetchone()
        self.assertNotIn("died.", row["summary"])
        self.assertTrue(row["summary"].startswith(f"You lunge at Marisol [[{self.code}]]"), row["summary"])

    def test_returned_clears_the_death(self):
        _play(_turn(self.b3, self._death_events(self.b3)), "i rip her in half")
        events = [interpreter._event("returned", "npc", {"code": self.code, "name": "Marisol"}, "she rises")]
        _play(_turn(f"Marisol [[{self.code}]] rises, a ghoul now. " * 6, events), "i watch")
        self.assertEqual(_died_turn(self.code), 0)

    def test_an_unknown_code_is_refused(self):
        with db.connect() as conn:
            out = interpreter.apply_events(conn, 3, [interpreter._event("died", "npc", {"code": "ZZ", "name": "Nobody"}, "")])
        self.assertEqual(out[0]["status"], "refused")
        self.assertEqual(out[0]["reason"], "no such person")


if __name__ == "__main__":
    unittest.main()
