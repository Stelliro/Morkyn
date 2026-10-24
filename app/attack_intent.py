"""Does the player's line attack someone here? One ask per person, a second to confirm (#85, #129).

What triggers a check was decided by the trigger tables in
skill_checks.infer_check_from_action: verbs like attack, stab, shoot. Lines
that harm a person in any other words rolled nothing, and the player's stated
result stood as the outcome: "i rip her in half, this move grants her instant
death" (cc87dd29 T10, baseline T3), "i rip her head from her shoulders ...
killing her instantly" (T13). A longer verb list was tried and rejected
(round 1): it missed "slit", "put a bullet in" and fired on "i cut the guard
off mid-sentence" and "i hit the guard with a question".

So the meaning is not read from words. The candidates are the engine's own
records, the people the turn has in the scene (the conversation's present,
addressed and listening people, the place's keeper and its people; never the
dead), and for each, in the order the engine ranks them (addressed first), one
plain question about the player's line:

    "Does the player try to hurt or kill Beth?"   yes, then
    "Is the player peaceful toward Beth?"         must be no

The second ask is worded the other way, so a model that says yes to anything
(or no to anything) changes nothing: the line rolls what the trigger tables
gave it, as before. On a confirmed yes the engine rolls the attack it already
knows how to roll: the trigger tables' melee or ranged when they found one,
else the skill of the weapon the player has equipped (the engine's record of
its roll profile), else melee; against that person, as the opposition. The
outcome the player states ("instant death") is the attempt, not the result:
the roll decides, and app/interpreter.py refuses a death the roll did not allow.

Each ask's prompt, reply and seconds go into the turn trace and model_usage
(the caller's ask goes through llm._chat_text with the turn's lists) and the
report goes to the turn ledger. Nothing here may break a turn.
"""
from __future__ import annotations

import re
import time
from typing import Any, Callable

# One ask: (phase, prompt, max_tokens) -> raw reply text (the interpreter's shape).
Ask = Callable[[str, str, int], str]

PHASE_ATTACK = "attack_ask"
PHASE_ATTACK_CHECK = "attack_ask_check"

# Skills an attack is rolled with (the engine's own codes).
ATTACK_SKILLS = ("melee", "ranged")
# Tests set ASK_OVERRIDE[0] to a scripted ask; the game leaves it None.
ASK_OVERRIDE: list[Ask | None] = [None]
MAX_PEOPLE = 4
LINE_CHARS = 600


def ask_attack(name: str, line: str) -> str:
    return f'{_opening(name)} is here. The player wrote: "{line}"\n\nDoes the player try to hurt or kill {name}? Answer yes or no.'


def ask_attack_check(name: str, line: str) -> str:
    return f'{_opening(name)} is here. The player wrote: "{line}"\n\nIs the player peaceful toward {name}? Answer yes or no.'


def _opening(name: str) -> str:
    """The name opening a sentence: "the ghoul" -> "The ghoul" (a person's name is unchanged)."""
    return name[:1].upper() + name[1:] if name else name


def player_line(model_input: str) -> str:
    """The player's own line from the engine's model input: its first paragraph, without codes."""
    from app.interpreter import plain

    first = re.split(r"\n\s*\n", str(model_input or ""), maxsplit=1)[0]
    return plain(first)[:LINE_CHARS].strip()


def _clean(name: Any) -> str:
    from app.interpreter import clean_name

    return clean_name(name)


def people_here(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The living people the engine has in this scene, the one the line addresses first.

    From the engine's records only: the conversation resolution (addressed,
    present, listening, with its names), the place's keeper and the people at
    the place. Each is the full roster record when the engine has one (for the
    opposition's rank and stats). The dead are never here.
    """
    ctx = context if isinstance(context, dict) else {}
    try:
        from app.skill_checks import _npc_pool_from_context

        pool = [n for n in _npc_pool_from_context(ctx) if isinstance(n, dict)]
    except Exception:
        pool = []
    here = ctx.get("current_location") if isinstance(ctx.get("current_location"), dict) else {}
    keeper = here.get("keeper") if isinstance(here.get("keeper"), dict) else None
    by_code: dict[str, dict[str, Any]] = {}
    for npc in [*pool, *([keeper] if keeper else [])]:
        code = str(npc.get("code") or "").strip().upper()
        if code and code not in by_code:
            by_code[code] = npc
    dead = {str(code).upper() for code in _dead_codes(ctx)}
    for npc in by_code.values():
        try:
            if int(npc.get("died_turn") or 0) > 0:
                dead.add(str(npc.get("code") or "").upper())
        except (TypeError, ValueError):
            pass
    conv = ctx.get("conversation_turn") if isinstance(ctx.get("conversation_turn"), dict) else {}
    names = conv.get("names") if isinstance(conv.get("names"), dict) else {}
    order: list[str] = []
    for key in ("addressed", "present", "listening"):
        for code in conv.get(key) or []:
            code = str(code or "").strip().upper()
            if code and code not in order:
                order.append(code)
    if keeper and str(keeper.get("code") or "").strip().upper() not in order:
        order.append(str(keeper.get("code") or "").strip().upper())
    # With a scene record, the scene is who is here (as skill_checks reads it);
    # without one (a fresh game, a harness) the place's people stand in.
    if not isinstance(conv.get("present"), list):
        for code in by_code:
            if code not in order:
                order.append(code)
    out: list[dict[str, Any]] = []
    for code in order:
        if not code or code in dead:
            continue
        record = by_code.get(code) or {}
        name = _clean(record.get("name") or names.get(code) or names.get(code.lower()) or "")
        if not name:
            continue
        out.append({**record, "code": code, "name": name})
    return out[:MAX_PEOPLE]


def _dead_codes(ctx: dict[str, Any]) -> set[str]:
    found = ctx.get("the_dead") if isinstance(ctx.get("the_dead"), dict) else {}
    codes = {str(p.get("code") or "") for p in found.get("people") or [] if isinstance(p, dict)}
    for location in ctx.get("locations") or []:
        for npc in (location.get("npcs") or []) if isinstance(location, dict) else []:
            try:
                if isinstance(npc, dict) and int(npc.get("died_turn") or 0) > 0:
                    codes.add(str(npc.get("code") or ""))
            except (TypeError, ValueError):
                continue
    return {c for c in codes if c}


def _ask(ask: Ask, report: dict[str, Any], phase: str, prompt: str, code: str) -> bool | None:
    from app.interpreter import yes_no

    started = time.time()
    entry: dict[str, Any] = {"phase": phase, "code": code}
    try:
        reply = ask(phase, prompt, 8)
    except Exception as exc:  # the model is down or slow: no answer, no attack
        entry["error"] = f"{type(exc).__name__}: {exc}"[:200]
        reply = None
    entry["reply"] = str(reply if reply is not None else "")[:120]
    entry["seconds"] = round(time.time() - started, 3)
    report["asks"].append(entry)
    return yes_no(reply)


def find_target(line: str, people: list[dict[str, Any]], ask: Ask, report: dict[str, Any]) -> dict[str, Any] | None:
    """The first person the line attacks: yes to the attack ask, then no to the peaceful ask."""
    if not str(line or "").strip():
        return None
    from app.unnamed import ask_label

    for person in people:
        # A numbered figure is asked about as the line names it: "the ghoul",
        # when Ghoul 1 is the only ghoul here (app/unnamed.py).
        name = ask_label(person, people)
        code = str(person.get("code") or "")
        if not name:
            continue
        if _ask(ask, report, PHASE_ATTACK, ask_attack(name, line), code) is not True:
            continue
        peaceful = _ask(ask, report, PHASE_ATTACK_CHECK, ask_attack_check(name, line), code)
        if peaceful is False:
            return person
        report["unconfirmed"].append({"code": code, "peaceful": peaceful})
    return None


def weapon_skill(context: dict[str, Any] | None) -> str:
    """melee or ranged from the equipped weapon's roll profile (the engine's record), else ""."""
    ctx = context if isinstance(context, dict) else {}
    gear = ctx.get("gear_roll_modifiers") if isinstance(ctx.get("gear_roll_modifiers"), dict) else {}
    found: set[str] = set()
    for source in gear.get("sources") or []:
        if not isinstance(source, dict) or source.get("kind") != "item":
            continue
        profile = source.get("profile") if isinstance(source.get("profile"), dict) else {}
        found |= {skill for skill in ATTACK_SKILLS if skill in profile}
    return next(iter(found)) if len(found) == 1 else ""


def opposition_of(person: dict[str, Any]) -> dict[str, Any]:
    """The person as the other side of the roll, from their roster record (as skill_checks builds it)."""
    return {
        "name": person.get("name"),
        "rank": person.get("rank"),
        "stats": person.get("stat_profile") or {},
        "defense": person.get("defense"),
        "attitude": person.get("attitude"),
        "presence": person.get("presence"),
        "power_rank": person.get("power_rank"),
    }


def npc_ref_of(person: dict[str, Any]) -> dict[str, Any]:
    keys = ("code", "name", "attitude", "personality", "role", "presence", "power_rank", "principles", "dislikes", "likes")
    return {key: person.get(key) for key in keys}


def attack_check(person: dict[str, Any], inferred: dict[str, Any] | None, context: dict[str, Any] | None) -> dict[str, Any]:
    """The attack the engine rolls against ``person``: the inferred blow's skill, else the weapon's, else melee."""
    inferred = inferred if isinstance(inferred, dict) else {}
    skill = str(inferred.get("skill_code") or "")
    if skill not in ATTACK_SKILLS:
        skill = weapon_skill(context) or "melee"
    return {
        "skill_code": skill,
        "opposition": opposition_of(person),
        "weapon_or_tool": str(inferred.get("weapon_or_tool") or "") if inferred.get("skill_code") in ATTACK_SKILLS else "",
        "social": False,
        "npc_ref": npc_ref_of(person),
        "attack": {"code": str(person.get("code") or ""), "name": str(person.get("name") or "")},
    }


# ---------------------------------------------------------------------------
# Whom the player's line can mean (the candidate list; unnamed T3, unnamed2 T3/T4)
# ---------------------------------------------------------------------------
#
# 'i shoot the nearest ghoul' was aimed at Tunde Iqbal, the one named person
# here, and 'i shoot the closest ghoul' at Carlos Khan, a companion: the engine
# took the only person present as the target of any attack line. The line's
# own words decide instead. A named person is the target only when the line
# names them, or describes them (their job: "the doctor"; a person word: "the
# man", "the stranger"), or names no one ("i shoot him", "i attack"). A thing
# the line names that is none of these ("the ghoul") is a figure of that kind
# when one is here (app/unnamed.py: numbered rows), else nobody known.

# What opens a noun phrase the line acts on. Possessives are left out: "my
# crowbar" is the player's own thing, never the target.
_DETERMINERS = r"the|a|an|another|that|this|those|these|each|every|some|one|two|three|four|five|six|\d+"
# Grammar words that end a noun phrase ("the ghoul with my crowbar" -> "the ghoul").
_PHRASE_END = frozenset({
    "with", "at", "in", "on", "of", "to", "and", "or", "but", "for", "from", "into", "by", "as", "then",
    "who", "that", "which", "while", "before", "after", "until", "so", "if", "when", "where", "through",
    "toward", "towards", "against", "over", "under", "behind", "near", "beside", "about", "off", "up",
    "down", "out", "away", "back", "across", "along", "onto", "upon", "without", "because",
})
# A pronoun in the line means someone here: "i snap her neck", "i put a bullet in his head".
_PRONOUN_RE = re.compile(r"\b(?:him|her|his|hers|them|their|theirs|it|its)\b", re.I)
# Words that mean whoever is meant, beside world._FIGURE_NOUNS (the engine's person words).
_ANYONE_WORDS = frozenset({"guy", "gal", "lad", "lass", "bloke", "kid", "chap", "foe", "enemy", "attacker", "target"})
_PRONOUN_OBJECTS = frozenset({"him", "her", "them", "it", "himself", "herself", "itself", "themselves"})


def object_nouns(line: str) -> list[str]:
    """The head nouns of the line's noun phrases, singular: 'i shoot the nearest ghoul with my crowbar' -> ['ghoul'].

    A phrase opens on a determiner or a count and ends at a grammar word or
    punctuation; its last word is the noun. "at the sound, maybe ghouls" gives
    ["sound"]: the bare "ghouls" opens no phrase.
    """
    from app.interpreter import plain
    from app.unnamed import singular

    text = plain(line).lower()
    out: list[str] = []
    for match in re.finditer(rf"\b(?:{_DETERMINERS})\s+([a-z][a-z'’-]*(?:\s+[a-z][a-z'’-]*)*)", text):
        words: list[str] = []
        for word in match.group(1).split():
            if word in _PHRASE_END:
                break
            words.append(word)
        if words:
            noun = re.sub(r"['’]s?$", "", words[-1])
            if noun:
                out.append(singular(noun))
    return out


def _is_person_word(noun: str) -> bool:
    if noun in _ANYONE_WORDS:
        return True
    try:
        from app.world import _FIGURE_NOUNS

        return re.fullmatch(_FIGURE_NOUNS, noun, re.I) is not None
    except Exception:
        return False


def kind_figures(line: str, people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The living numbered figures whose kind the line names as a thing ("the ghoul", "another ghoul"), lowest number first."""
    from app.interpreter import is_dead
    from app.unnamed import numbered_name, singular

    nouns = set(object_nouns(line))
    if not nouns:
        return []
    out: list[dict[str, Any]] = []
    for person in people:
        if not isinstance(person, dict) or is_dead(person):
            continue
        _name, kind = numbered_name(person)
        if kind and singular(kind.lower()) in nouns:
            out.append(person)
    out.sort(key=lambda p: int(p.get("kind_number") or 0))
    return out


def line_may_target(line: str, person: dict[str, Any]) -> bool:
    """Whether the player's line can mean this person as the one attacked.

    Yes when the line names them (code, full name, or first name as a word),
    names no thing at all ("i shoot him", "i attack"), or names a thing that
    is them: a numbered figure's kind ("the ghoul"), a named person's job
    ("the doctor"), a word of their name, or a person word ("the man"). No
    when every thing the line names is something else ("the nearest ghoul"
    with only Tunde the hunter here).
    """
    from app.interpreter import line_names
    from app.unnamed import numbered_name, singular

    text = str(line or "")
    if not text.strip() or not isinstance(person, dict):
        return False
    if line_names(text, person):
        return True
    first = str(person.get("name") or "").split()[0] if str(person.get("name") or "").strip() else ""
    if len(first) >= 3 and re.search(rf"(?<!\w){re.escape(first)}(?!\w)", text, re.I):
        return True
    nouns = object_nouns(text)
    if not nouns or _PRONOUN_RE.search(text):
        return True
    _numbered, kind = numbered_name(person)
    if kind:
        return singular(kind.lower()) in nouns
    described = {singular(w) for w in re.findall(r"[a-z]+", f"{person.get('role') or ''} {person.get('name') or ''}".lower()) if len(w) >= 3}
    return any(noun in described or _is_person_word(noun) for noun in nouns)


def decide(
    model_input: str,
    context: dict[str, Any] | None,
    inferred: dict[str, Any] | None,
    ask: Ask | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The attack check for this line, or None, and the report of the asks.

    A blow the trigger tables already aimed at a person (an "attack" key, or a
    melee / ranged check with that person as its npc_ref) is not asked about
    again: it is marked as the attack on that person, when the line can mean
    them (line_may_target). When it cannot ('i shoot the nearest ghoul' aimed
    at the one named person here), the figure of the kind the line names is
    the target instead, and with none here the blow has no target from the
    trigger. Otherwise each person here the line can mean is asked about, and
    a confirmed target gets an attack check: the inferred melee / ranged check
    aimed at them when there was one (returned with "replaces_inferred"), else
    a new one.
    """
    started = time.time()
    report: dict[str, Any] = {"asks": [], "unconfirmed": [], "target": None}
    inferred = inferred if isinstance(inferred, dict) else None
    try:
        line = player_line(model_input)
        people = people_here(context)
        if inferred and inferred.get("skill_code") in ATTACK_SKILLS:
            ref = inferred.get("npc_ref") if isinstance(inferred.get("npc_ref"), dict) else {}
            if ref.get("code"):
                person = next(
                    (p for p in people if str(p.get("code") or "").upper() == str(ref.get("code")).upper()), None
                ) or {**ref, "name": _clean(ref.get("name"))}
                if line_may_target(line, person):
                    inferred["attack"] = {"code": str(ref.get("code")), "name": _clean(ref.get("name"))}
                    report["target"] = inferred["attack"]
                    report["from"] = "trigger"
                    return None, report
                # The one named person here is not whom the line shoots at.
                report["not_the_lines"] = {"code": str(ref.get("code")), "name": _clean(ref.get("name"))}
                inferred["npc_ref"] = None
                inferred["opposition"] = None
                figures = kind_figures(line, people)
                if figures:
                    check = attack_check(figures[0], inferred, context)
                    check["replaces_inferred"] = True
                    report["target"] = check["attack"]
                    report["skill"] = check["skill_code"]
                    report["from"] = "kind"
                    return check, report
        if ask is None:
            report["skipped"] = "no_model"
            return None, report
        # The people the line can mean, the figures of the kind it names first.
        figures = kind_figures(line, people)
        people = [*figures, *[p for p in people if line_may_target(line, p) and p not in figures]]
        report["people"] = [p.get("code") for p in people]
        target = find_target(line, people, ask, report)
        if target is None:
            return None, report
        check = attack_check(target, inferred, context)
        report["target"] = check["attack"]
        report["skill"] = check["skill_code"]
        if inferred and inferred.get("skill_code") in ATTACK_SKILLS:
            check["replaces_inferred"] = True
        return check, report
    except Exception as exc:  # never break a turn
        report["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return None, report
    finally:
        report["seconds"] = round(time.time() - started, 3)


def attack_target(check: dict[str, Any] | None) -> str:
    """The code of the person a resolved check attacked, or ""."""
    if not isinstance(check, dict):
        return ""
    attack = check.get("attack") if isinstance(check.get("attack"), dict) else {}
    return str(attack.get("code") or "").strip().upper()


# What an attack roll's degree means for the blow, in the engine's own combat
# outcomes (world._resolve_player_attack: hit, glancing_hit, miss). One roll
# decides the attack: the combat math follows it (world._combat_follows_attack_check)
# and so does the line the engine adds when the prose leaves the target out.
LANDS = {
    "critical_success": "hit",
    "success": "hit",
    "partial": "glancing_hit",
    "failure": "miss",
    "critical_failure": "miss",
}
_LANDS_WORDS = {"hit": "hits", "glancing_hit": "only grazes", "miss": "misses"}


def lands(check: dict[str, Any] | None) -> str:
    """hit, glancing_hit or miss for a rolled attack check, else ""."""
    if not isinstance(check, dict) or check.get("natural") is None or not attack_target(check):
        return ""
    return LANDS.get(str(check.get("outcome") or ""), "")


def outcome_line(check: dict[str, Any] | None, label: str) -> str:
    """The attack's outcome as one plain line: "Your shot hits Vasilis [[B]]." ("" when it is no rolled attack)."""
    landed = lands(check)
    label = str(label or "").strip()
    if not landed or not label:
        return ""
    skill = check.get("skill") if isinstance(check.get("skill"), dict) else {}
    code = str(skill.get("code") or check.get("skill_code") or "")
    noun = "shot" if code == "ranged" else "blow"
    return f"Your {noun} {_LANDS_WORDS[landed]} {label}."
