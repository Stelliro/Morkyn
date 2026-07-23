"""Starter gear arrival fact-check."""

from __future__ import annotations

from app.starter_logic import (
    ARRIVAL_ISEKAI_ARRIVAL,
    ARRIVAL_NATIVE,
    ARRIVAL_REINCARNATED,
    classify_arrival,
    fact_check_starter_loadout,
)


def test_isekai_arrival_strips_shield():
    report = fact_check_starter_loadout(
        starter_equipment="worn hoodie, smartphone, wooden shield, iron sword, water flask",
        appearance="torso: plate armor; feet: sneakers",
        backstory_mode="transmigrated",
        character_backstory=(
            "They died at a desk job and woke on a dirt road in another world with city clothes still on."
        ),
        intent={"isekai": True, "genre": "isekai fantasy", "portal_or_rebirth": "other_world"},
        world_style="isekai dark fantasy",
        tech_level="medieval",
        apply_fixes=True,
    )
    assert report["arrival"]["arrival"] == ARRIVAL_ISEKAI_ARRIVAL
    kept = " ".join(k["name"].lower() for k in report["kept"])
    assert "shield" not in kept
    assert "sword" not in kept
    assert "hoodie" in kept or "clothes" in kept or "smartphone" in kept
    deferred = " ".join(d["name"].lower() for d in report["deferred"])
    assert "shield" in deferred or "sword" in deferred


def test_reincarnated_can_keep_this_life_tools():
    report = fact_check_starter_loadout(
        starter_equipment="work gloves, small tool pouch, pocket knife, water skin",
        backstory_mode="reincarnated",
        character_backstory=(
            "Reborn into a canal village, they grew up as a route clerk and tool-mender "
            "and spent years repairing carts before the story begins."
        ),
        intent={"isekai": True, "portal_or_rebirth": "same_world_rebirth"},
        world_style="low magic mercantile city",
        apply_fixes=True,
    )
    assert report["arrival"]["arrival"] == ARRIVAL_REINCARNATED
    kept = [k["name"].lower() for k in report["kept"]]
    assert any("glove" in k or "tool" in k or "knife" in k for k in kept)


def test_native_guard_can_keep_spear():
    report = fact_check_starter_loadout(
        starter_equipment="militia spear, leather vest, water skin",
        backstory_mode="known",
        character_backstory=(
            "Born in Mosswake Gate, they served as a caravan guard and militia spearman for three years."
        ),
        intent={"isekai": False},
        world_style="frontier dark fantasy",
        apply_fixes=True,
    )
    assert report["arrival"]["arrival"] == ARRIVAL_NATIVE
    kept = " ".join(k["name"].lower() for k in report["kept"])
    assert "spear" in kept


def test_classify_arrival_isekai_from_story():
    info = classify_arrival(
        backstory_mode="known",
        character_backstory="Summoned through a portal into a fantasy kingdom last night.",
        intent={"isekai": True},
        world_style="isekai fantasy",
    )
    assert info["arrival"] == ARRIVAL_ISEKAI_ARRIVAL
