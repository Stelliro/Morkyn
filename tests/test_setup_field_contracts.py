"""Regression tests: the randomizer tells the model which fields are closed enums.

A multi-field group roll shipped `return_fields` as a bare list of names with no
shape attached -- no return_shape, no field contracts, nothing marking
magic_level as one of five fixed strings. The contracts already existed and were
already sent on the single-field and repair paths; the group path was the one
caller asking a closed question in open form.

Measured live over eight rolls, the model answered magic_level with "low",
"Low", "low-magic", "post", and "Limited to arcane crafters and guilds". Every
one of those falls through `normalize_magic_level` to its default, so the stored
value was "rare" on 12 rolls out of 12. With the contracts attached the model
returned canonical values verbatim -- common utility, cultivation, forbidden --
and nothing needed normalizing at all.

The other guards here catch what a spark package leaks into a setup form: a raw
card id used as a value, a card's examples line used as a place, and one card
title filling two fields at once.

Run:  python -m unittest tests.test_setup_field_contracts
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-contracts-test-"))
_ENV = {
    "AI_RPG_DB": str(_TMP / "world.db"),
    "AI_RPG_PACK_DIR": str(_TMP / "packs"),
    "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
    "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
    "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
    "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
}
os.environ.update(_ENV)

from app import llm  # noqa: E402
from app.setup_composer import (  # noqa: E402
    MAGIC_LEVEL_VALUES,
    empty_intent,
    field_contamination_reasons,
    looks_like_card_slug,
)


class TestTheGroupPromptCarriesTheContracts(unittest.TestCase):
    def _prompt(self, group: str = "world") -> dict:
        captured: dict = {}

        def fake_chat(system, user, **kwargs):
            captured["user"] = user
            raise RuntimeError("stop after prompt build")

        original = llm._chat_json
        llm._chat_json = fake_chat
        try:
            llm.generate_setup_randomization(group, {})
        except Exception:
            pass
        finally:
            llm._chat_json = original
        return json.loads(captured["user"])

    def test_the_world_group_ships_field_contracts(self):
        prompt = self._prompt("world")
        self.assertIn("field_contracts", prompt)
        self.assertTrue(prompt["field_contracts"])

    def test_magic_level_arrives_with_its_five_allowed_values(self):
        contracts = self._prompt("world")["field_contracts"]
        self.assertIn("magic_level", contracts)
        self.assertEqual(
            [v.lower() for v in contracts["magic_level"]["allowed_values"]],
            [v.lower() for v in MAGIC_LEVEL_VALUES],
        )

    def test_every_requested_field_gets_a_contract(self):
        prompt = self._prompt("world")
        for field in prompt["return_fields"]:
            self.assertIn(field, prompt["field_contracts"], f"{field} has no contract")

    def test_a_boolean_field_is_marked_boolean(self):
        contracts = self._prompt("world")["field_contracts"]
        self.assertEqual(contracts["race_magic_enabled"]["kind"], "boolean")

    def test_the_rules_say_the_contract_is_binding(self):
        rules = " ".join(self._prompt("world")["rules"]).lower()
        self.assertIn("allowed_values", rules)

    def test_the_helper_survives_an_unknown_field(self):
        # field_contract() answers with a default short_phrase shape rather
        # than raising, so an unrecognised name costs a line, not a crash.
        self.assertEqual(llm._field_contracts_for_prompt([]), {})
        self.assertEqual(
            llm._field_contracts_for_prompt(["not_a_real_field"]),
            {"not_a_real_field": {"kind": "short_phrase"}},
        )


class TestRawCardIdsAreRefused(unittest.TestCase):
    """Idea cards carry ids like style.low_fantasy_mud.

    They are no longer sent to the model (see idea_bank.prompt_sparks); this is
    the backstop for anything that still reaches a field the player reads.
    Measured live: world_style=low_fantasy_mud and tone=pastoral_curious were
    written straight into the setup form.
    """

    def test_a_bare_slug_is_flagged(self):
        for field in ("world_style", "tone", "custom_style", "economy"):
            with self.subTest(field=field):
                self.assertIn(
                    "raw_idea_card_id", field_contamination_reasons(field, "low_fantasy_mud")
                )

    def test_a_dotted_card_id_is_flagged(self):
        self.assertIn(
            "raw_idea_card_id", field_contamination_reasons("world_style", "style.low_fantasy_mud")
        )

    def test_real_values_are_not_flagged(self):
        for field, value in (
            ("world_style", "Low fantasy mud and knives"),
            ("tone", "gritty"),
            ("economy", "coin-driven"),
            ("tech_level", "early industrial"),
            ("custom_style", "Glow means leave"),
        ):
            with self.subTest(field=field, value=value):
                self.assertNotIn("raw_idea_card_id", field_contamination_reasons(field, value))

    def test_the_slug_detector_itself(self):
        for value in ("low_fantasy_mud", "style.low_fantasy_mud", "a_b", "tone.rusted_iron"):
            self.assertTrue(looks_like_card_slug(value), value)
        for value in ("coin-driven", "early industrial", "Mosswake Gate", "gritty", "", "a b_c"):
            self.assertFalse(looks_like_card_slug(value), value)


class TestStartLocationMustBeAPlace(unittest.TestCase):
    """A cold randomize returned an idea card's examples line as the start place.

    "a broken cart axle starts the plot" was stored as start_location on 10
    rolls out of 10 -- it is the examples line of the one card that used to be
    pinned to the top of every spark list. The map layer already refused that
    shape; the setup form accepted it, so the repair pass never ran.
    """

    def test_the_recorded_example_paste_is_refused(self):
        self.assertIn(
            "start_location_not_a_place_name",
            field_contamination_reasons("start_location", "a broken cart axle starts the plot"),
        )

    def test_an_entity_code_is_refused(self):
        for code in ("[[L1]]", "L1"):
            with self.subTest(code=code):
                self.assertIn(
                    "start_location_not_a_place_name",
                    field_contamination_reasons("start_location", code),
                )

    def test_real_start_locations_pass(self):
        for name in (
            "Mosswake Gate",
            "Docking Bay Seven",
            "The Salt Crow",
            "Calico Junction Depot",
            "Redmill Ford",
        ):
            with self.subTest(name=name):
                self.assertEqual(field_contamination_reasons("start_location", name), [])


class TestCustomStyleMustAddSomething(unittest.TestCase):
    """Twice in twelve rolls one card title filled world_style AND custom_style.

    custom_style is the prose field for world constraints and DM stance, so a
    verbatim restatement of the genre phrase leaves the setup with nothing where
    its stance should be.
    """

    def _run(self, result: dict) -> dict:
        return llm._drop_echoed_custom_style(
            ["world_style", "custom_style"], {}, empty_intent(""), result
        )

    def test_a_verbatim_echo_is_replaced(self):
        out = self._run(
            {"world_style": "Grimdark mud calculus", "custom_style": "Grimdark mud calculus"}
        )
        self.assertNotEqual(out["custom_style"].lower(), "grimdark mud calculus")
        self.assertIn("Grimdark mud calculus", out["custom_style"])
        self.assertIn("DM stance", out["custom_style"])

    def test_case_and_spacing_do_not_hide_the_echo(self):
        out = self._run(
            {"world_style": "Raincoat city noir", "custom_style": "  raincoat CITY noir "}
        )
        self.assertNotEqual(out["custom_style"].strip().lower(), "raincoat city noir")

    def test_a_real_custom_style_is_untouched(self):
        result = {"world_style": "Raincoat city noir", "custom_style": "Glow means leave"}
        self.assertEqual(self._run(result), result)

    def test_the_world_style_itself_is_untouched(self):
        out = self._run(
            {"world_style": "Grimdark mud calculus", "custom_style": "Grimdark mud calculus"}
        )
        self.assertEqual(out["world_style"], "Grimdark mud calculus")

    def test_a_roll_without_custom_style_is_untouched(self):
        result = {"world_style": "Raincoat city noir"}
        self.assertEqual(self._run(result), result)


if __name__ == "__main__":
    unittest.main()
