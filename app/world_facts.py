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


def _title_for(text: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    title = " ".join(words[:6])
    return title[:TITLE_MAX] or text[:TITLE_MAX]


def _tags_for(text: str, extra: list[str] | None = None) -> list[str]:
    tags: list[str] = []
    for word in [*(extra or []), *re.findall(r"[a-z][a-z-]{3,}", text.lower())]:
        word = word.strip("-")
        if not word or word in _STOPWORDS or word in tags:
            continue
        tags.append(word[:24])
        if len(tags) >= TAG_MAX:
            break
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


def seed_from_options(conn, options: dict[str, Any]) -> dict[str, Any]:
    """Replace this world's fact rows with the deterministic split of its setup strings."""
    ensure_world_fact_tables(conn)
    clear_world_facts(conn)
    if not isinstance(options, dict):
        return {"races": 0, "facts": 0, "rejected": []}
    races = split_list(options.get("world_races") or "human")
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
        code, errors = store_race(
            conn,
            {
                "name": race,
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
    for label in split_list(options.get("faction_pressure"), limit=8):
        rows.append({"kind": "faction", "title": label, "text": f"Faction pressure in this world: {label}."})
    for row in rows:
        text = str(row["text"])
        row.setdefault("title", _title_for(text))
        row["tags"] = _tags_for(text)
        row["source"] = "split"
        code, errors = store_fact(conn, row)
        if code and "duplicate" not in errors:
            facts += 1
        elif not code:
            rejected.extend(f"fact '{text[:40]}': {error}" for error in errors)
    return {"races": len(codes), "facts": facts, "rejected": rejected[:12]}


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
    return {"races": races, "facts": facts, "post_start_pass": last_pass}


def _race_view(row: dict[str, Any], here: list[str]) -> dict[str, Any]:
    view: dict[str, Any] = {"code": row["code"], "name": row["name"], "magic": row["magic_access"]}
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

    ``present`` is the people in the scene, each ``{"name", "race"}``. Their
    races come first, then races the turn text names, then facts linked to
    those races, then facts whose words the turn shares, then one tone fact.
    """
    races = _race_by_key(conn)
    if not races:
        return {}
    focus = " ".join([text, location_name, quest_text])
    chosen: list[tuple[dict[str, Any], list[str]]] = []
    here_by_key: dict[str, list[str]] = {}
    for person in present:
        key = race_key(person.get("race") or "")
        if not key:
            continue
        match = races.get(key) or next(
            (row for row in races.values() if _mentions(str(person.get("race") or ""), row["name"])), None
        )
        if match:
            here_by_key.setdefault(match["name_key"], []).append(str(person.get("name") or ""))
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
        view = _race_view(row, here)
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
        present.append({"name": player.get("name") or "", "race": player.get("race")})
    quests = " ".join(
        f"{quest.get('title') or ''} {quest.get('current_objective') or ''}"
        for quest in state.get("active_quests") or []
        if isinstance(quest, dict)
    )
    with connect() as conn:
        ensure_seeded(conn)
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


_REFINE_SYSTEM = (
    "You turn one RPG world's setup text into short table rows. Answer with lines only, "
    "no prose, no JSON, no numbering. Two line shapes are allowed:\n"
    "RACE|<race name exactly as the table writes it>|<magic access>|<lifespan in years, a whole number>|<size>|<traits, at most 120 characters>|<ability rules, at most 160 characters>\n"
    "FACT|<kind>|<title, at most 6 words>|<one fact, at most 200 characters>|<linked codes separated by spaces, or empty>|<up to 4 one-word tags separated by spaces>\n"
    "magic access is one of: " + ", ".join(MAGIC_ACCESS) + ". "
    "size is one of: " + ", ".join(SIZE_BANDS) + ". "
    "kind is one of: " + ", ".join(FACT_KINDS) + ". "
    "Write one RACE line for each race in the table. Do not add peoples the table does not list. "
    "Each RACE line must agree with the setup text: when the text says a people has no magic, its access is none. "
    "Write FACT lines for customs, factions, history, places and rules the setup text states or plainly implies, "
    "each one fact, not a summary of the whole text. The fact table already holds every setup sentence: "
    "write only facts it does not hold yet, and write none when the setup text has nothing more to give. "
    "Links may only use codes shown in the input. Do not invent names the setup text does not give."
)


def refine_from_model(options: dict[str, Any]) -> dict[str, Any]:
    """One model call that adjusts the race rows and adds fact rows; the engine validates each line."""
    from app.db import connect
    from app.llm import _chat_content

    with connect() as conn:
        ensure_seeded(conn)
        races = [dict(row) for row in conn.execute("SELECT * FROM world_races ORDER BY id").fetchall()]
        facts = [_fact_dict(row) for row in conn.execute("SELECT * FROM world_facts ORDER BY id").fetchall()]
    if not races:
        return {"called": False, "reason": "no races"}
    user = json.dumps(
        {
            "setup": {
                "world_style": _clean(options.get("world_style"))[:120],
                "tone": _clean(options.get("tone"))[:100],
                "magic_level": _clean(options.get("magic_level"))[:80],
                "tech_level": _clean(options.get("tech_level"))[:80],
                "race_magic_rarity": _clean(options.get("race_magic_rarity"))[:80],
                "custom_style": _clean(options.get("custom_style"))[:800],
                "race_magic_rules": _clean(options.get("race_magic_rules"))[:1200],
                "race_ability_rules": _clean(options.get("race_ability_rules"))[:1200],
                "faction_pressure": _clean(options.get("faction_pressure"))[:200],
            },
            "race_table": [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "magic_access": row["magic_access"],
                    "lifespan_years": row["lifespan_years"],
                    "size": row["size_band"],
                    "traits": row["traits"],
                    "ability_rules": row["ability_rules"],
                }
                for row in races
            ],
            "fact_table": [{"code": fact["code"], "kind": fact["kind"], "text": fact["text"]} for fact in facts],
        },
        ensure_ascii=True,
    )
    # The first call after start may load the local model cold; 60s timed out
    # on Qwen3 8B with the reply two-thirds written.
    content = _chat_content(_REFINE_SYSTEM, user, timeout=180, temperature=0.3, max_tokens=900, response_format="text")
    with connect() as conn:
        return apply_refinement(conn, content)


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


def apply_refinement(conn, content: str) -> dict[str, Any]:
    """Validate and store the model's lines. Unknown race codes, bad enums and long text are refused."""
    by_code = {str(row["code"]).upper(): dict(row) for row in conn.execute("SELECT * FROM world_races").fetchall()}
    by_key = {str(row["name_key"]): row for row in by_code.values()}
    accepted = {"races": 0, "facts": 0}
    rejected: list[str] = []
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
            _, errors = store_race(
                conn,
                {
                    "name": current["name"],
                    "magic_access": fields[1] or current["magic_access"],
                    "lifespan_years": lifespan,
                    "size_band": fields[3] or current["size_band"],
                    "traits": fields[4] or current["traits"],
                    "ability_rules": fields[5] or current["ability_rules"],
                    "source": "model",
                },
            )
            if errors:
                rejected.append(f"RACE {code}: {'; '.join(errors)}")
            else:
                accepted["races"] += 1
        else:
            fields = (fields + [""] * 5)[:5]
            names = {str(row["name_key"]): str(row["code"]) for row in by_code.values()}
            links = []
            for token in fields[3].replace(",", " ").split():
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
            stored, errors = store_fact(
                conn,
                {
                    "kind": fields[0],
                    "title": fields[1],
                    "text": fields[2],
                    "links": links,
                    "tags": fields[4].replace(",", " ").split(),
                    "source": "model",
                },
            )
            if stored and not errors:
                accepted["facts"] += 1
            elif errors and errors != ["duplicate"]:
                rejected.append(f"FACT {fields[1][:30]}: {'; '.join(errors)}")
    return {"called": True, "accepted": accepted, "rejected": rejected[:12]}


register_post_start_pass("world_facts", refine_from_model)
