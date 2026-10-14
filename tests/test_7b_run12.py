"""7B run 12 (Qwen2.5 7B on MLE, agent as player): the person the prose introduces is the one stored."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class IntroducedPerson(unittest.TestCase):
    """T0: "Mattias Slade, a herbalist with a greying beard ... he says" stored a drawn "Dafydd, toll keeper"."""

    def test_reads_the_introduction(self):
        from app.world import _introduced_person as read

        self.assertEqual(
            read("Mattias Slade, a herbalist with a greying beard, is leaning against the wall. \"Morning,\" he says.", []),
            {"name": "Mattias Slade", "role": "herbalist"},
        )
        self.assertEqual(read("Oriel Rendle, the rag picker, glances up.", []), {"name": "Oriel Rendle", "role": "rag picker"})

    def test_not_a_place_a_known_person_or_two_people(self):
        from app.world import _introduced_person as read

        self.assertIsNone(read("Saltmarrow, a cluster of buildings, lies ahead.", [], {"Saltmarrow"}))
        self.assertIsNone(read("The Wren's Rest, a modest inn, beckons.", []))
        self.assertIsNone(read("Oriel Rendle, the rag picker, glances up.", ["Oriel Rendle"]))
        self.assertIsNone(read("Simon Pennick, a wheelwright, and Madoc Dimmock, the laundress, talk.", []))
        self.assertIsNone(read("A tall man, a stranger, waits by the gate.", []))


class UnquotedEchoIsQuoted(unittest.TestCase):
    """T1: the player's lines, written without quote marks, were said again at the opening (twice in the scene)."""

    def test_quoted_in_place(self):
        from app.narration_pipeline import keep_player_words

        line = ('"Morning, Mattias. Tide-reading and salvage, same as always." I glance at the forge behind him. '
                '"You\'re a long way from your herbs. Something wrong?"')
        prose = ("Morning, Mattias. Tide-reading and salvage, same as always. You glance at the forge behind him. "
                 "You're a long way from your herbs. Something wrong?\n\nMattias shifts. \"Ah. The tide's been odd.\"")
        text, changes = keep_player_words(prose, line)
        self.assertEqual(text.count("Tide-reading and salvage"), 1)
        self.assertIn("“Morning, Mattias. Tide-reading and salvage, same as always.”", text)
        # Since 7B run 36 (T2) the last line, untagged before "Mattias", also gets its tag.
        self.assertEqual([c["action"] for c in changes],
                         ["unquoted_line_quoted", "unquoted_line_quoted", "player_line_tagged"])


class UntaggedLineAfterSomeoneElse(unittest.TestCase):
    """Run 13 T1: 'She turns to you, her face stern. "Reeve Colley. ..."' read as the reeve's words."""

    def test_tagged_as_the_player(self):
        from app.narration_pipeline import keep_player_words

        line = 'I walk down to the docks. "Reeve Colley. You\'re out early."'
        text, changes = keep_player_words(
            'She turns to you, her face stern. "Reeve Colley. You\'re out early."\n\nRosamund nods.', line
        )
        self.assertIn('You say, "Reeve Colley.', text)
        self.assertEqual([c["action"] for c in changes], ["untagged_player_line_tagged"])

    def test_left_alone_after_the_player_or_with_a_tag(self):
        from app.narration_pipeline import keep_player_words

        line = 'I walk down to the docks. "Reeve Colley. You\'re out early."'
        self.assertEqual(keep_player_words('You walk down to the docks. "Reeve Colley. You\'re out early."', line)[1], [])
        self.assertEqual(
            keep_player_words('Rosamund looks up. "Reeve Colley. You\'re out early," you say.', line)[1], []
        )


class TheForgeIsNotSmithing(unittest.TestCase):
    """T1: "I glance at the forge behind him" rolled smithing at DC 16."""

    def test_noun_and_verbs(self):
        from app.skill_checks import infer_check_from_action as infer

        def skill(line):
            return (infer(line, {}) or {}).get("skill_code")

        self.assertIsNone(skill('"Morning, Mattias." I glance at the forge behind him. "Something wrong?"'))
        self.assertIsNone(skill("I walk past the forge."))
        self.assertEqual(skill("I forge a new blade at the anvil."), "smithing")
        self.assertEqual(skill("I hammer out the dent in the fitting."), "smithing")


if __name__ == "__main__":
    unittest.main()
