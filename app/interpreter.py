"""The interpreter: what the finished scene made happen, as plain events (#154, #157).

CLAUDE.md, Design decisions, "Narrator, interpreter, engine" (2026-10-23): the
narrator only describes; the interpreter reads the final prose and states the
outcome as events; the engine checks each event against its records and
applies or refuses it. This is its first part, for two kinds of fact:

    died       a person is dead at the end of the scene
    destroyed  a place is destroyed at the end of the scene
    returned   a person recorded dead comes back (a ghoul rising, a revival)

Candidates come from the engine's records, never from words: every person and
place the final prose names by its code ([[B]], [[L3]]) or by its roster name.
For each one the engine asks the model ONE plain question about only the
paragraphs that name it ("Is Beth dead at the end of it? Answer yes or no.").
One ask per candidate, not one ask over a list of people: a yes/no about one
named person is the simplest task the 8B can be given, it needs no code to be
copied back, and a wrong answer touches one person, not the whole cast.

Later turns are held to the record (the hold): for each dead person the prose
names, one question ("Beth died in turn 10. In this text, does Beth speak, move
or act as a living person?"). On yes, one more asks whether the text shows her
coming back from death (then that is a "returned" event, so a death is never a
dead end); otherwise the sentences that show her alive are found with one ask
over numbered sentences and each is rewritten with one small ask (remembered,
or the body described). A rewrite that still shows her alive is cut; cutting is
last.

The event shape is the one the later kinds (gold, items, moves) will use:
    {"kind": str, "subject": {"type": "npc"|"place", "code": str, "name": str},
     "evidence": str, "status": "proposed"|"applied"|"refused", "reason": str}
A gold event would add "amount" and an "object" of the same shape.

Every ask goes through the model call path the caller gives (app/llm.py passes
_chat_text with the turn's usage and trace, so each prompt, raw reply and its
seconds are in the turn trace and model_usage). Nothing here may break a turn.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

# One ask: (phase, prompt, max_tokens) -> raw reply text.
Ask = Callable[[str, str, int], str]

SYSTEM_PROMPT = "Answer the question about the text."

PHASE_DIED = "interpreter_died"
PHASE_DESTROYED = "interpreter_destroyed"
PHASE_HOLD = "interpreter_hold"
PHASE_RETURNED = "interpreter_returned"
PHASE_WHICH = "interpreter_hold_which"
PHASE_REWRITE = "interpreter_hold_rewrite"

KIND_DIED = "died"
KIND_DESTROYED = "destroyed"
KIND_RETURNED = "returned"

# How many candidates one turn may ask about (each is one small ask).
MAX_PEOPLE = 4
MAX_PLACES = 3
MAX_HELD = 3
PASSAGE_CHARS = 2000
MAX_UNITS = 16

_CODE_RE = re.compile(r"\[\[([A-Z]{1,3}|L\d+|I\d+|E\d+)\]\]")
_LABEL_RE = re.compile(r"^[A-Z][A-Z_ ]{1,15}:\s*")


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


def load_records(conn) -> dict[str, Any]:
    """People and places with their codes, names and death / ruin turns (0 = alive / standing)."""
    people: list[dict[str, Any]] = []
    places: list[dict[str, Any]] = []
    player_names: list[str] = []
    try:
        for row in conn.execute("SELECT code, name, died_turn FROM npcs").fetchall():
            people.append({"code": str(row["code"] or ""), "name": clean_name(row["name"]), "died_turn": int(row["died_turn"] or 0)})
    except Exception:
        pass
    try:
        for row in conn.execute("SELECT code, name, destroyed_turn FROM locations").fetchall():
            places.append({"code": str(row["code"] or ""), "name": clean_name(row["name"]), "destroyed_turn": int(row["destroyed_turn"] or 0)})
    except Exception:
        pass
    try:
        row = conn.execute("SELECT name, public_name FROM player WHERE id = 1").fetchone()
        if row:
            player_names = [str(row["name"] or ""), str(row["public_name"] or "")]
    except Exception:
        pass
    return {"people": people, "places": places, "player_names": [n for n in player_names if n.strip()]}


def clean_name(value: Any) -> str:
    """The roster name without an op label left in it ("NAME: Beth" -> "Beth")."""
    return _LABEL_RE.sub("", str(value or "").strip()).strip()


# ---------------------------------------------------------------------------
# Structure: who the prose names, and where
# ---------------------------------------------------------------------------


def _name_re(name: str) -> re.Pattern[str] | None:
    words = str(name or "").strip()
    if len(words) < 3:
        return None
    return re.compile(r"(?<![A-Za-z])" + re.escape(words) + r"(?![A-Za-z])", re.I)


def named(text: str, rows: list[dict[str, Any]], skip_names: list[str] | None = None) -> list[dict[str, Any]]:
    """The rows the text names by [[CODE]] or by a roster name that only one row has, in order of first mention."""
    body = str(text or "")
    skip = {str(n).strip().lower() for n in skip_names or [] if str(n).strip()}
    codes = set(_CODE_RE.findall(body))
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("name") or "").lower()
        if key:
            counts[key] = counts.get(key, 0) + 1
    found: list[tuple[int, dict[str, Any]]] = []
    for row in rows:
        code = str(row.get("code") or "")
        name = str(row.get("name") or "")
        if name.lower() in skip:
            continue
        at = -1
        if code and code in codes:
            at = body.find(f"[[{code}]]")
        elif name and counts.get(name.lower()) == 1:
            pattern = _name_re(name)
            match = pattern.search(body) if pattern else None
            if match:
                at = match.start()
        if at >= 0:
            found.append((at, row))
    found.sort(key=lambda item: item[0])
    return [row for _at, row in found]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]


def _names_row(paragraph: str, row: dict[str, Any]) -> bool:
    code = str(row.get("code") or "")
    if code and f"[[{code}]]" in paragraph:
        return True
    pattern = _name_re(str(row.get("name") or ""))
    return bool(pattern and pattern.search(paragraph))


def plain(text: str) -> str:
    """The text without engine codes, for an ask: "Beth [[B]]'s" -> "Beth's"."""
    value = re.sub(r"\s*\[\[(?:[A-Z]{1,3}|L\d+|I\d+|E\d+)\]\]", "", str(text or ""))
    return re.sub(r"[ \t]{2,}", " ", value).strip()


def passage_for(text: str, row: dict[str, Any], limit: int = PASSAGE_CHARS) -> str:
    """The paragraphs that name this row, codes removed; the last ones when too long (the end decides)."""
    picked = [p for p in _paragraphs(text) if _names_row(p, row)]
    out: list[str] = []
    size = 0
    for para in reversed(picked):
        para_plain = plain(para)
        if out and size + len(para_plain) > limit:
            break
        out.insert(0, para_plain[-limit:] if not out and len(para_plain) > limit else para_plain)
        size += len(para_plain)
    return "\n\n".join(out)


# Titles a sentence splitter must not stop at ("Dr. Beth"): splitting, not meaning.
_TITLE_END_RE = re.compile(r"(?:^|\s)(?:Dr|Mr|Mrs|Ms|St|Jr|Sr|Prof|Capt|Sgt|Lt|Gen|Col|Rev|Mt)\.$")


def units(text: str) -> list[tuple[int, int, str]]:
    """(start, end, text) sentences, joined where the splitter cut inside one.

    Joined: a quote still open ('"You're looking for something? I don't ...
    or leave."'), a speech tag after its quote ('"What are you doing?!" she
    demands, ...'), and a title ("Dr. Beth"). Never across paragraphs.
    """
    from app.prose_state import sentence_spans

    body = str(text or "")
    out: list[tuple[int, int, str]] = []
    for start, end, piece in sentence_spans(body):
        if out and "\n\n" not in body[out[-1][1]:start]:
            prev = out[-1][2]
            first = piece.lstrip()[:1]
            if not _quotes_balanced(prev) or _TITLE_END_RE.search(prev.rstrip()) or (first.isalpha() and first.islower()):
                prev_start = out[-1][0]
                out[-1] = (prev_start, end, body[prev_start:end])
                continue
        out.append((start, end, piece))
    return out


def _quotes_balanced(text: str) -> bool:
    straight = text.count('"') % 2 == 0
    curly = text.count("“") == text.count("”")
    return straight and curly


# ---------------------------------------------------------------------------
# Reading the replies
# ---------------------------------------------------------------------------


def _reply_text(raw: Any) -> str:
    try:
        from app.llm import strip_reasoning

        return strip_reasoning(str(raw or "")).strip()
    except Exception:
        return str(raw or "").strip()


def yes_no(raw: Any) -> bool | None:
    """True for yes, False for no, None for anything else (no action is taken on None)."""
    words = re.findall(r"[a-z]+", _reply_text(raw).lower())
    if not words:
        return None
    if words[0] == "yes":
        return True
    if words[0] == "no":
        return False
    return None


def numbers(raw: Any, count: int) -> list[int] | None:
    """The 1-based sentence numbers in a reply, inside 1..count; [] for none; None when unreadable."""
    text = _reply_text(raw)
    found = [int(n) for n in re.findall(r"\d+", text)]
    if not found:
        return [] if re.search(r"\bnone\b|\bno\b", text.lower()) else None
    picked: list[int] = []
    for n in found:
        if 1 <= n <= count and n not in picked:
            picked.append(n)
    return picked or None


def rewritten(raw: Any, original: str) -> str:
    """The rewritten sentence, or "" when the reply is not one usable sentence for it."""
    text = _reply_text(raw).strip()
    if not text or "\n\n" in text:
        return ""
    text = " ".join(text.split())
    if text[0] in "\"'“" and original.strip()[:1] not in "\"'“" and text[-1] in "\"'”":
        text = text[1:-1].strip()
    if not text or len(text) > len(original) * 3 + 120:
        return ""
    # A rewrite may not bring in a code the sentence did not have.
    if set(_CODE_RE.findall(text)) - set(_CODE_RE.findall(original)):
        return ""
    return text


# ---------------------------------------------------------------------------
# The asks (one question each, fewest plain words)
# ---------------------------------------------------------------------------


def ask_died(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} dead at the end of it? Answer yes or no."


def ask_destroyed(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} destroyed at the end of it? Answer yes or no."


def ask_hold(name: str, turn: int, passage: str) -> str:
    return (
        f"{name} died in turn {turn}. Read this.\n\n{passage}\n\n"
        f"In this text, does {name} speak, move or act as a living person? Answer yes or no."
    )


def ask_returned(name: str, turn: int, passage: str) -> str:
    return (
        f"{name} died in turn {turn}. Read this.\n\n{passage}\n\n"
        f"Does this text show {name} come back from death? Answer yes or no."
    )


def ask_which(name: str, turn: int, numbered: list[str]) -> str:
    lines = "\n".join(f"{i}. {s}" for i, s in enumerate(numbered, 1))
    return (
        f"{name} died in turn {turn}. Read these sentences.\n\n{lines}\n\n"
        f"Which sentences have {name} speak, move or act as a living person? Answer with the numbers."
    )


def ask_rewrite(name: str, sentence: str) -> str:
    return (
        f"{name} is dead. Rewrite this sentence so {name} does not speak, move or act. "
        f"{name} can be remembered, or the body described. Keep the rest. Return only the sentence.\n\n{sentence}"
    )


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def _event(kind: str, kind_of: str, row: dict[str, Any], evidence: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "subject": {"type": kind_of, "code": str(row.get("code") or ""), "name": str(row.get("name") or "")},
        "evidence": evidence[-400:],
        "status": "proposed",
        "reason": "",
    }


def _ask(ask: Ask, report: dict[str, Any], phase: str, prompt: str, max_tokens: int) -> Any:
    started = time.time()
    entry: dict[str, Any] = {"phase": phase}
    try:
        reply = ask(phase, prompt, max_tokens)
    except Exception as exc:  # the model is down or slow: no answer, no action
        entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        reply = None
    entry["reply"] = str(reply if reply is not None else "")[:200]
    entry["seconds"] = round(time.time() - started, 3)
    report["asks"].append(entry)
    return reply


def hold_the_dead(text: str, records: dict[str, Any], ask: Ask, report: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """The prose with each dead person it shows alive repaired, and any "returned" events."""
    events: list[dict[str, Any]] = []
    dead = [row for row in records.get("people") or [] if int(row.get("died_turn") or 0) > 0]
    for row in named(text, dead, records.get("player_names"))[:MAX_HELD]:
        name = str(row.get("name") or row.get("code"))
        turn = int(row.get("died_turn") or 0)
        passage = passage_for(text, row)
        if not passage:
            continue
        alive = yes_no(_ask(ask, report, PHASE_HOLD, ask_hold(name, turn, passage), 8))
        held = {"code": row.get("code"), "name": name, "alive": alive}
        report["held"].append(held)
        if alive is not True:
            continue
        back = yes_no(_ask(ask, report, PHASE_RETURNED, ask_returned(name, turn, passage), 8))
        held["returned"] = back
        if back is True:
            events.append(_event(KIND_RETURNED, "npc", row, passage))
            continue
        text, repairs = _repair(text, row, name, turn, ask, report, records.get("player_quotes") or [])
        held["repairs"] = repairs
    return text, events


def _repair(text: str, row: dict[str, Any], name: str, turn: int, ask: Ask, report: dict[str, Any], keep: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """Rewrite (else cut) each sentence the model points to as the dead person alive."""
    spans = [
        span for span in units(text)
        if _names_row(_paragraph_of(text, span[0]), row)
    ][-MAX_UNITS:]
    if not spans:
        return text, []
    picked = numbers(_ask(ask, report, PHASE_WHICH, ask_which(name, turn, [plain(s[2]) for s in spans]), 24), len(spans))
    repairs: list[dict[str, Any]] = []
    if not picked:
        return text, repairs
    # Back to front, so the earlier offsets still hold.
    for index in sorted(picked, reverse=True):
        start, end, sentence = spans[index - 1]
        if any(q and q.lower() in sentence.lower() for q in keep):
            repairs.append({"sentence": sentence, "action": "kept_player_words"})
            continue
        new = rewritten(_ask(ask, report, PHASE_REWRITE, ask_rewrite(name, sentence), 220), sentence)
        if new:
            still = yes_no(_ask(ask, report, PHASE_HOLD, ask_hold(name, turn, plain(new)), 8))
            if still is not True:
                text = text[:start] + new + text[end:]
                repairs.append({"sentence": sentence, "action": "rewritten", "to": new})
                continue
        text = _cut(text, start, end)
        repairs.append({"sentence": sentence, "action": "cut"})
    return text, repairs


def _paragraph_of(text: str, at: int) -> str:
    head = text.rfind("\n\n", 0, at)
    tail = text.find("\n\n", at)
    return text[head + 2 if head >= 0 else 0: tail if tail >= 0 else len(text)]


def _cut(text: str, start: int, end: int) -> str:
    head = text[:start].rstrip(" \t")
    tail = text[end:].lstrip(" \t")
    if head and not head.endswith("\n") and tail and not tail.startswith("\n"):
        return f"{head} {tail}"
    out = head + tail
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def interpret(text: str, records: dict[str, Any], ask: Ask, report: dict[str, Any]) -> list[dict[str, Any]]:
    """The deaths and destructions the final prose shows, one yes/no ask per named candidate."""
    events: list[dict[str, Any]] = []
    living = [row for row in records.get("people") or [] if int(row.get("died_turn") or 0) == 0]
    for row in named(text, living, records.get("player_names"))[:MAX_PEOPLE]:
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row)
        if not name or not passage:
            continue
        if yes_no(_ask(ask, report, PHASE_DIED, ask_died(name, passage), 8)) is True:
            events.append(_event(KIND_DIED, "npc", row, passage))
    standing = [row for row in records.get("places") or [] if int(row.get("destroyed_turn") or 0) == 0]
    for row in named(text, standing)[:MAX_PLACES]:
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row)
        if not name or not passage:
            continue
        if yes_no(_ask(ask, report, PHASE_DESTROYED, ask_destroyed(name, passage), 8)) is True:
            events.append(_event(KIND_DESTROYED, "place", row, passage))
    return events


def run(text: str, records: dict[str, Any], ask: Ask) -> dict[str, Any]:
    """Hold the prose to the dead, then read its new events. Returns {narration, events, report}."""
    started = time.time()
    report: dict[str, Any] = {"asks": [], "held": [], "events": []}
    events: list[dict[str, Any]] = []
    try:
        text, returned = hold_the_dead(text, records, ask, report)
        events.extend(returned)
        events.extend(interpret(text, records, ask, report))
    except Exception as exc:  # never break a turn
        report["error"] = f"{type(exc).__name__}: {exc}"[:300]
    report["events"] = [dict(e) for e in events]
    report["seconds"] = round(time.time() - started, 3)
    return {"narration": text, "events": events, "report": report}


# ---------------------------------------------------------------------------
# The turn summary (#157 a)
# ---------------------------------------------------------------------------


def event_line(event: dict[str, Any]) -> str:
    subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
    name = str(subject.get("name") or "").strip()
    code = str(subject.get("code") or "").strip()
    label = f"{name} [[{code}]]" if name and code else (name or (f"[[{code}]]" if code else ""))
    if not label:
        return ""
    kind = event.get("kind")
    if kind == KIND_DIED:
        return f"{label} died."
    if kind == KIND_DESTROYED:
        return f"{label} was destroyed."
    if kind == KIND_RETURNED:
        return f"{label} came back from death."
    return ""


def prose_line(text: str, limit: int = 360) -> str:
    """A short line from the final prose: its first sentence and its last one."""
    pieces = [" ".join(s[2].split()) for s in units(str(text or "")) if s[2].strip()]
    if not pieces:
        return ""
    picked = [pieces[0]] if len(pieces) == 1 else [pieces[0], pieces[-1]]
    line = " ".join(picked)
    if len(line) > limit:
        line = pieces[0][:limit]
    return line


def summary(events: list[dict[str, Any]], text: str, limit: int = 700) -> str:
    """The turn's summary: its events first ("Beth [[B]] died."), then a short line from the prose.

    A model's own summary is not used: on the 8B it invented what the prose
    never said (T7 'You apologize and leave the clinic') and contradicted it
    (T13 'You killed Dr. Beth' while she lives).
    """
    lines = [event_line(e) for e in events if e.get("status") != "refused"]
    lines = [line for line in lines if line]
    tail = prose_line(text)
    return " ".join([*lines, tail]).strip()[:limit]


# ---------------------------------------------------------------------------
# The engine side: check each event against the records, apply or refuse it
# ---------------------------------------------------------------------------


def without_refused(summary_text: str, events: list[dict[str, Any]]) -> str:
    """The summary with the line of each event the engine refused taken out."""
    text = str(summary_text or "")
    for event in events or []:
        if isinstance(event, dict) and event.get("status") == "refused":
            line = event_line(event)
            if line:
                text = text.replace(line, "", 1)
    return " ".join(text.split())


def allow_event(event: dict[str, Any], turn_result: dict[str, Any] | None = None) -> str:
    """"" when the event may stand, else why not.

    The seat for the dice/outcome check (#85, #129, a later round): a death the
    roll did not allow is refused here, from the turn's resolved checks, and
    the summary and records then agree with the refusal.
    """
    del event, turn_result
    return ""


def apply_events(conn, turn: int, events: list[dict[str, Any]], turn_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Check each event against the records and write it, or refuse it with a ledger note."""
    from app import turn_ledger

    out: list[dict[str, Any]] = []
    for raw in events or []:
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
        code = str(subject.get("code") or "").strip()
        kind = str(event.get("kind") or "")
        reason = allow_event(event, turn_result)
        row = None
        if not reason:
            if kind in (KIND_DIED, KIND_RETURNED):
                row = conn.execute("SELECT id, died_turn FROM npcs WHERE code = ?", (code,)).fetchone() if code else None
                if row is None:
                    reason = "no such person"
                elif kind == KIND_DIED and int(row["died_turn"] or 0) > 0:
                    reason = "already dead"
                elif kind == KIND_RETURNED and int(row["died_turn"] or 0) == 0:
                    reason = "not dead"
            elif kind == KIND_DESTROYED:
                row = conn.execute("SELECT id, destroyed_turn FROM locations WHERE code = ?", (code,)).fetchone() if code else None
                if row is None:
                    reason = "no such place"
                elif int(row["destroyed_turn"] or 0) > 0:
                    reason = "already destroyed"
            else:
                reason = "unknown kind"
        if reason:
            event["status"] = "refused"
            event["reason"] = reason
            turn_ledger.note("interpreter", "event_refused", kind=kind, code=code, reason=reason)
        else:
            if kind == KIND_DIED:
                conn.execute("UPDATE npcs SET died_turn = ? WHERE id = ?", (int(turn), int(row["id"])))
            elif kind == KIND_RETURNED:
                conn.execute("UPDATE npcs SET died_turn = 0 WHERE id = ?", (int(row["id"]),))
            elif kind == KIND_DESTROYED:
                conn.execute("UPDATE locations SET destroyed_turn = ? WHERE id = ?", (int(turn), int(row["id"])))
            event["status"] = "applied"
            event["turn"] = int(turn)
        out.append(event)
    return out


# ---------------------------------------------------------------------------
# Later turns: what the next scene is told, who is no longer present
# ---------------------------------------------------------------------------


def dead_and_destroyed(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The dead people and destroyed places in a world state (get_state shape)."""
    people: list[dict[str, Any]] = []
    for location in state.get("locations") or []:
        for npc in (location.get("npcs") or []) if isinstance(location, dict) else []:
            if isinstance(npc, dict) and int(npc.get("died_turn") or 0) > 0:
                people.append({"code": str(npc.get("code") or ""), "name": clean_name(npc.get("name")), "turn": int(npc["died_turn"])})
    places = [
        {"code": str(loc.get("code") or ""), "name": str(loc.get("name") or ""), "turn": int(loc.get("destroyed_turn") or 0)}
        for loc in state.get("locations") or []
        if isinstance(loc, dict) and int(loc.get("destroyed_turn") or 0) > 0
    ]
    people.sort(key=lambda p: -p["turn"])
    places.sort(key=lambda p: -p["turn"])
    return {"people": people, "places": places}


def hold_context(state: dict[str, Any], context: dict[str, Any]) -> None:
    """The next turn's context: who is dead (context["the_dead"]), and the dead off the people lists."""
    found = dead_and_destroyed(state)
    if not found["people"] and not found["places"]:
        return
    context["the_dead"] = found
    dead_codes = {p["code"] for p in found["people"] if p["code"]}
    if not dead_codes:
        return
    locations = []
    for location in context.get("locations") or []:
        if isinstance(location, dict) and isinstance(location.get("npcs"), list):
            location = {**location, "npcs": [n for n in location["npcs"] if not (isinstance(n, dict) and n.get("code") in dead_codes)]}
        locations.append(location)
    context["locations"] = locations
    here = context.get("current_location")
    if isinstance(here, dict):
        here = dict(here)
        keeper = here.get("keeper")
        if isinstance(keeper, dict) and keeper.get("code") in dead_codes:
            here.pop("keeper", None)
        if isinstance(here.get("npcs"), list):
            here["npcs"] = [n for n in here["npcs"] if not (isinstance(n, dict) and n.get("code") in dead_codes)]
        context["current_location"] = here


def facts(context: Any, limit: int = 4) -> list[str]:
    """The dead and the destroyed as sentences for facts_to_keep."""
    found = context.get("the_dead") if isinstance(context, dict) else None
    if not isinstance(found, dict):
        return []
    out: list[str] = []
    for person in found.get("people") or []:
        label = f"{person.get('name')} [[{person.get('code')}]]" if person.get("code") else str(person.get("name") or "")
        if label.strip():
            out.append(f"{label} died in turn {person.get('turn')} and is dead.")
    for place in found.get("places") or []:
        label = f"{place.get('name')} [[{place.get('code')}]]" if place.get("code") else str(place.get("name") or "")
        if label.strip():
            out.append(f"{label} was destroyed in turn {place.get('turn')}.")
    return out[:limit]


def dead_codes(conn) -> set[str]:
    try:
        return {str(r["code"] or "").upper() for r in conn.execute("SELECT code FROM npcs WHERE died_turn > 0").fetchall()}
    except Exception:
        return set()
