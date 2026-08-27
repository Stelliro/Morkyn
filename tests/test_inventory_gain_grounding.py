"""A gain needs the prose to name the item AND to say it arrived.

Reported from play: the player started with an item literally named "seed in
hand", inspected it, and was given two more. The narration said nothing about
acquiring anything.

Two separate holes made that possible.

1. `_filter_inventory_changes` skipped the check entirely for items already
   owned -- "losses and updates to existing stacks always ok". A quantity
   increase is a gain, not an update, and the item a model is most likely to
   inflate is the one it is currently describing at length.

2. The grounding test for a gain was "is this item named in the prose?". When
   you inspect a seed, the narration is *entirely about* a seed, so that test
   passes trivially. Naming an item is not acquiring it.

So a gain now needs both halves. The awkward part is the second one: English
uses the same words for looking and taking. "You find a rusty nail" is an
acquisition and "you find the husk is dry" is not. The determiner is what
separates them, and that is what `_DISCOVER_GAIN_RE` keys on.

Run:  python -m unittest tests.test_inventory_gain_grounding
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-invgain-test-"))
os.environ.update({
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
})

from app.db import connect, init_db  # noqa: E402
from app.world import _filter_inventory_changes, _prose_says_it_arrived  # noqa: E402

init_db()

INSPECT_SEED = (
    "You turn the seed in hand over between thumb and forefinger. The husk is dry, "
    "faintly ridged, and warm from your pocket. Nothing about it suggests it is "
    "anything but a seed."
)


_seq = iter(range(1, 10_000))


def _run(name, delta, *, owned=0, narration="", player_input="", input_kind="player"):
    with connect() as conn:
        conn.execute("DELETE FROM inventory WHERE name = ?", (name,))
        if owned:
            # inventory.code is UNIQUE, so every seeded row needs its own.
            conn.execute(
                "INSERT INTO inventory (code, name, quantity, description) VALUES (?, ?, ?, ?)",
                (f"IT{next(_seq)}", name, owned, "test item"),
            )
        return _filter_inventory_changes(
            conn,
            [{"name": name, "quantity_delta": delta}],
            narration=narration,
            player_input=player_input,
            input_kind=input_kind,
        )


class TestTheReportedBug(unittest.TestCase):
    def test_inspecting_an_owned_item_does_not_multiply_it(self):
        kept = _run("seed in hand", 2, owned=1,
                    narration=INSPECT_SEED, player_input="I inspect the seed in hand")
        self.assertEqual(kept, [], "inspecting an item must not grant more of it")

    def test_the_item_name_containing_a_verb_does_not_count_as_one(self):
        # "seed in hand" + "turn the seed in hand over" reads as "hand ... over"
        # unless inflection is required on the verb. This is why that guard
        # exists; it is not hypothetical tidying.
        self.assertFalse(_prose_says_it_arrived(INSPECT_SEED.lower(), "seed in hand", ["seed", "hand"]))

    def test_the_rejection_is_recorded(self):
        _run("seed in hand", 2, owned=1, narration=INSPECT_SEED, player_input="I inspect it")
        with connect() as conn:
            row = conn.execute(
                "SELECT content FROM journal WHERE kind = 'inventory_reject' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(row, "a silent rejection is as bad as a silent grant")
        self.assertIn("seed in hand", row["content"])


class TestOwnedItemsAreNotExempt(unittest.TestCase):
    """The whole class of bug, not just the seed."""

    def test_an_ungrounded_gain_on_an_owned_item_is_rejected(self):
        for name, narration in (
            ("iron sword", "You study the iron sword closely. The blade is notched near the guard."),
            ("lantern", "The lantern hangs where it always hangs. You have carried it a long way."),
            ("coin pouch", "The coin pouch you already carry feels lighter than it did."),
        ):
            with self.subTest(item=name):
                self.assertEqual(_run(name, 3, owned=1, narration=narration, player_input="I look"), [])

    def test_a_grounded_gain_on_an_owned_item_is_allowed(self):
        for narration, player_input in (
            ("You gather two more seeds from the pouch and add them to your pack.", "I gather seeds"),
            ("The farmer presses two more seeds into your palm.", "I talk to the farmer"),
            ("You pick up two seeds from the sack.", "I look around"),
        ):
            with self.subTest(narration=narration[:32]):
                kept = _run("seed in hand", 2, owned=1, narration=narration, player_input=player_input)
                self.assertEqual(len(kept), 1, "a real gain must still land")

    def test_player_intent_alone_carries_a_gain(self):
        # The player said to take it. Terse narration must not lose the item.
        kept = _run("brass key", 1, owned=1, narration="Done.", player_input="I take the brass key")
        self.assertEqual(len(kept), 1)


class TestLossesAndMetadataAreUntouched(unittest.TestCase):
    def test_a_loss_needs_no_grounding(self):
        kept = _run("seed in hand", -1, owned=3, narration="Nothing in particular.", player_input="I wait")
        self.assertEqual(len(kept), 1)

    def test_a_zero_delta_needs_no_grounding(self):
        kept = _run("seed in hand", 0, owned=3, narration="Nothing in particular.", player_input="I wait")
        self.assertEqual(len(kept), 1)


class TestPerceptionIsNotAcquisition(unittest.TestCase):
    """English reuses the same verbs for looking and taking."""

    def test_looking_verbs_do_not_read_as_gains(self):
        for narration in (
            "You find the husk of the seed is drier than you remember.",
            "You take in the sight of the iron sword on the rack.",
            "You take stock of the seed and decide to wait.",
            "You found the map you were already carrying was water-damaged.",
            "You spot the lantern's wick has burned down to a stub.",
        ):
            with self.subTest(narration=narration[:36]):
                self.assertFalse(
                    _prose_says_it_arrived(narration.lower(), "seed", ["seed"]),
                    f"{narration!r} describes looking, not taking",
                )

    def test_taking_verbs_do_read_as_gains(self):
        for narration, name in (
            ("You find a rusty nail wedged between two boards.", "rusty nail"),
            ("You loot a God Sword from the chest.", "god sword"),
            ("She hands you a silver key without a word.", "silver key"),
            ("You are given a wool cloak against the cold.", "wool cloak"),
            ("You unearth a clay jar from beneath the flagstones.", "clay jar"),
            ("You buy a bread loaf for two coppers.", "bread loaf"),
            ("You craft a healing salve from the reagents.", "healing salve"),
        ):
            with self.subTest(narration=narration[:36]):
                tokens = [t for t in name.split() if len(t) >= 4]
                self.assertTrue(
                    _prose_says_it_arrived(narration.lower(), name, tokens),
                    f"{narration!r} describes an acquisition",
                )


class TestNewItemsStillNeedBothHalves(unittest.TestCase):
    def test_a_named_but_unacquired_new_item_is_rejected(self):
        kept = _run("rusty key", 1, owned=0,
                    narration="A rusty key lies on the table, furred with corrosion.",
                    player_input="I look at the table")
        self.assertEqual(kept, [], "seeing an item on a table is not picking it up")

    def test_a_named_and_acquired_new_item_is_kept(self):
        kept = _run("rusty key", 1, owned=0,
                    narration="You pick up the rusty key from the table.",
                    player_input="I take the key")
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
