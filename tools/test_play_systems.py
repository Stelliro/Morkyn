"""Lightweight regression for clock/weather/wait/rep/events (no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.db import init_db, connect
    from app.world import (
        init_world_clock,
        get_world_time,
        normalize_wait_minutes,
        estimate_action_minutes,
        _filter_inventory_changes,
        ensure_settlement_ruler,
        apply_social_association_penalty,
        get_area_reputation,
        build_ambient_move_line,
        queue_quest_stage_event,
        get_quest_stages,
        cancel_world_event,
        list_pending_world_events,
        _time_of_day_crowd_mods,
        _local_crowd_danger,
    )
    from app.llm import _sanitize_setup_randomization_values, ambient_llm_enabled, generate_ambient_move_line
    from app.tile_world import walk_minutes_for_step, mark_hidden_base_discovered, generate_map

    init_db()
    with connect() as c:
        init_world_clock(c, epoch_label="Test Era")
        assert "Test Era" in get_world_time(c)["label"]
        assert normalize_wait_minutes(-1, c) >= 1
        assert estimate_action_minutes("I talk to her") == 5
        assert walk_minutes_for_step({"state": "road"}, {"state": "road"}) < walk_minutes_for_step(
            {"state": "road"}, {"state": "forest"}
        )
        # Ensure a location exists
        row = c.execute("SELECT id FROM locations LIMIT 1").fetchone()
        if not row:
            c.execute(
                "INSERT INTO locations (code, name, summary, visit_count) VALUES ('L1','Test','t',0)"
            )
            loc_id = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
        else:
            loc_id = int(row["id"])
        # Unique id each run so first-visit seed always builds hierarchy
        sid = f"Stest_{loc_id}_{int(__import__('time').time()) % 100000}"
        r = ensure_settlement_ruler(
            c, location_id=loc_id, settlement={"id": sid, "state": "city", "ruler_power_rank": 80}
        )
        assert r and len(r.get("hierarchy") or []) >= 3
        kept = _filter_inventory_changes(
            c,
            [{"name": "God Sword", "quantity_delta": 1}],
            narration="Nothing happens.",
            player_input="I wait",
        )
        assert kept == []

    s = _sanitize_setup_randomization_values(
        {"leveling_system": "Subtle blue-window system", "magic_level": "magic prevalence only"}
    )
    assert s["leveling_system"] is False
    assert s["magic_level"] == "rare"

    # n5: market day busier than night in settlements
    market = _time_of_day_crowd_mods(11, settlement_like=True, market_like=True)
    night = _time_of_day_crowd_mods(2, settlement_like=True, market_like=False)
    assert market["band"] == "market"
    assert night["band"] == "night"
    assert market["crowd_mul"] > night["crowd_mul"]
    assert night["danger_mul"] >= market["danger_mul"]
    night_cd = _local_crowd_danger({"world_time": {"hour": 2}, "current_location": {"name": "Market square"}})
    day_cd = _local_crowd_danger({"world_time": {"hour": 11}, "current_location": {"name": "Market square"}})
    assert day_cd["crowd"] > night_cd["crowd"]
    assert night_cd.get("time_band") == "night"

    # g3: ambient LLM off by default; template still builds
    assert ambient_llm_enabled(None) is False
    assert ambient_llm_enabled({}) is False
    assert ambient_llm_enabled({"ambient_llm": True}) is True
    ambient = build_ambient_move_line(
        travel={"terrain": "road", "from_terrain": "forest", "minutes": 12},
        travel_result={},
        weather={"kind": "rain", "label": "Light rain"},
    )
    assert ambient
    # When disabled, polish returns the template unchanged (no model call)
    assert generate_ambient_move_line(ambient, travel={"terrain": "road"}, settings={}) == ambient

    # n7: quest stage mark + list + cancel
    ev = queue_quest_stage_event("test_portal", kind="quest_portal", summary="A portal hums open.", due_in_turns=1)
    assert ev and (ev.get("id") or ev.get("kind"))
    q = get_quest_stages()
    assert any(s.get("stage_id") == "test_portal" for s in (q.get("stages") or []))
    pending = list_pending_world_events(limit=20)
    assert any(str(p.get("kind") or "").startswith("quest") for p in pending)
    eid = int(ev.get("id") or 0)
    if eid:
        assert cancel_world_event(eid) is True

    m = generate_map(seed=1, assign_images=False)
    assert (m.get("settlements_meta") or m.get("stats")) is not None
    print("test_play_systems: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
