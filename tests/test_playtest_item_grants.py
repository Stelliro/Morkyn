"""
Playtest issue #9: two loaves and two tarts from asking a question.

Turn 2 of the 2026-10-05 playtest. The player said to the baker "these
interest you Aria?". The draft wrote GRANT "loaf of bread" QTY small and GRANT
"sweet tart" QTY small; the engine rolled "small" as 1d2 and both came up 2.
The final prose had the baker offer a tart, the player take a bite and hand it
back, so the player should have gained nothing at all. The same prose said
"The baker at CAR": the mention "@Caria" had been read as the code CAR.

Four parts, one class each:
  (a) an item band is a count of objects, not an amount of stuff;
  (b) a gain is grounded per item, by a hand-over, never by a touch or a look;
  (c) the FINAL prose decides, so a hand-back after an offer is no gain;
  (d) "@Caria" is not the code CAR, and a dangling code never reaches prose.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from playtest_setup_presets import isolated_data_env  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-item-grants-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import db, rng, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.llm import _repair_entity_names_in_turn  # noqa: E402
from app.turn_dsl import parse_dsl_turn  # noqa: E402

# The turn-2 texts, as the trace recorded them.
DRAFT = (
    "You step into the baker's shop, Aria's shop, and she looks up from her dough.\n\n"
    "Aria gestures to a counter piled with loaves and pastries. \"These interest you, Aria?\" "
    "you ask, pointing to a selection of breads and pies.\n\n"
    "You can feel the weight of her scrutiny, but you're curious about her stock. "
    "\"I am interested,\" you say, reaching out to touch a crusty loaf.\n\n"
    "Aria's tone softens slightly. \"Fresh from the oven, these are.\"\n\n"
    "You take a loaf and a tart, the warmth of the bread in your hands a welcome change "
    "from the crisp morning air."
)
FINAL = (
    "You step into the Back Lane [[L1]], where Aria [[A]] stands with a basket filled with "
    "various treats. \"These interest you, Aria [[A]]?\" you ask, gesturing to a loaf of fresh "
    "bread and a sweet tart. Aria [[A]]'s eyes light up as she considers them, her fingers "
    "brushing the crust of the tart.\n\n"
    "\"The baker insists it's made from a rare flower,\" she says. \"I must try it.\" She offers "
    "you a piece, the tart still warm in her hand. You consider, then take a bite, the sweetness "
    "flooding your senses.\n\n"
    "You savor the tart, then hand it back to Aria [[A]] with a smile. Aria [[A]]'s eyes gleam "
    "with amusement as she takes the tart. \"The baker at CAR certainly knows his craft,\" she muses."
)
OPS = (
    "===NAR===\n" + DRAFT + "\n===OPS===\n"
    'GRANT "loaf of bread" QTY small\n'
    'GRANT "sweet tart" QTY small\n'
)
PLAYER_INPUT = 'i say to Aria [[A]] "these interest you Aria?"'


def _tokens(name: str) -> list[str]:
    return re.findall(r"[a-z0-9']{4,}", name.lower())


def _filter(changes, *, narration, draft="", player_input=PLAYER_INPUT):
    with connect() as conn:
        for change in changes:
            conn.execute("DELETE FROM inventory WHERE name = ?", (change["name"],))
        return world._filter_inventory_changes(
            conn,
            [dict(c) for c in changes],
            narration=narration,
            player_input=player_input,
            draft_narration=draft,
        )


class TestItemBandsAreCounts(unittest.TestCase):
    """(a) "QTY small" on one loaf means one loaf, on every roll."""

    def test_each_band_is_a_fixed_small_count(self):
        expected = {"trivial": 1, "small": 1, "moderate": 2, "large": 3, "huge": 5}
        for band, count in expected.items():
            for seed in range(40):
                with self.subTest(band=band, seed=seed):
                    self.assertEqual(rng.resolve_magnitude("item_count", band, seed=seed)["value"], count)

    def test_the_turn_two_grants_resolve_to_one_each(self):
        db.init_db()
        turn = parse_dsl_turn(OPS, PLAYER_INPUT)
        with connect() as conn:
            world.resolve_turn_bands(conn, turn, turn=2, options={})
        counts = {c["name"]: c["quantity_delta"] for c in turn["inventory_changes"]}
        self.assertEqual(counts, {"loaf of bread": 1, "sweet tart": 1})

    def test_an_explicit_count_is_honoured(self):
        db.init_db()
        turn = {"inventory_changes": [{"name": "arrow", "quantity_delta": 20}]}
        with connect() as conn:
            world.resolve_turn_bands(conn, turn, turn=2, options={})
        self.assertEqual(turn["inventory_changes"][0]["quantity_delta"], 20)

    def test_a_take_band_is_a_count_too(self):
        db.init_db()
        turn = {"inventory_changes": [{"name": "arrow", "quantity_band": "-small"}]}
        with connect() as conn:
            world.resolve_turn_bands(conn, turn, turn=2, options={})
        self.assertEqual(turn["inventory_changes"][0]["quantity_delta"], -1)


class TestTheReportedTurn(unittest.TestCase):
    """(b)+(c) together: the exact turn grants nothing."""

    def setUp(self):
        db.init_db()

    def test_turn_two_grants_nothing(self):
        kept = _filter(
            [{"name": "loaf of bread", "quantity_delta": 1}, {"name": "sweet tart", "quantity_delta": 1}],
            narration=FINAL,
            draft=DRAFT,
        )
        self.assertEqual(kept, [], "asking a question and handing a tart back is no gain")

    def test_the_rejection_names_the_prose_outcome(self):
        _filter([{"name": "sweet tart", "quantity_delta": 1}], narration=FINAL, draft=DRAFT)
        with connect() as conn:
            row = conn.execute(
                "SELECT content FROM journal WHERE kind = 'inventory_reject' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIn("sweet tart", row["content"])
        self.assertIn("prose_outcome=loss", row["content"])


class TestGainsAreGroundedPerItem(unittest.TestCase):
    """(b) a mention, a touch or a look is not a hand-over."""

    def outcome(self, text, name, owned=False):
        return world._prose_item_outcome(text, name, _tokens(name), owned=owned)

    def test_touching_and_looking_are_not_gains(self):
        for text in (
            "\"I am interested,\" you say, reaching out to touch a crusty loaf.",
            "You gesture to a loaf of fresh bread on the counter.",
            "The loaf of bread sits cooling by the window.",
        ):
            with self.subTest(text=text[:40]):
                self.assertIsNone(self.outcome(text, "loaf of bread"))

    def test_a_hand_over_elsewhere_does_not_ground_this_item(self):
        text = "Aria hands you a sweet tart. A loaf of bread cools on the sill."
        self.assertEqual(self.outcome(text, "sweet tart"), "gain")
        self.assertIsNone(self.outcome(text, "loaf of bread"))

    def test_real_hand_overs_are_gains(self):
        for text in (
            "Aria hands you a loaf of bread, still warm.",
            "You buy a loaf of bread for two coppers.",
            "You pick up the loaf of bread from the counter.",
            "She wraps a loaf of bread in cloth. She presses it into your hands.",
            "You tuck the loaf of bread into your pack.",
        ):
            with self.subTest(text=text[:40]):
                self.assertEqual(self.outcome(text, "loaf of bread"), "gain")

    def test_someone_else_taking_it_is_not_your_gain(self):
        self.assertIsNone(self.outcome("Aria takes the sweet tart from the tray.", "sweet tart"))

    def test_a_bite_is_not_a_pickup(self):
        self.assertIsNone(self.outcome("You take a bite of the sweet tart.", "sweet tart"))


class TestTheFinalProseDecides(unittest.TestCase):
    """(c) the last word on the item, in the text the player reads, wins."""

    def setUp(self):
        db.init_db()

    def test_offered_then_handed_back_is_a_loss(self):
        text = "She offers you a sweet tart. You savor it, then hand it back to her."
        self.assertEqual(world._prose_item_outcome(text, "sweet tart", _tokens("sweet tart")), "loss")

    def test_refused_and_eaten_are_not_gains(self):
        for text in (
            "Aria offers you a sweet tart, but you decline it with a smile.",
            "Aria hands you a sweet tart and you eat it on the spot.",
            "Aria refuses to part with the sweet tart.",
        ):
            with self.subTest(text=text[:40]):
                kept = _filter([{"name": "sweet tart", "quantity_delta": 1}], narration=text,
                               player_input="I ask about the tart")
                self.assertEqual(kept, [])

    def test_handed_back_to_you_is_a_gain(self):
        text = "You give her the sweet tart to inspect. She hands it back to you, satisfied."
        self.assertEqual(world._prose_item_outcome(text, "sweet tart", _tokens("sweet tart")), "gain")

    def test_a_draft_hand_over_the_final_prose_drops_is_not_granted(self):
        kept = _filter(
            [{"name": "loaf of bread", "quantity_delta": 1}],
            narration="You gesture to a loaf of fresh bread and ask what it costs.",
            draft="Aria hands you a loaf of bread.",
        )
        self.assertEqual(kept, [])

    def test_a_grant_the_final_prose_describes_lands(self):
        kept = _filter(
            [{"name": "loaf of bread", "quantity_delta": 1}],
            narration="Aria wraps the loaf of bread in cloth and hands you the bundle.",
            draft="Aria hands you a loaf of bread.",
        )
        self.assertEqual([c["name"] for c in kept], ["loaf of bread"])

    def test_player_intent_still_carries_a_terse_final(self):
        kept = _filter(
            [{"name": "loaf of bread", "quantity_delta": 1}],
            narration="Done.",
            player_input="I buy a loaf of bread",
        )
        self.assertEqual(len(kept), 1)


class TestMentionsAreNotCodes(unittest.TestCase):
    """(d) "@Caria" is a mention, and no dangling code reaches the prose."""

    def test_a_mention_is_not_read_as_a_code(self):
        refs = world._explicit_turn_references('i say to @Caria "these interest you Aria?"')
        self.assertNotIn("CAR", refs["all"])
        self.assertEqual(world._explicit_turn_references("I wave at @A")["all"], ["A"])
        self.assertEqual(world._explicit_turn_references("I wave at @BRN.")["all"], ["BRN"])

    def _repair(self, narration, *, refs, npcs):
        context = {
            "locations": [{"code": "L1", "name": "Back Lane", "npcs": npcs}],
            "turn_plan": {"explicit_references": {"all": refs}},
            "action_context": {"hard_reference_codes": refs, "target_codes": {"npcs": refs}},
        }
        return _repair_entity_names_in_turn({"narration": narration}, context)["narration"]

    def test_the_reported_line_loses_the_dangling_code(self):
        out = self._repair(FINAL, refs=["A", "CAR"], npcs=[{"code": "A", "name": "Aria"}])
        self.assertNotIn("CAR", out)
        self.assertIn('"The baker certainly knows his craft,"', out)

    def test_a_dangling_code_as_subject_becomes_someone(self):
        out = self._repair("Aria smiles. CAR nods from the doorway.", refs=["CAR"],
                           npcs=[{"code": "A", "name": "Aria"}])
        self.assertIn("Someone nods", out)

    def test_a_known_bare_code_is_rendered_as_its_name(self):
        out = self._repair("Bram leans on the cart. Then BRN waves you over.", refs=[],
                           npcs=[{"code": "BRN", "name": "Bram"}])
        self.assertIn("Bram [[BRN]] waves", out)
        self.assertNotRegex(out, r"(?<!\[\[)\bBRN\b(?!\]\])")


if __name__ == "__main__":
    unittest.main()
