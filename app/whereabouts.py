"""Where the people met are: the player's place (#33).

CLAUDE.md, Design decisions, "Where the player is, the people met are"
(2026-10-24): "play state needs to be in the same location as npc and hadded
to the llm to ensure that the llm knows where the player is". A person the
player meets is filed at the player's place, and the narrator is always told
plainly where the player is (prompts._place_view: "player_is_in").

Fault class: a person row got its place from whichever write made it, at that
moment of the turn. NPC ops are applied before the player's move, the prose
seeding after it, a sketch keeps the place of the turn it was drawn in, and an
op's LOC may be the place the context showed before the walk. The final
replay of 2026-10-24 (Hermes 3 8B): T1 "I go into the clinic." showed Nate at
his workbench inside the clinic, but his row stayed in the town, so at T3
"i shoot Nate" the attack found nobody at the player's place.

The decision is made once, here, at the end of the turn, when the player's
place is final (``decide``):

  * A person the turn introduced (a row made this turn, by an op, the prose
    seeding, a figure hint or a sketch, ``file_new_people``) is filed where
    the player is.
  * Someone already on record elsewhere is moved there only when the turn
    shows them with the player: the scene cast and the called person
    (world._move_cast_here, conversation.bring_called_here, as before), or the
    interpreter's measured hold ask "Does <Name> say or do anything in it?"
    answering yes (interpreter.with_player, ``file_shown_people``).

Unless the records say plainly they are elsewhere (no model ask, the records
and the prose's own structure):

  * shown at another place: a sentence names them and a place on record that
    is not the player's and not one the player's place stands in (a clinic is
    in its town), or the place the player left this turn ("Kim [[B]] waves
    from the Sanctuary [[L1]] gate as you go in");
  * talked about: every mention of them is inside quoted speech ("The mayor's
    at the town hall," Kim says);
  * left behind: the player left their place this turn and the prose names
    them only before the leaving (world.after_player_leaves).

A row moved here that existed before the turn is added to the turn's rewind
record first; rows made this turn are deleted by a rewind anyway. The dead are
never moved (their bodies are interpreter.place_bodies' and carry_bodies').
Every decision is a turn_ledger note. Nothing here may break a turn.
"""
from __future__ import annotations

from typing import Any, Iterable

from app import turn_ledger

# How far up the place tree "the place the player's place stands in" goes.
_MAX_DEPTH = 8


def here_id(conn) -> int:
    try:
        row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        return int((row[0] if row else 0) or 0)
    except Exception:
        return 0


def around(conn, place_id: int) -> set[int]:
    """The places ``place_id`` stands in (its parent, the parent's parent, ...), not itself."""
    out: set[int] = set()
    at = int(place_id or 0)
    for _ in range(_MAX_DEPTH):
        try:
            row = conn.execute("SELECT parent_id FROM locations WHERE id = ?", (at,)).fetchone()
        except Exception:
            break
        up = int((row[0] if row else 0) or 0)
        if not up or up in out or up == int(place_id or 0):
            break
        out.add(up)
        at = up
    return out


def _matcher(conn):
    """The interpreter's matcher over the whole roster: a code, or a full name only one row has."""
    from app.interpreter import Matcher, clean_name

    people = [
        {"id": int(r["id"]), "code": str(r["code"] or ""), "name": clean_name(r["name"])}
        for r in conn.execute("SELECT id, code, name FROM npcs").fetchall()
    ]
    places = [
        {"id": int(r["id"]), "code": str(r["code"] or ""), "name": clean_name(r["name"])}
        for r in conn.execute("SELECT id, code, name FROM locations").fetchall()
    ]
    return Matcher(people, places)


def _person(match, npc_id: int) -> dict[str, Any] | None:
    return next((p for p in match.people if p["id"] == int(npc_id)), None)


def talked_about(text: str, person: dict[str, Any], match) -> bool:
    """The prose names them, and only inside quoted speech."""
    from app.venues import strip_speech

    return match.names(text, person) and not match.names(strip_speech(text), person)


def shown_at(text: str, person: dict[str, Any], place_id: int, match) -> bool:
    """A sentence of the prose names both the person and the place."""
    from app.interpreter import units

    place = next((p for p in match.places if p["id"] == int(place_id or 0)), None)
    if place is None:
        return False
    return any(match.names(s, person) and match.names(s, place) for _a, _b, s in units(text))


def decide(conn, npc_id: int, text: str, *, here: int, here_at_start: int = 0, match=None) -> tuple[int, str]:
    """(the place this person is filed at, why) once the turn is over: the player's place unless plainly elsewhere."""
    row = conn.execute("SELECT location_id, died_turn FROM npcs WHERE id = ?", (int(npc_id),)).fetchone()
    if row is None:
        return 0, "no_row"
    filed = int(row["location_id"] or 0)
    if int(row["died_turn"] or 0) > 0:
        return filed, "dead"
    if not here or filed == here:
        return filed, "here"
    match = match or _matcher(conn)
    person = _person(match, npc_id)
    if person is None:
        return here, "filed_here"
    if talked_about(text, person, match):
        return filed, "talked_about"
    left = int(here_at_start or 0) if int(here_at_start or 0) != here else 0
    if filed and (filed not in around(conn, here) or filed == left) and shown_at(text, person, filed, match):
        return filed, "shown_elsewhere"
    if left and filed == left and match.names(text, person):
        from app.world import after_player_leaves

        if not match.names(after_player_leaves(text), person):
            return filed, "left_behind"
    return here, "filed_here"


def _move(conn, turn: int, npc_id: int, place_id: int) -> None:
    from app.interpreter import keep_for_rewind

    keep_for_rewind(conn, int(turn), "npcs", int(npc_id))  # a row made this turn is skipped: the rewind deletes it
    conn.execute("UPDATE npcs SET location_id = ? WHERE id = ?", (int(place_id), int(npc_id)))


def _settle(conn, turn: int, ids: Iterable[int], text: str, here_at_start: int, area: str) -> list[dict[str, Any]]:
    here = here_id(conn)
    if not here:
        return []
    match = _matcher(conn)
    out: list[dict[str, Any]] = []
    for npc_id in ids:
        try:
            row = conn.execute("SELECT code, name, location_id FROM npcs WHERE id = ?", (int(npc_id),)).fetchone()
            if row is None:
                continue
            was = int(row["location_id"] or 0)
            place, why = decide(conn, int(npc_id), text, here=here, here_at_start=here_at_start, match=match)
            entry = {"code": str(row["code"] or ""), "name": str(row["name"] or ""), "was": was, "now": place, "why": why}
            if why in ("here", "dead", "no_row"):
                continue
            if place and place != was:
                _move(conn, turn, int(npc_id), place)
            out.append(entry)
            turn_ledger.note("npc", area, **entry)
        except Exception as exc:  # never break a turn
            turn_ledger.note("npc", f"{area}_failed", npc_id=int(npc_id), error=f"{type(exc).__name__}: {exc}"[:200])
    return out


def introduced_ids(conn, max_id_before: int, text: str, turn_npcs: Any) -> list[int]:
    """Rows made this turn that the turn shows: named in the prose, or one of its people (ops, seeding, figures).

    One the engine already marked as only spoken of (world._file_people_at_unshown_places:
    a place known only from speech or hearsay) is someone talked about, not met.
    """
    def key_of(name: Any) -> str:
        return " ".join(str(name or "").lower().split())

    people = [n for n in (turn_npcs or []) if isinstance(n, dict)]
    spoken = {key_of(n.get("name")) for n in people if n.get("_spoken_of")}
    names = {key_of(n.get("name")) for n in people if not n.get("_spoken_of")}
    codes = {str(n.get("code") or "").strip().upper() for n in people if not n.get("_spoken_of")}
    names.discard("")
    codes.discard("")
    match = _matcher(conn)
    out: list[int] = []
    for row in conn.execute("SELECT id, code, name FROM npcs WHERE id > ? ORDER BY id", (int(max_id_before or 0),)).fetchall():
        person = _person(match, int(row["id"]))
        key = key_of(row["name"])
        if key in spoken:
            turn_ledger.note("npc", "filed_at_player_place", code=str(row["code"] or ""), name=str(row["name"] or ""),
                             why="spoken_of")
            continue
        if key in names or str(row["code"] or "").upper() in codes or (person is not None and match.names(text, person)):
            out.append(int(row["id"]))
    return out


def file_new_people(conn, turn: int, max_id_before: int, text: str, turn_npcs: Any = None, here_at_start: int = 0) -> list[dict[str, Any]]:
    """Everyone this turn introduced is filed at the player's place, unless plainly elsewhere."""
    try:
        ids = introduced_ids(conn, max_id_before, text, turn_npcs)
    except Exception as exc:
        turn_ledger.note("npc", "filed_at_player_place_failed", error=f"{type(exc).__name__}: {exc}"[:200])
        return []
    return _settle(conn, turn, ids, text, here_at_start, "filed_at_player_place")


def file_shown_people(conn, turn: int, codes: Iterable[str], text: str, here_at_start: int = 0) -> list[dict[str, Any]]:
    """People on record elsewhere whom the scene shows with the player (by code) are moved to the player's place."""
    ids: list[int] = []
    for code in codes or []:
        try:
            row = conn.execute("SELECT id FROM npcs WHERE UPPER(code) = ?", (str(code or "").strip().upper(),)).fetchone()
        except Exception:
            row = None
        if row is not None and int(row["id"]) not in ids:
            ids.append(int(row["id"]))
    return _settle(conn, turn, ids, text, here_at_start, "shown_with_player")
