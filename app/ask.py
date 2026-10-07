"""Ask: a short lookup that does not advance the story.

Edit this file to change what an Ask is allowed to say or remember.
The model only sees the one matched record, not the whole world.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.db import connect
from app.llm import LlmError, _chat_json
from app.world import (
    _active_scene,
    _mention_catalog,
    _pick_mention,
    get_state,
)

# Questions that try to invent a different scene. The answer may refuse.
# Remember and edit are always dropped when this matches.
HYPOTHETICAL_RE = re.compile(
    r"\b(what if|suppose|imagine|in another|alternate|but what if|hypothetically)\b",
    re.IGNORECASE,
)

# The player is asking to reword a detail they already accept, not to add a plot.
CHANGE_REQUEST_RE = re.compile(
    r"\b(change|reword|rewrite|correct|call it|make it|describe it as|edit the description)\b",
    re.IGNORECASE,
)

# Words that add story instead of appearance. Drop a memory that introduces one
# unless that word is already in the record.
PLOT_WORDS = (
    "suddenly",
    "secret",
    "secretly",
    "ancient",
    "cursed",
    "quest",
    "portal",
    "explosion",
    "assassin",
    "kingdom",
    "prophecy",
)

MAX_ANSWER_CHARS = 520
MAX_MEMORY_CHARS = 220

# Spoken to a person in the scene, not to the person running the game.
SCENE_ASK_RE = re.compile(
    r"\b(i ask|i say|i tell|ask (?:her|him|them)|tell (?:her|him|them)|what do you think)\b",
    re.IGNORECASE,
)

ASK_SYSTEM = """You answer one look-up. You do not take a turn and you do not play the protagonist.

The input says who is being addressed in "addressed_to".
- "dm": the player is asking you, the game master, not a character. Talk to them directly and plainly about what the game has recorded. This does not break the scene. Do not narrate their body or say "you look" or "you notice" as if you are them.
- "character": they are speaking to someone who is there. A short in-character reply from that person is appropriate. Still do not start a new scene.

Other rules:
- Use only "record" and its "history" lines. If something is not there, say the game has no more on it. Talk about the world and the character in plain words.
- Two to four short sentences. No new location, time, or relationship.
- You may notice one small physical detail already implied by the name or description: colour, wear, size, a mark, or writing already mentioned.
- Put that one sentence in "remember" so it can be stored on the record. Leave "remember" empty if you added nothing.
- If they explicitly ask to reword the description, put the replacement sentence in "edit". Otherwise leave "edit" empty.
- Refuse what-if, suppose, and imagine. Do not invent history, owners, magic, or plot.
- Return only JSON: {"answer": "...", "remember": "", "edit": ""}
"""


def _clip(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def ask_voice(question: str, subject: dict[str, str] | None) -> str:
    """ooc when they are asking the DM. scene only when they are talking to someone present."""
    if subject and subject.get("kind") == "C" and SCENE_ASK_RE.search(str(question or "")):
        return "scene"
    return "ooc"


def _hypothetical(question: str) -> bool:
    return bool(HYPOTHETICAL_RE.search(str(question or "")))


def _wants_edit(question: str) -> bool:
    return bool(CHANGE_REQUEST_RE.search(str(question or ""))) and not _hypothetical(question)


def _plot_words_new(note: str, known: str) -> bool:
    known_l = known.lower()
    for word in PLOT_WORDS:
        if word in note.lower() and word not in known_l:
            return True
    return False


def accept_memory(question: str, known_text: str, remember: str, edit: str) -> tuple[str, str]:
    """Return (append_note, replacement). Either may be empty.

    This is the gate. The model may propose a sentence; this decides if it is stored.
    """
    if _hypothetical(question):
        return "", ""
    remember = _clip(remember, MAX_MEMORY_CHARS)
    edit = _clip(edit, MAX_MEMORY_CHARS)
    if remember and _plot_words_new(remember, known_text):
        remember = ""
    if edit and (not _wants_edit(question) or _plot_words_new(edit, known_text)):
        edit = ""
    if edit and remember and edit.lower() in remember.lower():
        remember = ""
    return remember, edit


# Follow-ups lean on the last thing asked about: "where did the prayer beads
# come from?" then "i can see they were added to my inventory though".
_FOLLOW_UP_RE = re.compile(r"\b(?:they|them|those|these|it|its|that|this|he|she|him|her)\b", re.IGNORECASE)
_LAST_SUBJECT: dict[str, Any] = {}


def _remember_subject(subject: dict[str, str] | None) -> None:
    if subject:
        _LAST_SUBJECT.clear()
        _LAST_SUBJECT.update(subject)


def resolve_subject(context: dict[str, Any], question: str) -> dict[str, str] | None:
    found = _resolve_subject_direct(context, question)
    if found is None and _LAST_SUBJECT and _FOLLOW_UP_RE.search(str(question or "")):
        return dict(_LAST_SUBJECT)
    return found


def _resolve_subject_direct(context: dict[str, Any], question: str) -> dict[str, str] | None:
    rows = _mention_catalog(context)
    scene_codes = set(_active_scene(context).get("present") or []) | set(_active_scene(context).get("interacting") or [])
    explicit = re.search(r"@([CILSAE])([a-z0-9_]+)", question or "", re.IGNORECASE)
    if explicit:
        return _pick_mention(rows, explicit.group(1), explicit.group(2))
    question_l = str(question or "").lower()
    hits: list[dict[str, str]] = []
    for row in rows:
        name = str(row.get("name") or "")
        first = name.split()[0].lower() if name else ""
        full = name.lower()
        if full and full in question_l:
            hits.append(row)
        elif len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", question_l):
            hits.append(row)
    if not hits:
        return None
    in_scene = [row for row in hits if row.get("code") in scene_codes]
    pool = in_scene or hits
    if len(pool) == 1:
        return pool[0]
    pool.sort(key=lambda row: len(str(row.get("name") or "")), reverse=True)
    if len(pool) > 1 and str(pool[0].get("name") or "").lower() in question_l:
        return pool[0]
    return None


def _record_for(context: dict[str, Any], subject: dict[str, str] | None) -> tuple[str, dict[str, Any]]:
    if not subject:
        return "none", {}
    kind = subject.get("kind") or ""
    code = subject.get("code") or ""
    name = subject.get("name") or ""

    def match(row: dict[str, Any]) -> bool:
        if code and str(row.get("code") or "").upper() == code.upper():
            return True
        return bool(name) and str(row.get("name") or "").lower() == name.lower()

    if kind == "I":
        for item in context.get("inventory") or []:
            if isinstance(item, dict) and match(item):
                return "item", {
                    "name": item.get("name"),
                    "code": item.get("code"),
                    "description": item.get("description") or "",
                    "item_type": item.get("item_type") or "",
                    "rarity": item.get("rarity") or "",
                    "weight": item.get("weight"),
                    "equipped_slot": item.get("equipped_slot") or "",
                    "quantity": item.get("quantity"),
                    "history": _item_history(str(item.get("name") or "")),
                }
    if kind == "C":
        pools = list(context.get("npcs") or [])
        for location in context.get("locations") or []:
            if isinstance(location, dict):
                pools.extend(location.get("npcs") or [])
        for npc in pools:
            if isinstance(npc, dict) and match(npc):
                return "npc", {
                    "name": npc.get("name"),
                    "code": npc.get("code"),
                    "summary": npc.get("summary") or "",
                    "personality": npc.get("personality") or "",
                    "race": npc.get("race") or "",
                    "role": npc.get("role") or "",
                    "attitude": npc.get("attitude") or "",
                }
    if kind == "L":
        current = context.get("current_location")
        places = list(context.get("locations") or [])
        if isinstance(current, dict):
            places = [current, *places]
        for place in places:
            if isinstance(place, dict) and match(place):
                return "location", {
                    "name": place.get("name"),
                    "code": place.get("code"),
                    "summary": place.get("summary") or "",
                    "kind": place.get("kind") or "",
                }
    if kind == "S":
        for skill in context.get("skills") or []:
            if isinstance(skill, dict) and match(skill):
                return "skill", {
                    "name": skill.get("name"),
                    "notes": skill.get("notes") or "",
                    "value": skill.get("value"),
                }
    if kind == "A":
        for ability in context.get("abilities") or []:
            if isinstance(ability, dict) and match(ability):
                return "ability", {
                    "name": ability.get("name"),
                    "code": ability.get("code"),
                    "description": ability.get("description") or "",
                }
    return kind or "none", {"name": name, "code": code}


def _store_note(kind: str, code: str, name: str, note: str, replace: bool) -> bool:
    if not note:
        return False
    with connect() as conn:
        if kind == "item" and code:
            row = conn.execute("SELECT description FROM inventory WHERE code = ?", (code,)).fetchone()
            if not row:
                return False
            current = str(row["description"] or "")
            updated = note if replace else f"{current} {note}".strip()
            conn.execute("UPDATE inventory SET description = ? WHERE code = ?", (updated[:900], code))
            return True
        if kind == "npc" and code:
            row = conn.execute("SELECT summary FROM npcs WHERE code = ?", (code,)).fetchone()
            if not row:
                return False
            current = str(row["summary"] or "")
            updated = note if replace else f"{current} {note}".strip()
            conn.execute("UPDATE npcs SET summary = ? WHERE code = ?", (updated[:1400], code))
            return True
        if kind == "location" and code:
            row = conn.execute("SELECT summary FROM locations WHERE code = ?", (code,)).fetchone()
            if not row:
                return False
            current = str(row["summary"] or "")
            updated = note if replace else f"{current} {note}".strip()
            conn.execute("UPDATE locations SET summary = ? WHERE code = ?", (updated[:1400], code))
            return True
        if kind == "skill" and name:
            row = conn.execute("SELECT notes FROM player_skills WHERE name = ?", (name,)).fetchone()
            if not row:
                return False
            current = str(row["notes"] or "")
            updated = note if replace else f"{current} {note}".strip()
            conn.execute("UPDATE player_skills SET notes = ? WHERE name = ?", (updated[:700], name))
            return True
        if kind == "ability" and (code or name):
            row = conn.execute(
                "SELECT description FROM abilities WHERE code = ? OR name = ?",
                (code, name),
            ).fetchone()
            if not row:
                return False
            current = str(row["description"] or "")
            updated = note if replace else f"{current} {note}".strip()
            conn.execute(
                "UPDATE abilities SET description = ? WHERE code = ? OR name = ?",
                (updated[:900], code, name),
            )
            return True
    return False


def _item_history(name: str, limit: int = 4) -> list[str]:
    """Journal lines that mention this item (how and when it arrived), oldest first.

    Ask rows and out-of-character notes (playtest #79) are not world history.
    """
    name = str(name or "").strip()
    if not name:
        return []
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT turn, kind, content FROM journal WHERE kind NOT IN ('ask', 'ooc') AND content LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{name}%", limit),
            ).fetchall()
    except Exception:
        return []
    return [f"turn {row['turn']} ({row['kind']}): {str(row['content'])[:200]}" for row in reversed(rows)]


def _journal_ask(question: str, answer: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(row["value"]) if row else 0
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, "ask", f"Q: {question[:500]}\nA: {answer[:MAX_ANSWER_CHARS]}"),
        )


def ask_about(question: str) -> dict[str, Any]:
    """Answer one question without incrementing the turn or loading the whole world."""
    question = _clip(question, 500)
    if not question:
        return {"ok": False, "error": "Type a question first.", "advanced_turn": False}
    context = get_state(include_hidden=True)
    subject = resolve_subject(context, question)
    kind, record = _record_for(context, subject)
    known = " ".join(str(value) for value in record.values() if value not in (None, ""))
    if _hypothetical(question):
        answer = "That would be a different story. Nothing like that is written on the record."
        _journal_ask(question, answer)
        return {
            "ok": True,
            "question": question,
            "answer": answer,
            "subject": subject,
            "remembered": False,
            "edited": False,
            "advanced_turn": False,
        }
    voice = ask_voice(question, subject)
    if not record or not any(record.get(key) for key in ("name", "code")):
        answer = (
            "I can't tell which thing you mean. Name it, or type @ and pick it from the list."
        )
        _journal_ask(question, answer)
        return {
            "ok": True,
            "question": question,
            "answer": answer,
            "subject": None,
            "remembered": False,
            "edited": False,
            "advanced_turn": False,
            "voice": voice,
        }
    _remember_subject(subject)
    packet = json.dumps(
        {
            "addressed_to": "character" if voice == "scene" else "dm",
            "question": question,
            "record": record,
        },
        ensure_ascii=True,
    )
    try:
        parsed = _chat_json(ASK_SYSTEM, packet, timeout=45, phase="ask", max_tokens=280)
    except LlmError as exc:
        return {"ok": False, "error": str(exc), "advanced_turn": False}
    answer = _clip(str(parsed.get("answer") or ""), MAX_ANSWER_CHARS)
    if not answer:
        answer = "Nothing else is written down for that."
    remember, edit = accept_memory(question, known, str(parsed.get("remember") or ""), str(parsed.get("edit") or ""))
    stored = False
    edited = False
    if edit:
        edited = _store_note(kind, str(record.get("code") or ""), str(record.get("name") or ""), edit, replace=True)
    elif remember:
        stored = _store_note(kind, str(record.get("code") or ""), str(record.get("name") or ""), remember, replace=False)
    _journal_ask(question, answer)
    return {
        "ok": True,
        "question": question,
        "answer": answer,
        "subject": {"kind": kind, "name": record.get("name") or (subject or {}).get("name") or "", "code": record.get("code") or ""},
        "remembered": stored,
        "edited": edited,
        "advanced_turn": False,
        "voice": voice,
    }
