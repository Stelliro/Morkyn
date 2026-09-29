"""
Title system for Mørkyn.

Players (and, optionally, NPCs) can earn titles by meeting criteria that are
evaluated at the end of each turn.  Each title can carry small stat bonuses
that compound on top of equipment bonuses.

Tables (created / migrated in app.db):
  titles        – the catalogue of available titles
  entity_titles – which entities currently hold which titles

The system is toggled via the ``titles_enabled`` settings key (default on).
"""
from __future__ import annotations

import json
from typing import Any

from app.db import connect, rows_to_dicts, row_to_dict


# ---------------------------------------------------------------------------
# Catalogue – seeded once into the DB, idempotent
# ---------------------------------------------------------------------------

STARTER_TITLES: list[dict[str, str]] = [
    {
        "name": "Wanderer",
        "description": "One who has walked many roads and seen many lands.",
        "requirements_json": json.dumps({"type": "visit_locations", "count": 5}),
        "stat_bonuses_json": json.dumps({"dodge": 1}),
    },
    {
        "name": "Seeker",
        "description": "Ever pressing onward for what lies beyond the next horizon.",
        "requirements_json": json.dumps({"type": "visit_locations", "count": 10}),
        "stat_bonuses_json": json.dumps({"dodge": 2}),
    },
    {
        "name": "Dragonslayer",
        "description": "Slayer of dragonkind. A name that echoes in taverns for decades.",
        "requirements_json": json.dumps({"type": "kill_count_tag", "tag": "dragon", "count": 1}),
        "stat_bonuses_json": json.dumps({"strength": 3, "max_hp": 10}),
    },
    {
        "name": "Peacekeeper",
        "description": "Resolved conflicts rather than inflaming them. Disputes end around them.",
        "requirements_json": json.dumps({"type": "quests_completed_min", "count": 3}),
        "stat_bonuses_json": json.dumps({"defense": 1}),
    },
    {
        "name": "Beloved",
        "description": "Cherished by many; bonds run deep and loyalties stand firm.",
        "requirements_json": json.dumps({"type": "affinity_devoted_min", "count": 3}),
        "stat_bonuses_json": json.dumps({"max_hp": 15}),
    },
    {
        "name": "Ironborn",
        "description": "Survived ten consecutive combats without falling. Hardened by war.",
        "requirements_json": json.dumps({"type": "consecutive_combats_survived", "count": 10}),
        "stat_bonuses_json": json.dumps({"defense": 2, "max_hp": 20}),
    },
    {
        "name": "Kinslayer",
        "description": "Struck down kin of an ally. A dark mark that follows wherever they go.",
        "requirements_json": json.dumps({"type": "custom", "note": "killed an ally's family member"}),
        "stat_bonuses_json": json.dumps({"strength": 2}),
    },
    {
        "name": "Wealthy",
        "description": "Amassed considerable wealth through trade, plunder, or cunning.",
        "requirements_json": json.dumps({"type": "gold_min", "value": 500}),
        "stat_bonuses_json": json.dumps({}),
    },
    {
        "name": "Scourge",
        "description": "Feared by many — a name spoken in hushed tones at night.",
        "requirements_json": json.dumps({"type": "fear_terrified_min", "count": 3}),
        "stat_bonuses_json": json.dumps({"strength": 1, "defense": 1}),
    },
    {
        "name": "Luminary",
        "description": "A reputation for noble deeds shines far beyond the horizon.",
        "requirements_json": json.dumps({"type": "karma_above", "value": 50}),
        "stat_bonuses_json": json.dumps({"max_hp": 10}),
    },
    {
        "name": "Shadowborn",
        "description": "Moves through the margins of the world, unseen and unnoticed.",
        "requirements_json": json.dumps({"type": "karma_below", "value": -30}),
        "stat_bonuses_json": json.dumps({"dodge": 2}),
    },
    {
        "name": "Veteran",
        "description": "Has seen many battles and learned to endure what others cannot.",
        "requirements_json": json.dumps({"type": "total_combats_min", "count": 20}),
        "stat_bonuses_json": json.dumps({"defense": 1, "max_hp": 10}),
    },
    {
        "name": "Learned",
        "description": "Accumulated broad knowledge and skill across many disciplines.",
        "requirements_json": json.dumps({"type": "skills_count_min", "count": 5}),
        "stat_bonuses_json": json.dumps({}),
    },
    {
        "name": "Hermit",
        "description": "Walked alone through silence and solitude, self-reliant above all.",
        "requirements_json": json.dumps({"type": "custom", "note": "survived long without companions"}),
        "stat_bonuses_json": json.dumps({"dodge": 1, "defense": 1}),
    },
    {
        "name": "Revered",
        "description": "Has earned the deep respect of many across the land.",
        "requirements_json": json.dumps({"type": "respect_revered_min", "count": 3}),
        "stat_bonuses_json": json.dumps({"max_hp": 5, "defense": 1}),
    },
]


# ---------------------------------------------------------------------------
# DB initialisation (called from app.db._migrate_columns)
# ---------------------------------------------------------------------------

def init_titles(conn) -> None:
    """Create title tables and seed the catalogue. Safe to call multiple times."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            requirements_json TEXT NOT NULL DEFAULT '{}',
            stat_bonuses_json TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS entity_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id INTEGER NOT NULL,
            entity_type TEXT NOT NULL DEFAULT 'player',
            title_id INTEGER NOT NULL,
            acquired_turn INTEGER NOT NULL DEFAULT 0,
            is_hidden INTEGER NOT NULL DEFAULT 0,
            UNIQUE(entity_id, entity_type, title_id),
            FOREIGN KEY (title_id) REFERENCES titles(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_entity_titles_entity
        ON entity_titles(entity_id, entity_type);
    """)
    for title in STARTER_TITLES:
        conn.execute(
            """
            INSERT OR IGNORE INTO titles (name, description, requirements_json, stat_bonuses_json)
            VALUES (?, ?, ?, ?)
            """,
            (title["name"], title["description"], title["requirements_json"], title["stat_bonuses_json"]),
        )


# ---------------------------------------------------------------------------
# Requirement evaluation
# ---------------------------------------------------------------------------

def _check_requirement(req: dict[str, Any], conn) -> bool:
    """Evaluate a single requirement dict against live DB state."""
    req_type = str(req.get("type") or "")
    try:
        if req_type == "visit_locations":
            count = int(req.get("count", 5))
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM locations WHERE visit_count > 0"
            ).fetchone()
            return int(row["c"] or 0) >= count

        if req_type == "affinity_devoted_min":
            # Devoted band: affinity >= 91
            count = int(req.get("count", 3))
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM npc_player_relationships WHERE affinity >= 91"
            ).fetchone()
            return int(row["c"] or 0) >= count

        if req_type == "respect_revered_min":
            # Revered band: respect >= 81
            count = int(req.get("count", 3))
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM npc_player_relationships WHERE respect >= 81"
            ).fetchone()
            return int(row["c"] or 0) >= count

        if req_type == "quests_completed_min":
            count = int(req.get("count", 3))
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM quests WHERE status = 'completed'"
                ).fetchone()
                return int(row["c"] or 0) >= count
            except Exception:
                return False

        if req_type == "gold_min":
            value = int(req.get("value", 500))
            row = conn.execute("SELECT gold FROM player WHERE id = 1").fetchone()
            return int(row["gold"] or 0) >= value if row else False

        if req_type == "karma_above":
            value = int(req.get("value", 50))
            row = conn.execute("SELECT karma FROM player WHERE id = 1").fetchone()
            return int(row["karma"] or 0) >= value if row else False

        if req_type == "karma_below":
            value = int(req.get("value", -30))
            row = conn.execute("SELECT karma FROM player WHERE id = 1").fetchone()
            return int(row["karma"] or 0) <= value if row else False

        if req_type == "consecutive_combats_survived":
            count = int(req.get("count", 10))
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'consecutive_combats_survived'"
            ).fetchone()
            stored = int(row["value"] or 0) if row else 0
            return stored >= count

        if req_type == "total_combats_min":
            count = int(req.get("count", 20))
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'total_combats_count'"
            ).fetchone()
            stored = int(row["value"] or 0) if row else 0
            return stored >= count

        if req_type == "skills_count_min":
            count = int(req.get("count", 5))
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM player_skills WHERE value > 0"
            ).fetchone()
            return int(row["c"] or 0) >= count

        if req_type == "fear_terrified_min":
            # Terrified band: fear >= 81
            count = int(req.get("count", 3))
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM npc_player_relationships WHERE fear >= 81"
            ).fetchone()
            return int(row["c"] or 0) >= count

        if req_type == "kill_count_tag":
            tag = str(req.get("tag", "dragon")).lower().strip()
            count = int(req.get("count", 1))
            key = f"kill_count_{tag}"
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            stored = int(row["value"] or 0) if row else 0
            return stored >= count

        # "custom" titles are GM-assigned only; never auto-awarded
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_and_award_titles(
    entity_id: int,
    entity_type: str,
    conn=None,
) -> list[dict[str, Any]]:
    """
    Evaluate all active titles against current world state.
    Awards any newly-earned titles and returns the list of newly awarded ones.

    Only auto-evaluates for entity_type == 'player'; NPC titles must be
    assigned manually via award_title_to_entity.
    """
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        # Guard: table may not exist on very first run (before init_db completes)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "titles" not in tables or "entity_titles" not in tables:
            return []

        # Respect the opt-out setting
        row = conn.execute("SELECT value FROM settings WHERE key = 'titles_enabled'").fetchone()
        if row and str(row["value"]).strip().lower() in {"false", "0", "off"}:
            return []

        # Only auto-award to the player
        if entity_type != "player":
            return []

        titles = rows_to_dicts(
            conn.execute("SELECT * FROM titles WHERE is_active = 1").fetchall()
        )
        already_have = {
            int(r["title_id"])
            for r in conn.execute(
                "SELECT title_id FROM entity_titles WHERE entity_id = ? AND entity_type = ?",
                (entity_id, entity_type),
            ).fetchall()
        }

        turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        current_turn = int(turn_row["value"] or 0) if turn_row else 0

        newly_awarded: list[dict[str, Any]] = []
        for title in titles:
            if int(title["id"]) in already_have:
                continue
            try:
                req = json.loads(title["requirements_json"] or "{}")
            except Exception:
                continue
            if req.get("type") == "custom":
                continue
            if _check_requirement(req, conn):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO entity_titles
                      (entity_id, entity_type, title_id, acquired_turn, is_hidden)
                    VALUES (?, ?, ?, ?, 0)
                    """,
                    (entity_id, entity_type, int(title["id"]), current_turn),
                )
                try:
                    bonuses = json.loads(title["stat_bonuses_json"] or "{}")
                except Exception:
                    bonuses = {}
                newly_awarded.append({
                    "title_id": int(title["id"]),
                    "name": title["name"],
                    "description": title["description"],
                    "stat_bonuses": bonuses,
                    "acquired_turn": current_turn,
                })
        return newly_awarded
    finally:
        if close:
            conn.close()


def get_entity_titles(
    entity_id: int,
    entity_type: str,
    include_hidden: bool = False,
    conn=None,
) -> list[dict[str, Any]]:
    """Return all earned titles for an entity, enriched with stat bonuses."""
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "titles" not in tables or "entity_titles" not in tables:
            return []
        hidden_clause = "" if include_hidden else "AND et.is_hidden = 0"
        rows = rows_to_dicts(
            conn.execute(
                f"""
                SELECT t.id, t.name, t.description, t.stat_bonuses_json,
                       et.acquired_turn, et.is_hidden
                FROM entity_titles et
                JOIN titles t ON t.id = et.title_id
                WHERE et.entity_id = ? AND et.entity_type = ?
                {hidden_clause}
                ORDER BY et.acquired_turn ASC, t.id ASC
                """,
                (entity_id, entity_type),
            ).fetchall()
        )
        result = []
        for row in rows:
            try:
                bonuses = json.loads(row["stat_bonuses_json"] or "{}")
            except Exception:
                bonuses = {}
            result.append({
                "id": int(row["id"]),
                "name": row["name"],
                "description": row["description"],
                "stat_bonuses": bonuses,
                "acquired_turn": int(row["acquired_turn"] or 0),
                "is_hidden": bool(row["is_hidden"]),
            })
        return result
    finally:
        if close:
            conn.close()


def get_all_titles(conn=None) -> list[dict[str, Any]]:
    """Return the full title catalogue (for reference display)."""
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "titles" not in tables:
            return []
        rows = rows_to_dicts(
            conn.execute("SELECT * FROM titles ORDER BY id").fetchall()
        )
        result = []
        for row in rows:
            try:
                req = json.loads(row["requirements_json"] or "{}")
            except Exception:
                req = {}
            try:
                bonuses = json.loads(row["stat_bonuses_json"] or "{}")
            except Exception:
                bonuses = {}
            result.append({
                "id": int(row["id"]),
                "name": row["name"],
                "description": row["description"],
                "requirements": req,
                "stat_bonuses": bonuses,
                "is_active": bool(row["is_active"]),
            })
        return result
    finally:
        if close:
            conn.close()


def title_stat_bonuses_for_player(conn=None) -> dict[str, int]:
    """Aggregate all active title stat bonuses for the player (entity_id=1)."""
    titles = get_entity_titles(1, "player", include_hidden=False, conn=conn)
    bonuses: dict[str, int] = {}
    for t in titles:
        for stat, val in (t.get("stat_bonuses") or {}).items():
            try:
                bonuses[stat] = bonuses.get(stat, 0) + int(val)
            except (TypeError, ValueError):
                pass
    return bonuses


def award_title_to_entity(
    entity_id: int,
    entity_type: str,
    title_name: str,
    is_hidden: bool = False,
    conn=None,
) -> dict[str, Any]:
    """Manually award a title by name (for GM use or NPC assignment)."""
    close = False
    if conn is None:
        conn = connect()
        close = True
    try:
        title_row = row_to_dict(
            conn.execute("SELECT * FROM titles WHERE name = ?", (title_name,)).fetchone()
        )
        if not title_row:
            return {"ok": False, "error": f"Title '{title_name}' not found"}
        turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        current_turn = int(turn_row["value"] or 0) if turn_row else 0
        conn.execute(
            """
            INSERT OR IGNORE INTO entity_titles
              (entity_id, entity_type, title_id, acquired_turn, is_hidden)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_id, entity_type, int(title_row["id"]), current_turn, 1 if is_hidden else 0),
        )
        return {"ok": True, "title": title_name, "entity_id": entity_id, "entity_type": entity_type}
    finally:
        if close:
            conn.close()
