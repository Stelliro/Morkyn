"""Cross-field setup consistency: race rules vs world_races; memory vs backstory."""

from __future__ import annotations

from app.setup_composer import (
    apply_consistency_lint,
    memory_backstory_mismatch,
    parse_world_races,
    race_rules_mismatch_reasons,
    rebuild_race_rules,
    resolve_memory_policy,
    sanitize_setup_fields,
)


def test_parse_world_races():
    assert parse_world_races("human, elf, dwarf") == ["human", "elf", "dwarf"]
    assert parse_world_races(["Human", "elf", "human"]) == ["Human", "elf"]
    assert parse_world_races("human and riverfolk") == ["human", "riverfolk"]


def test_race_rules_flag_foreign_peoples():
    rules = "Elves inherit glamour; dwarves use runes; beastfolk sense spirits."
    reasons = race_rules_mismatch_reasons("human", rules)
    assert "race_rules_foreign_races" in reasons


def test_race_rules_ok_when_aligned():
    rules = "Humans need formal training; elves inherit low glamour."
    reasons = race_rules_mismatch_reasons("human, elf", rules)
    assert reasons == []


def test_rebuild_race_rules_human_only():
    text = rebuild_race_rules("race_magic_rules", "human")
    assert "Human" in text or "human" in text.lower()
    assert "elf" not in text.lower()


def test_rebuild_race_rules_multi():
    text = rebuild_race_rules("race_ability_rules", "human, beastfolk")
    assert "human" in text.lower()
    assert "beastfolk" in text.lower()


def test_apply_consistency_lint_rewrites_race_rules():
    fields = {
        "world_races": "human",
        "race_magic_rules": "Elves cast freely; dwarves use runes; orcs bind blood magic.",
        "race_ability_rules": "Elves sense forests; dwarves endure stone; goblins scavenge.",
    }
    out, dirty = apply_consistency_lint(fields)
    assert "race_magic_rules" in dirty
    assert "elf" not in out["race_magic_rules"].lower()
    assert "human" in out["race_magic_rules"].lower()


def test_memory_fragmented_backstory_vs_known_policy():
    reasons = memory_backstory_mismatch(
        "reincarnated",
        "known",
        "They woke with only fragments of a former life and cannot remember their death.",
    )
    assert reasons
    new_policy, r2 = resolve_memory_policy(
        "reincarnated",
        "known",
        "They woke with only fragments of a former life and cannot remember their death.",
    )
    assert new_policy == "former life fragments"
    assert r2


def test_memory_intact_former_life():
    new_policy, reasons = resolve_memory_policy(
        "transmigrated",
        "former life fragments",
        "In their former life they died in a blackout; most memories intact.",
    )
    assert reasons
    assert new_policy == "remembers former life"


def test_memory_policy_claims_former_without_story():
    new_policy, reasons = resolve_memory_policy(
        "known",
        "remembers former life",
        "Born in a canal district and worked as a route clerk before arriving here.",
    )
    assert "memory_policy_claims_former_life_without_backstory" in reasons
    assert new_policy == "ordinary memory"


def test_sanitize_setup_fields_runs_consistency_pass():
    fields = {
        "world_races": "human",
        "race_magic_rules": "Elves and dwarves dominate magic; orcs swear blood rites.",
        "backstory_mode": "reincarnated",
        "memory_policy": "known",
        "character_backstory": "They remember only fragments of dying on a rain-slick road in another world.",
    }
    out, dirty = sanitize_setup_fields(fields)
    assert "race_magic_rules" in dirty or "memory_policy" in dirty
    assert out["memory_policy"] == "former life fragments"
    assert "elf" not in str(out.get("race_magic_rules") or "").lower()
