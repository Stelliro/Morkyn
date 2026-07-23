"""Opening feel helpers: weak skill seed, stakes, opening prompt block."""

from __future__ import annotations

from app.setup_composer import (
    apply_keyword_intent,
    intent_to_field_overrides,
    opening_feel_prompt_block,
    theme_prompt_block,
    weak_skill_seed_spec,
)


def test_isekai_compounding_keyword_implies_weak_start():
    plan = apply_keyword_intent(
        "Isekai dark fantasy with a compounding near-useless skill and system UI"
    )
    assert plan["isekai"] is True
    assert plan["power_fantasy"]["growth"] == "compounding"
    assert plan["power_fantasy"]["start_power"] == "near_useless"
    assert plan["power_fantasy"]["system_ui"] is True


def test_intent_overrides_seed_custom_skills_and_dice():
    intent = apply_keyword_intent(
        "Isekai RPG: ordinary human, one weak skill that compounds, subtle system UI"
    )
    fields = intent_to_field_overrides(intent)
    assert fields.get("game_system") is True
    assert fields.get("dice_checks_enabled") is True
    assert "Observation" in str(fields.get("custom_skills") or "")
    assert fields.get("check_difficulty") in ("easy", "normal", "hard", "brutal")


def test_weak_skill_seed_spec_named():
    seed = weak_skill_seed_spec(
        {
            "custom_skills": "weak seed skill: Foraging (near-useless F rank).",
            "session_theme": {
                "power_fantasy": {"start_power": "near_useless", "growth": "compounding", "system_ui": True}
            },
        }
    )
    assert seed is not None
    assert seed["name"] == "Foraging"
    assert seed["value"] == 1


def test_weak_skill_seed_default_observation():
    seed = weak_skill_seed_spec(
        {},
        {"power_fantasy": {"start_power": "near_useless", "growth": "compounding"}},
    )
    assert seed is not None
    assert seed["name"] == "Observation"


def test_opening_feel_mentions_system_and_seed():
    opts = {
        "game_system": True,
        "system_style": "subtle blue-window system",
        "difficulty": "hard",
        "custom_skills": "weak seed skill: Observation",
    }
    theme = {
        "isekai": True,
        "adapter_hint": "isekai_rpg",
        "edge": "lasting injuries",
        "power_fantasy": {"start_power": "near_useless", "growth": "compounding", "system_ui": True},
    }
    block = opening_feel_prompt_block(theme, opts)
    assert "system window" in block.lower() or "diegetic" in block.lower()
    assert "Observation" in block
    assert "hard" in block.lower() or "danger" in block.lower() or "mark" in block.lower()


def test_theme_block_includes_stakes():
    theme = {
        "genre": "isekai fantasy",
        "isekai": True,
        "dm_stance": "fair pressure",
        "power_fantasy": {"start_power": "near_useless", "growth": "compounding", "system_ui": True},
        "edge": "scarce loot",
    }
    block = theme_prompt_block(theme, {"difficulty": "brutal", "game_system": True})
    assert "Stakes:" in block
    assert "System UI" in block or "system" in block.lower()
