"""
NPC-Player relationship system.

Each NPC has a relationship toward the player on three axes:
  - affinity:  -100 (Hatred) to +100 (Devoted)
  - fear:      0 to 100 (Terrified)
  - respect:   0 to 100 (Revered)

affinity bands:
  -100 to -61: Hostile
  -60  to -21: Unfriendly
  -20  to  20: Neutral
   21  to  60: Friendly
   61  to  90: Trusted
   91  to 100: Devoted
"""
from __future__ import annotations

from typing import Any

AFFINITY_BANDS = [
    (-100, -61, "Hostile"),
    (-60,  -21, "Unfriendly"),
    (-20,   20, "Neutral"),
    (21,    60, "Friendly"),
    (61,    90, "Trusted"),
    (91,   100, "Devoted"),
]

FEAR_BANDS = [
    (0,   20, "None"),
    (21,  50, "Wary"),
    (51,  80, "Afraid"),
    (81, 100, "Terrified"),
]

RESPECT_BANDS = [
    (0,   20, "Ignored"),
    (21,  50, "Acknowledged"),
    (51,  80, "Respected"),
    (81, 100, "Revered"),
]


def _band_name(value: int, bands: list[tuple[int, int, str]]) -> str:
    for lo, hi, label in bands:
        if lo <= value <= hi:
            return label
    return "Unknown"


def affinity_band(value: int) -> str:
    return _band_name(max(-100, min(100, value)), AFFINITY_BANDS)


def fear_band(value: int) -> str:
    return _band_name(max(0, min(100, value)), FEAR_BANDS)


def respect_band(value: int) -> str:
    return _band_name(max(0, min(100, value)), RESPECT_BANDS)


def get_or_create_relationship(conn, npc_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM npc_player_relationships WHERE npc_id = ?", (npc_id,)
    ).fetchone()
    if row:
        return dict(row)
    conn.execute(
        "INSERT OR IGNORE INTO npc_player_relationships (npc_id) VALUES (?)",
        (npc_id,),
    )
    row = conn.execute(
        "SELECT * FROM npc_player_relationships WHERE npc_id = ?", (npc_id,)
    ).fetchone()
    return dict(row) if row else {"npc_id": npc_id, "affinity": 0, "fear": 0, "respect": 0}


def update_relationship(
    conn,
    npc_id: int,
    *,
    affinity_delta: int = 0,
    fear_delta: int = 0,
    respect_delta: int = 0,
    reason: str = "",
) -> dict[str, Any]:
    """Apply delta changes to an NPC's relationship toward the player."""
    rel = get_or_create_relationship(conn, npc_id)
    new_affinity = max(-100, min(100, int(rel["affinity"]) + affinity_delta))
    new_fear = max(0, min(100, int(rel["fear"]) + fear_delta))
    new_respect = max(0, min(100, int(rel["respect"]) + respect_delta))
    conn.execute(
        """
        UPDATE npc_player_relationships
        SET affinity = ?, fear = ?, respect = ?,
            last_interaction = ?,
            interaction_count = interaction_count + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE npc_id = ?
        """,
        (new_affinity, new_fear, new_respect, str(reason), npc_id),
    )

    # Auto-seed hidden private feelings when affinity swings significantly.
    # Uses the psychology module; fails silently so relationship updates are never blocked.
    if abs(affinity_delta) > 20:
        try:
            from app.npc_psychology import auto_seed_feeling_from_affinity

            turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
            current_turn = int(turn_row["value"]) if turn_row else 0
            auto_seed_feeling_from_affinity(
                conn, npc_id,
                affinity_delta=affinity_delta,
                new_affinity=new_affinity,
                reason=str(reason)[:300],
                turn=current_turn,
            )
        except Exception:
            pass  # psychology layer must never block relationship updates

    return {
        "npc_id": npc_id,
        "affinity": new_affinity,
        "fear": new_fear,
        "respect": new_respect,
        "affinity_band": affinity_band(new_affinity),
        "fear_band": fear_band(new_fear),
        "respect_band": respect_band(new_respect),
    }


def get_relationship_summary(conn, npc_id: int) -> dict[str, Any]:
    rel = get_or_create_relationship(conn, npc_id)
    a = int(rel.get("affinity", 0))
    f = int(rel.get("fear", 0))
    r = int(rel.get("respect", 0))
    return {
        "npc_id": npc_id,
        "affinity": a,
        "fear": f,
        "respect": r,
        "affinity_band": affinity_band(a),
        "fear_band": fear_band(f),
        "respect_band": respect_band(r),
        "last_interaction": rel.get("last_interaction", ""),
        "interaction_count": int(rel.get("interaction_count", 0)),
    }


def all_relationships_for_llm(conn) -> list[dict[str, Any]]:
    """All NPCs with non-default relationships, for LLM context injection."""
    try:
        rows = conn.execute(
            """
            SELECT r.*, n.name as npc_name, n.code as npc_code
            FROM npc_player_relationships r
            JOIN npcs n ON n.id = r.npc_id
            WHERE r.affinity != 0 OR r.fear != 0 OR r.respect != 0
            ORDER BY ABS(r.affinity) DESC
            LIMIT 20
            """,
        ).fetchall()
    except Exception:
        return []
    result = []
    for row in rows:
        d = dict(row)
        a = int(d.get("affinity", 0))
        f = int(d.get("fear", 0))
        r_val = int(d.get("respect", 0))
        result.append({
            "npc_id": int(d.get("npc_id") or 0),
            "npc_code": d.get("npc_code"),
            "npc_name": d.get("npc_name"),
            "affinity": a,
            "affinity_band": affinity_band(a),
            "fear": f,
            "fear_band": fear_band(f),
            "respect": r_val,
            "respect_band": respect_band(r_val),
        })
    return result


# Preset relationship deltas for common events
RELATIONSHIP_EVENTS = {
    "attacked_npc": {"affinity_delta": -30, "fear_delta": +20, "respect_delta": -5},
    "helped_npc": {"affinity_delta": +15, "fear_delta": 0, "respect_delta": +10},
    "traded_npc": {"affinity_delta": +5, "fear_delta": 0, "respect_delta": +3},
    "ignored_npc": {"affinity_delta": -2, "fear_delta": 0, "respect_delta": -1},
    "quest_complete_for_npc": {"affinity_delta": +25, "fear_delta": 0, "respect_delta": +20},
    "quest_failed_for_npc": {"affinity_delta": -20, "fear_delta": 0, "respect_delta": -15},
    "intimidated_npc": {"affinity_delta": -10, "fear_delta": +30, "respect_delta": +5},
    "bribed_npc": {"affinity_delta": +8, "fear_delta": 0, "respect_delta": -5},
    "lied_to_npc_caught": {"affinity_delta": -15, "fear_delta": 0, "respect_delta": -10},
    "saved_npc_life": {"affinity_delta": +40, "fear_delta": 0, "respect_delta": +30},
    "killed_npc_friend": {"affinity_delta": -50, "fear_delta": +40, "respect_delta": -20},
}
