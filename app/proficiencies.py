"""
Custom proficiencies as engine rows (playtest #1).

The setup box "Custom Proficiencies" promises comma-separated proficiencies and
training-rule phrases: a seed skill name, how progress is tracked, hard limits.
The text used to ride whole in playthrough_options, and a randomized fill of
poetic slogans reached the DM as if it were rules nobody could record.

After start, before the opening turn, one post-start pass (the registry in
app/world_facts.py) settles that text into rows:

  player_proficiencies  one row per named proficiency: code (P1..), name,
                        start rank (a label from this world's rank_scale),
                        how progress is tracked, the hard limit
  world_facts           training rules, kind "rule", tagged "proficiency"

The model proposes lines in a closed format; the engine validates each one:
the name is a short noun phrase (no articles, pronouns or prepositions, so a
sentence or motto cannot pass as a name), the rank is on the scale and no
higher than this start allows, tracking and limit are present, names are
unique. Each accepted proficiency is mirrored into player_skills so the skill
card, checks and growth see it, and playthrough_options.custom_skills becomes
an engine-written summary of the rows (the setup text stays under
custom_skills_setup).

Playtest #22 (game 2) found three holes the first pass left open:

  * Names: a verb-led phrase ("master the dance of shadows") is not a name.
    ``leading_verb`` finds the verb structurally (a short lexicon for the first
    word, ``-ize``/``-ify`` endings, a verb before a determiner); ``noun_form``
    turns "master/learn/study ... X" into X when X is a noun phrase; anything
    else is re-asked once (``rename_with_model``) and dropped if it still
    names no skill. The setup roll and the post-start pass both do this.
  * Ranks: the stored session_theme said "ordinary" for an idea that asked to
    "start ordinary with one weak compounding seed power", so the cap was the
    lower half and C/C/D went through. ``start_profile`` floors the theme with
    the idea's own words (``floor_power_fantasy``); a weak, seed or compounding
    start keeps every proficiency at the bottom rank, and the seed may stand
    one step up only when the idea names a higher start rank for it.
  * Rule titles: "Crafting Mastery" over a rule about Unbreakable Bonds. The
    engine keeps a model title only when its words are in the rule's text and
    otherwise derives one from the text (``rule_title``).
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.world_facts import (
    TEXT_MAX,
    TITLE_MAX,
    _clean,
    _fact_dict,
    _next_code,
    _restates,
    _tags_for,
    _words,
    parse_lines,
    race_key,
    register_post_start_pass,
    store_fact,
)

NAME_MAX = 40
NAME_WORDS_MAX = 4
TRACKING_MAX = 100
LIMIT_MAX = 100
SKILL_LIMIT = 6
RULE_LIMIT = 6
SUMMARY_MAX = 1200
DEFAULT_RANKS = ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]

# Grammar words a proficiency name never needs. A name is a noun phrase; a
# phrase carrying an article, pronoun, preposition or auxiliary is a sentence
# or a motto. "of" and "and" may join two nouns inside a name.
_GRAMMAR_WORDS = frozenset({
    "a", "an", "the", "my", "your", "his", "her", "its", "our", "their", "this", "that",
    "these", "those", "i", "me", "you", "he", "she", "it", "we", "they", "them", "us",
    "to", "through", "by", "with", "from", "into", "onto", "upon", "for", "in", "on",
    "at", "as", "over", "under", "until", "when", "while", "if", "than", "then",
    "is", "are", "be", "was", "were", "will", "shall", "must", "can", "may", "should",
    "not", "no", "never", "always", "every", "each", "all", "only",
})
_JOINERS = frozenset({"of", "and"})
_NAME_SHAPE = re.compile(r"^[A-Za-z][A-Za-z'\-]*$")


def ensure_proficiency_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS player_proficiencies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    NOT NULL UNIQUE,
            name        TEXT    NOT NULL,
            name_key    TEXT    NOT NULL UNIQUE,
            start_rank  TEXT    NOT NULL,
            rank_index  INTEGER NOT NULL DEFAULT 0,
            tracking    TEXT    NOT NULL DEFAULT '',
            hard_limit  TEXT    NOT NULL DEFAULT '',
            source      TEXT    NOT NULL DEFAULT 'model',
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def clear_proficiencies(conn) -> None:
    ensure_proficiency_table(conn)
    conn.execute("DELETE FROM player_proficiencies")


def rank_labels(options: dict[str, Any]) -> list[str]:
    """The world's rank labels as the setup spells them (a word scale keeps its case)."""
    raw = str((options or {}).get("rank_scale") or "")
    labels = [part.strip() for part in re.split(r"[,/|;]", raw) if part.strip()]
    return labels or list(DEFAULT_RANKS)


def idea_text(options: dict[str, Any] | None, conn=None) -> str:
    """The player's Randomize idea: on the options, else in the stored start form."""
    opts = options if isinstance(options, dict) else {}
    for key in ("_randomize_idea", "randomize_idea"):
        if _clean(opts.get(key)):
            return _clean(opts.get(key))[:400]
    form = opts.get("setup_form") if isinstance(opts.get("setup_form"), dict) else {}
    if _clean(form.get("randomize_idea")):
        return _clean(form.get("randomize_idea"))[:400]
    theme = opts.get("session_theme") if isinstance(opts.get("session_theme"), dict) else {}
    if _clean(theme.get("raw_idea")):
        return _clean(theme.get("raw_idea"))[:400]
    if conn is not None:
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = 'game_start_form'").fetchone()
            stored = json.loads(str(row["value"] or "{}")) if row else {}
            if isinstance(stored, dict):
                return _clean(stored.get("randomize_idea"))[:400]
        except Exception:
            return ""
    return ""


def start_profile(
    options: dict[str, Any] | None,
    idea: str = "",
    power_fantasy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """start_power and growth for this start, floored by the idea's own words."""
    opts = options if isinstance(options, dict) else {}
    if not isinstance(power_fantasy, dict):
        theme = opts.get("session_theme") if isinstance(opts.get("session_theme"), dict) else {}
        power_fantasy = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}
    pf = dict(power_fantasy or {})
    if idea:
        try:
            from app.setup_composer import floor_power_fantasy

            pf = floor_power_fantasy(pf, idea)
        except Exception:
            pass
    start = str(pf.get("start_power") or "ordinary").lower()
    growth = str(pf.get("growth") or "steady").lower()
    return {
        "start_power": start,
        "growth": growth,
        # A strong start that also compounds is not a climb from the bottom.
        "seed_climb": start in ("near_useless", "weak") or (growth == "compounding" and start != "strong"),
    }


def start_rank_cap(
    options: dict[str, Any],
    labels: list[str],
    idea: str = "",
    power_fantasy: dict[str, Any] | None = None,
) -> int:
    """Highest rank index a starting proficiency may hold.

    A weak, seed or compounding start keeps every proficiency at the bottom
    rank (playtest #22: an "OP progression, start ordinary with one weak
    seed" idea got C/C/D), an ordinary one the lower half, a strong start the
    whole scale.
    """
    profile = start_profile(options, idea, power_fantasy)
    last = max(0, len(labels) - 1)
    if profile["seed_climb"]:
        return 0
    if profile["start_power"] == "strong":
        return last
    return max(0, (len(labels) - 1) // 2)


_SEED_RANK = re.compile(
    r"\bseed\b[^.;:]{0,60}?\b(?:at\s+|from\s+)?rank\s+([A-Za-z]{1,12})\b"
    r"|\brank\s+([A-Za-z]{1,12})\s+seed\b"
    r"|\bstart(?:s|ing)?\s+(?:at\s+)?rank\s+([A-Za-z]{1,12})\b",
    re.I,
)


def seed_rank_cap(
    options: dict[str, Any],
    labels: list[str],
    idea: str = "",
    power_fantasy: dict[str, Any] | None = None,
) -> int:
    """The seed proficiency's ceiling: the start's cap, one step up only when the idea names it."""
    cap = start_rank_cap(options, labels, idea, power_fantasy)
    if not start_profile(options, idea, power_fantasy)["seed_climb"]:
        return cap
    folded = [label.upper() for label in labels]
    for match in _SEED_RANK.finditer(str(idea or "")):
        label = next((group for group in match.groups() if group), "").upper()
        if label in folded:
            return min(cap + 1, folded.index(label), max(0, len(labels) - 1))
    return cap


def seed_names(options: dict[str, Any] | None) -> list[str]:
    """Names that mark the seed: the ability cards and a "seed skill: X" phrase."""
    opts = options if isinstance(options, dict) else {}
    names = [
        _clean(card.get("name"))
        for card in opts.get("special_abilities") or []
        if isinstance(card, dict) and _clean(card.get("name"))
    ]
    for key in ("custom_skills_setup", "custom_skills"):
        for match in re.finditer(r"seed(?:\s+skill)?\s*:\s*([^,;()]+)", str(opts.get(key) or ""), re.I):
            names.append(_clean(match.group(1)))
    return [name for name in names if name]


def is_seed_name(name: str, seeds: list[str]) -> bool:
    words = {word for word in re.findall(r"[a-z]{4,}", name.lower())}
    for seed in seeds:
        if race_key(seed) == race_key(name):
            return True
        if words & {word for word in re.findall(r"[a-z]{4,}", seed.lower())}:
            return True
    return False


# ---------------------------------------------------------------------------
# Verb-led names (playtest #22)
# ---------------------------------------------------------------------------
# A proficiency name is a noun phrase. The verb test is structural: a short
# lexicon for the first word, verb endings, and a verb's position before a
# determiner. It never lists whole slogans.

_DETERMINERS = frozenset({
    "the", "a", "an", "my", "your", "his", "her", "its", "our", "their", "one's", "this", "that",
    "these", "those", "every", "each", "all", "some", "any",
})
_PREPOSITIONS = frozenset({
    "from", "with", "under", "through", "into", "onto", "upon", "to", "by", "for", "in", "on", "at",
    "over", "among", "beyond", "across", "against", "within", "without", "between", "beneath",
    "toward", "towards", "about", "like", "as",
})
# Verbs of learning, whose object is the skill: "master the dance of shadows"
# -> Dance of Shadows. Verbs of getting ("earn trust", "unlock secrets") take
# objects that are not skills, so they are re-asked instead.
_META_VERBS = frozenset({
    "master", "learn", "study", "practice", "practise", "hone", "perfect", "develop", "improve",
    "train", "cultivate", "refine", "sharpen", "deepen",
})
# Words that are verbs at the head of a phrase (rarely a skill noun's first word).
_VERBS = frozenset({
    "earn", "gain", "unlock", "attain", "achieve", "acquire", "pursue", "seek", "discover",
    "embrace", "awaken", "become",
    "forge", "weave", "braid", "create", "make", "bend", "conjure", "summon", "bind", "tame",
    "navigate", "survive", "endure", "outwit", "uncover", "reveal", "unravel", "decipher",
    "understand", "protect", "defend", "overcome", "unleash", "manipulate", "harness", "wield",
    "speak", "sing", "walk", "run", "rise", "find", "build", "shape", "break", "mend", "heal",
    "brew", "read", "write", "see", "hear", "feel", "sense", "steal", "sneak", "hide", "strike",
    "fight", "climb", "command", "control", "channel", "call", "bring", "turn", "keep", "hold",
    "carry", "follow", "listen", "touch", "draw", "open", "close", "light", "kindle", "ignite",
    "tread", "wander", "whisper", "dance", "craft", "guard", "ride", "track", "hunt", "trade",
})
# Of these, the ones that are also skill nouns count as verbs only before a
# determiner or a preposition: "Dance of Shadows", "Trade Lore" stay names.
_NOUN_TOO = frozenset({
    "dance", "craft", "guard", "ride", "track", "hunt", "trade", "study", "practice", "practise",
    "train", "light", "call", "draw", "turn", "hold", "run", "walk", "break", "command", "control",
    "channel", "sense", "shape", "climb", "strike", "fight", "brew", "read", "build", "grow", "keep",
    "hide", "open", "close", "sneak", "whisper",
})
_VERB_SUFFIX = re.compile(r"[a-z]{3,}(?:ize|ify)$")


def leading_verb(name: str) -> str:
    """The verb a name starts with, or "" when it starts with a noun."""
    words = [word.lower().strip("'-.,") for word in str(name or "").split()]
    words = [word for word in words if word]
    if not words:
        return ""
    if words[0] == "to" and len(words) > 1:
        return words[1]
    first, nxt = words[0], (words[1] if len(words) > 1 else "")
    if nxt in ("of", "and"):
        return ""
    before_object = nxt in _DETERMINERS or (nxt in _PREPOSITIONS)
    if first in _NOUN_TOO:
        return first if before_object else ""
    if first in _META_VERBS or first in _VERBS or _VERB_SUFFIX.match(first):
        return first
    return ""


def noun_form(name: str) -> str:
    """The skill a verb-led name names, when its object is that skill; else "".

    "master the dance of shadows" -> "Dance of Shadows". "learn from the
    ancients" names no skill (its object is a preposition), and "forge
    unbreakable bonds" describes a deed: both are left for a re-ask.
    """
    words = str(name or "").split()
    if words and words[0].lower() == "to":
        # "to X ...": X is the verb by position.
        words = words[1:]
        verb = words[0].lower() if words else ""
    else:
        verb = leading_verb(" ".join(words))
    if not verb or verb not in _META_VERBS:
        return ""
    rest = words[1:]
    while rest and rest[0].lower() in _DETERMINERS:
        rest = rest[1:]
    if rest and rest[0].lower() == "to":
        return noun_form(" ".join(rest))
    if not rest or rest[0].lower() in _PREPOSITIONS:
        return ""
    kept: list[str] = []
    for word in rest:
        low = word.lower().strip(".,")
        if low in _GRAMMAR_WORDS or low in _PREPOSITIONS:
            break
        kept.append(word.strip(".,"))
    while kept and kept[-1].lower() in _JOINERS:
        kept.pop()
    candidate = " ".join(kept)
    if not candidate:
        return ""
    if len(kept) == 1 and re.search(r"[^s]s$", candidate.lower()) and not candidate.lower().endswith("ics"):
        # "study the stars" -> "Stars" is a topic, not a skill: re-ask.
        return ""
    if leading_verb(candidate):
        # "learn to brew tonics": the object is itself verb-led.
        return noun_form(candidate)
    if name_shape_errors(candidate):
        return ""
    return _title_case(candidate)


_RENAME_SYSTEM = (
    "Each input phrase was written as an RPG character's proficiency but reads as a deed or a motto. "
    "Answer one line per phrase, lines only: <number>|<name>. The name is the plain noun a teacher would "
    "use for the craft, trade, lore, field skill or practice the phrase describes, one to four words, "
    "fitting the character and the world; it never starts with a verb. name_shapes shows the form "
    "(drawn fresh for this call; they are not this character's skills). Answer <number>|NONE when the "
    "phrase describes no skill anyone could practise."
)


def rename_prompt(items: list[dict[str, Any]], options: dict[str, Any], exclude: list[str] | None = None) -> str:
    try:
        from app.example_pools import setup_context, draw_proficiency_names

        shapes = draw_proficiency_names(setup_context(options), 4, exclude=list(exclude or []))
    except Exception:
        shapes = []
    return json.dumps(
        {
            "phrases": [
                {"number": index + 1, **{k: v for k, v in item.items() if v}}
                for index, item in enumerate(items)
            ],
            "name_shapes": shapes,
            "character_backstory": _clean(options.get("character_backstory"))[:400],
            "world": {
                "world_style": _clean(options.get("world_style"))[:120],
                "tech_level": _clean(options.get("tech_level"))[:80],
                "magic_level": _clean(options.get("magic_level"))[:80],
            },
        },
        ensure_ascii=True,
    )


def parse_renames(content: str, count: int) -> dict[int, str]:
    """Accepted names by phrase number: a noun-phrase name, not NONE, not verb-led."""
    out: dict[int, str] = {}
    for line in str(content or "").splitlines():
        parts = [part.strip().strip("`*\"'") for part in line.split("|")]
        if len(parts) < 2 or not parts[0].rstrip(".").isdigit():
            continue
        number = int(parts[0].rstrip("."))
        name = parts[-1].strip(" .")
        if not (1 <= number <= count) or number in out or not name or name.upper() == "NONE":
            continue
        if name_shape_errors(name):
            continue
        out[number] = _title_case(name)
    return out


def rename_with_model(
    items: list[dict[str, Any]],
    options: dict[str, Any],
    *,
    exclude: list[str] | None = None,
    ask=None,
) -> dict[int, str]:
    """One re-ask for verb-led names the engine could not turn into a skill noun.

    ``items`` are dicts with "phrase" (and optional "tracking"/"limit");
    returns {index: name} for the ones the model named. ``ask(system, user)``
    defaults to the configured model.
    """
    if not items:
        return {}
    if ask is None:
        from app.llm import _chat_content

        def ask(system: str, user: str) -> str:
            return _chat_content(system, user, timeout=90, temperature=0.3, max_tokens=200, response_format="text")

    try:
        content = ask(_RENAME_SYSTEM, rename_prompt(items, options, exclude))
    except Exception:
        return {}
    return {number - 1: name for number, name in parse_renames(content, len(items)).items()}


# ---------------------------------------------------------------------------
# Rule titles (playtest #22)
# ---------------------------------------------------------------------------

_LIMIT_WORDS = ("cannot", "can't", "only", "never", "require", "needs", "need ", "until", "without", "cap", "limit", "no more")
_PROGRESS_WORDS = ("track", "progress", "xp", "experience", "rank", "level", "count")
_TITLE_KIND_WORDS = frozenset({"rule", "rules", "limit", "limits", "training", "progress", "growth", "cap", "law"})


def _stem_set(text: str) -> set[str]:
    return {word[:5] for word in re.findall(r"[a-z]{3,}", str(text or "").lower())}


def rule_title(title: str, text: str, names: list[str] | None = None) -> str:
    """A rule's title from its own text.

    The model's title is kept when every content word of it is in the text;
    otherwise the engine names the rule after the proficiency it mentions
    ("Unbreakable Bonds Limit") or its first content words.
    """
    title = _clean(title).strip(" .:")
    text = _clean(text)
    # A kind word ("Training", "Limit") may stand in a title without being in the text.
    content = [
        word for word in re.findall(r"[A-Za-z]{3,}", title)
        if word.lower() not in _GRAMMAR_WORDS and word.lower() not in _TITLE_KIND_WORDS
    ]
    stems = _stem_set(text)
    if content and all(word.lower()[:5] in stems for word in content):
        return title[:TITLE_MAX]
    low = text.lower()
    if any(word in low for word in _LIMIT_WORDS):
        kind = "Limit"
    elif any(word in low for word in _PROGRESS_WORDS):
        kind = "Progress"
    else:
        kind = "Training"
    for name in sorted(names or [], key=len, reverse=True):
        if name and name.lower() in low:
            return f"{name} {kind}"[:TITLE_MAX]
    # Otherwise one word of the text names it: the one the model's title
    # shares with the text, else the text's first content word.
    words = [
        word for word in re.findall(r"[A-Za-z][A-Za-z'\-]{2,}", text)
        if word.lower() not in _GRAMMAR_WORDS and not any(word.lower().startswith(w.strip()) for w in _LIMIT_WORDS + _PROGRESS_WORDS)
    ]
    title_stems = {word.lower()[:5] for word in content}
    anchor = next((word for word in words if word.lower()[:5] in title_stems), words[0] if words else "")
    if not anchor:
        return kind
    return f"{anchor[:1].upper()}{anchor[1:]} {kind}"[:TITLE_MAX]


# ---------------------------------------------------------------------------
# The setup roll's text (playtest #22)
# ---------------------------------------------------------------------------


def split_phrases(text: str) -> list[str]:
    """Top-level comma phrases; commas inside parentheses stay inside."""
    parts: list[str] = []
    depth = 0
    current = ""
    for char in str(text or ""):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
            continue
        current += char
    parts.append(current.strip())
    return [part for part in parts if part]


def _clamp_rank_text(tail: str, labels: list[str], cap: int) -> tuple[str, bool]:
    """Lower the start rank, the label that opens a phrase's parenthesis, to the cap.

    Only the opening label is the start rank: "(weak, seed, tracked by water
    awareness, capped at S)" names a limit, and a live roll had its "S"
    lowered to the start cap when any label in the parenthesis counted.
    """
    alternatives = "|".join(sorted(map(re.escape, labels), key=len, reverse=True))
    letters = all(len(label) <= 3 and label.isupper() for label in labels)
    lead = r"^\(\s*(?:(?:start(?:ing|s)?|rank)\s+(?:at\s+)?(?:rank\s+)?)?"
    if letters:
        pattern = re.compile(lead + r"(" + alternatives + r")(?![A-Za-z])")
    else:
        pattern = re.compile(lead + r"(" + alternatives + r")\b", re.I)
    match = pattern.search(tail)
    if not match:
        return tail, False
    folded = [label.upper() for label in labels]
    index = folded.index(match.group(1).upper())
    if index <= cap:
        return tail, False
    return tail[: match.start(1)] + labels[cap] + tail[match.end(1):], True


def settle_setup_text(
    text: str,
    options: dict[str, Any],
    *,
    power_fantasy: dict[str, Any] | None = None,
    idea: str = "",
    ask=None,
    keep_unnamed: bool = False,
) -> tuple[str, dict[str, Any]]:
    """The rolled custom_skills text with noun names and ranks inside this start's cap.

    A proficiency phrase is one with a parenthesis after its name, or a bare
    phrase of four words or fewer. Verb-led names become their noun form when
    the object names the skill; the rest are re-asked once together, and a
    phrase still without a skill noun is dropped. Training rules (longer
    clauses) pass untouched. ``keep_unnamed`` keeps such a phrase, its rank
    capped, for a later pass to name (Start runs with no model call).
    """
    labels = rank_labels(options)
    cap = start_rank_cap(options, labels, idea, power_fantasy)
    seed_cap = seed_rank_cap(options, labels, idea, power_fantasy)
    seeds = seed_names(options)
    report: dict[str, Any] = {"renamed": [], "reasked": [], "dropped": [], "ranks_lowered": []}
    phrases = split_phrases(text)
    out: list[str | None] = []
    pending: list[tuple[int, str, str]] = []
    seed_used = False
    folded = [label.upper() for label in labels]
    last_limit = cap
    for phrase in phrases:
        head, paren, tail = phrase.partition("(")
        head = head.strip()
        tail = paren + tail
        if not paren and len(head.split()) > NAME_WORDS_MAX:
            out.append(phrase)
            continue
        if head.upper() in folded:
            # A bare rank after its name ("Qi Circulation, F, tracked by ...",
            # live roll): the start rank of the phrase before it.
            if folded.index(head.upper()) > last_limit:
                report["ranks_lowered"].append(head)
                head = labels[last_limit]
            out.append(f"{head} {tail}".strip())
            continue
        if leading_verb(head):
            named = noun_form(head)
            if named:
                report["renamed"].append(f"{head} -> {named}")
                head = named
            else:
                pending.append((len(out), head, tail))
                out.append(None)
                continue
        is_seed = (not seed_used) and ("seed" in head.lower() or is_seed_name(head, seeds))
        limit = seed_cap if is_seed else cap
        seed_used = seed_used or is_seed
        last_limit = limit
        if tail:
            tail, lowered = _clamp_rank_text(tail, labels, limit)
            if lowered:
                report["ranks_lowered"].append(head)
        out.append(f"{head} {tail}".strip())
    if pending:
        names = rename_with_model(
            [{"phrase": head, "detail": tail.strip("() ")[:120]} for _, head, tail in pending],
            options,
            exclude=[part.partition("(")[0].strip() for part in out if part],
            ask=ask,
        )
        for index, (slot, head, tail) in enumerate(pending):
            if index in names:
                report["reasked"].append(f"{head} -> {names[index]}")
                tail, lowered = _clamp_rank_text(tail, labels, cap)
                if lowered:
                    report["ranks_lowered"].append(names[index])
                out[slot] = f"{names[index]} {tail}".strip()
            elif keep_unnamed:
                tail, lowered = _clamp_rank_text(tail, labels, cap)
                if lowered:
                    report["ranks_lowered"].append(head)
                report.setdefault("kept_for_the_pass", []).append(head)
                out[slot] = f"{head} {tail}".strip()
            else:
                report["dropped"].append(head)
    return ", ".join(part for part in out if part), report


def name_shape_errors(name: str) -> list[str]:
    """Structure checks on a proficiency name: a short noun phrase, not a sentence."""
    words = name.split()
    if not words:
        return ["name missing"]
    errors: list[str] = []
    if len(name) > NAME_MAX:
        errors.append(f"name over {NAME_MAX} chars")
    if len(words) > NAME_WORDS_MAX:
        errors.append(f"name over {NAME_WORDS_MAX} words")
    if any(not _NAME_SHAPE.match(word) for word in words):
        errors.append("name has characters other than letters")
    lowered = [word.lower().strip("'-") for word in words]
    if any(word in _GRAMMAR_WORDS for word in lowered):
        errors.append("name reads as a sentence, not a skill name")
    if lowered[0] in _JOINERS or lowered[-1] in _JOINERS:
        errors.append("name starts or ends on a joining word")
    if leading_verb(name):
        errors.append("name starts with a verb")
    return errors


def _title_case(name: str) -> str:
    return " ".join(
        word if word.lower() in _JOINERS and index else word[:1].upper() + word[1:]
        for index, word in enumerate(name.split())
    )


def validate_skill_row(
    row: dict[str, Any],
    labels: list[str],
    cap: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    name = _clean(row.get("name")).strip(" .:;,\"'")
    errors = name_shape_errors(name)
    rank_text = _clean(row.get("start_rank")).upper().removeprefix("RANK ").strip()
    folded = [label.upper() for label in labels]
    rank_index = folded.index(rank_text) if rank_text in folded else None
    clamped = False
    unranked = False
    if rank_index is None:
        # A word off the scale ("basic", "novice") or none at all: the
        # engine starts the proficiency at the lowest rank.
        rank_index, unranked = 0, True
    if rank_index is not None and rank_index > cap:
        # The engine owns the ceiling: an over-ranked proficiency starts at
        # the highest rank this start allows instead of being lost. Live,
        # the 8B gave the seed matching the ability card rank S.
        rank_index, clamped = cap, True
    # The summary writes "tracked by ..."; a leading "by" or "through" would double it.
    tracking = re.sub(r"^(?:tracked\s+)?(?:by|through|via)\s+", "", _clean(row.get("tracking")), flags=re.I).rstrip(".")
    hard_limit = _clean(row.get("hard_limit")).rstrip(".")
    if hard_limit.upper() in folded:
        # A bare rank in the limit column is a rank ceiling.
        hard_limit = f"capped at rank {labels[folded.index(hard_limit.upper())]}"
    if len(tracking) < 4:
        errors.append("tracking missing")
    elif len(tracking) > TRACKING_MAX:
        errors.append(f"tracking over {TRACKING_MAX} chars")
    if len(hard_limit) < 4:
        errors.append("limit missing")
    elif len(hard_limit) > LIMIT_MAX:
        errors.append(f"limit over {LIMIT_MAX} chars")
    if errors:
        return None, errors
    name = _title_case(name)
    return {
        "name": name,
        "clamped": clamped,
        "unranked": unranked,
        "name_key": race_key(name),
        "start_rank": labels[rank_index],
        "rank_index": rank_index,
        "tracking": tracking,
        "hard_limit": hard_limit,
        "source": _clean(row.get("source")) or "model",
    }, []


def skill_value_for_rank(rank_index: int) -> int:
    """player_skills.value for a starting rank: two points a rank from 1.

    Skill checks read the value as a 0..20 rank and new skills start at 1..15;
    the lowest rank is the same 1 a freshly practised skill gets.
    """
    return max(1, min(15, 1 + 2 * int(rank_index)))


def skill_note(clean: dict[str, Any]) -> str:
    note = f"Start rank {clean['start_rank']}; tracked by {clean['tracking']}; limit: {clean['hard_limit']}"
    if len(note) > 160:
        note = note[:160].rsplit(" ", 1)[0]
    return note


def store_proficiency(conn, clean: dict[str, Any], *, mirror_skill: bool = True) -> tuple[str | None, list[str]]:
    existing = conn.execute(
        "SELECT code FROM player_proficiencies WHERE name_key = ?", (clean["name_key"],)
    ).fetchone()
    if existing:
        return str(existing["code"]), ["duplicate"]
    if conn.execute("SELECT COUNT(*) AS n FROM player_proficiencies").fetchone()["n"] >= SKILL_LIMIT:
        return None, ["proficiency table full"]
    code = _next_code(conn, "player_proficiencies", "P")
    conn.execute(
        """
        INSERT INTO player_proficiencies (code, name, name_key, start_rank, rank_index, tracking, hard_limit, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (code, clean["name"], clean["name_key"], clean["start_rank"], clean["rank_index"],
         clean["tracking"], clean["hard_limit"], clean["source"]),
    )
    if mirror_skill:
        note = skill_note(clean)
        current = conn.execute(
            "SELECT id, notes FROM player_skills WHERE name = ? COLLATE NOCASE", (clean["name"],)
        ).fetchone()
        if current:
            # A seed skill start_playthrough already wrote keeps its value; its
            # note becomes the settled rank, tracking and limit.
            conn.execute("UPDATE player_skills SET notes = ? WHERE id = ?", (note, current["id"]))
        else:
            conn.execute(
                "INSERT INTO player_skills (name, value, notes) VALUES (?, ?, ?)",
                (clean["name"], skill_value_for_rank(clean["rank_index"]), note),
            )
    return code, []


def proficiency_rows(conn) -> list[dict[str, Any]]:
    ensure_proficiency_table(conn)
    return [dict(row) for row in conn.execute("SELECT * FROM player_proficiencies ORDER BY id").fetchall()]


def proficiency_rules(conn) -> list[dict[str, Any]]:
    rows = [_fact_dict(row) for row in conn.execute("SELECT * FROM world_facts WHERE kind = 'rule' ORDER BY id").fetchall()]
    return [row for row in rows if "proficiency" in (row.get("tags") or [])]


def summary_text(skills: list[dict[str, Any]], rules: list[dict[str, Any]]) -> str:
    """custom_skills as the engine now holds it: one phrase per row, comma-free inside."""
    parts = [
        f"{row['name']} (start rank {row['start_rank']}; tracked by {row['tracking']}; limit: {row['hard_limit']})"
        for row in skills
    ]
    parts += [str(row.get("text") or "").rstrip(".") for row in rules]
    text = ", ".join(part.replace(",", ";") for part in parts if part)
    return text[:SUMMARY_MAX]


_SETTLE_SYSTEM = (
    "You turn one RPG character's custom proficiency text into table rows. Answer with lines only, "
    "no prose, no JSON, no numbering. Two line shapes are allowed:\n"
    "SKILL|<proficiency name, one to four words>|<start rank, one label from rank_scale>|"
    "<how its progress is tracked, at most 100 characters>|<its hard limit, at most 100 characters>\n"
    "RULE|<title, at most 6 words>|<one training, tracking or limit rule, at most 200 characters>\n"
    "A SKILL line is a proficiency this character starts with. Its name is the plain name of a craft, trade, "
    "art, discipline or practice a teacher could name: a noun phrase, never a sentence or motto. "
    "Take the name from the text when it gives one. When a phrase only describes a practice, name the "
    "discipline it describes in plain words, as a noun that never starts with a verb; name_shapes shows the "
    "form (drawn fresh for this call; they are not this character's skills). Every start rank is at or below "
    "highest_start_rank (the seed's at or below seed_highest_start_rank when given). Tracking says what earns this proficiency "
    "progress in this character's life and world. The limit says what this proficiency cannot do yet or what caps it.\n"
    "A RULE line states how new proficiencies are found or trained, how progress is tracked, or a hard limit "
    "on growth, as a rule a game master can check in play. RULE lines come only from "
    "custom_proficiency_text; the world fields are context, not rules to copy.\n"
    "Every line must fit the character, the abilities and the world in the input. A phrase of the text that "
    "names no skill and states no checkable rule gets no line. "
    f"Write at most {SKILL_LIMIT} SKILL lines and {RULE_LIMIT} RULE lines. "
    "Calculable XP or rank formulas stay on the abilities; do not copy them here."
)


def settle_prompt(options: dict[str, Any], existing_skills: list[str], idea: str = "") -> str:
    labels = rank_labels(options)
    cap = start_rank_cap(options, labels, idea)
    seed_cap = seed_rank_cap(options, labels, idea)
    try:
        from app.example_pools import draw_proficiency_names, setup_context

        shapes = draw_proficiency_names(setup_context(options), 4, exclude=existing_skills)
    except Exception:
        shapes = []
    profile = start_profile(options, idea)
    abilities = []
    for ability in options.get("special_abilities") or []:
        if isinstance(ability, dict) and _clean(ability.get("name")):
            abilities.append({
                "name": _clean(ability.get("name"))[:60],
                "description": _clean(ability.get("description"))[:160],
                "locked": bool(ability.get("locked")),
            })
    theme = options.get("session_theme") if isinstance(options.get("session_theme"), dict) else {}
    pf = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}
    return json.dumps(
        {
            "custom_proficiency_text": _clean(options.get("custom_skills"))[:1200],
            "rank_scale": labels,
            "highest_start_rank": labels[cap],
            **({"seed_highest_start_rank": labels[seed_cap]} if seed_cap > cap else {}),
            "name_shapes": shapes,
            "character": {
                "name": _clean(options.get("player_name"))[:60],
                "backstory": _clean(options.get("character_backstory"))[:600],
                "abilities": abilities[:4],
                "skills_already_recorded": existing_skills[:8],
                "start_power": profile["start_power"],
                "growth": profile["growth"],
            },
            "world": {
                "world_style": _clean(options.get("world_style"))[:120],
                "tech_level": _clean(options.get("tech_level"))[:80],
                "magic_level": _clean(options.get("magic_level"))[:80],
                "skill_style": _clean(options.get("skill_style"))[:80],
                "proficiency_access": _clean(options.get("proficiency_access"))[:80],
                "new_skill_frequency": _clean(options.get("new_skill_frequency"))[:80],
            },
        },
        ensure_ascii=True,
    )


def _is_fragment_list(text: str) -> bool:
    """A rule is a clause. Comma pieces of three words or fewer each are a keyword list.

    Qwen3 8B, handed a rolled string, answered RULE lines such as "first
    lesson, successful attempts, no self-taught skills": the pieces of other
    phrases, not a rule anyone can check.
    """
    pieces = [piece.split() for piece in re.split(r"[,;]", text) if piece.strip()]
    if len(pieces) < 2:
        return len(text.split()) < 3
    return all(len(words) <= 3 for words in pieces)


def _restates_proficiency(conn, text: str, options: dict[str, Any] | None = None) -> bool:
    """True when most of a rule's words are one proficiency's parts or a setting the game already holds.

    The live 8B turned proficiency_access and skill_style, sent as context,
    into rules ("basic attempts allowed; mastery needs a mentor").
    """
    words = _words(text)
    if not words:
        return False
    sources = [
        f"{row['name']} {row['tracking']} {row['hard_limit']}"
        for row in conn.execute("SELECT name, tracking, hard_limit FROM player_proficiencies").fetchall()
    ]
    sources += [
        str((options or {}).get(key) or "")
        for key in ("skill_style", "proficiency_access", "new_skill_frequency", "skill_growth_speed")
    ]
    for source in sources:
        stored = _words(source)
        if stored and len(words & stored) / len(words) >= 0.5:
            return True
    return False


def _settle_records(content: str) -> list[tuple[str, list[str]]]:
    """SKILL and RULE records, plus SKILL lines whose head the model replaced with the name.

    Qwen3 8B answered "<name>|<name>|<rank>|<tracking>|<limit>": the SKILL
    shape with the name written twice. Five fields with the first two equal
    is that shape and nothing else.
    """
    records = parse_lines(content, ("SKILL", "RULE"))
    for line in str(content or "").splitlines():
        parts = [part.strip() for part in line.strip().strip("`").split("|")]
        if len(parts) == 5 and parts[0] and parts[0].lower() == parts[1].lower() and parts[0].upper() not in ("SKILL", "RULE"):
            records.append(("SKILL", parts[1:]))
    return records


def apply_settlement(conn, content: str, options: dict[str, Any], *, rename=None) -> dict[str, Any]:
    """Validate and store the model's SKILL and RULE lines, then rewrite custom_skills as their summary.

    ``rename(items)`` is the one re-ask for verb-led names with no skill noun
    in them (items: dicts with phrase, tracking, limit; returns {index: name}).
    Without it those lines are dropped.
    """
    ensure_proficiency_table(conn)
    labels = rank_labels(options)
    idea = idea_text(options, conn)
    cap = start_rank_cap(options, labels, idea)
    seed_cap = seed_rank_cap(options, labels, idea)
    seeds = seed_names(options)
    seed_used = False
    mirror = True
    try:
        from app.world import _setup_flag_enabled

        mirror = _setup_flag_enabled(options, "skills_enabled", True)
    except Exception:
        pass
    accepted = {"skills": 0, "rules": 0}
    rejected: list[str] = []
    adjusted: list[str] = []
    skills_seen = 0
    rules_seen = 0
    # Skills first, so a rule that only restates one is caught whatever the line order.
    records = sorted(_settle_records(content), key=lambda record: record[0] != "SKILL")
    skill_records = [record for record in records if record[0] == "SKILL"]
    rule_records = [record for record in records if record[0] != "SKILL"]
    unnamed: list[list[str]] = []

    def settle_skill(fields: list[str], original: str) -> None:
        nonlocal seed_used
        is_seed = not seed_used and is_seed_name(fields[0], seeds)
        clean, errors = validate_skill_row(
            {"name": fields[0], "start_rank": fields[1], "tracking": fields[2], "hard_limit": fields[3]},
            labels,
            seed_cap if is_seed else cap,
        )
        if clean is None:
            rejected.append(f"SKILL {original[:30]}: {'; '.join(errors)}")
            return
        code, errors = store_proficiency(conn, clean, mirror_skill=mirror)
        if code and not errors:
            accepted["skills"] += 1
            seed_used = seed_used or is_seed
            if original != fields[0]:
                adjusted.append(f"SKILL {original[:30]}: a verb phrase, named {clean['name']}")
            if clean["clamped"]:
                adjusted.append(f"SKILL {clean['name']}: start rank lowered to {clean['start_rank']}")
            if clean["unranked"]:
                adjusted.append(f"SKILL {clean['name']}: rank '{fields[1][:20]}' not on the scale, set to {clean['start_rank']}")
        elif errors:
            rejected.append(f"SKILL {clean['name']}: {'; '.join(errors)}")

    for head, fields in skill_records:
        skills_seen += 1
        if skills_seen > SKILL_LIMIT:
            rejected.append(f"SKILL {fields[0][:30] if fields else ''}: over {SKILL_LIMIT} lines")
            continue
        fields = (fields + [""] * 4)[:4]
        original = _clean(fields[0]).strip(" .:;,\"'")
        if leading_verb(original):
            named = noun_form(original)
            if not named:
                unnamed.append([original, *fields[1:]])
                continue
            fields = [named, *fields[1:]]
        settle_skill(fields, original)
    if unnamed:
        names: dict[int, str] = {}
        if rename:
            try:
                names = rename([{"phrase": row[0], "tracking": row[2], "limit": row[3]} for row in unnamed]) or {}
            except Exception:
                names = {}
        for index, row in enumerate(unnamed):
            if index in names and not name_shape_errors(names[index]):
                settle_skill([names[index], *row[1:]], row[0])
            else:
                rejected.append(f"SKILL {row[0][:30]}: a verb phrase that names no skill")
    proficiency_names = [str(row["name"]) for row in conn.execute("SELECT name FROM player_proficiencies").fetchall()]
    for head, fields in rule_records:
        rules_seen += 1
        if rules_seen > RULE_LIMIT:
            rejected.append(f"RULE {fields[0][:30] if fields else ''}: over {RULE_LIMIT} lines")
            continue
        fields = (fields + [""] * 2)[:2]
        title, text = _clean(fields[0])[:TITLE_MAX], _clean(fields[1])
        # The title comes from the rule's own words (game 2: "Crafting
        # Mastery" over a rule about Unbreakable Bonds).
        derived = rule_title(title, text, proficiency_names)
        if derived != title:
            adjusted.append(f"RULE {title[:30]}: titled {derived} from its text")
        title = derived
        if len(text) > TEXT_MAX:
            rejected.append(f"RULE {title[:30]}: text over {TEXT_MAX} chars")
            continue
        if _is_fragment_list(text):
            rejected.append(f"RULE {title[:30]}: a list of fragments, not a rule")
            continue
        if _restates(conn, f"{title} {text}") or _restates_proficiency(conn, text, options):
            rejected.append(f"RULE {title[:30]}: restates a stored fact")
            continue
        code, errors = store_fact(
            conn,
            {
                "kind": "rule",
                "title": title,
                "text": text,
                "tags": _tags_for(text, ["proficiency"]),
                "source": "model",
            },
        )
        if code and not errors:
            accepted["rules"] += 1
        elif errors and errors != ["duplicate"]:
            rejected.append(f"RULE {title[:30]}: {'; '.join(errors)}")
    summary = ""
    if accepted["skills"] or accepted["rules"]:
        summary = summary_text(proficiency_rows(conn), proficiency_rules(conn))
        if summary:
            row = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
            try:
                stored = json.loads(str(row["value"] or "{}")) if row else {}
            except json.JSONDecodeError:
                stored = {}
            if isinstance(stored, dict):
                stored.setdefault("custom_skills_setup", stored.get("custom_skills") or "")
                stored["custom_skills"] = summary
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES ('playthrough_options', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (json.dumps(stored, ensure_ascii=True),),
                )
    return {
        "called": True,
        "accepted": accepted,
        "adjusted": adjusted[:12],
        "rejected": rejected[:12],
        "summary": summary[:200],
    }


def settle_from_model(options: dict[str, Any]) -> dict[str, Any]:
    """One model call that settles custom_skills into proficiency and rule rows."""
    from app.db import connect
    from app.llm import _chat_content

    text = _clean(options.get("custom_skills"))
    if not text:
        return {"called": False, "reason": "no custom proficiency text"}
    with connect() as conn:
        ensure_proficiency_table(conn)
        existing = [str(row["name"]) for row in conn.execute("SELECT name FROM player_skills ORDER BY id").fetchall()]
        idea = idea_text(options, conn)
    content = _chat_content(
        _SETTLE_SYSTEM,
        settle_prompt(options, existing, idea),
        timeout=180,
        temperature=0.3,
        max_tokens=700,
        response_format="text",
    )
    def rename(items: list[dict[str, Any]]) -> dict[int, str]:
        return rename_with_model(items, options, exclude=existing)

    with connect() as conn:
        return apply_settlement(conn, content, options, rename=rename)


register_post_start_pass("proficiencies", settle_from_model)
