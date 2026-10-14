"""7B run 30 (Qwen2.5 7B on MLE, agent as player): the player's words, menus and stock deliberation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LINE = ('"Morning. Moles in the flats? I run the flats every dry tide and I have never seen one out there." '
        'I step closer to the tannery door. "What are they getting into?"')
DRAFT = ('Morning, flat-runner, you say, stepping closer to the tannery door. Dunstan [[A]], the runner, looks up from '
         'his work. "Morning," he replies. "Moles in the flats? I run the flats every dry tide and I have never seen one '
         'out there." You ask, your curiosity piqued. "What are they getting into?"\n\nDunstan [[A]] chuckles. "The moles?"')


class UnquotedSpeechInThePlayersMouth(unittest.TestCase):
    """T1: 'Morning, flat-runner, you say, stepping closer to the tannery door.' shipped."""

    def test_dropped_act_kept(self):
        from app.narration_pipeline import keep_player_words

        out, changes = keep_player_words(DRAFT, LINE)
        self.assertNotIn("Morning, flat-runner, you say", out)
        self.assertTrue(out.startswith("You step closer to the tannery door."))
        self.assertIn("unquoted_player_speech_dropped", [c["action"] for c in changes])

    def test_a_missing_line_is_quoted_in_place(self):
        from app.narration_pipeline import keep_player_words

        text = ("Morning, Dunstan, you say, stepping up to the door. Dunstan looks up from his work and wipes his hands "
                "on a rag that has seen better years.")
        out, changes = keep_player_words(text, '"Morning, Dunstan." I step up to the door.')
        self.assertTrue(out.startswith("“Morning, Dunstan,” you say, stepping up to the door."), out)
        self.assertNotIn("missing_line_said", [c["action"] for c in changes])

    def test_narrated_asking_is_not_speech(self):
        from app.narration_pipeline import keep_player_words

        text = 'Inside, you ask the keeper what a cot costs. "Four gold," she says.'
        out, _changes = keep_player_words(text, '"What does a cot cost?"')
        self.assertIn("Inside, you ask the keeper what a cot costs.", out)


class PlayersLineNotGluedToTheReply(unittest.TestCase):
    """T1: the restored line sat right after '"Morning," he replies.' with a capital 'You ask'."""

    def test_own_paragraph_and_tag(self):
        from app.narration_pipeline import keep_player_words

        out, _changes = keep_player_words(DRAFT, LINE)
        self.assertIn('"Morning," he replies.\n\n"Morning. Moles in the flats?', out)
        self.assertIn('out there," you ask, your curiosity piqued.', out)


class MenusAndStockDeliberation(unittest.TestCase):
    """T1: 'You step back, pondering your next move.' and 'You could take him up on that offer, or ...' shipped."""

    BODY = ("Dunstan watches you, his eyes scanning the flats where the brine stain dries slowly in the sun, and the "
            "smell of salt and leather hangs over the tannery yard like a held breath. A cart rattles past the gate, "
            "its driver hunched against the wind, and two tannery hands argue by the vats over whose turn it is to "
            "scrape the next hide. Gulls wheel over the drying racks and shriek at nothing in particular. ")

    def test_menu_after_a_quote_and_mid_text(self):
        from app import llm

        text = (self.BODY + '"Need any help with the moles? They\'ve been worse than usual." You could take him up on '
                "that offer, or you could continue on your own. What do you do?")
        out, removed = llm._trim_menu_ending(text)
        self.assertNotIn("You could take him up", out)
        self.assertTrue(out.endswith('worse than usual."'), out)
        text = ("You can walk to the Ferret, where the roofer Oswin works, or continue toward the flats. " + self.BODY)
        self.assertNotIn("Ferret", llm._trim_menu_ending(text)[0])

    def test_what_stays(self):
        from app import llm

        for text in (
            self.BODY + "You pull it free and wipe the grime off, a piece of salvage you can use or sell.",
            self.BODY + "You can see the quay or the flats from here.",
            self.BODY + '"You could go, or you could stay," he says.',
        ):
            self.assertEqual(llm._trim_menu_ending(text)[0], text.rstrip())

    def test_ponder_clause(self):
        from app import llm

        out, _removed = llm._trim_menu_ending(self.BODY + "You step back, pondering your next move.")
        self.assertTrue(out.endswith("You step back."), out)


if __name__ == "__main__":
    unittest.main()
