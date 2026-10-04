"""
Starting gear on the model side.

The form carries starter_gear (structured cards; see app/gear.py). The
randomizer must ask the model for that list with the parents it must read, keep
the player's locked cards verbatim, fall back to the engine's kit when the model
cannot answer, and derive the legacy comma string from the cards.

Nothing here talks to a model: llm._chat_json is replaced per test.
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

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-gear-prompts-test-"))
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
from app.gear import REQUIRED_GEAR_SLOTS  # noqa: E402
from app.setup_composer import (  # noqa: E402
    COMPOSER_FIELD_ORDER,
    STARTER_KIT_SEED_POOL,
    field_contract,
    field_dependencies,
)

SETUP = {
    "world_style": "frontier dark fantasy",
    "tech_level": "medieval",
    "player_sex": "male",
    "world_races": "human, elf, beastfolk",
    "backstory_mode": "known",
    "appearance": "torso: oilskin coat; feet: mud boots",
    "start_location": "Saltmarsh Gate",
    "_locked_fields": ["player_sex"],
    "_locked_values": {"player_sex": "male"},
}


def _capture_prompt(group: str, current: dict) -> dict:
    captured: dict = {}

    def fake_chat(system, user, **kwargs):
        captured["user"] = user
        raise RuntimeError("stop after prompt build")

    original = llm._chat_json
    llm._chat_json = fake_chat
    try:
        llm.generate_setup_randomization(group, current)
    except Exception:
        pass
    finally:
        llm._chat_json = original
    return json.loads(captured["user"])


def _with_reply(reply, group: str, current: dict) -> dict:
    def fake_chat(system, user, **kwargs):
        if isinstance(reply, Exception):
            raise reply
        return reply

    original = llm._chat_json
    llm._chat_json = fake_chat
    try:
        return llm.generate_setup_randomization(group, current)
    finally:
        llm._chat_json = original


def _required_slots(items: list) -> set:
    return {item["slot"] for item in items if item.get("required")}


class TestTheGearPromptCarriesItsParents(unittest.TestCase):
    def test_the_gear_button_ships_sex_race_and_the_required_slots(self):
        prompt = _capture_prompt("field:starter_gear", dict(SETUP))
        agree = prompt["depends_on"]["agree_with"]
        self.assertEqual(agree["player_sex"], "male")
        self.assertEqual(agree["world_races"], "human, elf, beastfolk")
        self.assertIn("player_sex", prompt["depends_on"]["locked_parents"])
        self.assertEqual(prompt["required_slots"], list(REQUIRED_GEAR_SLOTS))
        self.assertIn("LEGS", prompt["slot_codes"])
        self.assertIn("starter_gear", prompt["return_shape"])
        self.assertEqual(prompt["setup_context"]["appearance"], SETUP["appearance"])

    def test_no_example_item_names_ride_along(self):
        prompt = _capture_prompt("field:starter_gear", dict(SETUP))
        text = json.dumps(prompt).lower()
        for kit in STARTER_KIT_SEED_POOL:
            self.assertNotIn(kit.lower(), text, kit)
        for pasted in ("copper coins", "rusted wrench", "worn satchel", "patched work vest"):
            self.assertNotIn(pasted, text, pasted)
        self.assertNotIn("examples", prompt["field_contract"])

    def test_a_locked_card_is_named_immutable(self):
        current = {**SETUP, "starter_gear": [{"name": "Boots of the Hare", "slot": "FEET", "required": True, "keep": True}]}
        prompt = _capture_prompt("field:starter_gear", current)
        self.assertEqual(prompt["locked_gear"][0]["name"], "Boots of the Hare")
        self.assertTrue(prompt["locked_gear"][0]["locked"])
        self.assertTrue(any("locked_gear" in rule for rule in prompt["rules"]))

    def test_a_group_roll_ships_the_shape(self):
        prompt = _capture_prompt("character", dict(SETUP))
        self.assertIn("starter_gear", prompt["return_fields"])
        self.assertNotIn("starter_equipment", prompt["return_fields"])
        contract = prompt["field_contracts"]["starter_gear"]
        self.assertEqual(contract["required_slots"], list(REQUIRED_GEAR_SLOTS))
        self.assertIn("slot", contract["return_shape"][0])
        self.assertEqual(contract["agree_with"]["player_sex"], "male")


class TestTheWalkOrder(unittest.TestCase):
    def test_gear_rolls_after_its_parents_and_the_string_is_not_walked(self):
        self.assertNotIn("starter_equipment", COMPOSER_FIELD_ORDER)
        gear_at = COMPOSER_FIELD_ORDER.index("starter_gear")
        for parent in ("player_sex", "appearance", "start_location", "world_races", "tech_level"):
            self.assertLess(COMPOSER_FIELD_ORDER.index(parent), gear_at, parent)
        self.assertEqual(field_dependencies("starter_gear")[:2], ["world_style", "tech_level"])
        self.assertEqual(field_contract("starter_equipment").get("derived_from"), "starter_gear")


class TestValidationCoercesAndMerges(unittest.TestCase):
    def test_a_single_object_becomes_a_kit_with_the_three_basics(self):
        out = llm._validate_setup_randomization(
            "field:starter_gear",
            {"starter_gear": {"name": "oilskin coat", "slot": "torso"}},
            dict(SETUP),
        )
        items = out["starter_gear"]
        self.assertEqual(_required_slots(items), set(REQUIRED_GEAR_SLOTS))
        self.assertIn("oilskin coat", [i["name"] for i in items])
        self.assertEqual(out["starter_equipment"], ", ".join(i["name"] for i in items))

    def test_a_string_reply_becomes_a_kit_too(self):
        out = llm._validate_setup_randomization(
            "field:starter_gear",
            {"starter_gear": "oilskin coat, tin cup, mud boots"},
            dict(SETUP),
        )
        names = [i["name"] for i in out["starter_gear"]]
        self.assertIn("tin cup", names)
        self.assertEqual(_required_slots(out["starter_gear"]), set(REQUIRED_GEAR_SLOTS))
        for item in out["starter_gear"]:
            self.assertIn("weight", item["item_stats"])

    def test_a_locked_card_survives_a_roll_verbatim(self):
        current = {
            **SETUP,
            "starter_gear": [
                {"name": "Boots of the Hare", "slot": "FEET", "required": True, "keep": True, "description": "Quick and quiet.", "stats": {"dexterity": 1}},
            ],
        }
        out = llm._validate_setup_randomization(
            "field:starter_gear",
            {"starter_gear": [{"name": "mud boots", "slot": "FEET"}, {"name": "wool tunic", "slot": "TORSO"}]},
            current,
        )
        feet = [i for i in out["starter_gear"] if i["slot"] == "FEET"]
        self.assertEqual(len(feet), 1)
        self.assertEqual(feet[0]["name"], "Boots of the Hare")
        self.assertTrue(feet[0]["keep"])
        self.assertEqual(feet[0]["description"], "Quick and quiet.")
        self.assertEqual(feet[0]["stats"], {"dexterity": 1})
        self.assertNotIn("mud boots", [i["name"] for i in out["starter_gear"]])


class TestTheFallbackAndTheDerivedString(unittest.TestCase):
    def test_a_dead_model_hands_back_the_engines_kit_and_says_so(self):
        payload = _with_reply(RuntimeError("model unavailable"), "field:starter_gear", dict(SETUP))
        self.assertTrue(payload["fallback_used"])
        self.assertIn("model unavailable", payload["fallback_reason"])
        self.assertEqual(_required_slots(payload["starter_gear"]), set(REQUIRED_GEAR_SLOTS))
        self.assertEqual(payload["starter_equipment"], ", ".join(i["name"] for i in payload["starter_gear"]))

    def test_the_offline_fallback_path_also_returns_cards(self):
        payload = llm.fallback_setup_randomization("field:starter_gear", dict(SETUP), "offline")
        self.assertTrue(payload["fallback_used"])
        self.assertEqual(_required_slots(payload["fields"]["starter_gear"]), set(REQUIRED_GEAR_SLOTS))

    def test_sanitize_sets_the_string_to_the_names(self):
        out = llm._sanitize_setup_randomization_values(
            {"starter_gear": [{"name": "oilskin coat", "slot": "TORSO"}, {"name": "tin cup", "slot": ""}], "starter_equipment": "rusted wrench, copper coins"}
        )
        self.assertEqual(out["starter_equipment"], "oilskin coat, tin cup")


if __name__ == "__main__":
    unittest.main()
