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


class AQualityOfAMan(unittest.TestCase):
    PROSE = ("You finish the meal and ask Eldric for a room for the night. Eldric leans back in his chair, the worn "
             "leather creaking beneath him, and eyes you with the weight of a man who has seen too many travelers come "
             "and go. “A room for the night is a coin and a name,” he says.")

    def test_no_figure_is_shown(self):
        from app.world import _figure_hints

        self.assertEqual([h for h in _figure_hints(self.PROSE, ["Eldric"]) if "man" in h.lower()], [])

    def test_a_man_who_acts_is_still_shown(self):
        from app.world import _figure_hints

        prose = "A man in a salt-stained coat pushes through the door and eyes you across the room."
        self.assertTrue(any("man" in h.lower() for h in _figure_hints(prose, ["Eldric"])))


if __name__ == "__main__":
    unittest.main()
