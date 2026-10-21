"""Acts are read from grammar, not verbs; the day's energy is replayed from runs.

Fault log 2026-10-18: F153 (speech and plans costed as work), F171 (a plan
told to someone became a walk), F179 ("fix it in my memory" rolled craft and
cost energy), F153 cont. (an ordinary day of errands ran the pool to zero).
One clause reader (app/act_clauses.py) decides which parts of the player's
line are done now; the dice, the energy, the clock and the move reader all
use it. tools/energy_replay.py replays a run's turns through the engine's
own apply_action_spend.

Run:  .venv\\Scripts\\python -m unittest tests.test_acts_read_from_grammar
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-acts-grammar-"))
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


def _now(line: str, **kw) -> str:
    from app.act_clauses import acts_now

    return re.sub(r"\s+", " ", acts_now(line, **kw)).strip()


def _moods(line: str) -> list[str]:
    from app.act_clauses import read_clauses

    return [c["mood"] for c in read_clauses(line)]


class AClauseIsJudgedByItsForm(unittest.TestCase):
    def test_a_message_told_to_someone_is_not_done(self):
        self.assertEqual(_now("tell Nell I'll take the matter to the reeve myself"), "tell Nell")
        self.assertEqual(
            _now("I pocket the coins and ask Rafe to strike the three gold from Mabel's ledger."),
            "I pocket the coins and ask Rafe .",
        )

    def test_a_case_or_a_goal_is_not_done(self):
        out = _now("When the reef comes in sight I ask Rafe to hold the skiff, then I dive through the hull.")
        self.assertNotIn("reef comes", out)
        self.assertIn("I dive through the hull", out)
        self.assertNotIn("find him", _now("I follow Rafe's voice along the wharf until I find him, and wait."))
        self.assertNotIn("say anything", _now("I count the coins inside before I say anything."))

    def test_a_plan_for_later_or_a_wish_is_not_done(self):
        self.assertEqual(_moods("I'll polish the blades after lunch."), ["plan"])
        self.assertEqual(_moods("I want to climb the wall."), ["plan"])
        self.assertNotIn("climb", _now("I could climb the wall, but I wait instead."))
        self.assertNotIn("run", _now("If the guard sees me I'll run."))

    def test_a_bare_future_alone_is_the_act_and_after_an_act_is_the_plan(self):
        self.assertEqual(_now("I will search the chest."), "I will search the chest.")
        self.assertNotIn("carry", _now("I pick up the crate, then I'll carry it to the ship."))
        self.assertIn("pay the three gold", _now("I'll pay the three gold now and step back."))

    def test_a_thing_set_in_the_mind_is_no_act(self):
        self.assertNotIn("fix", _now("I read the name aloud to fix it in my memory."))
        self.assertNotIn("commit", _now("I commit the name to memory and leave."))

    def test_a_narrated_question_and_a_denied_clause_are_not_done(self):
        out = _now("I stop where I am and look around: is this the reeve's office?")
        self.assertIn("look around", out)
        self.assertNotIn("office", out)
        self.assertNotIn("draw", _now("I don't draw my knife; I raise my hands."))

    def test_speech_is_said_and_kept_only_when_asked_for(self):
        line = '"Coin for the loading, and the three gold struck from the book." I keep my hands at my sides.'
        self.assertEqual(_now(line), "I keep my hands at my sides.")
        self.assertIn("struck from the book", _now(line, keep_speech=True))

    def test_ordinary_acts_stay_whole(self):
        for line in (
            "I climb aboard Rafe's skiff and we push off for the east reef.",
            "I go down to the dock to find the reeve and ask his price for the boat.",
            "I sleep the night at the tally house steps and at first light go down to Rafe's boat.",
        ):
            self.assertEqual(_now(line), line)

    def test_reading_twice_reads_the_same(self):
        from app.act_clauses import acts_now

        for line in (
            "I tell Gideon to hold the skiff over the deep and I dive for the guild's box.",
            "tell Nell I'll take the matter to the reeve myself",
            "When the reef comes in sight I ask Rafe to hold the skiff, then I dive.",
        ):
            once = acts_now(line)
            self.assertEqual(acts_now(once), once)
            self.assertEqual(len(once), len(line))

    def test_the_undecided_future_can_be_asked_and_is_off_by_default(self):
        from app import act_clauses

        asked: list[str] = []

        def fake(line: str, clause: str):
            asked.append(clause)
            return False

        self.assertIsNone(act_clauses._now_ask)
        self.assertEqual(_now("I will search the chest.", ask=fake), ".")
        self.assertEqual(len(asked), 1)
        # A future beside a done act is decided without asking.
        asked.clear()
        _now("I pick up the crate, then I'll carry it to the ship.", ask=fake)
        self.assertEqual(asked, [])


class TheEngineReadersUseTheClauses(unittest.TestCase):
    def test_a_thing_fixed_in_memory_costs_no_work_and_rolls_no_craft(self):
        from app.player_resources import action_kind_from_text
        from app.skill_checks import infer_check_from_action

        line = "I pocket the drowned-town coin and read the name in the last entry aloud to fix it in my memory."
        self.assertNotEqual(action_kind_from_text(line), "physical")
        check = infer_check_from_action(line, {}) or {}
        self.assertNotEqual(check.get("skill_code"), "craft")
        self.assertNotIn("act_family", check)

    def test_work_someone_else_is_asked_to_do_costs_the_player_nothing(self):
        from app.player_resources import action_kind_from_text

        for line in (
            "I tell the men to haul the loose planks clear of the hull before the water rises.",
            "I ask Roderic to count out my pay for the haul here on the wharf.",
            "I'll polish the blades after lunch.",
        ):
            self.assertNotIn(action_kind_from_text(line), {"physical", "combat"}, line)

    def test_the_players_own_act_after_a_message_still_counts(self):
        from app.player_resources import action_kind_from_text
        from app.skill_checks import infer_check_from_action

        line = "I tell Gideon to hold the skiff over the deep and I dive for the guild's box."
        self.assertEqual(action_kind_from_text(line), "physical")
        self.assertEqual((infer_check_from_action(line, {}) or {}).get("skill_code"), "athletics")

    def test_a_question_still_asks_what_is_known(self):
        from app.skill_checks import infer_check_from_action

        self.assertEqual((infer_check_from_action("what is the ring worth?", {}) or {}).get("skill_code"), "appraise")

    def test_a_plan_told_to_someone_asks_for_no_walk(self):
        from app.world import _unasked_unshown_move

        rows = [{"code": "L6", "name": "The Hold"}]
        narration = "You turn toward the narrow path that leads to the reeve's office."
        told = _unasked_unshown_move(
            {}, {"move_to_location": "Raven's Office"}, rows, "I tell Nell I'll take the matter to the reeve myself.",
            intent="conversation", narration=narration, current_name="The Hold",
        )
        self.assertEqual(told, "Raven's Office")
        walked = _unasked_unshown_move(
            {}, {"move_to_location": "Raven's Office"}, rows, "I walk to the reeve's office.",
            intent="travel", narration=narration, current_name="The Hold",
        )
        self.assertEqual(walked, "")


class TheDayIsReplayedThroughTheEngine(unittest.TestCase):
    def test_a_town_walk_costs_by_the_minute(self):
        from app.player_resources import action_resource_delta

        short = action_resource_delta(kind="journey", minutes=6)["energy_exact"]
        hour = action_resource_delta(kind="journey", minutes=60)["energy_exact"]
        self.assertLess(short, 0.5)
        self.assertGreater(hour, 2.5)

    def test_an_ordinary_day_ends_between_a_third_and_a_half(self):
        import energy_replay as er

        summary = er.summarise(er.synthetic_rows(er.ORDINARY_DAY))
        self.assertGreaterEqual(summary["end_fraction"], 0.3)
        self.assertLessEqual(summary["end_fraction"], 0.55)
        self.assertEqual(summary["turns_at_zero"], 0)

    def test_heavy_labour_still_tires(self):
        import energy_replay as er

        rows = er.synthetic_rows(er.HEAVY_LABOUR)
        self.assertTrue(any(r["blocked"] for r in rows[:5]))
        self.assertLessEqual(rows[3]["energy"], 3)

    def test_the_replay_uses_the_engines_own_spend(self):
        import energy_replay as er
        from app.player_resources import LIGHT_ACTION_KINDS

        rows = er.replay_kinds([("physical", 25), ("talk", 6), ("wait", 60)], energy=10, max_energy=16)
        self.assertLess(rows[0]["energy"], 10)
        self.assertIn("wait", LIGHT_ACTION_KINDS)
        self.assertGreater(rows[2]["energy"], rows[1]["energy"])


if __name__ == "__main__":
    unittest.main()
