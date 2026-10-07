"""
Go with / Stay and Travel there (TODO n21, n22): what a turn offered, as buttons.

The engine decides what is on offer, from its own facts, never from a guess
at free prose:

* walk_with: a lead the town resolver read in the prose and did not walk
  (movement rule ``town_led_unasked``, playtest #76 T11: "Bertram leads you to
  the Blind Owl Forge"), or a LEAD op whose person is here this turn.
* travel_to: a direction the engine itself told (direction_hint), a [[L#]]
  place, a known plot or a known person someone here names in what they say,
  and the current step of a quest the player took that has a place.

Prompts live one turn in the ``turn_prompts`` settings row (snapshotted, so a
rewind restores them) and are shipped on get_state as ``prompts``. A typed
turn replaces them. Nothing here moves anyone on its own: the play-view
buttons do, through POST /api/prompts/{id} and /api/travel, and the walk is
the engine's own (town_moves walks, the world-map step), stopped only where
that route stops (a gate, exhaustion, an encounter).

``travel_destination`` (a settings row, snapshotted) keeps a place the player
set as their destination until they arrive or clear it; the Travel button
walks toward it one press at a time.
"""
from __future__ import annotations

import json
import re
from typing import Any

SETTING_KEY = "turn_prompts"
DEST_KEY = "travel_destination"
# Travel prompts per turn: a scene that names five places gets two buttons, not five.
TRAVEL_MAX = 2
# How long "the player stayed" is told to the draft after Stay (so the same
# person does not ask again every turn).
STAYED_TURNS = 5
_CODE_RE = re.compile(r"\[\[(L\d+)\]\]", re.I)


# ---------------------------------------------------------------------------
# The records
# ---------------------------------------------------------------------------


def _read(conn, key: str) -> Any:
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except Exception:
        return None
    if not row or row[0] in (None, ""):
        return None
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return None


def _write(conn, key: str, value: Any) -> None:
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
        return
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=True, separators=(",", ":"))),
    )


def load(conn) -> dict[str, Any]:
    raw = _read(conn, SETTING_KEY)
    raw = raw if isinstance(raw, dict) else {}
    return {
        "turn": int(raw.get("turn") or 0),
        "items": [row for row in raw.get("items") or [] if isinstance(row, dict) and row.get("id")],
        "stayed": [row for row in raw.get("stayed") or [] if isinstance(row, dict)],
    }


def save(conn, record: dict[str, Any]) -> None:
    if not record.get("items") and not record.get("stayed"):
        _write(conn, SETTING_KEY, None)
        return
    _write(conn, SETTING_KEY, record)


def destination(conn) -> dict[str, Any] | None:
    raw = _read(conn, DEST_KEY)
    return raw if isinstance(raw, dict) and isinstance(raw.get("target"), dict) else None


def set_destination(conn, dest: dict[str, Any] | None) -> None:
    _write(conn, DEST_KEY, dest)


def find(conn, prompt_id: str) -> dict[str, Any] | None:
    for item in load(conn)["items"]:
        if str(item.get("id")) == str(prompt_id):
            return item
    return None


def remove(conn, prompt_id: str, *, stayed: dict[str, Any] | None = None) -> None:
    record = load(conn)
    record["items"] = [row for row in record["items"] if str(row.get("id")) != str(prompt_id)]
    if stayed:
        record["stayed"] = [row for row in record["stayed"] if row.get("npc_code") != stayed.get("npc_code")] + [stayed]
    save(conn, record)


def state_view(conn) -> dict[str, Any]:
    """get_state's ``prompts`` and ``travel_destination``."""
    return {"prompts": load(conn)["items"], "travel_destination": destination(conn)}


def leads_for_draft(conn, turn: int) -> list[dict[str, Any]]:
    """world_state.open_leads: walk-with offers still waiting, and people the player chose not to go with."""
    record = load(conn)
    out: list[dict[str, Any]] = []
    for item in record["items"]:
        if item.get("kind") == "walk_with":
            out.append({"by": item.get("npc_name") or "", "to": item.get("to_label") or "",
                        "status": "waiting_for_answer"})
    for row in record["stayed"]:
        if int(turn) - int(row.get("turn") or 0) <= STAYED_TURNS:
            out.append({"by": row.get("npc_name") or "", "to": row.get("to_label") or "", "status": "player_stayed"})
    return out[:6]


def pending_lead(conn) -> dict[str, Any] | None:
    """The newest walk-with prompt still open (a typed "I go with him" answers it)."""
    leads = [item for item in load(conn)["items"] if item.get("kind") == "walk_with"]
    return leads[-1] if leads else None


# ---------------------------------------------------------------------------
# Places the engine knows
# ---------------------------------------------------------------------------


def _chart(conn) -> dict[str, Any] | None:
    from app import town_moves as tm

    return tm.world_chart(conn)


def _city_view(conn, *, generate: bool = False):
    from app import town_moves as tm

    chart = tm.world_chart(conn)
    pos = tm.get_position(conn)
    if chart is None or not pos:
        return None
    city = tm.city_by_id(chart, str(pos.get("city_id") or ""))
    if city is None:
        return None
    return tm._CityView(conn, chart, city, pos, tm._CellSource(conn, chart, generate=generate))


def plot_target(conn, plot_id: str) -> tuple[dict[str, Any], str] | None:
    """({plot, city, x, y}, label) for a plot of a stored town cell."""
    from app import town_moves as tm

    chart = _chart(conn)
    if chart is None or not plot_id:
        return None
    found = tm.locate_plot(conn, chart, str(plot_id))
    if found is None:
        return None
    city, cell, _town, plot = found
    label = str(plot.get("name") or "") or tm.plot_label(plot)
    return ({"plot": str(plot_id), "city": str(city.get("id") or ""), "x": int(cell["x"]), "y": int(cell["y"])},
            label)


def location_target(conn, row: Any) -> tuple[dict[str, Any], str] | None:
    """Where a locations row is on the map: its plot, its town, or the tile its pin holds."""
    if row is None:
        return None
    row = dict(row)
    code = str(row.get("code") or "")
    name = str(row.get("name") or "")
    if str(row.get("plot_id") or ""):
        found = plot_target(conn, str(row["plot_id"]))
        if found is not None:
            target, label = found
            target["location_code"] = code
            return target, name or label
    chart = _chart(conn)
    if chart is None:
        return None
    if str(row.get("city_id") or ""):
        from app import town_moves as tm

        city = tm.city_by_id(chart, str(row["city_id"]))
        if city is not None:
            return {"x": int(city.get("x") or 0), "y": int(city.get("y") or 0), "city": str(row["city_id"]),
                    "location_code": code}, name
    from app.tile_world import _anchor_at

    pin = _anchor_at(chart, code, name)
    if pin and pin.get("x") is not None:
        return {"x": int(pin["x"]), "y": int(pin["y"]), "location_code": code}, name
    return None


def resolve_place(conn, text: str) -> tuple[dict[str, Any], str] | None:
    """A place name or code the engine already has: a [[L#]] row, a plot of this town, a location by name."""
    from app import town_moves as tm
    from app import world as W

    value = str(text or "").strip().strip("\"'")
    if not value:
        return None
    code = _CODE_RE.search(value) or re.fullmatch(r"(L\d+)", value, re.I)
    if code:
        row = conn.execute("SELECT * FROM locations WHERE code = ? COLLATE NOCASE", (code.group(1).upper(),)).fetchone()
        found = location_target(conn, row)
        if found is not None:
            return found
        value = _CODE_RE.sub("", value).strip()
    view = _city_view(conn)
    if view is not None and value:
        plot = tm._plot_named(view, tm._norm(value), known=False)
        if plot is not None:
            found = plot_target(conn, str(plot[2]["id"]))
            if found is not None:
                return found
    match = W._match_location_by_name(conn, value) if value else None
    if match is not None:
        return location_target(conn, W._location_row(conn, int(match["id"])))
    return None


def _here(conn) -> dict[str, Any]:
    """The player's location, the places that contain it, their town tile and the plot they are inside."""
    from app import town_moves as tm

    out: dict[str, Any] = {"codes": set(), "id": 0, "inside": "", "cell": None}
    row = conn.execute(
        "SELECT l.id, l.code, l.parent_id FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
    ).fetchone()
    hops = 0
    if row is not None:
        out["id"] = int(row["id"])
    while row is not None and hops < 8:
        out["codes"].add(str(row["code"] or "").upper())
        parent = int(row["parent_id"] or 0)
        row = conn.execute("SELECT id, code, parent_id FROM locations WHERE id = ?", (parent,)).fetchone() if parent else None
        hops += 1
    pos = tm.get_position(conn)
    out["inside"] = str((pos or {}).get("inside") or "")
    chart = _chart(conn)
    if chart is not None:
        out["cell"] = tm.player_cell(chart)
    return out


def _is_here(target: dict[str, Any], here: dict[str, Any]) -> bool:
    if target.get("plot"):
        return str(target["plot"]) == here.get("inside")
    if str(target.get("location_code") or "").upper() in here["codes"]:
        return True
    return here.get("cell") is not None and (int(target.get("x", -1)), int(target.get("y", -1))) == tuple(here["cell"])


def _target_key(target: dict[str, Any]) -> str:
    if target.get("plot"):
        return "p:" + str(target["plot"])
    if target.get("location_code"):
        return "l:" + str(target["location_code"]).upper()
    return f"xy:{target.get('x')},{target.get('y')}"


def _npc_place(conn, npc_id: int) -> tuple[dict[str, Any], str] | None:
    row = conn.execute("SELECT location_id, workplace_id FROM npcs WHERE id = ?", (int(npc_id),)).fetchone()
    if row is None:
        return None
    for key in ("location_id", "workplace_id"):
        loc_id = int(row[key] or 0)
        if loc_id:
            found = location_target(conn, conn.execute("SELECT * FROM locations WHERE id = ?", (loc_id,)).fetchone())
            if found is not None:
                return found
    return None


def quest_step_target(conn, quest_id: int) -> tuple[dict[str, Any], str] | None:
    """The place of a quest's current step: its location code, its map coords, or a place name the engine knows."""
    try:
        row = conn.execute(
            "SELECT qs.location_code, qs.location_name, qs.location_coords FROM quests q "
            "JOIN quest_steps qs ON qs.quest_id = q.id AND qs.step_number = q.current_step WHERE q.id = ?",
            (int(quest_id),),
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    if str(row["location_code"] or ""):
        found = resolve_place(conn, str(row["location_code"]))
        if found is not None:
            return found
    try:
        coords = json.loads(row["location_coords"] or "")
    except (TypeError, ValueError):
        coords = None
    if isinstance(coords, dict) and coords.get("x") is not None and coords.get("y") is not None:
        return {"x": int(float(coords["x"])), "y": int(float(coords["y"]))}, str(row["location_name"] or "the marked place")
    if str(row["location_name"] or ""):
        return resolve_place(conn, str(row["location_name"]))
    return None


# ---------------------------------------------------------------------------
# The gate after a turn
# ---------------------------------------------------------------------------


def _roster(prompt_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    try:
        from app.conversation import roster

        return roster(prompt_context or {})
    except Exception:
        return []


def _person(rows: list[dict[str, Any]], ref: str) -> dict[str, Any] | None:
    """A person here by code or by name (full, or a first name of three letters or more)."""
    value = re.sub(r"^\[\[|\]\]$", "", str(ref or "").strip()).strip()
    if not value:
        return None
    for row in rows:
        if str(row.get("code") or "").upper() == value.upper():
            return row
    low = value.lower()
    for row in rows:
        name = str(row.get("name") or "").lower()
        first = name.split(" ")[0] if name else ""
        if name and (name == low or name in low or (len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", low))):
            return row
    return None


def _move_npc_here(conn, *, name: str = "", code: str = "", origin_code: str = "") -> bool:
    """A leader the player walked with stands where the player now is."""
    here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    here_id = int((here[0] if here else 0) or 0)
    if not here_id:
        return False
    row = None
    if code:
        row = conn.execute("SELECT id, location_id FROM npcs WHERE code = ?", (str(code),)).fetchone()
    if row is None and name:
        origin = conn.execute("SELECT id FROM locations WHERE code = ? COLLATE NOCASE", (origin_code,)).fetchone() if origin_code else None
        if origin is not None:
            row = conn.execute(
                "SELECT id, location_id FROM npcs WHERE name = ? COLLATE NOCASE AND location_id = ?", (name, int(origin["id"]))
            ).fetchone()
        if row is None:
            rows = conn.execute("SELECT id, location_id FROM npcs WHERE name = ? COLLATE NOCASE", (name,)).fetchall()
            row = rows[0] if len(rows) == 1 else None
    if row is None or int(row["location_id"] or 0) == here_id:
        return False
    try:
        conn.execute("UPDATE npcs SET location_id = ? WHERE id = ?", (here_id, int(row["id"])))
    except Exception:
        return False
    return True


def _leads(conn, movement_report: dict[str, Any], dsl: dict[str, Any], rows: list[dict[str, Any]],
           here: dict[str, Any], notes: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(person: dict[str, Any], found: tuple[dict[str, Any], str] | None, source: str) -> None:
        code = str(person.get("code") or "")
        if code in seen:
            return
        if found is not None and _is_here(found[0], here):
            notes.append(f"lead_already_there:{code}")
            return
        seen.add(code)
        out.append({
            "kind": "walk_with",
            "npc_code": code,
            "npc_name": str(person.get("name") or ""),
            "to": found[0] if found else None,
            "to_label": found[1] if found else "",
            "source": source,
        })

    # The prose had them lead the player and the player had not asked: the
    # resolver kept the player put and cut the walk (playtest #76). That lead is the offer.
    if str(movement_report.get("rule") or "") == "town_led_unasked":
        person = _person(rows, str(movement_report.get("led_by") or ""))
        found = plot_target(conn, str(movement_report.get("plot") or "")) if movement_report.get("plot") else None
        if person is not None:
            add(person, found, "prose_lead")
        else:
            notes.append("lead_by_nobody_here")
    walked_with = str(movement_report.get("led_by") or "") if movement_report.get("rule") == "town_led" else ""
    for lead in (dsl.get("leads") or []) if isinstance(dsl, dict) else []:
        if not isinstance(lead, dict):
            continue
        person = _person(rows, str(lead.get("npc") or ""))
        if person is None:
            notes.append(f"lead_not_here:{str(lead.get('npc') or '')[:20]}")
            continue
        if walked_with and _person([person], walked_with) is not None:
            continue  # the player asked to go and the engine already walked them together
        found = resolve_place(conn, str(lead.get("to") or "")) if lead.get("to") else None
        if found is None and lead.get("to"):
            # "my forge": the place they meant is their own workplace when it is known.
            npc = conn.execute("SELECT id FROM npcs WHERE code = ?", (str(person.get("code") or ""),)).fetchone()
            row = conn.execute("SELECT workplace_id FROM npcs WHERE id = ?", (int(npc["id"]),)).fetchone() if npc else None
            if row is not None and int(row["workplace_id"] or 0):
                found = location_target(conn, conn.execute(
                    "SELECT * FROM locations WHERE id = ?", (int(row["workplace_id"]),)).fetchone())
        add(person, found, "lead_op")
    return out


def _speech_places(conn, narration: str, rows: list[dict[str, Any]], player_input: str,
                   here: dict[str, Any]) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """Places someone here names in what they say, each resolved to a place the engine has."""
    from app import town_moves as tm
    from app.conversation import spoken_lines
    from app.db import clean_role_text

    present = {str(row.get("code") or "").upper() for row in rows}
    try:
        lines = spoken_lines(narration, rows, player_input)
    except Exception:
        return []
    view = _city_view(conn)
    others = [
        dict(r) for r in conn.execute(
            "SELECT id, code, name, role FROM npcs WHERE location_id != ? OR location_id IS NULL", (int(here.get("id") or 0),)
        ).fetchall()
        if str(r["code"] or "").upper() not in present
    ]
    roles: dict[str, list[dict[str, Any]]] = {}
    for npc in others:
        role = clean_role_text(npc.get("role")).lower()
        if role:
            roles.setdefault(role, []).append(npc)
    out: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for entry in lines:
        code = str(entry.get("code") or "").upper()
        if not code or code not in present:
            continue  # only someone here, named for the line, tells the player anything
        line = str(entry.get("line") or "")
        source = {"kind": "", "npc_code": code}
        for match in _CODE_RE.finditer(line):
            found = resolve_place(conn, match.group(1))
            if found is not None:
                out.append((found[0], found[1], {**source, "kind": "place_code"}))
        if view is not None:
            plot = tm._plot_named(view, tm._norm(_CODE_RE.sub("", line)), known=True)
            if plot is not None:
                found = plot_target(conn, str(plot[2]["id"]))
                if found is not None:
                    out.append((found[0], found[1], {**source, "kind": "place_named"}))
        flat = _CODE_RE.sub("", line).lower()
        for npc in others:
            name = str(npc.get("name") or "").lower()
            first = name.split(" ")[0] if name else ""
            by_name = bool(name) and (re.search(rf"\b{re.escape(name)}\b", flat) is not None or (
                len(first) >= 4 and re.search(rf"\b{re.escape(first)}\b", flat) is not None))
            role = clean_role_text(npc.get("role")).lower()
            # "the baker" is a person only when one known person has that job.
            by_role = bool(role) and len(roles.get(role) or []) == 1 and re.search(
                rf"\bthe {re.escape(role)}\b", flat) is not None
            if not (by_name or by_role):
                continue
            found = _npc_place(conn, int(npc["id"]))
            if found is not None:
                label = f"{npc.get('name')} ({found[1]})" if found[1] and found[1] != npc.get("name") else str(npc.get("name") or "")
                out.append((found[0], label, {**source, "kind": "person_named", "person": str(npc.get("code") or "")}))
    return out


def _quest_places(conn, quest_report: dict[str, Any]) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    out: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for row in list(quest_report.get("updated") or []) + list(quest_report.get("created") or []):
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or row.get("status") or "")
        if action not in {"accept", "step_done", "active"}:
            continue
        code = str(row.get("code") or "")
        quest = conn.execute(
            "SELECT id, title, status FROM quests WHERE code = ? COLLATE NOCASE", (code,)
        ).fetchone() if code else None
        if quest is None or str(quest["status"] or "") != "active":
            continue
        found = quest_step_target(conn, int(quest["id"]))
        if found is not None:
            out.append((found[0], found[1] or str(quest["title"] or ""), {"kind": "quest", "quest": code}))
    return out


def quest_prompt(conn, quest_id: int, turn: int) -> dict[str, Any] | None:
    """A Travel there prompt for a quest the player just took with the Accept button (TODO n20, n22)."""
    found = quest_step_target(conn, int(quest_id))
    if found is None:
        return None
    here = _here(conn)
    if _is_here(found[0], here):
        return None
    record = load(conn)
    if any(_target_key(item.get("target") or {}) == _target_key(found[0]) for item in record["items"]):
        return None
    row = conn.execute("SELECT code FROM quests WHERE id = ?", (int(quest_id),)).fetchone()
    item = {"id": f"t{int(turn)}-q{int(quest_id)}", "kind": "travel_to", "label": found[1], "target": found[0],
            "source": {"kind": "quest", "quest": str((row["code"] if row else "") or "")}, "turn": int(turn)}
    record["items"].append(item)
    save(conn, record)
    return item


def gate_after_turn(
    conn,
    *,
    narration: str,
    movement_report: dict[str, Any] | None,
    quest_report: dict[str, Any] | None,
    prompt_context: dict[str, Any] | None,
    dsl: dict[str, Any] | None,
    direction_hint: dict[str, Any] | None,
    player_input: str,
    turn: int,
) -> dict[str, Any]:
    """This turn's Go with / Travel there prompts, from engine facts. Replaces the last turn's. Returns a trace."""
    report = movement_report if isinstance(movement_report, dict) else {}
    notes: list[str] = []
    record = load(conn)
    stayed = [row for row in record["stayed"] if int(turn) - int(row.get("turn") or 0) <= STAYED_TURNS]
    here = _here(conn)
    rows = _roster(prompt_context)
    moved_leader = False
    if report.get("led_by") and str(report.get("status") or "") in {"model", "repaired"}:
        # The player asked to go along and the engine walked them: the one who
        # led comes too. Whatever the walk's rule: a typed "I go into Blind Owl
        # Forge" that answers the lead keeps the planner's town_enter (n21 review).
        moved_leader = _move_npc_here(conn, name=str(report["led_by"]), origin_code=str(report.get("from") or ""))
    items: list[dict[str, Any]] = []
    stayed_codes = {str(row.get("npc_code") or "") for row in stayed}
    for lead in _leads(conn, report, dsl or {}, rows, here, notes):
        # Stay holds for STAYED_TURNS whatever place the next lead names: a
        # prose lead always carries a plot, so the old "no place" test let the
        # same Go with card back the next time the prose led (n21 review).
        if lead["npc_code"] in stayed_codes:
            notes.append(f"lead_after_stay:{lead['npc_code']}")
            continue
        items.append(lead)
    taken = {_target_key(item["to"]) for item in items if item.get("to")}
    candidates: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    hint = direction_hint if isinstance(direction_hint, dict) else None
    if hint and hint.get("told") and hint.get("x") is not None and hint.get("y") is not None:
        # Labelled with what the prose was told: the true place name only when
        # the answer was exact and not a hidden trade. A blurred answer stops
        # short of the place, and a forbidden one never names it (n22 review).
        if hint.get("exact") and not hint.get("forbidden"):
            told_label = str(hint.get("name") or hint.get("label") or "the place you were told of")
        else:
            good = str(hint.get("good") or hint.get("label") or "").strip()
            compass = str(hint.get("compass") or "").strip()
            told_label = (f"where you were pointed for {good}" if good else "where you were pointed") + (
                f", {compass}" if compass else ""
            )
        candidates.append(({"x": int(hint["x"]), "y": int(hint["y"])}, told_label, {"kind": "direction_hint"}))
    candidates.extend(_quest_places(conn, quest_report if isinstance(quest_report, dict) else {}))
    candidates.extend(_speech_places(conn, narration, rows, player_input, here))
    travel = 0
    for target, label, source in candidates:
        key = _target_key(target)
        if key in taken or _is_here(target, here):
            continue
        if travel >= TRAVEL_MAX:
            notes.append(f"travel_over_limit:{label[:30]}")
            continue
        taken.add(key)
        travel += 1
        items.append({"kind": "travel_to", "label": label, "target": target, "source": source})
    for n, item in enumerate(items, start=1):
        item["id"] = f"t{int(turn)}-{n}"
        item["turn"] = int(turn)
    save(conn, {"turn": int(turn), "items": items, "stayed": stayed})
    return {
        "items": [{k: item.get(k) for k in ("id", "kind", "npc_code", "to_label", "label", "source")} for item in items],
        "notes": notes[:8],
        "moved_leader": moved_leader,
    }


# ---------------------------------------------------------------------------
# Acting on a choice (the buttons)
# ---------------------------------------------------------------------------


def bring_along(conn, codes: list[str]) -> list[str]:
    """People walking with the player stand where the player now is."""
    moved = []
    for code in codes or []:
        if code and _move_npc_here(conn, code=str(code)):
            moved.append(str(code))
    return moved


def join_companion(conn, person: dict[str, Any], turn: int) -> None:
    """Going with someone who named no place: they are on the scene thread's ``with`` list and in the party,
    so the player's next moves carry them (world._move_companions_with_player)."""
    from app import scene_thread as st

    thread = st.read(conn)
    entry = {"code": str(person.get("code") or ""), "name": str(person.get("name") or "")}
    if thread is None:
        thread = {
            "version": 1,
            "doing": f"go with {entry['name']}",
            "target": entry["name"],
            "target_code": entry["code"],
            "with": [],
            "quest": {},
            "source": "lead",
            "started_turn": int(turn),
            "touched_turn": int(turn),
            "where": "",
        }
    have = {str(row.get("code") or row.get("name")) for row in thread.get("with") or []}
    if str(entry["code"] or entry["name"]) not in have:
        thread.setdefault("with", []).append(entry)
    thread["with"] = list(thread["with"])[:4]
    thread["touched_turn"] = int(turn)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (st.SETTING_KEY, json.dumps(thread)),
    )
    try:
        from app.party import sync_scene_companions

        sync_scene_companions(conn, list(thread["with"]), "", int(turn))
    except Exception:
        pass


def walk_in_town(conn, target: dict[str, Any], *, enter: bool, context: dict[str, Any] | None,
                 rule: str = "town_walk") -> dict[str, Any]:
    """The engine's street walk to a plot of the player's own town, or to one of its cells.

    Returns {"reached", "partial", "entered", "minutes", "refused", "report"}.
    Raises ValueError (no road) and PermissionError (too tired).
    """
    from app import town_moves as tm

    view = _city_view(conn, generate=True)
    if view is None:
        raise ValueError("You are not in a town.")
    pos = view.pos
    budget = tm.across_town_budget(view.city)
    plot_id = str(target.get("plot") or "")
    if plot_id:
        found = tm.locate_plot(conn, view.chart, plot_id)
        if found is None or str(found[0].get("id") or "") != view.city_id:
            raise ValueError("That place is not in this town.")
        _city, cell, town, plot = found
        if not plot.get("f"):
            raise ValueError("No road you know leads there.")
        side = int(town["side"])
        dest = (int(cell["x"]), int(cell["y"]))
        plan = tm._plan_walk(view, dest, {int(plot["f"][1]) * side + int(plot["f"][0])},
                             kind="enter" if enter else "walk", rule=rule,
                             target=tm._target_entry(dest[0], dest[1], plot, side), enter=enter, context=context,
                             budget=budget)
    else:
        dest = (int(target.get("x", 0)), int(target.get("y", 0)))
        if dest not in view.cells:
            raise ValueError("That place is not in this town.")
        town = view.source.get(*dest)
        if town is None:
            raise ValueError("That part of town is out of reach.")
        goal = tm.entry_tile(view.chart, view.city, view.cells[dest], town, (int(pos["cx"]), int(pos["cy"])))
        plan = tm._plan_walk(view, dest, {goal}, kind="walk", rule=rule,
                             target={"name": tm.street_at(town, goal) or "the road", "cx": dest[0], "cy": dest[1]},
                             enter=False, context=context, budget=budget)
    if plan.get("kind") == "stay" or (not plan.get("legs") and not plan.get("reached")):
        raise ValueError("No road you know leads there.")
    if plan.get("blocked"):
        raise PermissionError("Too exhausted to walk there. Wait, meditate, or sleep to recover energy.")
    report = tm._commit_walk(conn, plan, pos, context)
    if report.get("blocked"):
        raise PermissionError("Too exhausted to walk there. Wait, meditate, or sleep to recover energy.")
    return {
        "reached": bool(plan.get("reached")),
        "partial": bool(plan.get("partial")),
        "entered": str(report.get("entered") or ""),
        "minutes": int(plan.get("minutes") or 0),
        "refused": str(report.get("refused") or ""),
        "report": report,
    }


def next_world_step(chart: dict[str, Any], tx: int, ty: int) -> tuple[int, int] | None:
    """The next walkable tile toward (tx, ty) on the world map, as walk_toward picks it. Pure."""
    from app.tile_world import NEIGHBOR_ORDER, _cell_at, _player_xy, tile_walkable

    px, py = _player_xy(chart)
    if (px, py) == (int(tx), int(ty)):
        return None
    here = max(abs(tx - px), abs(ty - py))
    width, height = int(chart.get("width") or 0), int(chart.get("height") or 0)
    options = []
    for _name, dx, dy in NEIGHBOR_ORDER:
        nx, ny = px + dx, py + dy
        if width and height and not (0 <= nx < width and 0 <= ny < height):
            continue
        cell = _cell_at(chart, nx, ny)
        if not tile_walkable(cell):
            continue
        cheb = max(abs(tx - nx), abs(ty - ny))
        if cheb >= here:
            continue
        road = 0 if str((cell or {}).get("state") or "") in {"road", "bridge"} else 1
        options.append((cheb, abs(tx - nx) + abs(ty - ny), road, nx, ny))
    if not options:
        return None
    options.sort()
    return options[0][3], options[0][4]
