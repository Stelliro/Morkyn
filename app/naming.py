"""
Naming: when the player asks for a name, the world must answer with one.

A 100-turn continuity probe planted "the sealed letter is addressed to Corvin
Marrow" on turn 2. Asked to read that name aloud on turn 26 the model answered
plainly. Asked again on turn 94 it wrote:

    ...the name you read brings a weight to your chest...

It still knew a letter existed. It even volunteered the debt to Hask unprompted
in the same paragraph. It simply would not commit to the name -- it narrated
*around* the fact. That is the same failure class as movement and venues: the
model describes a state change instead of recording one, and prompt guidance
alone has never fixed it here.

So naming gets the same treatment: a contract that tells the model what the
answer already is, and a deterministic repair that enforces an answer when the
narration dodges.

The rule, in one line: **when a name is demanded, reuse the established one if
the world has committed to it, otherwise mint one and write it down.**

  * ``name_request_intent`` classifies the player's line as demanding a name.
  * ``resolve_name_demand`` answers it -- from the ledger, then from history,
    then by minting a fresh name and recording it so the answer never drifts.
  * ``enforce_named_answer`` rewrites narration that dodged.
  * ``naming_contract`` is what the model is told before it writes.

Minted names are recorded in ``name_ledger`` precisely so the second asking
matches the first. An invented name that is not written down is just a
different dodge.
"""
from __future__ import annotations

import re
from typing import Any

# Phrase-level, never single words. "name" alone appears constantly in ordinary
# prose ("a name for the road", "names carved in the post"); triggering on it
# turned every third turn into a naming demand during development.
_DEMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    # asking someone else / reading a written name
    (r"\bread(?:s|ing)?\s+(?:out\s+)?the\s+name\b", "written"),
    (r"\bthe\s+name\s+(?:written|inscribed|printed|marked|scrawled)\b", "written"),
    # Both orders: the embedded question ("I ask who it is addressed to") and
    # the direct one ("Who is it addressed to?").
    (r"\bwho\s+(?:it|this|that)\s+is\s+addressed\s+to\b", "written"),
    (r"\bwho\s+is\s+(?:it|this|that)\s+addressed\s+to\b", "written"),
    (r"\baddressed\s+to\s+wh(?:om|o)\b", "written"),
    (r"\bwhat\s+name\s+is\s+(?:on|written)\b", "written"),
    (r"\bsays?\s+the\s+name\s+(?:out\s+loud|aloud)\b", "written"),
    (r"\bwhat\s+(?:is|are|was)\s+(?:his|her|their|its|the)\s+name\b", "person"),
    # Embedded form: "I ask the bargeman what his name is."
    (r"\bwhat\s+(?:his|her|their|its|the)\s+name\s+(?:is|was)\b", "person"),
    (r"\bask(?:s|ed|ing)?\s+(?:for\s+)?(?:his|her|their|the\w*)\s+name\b", "person"),
    (r"\bwhat\s+(?:do|does)\s+(?:they|he|she|people)\s+call\b", "person"),
    (r"\bwhat\s+(?:are|is)\s+(?:you|they|he|she)\s+called\b", "person"),
    (r"\bgive\s+(?:me|us|them)\s+(?:a|your|his|her|their)\s+name\b", "person"),
    (r"\btell\s+(?:me|us|them|him|her)\s+(?:your|his|her|their)\s+name\b", "person"),
    # the player naming themselves
    (r"\b(?:i|you)\s+(?:give|state|say)\s+my\s+name\b", "self"),
    (r"\bintroduce\s+(?:myself|yourself)\b", "self"),
    (r"\bwhat\s+is\s+my\s+name\b", "self"),
)

_COMPILED = tuple((re.compile(p, re.I), kind) for p, kind in _DEMAND_PATTERNS)

# Words that look like names because they start a sentence or a title.
_NOT_A_NAME = {
    "the", "a", "an", "you", "your", "yours", "i", "my", "we", "they", "he", "she", "it",
    "this", "that", "these", "those", "there", "here", "then", "when", "what", "who",
    "why", "how", "and", "but", "or", "so", "if", "as", "at", "in", "on", "of", "to",
    "for", "from", "with", "without", "north", "south", "east", "west", "yes", "no",
    "someone", "somebody", "nobody", "everyone", "stranger", "unknown", "none",
    "his", "her", "their", "its", "one", "two", "three", "sir", "madam", "lord", "lady",
}

_PROPER_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b")

# Words that can never be the thing a name belongs to. This list exists because
# a first cut keyed "read the name written on it aloud" to the subject "written"
# and "I ask the stranger what their name is" to "what" -- so the ledger stored
# a name under a participle, found nothing in history, and minted a *wrong*
# answer that contradicted the established one. Function words, the verbs these
# requests are built from, and "name" itself all have to go.
_SUBJECT_STOP = {
    "name", "names", "named", "aloud", "loud", "out", "there", "here", "confusion",
    "moment", "way", "time", "place", "thing", "things", "one", "someone", "person",
    "written", "inscribed", "printed", "marked", "scrawled", "read", "reads", "reading",
    "take", "takes", "taking", "say", "says", "saying", "ask", "asks", "asking",
    "tell", "tells", "telling", "give", "gives", "giving", "what", "who", "whom",
    "and", "but", "for", "with", "from", "that", "this", "about", "before", "after",
    "nearest", "next", "first", "last", "other", "same", "own", "very", "just",
    "is", "was", "are", "were", "it", "its", "his", "her", "their", "my", "your",
}

# Concrete things a name can belong to. A curated head list beats "last noun
# after 'the'", which is what produced the participle bug above.
_NAMEABLE_HEADS = {
    # carried / handled objects
    "letter", "parcel", "package", "note", "message", "envelope", "scroll", "book",
    "ledger", "map", "charm", "amulet", "ring", "blade", "sword", "knife", "dagger",
    "axe", "bow", "staff", "token", "coin", "seal", "banner", "flag", "key",
    # people
    "stranger", "man", "woman", "child", "boy", "girl", "merchant", "trader", "guard",
    "keeper", "innkeeper", "smith", "bargeman", "captain", "soldier", "priest",
    "lender", "courier", "rider", "hunter", "farmer", "beggar", "elder", "leader",
    "figure", "traveller", "traveler", "companion", "prisoner", "master", "mistress",
    # places and beasts
    "inn", "tavern", "shop", "smithy", "temple", "town", "village", "city", "camp",
    "gate", "bridge", "river", "road", "hill", "wood", "forest", "ruin", "keep",
    "horse", "dog", "hound", "cat", "bird", "beast", "ship", "boat", "cart", "wagon",
}


def name_request_intent(text: str) -> dict[str, Any]:
    """Classify a player line as demanding a name.

    Returns ``{"asked": bool, "kind": "written"|"person"|"self"|""}``.
    """
    line = str(text or "")
    if not line.strip():
        return {"asked": False, "kind": ""}
    for pattern, kind in _COMPILED:
        if pattern.search(line):
            return {"asked": True, "kind": kind}
    return {"asked": False, "kind": ""}


def proper_names_in(text: str) -> list[str]:
    """Proper-name candidates, minus sentence-initial ordinary words."""
    out: list[str] = []
    for match in _PROPER_RE.finditer(str(text or "")):
        candidate = match.group(1).strip()
        head = candidate.split()[0].lower()
        if head in _NOT_A_NAME:
            # "The Marrow" -> drop the article, keep the rest if anything is left
            rest = " ".join(candidate.split()[1:])
            if not rest:
                continue
            candidate = rest
            head = candidate.split()[0].lower()
            if head in _NOT_A_NAME:
                continue
        if all(part.lower() in _NOT_A_NAME for part in candidate.split()):
            continue
        out.append(candidate)
    return out


def subject_key(text: str, known_names: list[str] | None = None) -> str:
    """The thing a name is being asked *about*, normalised into a ledger key.

    Prefers an entity the world already knows (an inventory item, an NPC), so
    "the wax-sealed letter" and "the sealed letter" land on the same key.
    """
    line = str(text or "").lower()

    # 1. Something the world already knows about, mentioned by name.
    for name in sorted(known_names or [], key=len, reverse=True):
        low = str(name or "").strip().lower()
        if low and low in line:
            words = [w for w in re.findall(r"[a-z]+", low) if w not in _SUBJECT_STOP]
            for word in reversed(words):
                if word in _NAMEABLE_HEADS:
                    return word
            if words:
                return words[-1]

    # 2. A concrete head noun from the line itself, earliest first: "the sealed
    #    letter" is the subject of "read the name written on it", not "name".
    tokens = re.findall(r"[a-z][a-z\-]+", line)
    for word in tokens:
        if word in _NAMEABLE_HEADS:
            return word
    for word in tokens:
        if word.endswith("s") and word[:-1] in _NAMEABLE_HEADS:
            return word[:-1]

    # 3. Last resort: a noun-ish word introduced by "the" that is not a function
    #    word, a verb from the request itself, or a participle.
    for phrase in re.findall(r"\bthe\s+([a-z][a-z\-]+(?:\s+[a-z][a-z\-]+){0,2})", line):
        words = [w for w in phrase.split() if w not in _SUBJECT_STOP and len(w) > 3]
        if words:
            return words[-1]
    return ""


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def ledger_lookup(conn, subject: str) -> str:
    if not subject:
        return ""
    try:
        row = conn.execute(
            "SELECT name FROM name_ledger WHERE subject = ? COLLATE NOCASE LIMIT 1",
            (str(subject),),
        ).fetchone()
    except Exception:
        return ""
    return str(row[0]) if row and row[0] else ""


def ledger_record(conn, subject: str, name: str, *, source: str, turn: int = 0) -> None:
    """First writer wins. A name the world has already given out cannot change."""
    if not subject or not name:
        return
    try:
        conn.execute(
            "INSERT OR IGNORE INTO name_ledger (subject, name, source, turn) VALUES (?, ?, ?, ?)",
            (str(subject), str(name), str(source), int(turn or 0)),
        )
    except Exception:
        pass


def name_from_history(conn, subject: str, *, limit: int = 400) -> str:
    """A name the world already committed to for this subject.

    Scans the journal for rows that mention the subject and carry a proper
    name. Player rows outrank narration: what the player asserted is canon,
    what the narration echoed is derivative.
    """
    if not subject:
        return ""
    like = f"%{subject}%"
    try:
        rows = conn.execute(
            "SELECT kind, content FROM journal "
            "WHERE (kind = 'player' OR kind = 'narration' OR kind = 'fact') "
            "AND content LIKE ? COLLATE NOCASE ORDER BY id LIMIT ?",
            (like, int(limit)),
        ).fetchall()
    except Exception:
        return ""

    ranked: list[tuple[int, int, str]] = []
    for order, (kind, content) in enumerate(rows):
        text = str(content or "")
        weight = 0 if str(kind) == "player" else (1 if str(kind) == "fact" else 2)
        for candidate in proper_names_in(text):
            # Prefer names sitting near the subject word rather than anywhere in a
            # long paragraph.
            low = text.lower()
            pos_subject = low.find(subject.lower())
            pos_name = text.find(candidate)
            distance = abs(pos_name - pos_subject) if pos_subject >= 0 and pos_name >= 0 else 9999
            ranked.append((weight, distance if distance < 400 else 9999, candidate))
        _ = order
    if not ranked:
        return ""
    ranked.sort(key=lambda r: (r[0], r[1]))
    return ranked[0][2]


def mint_name(subject: str, *, seed_parts: tuple[Any, ...] = ()) -> str:
    """Invent a name deterministically so a rewind lands on the same person."""
    try:
        from app.world import invent_person_name, name_seed

        return invent_person_name(seed=name_seed("naming", subject, *seed_parts))
    except Exception:
        import hashlib

        digest = hashlib.blake2b(
            "|".join(["naming", str(subject), *[str(p) for p in seed_parts]]).encode("utf-8", "replace"),
            digest_size=4,
        ).hexdigest()
        return f"Stranger {digest[:4].upper()}"


def resolve_name_demand(
    conn,
    player_input: str,
    *,
    known_names: list[str] | None = None,
    turn: int = 0,
    player_name: str = "",
) -> dict[str, Any]:
    """Answer a naming demand: reuse what is established, else mint and record.

    Never returns an empty name when ``asked`` is true. That is the whole point.
    """
    intent = name_request_intent(player_input)
    result: dict[str, Any] = {
        "asked": bool(intent["asked"]),
        "kind": intent["kind"],
        "subject": "",
        "name": "",
        "source": "",
    }
    if not intent["asked"]:
        return result

    if intent["kind"] == "self" and str(player_name or "").strip():
        result.update(subject="self", name=str(player_name).strip(), source="player")
        return result

    subject = subject_key(player_input, known_names) or "unnamed"
    result["subject"] = subject

    existing = ledger_lookup(conn, subject)
    if existing:
        result.update(name=existing, source="ledger")
        return result

    found = name_from_history(conn, subject)
    if found:
        ledger_record(conn, subject, found, source="history", turn=turn)
        result.update(name=found, source="history")
        return result

    minted = mint_name(subject, seed_parts=(player_name,))
    ledger_record(conn, subject, minted, source="minted", turn=turn)
    result.update(name=minted, source="minted")
    return result


# ---------------------------------------------------------------------------
# Contract + repair
# ---------------------------------------------------------------------------


def naming_contract(resolved: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the model is told when the player has demanded a name."""
    if not resolved or not resolved.get("asked") or not resolved.get("name"):
        return None
    name = str(resolved["name"])
    source = str(resolved.get("source") or "")
    if source in {"ledger", "history", "player"}:
        rule = (
            f"The player asked for a name and this world already committed to one: {name}. "
            f"State {name} plainly in the narration. Do not hedge, do not describe the name "
            f"without giving it, and do not substitute a different name."
        )
    else:
        rule = (
            f"The player asked for a name and none was ever established. Use {name}. "
            f"State it plainly in the narration; it is now this world's answer and must not change."
        )
    return {
        "asked_for": resolved.get("kind") or "name",
        "subject": resolved.get("subject") or "",
        "name": name,
        "source": source or "resolved",
        "rule": rule,
    }


def enforce_named_answer(narration: str, resolved: dict[str, Any] | None) -> tuple[str, bool]:
    """Make sure the answer is actually in the prose.

    Returns ``(narration, repaired)``. Repair appends one plain sentence rather
    than rewriting the model's paragraph: the goal is that the player leaves the
    turn knowing the name, not that the prose is re-authored.
    """
    text = str(narration or "")
    if not resolved or not resolved.get("asked"):
        return text, False
    name = str(resolved.get("name") or "").strip()
    if not name:
        return text, False
    if re.search(rf"\b{re.escape(name)}\b", text, re.I):
        return text, False
    # Also accept the surname alone -- "Marrow" answers "Corvin Marrow".
    parts = [p for p in name.split() if len(p) > 2]
    if parts and re.search(rf"\b{re.escape(parts[-1])}\b", text, re.I):
        return text, False

    subject = str(resolved.get("subject") or "").strip()
    if resolved.get("kind") == "self":
        sentence = f"You give your name: {name}."
    elif subject and subject != "unnamed":
        sentence = f"The name is {name}."
    else:
        sentence = f"The name given is {name}."
    joined = text.rstrip()
    if joined and not joined.endswith((".", "!", "?", '"', "'", "”")):
        joined += "."
    return (f"{joined} {sentence}".strip() if joined else sentence), True
