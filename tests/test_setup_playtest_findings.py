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
        # The first call is the prompt under test; the abilities path makes
        # later calls (de-duplication) after the refusal.
        captured.setdefault("user", user)
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

    def test_a_comb_is_not_jewellery(self):
        items = gear.normalize_gear_list([{"name": "wooden comb", "slot": "FINGER"}], context={}, trust=False)
        comb = next(item for item in items if item["name"] == "wooden comb")
        self.assertEqual(comb["slot"], "")

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


class TestTheProgressionStartHasAPower(unittest.TestCase):
    def test_an_all_locked_kit_opens_its_first_power(self):
        kit = [{"name": "Seed", "locked": True, "prerequisites": "a rival forces it"}, {"name": "Later", "locked": True}]
        out = llm.ensure_an_opening_power(kit, progression=True)
        self.assertFalse(out[0]["locked"])
        self.assertEqual(out[0]["prerequisites"], "")
        self.assertTrue(out[1]["locked"])

    def test_other_starts_keep_their_locks(self):
        kit = [{"name": "Seed", "locked": True, "prerequisites": "x"}]
        self.assertTrue(llm.ensure_an_opening_power(kit, progression=False)[0]["locked"])

    def test_the_offline_fallback_opens_one_too(self):
        for _ in range(15):
            out = llm.fallback_setup_randomization("field:special_abilities", {"_randomize_idea": OVERPOWERED}, "down")
            abilities = out["fields"].get("special_abilities") or []
            self.assertTrue(abilities)
            self.assertTrue(any(not a.get("locked") for a in abilities))

    def test_no_arrival_seed_is_the_database_default(self):
        from app.setup_composer import LOCATION_SEEDS_BY_THEME

        for bank in LOCATION_SEEDS_BY_THEME.values():
            self.assertNotIn("Mosswake Gate", bank)


class TestSparksOnlyForProse(unittest.TestCase):
    def test_short_fields_get_no_sparks(self):
        for field in ("tone", "faction_pressure", "quest_style", "economy"):
            prompt = _capture_prompt(f"field:{field}", {"world_style": "cyberpunk megacity", "_randomize_idea": "cyberpunk debt noir"})
            self.assertFalse(prompt.get("idea_sparks"), field)

    def test_prose_fields_may_still_get_them(self):
        llm.idea_sparks_for_prompt  # the hook exists
        prompt = _capture_prompt("field:character_backstory", {"world_style": "cyberpunk megacity", "_randomize_idea": "cyberpunk debt noir"})
        self.assertIn("field_note", prompt)


class TestTheModelIntentStaysWithTheIdea(unittest.TestCase):
    ADVENTURERS = (
        "Guild-hall adventuring fantasy: a job board, a party of roles, dungeons and wilderness, loot and levels "
        "that matter. Normal difficulty; mythic progression tone; leveling and ranks on."
    )

    def _merge(self, idea, llm_pf):
        from app.setup_composer import empty_intent, merge_intent_plans

        base = empty_intent(idea)
        base["raw_idea"] = idea
        return merge_intent_plans(base, {"power_fantasy": llm_pf})

    def test_a_mythic_tone_is_not_a_weak_seed_climb(self):
        plan = self._merge(self.ADVENTURERS, {"growth": "compounding", "start_power": "near_useless"})
        self.assertNotEqual(plan["power_fantasy"]["growth"], "compounding")
        self.assertNotEqual(plan["power_fantasy"]["start_power"], "near_useless")
        self.assertNotIn("custom_skills", intent_to_field_overrides(plan, set()))

    def test_the_overpowered_idea_still_climbs(self):
        plan = self._merge(OVERPOWERED, {"growth": "compounding"})
        self.assertEqual(plan["power_fantasy"]["growth"], "compounding")

    def test_levels_in_the_idea_switch_levelling(self):
        plan = self._merge(self.ADVENTURERS, {})
        self.assertIs(intent_to_field_overrides(plan, set()).get("leveling_system"), True)
        plan = self._merge("Gritty survival with no levels and no XP.", {})
        self.assertIs(intent_to_field_overrides(plan, set()).get("leveling_system"), False)

    def test_gods_in_a_fantasy_idea_are_not_a_climb(self):
        plan = self._merge("Old gods walk the roads; temples and kingdoms.", {"growth": "compounding"})
        self.assertNotEqual(plan["power_fantasy"]["growth"], "compounding")


class TestBackstoryAndSeedProse(unittest.TestCase):
    def test_a_clause_hint_is_not_prefixed_with_you_can(self):
        text = player_facing_domain_description({"name": "Candle Whisper", "hint": "flame leans toward the larger lie in the room"})
        self.assertTrue(text.startswith("Flame leans"), text)

    def test_every_seed_reads_as_a_sentence_with_a_hook(self):
        from app.llm import _ABILITY_ACTION_HINT

        for domain in SEED_SKILL_DOMAIN_POOL:
            text = player_facing_domain_description(domain)
            self.assertRegex(text, _ABILITY_ACTION_HINT, domain.get("name"))

    def test_a_verb_hint_still_reads_you_can(self):
        text = player_facing_domain_description({"name": "Weapon Name", "hint": "whisper a name to your weapon"})
        self.assertTrue(text.startswith("You can whisper"), text)

    def test_a_native_backstory_is_not_rebuilt_as_a_transmigration(self):
        story = "They grew up hauling ore in the lower tunnels; the Seoul warehouse rumors never reached them."
        out = llm._sanitize_setup_randomization_values({"character_backstory": story})
        self.assertNotIn("Before the transfer", out["character_backstory"])


class TestSeedPowersAreNotAllDuplicates(unittest.TestCase):
    def test_seed_descriptions_do_not_read_as_near_duplicates(self):
        import itertools

        rng = random.Random(3)
        pool = rng.sample(list(SEED_SKILL_DOMAIN_POOL), 30)
        cards = [
            {"name": d["name"], "description": player_facing_domain_description(d), "cost": "Numb fingers", "growth_math": "XP_to_next = 36 * rank^1.58", "power_type": "linear"}
            for d in pool
        ]
        pairs = list(itertools.combinations(cards, 2))
        close = sum(llm.ability_similarity_score(a, b) >= llm.ABILITY_NEAR_DUP_THRESHOLD for a, b in pairs)
        # Shared boilerplate once made every pair a near-duplicate (435 of 435).
        self.assertLess(close, len(pairs) // 20)

    def test_a_remade_card_keeps_its_own_name(self):
        from app.setup_composer import SEED_SKILL_DOMAIN_POOL as POOL

        by_name = {d["name"]: player_facing_domain_description(d) for d in POOL}
        kit = [
            {"name": "Ward Cradle", "description": "You can hum a cradle ward over a sleeper.", "cost": "x", "growth_math": "m"},
            {"name": "Door Knock", "description": "You can hum a cradle ward over a sleeper.", "cost": "x", "growth_math": "m"},
        ]
        out = llm.ensure_distinct_abilities(kit, existing=[], origin="both", one_skillish=False, world_style="", use_llm=False)
        for card in out.get("abilities") or []:
            if card["name"] in by_name and card["name"] not in ("Ward Cradle", "Door Knock"):
                self.assertTrue(card["description"].startswith(by_name[card["name"]][:20]), card)
            self.assertNotIn("different practical niche", card.get("description", ""))


class TestTheEngineNamesTheSeed(unittest.TestCase):
    CARDS = [{"name": "Sigil Smudge", "locked": True}, {"name": "Rattle Command", "locked": False}]

    def test_a_foreign_seed_name_is_replaced_by_a_usable_card(self):
        text = "weak seed skill: Ember Resolve, rank F / level 1, grows with risk"
        out = llm.align_seed_skill_with_abilities(text, self.CARDS)
        self.assertTrue(out.startswith("weak seed skill: Rattle Command,"), out)

    def test_a_matching_name_and_no_cards_are_left_alone(self):
        text = "weak seed skill: Sigil Smudge, rank F"
        self.assertEqual(llm.align_seed_skill_with_abilities(text, self.CARDS), text)
        self.assertEqual(llm.align_seed_skill_with_abilities("weak seed skill: X, rank F", []), "weak seed skill: X, rank F")

    def test_the_simple_walk_rolls_gear_parents(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        import re as _re

        walk = _re.search(r"const SIMPLE_RANDOM_FIELD_ORDER = \[(.*?)\];", js, _re.S).group(1)
        for name in ("tech_level", "world_races", "start_location"):
            self.assertIn(f'"{name}"', walk)

if __name__ == "__main__":
    unittest.main()
