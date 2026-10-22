"""People pencilled in: a newly made person is a sketch until the story brings them back.

Fault class (run fault log F26 and its continuations, F35, F163, F22, F103,
F10): an NPC_NEW op, or a figure the binder or the prose seeding minted, made a
permanent person at once, so every bad mint lasted the whole game (the
wherryman spoken to last turn minted again under a new name, two rows for one
hooded figure, a name read off a page stored as someone here). The engine kept
adding catch rules in front of the mint (_figure_hints, name_only_spoken_of,
_known_by_mark, _QUALITY_OF_RE ...).

The mechanism here does not refuse a mint. Every person made during a turn is
stored as before, with ``npcs.sketch_turn`` set to that turn: a sketch. The row
is a normal person in every other way, so the narrator still sees them next turn
and can bring them back. Then, once a turn (``settle``):

  * Same turn, one figure: the new people the prose does not name are capped at
    the figures it shows; two sketches for one figure collapse into the first.
  * Confirmed: a later turn brings the sketch back (an op names or codes them,
    the prose tags their code or names them as present, the player names or
    @codes them, a conversation is held with them), or something hangs on them
    (a job they gave, the party, a venue they keep).
  * At confirmation, when someone else is already known at that place or in
    that trade, one small ask decides identity ("Is this the same person as one
    of these? ... Answer a code or new."). A code merges the sketch into that
    person (their rows, aliases and the turn's code tags move over); "new" keeps
    them. Engine first: no one to confuse them with, or the other person named
    beside them in the same prose, needs no ask; the same name needs none either.
  * Talked with: a conversation held with a sketch confirms them on the turn
    they were made (a clerk who gave directions once is a real person).
  * Faded: a sketch not brought back within FADE_AFTER turns leaves the world
    (the narrator and the people list no longer see them) but is kept in
    ``faded_people`` with their aliases and talks. Stell (2026-10-22, on a side
    note that a once-met person "may be forgotten"): a faded person mentioned
    again by the same name comes back as themselves, and a new sketch of the
    same trade at the same place is asked about them like anyone known.

Every decision is a turn_ledger note. Rows the pass changes are added to the
turn's rewind record first, so a rewind restores a faded or merged sketch.
The ask is injectable (``set_identity_ask``); tests use a fake.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable

from app import turn_ledger

FADE_AFTER = 5  # turns a sketch may go unmentioned before it fades
MAX_CANDIDATES = 5
PHASE = "sketch_identity"
MAX_TOKENS = 30

Ask = Callable[..., Any]
_ASK_OVERRIDE: list[Ask | None] = [None]

# Kept short on purpose (Stell, 2026-10-21: prompts "as simple but understood as possible").
_SYSTEM = (
    "You keep track of the people in a story. "
    "Answer only JSON: {\"answer\": \"...\"}"
)

# Tables a rewind restores by row (world._restore_snapshot_rows): rows of these
# that the pass changes are added to the turn's snapshot first.
_RESTORABLE = {"npcs", "aliases", "relationships", "conversations", "events", "quests"}
# A row in one of these ties the person to the game: they never fade.
_TIES = (
    ("quests", "giver_npc_id"),
    ("party_members", "npc_id"),
    ("locations", "keeper_npc_id"),
)
_SPEECH_VERB = re.compile(r"(?:says?|asks?|mutters?|whispers?|calls?|snorts?|grunts?)$")
_VAGUE = {"figure", "shape", "silhouette", "form", "person", "someone", "stranger"}
# A first word that is a title or a trade, not a given name: "Captain" or
# "Harbour" alone is not this person ("Captain Rafe", "Harbour Master Odo").
TITLE_WORDS = frozenset({
    "the", "a", "an", "old", "young", "little", "big", "captain", "harbour", "harbor", "master", "mistress",
    "mother", "father", "brother", "sister", "lady", "lord", "sir", "dame", "mister", "goodman", "goodwife",
    "widow", "uncle", "aunt", "elder", "reeve", "sergeant", "guard", "keeper",
})


def set_identity_ask(ask: Ask | None) -> Ask | None:
    """Use ``ask`` for the identity question (None: the turn's own model). Returns the previous one."""
    previous = _ASK_OVERRIDE[0]
    _ASK_OVERRIDE[0] = ask
    return previous


def model_ask() -> Ask:
    """The turn's own model, through the same JSON call the other small asks use."""

    def ask(system: str, user: str, *, max_tokens: int, phase: str) -> Any:
        from app.llm import _chat_json

        return _chat_json(system, user, timeout=60, usage=[], phase=phase, max_tokens=max_tokens, trace=[])

    return ask


def identity_ask() -> Ask:
    return _ASK_OVERRIDE[0] or model_ask()


# --------------------------------------------------------------------- marking


def pencil_in(conn, max_id_before: int, turn: int) -> list[int]:
    """Mark everyone made this turn (id above ``max_id_before``) as a sketch of ``turn``."""
    try:
        rows = conn.execute(
            "SELECT id, name FROM npcs WHERE id > ? AND COALESCE(sketch_turn, 0) = 0", (int(max_id_before),)
        ).fetchall()
    except Exception:
        return []
    ids = [int(r["id"]) for r in rows]
    if ids:
        conn.execute(
            f"UPDATE npcs SET sketch_turn = ? WHERE id IN ({','.join('?' * len(ids))})", (max(1, int(turn)), *ids)
        )
        turn_ledger.note("npc", "pencilled_in", names=[str(r["name"] or "") for r in rows])
    return ids


def is_sketch(row: Any) -> bool:
    try:
        return int(row["sketch_turn"] or 0) > 0
    except Exception:
        return False


# ------------------------------------------------------------------- the pass


def settle(
    conn,
    *,
    turn: int,
    max_id_before: int,
    narration: str,
    player_line: str = "",
    touched_ids: Iterable[int] = (),
    bound_hints: dict[int, str] | None = None,
    ask: Ask | None = None,
) -> dict[str, Any]:
    """Pencil in this turn's new people, collapse same-turn twins, confirm, merge or fade sketches.

    Returns {"pencilled", "collapsed", "confirmed", "merged", "faded"} and the
    code renames ({old: new}) a caller applies to the turn's own text.
    """
    report: dict[str, Any] = {"pencilled": [], "collapsed": [], "confirmed": [], "merged": [], "faded": [], "renames": {}}
    turn = max(1, int(turn or 0))
    text = re.sub(r"\s*\[\[[A-Z0-9]+\]\]", "", str(narration or ""))
    from app import venues

    unspoken = venues.strip_speech(text)
    report["pencilled"] = pencil_in(conn, max_id_before, turn)
    _collapse_twins(conn, turn, report, text, unspoken, bound_hints or {})
    _revive_by_name(conn, turn, report)
    touched = {int(i) for i in touched_ids or () if i}
    rows = conn.execute("SELECT * FROM npcs WHERE COALESCE(sketch_turn, 0) > 0 ORDER BY id").fetchall()
    for row in rows:
        if conn.execute("SELECT 1 FROM npcs WHERE id = ?", (int(row["id"]),)).fetchone() is None:
            continue  # merged away earlier in this pass
        made = int(row["sketch_turn"] or 0)
        evidence = _tie(conn, int(row["id"]))
        if not evidence and made < turn:
            evidence = _brought_back(conn, row, turn, narration, unspoken, player_line, touched)
        elif not evidence and _talked_with(conn, int(row["id"]), turn):
            evidence = "conversation"
        if evidence:
            _confirm(conn, row, turn, evidence, unspoken, report, ask)
        elif made < turn and turn - made >= FADE_AFTER:
            _fade(conn, row, turn, report)
    return report


def _talked_with(conn, npc_id: int, turn: int) -> bool:
    try:
        return conn.execute(
            "SELECT 1 FROM conversations WHERE npc_id = ? AND turn = ? LIMIT 1", (npc_id, int(turn))
        ).fetchone() is not None
    except Exception:
        return False


def _tie(conn, npc_id: int) -> str:
    for table, column in _TIES:
        try:
            if conn.execute(f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (npc_id,)).fetchone():
                return f"{table}.{column}"
        except Exception:
            continue
    return ""


def _name_forms(row: Any, others: list[str]) -> list[str]:
    """The full name, and the first name when no one else wears it."""
    name = str(row["name"] or "").strip()
    if not name:
        return []
    forms = [name]
    first = name.split()[0]
    if first != name and len(first) >= 3 and first.lower() not in TITLE_WORDS:
        if not any(o.lower() != name.lower() and o.split() and o.split()[0].lower() == first.lower() for o in others):
            forms.append(first)
    return forms


def _brought_back(conn, row: Any, turn: int, narration: str, unspoken: str, player_line: str, touched: set[int]) -> str:
    """Why this sketch counts as brought back this turn, or ""."""
    from app import world

    npc_id = int(row["id"])
    code = str(row["code"] or "").strip()
    if npc_id in touched:
        return "ops"
    if code and re.search(r"\[\[" + re.escape(code) + r"\]\]", str(narration or "")):
        return "prose_code"
    line = str(player_line or "")
    if code and re.search(r"@" + re.escape(code) + r"(?![A-Za-z0-9_])", line, re.I):
        return "player_code"
    try:
        others = [str(r[0] or "") for r in conn.execute("SELECT name FROM npcs WHERE id != ?", (npc_id,)).fetchall()]
    except Exception:
        others = []
    for form in _name_forms(row, others):
        pattern = r"(?<![\w'])" + re.escape(form) + r"(?![\w'])"
        if form[:1].isupper() and world._named_as_present(unspoken, pattern):
            return "prose_name"
        if line and re.search(pattern, line, re.I):
            return "player_name"
    # The figure phrase they were bound to ("the hooded woman", world._store_figure_aliases),
    # while the player is where they are: the prose often never says the name again.
    try:
        here = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        here_id = int((here[0] if here else 0) or 0)
        if code and here_id and here_id in _places_near(conn, int(row["location_id"] or 0)):
            for (alias,) in conn.execute(
                "SELECT alias FROM aliases WHERE entity_type = 'npc' AND entity_code = ?", (code,)
            ).fetchall():
                words = re.sub(r"^(?:the|a|an)\s+", "", str(alias or "").strip(), flags=re.I)
                if len(words) < 4:
                    continue
                alias_re = r"(?<![\w'])" + re.escape(words) + r"(?![\w'])"
                if world._named_as_present(unspoken, alias_re, flags=re.I) or (line and re.search(alias_re, line, re.I)):
                    return "figure_alias"
    except Exception:
        pass
    try:
        if conn.execute(
            "SELECT 1 FROM conversations WHERE npc_id = ? AND turn > ? LIMIT 1", (npc_id, int(row["sketch_turn"] or 0))
        ).fetchone():
            return "conversation"
    except Exception:
        pass
    return ""


# ------------------------------------------------------------------ identity


def _job_words(role: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", str(role or "").lower()) if len(w) >= 4} - {
        "local", "person", "stranger", "figure", "worker", "guild", "salvage", "town", "harbour", "harbor",
    }


def _places_near(conn, location_id: int) -> set[int]:
    """The place, the place it stands in, and the places inside it."""
    out = {int(location_id or 0)}
    try:
        row = conn.execute("SELECT parent_id FROM locations WHERE id = ?", (int(location_id or 0),)).fetchone()
        if row is not None and int(row[0] or 0):
            out.add(int(row[0]))
        out |= {int(r[0]) for r in conn.execute("SELECT id FROM locations WHERE parent_id = ?", (int(location_id or 0),))}
    except Exception:
        pass
    out.discard(0)
    return out


def candidates(conn, row: Any, unspoken: str = "") -> list[Any]:
    """People made before this sketch at its place (or the place around it) or in its trade.

    Someone the same prose names as present beside the sketch is another
    person, never a candidate.
    """
    from app import world

    npc_id = int(row["id"])
    places = _places_near(conn, int(row["location_id"] or 0))
    jobs = _job_words(str(row["role"] or ""))
    try:
        pool = conn.execute("SELECT * FROM npcs WHERE id < ? ORDER BY id DESC", (npc_id,)).fetchall()
    except Exception:
        return []
    same_place, same_job = [], []
    for other in pool:
        name = str(other["name"] or "").strip()
        if not name:
            continue
        if unspoken and world._named_as_present(unspoken, r"(?<![\w'])" + re.escape(name) + r"(?![\w'])"):
            continue
        at = int(other["location_id"] or 0) in places
        trade = bool(jobs & _job_words(str(other["role"] or "")))
        if at and trade:
            same_place.insert(0, other)
        elif at:
            same_place.append(other)
        elif trade:
            same_job.append(other)
    # Faded people of this trade at this place: "a clerk steps in" where the
    # clerk who once gave directions faded is asked about her too.
    if jobs:
        for other in _faded(conn):
            if int(other.get("location_id") or 0) in places and jobs & _job_words(str(other.get("role") or "")):
                same_place.append(other)
    return (same_place + same_job)[:MAX_CANDIDATES]


def _mark(row: Any) -> str:
    summary = re.sub(r"\s+", " ", str(row["summary"] or "")).strip()
    return summary[:90]


def _describe(row: Any) -> str:
    parts = [str(row["name"] or "").strip(), str(row["role"] or "").strip(), _mark(row)]
    return ", ".join(p for p in parts if p)


_MARK_STOP = {"with", "from", "that", "this", "their", "there", "they", "into", "over", "under", "about", "after",
              "before", "where", "which", "while", "worn", "weathered", "face", "eyes", "hands", "voice", "years",
              "look", "looks", "man", "woman", "figure", "someone", "person", "local"}


def _mark_words(row: Any) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", _mark(row).lower()) if len(w) >= 4} - _MARK_STOP


def _same_person_evidence(row: Any, other: Any) -> bool:
    """The engine's own reason to believe a model-named match: the same trade, or a mark they share."""
    if _job_words(str(row["role"] or "")) & _job_words(str(other["role"] or "")):
        return True
    return bool(_mark_words(row) & _mark_words(other))


def build_ask(row: Any, others: list[Any]) -> tuple[str, str]:
    """(system, user) for the identity question: one plain question, no examples."""
    lines = [f"A person in the story: {_describe(row)}.", "Is this the same person as one of these?"]
    lines += [f"{str(o['code'] or '').strip()}: {_describe(o)}" for o in others]
    # The choices by name: "Answer a code or new" came back as "code" (8B run 153, T2).
    lines.append("Answer with one of: " + ", ".join([*(str(o["code"] or "").strip() for o in others), "new"]) + ".")
    return _SYSTEM, "\n".join(lines)


def parse_answer(raw: Any, codes: Iterable[str]) -> str:
    """A code from ``codes``, "new", or "" when the reply is unusable."""
    codes = [str(c) for c in codes if str(c or "").strip()]
    data = raw
    if not isinstance(data, dict):
        text = str(raw or "")
        try:
            data = json.loads(text[text.find("{"): text.rfind("}") + 1]) if "{" in text else text
        except Exception:
            data = text
    if isinstance(data, dict):
        data = data.get("answer") or data.get("code") or next(iter(data.values()), "") if data else ""
    answer = str(data or "").strip()
    if re.fullmatch(r"(?i)\W*new\W*", answer) or re.match(r"(?i)\W*new\b", answer):
        return "new"
    hits = [c for c in codes if re.search(r"(?<![A-Za-z0-9])" + re.escape(c) + r"(?![A-Za-z0-9])", answer)]
    return hits[0] if len(hits) == 1 else ""


def _confirm(conn, row: Any, turn: int, evidence: str, unspoken: str, report: dict[str, Any], ask: Ask | None) -> None:
    name = str(row["name"] or "")
    others = candidates(conn, row, unspoken)
    target = None
    how = ""
    same_name = [o for o in others if str(o["name"] or "").strip().lower() == name.strip().lower()]
    if same_name:
        target, how = same_name[0], "same_name"
    elif others:
        system, user = build_ask(row, others)
        try:
            raw = (ask or identity_ask())(system, user, max_tokens=MAX_TOKENS, phase=PHASE)
        except Exception as exc:
            raw = None
            turn_ledger.note("npc", "sketch_identity_ask_failed", name=name, error=f"{type(exc).__name__}: {exc}"[:200])
        answer = parse_answer(raw, [str(o["code"] or "") for o in others])
        turn_ledger.note("npc", "sketch_identity_asked", name=name, asked=[str(o["code"] or "") for o in others],
                         answer=answer or "unusable", raw=str(raw)[:120])
        if answer and answer != "new":
            target = next((o for o in others if str(o["code"] or "") == answer), None)
            how = "asked"
            # One model answer must not fuse two real people (side note,
            # 2026-10-22): the engine also has to see it, the same trade or a
            # mark they share. Otherwise they stay two people.
            if target is not None and not _same_person_evidence(row, target):
                turn_ledger.note("npc", "sketch_merge_unsupported", name=name, answered=answer,
                                 known=str(target["name"] or ""))
                target = None
    if isinstance(target, dict) and target.get("_faded_id"):
        _revive(conn, target, row, turn, report)
        return
    if target is not None:
        merge_into(conn, row, target, turn, report)
        _keep_for_rewind(conn, turn, "npcs", int(target["id"]))
        conn.execute("UPDATE npcs SET sketch_turn = 0 WHERE id = ?", (int(target["id"]),))
        turn_ledger.note("npc", "sketch_is_known_person", name=name, known=str(target["name"] or ""), by=how,
                         evidence=evidence)
        return
    _keep_for_rewind(conn, turn, "npcs", int(row["id"]))
    conn.execute("UPDATE npcs SET sketch_turn = 0 WHERE id = ?", (int(row["id"]),))
    report["confirmed"].append(name)
    turn_ledger.note("npc", "sketch_confirmed", name=name, evidence=evidence)


# ------------------------------------------------------------- merge and fade


def _ref_columns(conn) -> list[tuple[str, str, bool]]:
    """(table, column, is_foreign_key) for every column that holds an npcs.id."""
    out: list[tuple[str, str, bool]] = []
    try:
        tables = [str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()]
    except Exception:
        return out
    for table in tables:
        if table == "npcs" or table.startswith("sqlite_"):
            continue
        try:
            fks = {(str(f["from"])) for f in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
                   if str(f["table"]) == "npcs"}
            cols = [str(c["name"]) for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        except Exception:
            continue
        for col in cols:
            if col in fks:
                out.append((table, col, True))
            elif col.endswith("npc_id"):
                out.append((table, col, False))
    return out


def _keep_for_rewind(conn, turn: int, table: str, row_id: int | None = None, where: str = "", params: tuple = ()) -> None:
    """Add the row(s) to this turn's rewind record, unless it already holds them (the first copy wins)."""
    if table not in _RESTORABLE:
        return
    try:
        snap = conn.execute(
            "SELECT id, snapshot FROM turn_snapshots WHERE turn = ? ORDER BY id DESC LIMIT 1", (int(turn),)
        ).fetchone()
        if snap is None:
            return
        data = json.loads(snap["snapshot"] or "{}")
        if not isinstance(data, dict) or data.get("format") != "ai-rpg-delta-v1":
            return
        if row_id is not None:
            where, params = "id = ?", (int(row_id),)
        found = conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()
        if not found:
            return
        max_ids = data.get("max_ids") or {}
        bucket = data.setdefault("rows", {}).setdefault(table, [])
        held = {row.get("id") for row in bucket if isinstance(row, dict)}
        changed = False
        for row in found:
            item = {key: row[key] for key in row.keys()}
            # A row made this turn is deleted by the rewind anyway.
            if table in max_ids and int(item.get("id") or 0) > int(max_ids.get(table) or 0):
                continue
            if item.get("id") in held:
                continue
            bucket.append(item)
            held.add(item.get("id"))
            changed = True
        if changed:
            conn.execute("UPDATE turn_snapshots SET snapshot = ? WHERE id = ?",
                         (json.dumps(data, ensure_ascii=True), int(snap["id"])))
    except Exception as exc:
        turn_ledger.note("npc", "sketch_rewind_record_failed", table=table, error=f"{type(exc).__name__}: {exc}"[:200])


def merge_into(conn, src: Any, dst: Any, turn: int, report: dict[str, Any] | None = None) -> None:
    """Fold person ``src`` into ``dst``: their rows, their name as an alias, then remove ``src``."""
    src_id, dst_id = int(src["id"]), int(dst["id"])
    if src_id == dst_id:
        return
    src_code, dst_code = str(src["code"] or "").strip(), str(dst["code"] or "").strip()
    # Kept whole, so a wrong merge can be seen and undone without a rewind.
    try:
        record = {key: src[key] for key in src.keys()}
        record["_merged_into"] = dst_code
        talks = [int(r[0]) for r in conn.execute("SELECT id FROM conversations WHERE npc_id = ?", (src_id,)).fetchall()]
        conn.execute(
            "INSERT INTO faded_people (npc_id, name, location_id, turn_faded, record, aliases, conversation_ids) "
            "VALUES (?, ?, ?, ?, ?, '[]', ?)",
            (src_id, str(src["name"] or ""), int(src["location_id"] or 0), int(turn),
             json.dumps(record, ensure_ascii=True), json.dumps(talks)),
        )
    except Exception as exc:
        turn_ledger.note("npc", "merge_record_unkept", name=str(src["name"] or ""), error=f"{type(exc).__name__}: {exc}"[:160])
    turn_ledger.note("npc", "merged_person", merged=_describe(src), into=_describe(dst))
    _keep_for_rewind(conn, turn, "npcs", src_id)
    _keep_for_rewind(conn, turn, "npcs", dst_id)
    for table, column, fk in _ref_columns(conn):
        _keep_for_rewind(conn, turn, table, where=f"{column} = ?", params=(src_id,))
        try:
            conn.execute(f"UPDATE OR IGNORE {table} SET {column} = ? WHERE {column} = ?", (dst_id, src_id))
            if fk:
                # A row of the sketch's that dst already has (one per person).
                conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (src_id,))
        except Exception:
            continue
    _drop_clock(conn, src_id)
    if src_code and dst_code:
        _keep_for_rewind(conn, turn, "aliases", where="entity_type = 'npc' AND entity_code = ?", params=(src_code,))
        conn.execute("UPDATE aliases SET entity_code = ? WHERE entity_type = 'npc' AND entity_code = ?", (dst_code, src_code))
    # What the sketch's record adds: an empty summary, pronouns, facts.
    try:
        facts = json.loads(dst["known_facts"] or "[]")
        facts = facts if isinstance(facts, list) else []
        for fact in json.loads(src["known_facts"] or "[]") or []:
            if fact not in facts:
                facts.append(fact)
    except Exception:
        facts = None
    conn.execute(
        "UPDATE npcs SET summary = CASE WHEN COALESCE(summary, '') = '' THEN ? ELSE summary END, "
        "pronouns = CASE WHEN COALESCE(pronouns, '') = '' THEN ? ELSE pronouns END, "
        "known_facts = COALESCE(?, known_facts) WHERE id = ?",
        (str(src["summary"] or ""), str(src["pronouns"] or ""), json.dumps(facts) if facts is not None else None, dst_id),
    )
    conn.execute("DELETE FROM npcs WHERE id = ?", (src_id,))
    src_name = str(src["name"] or "").strip()
    if src_name and dst_code and src_name.lower() != str(dst["name"] or "").strip().lower():
        try:
            conn.execute("INSERT OR IGNORE INTO aliases (alias, entity_type, entity_code) VALUES (?, 'npc', ?)",
                         (src_name, dst_code))
        except Exception:
            pass
    if report is not None:
        report["merged"].append({"from": src_name, "into": str(dst["name"] or "")})
        if src_code and dst_code:
            report["renames"][src_code] = dst_code


def _drop_clock(conn, npc_id: int) -> None:
    """The person's quest clock (local_intel keys it by id; a rewind restores the whole table)."""
    try:
        conn.execute("DELETE FROM quest_clocks WHERE subject_key = ?", (f"npc:{int(npc_id)}",))
    except Exception:
        pass


def _fade(conn, row: Any, turn: int, report: dict[str, Any]) -> None:
    npc_id = int(row["id"])
    code = str(row["code"] or "").strip()
    _keep_for_rewind(conn, turn, "npcs", npc_id)
    for table, column, fk in _ref_columns(conn):
        _keep_for_rewind(conn, turn, table, where=f"{column} = ?", params=(npc_id,))
        if not fk:
            try:
                conn.execute(f"UPDATE {table} SET {column} = 0 WHERE {column} = ?", (npc_id,))
            except Exception:
                pass
    _drop_clock(conn, npc_id)
    aliases: list[str] = []
    if code:
        aliases = [str(r[0]) for r in conn.execute(
            "SELECT alias FROM aliases WHERE entity_type = 'npc' AND entity_code = ?", (code,)).fetchall()]
        _keep_for_rewind(conn, turn, "aliases", where="entity_type = 'npc' AND entity_code = ?", params=(code,))
        conn.execute("DELETE FROM aliases WHERE entity_type = 'npc' AND entity_code = ?", (code,))
    _store_faded(conn, row, turn, aliases)
    conn.execute("DELETE FROM npcs WHERE id = ?", (npc_id,))
    report["faded"].append(str(row["name"] or ""))
    turn_ledger.note("npc", "sketch_faded", name=str(row["name"] or ""), made=int(row["sketch_turn"] or 0),
                     unmentioned_turns=turn - int(row["sketch_turn"] or 0))


# ------------------------------------------------- faded people come back


def _store_faded(conn, row: Any, turn: int, aliases: list[str]) -> None:
    """Keep a faded person's record, aliases and talks (their talk rows stay, npc_id set to NULL)."""
    npc_id = int(row["id"])
    try:
        talks = [int(r[0]) for r in conn.execute("SELECT id FROM conversations WHERE npc_id = ?", (npc_id,)).fetchall()]
        conn.execute(
            "INSERT INTO faded_people (npc_id, name, location_id, turn_faded, record, aliases, conversation_ids) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (npc_id, str(row["name"] or ""), int(row["location_id"] or 0), int(turn),
             json.dumps({key: row[key] for key in row.keys()}, ensure_ascii=True), json.dumps(aliases), json.dumps(talks)),
        )
    except Exception as exc:
        turn_ledger.note("npc", "sketch_fade_store_failed", name=str(row["name"] or ""), error=f"{type(exc).__name__}: {exc}"[:200])


def _faded(conn) -> list[dict[str, Any]]:
    """Faded people still out of the world (a rewind may have put one back: that entry is dropped)."""
    out: list[dict[str, Any]] = []
    try:
        rows = conn.execute("SELECT * FROM faded_people ORDER BY id DESC").fetchall()
    except Exception:
        return out
    for entry in rows:
        if conn.execute("SELECT 1 FROM npcs WHERE id = ?", (int(entry["npc_id"]),)).fetchone() is not None:
            conn.execute("DELETE FROM faded_people WHERE id = ?", (int(entry["id"]),))
            continue
        try:
            record = json.loads(entry["record"] or "{}")
        except Exception:
            continue
        # A merged person's record is kept for audit and undo, not offered back.
        if isinstance(record, dict) and record.get("name") and not record.get("_merged_into"):
            # The code the ask shows: a digit keeps it apart from the people's letter codes.
            out.append({**record, "code": f"X{int(entry['id'])}", "_faded_id": int(entry["id"])})
    return out


_KEEP_ON_REVIVE = {"id", "code", "location_id", "sketch_turn"}


def _revive(conn, faded: dict[str, Any], row: Any, turn: int, report: dict[str, Any]) -> None:
    """The sketch ``row`` is the faded person come back: their record, aliases and talks move onto it."""
    entry = conn.execute("SELECT * FROM faded_people WHERE id = ?", (int(faded["_faded_id"]),)).fetchone()
    record = json.loads(entry["record"] or "{}")
    npc_id, code = int(row["id"]), str(row["code"] or "")
    _keep_for_rewind(conn, turn, "npcs", npc_id)
    cols = [str(c["name"]) for c in conn.execute("PRAGMA table_info(npcs)").fetchall()]
    values = {key: record[key] for key in cols if key in record and key not in _KEEP_ON_REVIVE}
    values["sketch_turn"] = 0
    try:
        conn.execute(f"UPDATE npcs SET {', '.join(k + ' = ?' for k in values)} WHERE id = ?", (*values.values(), npc_id))
    except Exception:
        # Their name is held by someone else at this place: keep the sketch's name.
        values.pop("name", None)
        conn.execute(f"UPDATE npcs SET {', '.join(k + ' = ?' for k in values)} WHERE id = ?", (*values.values(), npc_id))
    sketch_name = str(row["name"] or "").strip()
    for alias in json.loads(entry["aliases"] or "[]") + ([sketch_name] if sketch_name.lower() != str(record.get("name") or "").strip().lower() else []):
        conn.execute("INSERT OR IGNORE INTO aliases (alias, entity_type, entity_code) VALUES (?, 'npc', ?)", (alias, code))
    talks = [int(t) for t in json.loads(entry["conversation_ids"] or "[]")]
    if talks:
        conn.execute(f"UPDATE conversations SET npc_id = ? WHERE npc_id IS NULL AND id IN ({','.join('?' * len(talks))})",
                     (npc_id, *talks))
    conn.execute("DELETE FROM faded_people WHERE id = ?", (int(entry["id"]),))
    report["confirmed"].append(str(record.get("name") or sketch_name))
    turn_ledger.note("npc", "faded_person_back", name=str(record.get("name") or ""), as_sketch=sketch_name,
                     faded_on=int(entry["turn_faded"] or 0))


def _revive_by_name(conn, turn: int, report: dict[str, Any]) -> None:
    """A sketch made this turn under a faded person's exact name is that person, come back."""
    fresh = conn.execute("SELECT * FROM npcs WHERE sketch_turn = ? ORDER BY id", (int(turn),)).fetchall()
    if not fresh:
        return
    faded = _faded(conn)
    for row in fresh:
        name = str(row["name"] or "").strip().lower()
        match = [f for f in faded if str(f.get("name") or "").strip().lower() == name]
        if len(match) != 1:
            continue
        _revive(conn, match[0], row, turn, report)
        faded = [f for f in faded if f is not match[0]]


# --------------------------------------------------------- same-turn twins


def figures_shown(unspoken: str, known_names: Iterable[str] = ()) -> int:
    """How many distinct new figures the narration shows.

    world._figure_hints already folds "the scarred woman" after "a wiry woman";
    here a vague definite one ("the stranger says", "the figure") after any
    earlier figure is that figure too (F35: "a figure steps into the light ...
    the stranger says" minted two people).
    """
    from app import world

    count, seen = 0, False
    for hint in world._figure_hints(unspoken, list(known_names)):
        words = hint.lower().split()
        noun = words[-2] if len(words) > 1 and _SPEECH_VERB.fullmatch(words[-1]) else words[-1]
        if words[0] == "the" and seen and noun in _VAGUE:
            continue
        count += 1
        seen = True
    return count


def _collapse_twins(conn, turn: int, report: dict[str, Any], text: str, unspoken: str, bound_hints: dict[int, str]) -> None:
    """New people this turn beyond the figures the prose shows are one person (F35)."""
    from app import world

    try:
        new = conn.execute("SELECT * FROM npcs WHERE sketch_turn = ? ORDER BY id", (turn,)).fetchall()
    except Exception:
        return
    if len(new) < 2:
        return
    # Two sketches bound to the same figure phrase are that one figure.
    by_hint: dict[str, Any] = {}
    for row in list(new):
        hint = str(bound_hints.get(int(row["id"])) or "").strip().lower()
        if not hint:
            continue
        if hint in by_hint:
            _collapse(conn, row, by_hint[hint], turn, report, why="same_figure")
            new = [r for r in new if int(r["id"]) != int(row["id"])]
        else:
            by_hint[hint] = row
    if len(new) < 2:
        return

    def named(row: Any) -> bool:
        name = str(row["name"] or "").strip()
        first = name.split()[0] if " " in name else ""
        forms = [name] + ([first] if len(first) >= 3 and first.lower() not in TITLE_WORDS else [])
        return any(world._named_as_present(unspoken, r"(?<![\w'])" + re.escape(f) + r"(?![\w'])") for f in forms if f)

    unnamed = [r for r in new if not named(r)]
    named_new = [r for r in new if r not in unnamed]
    if len(unnamed) < 2:
        return
    try:
        known = [str(r[0] or "") for r in conn.execute("SELECT name FROM npcs WHERE COALESCE(sketch_turn, 0) != ?", (turn,))]
    except Exception:
        known = []
    free = max(0, figures_shown(unspoken, known) - len(named_new))
    # Only a count of exactly one figure folds them: with none counted the
    # engine cannot tell, and a twin left standing is still asked about when it
    # is confirmed (the earlier one is a candidate), while a wrong fold loses a person.
    if free == 1:
        keep = unnamed[0]
        for row in unnamed[1:]:
            _collapse(conn, row, keep, turn, report, why="beyond_figures_shown")
    elif len(unnamed) > free:
        turn_ledger.note("npc", "sketches_beyond_figures", names=[str(r["name"] or "") for r in unnamed], figures=free)


def _collapse(conn, row: Any, keep: Any, turn: int, report: dict[str, Any], *, why: str) -> None:
    merge_into(conn, row, keep, turn, report)
    report["collapsed"].append({"from": str(row["name"] or ""), "into": str(keep["name"] or "")})
    turn_ledger.note("npc", "sketch_twin_collapsed", name=str(row["name"] or ""), kept=str(keep["name"] or ""), why=why)
