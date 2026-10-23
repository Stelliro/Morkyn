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
allow_event is the seat where the dice round refuses what a roll did not allow.
A gold event would add "amount" and an "object" of the same shape.

The outcome follows the roll (#85, #129): allow_event refuses the death of
someone the player attacked this turn unless an attack roll on them succeeded
(app/attack_intent.py marks which roll attacked whom). The refused person
stays alive, and reconcile_refused_death puts the prose back in line: the
sentences that show the death (asked one at a time) give way to the engine's
outcome beat ("Beth [[B]] is hurt, but still alive." and the check's own
outcome line), with the same floor and the same never-cut rules as the hold.

Gold (#41, read_gold): whether money leaves or reaches the player, asked over
the whole scene, each a positive question about one thing, and one check that
must answer "no" before either counts:

    out    "Does the player give, pay or lose money in this text?"   yes, then
    in     "Does the player receive money in this text?"             yes, then
    check  "Does any money change hands in this text?"                 must be yes

The amount is never the model's: it is the engine's (the sum the prose names,
read by prose_state, else the band roll). A gold event adds "direction"
("out" / "in") and "amount" to the shape above, with the player as subject.
world.apply_turn refuses a loss the scene does not show (out confirmed) and
logs both answers beside _settle_stated_gold in shadow mode.

The dead leave a body (CLAUDE.md, Design decisions, 2026-10-24): the row stays
where the person died (location_id; npcs.body '' = lies there), so the place's
records and the next scene carry the body (hold_context: each place's
"bodies", the "here" mark on the_dead, facts_to_keep "The body of Beth [[B]]
lies here."), never as someone to talk to: the living lists, the keeper, the
talk roster and the scene cast leave the dead out as before; an NPC op does
not move a body (world._upsert_npc). The roster can have the place wrong, so
a death recorded with the row at another place than the player's asks where
the body is (place_bodies); a confirmed yes puts it where the player is, no
answer keeps the record's place. What becomes of a body is read only when the
player's own line names the dead person and the body is here or carried. Each
is one plain question and a differently worded check, as for a death:

    here     "Is Beth's body with the player at the end of it?"        yes, then
             "Has the player walked away from Beth's body at the end of it?"  must be no
    buried   "Is Beth's body in a grave at the end of it?"        yes, then
             "Can Beth's body be seen at the end of it?"      must be no
    carried  "Is Beth's body in the player's arms or over the player's shoulder at the end of it?"  yes, then
             "Is Beth's body lying on the ground at the end of it?"  must be no

A carried body goes where the player goes (carry_bodies, every turn) until a
turn whose line names her has the carry ask answer no: it is set down there.
Each is a "body" event ({"kind": "body", "state": "buried"|"carried"|"lies"})
applied by apply_events, kept for rewind like a death.

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
PHASE_GOLD_OUT = "interpreter_gold_out"
PHASE_GOLD_IN = "interpreter_gold_in"
PHASE_GOLD_CHECK = "interpreter_gold_check"
PHASE_REFUSED_DEATH = "interpreter_refused_death"
PHASE_BODY_HERE = "interpreter_body_here"
PHASE_BODY_HERE_CHECK = "interpreter_body_here_check"
PHASE_BODY_BURIED = "interpreter_body_buried"
PHASE_BODY_BURIED_CHECK = "interpreter_body_buried_check"
PHASE_BODY_CARRIED = "interpreter_body_carried"
PHASE_BODY_CARRIED_CHECK = "interpreter_body_carried_check"
PHASE_WITH_PLAYER = "interpreter_with_player"
PHASE_WITH_PLAYER_CHECK = "interpreter_with_player_check"

KIND_DIED = "died"
KIND_DESTROYED = "destroyed"
KIND_RETURNED = "returned"
KIND_GOLD = "gold"
KIND_BODY = "body"

# What a body is doing (npcs.body): "" lies where it fell, or carried, or buried.
BODY_LIES = "lies"
BODY_CARRIED = "carried"
BODY_BURIED = "buried"
BODY_STATES = (BODY_LIES, BODY_CARRIED, BODY_BURIED)

# The gold asks read the whole scene (a payment can sit in any paragraph).
GOLD_PASSAGE_CHARS = 4000

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
    here_id = 0
    try:
        try:
            found_rows = conn.execute("SELECT code, name, died_turn, location_id, body, kind, kind_number FROM npcs").fetchall()
        except Exception:  # a save from before the unnamed figures' kind columns
            found_rows = conn.execute("SELECT code, name, died_turn, location_id, body FROM npcs").fetchall()
        for row in found_rows:
            people.append({
                "code": str(row["code"] or ""), "name": clean_name(row["name"]), "died_turn": int(row["died_turn"] or 0),
                "location_id": int(row["location_id"] or 0), "body": body_state(row["body"]),
                "kind": str(row["kind"] or "") if "kind" in row.keys() else "",
                "kind_number": int(row["kind_number"] or 0) if "kind_number" in row.keys() else 0,
            })
    except Exception:  # a save from before the body column
        try:
            for row in conn.execute("SELECT code, name, died_turn FROM npcs").fetchall():
                people.append({"code": str(row["code"] or ""), "name": clean_name(row["name"]), "died_turn": int(row["died_turn"] or 0)})
        except Exception:
            pass
    try:
        found = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        here_id = int((found["current_location_id"] if found else 0) or 0)
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
    return {"people": people, "places": places, "player_names": [n for n in player_names if n.strip()], "here_id": here_id}


def called(row: dict[str, Any], people: list[dict[str, Any]] | None = None, *, prose: bool = False) -> str:
    """How an ask or an engine line names this person: the record's name, or what an unnamed figure is.

    "Ghoul 1" is the engine's label (app/unnamed.py); the prose says "the
    ghoul". In a line the engine writes into the prose (``prose``, the code
    follows it) that is always "the ghoul"; in an ask about plain text it is
    "the ghoul" when it is the only one of its kind at its place, else the
    record's name (two ghouls read alike without their codes).
    """
    from app.unnamed import numbered_name, story_label

    name = str(row.get("name") or "").strip()
    numbered_as, kind = numbered_name(row)
    if not numbered_as:
        return name
    if not prose:
        place = int(row.get("location_id") or 0)
        code = str(row.get("code") or "")
        if any(
            str(p.get("code") or "") != code and int(p.get("location_id") or 0) == place
            and str(p.get("kind") or "").strip().lower() == kind.lower()
            for p in people or []
        ):
            return name
    return story_label(kind, definite=True)


def _opening(name: str) -> str:
    """A name opening a sentence: "the ghoul" -> "The ghoul" (a person's name is unchanged)."""
    return name[:1].upper() + name[1:] if name else name


def body_state(value: Any) -> str:
    """npcs.body as one of BODY_STATES ('' and anything unknown: the body lies where it fell)."""
    text = str(value or "").strip().lower()
    return text if text in BODY_STATES else BODY_LIES


def clean_name(value: Any) -> str:
    """The roster name without an op label left in it ("NAME: Beth" -> "Beth")."""
    return _LABEL_RE.sub("", str(value or "").strip()).strip()


def is_dead(row: Any) -> bool:
    """A person row (dict or sqlite row) the interpreter recorded dead: npcs.dead = 1, or died_turn > 0."""
    for key in ("dead", "died_turn"):
        try:
            value = row.get(key) if isinstance(row, dict) else (row[key] if key in row.keys() else 0)
            if int(value or 0) > 0:
                return True
        except Exception:
            continue
    return False


def set_dead(conn, row: Any, turn: int) -> None:
    """Record a death on the row: died_turn = the turn, and npcs.dead = 1 (#154) when the save has the column.

    turn 0 records a return: died_turn = 0 and dead = 0.
    """
    keys = row.keys() if hasattr(row, "keys") else ()
    if "dead" in keys:
        conn.execute("UPDATE npcs SET died_turn = ?, dead = ? WHERE id = ?", (int(turn), 1 if int(turn) > 0 else 0, int(row["id"])))
    else:
        conn.execute("UPDATE npcs SET died_turn = ? WHERE id = ?", (int(turn), int(row["id"])))


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
        f"{_opening(name)} died in turn {turn}. Read this.\n\n{passage}\n\n"
        f"Does this text show {name} come back from death? Answer yes or no."
    )


def ask_returned_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name} still dead at the end of it? Answer yes or no."


def ask_body_here(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name}'s body with the player at the end of it? Answer yes or no."


def ask_body_here_check(name: str, passage: str) -> str:
    # Measured live on Hermes 3 8B (live-eval-4): "left ... behind" read as "left lying there" and said
    # yes with the player standing over the body (14/27 right on death turns); "walked away from": 27/27.
    return f"Read this.\n\n{passage}\n\nHas the player walked away from {name}'s body at the end of it? Answer yes or no."


def ask_with_player(name: str, passage: str) -> str:
    # The body pair's shape for a living person (#33): presence, not acting. Not yet measured live.
    return f"Read this.\n\n{passage}\n\nIs {name} with the player at the end of it? Answer yes or no."


def ask_with_player_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nHas the player walked away from {name} at the end of it? Answer yes or no."


def ask_body_buried(name: str, passage: str) -> str:
    # Measured (live-eval-4): "buried" took Beth's flesh dissolved in an acid pit for a burial; "in a grave": 97%.
    return f"Read this.\n\n{passage}\n\nIs {name}'s body in a grave at the end of it? Answer yes or no."


def ask_body_buried_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nCan {name}'s body be seen at the end of it? Answer yes or no."


def ask_body_carried(name: str, passage: str) -> str:
    # Measured (live-eval-4): "carrying" said yes to almost any handling (a search, a burn, a sheet over
    # it; 36/90 false yes); "in the player's arms or over the player's shoulder": 96%.
    return f"Read this.\n\n{passage}\n\nIs {name}'s body in the player's arms or over the player's shoulder at the end of it? Answer yes or no."


def ask_body_carried_check(name: str, passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nIs {name}'s body lying on the ground at the end of it? Answer yes or no."


def ask_which(name: str, paragraph: str, sentence: str) -> str:
    return (
        f"Read this.\n\n{paragraph}\n\n"
        f"In the sentence \"{sentence}\", does {name} say or do something? Answer yes or no."
    )


def ask_gold_out(passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nDoes the player give, pay or lose money in this text? Answer yes or no."


def ask_gold_in(passage: str) -> str:
    return f"Read this.\n\n{passage}\n\nDoes the player receive money in this text? Answer yes or no."


def ask_gold_check(passage: str) -> str:
    # Measured live on Hermes 3 8B (docs/showcase/ask-live-eval-2026-10-24.md, round 3): "the same
    # money at the end as at the start?" said no on 4 of 5 real scenes with no money and blocked a
    # real tip; "does any money change hands?" (yes required) made no false yes in 33.
    return f"Read this.\n\n{passage}\n\nDoes any money change hands in this text? Answer yes or no."


# ---------------------------------------------------------------------------
# Gold (#41): does money leave or reach the player in this scene
# ---------------------------------------------------------------------------


def gold_passage(text: str, limit: int = GOLD_PASSAGE_CHARS) -> str:
    """The whole scene without codes; when too long, its last whole paragraphs."""
    out: list[str] = []
    size = 0
    for para in reversed(_paragraphs(text)):
        para_plain = plain(para)
        if out and size + len(para_plain) > limit:
            break
        out.insert(0, para_plain[-limit:] if not out and len(para_plain) > limit else para_plain)
        size += len(para_plain)
    return "\n\n".join(out)


def read_gold(text: str, ask: Ask) -> dict[str, Any]:
    """Whether the scene shows money leaving ("out") and reaching ("in") the player.

    Each side is True only when its ask says yes and the shared check ("does
    any money change hands in this text?") says yes; False when either did
    not (a no, an unread reply, a yes the check refutes); None when the asks
    could not be put at all (the model down: nothing is known, and the caller
    keeps what its own rules decided). The check is asked once, only after a yes.
    """
    report: dict[str, Any] = {"asks": [], "held": [], "events": [], "unconfirmed": []}
    out: dict[str, Any] = {"out": None, "in": None, "answers": {}, "report": report}
    passage = gold_passage(text)
    if not passage:
        return out
    started = time.time()
    check: dict[str, Any] = {}

    def failed() -> bool:
        return bool(report["asks"] and report["asks"][-1].get("error"))

    def side(phase: str, prompt: str, direction: str) -> bool | None:
        raw = _ask(ask, report, phase, prompt)
        if raw is None and failed():
            return None
        answer = yes_no(raw)
        out["answers"][direction] = answer
        if answer is not True:
            return False
        if "answer" not in check:
            raw_check = _ask(ask, report, PHASE_GOLD_CHECK, ask_gold_check(passage))
            check["failed"] = raw_check is None and failed()
            check["answer"] = yes_no(raw_check)
            out["answers"]["check"] = check["answer"]
        if check["failed"]:
            return None
        if check["answer"] is True:
            return True
        report["unconfirmed"].append({"kind": KIND_GOLD, "direction": direction, "check": check["answer"]})
        return False

    try:
        out["out"] = side(PHASE_GOLD_OUT, ask_gold_out(passage), "out")
        out["in"] = side(PHASE_GOLD_IN, ask_gold_in(passage), "in")
    except Exception as exc:  # never break a turn
        report["error"] = f"{type(exc).__name__}: {exc}"[:300]
    report["seconds"] = round(time.time() - started, 3)
    return out


def gold_event(direction: str, amount: int, status: str, reason: str = "", evidence: str = "") -> dict[str, Any]:
    """A gold event: the player pays ("out") or receives ("in") ``amount``, the engine's number."""
    return {
        "kind": KIND_GOLD,
        "subject": {"type": "player", "code": "", "name": "player"},
        "direction": direction,
        "amount": abs(int(amount)),
        "evidence": str(evidence or "")[-400:],
        "status": status,
        "reason": reason,
    }


def ask_talked_to(name: str, line: str) -> str:
    return f"Read this.\n\nThe player: {line}\n\nIs the player talking to {name}? Answer yes or no."


# ---------------------------------------------------------------------------
# An act aimed at the dead (#164): the engine answers it before the prose
# ---------------------------------------------------------------------------

PHASE_TALKED_TO = "interpreter_dead_talked_to"
MAX_TALKED_TO = 2


def dead_talked_to(line: str, records: dict[str, Any], ask: Ask, report: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """The dead person the player's own line talks to, or None.

    'i say hi to Dr. Theo' a turn after his death (live replay, #164): nothing
    told the narrator what that greeting comes to, and the 8B wrote another
    scene. Candidates are the records' dead that the line names, by code or by
    a full name only that row has (the Matcher, as for the prose); a name a
    living row shares names nobody. One positive ask per candidate, about the
    line alone. The caller asks only when the engine already reads the line as
    talk (its social check), so the two agree before the engine answers.
    """
    report = report if report is not None else {"asks": []}
    report.setdefault("asks", [])
    text = str(line or "").strip()
    if not text:
        return None
    match = Matcher(records.get("people"), records.get("places"))
    dead = [row for row in match.people if is_dead(row)]
    for row in match.named(text, dead, records.get("player_names"))[:MAX_TALKED_TO]:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        if yes_no(_ask(ask, report, PHASE_TALKED_TO, ask_talked_to(called(row, match.people), plain(text)), max_tokens=4)) is True:
            return row
    return None


def dead_talk_outcome(row: dict[str, Any], line: str, here: bool = False) -> dict[str, Any]:
    """The engine's outcome for talk to a dead person, in the act_outcome shape the draft already reads."""
    name = _opening(called(row, prose=True))
    code = str(row.get("code") or "").strip()
    label = f"{name} [[{code}]]" if code else name
    means = (
        f"{label} is dead; the body lies where it fell. {name} does not answer."
        if here
        else f"{label} is dead and does not answer."
    )
    return {
        "act": str(line or "").strip()[:100],
        "skill": "",
        "proficiency": "",
        "outcome": "no answer",
        "degree": "no roll",
        "means": means,
        "dead": code,
    }


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


def _event(kind: str, kind_of: str, row: dict[str, Any], evidence: str) -> dict[str, Any]:
    subject = {"type": kind_of, "code": str(row.get("code") or ""), "name": str(row.get("name") or "")}
    if kind_of == "npc" and called(row, prose=True) != subject["name"]:
        # What the turn summary calls an unnamed figure ("the ghoul [[A]] died"), not "Ghoul 1".
        subject["story"] = called(row, prose=True)
    return {
        "kind": kind,
        "subject": subject,
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
        asked = called(row, match.people)
        if yes_no(_ask(ask, report, PHASE_DIED, ask_died(asked, passage))) is True and _confirmed(
            ask, report, PHASE_DIED_CHECK, ask_died_check(asked, passage), row, KIND_DIED
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
        asked = called(row, match.people) or name
        acts = yes_no(_ask(ask, report, PHASE_HOLD, ask_hold(asked, passage)))
        held: dict[str, Any] = {"code": row.get("code"), "name": name, "acts": acts}
        report["held"].append(held)
        if acts is not True:
            continue
        back = yes_no(_ask(ask, report, PHASE_RETURNED, ask_returned(asked, turn, passage)))
        held["returned"] = back
        if back is True and _confirmed(ask, report, PHASE_RETURNED_CHECK, ask_returned_check(asked, passage), row, KIND_RETURNED):
            events.append(_event(KIND_RETURNED, "npc", row, passage))
            continue
        text, held["repairs"] = _cut_acts(text, row, asked, ask, report, records.get("player_quotes") or [], match)
    return text, events


def with_player_enabled() -> bool:
    import os

    return str(os.getenv("AI_RPG_WITH_PLAYER", "off")).strip().lower() in {"1", "on", "true", "yes"}


def with_player(
    text: str, events: list[dict[str, Any]], records: dict[str, Any], ask: Ask, report: dict[str, Any],
    matcher: Matcher | None = None,
) -> list[str]:
    """The codes of living people on record at another place than the player's whom the scene shows with the player (#33).

    A presence pair in the shape of the measured body pair (live-eval-4: "Is
    <Name>'s body with the player at the end of it?" 92%, its check "Has the
    player walked away from <Name>'s body ...?" 27/27): "Is <Name> with the
    player at the end of it?", then "Has the player walked away from <Name>
    at the end of it?", which must answer no. Presence, not acting: a keeper
    calling from inside their shop to the player outside acts but is not with
    the player. Asked only of people the prose names outside quoted speech, at
    most MAX_PEOPLE a turn. The engine decides what a confirmed yes moves
    (app/whereabouts.decide: not someone a sentence puts at another place, or
    left behind). Someone who died this turn is the body asks' (place_bodies).
    """
    from app.venues import strip_speech

    match = matcher or Matcher(records.get("people"), records.get("places"))
    here_id = int(records.get("here_id") or 0)
    if not here_id:
        return []
    died_now = {str((e.get("subject") or {}).get("code") or "") for e in events if e.get("kind") == KIND_DIED}
    dead_names = {_key(row) for row in match.people if is_dead(row)}
    elsewhere = [
        row for row in match.people
        if not is_dead(row) and _key(row) not in dead_names and str(row.get("code") or "") not in died_now
        and "location_id" in row and int(row.get("location_id") or 0) != here_id
    ]
    unspoken = strip_speech(text)
    out: list[str] = []
    for row in match.named(unspoken, elsewhere, records.get("player_names"))[:MAX_PEOPLE]:
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row, matcher=match)
        if not name or not passage:
            continue
        first = yes_no(_ask(ask, report, PHASE_WITH_PLAYER, ask_with_player(name, passage)))
        present = first is True and _confirmed(
            ask, report, PHASE_WITH_PLAYER_CHECK, ask_with_player_check(name, passage), row, "with_player"
        )
        report.setdefault("with_player", []).append({"code": row.get("code"), "name": name, "asked": first, "with_player": present})
        if present:
            out.append(str(row.get("code") or ""))
    return out


def place_bodies(
    text: str, events: list[dict[str, Any]], records: dict[str, Any], ask: Ask, report: dict[str, Any],
    matcher: Matcher | None = None,
) -> None:
    """For a death recorded with the row at another place than the player's, whether the body is with the player.

    The roster can have the place wrong (final replay T3: Nate on record in the
    town, the player in the clinic); the scene says where the body is. Asked
    only then, one plain question and a differently worded check; the answer
    rides on the event ("body_here"), and apply_events moves the row only on a
    confirmed yes. No answer keeps the record's place.
    """
    match = matcher or Matcher(records.get("people"), records.get("places"))
    here_id = int(records.get("here_id") or 0)
    if not here_id:
        return
    by_code = {str(row.get("code") or ""): row for row in match.people}
    for event in events:
        if event.get("kind") != KIND_DIED or event.get("status") == "refused":
            continue
        row = by_code.get(str((event.get("subject") or {}).get("code") or ""))
        if row is None or not int(row.get("location_id") or 0) or int(row.get("location_id") or 0) == here_id:
            continue
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row, matcher=match)
        if not name or not passage:
            continue
        asked = called(row, match.people)
        here = yes_no(_ask(ask, report, PHASE_BODY_HERE, ask_body_here(asked, passage))) is True and _confirmed(
            ask, report, PHASE_BODY_HERE_CHECK, ask_body_here_check(asked, passage), row, "body_here"
        )
        event["body_here"] = here
        report.setdefault("bodies", []).append({"code": row.get("code"), "name": name, "with_player": here})


def read_bodies(
    text: str, records: dict[str, Any], ask: Ask, report: dict[str, Any], matcher: Matcher | None = None,
    skip_codes: set[str] | None = None,
) -> list[dict[str, Any]]:
    """What became of the bodies the player's own line acts on: buried, carried, or set down ("body" events).

    Candidates are the records' dead that the player's line names (code or a
    name only that row has) whose body is at the player's place or carried, and
    that the prose names too; a buried body is done. Nothing is asked otherwise.
    """
    match = matcher or Matcher(records.get("people"), records.get("places"))
    line = str(records.get("player_line") or "")
    here_id = int(records.get("here_id") or 0)
    skip = {str(c).upper() for c in skip_codes or ()}
    if not line.strip():
        return []
    events: list[dict[str, Any]] = []
    dead = [row for row in match.people if is_dead(row) and str(row.get("code") or "").upper() not in skip]
    for row in match.named(line, dead, records.get("player_names"))[:MAX_HELD]:
        state = body_state(row.get("body"))
        here = bool(here_id) and int(row.get("location_id") or 0) == here_id
        if state == BODY_BURIED or not (here or state == BODY_CARRIED):
            continue
        name = str(row.get("name") or "").strip()
        passage = passage_for(text, row, matcher=match)
        if not name or not passage:
            continue
        seen: dict[str, Any] = {"code": row.get("code"), "name": name, "was": state}
        report.setdefault("bodies", []).append(seen)
        asked = called(row, match.people)
        if yes_no(_ask(ask, report, PHASE_BODY_BURIED, ask_body_buried(asked, passage))) is True and _confirmed(
            ask, report, PHASE_BODY_BURIED_CHECK, ask_body_buried_check(asked, passage), row, KIND_BODY
        ):
            seen["now"] = BODY_BURIED
            events.append({**_event(KIND_BODY, "npc", row, passage), "state": BODY_BURIED})
            continue
        carried = yes_no(_ask(ask, report, PHASE_BODY_CARRIED, ask_body_carried(asked, passage)))
        if carried is True and state != BODY_CARRIED and _confirmed(
            ask, report, PHASE_BODY_CARRIED_CHECK, ask_body_carried_check(asked, passage), row, KIND_BODY
        ):
            seen["now"] = BODY_CARRIED
            events.append({**_event(KIND_BODY, "npc", row, passage), "state": BODY_CARRIED})
        elif carried is False and state == BODY_CARRIED:
            seen["now"] = BODY_LIES  # set down where the player is
            events.append({**_event(KIND_BODY, "npc", row, passage), "state": BODY_LIES})
    return events


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


def ask_shows_death(name: str, paragraph: str, sentence: str) -> str:
    return (
        f"Read this.\n\n{paragraph}\n\n"
        # Measured live (round 3): "In the sentence ..., is X dead?" answered about the whole
        # paragraph (12/51 false yes); asking what the sentence says: 1/51.
        f"Does the sentence \"{sentence}\" say that {name} is dead? Answer yes or no."
    )


def outcome_beat(row: dict[str, Any], check: dict[str, Any] | None) -> str:
    """The engine's line for a death the roll refused: the person lives, then the check's own outcome line."""
    name = _opening(called(row, prose=True))
    code = str(row.get("code") or "").strip()
    label = f"{name} [[{code}]]" if name and code else (name or f"[[{code}]]")
    check = check if isinstance(check, dict) else {}
    first = f"{label} is hurt, but still alive." if check.get("outcome") == "partial" else f"{label} is still alive."
    flavor = " ".join(str(check.get("flavor") or "").split())
    return f"{first} {flavor}".strip()


def _append_beat(text: str, beat: str) -> str:
    body = str(text or "").rstrip()
    return f"{body} {beat}".strip() if body else beat


def reconcile_refused_death(
    text: str,
    event: dict[str, Any],
    rolls: list[dict[str, Any]],
    ask: Ask,
    report: dict[str, Any],
    match: Matcher,
    keep: list[str] | None = None,
) -> str:
    """The prose put back in line with the roll after a refused death (#129).

    Each sentence of the paragraphs that name the person is asked about on
    its own ("In the sentence "...", is Beth dead?"); the first one picked is
    replaced by the engine's outcome beat and the others are cut. Never cut:
    the scene's first sentence the player is the subject of (the act as
    narrated) and a sentence holding the player's quoted words. Never below
    the floor: then, and when nothing is picked, the prose is kept and the
    beat is added at its end, so the scene still says what the dice decided.
    """
    subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
    code = str(subject.get("code") or "")
    row = next((r for r in match.people if str(r.get("code") or "") == code), None) or {
        "code": code, "name": str(subject.get("name") or ""),
    }
    name = called(row, match.people) or code
    beat = outcome_beat(row, rolls[-1] if rolls else None)
    record: dict[str, Any] = {"code": code, "beat": beat, "sentences": []}
    report.setdefault("refused_deaths", []).append(record)
    every = units(text)
    act = next((u for u in every if players_own(u[2], []) and not _hook(u[2])), None)
    quotes = [q for q in keep or [] if q]
    picked: list[tuple[int, int, str]] = []
    for start, end, sentence in [u for u in every if match.names(_paragraph_of(text, u[0]), row)][-MAX_UNITS:]:
        if act is not None and start == act[0]:
            continue
        if any(q.lower() in plain(sentence).lower() for q in quotes):
            continue
        paragraph = plain(_paragraph_of(text, start))
        if yes_no(_ask(ask, report, PHASE_REFUSED_DEATH, ask_shows_death(name, paragraph, plain(sentence)))) is True:
            picked.append((start, end, sentence))
    record["sentences"] = [s for _a, _b, s in picked]
    if not picked:
        record["action"] = "beat_added"
        return _append_beat(text, beat)
    cut = text
    for start, end, _sentence in sorted(picked, reverse=True):
        cut = _cut(cut, start, end)
    before = len(plain(text))
    after = len(plain(cut))
    if after < FLOOR_CHARS or after < before * FLOOR_SHARE:
        record["action"] = "kept_floor_beat_added"
        _note("refused_death_floor", code=code, chars=before, chars_left=after)
        return _append_beat(text, beat)
    out = text
    first = min(picked)
    for start, end, _sentence in sorted(picked, reverse=True):  # back to front, so offsets hold
        out = (out[:start] + beat + out[end:]) if (start, end) == first[:2] else _cut(out, start, end)
    record["action"] = "replaced"
    return out


def _beat_before_hook(text: str, beat: str) -> str:
    """The beat at the end of the scene, or before the question it closes on ("What do you do?")."""
    body = str(text or "").rstrip()
    every = units(body)
    if every and _hook(every[-1][2]) and every[-1][0] > 0:
        start = every[-1][0]
        head = body[:start].rstrip(" \t")
        joiner = "\n\n" if head.endswith("\n") else " "
        return f"{head.rstrip()} {beat}{joiner}{body[start:].lstrip()}"
    return _append_beat(body, beat)


def show_unnamed_attacks(
    text: str, turn_result: dict[str, Any] | None, match: Matcher, report: dict[str, Any]
) -> str:
    """The attack the dice decided, put in a scene that never names its target (#129, both ways).

    A rolled attack check carries the person it was aimed at (its "attack"
    record, app/attack_intent.py). When the final prose names that person
    nowhere, by code or by a name only they have (the Matcher), the prose
    ignored the act (integ-r4 T3: 'i shoot Dr. Vasilis', a critical success,
    became a shooting test with someone else). The engine adds the roll's own
    outcome line ("Your shot hits Vasilis [[B]].") and keeps the prose. A
    prose that names the target is left alone: whether it shows the right
    outcome is not decided here.
    """
    checks = (turn_result or {}).get("skill_checks") if isinstance(turn_result, dict) else None
    if not isinstance(checks, list):
        return text
    from app.attack_intent import attack_target, outcome_line

    done: set[str] = set()
    for check in checks:
        code = attack_target(check)
        if not code or code in done:
            continue
        done.add(code)
        attack = check.get("attack") if isinstance(check.get("attack"), dict) else {}
        row = next((r for r in match.people if str(r.get("code") or "").upper() == code), None) or {
            "code": code, "name": clean_name(attack.get("name")),
        }
        if match.names(text, row):
            continue
        name = called(row, prose=True)
        beat = outcome_line(check, f"{name} [[{code}]]" if name else f"[[{code}]]")
        if not beat:
            continue
        text = _beat_before_hook(text, beat)
        report.setdefault("attack_beats", []).append({"code": code, "outcome": str(check.get("outcome") or ""), "beat": beat})
        _note("attack_not_in_prose", code=code, outcome=str(check.get("outcome") or ""), beat=beat)
    return text


def run(text: str, records: dict[str, Any], ask: Ask, turn_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read the prose's new events, refuse what the dice did not allow, then hold it to the dead.

    ``turn_result`` is the turn as apply_turn has it (its "skill_checks" are
    the rolls made before the draft). Returns {narration, events, report}.
    """
    started = time.time()
    report: dict[str, Any] = {"asks": [], "held": [], "events": [], "unconfirmed": []}
    events: list[dict[str, Any]] = []
    shown: list[str] = []
    try:
        match = Matcher(records.get("people"), records.get("places"))
        # The facts first (they change the save), so the ask cap never starves them.
        events.extend(interpret(text, records, ask, report, match))
        # The outcome follows the roll (#85, #129): a death the attack roll
        # did not allow is refused, the person stays alive, and the prose is
        # put back in line with the dice.
        for event in events:
            reason = allow_event(event, turn_result, str(records.get("player_line") or ""))
            if not reason:
                continue
            subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
            event["status"] = "refused"
            event["reason"] = reason
            _note("event_refused", kind=str(event.get("kind") or ""), code=str(subject.get("code") or ""), reason=reason)
            text = reconcile_refused_death(
                text, event, attack_rolls(event, turn_result, str(records.get("player_line") or "")), ask, report, match, records.get("player_quotes") or []
            )
        # The other way round: an attack the prose never shows its target in
        # gets the roll's outcome line (no ask: the records and the codes).
        text = show_unnamed_attacks(text, turn_result, match, report)
        # Where the body lies when the roster has the person elsewhere than the player.
        place_bodies(text, events, records, ask, report, match)
        text, returned = hold_the_dead(text, records, ask, report, match)
        events.extend(returned)
        # What became of a body the player's line acts on (read from the held prose).
        back = {str((e.get("subject") or {}).get("code") or "") for e in returned}
        events.extend(read_bodies(text, records, ask, report, match, back))
        # Who on record elsewhere the scene shows with the player (#33, app/whereabouts.py). Off by
        # default: measured live on Hermes 3 8B (live-eval-8) the presence pair moved the wrong
        # person in 27 of 69 tries (calls from a doorway, a radio, someone talked about) and missed
        # both real traces; "has the player walked away from X?" is honestly no whenever the two
        # were never together. New people are still filed where the player is (no ask needed).
        shown = with_player(text, events, records, ask, report, match) if with_player_enabled() else []
    except Exception as exc:  # never break a turn
        report["error"] = f"{type(exc).__name__}: {exc}"[:300]
    report["events"] = [dict(e) for e in events]
    report["seconds"] = round(time.time() - started, 3)
    return {"narration": text, "events": events, "report": report, "with_player": shown}


# ---------------------------------------------------------------------------
# The turn summary (#157 a)
# ---------------------------------------------------------------------------


def event_line(event: dict[str, Any]) -> str:
    subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
    name = str(subject.get("story") or subject.get("name") or "").strip()
    code = str(subject.get("code") or "").strip()
    label = f"{name} [[{code}]]" if name and code else (name or (f"[[{code}]]" if code else ""))
    if not label:
        return ""
    opens = _opening(label) if subject.get("story") else label  # "the ghoul [[A]]" opening a sentence
    kind = event.get("kind")
    if kind == KIND_DIED:
        return f"{opens} died."
    if kind == KIND_DESTROYED:
        return f"{opens} was destroyed."
    if kind == KIND_RETURNED:
        return f"{opens} came back from death."
    if kind == KIND_BODY:
        state = event.get("state")
        if state == BODY_BURIED:
            return f"{opens} was buried."
        if state == BODY_CARRIED:
            return f"You carry the body of {label}."
        if state == BODY_LIES:
            return f"You set down the body of {label}."
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


# The outcomes of an attack roll that may kill the one attacked. A partial is
# "something, but not everything": hurt, not dead (skill_checks.DEGREE_FLAVOR).
DEATH_ALLOWED_OUTCOMES = frozenset({"success", "critical_success"})


COMBAT_SKILLS = frozenset({"melee", "ranged"})


def line_names(line: str, subject: dict[str, Any]) -> bool:
    """Whether the player's own line names the person: their [[code]] or @code, or their recorded name whole."""
    text = str(line or "")
    code = str(subject.get("code") or "").strip()
    name = str(subject.get("name") or "").strip()
    if code and re.search(rf"(?:\[\[|@){re.escape(code)}(?:\]\]|\b)", text, re.I):
        return True
    return bool(name) and len(name) >= 3 and re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I) is not None


def attack_rolls(event: dict[str, Any], turn_result: dict[str, Any] | None, line: str = "") -> list[dict[str, Any]]:
    """The turn's rolled checks that attacked the event's person (their "attack" code, app/attack_intent.py).

    When no roll carries that mark but the player's own line names the person, an unaimed melee or
    ranged roll this turn is the attack on them. Live (final replay, 2026-10-24): 'i shoot Nate'
    rolled ranged critical_failure with no target, because the roster placed Nate in the town while
    the prose had him in the clinic, so attack_intent found nobody here; the prose killed him and the
    death stood.
    """
    subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
    code = str(subject.get("code") or "").strip().upper()
    checks = (turn_result or {}).get("skill_checks") if isinstance(turn_result, dict) else None
    if not code or not isinstance(checks, list):
        return []
    from app.attack_intent import attack_target

    rolled = [c for c in checks if isinstance(c, dict) and c.get("natural") is not None]
    aimed = [c for c in rolled if attack_target(c) == code]
    if aimed or not line_names(line, subject):
        return aimed
    return [
        c for c in rolled
        if not attack_target(c) and str(((c.get("skill") or {}).get("code") if isinstance(c.get("skill"), dict) else "") or "") in COMBAT_SKILLS
    ]


def allow_event(event: dict[str, Any], turn_result: dict[str, Any] | None = None, line: str = "") -> str:
    """"" when the event may stand, else why not.

    The dice/outcome check (#85, #129): the death of someone the player
    attacked this turn stands only when an attack roll on them succeeded. A
    death with no attack roll behind it (dice off, someone else's doing, no
    attack found) is not the dice's to refuse.
    """
    if not isinstance(event, dict) or event.get("kind") != KIND_DIED:
        return ""
    rolls = attack_rolls(event, turn_result, line)
    if not rolls or any(str(c.get("outcome") or "") in DEATH_ALLOWED_OUTCOMES for c in rolls):
        return ""
    return f"attack roll {rolls[-1].get('outcome') or 'failure'}"


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


def _here_id(conn) -> int:
    try:
        row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        return int((row["current_location_id"] if row else 0) or 0)
    except Exception:
        return 0


def apply_events(conn, turn: int, events: list[dict[str, Any]], turn_result: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Check each event against the records and write it, or refuse it with a ledger note."""
    out: list[dict[str, Any]] = []
    here_id = _here_id(conn)
    for raw in events or []:
        if not isinstance(raw, dict):
            continue
        event = dict(raw)
        if event.get("status") == "refused":  # refused (and noted) in run(): it writes nothing
            out.append(event)
            continue
        subject = event.get("subject") if isinstance(event.get("subject"), dict) else {}
        code = str(subject.get("code") or "").strip()
        kind = str(event.get("kind") or "")
        reason = allow_event(event, turn_result)
        row = None
        table = "npcs" if kind in (KIND_DIED, KIND_RETURNED, KIND_BODY) else "locations"
        if not reason:
            if kind in (KIND_DIED, KIND_RETURNED, KIND_BODY):
                row = conn.execute("SELECT * FROM npcs WHERE code = ?", (code,)).fetchone() if code else None
                if row is None:
                    reason = "no such person"
                elif kind == KIND_DIED and int(row["died_turn"] or 0) > 0:
                    reason = "already dead"
                elif kind in (KIND_RETURNED, KIND_BODY) and int(row["died_turn"] or 0) == 0:
                    reason = "not dead"
                elif kind == KIND_BODY and event.get("state") not in BODY_STATES:
                    reason = "unknown body state"
                elif kind == KIND_BODY and "body" in row.keys() and body_state(row["body"]) == event.get("state"):
                    reason = "no change"
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
                set_dead(conn, row, int(turn))
                # The body lies where the prose leaves it (place_bodies): a row the
                # roster kept at another place than the player's moves here only
                # when the scene has the body with the player.
                at = int(row["location_id"] or 0)
                if here_id and at != here_id and event.get("body_here") is True:
                    conn.execute("UPDATE npcs SET location_id = ? WHERE id = ?", (here_id, int(row["id"])))
                    event["body_at"] = here_id
                    _note("body_placed", code=code, was=at, now=here_id)
            elif kind == KIND_RETURNED:
                set_dead(conn, row, 0)
                if "body" in row.keys():
                    conn.execute("UPDATE npcs SET body = '' WHERE id = ?", (int(row["id"]),))
            elif kind == KIND_BODY:
                state = str(event.get("state"))
                conn.execute(
                    "UPDATE npcs SET body = ?, location_id = ? WHERE id = ?",
                    ("" if state == BODY_LIES else state, here_id or int(row["location_id"] or 0), int(row["id"])),
                )
            elif kind == KIND_DESTROYED:
                conn.execute("UPDATE locations SET destroyed_turn = ? WHERE id = ?", (int(turn), int(row["id"])))
            event["status"] = "applied"
            event["turn"] = int(turn)
        out.append(event)
    return out


def carry_bodies(conn, turn: int) -> list[str]:
    """A carried body goes where the player goes: each turn, after the moves. Returns the codes moved."""
    here_id = _here_id(conn)
    if not here_id:
        return []
    try:
        rows = conn.execute(
            "SELECT id, code, location_id FROM npcs WHERE died_turn > 0 AND body = ? AND location_id != ?",
            (BODY_CARRIED, here_id),
        ).fetchall()
    except Exception:  # a save from before the body column
        return []
    moved: list[str] = []
    for row in rows:
        keep_for_rewind(conn, turn, "npcs", int(row["id"]))
        conn.execute("UPDATE npcs SET location_id = ? WHERE id = ?", (here_id, int(row["id"])))
        moved.append(str(row["code"] or ""))
    if moved:
        _note("bodies_carried", codes=moved, now=here_id)
    return moved


# ---------------------------------------------------------------------------
# Later turns: what the next scene is told, who is no longer present
# ---------------------------------------------------------------------------


def dead_and_destroyed(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The dead people and destroyed places in a world state (get_state shape).

    Each dead person carries where the body is ("location_id", "location_code")
    and what it is doing ("body": lies / carried / buried); "here" marks a body
    at the player's place.
    """
    current = state.get("current_location") if isinstance(state.get("current_location"), dict) else {}
    here_id = int(current.get("id") or 0)
    here_code = str(current.get("code") or "")
    people: list[dict[str, Any]] = []
    for location in state.get("locations") or []:
        for npc in (location.get("npcs") or []) if isinstance(location, dict) else []:
            if isinstance(npc, dict) and is_dead(npc):
                at_id = int(npc.get("location_id") or location.get("id") or 0)
                at_code = str(location.get("code") or "")
                people.append({
                    "code": str(npc.get("code") or ""), "name": clean_name(npc.get("name")), "turn": int(npc.get("died_turn") or 0),
                    "body": body_state(npc.get("body")), "location_id": at_id, "location_code": at_code,
                    "kind": str(npc.get("kind") or ""), "kind_number": int(npc.get("kind_number") or 0),
                    "here": bool((here_id and at_id == here_id) or (not here_id and here_code and at_code == here_code)),
                })
    places = [
        {"code": str(loc.get("code") or ""), "name": str(loc.get("name") or ""), "turn": int(loc.get("destroyed_turn") or 0)}
        for loc in state.get("locations") or []
        if isinstance(loc, dict) and int(loc.get("destroyed_turn") or 0) > 0
    ]
    people.sort(key=lambda p: -p["turn"])
    places.sort(key=lambda p: -p["turn"])
    return {"people": people, "places": places}


def body_entry(person: dict[str, Any]) -> dict[str, Any]:
    """A body as a place lists it: who, since when, and what it is doing."""
    return {"code": person.get("code") or "", "name": person.get("name") or "", "died_turn": int(person.get("turn") or 0),
            "body": person.get("body") or BODY_LIES,
            # An unnamed figure stays recognisable as one, so the story sees "the ghoul", not "Ghoul 1".
            "kind": person.get("kind") or "", "kind_number": int(person.get("kind_number") or 0)}


def hold_context(state: dict[str, Any], context: dict[str, Any]) -> None:
    """The next turn's context: who is dead (context["the_dead"]), each place's bodies, and the living lists.

    The dead leave a body (CLAUDE.md 2026-10-24): a place's dead move from its
    "npcs" (the living, whom the scene can talk to and roll against) to its
    "bodies"; the place the player is in carries its bodies too, and a dead
    keeper is no keeper (a dead doctor sells nothing).
    """
    found = dead_and_destroyed(state)
    if not found["people"] and not found["places"]:
        return
    context["the_dead"] = found
    dead_codes = {p["code"] for p in found["people"] if p["code"]}
    if not dead_codes:
        return
    by_place: dict[Any, list[dict[str, Any]]] = {}
    for person in found["people"]:
        by_place.setdefault(person.get("location_id") or person.get("location_code"), []).append(body_entry(person))
    locations = []
    for location in context.get("locations") or []:
        if isinstance(location, dict) and isinstance(location.get("npcs"), list):
            location = {**location, "npcs": [n for n in location["npcs"] if not (isinstance(n, dict) and n.get("code") in dead_codes)]}
            bodies = by_place.get(location.get("id")) or by_place.get(location.get("code")) or []
            if bodies:
                location["bodies"] = bodies
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
        bodies = [body_entry(p) for p in found["people"] if p.get("here")]
        if bodies:
            here["bodies"] = bodies
        context["current_location"] = here


_BODY_FACTS = {
    BODY_LIES: "The body of {label} lies here.",
    BODY_CARRIED: "You carry the body of {label}.",
    BODY_BURIED: "{label} is buried here.",
}


# Death is a 0/1 state the narrator is told only when it is 1 (CLAUDE.md,
# Design decisions, 2026-10-24, #154): a dead person the narrator is shown
# carries DEAD_FLAG ("Beth [[B]] dead=1"); the living carry nothing, as the
# model already takes everyone for alive. DEAD_RULE, Stell's one line, goes
# out only with a flag (turn_dsl.build_dsl_user_prompt, the expansion pass).
DEAD_FLAG = "dead=1"
DEAD_RULE = "dead=1 means the character is dead."


def narrated_dead(context: Any) -> list[dict[str, Any]]:
    """The dead the narrator is shown: those at the player's place, and those whose death was recorded last turn.

    context["the_dead"] (hold_context) keeps every dead person for the
    engine's own reads (attack candidates, the hold); this is only who the
    narrator's text names. "Last turn" is the turn the context follows
    (context["turn"], the last one played): the interpreter records a death
    after the scene that shows it, so the next scene is the first to be told.
    """
    found = context.get("the_dead") if isinstance(context, dict) else None
    if not isinstance(found, dict):
        return []
    try:
        last = int(context.get("turn") or 0)
    except (TypeError, ValueError):
        last = 0
    return [
        p for p in found.get("people") or []
        if isinstance(p, dict) and (p.get("here") or (last > 0 and int(p.get("turn") or 0) >= last))
    ]


def shows_dead(lines: Any) -> bool:
    """Whether any of these narrator lines carries the dead flag (then DEAD_RULE goes with them)."""
    return any(DEAD_FLAG in str(line) for line in lines or [])


def facts(context: Any, limit: int = 6) -> list[str]:
    """The narrated dead (flagged) and the destroyed as sentences for facts_to_keep; a body here is said after its flag."""
    found = context.get("the_dead") if isinstance(context, dict) else None
    if not isinstance(found, dict):
        return []
    out: list[str] = []
    for person in narrated_dead(context):
        # An unnamed figure is "the ghoul [[A]]" to the story, never its engine number (Ghoul 1).
        name = called(person, prose=True)
        label = f"{name} [[{person.get('code')}]]" if person.get("code") else str(name or "")
        if label.strip():
            out.append(_sentence_start(f"{label} {DEAD_FLAG}"))
            if person.get("here"):
                out.append(_sentence_start(_BODY_FACTS.get(str(person.get("body") or BODY_LIES), _BODY_FACTS[BODY_LIES]).format(label=label)))
    for place in found.get("places") or []:
        label = f"{place.get('name')} [[{place.get('code')}]]" if place.get("code") else str(place.get("name") or "")
        if label.strip():
            out.append(f"{label} was destroyed in turn {place.get('turn')}.")
    return out[:limit]


def _sentence_start(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def dead_codes(conn) -> set[str]:
    try:
        return {str(r["code"] or "").upper() for r in conn.execute("SELECT code FROM npcs WHERE died_turn > 0").fetchall()}
    except Exception:
        return set()
