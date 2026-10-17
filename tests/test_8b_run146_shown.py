"""8B run 146, T51 and T53: a new place or person the prose never shows is not stored.

T53: "There is no sign of Rolf Joliffe" and the player's own call for him
minted Rolf at the stream nobody answered from; a name with an absence before
it ("no sign of", "looking for", "not") or after it ("is not here", "never
answers") is said of someone who is not in the scene.

T51: LOC_NEW "The Bridge at the Hollow" was stored while the prose walked a
muddy trail and the turn's move went elsewhere; a new place neither the prose
nor the player names, that the turn does not travel to, is not stored.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run146_shown
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.world import _named_as_present, _new_place_shown  # noqa: E402


def present(text: str, name: str) -> bool:
    return _named_as_present(text, r"(?<!\w)" + re.escape(name) + r"(?!\w)", flags=re.I)


class ANameSaidOfSomeoneAbsent(unittest.TestCase):
    def test_no_sign_of_him_is_not_him_here(self):
        prose = ("The words echo, swallowed by the wind. No answer comes. There is no sign of Rolf Joliffe, "
                 "no sign of anyone else.")
        self.assertFalse(present(prose, "Rolf Joliffe"))

    def test_calling_out_for_him_is_not_him_here(self):
        self.assertFalse(present("Your voice cuts through the quiet, calling out to Rolf Joliffe, and no one answers.", "Rolf Joliffe"))
        self.assertFalse(present("You wait for Mira by the well until the light goes.", "Mira"))

    def test_not_here_after_the_name_is_absence(self):
        self.assertFalse(present("Rolf Joliffe is not here. The well is dry.", "Rolf Joliffe"))
        self.assertFalse(present("Mira isn't there when you look up.", "Mira"))

    def test_someone_who_acts_is_here(self):
        self.assertTrue(present("Rolf Joliffe steps out of the trees, a bucket in his hand.", "Rolf Joliffe"))
        self.assertTrue(present("You wait for Mira by the well. Mira arrives late, out of breath.", "Mira"))
        # "is not pleased" is a mood, not an absence.
        self.assertTrue(present("Hargrave is not pleased with the price.", "Hargrave"))

    def test_an_absent_mention_and_a_present_one_count_as_here(self):
        self.assertTrue(present("There is no sign of Rolf at first. Then Rolf steps from the shadows.", "Rolf"))


class APinTheStoryContradicts(unittest.TestCase):
    """8B run 146, T82: Elara, pinned "he", was written "her fingers", "her face", "she says" all turn."""

    T82 = ("Elara Veyne [[J]]’s gaze sharpens as you speak, her fingers tightening around the rope of her cloak. "
           "The Mire’s Breath is a place of whispers, and she knows the weight of those who cross it. "
           "\"You think the Drowned Hand will stop at a ship?\" she says, her tone low. "
           "Elara’s expression shifts, a flicker of uncertainty crossing her face.")

    def test_two_named_sentences_in_the_other_set_and_none_in_the_pin(self):
        from app.prose_state import pronoun_evidence

        self.assertEqual(pronoun_evidence(self.T82, ["Elara Veyne", "Elara"]), {"he": 0, "she": 2})

    def test_a_mixed_sentence_counts_for_neither(self):
        from app.prose_state import pronoun_evidence

        text = "Rolf nods at Elara, his hand on her shoulder. Elara says nothing."
        self.assertEqual(pronoun_evidence(text, ["Elara"]), {"he": 0, "she": 0})

    def test_speech_is_not_evidence(self):
        from app.prose_state import pronoun_evidence

        text = "\"She told me herself,\" Rolf says of Elara. Rolf shrugs, his eyes on the sea."
        self.assertEqual(pronoun_evidence(text, ["Rolf"]), {"he": 1, "she": 0})


class ANewPlaceTheTurnNeverShows(unittest.TestCase):
    PROSE = ("The unmarked trail east is narrow, packed with mud that clings to your boots. You count your paces. "
             "The Flats [[L7]] stretch out behind you.")

    def test_a_place_in_neither_prose_nor_line_nor_move_is_not_shown(self):
        result = {"player": {"move_to_location": "The Mire's Breath"}}
        self.assertFalse(_new_place_shown("The Bridge at the Hollow", self.PROSE, "I take the unmarked trail east.", result, {"destination": ""}))

    def test_the_prose_naming_it_shows_it(self):
        prose = "You stop at the edge of the clearing, your breath catching as you see the well."
        self.assertTrue(_new_place_shown("The clearing", prose, "I follow the stream.", {"player": {}}, {}))

    def test_the_players_line_naming_it_shows_it(self):
        self.assertTrue(_new_place_shown("Harbour Reeve's Office", "You knock.", "I go to the harbour reeve's office.", {"player": {}}, {}))

    def test_the_turns_move_going_there_shows_it(self):
        self.assertTrue(_new_place_shown("Shore Road", "You walk on.", "I head out.", {"player": {"move_to_location": "Shore Road"}}, {}))
        self.assertTrue(_new_place_shown("Shore Road", "You walk on.", "I head out.", {"player": {}}, {"destination": "Shore Road"}))


if __name__ == "__main__":
    unittest.main()
