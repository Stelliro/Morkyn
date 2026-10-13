"""7B run 14 (Qwen2.5 7B on MLE, agent as player): several people introduced; the opening's untagged player line."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class SeveralIntroduced(unittest.TestCase):
    """T0: three people introduced by name and job stored a drawn "Cuthbert, carter" instead."""

    def test_all_three(self):
        from app.world import _introduced_people

        text = (
            "Millicent Redfern, the fuller, is already at work. Beside her, Iseult Gilchrist, the chandler, is "
            "setting up her stall. Osric Northcott, the pie seller, is preparing pastries."
        )
        self.assertEqual(
            [p["name"] for p in _introduced_people(text, [])],
            ["Millicent Redfern", "Iseult Gilchrist", "Osric Northcott"],
        )

    def test_known_and_places_skipped(self):
        from app.world import _introduced_people

        self.assertEqual(_introduced_people("Saltmarrow, a cluster of buildings, lies ahead.", [], {"Saltmarrow"}), [])
        self.assertEqual(_introduced_people("Millicent Redfern, the fuller, nods.", ["Millicent Redfern"]), [])


class OpeningLineCallingSomeone(unittest.TestCase):
    """T0: 'You approach Millicent, your purpose clear. "Millicent, I need to know ..."' kept Isk's invented line."""

    def test_dropped_on_the_opening(self):
        from app.narration_pipeline import SILENT_TURN_PREFIXES, drop_invented_player_speech

        paras = [
            "Millicent Redfern, the fuller, is already at work.",
            'You approach Millicent, your purpose clear. "Millicent, I need to know when the tide will turn."',
            'Millicent looks up. "Not for another hour. Why do you ask?"',
        ]
        _kept, dropped = drop_invented_player_speech(paras, SILENT_TURN_PREFIXES[0])
        self.assertEqual(dropped, ['"Millicent, I need to know when the tide will turn."'])

    def test_a_greeting_to_the_player_stays(self):
        from app.narration_pipeline import SILENT_TURN_PREFIXES, drop_invented_player_speech

        _kept, dropped = drop_invented_player_speech(
            ['You step up to the counter. "Morning, what can I get you?"'], SILENT_TURN_PREFIXES[0]
        )
        self.assertEqual(dropped, [])


if __name__ == "__main__":
    unittest.main()
