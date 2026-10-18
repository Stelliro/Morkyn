"""Jobs bind by reference (Stell, 2026-10-18): "@Q1" in the player's line, and the check's
same_job code on a job told again under another name.

Run:  .venv\\Scripts\\python -m unittest tests.test_quest_references
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-questref-"))
_ENV = isolated_data_env(str(_TMP))
_SAVED_ENV: dict[str, str | None] = {}


def setUpModule():
    _SAVED_ENV.update({key: os.environ.get(key) for key in _ENV})
    os.environ.update(_ENV)


def tearDownModule():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


CONTEXT = {
    "current_location": {"name": "The Salvage Guild's Tally House", "code": "L2", "npcs": [{"name": "Garrick Thorne", "code": "A"}]},
    "locations": [],
    "inventory": [],
    "events": [],
    "aliases": [],
    "active_quests": [],
    "open_quest_offers": [{"id": 1, "code": "Q1", "title": "Clear the Guild's Sheds", "giver": "Garrick Thorne", "giver_code": "A"}],
}


class TheQuestReferenceInTheLine(unittest.TestCase):
    def test_at_q1_names_the_quest(self):
        from app.world import _expand_input_references

        out = _expand_input_references(CONTEXT, "I'll take @Q1, Garrick. When do I start?")
        self.assertIn("Clear the Guild's Sheds [[Q1]]", out)
        self.assertIn("Q1, quest", out)

    def test_a_person_reference_still_works(self):
        from app.world import _expand_input_references

        out = _expand_input_references(CONTEXT, "I nod to @Cgarrick_thorne.")
        self.assertIn("Garrick Thorne [[A]]", out)


class TheCheckNamesTheJobToldAgain(unittest.TestCase):
    PROSE = ("“What is the job?” you ask. Garrick Thorne [[A]] drums the counter. “You’ll be fetching salvage "
             "from the docks. The storm’s left a mess.”")
    LINE = "\"What is the job, and how much does it take off the ledger?\""
    GARRICK = [{"code": "A", "name": "Garrick Thorne", "role": "tallyman"}]
    OPEN = [{"code": "Q1", "title": "Clear the Guild's Sheds", "giver": "Garrick Thorne"}]

    def _ask(self, same_job):
        calls = []

        def ask(system, user, *, max_tokens, phase):
            calls.append({"phase": phase, "user": user})
            if phase == "quest_fill":
                return {"offers_work": True, "task": "You'll be fetching salvage from the docks.", "title": "Fetch Salvage from the Docks",
                        "steps": ["Go to the docks", "Fetch the salvage"], "place": "the docks", "pay": "", "gold": 0}
            return {"offered": "yes", "specific": "yes", "in_text": "yes", "why": "he sets the work", "same_job": same_job}

        return ask, calls

    def test_the_open_jobs_are_shown_and_the_code_comes_back(self):
        import json

        from app import quest_offers as qo

        ask, calls = self._ask("Q1")
        report = qo.run_offer_pass(self.PROSE, self.LINE, npcs=self.GARRICK, asked_for_work=True, ask=ask, open_jobs=self.OPEN)
        check_call = next(c for c in calls if c["phase"] == qo.CHECK_PHASE)
        payload = json.loads(check_call["user"])
        self.assertEqual(payload["open_jobs"][0]["code"], "Q1")
        self.assertIn("same_job", payload["questions"])
        self.assertEqual(len(report["new"]), 1)
        self.assertEqual(report["new"][0].get("retells"), "Q1")

    def test_an_unlisted_code_is_no_reference(self):
        from app import quest_offers as qo

        ask, _calls = self._ask("Q7")
        report = qo.run_offer_pass(self.PROSE, self.LINE, npcs=self.GARRICK, asked_for_work=True, ask=ask, open_jobs=self.OPEN)
        self.assertEqual(len(report["new"]), 1)
        self.assertNotIn("retells", report["new"][0])

    def test_another_givers_job_is_no_reference(self):
        from app import quest_offers as qo

        ask, _calls = self._ask("Q1")
        other = [{"code": "Q1", "title": "Clear the Guild's Sheds", "giver": "Mabel Crane"}]
        report = qo.run_offer_pass(self.PROSE, self.LINE, npcs=self.GARRICK, asked_for_work=True, ask=ask, open_jobs=other)
        self.assertNotIn("retells", report["new"][0])


class TheParserBindsByReference(unittest.TestCase):
    def test_the_referenced_offer_takes_the_telling(self):
        from app import quest_parser

        narration = ("“What is the job?” you ask. Garrick [[A]] drums the counter. “You’ll be hauling nets off the "
                     "east pier.”")
        reply = {"new": [{"title": "Haul the Nets", "giver": "A", "difficulty": "normal", "summary": "Haul the nets off the east pier.",
                          "steps": [{"title": "Haul the nets off the east pier", "location": "L2"}],
                          "reward": {"gold": 0, "xp": 0, "items": [], "text": ""},
                          "offer_line": "You’ll be hauling nets off the east pier.",
                          "evidence": "You’ll be hauling nets off the east pier.", "retells": "Q1", "_from_mark": True}],
                 "updates": []}
        npcs = [{"id": 2, "code": "A", "name": "Garrick", "role": "tallyman"}]
        existing = [{"id": 1, "code": "Q1", "title": "Clear the Guild's Sheds", "status": "offered", "giver_npc_id": 2,
                     "current_step": 1, "first_step_location": ""}]
        accepted, _ = quest_parser.validate_quest_changes(
            reply, narration=narration, player_input="\"Alright. What is the job?\"", npcs=npcs, existing=existing)
        self.assertEqual(accepted["new"], [])
        self.assertEqual([r["title"] for r in accepted.get("retold") or []], ["Haul the Nets"])


if __name__ == "__main__":
    unittest.main()
