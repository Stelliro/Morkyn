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


def start_rank_cap(options: dict[str, Any], labels: list[str]) -> int:
    """Highest rank index a starting proficiency may hold.

    A weak or near-useless start keeps to the two lowest ranks, an ordinary one
    to the lower half, a strong start may use the whole scale.
    """
    theme = (options or {}).get("session_theme") if isinstance((options or {}).get("session_theme"), dict) else {}
    pf = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}
    start = str(pf.get("start_power") or "ordinary").lower()
    last = max(0, len(labels) - 1)
    if start in ("near_useless", "weak"):
        return min(1, last)
    if start == "strong":
        return last
    return max(0, (len(labels) - 1) // 2)


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
    "discipline it describes in plain words. Keep the rank the text gives that proficiency; otherwise "
    "choose one from rank_scale at or below highest_start_rank. Tracking says what earns this proficiency "
    "progress in this character's life and world. The limit says what this proficiency cannot do yet or what caps it.\n"
    "A RULE line states how new proficiencies are found or trained, how progress is tracked, or a hard limit "
    "on growth, as a rule a game master can check in play. RULE lines come only from "
    "custom_proficiency_text; the world fields are context, not rules to copy.\n"
    "Every line must fit the character, the abilities and the world in the input. A phrase of the text that "
    "names no skill and states no checkable rule gets no line. "
    f"Write at most {SKILL_LIMIT} SKILL lines and {RULE_LIMIT} RULE lines. "
    "Calculable XP or rank formulas stay on the abilities; do not copy them here."
)


def settle_prompt(options: dict[str, Any], existing_skills: list[str]) -> str:
    labels = rank_labels(options)
    cap = start_rank_cap(options, labels)
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
            "character": {
                "name": _clean(options.get("player_name"))[:60],
                "backstory": _clean(options.get("character_backstory"))[:600],
                "abilities": abilities[:4],
                "skills_already_recorded": existing_skills[:8],
                "start_power": str(pf.get("start_power") or "ordinary"),
                "growth": str(pf.get("growth") or "steady"),
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


def apply_settlement(conn, content: str, options: dict[str, Any]) -> dict[str, Any]:
    """Validate and store the model's SKILL and RULE lines, then rewrite custom_skills as their summary."""
    ensure_proficiency_table(conn)
    labels = rank_labels(options)
    cap = start_rank_cap(options, labels)
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
    for head, fields in records:
        if head == "SKILL":
            skills_seen += 1
            if skills_seen > SKILL_LIMIT:
                rejected.append(f"SKILL {fields[0][:30] if fields else ''}: over {SKILL_LIMIT} lines")
                continue
            fields = (fields + [""] * 4)[:4]
            clean, errors = validate_skill_row(
                {"name": fields[0], "start_rank": fields[1], "tracking": fields[2], "hard_limit": fields[3]},
                labels,
                cap,
            )
            if clean is None:
                rejected.append(f"SKILL {fields[0][:30]}: {'; '.join(errors)}")
                continue
            code, errors = store_proficiency(conn, clean, mirror_skill=mirror)
            if code and not errors:
                accepted["skills"] += 1
                if clean["clamped"]:
                    adjusted.append(f"SKILL {clean['name']}: start rank lowered to {clean['start_rank']}")
                if clean["unranked"]:
                    adjusted.append(f"SKILL {clean['name']}: rank '{fields[1][:20]}' not on the scale, set to {clean['start_rank']}")
            elif errors:
                rejected.append(f"SKILL {clean['name']}: {'; '.join(errors)}")
        else:
            rules_seen += 1
            if rules_seen > RULE_LIMIT:
                rejected.append(f"RULE {fields[0][:30] if fields else ''}: over {RULE_LIMIT} lines")
                continue
            fields = (fields + [""] * 2)[:2]
            title, text = _clean(fields[0])[:TITLE_MAX], _clean(fields[1])
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
    content = _chat_content(
        _SETTLE_SYSTEM,
        settle_prompt(options, existing),
        timeout=180,
        temperature=0.3,
        max_tokens=700,
        response_format="text",
    )
    with connect() as conn:
        return apply_settlement(conn, content, options)


register_post_start_pass("proficiencies", settle_from_model)
