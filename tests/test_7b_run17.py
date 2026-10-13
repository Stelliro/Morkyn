"""7B run 17 (Qwen2.5 7B on MLE, agent as player): invented speech is compared with the player's quotes only."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = ('"Salvage. I run the flats." I look around the passage. '
        '"A ploughman, working inside a drowned house? What are you building down here, Madoc?"')


class QuotedPlayerNarratedActsAreNotSpeech(unittest.TestCase):
    """T5: '"That looks useful," you say' shared "look" with "I look around the passage" and was kept."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = [
            '"Salvage. I run the flats," you say. "A ploughman, working inside a drowned house? What are you building down here, Madoc?"',
            '"Building? I\'m just clearing the mud," Madoc replies.',
            'You notice a small, rusted tool. "That looks useful," you say, bending to pick it up.',
        ]
        _kept, dropped = drop_invented_player_speech(paras, LINE)
        self.assertEqual(dropped, ['"That looks useful," you say, bending to pick it up.'])

    def test_typed_lines_stay(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = ['"Salvage. I run the flats," you say.', '"Building?" Madoc asks.']
        self.assertEqual(drop_invented_player_speech(paras, LINE)[1], [])


class ConversationEndsHere(unittest.TestCase):
    """Run 18 T1: "The conversation with Wymarc ends here." shipped as narration."""

    def test_repaired(self):
        from app.prose_state import repair_meta_leaks

        text, leaks = repair_meta_leaks("Wymarc smiles.\n\nThe conversation with Wymarc ends here. You are still thinking.")
        self.assertNotIn("ends here", text)
        self.assertEqual(leaks[0]["why"], "stage_direction")
        self.assertEqual(repair_meta_leaks("The conversation ends when the bell rings.")[1], [])


if __name__ == "__main__":
    unittest.main()
