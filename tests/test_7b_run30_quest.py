"""7B run 30: a work job is finished by the work, not by being there or by naming the trouble."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.quest_parser import validate_quest_changes  # noqa: E402

MOLES = {
    "id": 1, "code": "Q1", "title": "Help with moles", "status": "active", "current_step": 1, "total_steps": 1,
    "current_step_text": "The tannery is where the moles are causing trouble",
}
T15_LINE = ('"Nothing in either trap yet." I wipe my hands on my trousers. "Dunstan, I will come back at dusk to '
            'check them. Where do I find you then?"')
T15_PROSE = ('Dunstan [[A]] scratches his beard. "The tannery is where the moles are causing trouble. It\'s not far, '
             'but you need to watch your step. I\'ll be there."')


def _update(evidence: str, prose: str, line: str, quest=MOLES):
    return validate_quest_changes(
        {"updates": [{"quest": "Q1", "action": "step_done", "evidence": evidence}]},
        narration=prose, player_input=line, existing=[dict(quest)],
    )


class NamingTheTroubleIsNotTheWork(unittest.TestCase):
    """T15: 'The tannery is where the moles are causing trouble' finished and paid 'Help with moles'."""

    def test_refused_on_the_players_word(self):
        accepted, rejected = _update("The tannery is where the moles are causing trouble", T15_PROSE, T15_LINE)
        self.assertEqual(accepted["updates"], [])
        self.assertIn("player_says_not_done", rejected[0]["reasons"])

    def test_refused_on_the_quote_alone(self):
        accepted, rejected = _update("The tannery is where the moles are causing trouble", T15_PROSE,
                                     '"Where do I find you then?"')
        self.assertEqual(accepted["updates"], [])
        self.assertIn("evidence_shows_no_outcome", rejected[0]["reasons"])

    def test_the_catch_finishes_it(self):
        prose = ("The spring snaps shut. You lift the trap: two moles caught. Dunstan grins. "
                 "\"Good work, that is the last of them.\"")
        accepted, rejected = _update("You lift the trap: two moles caught.", prose, "I lift the trap and look.")
        self.assertEqual(rejected, [])
        self.assertEqual(len(accepted["updates"]), 1)

    def test_a_middle_step_is_unchanged(self):
        quest = dict(MOLES, current_step=1, total_steps=2, current_step_text="Go to the tannery")
        accepted, _rejected = _update("You stand at the tannery, where the moles are causing trouble.",
                                      "You stand at the tannery, where the moles are causing trouble.",
                                      "I go to the tannery.", quest)
        self.assertEqual(len(accepted["updates"]), 1)


class AWorkJobGetsItsWorkStep(unittest.TestCase):
    """T0: the parser wrote 'Help with moles' with the one step 'Go to the tannery'."""

    def _new(self, title, steps):
        prose = ('"Morning, flat-runner," Dunstan calls out. "Need any help with the moles? They\'ve been worse than usual."')
        accepted, _rejected = validate_quest_changes(
            {"new": [{"title": title, "giver": "Dunstan", "steps": steps,
                      "evidence": "Need any help with the moles? They've been worse than usual.",
                      "offer_line": "Need any help with the moles? They've been worse than usual."}]},
            narration=prose, player_input="", npcs=[{"id": 1, "code": "A", "name": "Dunstan"}],
            locations=[{"code": "L1", "name": "Saltmarrow"}], existing=[],
        )
        return accepted["new"][0]["steps"] if accepted["new"] else None

    def test_work_step_added(self):
        steps = self._new("Help with moles", [{"title": "Go to the tannery", "location": "L1"}])
        self.assertEqual([s["title"] for s in steps], ["Go to the tannery", "Help with moles"])
        self.assertEqual(steps[-1]["location_code"], "L1")

    def test_a_trip_job_keeps_its_steps(self):
        steps = self._new("Deliver the moles to the tanner", [{"title": "Go to the tannery", "location": "L1"}])
        self.assertEqual([s["title"] for s in steps], ["Go to the tannery"])

    def test_a_work_step_is_kept_as_is(self):
        steps = self._new("Help with moles", [{"title": "Set traps in the tunnels", "location": "L1"}])
        self.assertEqual([s["title"] for s in steps], ["Set traps in the tunnels"])


if __name__ == "__main__":
    unittest.main()
