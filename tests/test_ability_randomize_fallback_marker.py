"""The Randomize Abilities button must reach the model, and say so when it could not.

Two silent paths used to send the UI to its local seed pool without a word:
the section lock emptied a direct `field:special_abilities` request, and a model
error swapped in the seed pool while the quality gate re-labelled it "llm".
"""

from __future__ import annotations

import unittest
from unittest import mock

from app import llm


def _current(**extra):
    current = {
        "_locked_fields": [],
        "_field_context": {
            "type": "special_abilities",
            "count_min": 1,
            "count_max": 2,
            "requested_count": 2,
            "target_count": 2,
            "count_rolled": True,
        },
        "world_style": "frontier dark fantasy",
        "magic_level": "low",
        "custom_style": "rain-slick salt marsh towns where oaths are currency",
        "special_abilities": [],
    }
    current.update(extra)
    return current


MODEL_ANSWER = {
    "special_abilities": [
        {
            "name": "Brine Ledger",
            "description": "Taste a handful of marsh water and know which oath was last sworn over it within a day; one pool per scene.",
            "locked": False,
            "prerequisites": "",
            "cost": "A salt-dry mouth; no speech for a short while afterward",
            "growth_math": "XP_to_next = 30 * rank_index^1.4; 5-9 XP per risky use (x2 under threat); soft cap at rank 4, breakthrough needs a sworn witness",
            "power_type": "compounding",
        },
        {
            "name": "Reed Lantern",
            "description": "Coax a cut reed to glow dimly for ten minutes, enough to read a face but not a path.",
            "locked": False,
            "prerequisites": "",
            "cost": "Burns one fresh reed and leaves fingertips numb",
            "growth_math": "Rank thresholds 20/50/110 XP; +5 minutes of light per rank; soft cap at rank 3 until a night spent lightless",
            "power_type": "linear",
        },
    ]
}


class ReturnFieldsTests(unittest.TestCase):
    def test_direct_field_request_survives_the_section_lock(self):
        fields = llm._setup_randomizer_return_fields(
            "field:special_abilities", {"_locked_fields": ["special_abilities"]}
        )
        self.assertEqual(fields, ["special_abilities"])

    def test_group_requests_still_respect_locks(self):
        fields = llm._setup_randomizer_return_fields(
            "special_abilities", {"_locked_fields": ["special_abilities"]}
        )
        self.assertEqual(fields, [])


class FallbackMarkerTests(unittest.TestCase):
    def test_model_error_is_reported_not_hidden(self):
        with mock.patch.object(llm, "_chat_json", side_effect=llm.LlmError("model offline")):
            result = llm.generate_setup_randomization("field:special_abilities", _current())
        self.assertEqual(len(result["special_abilities"]), 2)
        self.assertIs(result["fallback_used"], True)
        self.assertIn("model offline", result["fallback_reason"])
        self.assertEqual(result["quality_gate"]["source"], "fallback_model_error")

    def test_model_abilities_carry_no_fallback_marker(self):
        with mock.patch.object(llm, "_chat_json", return_value=MODEL_ANSWER):
            result = llm.generate_setup_randomization("field:special_abilities", _current())
        self.assertFalse(result.get("fallback_used"))
        self.assertTrue(result["quality_gate"]["source"].startswith("llm"))


if __name__ == "__main__":
    unittest.main()
