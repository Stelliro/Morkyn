"""Regression tests: if the prose says you took it, the world records it.

From the third 100-turn continuity run. On seven turns the narration said the
player pocketed or picked up a named object; the ops emitted GRANT on one. The
inventory never moved, so the object stayed where it was -- the same sign was
"picked up" on turns 59, 69 and 94 because it never left the ground.

Same shape as the movement repair: the narration asserts a state change, the
model emitted no op for it, and the server makes the world match the story
rather than letting the two drift apart.

The verb set is deliberately narrow. "you take" is excluded outright: a probe
run is full of "you take a slow breath", "you take stock", "you take the road",
and an earlier grounding metric built on that verb was pure false positives.
"now carry" is excluded too -- it matched "the burden you now carry" about a
letter the player was already holding.

Scored over that run's 100 turns this finds 7 claims, all real.

Run:  python -m unittest tests.test_acquisition_grounding
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-acq-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.world import acquisition_claims, ground_acquisitions  # noqa: E402


class TestClaimDetection(unittest.TestCase):
    def test_a_named_object_is_a_claim(self):
        self.assertEqual(
            acquisition_claims("You pocket the sketch, its edges frayed but its lines clear."),
            ["sketch"],
        )
        self.assertEqual(
            acquisition_claims("You pick up the sign, its weight surprising."), ["sign"]
        )
        self.assertEqual(
            acquisition_claims("You are handed a folded note from the courier."), ["folded note"]
        )

    def test_take_is_never_an_acquisition_verb(self):
        # Every one of these appeared in a real run. An earlier detector built on
        # "take" reported 15 ungrounded pickups, all of them false.
        for line in (
            "You take a slow breath and steady yourself.",
            "You take stock of your injuries and how tired you are.",
            "You take the road out of the square.",
            "You take a moment to consider the offer.",
            "You take out the letter you already carry.",
        ):
            with self.subTest(line=line):
                self.assertEqual(acquisition_claims(line), [])

    def test_an_unnamed_object_is_not_a_claim(self):
        # "it" is unresolvable, and guessing the referent is how a scene about a
        # dagger ends up granting an item called "it".
        self.assertEqual(acquisition_claims("You pocket it, then glance around."), [])

    def test_an_item_already_held_is_not_being_acquired(self):
        self.assertEqual(acquisition_claims("the burden you now carry"), [])

    def test_a_figure_of_speech_is_not_an_object(self):
        self.assertEqual(acquisition_claims("You pick up the pace along the road."), [])
        self.assertEqual(acquisition_claims("You pick up the moment and hold it."), [])


class TestGrounding(unittest.TestCase):
    def _turn(self, changes=None):
        return {"inventory_changes": list(changes or [])}

    def test_an_ungranted_claim_is_granted(self):
        turn = self._turn()
        granted = ground_acquisitions(turn, "You pick up the sign, its weight surprising.", {})
        self.assertEqual(granted, ["sign"])
        self.assertEqual(len(turn["inventory_changes"]), 1)
        self.assertEqual(turn["inventory_changes"][0]["name"], "sign")

    def test_a_claim_the_model_already_granted_is_left_alone(self):
        turn = self._turn([{"name": "sign", "quantity_band": "trivial"}])
        granted = ground_acquisitions(turn, "You pick up the sign.", {})
        self.assertEqual(granted, [])
        self.assertEqual(len(turn["inventory_changes"]), 1, "no duplicate grant")

    def test_an_item_already_carried_is_not_granted_again(self):
        # This is the turn-69 case: the sign was picked up on 59 and again on 69.
        turn = self._turn()
        state = {"inventory": [{"name": "sign"}]}
        self.assertEqual(ground_acquisitions(turn, "You pocket the sign.", state), [])
        self.assertEqual(turn["inventory_changes"], [])

    def test_prose_with_no_claim_changes_nothing(self):
        turn = self._turn()
        self.assertEqual(ground_acquisitions(turn, "You take a slow breath.", {}), [])
        self.assertEqual(turn["inventory_changes"], [])

    def test_the_granted_row_is_shaped_like_a_grant_op(self):
        turn = self._turn()
        ground_acquisitions(turn, "You pocket the sketch, its edges frayed.", {})
        row = turn["inventory_changes"][0]
        for key in ("name", "quantity_band", "weight", "slot_size", "item_type", "rarity"):
            self.assertIn(key, row)

    def test_several_claims_in_one_scene_are_all_grounded(self):
        turn = self._turn()
        prose = "You pocket the sketch, and then you pick up the map, tracing its lines."
        self.assertEqual(sorted(ground_acquisitions(turn, prose, {})), ["map", "sketch"])


if __name__ == "__main__":
    unittest.main()
