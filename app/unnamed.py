"""Unnamed people and creatures: stored and numbered per kind (Stell, 2026-10-24).

CLAUDE.md, Design decisions, "Unnamed NPCs are stored and numbered per kind":
every unnamed NPC that appears (monster, raider, guard) gets a row named by its
kind and the next number for that kind (Ghoul 1, Ghoul 2, Raider 1); the code
stays the engine's own (A, B, ...); a creature is a person row.

Before this, an unnamed figure was a shell NPC with a drawn name, and only for
the person words world._figure_hints knows ("a wiry woman"); a creature never
became a row (the person-or-place ask answers "place" for one), so "a group of
4 ghouls" (offline game a1fedf99) and a Deathclaw (cc87dd29 T2) left nothing to
attack, search or remember.

How the engine reads a figure, structurally (no list of monster words):

* A mention is a noun phrase the prose opens with a determiner or a count and
  closes on a verb: "A ghoul lunges at you", "a group of 4 ghouls brutally
  attack you", "Two raiders step out", "Another ghoul drops", "the second
  ghoul", "The ghoul staggers back". The kind is the phrase's head noun (the
  word before the verb), made singular and title case ("ghouls" -> "Ghoul").
  Quoted speech is never read.
* Whether that noun is a figure at all is the engine's records first: a person
  word world._figure_hints already knows, a kind the save has numbered before,
  or a figure this turn's own NPC op introduces (NPC_NEW "Ghoul" over prose
  that only says "a ghoul" / "the ghoul": a common noun, not a name). For any
  other noun in a sentence that has the player in it, one small ask decides,
  once per noun per turn, before apply_turn's write block (settle):
      'In this text, is "ghoul" a person, an animal or a monster?'
* Counts are per kind across the save: Ghoul 3 is the third ghoul ever met
  (npcs.kind / npcs.kind_number, the faded ones included), not the third here.
  A stated count is that many ("4 ghouls", "two raiders"); an unstated plural
  ("some ghouls", "a pack of wolves") is two, the least a plural can be, and
  later prose that counts more ("the third ghoul") adds the rest.
* The rosters rule: the figures of that kind already here (alive) are matched
  first. "a ghoul" / "the ghoul" with one ghoul here is that ghoul; "two
  ghouls" with one here adds one; "another ghoul" and "the second ghoul" (with
  one here) add the next; "the raider" with two raiders here names neither and
  mints nothing. A person here whose job is the noun ("a guard" where Aldric
  the guard stands) is that person, so named people are never numbered.
* A new figure's attitude is its op's ATTITUDE, else one more small ask when
  the kind is minted this turn:
      'In this text, does "a group of 4 ghouls" attack or threaten the player?'
  yes -> hostile. Attack candidates (app/attack_intent.py) are the people here,
  so "i shoot the ghoul" is asked about Ghoul 1.
* Named later: "the raider, who says his name is Kade" renames the one numbered
  raider here, keeping its code and its number (world._ensure_npcs_from_narration's
  introduced-name step calls rename_told).

Rows minted here are above the turn's max id, so a rewind deletes them; a
rename or attitude change of an older row is added to the turn's rewind record
first. Every decision is a turn_ledger note; every ask goes through the
injectable entity_kinds ask, so its prompt, reply and seconds are in the turn
trace and model_usage.
"""
from __future__ import annotations

import re
from typing import Any

from app import turn_ledger

KIND_PHASE = "figure_kind"
KIND_QUESTION = 'In this text, is "{noun}" a person, an animal or a monster?'
HOSTILE_PHASE = "figure_hostile"
HOSTILE_QUESTION = 'In this text, does "{phrase}" attack or threaten the player?'
YES_NO_SYSTEM = "Answer yes or no."
MAX_TOKENS = 4
MAX_KIND_ASKS = 3
MAX_HOSTILE_ASKS = 2
# An unstated plural ("some ghouls", "a pack of wolves") is the least a plural can be.
UNSTATED_PLURAL = 2
# Never more than this many rows of one kind from one turn.
MAX_PER_KIND = 8

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8}
# English function words (grammar, not meaning): never a head noun, a modifier or a verb.
_CLOSED = frozenset({
    "of", "and", "or", "but", "nor", "with", "without", "in", "inside", "on", "at", "from", "to", "by", "for",
    "into", "onto", "over", "under", "near", "behind", "beside", "before", "after", "through", "across",
    "around", "toward", "towards", "against", "along", "past", "up", "down", "off", "out", "about",
    "the", "a", "an", "that", "this", "these", "those", "who", "whom", "whose", "which", "what", "as",
    "than", "like", "if", "then", "so", "not", "no", "his", "her", "hers", "its", "their", "theirs",
    "your", "yours", "my", "our", "you", "he", "she", "it", "they", "we", "i", "me", "him", "them", "us",
    "there", "here", "where", "when", "while", "all", "both", "each", "every", "few", "many", "much",
    "more", "most", "other", "another", "some", "any", "such", "own", "same", "one", "is", "are", "was",
    "were", "be", "been", "has", "have", "had", "do", "does", "did", "will", "would", "can", "could",
    "may", "might", "must", "shall", "should", "very", "too", "also", "just", "still", "even", "only",
    "named", "called",
})
_BE_HAVE = frozenset({"is", "was", "are", "were", "has", "have", "had"})
# Irregular English plurals (morphology, not meaning).
_IRREGULAR = {
    "men": "man", "women": "woman", "people": "person", "children": "child", "feet": "foot", "teeth": "tooth",
    "mice": "mouse", "geese": "goose", "oxen": "ox", "wolves": "wolf", "thieves": "thief", "elves": "elf",
    "dwarves": "dwarf", "halves": "half", "knives": "knife", "wives": "wife", "lives": "life",
    "zombies": "zombie", "rookies": "rookie", "junkies": "junkie", "pixies": "pixie", "newbies": "newbie",
}
_IRREGULAR_PLURALS = frozenset(_IRREGULAR) | {"sheep", "deer", "fish"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9][\w'’-]*|[,;:—–()]")
_CLAUSE_MARKS = frozenset({",", ";", ":", "—", "–", "(", ")"})
# A prepositional phrase between the noun and its verb: "A guard in a dented
# helmet steps", "A ghoul with rotting skin lunges" (grammar words).
_PP_OPENERS = frozenset({"with", "in", "from", "of", "near", "at", "on", "under", "behind", "by"})
_PP_MAX = 5
_YOU_RE = re.compile(r"\b(?:you|your|yours|yourself)\b", re.I)
_HOSTILE_WORDS = frozenset({"hostile", "aggressive", "violent", "antagonistic", "angry", "enemy", "furious"})


# ------------------------------------------------------------------ words


def _person_words() -> frozenset[str]:
    from app import world

    return frozenset(re.findall(r"[a-z]+", world._FIGURE_NOUNS)) - {"a"}


def _vague_words() -> frozenset[str]:
    """Person words that say nothing of a job: "a man" may be anyone here (the figure hints own them)."""
    from app import world

    return frozenset(world._VAGUE_FIGURES) | {
        "man", "woman", "girl", "boy", "lady", "fellow", "youth", "elder", "crone", "widow",
    }


def singular(word: str) -> str:
    """The singular of an English noun, lower case ("ghouls" -> "ghoul", "wolves" -> "wolf")."""
    w = str(word or "").strip().lower().strip("'’-")
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and re.search(r"(?:ch|sh|x|ss|zz)es$", w):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def is_plural(word: str) -> bool:
    w = str(word or "").lower()
    return w in _IRREGULAR_PLURALS or (len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")))


def kind_title(noun: str) -> str:
    """The kind as a row's name part: singular, title case, one word ("Deathclaw", "Ghoul")."""
    base = singular(noun)
    return base[:1].upper() + base[1:] if base else ""


def numbered(kind: str, number: int) -> str:
    return f"{kind} {int(number)}"


def next_number(conn, kind: str) -> int:
    """The next number for this kind across the save: the living, the dead and the faded."""
    key = str(kind or "").strip().lower()
    best = 0
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(kind_number), 0) FROM npcs WHERE LOWER(kind) = ?", (key,)
        ).fetchone()
        best = int((row[0] if row else 0) or 0)
    except Exception:
        best = 0
    try:
        import json

        for (record,) in conn.execute("SELECT record FROM faded_people").fetchall():
            try:
                data = json.loads(record or "{}")
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict) and str(data.get("kind") or "").strip().lower() == key:
                best = max(best, int(data.get("kind_number") or 0))
    except Exception:
        pass
    return best + 1


# --------------------------------------------------------------- mentions


def _plain(text: str) -> str:
    from app import venues

    flat = re.sub(r"\s*\[\[[^\]]*\]\]", "", venues.strip_speech(str(text or "")))
    return re.sub(r"\s+", " ", flat).strip()


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", _plain(text)) if s.strip()]


def _word(tok: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z'’-]*", tok or ""))


def _verb_shaped(tok: str, plural: bool) -> bool:
    """A finite or participle verb right after the noun: agreement and endings, no word list."""
    low = str(tok or "")
    if not _word(low) or low[:1].isupper():
        return False
    low = low.lower()
    if low in _BE_HAVE:
        return True
    if low in _CLOSED or low.endswith(("'s", "’s")):
        return False
    # A participle has a vowel in its stem: "eating", "lurking", "raised";
    # "ping", "thing", "red" and "shed" are not.
    for end in ("ing", "ed"):
        if low.endswith(end) and re.search(r"[aeiouy]", low[: -len(end)]):
            return True
    if low.endswith(("ing", "ed")):
        return False
    if plural:
        return not low.endswith("ly")
    return len(low) > 2 and low.endswith("s") and not low.endswith(("ss", "us", "is"))


def _count_of(tok: str) -> int:
    low = str(tok or "").lower()
    if low.isdigit():
        return int(low)
    return _NUMBER_WORDS.get(low, 0)


def mentions(text: str) -> list[dict[str, Any]]:
    """Every figure-shaped noun phrase the prose shows, in order.

    Each: {kind (lower singular), noun (as written), phrase, sentence, form,
    count, ordinal, you}. ``form`` is "count" (a/an/one: 1, a number, an
    unstated plural), "another", "ordinal" (the/a second ...), "the" (one
    referred back to) or "the_plural" (several referred back to). ``you``: the
    sentence has the player in it.
    """
    out: list[dict[str, Any]] = []
    for sentence in _sentences(text):
        toks = [m.group(0) for m in _TOKEN_RE.finditer(sentence)]
        i = 0
        while i < len(toks):
            found = _mention_at(toks, i)
            if found is None:
                i += 1
                continue
            end = found.pop("_end")
            # The clause the mention stands in (between punctuation marks):
            # "A ghoul lunges at you", "You see 4 ghouls eating someone".
            start = max([k for k in range(i) if toks[k] in _CLAUSE_MARKS] + [-1]) + 1
            stop = min([k for k in range(end, len(toks)) if toks[k] in _CLAUSE_MARKS] + [len(toks)])
            found["sentence"] = sentence
            found["you"] = bool(_YOU_RE.search(" ".join(toks[start:stop])))
            out.append(found)
            i = end
    return out


def _mention_at(toks: list[str], i: int) -> dict[str, Any] | None:
    low = toks[i].lower()
    if i > 0 and toks[i - 1].lower() in {"of"} and low in {"the"}:
        return None  # "one of the ghouls": the ghouls already met
    form, count, ordinal, plural_needed, j, stated = "", 0, 0, None, i + 1, True
    nxt = toks[i + 1].lower() if i + 1 < len(toks) else ""
    if low in {"a", "an"} and i + 2 < len(toks) and toks[i + 2].lower() == "of" and _word(toks[i + 1]):
        # "a group of 4 ghouls", "a pack of wolves", "a couple of raiders"
        j = i + 3
        n = _count_of(toks[j]) if j < len(toks) else 0
        if n:
            j += 1
        form, count, plural_needed, stated = "count", n or UNSTATED_PLURAL, True, bool(n)
    elif low in {"a", "an"} and nxt == "few":
        form, count, plural_needed, j, stated = "count", UNSTATED_PLURAL, True, i + 2, False
    elif low in {"a", "an", "the"} and nxt in _ORDINALS:
        form, ordinal, plural_needed, j = "ordinal", _ORDINALS[nxt], False, i + 2
    elif low == "another":
        form, count, plural_needed = "another", 1, False
    elif low in {"a", "an"}:
        form, count, plural_needed = "count", 1, False
    elif low in {"some", "several"}:
        form, count, plural_needed, stated = "count", UNSTATED_PLURAL, True, False
    elif _count_of(low):
        if nxt == "of":
            return None
        n = _count_of(low)
        form, count, plural_needed = "count", n, n > 1
    elif low == "the":
        n = _count_of(nxt)
        if n:
            form, count, plural_needed, j = "count", n, n > 1, i + 2
        else:
            form = "the"
    else:
        return None
    for k in range(3):
        at = j + k
        if at + 1 >= len(toks):
            return None
        noun = toks[at]
        if not _word(noun) or noun.lower() in _CLOSED or noun.lower().endswith(("'s", "’s")):
            return None
        # The modifiers before the noun must be words too ("a rotting ghoul").
        verb_at = at + 1
        if verb_at < len(toks) and re.fullmatch(r"[a-z]+ly", toks[verb_at], re.I) and verb_at + 1 < len(toks):
            verb_at += 1  # an adverb: "4 ghouls brutally attack you"
        plural = is_plural(noun)
        if plural_needed is True and not plural:
            continue
        if plural_needed is False and plural and form != "the":
            continue
        if not _verb_shaped(toks[verb_at], plural):
            verb_at = _verb_after_phrase(toks, at + 1, plural)
            if verb_at < 0:
                continue
        this_form = form
        if form == "the" and plural:
            this_form = "the_plural"
        return {
            "kind": singular(noun),
            "noun": noun,
            "phrase": " ".join(toks[i: at + 1]),
            "form": this_form,
            "count": count,
            "ordinal": ordinal,
            "stated": stated,
            "_end": verb_at + 1,
        }
    return None


def _verb_after_phrase(toks: list[str], at: int, plural: bool) -> int:
    """The verb after a short prepositional phrase that follows the noun, or -1."""
    if at >= len(toks) or toks[at].lower() not in _PP_OPENERS:
        return -1
    for k in range(at + 2, min(len(toks), at + 2 + _PP_MAX)):
        if toks[k] in _CLAUSE_MARKS:
            return -1
        prev = toks[k - 1]
        if _word(prev) and prev.lower() not in _CLOSED and _verb_shaped(toks[k], plural):
            return k
    return -1


# ------------------------------------------------------------------ the op


def op_kind(name: Any, narration: str) -> str:
    """The kind an op's "name" is when it is only a common noun the prose shows.

    NPC_NEW "Ghoul" over "A ghoul lunges at you ... the ghoul hisses": every
    time the prose uses the word it has a determiner or a count before it, or
    it is plural, so it is a kind of figure, not someone's name. A name the
    prose ever uses bare ("Stone [[B]] nods") is a name. One word only.
    """
    raw = re.sub(r"\s*\[\[[^\]]*\]\]", "", str(name or "")).strip()
    if not re.fullmatch(r"[A-Za-z][A-Za-z'’-]{2,}", raw):
        return ""
    base = singular(raw)
    plain = _plain(narration)
    hits = list(re.finditer(rf"(?<![\w'’-])({re.escape(base)}(?:s|es)?|{re.escape(raw)})(?![\w'’-])", plain, re.I))
    if not hits:
        return ""
    det = re.compile(
        r"(?:\b(?:a|an|the|another|some|several|any|each|every|that|this|whatever|which|no|"
        + "|".join(_NUMBER_WORDS) + "|" + "|".join(_ORDINALS) + r")|\d+)\s+(?:[A-Za-z][\w'’-]*\s+){0,2}$",
        re.I,
    )
    for hit in hits:
        if is_plural(hit.group(1)) and hit.group(1).lower() != base:
            continue
        if not det.search(plain[max(0, hit.start() - 60): hit.start()]):
            return ""
    return kind_title(base)


def take_op_figures(npcs: list[Any], result: dict[str, Any] | None) -> list[Any]:
    """Op people settle marked as kinds are not filed by name: their kind and attitude go to file_figures."""
    if not isinstance(result, dict):
        return npcs
    kept: list[Any] = []
    ops = result.setdefault("_unnamed_ops", {}) if any(
        isinstance(n, dict) and n.get("_unnamed_kind") for n in npcs or []
    ) else result.get("_unnamed_ops") or {}
    for npc in npcs or []:
        kind = str(npc.get("_unnamed_kind") or "") if isinstance(npc, dict) else ""
        if not kind or str(npc.get("code") or "").strip():
            kept.append(npc)
            continue
        entry = ops.setdefault(kind.lower(), {"kind": kind, "count": 0, "attitude": "", "role": ""})
        entry["count"] = int(entry.get("count") or 0) + 1
        attitude = str(npc.get("attitude") or "").strip().lower()
        if attitude and attitude != "neutral":
            entry["attitude"] = attitude
        role = str(npc.get("role") or "").strip()
        if role and role.lower() not in {"local", "passerby"}:
            entry["role"] = role
        turn_ledger.note("npc", "op_figure_is_a_kind", name=str(npc.get("name") or ""), kind=kind)
    return kept


# ------------------------------------------------- the asks (before apply_turn)


def kind_prompt(sentence: str, noun: str) -> str:
    """The user half of the figure-kind ask, exactly as sent."""
    return f"Text: {sentence}\n{KIND_QUESTION.format(noun=noun)}"


def hostile_prompt(sentence: str, phrase: str) -> str:
    """The user half of the hostility ask, exactly as sent."""
    return f"Text: {sentence}\n{HOSTILE_QUESTION.format(phrase=phrase)}"


def _stored_kinds(conn) -> set[str]:
    try:
        return {str(r[0] or "").strip().lower() for r in conn.execute("SELECT DISTINCT kind FROM npcs").fetchall()} - {""}
    except Exception:
        return set()


def settle(result: dict[str, Any], narration: str, conn, *, ask: bool, call, trace=None, usage=None) -> dict[str, Any]:
    """Decide, before apply_turn's write block, which nouns are figures and whether new ones are hostile.

    Verdicts go on ``result["_figures"]``: {kind: {"figure": bool, "hostile":
    bool | None, "by": "record" | "op" | "ask"}}. ``call(system, user, phase,
    max_tokens, trace, usage)`` is entity_kinds' ask. ``ask=False`` (the
    offline narrator) asks nothing: only the records and the ops decide.
    """
    found = mentions(narration)
    if not found:
        return {}
    people = _person_words()
    stored = _stored_kinds(conn)
    op_npcs = [n for n in result.get("npcs") or [] if isinstance(n, dict) and n.get("_unnamed_kind")]
    ops = {str(n["_unnamed_kind"]).lower() for n in op_npcs}
    op_attitudes = {
        str(n["_unnamed_kind"]).lower() for n in op_npcs
        if str(n.get("attitude") or "").strip().lower() not in {"", "neutral"}
    }
    verdicts: dict[str, dict[str, Any]] = {}
    kind_asks = hostile_asks = 0
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for m in found:
        by_kind.setdefault(m["kind"], []).append(m)
    for kind, ms in by_kind.items():
        if kind in people or kind in stored:
            verdicts[kind] = {"figure": True, "hostile": None, "by": "record"}
        elif kind in ops:
            verdicts[kind] = {"figure": True, "hostile": None, "by": "op"}
        else:
            # Only a noun in a sentence with the player in it is asked about.
            shown = next((m for m in ms if m["you"] and m["form"] in {"count", "another", "ordinal"}), None)
            if shown is None or not ask:
                continue
            if kind_asks >= MAX_KIND_ASKS:
                turn_ledger.note("npc", "figure_kind_not_asked", kind=kind, reason="ask limit")
                continue
            kind_asks += 1
            try:
                reply = call(YES_NO_SYSTEM, kind_prompt(shown["sentence"], kind), KIND_PHASE, MAX_TOKENS, trace, usage)
            except Exception as exc:
                turn_ledger.note("npc", "figure_kind_ask_failed", kind=kind, error=f"{type(exc).__name__}: {exc}"[:160])
                continue
            from app.entity_kinds import read_yes_no

            said = read_yes_no(reply)
            if said is None:
                turn_ledger.note("npc", "figure_kind_unread", kind=kind, reply=str(reply or "")[:80])
                continue
            turn_ledger.note("npc", "noun_is_a_figure" if said else "noun_is_no_figure", kind=kind, by="ask")
            verdicts[kind] = {"figure": bool(said), "hostile": None, "by": "ask"}
            if not said:
                continue
        # Hostility, for a kind this turn may mint (a count, another, an
        # ordinal). The person words the figure hints know keep their old
        # default (neutral, or the op's ATTITUDE): only other kinds are asked.
        minting = next((m for m in ms if m["form"] in {"count", "another", "ordinal"}), None)
        if not ask or minting is None or kind in op_attitudes or kind in people:
            continue
        if hostile_asks >= MAX_HOSTILE_ASKS:
            continue
        hostile_asks += 1
        try:
            reply = call(YES_NO_SYSTEM, hostile_prompt(minting["sentence"], minting["phrase"]), HOSTILE_PHASE,
                         MAX_TOKENS, trace, usage)
        except Exception as exc:
            turn_ledger.note("npc", "figure_hostile_ask_failed", kind=kind, error=f"{type(exc).__name__}: {exc}"[:160])
            continue
        from app.entity_kinds import read_yes_no

        said = read_yes_no(reply)
        verdicts[kind]["hostile"] = said
        turn_ledger.note("npc", "figure_hostile" if said else "figure_not_hostile" if said is False else "figure_hostile_unread",
                         kind=kind, reply=str(reply or "")[:40])
    if verdicts:
        result["_figures"] = {**(result.get("_figures") or {}), **verdicts}
    return verdicts


# ------------------------------------------------------- filing (apply_turn)


def _here(conn, location_id: int, kind: str) -> list[Any]:
    """The living people at this place who are this kind: a numbered row of it, or someone whose job it is."""
    try:
        rows = conn.execute(
            "SELECT * FROM npcs WHERE location_id = ? AND COALESCE(died_turn, 0) = 0 ORDER BY kind_number, id",
            (int(location_id),),
        ).fetchall()
    except Exception:
        return []
    out = []
    for row in rows:
        if str(row["kind"] or "").strip().lower() == kind:
            out.append(row)
        elif kind not in _vague_words() and any(
            singular(w) == kind for w in re.findall(r"[a-z]+", str(row["role"] or "").lower())
        ):
            out.append(row)
    return out


def _latest_turn(conn) -> int:
    try:
        row = conn.execute("SELECT turn FROM turn_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def _keep(conn, row_id: int) -> None:
    from app.interpreter import keep_for_rewind

    turn = _latest_turn(conn)
    if turn:
        keep_for_rewind(conn, turn, "npcs", int(row_id))


def _mark_present(result: dict[str, Any], code: str) -> None:
    cast = result.get("scene_cast")
    if not isinstance(cast, dict):
        cast = {}
        result["scene_cast"] = cast
    present = cast.setdefault("present", [])
    if isinstance(present, list) and code and code.upper() not in [str(c).upper() for c in present]:
        present.append(code.upper())


def mint(conn, location_id: int, kind: str, *, attitude: str = "", role: str = "",
         person: bool = True) -> dict[str, Any] | None:
    """One new numbered row of this kind at this place: "<Kind> <next number>", the engine's next code."""
    from app import world

    title = kind_title(kind)
    if not title:
        return None
    shell = world.create_shell_npc(
        conn, int(location_id), presence="event_worthy", power_rank=8, role=role or kind.lower(),
        summary="", kind=title,
        sex={"female": "female", "male": "male"}.get(world._hint_sex(kind, ""), ""),
    )
    if not shell:
        return None
    updates: dict[str, Any] = {}
    if attitude:
        updates["attitude"] = attitude[:80]
    if not person:
        updates["race"] = "unknown"
    if updates:
        conn.execute(f"UPDATE npcs SET {', '.join(k + ' = ?' for k in updates)} WHERE id = ?",
                     (*updates.values(), int(shell["id"])))
        shell.update(updates)
    return shell


def _fresh_unnamed(conn, location_id: int, max_id_before: int | None, narration: str,
                   result: dict[str, Any]) -> list[Any]:
    """People the cast seeding made here this turn under a drawn name the prose never uses.

    A line nobody known speaks seeds a face with a drawn name and no kind
    (world._ensure_npcs_from_narration): cc87dd29 T3's "a nurse in a blue
    helmet ... she asks" was stored as a drawn "Beth". That face is the figure
    the prose shows, so it is numbered as that figure, not minted beside it.
    """
    if max_id_before is None:
        return []
    try:
        rows = conn.execute(
            "SELECT * FROM npcs WHERE id > ? AND location_id = ? AND COALESCE(kind, '') = '' "
            "AND COALESCE(died_turn, 0) = 0 ORDER BY id",
            (int(max_id_before), int(location_id)),
        ).fetchall()
    except Exception:
        return []
    plain = _plain(narration)
    # Only the faces this turn's cast seeding made from the prose (never a
    # keeper or a ruler the engine made for its own reasons).
    seeded = {
        str(n.get("code") or "").upper() for n in result.get("npcs") or []
        if isinstance(n, dict) and n.get("_seeded_from_narration") and not n.get("kind")
    }
    out = []
    for row in rows:
        if str(row["code"] or "").upper() not in seeded:
            continue
        name = str(row["name"] or "").strip()
        forms = [name] + ([name.split()[0]] if len(name.split()) > 1 and len(name.split()[0]) >= 3 else [])
        if name and not any(re.search(r"(?<![\w'’])" + re.escape(f) + r"(?![\w'’])", plain) for f in forms):
            out.append(row)
    return out


def _number_fresh(conn, row: Any, kind: str, attitude: str, result: dict[str, Any]) -> dict[str, Any]:
    title = kind_title(kind)
    number = next_number(conn, title)
    name = numbered(title, number)
    updates: dict[str, Any] = {"name": name, "kind": title, "kind_number": number}
    if attitude:
        updates["attitude"] = attitude[:80]
    conn.execute(f"UPDATE npcs SET {', '.join(k + ' = ?' for k in updates)} WHERE id = ?",
                 (*updates.values(), int(row["id"])))
    code = str(row["code"] or "")
    for npc in result.get("npcs") or []:
        if isinstance(npc, dict) and str(npc.get("code") or "") == code:
            npc.update({k: v for k, v in updates.items() if k in {"name", "attitude"}})
            npc["kind"], npc["kind_number"] = title, number
    turn_ledger.note("npc", "seeded_face_numbered", was=str(row["name"] or ""), name=name, code=code)
    out = {key: row[key] for key in row.keys()}
    out.update(updates)
    return out


def file_figures(conn, result: dict[str, Any], narration: str, location_id: int | None,
                 max_id_before: int | None = None) -> list[dict[str, Any]]:
    """Resolve each figure the prose shows to the rows here, and mint the rest numbered per kind.

    Called by apply_turn after the cast seeding; ``max_id_before`` is the
    highest npcs id before the turn. Returns the new rows.
    """
    if not location_id or not isinstance(result, dict):
        return []
    found = mentions(narration)
    ops = result.get("_unnamed_ops") or {}
    if not found and not ops:
        return []
    people = _person_words()
    vague = _vague_words()
    stored = _stored_kinds(conn)
    verdicts = result.get("_figures") or {}
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for m in found:
        by_kind.setdefault(m["kind"], []).append(m)
    for kind in ops:
        by_kind.setdefault(str(kind).lower(), [])
    created: list[dict[str, Any]] = []
    for kind, ms in by_kind.items():
        op = ops.get(kind) or {}
        verdict = verdicts.get(kind) or {}
        if not (kind in people or kind in stored or op or verdict.get("figure")):
            continue
        # One person seen as "a man" may be anyone here: the figure hints own
        # those. Several are numbered only when the prose counts them and they
        # meet the player ("Two men step out and level rifles at you"), not a
        # crowd ("A few people move between the shops", baseline T0).
        if kind in vague:
            ms = [m for m in ms if m["form"] not in {"count", "ordinal"} or (
                is_plural(m["noun"]) and m.get("stated") and m["you"])]
        here = _here(conn, int(location_id), kind)
        total = len(here)
        ambiguous = False
        for m in ms:
            if m["form"] == "count":
                total = max(total, int(m["count"] or 0))
            elif m["form"] == "another":
                total += 1
            elif m["form"] == "ordinal":
                total = max(total, int(m["ordinal"] or 0))
            elif m["form"] == "the":
                if total > 1:
                    ambiguous = True
        if op and total == 0:
            total = max(1, min(MAX_PER_KIND, int(op.get("count") or 1)))
        new = max(0, min(MAX_PER_KIND, total - len(here)))
        if ambiguous and not new:
            turn_ledger.note("npc", "figure_ambiguous", kind=kind, here=[str(r["name"] or "") for r in here])
        # The ones the prose shows of this kind are in the scene (attack candidates next turn).
        for row in (here if ms else []):
            _mark_present(result, str(row["code"] or ""))
        if not new:
            if here and ms:
                turn_ledger.note("npc", "figure_is_one_here", kind=kind, names=[str(r["name"] or "") for r in here])
            continue
        attitude = str(op.get("attitude") or "")
        if not attitude and verdict.get("hostile"):
            attitude = "hostile"
        fresh = _fresh_unnamed(conn, int(location_id), max_id_before, narration, result) if kind not in vague else []
        for _ in range(new):
            if fresh:
                numbered_row = _number_fresh(conn, fresh.pop(0), kind, attitude, result)
                _mark_present(result, str(numbered_row.get("code") or ""))
                continue
            shell = mint(conn, int(location_id), kind, attitude=attitude, role=str(op.get("role") or ""),
                         person=kind in people)
            if not shell:
                continue
            _mark_present(result, str(shell.get("code") or ""))
            entry = {
                "code": shell.get("code"), "name": shell.get("name"), "role": shell.get("role") or kind,
                "summary": "", "attitude": shell.get("attitude") or attitude or "neutral", "location": "",
                "presence": "event_worthy", "shell": False, "power_rank": shell.get("power_rank") or 8,
                "_seeded_from_narration": True, "kind": shell.get("kind"), "kind_number": shell.get("kind_number"),
            }
            created.append(entry)
            turn_ledger.note("npc", "unnamed_figure_numbered", name=str(shell.get("name") or ""),
                             code=str(shell.get("code") or ""), attitude=entry["attitude"],
                             by=("op" if op else str(verdict.get("by") or "record")))
    if created:
        result["npcs"] = [n for n in (result.get("npcs") or []) if isinstance(n, dict)] + created
    return created


# ------------------------------------------------------------ named later


def rename_told(conn, text: str, name: str, location_id: int | None) -> dict[str, Any] | None:
    """A name the prose tells for a numbered figure here renames that row, keeping its code and number.

    "The raider, who says his name is Kade, lowers his rifle": the one Raider
    here is Kade now. The figure is the one the telling sentence (or the one
    before it) refers back to as "the <kind>"; with two of that kind here it
    names neither and nothing is renamed.
    """
    if not location_id or not str(name or "").strip():
        return None
    sentences = _sentences(text)
    told = re.compile(r"\b(?:name\s+(?:is|was)|named|called|introduces\s+(?:him|her|them)self\s+as)\s+" + re.escape(name) + r"\b")
    for index, sentence in enumerate(sentences):
        if not told.search(sentence):
            continue
        for near in (sentence, sentences[index - 1] if index > 0 else ""):
            for m in re.finditer(r"\b[Tt]he\s+(?:[a-z][\w'’-]*\s+){0,2}?([A-Za-z][\w'’-]*)\b", near):
                kind = singular(m.group(1))
                rows = [r for r in _here(conn, int(location_id), kind) if int(r["kind_number"] or 0) > 0]
                if len(rows) != 1:
                    continue
                row = rows[0]
                if str(row["name"] or "") != numbered(str(row["kind"] or ""), int(row["kind_number"] or 0)):
                    continue  # already named
                _keep(conn, int(row["id"]))
                conn.execute("UPDATE npcs SET name = ? WHERE id = ?", (name.strip(), int(row["id"])))
                try:
                    conn.execute("INSERT OR IGNORE INTO aliases (alias, entity_type, entity_code) VALUES (?, 'npc', ?)",
                                 (str(row["name"] or ""), str(row["code"] or "")))
                except Exception:
                    pass
                turn_ledger.note("npc", "numbered_figure_named", was=str(row["name"] or ""), name=name.strip(),
                                 code=str(row["code"] or ""))
                return {"code": str(row["code"] or ""), "name": name.strip(), "role": str(row["role"] or ""),
                        "attitude": str(row["attitude"] or "neutral"), "was": str(row["name"] or "")}
        return None
    return None


def ask_label(person: dict[str, Any], people: list[dict[str, Any]]) -> str:
    """What the attack ask calls a numbered figure: "the ghoul" when it is the only one of its kind here."""
    kind = str(person.get("kind") or "").strip()
    name = str(person.get("name") or "").strip()
    if not kind or not int(person.get("kind_number") or 0) or name != numbered(kind, int(person.get("kind_number") or 0)):
        return name
    same = [p for p in people if str(p.get("kind") or "").strip().lower() == kind.lower()]
    return f"the {kind.lower()}" if len(same) == 1 else name
