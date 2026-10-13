"""Jobs paid without the work (7B Saltmarrow run 5, playtest #130).

The quest parser cited any sentence as proof a job was done and the engine
paid it: a job still owed (T5), the weather (T58), a question put in the
player's mouth (T96), a sack handed over on a Wait (T89). A job the parser paid
was paid again by the model's own GOLD and XP ops (T45), and a job finished
and paid could be offered and taken again (T90).
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-7b-run5-jobs-"))
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


HOLD = {"id": 1, "code": "Q1", "title": "Clean out the hold of a smaller craft", "status": "active",
        "current_step": 1, "total_steps": 1, "current_step_text": "Clean out the hold of the Sea Sprite"}
SIXTEEN = {"id": 2, "code": "Q2", "title": "Cover the remaining sixteen gold", "status": "active",
           "current_step": 1, "total_steps": 1, "current_step_text": "Accept the job"}
FITTINGS = {"id": 4, "code": "Q4", "title": "Retrieve brass fittings from wreck", "status": "active",
            "current_step": 1, "total_steps": 1, "current_step_text": "Take the brass fittings to the reeve's desk"}
BREAD = {"id": 5, "code": "Q5", "title": "A debt of bread", "status": "active",
         "current_step": 1, "total_steps": 1, "current_step_text": "A debt of bread"}
MEET = {"id": 8, "code": "Q8", "title": "Meet with Warin Croft", "status": "active",
        "current_step": 1, "total_steps": 1, "current_step_text": "Go to the harbour office"}


class TheQuoteMustShowTheWorkDone(unittest.TestCase):
    def test_run5_quotes_finish_nothing(self):
        from app.quest_parser import done_check

        self.assertEqual(done_check("You will have to clear out this hold, piece by piece.", HOLD),
                         ["evidence_is_owed_work"])
        self.assertEqual(done_check("The rain continues to pour, obscuring the view but not your resolve.", SIXTEEN),
                         ["evidence_not_about_this_job"])
        self.assertEqual(done_check("\"Yeah, I didn't sleep well. Any word from Warin Croft [[F]]?\"", MEET),
                         ["evidence_is_question"])
        self.assertEqual(
            done_check("Warin hands you the sack, and you feel a lightness in your hand and the promise of a meal.",
                       BREAD, passive=True),
            ["passive_turn_not_done"],
        )
        self.assertEqual(
            done_check("You keep the shiny bronze-finished piece you just pulled out of the mud.", FITTINGS, passive=True),
            ["passive_turn_not_done"],
        )

    def test_work_done_still_finishes_the_job(self):
        from app.quest_parser import done_check

        # Acting turn: a result word, or a quote about this job, is enough.
        self.assertEqual(done_check("You haul the last of the rotten nets out and the hold is bare.", HOLD), [])
        self.assertEqual(done_check("Carter pays you the forty silver.", {"title": "Escort the silk"}), [])
        # Passive turn: the result and this job both.
        self.assertEqual(
            done_check("You hand the brass fittings over at the reeve's desk and the clerk signs for them.",
                       FITTINGS, passive=True),
            [],
        )
        # A done word outweighs a modal: the job is done, the rest is talk.
        self.assertEqual(done_check("You finished the hold; Roger will pay you at noon.", HOLD), [])


class ValidationReadsTheQuote(unittest.TestCase):
    def _validate(self, update, narration, existing, *, passive=False, player_input="I walk to the cottage."):
        from app.quest_parser import validate_quest_changes

        return validate_quest_changes(
            {"new": [], "updates": [update]}, narration=narration, player_input=player_input,
            npcs=[], locations=[], existing=existing, passive=passive,
        )

    def test_t45_payment_line_does_not_finish_the_reckoner(self):
        reckoner = {"id": 3, "code": "Q3", "title": "Retrieve the tide-reckoner", "status": "active",
                    "current_step": 1, "total_steps": 1, "current_step_text": "Retrieve the tide-reckoner"}
        narration = "Roger looks up. \"Brass, you're right on time. Here, this is your payment,\" he says."
        accepted, rejected = self._validate(
            {"quest": "Q3", "action": "complete", "evidence": "Brass, you're right on time. Here, this is your payment,"},
            narration, [reckoner],
        )
        self.assertEqual(accepted["updates"], [])
        self.assertEqual(rejected[0]["reasons"], ["evidence_not_about_this_job"])

    def test_a_finished_job_cannot_be_updated_or_offered_again(self):
        from app.quest_parser import validate_quest_changes

        done = {**FITTINGS, "status": "completed", "giver_npc_id": 6}
        narration = "Warin hands you the fittings. \"Bring me brass fittings from the wreck again,\" he says."
        accepted, rejected = self._validate(
            {"quest": "Q4", "action": "complete", "evidence": "Warin hands you the fittings."}, narration, [done],
        )
        self.assertEqual(accepted["updates"], [])
        self.assertIn("unknown_quest", rejected[0]["reasons"])
        accepted, rejected = validate_quest_changes(
            {"new": [{"title": "Retrieve brass fittings from the wreck", "giver": "Warin Croft",
                      "evidence": "Bring me brass fittings from the wreck again", "_from_mark": True,
                      "steps": [{"title": "Retrieve brass fittings"}]}], "updates": []},
            narration=narration, player_input="", npcs=[{"id": 6, "code": "F", "name": "Warin Croft"}],
            locations=[], existing=[done],
        )
        self.assertEqual(accepted["new"], [])
        self.assertTrue(any(r.startswith("completed_before:") for r in rejected[0]["reasons"]), rejected)


class PassiveTurns(unittest.TestCase):
    def test_which_turns_are_passive(self):
        from app.world import _quest_passive_turn

        self.assertTrue(_quest_passive_turn("wait", "__wait_request__: kind=wait minutes=30"))
        self.assertTrue(_quest_passive_turn("player", "What time is it, and is the tide in or out?"))
        self.assertTrue(_quest_passive_turn("player", "I look around the yard."))
        self.assertFalse(_quest_passive_turn("player", "I hand the brass fittings to the reeve."))
        self.assertFalse(_quest_passive_turn("player", "I climb down into the hold and start hauling out the nets."))


def _world_with_active_job(reward_gold: int = 15, reward_xp: int = 25) -> tuple[str, int, int]:
    from app import db, world
    from app.quests import create_quest

    db.init_db()
    world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
    with db.connect() as conn:
        quest_id = create_quest(
            conn, title="Retrieve the tide-reckoner", description="Fetch it from the cottage.",
            steps=[{"title": "Retrieve the tide-reckoner", "description": "Bring the tide-reckoner back to Roger"}],
            reward_gold=reward_gold, reward_xp=reward_xp, status="active", created_turn=1,
        )
        row = conn.execute("SELECT gold, xp FROM player WHERE id = 1").fetchone()
        return f"Q{quest_id}", int(row["gold"]), int(row["xp"])


def _turn(narration: str, **extra) -> dict:
    return {
        "scene_plan": {"goal": "deliver", "focus_points": []},
        "narration_segments": [{"label": "scene", "text": narration}],
        "narration": narration,
        "player": {},
        "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
        "turn_summary": "a beat",
        "scene_focus": "dialogue",
        **extra,
    }


class OneJobOnePayout(unittest.TestCase):
    def test_parser_payout_drops_the_models_own_reward(self):
        from app import db, world

        code, gold0, xp0 = _world_with_active_job()
        narration = ("You bring the tide-reckoner back to Roger and hand it over. He turns it in his hands, "
                     "nods, and counts fifteen gold into your palm.")
        world.apply_turn(
            _turn(narration, player={"gold_delta": 35, "xp_delta": 11},
                  quest_changes={"new": [], "updates": [
                      {"quest": code, "action": "complete", "evidence": "You bring the tide-reckoner back to Roger and hand it over."}
                  ], "source": "parser"}),
            "I give Roger the tide-reckoner.",
        )
        with db.connect() as conn:
            row = conn.execute("SELECT gold, xp FROM player WHERE id = 1").fetchone()
            status = conn.execute("SELECT status FROM quests WHERE code = ?", (code,)).fetchone()["status"]
        self.assertEqual(status, "completed")
        self.assertEqual(int(row["gold"]) - gold0, 15)
        self.assertEqual(int(row["xp"]) - xp0, 25)

    def test_wait_turn_does_not_pay_on_a_gift(self):
        from app import db, world

        code, gold0, _xp0 = _world_with_active_job()
        narration = "Warin hands you a sack of bread. \"That settles it,\" he says, and goes back to his nets."
        state = world.apply_turn(
            _turn(narration, quest_changes={"new": [], "updates": [
                {"quest": code, "action": "complete", "evidence": "Warin hands you a sack of bread."}
            ], "source": "parser"}),
            "__wait_request__: kind=wait minutes=30",
            input_kind="wait",
        )
        with db.connect() as conn:
            status = conn.execute("SELECT status FROM quests WHERE code = ?", (code,)).fetchone()["status"]
            gold = int(conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()["gold"])
        self.assertEqual(status, "active")
        self.assertEqual(gold, gold0)
        self.assertIn("passive_turn_not_done", state["quest_report"]["rejected"][0]["reasons"])

    def test_model_quest_journal_is_kept_as_a_fact(self):
        from app import db, world

        _world_with_active_job()
        world.apply_turn(
            _turn("The yard is quiet.", journal=[{"kind": "quest", "content": "Retrieve the missing tide-reckoner."}]),
            "I look around the yard.",
        )
        with db.connect() as conn:
            rows = conn.execute("SELECT kind FROM journal WHERE content = 'Retrieve the missing tide-reckoner.'").fetchall()
        self.assertEqual([r["kind"] for r in rows], ["fact"])


if __name__ == "__main__":
    unittest.main()
