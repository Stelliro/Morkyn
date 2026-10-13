"""7B run 17 T5 (Qwen2.5 7B on MLE, agent as player): speech is not a walk request; a named line with a gesture tail."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = (
    '"Salvage. I run the flats." I look around the passage. '
    '"A ploughman, working inside a drowned house? What are you building down here, Madoc?"'
)
DRAFT = """===NAR===
You look around the passage. A ploughman named Madoc Joliffe is working inside a drowned house, clearing mud from the floor with a broad blade.

"Building? I'm just clearing the mud and roots," Madoc replies, stepping back to let you see the structure. "This place was a house before the waters rose. I try to make something useful of it, but the sea's not done yet."

You notice a small, rusted tool lying on the ground, half-buried in mud. "That looks useful," you say, bending to pick it up. It's a chisel, slightly bent but still sharp.

"Well, you might as well have it," Madoc says. "The sea's done with me for now."

You take the chisel, feeling its weight in your hand. "Thanks. I'll use it well. What about you, Madoc? Any leads on a job around here?" he shrugs, a hint of a smile playing on his lips.

"You might find something worthwhile at the harbour. It's just over the flats, near the salt marsh."

You thank him and start walking towards the salt marsh, the chisel in hand.
===OPS===
MOVE "salt marsh"
"""


class SpeechIsNotAWalkRequest(unittest.TestCase):
    """The cut was skipped because '"I run the flats."' read as travel, and the MOVE to Salt Marsh stood."""

    def test_cut_applies_and_move_goes(self):
        from app import llm
        from app.turn_dsl import parse_dsl_turn

        turn = parse_dsl_turn(DRAFT, LINE)
        self.assertEqual((turn.get("player") or {}).get("move_to_location"), "salt marsh")
        out = llm._drop_player_overreach(turn, LINE, "test", [])
        self.assertTrue(out.get("_scene_cut"), "no cut")
        self.assertIsNone((out.get("player") or {}).get("move_to_location"))
        self.assertNotIn("start walking towards the salt marsh", out["narration"])
        self.assertIn("the sea's not done yet", out["narration"])


class NamedLineWithAGesture(unittest.TestCase):
    """'You take the chisel ... "Thanks ... What about you, Madoc?" he shrugs' is the player's invented line."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        paras = [
            '"I\'m just clearing the mud," Madoc replies.',
            'You take the chisel, feeling its weight in your hand. "Thanks. I\'ll use it well. What about you, '
            'Madoc? Any leads on a job around here?" he shrugs, a hint of a smile playing on his lips.',
        ]
        _kept, dropped = drop_invented_player_speech(paras, LINE)
        self.assertEqual(len(dropped), 1)
        self.assertIn("What about you, Madoc?", dropped[0])

    def test_voiced_request_with_a_name_stays(self):
        """Run 5 T51: 'ask Warin for a bed' voiced as 'You then ask, "Could you give me a bed ..., Warin?"' stays."""
        from app.narration_pipeline import drop_invented_player_speech

        line = ('"I never said that, and I don\'t know the ship\'s name." I leave the book with her again and ask '
                "Warin for a bed for tonight.")
        paras = [
            '"Suit yourself," Verity says.',
            'You turn to Warin. You then ask, "Could you give me a bed for the night, Warin?"',
        ]
        _kept, dropped = drop_invented_player_speech(paras, line)
        self.assertEqual(dropped, [])


class NotNamesNotTakes(unittest.TestCase):
    def test_some_is_not_a_person(self):
        from app.world import _figure_hints

        self.assertEqual(
            _figure_hints('"Building?" Madoc replies. "Some say it was a fine home." Some say the tide took it.',
                          ["Madoc Joliffe"]),
            [],
        )

    def test_salvage_as_an_answer_is_not_a_take(self):
        from app.llm import player_take_intent

        self.assertFalse(player_take_intent('"Salvage. I run the flats." I look around the passage.'))
        self.assertTrue(player_take_intent("I salvage the brass fittings."))


if __name__ == "__main__":
    unittest.main()
