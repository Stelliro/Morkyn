"""
Party system for Mørkyn.

NPCs can join the player's travelling party when their affinity is Friendly+
(>= 40).  Party members assist in combat (flat damage bonus by rank / role),
have morale that drifts with events, and leave automatically when morale
reaches zero.

Table:
  party_members – tracks current party composition and per-member morale
"""
from __future__ import annotations

from typing import Any

from app.db import connect, rows_to_dicts, row_to_dict


# ---------------------------------------------------------------------------
# Combat contribution look-up
# ---------------------------------------------------------------------------

# Base bonus per role (added to a rank-scaled level bonus)
PARTY_ROLE_COMBAT_BONUS: dict[str, int] = {
    "companion": 3,
    "guard": 6,
    "guide": 1,
}

# NPC rank → rough level equivalent for bonus scaling
RANK_TO_LEVEL: dict[str, int] = {
    "F": 1, "E": 2, "D": 3, "C": 4, "B": 5,
    "A": 6, "S": 7, "SS": 8, "SSS": 9,
}


# ---------------------------------------------------------------------------
# DB initialisation (called from app.db._migrate_columns)
# ---------------------------------------------------------------------------

def init_party(conn) -> None:
    """Create the party_members table. Safe to call multiple times."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS party_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            npc_id INTEGER NOT NULL UNIQUE,
            npc_name TEXT NOT NULL DEFAULT '',
            joined_turn INTEGER NOT NULL DEFAULT 0,
            role TEXT NOT NULL DEFAULT 'companion',
            morale INTEGER NOT NULL DEFAULT 50,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (npc_id) REFERENCES npcs(id) ON DELETE CASCADE
        );
    """)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tables(conn) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _current_turn(conn) -> int:
    row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
    return int(row["value"] or 0) if row else 0


def _combat_bonus_for_member(rank: str, role: str) -> int:
    level = RANK_TO_LEVEL.get(str(rank or "F").upper(), 1)
    base = PARTY_ROLE_COMBAT_BONUS.get(str(role or "companion"), 3)
    return base + (level - 1)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_party(conn=None) -> list[dict[str, Any]]:
    """Return current party members with morale and derived combat bonus."""
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        if "party_members" not in _tables(conn):
            return []
        rows = rows_to_dicts(
            conn.execute(
                """
                SELECT pm.id, pm.npc_id, pm.npc_name, pm.joined_turn, pm.role, pm.morale,
                       n.rank, n.race, n.attitude,
                       l.name AS location_name, l.code AS location_code
                FROM party_members pm
                JOIN npcs n ON n.id = pm.npc_id
                LEFT JOIN locations l ON l.id = n.location_id
                ORDER BY pm.joined_turn ASC
                """
            ).fetchall()
        )
        result = []
        for row in rows:
            rank = str(row.get("rank") or "F")
            role = str(row.get("role") or "companion")
            result.append({
                "id": int(row["id"]),
                "npc_id": int(row["npc_id"]),
                "npc_name": str(row["npc_name"] or ""),
                "joined_turn": int(row["joined_turn"] or 0),
                "role": role,
                "morale": int(row["morale"] or 50),
                "rank": rank,
                "level_equiv": RANK_TO_LEVEL.get(rank, 1),
                "combat_bonus": _combat_bonus_for_member(rank, role),
                "location_name": str(row.get("location_name") or ""),
                "location_code": str(row.get("location_code") or ""),
            })
        return result
    finally:
        if close:
            conn.close()


def invite_npc_to_party(npc_id: int, role: str = "companion", conn=None) -> dict[str, Any]:
    """
    Invite an NPC to the party.  Requires affinity >= 40 (Friendly band).
    Returns {"ok": True, ...} or {"ok": False, "error": "..."}.
    """
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        init_party(conn)  # ensure table exists

        npc_row = row_to_dict(
            conn.execute("SELECT id, name, rank FROM npcs WHERE id = ?", (npc_id,)).fetchone()
        )
        if not npc_row:
            return {"ok": False, "error": f"NPC {npc_id} not found"}

        npc_name = str(npc_row["name"] or "")

        # Already in party?
        if conn.execute(
            "SELECT 1 FROM party_members WHERE npc_id = ?", (npc_id,)
        ).fetchone():
            return {"ok": False, "error": f"{npc_name} is already in your party"}

        # Affinity check
        rel = conn.execute(
            "SELECT affinity FROM npc_player_relationships WHERE npc_id = ?", (npc_id,)
        ).fetchone()
        affinity = int(rel["affinity"] or 0) if rel else 0
        if affinity < 40:
            try:
                from app.relationships import affinity_band
                band = affinity_band(affinity)
            except Exception:
                band = "unknown"
            return {
                "ok": False,
                "error": (
                    f"{npc_name} won't join — affinity is {band} ({affinity}). "
                    "Reach Friendly (40+) first."
                ),
                "affinity": affinity,
                "required": 40,
            }

        valid_roles = {"companion", "guard", "guide"}
        safe_role = role if role in valid_roles else "companion"
        turn = _current_turn(conn)

        conn.execute(
            """
            INSERT INTO party_members (npc_id, npc_name, joined_turn, role, morale)
            VALUES (?, ?, ?, ?, 50)
            """,
            (npc_id, npc_name, turn, safe_role),
        )
        return {
            "ok": True,
            "npc_id": npc_id,
            "npc_name": npc_name,
            "role": safe_role,
            "joined_turn": turn,
        }
    finally:
        if close:
            conn.close()


def sync_scene_companions(conn, companions: list[dict[str, Any]], narration: str, turn: int) -> dict[str, list[str]]:
    """Keep the party in step with who the scene shows travelling with the player.

    Playtest #51 (live, all four A/B games): "Mira, come with me" put Mira on
    the scene thread's ``with`` list and moved her along, but party_members,
    which the Party tab, party_combat_bonus and morale read, was only ever
    filled by the manual invite button. An invitation the prose shows accepted
    is a join; the engine decides, so the button's affinity gate does not
    apply to it. Someone the prose shows staying behind, and whom the move
    really left at another place, leaves without the dismissal penalty.
    """
    out: dict[str, list[str]] = {"joined": [], "left": []}
    try:
        if "party_members" not in _tables(conn):
            init_party(conn)
    except Exception:
        return out
    from app.scene_thread import left_behind

    stayed = left_behind(narration)
    here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    here_id = int((here[0] if here else 0) or 0)
    for member in rows_to_dicts(
        conn.execute(
            "SELECT pm.npc_id, pm.npc_name, n.name AS name, n.location_id AS location_id "
            "FROM party_members pm LEFT JOIN npcs n ON n.id = pm.npc_id"
        ).fetchall()
    ):
        name = str(member.get("name") or member.get("npc_name") or "")
        if name and stayed(name) and here_id and int(member.get("location_id") or 0) != here_id:
            conn.execute("DELETE FROM party_members WHERE npc_id = ?", (int(member["npc_id"]),))
            out["left"].append(name)
    for person in companions or []:
        if not isinstance(person, dict):
            continue
        row = None
        if person.get("code"):
            row = conn.execute("SELECT id, name FROM npcs WHERE code = ?", (str(person["code"]),)).fetchone()
        if row is None and person.get("name"):
            row = conn.execute(
                "SELECT id, name FROM npcs WHERE name = ? COLLATE NOCASE LIMIT 1", (str(person["name"]),)
            ).fetchone()
        if row is None or str(row["name"]) in out["left"]:
            continue
        if stayed(str(row["name"])):
            continue
        if conn.execute("SELECT 1 FROM party_members WHERE npc_id = ?", (int(row["id"]),)).fetchone():
            continue
        conn.execute(
            "INSERT INTO party_members (npc_id, npc_name, joined_turn, role, morale) VALUES (?, ?, ?, 'companion', 50)",
            (int(row["id"]), str(row["name"]), int(turn or 0)),
        )
        out["joined"].append(str(row["name"]))
    return out


def remove_from_party(npc_id: int, reason: str = "dismissed", conn=None) -> dict[str, Any]:
    """
    Remove an NPC from the party.
    Applies an affinity penalty of −10 (narrative friction of parting ways).
    """
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        member = row_to_dict(
            conn.execute(
                "SELECT * FROM party_members WHERE npc_id = ?", (npc_id,)
            ).fetchone()
        )
        if not member:
            return {"ok": False, "error": "NPC is not in the party"}

        npc_name = str(member.get("npc_name") or "")
        conn.execute("DELETE FROM party_members WHERE npc_id = ?", (npc_id,))

        try:
            from app.relationships import update_relationship
            update_relationship(
                conn, npc_id,
                affinity_delta=-10,
                reason=f"Left party: {reason}",
            )
        except Exception:
            pass

        return {"ok": True, "npc_id": npc_id, "npc_name": npc_name, "reason": reason}
    finally:
        if close:
            conn.close()


def update_party_morale(delta: int, reason: str = "", conn=None) -> list[dict[str, Any]]:
    """
    Apply a morale delta to every party member, clamped to 0–100.
    Members whose morale reaches 0 are removed; a list of departed members
    is returned.
    """
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        if "party_members" not in _tables(conn):
            return []

        members = rows_to_dicts(
            conn.execute("SELECT npc_id, npc_name, morale FROM party_members").fetchall()
        )
        departed: list[dict[str, Any]] = []
        for member in members:
            npc_id = int(member["npc_id"])
            new_morale = max(0, min(100, int(member["morale"] or 50) + delta))
            if new_morale <= 0:
                remove_from_party(npc_id, reason=reason or "morale collapsed", conn=conn)
                departed.append({
                    "npc_id": npc_id,
                    "npc_name": member["npc_name"],
                    "reason": f"Morale collapsed: {reason or 'no reason given'}",
                })
            else:
                conn.execute(
                    "UPDATE party_members SET morale = ? WHERE npc_id = ?",
                    (new_morale, npc_id),
                )
        return departed
    finally:
        if close:
            conn.close()


def party_combat_bonus(conn=None) -> int:
    """
    Return the total flat combat damage bonus from party members.
    Members with morale == 0 contribute nothing (they are already removed by
    update_party_morale, but this is a safety guard).
    """
    members = get_party(conn=conn)
    total = 0
    for member in members:
        if int(member.get("morale") or 0) > 0:
            total += int(member.get("combat_bonus") or 0)
    return total


def tick_party_morale(turn_result: dict[str, Any] | None = None, conn=None) -> list[dict[str, Any]]:
    """
    Called at end of each turn.  Applies event-driven morale changes:
      - Quest completed this turn: +15
      - Player at < 25 % HP:       −10
      - Otherwise (idle drift):    −2

    Returns list of members who left due to morale collapse.
    """
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        if "party_members" not in _tables(conn):
            return []

        # No members → nothing to do
        if not conn.execute("SELECT 1 FROM party_members LIMIT 1").fetchone():
            return []

        delta = -2
        reason = "idle"

        # Quest completed check
        try:
            turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
            current_turn = int(turn_row["value"] or 0) if turn_row else 0
            q_row = conn.execute(
                "SELECT value FROM settings WHERE key = 'last_quest_completed_turn'"
            ).fetchone()
            if q_row and int(q_row["value"] or -1) == current_turn:
                delta = 13  # net +15 after idle offset already baked in
                reason = "quest completed"
        except Exception:
            pass

        # Player near death check (< 25 % HP)
        try:
            p_row = conn.execute("SELECT health, max_health FROM player WHERE id = 1").fetchone()
            if p_row:
                hp = int(p_row["health"] or 0)
                max_hp = max(1, int(p_row["max_health"] or 1))
                if hp / max_hp < 0.25:
                    delta -= 10
                    reason = "player near death"
        except Exception:
            pass

        return update_party_morale(delta, reason=reason, conn=conn)
    finally:
        if close:
            conn.close()
