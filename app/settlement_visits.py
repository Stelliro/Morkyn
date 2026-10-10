"""Settlement visit journal: first visit, last visit, count, and the seeding proposal.

Status: built, not wired (TODO g8).

One row per settlement id (board "S3" or world city "C7") in the module's own table settlement_visits.
record_enter() is the one writer: it upserts the row and returns whether this was a first visit, the row,
a proposed journal line and, while no ruler exists yet (a first visit, or a later one whose seeding never
ran), a seeding proposal listing the ruler, two officers and two workers with roles and power ranks. It
never inserts npcs, never writes settings and never writes journal; the existing ensure_settlement_ruler
(app/world.py) stays the one seeder. Re-entry within REENTRY_GRACE_MINUTES of the last visit on the same
turn (stepping between cells of one city) is not a new visit. The live game does not call this module.

Wiring (not done):
  app/world.py:apply_map_travel_step() (after _spend_travel, where settlement and loc_id are known) ->
      visit = settlement_visits.enter_from_travel(conn, travel, location_id=loc_id, turn=_turn_value(conn),
      world_time=(out.get("time") or {}).get("after")); then out["visit"] = visit, the journal INSERT from
      visit["journal"], and ensure_settlement_ruler only when visit["seed"] is not None (today it runs
      unconditionally and is idempotent, so the order does not matter).
  app/town_moves.py:enter_town() (after settlement_row(conn, city, create=True)) ->
      settlement_visits.enter_from_city(conn, city, location_id=settle, turn=turn, map_id=chart["id"],
      world_time=world.get_world_time(conn)) (the live map kind reaches a town only through this path).
      enter_town's turn defaults to 0 and the live travel route reaches it through
      app/main.py sync_after_world_move(conn, get_map(None, conn=conn), (px, py)) with no turn, so that
      call must pass turn=_turn_value(conn) as well; without the turn and the clock every entry to a city
      on that route looks like turn 0, minute 0 and re-entries are never counted.
  app/world.py:build_ambient_move_line() "You enter the bounds of" branch -> say "for the first time"
      when (travel_result.get("visit") or {}).get("first_visit").
  app/world.py:get_state() next to the turn_prompts.state_view merge -> state.update(settlement_visits.state_view(conn)).

Turn on:
  [ ] no playthrough_options flag: a gap fix that turns on with its hook lines
  [ ] app/db.py:_migrate_columns() tail: try: from app.settlement_visits import ensure_schema; ensure_schema(conn)
  [ ] app/world.py: WORLD_TABLES, RESTORE_ORDER, _REPLACE_ONLY_WHEN_EXPORTED += "settlement_visits";
      _save_snapshot / _restore_snapshot_rows: snapshot and replace whole like quest_clocks (text primary key);
      export filter by map_id like town_cells; _clear_playthrough: DELETE FROM settlement_visits
  [ ] the two hook calls above; the ambient line change
  [ ] UI: nothing required; optional "first visit" note in the travel banner from travel_result.visit
  [ ] prompt: nothing

Tests: tests/test_settlement_visits.py
"""
from __future__ import annotations

import json
from typing import Any

from app.db import row_to_dict, rows_to_dicts
from app.player_resources import world_abs_minutes
from app.tile_world import SETTLEMENT_STATES

# The settlement members of tile_world.SETTLEMENT_STATES. That set also holds the map states ruins,
# dungeon and gate, which are not settlements: a step from one of them onto a town cell is an entry.
NOT_SETTLEMENTS = frozenset({"ruins", "dungeon", "gate"})
SETTLEMENT_TERRAINS = frozenset(SETTLEMENT_STATES) - NOT_SETTLEMENTS

# ---------------------------------------------------------------------------
# Rules tables (data)
# ---------------------------------------------------------------------------

REENTRY_GRACE_MINUTES = 30  # a second enter within this many world minutes on the same turn is the same visit
POWER_MIN, POWER_MAX, POWER_DEFAULT = 30, 100, 50  # copies ensure_settlement_ruler (app/world.py)
OFFICER_COUNT, WORKER_COUNT = 2, 2

# settlement state / class / band word -> class (the RULER_ROLES key). Unknown -> "town".
SETTLEMENT_CLASS: dict[str, str] = {
    "city": "city", "large_city": "city", "metropolis": "city",
    "town": "town",
    "village": "village", "hamlet": "village",
    "harbor": "harbor", "colony": "colony", "station": "station", "farm": "farm", "shipyard": "shipyard",
}
SETTLEMENT_CLASS_DEFAULT = "town"

# World-scale city bands carry no ruler_power_rank; this stands in (power_source "band").
POWER_BY_BAND: dict[str, int] = {
    "hamlet": 35, "village": 42, "town": 50, "city": 62, "large_city": 72, "metropolis": 85,
}

# Copies of the role words in app/world.py ensure_settlement_ruler so the proposal names what the seeder
# will create. They are copied, not imported: _RULER_ROLE_BY_CLASS is private and the officer and worker
# lists are locals of that function.
RULER_ROLES: dict[str, str] = {
    "city": "city reeve", "town": "town head", "village": "village elder", "harbor": "harbor master",
    "colony": "colony overseer", "station": "station chief", "farm": "landholder", "shipyard": "yard master",
}
RULER_ROLE_DEFAULT = "local authority"
OFFICER_ROLES: dict[str, tuple[str, str]] = {
    "city": ("guard captain", "clerk of stores"), "town": ("constable", "market warden"),
    "village": ("reeve's hand", "watch volunteer"), "harbor": ("dock sergeant", "customs runner"),
    "colony": ("gate officer", "ration clerk"), "station": ("shift lead", "security aide"),
}
OFFICER_ROLES_DEFAULT: tuple[str, str] = ("deputy", "scribe")
WORKER_ROLES: dict[str, tuple[str, str]] = {
    "city": ("porter", "street cleaner"), "town": ("carter", "apprentice"), "village": ("farm hand", "herder"),
    "harbor": ("stevedore", "net mender"), "colony": ("laborer", "runner"), "station": ("technician", "mess hand"),
}
WORKER_ROLES_DEFAULT: tuple[str, str] = ("laborer", "helper")

JOURNAL_KIND = "visit"
JOURNAL_FIRST = "First visit to {name} ({cls}). {when}."
JOURNAL_AGAIN = "Back in {name} (visit {n}). {when}."
JOURNAL_MAX_CHARS = 900

RULER_FLAG_PREFIX = "settlement_ruler:"
APPLY_CALL = "app.world.ensure_settlement_ruler(conn, location_id={location_id}, settlement={settlement})"

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settlement_visits (
    settlement_id TEXT PRIMARY KEY,
    map_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    class TEXT NOT NULL DEFAULT 'town',
    location_id INTEGER NOT NULL DEFAULT 0,
    x INTEGER NOT NULL DEFAULT 0,
    y INTEGER NOT NULL DEFAULT 0,
    first_visit_turn INTEGER NOT NULL DEFAULT 0,
    first_visit_minute INTEGER NOT NULL DEFAULT 0,
    last_visit_turn INTEGER NOT NULL DEFAULT 0,
    last_visit_minute INTEGER NOT NULL DEFAULT 0,
    visit_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_settlement_visits_map ON settlement_visits (map_id, last_visit_turn)"

# One literal statement per fillable column; nothing in the SQL comes from caller text.
_FILL_SQL: dict[str, str] = {
    "map_id": "UPDATE settlement_visits SET map_id = ? WHERE settlement_id = ?",
    "name": "UPDATE settlement_visits SET name = ? WHERE settlement_id = ?",
    "class": "UPDATE settlement_visits SET class = ? WHERE settlement_id = ?",
    "location_id": "UPDATE settlement_visits SET location_id = ? WHERE settlement_id = ?",
    "x": "UPDATE settlement_visits SET x = ? WHERE settlement_id = ?",
    "y": "UPDATE settlement_visits SET y = ? WHERE settlement_id = ?",
}

_STATE_VIEW_KEYS = ("settlement_id", "name", "class", "visit_count", "first_visit_turn", "last_visit_turn")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def ensure_schema(conn) -> None:
    """Create the settlement_visits table and its index when missing. No commit; the caller's connection commits."""
    conn.execute(_TABLE_SQL)
    conn.execute(_INDEX_SQL)


# ---------------------------------------------------------------------------
# Pure helpers over the three settlement record shapes
# ---------------------------------------------------------------------------

def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def officer_power(power: int, i: int) -> int:
    """The seeder's officer rank: max(15, power - 20 - 5 * i)."""
    return max(15, int(power) - 20 - 5 * int(i))


def worker_power(power: int, i: int) -> int:
    """The seeder's worker rank: max(5, power // 4 - 2 * i)."""
    return max(5, int(power) // 4 - 2 * int(i))


def settlement_key(settlement: dict | str | None) -> str:
    """The settlement id: a string stripped, or a record's id, settlement_id or city_id; "" when none."""
    if settlement is None:
        return ""
    if isinstance(settlement, str):
        return settlement.strip()
    if not isinstance(settlement, dict):
        return ""
    for key in ("id", "settlement_id", "city_id"):
        value = settlement.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def settlement_class(settlement: dict | None) -> str:
    """The ruler-role class from state, class or band, through SETTLEMENT_CLASS; "town" when unknown."""
    if not isinstance(settlement, dict):
        return SETTLEMENT_CLASS_DEFAULT
    for key in ("state", "class", "band", "population_band"):
        word = str(settlement.get(key) or "").strip().lower()
        if word and word in SETTLEMENT_CLASS:
            return SETTLEMENT_CLASS[word]
    return SETTLEMENT_CLASS_DEFAULT


def settlement_name(settlement: dict | None) -> str:
    """The settlement's name, else its label, else the class word with a capital."""
    if isinstance(settlement, dict):
        for key in ("name", "label"):
            value = str(settlement.get(key) or "").strip()
            if value:
                return value
    return settlement_class(settlement).title()


def settlement_ref(settlement: dict | None, *, location_id: int = 0) -> dict[str, Any]:
    """The SettlementRef for a record: economy.settlement_profile's answer, unchanged (lazy import)."""
    from app.economy import settlement_profile

    location_row = {"id": int(location_id)} if _int(location_id) > 0 else None
    return settlement_profile(settlement if isinstance(settlement, dict) else None, location_row)


def is_entry_step(travel: dict | None) -> bool:
    """True when a travel pack steps onto a settlement cell from a cell that is not one."""
    if not isinstance(travel, dict):
        return False
    if not travel.get("settlement_id"):
        return False
    from_terrain = str(travel.get("from_terrain") or "").strip().lower()
    return from_terrain not in SETTLEMENT_TERRAINS


def _settlement_power(settlement: dict | None) -> tuple[int, str]:
    """Clamped ruler power and where it came from: meta (ruler_power_rank), band, or default."""
    source = settlement if isinstance(settlement, dict) else {}
    rank = _int(source.get("ruler_power_rank"), 0)
    if rank > 0:
        return max(POWER_MIN, min(POWER_MAX, rank)), "meta"
    band = str(source.get("band") or source.get("population_band") or "").strip().lower()
    if band in POWER_BY_BAND:
        return max(POWER_MIN, min(POWER_MAX, POWER_BY_BAND[band])), "band"
    return POWER_DEFAULT, "default"


def seed_proposal(settlement: dict | None, *, location_id: int, ruler_exists: bool = False) -> dict[str, Any] | None:
    """What ensure_settlement_ruler would create for this settlement; None when nothing should be seeded."""
    sid = settlement_key(settlement)
    loc = _int(location_id)
    if ruler_exists or loc <= 0 or not sid:
        return None
    cls = settlement_class(settlement)
    power, power_source = _settlement_power(settlement)
    officer_roles = OFFICER_ROLES.get(cls, OFFICER_ROLES_DEFAULT)
    worker_roles = WORKER_ROLES.get(cls, WORKER_ROLES_DEFAULT)
    record = dict(settlement) if isinstance(settlement, dict) else {"id": sid}
    # The seeder reads only state and class, so a band-only record (a world city) would seed a town.
    if not (record.get("state") or record.get("class")):
        record["class"] = cls
    return {
        "settlement_id": sid,
        "location_id": loc,
        "class": cls,
        "flag_key": f"{RULER_FLAG_PREFIX}{sid}",
        "power_source": power_source,
        "ruler": {
            "role": RULER_ROLES.get(cls, RULER_ROLE_DEFAULT),
            "power_rank": power,
            "presence": "full",
            "tier": "ruler",
            "shell": 0,
        },
        "officers": [
            {"role": officer_roles[i], "power_rank": officer_power(power, i), "presence": "event_worthy",
             "tier": "staff", "shell": 0}
            for i in range(OFFICER_COUNT)
        ],
        "workers": [
            {"role": worker_roles[i], "power_rank": worker_power(power, i), "presence": "background",
             "tier": "staff", "shell": 1}
            for i in range(WORKER_COUNT)
        ],
        "apply": APPLY_CALL.format(location_id=loc, settlement=json.dumps(record, sort_keys=True, default=str)),
    }


def journal_line(settlement: dict | None, *, first_visit: bool, visit_count: int,
                 world_time: dict | None = None, turn: int = 0) -> str:
    """The journal sentence for a visit; the world clock label when known, else the turn number."""
    label = str((world_time or {}).get("label") or "").strip() if isinstance(world_time, dict) else ""
    when = label or f"Turn {max(0, _int(turn))}"
    name = settlement_name(settlement)
    if first_visit:
        text = JOURNAL_FIRST.format(name=name, cls=settlement_class(settlement), when=when)
    else:
        text = JOURNAL_AGAIN.format(name=name, n=max(1, _int(visit_count, 1)), when=when)
    return text[:JOURNAL_MAX_CHARS]


def _journal_note(content: str) -> dict[str, str]:
    return {"kind": JOURNAL_KIND, "content": str(content or "")[:JOURNAL_MAX_CHARS]}


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def ruler_exists(conn, settlement_id: str) -> bool:
    """True when the settings row settlement_ruler:<sid> holds a truthy value (the seeder's flag)."""
    sid = settlement_key(settlement_id)
    if not sid:
        return False
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (f"{RULER_FLAG_PREFIX}{sid}",)).fetchone()
    if row is None:
        return False
    raw = row["value"]
    if isinstance(raw, str):
        try:
            return bool(json.loads(raw))
        except json.JSONDecodeError:
            return bool(raw.strip())
    return bool(raw)


def get_visit(conn, settlement_id: str) -> dict[str, Any] | None:
    """The stored visit row for a settlement id, or None."""
    sid = settlement_key(settlement_id)
    if not sid:
        return None
    row = conn.execute("SELECT * FROM settlement_visits WHERE settlement_id = ?", (sid,)).fetchone()
    return row_to_dict(row) if row else None


def list_visits(conn, *, map_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """Visit rows, most recent last visit first, then by id; filtered to one map when map_id is given."""
    cap = max(1, _int(limit, 50))
    if map_id:
        rows = conn.execute(
            "SELECT * FROM settlement_visits WHERE map_id = ? ORDER BY last_visit_turn DESC, settlement_id ASC LIMIT ?",
            (str(map_id), cap),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM settlement_visits ORDER BY last_visit_turn DESC, settlement_id ASC LIMIT ?",
            (cap,),
        ).fetchall()
    return rows_to_dicts(rows)


def is_first_visit(conn, settlement_id: str) -> bool:
    """True when no visit row exists for the id yet."""
    return get_visit(conn, settlement_id) is None


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------

def record_enter(conn, settlement_id: str, turn: int, *, settlement: dict | None = None, map_id: str = "",
                 location_id: int = 0, world_time: dict | None = None,
                 x: int | None = None, y: int | None = None) -> dict[str, Any]:
    """Upsert the visit row for one settlement entry and return the EnterResult.

    A new id is a first visit. An existing row entered again on the same turn within
    REENTRY_GRACE_MINUTES is the same visit (no count, no journal). Otherwise the last visit moves
    and the count grows. On every entry blank or zero stored fields are filled from the arguments
    and never overwritten, with one exception: a stored class of "town" is also the default for a
    record that carried no class word, so a later record naming another class replaces it.
    Writes only settlement_visits.
    """
    sid = settlement_key(settlement_id)
    if not sid:
        raise ValueError("settlement id is blank")
    turn_value = max(0, _int(turn))
    abs_minute = world_abs_minutes(world_time if isinstance(world_time, dict) else None)
    record = dict(settlement) if isinstance(settlement, dict) else {}
    record["id"] = sid
    name = settlement_name(record) if record.get("name") or record.get("label") else ""
    cls = settlement_class(record)
    loc = max(0, _int(location_id))
    ensure_schema(conn)
    existing = get_visit(conn, sid)

    if existing is None:
        conn.execute(
            """
            INSERT INTO settlement_visits (
                settlement_id, map_id, name, class, location_id, x, y,
                first_visit_turn, first_visit_minute, last_visit_turn, last_visit_minute, visit_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (sid, str(map_id or ""), name[:120], cls, loc, _int(x), _int(y),
             turn_value, abs_minute, turn_value, abs_minute),
        )
        first_visit, counted = True, True
    else:
        same_turn = _int(existing.get("last_visit_turn")) == turn_value
        within_grace = (abs_minute - _int(existing.get("last_visit_minute"))) < REENTRY_GRACE_MINUTES
        counted = not (same_turn and within_grace)
        first_visit = False
        if counted:
            conn.execute(
                """
                UPDATE settlement_visits
                SET last_visit_turn = ?, last_visit_minute = ?, visit_count = visit_count + 1
                WHERE settlement_id = ?
                """,
                (turn_value, abs_minute, sid),
            )
        _fill_blanks(conn, existing, sid, map_id=str(map_id or ""), name=name, cls=cls, location_id=loc, x=x, y=y)

    row = get_visit(conn, sid) or {}
    has_ruler = ruler_exists(conn, sid)
    seed_record = dict(record)
    if not (seed_record.get("state") or seed_record.get("class") or seed_record.get("band")):
        seed_record["state"] = str(row.get("class") or cls)
    if not seed_record.get("name") and row.get("name"):
        seed_record["name"] = row.get("name")
    seed_location = loc if loc > 0 else _int(row.get("location_id"))
    seed = seed_proposal(seed_record, location_id=seed_location, ruler_exists=has_ruler)
    journal = None
    if counted:
        journal = _journal_note(
            journal_line(seed_record, first_visit=first_visit, visit_count=_int(row.get("visit_count"), 1),
                         world_time=world_time, turn=turn_value)
        )
    return {
        "settlement_id": sid,
        "first_visit": first_visit,
        "counted": counted,
        "visit": row,
        "journal": journal,
        "ruler_exists": has_ruler,
        "seed": seed,
    }


def _fill_blanks(conn, existing: dict[str, Any], sid: str, *, map_id: str, name: str, cls: str,
                 location_id: int, x: int | None, y: int | None) -> None:
    """Fill stored fields that are blank or 0 from the new arguments; never overwrite a stored value.

    The class column is the one exception: "town" is both a real class and the default written when
    the record carried no class word, so a stored "town" gives way to a later, more specific class.
    """
    updates: list[tuple[str, Any]] = []
    if not str(existing.get("map_id") or "") and map_id:
        updates.append(("map_id", map_id))
    if not str(existing.get("name") or "") and name:
        updates.append(("name", name[:120]))
    if str(existing.get("class") or "") in ("", SETTLEMENT_CLASS_DEFAULT) and cls != SETTLEMENT_CLASS_DEFAULT:
        updates.append(("class", cls))
    if _int(existing.get("location_id")) <= 0 and location_id > 0:
        updates.append(("location_id", location_id))
    if _int(existing.get("x")) == 0 and x is not None and _int(x) != 0:
        updates.append(("x", _int(x)))
    if _int(existing.get("y")) == 0 and y is not None and _int(y) != 0:
        updates.append(("y", _int(y)))
    for column, value in updates:
        conn.execute(_FILL_SQL[column], (value, sid))


def enter_from_travel(conn, travel: dict | None, *, location_id: int, turn: int,
                      world_time: dict | None = None, map_id: str = "") -> dict[str, Any] | None:
    """record_enter for a tile_world.move_player travel pack; None unless the step enters a settlement."""
    if not is_entry_step(travel):
        return None
    pack = travel if isinstance(travel, dict) else {}
    settlement = pack.get("settlement") if isinstance(pack.get("settlement"), dict) else {}
    record = dict(settlement)
    if not settlement_key(record.get("id")):
        record["id"] = settlement_key(str(pack.get("settlement_id") or ""))
    to = pack.get("to")
    x = y = None
    if isinstance(to, (list, tuple)) and len(to) >= 2:
        x, y = _int(to[0]), _int(to[1])
    elif isinstance(to, dict):
        x, y = _int(to.get("x")), _int(to.get("y"))
    return record_enter(
        conn, settlement_key(record), turn, settlement=record, map_id=str(map_id or ""),
        location_id=location_id, world_time=world_time, x=x, y=y,
    )


def enter_from_city(conn, city: dict, *, location_id: int, turn: int, map_id: str,
                    world_time: dict | None = None) -> dict[str, Any]:
    """record_enter for a world-scale city record (town_moves.enter_town); x and y come from the record."""
    record = dict(city) if isinstance(city, dict) else {}
    return record_enter(
        conn, settlement_key(record), turn, settlement=record, map_id=str(map_id or ""),
        location_id=location_id, world_time=world_time,
        x=_int(record.get("x")), y=_int(record.get("y")),
    )


# ---------------------------------------------------------------------------
# State view and clearing
# ---------------------------------------------------------------------------

def state_view(conn, *, limit: int = 12) -> dict[str, list[dict[str, Any]]]:
    """The slim rows a state payload would carry: id, name, class, count, first and last turn."""
    rows = list_visits(conn, limit=limit)
    return {"settlement_visits": [{key: row.get(key) for key in _STATE_VIEW_KEYS} for row in rows]}


def clear_visits(conn, *, map_id: str = "") -> int:
    """Delete visit rows: those of one map when map_id is given, else all. Returns the count removed."""
    if map_id:
        cur = conn.execute("DELETE FROM settlement_visits WHERE map_id = ?", (str(map_id),))
    else:
        cur = conn.execute("DELETE FROM settlement_visits")
    return int(cur.rowcount or 0)
