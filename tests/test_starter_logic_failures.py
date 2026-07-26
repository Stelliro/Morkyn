"""
Stress tests: lore-mismatch failure methods for starter gear.

Each case must:
1) strip or defer the offending item(s)
2) leave show_popup True
3) provide a clear player_reason / player_messages explaining why
4) not leave the item in kept inventory names
"""

from __future__ import annotations

from app.starter_logic import (
    ARRIVAL_ISEKAI_ARRIVAL,
    ARRIVAL_NATIVE,
    fact_check_starter_loadout,
)


def _names(rows: list[dict]) -> str:
    return " | ".join(str(r.get("name") or "").lower() for r in rows)


def _assert_popup_explains(report: dict, *needles: str) -> None:
    assert report.get("show_popup") is True, report.get("summary")
    blob = " ".join(report.get("player_messages") or []).lower()
    for row in list(report.get("stripped") or []) + list(report.get("deferred") or []):
        blob += " " + str(row.get("player_reason") or "").lower()
        blob += " " + " ".join(str(x) for x in (row.get("reasons") or []))
    for n in needles:
        assert n.lower() in blob, f"expected player-facing reason to mention {n!r}; got: {blob[:400]}"


def _assert_not_kept(report: dict, *fragments: str) -> None:
    kept = _names(report.get("kept") or [])
    for frag in fragments:
        assert frag.lower() not in kept, f"{frag!r} still in kept: {kept}"


def test_cyberpunk_wand_powers_off_strips_magic():
    report = fact_check_starter_loadout(
        starter_equipment="neon jacket, cyberdeck, oak wand, healing potion, spell scroll",
        backstory_mode="known",
        character_backstory="Street courier in Night City. No magic. Just chrome and debt.",
        intent={"isekai": False, "genre": "cyberpunk"},
        world_style="neon megacity cyberpunk",
        tech_level="near future cyber",
        magic_level="none",
        special_ability_origin="none",
    )
    assert report["arrival"]["cyberpunk_world"] is True
    _assert_not_kept(report, "wand", "potion", "spell")
    stripped = _names(report["stripped"])
    assert "wand" in stripped
    assert "potion" in stripped
    assert report["show_popup"] is True
    assert all(r.get("player_reason") for r in report["stripped"])
    _assert_popup_explains(report, "magical", "wand")


def test_cyberpunk_medieval_plate_stripped():
    report = fact_check_starter_loadout(
        starter_equipment="neon jacket, plate armor, iron sword, wooden shield, pistol",
        backstory_mode="known",
        character_backstory="Netrunner who lives in the megacity undercorp.",
        intent={"genre": "cyberpunk"},
        world_style="cyberpunk neon chrome",
        tech_level="cyber",
        magic_level="none",
        special_ability_origin="none",
    )
    _assert_not_kept(report, "plate", "iron sword", "shield")
    stripped = _names(report["stripped"])
    assert "plate" in stripped
    # pistol is modern tech — keep in cyber
    kept = _names(report["kept"])
    assert "neon" in kept or "pistol" in kept
    assert report["show_popup"] is True
    _assert_popup_explains(report, "fantasy")


def test_isekai_non_magic_origin_strips_wand_and_grimoire():
    report = fact_check_starter_loadout(
        starter_equipment="worn hoodie, smartphone, wooden wand, grimoire of fire, iron sword",
        appearance="torso: hoodie; bag: messenger bag",
        backstory_mode="transmigrated",
        character_backstory=(
            "They died at a desk job and woke on a dirt road in another world "
            "with city clothes still on."
        ),
        intent={"isekai": True, "genre": "isekai fantasy", "portal_or_rebirth": "other_world"},
        world_style="isekai dark fantasy",
        tech_level="medieval",
        magic_level="common",
        special_ability_origin="none",
    )
    assert report["arrival"]["arrival"] == ARRIVAL_ISEKAI_ARRIVAL
    _assert_not_kept(report, "wand", "grimoire", "sword")
    stripped = _names(report["stripped"])
    assert "wand" in stripped
    assert "grimoire" in stripped
    deferred = _names(report["deferred"])
    assert "sword" in deferred
    kept = _names(report["kept"])
    assert "hoodie" in kept or "smartphone" in kept
    assert report["show_popup"] is True
    assert len(report["player_messages"]) >= 2
    _assert_popup_explains(report, "non-magical", "wand")


def test_isekai_magic_origin_keeps_pocket_wand():
    report = fact_check_starter_loadout(
        starter_equipment="worn robes, wooden wand, notebook",
        backstory_mode="transmigrated",
        character_backstory=(
            "Was a wizard in their previous world which had magic, then transported "
            "through a portal into another world with robes and a pocket wand still on them."
        ),
        intent={"isekai": True, "genre": "isekai fantasy"},
        world_style="isekai fantasy",
        tech_level="medieval",
        magic_level="common",
    )
    assert report["arrival"]["arrival"] == ARRIVAL_ISEKAI_ARRIVAL
    kept = _names(report["kept"])
    assert "wand" in kept
    assert "robe" in kept or "notebook" in kept


def test_legendary_op_items_always_stripped():
    report = fact_check_starter_loadout(
        starter_equipment="tunic, Excalibur, SSS-rank mythic relic blade, holy grail",
        backstory_mode="known",
        character_backstory="A simple farmer from the village outskirts.",
        intent={},
        world_style="fantasy kingdom",
        magic_level="rare",
    )
    _assert_not_kept(report, "excalibur", "mythic", "grail")
    assert len(report["stripped"]) >= 3
    assert all("legendary" in (r.get("player_reason") or "").lower() or "god-tier" in (r.get("player_reason") or "").lower() for r in report["stripped"])
    assert report["show_popup"] is True


def test_modern_phone_in_native_medieval_fantasy_stripped():
    report = fact_check_starter_loadout(
        starter_equipment="smartphone, laptop, tunic, bread",
        backstory_mode="known",
        character_backstory="Born in a medieval village as a baker's apprentice.",
        intent={},
        world_style="medieval fantasy kingdom",
        tech_level="iron age",
        magic_level="rare",
    )
    assert report["arrival"]["arrival"] == ARRIVAL_NATIVE
    _assert_not_kept(report, "smartphone", "laptop")
    kept = _names(report["kept"])
    assert "tunic" in kept
    _assert_popup_explains(report, "modern")


def test_amnesia_strips_unexplained_kit():
    report = fact_check_starter_loadout(
        starter_equipment="iron sword, gold bar, enchanted amulet of power, torn shirt",
        backstory_mode="amnesia",
        character_backstory="Woke with no memory and only the clothes on their back.",
        intent={},
        world_style="fantasy",
        magic_level="rare",
    )
    _assert_not_kept(report, "sword", "gold")
    # Power amulet may be demoted to plain amulet then still stripped by amnesia rules,
    # or stripped as power claim — never kept as free enchanted gear.
    kept = _names(report["kept"])
    assert "enchanted" not in kept
    assert "shirt" in kept
    assert report["show_popup"] is True
    _assert_popup_explains(report, "amnesia")


def test_enchanted_clothing_non_magic_modern_stripped():
    report = fact_check_starter_loadout(
        starter_equipment="enchanted cloak, arcane gloves, work boots, smartphone",
        backstory_mode="known",
        character_backstory="Office worker in present day Tokyo. Completely mundane life.",
        intent={"genre": "modern slice of life"},
        world_style="contemporary urban",
        tech_level="modern",
        magic_level="none",
        special_ability_origin="none",
    )
    # Power claims removed or demoted — never kept as free enchanted gear
    _assert_not_kept(report, "enchanted", "arcane")
    kept = _names(report["kept"])
    assert "boot" in kept or "cloak" in kept or "glove" in kept or "smartphone" in kept
    # Ordinary demotion or magic lore strip should surface in popup
    assert report.get("show_popup") is True


def test_powers_off_fantasy_strips_wand_without_mage_vocation():
    report = fact_check_starter_loadout(
        starter_equipment="tunic, wooden wand, water skin",
        backstory_mode="known",
        character_backstory="A quiet cartwright in a market town. No magic training.",
        intent={},
        world_style="low magic frontier",
        tech_level="iron age",
        magic_level="rare",
        special_ability_origin="none",
    )
    # wand should not be free starter when powers off and no vocation
    _assert_not_kept(report, "wand")
    assert report["show_popup"] is True
    assert any("wand" in (r.get("name") or "").lower() for r in report["stripped"] + report["deferred"])


def test_valuable_gold_bar_stripped_native():
    report = fact_check_starter_loadout(
        starter_equipment="tunic, sack of gold, diamond necklace",
        backstory_mode="known",
        character_backstory="A poor fisherman from the docks.",
        intent={},
        world_style="fantasy port",
        magic_level="rare",
    )
    _assert_not_kept(report, "gold", "diamond")
    assert report["show_popup"] is True
    _assert_popup_explains(report, "valuab")


def test_isekai_combat_kit_deferred_not_kept():
    report = fact_check_starter_loadout(
        starter_equipment="jeans, sneakers, wooden shield, iron sword, plate helm",
        backstory_mode="known",
        character_backstory="Summoned through a portal into a fantasy kingdom last night.",
        intent={"isekai": True, "genre": "isekai fantasy"},
        world_style="isekai fantasy",
        tech_level="medieval",
        magic_level="common",
    )
    assert report["arrival"]["arrival"] == ARRIVAL_ISEKAI_ARRIVAL
    _assert_not_kept(report, "shield", "sword", "helm")
    deferred = _names(report["deferred"])
    assert "shield" in deferred or "sword" in deferred
    assert report["show_popup"] is True
    assert all(r.get("player_reason") for r in report["deferred"])


def test_modern_origin_localized_not_free_full_kit():
    """Near-future origin in fantasy compound: stitch arrival; do not keep every modern item."""
    report = fact_check_starter_loadout(
        starter_equipment=(
            "frayed maintenance vest, small tool pouch, water flask, "
            "cracked gloves, worn boots, copper coins, wooden charm, smartphone"
        ),
        appearance="torso: frayed maintenance vest; hands: cracked gloves; feet: worn boots",
        backstory_mode="transmigrated",
        character_backstory=(
            "A maintenance technician in a near-future city specializing in automated systems."
        ),
        intent={"isekai": True, "genre": "isekai fantasy"},
        world_style="Mundane isekai compound",
        tech_level="medieval",
        magic_level="cultivation",
    )
    path = str((report.get("vibe") or {}).get("path") or "")
    assert path in {"stitch_arrival_keep_former_life", "keep_earth_origin_thin_kit", "localize_origin_to_world"}
    story = (report.get("character_backstory") or "").lower()
    assert "woke" in story or "died" in story or "another world" in story
    kept = _names(report["kept"])
    assert "smartphone" not in kept
    assert len(report["kept"]) <= 8
    assert report.get("show_popup") is True


def test_explicit_earth_arrival_keeps_thin_not_all():
    """Explicit truck-kun arrival may keep Earth origin, but not a full survival pack."""
    report = fact_check_starter_loadout(
        starter_equipment="hoodie, jeans, sneakers, smartphone, water flask, small tool pouch, iron sword",
        appearance="torso: hoodie; feet: sneakers",
        backstory_mode="known",
        character_backstory="Died at a desk job and woke on a dirt road in another world.",
        intent={"isekai": True, "genre": "isekai fantasy"},
        world_style="isekai fantasy",
        tech_level="medieval",
    )
    kept = _names(report["kept"])
    assert "sword" not in kept
    assert "tool" not in kept
    assert "flask" not in kept
    # Clothes / one pocket gadget ok
    assert "hoodie" in kept or "clothes" in kept or "jean" in kept or "sneaker" in kept or "smartphone" in kept


def test_hard_scifi_mana_crystal_stripped():
    report = fact_check_starter_loadout(
        starter_equipment="vac suit liner, datapad, mana crystal, spellbook",
        backstory_mode="known",
        character_backstory="Spacer engineer on a colony freighter. Hard science only.",
        intent={"genre": "sci-fi"},
        world_style="hard sci-fi space colony",
        tech_level="space age sci-fi",
        magic_level="none",
        special_ability_origin="none",
    )
    _assert_not_kept(report, "mana", "spell")
    assert report["show_popup"] is True
    _assert_popup_explains(report, "magical")


def test_popup_payload_has_structured_reasons_for_ui():
    """Mirrors what world.start stores and the FE modal renders."""
    report = fact_check_starter_loadout(
        starter_equipment="hoodie, magic wand, Excalibur",
        backstory_mode="known",
        character_backstory="Street samurai courier. Chrome and neon only.",
        intent={"genre": "cyberpunk"},
        world_style="cyberpunk neon",
        tech_level="cyber",
        magic_level="none",
        special_ability_origin="none",
    )
    assert report["show_popup"] is True
    assert report["popup_title"]
    assert report["player_messages"]
    for row in report["stripped"]:
        assert row.get("name")
        assert row.get("player_reason")
        assert "Removed" in row["player_reason"] or "removed" in row["player_reason"].lower()


def test_bulk_failure_battery_all_show_popup():
    """Run many intentional fail kits; every one must rip something and explain it."""
    kits = [
        {
            "name": "cyber wand",
            "starter_equipment": "chrome jacket, oak wand",
            "backstory_mode": "known",
            "character_backstory": "Fixer in the neon district.",
            "intent": {"genre": "cyberpunk"},
            "world_style": "cyberpunk",
            "tech_level": "cyber",
            "magic_level": "none",
            "special_ability_origin": "none",
            "must_rip": ["wand"],
        },
        {
            "name": "isekai grimoire",
            "starter_equipment": "t-shirt, jeans, grimoire of ice, staff of storms",
            "backstory_mode": "transmigrated",
            "character_backstory": "Hit by a truck and woke in another world with only street clothes.",
            "intent": {"isekai": True, "genre": "isekai"},
            "world_style": "isekai fantasy",
            "tech_level": "medieval",
            "magic_level": "common",
            "special_ability_origin": "none",
            "must_rip": ["grimoire", "staff"],
        },
        {
            "name": "god loot",
            "starter_equipment": "cloak, infinity blade, unique divine spear",
            "backstory_mode": "known",
            "character_backstory": "A kitchen hand in a tavern.",
            "intent": {},
            "world_style": "fantasy",
            "tech_level": "iron age",
            "magic_level": "rare",
            "special_ability_origin": "system",
            "must_rip": ["infinity", "divine"],
        },
        {
            "name": "gold dump",
            "starter_equipment": "shirt, gold bar, treasure chest key? no — sack of gold",
            "backstory_mode": "known",
            "character_backstory": "Street beggar.",
            "intent": {},
            "world_style": "fantasy",
            "tech_level": "iron age",
            "magic_level": "rare",
            "special_ability_origin": "",
            "must_rip": ["gold"],
        },
        {
            "name": "modern gun fantasy native",
            "starter_equipment": "tunic, pistol, credit card",
            "backstory_mode": "known",
            "character_backstory": "Born and raised as a shepherd in the hills.",
            "intent": {},
            "world_style": "medieval fantasy",
            "tech_level": "iron age",
            "magic_level": "rare",
            "special_ability_origin": "",
            "must_rip": ["pistol", "credit"],
        },
        {
            "name": "healing potion cyber",
            "starter_equipment": "hoodie, healing potion, mana crystal",
            "backstory_mode": "known",
            "character_backstory": "Barista with a side hustle in the megacity.",
            "intent": {"genre": "cyberpunk"},
            "world_style": "neon cyberpunk megacity",
            "tech_level": "cyber",
            "magic_level": "off",
            "special_ability_origin": "none",
            "must_rip": ["potion", "mana"],
        },
        {
            "name": "amnesia arsenal",
            "starter_equipment": "warhammer, plate mail, gold bar, rags",
            "backstory_mode": "amnesia",
            "character_backstory": "Blank slate. Cannot remember anything.",
            "intent": {},
            "world_style": "fantasy",
            "tech_level": "iron age",
            "magic_level": "rare",
            "special_ability_origin": "",
            "must_rip": ["warhammer", "plate", "gold"],
        },
        {
            "name": "summoned with shield",
            "starter_equipment": "school uniform, wooden shield, shortsword",
            "backstory_mode": "known",
            "character_backstory": "Just arrived after being summoned as a hero candidate.",
            "intent": {"isekai": True, "genre": "isekai"},
            "world_style": "isekai",
            "tech_level": "medieval",
            "magic_level": "common",
            "special_ability_origin": "system",
            "must_rip": ["shield", "sword"],
        },
    ]
    failures: list[str] = []
    for kit in kits:
        report = fact_check_starter_loadout(
            starter_equipment=kit["starter_equipment"],
            backstory_mode=kit["backstory_mode"],
            character_backstory=kit["character_backstory"],
            intent=kit["intent"],
            world_style=kit["world_style"],
            tech_level=kit["tech_level"],
            magic_level=kit["magic_level"],
            special_ability_origin=kit["special_ability_origin"],
            apply_fixes=True,
        )
        if not report.get("show_popup"):
            failures.append(f"{kit['name']}: no popup")
        ripped = _names(report.get("stripped") or []) + " " + _names(report.get("deferred") or [])
        for frag in kit["must_rip"]:
            if frag.lower() not in ripped:
                failures.append(f"{kit['name']}: {frag!r} not ripped (ripped={ripped})")
            if frag.lower() in _names(report.get("kept") or []):
                failures.append(f"{kit['name']}: {frag!r} still kept")
        msgs = report.get("player_messages") or []
        if not msgs:
            failures.append(f"{kit['name']}: empty player_messages")
        for row in list(report.get("stripped") or []) + list(report.get("deferred") or []):
            if not str(row.get("player_reason") or "").strip():
                failures.append(f"{kit['name']}: missing player_reason on {row.get('name')}")
    assert not failures, "\n".join(failures)
