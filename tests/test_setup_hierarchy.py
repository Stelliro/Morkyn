"""Setup fields have parents, and the randomizer honours them.

A randomize through the Overpowered preset with the player's sex locked to
male came back with a feminine name, and the World vibe box read "Exactly one
weak seed power compounds through risk and training; no free combat kit."

Three causes, all structural:
  * dependencies existed only between phases; inside the identity phase the
    declaration order rolled player_name before player_sex, so the name could
    not know the sex, and the group list for "character" did the same;
  * nothing in the name's contract said it had to read as the sex, and the
    identity rules shipped example names, which a 7B pastes;
  * custom_style's intent keys included power_fantasy and the field banned
    growth timers but not growth slogans, so the preset's power frame was
    handed to the World vibe roll and nothing refused the result.

Run:  python -m unittest tests.test_setup_hierarchy
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-hierarchy-test-"))
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
    COMPOSER_FIELD_ORDER,
    FIELD_CONTRACTS,
    _clean_custom_style_fallback,
    composer_tree_public,
    dependency_sorted,
    empty_intent,
    field_contamination_reasons,
    field_contract,
    field_dependencies,
    has_growth_slogan,
)

LEAKED_VIBE = "Exactly one weak seed power compounds through risk and training; no free combat kit."


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


class TestParentsRollFirst(unittest.TestCase):
    def test_every_declared_parent_precedes_its_child(self):
        index = {name: i for i, name in enumerate(COMPOSER_FIELD_ORDER)}
        for field in COMPOSER_FIELD_ORDER:
            for parent in field_dependencies(field):
                self.assertLess(index[parent], index[field], f"{parent} must roll before {field}")

    def test_the_sex_comes_before_everything_that_reads_it(self):
        index = {name: i for i, name in enumerate(COMPOSER_FIELD_ORDER)}
        for child in ("player_name", "hair", "facial_features", "appearance", "character_backstory"):
            self.assertLess(index["player_sex"], index[child], child)
        self.assertLess(index["backstory_mode"], index["character_backstory"])
        self.assertLess(index["backstory_mode"], index["previous_life_sex"])

    def test_the_character_group_rolls_the_sex_before_the_name(self):
        fields = llm._setup_randomizer_return_fields("character", {})
        self.assertLess(fields.index("player_sex"), fields.index("player_name"))
        self.assertLess(fields.index("backstory_mode"), fields.index("character_backstory"))

    def test_dependency_sorted_keeps_unrelated_order_and_survives_a_cycle(self):
        self.assertEqual(dependency_sorted(["player_name", "player_sex", "tone"]), ["player_sex", "player_name", "tone"])
        self.assertEqual(dependency_sorted(["tone", "economy"]), ["tone", "economy"])
        # Only names in the list are pulled forward; a parent outside it is not invented.
        self.assertEqual(dependency_sorted(["player_name"]), ["player_name"])

    def test_the_tree_endpoint_names_the_dependencies(self):
        tree = composer_tree_public()
        self.assertIn("player_sex", tree["dependencies"]["player_name"])
        self.assertEqual(tree["field_order"], list(COMPOSER_FIELD_ORDER))

    def test_every_dependency_points_at_a_real_field(self):
        for field, contract in FIELD_CONTRACTS.items():
            for parent in contract.get("depends_on") or []:
                self.assertIn(parent, FIELD_CONTRACTS, f"{field} depends on unknown {parent}")
                self.assertNotEqual(parent, field)


class TestTheModelSeesTheParents(unittest.TestCase):
    LOCKED_MALE = {
        "player_sex": "male",
        "world_style": "frontier dark fantasy",
        "_locked_fields": ["player_sex"],
        "_locked_values": {"player_sex": "male"},
    }

    def test_a_group_roll_tells_the_name_which_sex_it_must_read_as(self):
        prompt = _capture_prompt("character", dict(self.LOCKED_MALE))
        name = prompt["field_contracts"]["player_name"]
        self.assertEqual(name["agree_with"]["player_sex"], "male")
        self.assertIn("player_sex", name["locked_parents"])
        self.assertEqual(name["agree_with"]["world_style"], "frontier dark fantasy")
        self.assertIn("player_sex", name["forbidden"])
        self.assertNotIn("player_sex", prompt["return_fields"], "a locked parent is not rolled")
        self.assertTrue(any("agree_with" in rule for rule in prompt["rules"]))

    def test_an_unset_parent_is_named_so_it_is_decided_first(self):
        prompt = _capture_prompt("character", {"world_style": "noir city"})
        name = prompt["field_contracts"]["player_name"]
        self.assertIn("player_sex", name["decide_first"])
        self.assertLess(prompt["return_fields"].index("player_sex"), prompt["return_fields"].index("player_name"))

    def test_the_name_button_carries_the_same_block_and_no_example_names(self):
        # The direct name button has its own prompt (name_rules), not the generic field path.
        prompt = _capture_prompt("field:player_name", dict(self.LOCKED_MALE))
        self.assertEqual(prompt["depends_on"]["agree_with"]["player_sex"], "male")
        self.assertIn("player_sex", prompt["depends_on"]["locked_parents"])
        self.assertTrue(any("player_sex" in rule for rule in prompt["name_rules"]))
        text = json.dumps(prompt)
        for pasted in ("Elena", "Mara Ellison", "Corvin Hale", "Ashwalker", "Northlight"):
            self.assertNotIn(pasted, text, pasted)

    def test_a_generic_single_field_roll_carries_the_block(self):
        prompt = _capture_prompt("field:hair", dict(self.LOCKED_MALE))
        self.assertEqual(prompt["depends_on"]["agree_with"]["player_sex"], "male")
        self.assertIn("player_sex", prompt["depends_on"]["locked_parents"])
        self.assertNotIn("examples", prompt["field_contract"])
        self.assertTrue(any("agree_with" in rule for rule in prompt["rules"]))

    def test_the_identity_rules_carry_no_example_names(self):
        prompt = _capture_prompt("character", {})
        text = json.dumps(prompt)
        for pasted in ("Mara Ellison", "Tomas Reed", "Ashwalker"):
            self.assertNotIn(pasted, text)
        rules = " ".join(prompt["character_identity_rules"])
        self.assertIn("must read as the character's player_sex", rules)


class TestTheWorldVibeIsNotAPowerRule(unittest.TestCase):
    def test_the_leaked_sentence_is_refused(self):
        reasons = field_contamination_reasons("custom_style", LEAKED_VIBE)
        self.assertIn("growth_slogan_in_wrong_field", reasons)

    def test_a_real_vibe_is_still_accepted(self):
        for vibe in ("Rain-slick salt marsh towns where oaths are currency.", "Glow means leave", "Grimdark mud calculus"):
            self.assertEqual(field_contamination_reasons("custom_style", vibe), [], vibe)

    def test_the_vibe_contract_no_longer_reads_the_power_frame(self):
        contract = field_contract("custom_style")
        self.assertNotIn("power_fantasy", contract["intent_keys"])
        self.assertTrue(contract.get("ban_growth_slogans"))
        self.assertNotIn("examples", contract)
        for field in ("hair", "facial_features", "appearance"):
            self.assertNotIn("power_fantasy", field_contract(field)["intent_keys"], field)

    def test_the_clean_fallback_is_itself_clean(self):
        intent = empty_intent("")
        intent["power_fantasy"] = {**intent["power_fantasy"], "growth": "compounding", "start_power": "near_useless"}
        intent["genre"] = "frontier dark fantasy"
        text = _clean_custom_style_fallback(intent, {})
        self.assertFalse(has_growth_slogan(text), text)
        self.assertEqual(field_contamination_reasons("custom_style", text), [], text)
        self.assertIn("frontier dark fantasy", text)


class TestTheVibeIsWorldScoped(unittest.TestCase):
    """The vibe prompt asks the model to describe the world. The fix is the ask, not a gate."""

    WORLD_SENTENCES = (
        "Power here is earned: talent starts small and grows with risk and training; nobody is born strong.",
        "Rain-slick salt marsh towns where oaths are currency and the guilds hold the gates.",
        "Magic is a trade like any other; the gifted are rare and watched.",
        "Setting frame: frontier dark fantasy. DM stance: fair pressure, player agency.",
    )

    def test_there_is_no_player_scope_gate(self):
        import app.setup_composer as composer

        self.assertFalse(hasattr(composer, "is_player_scoped"))
        reasons = field_contamination_reasons("custom_style", "A single hidden gift the player nurtures through hardship.")
        self.assertNotIn("player_scoped_in_world_field", reasons)

    def test_world_sentences_pass(self):
        for sentence in self.WORLD_SENTENCES:
            self.assertEqual(field_contamination_reasons("custom_style", sentence), [], sentence)

    def test_the_progression_fallback_states_the_world_fact(self):
        intent = empty_intent("")
        intent["power_fantasy"] = {**intent["power_fantasy"], "growth": "compounding", "start_power": "near_useless"}
        intent["genre"] = "frontier dark fantasy"
        text = _clean_custom_style_fallback(intent, {})
        self.assertIn("nobody is born strong", text)
        self.assertEqual(field_contamination_reasons("custom_style", text), [], text)

    def test_the_prompts_ask_for_a_description_of_the_world(self):
        single = _capture_prompt("field:custom_style", {"world_style": "frontier dark fantasy"})
        for text in (single["field_note"], single["field_contract"]["forbidden"]):
            self.assertIn("Describe the world", text)
            self.assertIn("how power is earned", text)
            self.assertIn("who lives there", text)
        self.assertIn("agree_with", single["field_note"])
        group = _capture_prompt("world", {})
        self.assertTrue(any("custom_style describes the world" in rule for rule in group["rules"]))

    def test_world_style_is_a_phrase_about_the_world(self):
        self.assertIn("about the world", field_contract("world_style")["forbidden"])
        self.assertEqual(field_contamination_reasons("world_style", "Dying empire of salt and iron"), [])


class TestThePresetAndTheClientOrder(unittest.TestCase):
    JS = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    def test_the_preset_is_called_overpowered_and_is_not_tied_to_isekai(self):
        self.assertIn('label: "Overpowered"', self.JS)
        self.assertNotIn('label: "OP MC"', self.JS)
        block = self.JS[self.JS.index('id: "op_mc"'): self.JS.index('id: "fantasy"')]
        self.assertNotIn("isekai-friendly", block)
        self.assertIn("any setting", block)
        # The composer still recognises the fantasy from the idea text.
        self.assertIn("snowball", block)
        self.assertNotIn("no free second combat kit", block)

    def test_the_client_walks_in_the_composer_order(self):
        self.assertIn("function orderByComposer(", self.JS)
        self.assertIn("orderByComposer(fieldOrder)", self.JS)
        self.assertIn("orderByComposer(RANDOM_GROUPS[group]", self.JS)

    def test_the_fallback_lists_put_the_sex_before_the_name(self):
        simple = re.search(r"const SIMPLE_RANDOM_FIELD_ORDER = \[(.*?)\];", self.JS, re.S).group(1)
        names = re.findall(r'"([a-z_]+)"', simple)
        self.assertLess(names.index("player_sex"), names.index("player_name"))
        self.assertLess(names.index("player_sex"), names.index("hair"))
        self.assertLess(names.index("backstory_mode"), names.index("character_backstory"))


if __name__ == "__main__":
    unittest.main()
