"""g13: post-randomize bool/enum/instruction-echo sanitation for 8B setup rolls."""

from __future__ import annotations

from app.llm import _sanitize_setup_randomization_values
from app.setup_composer import (
    coerce_setup_bool,
    coerce_typed_setup_fields,
    coerce_typed_setup_value,
    is_instruction_echo,
    normalize_magic_level,
    sanitize_setup_fields,
)
from app.setup_crosscheck import check_typed_fields, crosscheck_setup_fields


def test_coerce_setup_bool_strings_and_labels():
    assert coerce_setup_bool(True) is True
    assert coerce_setup_bool("true") is True
    assert coerce_setup_bool("yes") is True
    assert coerce_setup_bool("false") is False
    assert coerce_setup_bool("off") is False
    # 8B returns system UI label instead of bool
    assert coerce_setup_bool("Subtle blue-window system") is False
    assert coerce_setup_bool("compounding edge") is False


def test_normalize_magic_level_canonical_and_aliases():
    assert normalize_magic_level("rare") == "rare"
    assert normalize_magic_level("forbidden") == "forbidden"
    assert normalize_magic_level("common utility") == "common utility"
    assert normalize_magic_level("cultivation") == "cultivation"
    assert normalize_magic_level("none") == "none"
    # aliases
    assert normalize_magic_level("low and dangerous") == "rare"
    assert normalize_magic_level("high magic") == "common utility"
    assert normalize_magic_level("no magic") == "none"
    assert normalize_magic_level("xianxia") == "cultivation"
    assert normalize_magic_level("banned") == "forbidden"
    # instruction echo
    assert normalize_magic_level("magic prevalence only") == "rare"
    assert normalize_magic_level("Return magic prevalence only.") == "rare"


def test_is_instruction_echo():
    assert is_instruction_echo("magic prevalence only")
    assert is_instruction_echo("Return only easy, normal, hard, or brutal")
    assert is_instruction_echo("Growth speed label only.")
    assert not is_instruction_echo("forbidden")  # valid magic_level
    assert not is_instruction_echo("rare")
    assert not is_instruction_echo("normal")


def test_coerce_typed_enums_and_bools():
    out, dirty = coerce_typed_setup_fields(
        {
            "leveling_system": "Subtle blue-window system",
            "game_system": "true",
            "magic_level": "magic prevalence only",
            "difficulty": "COMPOUNDING EDGE",
            "narration_detail": "rich prose please",
            "xp_growth_speed": "very slow",
            "proficiency_access": "Start with one near-useless compounding skill seed frame",
        }
    )
    assert out["leveling_system"] is False
    assert out["game_system"] is True
    assert out["magic_level"] == "rare"
    assert out["difficulty"] == "normal"
    assert out["xp_growth_speed"] == "very slow"
    assert "compound" not in str(out["proficiency_access"]).lower()
    assert dirty


def test_sanitize_setup_fields_clamps_8b_slop():
    fields, dirty = sanitize_setup_fields(
        {
            "leveling_system": "Subtle blue-window system",
            "magic_level": "magic prevalence only",
            "difficulty": "brutal difficulty with compounding edge",
            "game_system": "yes",
            "skill_levels_enabled": "1",
            "quest_style": "near-useless skill compounds after 1-hour delay",
            "economy": "Return only economy structure; never paste skills.",
        }
    )
    assert fields["leveling_system"] is False
    assert fields["magic_level"] == "rare"
    assert fields["difficulty"] == "normal" or fields["difficulty"] == "brutal"
    # difficulty fuzzy: "brutal difficulty..." may fuzzy-match brutal
    assert fields["difficulty"] in {"easy", "normal", "hard", "brutal"}
    assert fields["game_system"] is True
    assert fields["skill_levels_enabled"] is True
    assert "compound" not in str(fields.get("quest_style") or "").lower()
    assert "return only" not in str(fields.get("economy") or "").lower()
    assert dirty


def test_llm_sanitize_setup_randomization_values():
    s = _sanitize_setup_randomization_values(
        {
            "leveling_system": "Subtle blue-window system",
            "magic_level": "magic prevalence only",
            "game_system": "on",
            "difficulty": "hard",
            "special_ability_origin": "acquired",
            "special_abilities": [{"name": "Footprint Echo", "description": "Tracks steps.", "locked": False}],
            "custom_skills": "one-skill compounding seed frame",
            "proficiency_access": "only expert tasks require training",
        }
    )
    assert s["leveling_system"] is False
    assert s["magic_level"] == "rare"
    assert s["game_system"] is True
    assert s["difficulty"] == "hard"
    # special_ability_origin is legacy and is popped before this sanitizer runs
    # (app/llm.py), so it does not drive locks here -- per-card locks pass through.
    assert s["special_abilities"][0]["locked"] is False
    # Locking is decided once the whole batch exists. It is deliberately
    # probabilistic for mild/moderate powers, but a strong power is always locked
    # when it can be acquired rather than innate.
    from app.llm import assign_ability_locks_after_creation

    strong = {
        "name": "Absolute Dominion",
        "description": "Instantly kills any target, unlimited range, no cost, compounding forever.",
        "locked": False,
    }
    for origin in ("acquired", "both"):
        rolled = assign_ability_locks_after_creation([dict(strong)], origin=origin)
        assert rolled[0]["locked"] is True, (origin, rolled)
    assert assign_ability_locks_after_creation([dict(strong)], origin="innate")[0]["locked"] is False
    assert "Footprint Echo" in s["custom_skills"]
    assert "one-skill" not in s["custom_skills"].lower()


def test_crosscheck_typed_fields_repairs():
    out, findings = check_typed_fields(
        {
            "magic_level": "Return magic prevalence only",
            "race_magic_enabled": "false",
            "difficulty": "normal",
        }
    )
    assert out["magic_level"] == "rare"
    assert out["race_magic_enabled"] is False
    assert findings


def test_crosscheck_setup_fields_end_to_end():
    report = crosscheck_setup_fields(
        {
            "magic_level": "low and dangerous",
            "leveling_system": "yes",
            "game_system": "Subtle blue-window system",
            "quest_style": "compounding near-useless skill growth",
            "difficulty": "normal",
        },
        idea="OP MC with one weak skill that compounds",
        repair=True,
    )
    fields = report["fields"]
    assert fields["magic_level"] == "rare"
    assert fields["leveling_system"] is True
    assert fields["game_system"] is False
    assert "compound" not in str(fields.get("quest_style") or "").lower()


def test_coerce_typed_value_single_field():
    v, reasons = coerce_typed_setup_value("magic_level", "cultivation world")
    assert v == "cultivation"
    assert reasons
    v2, r2 = coerce_typed_setup_value("difficulty", "easy")
    assert v2 == "easy"
    assert r2 == []
