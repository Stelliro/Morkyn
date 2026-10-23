"""Person or place: the one question asked before a name is filed (#155, #152).

The engine mints people and places from names. A name it reads out of the
prose ("New Vegas, the minigun cradled in your armored fist") can be either,
and the shape of the sentence does not say which: Hermes 3 8B run cc87dd29 T2
filed the city New Vegas as NPC A because the player "set off to New Vegas to
fight a Deathclaw". So, before apply_turn files anyone:

1. A name the engine itself reads out of the prose (world._introduced_people)
   is a place when a record says so (a place this turn's ops name: LOC_NEW,
   MOVE, a job's AT); otherwise one small plain ask decides:
   'In this text, is "New Vegas" a person or a place?'
2. When the ops and the records disagree (NPC_NEW under a place's name, or
   LOC_NEW under a roster person's name), the same ask decides.

Each ask goes through llm._chat_text, so its prompt, raw reply and seconds are
in the turn's trace (model_trace) and model_usage like every other call, and
its decision is a turn_ledger note. A name settled as a place is never filed as
a person; a name settled as a person is never filed as a place.

The same file holds the reference binding of #152: a place the player's line
names ("I go into the clinic") is the place the chat last showed with that
word, by its code ([[L3]]), before any matching by name.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app import turn_ledger

# The ask: one question, a one-word answer.
KIND_SYSTEM = "Answer with one word: person or place."
KIND_QUESTION = 'In this text, is "{name}" a person or a place?'
KIND_PHASE = "entity_kind"
KIND_MAX_TOKENS = 4
# At most this many asks in one turn; a name past them is filed as before.
MAX_ASKS = 3

Ask = Callable[..., str]
_ASK_OVERRIDE: list[Ask | None] = [None]


def set_kind_ask(ask: Ask | None) -> Ask | None:
    """Use ``ask`` for the kind question (None: the turn's own model). Returns the previous one."""
    previous = _ASK_OVERRIDE[0]
    _ASK_OVERRIDE[0] = ask
    return previous


def _model_ask(system: str, user: str, *, trace: list | None, usage: list | None) -> str:
    """The turn's own model, through the plain-text call path that records the
    prompt, the raw reply and the seconds in the turn's trace and usage."""
    from app.llm import _chat_text

    return _chat_text(
        system, user, timeout=60, usage=usage, phase=KIND_PHASE, max_tokens=KIND_MAX_TOKENS,
        trace=trace, temperature=0.0,
    )


def _ask() -> Ask:
    return _ASK_OVERRIDE[0] or _model_ask


def read_kind(reply: Any) -> str:
    """'person', 'place', or '' when the reply is neither or both."""
    words = set(re.findall(r"[a-z]+", str(reply or "").lower()))
    person, place = "person" in words, "place" in words
    if person == place:
        return ""
    return "person" if person else "place"


# ------------------------------------------------------------------ records


def _norm(name: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\s*\[\[[^\]]*\]\]", "", str(name or ""))).strip().lower()


def turn_place_names(result: dict[str, Any] | None) -> set[str]:
    """Places this turn's own ops name: new places, the move, a job's place."""
    if not isinstance(result, dict):
        return set()
    names: set[str] = set()
    for loc in result.get("locations") or []:
        if isinstance(loc, dict):
            names.add(_norm(loc.get("name")))
    player = result.get("player") if isinstance(result.get("player"), dict) else {}
    names.add(_norm(player.get("move_to_location")))
    for mark in result.get("quest_marks") or []:
        if isinstance(mark, dict):
            names.add(_norm(mark.get("location")))
    names.discard("")
    return names


def _kinds(result: dict[str, Any] | None) -> dict[str, str]:
    kinds = result.get("_entity_kinds") if isinstance(result, dict) else None
    return kinds if isinstance(kinds, dict) else {}


def settled_places(result: dict[str, Any] | None) -> set[str]:
    """Names this turn settled as places (by a record or by the ask)."""
    return {str(name) for name, kind in _kinds(result).items() if kind == "place"}


def settled_person(result: dict[str, Any] | None, name: Any) -> bool:
    """The ask settled this name as a person this turn."""
    return _kinds(result).get(_norm(name)) == "person"


def not_people(result: dict[str, Any] | None) -> set[str]:
    """Names the prose-reading mint must not file as a person (lower case):
    places this turn names, and names settled as places, unless the ask
    settled them as people."""
    kinds = _kinds(result)
    return {n for n in turn_place_names(result) if kinds.get(n) != "person"} | settled_places(result)


def drop_places_from_people(conn, npcs: list[Any], result: dict[str, Any] | None) -> list[Any]:
    """New people (no code) whose name this turn settled as a place are not filed."""
    places = settled_places(result)
    if not places:
        return npcs
    kept: list[Any] = []
    for npc in npcs:
        name = _norm(npc.get("name")) if isinstance(npc, dict) else ""
        if name and name in places and not str(npc.get("code") or "").strip():
            turn_ledger.note("npc", "place_not_person", name=str(npc.get("name") or ""))
            continue
        kept.append(npc)
    return kept


# --------------------------------------------------------------- the ask


def _sentences_naming(text: str, name: str, limit: int = 2) -> list[str]:
    flat = re.sub(r"\s+", " ", re.sub(r"\s*\[\[[^\]]*\]\]", "", str(text or ""))).strip()
    pattern = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.I)
    hits = [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if pattern.search(s)]
    return hits[:limit]


def _ask_text(name: str, narration: str, player_line: str) -> str:
    """The player's line when it names the name, then the scene's first two sentences naming it."""
    parts = []
    line = re.sub(r"\s+", " ", str(player_line or "")).strip()
    if line and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", line, re.I):
        parts.append(line)
    parts.extend(s for s in _sentences_naming(narration, name) if s not in parts)
    return " ".join(parts)[:700]


def kind_prompt(name: str, narration: str, player_line: str) -> str:
    """The user half of the ask, exactly as sent."""
    return f"Text: {_ask_text(name, narration, player_line)}\n{KIND_QUESTION.format(name=name)}"


def settle_kinds(result: dict[str, Any], player_input: str, *, ask: bool = True) -> dict[str, str]:
    """Settle which names this turn would file as the wrong kind; called before apply_turn.

    Verdicts go on ``result["_entity_kinds"]`` (lower-case name -> "person" or
    "place"); apply_turn and the prose mint read them. ``ask=False`` (the
    offline narrator) keeps to the records.
    """
    if not isinstance(result, dict):
        return {}
    from app import world
    from app.db import connect

    narration = world._narration_text_of(result)
    if not narration.strip():
        return {}
    try:
        with connect().closing() as conn:
            roster = [str(r[0] or "") for r in conn.execute("SELECT name FROM npcs").fetchall()]
            try:
                player_names = [
                    str(v or "") for row in conn.execute("SELECT name, public_name FROM player").fetchall()
                    for v in (row[0], row[1]) if str(v or "").strip()
                ]
            except Exception:
                player_names = []
            places = [str(r[0] or "") for r in conn.execute("SELECT name FROM locations").fetchall()]
    except Exception:
        return {}
    roster_keys = {_norm(n) for n in roster} - {""}
    place_keys = {_norm(n) for n in places} - {""}
    records = turn_place_names(result)
    op_people = [
        str(n.get("name") or "").strip() for n in result.get("npcs") or []
        if isinstance(n, dict) and str(n.get("name") or "").strip() and not str(n.get("code") or "").strip()
    ]

    # (name, the record that disagrees or "" for the engine's own guess)
    questions: list[tuple[str, str]] = []
    kinds: dict[str, str] = {}
    # 1. People the engine reads out of the prose.
    for person in world._introduced_people(narration, roster + player_names + op_people, set(places)):
        name = str(person.get("name") or "").strip()
        key = _norm(name)
        if not key or key in kinds:
            continue
        if key in records:
            kinds[key] = "place"
            turn_ledger.note("npc", "name_is_a_place", name=name, by="record")
        else:
            questions.append((name, "prose"))
    # 2. A new person the ops file under a place's name.
    for name in op_people:
        key = _norm(name)
        if key and key not in roster_keys and (key in place_keys or key in records) and key not in kinds:
            questions.append((name, "op_person_named_as_place"))
    # 3. A new place the ops file under a roster person's name.
    for loc in result.get("locations") or []:
        name = str(loc.get("name") or "").strip() if isinstance(loc, dict) else ""
        key = _norm(name)
        if key and key not in place_keys and key in roster_keys and key not in kinds:
            questions.append((name, "op_place_named_as_person"))

    trace = result.get("_model_trace") if isinstance(result.get("_model_trace"), list) else None
    usage = result.get("_model_usage") if isinstance(result.get("_model_usage"), list) else None
    line = world._player_line(player_input)
    asked: set[str] = set()
    for name, why in questions:
        key = _norm(name)
        if not ask or key in asked or key in kinds or len(asked) >= MAX_ASKS:
            continue
        asked.add(key)
        try:
            reply = _ask()(KIND_SYSTEM, kind_prompt(name, narration, line), trace=trace, usage=usage)
        except Exception as exc:
            turn_ledger.note("npc", "kind_ask_failed", name=name, why=why, error=f"{type(exc).__name__}: {exc}"[:160])
            continue
        kind = read_kind(reply)
        if not kind:
            turn_ledger.note("npc", "kind_unread", name=name, why=why, reply=str(reply or "")[:80])
            continue
        kinds[key] = kind
        turn_ledger.note("npc", "name_is_a_place" if kind == "place" else "name_is_a_person", name=name, by="ask", why=why)
    if kinds:
        result["_entity_kinds"] = {**_kinds(result), **kinds}
    return kinds


# ------------------------------------------------- places by the chat's code


_CODE_RE = re.compile(r"\[\[(L\d+)\]\]", re.I)
_TYPED_CODE_RE = re.compile(r"#(L\d+)\b|\[\[(L\d+)\]\]", re.I)
_LABEL_STOP_RE = re.compile(r"[.!?;:\"“”(\]]")


def chat_narrations(conn, limit: int = 3) -> list[str]:
    """The last few scenes the player was shown, newest first, codes kept."""
    try:
        return [
            str(r[0] or "")
            for r in conn.execute(
                "SELECT content FROM journal WHERE kind = 'narration' ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        ]
    except Exception:
        return []


def _bare(word: str) -> str:
    return re.sub(r"['’]s$", "", word.lower())


def _heads(text: str, at: int, stored_name: str) -> set[str]:
    """The words a line can name a place by: the last word of its stored name,
    and the common noun the chat showed its code on ('the clinic [[L3]]').

    A capitalised word the stored name does not have is someone else's name
    the code was put on ('Jonah [[L1]]', cc87dd29 T14), not this place's."""
    stored = [_bare(w) for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", stored_name)]
    heads = {stored[-1]} if stored else set()
    before = _CODE_RE.sub(" ", _LABEL_STOP_RE.split(text[max(0, at - 80): at])[-1])
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", before)
    if words:
        shown = words[-1]
        if shown[:1].islower() or _bare(shown) in stored:
            heads.add(_bare(shown))
    return {h for h in heads if len(h) >= 4}


def place_shown_in_chat(rows: list[Any], player_input: str, chat: list[str] | None, current_name: str = "") -> Any:
    """The known place the player's line goes to, read by reference (#152).

    First a place code the player typed (#L3); then the place the chat showed
    most recently under a word the line goes to ("I go into the clinic" after
    "... the clinic [[L3]]"). None leaves the matching by name to decide.
    """
    from app import world

    by_code = {str(r["code"] or "").upper(): r for r in rows if r["code"]}
    if not by_code:
        return None
    current = _norm(current_name)
    line = world._player_line(player_input)
    for m in _TYPED_CODE_RE.finditer(line):
        row = by_code.get((m.group(1) or m.group(2) or "").upper())
        if row is not None and _norm(row["name"]) != current:
            turn_ledger.note("movement", "place_bound_by_typed_code", code=str(row["code"]), place=str(row["name"] or ""))
            return row
    if not chat:
        return None
    dest = f" {world._destination_text(player_input).lower()} "
    for text in chat:
        for m in reversed(list(_CODE_RE.finditer(text or ""))):
            row = by_code.get(m.group(1).upper())
            if row is None or _norm(row["name"]) == current:
                continue
            for head in _heads(text, m.start(), str(row["name"] or "")):
                for hit in re.finditer(rf"(?<![\w'’-]){re.escape(head)}s?(?![\w'’-])", dest):
                    # Gone to: a going word with at most an article and a few
                    # describing words before the noun ("into the old clinic").
                    clause = re.split(r"[.!?;,]", dest[: hit.start()])[-1]
                    goings = list(world._GOING_WORD_RE.finditer(clause))
                    if not goings or not re.fullmatch(r"\s*(?:[\w'’-]+\s+){0,3}", clause[goings[-1].end():]):
                        continue
                    if world._code_is_origin(dest, hit.start(), hit.end()):
                        continue
                    turn_ledger.note("movement", "place_bound_by_chat_code", word=head, code=str(row["code"]),
                                     place=str(row["name"] or ""))
                    return row
    return None
