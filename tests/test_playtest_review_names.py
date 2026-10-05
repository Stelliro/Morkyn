"""Review of the playtest #14 and #16 (d) name fixes (game 2, "Eldoria's Edge").

- The stored-role rewrite (#16 d) matched any article and word pair before a
  tag, so "You hand the loaf to Aria [[A]]" became "You hand the baker Aria
  [[A]]" and "a smiling Aria [[A]]" became "a baker Aria [[A]]". Only a word
  shaped like a job before the tag is a job.
- One name per person (#14) only knew people who already had a code. In the
  opening that logged the defect, Aria was filed in the same turn, so "A net
  mender named Aria weaves a new net" went through unchanged.
- The reports (name_reuses, role_mismatches) were dropped by the handoff
  cleanup before the turn trace was written.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-review-names-"))
os.environ.update(isolated_data_env(str(_TMP)))

from app import llm  # noqa: E402

NAMES = {"A": "Aria", "C": "Hearthbin"}
ROLES = {"A": "baker", "C": "message runner"}

CONTEXT = {
    "current_location": {"code": "L1", "name": "Eldoria's Edge"},
    "locations": [
        {
            "code": "L1",
            "name": "Eldoria's Edge",
            "npcs": [
                {"code": "A", "name": "Aria", "role": "baker"},
                {"code": "C", "name": "Hearthbin", "role": "message runner"},
            ],
        }
    ],
}


class StoredRoleLeavesOrdinaryProseAlone(unittest.TestCase):
    def test_prepositions_and_adjectives_before_a_tag_are_not_jobs(self):
        for text in (
            "You hand the loaf to Aria [[A]].",
            "She gives a nod to Aria [[A]] and turns away.",
            "A smiling Aria [[A]] waves you over.",
            "You lean on the stall beside Aria [[A]].",
            "It is a gift for Aria [[A]].",
            "The old Hearthbin [[C]] coughs.",
            "The other Hearthbin [[C]] is not here.",
        ):
            with self.subTest(text=text):
                self.assertEqual(llm._prefer_stored_roles(text, NAMES, ROLES), text)

    def test_the_logged_wrong_job_is_still_replaced(self):
        # Turn 2's depth retry: "a cartter [[C]]" for Hearthbin the message runner.
        out = llm._prefer_stored_roles("Nearby, a cartter [[C]] is unloading crates.", NAMES, ROLES)
        self.assertEqual(out, "Nearby, a message runner Hearthbin [[C]] is unloading crates.")

    def test_full_repair_keeps_a_hand_over_intact(self):
        result = {"narration": "You hand the loaf to Aria [[A]]. A cartter [[C]] waves.", "npcs": []}
        out = llm._repair_entity_names_in_turn(result, CONTEXT)["narration"]
        self.assertIn("You hand the loaf to Aria [[A]].", out)
        self.assertNotIn("cartter", out)


class OpeningNameReuse(unittest.TestCase):
    # Turn 1 as logged: NPC_NEW Aria ROLE baker, no code yet, and the final prose
    # also introduces "A net mender named Aria".
    OPENING = (
        "She hands you a crusty loaf. Aria, the baker, glances your way. To your east, the market "
        "stalls begin to open. A net mender named Aria weaves a new net, her hands steady and practiced."
    )

    def test_a_person_filed_this_turn_keeps_their_name_to_themselves(self):
        result = {
            "narration": self.OPENING,
            "npcs": [{"code": None, "name": "Aria", "role": "baker", "location": "L1"}],
        }
        out = llm._repair_entity_names_in_turn(result, {"current_location": {"code": "L1", "name": "Eldoria's Edge"}})
        self.assertIn("A net mender weaves a new net", out["narration"])
        self.assertNotIn("net mender named Aria", out["narration"])
        self.assertEqual(out.get("name_reuses"), [{"code": "", "name": "Aria", "stored": "baker", "prose": "net mender"}])

    def test_the_reuse_survives_the_handoff_cleanup(self):
        # The cleanup before apply_turn listed name_reuses under removed_keys,
        # so the turn trace never showed one.
        result = {
            "narration": self.OPENING,
            "npcs": [{"code": None, "name": "Aria", "role": "baker", "location": "L1"}],
        }
        repaired = llm._repair_entity_names_in_turn(result, {})
        trace: list = []
        cleaned = llm._clean_turn_for_handoff(repaired, "verifier_to_world", trace)
        self.assertEqual(cleaned.get("name_reuses"), repaired["name_reuses"])
        self.assertNotIn("name_reuses", trace[-1]["removed_keys"])
        self.assertNotIn("name_reuses", llm._turn_for_depth_retry(cleaned))

    def test_same_job_or_no_job_keeps_the_name(self):
        for text in ("A baker named Aria waves.", "A woman named Aria waves.", "A dog named Aria barks."):
            with self.subTest(text=text):
                result = {"narration": text, "npcs": [{"code": None, "name": "Aria", "role": "baker"}]}
                out = llm._repair_entity_names_in_turn(result, {})
                self.assertIn("named Aria", out["narration"])
                self.assertNotIn("name_reuses", out)

if __name__ == "__main__":
    unittest.main()
