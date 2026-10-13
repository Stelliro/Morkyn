"""7B run 16 (Qwen2.5 7B on MLE, agent as player): the player is not introduced, shop names off jobs, stray codes."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class ThePlayerIsNotAPerson(unittest.TestCase):
    """T0: "You are Isk Tarrow, the flat-runner" stored Isk as an NPC (a regression from run 14's fix)."""

    def test_you_are(self):
        from app.world import _introduced_people

        self.assertEqual(_introduced_people("You are Isk Tarrow, the flat-runner, and the tide is low.", []), [])

    def test_player_name_known(self):
        from app.world import _introduced_people

        self.assertEqual(_introduced_people("Isk Tarrow, the flat-runner, looks out.", ["Isk Tarrow"]), [])


class NamesAndCodes(unittest.TestCase):
    """T0: 'Dunstan Upcott [[A]] [[D1]]', 'Quarrel and Sons [[Quarrel and Sons]]', role 'grocer Quarrel and Sons'."""

    def test_prose(self):
        from app.llm import _repair_prose_entity_labels as repair

        self.assertEqual(
            repair("A grocer, Dunstan Upcott [[A]] [[D1]], stands outside his shop, Quarrel and Sons [[Quarrel and Sons]], sorting.",
                   {"L1": "Saltmarrow", "A": "Dunstan Upcott"}),
            "A grocer, Dunstan Upcott [[A]], stands outside his shop, Quarrel and Sons, sorting.",
        )
        self.assertEqual(repair("You meet [[Bertram Yates]] at the gate.", {}), "You meet Bertram Yates at the gate.")
        # Run 17 T0: a known name with a code nothing holds takes its own code.
        self.assertEqual(
            repair("Hereward Treloar [[H1]] pauses.", {"A": "Hereward Treloar"}), "Hereward Treloar [[A]] pauses."
        )

    def test_role(self):
        from app.turn_dsl import parse_dsl_turn

        npcs = parse_dsl_turn('===NAR===\nX.\n===OPS===\nNPC_NEW "Dunstan Upcott" "grocer Quarrel and Sons" "L1"')["npcs"]
        self.assertEqual((npcs[0]["role"], npcs[0]["summary"]), ("grocer", "works at Quarrel and Sons"))
        npcs = parse_dsl_turn('===NAR===\nX.\n===OPS===\nNPC_NEW "Oriel Rendle" "rag picker" "L1"')["npcs"]
        self.assertEqual(npcs[0]["role"], "rag picker")


class WordsEchoInYourMind(unittest.TestCase):
    """Run 17 T2: the player's line came back as "Hereward Treloar's words echo in your mind: ..."."""

    def test_line_is_the_players_again(self):
        from app.narration_pipeline import keep_player_words

        line = '"Keep your splints handy, then. The flats ate three hauling carts last month." I walk out onto the flats.'
        text, _changes = keep_player_words(
            "You step out onto the flats. Hereward Treloar [[A]]'s words echo in your mind: "
            '"Keep your splints handy, then. The flats ate three hauling carts last month."\n\n'
            'Hereward calls out, "Salvage again, I see."',
            line,
        )
        self.assertNotIn("echo in your mind", text)
        self.assertIn("last month,” you say.", text)


if __name__ == "__main__":
    unittest.main()
