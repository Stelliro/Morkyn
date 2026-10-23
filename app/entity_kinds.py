"""Person or place, and the place a line goes to: small asks before a turn is filed (#155, #152).

The engine mints people and places from names. A name it reads out of the
prose ("New Vegas, the minigun cradled in your armored fist") or out of the
model's own ops (NPC_NEW "Megaton", QUEST AT "Mattias Slade") can be either,
and neither the sentence's shape nor the op says which: Hermes 3 8B run
cc87dd29 T2 filed the city New Vegas as NPC A because the player "set off to
New Vegas to fight a Deathclaw". So, before apply_turn files anyone, outside
its write block:

1. Every new name the turn would file (a person the engine reads out of the
   prose, a new person or place the ops write) is a candidate. The engine's
   own records decide what they can (a stored place is never read as a new
   person); the model's ops are candidates, not records. One small plain ask
   decides each one: 'In this text, is "New Vegas" a person or a place?'.
   Only the offline narrator, whose ops the engine wrote, is read as a record.
2. A quoted line no known person says still seeds a stranger in
   world._ensure_npcs_from_narration. When the turn files nobody, one ask
   checks that a person says it ('A new message blinks into existence:
   "New target detected."' is a readout, not a stranger).
3. #152, places by reference: the place the player's line goes to is first a
   place the line names outright (world's name matching), then a place code
   the line types (#L3) or the chat last showed under a word the line uses
   ("I go into the clinic" after "... clinic [[L3]]"). That reference is a
   candidate; one ask checks the player is the one going there ('I tell Beth
   to go to the clinic' is not the player going).

Each ask goes through llm._chat_text, so its prompt, raw reply and seconds are
in the turn's trace (model_trace) and model_usage like every other call, and
its decision is a turn_ledger note. A reply the engine cannot read changes
nothing: the turn is filed as it was before these asks.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app import turn_ledger

# The kind ask: one question, a one-word answer (Hermes 3 8B: 54/54, live eval 2026-10-23).
KIND_SYSTEM = "Answer with one word: person or place."
KIND_QUESTION = 'In this text, is "{name}" a person or a place?'
KIND_PHASE = "entity_kind"
KIND_MAX_TOKENS = 4
# The yes/no asks.
YES_NO_SYSTEM = "Answer yes or no."
# Measured live on Hermes 3 8B (round 2): "does a person say" took a written note and graffiti for a
# speaker; "spoken by someone" scored 42/42 and kept unseen voices.
SPEAKER_QUESTION = 'In this text, is "{quote}" spoken by someone?'
SPEAKER_PHASE = "quote_speaker"
GOING_QUESTION = "Is the player going to {place}?"
GOING_PHASE = "place_going"
YES_NO_MAX_TOKENS = 4
# At most this many kind asks in one turn; a name past them is filed as before.
MAX_ASKS = 6
# At most this many places checked for one line.
MAX_GOING_ASKS = 2

Ask = Callable[..., str]
_ASK_OVERRIDE: list[Ask | None] = [None]


def set_kind_ask(ask: Ask | None) -> Ask | None:
    """Use ``ask`` for this module's asks (None: the turn's own model). Returns the previous one.

    ``ask(system, user, *, trace, usage, phase, max_tokens)`` returns the reply text.
    """
    previous = _ASK_OVERRIDE[0]
    _ASK_OVERRIDE[0] = ask
    return previous


def _model_ask(system: str, user: str, *, trace: list | None, usage: list | None,
               phase: str = KIND_PHASE, max_tokens: int = KIND_MAX_TOKENS) -> str:
    """The turn's own model, through the plain-text call path that records the
    prompt, the raw reply and the seconds in the turn's trace and usage."""
    from app.llm import _chat_text

    return _chat_text(
        system, user, timeout=60, usage=usage, phase=phase, max_tokens=max_tokens,
        trace=trace, temperature=0.0,
    )


def _ask() -> Ask:
    return _ASK_OVERRIDE[0] or _model_ask


def read_kind(reply: Any) -> str:
    """'person' or 'place' when the reply opens on it, else '' (unread)."""
    m = re.match(r"\W*(person|place)\b", str(reply or "").lower())
    return m.group(1) if m else ""


def read_yes_no(reply: Any) -> bool | None:
    """True or False when the reply opens on yes or no, else None (unread)."""
    m = re.match(r"\W*(yes|no)\b", str(reply or "").lower())
    return None if not m else m.group(1) == "yes"


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
    """Names this turn settled as places (by the ask, or the offline narrator's own ops)."""
    return {str(name) for name, kind in _kinds(result).items() if kind == "place"}


def settled_person(result: dict[str, Any] | None, name: Any) -> bool:
    """The ask settled this name as a person this turn."""
    return _kinds(result).get(_norm(name)) == "person"


def not_people(result: dict[str, Any] | None) -> set[str]:
    """Names the prose-reading mint must not file as a person (lower case): the
    names this turn settled as places. A model op naming a place is not enough
    on its own: QUEST AT "Mattias Slade" over "Mattias Slade, the courier"."""
    return settled_places(result)


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


def quote_not_spoken(result: dict[str, Any] | None) -> list[str]:
    """Quoted lines the speaker ask said no person says (they seed no stranger)."""
    quotes = result.get("_quotes_not_spoken") if isinstance(result, dict) else None
    return [str(q) for q in quotes] if isinstance(quotes, list) else []


# --------------------------------------------------------------- the asks


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
    """The user half of the kind ask, exactly as sent."""
    return f"Text: {_ask_text(name, narration, player_line)}\n{KIND_QUESTION.format(name=name)}"


def _call(system: str, user: str, phase: str, max_tokens: int, trace, usage) -> str:
    return _ask()(system, user, trace=trace, usage=usage, phase=phase, max_tokens=max_tokens)


def settle_kinds(result: dict[str, Any], player_input: str, *, ask: bool = True) -> dict[str, str]:
    """Settle person or place for every new name this turn would file; called before apply_turn.

    Verdicts go on ``result["_entity_kinds"]`` (lower-case name -> "person" or
    "place"); apply_turn and the prose mint read them. The same call runs the
    speaker check and the place-reference check (see the module notes).
    ``ask=False`` (the offline narrator, whose ops the engine wrote) reads
    those ops as records and asks nothing.
    """
    if not isinstance(result, dict):
        return {}
    from app import world
    from app.db import connect

    narration = world._narration_text_of(result)
    trace = result.get("_model_trace") if isinstance(result.get("_model_trace"), list) else None
    usage = result.get("_model_usage") if isinstance(result.get("_model_usage"), list) else None
    line = world._player_line(player_input)
    if ask:
        try:
            settle_place_reference(result, player_input, trace=trace, usage=usage)
        except Exception as exc:
            turn_ledger.note("movement", "place_reference_failed", error=f"{type(exc).__name__}: {exc}"[:160])
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
            unspoken = world._unattributed_dialogue(conn, narration, result) if ask else ""
    except Exception:
        return {}
    roster_keys = {_norm(n) for n in roster} - {""}
    place_keys = {_norm(n) for n in places} - {""}
    op_places = turn_place_names(result)
    op_people = [
        str(n.get("name") or "").strip() for n in result.get("npcs") or []
        if isinstance(n, dict) and str(n.get("name") or "").strip() and not str(n.get("code") or "").strip()
    ]

    # (name, why it is asked about)
    questions: list[tuple[str, str]] = []
    kinds: dict[str, str] = {}
    introduced: list[str] = []
    # 1. People the engine reads out of the prose (stored places are already left out).
    for person in world._introduced_people(narration, roster + player_names + op_people, set(places)):
        name = str(person.get("name") or "").strip()
        if _norm(name):
            introduced.append(name)
            questions.append((name, "prose"))
    # 2. A new person the ops file (not one the roster already holds).
    for name in op_people:
        if _norm(name) and _norm(name) not in roster_keys:
            questions.append((name, "op_person"))
    # 3. A new place the ops file under a roster person's name.
    for loc in result.get("locations") or []:
        name = str(loc.get("name") or "").strip() if isinstance(loc, dict) else ""
        key = _norm(name)
        if key and key not in place_keys and key in roster_keys:
            questions.append((name, "op_place_named_as_person"))

    asked: set[str] = set()
    for name, why in questions:
        key = _norm(name)
        if key in asked or key in kinds:
            continue
        if not ask:
            # The offline narrator's ops are the engine's own: they are records.
            if key in op_places and why != "op_place_named_as_person":
                kinds[key] = "place"
                turn_ledger.note("npc", "name_is_a_place", name=name, by="record", why=why)
            continue
        if len(asked) >= MAX_ASKS:
            turn_ledger.note("npc", "kind_not_asked", name=name, why=why, reason="ask limit")
            continue
        asked.add(key)
        try:
            reply = _call(KIND_SYSTEM, kind_prompt(name, narration, line), KIND_PHASE, KIND_MAX_TOKENS, trace, usage)
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

    # The speaker check: only when the turn files nobody, so a quote is all
    # that would seed a stranger.
    files_someone = any(_norm(n) not in settled_places(result) for n in op_people) or any(
        _norm(n) not in settled_places(result) for n in introduced
    )
    if ask and unspoken and not files_someone:
        _check_speaker(result, narration, unspoken, trace, usage)
    return kinds


_QUOTE_RE = re.compile(r"[“\"]([^”\"]{8,})[”\"]")


def _paragraph_with(text: str, quote: str) -> str:
    flat = re.sub(r"\s*\[\[[^\]]*\]\]", "", str(text or ""))
    for para in re.split(r"\n\s*\n", flat):
        if quote in para:
            return re.sub(r"\s+", " ", para).strip()[:700]
    return ""


def speaker_prompt(paragraph: str, quote: str) -> str:
    """The user half of the speaker ask, exactly as sent."""
    return f"Text: {paragraph}\n{SPEAKER_QUESTION.format(quote=quote)}"


def _check_speaker(result: dict[str, Any], narration: str, unspoken: str, trace, usage) -> None:
    """Ask whether a person says the first quoted line no known person says."""
    m = _QUOTE_RE.search(unspoken)
    if not m:
        return
    quote = m.group(1).strip()
    paragraph = _paragraph_with(narration, quote)
    if not paragraph:
        return
    try:
        reply = _call(YES_NO_SYSTEM, speaker_prompt(paragraph, quote), SPEAKER_PHASE, YES_NO_MAX_TOKENS, trace, usage)
    except Exception as exc:
        turn_ledger.note("npc", "speaker_ask_failed", quote=quote[:80], error=f"{type(exc).__name__}: {exc}"[:160])
        return
    said = read_yes_no(reply)
    if said is None:
        turn_ledger.note("npc", "speaker_unread", quote=quote[:80], reply=str(reply or "")[:80])
        return
    if said:
        turn_ledger.note("npc", "quote_said_by_a_person", quote=quote[:80])
        return
    turn_ledger.note("npc", "quote_not_said_by_a_person", quote=quote[:80])
    result["_quotes_not_spoken"] = quote_not_spoken(result) + [quote]


# ------------------------------------------------- places by reference (#152)


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


def reference_candidates(rows: list[Any], player_input: str, chat: list[str] | None,
                         current_name: str = "") -> list[tuple[Any, str, str]]:
    """Known places the player's line refers to by reference, best first, as
    (row, the words the ask names it by, the line as the ask shows it).

    A code the line types (#L3) comes first; then the places the chat showed
    most recently under a word the line uses ("the clinic" after "... clinic
    [[L3]]"). A place the line names as where the player comes from is left
    out (world._code_is_origin). Whether the player goes there is the ask's.
    """
    from app import world

    by_code = {str(r["code"] or "").upper(): r for r in rows if r["code"]}
    if not by_code:
        return []
    current = _norm(current_name)
    line = world._player_line(player_input)
    out: list[tuple[Any, str, str]] = []
    seen: set[str] = set()

    def _with_names(text: str) -> str:
        def _name(m: re.Match[str]) -> str:
            row = by_code.get((m.group(1) or m.group(2) or "").upper())
            return str(row["name"] or "") if row is not None else m.group(0)

        return re.sub(r"\s+", " ", _TYPED_CODE_RE.sub(_name, text)).strip()

    for m in _TYPED_CODE_RE.finditer(line):
        row = by_code.get((m.group(1) or m.group(2) or "").upper())
        code = str(row["code"]).upper() if row is not None else ""
        if row is None or code in seen or _norm(row["name"]) == current:
            continue
        if world._code_is_origin(line, m.start(), m.end()):
            continue
        seen.add(code)
        out.append((row, str(row["name"] or ""), _with_names(line)))
    if not chat:
        return out
    dest = f" {world._destination_text(player_input)} "
    for text in chat:
        for m in reversed(list(_CODE_RE.finditer(text or ""))):
            row = by_code.get(m.group(1).upper())
            code = m.group(1).upper()
            if row is None or code in seen or _norm(row["name"]) == current:
                continue
            for head in sorted(_heads(text, m.start(), str(row["name"] or ""))):
                hit = next((
                    h for h in re.finditer(rf"(?<![\w'’-]){re.escape(head)}s?(?![\w'’-])", dest, re.I)
                    if not world._code_is_origin(dest.lower(), h.start(), h.end())
                ), None)
                if hit is None:
                    continue
                article = re.search(r"\b(the|a|an)\s+$", dest[: hit.start()], re.I)
                seen.add(code)
                out.append((row, f"the {hit.group(0).lower()}" if article else hit.group(0), _with_names(line)))
                break
    return out


def going_prompt(line: str, place: str) -> str:
    """The user half of the going ask, exactly as sent."""
    return f"The player wrote: {line}\n{GOING_QUESTION.format(place=place)}"


def settle_place_reference(result: dict[str, Any], player_input: str, *, trace=None, usage=None) -> str:
    """The place code this line goes to by reference, or ''. Set on
    ``result["_place_by_reference"]`` for resolve_movement.

    A place the line names outright wins and nothing is asked. Otherwise each
    reference candidate (at most two) is checked with one ask: is the player
    going there?
    """
    from app import world
    from app.db import connect

    with connect().closing() as conn:
        rows = conn.execute("SELECT id, code, name, parent_id, kind FROM locations ORDER BY id").fetchall()
        here = conn.execute(
            "SELECT l.name FROM player p LEFT JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
        ).fetchone()
        current_name = str((here[0] if here else "") or "")
        chat = chat_narrations(conn)
    if world._movement_destination_from_input(rows, player_input, current_name, names_only=True) is not None:
        return ""
    candidates = reference_candidates(rows, player_input, chat, current_name)
    for row, place, shown_line in candidates[:MAX_GOING_ASKS]:
        code = str(row["code"])
        try:
            reply = _call(YES_NO_SYSTEM, going_prompt(shown_line, place), GOING_PHASE, YES_NO_MAX_TOKENS, trace, usage)
        except Exception as exc:
            turn_ledger.note("movement", "going_ask_failed", code=code, error=f"{type(exc).__name__}: {exc}"[:160])
            return ""
        going = read_yes_no(reply)
        if going:
            turn_ledger.note("movement", "place_bound_by_reference", code=code, place=str(row["name"] or ""), words=place)
            result["_place_by_reference"] = code
            return code
        turn_ledger.note("movement", "place_not_gone_to" if going is False else "going_unread", code=code,
                         words=place, reply=str(reply or "")[:80])
    return ""


def place_by_reference(result: dict[str, Any] | None, rows: list[Any], current_name: str = "") -> Any:
    """The row settle_place_reference bound this turn's line to, or None."""
    code = str((result or {}).get("_place_by_reference") or "").upper() if isinstance(result, dict) else ""
    if not code:
        return None
    for row in rows:
        if str(row["code"] or "").upper() == code and _norm(row["name"]) != _norm(current_name):
            return row
    return None
