"""Pronoun pins and their repair do less harm (fault log F59, F119 and its continuations).

F59 (8B run 146, T39): Elara Veyne was pinned "he" when she was named only in
the player's quoted question and the ferry captain's "his desk" came next. Every
later "her" was then mended to "his".

F119 (8B runs 149 and 150): the repair rewrote someone else's pronouns because
the pinned person was in the sentence: "Lettice's gaze flicks to him" (Hugh),
"You call out to him" (Rafe) with Mabel named later, and "Her gaze flicked
between you and Rafe" (Mabel's) made Rafe's.

The pin now comes from the majority of the sentences about the person and waits
on a tie or a near split; the repair only mends pronouns after the pinned name,
in a sentence that names no one else, and leaves the rest as written.

Run:  .venv\\Scripts\\python -m unittest tests.test_pronoun_pins_do_less_harm
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prose_state import repair_pinned_pronouns  # noqa: E402
from app.world import infer_npc_pronouns  # noqa: E402


class ThePinFollowsTheMajority(unittest.TestCase):
    def test_a_name_only_in_the_players_question_pins_nothing(self):
        prose = (
            "You look up from the ledger at Hamon Lockwood [[I]]. \"Who is Elara Veyne, and where would I find "
            "her?\" you ask. The ferry captain leans back, the candle on his desk casting long lines across the "
            "room. He exhales, a slow, measured breath."
        )
        self.assertEqual(infer_npc_pronouns("Elara Veyne", prose, ["Hamon Lockwood"]), "")

    def test_a_role_figure_after_the_name_is_not_their_pronoun(self):
        prose = "Elara Veyne waits at the end of the pier. The old ferryman spits, wiping his mouth."
        self.assertEqual(infer_npc_pronouns("Elara Veyne", prose), "")

    def test_most_sentences_win_over_one_slip(self):
        prose = (
            "Elara Veyne tilts her head. She says nothing for a while. "
            "Elara folds her arms against the wind. Elara Veyne nods, his eyes on the water."
        )
        self.assertEqual(infer_npc_pronouns("Elara Veyne", prose), "she")

    def test_a_tie_waits_for_a_later_turn(self):
        prose = "Elara Veyne tilts her head. Elara Veyne rubs his jaw."
        self.assertEqual(infer_npc_pronouns("Elara Veyne", prose), "")

    def test_a_sentence_with_both_sets_is_no_vote(self):
        prose = "Elara Veyne lifts his lantern toward her face."
        self.assertEqual(infer_npc_pronouns("Elara Veyne", prose), "")


class TheRepairOnlyMendsWhatIsCertain(unittest.TestCase):
    MABEL = [{"names": ["Mabel"], "key": "she"}]

    def test_a_pronoun_before_the_pinned_name_is_left(self):
        text = "You call out to him, and Mabel looks up from the counter."
        self.assertEqual(repair_pinned_pronouns(text, self.MABEL)[0], text)

    def test_a_sentence_naming_an_unpinned_known_person_is_left(self):
        cast = [{"names": ["Rafe"], "key": "he"}]
        text = "Her gaze flicked between you and Rafe. She had never been the type to meddle."
        self.assertEqual(repair_pinned_pronouns(text, cast, others=["Mabel"])[0], text)
        text = "Mabel glances at Rafe. She had never been the type to meddle."
        self.assertEqual(repair_pinned_pronouns(text, cast, others=["Mabel"])[0], text)

    def test_the_one_the_pinned_person_looks_at_is_someone_else(self):
        cast = [{"names": ["Lettice"], "key": "she"}]
        text = "Lettice's gaze flicks to him, and he shrinks into his corner."
        self.assertEqual(repair_pinned_pronouns(text, cast)[0], text)

    def test_the_sentence_after_a_left_one_is_left_too(self):
        text = "His eyes go to Mabel. He shrugs."
        self.assertEqual(repair_pinned_pronouns(text, self.MABEL)[0], text)

    def test_a_clean_slip_after_the_name_is_still_mended(self):
        text = "Mabel wipes the counter, his sleeves rolled. He sighs."
        fixed, notes = repair_pinned_pronouns(text, self.MABEL)
        self.assertEqual(fixed, "Mabel wipes the counter, her sleeves rolled. She sighs.")
        self.assertEqual(len(notes), 2)


class ThePlayersOwnSexNoun(unittest.TestCase):
    """8B runs 152c T2, 152d T3, 152e T2: NPCs called Isk (she) "a man"."""

    def test_a_noun_said_of_you_follows_the_players_pronouns(self):
        from app.world import _repair_player_sex_nouns

        text, fixed = _repair_player_sex_nouns(
            "\"You look like a man who's been running flat for a long time,\" he says. \"You're not the kind of man they'd trust.\"",
            "she",
        )
        self.assertIn("You look like a woman who's", text)
        self.assertIn("not the kind of woman they'd", text)
        self.assertEqual(len(fixed), 2)

    def test_other_people_and_other_nouns_are_left_alone(self):
        from app.world import _repair_player_sex_nouns

        prose = "A man with a scar looks up. \"He's a hard man,\" she says. You nod to the old man."
        self.assertEqual(_repair_player_sex_nouns(prose, "she"), (prose, []))
        self.assertEqual(_repair_player_sex_nouns("You look like a man.", "he")[1], [])


if __name__ == "__main__":
    unittest.main()
