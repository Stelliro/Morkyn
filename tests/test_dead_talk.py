"""Talk to someone recorded dead: the engine answers it before the prose (#164).

Live replay on the merged code (Hermes 3 8B, scratchpad live/integ-r3, T5):
'i say hi to Dr. Theo' a turn after his death (npcs B died_turn 4). The engine
rolled persuasion against the dead man ("You succeed cleanly", attitude
neutral) and told the narrator nothing about what that greeting comes to; the
8B moved the player to a guildhall in the fog with a stranger and a menu of
options. Now the engine, from its records and its own reading of the line as
talk, plus one small ask ("Is the player talking to Dr. Theo?"), hands the
draft the outcome through act_outcome: he is dead and does not answer. No
social roll is made against the dead.

The reverse stays free: "i search Beth's body" (tester's game cc87dd29, T11)
is no talk, and a living person greeted is untouched. The model is mocked:
a yes-biased and a no-biased one.

Run:  cd tests && python -m unittest test_dead_talk
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-dead-talk-test-"))
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
from app.turn_dsl import build_dsl_user_prompt  # noqa: E402

I = interpreter

# The records of integ-r3 at T5 (data/world.db): A is a label-leak row, B and C died in turn 4.
INTEG_R3_PEOPLE = [
    {"code": "A", "name": "NAME Theo ROLE", "died_turn": 0},
    {"code": "B", "name": "Dr. Theo", "died_turn": 4},
    {"code": "C", "name": "Theo", "died_turn": 4},
]
INTEG_R3_T5 = "i say hi to Dr. Theo"
# cc87dd29: B is Beth (dead from T10 on), C the "NAME: Beth" duplicate row.
CC_T11 = "i search Beth's body"
CC_T14 = "i say hi to @Cbeth"
CC_T14_EXPANDED = "i say hi to Beth [[B]]"

TALK_MARK = "Is the player talking to"


def yes_model(phase, prompt, max_tokens):
    return "Yes, the player is talking to them."


def no_model(phase, prompt, max_tokens):
    return "No."


class TestTheAsk(unittest.TestCase):
    def records(self, people=None):
        return {"people": people or INTEG_R3_PEOPLE, "places": [], "player_names": ["Will Tanaka"]}

    def test_integ_r3_t5_the_dead_doctor_is_the_one_named(self):
        report = {"asks": []}
        row = I.dead_talked_to(INTEG_R3_T5, self.records(), yes_model, report)
        self.assertEqual(row["code"], "B")
        # One ask, about the one name the line gives in full ("Theo" inside "Dr. Theo" is his).
        self.assertEqual(len(report["asks"]), 1)
        self.assertEqual(report["asks"][0]["phase"], I.PHASE_TALKED_TO)

    def test_the_ask_is_one_positive_question_about_one_name(self):
        seen = []

        def model(phase, prompt, max_tokens):
            seen.append((phase, prompt, max_tokens))
            return "Yes"

        I.dead_talked_to(CC_T14_EXPANDED, self.records([{"code": "B", "name": "Beth", "died_turn": 10}]), model)
        self.assertEqual(seen, [(I.PHASE_TALKED_TO,
                                 "Read this.\n\nThe player: i say hi to Beth\n\nIs the player talking to Beth? Answer yes or no.",
                                 4)])

    def test_a_no_biased_model_answers_nothing(self):
        self.assertIsNone(I.dead_talked_to(INTEG_R3_T5, self.records(), no_model))

    def test_an_unreadable_or_failed_reply_answers_nothing(self):
        self.assertIsNone(I.dead_talked_to(INTEG_R3_T5, self.records(), lambda *a: "Hmm"))

        def down(*_a):
            raise RuntimeError("model down")

        self.assertIsNone(I.dead_talked_to(INTEG_R3_T5, self.records(), down))

    def test_the_living_are_never_asked_about(self):
        asked = []
        people = [{"code": "B", "name": "Marisol", "died_turn": 0}]
        self.assertIsNone(I.dead_talked_to("i say hi to Marisol", self.records(people),
                                           lambda *a: asked.append(a) or "Yes"))
        self.assertEqual(asked, [])

    def test_a_name_a_living_row_shares_names_nobody_but_the_code_does(self):
        # cc87dd29: B "Beth" dead, C "NAME: Beth" living (clean_name -> "Beth").
        people = [{"code": "B", "name": "Beth", "died_turn": 10}, {"code": "C", "name": I.clean_name("NAME: Beth"), "died_turn": 0}]
        self.assertIsNone(I.dead_talked_to("i say hi to Beth", self.records(people), yes_model))
        self.assertEqual(I.dead_talked_to(CC_T14_EXPANDED, self.records(people), yes_model)["code"], "B")

    def test_the_outcome_is_the_act_outcome_shape(self):
        row = INTEG_R3_PEOPLE[1]
        here = I.dead_talk_outcome(row, INTEG_R3_T5, here=True)
        self.assertEqual(here["means"], "Dr. Theo [[B]] is dead; the body lies where it fell. Dr. Theo does not answer.")
        self.assertEqual(here["act"], INTEG_R3_T5)
        self.assertEqual(here["outcome"], "no answer")
        away = I.dead_talk_outcome({"code": "B", "name": "Beth"}, CC_T14_EXPANDED)
        self.assertEqual(away["means"], "Beth [[B]] is dead and does not answer.")


# --- The engine side, on a real (isolated) save ------------------------------


def _fresh_world(dice: bool = False):
    os.environ.update(_ENV)
    assert str(db.db_path()).startswith(str(_TMP)), db.db_path()
    db.init_db()
    options = {"player_name": "Will", "start_location": "Low Gate", "special_ability_origin": "none"}
    if dice:
        # Off in the shipped defaults; the tester's and the replay's games had them on.
        options["dice_checks_enabled"] = True
    world.start_playthrough(options)


def _add_npc(name: str, died_turn: int = 0, elsewhere: bool = False) -> str:
    with db.connect().closing() as conn:
        loc = int(conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()["current_location_id"])
        if elsewhere:
            other = conn.execute("SELECT id FROM locations WHERE id != ? ORDER BY id LIMIT 1", (loc,)).fetchone()
            if other is None:
                conn.execute("INSERT INTO locations (code, name, summary) VALUES ('L9', 'Far Clinic', 'a clinic')")
                other = conn.execute("SELECT id FROM locations WHERE code = 'L9'").fetchone()
            loc = int(other["id"])
        code = world._next_alpha_code(conn, "npcs")
        conn.execute("INSERT INTO npcs (code, location_id, name, died_turn) VALUES (?, ?, ?, ?)", (code, loc, name, died_turn))
        conn.commit()
        return code


def _attitude(code: str) -> str:
    with db.connect().closing() as conn:
        return str(conn.execute("SELECT attitude FROM npcs WHERE code = ?", (code,)).fetchone()["attitude"] or "")


def _content(model):
    """The transport under _chat_text / _chat_json: only the talk ask goes to ``model``."""

    def content(system, user, **kwargs):
        if TALK_MARK in str(user):
            return model("", user, kwargs.get("max_tokens") or 4)
        return "No"

    return content


def _capture(player_input: str, model) -> dict:
    """play_turn up to the draft: the context the narrator is handed."""
    seen: dict = {}

    def gen(context, model_input):
        seen["context"] = context
        seen["model_input"] = model_input
        raise llm.LlmError("stop here")

    with mock.patch.object(world, "generate_turn", side_effect=gen), \
            mock.patch.object(llm, "_chat_content", side_effect=_content(model)):
        try:
            world.play_turn(player_input)
        except Exception:
            pass
    return seen


def _turn(narration: str) -> dict:
    return {
        "scene_plan": {"goal": "look", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "action",
        "scene_cast": {"present": [], "interacting": [], "off": []},
    }


def _social_rolls(context: dict) -> list:
    mech = context.get("mechanics_context") or {}
    return [c for c in mech.get("resolved_checks") or [] if c.get("social_attitude")]


class TestTheEngineAnswersTalkToTheDead(unittest.TestCase):
    """With dice on, as in the tester's game and the replay."""

    DICE = True

    def setUp(self):
        _fresh_world(dice=self.DICE)

    def test_integ_r3_t5_say_hi_to_the_dead_doctor(self):
        theo = _add_npc("Dr. Theo", died_turn=4)
        before = _attitude(theo)
        seen = _capture(INTEG_R3_T5, yes_model)
        context = seen["context"]
        outcome = (context.get("mechanics_context") or {}).get("act_outcome") or {}
        self.assertEqual(outcome.get("means"), f"Dr. Theo [[{theo}]] is dead; the body lies where it fell. Dr. Theo does not answer.")
        self.assertEqual(outcome.get("act"), INTEG_R3_T5)
        self.assertNotIn("dead", outcome)
        # No persuasion roll against a dead man, and nothing written to his row.
        self.assertEqual(_social_rolls(context), [])
        self.assertEqual(_attitude(theo), before)
        # The draft reads it in the slot it already reads check outcomes from.
        packet = json.loads(build_dsl_user_prompt(context, seen["model_input"]))
        self.assertEqual(packet["act_outcome"]["means"], outcome["means"])

    def test_cc87dd29_t14_say_hi_to_beth_by_reference_while_elsewhere(self):
        beth = _add_npc("Beth", died_turn=10, elsewhere=True)
        seen = _capture(CC_T14, yes_model)
        self.assertIn(f"Beth [[{beth}]]", seen["model_input"])
        outcome = (seen["context"].get("mechanics_context") or {}).get("act_outcome") or {}
        self.assertEqual(outcome.get("means"), f"Beth [[{beth}]] is dead and does not answer.")
        self.assertEqual(_social_rolls(seen["context"]), [])

    def test_cc87dd29_t11_searching_the_body_stays_free_even_with_a_yes_biased_model(self):
        beth = _add_npc("Beth", died_turn=10)
        before = _attitude(beth)
        asked = []

        def model(phase, prompt, max_tokens):
            asked.append(prompt)
            return "Yes"

        seen = _capture(CC_T11, model)
        outcome = (seen["context"].get("mechanics_context") or {}).get("act_outcome") or {}
        self.assertNotIn("does not answer", str(outcome.get("means") or ""))
        # The engine's own reading of the line is no talk: the model is not even asked.
        self.assertEqual(asked, [])
        self.assertEqual(_attitude(beth), before)

    def test_a_no_biased_model_leaves_the_outcome_open_but_rolls_nothing_against_the_dead(self):
        theo = _add_npc("Dr. Theo", died_turn=4)
        before = _attitude(theo)
        seen = _capture(INTEG_R3_T5, no_model)
        outcome = (seen["context"].get("mechanics_context") or {}).get("act_outcome") or {}
        self.assertNotIn("does not answer", str(outcome.get("means") or ""))
        for check in (seen["context"].get("mechanics_context") or {}).get("resolved_checks") or []:
            self.assertNotEqual((check.get("opposition") or {}).get("name"), "Dr. Theo")
        self.assertEqual(_attitude(theo), before)

    def test_a_living_target_is_unchanged(self):
        marisol = _add_npc("Marisol")
        asked = []

        def model(phase, prompt, max_tokens):
            asked.append(prompt)
            return "Yes"

        seen = _capture("i say hi to Marisol", model)
        context = seen["context"]
        outcome = (context.get("mechanics_context") or {}).get("act_outcome") or {}
        self.assertNotIn("does not answer", str(outcome.get("means") or ""))
        self.assertEqual(asked, [])
        self.assertIn(marisol, (context.get("conversation_turn") or {}).get("addressed") or [])
        if self.DICE:
            rolls = _social_rolls(context)
            self.assertTrue(rolls, "the greeting to a living person still rolls")
            self.assertEqual((rolls[0].get("opposition") or {}).get("name"), "Marisol")

    def test_the_ask_reaches_the_turn_trace_and_model_usage(self):
        _add_npc("Dr. Theo", died_turn=4)
        narration = "You stand over the doctor's body in the quiet clinic. He does not answer. " * 4
        with mock.patch.object(world, "generate_turn", return_value=_turn(narration)), \
                mock.patch.object(llm, "_chat_content", side_effect=_content(yes_model)):
            world.play_turn(INTEG_R3_T5)
        files = sorted((_TMP / "traces").glob("turn-*.json"), key=lambda p: p.stat().st_mtime)
        trace = json.loads(files[-1].read_text(encoding="utf-8"))
        request = next(t for t in trace["model_trace"] if t.get("phase") == I.PHASE_TALKED_TO and t.get("event") == "request")
        self.assertTrue(request["user_prompt"].endswith("Is the player talking to Dr. Theo? Answer yes or no."))
        self.assertTrue(any(t.get("phase") == I.PHASE_TALKED_TO and t.get("event") != "request" for t in trace["model_trace"]))
        self.assertIn(I.PHASE_TALKED_TO, [u.get("phase") for u in trace["model_usage"]])
        notes = [n for n in trace["engine"]["ledger"]["notes"] if n.get("decision") == "dead_talked_to"]
        self.assertTrue(notes and notes[0]["asks"][0]["seconds"] >= 0, notes)
        with db.connect().closing() as conn:
            logged = {r["phase"] for r in conn.execute("SELECT phase FROM model_logs").fetchall()}
        self.assertIn(I.PHASE_TALKED_TO, logged)


class TestTheEngineAnswersTalkToTheDeadDiceOff(TestTheEngineAnswersTalkToTheDead):
    """The shipped default: no dice. The engine still reads the line as talk and answers it."""

    DICE = False


if __name__ == "__main__":
    unittest.main()
