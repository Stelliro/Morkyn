"""7B run 11 (Qwen2.5 7B on MLE, agent as player): invented walks end the scene; the player's lines keep their order."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

T1_LINE = (
    '"Morning. Not a traveller - I was born here." I nod toward the flats. '
    '"Heading out, yes. Is the yard posting any work today, or is it all private hauling?"'
)
T1_PROSE = (
    '"Morning," you reply, your voice carrying a tone of ease. "Not a traveller - I was born here." You nod toward '
    'the flats. "Heading out, yes. Is the yard posting any work today, or is it all private hauling?"\n\n'
    'Iseult Pennick ponders your question for a moment, her gaze shifting to the stable door. "Well, it\'s quiet '
    "today, but there's always work to be done. You might check the notice board by the inn, though; folks there "
    'often post work for the flats."\n\n'
    "You thank her and walk over to the inn, the morning breeze rustling the leaves of the nearby willow tree. The "
    "notice board, a weathered wooden sign, hangs on the wall by the front door."
)
T2_LINE = (
    'I stay where I am by the stable. "The notice board by the inn, then. Which inn, Iseult - there are three in '
    'this town and they all lie."'
)
T2_PROSE = (
    'You stay where you are by the stable. "The notice board by the inn, then. Which inn, Iseult - there are three '
    'in this town and they all lie."\n\n'
    'Iseult Pennick nods, her eyes thoughtful. "The Leaning Spindle, The Pear at Saltmarrow, or The Crooked Plough. '
    "I've heard the Spindle's board is the least likely to be full of lies, but that's just the talk of the town.\"\n\n"
    "You thank her and head towards the Leaning Spindle, the inn you heard is least likely to be filled with deceit. "
    "As you approach, the sign creaks in the light breeze, inviting you inside.\n\n"
    "You make your way to the board that hangs above the fireplace. You read the details aloud: \"Lifting supplies "
    'to the upper levels of the market hall. They need a strong back."'
)


class InventedWalksEndTheScene(unittest.TestCase):
    def test_stay_put_then_a_walk_to_the_inn(self):
        """T2: 'I stay where I am' and the prose walked her into the Leaning Spindle."""
        from app.llm import _scene_cut_point

        point = _scene_cut_point(T2_PROSE, T2_LINE)
        self.assertIsNotNone(point)
        self.assertEqual(point["family"], "movement")
        self.assertTrue(point["trigger"].startswith("You thank her and head towards the Leaning Spindle"))
        self.assertTrue(T2_PROSE[: point["cut"]].rstrip().endswith('talk of the town."'))

    def test_heading_out_does_not_cover_a_walk_to_the_inn(self):
        """T1: 'Heading out, yes' (to the flats) did not ask for the inn Iseult suggested."""
        from app.llm import _scene_cut_point

        point = _scene_cut_point(T1_PROSE, T1_LINE)
        self.assertIsNotNone(point)
        self.assertTrue(point["trigger"].startswith("You thank her and walk over to the inn"))
        self.assertIn("notice board by the inn", point["npc_line"])

    def test_walks_the_player_asked_for(self):
        from app.llm import _walk_asked

        self.assertTrue(_walk_asked("walk over to the inn.", "I walk over to the inn to find Madoc."))
        self.assertTrue(_walk_asked("leave the Salvage Yard and head north.", "I walk to the old cottage near the docks."))
        self.assertTrue(_walk_asked("step outside to judge the tide.", "Then I step outside and look at the sky."))
        self.assertTrue(_walk_asked("walk with her to the inn.", "I follow Iseult."))
        self.assertTrue(_walk_asked("head towards the notice board.", "I head for the salvage yard to see what is posted."))
        self.assertFalse(_walk_asked("walk over to the inn.", 'I nod toward the flats. "Heading out, yes."'))
        self.assertFalse(_walk_asked("make your way to the board.", "I stay where I am by the stable."))

    def test_back_to_work_is_not_a_walk(self):
        """Run 5, T55: 'you return to the task at hand' cut away Warin handing over the coin."""
        from app.llm import _invented_unit_family

        line = '"Ten gold for the lot. Done." I push the fittings across the desk and hold out my hand for the coin.'
        own = line
        self.assertEqual(_invented_unit_family("You return to the task at hand, ready to begin.", own, line), "")


class ReadAloudIsSpeech(unittest.TestCase):
    def test_reading_a_posting_aloud_is_the_players_line(self):
        from app.narration_pipeline import drop_invented_player_speech

        kept, spoken = drop_invented_player_speech(
            [
                "The interior of the Leaning Spindle is dim and cozy, with a fire crackling in the hearth.",
                'You read the details aloud: "Lifting supplies to the upper levels of the market hall."',
            ],
            T2_LINE,
        )
        self.assertEqual(len(spoken), 1, kept)
        self.assertIn("Lifting supplies", spoken[0])


class PlayerLinesKeepTheirOrder(unittest.TestCase):
    def test_missing_line_goes_after_the_line_typed_before_it(self):
        """T1: 'Heading out, yes ...' was put before 'Morning. Not a traveller ...'."""
        from app.narration_pipeline import keep_player_words

        text = (
            'Iseult greets you. "Not a traveller, then," she says. "Heading out, yes. Is the yard posting any work '
            'today, or is it all private hauling?" she adds.\n\n'
            '"Morning," you reply, your voice easy. "Not a traveller - I was born here." You nod toward the flats.'
        )
        fixed, changes = keep_player_words(text, T1_LINE)
        self.assertIn("Morning,", fixed)
        first = fixed.index("Not a traveller - I was born here.")
        second = fixed.index("Heading out, yes.")
        self.assertLess(first, second)
        self.assertNotIn("invented_line_replaced", [c["action"] for c in changes])


if __name__ == "__main__":
    unittest.main()
