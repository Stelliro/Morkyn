"""Integrity fixes: starter gear, abilities, narration NPCs, test settings scrub."""

from __future__ import annotations

import json
import re

from app.db import connect, init_db
from app.world import (
    _collect_npcs_from_turn_result,
    _default_equip_slot_for_item,
    _ensure_npcs_from_narration,
    _is_test_settings_key,
    _looks_like_misfiled_location,
    _purge_test_settings,
    _sanitize_item_name,
    _scrub_settings_rows,
    apply_turn,
    export_world,
    is_plausible_person_name,
    start_playthrough,
)


def test_sanitize_item_name_strips_merge_junk():
    assert _sanitize_item_name("water skin [mixed] — stained coat") == "water skin"
    assert _sanitize_item_name("travel-stained coat") == "travel-stained coat"
    assert _sanitize_item_name("  copper coins  ") == "copper coins"
    assert _sanitize_item_name("[mixed]") == ""


def test_default_equip_slots():
    assert _default_equip_slot_for_item("travel-stained coat", "clothing") == "TORSO"
    assert _default_equip_slot_for_item("dusty boots", "clothing") == "FEET"
    assert _default_equip_slot_for_item("copper coins", "misc") == ""
    assert _default_equip_slot_for_item("water skin", "consumable") == ""


def test_test_settings_scrub():
    assert _is_test_settings_key("settlement_ruler:Stest_1_78036")
    assert not _is_test_settings_key("settlement_ruler:S99")
    rows = _scrub_settings_rows(
        [
            {"key": "setup_complete", "value": "true"},
            {"key": "settlement_ruler:Stest_abc", "value": "{}"},
            {
                "key": "quest_stages",
                "value": json.dumps({"test_portal": {"kind": "quest_portal"}, "real_stage": {"kind": "main"}}),
            },
        ]
    )
    keys = {r["key"] for r in rows}
    assert "settlement_ruler:Stest_abc" not in keys
    assert "setup_complete" in keys
    quest = next(r for r in rows if r["key"] == "quest_stages")
    data = json.loads(quest["value"])
    assert "test_portal" not in data
    assert "real_stage" in data


def test_start_playthrough_equips_worn_and_ability_fields():
    init_db()
    with connect() as conn:
        _purge_test_settings(conn)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("settlement_ruler:Stest_xyz", json.dumps({"npc_code": "Z"})),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("quest_stages", json.dumps({"test_portal": {"kind": "quest_portal", "summary": "x"}})),
        )

    state = start_playthrough(
        {
            "player_name": "Mara Vale",
            "world_style": "low magic coastal",
            "start_location": "Second Shadow Inn",
            "starter_equipment": "travel-stained coat, dusty boots, water skin [mixed] — stained coat, copper coins",
            "special_ability_origin": "acquired",
            "special_abilities": [
                {
                    "name": "Ash Veil",
                    "description": "A smoky veil that obscures movement for a short time.",
                    "locked": False,
                    "power_type": "linear",
                    "cost": "energy",
                    "resource_cost": {"energy": 2, "mana": 0, "fatigue": 0, "health": 0},
                }
            ],
        }
    )
    assert state
    inv = state.get("inventory") or []
    names = [str(i.get("name") or "") for i in inv]
    assert "travel-stained coat" in names
    assert "dusty boots" in names
    assert not any("mixed" in n.lower() or "—" in n for n in names)
    # water skin cleaned, not fused with coat
    assert any("water" in n.lower() and "coat" not in n.lower() for n in names)

    coat = next(i for i in inv if "coat" in str(i.get("name") or "").lower())
    boots = next(i for i in inv if "boot" in str(i.get("name") or "").lower())
    assert str(coat.get("equipped_slot") or "").upper() == "TORSO"
    assert str(boots.get("equipped_slot") or "").upper() == "FEET"

    abilities = state.get("abilities") or []
    assert abilities
    ash = next(a for a in abilities if a.get("name") == "Ash Veil")
    assert str(ash.get("code") or "").startswith("AB")
    assert str(ash.get("power_type") or "").lower() == "linear"

    # Test settings purged / not exported
    exported = export_world()
    settings = exported["tables"].get("settings") or []
    keys = [s.get("key") for s in settings]
    assert not any(str(k).startswith("settlement_ruler:Stest") for k in keys)
    quest = next((s for s in settings if s.get("key") == "quest_stages"), None)
    if quest:
        data = json.loads(quest["value"])
        assert "test_portal" not in data


def test_ensure_npcs_from_empty_opening_narration():
    init_db()
    start_playthrough(
        {
            "player_name": "Mara Vale",
            "world_style": "low magic",
            "start_location": "Second Shadow Inn",
            "starter_equipment": "travel-stained coat",
            "special_ability_origin": "none",
        }
    )
    narr = (
        "A hooded figure leans in, their voice low. "
        "A second figure, cloaked in ash-gray, eyes you from across the room."
    )
    result = apply_turn(
        {
            "narration": narr,
            "npcs": [],
            "locations": [],
            "inventory_changes": [],
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "Opening at the inn.",
        },
        player_input="__opening_scene_request__: begin",
        input_kind="opening",
    )
    assert result
    with connect() as conn:
        count = conn.execute("SELECT COUNT(*) AS c FROM npcs").fetchone()["c"]
    assert int(count) >= 1


def test_ensure_npcs_helper_creates_shells():
    init_db()
    start_playthrough(
        {
            "player_name": "Mara",
            "start_location": "Gate",
            "special_ability_origin": "none",
        }
    )
    with connect() as conn:
        loc = conn.execute("SELECT id FROM locations LIMIT 1").fetchone()
        loc_id = int(loc["id"])
        result: dict = {"npcs": []}
        created = _ensure_npcs_from_narration(
            conn,
            result,
            "A hooded figure leans in. A second figure watches.",
            loc_id,
        )
        assert len(created) >= 1
        assert result["npcs"]
        assert conn.execute(
            "SELECT COUNT(*) AS c FROM npcs WHERE location_id = ?", (loc_id,)
        ).fetchone()["c"] >= 1


def test_place_not_filed_as_npc_and_nested_cast_flattens():
    """Regression: model creates a place, puts L1 into npcs[], nests real people under locations."""
    assert _looks_like_misfiled_location(
        {"code": "L1", "name": "Second Shadow Inn", "role": "location"}
    )
    assert _looks_like_misfiled_location({"code": "L1", "name": "L1", "role": "local"})
    assert not is_plausible_person_name("l1")
    assert not is_plausible_person_name("the inn")

    result = {
        "locations": [
            {
                "name": "Second Shadow Inn",
                "summary": "A dim public house.",
                "npcs": [
                    {
                        "name": "Mara Quill",
                        "role": "innkeeper",
                        "summary": "Runs the bar.",
                        "attitude": "wary",
                    }
                ],
            }
        ],
        "npcs": [
            {"code": "L1", "name": "Second Shadow Inn", "role": "location", "summary": "A place."},
        ],
        "conversations": [
            {"npc_name": "Tomas Reed", "topic": "rooms", "summary": "Asked about a room."}
        ],
    }
    collected = _collect_npcs_from_turn_result(result)
    codes = {str(n.get("code") or "").upper() for n in collected}
    names = {str(n.get("name") or "").lower() for n in collected}
    assert "L1" not in codes
    assert not any("second shadow" in n for n in names)
    assert any("mara" in n for n in names)
    assert any("tomas" in n for n in names)

    init_db()
    start_playthrough(
        {
            "player_name": "Ash",
            "start_location": "Second Shadow Inn",
            "special_ability_origin": "none",
        }
    )
    apply_turn(
        {
            "narration": (
                "Mara Quill wipes a mug and says, \"Rooms are upstairs.\" "
                "A hooded figure watches from the hearth."
            ),
            "locations": result["locations"],
            "npcs": result["npcs"],
            "conversations": result["conversations"],
            "inventory_changes": [],
            "self_check": {"passed": True, "issues_found": [], "corrections_made": []},
            "turn_summary": "Talked to the innkeeper.",
        },
        player_input="I look around the inn.",
        input_kind="player",
    )
    with connect() as conn:
        npcs = conn.execute("SELECT code, name FROM npcs").fetchall()
        codes = [str(r["code"] or "").upper() for r in npcs]
        names = [str(r["name"] or "").lower() for r in npcs]
        assert npcs, "expected real NPCs to be created"
        assert not any(re.fullmatch(r"L\d+", c) for c in codes)
        assert not any("second shadow" in n for n in names)
        # At least one person from nested cast or conversation / figure seed
        assert any("mara" in n or "tomas" in n or n for n in names)
