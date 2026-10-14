"""7B run 30, T7 (Qwen2.5 7B on MLE, agent as player): a degenerate draft about moles, repaired narrowly."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = ('"I have not told you my name, mole catcher." I set the next trap at the second tunnel mouth and tamp '
        'the earth flat with my palm.')


class ParaphrasedQuoteGoes(unittest.TestCase):
    """'You have not shared your name, mole catcher.' restated the typed line as narration."""

    def test_dropped(self):
        from app.narration_pipeline import keep_player_words

        text = ('“I have not told you my name, mole catcher,” you say. You have not shared your name, mole '
                'catcher. The rain drips from the eaves.')
        out, changes = keep_player_words(text, LINE)
        self.assertNotIn("You have not shared your name", out)
        self.assertIn("echoed_quote_paraphrase_dropped", [c["action"] for c in changes])

    def test_narration_without_the_vocative_stays(self):
        from app.narration_pipeline import _paraphrased_quote

        quotes = ["I have not told you my name, mole catcher."]
        self.assertFalse(_paraphrased_quote("You have not shared your name with anyone here.", quotes))
        self.assertFalse(_paraphrased_quote("He nods at the mole catcher.", quotes))


class TheActIsThePlayers(unittest.TestCase):
    """'He tamps the earth flat with his palm' for the player's typed 'tamp the earth flat with my palm'."""

    def test_given_back(self):
        from app.narration_pipeline import keep_player_words

        text = ('“I have not told you my name, mole catcher,” you say. Dunstan [[A]] watches as you, setting '
                'the next trap at the second mouth of the second burrow. He tamps the earth flat with his palm, '
                'ensuring the trap is secure.')
        out, _changes = keep_player_words(text, LINE)
        self.assertIn("You tamp the earth flat with your palm, ensuring the trap is secure.", out)
        self.assertIn("watches as you set the next trap", out)

    def test_working_beside_stays(self):
        from app.narration_pipeline import keep_player_words

        text = ('“I have not told you my name, mole catcher,” you say. You set the next trap at the second '
                'tunnel mouth. Dunstan sets another trap beside yours at the second tunnel mouth.')
        out, _changes = keep_player_words(text, LINE)
        self.assertIn("Dunstan sets another trap beside yours", out)


class NoClawsOnAHuman(unittest.TestCase):
    def test_dropped_for_human_only(self):
        from app.prose_state import repair_player_body

        text = ("You dig at the earth with your claws. You wrap the scrolls in your shirt tail. "
                + "The rain runs off the planks and the rope creaks against the post. " * 4)
        out, fixes = repair_player_body(text, "human")
        self.assertNotIn("your claws", out)
        self.assertIn("your shirt tail", out)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(repair_player_body(text, "ratfolk")[1], [])


class CutWordInAQuote(unittest.TestCase):
    def test_fragment_goes(self):
        from app.prose_state import repair_cut_word_in_quote

        out, _ = repair_cut_word_in_quote('"If we don\'t get them soon, they\'ll start eating through the t." He fetches a trap.')
        self.assertIn('"If we don\'t get them soon, they\'ll start eating through." He fetches a trap.', out)
        for kept in ('"What does Madoc know that the reckoner doesn\'t?"', '"Plan B."', '"I\'ll take a."'):
            self.assertEqual(repair_cut_word_in_quote(kept), (kept, []))


class TimeToMakeAMove(unittest.TestCase):
    def test_closer_goes(self):
        from app import llm

        text = ("You can feel the tension in the tannery, the sound of moles underground. " * 6) + "It's time to make a move."
        out, count = llm._drop_menu_sentences(text, floor=0)
        self.assertEqual(count, 1)
        self.assertNotIn("time to make a move", out)
        kept = "It's time to make a move on the tide tables before the reeve closes."
        self.assertEqual(llm._drop_menu_sentences(kept, floor=0)[1], 0)


if __name__ == "__main__":
    unittest.main()
