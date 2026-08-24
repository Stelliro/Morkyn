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
from app.prompts import SYSTEM_PROMPT, VERIFY_PROMPT  # noqa: E402
from app.setup_composer import FIELD_CONTRACTS, field_contract  # noqa: E402
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


class TestTheSetupContractsNameNobody(unittest.TestCase):
    """The same leak, one layer up: `FIELD_CONTRACTS` fed the setup prompts.

    `app/llm.py` sends each contract's `forbidden` text on every path, and its
    `examples` on the single-field path, labelled "Good examples for this field
    (adapt, do not copy blindly)". Two fields carried invented proper nouns:

        player_name     Mara Ellison, Tomas Reed, Elena Croft, Kael Morin
                        -- in `examples` AND named again inside `forbidden`
        start_location  Mosswake Gate, Outer Compound Yard, Ferry Landing Stone

    Telling a 7B not to copy a name it has just been shown is the mitigation
    that already failed once, at the top of this file. The rule survives; the
    names do not. Theme-appropriate worked examples are still supplied for
    start_location, but built from this world's own arrival pool at prompt time.
    """

    # Names that were shipped in the contracts, and the ones the leak invented.
    LEAKED_PEOPLE = ("mara ellison", "tomas reed", "elena croft", "kael morin")

    def _contract_text(self, field: str) -> str:
        contract = field_contract(field)
        parts = [str(contract.get("forbidden") or "")]
        parts += [str(e) for e in (contract.get("examples") or [])]
        return " ".join(parts).lower()

    def test_the_player_name_contract_names_no_person(self):
        text = self._contract_text("player_name")
        for name in self.LEAKED_PEOPLE:
            with self.subTest(name=name):
                self.assertNotIn(name, text, f"{name!r} is still shipped to the prompt")

    def test_the_player_name_contract_still_states_the_rule(self):
        text = self._contract_text("player_name")
        self.assertIn("family", text)
        self.assertIn("nickname", text)

    def test_the_start_location_contract_names_no_place(self):
        text = self._contract_text("start_location")
        for name in LEAKED_TOPONYMS:
            with self.subTest(name=name):
                self.assertNotIn(name, text, f"{name!r} is still shipped to the prompt")

    def test_the_start_location_contract_cites_no_real_city(self):
        # "Seoul warehouse" was named here as a counter-example while the repo
        # separately ban-lists it as a motif the model keeps producing.
        self.assertNotIn("seoul", self._contract_text("start_location"))

    def test_the_start_location_contract_still_states_the_rule(self):
        text = self._contract_text("start_location")
        self.assertIn("arrive", text)
        self.assertIn("previous life", text)

    def test_no_setup_contract_ships_an_invented_toponym(self):
        for field, contract in FIELD_CONTRACTS.items():
            blob = " ".join(
                [str(contract.get("forbidden") or "")]
                + [str(e) for e in (contract.get("examples") or [])]
            ).lower()
            for name in LEAKED_TOPONYMS:
                with self.subTest(field=field, name=name):
                    self.assertNotIn(name, blob)


class TestTheNarrationPromptsNameNobody(unittest.TestCase):
    """SYSTEM_PROMPT and VERIFY_PROMPT taught naming by minting names.

        SYSTEM_PROMPT  "Sarah [[A]]" ... Right: "Aria", "Thornrow", "Captain Vesk"
                       "name people (Mara [[A]])" ... "Second Shadow Inn"
        VERIFY_PROMPT  short proper labels (e.g. "Mara", "Dockhand Kesh",
                       "Mosswake Gate")

    Six invented people and two invented places, shipped on every turn of every
    world, in the four rules whose whole subject is what a name should look
    like. That is the strongest possible position for a name to be copied out
    of, and it is the same mistake as "Riverbend Camp" at the top of this file.

    The rules are all still here -- the name goes before the code, a
    description is not a name, gear is not a person, a place is not a brand --
    stated as shapes rather than as examples. The counter-examples that are
    generic nouns ("Woman", "Old Man", "Hooded Figure") are deliberately kept:
    those are the anti-pattern itself, not a name waiting to be borrowed.
    """

    INVENTED = (
        "sarah",
        "aria",
        "thornrow",
        "vesk",
        "mara",
        "kesh",
        "second shadow",
    )

    def test_the_system_prompt_mints_no_person(self):
        low = SYSTEM_PROMPT.lower()
        for name in self.INVENTED:
            with self.subTest(name=name):
                self.assertNotIn(name, low, f"{name!r} is still shipped in SYSTEM_PROMPT")

    def test_the_verify_prompt_mints_no_person(self):
        low = VERIFY_PROMPT.lower()
        for name in self.INVENTED:
            with self.subTest(name=name):
                self.assertNotIn(name, low, f"{name!r} is still shipped in VERIFY_PROMPT")

    def test_neither_narration_prompt_names_a_place(self):
        for label, text in (("SYSTEM_PROMPT", SYSTEM_PROMPT), ("VERIFY_PROMPT", VERIFY_PROMPT)):
            for name in LEAKED_TOPONYMS:
                with self.subTest(prompt=label, name=name):
                    self.assertNotIn(name, text.lower())

    def test_the_code_placement_rule_survives(self):
        # The format is the point of that line; losing it would cost the UI its links.
        low = SYSTEM_PROMPT.lower()
        self.assertIn("[[a]]", low)
        self.assertIn("[[l2]]", low)
        self.assertIn("name/title first", low)
        self.assertIn("never use a code with no name in front of it", low)

    def test_the_description_is_not_a_name_rule_survives(self):
        low = SYSTEM_PROMPT.lower()
        self.assertIn("real name, not a description", low)
        # The generic-noun counter-examples stay: they are the anti-pattern.
        for bad in ("woman", "old man", "hooded figure", "guard", "stranger"):
            with self.subTest(bad=bad):
                self.assertIn(bad, low)


if __name__ == "__main__":
    unittest.main()
