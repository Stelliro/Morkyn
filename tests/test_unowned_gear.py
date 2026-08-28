"""
Prose must not hand the player gear the record says they do not have.

Reported from play: a shed scene wrote "the cold metal biting through your
gloves" for a character whose whole recorded wardrobe is

    torso: patched overshirt; feet: scuffed boots; bag: leather satchel

Nothing on the hands, and the record has always known it: appearance is written
by body zone at setup, so an absent zone means bare rather than unrecorded.

The wardrobe was not missing from the packet. `build_user_prompt` sends
`playthrough_options` whole, appearance included, and the model was reading it.
What was missing was a rule that covered it. The no-invention rule beside it
reads:

    mechanics_context.player_inventory_codes (when present) is the only gear
    the player currently holds. Do not invent pocket items, keys, knives, or
    coupons not listed.

That is scoped to held inventory, and clothing is not inventory here -- it
lives in appearance. Its examples are all small carried objects, which narrows
the scope further for anyone reading it. Worn clothing fell in the gap.
"""

import re
import unittest

from app.world import check_unowned_gear, worn_gear_index

APPEARANCE = "torso: patched overshirt; feet: scuffed boots; bag: leather satchel"
STARTER = "threadbare scarf, frayed leather satchel, cracked compass"

REPORTED = (
    "The shed creaks as you press your palm against the rusted lock, its metal "
    "groaning under your grip, the cold metal biting through your gloves."
)


def state(appearance=APPEARANCE, starter=STARTER, inventory=None):
    return {
        "settings": {"playthrough_options": {"appearance": appearance, "starter_equipment": starter}},
        "inventory": inventory or [],
    }


class WornGearIndexTests(unittest.TestCase):
    def test_reads_the_zone_tags_setup_wrote(self):
        index = worn_gear_index(state())
        self.assertEqual(index["zones"], ["bag", "feet", "torso"])
        self.assertTrue(index["structured"])

    def test_free_text_appearance_is_not_structured(self):
        """Without zone tags, a missing zone means nobody wrote it down."""
        index = worn_gear_index(state(appearance="a tall woman with a weathered face"))
        self.assertFalse(index["structured"])

    def test_survives_a_missing_state(self):
        for empty in (None, {}, {"settings": {}}):
            self.assertFalse(worn_gear_index(empty)["structured"])


class CheckUnownedGearTests(unittest.TestCase):
    def test_the_reported_sentence_is_caught(self):
        report = check_unowned_gear(REPORTED, worn_gear_index(state()))
        self.assertTrue(report["unowned"])
        self.assertEqual([f["noun"] for f in report["findings"]], ["gloves"])
        self.assertEqual(report["findings"][0]["zone"], "hands")

    def test_gear_the_player_actually_wears_is_left_alone(self):
        index = worn_gear_index(state())
        report = check_unowned_gear("You pull your boots on and shrug your overshirt straight.", index)
        self.assertEqual(report["findings"], [])

    def test_owning_the_item_in_inventory_is_enough(self):
        """Gloves in the pack are still gloves, even with no hands zone."""
        index = worn_gear_index(state(inventory=[{"name": "oiled leather gloves"}]))
        self.assertFalse(check_unowned_gear(REPORTED, index)["unowned"])

    def test_a_synonym_counts_as_owning_the_category(self):
        index = worn_gear_index(state(inventory=[{"name": "steel gauntlets"}]))
        self.assertFalse(check_unowned_gear(REPORTED, index)["unowned"])

    def test_anatomy_is_never_gear(self):
        """'your beard' and 'your hair' sit in the same table and must not fire."""
        index = worn_gear_index(state())
        report = check_unowned_gear(
            "You drag a hand through your hair, your beard rough against your palm.", index
        )
        self.assertEqual(report["findings"], [])

    def test_a_bag_is_never_flagged(self):
        """Having an inventory implies something to carry it in."""
        index = worn_gear_index(state(appearance="torso: patched overshirt"))
        self.assertEqual(check_unowned_gear("Your pack shifts on your shoulder.", index)["findings"], [])

    def test_someone_elses_gear_is_their_business(self):
        index = worn_gear_index(state())
        report = check_unowned_gear("He tugs his gloves tighter and her boots scrape the step.", index)
        self.assertEqual(report["findings"], [])

    def test_adjectives_do_not_hide_the_noun(self):
        index = worn_gear_index(state())
        self.assertTrue(check_unowned_gear("You flex your thick leather gloves.", index)["unowned"])

    def test_each_noun_is_reported_once(self):
        index = worn_gear_index(state())
        text = "Your gloves catch. Your gloves slip again. Your gloves tear."
        self.assertEqual(len(check_unowned_gear(text, index)["findings"]), 1)

    def test_unstructured_wardrobe_disables_the_check(self):
        index = worn_gear_index(state(appearance="a tall woman with a weathered face"))
        report = check_unowned_gear(REPORTED, index)
        self.assertFalse(report["checked"])
        self.assertEqual(report["findings"], [])

    def test_empty_narration_is_not_a_finding(self):
        self.assertFalse(check_unowned_gear("", worn_gear_index(state()))["unowned"])


class PacketContractTests(unittest.TestCase):
    """
    The wardrobe was never missing from the packet -- `build_user_prompt` sends
    `playthrough_options` whole, appearance included. What was missing was a rule
    covering it: the no-invention rule next to this one is scoped to
    `player_inventory_codes`, which is held inventory, and clothing is not
    inventory here. Both halves are pinned, because either one going away
    restores the bug.
    """

    def test_appearance_reaches_the_model(self):
        from app.prompts import build_user_prompt

        context = {"settings": {"playthrough_options": {"appearance": APPEARANCE}, "setup_complete": True}}
        prompt = build_user_prompt(context, "open the shed")
        self.assertIn("patched overshirt", prompt)
        self.assertIn("scuffed boots", prompt)

    def test_the_wardrobe_is_declared_complete(self):
        from app.prompts import SYSTEM_PROMPT

        self.assertIn("playthrough_options.appearance is the whole of what the player is wearing", SYSTEM_PROMPT)
        self.assertIn("a zone that is not listed is bare", SYSTEM_PROMPT)

    def test_the_rule_names_no_garments(self):
        """
        Concrete instances in these prompts come back as prose, so the rule says
        what is authoritative rather than listing things the player lacks.
        """
        from app.prompts import SYSTEM_PROMPT

        line = next(
            l for l in SYSTEM_PROMPT.splitlines() if "the whole of what the player is wearing" in l
        )
        # Word boundaries, or "hat" matches inside "what" and "that".
        for garment in ("gloves", "hat", "boots", "cloak", "armor", "armour", "hood", "scarf"):
            self.assertIsNone(
                re.search(rf"\b{garment}\b", line, re.I),
                f"{garment!r} in the rule invites it into the prose",
            )


if __name__ == "__main__":
    unittest.main()
