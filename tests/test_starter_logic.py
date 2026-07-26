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
    # Explicit just-arrived Earth life may keep thin isekai kit; combat never free.
    kept = " ".join(k["name"].lower() for k in report["kept"])
    assert "shield" not in kept
    assert "sword" not in kept
    deferred = " ".join(d["name"].lower() for d in report["deferred"])
    assert "shield" in deferred or "sword" in deferred
    # Pure isekai does not pre-pack flask
    assert "flask" not in kept


def test_localizes_modern_origin_to_world_vibe():
    """Near-future CV without arrival is stitched, not wiped to a generic yard-mender template."""
    report = fact_check_starter_loadout(
        starter_equipment=(
            "frayed maintenance vest, small tool pouch, water flask, "
            "cracked gloves, worn boots, copper coins, wooden charm"
        ),
        appearance="torso: frayed maintenance vest; hands: cracked gloves; feet: worn boots",
        backstory_mode="transmigrated",
        character_backstory=(
            "A maintenance technician in a near-future city, specializing in repairing automated systems. "
            "They lived a routine life balancing work and family."
        ),
        intent={"isekai": True, "genre": "isekai fantasy"},
        world_style="Mundane isekai compound",
        tech_level="medieval",
        magic_level="cultivation",
        apply_fixes=True,
    )
    path = str((report.get("vibe") or {}).get("path") or "")
    assert path in {"stitch_arrival_keep_former_life", "keep_earth_origin_thin_kit", "localize_origin_to_world"}
    story = (report.get("character_backstory") or "").lower()
    assert "technician" in story or "maintenance" in story or "mender" in story
    assert "woke" in story or "died" in story or "another world" in story
    assert "yard mender who kept pumps" not in story or "technician" in story
    kept = " ".join(k["name"].lower() for k in report["kept"])
    assert "smartphone" not in kept
    assert "vest" in kept or "glove" in kept or "boot" in kept
    assert len(report["kept"]) <= 8


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


def test_native_ordinary_no_powerful_items_clothing_matches_life():
    """Born-in-world ordinary: demote power claims; clothes must match vocation."""
    report = fact_check_starter_loadout(
        starter_equipment="enchanted cloak, plate breastplate, wooden charm, baker's apron, water skin",
        appearance="torso: plate breastplate; waist: baker's apron",
        backstory_mode="known",
        character_backstory="Born in a market town as a baker's apprentice who works the night ovens.",
        intent={},
        world_style="medieval fantasy kingdom",
        tech_level="iron age",
        magic_level="rare",
        apply_fixes=True,
    )
    assert report.get("ordinary_start") is True
    kept = " ".join(k["name"].lower() for k in report["kept"])
    assert "enchanted" not in kept
    assert "plate" not in kept
    assert "apron" in kept or "clothes" in kept or "cloak" in kept
    # plate deferred/replaced; combat free not kept
    deferred = " ".join(d["name"].lower() for d in report["deferred"])
    stripped = " ".join(s["name"].lower() for s in report["stripped"])
    assert "plate" in deferred or "plate" in stripped or "plate" not in kept
    # Latent candidates exist for DM later; items themselves not pre-powered
    assert report.get("latent_candidates") is not None
    for row in report["kept"]:
        assert row.get("rarity") == "common"
        assert row.get("enchantments") == []
        assert row.get("granted_abilities") == []
    assert "LATENT" in (report.get("gm_brief") or "") or "latent" in (report.get("gm_brief") or "").lower()


def test_clothing_mismatch_rewrites_mage_robe_for_clerk():
    report = fact_check_starter_loadout(
        starter_equipment="mage robe, coin purse, plain boots",
        appearance="torso: mage robe; feet: plain boots",
        backstory_mode="known",
        character_backstory="A compound clerk who tallies grain fees at the gate office.",
        intent={},
        world_style="fantasy compound",
        tech_level="iron age",
        magic_level="rare",
    )
    kept = " ".join(k["name"].lower() for k in report["kept"])
    app = (report.get("appearance") or "").lower()
    assert "mage robe" not in kept
    assert "mage robe" not in app
    assert "clerk" in (report.get("character_backstory") or "").lower() or report.get("ordinary_start")
