"""Regression tests: no prompt rule ships an invented place name.

Two toponyms were hardcoded as worked examples in the movement rules --
"Riverbend Camp" in both `movement_contract()` and the DSL rule block, and
"Redmill Ford" in the DSL MOVE line -- and they went into every turn of every
world. Counted across the 42 recorded playtest databases still on disk:

    170 place names total
     36 contain "Riverbend"
      8 contain "Redmill"
     -> 21 of 42 worlds carry at least one

That is 26% of every place the game has ever named, and it is why a high-fantasy
campaign set up for "high fantasy with open magic and old empires", opening at
The Sunken Colonnade, spent its second half in Riverbend Piers and Riverbend
Village. The genre words the run looked for scored 1 of 8. A 7B handed a
concrete name in an instruction does not read it as a placeholder.

The rule still needs a worked example to land, so `_movement_rule_example()`
builds one from the world's own map -- a known place, or failing that the place
the player is standing in, which is the name most likely to get a word bolted
onto it. Copying that example costs nothing: the move resolves to a row that
already exists instead of minting a river hamlet in someone's space opera.

Run:  python -m unittest tests.test_prompt_exemplar_leak
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-exemplar-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app.turn_dsl import DSL_SYSTEM_PROMPT  # noqa: E402
from app.world import _movement_rule_example, movement_contract  # noqa: E402

# The names that leaked, plus the ones the earlier runs invented around them.
LEAKED_TOPONYMS = ("riverbend", "redmill", "mosswake", "hillcrest", "grainwick")


def _state(current: str, *others: str) -> dict:
    locations = [{"code": "L1", "name": current, "parent_id": 0}]
    locations += [
        {"code": f"L{i + 2}", "name": name, "parent_id": 0} for i, name in enumerate(others)
    ]
    return {"current_location": {"code": "L1", "name": current}, "locations": locations}


class TestTheShippedRulesNameNoPlace(unittest.TestCase):
    def test_the_dsl_prompt_carries_no_invented_toponym(self):
        low = DSL_SYSTEM_PROMPT.lower()
        for name in LEAKED_TOPONYMS:
            with self.subTest(name=name):
                self.assertNotIn(name, low, f"{name!r} is still shipped in DSL_SYSTEM_PROMPT")

    def test_the_dsl_prompt_still_teaches_the_move_op(self):
        # Removing the example must not remove the rule.
        low = DSL_SYSTEM_PROMPT.lower()
        self.assertIn("move takes a place name", low)
        self.assertIn("move l2", low)  # the code counter-example is the point

    def test_the_dsl_prompt_still_forbids_extending_a_known_name(self):
        low = DSL_SYSTEM_PROMPT.lower()
        self.assertIn("known_places", low)
        self.assertIn("word added", low)

    def test_the_movement_contract_names_no_invented_place(self):
        rule = movement_contract(_state("The Sunken Colonnade"), "walk east", "travel")["rule"]
        for name in LEAKED_TOPONYMS:
            with self.subTest(name=name):
                self.assertNotIn(name, rule.lower())


class TestTheExampleComesFromThisWorld(unittest.TestCase):
    def test_a_known_place_is_used_when_there_is_one(self):
        rule = movement_contract(
            _state("Docking Bay Seven", "Reactor Deck"), "walk on", "travel"
        )["rule"]
        self.assertIn("Reactor Deck", rule)

    def test_turn_one_falls_back_to_where_the_player_stands(self):
        # known_places deliberately excludes the current location, so the very
        # first turn has none -- and the current name is the one most likely to
        # be extended ("Mosswake Gate" -> "Mosswake Gate Market Square").
        rule = movement_contract(_state("The Sunken Colonnade"), "walk east", "travel")["rule"]
        self.assertIn("The Sunken Colonnade", rule)

    def test_an_empty_world_still_states_the_rule(self):
        example = _movement_rule_example([], "")
        self.assertIn("known_places", example)
        self.assertIn("added or removed", example)

    def test_the_example_shows_both_directions(self):
        example = _movement_rule_example([{"code": "L1", "name": "Calico Junction Depot"}])
        self.assertIn("Calico Junction Depot East", example)
        self.assertIn("last word dropped", example)

    def test_a_blank_name_in_the_map_is_skipped(self):
        example = _movement_rule_example(
            [{"code": "L1", "name": ""}, {"code": "L2", "name": "Neon Market District"}]
        )
        self.assertIn("Neon Market District", example)

    def test_the_example_never_invents_a_word_of_its_own(self):
        # Everything in the sentence is either the world's own name or fixed
        # instruction text -- no third toponym can appear.
        for world in ("Docking Bay Seven", "The Sunken Colonnade", "Sublevel Four"):
            with self.subTest(world=world):
                example = _movement_rule_example([{"code": "L1", "name": world}])
                leftover = example.replace(world, " ")
                capitalized = re.findall(r"(?<![.\"] )\b[A-Z][a-z]+", leftover)
                self.assertEqual(
                    [w for w in capitalized if w not in {"East", "Either"}],
                    [],
                    f"unexpected proper noun in {example!r}",
                )


if __name__ == "__main__":
    unittest.main()
