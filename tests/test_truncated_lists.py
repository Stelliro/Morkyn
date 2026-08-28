"""
A shortened list must not be presented as the whole of anything.

Two places said it was, in different registers.

The packet: `mechanics_context.player_inventory_codes` is capped at 40, and the
system prompt called it "the only gear the player currently holds" and told the
narrator that when the player searches their pockets, "only listed items
exist". Past the cap that instruction is false, and its cost is the inverse of
the usual one -- the player owns the thing and is told they do not. It is
reachable rather than theoretical: `_inventory_summary` sets `slot_capacity`
to None once a dimensional container is equipped, so nothing bounds the count.

The prose: the deterministic fallback opens with "What you still carry is
plain: ..." built from `inventory[:6]`, which states a six-item summary as a
complete account of the pack.
"""

import unittest

from app.llm import fallback_turn
from app.prompts import SYSTEM_PROMPT
from app.world import PROMPT_INVENTORY_CODE_CAP, inventory_codes_for_prompt


def item(index):
    return {"code": f"I{index}", "name": f"item {index}", "quantity": 1}


def context_with(count):
    return {
        "current_location": {"name": "the yard", "code": "L1"},
        "inventory": [item(i) for i in range(1, count + 1)],
        "settings": {"playthrough_options": {}},
    }


def opening(count):
    return str(fallback_turn(context_with(count), "__opening_scene_request__").get("narration") or "")


class FallbackInventoryClaimTests(unittest.TestCase):
    def test_a_complete_short_list_still_claims_completeness(self):
        text = opening(3)
        self.assertIn("What you still carry is plain:", text)
        self.assertIn("item 3", text)

    def test_exactly_six_is_still_the_whole_pack(self):
        self.assertIn("What you still carry is plain:", opening(6))

    def test_a_seventh_item_drops_the_claim(self):
        text = opening(7)
        self.assertNotIn(
            "What you still carry is plain:",
            text,
            "six of seven items were described as the whole pack",
        )
        self.assertIn("Among what you still carry:", text)

    def test_the_sentence_is_still_capped_for_readability(self):
        """Honesty about the cap, not removal of it -- forty items is not prose."""
        text = opening(40)
        self.assertIn("item 6", text)
        self.assertNotIn("item 7", text)

    def test_an_empty_pack_says_nothing_about_gear(self):
        text = opening(0)
        self.assertNotIn("What you still carry", text)
        self.assertNotIn("Among what you still carry", text)

    def test_unnamed_entries_do_not_fake_a_shortfall(self):
        """A nameless row is unprintable, not evidence the list was cut."""
        context = context_with(2)
        context["inventory"].append({"code": "I9", "name": "   ", "quantity": 1})
        text = str(fallback_turn(context, "__opening_scene_request__").get("narration") or "")
        self.assertIn("What you still carry is plain:", text)


class InventoryCodesTests(unittest.TestCase):
    def test_a_pack_within_the_cap_is_not_marked_truncated(self):
        codes, truncated = inventory_codes_for_prompt([item(i) for i in range(1, 10)])
        self.assertEqual(len(codes), 9)
        self.assertIsNone(truncated)

    def test_exactly_the_cap_is_not_truncated(self):
        codes, truncated = inventory_codes_for_prompt(
            [item(i) for i in range(1, PROMPT_INVENTORY_CODE_CAP + 1)]
        )
        self.assertEqual(len(codes), PROMPT_INVENTORY_CODE_CAP)
        self.assertIsNone(truncated, "an exact fit is the whole pack")

    def test_one_over_the_cap_says_so_and_names_the_full_record(self):
        rows = [item(i) for i in range(1, PROMPT_INVENTORY_CODE_CAP + 2)]
        codes, truncated = inventory_codes_for_prompt(rows)
        self.assertEqual(len(codes), PROMPT_INVENTORY_CODE_CAP)
        self.assertEqual(truncated["shown"], PROMPT_INVENTORY_CODE_CAP)
        self.assertEqual(truncated["total"], PROMPT_INVENTORY_CODE_CAP + 1)
        self.assertEqual(truncated["complete_list"], "world_state.inventory")

    def test_junk_rows_are_dropped_before_counting(self):
        codes, truncated = inventory_codes_for_prompt([item(1), None, "rope", item(2)])
        self.assertEqual(len(codes), 2)
        self.assertIsNone(truncated)

    def test_no_inventory_is_not_a_truncation(self):
        for empty in (None, []):
            codes, truncated = inventory_codes_for_prompt(empty)
            self.assertEqual(codes, [])
            self.assertIsNone(truncated)


class InventoryCodesContractTests(unittest.TestCase):
    def test_the_rule_no_longer_calls_the_short_list_the_only_gear(self):
        self.assertNotIn("is the only gear the player currently holds", SYSTEM_PROMPT)

    def test_the_rule_points_at_the_complete_record_when_truncated(self):
        self.assertIn("player_inventory_truncated", SYSTEM_PROMPT)
        self.assertIn("world_state.inventory is the complete record", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
