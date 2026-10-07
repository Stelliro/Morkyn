"""
Per-world fact tables (playtest #8).

Setup describes the world in free-text settings: world_races, race_magic_rules,
race_ability_rules, custom_style, faction_pressure. Those strings used to sit
whole in playthrough_options, and the turn packet either carried them as
paragraphs or (for custom_style and the race rules) dropped them entirely, so a
rule like "only these peoples have magic" never reached the scene writer.

This module keeps them as small rows the engine owns:

  world_races  one row per people: code (R1..), name, short traits, magic
               access (closed enum), short ability rules, lifespan in years,
               size band
  world_facts  lore and custom rows: code (F1..), kind (closed enum), title,
               text of at most 200 characters, links to other codes, tags

Population happens in two steps:

  seed_from_options(conn, options)  deterministic split, run inside
                                    world.start_playthrough. The game works
                                    with this alone.
  run_post_start_passes()           the post-start, pre-turn-1 phase. Each
                                    registered pass makes one small model call
                                    in a closed line format; the engine parses
                                    and validates every line. The world-facts
                                    refinement is the first pass; custom
                                    proficiencies (playtest #1) register here
                                    the same way.

Read side:

  relevant_facts_for_state(state, player_input)  a budgeted handful of rows
                                    for one turn's packet: the races of people
                                    present, races and lore the player names,
                                    facts linked to those
  all_facts(conn)                   everything, for GET /api/world-facts
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

MAGIC_ACCESS = ("none", "rare", "learned", "innate", "common", "unknown")
SIZE_BANDS = ("tiny", "small", "medium", "large", "huge", "varies", "unknown")
FACT_KINDS = ("custom", "history", "rule", "faction", "place_lore", "magic", "tone")

NAME_MAX = 40
TRAITS_MAX = 120
ABILITY_MAX = 160
TITLE_MAX = 60
TEXT_MAX = 200
TAG_MAX = 4
LINK_MAX = 6
RACE_LIMIT = 16
FACT_LIMIT = 60
LIFESPAN_MAX = 100000

# Turn packet budget for fact rows, in characters of compact JSON.
RELEVANT_BUDGET_CHARS = 900
RELEVANT_FACT_LIMIT = 6

_MAGIC_WORDS = re.compile(r"\b(magic|magical|spells?|cast(?:s|ing|ers?)?|mana|sorcery|arcane|witchcraft|miracles?|enchant\w*)\b", re.I)
_NEGATION = re.compile(r"\b(no|not|never|cannot|can't|cant|without|lacks?|lacking|forbidden|unable|barred)\b", re.I)
_ONLY = re.compile(r"\bonly\b", re.I)
_LEARNED = re.compile(r"\b(learn\w*|train\w*|stud(?:y|ies|ied)|taught|teach\w*|apprentic\w*)\b", re.I)
_RARE = re.compile(r"\b(rare|rarely|seldom|few|scarce)\b", re.I)
_COMMON = re.compile(r"\b(common|commonly|all|every|most|widespread)\b", re.I)
_TONE = re.compile(r"\b(mood|tone|feel|feeling|atmosphere|stakes|grounded|grim|hopeful|bleak)\b", re.I)
_HISTORY = re.compile(r"\b(once|ago|ancient|fell|founded|war|wars|age of|era|before the)\b", re.I)
_STOPWORDS = {
    "the", "and", "with", "that", "this", "from", "into", "their", "there", "they", "them",
    "have", "has", "had", "are", "was", "were", "been", "being", "but", "for", "not", "only",
    "its", "it's", "than", "then", "when", "where", "which", "while", "who", "whom", "will",
    "can", "may", "must", "through", "earned", "present", "land", "world", "life", "daily",
}

# Engine numbers for peoples the setup names by a familiar word. A people the
# table does not know rolls its numbers from the campaign seed, so the same
# world always gets the same numbers and the model pass may adjust them.
_KNOWN_PEOPLES: dict[str, tuple[int, str]] = {
    "human": (80, "medium"),
    "elf": (700, "medium"),
    "half-elf": (180, "medium"),
    "dwarf": (300, "small"),
    "orc": (60, "medium"),
    "half-orc": (70, "medium"),
    "goblin": (40, "small"),
    "hobgoblin": (60, "medium"),
    "halfling": (120, "small"),
    "gnome": (350, "small"),
    "giant": (400, "huge"),
    "ogre": (90, "large"),
    "troll": (150, "large"),
    "kobold": (40, "tiny"),
}
_LIFESPAN_ROLLS = (40, 60, 80, 100, 150, 250, 400)
_SIZE_ROLLS = ("small", "medium", "medium", "medium", "large")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def ensure_world_fact_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS world_races (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            code            TEXT    NOT NULL UNIQUE,
            name            TEXT    NOT NULL,
            name_key        TEXT    NOT NULL UNIQUE,
            traits          TEXT    NOT NULL DEFAULT '',
            magic_access    TEXT    NOT NULL DEFAULT 'unknown',
            ability_rules   TEXT    NOT NULL DEFAULT '',
            lifespan_years  INTEGER NOT NULL DEFAULT 0,
            size_band       TEXT    NOT NULL DEFAULT 'unknown',
            source          TEXT    NOT NULL DEFAULT 'split',
            created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS world_facts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    NOT NULL UNIQUE,
            kind        TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            text        TEXT    NOT NULL,
            links       TEXT    NOT NULL DEFAULT '[]',
            tags        TEXT    NOT NULL DEFAULT '[]',
            source      TEXT    NOT NULL DEFAULT 'split',
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_world_facts_kind ON world_facts(kind)")


def clear_world_facts(conn) -> None:
    conn.execute("DELETE FROM world_races")
    conn.execute("DELETE FROM world_facts")


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def race_key(name: Any) -> str:
    """Folded name a people is matched by: lower case, hyphens and spaces alike."""
    return re.sub(r"[\s_-]+", "-", _clean(name).lower()).strip("-")


def _singular(word: str) -> str:
    if word.endswith("ves") and len(word) > 4:
        return word[:-3] + "f"
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and word[:-2].endswith(("sh", "ch", "x", "s")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def _race_forms(name: str) -> set[str]:
    key = race_key(name)
    if not key:
        return set()
    spaced = key.replace("-", " ")
    forms = {key, spaced, key.replace("-", "")}
    last = spaced.split(" ")[-1]
    stem = spaced[: len(spaced) - len(last)]
    if last.endswith("f"):
        forms.update({stem + last[:-1] + "ves", stem + last + "s"})
    elif last.endswith(("s", "sh", "ch", "x")):
        forms.add(stem + last + "es")
    elif last.endswith("folk") or last.endswith("kin"):
        pass
    else:
        forms.add(stem + last + "s")
    forms.update({form.replace(" ", "-") for form in list(forms)})
    head = spaced.split(" ")[0]
    if " " in spaced and len(head) >= 5:
        forms.update({head, head + "s"})
    return {form for form in forms if form}


def _mentions(text: str, name: str) -> bool:
    low = text.lower()
    for form in _race_forms(name):
        tokens = [re.escape(token) for token in re.split(r"[\s-]+", form) if token]
        if not tokens:
            continue
        pattern = r"(?<![a-z0-9])" + r"[\s-]?".join(tokens) + r"(?![a-z0-9])"
        if re.search(pattern, low):
            return True
    return False


def split_list(text: Any, limit: int = RACE_LIMIT) -> list[str]:
    """A comma, semicolon, slash or 'and' list as separate labels, first spelling kept."""
    raw = _clean(text)
    if not raw:
        return []
    parts = re.split(r"\s*(?:[,;/\n]|\band\b|\bor\b|&)\s*", raw, flags=re.I)
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        label = part.strip(" .:!?\"'()[]")
        if not label:
            continue
        key = race_key(label)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(label[:NAME_MAX])
        if len(out) >= limit:
            break
    return out


def _chunks(sentence: str, limit: int = TEXT_MAX) -> list[str]:
    """Cut a long sentence at clause commas, then at words, into pieces under the cap."""
    if len(sentence) <= limit:
        return [sentence]
    pieces: list[str] = []
    current = ""
    for clause in re.split(r"(?<=,)\s+", sentence):
        candidate = f"{current} {clause}".strip() if current else clause
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current.rstrip(","))
        while len(clause) > limit:
            cut = clause.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            pieces.append(clause[:cut].rstrip(","))
            clause = clause[cut:].strip()
        current = clause
    if current:
        pieces.append(current.rstrip(","))
    return [piece for piece in pieces if piece]


def split_sentences(text: Any) -> list[str]:
    """Sentences (and semicolon clauses) of a free-text field, each at most TEXT_MAX."""
    raw = _clean(str(text or "").replace("\r", "\n"))
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\s*;\s*|\n+", raw):
        sentence = sentence.strip()
        if len(sentence) < 3:
            continue
        for piece in _chunks(sentence):
            key = piece.lower().rstrip(".")
            if key in seen:
                continue
            seen.add(key)
            out.append(piece)
    return out


# Titles and tags (playtest #23). A title is the subject noun phrase of the
# fact, not its first six words: "In a land of mist-shrouded forests, the
# kingdom of Eldoria is ruled by..." is titled "Kingdom of Eldoria". Tags are
# the nouns it is about, never "both" or an -ed adjective.
_LEAD_IN = re.compile(
    r"^(?:in|on|at|across|under|beyond|throughout|within|among|before|after|since|when|where|while|"
    r"though|although|as|for|from|during|along|over|once|long ago)\b[^,]{0,100},\s*",
    re.I,
)
_VERB_WORDS = {
    "is", "are", "was", "were", "be", "been", "has", "have", "had", "can", "cannot", "can't", "could",
    "may", "might", "must", "will", "would", "should", "shall", "do", "does", "did", "don't", "doesn't",
    "coexist", "coexists", "rule", "rules", "ruled", "hold", "holds", "held", "live", "lives", "dictate",
    "dictates", "earn", "earns", "need", "needs", "lack", "lacks", "keep", "keeps", "kept", "control",
    "controls", "own", "owns", "see", "sees", "run", "runs", "guard", "guards", "worship", "worships",
    "fear", "fears", "trade", "trades", "serve", "serves", "sense", "senses", "learn", "learns", "cast",
    "casts", "resist", "resists", "work", "works", "draw", "draws", "pay", "pays", "lose", "loses", "gain",
    "gains", "inherit", "inherits", "heal", "heals", "hear", "hears", "climb", "climbs", "endure", "endures",
    "remember", "remembers", "track", "tracks", "feel", "feels", "start", "starts", "tire", "tires",
    "harbor", "harbors", "harbour", "harbours", "shape", "shapes", "govern", "governs", "lead", "leads",
    "led", "want", "wants", "seek", "seeks", "hunt", "hunts", "fight", "fights", "follow", "follows",
    "stand", "stands", "lie", "lies", "rise", "rises", "fell", "falls", "dwell", "dwells", "come", "comes",
    "came", "remain", "remains", "bring", "brings", "mark", "marks", "carry", "carries", "spread", "spreads",
    "grow", "grows", "know", "knows", "believe", "believes", "use", "uses", "make", "makes", "take", "takes",
    "meet", "meets", "gather", "gathers", "forbid", "forbids", "allow", "allows", "require", "requires",
}
_HAVE_WORDS = {"has", "have", "had", "hold", "holds", "own", "owns", "keep", "keeps"}
_DETERMINERS = {
    "the", "a", "an", "only", "all", "most", "some", "every", "each", "both", "many", "few", "no", "its",
    "their", "this", "these", "those", "that", "his", "her", "our", "any",
}
_PREPOSITIONS = {"through", "by", "of", "in", "from", "with", "under", "over", "against", "among", "across", "beyond", "to", "for"}
_TAG_SKIP = {
    "both", "alike", "each", "every", "other", "others", "some", "many", "much", "very", "also", "thick",
    "high", "such", "more", "most", "less", "into", "onto", "upon", "over", "under", "about", "among",
    "across", "still", "even", "just", "like", "same", "whose", "what", "these", "those", "here", "your",
    "between", "against", "within", "without", "beyond", "around", "after", "before", "because", "though",
    "although", "people", "peoples", "thing", "things", "kind", "kinds", "part", "parts", "way", "ways",
    "fates", "fate", "air", "tension", "stakes", "pressure", "pressures", "groups",
}
_ADJECTIVE_ENDINGS = ("ical", "ious", "eous", "ous", "ful", "less", "ish", "ly")
_COMMON_ADJECTIVES = {
    "harsh", "sparse", "rare", "local", "fair", "common", "small", "large", "great", "little", "young",
    "dark", "deep", "cold", "warm", "hard", "true", "real", "full", "free", "secret", "ancient", "dead",
    "long", "short", "whole", "first", "second", "third", "last", "next", "three", "four", "five",
    "seven", "eight", "nine", "twelve", "hundred", "thousand", "present", "strong", "weak", "open",
    "close", "near", "distant", "wild", "grim", "bleak", "safe", "rich", "poor", "proud", "known",
    "ordinary", "usual", "strict", "severe", "often",
}


def _is_verbish(word: str) -> bool:
    low = word.lower()
    return low in _VERB_WORDS or (low.endswith("ed") and len(low) > 4) or (low.endswith("en") and low in {"taken", "given", "broken", "chosen", "forbidden", "hidden", "written"})


# A title never ends on a joiner, preposition or determiner (playtest #35:
# "Survivors harness forbidden magic and", "Modern urban elements blend with").
_TITLE_TAIL = _DETERMINERS | _PREPOSITIONS | {
    "and", "or", "but", "nor", "at", "on", "into", "when", "where", "while", "which", "that", "who", "here",
    "there", "now", "as", "always", "never", "often", "it", "is", "are",
}
_PRONOUN_SUBJECTS = {"nobody", "everyone", "everybody", "none", "anyone", "someone", "somebody", "nothing", "everything", "no-one"}
_PARENTHETICAL = re.compile(r",\s*(?:when|where|if|though|although|once|unless|while|as)\b[^,]{0,60},\s*", re.I)
# A noun phrase ends at a subordinator or relative word: "Frontier dark
# fantasy where thin law..." is titled "Frontier dark fantasy" (playtest #35).
_SUBORDINATORS = {"where", "when", "which", "that", "who", "whom", "whose", "while", "whereas"}
# A fact split off the tail of a sentence can open on a participle clause
# ("ensuring that strength is not inherited..."): the clause is not the subject.
_LEAD_PARTICIPLE = re.compile(r"^[a-z]+ing\s+that\s+", re.I)


def _cut_at_subordinator(words: list[str]) -> list[str]:
    cut = next((i for i, w in enumerate(words) if i and w.lower() in _SUBORDINATORS), None)
    return words[:cut] if cut is not None else words


def _trim_tail(words: list[str]) -> list[str]:
    out = list(words)
    while len(out) > 1 and out[-1].lower() in _TITLE_TAIL:
        out.pop()
    return out


def _cap(words: list[str]) -> str:
    words = _trim_tail(words)
    title = " ".join(words).replace("/", " and ")
    title = re.sub(r"\s+", " ", title).strip(" ,;:-")
    while len(title) > TITLE_MAX and " " in title:
        title = title.rsplit(" ", 1)[0]
    return title[:1].upper() + title[1:TITLE_MAX]


def _object_words(words: list[str], limit: int = 2) -> list[str]:
    """The head of the phrase after a verb: up to ``limit`` content words, skipping determiners.

    A leading participle used as an adjective counts ("calculated risks",
    "forbidden magic").
    """
    out: list[str] = []
    for index, word in enumerate(words):
        low = word.lower()
        if low in _DETERMINERS and not out:
            continue
        participle = (
            not out
            and _is_verbish(word)
            and low not in _VERB_WORDS
            and index + 1 < len(words)
            and not _is_verbish(words[index + 1])
            and words[index + 1].lower() not in _PREPOSITIONS | _DETERMINERS | {"and", "or", "but"}
        )
        if low in {"and", "or", "but", "that", "which", "who"} or low in _PREPOSITIONS or (_is_verbish(word) and not participle):
            break
        out.append(word)
        if len(out) >= limit:
            break
    return out


def _clause_words(text: str) -> tuple[list[str], int | None]:
    """The words of a fact after any lead-in clause, and the index of its main verb if one is found."""
    body = _clean(text).rstrip(".!?")
    trimmed = _LEAD_IN.sub("", body, count=1)
    trimmed = _LEAD_PARTICIPLE.sub("", trimmed or body, count=1)
    # "Magic, when it exists, is a secret": the aside is not the subject.
    trimmed = _PARENTHETICAL.sub(" ", trimmed or body)
    words = re.findall(r"[A-Za-z][A-Za-z'/-]*", trimmed or body)
    verb = next((index for index, word in enumerate(words) if index and word.lower() in _VERB_WORDS), None)
    if verb is None or verb > 7:
        # "Snow closes the passes", "The river floods each spring": a
        # third-person verb right after a one-noun subject.
        start = 1 if words and words[0].lower() in _DETERMINERS else 0
        guessed = None
        if len(words) > start + 2:
            noun, guess = words[start].lower(), words[start + 1].lower()
            # "Small settlements struggle...": an adjective then a plural
            # noun is a noun phrase, not a noun and its verb (playtest #35).
            adjective_first = noun in _COMMON_ADJECTIVES or noun.endswith(_ADJECTIVE_ENDINGS)
            if (
                not adjective_first
                and guess.endswith("s") and not guess.endswith("ss") and not noun.endswith("s") and guess not in _DETERMINERS
            ):
                guessed = start + 1
        if guessed is None:
            # "Survivors harness forbidden magic", "Modern urban elements
            # blend with...": a plural noun and a plain verb (playtest #35).
            for j in range(start, min(start + 4, len(words) - 2)):
                noun, guess = words[j].lower(), words[j + 1]
                low = guess.lower()
                if not (noun.endswith("s") and not noun.endswith(("ss", "'s")) and len(noun) > 3):
                    continue
                if noun in _VERB_WORDS or noun in _PRONOUN_SUBJECTS:
                    continue
                if (
                    guess.islower()
                    and (not low.endswith("s") or low.endswith("ss"))
                    and low not in _DETERMINERS | _PREPOSITIONS | _TITLE_TAIL | _COMMON_ADJECTIVES
                    and not low.endswith(_ADJECTIVE_ENDINGS)
                    and not low.endswith(("ed", "ing"))
                    and not _is_verbish(guess)
                ):
                    guessed = j + 1
                    break
        if guessed is not None:
            verb = guessed
    return words, verb


def _title_for(text: str) -> str:
    """A short noun phrase naming what the fact is about."""
    # "DM stance: always keep fair..." is titled by its label.
    label, colon, _ = _clean(text).partition(":")
    label_words = re.findall(r"[A-Za-z][A-Za-z'/-]*", label)
    if colon and 2 <= len(label_words) <= 4 and not any(w.lower() in _VERB_WORDS for w in label_words):
        return _cap(label_words)
    words, verb = _clause_words(text)
    if not words:
        return _clean(text)[:TITLE_MAX]
    if verb is None or verb > 7:
        subject = words[: min(5, len(words))]
        while subject and subject[0].lower() in _DETERMINERS:
            subject = subject[1:]
        subject = _cut_at_subordinator(subject)
        # The noun phrase stops at the first verb-like word.
        cut = next((i for i, w in enumerate(subject) if i and _is_verbish(w)), None)
        if cut is not None:
            subject = subject[:cut]
        return _cap(subject or words[:4])
    if words[0].lower() in _PRONOUN_SUBJECTS:
        # "Nobody is born strong" says itself; "Born nobody" did not.
        return _cap(words[:5])
    subject = words[:verb]
    while len(subject) > 1 and subject[0].lower() in _DETERMINERS:
        subject = subject[1:]
    subject = _cut_at_subordinator(subject)[:5]
    rest = words[verb + 1:]
    content = [word for word in subject if word.lower() not in _DETERMINERS | _TITLE_TAIL | {"and", "or", "of"}]
    verb_word = words[verb].lower()
    if verb_word in _HAVE_WORDS:
        obj = _object_words(rest)
        if obj:
            return _cap([*obj, "of", *[w.lower() if w[:1].isupper() and w.lower() in _DETERMINERS else w for w in subject]])
    if len(content) <= 1 and rest:
        if verb_word in {"is", "are", "was", "were"} and len(rest) > 1 and _is_verbish(rest[0]) and rest[0].lower() not in _VERB_WORDS:
            # "The tone is grounded, with a focus on..." -> "Grounded tone":
            # the comma closes the predicate (playtest #35).
            after = re.search(
                r"\b" + re.escape(words[verb]) + r"\s+" + re.escape(rest[0]) + r"\s*[,;]", _clean(text), re.I
            )
            if after:
                return _cap([rest[0], *(word.lower() if word != word.upper() else word for word in subject)])
        index = 0
        while index < len(rest) and (
            _is_verbish(rest[index]) or rest[index].lower() in {"not", "never", "often", "always"}
            # "is not inherited but earned through..." reads past the "but".
            or (rest[index].lower() == "but" and index and rest[index - 1].lower() not in _PREPOSITIONS)
        ):
            index += 1
        if index < len(rest) and rest[index].lower() in _PREPOSITIONS:
            obj = _object_words(rest[index + 1:])
            if obj:
                # "Power is earned through calculated risks" -> "Power earned through calculated risks".
                lead = rest[:index]
                if any(w.lower() == "but" for w in lead):
                    # "not inherited but earned" -> the affirmed half: "earned".
                    lead = lead[max(i for i, w in enumerate(lead) if w.lower() == "but") + 1:]
                participles = [w for w in lead if _is_verbish(w) and w.lower() not in _VERB_WORDS]
                return _cap([*subject, *participles, rest[index].lower(), *obj])
        elif verb_word in {"is", "are", "was", "were"} and rest and rest[0].lower() in {"a", "an", "the"}:
            # "The land is a brutal frontier" -> "Land is a brutal frontier".
            obj = _object_words(rest)
            if obj:
                return _cap([*subject, verb_word, rest[0].lower(), *obj])
        elif verb_word in {"is", "are", "was", "were"} and index <= 1:
            # "Magic is rare" -> "Rare magic"; "The mood is grounded" -> "Grounded mood".
            adjective = rest[0]
            if adjective.lower() not in _DETERMINERS and adjective.lower() not in _PREPOSITIONS:
                return _cap([adjective, *(word.lower() if word != word.upper() else word for word in subject)])
        elif index == 0 and verb_word not in {"is", "are", "was", "were"}:
            # "Snow closes the high passes" -> "Snow and high passes".
            obj = _object_words(rest)
            if obj:
                return _cap([*subject, "and", *obj])
    if len(_trim_tail(content)) <= 1 and rest:
        # A one-word subject is not a title ("Power", "Land", "Survivors"):
        # name what it does as well.
        obj = _object_words(rest)
        if obj:
            return _cap([*_trim_tail(subject), words[verb], *obj])
    return _cap(subject)


def _tag_word(word: str) -> str:
    low = word.lower().strip("-'/")
    if len(low) < 4 or low in _STOPWORDS or low in _TAG_SKIP or low in _DETERMINERS:
        return ""
    if low in _VERB_WORDS or low.endswith(("ed", "ing")) and len(low) > 4:
        return ""
    if low.endswith(_ADJECTIVE_ENDINGS) or low in _COMMON_ADJECTIVES:
        return ""
    return low[:24]


def _tags_for(text: str, extra: list[str] | None = None, title: str = "") -> list[str]:
    """The nouns a fact is about: given tags, then title words, then names, then the rest."""
    words, verb = _clause_words(text)
    verb_word = words[verb].lower() if verb is not None and verb < len(words) else ""
    candidates: list[str] = [str(word) for word in extra or []]
    candidates += re.findall(r"[A-Za-z][A-Za-z'-]*", title)
    sentence_words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    candidates += [word for word in sentence_words[1:] if word[:1].isupper()]
    candidates += [word for word in sentence_words if word.lower() != verb_word]
    tags: list[str] = []
    seen: set[str] = set()
    for word in candidates:
        for part in re.split(r"/", word):
            tag = _tag_word(part)
            key = _singular(tag)
            if not tag or key in seen:
                continue
            seen.add(key)
            tags.append(tag)
            if len(tags) >= TAG_MAX:
                return tags
    return tags


def _sentence_kind(sentence: str, default: str = "custom") -> str:
    if _MAGIC_WORDS.search(sentence):
        return "magic"
    if _TONE.search(sentence):
        return "tone"
    if _HISTORY.search(sentence):
        return "history"
    return default


# ---------------------------------------------------------------------------
# Validation (every row, deterministic or model, passes through here)
# ---------------------------------------------------------------------------


def _enum(value: Any, allowed: tuple[str, ...], default: str | None = None) -> str | None:
    text = race_key(value).replace("-", "_") if value is not None else ""
    if text in allowed:
        return text
    return default


def validate_race_row(row: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    name = _clean(row.get("name")).strip(" .")
    if not name:
        errors.append("race name missing")
    elif len(name) > NAME_MAX or len(name.split()) > 4:
        errors.append("race name too long")
    magic = _enum(row.get("magic_access") or "unknown", MAGIC_ACCESS)
    if magic is None:
        errors.append(f"magic_access not one of {', '.join(MAGIC_ACCESS)}")
    size = _enum(row.get("size_band") or "unknown", SIZE_BANDS)
    if size is None:
        errors.append(f"size_band not one of {', '.join(SIZE_BANDS)}")
    try:
        lifespan = int(row.get("lifespan_years") or 0)
    except (TypeError, ValueError):
        lifespan = -1
    if lifespan < 0 or lifespan > LIFESPAN_MAX:
        errors.append("lifespan_years out of range")
    traits = _clean(row.get("traits"))
    if len(traits) > TRAITS_MAX:
        errors.append(f"traits over {TRAITS_MAX} chars")
    ability = _clean(row.get("ability_rules"))
    if len(ability) > ABILITY_MAX:
        errors.append(f"ability_rules over {ABILITY_MAX} chars")
    if errors:
        return None, errors
    return {
        "name": name,
        "name_key": race_key(name),
        "traits": traits,
        "magic_access": magic,
        "ability_rules": ability,
        "lifespan_years": lifespan,
        "size_band": size,
        "source": _clean(row.get("source")) or "split",
    }, []


def validate_fact_row(row: dict[str, Any], known_codes: set[str]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    kind = _enum(row.get("kind"), FACT_KINDS)
    if kind is None:
        errors.append(f"kind not one of {', '.join(FACT_KINDS)}")
    title = _clean(row.get("title")).strip(" .")
    text = _clean(row.get("text"))
    if not title:
        errors.append("title missing")
    elif len(title) > TITLE_MAX:
        errors.append(f"title over {TITLE_MAX} chars")
    if len(text) < 8:
        errors.append("text missing")
    elif len(text) > TEXT_MAX:
        errors.append(f"text over {TEXT_MAX} chars")
    links: list[str] = []
    for link in row.get("links") or []:
        code = _clean(link).upper()
        if not code or code in links:
            continue
        if code not in known_codes:
            errors.append(f"link {code} does not resolve")
            continue
        links.append(code)
    tags: list[str] = []
    for tag in row.get("tags") or []:
        word = race_key(tag)[:24]
        if word and word not in tags:
            tags.append(word)
    if errors:
        return None, errors
    return {
        "kind": kind,
        "title": title,
        "text": text,
        "links": links[:LINK_MAX],
        "tags": tags[:TAG_MAX],
        "source": _clean(row.get("source")) or "split",
    }, []


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _next_code(conn, table: str, prefix: str) -> str:
    used = {str(row["code"]) for row in conn.execute(f"SELECT code FROM {table}").fetchall()}
    number = 1
    while f"{prefix}{number}" in used:
        number += 1
    return f"{prefix}{number}"


def known_codes(conn) -> set[str]:
    codes = {str(row["code"]).upper() for row in conn.execute("SELECT code FROM world_races").fetchall()}
    codes |= {str(row["code"]).upper() for row in conn.execute("SELECT code FROM world_facts").fetchall()}
    try:
        codes |= {str(row["code"]).upper() for row in conn.execute("SELECT code FROM locations WHERE code != ''").fetchall()}
    except Exception:
        pass
    return codes


def _race_by_key(conn) -> dict[str, dict[str, Any]]:
    return {str(row["name_key"]): dict(row) for row in conn.execute("SELECT * FROM world_races ORDER BY id").fetchall()}


def store_race(conn, row: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Insert or update one people by folded name. Returns its code."""
    clean, errors = validate_race_row(row)
    if clean is None:
        return None, errors
    existing = conn.execute("SELECT code FROM world_races WHERE name_key = ?", (clean["name_key"],)).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE world_races SET traits = ?, magic_access = ?, ability_rules = ?,
                lifespan_years = ?, size_band = ?, source = ?
            WHERE name_key = ?
            """,
            (clean["traits"], clean["magic_access"], clean["ability_rules"], clean["lifespan_years"],
             clean["size_band"], clean["source"], clean["name_key"]),
        )
        return str(existing["code"]), []
    if conn.execute("SELECT COUNT(*) AS n FROM world_races").fetchone()["n"] >= RACE_LIMIT:
        return None, ["race table full"]
    code = _next_code(conn, "world_races", "R")
    conn.execute(
        """
        INSERT INTO world_races (code, name, name_key, traits, magic_access, ability_rules,
            lifespan_years, size_band, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (code, clean["name"], clean["name_key"], clean["traits"], clean["magic_access"],
         clean["ability_rules"], clean["lifespan_years"], clean["size_band"], clean["source"]),
    )
    return code, []


def store_fact(conn, row: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Insert one fact after validation. A repeat of an existing text is not stored twice."""
    clean, errors = validate_fact_row(row, known_codes(conn))
    if clean is None:
        return None, errors
    folded = clean["text"].lower().rstrip(".")
    for existing in conn.execute("SELECT code, text FROM world_facts").fetchall():
        if str(existing["text"]).lower().rstrip(".") == folded:
            return str(existing["code"]), ["duplicate"]
    if conn.execute("SELECT COUNT(*) AS n FROM world_facts").fetchone()["n"] >= FACT_LIMIT:
        return None, ["fact table full"]
    code = _next_code(conn, "world_facts", "F")
    conn.execute(
        "INSERT INTO world_facts (code, kind, title, text, links, tags, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (code, clean["kind"], clean["title"], clean["text"], json.dumps(clean["links"]),
         json.dumps(clean["tags"]), clean["source"]),
    )
    return code, []


# ---------------------------------------------------------------------------
# Deterministic split (start_playthrough)
# ---------------------------------------------------------------------------


def _rolled_numbers(name: str, seed: int | None) -> tuple[int, str]:
    key = race_key(name)
    singular = "-".join(_singular(part) for part in key.split("-"))
    for candidate in (key, singular):
        if candidate in _KNOWN_PEOPLES:
            return _KNOWN_PEOPLES[candidate]
    try:
        from app.rng import rng_for

        rng = rng_for("world_race_numbers", seed=seed, salt=key)
    except Exception:
        import random

        rng = random.Random(key)
    return rng.choice(_LIFESPAN_ROLLS), rng.choice(_SIZE_ROLLS)


def race_magic_from_rules(races: list[str], rules: str, magic_level: str = "") -> tuple[dict[str, str], list[tuple[str, list[str]]]]:
    """Magic access per people from the setup sentences, and which sentence named whom.

    A sentence with a magic word sets access for the peoples it names: a
    negation means none, learn/train words mean learned, rare words rare,
    common words common, otherwise innate. "Only" also closes magic to every
    people the sentence leaves out.
    """
    access: dict[str, str] = {}
    closed_by_only: set[str] = set()
    named_sentences: list[tuple[str, list[str]]] = []
    for sentence in split_sentences(rules):
        named = [race for race in races if _mentions(sentence, race)]
        named_sentences.append((sentence, named))
        if not _MAGIC_WORDS.search(sentence) or not named:
            continue
        only = bool(_ONLY.search(sentence))
        if _NEGATION.search(sentence) and not only:
            value = "none"
        elif _LEARNED.search(sentence):
            value = "learned"
        elif _RARE.search(sentence):
            value = "rare"
        elif _COMMON.search(sentence) and not only:
            value = "common"
        else:
            value = "innate"
        for race in named:
            access[race_key(race)] = value
        if only:
            closed_by_only.update(race_key(race) for race in races if race not in named)
    for key in closed_by_only:
        access.setdefault(key, "none")
    level = str(magic_level or "").lower()
    if re.search(r"\b(no|none|without)\b.*magic|\bno magic\b|^none$", level):
        for race in races:
            access[race_key(race)] = "none"
    return access, named_sentences


def _ability_by_race(races: list[str], rules: str) -> tuple[dict[str, str], list[tuple[str, list[str]]]]:
    """Ability rule text per people. "people: rule" segments and sentences that name a people."""
    by_race: dict[str, list[str]] = {}
    named_sentences: list[tuple[str, list[str]]] = []
    for sentence in split_sentences(rules):
        head, sep, tail = sentence.partition(":")
        target = [race for race in races if sep and race_key(head) and _mentions(head, race)]
        if target and tail.strip():
            for race in target:
                by_race.setdefault(race_key(race), []).append(tail.strip())
            named_sentences.append((sentence, target))
            continue
        named = [race for race in races if _mentions(sentence, race)]
        for race in named:
            by_race.setdefault(race_key(race), []).append(sentence)
        named_sentences.append((sentence, named))
    joined = {key: "; ".join(parts)[:ABILITY_MAX].rstrip("; ") for key, parts in by_race.items()}
    return joined, named_sentences


# Form markers that are not peoples: the "custom" and "random" checkboxes of
# the world_races list (playtest #23).
_RACE_LIST_MARKERS = {"custom", "random", "none", "other", "any", "default"}


def resolve_race_list(conn, options: dict[str, Any]) -> list[str]:
    """The peoples this world uses, never empty and never a form marker.

    playthrough_options.world_races first; a list that holds only "custom" or
    "random" (an unfilled custom box) falls back to the setting template's
    stored choice, then the checked boxes of the saved setup form, then human.
    """
    def _clean_list(value: Any) -> list[str]:
        return [label for label in split_list(value) if race_key(label) not in _RACE_LIST_MARKERS]

    races = _clean_list(options.get("world_races") if isinstance(options, dict) else "")
    if races:
        return races
    try:
        row = conn.execute("SELECT choice FROM setting_templates WHERE key = 'world_races'").fetchone()
        races = _clean_list(row["choice"] if row else "")
    except Exception:
        races = []
    if races:
        return races
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'game_start_form'").fetchone()
        form = json.loads(str(row["value"] or "{}")) if row else {}
        checked = [
            str(control.get("value") or "")
            for control in form.get("controls") or []
            if isinstance(control, dict) and control.get("name") == "world_races" and control.get("checked")
        ]
        custom = [
            str(item.get("value") or "")
            for item in form.get("list_custom") or []
            if isinstance(item, dict) and item.get("name") == "world_races"
        ]
        races = _clean_list(", ".join(checked + custom))
    except Exception:
        races = []
    return races or ["human"]


_PLAYER_RACE_VERBS = r"(?:born|reborn|reincarnated|raised|awakens?|wakes?|is|was|as|being)"


def resolve_player_race(options: dict[str, Any], races: list[str]) -> str:
    """The player's people: a setup value if one is given, a backstory that says
    "born/reborn/... as a <people>", else human when the world has humans,
    else the world's first people."""
    options = options if isinstance(options, dict) else {}
    explicit = _clean(options.get("player_race"))
    if explicit and race_key(explicit) not in _RACE_LIST_MARKERS:
        match = next((race for race in races if race_key(race) == race_key(explicit) or _mentions(explicit, race)), None)
        return match or explicit[:NAME_MAX]
    story = " ".join(_clean(options.get(key)) for key in ("character_backstory", "appearance"))
    if story:
        low = story.lower()
        for race in races:
            for form in sorted(_race_forms(race), key=len, reverse=True):
                tokens = [re.escape(token) for token in re.split(r"[\s-]+", form) if token]
                if not tokens:
                    continue
                pattern = _PLAYER_RACE_VERBS + r"\s+(?:a|an)\s+(?:young\s+|half-?\s*)?" + r"[\s-]?".join(tokens) + r"(?![a-z0-9])"
                if re.search(pattern, low):
                    return race
    if any(race_key(race) == "human" for race in races):
        return next(race for race in races if race_key(race) == "human")
    return races[0] if races else "human"


def _store_player_race(conn, race: str) -> None:
    """Set the player's people once; a stored race is never overwritten here."""
    try:
        conn.execute("UPDATE player SET race = ? WHERE id = 1 AND COALESCE(race, '') = ''", (race[:NAME_MAX],))
    except Exception:
        pass


def player_race(conn) -> str:
    try:
        row = conn.execute("SELECT race FROM player WHERE id = 1").fetchone()
    except Exception:
        return ""
    return _clean(row["race"]) if row else ""


def _race_trait_rng(name: str, seed: int | None):
    try:
        from app.rng import rng_for

        return rng_for("world_race_traits", seed=seed, salt=race_key(name))
    except Exception:
        import random

        return random.Random(f"traits:{race_key(name)}")


def seed_from_options(conn, options: dict[str, Any]) -> dict[str, Any]:
    """Replace this world's fact rows with the deterministic split of its setup strings."""
    ensure_world_fact_tables(conn)
    clear_world_facts(conn)
    if not isinstance(options, dict):
        return {"races": 0, "facts": 0, "rejected": []}
    races = resolve_race_list(conn, options)
    raw_labels = split_list(options.get("world_races"))
    if not raw_labels or any(race_key(label) in _RACE_LIST_MARKERS for label in raw_labels):
        # A marker-only list ("custom" with an empty box) is replaced by the
        # list actually used, so the stored options agree with the table.
        options["world_races"] = ", ".join(races)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
            stored = json.loads(str(row["value"] or "{}")) if row else None
            if isinstance(stored, dict):
                stored["world_races"] = options["world_races"]
                conn.execute(
                    "UPDATE settings SET value = ? WHERE key = 'playthrough_options'",
                    (json.dumps(stored),),
                )
        except Exception:
            pass
    magic_rules = str(options.get("race_magic_rules") or "")
    ability_rules = str(options.get("race_ability_rules") or "")
    magic_level = str(options.get("magic_level") or "")
    access, magic_sentences = race_magic_from_rules(races, magic_rules, magic_level)
    abilities, ability_sentences = _ability_by_race(races, ability_rules)
    try:
        from app.rng import campaign_seed

        seed = campaign_seed(conn)
    except Exception:
        seed = None
    rejected: list[str] = []
    codes: dict[str, str] = {}
    for race in races:
        lifespan, size = _rolled_numbers(race, seed)
        # Engine-rolled traits so no people is empty-traited when no model
        # pass runs; the post-start pass writes this world's own (#23).
        try:
            from app.example_pools import roll_race_traits

            traits = roll_race_traits(race, _race_trait_rng(race, seed), limit=TRAITS_MAX)
        except Exception:
            traits = ""
        code, errors = store_race(
            conn,
            {
                "name": race,
                "traits": traits,
                "magic_access": access.get(race_key(race), "unknown"),
                "ability_rules": abilities.get(race_key(race), ""),
                "lifespan_years": lifespan,
                "size_band": size,
                "source": "split",
            },
        )
        if code:
            codes[race_key(race)] = code
        else:
            rejected.extend(f"race {race}: {error}" for error in errors)

    def _links(named: list[str]) -> list[str]:
        return [codes[race_key(race)] for race in named if race_key(race) in codes]

    facts = 0
    rows: list[dict[str, Any]] = []
    for sentence, named in magic_sentences:
        rows.append({"kind": "magic", "text": sentence, "links": _links(named)})
    for sentence, named in ability_sentences:
        rows.append({"kind": "rule", "text": sentence, "links": _links(named)})
    for sentence in split_sentences(options.get("custom_style")):
        named = [race for race in races if _mentions(sentence, race)]
        rows.append({"kind": _sentence_kind(sentence), "text": sentence, "links": _links(named)})
    # The faction_pressure labels are one setting row, not one near-empty row
    # each; the post-start pass replaces it with named factions (#23).
    pressures = [label for label in split_list(options.get("faction_pressure"), limit=8) if race_key(label) not in _RACE_LIST_MARKERS]
    if pressures:
        rows.append(
            {
                "kind": "faction",
                "title": "Faction pressure",
                "text": f"Pressures between groups here: {'; '.join(pressures)}."[:TEXT_MAX],
                "tag_extra": ["faction"],
            }
        )
    for row in rows:
        text = str(row["text"])
        row.setdefault("title", _title_for(text))
        row["tags"] = _tags_for(text, extra=row.pop("tag_extra", None), title=str(row["title"]))
        row["source"] = "split"
        code, errors = store_fact(conn, row)
        if code and "duplicate" not in errors:
            facts += 1
        elif not code:
            rejected.extend(f"fact '{text[:40]}': {error}" for error in errors)
    player = resolve_player_race(options, races)
    _store_player_race(conn, player)
    return {"races": len(codes), "facts": facts, "rejected": rejected[:12], "player_race": player}


def ensure_seeded(conn) -> bool:
    """A world started before these tables existed gets its split on first read."""
    ensure_world_fact_tables(conn)
    if conn.execute("SELECT 1 FROM world_races LIMIT 1").fetchone():
        return False
    row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
    if not row:
        return False
    try:
        options = json.loads(str(row["value"] or "{}"))
    except json.JSONDecodeError:
        return False
    if not isinstance(options, dict) or not options:
        return False
    seed_from_options(conn, options)
    return True


# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------


def _fact_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    for key in ("links", "tags"):
        try:
            item[key] = json.loads(item.get(key) or "[]")
        except (TypeError, json.JSONDecodeError):
            item[key] = []
    return item


def all_facts(conn) -> dict[str, Any]:
    ensure_world_fact_tables(conn)
    races = [dict(row) for row in conn.execute("SELECT * FROM world_races ORDER BY id").fetchall()]
    facts = [_fact_dict(row) for row in conn.execute("SELECT * FROM world_facts ORDER BY id").fetchall()]
    last_pass: Any = None
    row = conn.execute("SELECT value FROM settings WHERE key = 'world_facts_pass'").fetchone()
    if row:
        try:
            last_pass = json.loads(str(row["value"] or "null"))
        except json.JSONDecodeError:
            last_pass = None
    return {"races": races, "facts": facts, "player_race": player_race(conn), "post_start_pass": last_pass}


def _race_view(row: dict[str, Any], here: list[str], player: bool = False) -> dict[str, Any]:
    view: dict[str, Any] = {"code": row["code"], "name": row["name"], "magic": row["magic_access"]}
    if player:
        # The player is of this people (#23); "here" stays the NPCs present.
        view["player"] = True
    if row.get("traits"):
        view["traits"] = row["traits"]
    if row.get("ability_rules"):
        view["abilities"] = row["ability_rules"]
    if int(row.get("lifespan_years") or 0):
        view["lifespan_years"] = int(row["lifespan_years"])
    if row.get("size_band") and row["size_band"] != "unknown":
        view["size"] = row["size_band"]
    if here:
        view["here"] = here[:6]
    return view


def _words(text: str) -> set[str]:
    return {
        _singular(word)
        for word in re.findall(r"[a-z][a-z-]{3,}", str(text or "").lower())
        if word not in _STOPWORDS
    }


def relevant_facts(
    conn,
    *,
    present: list[dict[str, Any]],
    text: str = "",
    location_name: str = "",
    quest_text: str = "",
    budget_chars: int = RELEVANT_BUDGET_CHARS,
) -> dict[str, list[dict[str, Any]]]:
    """A budgeted handful of rows for one turn.

    ``present`` is the people in the scene, each ``{"name", "race"}``; the
    player's entry carries ``"player": True``. Their races come first, then
    races the turn text names, then facts linked to those races, then facts
    whose words the turn shares, then one tone fact.
    """
    races = _race_by_key(conn)
    if not races:
        return {}
    focus = " ".join([text, location_name, quest_text])
    chosen: list[tuple[dict[str, Any], list[str]]] = []
    here_by_key: dict[str, list[str]] = {}
    player_key = ""
    for person in present:
        key = race_key(person.get("race") or "")
        if not key:
            continue
        match = races.get(key) or next(
            (row for row in races.values() if _mentions(str(person.get("race") or ""), row["name"])), None
        )
        if not match:
            continue
        names = here_by_key.setdefault(match["name_key"], [])
        if person.get("player"):
            player_key = match["name_key"]
        else:
            names.append(str(person.get("name") or ""))
    for key, names in here_by_key.items():
        chosen.append((races[key], [name for name in names if name]))
    for row in races.values():
        if row["name_key"] not in here_by_key and _mentions(text, row["name"]):
            chosen.append((row, []))
    race_codes = {row["code"] for row, _ in chosen}

    facts = [_fact_dict(row) for row in conn.execute("SELECT * FROM world_facts ORDER BY id").fetchall()]
    focus_words = _words(focus)
    magic_turn = bool(_MAGIC_WORDS.search(text))
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, fact in enumerate(facts):
        score = 0
        if race_codes & set(fact.get("links") or []):
            score += 6
        overlap = focus_words & (_words(fact.get("text") or "") | set(fact.get("tags") or []) | _words(fact.get("title") or ""))
        score += 2 * len(overlap)
        if magic_turn and fact.get("kind") == "magic":
            score += 4
        if score:
            scored.append((score, -index, fact))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    picked = [fact for _, _, fact in scored[:RELEVANT_FACT_LIMIT]]
    if not any(fact.get("kind") == "tone" for fact in picked):
        tone = next((fact for fact in facts if fact.get("kind") == "tone"), None)
        if tone:
            picked.append(tone)

    out: dict[str, list[dict[str, Any]]] = {"races": [], "facts": []}
    used = 0
    for row, here in chosen:
        view = _race_view(row, here, player=row["name_key"] == player_key)
        size = len(json.dumps(view, separators=(",", ":")))
        if used + size > budget_chars:
            break
        out["races"].append(view)
        used += size
    for fact in picked:
        view = {"code": fact["code"], "kind": fact["kind"], "title": fact["title"], "text": fact["text"]}
        size = len(json.dumps(view, separators=(",", ":")))
        if used + size > budget_chars:
            continue
        out["facts"].append(view)
        used += size
    return {key: value for key, value in out.items() if value}


def relevant_facts_for_state(state: dict[str, Any], player_input: str) -> dict[str, list[dict[str, Any]]]:
    """The turn's rows, read from the state the prompt context is built from."""
    from app.db import connect

    current = state.get("current_location") if isinstance(state.get("current_location"), dict) else {}
    code = str(current.get("code") or "")
    present: list[dict[str, Any]] = []
    for location in state.get("locations") or []:
        if not isinstance(location, dict) or str(location.get("code") or "") != code:
            continue
        for npc in location.get("npcs") or []:
            if isinstance(npc, dict):
                present.append({"name": npc.get("name") or "", "race": npc.get("race") or ""})
    player = state.get("player") if isinstance(state.get("player"), dict) else {}
    if player.get("race"):
        present.append({"name": player.get("name") or "", "race": player.get("race"), "player": True})
    quests = " ".join(
        f"{quest.get('title') or ''} {quest.get('current_objective') or ''}"
        for quest in state.get("active_quests") or []
        if isinstance(quest, dict)
    )
    with connect() as conn:
        ensure_seeded(conn)
        if not player.get("race"):
            # A world started before the player had a race column: store
            # the resolved people once, so the player is of somebody (#23).
            race = player_race(conn)
            if not race:
                try:
                    row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
                    options = json.loads(str(row["value"] or "{}")) if row else {}
                except (TypeError, json.JSONDecodeError):
                    options = {}
                names = [str(row["name"]) for row in conn.execute("SELECT name FROM world_races ORDER BY id").fetchall()]
                if names:
                    race = resolve_player_race(options if isinstance(options, dict) else {}, names)
                    _store_player_race(conn, race)
            if race:
                present.append({"name": player.get("name") or "", "race": race, "player": True})
        return relevant_facts(
            conn,
            present=present,
            text=str(player_input or ""),
            location_name=str(current.get("name") or ""),
            quest_text=quests,
        )


# ---------------------------------------------------------------------------
# Post-start, pre-turn-1 passes
# ---------------------------------------------------------------------------

PostStartPass = Callable[[dict[str, Any]], dict[str, Any]]
_POST_START_PASSES: list[tuple[str, PostStartPass]] = []


def register_post_start_pass(name: str, fn: PostStartPass) -> None:
    """Add a pass to the phase between start_playthrough and the opening turn.

    A pass gets the stored playthrough_options, makes at most one small
    model call, validates every row in the engine and returns a short report.
    It opens its own short connections: one to read, one to write after the
    model answers, so no write lock is held while the model runs. A failing
    pass never blocks the opening.
    """
    for index, (existing, _) in enumerate(_POST_START_PASSES):
        if existing == name:
            _POST_START_PASSES[index] = (name, fn)
            return
    _POST_START_PASSES.append((name, fn))


def post_start_model_allowed() -> bool:
    """AI_RPG_POST_START_MODEL=off skips every model pass; the split alone stands."""
    flag = os.getenv("AI_RPG_POST_START_MODEL", "auto").strip().lower()
    if flag in {"0", "false", "off", "no", "skip"}:
        return False
    try:
        from app.llm import _normalize_provider, get_model_config, resolve_api_key

        config = get_model_config()
        provider = _normalize_provider(str(config.get("provider") or ""))
        if provider == "mle":
            from app.mle import resolve_model_path

            return resolve_model_path(str(config.get("mle_model") or "")) is not None
        if provider == "openai":
            return bool(resolve_api_key(config))
        return True
    except Exception:
        return False


def parse_lines(content: str, prefixes: tuple[str, ...]) -> list[tuple[str, list[str]]]:
    """Closed line format: PREFIX|field|field... One record per line, others ignored."""
    records: list[tuple[str, list[str]]] = []
    for line in str(content or "").splitlines():
        line = line.strip().strip("`").strip()
        if "|" not in line:
            continue
        head, *fields = [part.strip() for part in line.split("|")]
        head = head.upper().lstrip("-* ")
        if head in prefixes:
            records.append((head, fields))
    return records


def run_post_start_passes() -> dict[str, Any]:
    from app.db import connect

    report: dict[str, Any] = {"model_allowed": post_start_model_allowed(), "passes": {}}
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
    try:
        options = json.loads(str(row["value"] or "{}")) if row else {}
    except json.JSONDecodeError:
        options = {}
    if not isinstance(options, dict):
        options = {}
    for name, fn in list(_POST_START_PASSES):
        if not report["model_allowed"]:
            report["passes"][name] = {"called": False, "reason": "model pass off or no model"}
            continue
        try:
            result = fn(options)
        except Exception as exc:  # a pass never blocks the opening turn
            result = {"called": True, "error": str(exc)[:200]}
        report["passes"][name] = result
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('world_facts_pass', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(report, ensure_ascii=True),),
        )
    return report


# The pass enriches (playtest #23). Asked to "write facts the table does not
# hold yet" beside the full setup text, the 8B restated the setup sentences
# and every one was refused. Now the stored rows are shown as already known,
# each call asks for a few kinds of new lore drawn from app/example_pools.py,
# and each race is asked for traits and ability rules of its own.
_REFINE_SYSTEM = (
    "You enrich one RPG world's tables with what its setup implies but does not say. Answer with lines only, "
    "no prose, no JSON, no numbering. Two line shapes are allowed:\n"
    "RACE|<race name exactly as given>|<magic access>|<lifespan in years, a whole number>|<size>|<traits>|<gifts and limits beyond magic>\n"
    "FACT|<kind>|<title>|<the fact>|<race codes it is about, separated by spaces, or empty>|<up to 4 nouns it is about, separated by spaces>\n"
    "magic access is one of: " + ", ".join(MAGIC_ACCESS) + ". "
    "size is one of: " + ", ".join(SIZE_BANDS) + ". "
    "kind is one of: " + ", ".join(FACT_KINDS) + ".\n"
    "Write one RACE line for every race in races, and no other peoples. traits: two to four short phrases on how "
    "this people looks, lives and behaves in this world, at most 120 characters. gifts and limits beyond magic (stored as the race's ability rules): one or two gifts or "
    "limits this people has in play beyond its magic access (senses, body, endurance, craft, lore), at most 160 "
    "characters; magic access is its own field, so do not repeat it here. When a race has magic_fixed, copy its magic access as shown: "
    "the setup decided it. Ability rules never give spells to a race whose magic access is none. When setup_rule is "
    "shown for a race, its ability rules keep that rule and may add to it.\n"
    "Then write one FACT line for each item in write_facts_about, using the kind before the colon. already_known is "
    "what the world's tables hold: do not repeat or reword any of it; each fact adds something new that fits it. "
    "A fact is one or two plain sentences, at most 200 characters. The title is a short noun phrase naming the "
    "subject, two to five words. Factions grow out of setup.faction_pressure and get a proper name of their own. "
    "Links may only use race codes from races."
)


def _fixed_magic(races: list[dict[str, Any]], options: dict[str, Any]) -> dict[str, str]:
    """Magic access the setup rules decide, by race key. The model may not change these."""
    names = [str(row["name"]) for row in races]
    access, _ = race_magic_from_rules(
        names, str(options.get("race_magic_rules") or ""), str(options.get("magic_level") or "")
    )
    return access


def _fact_asks(options: dict[str, Any], rng=None) -> list[str]:
    """Three to five kinds of new lore for this call, drawn fresh from the pool."""
    import random

    from app.example_pools import draw, world_context

    rng = rng or random.Random()
    context = world_context(options)
    asks = draw("world_fact_ask", context, rng.randint(3, 5), rng)
    pressures = [label for label in split_list(options.get("faction_pressure"), limit=8) if race_key(label) not in _RACE_LIST_MARKERS]
    if pressures and not any(ask.startswith("faction:") for ask in asks):
        factions = [ask for ask in draw("world_fact_ask", context, 40, rng) if ask.startswith("faction:")]
        if factions:
            asks = [*asks[:-1], factions[0]] if len(asks) >= 3 else [*asks, factions[0]]
    return asks


def build_refine_request(conn, options: dict[str, Any], rng=None) -> tuple[str, dict[str, Any]]:
    """The user message for the pass, and what the engine fixed for the answer."""
    races = [dict(row) for row in conn.execute("SELECT * FROM world_races ORDER BY id").fetchall()]
    facts = [_fact_dict(row) for row in conn.execute("SELECT * FROM world_facts ORDER BY id").fetchall()]
    fixed = _fixed_magic(races, options)
    abilities, _ = _ability_by_race([str(row["name"]) for row in races], str(options.get("race_ability_rules") or ""))
    asks = _fact_asks(options, rng)
    race_rows = []
    for row in races:
        key = str(row["name_key"])
        item: dict[str, Any] = {
            "code": row["code"],
            "name": row["name"],
            "magic_access": row["magic_access"],
            "lifespan_years": row["lifespan_years"],
            "size": row["size_band"],
        }
        if key in fixed:
            item["magic_fixed"] = True
        if abilities.get(key):
            item["setup_rule"] = abilities[key]
        race_rows.append(item)
    user = json.dumps(
        {
            "setup": {
                "world_style": _clean(options.get("world_style"))[:120],
                "tone": _clean(options.get("tone"))[:100],
                "magic_level": _clean(options.get("magic_level"))[:80],
                "tech_level": _clean(options.get("tech_level"))[:80],
                "race_magic_rarity": _clean(options.get("race_magic_rarity"))[:80],
                "race_magic_rules": _clean(options.get("race_magic_rules"))[:1200],
                "race_ability_rules": _clean(options.get("race_ability_rules"))[:1200],
                "faction_pressure": _clean(options.get("faction_pressure"))[:200],
            },
            "races": race_rows,
            "already_known": [f"{fact['code']} ({fact['kind']}): {fact['text']}" for fact in facts],
            "write_facts_about": asks,
        },
        ensure_ascii=True,
    )
    return user, {"fixed_magic": fixed, "asked": asks}


def refine_from_model(options: dict[str, Any]) -> dict[str, Any]:
    """One model call that enriches the race rows and adds new fact rows; the engine validates each line."""
    from app.db import connect
    from app.llm import _chat_content

    with connect() as conn:
        ensure_seeded(conn)
        if not conn.execute("SELECT 1 FROM world_races LIMIT 1").fetchone():
            return {"called": False, "reason": "no races"}
        user, plan = build_refine_request(conn, options)
    # The first call after start may load the local model cold; 60s timed out
    # on Qwen3 8B with the reply two-thirds written.
    content = _chat_content(_REFINE_SYSTEM, user, timeout=180, temperature=0.4, max_tokens=1300, response_format="text")
    with connect() as conn:
        report = apply_refinement(conn, content, fixed_magic=plan["fixed_magic"])
    report["asked"] = plan["asked"]
    return report


def _filled(value: str) -> str:
    """A field the model left as a placeholder ("none", "n/a", "-") counts as not written."""
    text = _clean(value)
    return "" if race_key(text).strip(".") in {"", "none", "n/a", "na", "nil", "nothing", "empty", "-", "unknown"} else text


def _restates(conn, text: str) -> bool:
    """True when most of a new fact's words already sit in one stored fact."""
    words = _words(text)
    if not words:
        return False
    for row in conn.execute("SELECT title, text FROM world_facts").fetchall():
        stored = _words(f"{row['title']} {row['text']}")
        if stored and len(words & stored) / len(words) >= 0.6:
            return True
    return False


def retitle_split_rows(conn) -> list[str]:
    """Engine-titled rows get the current title rule; a save started before it keeps no first-words title."""
    changed: list[str] = []
    for row in conn.execute("SELECT code, title, text FROM world_facts WHERE source = 'split'").fetchall():
        title = str(row["title"] or "")
        if title == "Faction pressure":
            continue
        fresh = _title_for(str(row["text"] or ""))
        if fresh and fresh != title:
            conn.execute("UPDATE world_facts SET title = ? WHERE code = ?", (fresh, row["code"]))
            changed.append(f"{row['code']}: {title[:30]} -> {fresh}")
    return changed


def apply_refinement(conn, content: str, fixed_magic: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate and store the model's lines. Unknown race codes, bad enums and long text are refused.

    ``fixed_magic`` is the magic access the setup rules decided, by race key;
    the model's value for those peoples is replaced by the engine's. Without it
    the stored playthrough_options decide.
    """
    by_code = {str(row["code"]).upper(): dict(row) for row in conn.execute("SELECT * FROM world_races").fetchall()}
    by_key = {str(row["name_key"]): row for row in by_code.values()}
    if fixed_magic is None:
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
            options = json.loads(str(row["value"] or "{}")) if row else {}
        except (TypeError, json.JSONDecodeError):
            options = {}
        fixed_magic = _fixed_magic(list(by_code.values()), options) if isinstance(options, dict) else {}
    accepted = {"races": 0, "facts": 0}
    rejected: list[str] = []
    adjusted: list[str] = []
    new_factions = 0
    for head, fields in parse_lines(content, ("RACE", "FACT")):
        if head == "RACE":
            fields = (fields + [""] * 6)[:6]
            # The name, as asked; a code is accepted too. Qwen3 8B answered
            # with invented one-letter codes when it was asked for codes.
            current = by_key.get(race_key(fields[0])) or by_code.get(fields[0].upper())
            if current is None:
                current = next((row for row in by_code.values() if _mentions(fields[0], row["name"])), None)
            if current is None:
                rejected.append(f"RACE {fields[0][:20]}: not in the race table")
                continue
            code = str(current["code"])
            try:
                lifespan = int(re.sub(r"[^\d]", "", fields[2]) or current["lifespan_years"])
            except ValueError:
                lifespan = int(current["lifespan_years"])
            magic = fields[1] or current["magic_access"]
            decided = fixed_magic.get(str(current["name_key"]))
            # A valid but different value is corrected; an invalid one is still refused below.
            said = _enum(magic, MAGIC_ACCESS)
            if decided and said is not None and said != decided:
                adjusted.append(f"RACE {code}: magic {magic[:12]} -> {decided} (setup rule)")
                magic = decided
            _, errors = store_race(
                conn,
                {
                    "name": current["name"],
                    "magic_access": magic,
                    "lifespan_years": lifespan,
                    "size_band": fields[3] or current["size_band"],
                    "traits": _filled(fields[4]) or current["traits"],
                    "ability_rules": _filled(fields[5]) or current["ability_rules"],
                    "source": "model",
                },
            )
            if errors:
                rejected.append(f"RACE {code}: {'; '.join(errors)}")
            else:
                accepted["races"] += 1
        else:
            fields = (fields + [""] * 5)[:5]
            # Qwen3 8B wrote the link codes at the end of the fact text
            # ("...salted fish. R1 R2 R3 R4 R5 R6"): they are links, not text.
            trailing = re.search(r"(?:\s+\b[RF]\d{1,3}\b[,;]?)+\s*$", fields[2])
            if trailing:
                fields[3] = f"{fields[3]} {trailing.group(0)}"
                fields[2] = fields[2][: trailing.start()].rstrip()
            names = {str(row["name_key"]): str(row["code"]) for row in by_code.values()}
            links = []
            for token in fields[3].replace(",", " ").replace(";", " ").split():
                links.append(names.get(race_key(token), token))
            # A race link stands only when the fact names that people; the
            # 8B linked a rule about two peoples to all six.
            said = f"{fields[1]} {fields[2]}"
            links = [
                link for link in links
                if link.upper() not in by_code or _mentions(said, by_code[link.upper()]["name"])
            ]
            links += [
                str(row["code"]) for row in by_code.values()
                if _mentions(said, row["name"]) and str(row["code"]) not in links
            ]
            if _restates(conn, said):
                rejected.append(f"FACT {fields[1][:30]}: restates a stored fact")
                continue
            title = _clean(fields[1]).strip(" .")
            if not title or len(title) > TITLE_MAX:
                title = _title_for(fields[2])
            stored, errors = store_fact(
                conn,
                {
                    "kind": fields[0],
                    "title": title,
                    "text": fields[2],
                    "links": links,
                    "tags": _tags_for(fields[2], extra=fields[4].replace(",", " ").split(), title=title),
                    "source": "model",
                },
            )
            if stored and not errors:
                accepted["facts"] += 1
                if _enum(fields[0], FACT_KINDS) == "faction":
                    new_factions += 1
            elif errors and errors != ["duplicate"]:
                rejected.append(f"FACT {fields[1][:30]}: {'; '.join(errors)}")
    dropped: list[str] = []
    if new_factions:
        # Named factions replace the split's one-line pressure summary.
        for row in conn.execute("SELECT code FROM world_facts WHERE kind = 'faction' AND source = 'split'").fetchall():
            dropped.append(str(row["code"]))
        if dropped:
            conn.execute(
                f"DELETE FROM world_facts WHERE code IN ({', '.join('?' for _ in dropped)})", dropped
            )
    retitled = retitle_split_rows(conn)
    report: dict[str, Any] = {"called": True, "accepted": accepted, "rejected": rejected[:12]}
    if retitled:
        report["retitled"] = retitled[:12]
    if adjusted:
        report["adjusted"] = adjusted[:12]
    if dropped:
        report["replaced_split_factions"] = dropped
    return report


register_post_start_pass("world_facts", refine_from_model)

# Custom proficiencies (playtest #1) register the second pass on import, so
# it runs after the world facts it may add rule rows beside.
import app.proficiencies  # noqa: E402,F401
