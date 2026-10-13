"""7B run 20: 'a shipment of salvage' is not a take; inquire/state are the player's speech tags."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class SalvageNounIsNotATake(unittest.TestCase):
    """T2: '"A shipment of salvage at the Gilded Heron ..."' put "salvage x1" in the pack."""

    def test_take_intent(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent('"A shipment of salvage at the Gilded Heron?" I stay where I am.'))
        self.assertFalse(player_take_intent('"Any salvage worth the trip?"'))
        self.assertTrue(player_take_intent("I salvage what I can from the hull."))


class InquireAndStateAreSpeech(unittest.TestCase):
    """T4: '"Is this Thaddeus?" you inquire' and 'You state, "..."' were not read as the player's lines."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        line = '"Where do I find this Thaddeus, then - the harbour office?"'
        paras = [
            '"Where do I find this Thaddeus, then - the harbour office?" you ask.',
            'Gunilda nods. "In the office."',
            '"Is this Thaddeus?" you inquire, approaching the desk.',
            'You state, "I heard you have salvage contracts for me."',
        ]
        _kept, dropped = drop_invented_player_speech(paras, line)
        self.assertTrue(any("you inquire" in d for d in dropped), dropped)
        self.assertTrue(any("You state" in d for d in dropped), dropped)


class EchoedPiecesOfTheLine(unittest.TestCase):
    """Run 21 T1: '... you say. Morning, Cressida. I check the reckoner. Seen anyone else ...?'"""

    def test_cleaned(self):
        from app.narration_pipeline import keep_player_words

        line = ('"Morning, Cressida. Same as always - whatever the lower district gives up." I check the reckoner. '
                '"Seen anyone else out there today?"')
        text = ("“Morning, Cressida. Same as always - whatever the lower district gives up,” you say. "
                "Morning, Cressida. I check the reckoner. Seen anyone else out there today?\n\nCressida looks over the flat.")
        fixed, _changes = keep_player_words(text, line)
        self.assertIn("you say. You check the reckoner. “Seen anyone else out there today?”", fixed)
        self.assertEqual(fixed.count("Morning, Cressida"), 1)


if __name__ == "__main__":
    unittest.main()
