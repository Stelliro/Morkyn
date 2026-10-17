"""8B run 146, T73, T76, T77: compound sums, a payment over a gain op, a pointed-at place, a name asked after.

T73: "You count forty-six gold out of your purse into Veyra's palm" came with
GOLD +moderate; "forty-six" read as "six", and the purse grew by 38. Tens and
units together are one number, and a payment the narration shows beats a gain
op. T73 also minted "And Veyra" from a sentence-opening conjunction.

T76: "a narrow passage that leads to the Edge of the Flats [[L8]]" kept a MOVE
there while the player had walked into the Old Wharf: a place named only as
where a path leads is not reached.

T77: "ask the nearest dockhand where Elara Veyne can be found" rolled
persuasion against Elara, who was not there.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run146_coin
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import prose_state  # noqa: E402
from app.skill_checks import infer_check_from_action  # noqa: E402
from app.world import _introduced_people, _place_only_pointed_at, _settle_stated_gold  # noqa: E402

PAID = ("You count forty-six gold out of your purse into Veyra’s palm, coin by coin, and speak: “Then I walk.” "
        "The spymaster’s fingers close around the coins, her dark eyebrows knitting together.")


class CompoundSumsAreOneNumber(unittest.TestCase):
    def test_forty_six_is_forty_six(self):
        self.assertEqual(prose_state._number("forty-six"), 46)
        self.assertEqual(prose_state._number("twenty one"), 21)
        self.assertEqual(prose_state._number("ninety"), 90)
        self.assertIsNone(prose_state._number("forty-forty"))

    def test_the_payment_is_read_whole(self):
        self.assertEqual(prose_state.stated_coin_amounts(PAID)["paid"], [46])
        self.assertEqual(prose_state.coin_mentions(PAID), [46])


class APaymentShownBeatsAGainOp(unittest.TestCase):
    def test_the_purse_loses_what_the_prose_pays(self):
        result = {"narration": PAID, "player": {"gold_band": "moderate"}}
        line = "I count forty-six gold out of my purse into Veyra's hand, coin by coin."
        note = _settle_stated_gold(result, line)
        self.assertEqual(result["player"].get("gold_delta"), -46, note)
        self.assertNotIn("gold_band", result["player"])

    def test_the_players_own_coin_backs_no_gain(self):
        # T71: "counting the gold in your purse ... close to forty-six"; T79: "the memory of forty-six gold coins spent".
        for prose in (
            "You hold your ground, counting the gold in your purse, knowing the number is close to forty-six. Still, the coin in your hand is a promise.",
            "Veyra Drowned’s name lingers, a ghost of debt, and the memory of forty-six gold coins spent on a walk back that felt like a lifetime.",
        ):
            result = {"narration": prose, "player": {"gold_band": "moderate"}}
            note = _settle_stated_gold(result, "I wait.")
            self.assertEqual((note or {}).get("source"), "gain_without_coin_dropped", prose)
            self.assertNotIn("gold_band", result["player"])

    def test_coin_handed_to_the_player_still_gains(self):
        prose = "He counts out twenty gold into your palm. “For the warning,” he says."
        result = {"narration": prose, "player": {"gold_delta": 20}}
        _settle_stated_gold(result, "I hold out my hand.")
        self.assertEqual(result["player"].get("gold_delta"), 20)


class AConjunctionIsNoName(unittest.TestCase):
    def test_and_veyra_is_not_a_new_person(self):
        prose = "Rolf is watching, his grip tight on his pack. And Veyra, the spymaster, is watching you just as closely."
        self.assertEqual(_introduced_people(prose, ["Veyra Drowned", "Rolf Joliffe"], set()), [])

    def test_a_real_introduction_still_counts(self):
        prose = "Gareth Radley, the dockhand, leans against a stack of barrels."
        self.assertEqual([p["name"] for p in _introduced_people(prose, [], set())], ["Gareth Radley"])


class APlaceOnlyPointedAtIsNotReached(unittest.TestCase):
    LOW = ("you step between the pilings. you move deeper into the wharf until you reach a narrow passage "
           "that leads to the edge of the flats [[l8]].")

    def test_where_a_passage_leads_is_pointed_at(self):
        self.assertTrue(_place_only_pointed_at(self.LOW, "edge of the flats"))
        self.assertTrue(_place_only_pointed_at(self.LOW, "[[l8]]"))

    def test_a_place_come_out_onto_is_reached(self):
        self.assertFalse(_place_only_pointed_at("you come out onto the edge of the flats [[l8]], mud to the horizon.", "edge of the flats"))

    def test_pointed_at_then_reached_is_reached(self):
        low = "the path leads to the edge of the flats. you walk it and stand on the edge of the flats at last."
        self.assertFalse(_place_only_pointed_at(low, "edge of the flats"))


class ANameAskedAfterIsNoOpponent(unittest.TestCase):
    def test_asking_where_someone_is_does_not_roll_against_them(self):
        ctx = {
            "npcs": [{"code": "J", "name": "Elara Veyne"}, {"code": "R", "name": "Gareth Radley"}],
            "conversation_turn": {"present": ["R"], "addressed": ["J"]},
        }
        check = infer_check_from_action("I turn back into the Old Wharf and ask the nearest dockhand where Elara Veyne can be found.", ctx)
        self.assertIsNotNone(check)
        self.assertNotEqual(((check or {}).get("opposition") or {}).get("name"), "Elara Veyne")

    def test_asking_someone_present_still_rolls_against_them(self):
        ctx = {
            "npcs": [{"code": "J", "name": "Elara Veyne"}, {"code": "R", "name": "Gareth Radley"}],
            "conversation_turn": {"present": ["J", "R"], "addressed": ["J"]},
        }
        check = infer_check_from_action("I ask Elara Veyne what the journal says.", ctx)
        self.assertEqual(((check or {}).get("opposition") or {}).get("name"), "Elara Veyne")


if __name__ == "__main__":
    unittest.main()
