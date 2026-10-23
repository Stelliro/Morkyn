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
  shows present by its grammar: the subject of a verb in its clause ("A ghoul
  lunges at you", "a group of 4 ghouls brutally attack you", "Two raiders
  step out", "Another ghoul drops", "The ghoul staggers back"); followed by an
  -ing or a relative clause that has it act ("a pack of ghouls feasting",
  "a ghoul that lunges"); the direct object of a verb the player is the
  subject of in that clause ("you see a pack of ghouls", "you spot two
  raiders behind the wreck", "you look up to face a deathclaw"); or of the
  kind the player's own line acts on (player_objects). The kind is the
  phrase's head noun, made singular and title case ("ghouls" -> "Ghoul").
  Quoted speech is never read. Anything else ("the sensors flash a warning",
  "stand over the two halves", "you shoot at a ghoul") is not shown present.
* Whether that noun is a figure at all is the engine's records first: a person
  word world._figure_hints already knows, a kind the save has numbered before,
  or a figure this turn's own NPC op introduces (NPC_NEW "Ghoul" over prose
  that only says "a ghoul" / "the ghoul": a common noun, not a name). For any
  other noun in a sentence that has the player in it, one small ask decides,
  once per noun per turn, before apply_turn's write block (settle):
      'In this text, is "ghoul" a being that can act on its own?'
  and a second, differently worded check must agree:
      'In this text, could you fight or talk to the ghoul? Answer yes or no.'
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
# Measured live on Hermes 3 8B (live-eval-5, 75 attempts each): "a person, an
# animal or a monster?" is a choice question, and 42 of 75 replies spent the
# 4 tokens on "In this text," before answering; this one is yes/no: 75/75
# right, 0 unparseable.
KIND_QUESTION = 'In this text, is "{noun}" a being that can act on its own?'
# The second, differently worded check that must agree before a noun is filed
# as a figure (CLAUDE.md 2026-10-18: one small ask finds, a second checks).
# Over the 44 recorded narrations the first ask was put to scenery ten times
# in eleven (ping, counter, tear ...); one false yes minted "Ping 1".
# Measured (live-eval-5, 87 attempts): "could the player fight or talk to the
# ghoul?" said no to 41 of 51 true figures; "could you ...? Answer yes or no."
# 93% right, 0 false yes in 36.
KIND_CHECK_PHASE = "figure_kind_check"
# Measured live on Hermes 3 8B (live-eval-7): "could you fight or talk to" said no to figures that are
# present but not engaging ("you see a pack of ghouls feasting", an NPC watching, a sleeping deathclaw);
# "a creature or a person?": 0 false no on true figures, and the pair still filed 0 of 90 items and scenery.
KIND_CHECK_QUESTION = "In this text, is the {noun} a creature or a person? Answer yes or no."
HOSTILE_PHASE = "figure_hostile"
HOSTILE_QUESTION = 'In this text, does "{phrase}" attack or threaten the player?'
# Asked only when a pronoun ('"..." she asks') would give a quoted line to a
# figure that is no person word the figure hints know (the nurse in cc87dd29
# T3; not the ghoul in 'A ghoul lunges at you. "Get down!" she shouts').
# Not yet measured live on Hermes 3 8B.
SPEAKS_PHASE = "figure_speaks"
# Measured live on Hermes 3 8B (live-eval-6): "does the ghoul say ..." said yes 3/3 to the very case
# it is for (a bystander shouting while a ghoul lunges); "are the words ... spoken by": 89.5%, false yes 12 -> 6, false no 3 -> 0.
SPEAKS_QUESTION = 'In this text, are the words "{quote}" spoken by the {noun}? Answer yes or no.'
SPEAKS_QUOTE_CHARS = 120
MAX_SPEAK_ASKS = 1
YES_NO_SYSTEM = "Answer yes or no."
MAX_TOKENS = 4
# The figure_kind and figure_kind_check asks together, per turn: a noun is
# started only when both of its asks still fit, so at most three nouns are
# fully checked (a first "no" costs one ask and leaves room for the next).
# Measured on Hermes 3 8B at ~0.07 s an ask (live-eval-5): about 0.4 s a turn
# at the cap. The hostility (MAX_HOSTILE_ASKS) and speech (MAX_SPEAK_ASKS)
# asks have their own caps.
MAX_FIGURE_ASKS = 6
MAX_HOSTILE_ASKS = 2
# A group the prose does not count ("a pack of ghouls", "some raiders", "a
# few drifters", "a crowd of refugees") is the least a plural can be: two.
# Later prose that counts more ("another ghoul", "the third ghoul", "two more
# ghouls") adds the rest; "some ghouls" again with two here adds none. A
# collective noun alone ("A crowd gathers", "a pack circles") is asked about
# as itself and files nothing unless both asks say it is a being.
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
    "named", "called", "between", "among", "amid", "beyond", "above", "below", "beneath", "underneath",
    "upon", "within", "outside", "until", "because", "though", "although", "since", "once",
})
_BE_HAVE = frozenset({"is", "was", "are", "were", "has", "have", "had"})
# The mention forms that can file a new figure (a "the" refers back to one met).
_MINTING_FORMS = frozenset({"count", "another", "more", "ordinal"})
# Irregular English plurals (morphology, not meaning).
_IRREGULAR = {
    "men": "man", "women": "woman", "people": "person", "children": "child", "feet": "foot", "teeth": "tooth",
    "mice": "mouse", "geese": "goose", "oxen": "ox", "wolves": "wolf", "thieves": "thief", "elves": "elf",
    "dwarves": "dwarf", "halves": "half", "knives": "knife", "wives": "wife", "lives": "life",
    "zombies": "zombie", "rookies": "rookie", "junkies": "junkie", "pixies": "pixie", "newbies": "newbie",
}
_IRREGULAR_PLURALS = frozenset(_IRREGULAR) | {"sheep", "deer", "fish"}
# A spaced hyphen is a dash ("flash a warning - supplies are running low").
_TOKEN_RE = re.compile(r"[A-Za-z0-9][\w'’-]*|[,;:—–()]|(?<=\s)-(?=\s)")
_CLAUSE_MARKS = frozenset({",", ";", ":", "—", "–", "(", ")", "-"})
# Grammar for where a clause's subject may stand: what can come before it in
# its own clause. Conjunctions and sentence adverbs ("when a sudden ping
# pulls", "Then two raiders step out") and a leading prepositional phrase
# ("From behind the counter a ghoul lunges"); anything else before the noun
# ("you see", "the sensors flash", "as you stand over") makes it an object.
_CLAUSE_OPENERS = frozenset({
    "and", "but", "or", "nor", "then", "as", "when", "while", "until", "before", "after", "because", "so",
    "once", "now", "yet", "where", "that", "who", "which", "if", "though", "although", "since", "just",
    "still", "there", "here", "even", "again",
})
_PREPOSITIONS = frozenset({
    "with", "in", "inside", "from", "of", "near", "at", "on", "under", "behind", "by", "out", "into", "onto",
    "across", "through", "beyond", "above", "below", "among", "between", "outside", "over", "around",
    "toward", "towards", "beside", "past", "along", "upon", "within", "beneath", "amid", "off", "down", "up",
})
_SUBJECT_PRONOUNS = frozenset({"i", "you", "he", "she", "they", "we", "it"})
_OBJECT_PRONOUNS = frozenset({"you", "him", "her", "them", "it", "me", "us"})
# A prepositional phrase between the noun and its verb: "A guard in a dented
# helmet steps", "A ghoul with rotting skin lunges" (grammar words).
_PP_OPENERS = frozenset({"with", "in", "from", "of", "near", "at", "on", "under", "behind", "by"})
_PP_MAX = 5
_YOU_RE = re.compile(r"\b(?:you|your|yours|yourself)\b", re.I)


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
    """The next number for this kind in this game: the living, the dead and the faded.

    Both tables hold only the current playthrough's people
    (world._clear_playthrough empties npcs and faded_people for a new game),
    so a new game in the same data folder starts again at Ghoul 1.
    """
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


def mentions(text: str, objects: Any = ()) -> list[dict[str, Any]]:
    """Every figure the prose shows doing something, in order.

    A figure does something when its noun phrase is the subject of a verb in
    its own clause: the phrase opens the clause ("A ghoul lunges at you",
    "At the front desk, a nurse ... looks up", "when a sudden ping ... pulls
    you") and a verb follows it, or an -ing verb follows it right away ("You
    see 4 ghouls eating someone"). A phrase after the clause's own verb is an
    object ("you see a few scattered buildings", "flash a warning") and the
    head of a prepositional phrase is not a subject ("stand over the two
    halves"); neither is a figure shown acting. ``objects`` are the kinds the
    player's own line acts on (player_objects: "i shoot the ghoul"): a phrase
    of that kind counts wherever it stands ("Your shot takes a ghoul in the
    shoulder").

    Each: {kind (lower singular), noun (as written), phrase, sentence, form,
    count, ordinal, you, acts, subject, seen}. ``seen``: the phrase is the
    direct object of a verb whose subject is the player in that clause ("you
    see a pack of ghouls", "you spot two raiders behind the wreck"), taken with
    or without a verb of its own; an -ing or a relative clause after the noun
    ("ghouls feasting", "a ghoul that lunges") makes it a subject wherever it
    stands. ``form`` is "count" (a/an/one: 1, a
    number, an unstated plural), "another", "more" ("two more ghouls": that
    many added), "ordinal" (the/a second ...),
    "the" (one referred back to) or "the_plural" (several referred back to).
    ``you``: the clause has the player in it. ``acts``: the verb is an action,
    not "is"/"has" alone ("An ironbound door is your only way in" shows a door,
    not a door doing something; "a raider is aiming" acts). ``subject``: False
    for a phrase taken only because the player's line acts on its kind.
    """
    kinds = {singular(k) for k in objects or () if str(k or "").strip()}
    out: list[dict[str, Any]] = []
    for sentence in _sentences(text):
        toks = [m.group(0) for m in _TOKEN_RE.finditer(sentence)]
        i = 0
        while i < len(toks):
            # The clause the mention stands in (between punctuation marks).
            start = max([k for k in range(i) if toks[k] in _CLAUSE_MARKS] + [-1]) + 1
            seen = _players_object(toks[start:i])
            found = _mention_at(toks, i, kinds, bare=seen)
            if found is None:
                i += 1
                continue
            bare = found.pop("_bare", False)
            subject = (found.pop("_object") is False and not bare
                       and (found["_ing"] or _opens_clause(toks[start:i])))
            if not subject and not seen and found["kind"] not in kinds:
                i += 1
                continue
            end = found.pop("_end")
            head = found.pop("_head")
            if not subject:
                # Taken as an object: its "verb" may be another phrase's ("you catch a
                # glimpse of an NPC watching you"), so the next phrase is read too.
                end = head + 1
            found.pop("_ing", None)
            stop = min([k for k in range(end, len(toks)) if toks[k] in _CLAUSE_MARKS] + [len(toks)])
            found["sentence"] = sentence
            found["subject"] = bool(subject)
            found["seen"] = bool(seen and not subject)
            # The player's own act on it, or the player seeing it, has the player in it.
            found["you"] = (not subject) or bool(_YOU_RE.search(" ".join(toks[start:stop])))
            if not subject:
                found["acts"] = True
            out.append(found)
            i = end
    return out


def _opens_clause(before: list[str]) -> bool:
    """Whether a noun phrase after these tokens of its clause is the clause's subject.

    Only conjunctions, sentence adverbs and a leading prepositional phrase may
    come before a subject; a subject pronoun ("you see", "as you stand") or a
    noun with its verb ("the sensors flash") make the phrase an object.
    """
    in_pp = False
    for tok in before:
        low = tok.lower()
        if low in _PREPOSITIONS:
            in_pp = True
            continue
        if in_pp:
            # Inside "from behind the counter", "behind you": its own object.
            if low in _SUBJECT_PRONOUNS - _OBJECT_PRONOUNS:
                return False
            continue
        if low in _CLAUSE_OPENERS or re.fullmatch(r"[a-z]+ly", low):
            continue
        return False
    return True


def _players_object(before: list[str]) -> bool:
    """Whether a noun phrase after these tokens of its clause is the object of the player's own verb.

    The word right before the phrase (past any -ly adverb) is a verb, and the
    player is a subject earlier in the clause: "you see", "Through the gap,
    you see", "you look up to face", "you can see" (grammar: a "you" that is
    no preposition's object, then an open-class word). "hands you a knife"
    (you right before it), "behind you stands" and "you shoot at a ghoul" (a
    preposition before it) are not; nor is a verb with a particle ("you make
    out some raiders"), which reads as a preposition.
    """
    k = len(before) - 1
    while k >= 0 and re.fullmatch(r"[a-z]+ly", before[k]):
        k -= 1
    if k < 1:
        return False
    verb = before[k]
    if (not _word(verb) or verb[:1].isupper() or verb.lower() in _CLOSED or verb.lower() in _PREPOSITIONS
            or verb.lower().endswith(("'s", "’s"))):
        return False
    for at in range(k - 1, -1, -1):
        if before[at].lower() != "you":
            continue
        prev = before[at - 1].lower() if at > 0 else ""
        if prev in _PREPOSITIONS or prev in {"for", "to", "like", "than"}:
            continue  # "behind you", "gestures for you to take a seat": you are no subject there
        nxt = before[at + 1]
        # "you" then its verb (or a helper: "you can see", "you now spot"), never "you" then a noun phrase.
        return nxt.lower() not in {"a", "an", "the", "some", "another"} and not _count_of(nxt)
    return False


def _np_ends(toks: list[str], at: int) -> bool:
    """The noun phrase stops at this word: the clause, a function word or the sentence comes next."""
    nxt = toks[at + 1] if at + 1 < len(toks) else ""
    return not nxt or nxt in _CLAUSE_MARKS or not _word(nxt) or nxt.lower() in _CLOSED or nxt.lower() in _PREPOSITIONS


def _acts(toks: list[str], verb_at: int) -> bool:
    """The verb is an action: not "is"/"was"/"has" on its own, but "is lunging" and "has drawn" are."""
    low = toks[verb_at].lower() if 0 <= verb_at < len(toks) else ""
    if low not in _BE_HAVE:
        return True
    nxt = toks[verb_at + 1].lower() if verb_at + 1 < len(toks) else ""
    if low in {"has", "have", "had"}:
        return bool(re.fullmatch(r"[a-z]+(?:ed|en|wn|ung|ught)", nxt))
    return nxt.endswith("ing") and len(nxt) > 4


def player_objects(line: str) -> set[str]:
    """The kinds the player's own line acts on: "i shoot the ghoul" -> {"ghoul"}.

    The noun phrase right after the player's verb ("i <verb> the <noun>", or
    an order "shoot the ghouls"), in each clause of the line; a possessive
    ("my gun") is the player's own and a preposition after the verb ("go into
    the clinic") means no object. Quoted speech is not an act.
    """
    from app import venues

    flat = re.sub(r"[@#!&]\w+|\[\[[^\]]*\]\]", " ", venues.strip_speech(str(line or "")))
    out: set[str] = set()
    for clause in re.split(r"[,;:.!?]|\b(?:and|then)\b", flat, flags=re.I):
        toks = [m.group(0) for m in _TOKEN_RE.finditer(clause)]
        while toks and (toks[0].lower() in {"i", "try", "to", "then"} or re.fullmatch(r"[a-z]+ly", toks[0].lower())):
            toks = toks[1:]
        if len(toks) < 3:
            continue
        det = toks[1].lower()
        if not (det in {"the", "a", "an", "another", "that", "this", "these", "those"} or _count_of(det)):
            continue
        head = ""
        for tok in toks[2:5]:
            low = tok.lower()
            if not _word(tok) or low in _CLOSED or low in _PREPOSITIONS:
                break
            head = low
        if head and not _count_of(head):
            out.add(singular(head))
    return out


def _mention_at(toks: list[str], i: int, objects: frozenset[str] | set[str] = frozenset(),
                bare: bool = False) -> dict[str, Any] | None:
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
        found = _head_at(toks, i, j, form, count, 0, True, bool(n), objects, bare)
        if found is not None:
            return found
        # Not a group of figures ("A flicker of understanding passes"): the
        # phrase is "a flicker" with "of understanding" after it.
        form, count, plural_needed, j, stated = "count", 1, False, i + 1, True
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
        if nxt == "more":
            # "Then two more ghouls follow": that many beside the ones already met.
            form, count, plural_needed, j = "more", n, n > 1, i + 2
        else:
            form, count, plural_needed = "count", n, n > 1
    elif low == "the":
        n = _count_of(nxt)
        if n:
            form, count, plural_needed, j = "count", n, n > 1, i + 2
        else:
            form = "the"
    else:
        return None
    return _head_at(toks, i, j, form, count, ordinal, plural_needed, stated, objects, bare)


def _head_at(toks: list[str], i: int, j: int, form: str, count: int, ordinal: int, plural_needed: bool | None,
             stated: bool, objects: frozenset[str] | set[str] = frozenset(), bare: bool = False) -> dict[str, Any] | None:
    """The head noun (after up to two modifiers from ``j``) and the verb it is the subject of.

    ``bare``: the phrase is the object of the player's verb, so it needs no
    verb of its own; its head is the word the noun phrase stops on.
    """
    for k in range(3):
        at = j + k
        if at >= len(toks):
            return None
        noun = toks[at]
        if not _word(noun) or noun.lower() in _CLOSED or noun.lower().endswith(("'s", "’s")):
            return None
        plural = is_plural(noun)
        if plural_needed is True and not plural:
            continue
        if plural_needed is False and plural and form != "the":
            continue
        # The modifiers before the noun must be words too ("a rotting ghoul").
        verb_at = at + 1
        if verb_at < len(toks) and re.fullmatch(r"[a-z]+ly", toks[verb_at], re.I) and verb_at + 1 < len(toks):
            verb_at += 1  # an adverb: "4 ghouls brutally attack you"
        ing = False
        is_object = False
        is_bare = False
        if (verb_at + 1 < len(toks) and toks[verb_at].lower() in {"that", "who", "which"}
                and _verb_shaped(toks[verb_at + 1], plural)):
            # A relative clause that has it act ("a ghoul that lunges", "raiders who
            # are aiming"): the figure doing it, wherever the phrase stands.
            verb_at, ing = verb_at + 1, True
        elif verb_at < len(toks) and _verb_shaped(toks[verb_at], plural):
            # Right after the noun, "-ing" is the figure doing it ("4 ghouls eating someone").
            ing = toks[verb_at].lower().endswith("ing") and toks[verb_at].lower() not in _BE_HAVE
        else:
            verb_at = _verb_after_phrase(toks, at + 1, plural) if at + 1 < len(toks) else -1
            if verb_at < 0:
                if bare and _np_ends(toks, at):
                    # The player sees it: "you see a pack of ghouls", "you spot two raiders behind the wreck".
                    verb_at, is_bare = at, True
                elif singular(noun) in objects:
                    # The player's line acts on this kind: the phrase counts with no verb.
                    verb_at, is_object = at, True
                else:
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
            "acts": True if (is_object or is_bare) else _acts(toks, verb_at),
            "_end": verb_at + 1,
            "_ing": ing,
            "_object": is_object,
            "_bare": is_bare,
            "_head": at,
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


# What may stand before a capitalised word at the start of a sentence or of a quote.
_SENTENCE_OPENERS = frozenset('.!?"\'“”‘’:')


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
        word = hit.group(1)
        before = plain[: hit.start()].rstrip()
        if word[:1].isupper() and before and before[-1] not in _SENTENCE_OPENERS:
            # Capitalised inside a sentence: a proper name, never a kind ('the name Veyra' read as
            # the kind Veyra and made 'Veyra 1'; prose does not capitalise 'ghoul' mid-sentence).
            return ""
        if is_plural(word) and word.lower() != base:
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


def speaks_prompt(text: str, kind: str, quote: str) -> str:
    """The user half of the figure-speaks ask, exactly as sent."""
    said = quote if len(quote) <= SPEAKS_QUOTE_CHARS else quote[:SPEAKS_QUOTE_CHARS].rsplit(" ", 1)[0] + " ..."
    return f"Text: {text}\n{SPEAKS_QUESTION.format(noun=kind, quote=said)}"


def _stored_kinds(conn) -> set[str]:
    try:
        return {str(r[0] or "").strip().lower() for r in conn.execute("SELECT DISTINCT kind FROM npcs").fetchall()} - {""}
    except Exception:
        return set()


def kind_check_prompt(sentence: str, noun: str) -> str:
    """The user half of the second figure check, exactly as sent."""
    return f"Text: {sentence}\n{KIND_CHECK_QUESTION.format(noun=noun)}"


def _ask_yes_no(call, system: str, user: str, phase: str, kind: str, trace, usage) -> bool | None:
    """One traced yes/no ask; None when it failed or the reply could not be read (both noted)."""
    from app.entity_kinds import read_yes_no

    try:
        reply = call(system, user, phase, MAX_TOKENS, trace, usage)
    except Exception as exc:
        turn_ledger.note("npc", f"{phase}_ask_failed", kind=kind, error=f"{type(exc).__name__}: {exc}"[:160])
        return None
    said = read_yes_no(reply)
    if said is None:
        turn_ledger.note("npc", f"{phase}_unread", kind=kind, reply=str(reply or "")[:80])
    return said


def settle(result: dict[str, Any], narration: str, conn, *, ask: bool, call, trace=None, usage=None,
           line: str = "") -> dict[str, Any]:
    """Decide, before apply_turn's write block, which nouns are figures and whether new ones are hostile.

    Verdicts go on ``result["_figures"]``: {kind: {"figure": bool, "hostile":
    bool | None, "by": "record" | "op" | "ask"}}. ``call(system, user, phase,
    max_tokens, trace, usage)`` is entity_kinds' ask. ``ask=False`` (the
    offline narrator) asks nothing: only the records and the ops decide.
    ``line`` is the player's own line: the kinds it acts on ("i shoot the
    ghoul") are kept on ``result["_figure_objects"]`` for file_figures.

    A noun with no record is asked about only when the prose shows it present
    (the subject of an action verb in a clause that has the player in it, an
    -ing or relative clause that has it act, or the object of the player's
    own verb: "you see a pack of ghouls") or the player's line acts on it,
    and only in a form that could file one (a count, "another", an ordinal).
    It is a figure only when two differently worded asks both say yes; at
    most MAX_FIGURE_ASKS of those asks a turn, in the order the prose shows
    the nouns.
    """
    objects = sorted(player_objects(line)) if line else []
    if objects:
        result["_figure_objects"] = objects
    found = mentions(narration, objects)
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
            # Only a noun shown doing something in a clause with the player
            # in it, or one the player's own line acts on, is asked about.
            shown = next((m for m in ms if m["you"] and m["acts"] and m["form"] in _MINTING_FORMS),
                         None)
            if shown is None or not ask:
                continue
            if kind_asks + 2 > MAX_FIGURE_ASKS:
                # Both of a noun's asks must fit, or it is not started.
                turn_ledger.note("npc", "figure_kind_not_asked", kind=kind, reason="ask limit",
                                 limit=MAX_FIGURE_ASKS)
                continue
            kind_asks += 1
            said = _ask_yes_no(call, YES_NO_SYSTEM, kind_prompt(shown["sentence"], kind), KIND_PHASE, kind, trace, usage)
            if said is None:
                continue
            checked = None
            if said:
                # One yes files nothing: the second, differently worded check must agree.
                kind_asks += 1
                checked = _ask_yes_no(call, YES_NO_SYSTEM, kind_check_prompt(shown["sentence"], kind),
                                      KIND_CHECK_PHASE, kind, trace, usage)
                if checked is None:
                    continue
            figure = bool(said and checked)
            turn_ledger.note("npc", "noun_is_a_figure" if figure else "noun_is_no_figure", kind=kind, by="ask",
                             first=bool(said), check=checked)
            verdicts[kind] = {"figure": figure, "hostile": None, "by": "ask"}
            if not figure:
                continue
        # Hostility, for a kind this turn may mint (a count, another, an
        # ordinal). The person words the figure hints know keep their old
        # default (neutral, or the op's ATTITUDE): only other kinds are asked.
        minting = next((m for m in ms if m["form"] in _MINTING_FORMS), None)
        if not ask or minting is None or kind in op_attitudes or kind in people:
            continue
        if hostile_asks >= MAX_HOSTILE_ASKS:
            continue
        hostile_asks += 1
        said = _ask_yes_no(call, YES_NO_SYSTEM, hostile_prompt(minting["sentence"], minting["phrase"]), HOSTILE_PHASE,
                           kind, trace, usage)
        verdicts[kind]["hostile"] = said
        if said is not None:
            turn_ledger.note("npc", "figure_hostile" if said else "figure_not_hostile", kind=kind)
    # A line a pronoun gives to a figure that is no person word ('"..." she
    # asks' after "a nurse looks up at you") is that figure's only when one ask
    # says so: after "A ghoul lunges at you", the "she" who shouts "Get down!"
    # is someone else, and the face seeded for the line stays the speaker.
    speak_asks = 0
    for spoken in speaker_lines(narration) if ask else []:
        kind = spoken["kind"]
        if spoken["by"] != "pronoun" or not kind or kind in people:
            continue
        verdict = verdicts.get(kind) or ({"figure": True, "hostile": None, "by": "record"} if kind in stored or kind in ops else None)
        if not verdict or not verdict.get("figure") or "speaks" in verdict:
            continue
        if speak_asks >= MAX_SPEAK_ASKS:
            turn_ledger.note("npc", "figure_speaks_not_asked", kind=kind, reason="ask limit")
            continue
        speak_asks += 1
        said = _ask_yes_no(call, YES_NO_SYSTEM, speaks_prompt(spoken["text"], kind, spoken["quote"]), SPEAKS_PHASE,
                           kind, trace, usage)
        verdict["speaks"] = bool(said)
        verdicts[kind] = verdict
        turn_ledger.note("npc", "figure_speaks" if said else "figure_does_not_speak", kind=kind, reply=said)
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


def speaker_lines(narration: str) -> list[dict[str, Any]]:
    """Who speaks each quoted line, in order: {"kind", "by", "quote", "text"}.

    The speaker is the first noun outside the quotes of the line's own unit
    ('"..." the nurse says' -> "nurse", by "noun"; '"Get down!" someone shouts'
    -> "someone"); a pronoun alone ('"..." she asks') points at the last figure
    shown before the line (by "pronoun"; ``text`` is that sentence and the
    line). ``kind`` is "" when it is no figure kind the prose shows. The
    player's own lines ("you say") are no one's here.
    """
    from app.conversation import _QUOTE_RE, _spoken_span
    from app.narration_pipeline import quoted_spans, speech_units

    flat = re.sub(r"\s+", " ", re.sub(r"\s*\[\[[^\]]*\]\]", "", str(narration or ""))).strip()
    out: list[dict[str, Any]] = []
    last, last_unit = "", ""
    for unit in speech_units(flat):
        outside = _QUOTE_RE.sub(" ", unit)
        spoken = [s for s in quoted_spans(unit) if _spoken_span(s)]
        if spoken:
            word, by = _speaker_word(outside, last)
            text = unit if by != "pronoun" or not last_unit or last_unit == unit else f"{last_unit} {unit}"
            out.append({"kind": word, "by": by, "quote": spoken[0], "text": text})
        # The last figure shown doing something, as before the player's seeing was read:
        # "you see a clipboard in her hand" is not who speaks next.
        shown = [m for m in mentions(outside) if m["subject"]]
        if shown:
            last, last_unit = shown[-1]["kind"], unit
    return out


def speaker_kinds(narration: str, speaks: Any = ()) -> list[str]:
    """The kind of whoever speaks each quoted line, in order ("" when it is no figure kind the prose shows).

    A pronoun ("she asks") is the last figure shown only when that figure is
    a person word the figure hints know, or a kind in ``speaks`` (the turn's
    figure_speaks ask said yes): in 'A ghoul lunges at you. "Get down!" she
    shouts' the "she" is not the ghoul, and the face seeded for the line
    stays the speaker.
    """
    people = _person_words()
    allowed = {str(k).lower() for k in speaks or ()}
    out: list[str] = []
    for line in speaker_lines(narration):
        kind = line["kind"]
        if line["by"] == "pronoun" and kind and kind not in people and kind not in allowed:
            kind = ""
        out.append(kind)
    return out


def _speaker_word(outside: str, last: str) -> tuple[str, str]:
    for tok in _TOKEN_RE.findall(outside):
        low = tok.lower()
        if low in {"he", "she", "they"}:
            return last, "pronoun"
        if low in {"you", "i", "we"} or not _word(tok):
            return "", ""
        if low in _CLOSED or _verb_shaped(low, False) or re.fullmatch(r"[a-z]+ly", low):
            continue  # "says the nurse", "the nurse", "quietly"
        return singular(low), "noun"
    return "", ""


def _fresh_unnamed(conn, location_id: int, max_id_before: int | None, narration: str,
                   result: dict[str, Any], kind: str = "") -> list[Any]:
    """People the cast seeding made here this turn under a drawn name the prose never uses.

    A line nobody known speaks seeds a face with a drawn name and no kind
    (world._ensure_npcs_from_narration): cc87dd29 T3's "a nurse in a blue
    helmet ... she asks" was stored as a drawn "Beth". That face is the figure
    the prose shows, so it is numbered as that figure, not minted beside it.

    Only when the line is that figure's: the face is a figure of ``kind`` when
    one of the turn's quoted lines is spoken by that kind (speaker_kinds). In
    '"Get down!" someone shouts from behind the counter. A ghoul lunges at
    you' the speaker is someone, not the ghoul: two figures, and the face
    stays who it is.
    """
    if max_id_before is None:
        return []
    speaks = [k for k, v in (result.get("_figures") or {}).items() if isinstance(v, dict) and v.get("speaks")]
    if kind and singular(kind) not in speaker_kinds(narration, speaks):
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
    if str(kind or "").strip().lower() not in _person_words():
        # The face was drawn as a person (a role, a race) for a line a creature turns out to
        # speak: it is the creature now, minted as one would be (reviewer: Raider 1 had become
        # a human scribe).
        updates["race"] = "unknown"
        updates["role"] = "local"
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
    found = mentions(narration, result.get("_figure_objects") or ())
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
            ms = [m for m in ms if m["form"] not in {"count", "more", "ordinal"} or (
                is_plural(m["noun"]) and m.get("stated") and m["you"])]
        here = _here(conn, int(location_id), kind)
        total = len(here)
        ambiguous = False
        for m in ms:
            if m["form"] == "count":
                total = max(total, int(m["count"] or 0))
            elif m["form"] == "another":
                total += 1
            elif m["form"] == "more":
                total += int(m["count"] or 0)
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
        # And brought back for the sketch pass (sketches._brought_back reads
        # the turn's touched ids): prose that keeps saying "the ghoul" never
        # says "Ghoul 1", and the figure faded mid-fight without this.
        shown = result.setdefault("_figures_shown", []) if ms and here else []
        for row in (here if ms else []):
            _mark_present(result, str(row["code"] or ""))
            if int(row["id"]) not in shown:
                shown.append(int(row["id"]))
        if not new:
            if here and ms:
                turn_ledger.note("npc", "figure_is_one_here", kind=kind, names=[str(r["name"] or "") for r in here])
            elif ms:
                # "The deathclaw charges you" with none here and no op: a "the"
                # refers back to one met, which may be following the player
                # from elsewhere, so nothing is minted (an op files it).
                turn_ledger.note("npc", "figure_referred_back_none_here", kind=kind)
            continue
        attitude = str(op.get("attitude") or "")
        if not attitude and verdict.get("hostile"):
            attitude = "hostile"
        fresh = _fresh_unnamed(conn, int(location_id), max_id_before, narration, result, kind) if kind not in vague else []
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


# ------------------------------------------------------- what the story sees


def story_label(kind: str, *, definite: bool = False) -> str:
    """What the story is shown for an unnamed figure: what it is, never "Ghoul 1".

    "an unnamed ghoul" in what the narrator reads (the context, the engine's
    notes); ``definite`` gives "the ghoul", the form prose uses when the
    engine writes the figure into the story itself (a bare [[B]] filled in).
    """
    word = str(kind or "").strip().lower()
    if not word:
        return ""
    return f"the {word}" if definite else f"an unnamed {word}"


def numbered_name(row: Any) -> tuple[str, str]:
    """(name, kind) when the record is an unnamed figure still under its number ("Ghoul 1", "Ghoul"), else ("", "")."""
    try:
        getter = row.get if isinstance(row, dict) else (lambda key: row[key])
        kind = str(getter("kind") or "").strip()
        number = int(getter("kind_number") or 0)
        name = str(getter("name") or "").strip()
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return "", ""
    if kind and number and name == numbered(kind, number):
        return name, kind
    return "", ""


def _numbered_rows(value: Any, out: dict[str, str], depth: int = 0, definite: bool = False) -> None:
    if depth > 6:
        return
    if isinstance(value, dict):
        name, kind = numbered_name(value)
        if name:
            out[name] = story_label(kind, definite=definite)
        # The dead too: a place's bodies and the_dead's people (the body change), or "Ghoul 1"
        # reaches the story through the bodies list and the death facts.
        for key in ("npcs", "current_location", "locations", "bodies", "the_dead", "people"):
            if key in value:
                _numbered_rows(value[key], out, depth + 1, definite)
    elif isinstance(value, list):
        for item in value:
            _numbered_rows(item, out, depth + 1, definite)


def story_names(context: dict[str, Any] | None, *, definite: bool = False) -> dict[str, str]:
    """{numbered name: story label} for the unnamed figures still under their number in this context.

    Read from the people records the context carries (locations[].npcs,
    current_location.npcs, npcs), so a row named later ("Kade") is not in it.
    """
    out: dict[str, str] = {}
    if isinstance(context, dict):
        _numbered_rows(context, out, definite=definite)
    return out


def prose_view(text: str, names: dict[str, str]) -> str:
    """Prose with every numbered name in it written as the figure it is ("the ghoul [[B]]").

    The one place the engine's own label could reach the player's story: the
    label repair fills a bare "[[B]]" with the record's name, and the narrator
    may copy a name it saw. ``names`` is story_names(context, definite=True).
    "while Ghoul 2 [[B]] lunges" reads "while the ghoul [[B]] lunges"; at a
    sentence's start, "The ghoul [[B]]"; "the Ghoul 2" does not double the "the".
    """
    if not text or not names:
        return text or ""
    pattern = re.compile(
        r"(?<![\w'’])(?:(the|a|an)\s+)?("
        + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        + r")(?![\w'’])",
        re.IGNORECASE,
    )
    lookup = {n.lower(): label for n, label in names.items()}

    def put(match: re.Match[str]) -> str:
        label = lookup.get(match.group(2).lower(), "")
        if not label:
            return match.group(0)
        article = match.group(1)
        if article:
            word = label.split(" ", 1)[-1]
            return f"{article} {word}"
        before = text[: match.start()].rstrip()
        if not before or before[-1] in ".!?\"“”":
            return label[:1].upper() + label[1:]
        return label

    return pattern.sub(put, text)


def story_view(value: Any, names: dict[str, str]) -> Any:
    """``value`` with every numbered name in it shown as the figure it is (see story_names).

    The record keeps its name (the save and the UI number them: they are the
    engine's and the player's); the narrator's packet does not, so "Woman 1"
    and "Ghoul 1" never reach the prose. The code beside a name stays, so
    "Ghoul 1 [[C]]" reads "an unnamed ghoul [[C]]".
    """
    if not names:
        return value
    pattern = re.compile(
        r"(?<![\w'’])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![\w'’])"
    )

    def walk(item: Any) -> Any:
        if isinstance(item, str):
            return pattern.sub(lambda m: names[m.group(1)], item) if item else item
        if isinstance(item, dict):
            return {key: walk(v) for key, v in item.items()}
        if isinstance(item, list):
            return [walk(v) for v in item]
        if isinstance(item, tuple):
            return tuple(walk(v) for v in item)
        return item

    return walk(value)


def ask_label(person: dict[str, Any], people: list[dict[str, Any]]) -> str:
    """What the attack ask calls a numbered figure: "the ghoul" when it is the only one of its kind here."""
    kind = str(person.get("kind") or "").strip()
    name = str(person.get("name") or "").strip()
    if not kind or not int(person.get("kind_number") or 0) or name != numbered(kind, int(person.get("kind_number") or 0)):
        return name
    same = [p for p in people if str(p.get("kind") or "").strip().lower() == kind.lower()]
    return f"the {kind.lower()}" if len(same) == 1 else name
