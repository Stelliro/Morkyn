"""
Playtest issues #13, #14 and #15, game 2 ("Eldoria's Edge"), turns 1-2.

#13  The opening said "She hands you a crusty loaf" and the draft wrote
     GRANT "loaf of bread" QTY small, but the journal read "Rejected unearned
     gain: loaf of bread x1 (named=True, prose_says_arrived=True ...)": the
     opening refused every item the player did not already own. The kit rule
     is about weapons, armour and better-than-ordinary loot, not a loaf.
#14  The draft prompt shipped "Aria", "Thornrow", "Captain Vesk" and the jobs
     carter, net mender, baker; two games in a row opened on Aria the baker
     next to a net mender. The same opening then said "A net mender named Aria
     weaves a new net": one name on two people.
#15  The depth retry wrote "Aria's [[A]] story" and the name repair made it
     "Aria [[A]]'s [[A]] story".
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-opening-names-"))
os.environ.update(isolated_data_env(str(_TMP)))
os.environ.update(
    {
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import db, llm, world  # noqa: E402
from app.db import connect  # noqa: E402
from app.prompts import SYSTEM_PROMPT  # noqa: E402
from app.setup_composer import opening_feel_prompt_block  # noqa: E402
from app.turn_dsl import DSL_SYSTEM_PROMPT, parse_dsl_turn  # noqa: E402

# Turn 1, as turn-000001-opening.json recorded it.
DRAFT = (
    "A baker, her face etched with a resolute expression, calls out a warm greeting, \"Good morn, "
    "traveler. A loaf of fresh bread will lift your spirits.\" She hands you a crusty loaf, and the "
    "warmth of the bread is a welcome comfort in the cool air.\n\n"
    "To your east, the market stalls begin to open, and vendors are arranging their goods. A net "
    "mender, [[A]], is weaving a new net, his hands steady and practiced."
)
FINAL = (
    "A baker, her face etched with a resolute expression, calls out a warm greeting: \"Good morn, "
    "traveler.\"\n\n"
    "She hands you a crusty loaf, and the warmth of the bread is a welcome comfort in the cool air. "
    "Aria, the baker, glances your way, her gaze narrowing slightly, as if sizing you up. To your "
    "east, the market stalls begin to open, and vendors are arranging their goods. A net mender "
    "named Aria weaves a new net, her hands steady and practiced. Her gaze briefly meets yours "
    "before she returns to her work."
)
OPENING_INPUT = "__opening_scene_request__: begin"


def _opening_filter(changes, *, narration=FINAL, draft=DRAFT):
    with connect() as conn:
        for change in changes:
            conn.execute("DELETE FROM inventory WHERE name = ?", (change["name"],))
        return world._filter_inventory_changes(
            conn,
            [dict(c) for c in changes],
            narration=narration,
            player_input=OPENING_INPUT,
            input_kind="opening",
            draft_narration=draft,
        )


def _granted(ops_line: str) -> dict:
    turn = parse_dsl_turn("===NAR===\n" + DRAFT + "\n===OPS===\n" + ops_line + "\n", OPENING_INPUT)
    change = dict(turn["inventory_changes"][0])
    change["quantity_delta"] = 1
    return change


class TestOpeningGiftIsKept(unittest.TestCase):
    """#13: a hand-over of ordinary goods in the opening is a grounded gain."""

    def setUp(self):
        db.init_db()

    def test_the_logged_loaf_reaches_the_inventory(self):
        kept = _opening_filter([_granted('GRANT "loaf of bread" QTY small')])
        self.assertEqual([c["name"] for c in kept], ["loaf of bread"])

    def test_kit_is_still_refused_at_the_opening(self):
        cases = {
            "a weapon by name": ('GRANT "loaf of bread" QTY small', {"name": "short sword"}),
            "a weapon by type": ('GRANT "loaf of bread" QTY small TYPE weapon', {}),
            "armour": ('GRANT "loaf of bread" QTY small', {"name": "leather armor"}),
            "a rare item": ('GRANT "loaf of bread" QTY small RARITY rare', {}),
            "an enchanted item": ('GRANT "loaf of bread" QTY small', {"enchantments": ["warm forever"]}),
        }
        for label, (line, override) in cases.items():
            with self.subTest(label):
                change = {**_granted(line), **override}
                text = FINAL.replace("crusty loaf", change["name"]) if "name" in override else FINAL
                kept = _opening_filter([change], narration=text, draft=DRAFT.replace("crusty loaf", change["name"]))
                self.assertEqual(kept, [])

    def test_a_gift_the_final_prose_never_hands_over_is_refused(self):
        text = "A baker calls out a warm greeting. A loaf of bread cools on her sill."
        kept = _opening_filter([_granted('GRANT "loaf of bread" QTY small')], narration=text)
        self.assertEqual(kept, [])

    def test_ordinary_goods_pass_the_kit_check(self):
        for change in (
            {"name": "loaf of bread", "item_type": "misc", "rarity": "common"},
            {"name": "wooden bowl", "item_type": "misc", "rarity": "common"},
            {"name": "apple", "item_type": "consumable", "rarity": ""},
        ):
            with self.subTest(change["name"]):
                self.assertFalse(world._is_opening_kit(change))


class TestDraftPromptShipsNoSampleNamesOrJobs(unittest.TestCase):
    """#14: the prompt surface names nobody and gives no sample jobs."""

    SAMPLES = ("aria", "thornrow", "vesk", "carter", "net mender", "baker", "ferryman", '\\"rope\\"', '"rope"',
               "sarah", "low gate timber arch", "elena croft", "tomas reed")

    def test_no_prompt_carries_a_sample(self):
        prompts = {
            "DSL_SYSTEM_PROMPT": DSL_SYSTEM_PROMPT,
            "SYSTEM_PROMPT": SYSTEM_PROMPT,
            "opening lines": opening_feel_prompt_block({}, {}),
        }
        llm_src = (ROOT / "app" / "llm.py").read_text(encoding="utf-8")
        start = llm_src.index('"name_rules": [')
        prompts["name retry rules"] = llm_src[start: llm_src.index("]", start)]
        for label, text in prompts.items():
            low = text.lower()
            for sample in self.SAMPLES:
                with self.subTest(prompt=label, sample=sample):
                    self.assertNotIn(sample, low)

    def test_the_rules_are_still_stated(self):
        self.assertIn("NPC_NEW NAME is the person's own given name", DSL_SYSTEM_PROMPT)
        self.assertIn("NPC_NEW ROLE is the person's occupation", DSL_SYSTEM_PROMPT)
        self.assertIn("GRANT takes the item's name in quotes", DSL_SYSTEM_PROMPT)


class TestOneNameIsNotTwoPeople(unittest.TestCase):
    """#14: a known name on a different job's introduction comes off and is traced."""

    CONTEXT = {"npcs": [{"code": "A", "name": "Aria", "role": "baker"}]}

    def _repair(self, narration):
        turn = {"narration": narration, "npcs": [{"code": "A", "name": "Aria", "role": "baker"}]}
        return llm._repair_entity_names_in_turn(turn, self.CONTEXT)

    def test_the_logged_opening(self):
        out = self._repair(FINAL)
        self.assertIn("A net mender weaves a new net", out["narration"])
        self.assertNotIn("named Aria", out["narration"])
        self.assertIn("Aria [[A]], the baker", out["narration"])
        self.assertEqual(
            out["name_reuses"],
            [{"code": "A", "name": "Aria", "stored": "baker", "prose": "net mender"}],
        )

    def test_the_same_job_keeps_the_name(self):
        out = self._repair("A baker named Aria waves you over.")
        self.assertIn("named Aria [[A]]", out["narration"])
        self.assertNotIn("name_reuses", out)

    def test_a_plain_description_keeps_the_name(self):
        out = self._repair("A woman named Aria waves you over.")
        self.assertIn("named Aria [[A]]", out["narration"])
        self.assertNotIn("name_reuses", out)

    def test_an_unknown_name_is_left_alone(self):
        out = self._repair("A net mender named Brisk weaves a new net.")
        self.assertIn("named Brisk", out["narration"])


class TestPossessiveNameWithCode(unittest.TestCase):
    """#15: "Name's [[CODE]]" already has the name; the code moves, once."""

    RETRY = "The apprentice glances up, her eyes wide with interest, as if she's listening to Aria's [[A]] story."

    def test_the_exact_trace_string(self):
        out = llm._repair_prose_entity_labels(self.RETRY, {"A": "Aria", "L1": "Eldoria's Edge"})
        self.assertIn("listening to Aria [[A]]'s story.", out)
        self.assertEqual(out.count("[[A]]"), 1)

    def test_through_the_turn_repair(self):
        turn = {
            "narration": self.RETRY,
            "narration_segments": [{"text": self.RETRY}],
            "npcs": [{"code": "A", "name": "Aria", "role": "baker"}],
        }
        out = llm._repair_entity_names_in_turn(turn, {"npcs": [{"code": "A", "name": "Aria", "role": "baker"}]})
        self.assertIn("Aria [[A]]'s story", out["narration"])
        self.assertNotIn("[[A]]'s [[A]]", out["narration"])

    def test_curly_apostrophe_and_already_right_forms(self):
        cmap = {"A": "Aria"}
        self.assertIn("Aria [[A]]’s story", llm._repair_prose_entity_labels("Aria’s [[A]] story.", cmap))
        self.assertIn("Aria [[A]]'s story", llm._repair_prose_entity_labels("Aria [[A]]'s story.", cmap))
        self.assertIn("Aria [[A]]'s story", llm._repair_prose_entity_labels("Aria's story.", cmap))


if __name__ == "__main__":
    unittest.main()
