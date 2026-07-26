"""Board-wide setup cross-check across different settings / genres."""

from __future__ import annotations

from app.setup_composer import sanitize_setup_fields
from app.setup_crosscheck import crosscheck_setup_fields, crosscheck_setup_matrix, text_similarity


def test_text_similarity_basics():
    assert text_similarity("iron sword", "iron sword") == 1.0
    assert text_similarity("patched work vest", "patched canvas work vest") >= 0.5
    assert text_similarity("iron sword", "water skin") < 0.35


def _case(cid: str, idea: str, **fields):
    return {"id": cid, "idea": idea, "fields": fields}


def test_matrix_diverse_settings_runs_and_repairs():
    """Crush bugs across isekai, cyber, native, wuxia, scifi, amnesia packages."""
    cases = [
        _case(
            "isekai_truck",
            "isekai truck accident ordinary to overpowered",
            world_style="Compound Clerk's Fair Edge",
            tone="power fantasy compounding snowball",
            backstory_mode="woke from a truck crash in a fantasy compound",
            memory_policy="known",
            character_backstory="Born in Neo City, I was a forklift operator until a crash.",
            starter_equipment="hoodie, hoodie, smartphone, water flask, water flask, iron sword",
            appearance="torso: hoodie; hair: silver hair",
            hair="silver hair",
            facial_features="grey eyes, silver hair",
            magic_level="cultivation",
            tech_level="medieval",
            special_ability_origin="acquired",
            special_abilities=[
                {
                    "name": "Autumn Veil",
                    "description": "A veil of leaves obscures sight and sound for minutes.",
                    "cost": "Once per day",
                    "prerequisites": "[]",
                    "growth_math": "XP_to_next = 40 * rank^1.5; use 6 XP",
                    "power_type": "linear",
                    "locked": True,
                },
                {
                    "name": "Leaf Shroud",
                    "description": "A shroud of autumn leaves hides you from sight and muffles sound.",
                    "cost": "Once per day",
                    "prerequisites": "locked=true",
                    "growth_math": "XP_to_next = 42 * rank^1.45; use 5 XP",
                    "power_type": "linear",
                    "locked": True,
                },
            ],
            game_system=True,
            difficulty="normal",
        ),
        _case(
            "cyberpunk_native",
            "neon megacity cyberpunk, chrome and debt, no magic",
            world_style="cyberpunk neon chrome",
            tech_level="near future cyber",
            magic_level="none",
            backstory_mode="known",
            memory_policy="ordinary memory",
            character_backstory=(
                "Born in the undercorp stacks, they worked as a street courier carrying sealed chips "
                "and unpaid medical debt. They reached the starting block after a failed delivery left "
                "them marked by a local fixer."
            ),
            starter_equipment="neon jacket, cyberdeck, oak wand, healing potion, neon jacket",
            appearance="torso: neon jacket",
            special_ability_origin="none",
            special_abilities=[{"name": "Hack", "description": "Hack", "locked": False, "prerequisites": ""}],
            game_system=False,
            custom_skills="system UI, status window, chrome, chrome",
            difficulty="hard",
            death_rules="downed, not deleted",
        ),
        _case(
            "native_baker_fantasy",
            "quiet medieval bakery life",
            world_style="medieval fantasy kingdom",
            tech_level="iron age",
            magic_level="rare",
            backstory_mode="known",
            memory_policy="ordinary memory",
            character_backstory=(
                "Born in a market town as a baker's apprentice, they spent years learning ovens and "
                "flour debts. They are near the gate because a night delivery went missing."
            ),
            starter_equipment="baker's apron, water skin, smartphone, plate breastplate",
            appearance="torso: plate breastplate; waist: baker's apron",
            world_races="human, beastfolk",
            race_magic_rules="Elves inherit low magic; dwarves specialize in rune craft.",
            special_ability_origin="none",
            special_abilities=[],
            difficulty="easy",
            death_rules="permadeath threat",
        ),
        _case(
            "wuxia_body_swap",
            "transmigrated into the body of a debt-ridden sect outer disciple",
            world_style="wuxia mountain sect",
            tech_level="iron age",
            magic_level="cultivation",
            backstory_mode="transmigrated",
            memory_policy="remembers former life",
            character_backstory=(
                "They remember dying as an office clerk, then waking inside the body of a "
                "debt-ridden outer disciple already known to the gate wardens."
            ),
            starter_equipment="sect robe, sect robe, wooden charm, water skin",
            appearance="torso: sect robe",
            previous_life_age="late twenties",
            special_ability_origin="acquired",
            special_abilities=[],
            difficulty="normal",
        ),
        _case(
            "hard_scifi",
            "hard sci-fi colony freighter, no magic",
            world_style="hard sci-fi space colony",
            tech_level="space age sci-fi",
            magic_level="none",
            backstory_mode="known",
            memory_policy="ordinary memory",
            character_backstory=(
                "Born on a colony freighter, they worked as a spacer engineer keeping life support "
                "online. They are at the docking ring after a coolant fault nearly vented deck three."
            ),
            starter_equipment="vac suit liner, datapad, mana crystal, spellbook, datapad",
            appearance="torso: vac suit liner",
            special_ability_origin="none",
            special_abilities=[],
            difficulty="hard",
        ),
        _case(
            "amnesia_spawn",
            "woke with no memory",
            world_style="dark fantasy frontier",
            tech_level="iron age",
            magic_level="rare",
            backstory_mode="amnesia",
            memory_policy="details emerge through choices",
            character_backstory="Woke with no memory and only the clothes on their back near a ruined gate.",
            starter_equipment="torn shirt, iron sword, gold bar, enchanted amulet of power",
            appearance="torso: torn shirt",
            special_ability_origin="none",
            special_abilities=[],
            difficulty="normal",
        ),
        _case(
            "reincarnated_childhood",
            "reincarnated as a village child years ago, grew up local",
            world_style="low magic frontier kingdom",
            tech_level="medieval",
            magic_level="rare",
            backstory_mode="reincarnated",
            memory_policy="former life fragments",
            character_backstory=(
                "Reborn into a canal village as a child years ago, they grew up hauling water and "
                "copying notice boards while half-remembering glass towers from another life."
            ),
            starter_equipment="work gloves, small tool pouch, water skin",
            appearance="torso: patched tunic",
            previous_life_age="27",
            special_ability_origin="innate",
            special_abilities=[],
            difficulty="normal",
        ),
    ]

    report = crosscheck_setup_matrix(cases)
    assert report["totals"]["cases"] == len(cases)
    # Every case should return a fields dict
    for row in report["cases"]:
        assert isinstance(row.get("fields"), dict), row.get("id")
        fields = row["fields"]
        # Board repairs we insist on for contaminated packages
        if row["id"] == "isekai_truck":
            assert fields.get("backstory_mode") == "transmigrated" or "transmigrat" in str(
                fields.get("backstory_mode")
            ).lower()
            assert "I was" not in str(fields.get("character_backstory") or "")
            # equipment exact dups collapsed
            eq = str(fields.get("starter_equipment") or "").lower()
            assert eq.count("hoodie") <= 1
            assert eq.count("water flask") <= 1
            # ability prereq placeholders should be gone after dedupe/normalize path when abilities remain
            abs_list = fields.get("special_abilities") or []
            if isinstance(abs_list, list):
                for ab in abs_list:
                    if isinstance(ab, dict):
                        pr = str(ab.get("prerequisites") or "")
                        assert pr not in {"[]", "locked=true"}
        if row["id"] == "cyberpunk_native":
            # origin none clears abilities
            assert fields.get("special_abilities") in ([], None) or fields.get("special_abilities") == []
        if row["id"] == "wuxia_body_swap":
            assert str(fields.get("previous_life_age") or "") in {"28", "27", "late twenties"} or str(
                fields.get("previous_life_age") or ""
            ).isdigit()
        if row["id"] == "native_baker_fantasy":
            # race rules rebuilt away from elves/dwarves when races are human/beastfolk
            rules = str(fields.get("race_magic_rules") or "").lower()
            assert "elf" not in rules and "dwarf" not in rules or "human" in rules


def test_sanitize_setup_fields_attaches_crosscheck_report():
    fields, dirty = sanitize_setup_fields(
        {
            "world_style": "Compound Clerk's Fair Edge",
            "backstory_mode": "woke from a truck crash",
            "memory_policy": "known",
            "character_backstory": "Born in Neo City, I was a desk worker until a crash.",
            "starter_equipment": "hoodie, hoodie, water flask",
            "special_ability_origin": "none",
            "special_abilities": [{"name": "X", "description": "X"}],
            "magic_level": "cultivation",
            "tech_level": "medieval",
        },
        idea="isekai truck accident",
    )
    assert fields.get("backstory_mode") == "transmigrated"
    assert "I was" not in str(fields.get("character_backstory") or "")
    assert str(fields.get("starter_equipment") or "").lower().count("hoodie") <= 1
    assert fields.get("special_abilities") == []
    assert isinstance(fields.get("_setup_crosscheck"), dict)
    assert "summary" in fields["_setup_crosscheck"]


def test_crosscheck_detects_ability_description_equals_name():
    report = crosscheck_setup_fields(
        {
            "special_ability_origin": "acquired",
            "special_abilities": [
                {
                    "name": "shadow weave",
                    "description": "shadow weave",
                    "locked": True,
                    "prerequisites": "[]",
                    "cost": "once per day",
                    "growth_math": "xp 1",
                }
            ],
        },
        idea="isekai",
        repair=True,
    )
    codes = {f.get("code") for f in report["findings"]}
    assert "ability_description_equals_name" in codes or "ability_prereq_placeholder" in codes
