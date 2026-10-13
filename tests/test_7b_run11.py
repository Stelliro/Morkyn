"""7B run 11 (Qwen2.5 7B on MLE, agent as player): codes set off by commas, town names inside venue names."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NAMES = {"L1": "Saltmarrow", "A": "Iseult Pennick", "L2": "Saltmarrow Salvage Yard"}


class AppositiveCodes(unittest.TestCase):
    """T0: "Saltmarrow, [[L1]], is a ghost town" shipped as "Saltmarrow [[L1]], Saltmarrow [[L1]], is"."""

    def test_code_after_its_name_attaches(self):
        from app.llm import _repair_prose_entity_labels as repair

        self.assertEqual(repair("Saltmarrow, [[L1]], is a ghost town.", NAMES), "Saltmarrow [[L1]] is a ghost town.")
        self.assertEqual(repair("You stand in Saltmarrow, [[L1]].", NAMES), "You stand in Saltmarrow [[L1]].")

    def test_stray_code_after_another_name_goes(self):
        from app.llm import _repair_prose_entity_labels as repair

        self.assertEqual(repair("The Saltmarrow Stables, [[L1]], stands just ahead.", NAMES),
                         "The Saltmarrow Stables stands just ahead.")

    def test_known_longer_names_and_plain_mentions(self):
        from app.llm import _repair_prose_entity_labels as repair

        self.assertEqual(
            repair("You walk to the Saltmarrow Salvage Yard and then back to Saltmarrow.", NAMES),
            "You walk to the Saltmarrow Salvage Yard [[L2]] and then back to Saltmarrow [[L1]].",
        )
        self.assertEqual(repair("You reach Saltmarrow [[L1]], and the gulls cry.", NAMES),
                         "You reach Saltmarrow [[L1]], and the gulls cry.")


if __name__ == "__main__":
    unittest.main()
