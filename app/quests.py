"""
Quest / Objectives system for Morkyn.

Quests are chains of up to 6 location steps. Each quest has:
- title, description, reward (gold/XP/items)
- optional timer
- optional hidden sub-tasks revealed on arrival
- status: active | offered | completed | failed | abandoned | expired

Reward scales with length (steps) and difficulty.
"""
from __future__ import annotations

import json
from typing import Any

from app.db import connect


def _snap_to_settlement(location_name: str) -> dict[str, float] | None:
    """
    Return grid coords {"x": float, "y": float} if a settlement with a
    name matching *location_name* (case-insensitive) exists on the active map.
    Returns None if no map is loaded or no matching settlement is found.
    """
    if not location_name:
        return None
    try:
        from app.tile_world import get_map, list_settlements

        map_data = get_map()
        if not map_data:
            return None
        name_lower = location_name.strip().lower()
        for s in list_settlements(map_data):
            if str(s.get("name") or "").strip().lower() == name_lower:
                x = s.get("x")
                y = s.get("y")
                if x is not None and y is not None:
                    return {"x": float(x), "y": float(y)}
    except Exception:
        pass
    return None

DIFFICULTY_MULTIPLIERS = {
    "trivial": 0.5,
    "easy": 0.75,
    "normal": 1.0,
    "hard": 1.5,
    "deadly": 2.5,
}

BASE_REWARDS = {
    "gold_per_step": 15,
    "xp_per_step": 25,
}


def _quest_code(conn, quest_id: int) -> str:
    return f"Q{quest_id}"


def create_quest(
    conn,
    *,
    title: str,
    description: str = "",
    steps: list[dict[str, Any]],
    reward_gold: int | None = None,
    reward_xp: int | None = None,
    reward_items: list[str] | None = None,
    difficulty: str = "normal",
    timer_turns: int = 0,
    giver_npc_id: int | None = None,
    target_location_id: int | None = None,
    created_turn: int = 0,
    notes: str = "",
    status: str = "active",
) -> int:
    """Create a quest with its steps. Returns the quest id.

    ``offered`` is posted and not yet taken. Every older caller stays ``active``.
    """
    if not steps:
        raise ValueError("Quest must have at least one step")
    if len(steps) > 6:
        raise ValueError("Quest may have at most 6 steps")
    status = str(status or "active").strip().lower()
    if status not in {"active", "offered"}:
        status = "active"

    mult = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
    n_steps = len(steps)
    if reward_gold is None:
        reward_gold = int(BASE_REWARDS["gold_per_step"] * n_steps * mult)
    if reward_xp is None:
        reward_xp = int(BASE_REWARDS["xp_per_step"] * n_steps * mult)
    if reward_items is None:
        reward_items = []

    cur = conn.execute(
        """
        INSERT INTO quests
          (title, description, status, current_step, total_steps,
           reward_gold, reward_xp, reward_items, difficulty,
           timer_turns, turns_remaining, giver_npc_id, target_location_id,
           created_turn, notes)
        VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(title),
            str(description),
            status,
            int(n_steps),
            int(reward_gold),
            int(reward_xp),
            json.dumps(reward_items),
            str(difficulty),
            int(timer_turns),
            int(timer_turns),  # turns_remaining starts equal to timer
            giver_npc_id,
            target_location_id,
            int(created_turn),
            str(notes),
        ),
    )
    quest_id = int(cur.lastrowid)
    code = _quest_code(conn, quest_id)
    conn.execute("UPDATE quests SET code = ? WHERE id = ?", (code, quest_id))

    for i, step in enumerate(steps, 1):
        loc_name = str(step.get("location_name", "") or "")
        # Town snapping: if location_name matches a known settlement, use its coords
        loc_coords_raw = step.get("location_coords")
        if loc_name and loc_coords_raw is None:
            snapped = _snap_to_settlement(loc_name)
            if snapped is not None:
                loc_coords_raw = snapped
        loc_coords_str = json.dumps(loc_coords_raw) if loc_coords_raw else ""
        conn.execute(
            """
            INSERT INTO quest_steps
              (quest_id, step_number, title, description, location_code,
               location_name, location_coords,
               status, hidden, revealed_at_step, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                quest_id,
                i,
                str(step.get("title", f"Step {i}")),
                str(step.get("description", "")),
                str(step.get("location_code", "")),
                loc_name,
                loc_coords_str,
                "active" if i == 1 else "pending",
                1 if step.get("hidden", False) and i > 1 else 0,
                int(step.get("revealed_at_step", 0)),
                str(step.get("notes", "")),
            ),
        )
    return quest_id


def get_active_quests(conn) -> list[dict[str, Any]]:
    """Return all active quests with their steps."""
    return _quests_with_status(conn, "active")


def get_offered_quests(conn) -> list[dict[str, Any]]:
    """Offered (posted, not yet taken) quests with their steps and giver name."""
    quests = _quests_with_status(conn, "offered")
    for quest in quests:
        quest["giver_name"] = ""
        if quest.get("giver_npc_id"):
            row = conn.execute("SELECT name FROM npcs WHERE id = ?", (quest["giver_npc_id"],)).fetchone()
            quest["giver_name"] = str(row["name"] or "") if row else ""
    return quests


def pay_quest_completion(conn, quest_id: int, result: dict[str, Any]) -> None:
    """Pay gold/xp and credit the giver when ``result`` (from advance_quest_step) completed the quest."""
    if not result.get("completed"):
        return
    try:
        conn.execute(
            "UPDATE player SET gold = gold + ?, xp = xp + ? WHERE id = 1",
            (int(result.get("reward_gold") or 0), int(result.get("reward_xp") or 0)),
        )
    except Exception:
        pass
    try:
        quest_row = conn.execute("SELECT giver_npc_id FROM quests WHERE id = ?", (quest_id,)).fetchone()
        giver_npc_id = int(quest_row["giver_npc_id"]) if quest_row and quest_row["giver_npc_id"] else None
        if giver_npc_id:
            from app.relationships import RELATIONSHIP_EVENTS, update_relationship

            update_relationship(
                conn,
                giver_npc_id,
                reason=f"Player completed quest {quest_id}",
                **RELATIONSHIP_EVENTS["quest_complete_for_npc"],
            )
    except Exception:
        pass


def _quests_with_status(conn, status: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM quests WHERE status = ? ORDER BY created_turn DESC, id DESC", (status,)
    ).fetchall()
    result = []
    for row in rows:
        quest = dict(row)
        quest["reward_items"] = json.loads(quest.get("reward_items") or "[]")
        steps = conn.execute(
            "SELECT * FROM quest_steps WHERE quest_id = ? ORDER BY step_number",
            (quest["id"],),
        ).fetchall()
        visible_steps = []
        current = quest["current_step"]
        for s in steps:
            sd = dict(s)
            # Hide steps that are hidden and not yet revealed
            if sd["hidden"] and sd["step_number"] > current:
                rev_at = sd["revealed_at_step"]
                if rev_at == 0 or current < rev_at:
                    sd["description"] = "[Hidden — reveals on arrival]"
            visible_steps.append(sd)
        quest["steps"] = visible_steps
        result.append(quest)
    return result


def get_quest(conn, quest_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM quests WHERE id = ?", (quest_id,)).fetchone()
    if not row:
        return None
    quest = dict(row)
    quest["reward_items"] = json.loads(quest.get("reward_items") or "[]")
    steps = conn.execute(
        "SELECT * FROM quest_steps WHERE quest_id = ? ORDER BY step_number",
        (quest_id,),
    ).fetchall()
    quest["steps"] = [dict(s) for s in steps]
    return quest


def advance_quest_step(conn, quest_id: int, *, turn: int = 0) -> dict[str, Any]:
    """Mark current step complete and advance to next. Returns result dict."""
    quest = get_quest(conn, quest_id)
    if not quest:
        return {"ok": False, "error": "Quest not found"}
    if quest["status"] != "active":
        return {"ok": False, "error": f"Quest is {quest['status']}"}

    current = quest["current_step"]
    total = quest["total_steps"]

    # Mark current step done
    conn.execute(
        "UPDATE quest_steps SET status = 'completed', completed_turn = ? WHERE quest_id = ? AND step_number = ?",
        (int(turn), quest_id, current),
    )

    if current >= total:
        # Quest complete
        conn.execute(
            "UPDATE quests SET status = 'completed', completed_turn = ?, current_step = ? WHERE id = ?",
            (int(turn), total, quest_id),
        )
        return {
            "ok": True,
            "completed": True,
            "quest_id": quest_id,
            "reward_gold": quest["reward_gold"],
            "reward_xp": quest["reward_xp"],
            "reward_items": quest["reward_items"],
        }
    else:
        next_step = current + 1
        conn.execute(
            "UPDATE quests SET current_step = ? WHERE id = ?",
            (next_step, quest_id),
        )
        # Activate next step
        conn.execute(
            "UPDATE quest_steps SET status = 'active' WHERE quest_id = ? AND step_number = ?",
            (quest_id, next_step),
        )
        # Reveal any hidden steps that unlock at this step
        conn.execute(
            "UPDATE quest_steps SET hidden = 0 WHERE quest_id = ? AND revealed_at_step = ?",
            (quest_id, next_step),
        )
        return {"ok": True, "completed": False, "quest_id": quest_id, "next_step": next_step}


def fail_quest(conn, quest_id: int, *, turn: int = 0, reason: str = "") -> None:
    conn.execute(
        "UPDATE quests SET status = 'failed', failed_turn = ?, notes = ? WHERE id = ?",
        (int(turn), str(reason), quest_id),
    )


def tick_quest_timers(conn, *, turn: int = 0) -> list[int]:
    """Decrement timer for all timed active quests. Returns list of failed quest ids."""
    rows = conn.execute(
        "SELECT id, turns_remaining FROM quests WHERE status = 'active' AND timer_turns > 0"
    ).fetchall()
    failed = []
    for row in rows:
        remaining = int(row["turns_remaining"]) - 1
        if remaining <= 0:
            fail_quest(conn, int(row["id"]), turn=turn, reason="Time expired")
            failed.append(int(row["id"]))
        else:
            conn.execute(
                "UPDATE quests SET turns_remaining = ? WHERE id = ?",
                (remaining, int(row["id"])),
            )
    return failed


def seed_starter_quests(conn, *, turn: int = 0) -> None:
    """Add a few starter quests to seed the world. Idempotent."""
    try:
        from app.local_intel import _play_flag_on

        if not _play_flag_on(conn, "quests_enabled"):
            return
    except Exception:
        pass
    existing = conn.execute("SELECT COUNT(*) FROM quests").fetchone()[0]
    if existing > 0:
        return

    # Discover what towns actually exist on the map (if any) for snapping
    _town_names: list[str] = []
    try:
        from app.tile_world import get_map, list_settlements
        _md = get_map()
        if _md:
            _town_names = [
                str(s.get("name") or "")
                for s in list_settlements(_md)
                if s.get("name") and s.get("x") is not None and s.get("y") is not None
            ]
    except Exception:
        pass
    # Pick up to two town names for seeded quest destinations (falls back to
    # generic empty location_name when no map exists yet)
    _dest1 = _town_names[0] if len(_town_names) > 0 else ""
    _dest2 = _town_names[1] if len(_town_names) > 1 else _dest1

    # Quest 1: Simple delivery
    create_quest(
        conn,
        title="The Sealed Letter",
        description="A dying courier pressed a sealed letter into your hands. Find out who it is addressed to and deliver it.",
        steps=[
            {"title": "Read the letter", "description": "Examine the sealed letter to find the recipient's name.", "location_code": ""},
            {"title": "Find the recipient", "description": "Locate the person named on the letter.", "location_code": "", "location_name": _dest1},
            {"title": "Deliver the letter", "description": "Hand it over — and decide whether you mention the courier's fate.", "location_code": "", "location_name": _dest1},
        ],
        reward_gold=30,
        reward_xp=60,
        difficulty="easy",
        created_turn=turn,
    )

    # Quest 2: Investigation chain
    create_quest(
        conn,
        title="The Missing Grain",
        description="Half a shipment of grain has gone missing between the mill and the market. The miller blames the carter. The carter blames the miller.",
        steps=[
            {"title": "Talk to the miller", "description": "Get the miller's side of the story.", "location_code": "", "location_name": _dest1},
            {"title": "Talk to the carter", "description": "Get the carter's account. Note any contradictions.", "location_code": "", "location_name": _dest2},
            {"title": "Find the grain", "description": "Investigate what actually happened.", "location_code": "", "hidden": True, "revealed_at_step": 2},
            {"title": "Settle the dispute", "description": "Bring what you found back to the parties.", "location_code": "", "location_name": _dest1, "hidden": True, "revealed_at_step": 3},
        ],
        reward_gold=50,
        reward_xp=80,
        difficulty="normal",
        created_turn=turn,
    )

    # Quest 3: Timed urgent quest
    create_quest(
        conn,
        title="Before the Gate Closes",
        description="A traveller needs a specific herb from the market before the east gate closes at dusk. They cannot walk that far.",
        steps=[
            {"title": "Buy the herb", "description": "Find it at the apothecary or the market stalls.", "location_code": "", "location_name": _dest2},
            {"title": "Return before dusk", "description": "Deliver the herb before the gate closes.", "location_code": "", "location_name": _dest1},
        ],
        reward_gold=20,
        reward_xp=35,
        difficulty="easy",
        timer_turns=8,
        created_turn=turn,
    )


def quest_context_for_llm(conn) -> list[dict[str, Any]]:
    """Compact quest state for LLM injection."""
    try:
        quests = get_active_quests(conn)
    except Exception:
        return []
    out = []
    for q in quests:
        current_step = next((s for s in q["steps"] if s["step_number"] == q["current_step"]), None)
        entry: dict[str, Any] = {
            "code": q["code"],
            "title": q["title"],
            "status": q["status"],
            "current_step": q["current_step"],
            "total_steps": q["total_steps"],
            "reward": f"{q['reward_gold']}g / {q['reward_xp']}xp",
            "current_objective": current_step["description"] if current_step else "",
        }
        if q.get("turns_remaining", 0) > 0:
            entry["turns_remaining"] = q["turns_remaining"]
        out.append(entry)
    return out
