"""8B run 145, T9: the dive on the wreck rolled nothing and finished no step.

"I make the line fast to the thwart, check the knot twice, then go over the
side and dive on the wreck to bring up anything of value" was the active job's
own work and a risky act, and no die was thrown: "dive" was no act family and
no athletics trigger. Swimming and diving are an act now (athletics), so the
dice roll it and the quest step the line does is matched. A dive named is not a
dive done: "The dive. I'll take it." still rolls nothing.

Run:  .venv\\Scripts\\python -m unittest tests.test_8b_run145_dive
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prose_state import act_rules  # noqa: E402
from app.quests import match_quest_step  # noqa: E402
from app.skill_checks import infer_check_from_action  # noqa: E402

DIVE = ("I make the line fast to the thwart, check the knot twice, then go over the side and dive on the wreck "
        "to bring up anything of value before the current turns.")
QUESTS = [{
    "id": 1, "code": "Q1", "title": "Deep Site Salvage Dive", "status": "active", "current_step": 1, "total_steps": 3,
    "steps": [
        {"step_number": 1, "title": "Join a team for a deep dive", "description": "Join a team for a deep dive", "location_code": ""},
        {"step_number": 2, "title": "Search the site near the old shipwreck", "description": "", "location_code": ""},
        {"step_number": 3, "title": "Recover valuable items from the depths", "description": "", "location_code": ""},
    ],
}]


class TheDiveIsAnAct(unittest.TestCase):
    def test_diving_on_the_wreck_is_an_athletics_act(self):
        act = act_rules(DIVE)
        self.assertIsNotNone(act)
        self.assertEqual(act["family"], "swim")
        self.assertEqual(act["skill_code"], "athletics")
        check = infer_check_from_action(DIVE, {})
        self.assertEqual(check["skill_code"], "athletics")

    def test_the_dive_does_the_jobs_step(self):
        match = match_quest_step(DIVE, QUESTS)
        self.assertIsNotNone(match)
        self.assertEqual(match["quest_id"], 1)

    def test_a_dive_named_is_not_a_dive_done(self):
        self.assertIsNone(act_rules("\"The dive. I'll take it.\" I set my hands flat on the desk."))
        check = infer_check_from_action("\"The dive. I'll take it.\" I set my hands flat on the desk. \"When does the team go out?\"", {})
        self.assertNotEqual((check or {}).get("skill_code"), "athletics")


if __name__ == "__main__":
    unittest.main()
