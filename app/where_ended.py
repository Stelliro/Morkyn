"""Where the player is when the scene ends: one small ask, the engine's own places as the answers.

Playtest #46 and #76 (Linux .deb playtest, Hermes 3 8B, cc87dd29) are one fault class seen from both
sides: on a turn the draft wrote no MOVE for, the engine decided the move from the player's line alone.

* T6 "i leave the town, and find a city that has a ghoul problem": the prose left the town for the forest
  trail, the line names no known place, so movement was "unresolved" and the player stayed in the clinic.
  T5, T10 and T12 were the same note.
* T13 "i rip her head from her shoulders, her spine comes out still connected ...": the doorway reader
  read "comes ... out" as leaving the building and the server walked the player from the clinic (L3) to
  the town (L1), while the prose stayed at Beth's desk.

The fact that decides both is where the prose leaves the player, and only the prose knows it. So the
engine lists its own answers, from its records, and asks the turn's model one plain question with one
letter for a reply:

    Where is the player at the end of this text?
    A) still in <the place they are in>
    B) in <the place around it>, outside <the place they are in>
    C) outside <the settlement>, on the road or in the wilds
    D) at <a known place this text names>

The options are the current place, each place it stands in (parent_id), "outside" the outermost one,
and up to two other known places the text names by code or stored name. No word list decides anything.
The engine then acts (``settle``), after resolve_movement, on the two cases the evidence showed:

* a move the server made with no MOVE op, to a known place up the chain or elsewhere, is not applied
  when the answer is the place the player is in (T13); when the answer is further out the same way
  ("outside the town" for a walk out of the clinic) the move goes there instead;
* a travel turn the movement rules could not resolve moves to the place answered: a place up the
  chain, a known place, or for "outside" the engine's own place "Outside <settlement>" (made once per
  settlement and kept), whose summary carries the line the player set off with (T6). "Still here"
  leaves them where they are, as before.

Moves into a building (venue entry rules) and moves the draft wrote are left to their own rules. A
missing, failed or unclear reply changes nothing. The ask goes through app.llm._chat_text with the
turn's own usage and trace lists, so its prompt, raw reply and time are in the turn's trace file and
model_logs (phase ``where_ended``).
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

from app import turn_ledger

PHASE = "where_ended"
MAX_KNOWN = 2
OUTSIDE_PREFIX = "Outside "
SYSTEM = "Answer with one letter."
QUESTION = "Where is the player at the end of this text?"

Ask = Callable[[str, str], str]
_ASK_OVERRIDE: list[Ask | None] = [None]

# Server moves this checks: a move to a known place, not a walk into a building
# (the venue rules check those against the prose themselves).
_CHECKED_RULES = frozenset({
    "venue_exit", "venue_exit_to", "player_input", "venue_return", "narration_code", "follow_named",
    "player_named",
})


def set_ask(ask: Ask | None) -> Ask | None:
    """Use ``ask`` (system, user) -> reply text for the question (None: the turn's model). Returns the previous one."""
    previous = _ASK_OVERRIDE[0]
    _ASK_OVERRIDE[0] = ask
    return previous


def _model_ask(result: dict[str, Any]) -> Ask | None:
    """The turn's own model through _chat_text, recorded on the turn's usage and trace."""
    trace = result.get("_model_trace")
    usage = result.get("_model_usage")
    # Only a turn the model wrote: a fallback turn or a turn built without a
    # model call (tests, harness stubs) has no model to ask.
    if not isinstance(trace, list) or not any(isinstance(e, dict) and e.get("event") == "request" for e in trace):
        return None
    if not isinstance(usage, list):
        usage = []
        result["_model_usage"] = usage

    def ask(system: str, user: str) -> str:
        from app.llm import _chat_text

        return _chat_text(system, user, timeout=45, usage=usage, phase=PHASE, max_tokens=4, trace=trace, temperature=0.0)

    return ask


# ------------------------------------------------------------------- options


def _chain(conn, here_id: int) -> list[Any]:
    """The place the player is in, then each place it stands in, outermost last."""
    from app.world import _location_row

    rows: list[Any] = []
    seen: set[int] = set()
    row = _location_row(conn, here_id)
    while row is not None and int(row["id"]) not in seen and len(rows) < 6:
        rows.append(row)
        seen.add(int(row["id"]))
        parent = int((row["parent_id"] if "parent_id" in row.keys() else 0) or 0)
        row = _location_row(conn, parent) if parent else None
    return rows


def _named_in(text: str, name: str, code: str) -> bool:
    low = text.lower()
    if code and f"[[{code.lower()}]]" in low:
        return True
    name = str(name or "").strip().lower()
    return bool(name) and len(name) >= 4 and re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", low) is not None


def build_options(conn, narration: str) -> dict[str, Any] | None:
    """The answers the engine has: here, each place around it, outside, known places the text names."""
    from app.world import _is_settlement

    row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    here_id = int((row[0] if row else 0) or 0)
    chain = _chain(conn, here_id)
    if not chain:
        return None
    here = chain[0]
    options: list[dict[str, Any]] = [
        {"kind": "here", "id": int(here["id"]), "code": str(here["code"] or ""), "name": str(here["name"] or ""),
         "label": f"still in {here['name']}"}
    ]
    inner = str(here["name"] or "")
    for up in chain[1:]:
        options.append({"kind": "up", "id": int(up["id"]), "code": str(up["code"] or ""), "name": str(up["name"] or ""),
                        "label": f"in {up['name']}, outside {inner}"})
        inner = str(up["name"] or "")
    top = chain[-1]
    top_name = str(top["name"] or "")
    # Not outside a place the engine made as "outside" one: that is already the open road.
    if not top_name.startswith(OUTSIDE_PREFIX) or _is_settlement(conn, top):
        options.append({"kind": "outside", "id": 0, "code": "", "name": f"{OUTSIDE_PREFIX}{top_name}"[:80],
                        "top_id": int(top["id"]), "label": f"outside {top_name}, on the road or in the wilds"})
    chain_ids = {int(r["id"]) for r in chain}
    known = 0
    for other in conn.execute("SELECT id, code, name FROM locations ORDER BY id").fetchall():
        if known >= MAX_KNOWN:
            break
        if int(other["id"]) in chain_ids:
            continue
        if _named_in(narration, str(other["name"] or ""), str(other["code"] or "")):
            options.append({"kind": "known", "id": int(other["id"]), "code": str(other["code"] or ""),
                            "name": str(other["name"] or ""), "label": f"at {other['name']}"})
            known += 1
    for i, option in enumerate(options):
        option["letter"] = chr(ord("A") + i)
    return {"here_id": here_id, "options": options}


def build_prompt(narration: str, options: list[dict[str, Any]]) -> tuple[str, str]:
    text = re.sub(r"\s*\[\[[^\]]*\]\]", "", str(narration or "")).strip()
    lines = [text, "", QUESTION]
    lines += [f"{o['letter']}) {o['label']}" for o in options]
    return SYSTEM, "\n".join(lines)


def parse_letter(reply: Any, options: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The option a reply names by its letter ("B", "B)", "Answer: B"), or None."""
    letters = {o["letter"]: o for o in options}
    text = str(reply or "").strip()
    first = re.match(r"^\W*([A-Za-z])\s*(?:$|[).:\]])", text)
    if first and first.group(1).upper() in letters:
        return letters[first.group(1).upper()]
    found = {m.group(1) for m in re.finditer(r"\b([A-Z])\b", text) if m.group(1) in letters}
    if len(found) == 1:
        return letters[found.pop()]
    return None


# ----------------------------------------------------------------------- ask


def wants_ask(conn, result: dict[str, Any], player_input: str) -> bool:
    """A player turn with movement in its line and no MOVE or WALK from the draft."""
    from app.world import _movement_intent, _player_line, travel_intent, venue_move_intent

    line = _player_line(player_input)
    if not line.strip() or line.lstrip().startswith("__"):
        return False
    patch = result.get("player") if isinstance(result.get("player"), dict) else {}
    if str(patch.get("move_to_location") or "").strip() or str(patch.get("move_to_location_code") or "").strip():
        return False
    if result.get("map_walk"):
        return False
    try:
        return bool(travel_intent(line) or venue_move_intent(line) or _movement_intent(conn, line) == "travel")
    except Exception:
        return False


def ask_where(conn, result: dict[str, Any], player_input: str, narration: str) -> dict[str, Any] | None:
    """Ask where the prose leaves the player and put the answer on ``result["_where_ended"]``."""
    if not isinstance(result, dict) or not str(narration or "").strip():
        return None
    if not wants_ask(conn, result, player_input):
        return None
    ask = _ASK_OVERRIDE[0] or _model_ask(result)
    if ask is None:
        return None
    built = build_options(conn, narration)
    if not built or len(built["options"]) < 2:
        return None
    system, user = build_prompt(narration, built["options"])
    started = time.time()
    record: dict[str, Any] = {"here_id": built["here_id"], "options": built["options"]}
    try:
        reply = ask(system, user)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"[:200]
        reply = ""
    record["reply"] = str(reply or "")[:80]
    record["seconds"] = round(time.time() - started, 3)
    choice = parse_letter(reply, built["options"])
    record["choice"] = choice
    turn_ledger.note("movement", "where_ended_asked", reply=record["reply"],
                     answer=(choice or {}).get("label") or "unclear", seconds=record["seconds"])
    result["_where_ended"] = record
    return record


# -------------------------------------------------------------------- settle


def _destination_row(conn, patch: dict[str, Any]):
    from app.world import _match_location_by_name, humanize_place_name

    code = str(patch.get("move_to_location_code") or "").strip().upper()
    if code:
        return conn.execute("SELECT * FROM locations WHERE UPPER(code) = ?", (code,)).fetchone()
    name = str(patch.get("move_to_location") or "").strip()
    if not name:
        return None
    try:
        found = _match_location_by_name(conn, humanize_place_name(name))
    except Exception:
        return None
    if found is None:
        return None
    return conn.execute("SELECT * FROM locations WHERE id = ?", (int(found["id"]),)).fetchone()


def outside_place(conn, option: dict[str, Any], player_input: str) -> str:
    """The engine's place outside a settlement: found by name or made once. Returns its code."""
    from app.world import _location_row, _next_code, _player_line

    name = str(option.get("name") or "").strip()
    found = conn.execute("SELECT code FROM locations WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
    line = re.sub(r"\s+", " ", re.sub(r"[@#!&]\w+|\[\[[^\]]*\]\]", "", _player_line(player_input))).strip()
    if found is not None:
        return str(found["code"] or "")
    top = _location_row(conn, int(option.get("top_id") or 0))
    top_name = str(top["name"] or "") if top is not None else name[len(OUTSIDE_PREFIX):]
    summary = f"Open ground outside {top_name}. The player left it set on: {line}"[:400]
    code = _next_code(conn, "locations", "L")
    conn.execute(
        "INSERT INTO locations (code, name, summary, visit_count, parent_id) VALUES (?, ?, ?, 0, 0)",
        (code, name, summary),
    )
    turn_ledger.note("place", "outside_place_made", name=name, outside_of=top_name)
    return code


def settle(conn, result: dict[str, Any], report: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Act on the answer: refuse an unshown server move, or resolve an unresolved trip."""
    record = result.pop("_where_ended", None)
    if not isinstance(record, dict) or not isinstance(report, dict):
        return report
    row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    if int((row[0] if row else 0) or 0) != int(record.get("here_id") or 0):
        return report
    choice = record.get("choice") if isinstance(record.get("choice"), dict) else None
    report = dict(report)
    report["where_ended"] = (choice or {}).get("label") or "unclear"
    if choice is None:
        return report
    patch = result.get("player")
    if not isinstance(patch, dict):
        patch = {}
        result["player"] = patch
    options = record.get("options") or []
    status = str(report.get("status") or "")
    rule = str(report.get("rule") or "")

    def move_to(option: dict[str, Any]) -> str:
        code = outside_place(conn, option, player_input) if option["kind"] == "outside" else str(option.get("code") or "")
        patch["move_to_location"] = None
        patch["move_to_location_code"] = code
        return code

    if status == "repaired" and rule in _CHECKED_RULES:
        dest = _destination_row(conn, patch)
        if dest is None:
            return report
        dest_id = int(dest["id"])
        if choice["kind"] == "here":
            turn_ledger.note("movement", "server_move_not_shown", destination=str(dest["name"] or ""), rule=rule)
            patch["move_to_location"] = None
            patch["move_to_location_code"] = None
            result["map_walk"] = None
            return {"status": "dropped_unshown", "from": report.get("from"), "destination": str(dest["name"] or ""),
                    "rule": "where_ended_here", "dropped_rule": rule, "where_ended": report["where_ended"]}
        if int(choice.get("id") or 0) == dest_id:
            return report
        # Further out the same way: out of the clinic and out of the town.
        order = [o for o in options if o["kind"] in {"up", "outside"}]
        dest_at = next((i for i, o in enumerate(order) if int(o.get("id") or 0) == dest_id), -1)
        choice_at = next((i for i, o in enumerate(order) if o["letter"] == choice["letter"]), -1)
        if dest_at >= 0 and choice_at > dest_at:
            move_to(choice)
            turn_ledger.note("movement", "server_move_went_further", destination=choice["name"], was=str(dest["name"] or ""))
            rule_now = "where_ended_outside" if choice["kind"] == "outside" else "where_ended"
            return {**report, "destination": choice["name"], "rule": rule_now, "replaced": str(dest["name"] or "")}
        turn_ledger.note("movement", "where_ended_disagrees", destination=str(dest["name"] or ""), answer=choice["label"])
        return report

    if status == "unresolved":
        if choice["kind"] == "here":
            turn_ledger.note("movement", "travel_stays_shown", place=choice["name"])
            return report
        move_to(choice)
        turn_ledger.note("movement", "travel_resolved_from_prose", destination=choice["name"], kind=choice["kind"])
        out = {"status": "repaired", "rule": "where_ended_outside" if choice["kind"] == "outside" else "where_ended",
               "from": report.get("from"), "destination": choice["name"], "where_ended": report["where_ended"]}
        if report.get("follow"):
            out["follow"] = report["follow"]
        return out
    return report
