"""HIM audit regression checks (no LLM)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.db import init_db, connect
    from app.world import (
        _filter_inventory_changes,
        queue_quest_stage_event,
        consume_due_world_events,
        list_due_world_events,
        resolve_world_event,
        queue_world_event,
        _current_turn_number,
    )
    from app.llm import generate_ambient_move_line, ambient_llm_enabled

    init_db()

    with connect() as c:
        kept = _filter_inventory_changes(
            c,
            [{"name": "God Sword", "quantity_delta": 1, "justified": True, "source": "loot"}],
            narration="Nothing happens.",
            player_input="I wait",
        )
        assert kept == [], kept
        kept2 = _filter_inventory_changes(
            c,
            [{"name": "God Sword", "quantity_delta": 1, "source": "loot"}],
            narration="You loot a God Sword from the chest.",
            player_input="I loot the chest",
        )
        assert len(kept2) == 1, kept2
        kept3 = _filter_inventory_changes(
            c,
            [{"name": "rusty nail", "quantity_delta": 500}],
            narration="You find a rusty nail.",
            player_input="I search",
        )
        assert kept3 and kept3[0]["quantity_delta"] == 99, kept3
        kept4 = _filter_inventory_changes(
            c,
            [{"name": "Blade of Infinite Truths", "quantity_delta": 1}],
            narration="Hard truths surface in the quiet.",
            player_input="I think",
        )
        assert kept4 == [], kept4
        print("inventory filter hardened: ok")

    with connect() as c:
        c.execute(
            "UPDATE gm_events SET status='cancelled' WHERE status IN ('pending','active','seeded','')"
        )

    turn = _current_turn_number()
    e1 = queue_world_event(
        kind="quest_force",
        summary="A",
        force=True,
        due_turn=turn,
        priority=9,
        payload={"stage_id": "a", "replace_turn": True},
    )
    e2 = queue_world_event(
        kind="quest_force",
        summary="B",
        force=True,
        due_turn=turn,
        priority=8,
        payload={"stage_id": "b", "replace_turn": True},
    )
    due = consume_due_world_events(force_only=True, limit=1)
    assert len(due) == 1, due
    left = list_due_world_events(force_only=True, limit=5, include_active=False)
    assert any(x.get("id") == e2.get("id") for x in left), (left, e2)
    resolve_world_event(int(due[0]["id"]))
    due2 = consume_due_world_events(force_only=True, limit=1)
    assert len(due2) == 1 and due2[0].get("id") == e2.get("id"), due2
    print("force consume single: ok")

    assert generate_ambient_move_line("Bootfalls find packed road.", settings={}) == "Bootfalls find packed road."
    assert ambient_llm_enabled(None) is False
    print("ambient: ok")

    ev = queue_quest_stage_event("him_force_check", force=True, summary="Portal")
    with connect() as c:
        row = c.execute("SELECT payload FROM gm_events WHERE id=?", (ev["id"],)).fetchone()
        pl = json.loads(row["payload"] or "{}")
        assert pl.get("replace_turn") is True and pl.get("immutable") is True, pl
    print("quest stage replace flags: ok")

    # Pass 2: new NPC shells + no apex spawn + capacity dimensional reject
    from app.world import _upsert_npc, _apply_inventory_capacity_modifiers, _apply_skills

    with connect() as c:
        # Ensure location
        row = c.execute("SELECT id FROM locations LIMIT 1").fetchone()
        if not row:
            c.execute(
                "INSERT INTO locations (code, name, summary, visit_count) VALUES ('L_him','HimLoc','t',0)"
            )
            loc_id = int(c.execute("SELECT last_insert_rowid()").fetchone()[0])
            loc_name = "HimLoc"
        else:
            loc_id = int(row["id"])
            loc_name = c.execute("SELECT name FROM locations WHERE id=?", (loc_id,)).fetchone()["name"]
        # Unique names each run so we always exercise CREATE path (not update of residue)
        import time

        stamp = int(time.time() * 1000) % 1_000_000
        shell_name = f"Crowd Face Him {stamp}"
        apex_name = f"Apex Him {stamp}"
        nid = _upsert_npc(
            c,
            {
                "name": shell_name,
                "location": loc_name,
                "role": "passerby",
                "rank": "SSS",
                "summary": "Should be shell",
                "stat_profile": {"strength": "SSS"},
            },
        )
        assert nid
        n = c.execute("SELECT shell, presence, rank, power_rank FROM npcs WHERE id=?", (nid,)).fetchone()
        assert int(n["shell"] or 0) == 1, dict(n)
        assert str(n["presence"]) in {"nameless", "background"}, dict(n)
        assert str(n["rank"]) == "F", dict(n)
        print("shell create passerby: ok")

        nid2 = _upsert_npc(
            c,
            {
                "name": apex_name,
                "location": loc_name,
                "role": "guild captain",
                "rank": "SSS",
                "summary": "New full contact",
            },
        )
        n2 = c.execute("SELECT shell, rank FROM npcs WHERE id=?", (nid2,)).fetchone()
        assert int(n2["shell"] or 0) == 0, dict(n2)
        assert str(n2["rank"]) == "C", dict(n2)
        print("apex demote on create: ok")

        # Code allocator must not collide when max(id) codes already exist
        for i in range(3):
            nid_extra = _upsert_npc(
                c,
                {
                    "name": f"Code Probe {stamp}-{i}",
                    "location": loc_name,
                    "role": "local",
                    "rank": "D",
                    "summary": "code alloc",
                },
            )
            assert nid_extra
        print("npc code alloc: ok")

        _apply_inventory_capacity_modifiers(
            c,
            [{"source": "Free Void", "dimensional_space": True, "slot_bonus": 9999, "weight_bonus": 9999}],
        )
        m = c.execute(
            "SELECT dimensional_space, slot_bonus FROM inventory_capacity_modifiers WHERE source=?",
            ("Free Void",),
        ).fetchone()
        assert m is None or int(m["dimensional_space"] or 0) == 0, m
        print("capacity dimensional reject: ok")

        skill_name = f"godmode skill {stamp}"
        _apply_skills(c, [{"name": skill_name, "delta": 100}])
        # COLLATE NOCASE: `_apply_skills` stores a display name now, so
        # "godmode skill 1234" comes back as "Godmode Skill 1234". This lock is
        # about the value cap, not the spelling -- keep the assertion, widen the
        # lookup. The row must still exist; a missing one is a real failure.
        sk = c.execute(
            "SELECT value FROM player_skills WHERE name=? COLLATE NOCASE", (skill_name,)
        ).fetchone()
        assert sk is not None, f"skill row missing for {skill_name!r}"
        assert int(sk["value"]) <= 15, dict(sk)
        print("skill mint cap: ok")

    print("him_audit_checks: ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
