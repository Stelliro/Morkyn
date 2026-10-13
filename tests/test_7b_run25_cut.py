"""7B runs 24-25: the scene ends when the player's act is done and the prose walks them on."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ROPE_LINE = ('"Yes, I\'ll take it at that price. That\'s what the coin on your counter is for." '
             "I pick up the rope and coil it over my shoulder.")
ROPE_PROSE = (
    "“Yes, I'll take it at that price. That's what the coin on your counter is for,” you say. You pick up the "
    "rope and coil it over your shoulder, the rope tested in the worst storms, a deal done. Katerine nods, her voice low "
    "and confident as she says, \"It's a good price, and a fair one.\"\n\n"
    "\"Thank you,\" Katerine says, her eyes meeting yours for a moment before she returns to her work. The chandler "
    "continues her tasks, the sound of her scraping and sorting filling the small store.\n\n"
    "You step back onto the edge of the flat, the salty breeze of the coast blowing against your face. You take a deep "
    "breath, ready to face whatever comes next."
)
SHIP_LINE = '"I\'ll find her myself, thanks." I climb out of the hold and walk along the dock looking for a ship called the Black Raven.'
SHIP_PROSE = (
    "You climb out of the hold and walk along the dock, searching for a ship called the Black Raven. The salty air "
    "carries the distant sound of waves and the occasional shout from a fisherman. You see a ship moored at the dock, "
    "just outside the bustling harbor. You can tell by the crest of the Old Harbor visible on the ship's flag.\n\n"
    "You continue your search, your footsteps echoing softly on the dock. The Black Raven looms ahead, its sails hanging "
    "limply from its mast. You climb aboard and step into the hold, where the cargo is stacked high. You take the crate "
    "and walk back to the dock."
)


class AfterTheActTheSceneEnds(unittest.TestCase):
    def _cut(self, prose, line):
        from app import llm

        turn = {"narration": prose, "narration_segments": [{"label": "paragraph", "text": p} for p in prose.split("\n\n")]}
        return llm._cut_scene_after_completed_act(turn, line)

    def test_rope_bought_then_walked_off(self):
        out = self._cut(ROPE_PROSE, ROPE_LINE)
        self.assertEqual(out["_scene_cut"]["family"], "after_act")
        self.assertNotIn("step back onto the edge", out["narration"])
        self.assertIn("You pick up the rope", out["narration"])
        self.assertIn('"Thank you,"', out["narration"])

    def test_ship_found_then_boarded(self):
        out = self._cut(SHIP_PROSE, SHIP_LINE)
        self.assertEqual(out["_scene_cut"]["family"], "after_act")
        self.assertTrue(out["narration"].endswith("its sails hanging limply from its mast."), out["narration"][-120:])
        self.assertNotIn("You take the crate", out["narration"])

    def test_own_walk_continuing_is_not_cut(self):
        from app import llm

        line = "I'm out on the coast road. I put the key on a string and start walking back toward Saltmarrow."
        prose = ("You put the key on a string around your neck, the brass cold against your skin. The coast road is "
                 "empty at this hour, the gulls loud over the flats and the light thin and grey on the water. You walk "
                 "eastward, the road stretching ahead under the growing sunlight.")
        self.assertIsNone(llm._completion_cut_point(prose, line))

    def test_stepping_back_in_place_is_not_a_move(self):
        from app import llm

        line = "I finish the last of the pile and carry the pieces over to Oldfield."
        prose = ("You finish the last of the pile and carry the pieces over to Oldfield, who turns each one over in "
                 "his hands with a grunt. The sorting shed is quiet, the steady hum of the early hour still lingering "
                 "in the misty air around the heaps. You step back to observe, letting Oldfield inspect them. "
                 "You step back, feeling the weight of the morning in your arms.")
        self.assertIsNone(llm._completion_cut_point(prose, line))

    def test_a_question_put_to_her_defers(self):
        from app import llm

        prose = ROPE_PROSE.replace('"Thank you," Katerine says', '"Anything else?" Katerine asks')
        self.assertIsNone(llm._completion_cut_point(prose, ROPE_LINE))


if __name__ == "__main__":
    unittest.main()
