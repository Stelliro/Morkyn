"""Player words and prose leaks from the sixth Saltmarrow run on Qwen2.5 7B (MLE), the player played by an agent."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.narration_pipeline import drop_invented_player_speech, keep_player_words  # noqa: E402


class CodesAreNotSaid(unittest.TestCase):
    """T4, T9, T10: '..., Oldfield [[B]]. What's it pay?' inside Isk's own words."""

    LINE = '"Sorting rags won\'t pay my debt, Oldfield. What\'s it pay?" I lean on the edge of his table.'

    def test_a_code_is_not_a_reworded_line(self):
        text = 'You lean on the table. "Sorting rags won\'t pay my debt, Oldfield [[B]]. What\'s it pay?"'
        out, changes = keep_player_words(text, self.LINE)
        self.assertNotIn("reworded_line_restored", [c["action"] for c in changes])
        self.assertIn("\"Sorting rags won't pay my debt, Oldfield. What's it pay?\"", out)
        self.assertEqual([c["action"] for c in changes], ["code_taken_out_of_player_line"])

    def test_no_code_is_added_inside_speech(self):
        from app.llm import _repair_prose_entity_labels

        out = _repair_prose_entity_labels(
            'Oldfield looks up. "Sorting rags won\'t pay my debt, Oldfield." Oldfield nods.', {"B": "Oldfield"}
        )
        self.assertIn('"Sorting rags won\'t pay my debt, Oldfield."', out)
        self.assertIn("Oldfield [[B]] looks up", out)


class SplitLineGoesWhole(unittest.TestCase):
    """T2: '"Salvagers, Isk," he says, ... "From where? Not ours, then."' left '"Salvagers," he says'."""

    def test_both_halves_go(self):
        text = (
            "Simon Pennick stands beside you, his arms folded. \"Salvagers, Isk,\" he says, his voice a low, "
            "matter-of-fact tone. \"From where? Not ours, then.\" You turn to him. \"Who's paying them, Simon? "
            "Somebody always is.\""
        )
        line = "\"Salvagers from where? Not ours, then.\" I glance out. \"Who's paying them, Simon? Somebody always is.\""
        out, changes = keep_player_words(text, line)
        self.assertNotIn("Salvagers, Isk", out)
        self.assertNotIn("he says", out)
        self.assertTrue(out.startswith("“Salvagers from where? Not ours, then,” you ask."))
        self.assertIn("arms folded. You turn to him.", out)
        self.assertEqual(changes[0]["action"], "line_taken_from_other_speaker")

    def test_an_unrelated_line_before_stays(self):
        text = (
            "\"Morning, Isk,\" Simon says. \"Salvagers from where? Not ours, then.\" He shrugs."
        )
        out, _ = keep_player_words(text, "\"Salvagers from where? Not ours, then.\"")
        self.assertIn('"Morning, Isk," Simon says.', out)


class AnsweringThePersonWhoSpoke(unittest.TestCase):
    """T9: '"Thanks, Oldfield."' after Oldfield's line, never typed by the player."""

    LINE = 'I follow Oldfield to the door. "Oldfield. Two gold, by noon, we said."'

    def test_invented_thanks_goes(self):
        paras = ['Oldfield [[B]] gives you a nod of approval. "Well, you\'ve earned this."', '"Thanks, Oldfield [[B]]."']
        kept, dropped = drop_invented_player_speech(paras, self.LINE)
        self.assertEqual(dropped, ['"Thanks, Oldfield [[B]]."'])
        self.assertEqual(kept[1], "")

    def test_a_line_to_someone_only_spoken_about_stays(self):
        paras = ["Oldfield turns to Isolde.", '"Get back to work, Isolde."']
        kept, dropped = drop_invented_player_speech(paras, 'I wait. "Fine."')
        self.assertEqual(dropped, [])

    def test_the_players_own_words_stay(self):
        paras = ['Oldfield nods. "Done, then."', '"Two gold, by noon, Oldfield."']
        kept, dropped = drop_invented_player_speech(paras, '"Two gold, by noon." I wait.')
        self.assertEqual(dropped, [])


class SceneEndsOnTheQuestion(unittest.TestCase):
    """T7: the scene answered Oldfield's question for the player and left '"Good," Oldfield nods.'"""

    def test_cut_when_the_going_is_shown(self):
        from app.llm import _cut_scene_at_invented_request

        text = (
            "You walk over to the large, open sorting shed where salvaged materials are piled high. You begin "
            "sorting the materials into three piles: one for the metals, one for the wooden pieces, and a heap of "
            "rags by the wall.\n\nOldfield approaches, his steps deliberate and measured. \"You're doing well,\" "
            "he says, a hint of approval in his tone. \"How are you finding the job?\"\n\nYou explain your progress, "
            "pointing to the piles you've created. \"I think we should have this sorted by noon,\" you say.\n\n"
            "\"Good,\" Oldfield nods. \"If it's done by then, you'll have your gold.\""
        )
        line = "I go to the pile and start sorting: metal on the left, wood on the right, rags in a heap by the wall."
        turn = _cut_scene_at_invented_request({"narration": text, "self_check": {}}, line)
        self.assertTrue(turn["narration"].endswith('"How are you finding the job?"'))
        self.assertIn("_scene_cut", turn)

    def test_no_cut_when_the_going_is_not_shown(self):
        from app.llm import _cut_scene_at_invented_request

        text = (
            "Oldfield looks up from his ledger. \"Heading out? Where to?\" he asks, studying the board for a long "
            "while before he looks back at you with tired eyes.\n\n\"The harbour,\" you say. You cross the flats "
            "to the harbour, where the boats lie on their sides in the mud."
        )
        turn = _cut_scene_at_invented_request({"narration": text}, "I go to the harbour.")
        self.assertNotIn("_scene_cut", turn)


class MetaAndQuotes(unittest.TestCase):
    def test_scene_ends_closer(self):
        from app.prose_state import repair_meta_leaks

        out, fixes = repair_meta_leaks(
            'Oldfield nods. "Deal."\n\nThe scene ends with you standing in the town square, the deal made and the clock ticking.'
        )
        self.assertEqual(out, 'Oldfield nods. "Deal."')
        self.assertEqual(fixes[0]["why"], "stage_direction")

    def test_doubled_closing_quote(self):
        from app.prose_state import repair_meta_leaks

        out, fixes = repair_meta_leaks('He smiles. "Well, you\'ve earned this."\n\n"Thanks, Oldfield.""')
        self.assertTrue(out.endswith('"Thanks, Oldfield."'))
        self.assertEqual(fixes[0]["why"], "doubled_quote")

    def test_scene_words_in_the_story_stay(self):
        from app.prose_state import repair_meta_leaks

        text = "The scene below the cliff ends in a tangle of rope and spars."
        self.assertEqual(repair_meta_leaks(text), (text, []))


class WeatherIsAChangeNotAMorning(unittest.TestCase):
    """T5: 'Weather shifts to Steady fog.' restarted the scene as a fresh morning."""

    def test_the_ask_says_what_weather_announce_is(self):
        from app.prompts import _scene_instruction

        text = _scene_instruction("player_action", {}, checking=False)
        self.assertIn("weather_announce is present, the weather turns during this scene", text)
        self.assertIn("not a new day or a new scene", text)


if __name__ == "__main__":
    unittest.main()
