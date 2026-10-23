"""The interpreter: what the finished scene made happen, as plain events (#154, #157).

CLAUDE.md, Design decisions, "Narrator, interpreter, engine" (2026-10-23): the
narrator only describes; the interpreter reads the final prose and states the
outcome as events; the engine checks each event against its records and
applies or refuses it. This is its first part, for two kinds of fact:

    died       a person is dead at the end of the scene
    destroyed  a place is destroyed at the end of the scene
    returned   a person recorded dead comes back (a ghoul rising, a revival)

It runs inside world.apply_turn, after the engine's own edits to the prose and
after the turn's new people are on the roster, so it reads the scene the player
reads and can record the death of someone met and killed in the same turn.

Candidates come from the engine's records, never from words: every person and
place the prose names by its code ([[B]], [[L3]]) or by its full roster name,
when no other row has that name and the name is not only part of a longer
roster name ("Radiation Fenced Sanctuary" inside "Radiation Fenced Sanctuary
Clinic" names the clinic, not the town). A name two rows share, living or
dead, names neither of them; a living row that shares a dead person's name is
never asked about (the "NAME: Beth" duplicate row, live run).

Each fact is one plain question about only the paragraphs that name the
candidate, and a second, differently worded question checks it before the
engine acts (CLAUDE.md 2026-10-18):

    died       "Is Beth dead at the end of it?"        yes, then
               "Is Beth alive at the end of it?"       must be no
    destroyed  "Is X destroyed at the end of it?"      yes, then
               "Is any of X still standing at the end of it?"  must be no
    returned   "Does this text show Beth come back from death?"  yes, then
               "Is Beth still dead at the end of it?"  must be no

Later turns are held to the record (the hold), for each dead person the prose
names: "Does Beth say or do anything in it?" (measured on Hermes 3 8B: no
false no). On yes, and no return, each sentence of the paragraphs that name
her is asked about on its own, with its paragraph ("In the sentence "...",
does Beth say or do something?", no false picks measured), and the sentences
picked are cut. Nothing is rewritten: the rewrite ask produced unusable
sentences two times in three. Never cut: a sentence the player is the subject
of ("You pat Beth down ...", "You remember Beth's laugh ..."), and a sentence
holding the player's own quoted words. Never cut below the floor: when the
cuts would leave too little of the scene, the prose is shipped as written and
the record (facts_to_keep next turn) carries the death.

The event shape is the one later kinds (gold, items, moves) will use:
    {"kind": str, "subject": {"type": "npc"|"place", "code": str, "name": str},
     "evidence": str, "status": "proposed"|"applied"|"refused", "reason": str}
A gold event would add "amount" and an "object" of the same shape;
allow_event is the seat where the dice round refuses what a roll did not allow.

Every ask goes through the model call path the caller gives (app/llm.py passes
_chat_text with the turn's usage and trace, so each prompt, raw reply and its
seconds are in the turn trace and model_usage). A turn asks at most MAX_ASKS
questions. Nothing here may break a turn.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

# One ask: (phase, prompt, max_tokens) -> raw reply text.
Ask = Callable[[str, str, int], str]

SYSTEM_PROMPT = "Answer the question about the text."

PHASE_DIED = "interpreter_died"
PHASE_DIED_CHECK = "interpreter_died_check"
PHASE_DESTROYED = "interpreter_destroyed"
PHASE_DESTROYED_CHECK = "interpreter_destroyed_check"
PHASE_HOLD = "interpreter_hold"
PHASE_RETURNED = "interpreter_returned"
PHASE_RETURNED_CHECK = "interpreter_returned_check"
PHASE_WHICH = "interpreter_hold_which"

KIND_DIED = "died"
KIND_DESTROYED = "destroyed"
KIND_RETURNED = "returned"

# How many candidates one turn may ask about, and how many asks in all.
MAX_PEOPLE = 4
MAX_PLACES = 3
MAX_HELD = 2
MAX_UNITS = 16
MAX_ASKS = 40
PASSAGE_CHARS = 2000
# The hold never leaves less than this of the scene (characters, and share of
# the scene as written); below it the prose ships as written.
FLOOR_CHARS = 120
FLOOR_SHARE = 0.4

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


def is_dead(row: Any) -> bool:
    """A person row (dict or sqlite row) the interpreter recorded dead."""
    try:
        value = row.get("died_turn") if isinstance(row, dict) else row["died_turn"]
        return int(value or 0) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Structure: who the prose names, and where
# ---------------------------------------------------------------------------


def _name_re(name: str) -> re.Pattern[str] | None:
    words = str(name or "").strip()
    if len(words) < 3:
        return None
    return re.compile(r"(?<![A-Za-z])" + re.escape(words) + r"(?![A-Za-z])", re.I)


def _key(row: dict[str, Any]) -> str:
    return " ".join(str(row.get("name") or "").lower().split())


class Matcher:
    """Where the prose names a row: its exact code, or its full name when that name is the row's alone.

    ``people`` and ``places`` are the whole roster (living and dead, standing
    and destroyed): a name two rows of one kind share names neither, and a name
    that is only part of a longer roster name (of either kind) is that longer
    name's mention, not its own.
    """

    def __init__(self, people: list[dict[str, Any]] | None = None, places: list[dict[str, Any]] | None = None):
        self.people = [row for row in people or [] if isinstance(row, dict)]
        self.places = [row for row in places or [] if isinstance(row, dict)]
        self._shared: set[int] = set()
        for rows in (self.people, self.places):
            counts: dict[str, int] = {}
            for row in rows:
                if _key(row):
                    counts[_key(row)] = counts.get(_key(row), 0) + 1
            self._shared |= {id(row) for row in rows if counts.get(_key(row), 0) > 1}
        self._all = [row for row in [*self.people, *self.places] if _key(row)]

    def shared(self, row: dict[str, Any]) -> bool:
        return id(row) in self._shared

    def spans(self, text: str, row: dict[str, Any]) -> list[tuple[int, int]]:
        body = str(text or "")
        code = str(row.get("code") or "")
        out = [(m.start(), m.end()) for m in re.finditer(re.escape(f"[[{code}]]"), body)] if code else []
        pattern = _name_re(str(row.get("name") or ""))
        if pattern and not self.shared(row):
            key = _key(row)
            longer = [
                other for other in self._all
                if other is not row and len(_key(other)) > len(key) and pattern.search(str(other.get("name") or ""))
            ]
            covers = [
                (m.start(), m.end())
                for other in longer
                for m in (_name_re(str(other.get("name") or "")) or re.compile(r"(?!)")).finditer(body)
            ]
            for m in pattern.finditer(body):
                if not any(a <= m.start() and m.end() <= b for a, b in covers):
                    out.append((m.start(), m.end()))
        return sorted(out)

    def names(self, text: str, row: dict[str, Any]) -> bool:
        return bool(self.spans(text, row))

    def named(self, text: str, rows: list[dict[str, Any]], skip_names: list[str] | None = None) -> list[dict[str, Any]]:
        """The rows of ``rows`` the text names, in order of first mention."""
        skip = {" ".join(str(n).lower().split()) for n in skip_names or [] if str(n).strip()}
        found: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            if _key(row) in skip:
                continue
            spans = self.spans(text, row)
            if spans:
                found.append((spans[0][0], row))
        found.sort(key=lambda item: item[0])
        return [row for _at, row in found]


def named(text: str, rows: list[dict[str, Any]], skip_names: list[str] | None = None) -> list[dict[str, Any]]:
    """The rows the text names by [[CODE]] or by a full name only one of ``rows`` has."""
    return Matcher(rows).named(text, rows, skip_names)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]


def plain(text: str) -> str:
    """The text without engine codes, for an ask: "Beth [[B]]'s" -> "Beth's"."""
    value = re.sub(r"\s*\[\[(?:[A-Z]{1,3}|L\d+|I\d+|E\d+)\]\]", "", str(text or ""))
    return re.sub(r"[ \t]{2,}", " ", value).strip()


def passage_for(text: str, row: dict[str, Any], limit: int = PASSAGE_CHARS, matcher: Matcher | None = None) -> str:
    """The paragraphs that name this row, codes removed; the last ones when too long (the end decides)."""
    match = matcher or Matcher([row])
    picked = [p for p in _paragraphs(text) if match.names(p, row)]
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


_PLAYER_SUBJECT = {"you", "your", "you're", "you've", "you'd", "you'll", "you’re", "you’ve", "you’d", "you’ll"}


def players_own(sentence: str, player_quotes: list[str] | None = None) -> bool:
    """The player's own sentence: the player is its subject ("You ..."), or it holds the player's quoted words.

    Grammar, not meaning: the scene is written to the player as "you", so a
    sentence that opens on "you" is the player's act or thought ("You pat Beth
    down", "You remember Beth's laugh"). Those are never cut.
    """
    text = plain(sentence)
    if any(q and q.lower() in text.lower() for q in player_quotes or []):
        return True
    first = re.match(r"\s*([A-Za-z’']+)", text)
    return bool(first and first.group(1).lower() in _PLAYER_SUBJECT)


def _has_quote(sentence: str) -> bool:
    return any(mark in sentence for mark in ('"', "“", "”"))


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


# ---------------------------------------------------------------------------
# The asks (one question each, fewest plain words)
# ---------------------------------------------------------------------------


def ask_died(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} dead at the end of it? Answer yes or no."


def ask_died_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} alive at the end of it? Answer yes or no."


def ask_destroyed(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} destroyed at the end of it? Answer yes or no."


def ask_destroyed_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs any of {name} still standing at the end of it? Answer yes or no."


def ask_hold(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nDoes {name} say or do anything in it? Answer yes or no."


def ask_returned(name: str, turn: int, passage: str) -> str:
    return (
        f"{name} died in turn {turn}. Read this.\n\n{passage}\n\n"
        f"Does this text show {name} come back from death? Answer yes or no."
    )


def ask_returned_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} still dead at the end of it? Answer yes or no."


def ask_which(name: str, paragraph: str, sentence: str) -> str:
    return (
        f"Read this.\n\n{paragraph}\n\n"
        f"In the sentence \"{sentence}\", does {name} say or do something? Answer yes or no."
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


def _ask(ask: Ask, report: dict[str, Any], phase: str, prompt: str, max_tokens: int = 8) -> Any:
    if len(report["asks"]) >= MAX_ASKS:
        report["capped"] = int(report.get("capped") or 0) + 1
        return None
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


def _confirmed(ask: Ask, report: dict[str, Any], phase: str, prompt: str, row: dict[str, Any], kind: str) -> bool:
    """The second, differently worded ask: it must answer "no" for the fact to stand."""
    answer = yes_no(_ask(ask, report, phase, prompt))
    if answer is False:
        return True
    report["unconfirmed"].append({"kind": kind, "code": str(row.get("code") or ""), "check": answer})
    return False


def interpret(text: str, records: dict[str, Any], ask: Ask, report: dict[str, Any], matcher: Matcher | None = None) -> list[dict[str, Any]]:
    """The deaths and destructions the prose shows: one ask per named candidate, a second to confirm."""
    match = matcher or Matcher(records.get("people"), records.get("places"))
    events: list[dict[str, Any]] = []
    dead_names = {_key(row) for row in match.people if is_dead(row)}
    living = [row for row in match.people if not is_dead(row) and _key(row) not in dead_names]
    for row in match.named(text, living, records.get("player_names"))[:MAX_PEOPLE]:
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row, matcher=match)
        if not name or not passage:
            continue
        if yes_no(_ask(ask, report, PHASE_DIED, ask_died(name, passage))) is True and _confirmed(
            ask, report, PHASE_DIED_CHECK, ask_died_check(name, passage), row, KIND_DIED
        ):
            events.append(_event(KIND_DIED, "npc", row, passage))
    standing = [row for row in match.places if int(row.get("destroyed_turn") or 0) == 0]
    for row in match.named(text, standing)[:MAX_PLACES]:
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row, matcher=match)
        if not name or not passage:
            continue
        if yes_no(_ask(ask, report, PHASE_DESTROYED, ask_destroyed(name, passage))) is True and _confirmed(
            ask, report, PHASE_DESTROYED_CHECK, ask_destroyed_check(name, passage), row, KIND_DESTROYED
        ):
            events.append(_event(KIND_DESTROYED, "place", row, passage))
    return events


def hold_the_dead(text: str, records: dict[str, Any], ask: Ask, report: dict[str, Any], matcher: Matcher | None = None) -> tuple[str, list[dict[str, Any]]]:
    """The prose with each dead person it shows acting cut out (above the floor), and any "returned" events."""
    match = matcher or Matcher(records.get("people"), records.get("places"))
    events: list[dict[str, Any]] = []
    dead = [row for row in match.people if is_dead(row)]
    for row in match.named(text, dead, records.get("player_names"))[:MAX_HELD]:
        name = str(row.get("name") or row.get("code"))
        turn = int(row.get("died_turn") or 0)
        passage = passage_for(text, row, matcher=match)
        if not passage:
            continue
        acts = yes_no(_ask(ask, report, PHASE_HOLD, ask_hold(name, passage)))
        held: dict[str, Any] = {"code": row.get("code"), "name": name, "acts": acts}
        report["held"].append(held)
        if acts is not True:
            continue
        back = yes_no(_ask(ask, report, PHASE_RETURNED, ask_returned(name, turn, passage)))
        held["returned"] = back
        if back is True and _confirmed(ask, report, PHASE_RETURNED_CHECK, ask_returned_check(name, passage), row, KIND_RETURNED):
            events.append(_event(KIND_RETURNED, "npc", row, passage))
            continue
        text, held["repairs"] = _cut_acts(text, row, name, ask, report, records.get("player_quotes") or [], match)
    return text, events


def _cut_acts(
    text: str, row: dict[str, Any], name: str, ask: Ask, report: dict[str, Any], keep: list[str], match: Matcher
) -> tuple[str, list[dict[str, Any]]]:
    """Cut each sentence, asked one at a time, that has the dead person say or do something."""
    spans = [span for span in units(text) if match.names(_paragraph_of(text, span[0]), row)][-MAX_UNITS:]
    repairs: list[dict[str, Any]] = []
    picked: list[tuple[int, int, str]] = []
    for start, end, sentence in spans:
        if players_own(sentence, keep):
            continue
        paragraph = plain(_paragraph_of(text, start))
        if yes_no(_ask(ask, report, PHASE_WHICH, ask_which(name, paragraph, plain(sentence)))) is True:
            picked.append((start, end, sentence))
    if not picked:
        return text, repairs
    cut = text
    for start, end, _sentence in sorted(picked, reverse=True):  # back to front, so offsets hold
        cut = _cut(cut, start, end)
    before = len(plain(text))
    after = len(plain(cut))
    if after < FLOOR_CHARS or after < before * FLOOR_SHARE:
        repairs.append({"action": "kept_floor", "sentences": [s for _a, _b, s in picked], "chars_left": after, "chars": before})
        _note("hold_floor", code=str(row.get("code") or ""), chars=before, chars_left=after)
        return text, repairs
    repairs.extend({"sentence": s, "action": "cut"} for _a, _b, s in picked)
    return cut, repairs


def _note(event: str, **fields: Any) -> None:
    try:
        from app import turn_ledger

        turn_ledger.note("interpreter", event, **fields)
    except Exception:
        pass


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


def run(text: str, records: dict[str, Any], ask: Ask) -> dict[str, Any]:
    """Read the prose's new events, then hold it to the dead. Returns {narration, events, report}."""
    started = time.time()
    report: dict[str, Any] = {"asks": [], "held": [], "events": [], "unconfirmed": []}
    events: list[dict[str, Any]] = []
    try:
        match = Matcher(records.get("people"), records.get("places"))
        # The facts first (they change the save), so the ask cap never starves them.
        events.extend(interpret(text, records, ask, report, match))
        text, returned = hold_the_dead(text, records, ask, report, match)
        events.extend(returned)
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


def _hook(sentence: str) -> bool:
    """A question the narration puts to the player, outside any quote ("What do you do now?")."""
    return sentence.rstrip().endswith("?") and not _has_quote(sentence)


def prose_line(text: str, player_quotes: list[str] | None = None, limit: int = 420) -> str:
    """What happened, from the final prose: the player's act, the first reply someone gives, and how it ends.

    By grammar only: the act is the first sentence the player is the subject
    of; the reply is the first quoted line that is not the player's own; the
    end is the last sentence that is not a question put to the player. Each
    is taken once, in the order the prose has them.
    """
    pieces = [" ".join(s[2].split()) for s in units(str(text or "")) if s[2].strip()]
    if not pieces:
        return ""
    keep = player_quotes or []
    act = next((i for i, s in enumerate(pieces) if players_own(s, []) and not _hook(s)), 0)
    reply = next(
        (i for i, s in enumerate(pieces) if i != act and _has_quote(s) and not players_own(s, keep)),
        None,
    )
    end = next((i for i in range(len(pieces) - 1, -1, -1) if not _hook(pieces[i])), None)
    picked = sorted({i for i in (act, reply, end) if i is not None})
    share = max(80, limit // max(1, len(picked)))
    parts = [p if len(p) <= share else p[: share - 3].rstrip() + "..." for p in (pieces[i] for i in picked)]
    return " ".join(parts)[:limit]


def summary(events: list[dict[str, Any]], text: str, limit: int = 700, player_quotes: list[str] | None = None) -> str:
    """The turn's summary: its events first ("Beth [[B]] died."), then what happened, from the prose.

    A model's own summary is not used: on the 8B it invented what the prose
    never said (T7 'You apologize and leave the clinic') and contradicted it
    (T13 'You killed Dr. Beth' while she lives).
    """
    lines = [event_line(e) for e in events if e.get("status") != "refused"]
    lines = [line for line in lines if line]
    tail = prose_line(text, player_quotes)
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


def keep_for_rewind(conn, turn: int, table: str, row_id: int) -> None:
    """Add the row, as it is before the event writes it, to this turn's rewind record (the first copy wins)."""
    try:
        snap = conn.execute(
            "SELECT id, snapshot FROM turn_snapshots WHERE turn = ? ORDER BY id DESC LIMIT 1", (int(turn),)
        ).fetchone()
        if snap is None:
            return
        data = json.loads(snap["snapshot"] or "{}")
        if not isinstance(data, dict) or data.get("format") != "ai-rpg-delta-v1":
            return
        if int(row_id) > int((data.get("max_ids") or {}).get(table) or 1 << 62):
            return  # made this turn: the rewind deletes it anyway
        bucket = data.setdefault("rows", {}).setdefault(table, [])
        if any(isinstance(r, dict) and r.get("id") == int(row_id) for r in bucket):
            return
        found = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (int(row_id),)).fetchone()
        if found is None:
            return
        bucket.append({key: found[key] for key in found.keys()})
        conn.execute("UPDATE turn_snapshots SET snapshot = ? WHERE id = ?", (json.dumps(data, ensure_ascii=True), int(snap["id"])))
    except Exception as exc:
        _note("rewind_record_failed", table=table, error=f"{type(exc).__name__}: {exc}"[:200])


def apply_events(conn, turn: int, events: list[dict[str, Any]], turn_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Check each event against the records and write it, or refuse it with a ledger note."""
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
        table = "npcs" if kind in (KIND_DIED, KIND_RETURNED) else "locations"
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
            _note("event_refused", kind=kind, code=code, reason=reason)
        else:
            keep_for_rewind(conn, turn, table, int(row["id"]))
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
