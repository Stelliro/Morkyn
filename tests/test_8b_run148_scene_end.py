"""8B run 148, T60: the scene ends on the line spoken to the player, not after a walk made for them.

"Then I'll see the guildmaster. Where does he sit, and what's his name?" was
answered by Griselda's directions, and the prose then had "you" step toward
the storage room and meet the guildmaster. A step toward somewhere the line
never asked to go is a move made for the player; the scene ends on her line.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run148_scene_end
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = "\"Then I'll see the guildmaster. Where does he sit, and what's his name?\""
PROSE = (
    "“Then I'll see the guildmaster. Where does he sit, and what's his name?” you ask. Griselda Kemp [[B]]’s fingers "
    "drummed the desk as she glanced up from the records. \"The master’s office is through the hall, past the storage "
    "room. You’ll find it at the end of the corridor.\" She hesitated, then added, \"He’s not one for pleasantries. Say "
    "what you need to say quickly.\"\n\nYou step toward the storage room, the creak of the door echoing through the Tally "
    "House. Inside, the smell of old parchment and sea brine clings to the walls. A figure emerges from the shadows — a "
    "man with a weathered face and a scar running from his temple to his jaw. \"Ah, the flat-runner. I was told you’d be "
    "coming.\" His voice is low and gravelly. \"I’m Master Varrin. You’re here about the Stormbreaker, I presume.\""
)


class AStepMadeForThePlayer(unittest.TestCase):
    def test_the_step_toward_the_storage_room_is_a_move(self):
        from app.llm import _invented_unit_family, player_line_of

        own = player_line_of(LINE)
        self.assertEqual(_invented_unit_family(
            "You step toward the storage room, the creak of the door echoing through the Tally House.", own, LINE), "movement")

    def test_the_scene_ends_on_griseldas_line(self):
        from app.llm import _scene_cut_point

        point = _scene_cut_point(PROSE, LINE)
        self.assertIsNotNone(point)
        self.assertTrue(point["trigger"].startswith("You step toward the storage room"), point)
        self.assertIn("Say what you need to say quickly", point["npc_line"])

    def test_a_step_the_line_asked_for_is_kept(self):
        from app.llm import _invented_unit_family, player_line_of

        line = "I step toward the counter and ask the clerk for the ledger."
        self.assertEqual(_invented_unit_family("You step toward the counter, boots loud on the boards.", player_line_of(line), line), "")


if __name__ == "__main__":
    unittest.main()
