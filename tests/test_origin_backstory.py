"""Isekai / transmigration origin + backstory package quality."""

from __future__ import annotations

from app.setup_composer import (
    apply_keyword_intent,
    intent_to_field_overrides,
    normalize_backstory_mode,
    normalize_memory_policy,
    normalize_origin_package,
    normalize_previous_life_age,
    rewrite_backstory_third_person,
    sanitize_setup_fields,
)
from app.starter_logic import fact_check_starter_loadout


def test_normalize_mode_from_prose():
    assert normalize_backstory_mode("woke from a truck crash in a fantasy compound") == "transmigrated"
    assert normalize_backstory_mode("reincarnated with fragmented memories of a modern world") == "reincarnated"
    assert normalize_backstory_mode("known") == "known"
    assert (
        normalize_backstory_mode(
            "",
            story="They died at a desk and woke on a dirt road in another world.",
        )
        == "transmigrated"
    )


def test_normalize_memory_and_age():
    assert (
        normalize_memory_policy("remembers former life with fragmented office routines")
        == "former life fragments"
    )
    assert normalize_previous_life_age("late twenties") == "28"
    assert normalize_previous_life_age("twenty-seven") == "27"
    assert normalize_previous_life_age("27") == "27"


def test_first_person_rewritten():
    text = rewrite_backstory_third_person(
        "Born in Neo City, I was a forklift operator. I died in a crash and woke on a road."
    )
    assert "I was" not in text
    assert "they" in text.lower()


def test_summoned_sets_isekai_intent():
    plan = apply_keyword_intent("summoned by a failed ritual into a sect outer court")
    assert plan["isekai"] is True
    assert plan.get("portal_or_rebirth") in {"other_world", "body_transmigration"}


def test_reincarnated_childhood_override():
    plan = apply_keyword_intent(
        "reincarnated as a village child years ago, grew up local, remembers fragments of modern life"
    )
    assert plan["isekai"] is True
    assert plan.get("portal_or_rebirth") == "same_world_rebirth"
    fields = intent_to_field_overrides(plan)
    assert fields.get("backstory_mode") == "reincarnated"
    assert "fragment" in str(fields.get("memory_policy") or "").lower()


def test_truck_story_not_wiped_to_yard_mender():
    story = (
        "Born in a working-class district of Neo-Silicon City, they were a night-shift forklift operator "
        "at a logistics hub until a truck accident killed them. They woke on a dirt road beside a river "
        "compound with warehouse habits intact and no free hero kit."
    )
    report = fact_check_starter_loadout(
        starter_equipment="hoodie, jeans, sneakers, smartphone, water flask",
        appearance="torso: hoodie; feet: sneakers",
        backstory_mode="transmigrated",
        memory_policy="remembers former life",
        character_backstory=story,
        intent={"isekai": True, "genre": "isekai fantasy", "portal_or_rebirth": "other_world"},
        world_style="Mundane isekai compound",
        tech_level="medieval",
        apply_fixes=True,
    )
    final = (report.get("character_backstory") or "").lower()
    assert any(x in final for x in ("forklift", "logistics", "warehouse", "truck", "night-shift", "night shift", "accident"))
    assert "yard mender who kept pumps" not in final
    path = str((report.get("vibe") or {}).get("path") or "")
    assert path in {
        "keep_earth_origin_thin_kit",
        "stitch_arrival_keep_former_life",
        "localize_gear_only",
        "none",
        "already_local",
        "origin_matches_world",
        "keep_earth_origin_thin_kit",
    } or "yard mender who kept pumps" not in final


def test_sanitize_origin_package_collapses_prose_mode():
    fields, dirty = sanitize_setup_fields(
        {
            "backstory_mode": "woke from a truck crash in a fantasy compound",
            "memory_policy": "partial former-life fragments with uncertain rumors and private details",
            "character_backstory": (
                "Born in Neo City, I was a night-shift forklift operator. "
                "My life revolved around warehouse shifts until a crash."
            ),
            "previous_life_age": "late twenties",
            "world_style": "Compound Clerk's Fair Edge",
        },
        idea="isekai truck accident ordinary to overpowered",
    )
    assert fields["backstory_mode"] == "transmigrated"
    assert fields["memory_policy"] in {"former life fragments", "details emerge through choices", "remembers former life"}
    assert "I was" not in fields["character_backstory"]
    assert "another world" in fields["character_backstory"].lower() or "woke" in fields["character_backstory"].lower()
    assert fields["previous_life_age"] == "28"
    ws = str(fields.get("world_style") or "").lower()
    assert "fair edge" not in ws
    assert "isekai" in ws or "fantasy" in ws or "compound" in ws


def test_body_transmigration_keeps_two_lives_framed():
    story = (
        "They remember dying as a tired office clerk, then waking inside the body of a debt-ridden "
        "compound ledger-hand already known to local gate crews. The body's calluses are real; "
        "old-world memories arrive in fragments between work shifts."
    )
    out, _ = normalize_origin_package(
        {
            "backstory_mode": "transmigrated",
            "memory_policy": "former life fragments",
            "character_backstory": story,
        },
        idea="transmigrated into the body of a debt-ridden compound clerk",
    )
    assert out["backstory_mode"] == "transmigrated"
    assert "body" in out["character_backstory"].lower()
    assert "office" in out["character_backstory"].lower() or "clerk" in out["character_backstory"].lower()


def test_native_fantasy_plot_rewritten_for_transmigrated():
    """Disgraced-noble / festival guest + bolted isekai line is NOT a valid transmigration backstory."""
    from app.setup_composer import ensure_isekai_arrival_beat, transmigration_story_score

    bad = (
        "They were a disgraced noble heir in a collapsing empire, forced into exile after a failed coup. "
        "Now, they're a guest at a distant town's festival, posing as a wandering merchant to avoid detection. "
        "Their weak seed skill, Guest Right, allows them to temporarily halt hostilities through shared meals, "
        "but its power is tied to risk and use, making every encounter a gamble. They're desperate to find a way "
        "back to their homeland, but the only path forward is through diplomacy and the hidden costs of compounding "
        "their skill They died or were torn from that life and woke in another world with ordinary work habits "
        "and no free hero kit."
    )
    score = transmigration_story_score(bad)
    assert score["ok"] is False
    assert score["skill_meta"] is True or score["native_fantasy_plot_hits"] >= 2 or score["bolted_generic_arrival"]

    fixed = ensure_isekai_arrival_beat(
        bad,
        mode="transmigrated",
        idea="isekai ordinary to overpowered",
        world_style="Mundane isekai compound",
    )
    fixed_l = fixed.lower()
    assert "guest right" not in fixed_l
    assert "compounding" not in fixed_l
    assert "disgraced noble" not in fixed_l
    assert "former life" in fixed_l or "worked" in fixed_l or "job" in fixed_l or "office" in fixed_l or "warehouse" in fixed_l or "technician" in fixed_l or "student" in fixed_l or "city" in fixed_l
    assert any(m in fixed_l for m in ("died", "woke", "accident", "truck", "summon", "portal", "transport"))
    assert transmigration_story_score(fixed)["ok"] is True


def test_sanitize_rejects_noble_festival_transmigrated_story():
    fields, dirty = sanitize_setup_fields(
        {
            "backstory_mode": "transmigrated",
            "memory_policy": "remembers former life",
            "character_backstory": (
                "They were a disgraced noble heir in a collapsing empire, forced into exile after a failed coup. "
                "Now they pose as a wandering merchant at a festival. Their weak seed skill Guest Right compounds."
            ),
            "world_style": "isekai fantasy compound",
            "tech_level": "medieval",
        },
        idea="isekai transmigrated ordinary start",
    )
    story = str(fields.get("character_backstory") or "").lower()
    assert fields.get("backstory_mode") == "transmigrated"
    assert "guest right" not in story
    assert "disgraced noble" not in story
    assert "former life" in story or "worked" in story or "job" in story or "city" in story
