"""8B run 148, T45 and T46: a meal at the Stag and Heron.

T45: "I order the fish and a mug of ale, pay Eldric for them" came back with
GRANT "ale", GRANT "fish" and GOLD 30. The ale and the fish entered the pack
(and their "find" kept the model's XP), and the payment grew the purse.

T46: "Eldric eyes you with the weight of a man who has seen too many
travelers come and go" let NPC_NEW "Hawise Hayward" bind to "a man" and
minted Aldous at the inn; a quality measured by a figure describes someone
already here.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run148_inn
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = "I order the fish and a mug of ale, pay Eldric for them, and let the matter of the stranger drop for now."


class OrderedAndEaten(unittest.TestCase):
    def test_the_fish_and_the_ale_are_consumed(self):
        from app.world import _consumed_in_line

        self.assertTrue(_consumed_in_line(LINE, ["ale"]))
        self.assertTrue(_consumed_in_line(LINE, ["fish"]))

    def test_food_bought_for_the_road_is_carried(self):
        from app.world import _consumed_in_line

        self.assertFalse(_consumed_in_line("I buy three loaves and a wedge of cheese for the road.", ["loaves"]))
        self.assertFalse(_consumed_in_line("I order a crate of salt fish to be loaded on the cart.", ["fish"]))

    def test_eating_it_is_consuming_it(self):
        from app.world import _consumed_in_line

        self.assertTrue(_consumed_in_line("I eat the bread and drink the broth by the fire.", ["bread"]))
        self.assertTrue(_consumed_in_line("I eat the bread and drink the broth by the fire.", ["broth"]))


class AnOfferSaidBack(unittest.TestCase):
    """T47: "I'll pay five" answered "Five gold, and your name stays yours" moved no coin."""

    LINE = "\"Ten gold is steep for a bed. I'll pay five, and my name stays mine.\""
    PROSE = ("“Ten gold is steep for a bed. I'll pay five, and my name stays mine,” you say. You haggle with Eldric over "
             "the price of a night’s stay. His offer is clear—ten gold for a bed and a name. You counter with five gold. "
             "Eldric finally speaks, his tone measured but firm. “Five gold, and your name stays yours. But know this—” "
             "He pauses, his eye narrowing.")

    def test_a_bare_sum_in_a_line_about_gold_is_the_offer(self):
        from app.prose_state import player_trade_offer

        self.assertEqual(player_trade_offer(self.LINE), 5)
        self.assertIsNone(player_trade_offer("I'll pay five men to carry it."))

    def test_the_sum_said_back_is_accepted(self):
        from app.prose_state import offer_answer

        self.assertEqual(offer_answer(self.PROSE, self.LINE), "accepted")
        self.assertEqual(offer_answer("“Five? Not enough,” Eldric says.", self.LINE), "refused")

    def test_the_five_gold_leave_the_purse(self):
        from app.world import _settle_stated_gold

        result = {"narration": self.PROSE, "player": {}}
        note = _settle_stated_gold(result, self.LINE)
        self.assertEqual(result["player"].get("gold_delta"), -5, note)


class CoinSetDownForWords(unittest.TestCase):
    """T51: three gold put on the bar for Eldric's story were voided as a purchase of a refused GRANT "clue"."""

    LINE = "I put three gold on the bar for Eldric and swear to keep it to myself. \"Now, the cargo. What was it?\""
    PROSE = ("You put three gold on the bar for Eldric and swear to keep it to yourself. \"Now, the cargo. What was it?\" "
             "you ask. The old barkeep’s face tightens. \"The Stormbreaker’s cargo was never meant to be found,\" he says. "
             "\"It was a ship full of relics—old, cursed things.\"")

    def test_the_players_own_payment_stands(self):
        from app.world import _void_unbought_spend

        result = {"player": {"gold_delta": -3}, "_dsl": {"grants": ["clue about the Stormbreaker's cargo"]}}
        voided = _void_unbought_spend(result, ["clue about the Stormbreaker's cargo"], [], None, self.LINE, self.PROSE)
        self.assertFalse(voided)
        self.assertEqual(result["player"]["gold_delta"], -3)

    def test_coin_refused_stays_in_the_purse(self):
        from app.world import _void_unbought_spend

        prose = "You put three gold on the bar. Eldric pushes the coins back across the wood. \"Keep your gold,\" he says."
        result = {"player": {"gold_delta": -3}, "_dsl": {"grants": ["clue"]}}
        self.assertTrue(_void_unbought_spend(result, ["clue"], [], None, "I put three gold on the bar for the story.", prose))

    def test_a_bed_and_a_meal_bought_are_a_spend(self):
        # 8B run 149, T42: twenty gold for a meal and a bed were voided once the bed and meal grants were refused as fixtures.
        from app.world import _void_unbought_spend

        prose = ("\"A meal and a bed,\" she said. \"That'll be twenty gold, plus a coin for the chamber pot.\" You handed over the "
                 "coins, and she nodded, setting the change on the counter. As you settled into the bed, the weight of the day pressed down.")
        result = {"player": {"gold_delta": -20}, "_dsl": {"grants": ["bed", "meal"]}}
        voided = _void_unbought_spend(result, ["bed", "meal"], [], None,
                                      "I ask the innkeeper for a hot meal and a bed for the night, and pay what she asks.", prose)
        self.assertFalse(voided)
        self.assertEqual(result["player"]["gold_delta"], -20)

    def test_a_purchase_of_nothing_is_still_voided(self):
        from app.world import _void_unbought_spend

        prose = "The stall is bare. Nothing changes hands."
        result = {"player": {"gold_delta": -12}, "_dsl": {"grants": ["coal", "cloth"]}}
        self.assertTrue(_void_unbought_spend(result, ["coal", "cloth"], [], None, "I buy coal and cloth.", prose))


class AQualityOfAMan(unittest.TestCase):
    PROSE = ("You finish the meal and ask Eldric for a room for the night. Eldric leans back in his chair, the worn "
             "leather creaking beneath him, and eyes you with the weight of a man who has seen too many travelers come "
             "and go. “A room for the night is a coin and a name,” he says.")

    def test_no_figure_is_shown(self):
        from app.world import _figure_hints

        self.assertEqual([h for h in _figure_hints(self.PROSE, ["Eldric"]) if "man" in h.lower()], [])

    def test_a_man_in_a_memory_is_not_here(self):
        # 8B run 149, T56: "the memory of a man you once saw in the Docks" minted Elias Vane at the yard.
        from app.world import _figure_hints

        prose = ("A name catches your eye—Elias Vane—and the memory of a man you once saw in the Docks flickers to life. "
                 "You flip through the pages.")
        self.assertEqual([h for h in _figure_hints(prose, []) if "man" in h.lower()], [])

    def test_a_man_who_acts_is_still_shown(self):
        from app.world import _figure_hints

        prose = "A man in a salt-stained coat pushes through the door and eyes you across the room."
        self.assertTrue(any("man" in h.lower() for h in _figure_hints(prose, ["Eldric"])))


if __name__ == "__main__":
    unittest.main()
