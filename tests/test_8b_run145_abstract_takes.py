"""8B run 145, T41: a duty kept is not a thing taken.

"I keep the lookout" put "lookout x1" in the pack as taken-as-asked, and the
same take intent let a model GRANT "Salvage Rights Claim" through. Keeping a
duty or a state (the lookout, watch, one's word, the pace) asks for nothing.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run145_abstract_takes
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.llm import player_take_intent  # noqa: E402
from app.world import _NOT_A_TAKEN_THING  # noqa: E402


class ADutyKeptIsNoTake(unittest.TestCase):
    def test_keeping_the_lookout_asks_for_nothing(self):
        self.assertFalse(player_take_intent("I keep the lookout, watching the swell while the crew patches the line."))
        self.assertFalse(player_take_intent("I keep the watch till dawn and keep my word to Orme."))

    def test_keeping_a_thing_still_takes_it(self):
        self.assertTrue(player_take_intent("I keep the fitting I pulled out of the mud."))
        self.assertTrue(player_take_intent("I keep the box in my grasp and climb aboard."))

    def test_the_duty_words_are_no_taken_things(self):
        for word in ("lookout", "watch", "guard", "word", "pace", "course"):
            self.assertIn(word, _NOT_A_TAKEN_THING, word)


if __name__ == "__main__":
    unittest.main()
