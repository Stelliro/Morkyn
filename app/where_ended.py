"""Where the player is when the scene ends: one small ask, the engine's own places as the answers, and a check.

Playtest #46 and #76 (Linux .deb playtest, Hermes 3 8B, cc87dd29) are one fault class seen from both
sides: the engine decided where the player stands from the player's line, not from where the prose
leaves them.

* T6 "i leave the town, and find a city that has a ghoul problem": the prose left the town for the forest
  trail, the line names no known place, so movement was "unresolved" and the player stayed in the clinic.
  T5, T10 and T12 were the same note.
* T13 "i rip her head from her shoulders, her spine comes out still connected ...": the draft wrote
  MOVE "Radiation Fenced Sanctuary Clinic" (where the player already was), resolve_movement threw that
  away as no move, and then its doorway reader read "comes ... out" as leaving the building: the server
  walked the player from the clinic (L3) to the town (L1) while the prose stayed at Beth's desk.

The fact that decides both is where the prose leaves the player, and only the prose knows it. So on every
player turn the engine lists its own answers, from its records, and asks the turn's model one plain
question with one letter for a reply (live on Hermes 3 8B: 45/45, 0.05-0.2 s):

    Where is the player at the end of this text?
    A) still in <the place they are in>
    B) in <the place around it>, outside <the place they are in>
    C) outside <the settlement>, on the road or in the wilds
    D) at <a known place named in the ending of the text>

The options are the current place, each place it stands in (parent_id), "outside" the outermost one,
and up to two other known places named (by code or stored name) in the ending of the text, the second
half of its sentences, in text order: a place left or looked at early in the scene is not offered.

One letter does not move the player alone (CLAUDE.md 2026-10-18: one ask fills it in, a second checks
it): a second question, always "are you still in <here>?", must agree (a move needs no, staying needs
yes); see confirm_prompt for why it is not the answer put back. ``settle`` then runs after resolve_movement, on what the movement
rules decided:

* a move the server made with no MOVE op, to a known place up the chain or elsewhere (venue_exit and the
  other known-place rules), is not made when the answer is the place the player is in (T13); when the
  answer is further out the same way ("outside the town" for a walk out of the clinic) it goes there;
* a turn the rules left in place (no travel read in the line, or travel with no place found) moves to
  the place answered: a place up the chain, a known place, or for "outside" the engine's own place
  "Outside <settlement>" (made once per settlement and kept), whose summary carries the line the
  player set off with (T6). "Still here" leaves them where they are.

Moves into a building (the venue rules), moves the draft wrote, and map walks keep their own rules (a
disagreement is noted in the ledger). A missing, failed, unclear or unconfirmed reply changes nothing.
Both asks go through app.llm._chat_text with the turn's own usage and trace lists, so their prompts, raw
replies and times are in the turn's trace file and model_logs (phase ``where_ended``).
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
QUESTION = 'In this text, "you" is the player. Where are you at the end of it?'
CONFIRM_SYSTEM = "Answer yes or no."

Ask = Callable[[str, str], str]
_ASK_OVERRIDE: list[Ask | None] = [None]

# Server moves this checks: a move to a known place, not a walk into a building
# (the venue rules check those against the prose themselves).
_CHECKED_RULES = frozenset({
    "venue_exit", "venue_exit_to", "player_input", "venue_return", "narration_code", "follow_named",
    "player_named",
})
# What the movement rules return when they left the player where they were.
_STAYED = frozenset({"unresolved", "not_travel"})


def set_ask(ask: Ask | None) -> Ask | None:
    """Use ``ask`` (system, user) -> reply text for both questions (None: the turn's model). Returns the previous one."""
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


def _ending_start(text: str) -> int:
    """Where the ending of the text begins: its second half by sentences (the last three at least)."""
    from app.prose_state import sentence_spans

    spans = sentence_spans(text)
    if len(spans) <= 3:
        return 0
    return spans[max(0, min(len(spans) // 2, len(spans) - 3))][0]


def _last_named_at(text: str, name: str, code: str) -> int:
    """The offset of the last mention of a place in ``text`` (its [[code]] or its whole stored name), or -1."""
    low = text.lower()
    at = -1
    if code:
        at = low.rfind(f"[[{code.lower()}]]")
    name = str(name or "").strip().lower()
    if name and len(name) >= 4:
        for found in re.finditer(rf"(?<![\w]){re.escape(name)}(?![\w])", low):
            at = max(at, found.start())
    return at


def build_options(conn, narration: str) -> dict[str, Any] | None:
    """The answers the engine has: here, each place around it, outside, known places the ending names."""
    from app.world import _is_settlement

    row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    here_id = int((row[0] if row else 0) or 0)
    chain = _chain(conn, here_id)
    if not chain:
        return None
    if any(not _named(r["name"]) for r in chain):
        # A place with no name cannot be asked about ("A) still in None", live round 2).
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
    # Known places named in the ending, nearest the end first, offered in text order.
    text = str(narration or "")
    ending = text[_ending_start(text):]
    chain_ids = {int(r["id"]) for r in chain}
    named: list[tuple[int, Any]] = []
    for other in conn.execute("SELECT id, code, name FROM locations ORDER BY id").fetchall():
        if int(other["id"]) in chain_ids or not _named(other["name"]):
            continue
        at = _last_named_at(ending, str(other["name"] or ""), str(other["code"] or ""))
        if at >= 0:
            named.append((at, other))
    for _at, other in sorted(sorted(named, key=lambda item: -item[0])[:MAX_KNOWN], key=lambda item: item[0]):
        options.append({"kind": "known", "id": int(other["id"]), "code": str(other["code"] or ""),
                        "name": str(other["name"] or ""), "label": f"at {other['name']}"})
    for i, option in enumerate(options):
        option["letter"] = chr(ord("A") + i)
    return {"here_id": here_id, "options": options}


def _named(name: Any) -> bool:
    text = str(name or "").strip()
    return bool(text) and text.lower() not in {"none", "null", "n/a", "unknown"}


def _plain(narration: str) -> str:
    return re.sub(r"\s*\[\[[^\]]*\]\]", "", str(narration or "")).strip()


def build_prompt(narration: str, options: list[dict[str, Any]]) -> tuple[str, str]:
    lines = [_plain(narration), "", QUESTION]
    lines += [f"{o['letter']}) {o['label']}" for o in options]
    return SYSTEM, "\n".join(lines)


def confirm_prompt(narration: str, here: dict[str, Any]) -> tuple[str, str]:
    """The second check, always about the place the player is in.

    Measured live on Hermes 3 8B (docs/showcase/ask-live-eval-2026-10-24.md, round 2): putting the
    chosen answer back ("is the player in <town>, outside <building>?") echoes the label (15 of 17
    yes whatever the text, T11 moved out of the clinic 3/3) and gets no yes/no for "on the road".
    "Are you still in <here>?" made no wrong move in 72: a move needs its "no", staying needs "yes".
    """
    return CONFIRM_SYSTEM, (
        f'{_plain(narration)}\n\nIn this text, "you" is the player. '
        f"At the end of it, are you still in {here['name']}? Answer yes or no."
    )


def confirms(choice: dict[str, Any], still_here: bool | None) -> bool | None:
    """Whether the check agrees with the letter: a move needs "not still here", staying needs "still here"."""
    if still_here is None:
        return None
    return still_here if choice.get("kind") == "here" else not still_here


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


def parse_yes(reply: Any) -> bool | None:
    """True for a reply that starts with yes, False for no, None for anything else."""
    first = re.match(r"^\W*(yes|no)\b", str(reply or "").strip(), re.I)
    return None if first is None else first.group(1).lower() == "yes"


# ----------------------------------------------------------------------- ask


def wants_ask(conn, result: dict[str, Any], player_input: str) -> bool:
    """Every player turn, except one with no line, an engine request, or a map walk (the grid decides that)."""
    from app.world import _player_line

    line = _player_line(player_input)
    if not line.strip() or line.lstrip().startswith("__"):
        return False
    return not result.get("map_walk")


def ask_where(conn, result: dict[str, Any], player_input: str, narration: str) -> dict[str, Any] | None:
    """Ask where the prose leaves the player, check the answer, and put both on ``result["_where_ended"]``."""
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
    record: dict[str, Any] = {"here_id": built["here_id"], "options": built["options"], "confirmed": None}

    def _one(system: str, user: str, key: str) -> str:
        started = time.time()
        try:
            reply = ask(system, user)
        except Exception as exc:
            record[f"{key}_error"] = f"{type(exc).__name__}: {exc}"[:200]
            reply = ""
        record[f"{key}_seconds"] = round(time.time() - started, 3)
        return str(reply or "")

    record["reply"] = _one(*build_prompt(narration, built["options"]), "reply")[:80]
    choice = parse_letter(record["reply"], built["options"])
    record["choice"] = choice
    if choice is not None:
        here = built["options"][0]
        record["confirm_reply"] = _one(*confirm_prompt(narration, here), "confirm")[:80]
        record["confirmed"] = confirms(choice, parse_yes(record["confirm_reply"]))
    turn_ledger.note("movement", "where_ended_asked", reply=record["reply"],
                     answer=(choice or {}).get("label") or "unclear", confirm=record.get("confirm_reply", ""),
                     confirmed=record["confirmed"],
                     seconds=round(float(record.get("reply_seconds") or 0) + float(record.get("confirm_seconds") or 0), 3))
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


def attacked_here(conn, result: dict[str, Any], here_id: int) -> str:
    """The code of a living person the turn's rolled attack was aimed at who is at ``here_id``, else "".

    The records decide it: the attack check's own target (app/attack_intent.py)
    and that person's row (alive, at the place the player is in).
    """
    from app.attack_intent import attack_target

    for check in result.get("skill_checks") or [] if isinstance(result, dict) else []:
        code = attack_target(check)
        if not code or not isinstance(check, dict) or check.get("natural") is None:
            continue
        try:
            row = conn.execute("SELECT location_id, died_turn FROM npcs WHERE UPPER(code) = ?", (code,)).fetchone()
        except Exception:
            row = None
        if row is not None and int(row["location_id"] or 0) == int(here_id) and int(row["died_turn"] or 0) == 0:
            return code
    return ""


def settle(conn, result: dict[str, Any], report: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Act on a checked answer: refuse an unshown server move, or move a player the rules left in place."""
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
    if record.get("confirmed") is not True:
        # One letter alone moves nobody: the check said no, or gave no answer.
        turn_ledger.note("movement", "where_ended_not_confirmed", answer=choice["label"],
                         confirm=str(record.get("confirm_reply") or ""))
        report["where_ended_confirmed"] = False
        return report
    # The checked answer rides on the report: a part of a place reached this
    # turn is filed where the scene ended, not in the place left (drift eval, combined T2).
    report["where_ended_choice"] = {k: choice.get(k) for k in ("kind", "id", "code", "name", "top_id", "letter")}
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
                    "rule": "where_ended_here", "dropped_rule": rule, "where_ended": report["where_ended"],
                    "where_ended_choice": report["where_ended_choice"]}
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

    if status in _STAYED and not result.get("map_walk"):
        if choice["kind"] == "here":
            turn_ledger.note("movement", "stays_as_shown", place=choice["name"], status=status)
            return report
        aimed = attacked_here(conn, result, int(record.get("here_id") or 0)) if status == "not_travel" else ""
        if aimed:
            # The line asked for no travel and its act was aimed at someone in
            # this room: a scene that ends elsewhere drifted (integ-r4 T3).
            turn_ledger.note("movement", "move_from_prose_refused", answer=choice["label"], attacked=aimed,
                             why="the line attacks someone here and asks for no travel")
            report["where_ended_refused"] = "act_aimed_here"
            return report
        move_to(choice)
        turn_ledger.note("movement", "move_from_prose", destination=choice["name"], kind=choice["kind"], status=status)
        out = {"status": "repaired", "rule": "where_ended_outside" if choice["kind"] == "outside" else "where_ended",
               "from": report.get("from"), "destination": choice["name"], "where_ended": report["where_ended"],
               "was": status, "where_ended_choice": report["where_ended_choice"]}
        if report.get("follow"):
            out["follow"] = report["follow"]
        return out

    # The draft's own MOVE, a walk into a building, a map walk: their rules
    # stand. A different answer is kept for measurement.
    dest = _destination_row(conn, patch) if status in {"model", "repaired"} else None
    dest_id = int(dest["id"]) if dest is not None else int(record.get("here_id") or 0)
    if int(choice.get("id") or 0) != dest_id or choice["kind"] == "outside":
        turn_ledger.note("movement", "where_ended_disagrees", status=status, rule=rule, answer=choice["label"],
                         destination=str(dest["name"] or "") if dest is not None else "")
    return report
