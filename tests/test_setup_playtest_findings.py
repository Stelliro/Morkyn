"""
Regressions from a headless Qwen3 8B playtest of New game presets
(tools/playtest_setup_presets.py). Each test pins one infraction that
run found.
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="morkyn-playtest-findings-"))
os.environ.update(
    {
        "AI_RPG_DB": str(_TMP / "world.db"),
        "AI_RPG_PACK_DIR": str(_TMP / "packs"),
        "AI_RPG_SOURCE_INDEX": str(_TMP / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(_TMP / "history.jsonl"),
        "AI_RPG_MODEL_TRACE_DIR": str(_TMP / "traces"),
        "AI_RPG_SKILL_LIBRARY": str(_TMP / "skill_library.json"),
    }
)

from app import gear, llm  # noqa: E402
from app.setup_composer import (  # noqa: E402
    SEED_SKILL_DOMAIN_POOL,
    apply_keyword_intent,
    intent_to_field_overrides,
    player_facing_domain_description,
)

OVERPOWERED = (
    "Overpowered progression in any setting: start ordinary with one weak compounding seed power that "
    "snowballs toward late-game OP (rank F up through S/SS/SSS). Growth Math makes the climb calculable; "
    "passives allowed; more powers can unlock later. Normal difficulty; mythic progression tone; local "
    "stakes early; fair DM."
)


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


class TestTheIdeaSetsProgression(unittest.TestCase):
    def setUp(self):
        self.fields = intent_to_field_overrides(apply_keyword_intent(OVERPOWERED), set())

    def test_a_progression_idea_turns_levelling_on(self):
        self.assertIs(self.fields.get("leveling_system"), True)

    def test_the_vibe_override_is_a_world_fact_not_a_power_rule(self):
        vibe = self.fields.get("custom_style") or ""
        self.assertNotIn("Power fantasy", vibe)
        self.assertNotIn("start weak", vibe)
        self.assertIn("Power here is earned", vibe)


class TestSeedAbilityText(unittest.TestCase):
    def test_no_design_notes_in_the_base_description(self):
        for domain in SEED_SKILL_DOMAIN_POOL:
            text = player_facing_domain_description(domain)
            self.assertNotIn("At F rank", text, domain.get("name"))
            self.assertNotIn("grow toward", text, domain.get("name"))
            self.assertNotIn("never as a free start", text, domain.get("name"))
            self.assertNotIn("answers cleanly", text, domain.get("name"))

    def test_the_inspiration_list_carries_no_names(self):
        prompt = _capture_prompt("field:special_abilities", {"world_style": "frontier dark fantasy"})
        spice = prompt.get("inspiration_only") or []
        self.assertTrue(spice)
        for entry in spice:
            self.assertNotIn("name", entry)


class TestTheOfflineFallback(unittest.TestCase):
    def test_the_name_reads_as_the_sex(self):
        for sex, wrong in (("male", "female"), ("female", "male")):
            for _ in range(40):
                name = llm._fallback_setup_value("player_name", {"player_sex": sex})
                self.assertNotIn(name, llm.FALLBACK_NAME_SEX[wrong], (sex, name))

    def test_the_fallback_walk_reads_the_idea(self):
        current = {"_randomize_idea": OVERPOWERED, "_locked_fields": []}
        for _ in range(10):
            out = llm.fallback_setup_randomization("field:leveling_system", current, "model down")
            self.assertIs(out["fields"].get("leveling_system"), True)

    def test_the_fallback_vibe_is_never_blank(self):
        out = llm.fallback_setup_randomization("field:custom_style", {"_randomize_idea": OVERPOWERED}, "model down")
        self.assertTrue(str(out["fields"].get("custom_style") or "").strip())

    def test_no_racial_casting_without_world_magic(self):
        current = {"magic_level": "forbidden"}
        for _ in range(20):
            out = llm.fallback_setup_randomization("field:race_magic_enabled", current, "model down")
            self.assertIs(out["fields"].get("race_magic_enabled"), False)


class TestFallbackAnswersOnlyWhatWasAsked(unittest.TestCase):
    def test_a_single_field_fallback_returns_that_field_alone(self):
        current = {"_randomize_idea": OVERPOWERED, "world_style": "frontier dark fantasy", "_locked_fields": []}
        for field in ("custom_skills", "tone", "magic_level", "player_name", "hair", "dice_checks_enabled"):
            out = llm.fallback_setup_randomization(f"field:{field}", current, "model down")
            self.assertEqual(set(out["fields"]) - {field}, set(), field)

    def test_progression_skills_name_the_seed(self):
        out = llm.fallback_setup_randomization(
            "field:custom_skills", {"_randomize_idea": OVERPOWERED, "special_abilities": [{"name": "Trail Mud"}]}, "down"
        )
        self.assertIn("Trail Mud", out["fields"]["custom_skills"])
        self.assertNotIn("Do not seed", out["fields"]["custom_skills"])

    def test_tech_level_fits_the_genre(self):
        for _ in range(20):
            out = llm.fallback_setup_randomization("field:tech_level", {"world_style": "frontier dark fantasy"}, "down")
            self.assertIn(out["fields"]["tech_level"], {"medieval", "iron age"})


class TestModelGearIsSane(unittest.TestCase):
    RAW = [
        {"name": "scuffed steel-toed boots", "slot": "FEET", "item_stats": {"weight": 6}},
        {"name": "reinforced satchel", "slot": "WAIST", "item_stats": {"weight": 4}},
        {"name": "pocket knife", "slot": "WRIST"},
        {"name": "iron ring", "slot": "NECK"},
    ]

    def _by_name(self, trust):
        items = gear.normalize_gear_list(self.RAW, context={}, rng=random.Random(1), trust=trust)
        return {item["name"]: item for item in items}

    def test_model_slots_follow_the_item_name(self):
        items = self._by_name(trust=False)
        self.assertEqual(items["pocket knife"]["slot"], "MAIN")
        self.assertEqual(items["reinforced satchel"]["slot"], "BACK")
        self.assertEqual(items["iron ring"]["slot"], "FINGER")

    def test_absurd_model_weights_are_re_estimated(self):
        items = self._by_name(trust=False)
        self.assertLess(items["scuffed steel-toed boots"]["item_stats"]["weight"], 2.5)
        self.assertLess(items["reinforced satchel"]["item_stats"]["weight"], 3.0)

    def test_a_players_own_card_keeps_its_choices(self):
        items = self._by_name(trust=True)
        self.assertEqual(items["iron ring"]["slot"], "NECK")
        self.assertEqual(items["scuffed steel-toed boots"]["item_stats"]["weight"], 6.0)



class TestModelTextCleanups(unittest.TestCase):
    def test_retry_wording_leaves_ability_names(self):
        self.assertEqual(llm.sanitize_ability_name("Eclipse Sigil (Reinvented)"), "Eclipse Sigil")
        self.assertEqual(llm.sanitize_ability_name("Glass Tongue (v2)"), "Glass Tongue")
        self.assertEqual(llm.sanitize_ability_name("Mirror (Debt)"), "Mirror (Debt)")

    def test_the_name_prompt_steers_by_initials_not_examples(self):
        prompt = _capture_prompt("field:player_name", {"player_sex": "male", "world_style": "frontier dark fantasy"})
        shape = prompt.get("name_shape") or {}
        self.assertEqual(len(shape.get("given_name_starts_with", "")), 1)
        self.assertEqual(len(shape.get("family_name_starts_with", "")), 1)

    def test_ability_rules_forbid_tabletop_shorthand(self):
        prompt = _capture_prompt("field:special_abilities", {"world_style": "frontier dark fantasy"})
        self.assertTrue(any("armor class" in rule for rule in prompt["rules"]))

    def test_carried_items_give_no_bonus(self):
        items = gear.normalize_gear_list(
            [{"name": "ledger", "slot": "", "stats": {"intelligence": 1}}], context={}, rng=random.Random(2)
        )
        ledger = next(item for item in items if item["name"] == "ledger")
        self.assertEqual(ledger["stats"], {})

if __name__ == "__main__":
    unittest.main()
