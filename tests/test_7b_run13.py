"""7B run 13 (Qwen2.5 7B on MLE, agent as player): names said to someone, more speech tags, bracketed words."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = '"Then tell me the tally, Reeve. How much do I owe the guild, to the coin?"'
SCENE = [
    '"Then tell me the tally, Reeve. How much do I owe the guild, to the coin?" Your question hangs.',
    'Reeve Oakes sighs. "It is private."',
    '"I need to know, Reeve," you press, your voice firm, "or else I cannot leave."',
    'Reeve Oakes sighs. "Very well, the tally stands at 125 coins."',
    '"Thank you, Reeve," you say, turning to leave. The Docks stretch out.',
]


class InventedLinesWithTheSameAddressee(unittest.TestCase):
    """T3: '"Thank you, Reeve," you say' and '"I need to know, Reeve," you press' were kept as the player's."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        _paras, dropped = drop_invented_player_speech(list(SCENE), LINE)
        self.assertEqual(len(dropped), 2, dropped)
        self.assertTrue(any("you press" in d for d in dropped))
        self.assertTrue(any("Thank you, Reeve" in d for d in dropped))

    def test_the_typed_line_stays(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras, _dropped = drop_invented_player_speech(list(SCENE), LINE)
        self.assertIn("How much do I owe the guild", paras[0])


class BracketedWords(unittest.TestCase):
    """T3: 'in the (docks)', 'just (reveal)', 'the (tally) stands' shipped as written."""

    def test_unwrapped(self):
        from app.prose_state import repair_bracketed_words

        text, note = repair_bracketed_words(
            '"I know you\'ve been in the (docks) for some time," he says, "but I can\'t just (reveal) it."'
        )
        self.assertEqual(text, '"I know you\'ve been in the docks for some time," he says, "but I can\'t just reveal it."')
        self.assertEqual(note["count"], 2)

    def test_a_single_aside_stays(self):
        from app.prose_state import repair_bracketed_words

        self.assertEqual(repair_bracketed_words("He nods (barely) and turns away."), ("He nods (barely) and turns away.", None))


if __name__ == "__main__":
    unittest.main()
