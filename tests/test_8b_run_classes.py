"""8B run classes (runs 7+): one test per fixed class."""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.scene_thread import follow_target, pursuit_in  # noqa: E402
from app.skill_checks import infer_check_from_action, resolve_check  # noqa: E402


class AWayIsWalkedNotFollowed(unittest.TestCase):
    """8B run 7, T1: "I follow the narrow path" logged following a person."""

    def test_ways_are_no_one(self):
        for line in (
            "I follow the narrow path down into the drowned district.",
            "I follow the footprints toward the water.",
            "I follow the old road north.",
        ):
            self.assertEqual(follow_target(line), "", line)

    def test_a_person_is_still_followed(self):
        self.assertIn("fisherman", follow_target("I follow the old fisherman down to the docks.").lower())

    def test_no_pursuit_thread_for_a_way(self):
        # T2 moved the player onto "Saltmarrow's narrow path" after the thread said
        # the player was following it.
        self.assertIsNone(pursuit_in("I follow the narrow path down into the drowned district."))
        self.assertIsNotNone(pursuit_in("I follow Rolf down the narrow path."))


class AReasonIsNotTheAct(unittest.TestCase):
    """8B run 8, T1: "...anything half-buried in the mud that might fetch a price" rolled appraise."""

    def test_what_a_thing_might_fetch_is_no_appraisal(self):
        line = ("I check the tide-reckoner against the sky, then walk out along the single path toward the "
                "Hollow Maw, keeping an eye out for anything half-buried in the mud that might fetch a price.")
        check = infer_check_from_action(line, {})
        self.assertNotEqual((check or {}).get("skill_code"), "appraise")

    def test_a_price_asked_still_appraises(self):
        self.assertEqual(infer_check_from_action("I haggle over the price of the copper.", {})["skill_code"], "appraise")


class NoOneToOffend(unittest.TestCase):
    """8B run 8, T1: "Botched Appraise: you misjudge the moment and give offense" alone on the mud."""

    def _first(self, predicate, **kw):
        for seed in range(4000):
            check = resolve_check(skill_code="appraise", rng=random.Random(seed), **kw)
            if predicate(check):
                return check
        raise AssertionError("no roll matched")

    def test_a_lone_bad_miss_is_no_blunder(self):
        check = self._first(lambda c: c["natural"] != 1 and c["margin"] <= -7)
        self.assertIsNone(check["blunder"])
        self.assertNotIn("offense", check.get("flavor") or "")

    def test_a_bad_miss_against_someone_still_blunders(self):
        check = self._first(lambda c: c["natural"] == 1, opposition={"name": "Vael", "rank": "F", "stats": {}})
        self.assertEqual(check["blunder"]["kind"], "social_blunder")


if __name__ == "__main__":
    unittest.main()
