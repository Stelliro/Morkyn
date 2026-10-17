"""8B run 146, T49: a verb someone else does is not the player's check.

"I leave the flats before the tide covers them and set off north" rolled
support: the de-inflected reading turned "covers them" into "cover them", a
trigger meant for the player covering an ally. A word ending in -s right after
"the <noun>" or "he/she/it/they" is another's verb (or a plural noun) and is
read as typed; the player's own "I cover them" still rolls.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run146_others_act
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.skill_checks import _trigger_text_variants, infer_check_from_action  # noqa: E402

LINE = ("I leave the flats before the tide covers them and set off north out of town along the road, "
        "to find the well-keeper Rolf Joliffe.")


class AnothersVerbIsNotTheirAct(unittest.TestCase):
    def test_the_tide_covering_the_flats_rolls_nothing(self):
        self.assertIsNone(infer_check_from_action(LINE, {}))

    def test_the_others_verb_stays_as_typed_in_every_variant(self):
        for variant in _trigger_text_variants(LINE):
            self.assertIn("covers them", variant)

    def test_a_pronoun_subject_is_anothers_act_too(self):
        self.assertIsNone(infer_check_from_action("I wait at the rail while she covers them with the lamp.", {}))

    def test_the_players_own_cover_still_rolls_support(self):
        check = infer_check_from_action("I cover them while they run for the boat.", {})
        self.assertIsNotNone(check)
        self.assertEqual(check["skill_code"], "support")

    def test_the_players_own_de_inflected_act_still_rolls(self):
        # "covering" is the player's own; de-inflection to "cover them" stays.
        check = infer_check_from_action("I keep covering them from the doorway.", {})
        self.assertIsNotNone(check)
        self.assertEqual(check["skill_code"], "support")


if __name__ == "__main__":
    unittest.main()
