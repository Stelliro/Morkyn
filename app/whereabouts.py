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
    interpreter's presence pair, "Is <Name> with the player at the end of
    it?" yes and "Has the player walked away from <Name> at the end of it?"
    no (interpreter.with_player, ``file_shown_people``).

Unless the records say plainly they are elsewhere (no model ask, the records
and the prose's own structure):

  * shown at another place: the last sentence that names them and a place
    (``places_named``: the engine's place matching, by code, a full or
    two-word name only one place has, or the one place near the player of
    that kind or head word, "the clinic", "the town hall") names the place
    they are filed at and not the player's ("Through the window you see Bram
    crossing the Sanctuary [[L1]]" from inside the clinic keeps Bram in the
    town), or names the place the player left this turn ("Kim [[B]] waves
    from the Sanctuary [[L1]] gate as you go in"). A sentence that names the
    player's place puts them here;
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

# How far up the place tree "the places the player's place stands in" goes.
_MAX_DEPTH = 8


def here_id(conn) -> int:
    try:
        row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        return int((row[0] if row else 0) or 0)
    except Exception:
        return 0


def _matcher(conn):
    """The interpreter's matcher over the whole roster: a code, or a full name only one row has."""
    from app.interpreter import Matcher, clean_name

    people = [
        {"id": int(r["id"]), "code": str(r["code"] or ""), "name": clean_name(r["name"])}
        for r in conn.execute("SELECT id, code, name FROM npcs").fetchall()
    ]
    places = [
        {"id": int(r["id"]), "code": str(r.get("code") or ""), "name": clean_name(r.get("name")),
         "parent_id": int(r.get("parent_id") or 0), "kind": str(r.get("kind") or ""), "plot_id": str(r.get("plot_id") or "")}
        for r in (dict(row) for row in conn.execute("SELECT * FROM locations").fetchall())
    ]
    return Matcher(people, places)


def near(match, here: int, also: Iterable[int] = ()) -> set[int]:
    """The places a short common noun can mean from where the player is: the
    player's place, the places it stands in, what stands in any of those, and ``also``."""
    by_id = {p["id"]: p for p in match.places}
    chain: list[int] = []
    at = int(here or 0)
    while at and at in by_id and at not in chain and len(chain) < _MAX_DEPTH:
        chain.append(at)
        at = int(by_id[at].get("parent_id") or 0)
    out = set(chain) | {p["id"] for p in match.places if int(p.get("parent_id") or 0) in chain}
    return out | {int(i) for i in also if int(i or 0) in by_id}


def _blank(text: str, spans: Iterable[tuple[int, int]]) -> str:
    for start, end in spans:
        text = text[:start] + " " * (end - start) + text[end:]
    return text


def places_named(sentence: str, match, near_ids: Iterable[int]) -> set[int]:
    """The recorded places a sentence names outside quoted speech, by the engine's place matching.

    Longest first, each mention used once: a [[L#]] code or a full name only
    one place has (interpreter.Matcher); the last two words of a name side by
    side when only one place has them ("the town hall" for "Radiation Fenced
    Sanctuary Town Hall", world.place_pair_span, as a move is read); then a
    head word (the last word of a place's name, world._place_words) or the
    labels of its kind (venues.kind_family_labels) when only one place in
    ``near_ids`` has it ("the clinic"). A word two places share names neither.
    """
    import re

    from app import venues
    from app.world import _place_words, place_pair_span

    text = venues.strip_speech(str(sentence or ""))
    found: set[int] = set()
    for place in sorted(match.places, key=lambda p: -len(str(p.get("name") or ""))):
        spans = match.spans(text, place)
        if spans:
            found.add(place["id"])
            text = _blank(text, spans)
    low = text.lower()
    words = {p["id"]: _place_words(str(p.get("name") or "")) for p in match.places}
    pairs: dict[tuple[str, str], list[int]] = {}
    for pid, w in words.items():
        if len(w) >= 2:
            pairs.setdefault((w[-2], w[-1]), []).append(pid)
    for pair, ids in pairs.items():
        span = place_pair_span(low, list(pair)) if len(ids) == 1 else None
        if span is not None:
            found.add(ids[0])
            low = _blank(low, [span])
    by_id = {p["id"]: p for p in match.places}
    heads: dict[str, set[int]] = {}
    for pid in near_ids:
        place = by_id.get(int(pid))
        if place is None:
            continue
        own = set(words.get(place["id"])[-1:]) | set(venues.kind_family_labels(venues.row_kind(place)))
        for head in own:
            if len(head) >= 3:
                heads.setdefault(head, set()).add(place["id"])
    for head, ids in heads.items():
        if len(ids) == 1 and re.search(rf"(?<![\w'’-]){re.escape(head)}(?:e?s)?(?![\w-])", low):
            found |= ids
    return found


def placed_by_prose(text: str, person: dict[str, Any], filed: int, here: int, left: int, match) -> str:
    """"elsewhere", "here" or "": what the last sentence naming this person and a place says.

    "elsewhere": it names the place they are filed at and not the player's
    (or names the place the player just left). "here": it names the player's place.
    """
    from app.interpreter import units
    from app.venues import strip_speech

    around_here = near(match, here, (filed, left))
    verdict = ""
    for _a, _b, sentence in units(text):
        if not match.names(strip_speech(sentence), person):
            continue
        named = places_named(sentence, match, around_here)
        if filed and filed != here and filed in named and (filed == left or here not in named):
            verdict = "elsewhere"
        elif here in named:
            verdict = "here"
    return verdict


def _person(match, npc_id: int) -> dict[str, Any] | None:
    return next((p for p in match.people if p["id"] == int(npc_id)), None)


def talked_about(text: str, person: dict[str, Any], match) -> bool:
    """The prose names them, and only inside quoted speech."""
    from app.venues import strip_speech

    return match.names(text, person) and not match.names(strip_speech(text), person)


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
    verdict = placed_by_prose(text, person, filed, here, left, match)
    if verdict == "elsewhere":
        return filed, "shown_elsewhere"
    # "You thank Aldric and step out onto Low Street" names the player's new
    # place in the leaving sentence; he is still left behind.
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
