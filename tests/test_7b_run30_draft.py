"""7B run 30, T7 (Qwen2.5 7B on MLE, agent as player): a degenerate draft about moles, repaired narrowly."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = ('"I have not told you my name, mole catcher." I set the next trap at the second tunnel mouth and tamp '
        'the earth flat with my palm.')


class ParaphrasedQuoteGoes(unittest.TestCase):
    """'You have not shared your name, mole catcher.' restated the typed line as narration."""

    def test_dropped(self):
        from app.narration_pipeline import keep_player_words

        text = ('“I have not told you my name, mole catcher,” you say. You have not shared your name, mole '
                'catcher. The rain drips from the eaves.')
        out, changes = keep_player_words(text, LINE)
        self.assertNotIn("You have not shared your name", out)
        self.assertIn("echoed_quote_paraphrase_dropped", [c["action"] for c in changes])

    def test_narration_without_the_vocative_stays(self):
        from app.narration_pipeline import _paraphrased_quote

        quotes = ["I have not told you my name, mole catcher."]
        self.assertFalse(_paraphrased_quote("You have not shared your name with anyone here.", quotes))
        self.assertFalse(_paraphrased_quote("He nods at the mole catcher.", quotes))


class TheActIsThePlayers(unittest.TestCase):
    """'He tamps the earth flat with his palm' for the player's typed 'tamp the earth flat with my palm'."""

    def test_given_back(self):
        from app.narration_pipeline import keep_player_words

        text = ('“I have not told you my name, mole catcher,” you say. Dunstan [[A]] watches as you, setting '
                'the next trap at the second mouth of the second burrow. He tamps the earth flat with his palm, '
                'ensuring the trap is secure.')
        out, _changes = keep_player_words(text, LINE)
        self.assertIn("You tamp the earth flat with your palm, ensuring the trap is secure.", out)
        self.assertIn("watches as you set the next trap", out)

    def test_working_beside_stays(self):
        from app.narration_pipeline import keep_player_words

        text = ('“I have not told you my name, mole catcher,” you say. You set the next trap at the second '
                'tunnel mouth. Dunstan sets another trap beside yours at the second tunnel mouth.')
        out, _changes = keep_player_words(text, LINE)
        self.assertIn("Dunstan sets another trap beside yours", out)


class NoClawsOnAHuman(unittest.TestCase):
    def test_dropped_for_human_only(self):
        from app.prose_state import repair_player_body

        text = ("You dig at the earth with your claws. You wrap the scrolls in your shirt tail. "
                + "The rain runs off the planks and the rope creaks against the post. " * 4)
        out, fixes = repair_player_body(text, "human")
        self.assertNotIn("your claws", out)
        self.assertIn("your shirt tail", out)
        self.assertEqual(len(fixes), 1)
        self.assertEqual(repair_player_body(text, "ratfolk")[1], [])


class CutWordInAQuote(unittest.TestCase):
    def test_fragment_goes(self):
        from app.prose_state import repair_cut_word_in_quote

        out, _ = repair_cut_word_in_quote('"If we don\'t get them soon, they\'ll start eating through the t." He fetches a trap.')
        self.assertIn('"If we don\'t get them soon, they\'ll start eating through." He fetches a trap.', out)
        for kept in ('"What does Madoc know that the reckoner doesn\'t?"', '"Plan B."', '"I\'ll take a."'):
            self.assertEqual(repair_cut_word_in_quote(kept), (kept, []))


class TimeToMakeAMove(unittest.TestCase):
    def test_closer_goes(self):
        from app import llm

        text = ("You can feel the tension in the tannery, the sound of moles underground. " * 6) + "It's time to make a move."
        out, count = llm._drop_menu_sentences(text, floor=0)
        self.assertEqual(count, 1)
        self.assertNotIn("time to make a move", out)
        kept = "It's time to make a move on the tide tables before the reeve closes."
        self.assertEqual(llm._drop_menu_sentences(kept, floor=0)[1], 0)


class CutAtTheQuestionAfterAWalk(unittest.TestCase):
    """T14: 'then make your way to the first of the traps' was not seen as the going, so no cut at Dunstan's question."""

    def test_cut(self):
        from app import llm

        line = "I give it a while longer, then go and check the first trap by the brine vats to see whether it has sprung."
        text = (
            "You give it a while longer, then make your way to the first of the traps by the brine vats. The tannery is "
            "quiet, the moles' movements barely audible. You approach the first mechanism, a simple wooden lever near "
            "the vats. Nothing happens, but you can feel the tension in the air.\n\n"
            "Dunstan, your local informant, looks up from his work in the storeroom. \"You sure you want to check that, "
            "Isk? The moles are known to avoid the brine vats.\"\n\n"
            "You nod, ignoring the hint. \"Just being cautious, Dunstan.\"\n\n"
            "Dunstan grunts and returns to his work.\n\n"
            "Dunstan looks up as you re-enter. \"Well, you were thorough. The rest of the traps?\""
        )
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": x} for x in text.split("\n\n")]}
        out = llm._cut_scene_at_invented_request(turn, line, earlier=[])
        self.assertTrue(out["narration"].endswith("The moles are known to avoid the brine vats.\""))
        self.assertNotIn("grunts", out["narration"])


class NarratorInTheFirstPerson(unittest.TestCase):
    """T15: 'You wipe my hands on my trousers.' and 'I nod and turn to leave, the sense of duty guiding me.'"""

    LINE = ('"Nothing in either trap yet." I wipe my hands on my trousers. "Dunstan, I will come back at dusk to '
            'check them. Where do I find you then?"')

    def test_echoed_act_turns_whole(self):
        from app.narration_pipeline import keep_player_words

        out, _ = keep_player_words("Nothing in either trap yet. I wipe my hands on my trousers. The vats steam.", self.LINE)
        self.assertIn("You wipe your hands on your trousers.", out)

    def test_voice_and_walk(self):
        from app import llm

        text = (
            "“Nothing in either trap yet.” You wipe your hands on your trousers. \"Dunstan, I will come back at "
            "dusk to check them. Where do I find you then?\"\n\n"
            "Dunstan scratches his beard. \"The tannery is where the moles are causing trouble. I'll be there.\"\n\n"
            "The storeroom is a small, dimly lit space filled with wooden crates and sacks. The brine vats loom in the "
            "corner, their surfaces reflecting the faint light.\n\n"
            "The tannery is only a short walk from here. I nod and turn to leave, the sense of duty guiding me."
        )
        turn = {"narration": text, "narration_segments": [{"label": "paragraph", "text": x} for x in text.split("\n\n")]}
        out = llm._drop_player_overreach(turn, self.LINE, "test", [], {})
        self.assertNotIn("turn to leave", out["narration"])
        self.assertNotIn("guiding me", out["narration"])

    def test_speech_and_names_stay(self):
        from app.narration_pipeline import narrator_voice_to_second_person

        line = '"Morning."'
        for text in ('"Ah," she says with a smile. I can help you with that."',
                     "I'll fetch more traps from the storeroom.",
                     "You pass My Lady's Rest on the corner."):
            self.assertEqual(narrator_voice_to_second_person(text, line)[1], [], text)


if __name__ == "__main__":
    unittest.main()
