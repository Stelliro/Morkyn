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


class CommonWordsAreNotNames(unittest.TestCase):
    """Run 22 T0: "Inside, the scent of bread ..." stored a person called Inside, job "scent"."""

    def test_skipped(self):
        from app.world import _introduced_people

        self.assertEqual(_introduced_people("Inside, the scent of bread hangs thick.", []), [])
        self.assertEqual(
            [p["name"] for p in _introduced_people("Inside, the scent hangs. Elias Fairweather, the miller, waits.", [])],
            ["Elias Fairweather"],
        )


class AJobNamedSomeone(unittest.TestCase):
    """Run 23 T0: "A bell ringer named Clemence Skinner stands near the mill" stored nobody."""

    def test_read(self):
        from app.world import _introduced_people

        self.assertEqual(
            _introduced_people("A bell ringer named Clemence Skinner stands near the mill.", []),
            [{"name": "Clemence Skinner", "role": "bell ringer"}],
        )
        self.assertEqual(_introduced_people("A grizzled man named Rusk greets you.", []), [{"name": "Rusk", "role": ""}])


class JobThenName(unittest.TestCase):
    """Run 23 T1: "The mill's bell ringer, Esme Larkin, stands ..." stored a drawn Yolande instead."""

    def test_read(self):
        from app.world import _introduced_people

        self.assertEqual(
            _introduced_people("The mill's bell ringer, Esme Larkin, stands at the edge of the mill pond.", []),
            [{"name": "Esme Larkin", "role": "bell ringer"}],
        )


class AnswerInTheSecondSentence(unittest.TestCase):
    """Run 23 T1: '"Not since the storm. I've been tracking the tides ..."' answered the bell ringer for Isk."""

    def test_dropped(self):
        from app.narration_pipeline import drop_invented_player_speech

        line = 'I walk over to the bell ringer. "Morning. Any word on when the water turns today?"'
        paras = [
            'Esme looks up. "The tide should turn around noon. Have you been out on the flats recently?"',
            '"Not since the storm. I\'ve been tracking the tides."',
            "Esme nods thoughtfully.",
        ]
        self.assertEqual(len(drop_invented_player_speech(paras, line)[1]), 1)


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


class FreeingIsTaking(unittest.TestCase):
    """Run 17 T4: "working the rusted iron loose with both hands" refused the iron as taken unasked."""

    def test_take_intent(self):
        from app.llm import player_take_intent

        self.assertTrue(player_take_intent("I try again, working the rusted iron loose with both hands."))
        self.assertTrue(player_take_intent("I pry the board free."))
        self.assertFalse(player_take_intent("I pull myself free of the mud."))


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
