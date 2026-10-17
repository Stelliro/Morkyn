"""8B run 145, T17-T24: the clock, a service paid for, and a bystander named in the line.

- "rest until the evening tide" left the clock at noon, so the prose's evening
  was rewritten to morning (T17-T22): a wait until a time of day lasts until it.
- "I count six gold coins into the bargeman's hand" for a passage was voided as
  a purchase with nothing bought (T21): the player's own stated payment stands.
- "kick back up to Bennet's boat" rolled perception vs Bennet (T24): only a
  contest has another side.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run145_clock_coin
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-run145-clock-"))
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


class AWaitLastsUntilItsHour(unittest.TestCase):
    def _at(self, minute: int):
        from app import world
        from app.db import connect, init_db

        init_db()
        world.start_playthrough({"player_name": "Isk", "start_location": "Saltmarrow", "special_ability_origin": "none"})
        with connect() as conn:
            world._pacing_set(conn, "world_minute", minute)
        return world

    def test_until_the_evening_tide_at_eleven_is_seven_hours(self):
        from app.db import connect

        world = self._at(11 * 60)
        with connect() as conn:
            self.assertEqual(world._wait_until_minutes(conn, "I sit on the sea wall to eat what bread I have and rest until the evening tide."), 7 * 60)

    def test_a_time_already_past_is_tomorrows(self):
        from app.db import connect

        world = self._at(20 * 60)
        with connect() as conn:
            self.assertEqual(world._wait_until_minutes(conn, "I wait here until dawn."), 10 * 60)

    def test_a_wait_said_in_speech_asks_nothing_of_the_clock(self):
        from app.db import connect

        world = self._at(11 * 60)
        with connect() as conn:
            self.assertEqual(world._wait_until_minutes(conn, "\"I'll wait until evening if I must.\" I keep walking to the dock."), 0)

    def test_a_line_that_opens_on_a_time_of_day_skips_to_it(self):
        # 8B run 146, T24: "In the morning I take the ledger down to Emery" at the inn in the evening.
        from app.db import connect

        world = self._at(20 * 60)
        with connect() as conn:
            self.assertEqual(world._wait_until_minutes(conn, "In the morning I take the ledger down to Emery at the old wharf."), 12 * 60)
            self.assertEqual(world._wait_until_minutes(conn, "At first light I walk down to the wharf."), 10 * 60)

    def test_the_noun_bargain_is_not_the_act_of_haggling(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action("I hold him to the Drowned Hand's side of the bargain.", {})
        self.assertNotEqual((check or {}).get("skill_code"), "appraise")
        check = infer_check_from_action("I haggle over the pelt.", {})
        self.assertEqual((check or {}).get("skill_code"), "appraise")

    def test_a_tide_with_no_hour_is_a_quarter_day(self):
        from app.db import connect

        world = self._at(11 * 60)
        with connect() as conn:
            self.assertEqual(world._wait_until_minutes(conn, "I wait on the dock for the next tide."), 360)


class ThePlayersOwnPaymentStands(unittest.TestCase):
    def test_counting_out_coin_for_a_passage_is_not_voided(self):
        from app import world

        result = {"player": {"gold_delta": -6}, "_dsl": {"grants": ["crate"]}}
        line = "\"Six gold, there and back.\" I count six gold coins into the bargeman's hand and keep the rest of my purse closed."
        prose = "You count out the coins. Bennet Harrow [[H]]'s fingers close around them like a vice, and he nods."
        voided = world._void_unbought_spend(result, ["crate"], [], {}, line, prose)
        self.assertFalse(voided)
        self.assertEqual(result["player"]["gold_delta"], -6)

    def test_coin_set_down_and_refused_is_still_the_players(self):
        # 8B run 146, T16: six gold set on the counter, the chandler refused the deal.
        from app import world

        result = {"player": {"gold_delta": -6}, "_dsl": {"grants": ["flask of oils"]}}
        line = "\"Forty-five gold for a lamp? I have twelve.\" I set six gold coins on his counter. \"Six for both, or I walk.\""
        prose = "Theobald Garner [[F]] eyes the six gold coins. \"You think you're getting a deal,\" he mutters. \"You want a flask? You'll pay for it.\""
        voided = world._void_unbought_spend(result, ["flask of oils"], [], {}, line, prose)
        self.assertTrue(voided)
        self.assertEqual(result["player"]["gold_delta"], 0)

    def test_a_price_named_across_a_full_stop_in_speech_is_a_bargain(self):
        from app.skill_checks import infer_check_from_action

        line = "\"Forty-five gold for a lamp and a flask? I have twelve to my name.\" I set six gold coins on his counter. \"Six for both, or I walk.\""
        check = infer_check_from_action(line, {})
        self.assertEqual((check or {}).get("skill_code"), "persuasion")
        self.assertFalse((check or {}).get("routine"))

    def test_a_model_spend_for_refused_goods_is_still_voided(self):
        from app import world

        result = {"player": {"gold_delta": -12}, "_dsl": {"grants": ["coal", "cloth"]}}
        voided = world._void_unbought_spend(result, ["coal", "cloth"], [], {}, "I look over the stall.")
        self.assertTrue(voided)
        self.assertEqual(result["player"]["gold_delta"], 0)


class AKickUpwardIsNoBlow(unittest.TestCase):
    def test_kicking_back_up_to_the_boat_is_not_combat(self):
        from app import world
        from app.player_resources import action_kind_from_text

        line = "I search inside the hull by lamplight, then kick back up to Bennet's boat for air."
        self.assertNotEqual(world._turn_intent(line)[0], "combat")
        self.assertNotEqual(action_kind_from_text(line), "combat")

    def test_the_blade_striking_mud_is_no_blow(self):
        # 8B run 146, T11: "until the blade strikes something solid" rolled melee vs the crewman.
        from app import world
        from app.skill_checks import infer_check_from_action

        line = "I work the hollow with the oar until the blade strikes something solid, then kneel and dig it out of the silt with my hands."
        self.assertNotEqual(world._turn_intent(line)[0], "combat")
        check = infer_check_from_action(line, {})
        self.assertNotEqual((check or {}).get("skill_code"), "melee")

    def test_kicking_a_man_still_is(self):
        from app import world
        from app.player_resources import action_kind_from_text

        line = "I kick the man in the knee and go for his knife."
        self.assertEqual(world._turn_intent(line)[0], "combat")
        self.assertEqual(action_kind_from_text(line), "combat")


class OnlyAContestHasAnotherSide(unittest.TestCase):
    BENNET = {"id": 8, "code": "H", "name": "Bennet Harrow", "role": "bargeman", "stat_profile": {"wisdom": 10}}

    def _ctx(self):
        return {
            "current_location": {"id": 5, "code": "L5", "name": "Wreck Site", "npcs": [self.BENNET]},
            "locations": [{"id": 5, "code": "L5", "name": "Wreck Site", "npcs": [self.BENNET]}],
            "conversation_turn": {"addressed": [], "present": ["H"], "listening": ["H"]},
            "settings": {"playthrough_options": {}},
        }

    def test_a_search_is_not_opposed_by_a_bystander_named_in_the_line(self):
        from app.skill_checks import infer_check_from_action

        line = "I search inside the hull by lamplight for a small boat or a pack, then kick back up to Bennet's boat for air."
        check = infer_check_from_action(line, self._ctx())
        self.assertIsNotNone(check)
        self.assertNotEqual(check.get("skill_code"), "persuasion")
        self.assertIsNone(check.get("opposition"))

    def test_a_bargain_with_bennet_is_opposed_by_him(self):
        from app.skill_checks import infer_check_from_action

        check = infer_check_from_action("I try to convince Bennet to take six gold for the passage.", self._ctx())
        self.assertEqual(check.get("skill_code"), "persuasion")
        self.assertEqual((check.get("opposition") or {}).get("name"), "Bennet Harrow")


if __name__ == "__main__":
    unittest.main()
