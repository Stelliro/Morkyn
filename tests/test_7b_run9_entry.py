"""7B run 9 (Qwen2.5 7B on MLE, agent as player): a choice put to the player is not an entry."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class AChoiceIsNotAnEntry(unittest.TestCase):
    """T0: "do you enter the warehouse and gather supplies" opened a store and moved Isk and Hal in."""

    def test_offered_entries_do_not_count(self):
        from app.venues import entry_in_prose

        for text in (
            "You have a choice to make: do you enter the warehouse and gather supplies, or approach Hal Garner?",
            "The door creaks in the morning breeze, inviting you to step inside the warehouse.",
            "Will you step into the bakery or keep walking?",
            "You could go into the smithy and ask for work.",
        ):
            self.assertIsNone(entry_in_prose(text, ["Hal Garner"]), text)

    def test_real_entries_still_count(self):
        from app.venues import entry_in_prose

        self.assertEqual(entry_in_prose("You push open the door and step into the bakery.")["kind"], "bakery")
        hit = entry_in_prose("You step inside the smithy, where Tam is at the anvil.", ["Tam"])
        self.assertEqual(hit["kind"], "smithy")


class AskingWhoBuysIsNotBuying(unittest.TestCase):
    """T4: "Hal, who in Saltmarrow buys old coins?" read as the player asking to take something."""

    def test_someone_else_buying(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent("Hal, who in Saltmarrow buys old coins - and who pays fair for them?"))
        self.assertFalse(player_take_intent("I ask Hal who buys coins."))
        self.assertTrue(player_take_intent("I buy the lantern."))
        self.assertTrue(player_take_intent("I keep the coin and ask who buys them."))


if __name__ == "__main__":
    unittest.main()
