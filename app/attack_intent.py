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


def _places_here(context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The place records the context carries (the player's place and the known places), for line_may_target."""
    ctx = context if isinstance(context, dict) else {}
    out: list[dict[str, Any]] = []
    here = ctx.get("current_location")
    if isinstance(here, dict):
        out.append(here)
    out.extend(p for p in ctx.get("locations") or [] if isinstance(p, dict))
    return out


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
# here, and 'i shoot the closest ghoul' at Carlos Khan, a companion, while the
# ghouls were on the roster: the engine took the only person present as the
# target of any attack line. The line's own words decide instead, by what the
# engine knows. A person is meant when the line names them (their code, any
# word of their name that is not a title: "Theo" for Dr. Theo, "Sam" for Old
# Sam, "Iqbal", "Theo's"), or names a thing that is them (a figure's kind
# column: "the ghoul"; a person's job: "the doctor"). A person is NOT meant
# only on positive evidence that the thing the line names is something else:
# another living figure's kind here, another person's job, or nothing named
# but a place or scenery the engine knows is never a person (a door, a lock). Any
# other noun ("the bastard", "the creep", "the thing", "the doc", "the merc")
# leaves the person a possible target, as the trigger tables aimed it: a
# noun's absence from a list is never evidence (round 2 kept a person-word
# list and refused 'i shoot the bastard' at the one person present).

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
# Scenery the engine never takes for a person (world._NAME_SCENERY_RE: door, gate,
# window, ...) and the two fixtures the live lines shot at ("the lock", "the sign").
_FIXTURE_WORDS = frozenset({"lock", "sign"})
# A pronoun for a person: the line means someone here ("i snap her neck", "i put a bullet in his head").
_PERSON_PRONOUN_RE = re.compile(r"\b(?:him|her|his|hers|them|their|theirs)\b", re.I)
_PRONOUN_OBJECTS = frozenset({"him", "her", "them", "it", "himself", "herself", "itself", "themselves"})


def object_nouns(line: str) -> list[str]:
    """The head nouns of the line's noun phrases, singular: 'i shoot the nearest ghoul with my crowbar' -> ['ghoul'].

    A phrase opens on a determiner or a count and ends at a grammar word,
    punctuation, the next determiner or a possessive ("the ghoul's head" is
    about the ghoul); its last word is the noun. "the ghouls and the raider"
    gives ["ghoul", "raider"]; "at the sound, maybe ghouls" gives ["sound"]:
    the bare "ghouls" opens no phrase.
    """
    return [p["head"] for p in noun_phrases(line)]


# Where a phrase's description after its head ends: a clause, an infinitive, a condition (grammar).
_DESCRIPTION_END = frozenset({"and", "then", "but", "or", "to", "so", "if", "while", "when", "because", "until",
                              "before", "after", "as", "unless"})
# What opens a description after the head: "the man in tattered robes", "the man with the scar"; a
# possessive after it is the player's own thing ("with my knife"), never the target's look.
_DESCRIPTION_OPENERS = frozenset({"in", "with", "by", "near", "at", "from", "on", "wearing", "under", "beside"})
_OWN_THINGS = frozenset({"my", "our", "your", "mine"})
_DESCRIPTION_MAX = 6
_NOT_DESCRIPTION = frozenset({
    "him", "her", "his", "hers", "them", "their", "its", "it", "me", "you", "us", "same", "other", "again",
})


def noun_phrases(line: str) -> list[dict[str, Any]]:
    """The line's noun phrases as object_nouns reads them, each with what describes it.

    {"head": singular noun, "description": the content words before the head
    and in the phrase after it ("the robed man in the office doorway" ->
    {"robed", "office", "doorway"}; "the black shape stirring in the Eel Pool"
    -> {"black", "stirring", "eel", "pool"}; the parts of an "eel-thing"),
    "start": token index}. Superlatives ("the nearest man") say where, not
    who, and are no description.
    """
    from app.interpreter import plain
    from app.unnamed import singular

    text = plain(line).lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9'’-]*|[^\sa-z0-9]", text)
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(tokens):
        if not _is_determiner(tokens[i]):
            i += 1
            continue
        words: list[str] = []
        j = i + 1
        while j < len(tokens) and re.fullmatch(r"[a-z][a-z'’-]*", tokens[j]) and tokens[j] not in _PHRASE_END \
                and not _is_determiner(tokens[j]):
            if words and _participle(tokens[j]) and j + 1 < len(tokens) and re.fullmatch(r"[a-z][a-z'’-]*", tokens[j + 1]):
                # A participle after the noun with its own words after it ends the phrase: "the dire
                # wolf circling us in the fog" is about the wolf (base100 T24 read "us"); "the ghoul
                # lunging at you" about the ghoul. "the old building" keeps its head.
                break
            words.append(tokens[j])
            j += 1
            if re.search(r"['’]s$", words[-1]):
                break
        if words:
            noun = re.sub(r"['’]s?$", "", words[-1])
            if noun:
                head = singular(noun)
                # An "eel-thing" is described by its own first part.
                described = [*words[:-1], *noun.split("-")[:-1], *_described_after(tokens, j)]
                out.append({"head": head, "start": i, "description": _content_words(described)})
        i = max(j, i + 1)
    return out


def _described_after(tokens: list[str], j: int) -> list[str]:
    """The words after a head that describe it: a participle or a description opener and what follows, to the clause's end."""
    if j >= len(tokens) or not re.fullmatch(r"[a-z][a-z'’-]*", tokens[j]):
        return []
    if not (_participle(tokens[j]) or tokens[j] in _DESCRIPTION_OPENERS):
        return []
    out: list[str] = []
    for tok in tokens[j: j + _DESCRIPTION_MAX]:
        if not re.fullmatch(r"[a-z][a-z'’-]*", tok) or tok in _DESCRIPTION_END or tok in _OWN_THINGS:
            break
        out.append(tok)
    return out


def _content_words(words: list[str]) -> set[str]:
    """The words of a description that say what a thing looks like: no grammar word, determiner or superlative."""
    from app.unnamed import singular

    out: set[str] = set()
    for word in words:
        w = re.sub(r"['’]s?$", "", str(word or "").lower())
        if (len(w) < 3 or w in _PHRASE_END or w in _NOT_DESCRIPTION or _is_determiner(w) or w in _DESCRIPTION_OPENERS
                or (w.endswith("est") and len(w) > 5)):
            continue
        out.add(singular(w))
    return out


_DETERMINER_WORDS = frozenset(_DETERMINERS.split("|")) - {r"\d+"}
# Where one act of the line ends and another begins (grammar, as app/unnamed.player_objects splits).
_LINE_CLAUSE_RE = re.compile(r"[,;:.!?]|\b(?:and|then|but)\b", re.I)


def _is_determiner(token: str) -> bool:
    return token in _DETERMINER_WORDS or token.isdigit()


def _participle(token: str) -> bool:
    """An -ing verb form: a vowel in its stem ("circling", "lunging"; not "thing", "king", "ping")."""
    low = str(token or "").lower()
    return low.endswith("ing") and len(low) > 5 and bool(re.search(r"[aeiouy]", low[:-3]))


def attack_clauses(line: str) -> list[str]:
    """The clauses of the player's line that hold the blow, by the engine's own trigger tables; [] when the whole line is one.

    "I ignore Orabel and slash at the dire wolf circling us in the fog"
    (base100 T24): the blow is "slash at the dire wolf ..."; Orabel stands in
    the clause the line ignores her in. The melee and ranged patterns of
    skill_checks.SKILL_TRIGGER_PATTERNS, which rolled the check, say which
    clause it was read from. Empty when no clause matches on its own or every
    clause does (one act, or the tables did not fire): the whole line is read.
    """
    from app.interpreter import plain

    text = plain(line)
    clauses = [c.strip() for c in _LINE_CLAUSE_RE.split(text) if c and c.strip()]
    if len(clauses) < 2:
        return []
    try:
        from app.skill_checks import SKILL_TRIGGER_PATTERNS, _trigger_text_variants

        patterns = [p for p, code in SKILL_TRIGGER_PATTERNS if code in ATTACK_SKILLS]
    except Exception:
        return []
    found: list[str] = []
    for clause in clauses:
        low = clause.lower()
        try:
            variants = _trigger_text_variants(low, protect_others=False)
        except Exception:
            variants = [low]
        if any(re.search(p, v) for p in patterns for v in variants):
            found.append(clause)
    return found if 0 < len(found) < len(clauses) else []


def _title_words() -> frozenset[str]:
    """The titles a roster name may open on (world._TITLE_WORDS, #163: "Dr. Theo" is Theo), lower case, no dot."""
    try:
        from app.world import _TITLE_WORDS

        return frozenset(_TITLE_WORDS)
    except Exception:
        try:
            from app.narration_pipeline import _TITLE_ABBREVIATIONS

            return frozenset(t.lower() for t in _TITLE_ABBREVIATIONS)
        except Exception:
            return frozenset()


def name_words(person: dict[str, Any]) -> list[str]:
    """The words of a roster name that name the person: the titles in front taken off ("Dr. Theo" -> ["Theo"],
    "Old Sam" -> ["Sam"], "Tunde Iqbal" -> ["Tunde", "Iqbal"]); a lone word is left alone; numbers and two-letter
    words are not names. A figure still under its number ("Ghoul 1") has no name words: it is meant by its kind
    (two ghouls share the word, and "the ghoul" is one of them, lowest first: kind_figures)."""
    from app.unnamed import numbered_name

    if numbered_name(person)[0]:
        return []
    words = [w.strip(".,;:'’\"") for w in _clean(person.get("name")).split()]
    words = [w for w in words if w]
    titles = _title_words()
    while len(words) > 1 and words[0].lower() in titles:
        words.pop(0)
    return [w for w in words if len(w) >= 3 and not w.isdigit()]


def line_names_person(line: str, person: dict[str, Any]) -> bool:
    """The player's line names this person: their code (@A, [[A]]), their whole name, or any word of it as a word
    ("Theo", "Theo's", "Iqbal"; never "Theo" inside "Theodora")."""
    from app.interpreter import line_names

    text = str(line or "")
    if line_names(text, person):
        return True
    return any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.I) for word in name_words(person))


def _kind_of(person: dict[str, Any]) -> str:
    """The figure's kind from the row's kind column, its head noun singular and lower ("Dire Wolf 1" -> "wolf"); "" for a named person."""
    from app.unnamed import kind_head

    return kind_head(person.get("kind"))


def _kinds_of(person: dict[str, Any]) -> set[str]:
    """The kind column as the line may name it: its head and the whole ("wolf", "dire wolf").

    A creature row of any kind is also "the creature", "the animal", "the
    beast" (unnamed.VAGUE_CREATURES): Creature 1 is "the snarling animal".
    """
    from app.unnamed import VAGUE_CREATURES, _person_kind, singular

    kind = str(person.get("kind") or "").strip().lower()
    out = {_kind_of(person), singular(kind) if kind else ""} - {""}
    if out and not _person_kind(kind):
        out |= VAGUE_CREATURES
    return out


def shown_kinds(*texts: Any, people: list[dict[str, Any]] | None = None) -> set[str]:
    """The creature kinds these texts (the last turn's prose, the player's line, this turn's) show attacking; see unnamed.shown_kinds.

    The names of ``people`` are never a kind ("The kitchen hand Orabel watches you").
    """
    try:
        from app.unnamed import shown_kinds as _shown

        names = {w for p in people or [] if isinstance(p, dict)
                 for w in re.findall(r"[a-z]+", str(p.get("name") or "").lower())}
        return _shown(*texts, names=names)
    except Exception:
        return set()


def _role_family(person: dict[str, Any]) -> set[str]:
    """Every word the engine has for this person's job: the role's own words and its job family (app/shifts).

    A kitchen hand is called "the cook"; a hired gun "the merc". The shift
    templates group the jobs that are one job under different names, so a
    word of the family is a plausible word for the person.
    """
    from app.shifts import job_of, job_words
    from app.unnamed import singular

    role = job_of(person.get("role"))
    out = {singular(w) for w in re.findall(r"[a-z]+", role.lower())}
    for job in job_words(role):
        out.add(singular(job))
        out |= {singular(w) for w in job.split()}
    return out - {""}


def plausible_word(person: dict[str, Any], noun: str) -> bool:
    """Whether a thing-noun the line or the prose uses may mean this person: their kind, or a word of their job."""
    return noun in _kinds_of(person) or noun in _role_family(person)


def creature_evidence(shown: set[str] | None, people: list[dict[str, Any]] | None) -> set[str]:
    """The shown kinds that are plausible for no one present: positive evidence of a creature with no row.

    A shown kind is evidence against a person present only when it is not a
    word for them (CLAUDE.md: a noun's absence from a list is never evidence;
    the one person present takes a noun the engine knows nothing about, as
    4833150 decided). "the cook" with Orabel the kitchen hand here, "the merc"
    with Grit the hired gun, are words for them, not creatures.
    """
    return {k for k in shown or () if not any(plausible_word(p, k) for p in people or [] if isinstance(p, dict))}


def line_antecedents(line: str) -> set[str]:
    """The kinds a "them" in the line refers back to: a plural the line itself named before it.

    "Marsh rats come at me out of the reeds; I kick and slash at them" (base100
    T60): "them" is the rats of the line's own first clause, never someone
    present. Empty when the line has no "them", or no plural before it.
    """
    from app.interpreter import plain
    from app.unnamed import is_plural, mentions, singular

    text = plain(line)
    hit = re.search(r"\b(?:them|they|their|theirs)\b", text, re.I)
    if not hit:
        return set()
    before = text[: hit.start()]
    out: set[str] = set()
    for m in mentions(before):
        if m["subject"] and is_plural(m["noun"]):
            out.add(m["kind"])
            if m.get("full"):
                out.add(m["full"])
    plural_words = {singular(w) for w in re.findall(r"[a-z]+", before.lower()) if is_plural(w)}
    out |= set(object_nouns(before)) & plural_words
    return out - {""}


# ---------------------------------------------------------------------------
# A body that is no one present (F192: sonnet100 T74, T93-T94)
# ---------------------------------------------------------------------------
#
# Filing a creature needs it shown closing on someone (unnamed.shown_kinds:
# it keeps the fog and the weather out). Clearing a person present of a blow
# needs less: that the thing the blow names is a body, and no word for them.
# "stab at the eel-thing" with Delphine the herb gatherer here (T74: the eel
# was only shown diving), "the man in tattered robes ... ready to stab him"
# and "the robed man in the office doorway ... stab at him" with Elric the
# reeve's deputy here (T93-T94) all hit the one person present: the noun was
# one the engine knew nothing about, and 4833150 gives such a noun to the
# person. A hit on a person present is the worse error, so a body the line
# describes, or a creature the prose or the line shows, is evidence that the
# blow is not at them when nothing the engine has for them (their name, job,
# kind, record, the prose's sentences naming them) is in it. A bare "the
# bastard", "the thing", "the man" is still no evidence (4833150).

_SINGULAR_PRONOUN_RE = re.compile(r"\b(?:him|her|his|hers)\b", re.I)
_CODE_RE = re.compile(r"(?:@|\[\[)([A-Z]{1,3})\b")


def generic_body(noun: str) -> str:
    """"person" for a word that says only that it is someone ("man", "figure", "stranger"), "creature" for one that
    says only that it is a creature ("creature", "animal", "thing", an "eel-thing"), else ""."""
    from app.unnamed import VAGUE_CREATURES, _vague_words

    low = str(noun or "").lower()
    last = low.rsplit("-", 1)[-1]
    if low in VAGUE_CREATURES or low == "thing" or ("-" in low and (last in VAGUE_CREATURES or last == "thing")):
        return "creature"
    if low in _vague_words():
        return "person"
    return ""


def _words_for(person: dict[str, Any]) -> set[str]:
    """The thing-nouns that are a word for this person: their kind, their job and its family, their name's words."""
    from app.unnamed import singular

    return (_kinds_of(person) | _role_words(person)[1] | _role_family(person)
            | {singular(w.lower()) for w in name_words(person)}) - {""}


def _record_words(person: dict[str, Any], prose: str) -> set[str]:
    """Every word the engine has about this person: the row's own fields and the prose's sentences that name them.

    What they say is not what they are: quoted speech is left out ("'The Eel
    Pool,' Delphine says" does not make her an eel, T74).
    """
    from app.unnamed import singular

    fields = ("name", "role", "summary", "description", "appearance", "personality", "kind", "race", "notes")
    text = " ".join(str(person.get(k) or "") for k in fields)
    unquoted = re.sub(r"\"[^\"]*\"|“[^”]*”", " ", str(prose or ""))
    for sentence in re.split(r"(?<=[.!?])\s+", unquoted):
        if sentence and line_names_person(sentence, person):
            text += " " + sentence
    return {singular(w) for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 3}


def _creature_shown(*texts: Any) -> bool:
    """A body these texts show as only "a creature" doing something or seen ("The creature growls", "the creature dove")."""
    from app.unnamed import mentions

    for text in texts:
        if not str(text or "").strip():
            continue
        try:
            found = mentions(str(text))
        except Exception:
            continue
        if any((m["subject"] or m["seen"]) and generic_body(m["kind"]) == "creature" for m in found):
            return True
    return False


def _sex_of_word(noun: str) -> str:
    """"male" for "man", "fellow"; "female" for "woman", "crone"; "" for "figure", "stranger" (world._hint_sex)."""
    try:
        from app.world import _hint_sex

        return _hint_sex(f"a {noun}", "")
    except Exception:
        return ""


def _sex_conflict(person: dict[str, Any], noun: str) -> bool:
    """The row's own sex says the word is not them: "the man" for a woman on record."""
    sex = str(person.get("sex") or "").strip().lower()
    word = _sex_of_word(noun)
    return bool(sex in {"male", "female"} and word and sex != word)


def bodies_not(person: dict[str, Any], line: str, prose: str = "",
               people: list[dict[str, Any]] | None = None) -> set[str]:
    """The thing-nouns of the line that are a body and no word for this person: positive evidence the blow is not at them.

    A body is a word that says only that it is someone or a creature
    (generic_body: "man", "shape", "creature", "eel-thing") and is no word
    for this person (_words_for: a creature row is "the creature").

    A creature word is not a person when the line says anything of it ("the
    eel-thing", T74; "the snarling creature", T48), or the last turn's prose
    or the line shows a creature doing something.

    A word for someone ("the man in tattered robes", T93; "the robed man in
    the office doorway", T94) is not this person when the line names them
    elsewhere ("this time ignoring Elric": they are not called "the man"),
    when their row's sex is not the word's, or when it is ambiguous: another
    living person here fits it as well (CLAUDE.md, rosters: an ambiguous
    match resolves to nothing). A description in the line that is in some
    rows' records (_record_words) fits those rows only.

    None for "the bastard", a bare "the thing" with no creature shown, or
    "the old man" with one person here (4833150).
    """
    if not isinstance(person, dict):
        return set()
    own = _words_for(person)
    code = str(person.get("code") or "").strip().upper()
    others = [o for o in people or [] if isinstance(o, dict) and str(o.get("code") or "").strip().upper() != code
              and not _is_dead_row(o)]
    records: dict[int, set[str]] = {}

    def record(row: dict[str, Any]) -> set[str]:
        key = id(row)
        if key not in records:
            records[key] = _record_words(row, prose)
        return records[key]

    shown: bool | None = None
    out: set[str] = set()
    for phrase in noun_phrases(line):
        head = phrase["head"]
        generic = generic_body(head)
        if not generic or head in own:
            continue
        described = phrase["description"]
        if generic == "creature":
            if described:
                out.add(head)
                continue
            if shown is None:
                shown = _creature_shown(prose, line)
            if shown:
                out.add(head)
            continue
        # A word for someone.
        if line_names_person(line, person) or _sex_conflict(person, head):
            out.add(head)
            continue
        if any(head in _words_for(other) for other in others):
            out.add(head)
            continue
        fit_others = [other for other in others if not _sex_conflict(other, head)]
        if described:
            matched = [row for row in [person, *fit_others] if described & record(row)]
            if matched:
                if person not in matched:
                    out.add(head)
                continue
        if fit_others:
            out.add(head)
    return out


def _is_dead_row(row: dict[str, Any]) -> bool:
    try:
        from app.interpreter import is_dead

        return bool(is_dead(row))
    except Exception:
        return False


def pronoun_reads(line: str, person: dict[str, Any], people: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Each him / her / his / hers in the line and whether it may be this person.

    A pronoun is the line's own antecedent when the line gave it one: "shout
    at the man in tattered robes to let go of @R, ready to stab him" (T93)
    has "him" for the man (or Edmund), never for Elric. It may be this person
    when the line names them or a word for them before it, or names no one
    and no body before it (cc87dd29 T5: "i snap her neck"). Each: {"at":
    offset in the plain line, "may": bool, "antecedents": the body nouns
    before it that are not them}.
    """
    from app.interpreter import plain

    text = plain(line)
    own = _words_for(person) if isinstance(person, dict) else set()
    code = str((person or {}).get("code") or "").strip().upper()
    out: list[dict[str, Any]] = []
    for hit in _SINGULAR_PRONOUN_RE.finditer(text):
        before = text[: hit.start()]
        heads = [p["head"] for p in noun_phrases(before)]
        if line_names_person(before, person) or any(h in own for h in heads):
            out.append({"at": hit.start(), "may": True, "antecedents": set()})
            continue
        others = {h for h in heads if generic_body(h)}
        for other in people or []:
            if not isinstance(other, dict) or str(other.get("code") or "").strip().upper() == code:
                continue
            others |= {h for h in heads if h in _words_for(other)}
        named_other = any(c.upper() != code for c in _CODE_RE.findall(before)) or any(
            isinstance(o, dict) and str(o.get("code") or "").strip().upper() != code and line_names_person(before, o)
            for o in people or [])
        out.append({"at": hit.start(), "may": not (others or named_other), "antecedents": others})
    return out


def _role_words(person: dict[str, Any]) -> tuple[str, set[str]]:
    """The role as a phrase and its head noun, singular: "ghoul hunter" -> ("ghoul hunter", {"hunter"}).

    A role is matched on its head noun, never on every word in it: a "ghoul
    hunter" is "the hunter", not "the ghoul" (the kind of a figure is its kind
    column, never a word of someone else's job).
    """
    from app.unnamed import singular

    words = re.findall(r"[a-z]+", str(person.get("role") or "").lower())
    if not words:
        return "", set()
    return " ".join(words), {singular(words[-1])}


def _place_heads(places: list[dict[str, Any]] | None) -> set[str]:
    from app.unnamed import singular

    out: set[str] = set()
    for place in places or []:
        if not isinstance(place, dict):
            continue
        words = re.findall(r"[a-z]+", str(place.get("name") or "").lower())
        if words and len(words[-1]) >= 3:
            out.add(singular(words[-1]))
    return out


def _is_fixture(noun: str) -> bool:
    if noun in _FIXTURE_WORDS:
        return True
    try:
        from app.world import _NAME_SCENERY_RE

        return _NAME_SCENERY_RE.fullmatch(noun) is not None
    except Exception:
        return False


def kind_figures(line: str, people: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The living numbered figures whose kind the line names as a thing ("the ghoul", "another ghoul"), lowest number first."""
    from app.interpreter import is_dead
    from app.unnamed import numbered_name

    nouns = set(object_nouns(line))
    if not nouns:
        return []
    out: list[dict[str, Any]] = []
    for person in people:
        if not isinstance(person, dict) or is_dead(person):
            continue
        _name, kind = numbered_name(person)
        if kind and _kinds_of(person) & nouns:
            out.append(person)
    out.sort(key=lambda p: int(p.get("kind_number") or 0))
    return out


def unknown_creature(line: str, people: list[dict[str, Any]] | None, shown: set[str] | None) -> str:
    """The thing the line's blow names that the prose has shown acting and no one here is: "wolf", or "".

    Positive evidence that the blow is at something other than the people
    present (base100 T23-T24: "the dire wolf" with the wolf shown lunging the
    turn before and no row for it), read from the attack's own clauses.
    """
    text = str(line or "")
    if not text.strip() or not shown:
        return ""
    evidence = creature_evidence(shown, people)
    if not evidence:
        return ""
    focus = " ".join(attack_clauses(text)) or text
    for noun in [*object_nouns(focus), *object_nouns(text), *sorted(line_antecedents(text))]:
        if noun in evidence:
            return noun
    return ""


def unknown_body(line: str, people: list[dict[str, Any]] | None, prose: str = "") -> str:
    """The body the line's blow names that is no one here (bodies_not for each person present): "eel-thing", or "".

    sonnet100 T74 "stab at the eel-thing", T93-T94 "the man in tattered
    robes ... stab him": the blow is at something the engine has no row for,
    and no person present takes it. The blow's own clauses first, then the
    line, then a him / her's antecedent there.
    """
    text = str(line or "")
    here = [p for p in people or [] if isinstance(p, dict)]
    if not text.strip() or not here:
        return ""
    focus = " ".join(attack_clauses(text)) or text
    antecedents: list[str] = []
    for read in pronoun_reads(text, here[0], here):
        antecedents += sorted(read["antecedents"])
    for noun in [*object_nouns(focus), *object_nouns(text), *antecedents]:
        if all(noun in bodies_not(p, text, prose, here) for p in here):
            return noun
    return ""


def line_may_target(
    line: str,
    person: dict[str, Any],
    people: list[dict[str, Any]] | None = None,
    places: list[dict[str, Any]] | None = None,
    shown: set[str] | None = None,
    prose: str = "",
) -> bool:
    """Whether the player's line can mean this person as the one attacked.

    Read from the attack's own clauses (attack_clauses) when the line has
    more than one act: "I ignore Orabel and slash at the dire wolf" names
    Orabel where it ignores her, and the blow names a wolf, so she is not
    whom it is at (base100 T24). Yes when the blow names them: their code,
    their whole name, or any word of their name that is not a title ("i shoot
    Theo in the chest" and "a bullet in Theo's head" for Dr. Theo; "Sam" for
    Old Sam; "Iqbal"). Yes when a thing it names ("the X") is them: their
    kind column ("the ghoul" for Ghoul 1, "the wolf" or "the dire wolf" for
    Dire Wolf 1) or the head noun of their job ("the doctor", "the hunter"
    for a ghoul hunter). No only on positive evidence that the thing named is
    something else: the kind of another living figure in ``people`` ("the
    ghoul" with Ghoul 1 here, for Tunde or for Carlos the ghoul hunter),
    another person's job there ("the doctor" for the ghoul, with Chiara the
    doctor here), a creature the prose has shown acting and no one here is
    (``shown``, from unnamed.shown_kinds over the last turn's prose and this
    one's: "the dire wolf" with the wolf shown lunging, base100 T23), or
    nothing named but a place in ``places`` or scenery the engine knows is
    never a person ("the lock", "at the clinic"; "the man by the gate" is at
    the man). Anything else, a person pronoun, no thing at all, or a noun
    the engine knows nothing about ("the bastard", "the creep", "the doc",
    "the merc"), leaves them a possible target, as the trigger tables aimed it.

    Also no on a body the blow names that is no word for them (bodies_not,
    over the line and ``prose``, the last turn's: "the eel-thing", "the man
    in tattered robes", "the creature" after "The creature growls"; F192),
    and a him / her the line gave its own antecedent ("the man ... stab him")
    is that antecedent, not them (pronoun_reads).
    """
    text = str(line or "")
    if not text.strip() or not isinstance(person, dict):
        return False
    from app.interpreter import is_dead

    phrase, heads = _role_words(person)
    own = (_kinds_of(person) | heads) - {""}
    # What the engine knows a thing-noun to be that is not this person: another living figure's
    # kind or job here, or a creature shown attacking that is a word for no one present
    # (creature_evidence: "the cook" with Orabel the kitchen hand here is a word for her).
    code = str(person.get("code") or "").strip().upper()
    elsewhere: set[str] = set()
    for other in people or []:
        if not isinstance(other, dict) or other is person or is_dead(other):
            continue
        if code and str(other.get("code") or "").strip().upper() == code:
            continue
        elsewhere |= _kinds_of(other)
        elsewhere |= _role_words(other)[1]
    elsewhere.discard("")
    evidence = (elsewhere | creature_evidence(shown, [person, *(people or [])]) | bodies_not(person, text, prose, people)) - own
    scenery = _place_heads(places)
    antecedents = line_antecedents(text)
    clauses = attack_clauses(text)
    focus = " ".join(clauses)
    # him / her / his / hers: whether each may be this person, and the bodies the line gave them.
    from app.interpreter import plain

    reads = pronoun_reads(text, person, people)
    plain_text = plain(text)
    spans = [(plain_text.find(c), plain_text.find(c) + len(c)) for c in clauses if plain_text.find(c) >= 0]
    in_focus = [r for r in reads if any(a <= r["at"] < b for a, b in spans)]
    them_re = r"\b(?:them|their|theirs)\b"
    if focus:
        # The blow is one act of several. Named or meant by a pronoun only in another act ("I ignore
        # Orabel and ...", "I shout at @E to get back, then stab at ..."), while the blow itself is at
        # a thing the engine knows is not them: not whom it is at. A thing it knows nothing about
        # ("I turn to Orabel and stab the bastard", "I push past Mira and stab the doc") decides
        # nothing, as in one act.
        in_blow = line_names_person(focus, person) or re.search(them_re, focus, re.I) or any(
            r["may"] for r in in_focus)
        aside = line_names_person(text, person) or re.search(them_re, text, re.I) or any(r["may"] for r in reads)
        blow_nouns = set(object_nouns(focus))
        if re.search(r"\b(?:them|they|their|theirs)\b", focus, re.I):
            blow_nouns |= antecedents
        for r in in_focus:
            blow_nouns |= r["antecedents"]
        blow_nouns -= own
        if aside and not in_blow and blow_nouns and (
            blow_nouns & evidence or all(n in scenery or _is_fixture(n) for n in blow_nouns)
        ):
            return False
    if line_names_person(text, person):
        return True
    nouns = set(object_nouns(text)) | antecedents
    for r in reads:
        nouns |= r["antecedents"]
    if not nouns:
        return True
    if nouns & own or (" " in phrase and re.search(rf"\b{re.escape(phrase)}s?\b", text, re.I)):
        return True
    # A person pronoun means someone here, whatever else the line goes on to name ("i snap her neck
    # and burn the clinic", cc87dd29 T5); "it" / "its" is a creature's or a thing's and decides
    # nothing, and a "them" the line's own earlier plural answers for is that plural ("Marsh rats
    # come at me out of the reeds; I kick and slash at them", base100 T60). A him / her the line
    # gave its own body ("the man in tattered robes ... ready to stab him", T93) is that body.
    if (re.search(them_re, text, re.I) and not antecedents) or any(r["may"] for r in reads):
        return True
    if nouns & evidence:
        return False
    # A place or scenery is where the shot goes only when nothing else is named: "the lock", "at the
    # clinic"; "the man by the gate" is at the man.
    if all(n in scenery or _is_fixture(n) for n in nouns):
        return False
    return True


Minter = Callable[[str], Any]


def decide(
    model_input: str,
    context: dict[str, Any] | None,
    inferred: dict[str, Any] | None,
    ask: Ask | None,
    minter: Minter | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The attack check for this line, or None, and the report of the asks.

    A blow the trigger tables already aimed at a person (an "attack" key, or a
    melee / ranged check with that person as its npc_ref) is not asked about
    again: it is marked as the attack on that person, when the line can mean
    them (line_may_target). When it cannot ('i shoot the nearest ghoul' aimed
    at the one named person here), the figure of the kind the line names is
    the target instead; with none here and the thing named a creature the
    last turn's prose shows acting (context["last_narration"]; base100 T23
    "the dire wolf"), ``minter(kind)`` (the engine's unnamed.mint_shown) files
    it and the blow is aimed at the new row; else the blow has no target from
    the trigger, and the report names the noun ("unknown_noun"). Otherwise each
    person here the line can mean is asked about, and a confirmed target gets
    an attack check: the inferred melee / ranged check aimed at them when
    there was one (returned with "replaces_inferred"), else a new one.
    """
    started = time.time()
    report: dict[str, Any] = {"asks": [], "unconfirmed": [], "target": None}
    inferred = inferred if isinstance(inferred, dict) else None
    try:
        line = player_line(model_input)
        people = people_here(context)
        ctx = context if isinstance(context, dict) else {}
        # The creatures shown attacking: by the last turn's prose, or by the player's own line.
        shown = shown_kinds(ctx.get("last_narration"), line, people=people)
        prose = str(ctx.get("last_narration") or "")
        if inferred and inferred.get("skill_code") in ATTACK_SKILLS:
            ref = inferred.get("npc_ref") if isinstance(inferred.get("npc_ref"), dict) else {}
            if ref.get("code"):
                person = next(
                    (p for p in people if str(p.get("code") or "").upper() == str(ref.get("code")).upper()), None
                ) or {**ref, "name": _clean(ref.get("name"))}
                if line_may_target(line, person, people=people, places=_places_here(context), shown=shown, prose=prose):
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
                # A creature shown attacking, else a body the line or the prose shows that is no one here
                # (F192: "the eel-thing", "the man in tattered robes"); minted only when shown attacking.
                noun = unknown_creature(line, people, shown) or unknown_body(line, people, prose)
                if noun:
                    report["unknown_noun"] = noun
                    minted = minter(noun) if minter is not None else None
                    if isinstance(minted, dict) and minted.get("code"):
                        check = attack_check(minted, inferred, context)
                        check["replaces_inferred"] = True
                        report["target"] = check["attack"]
                        report["skill"] = check["skill_code"]
                        report["from"] = "minted"
                        return check, report
                    # The roll stands with no target: no bystander takes it, and no line names one.
                    return None, report
        if ask is None:
            report["skipped"] = "no_model"
            return None, report
        # The people the line can mean, the figures of the kind it names first.
        figures = kind_figures(line, people)
        places = _places_here(context)
        here = people
        people = [*figures, *[p for p in people if line_may_target(line, p, people=here, places=places, shown=shown,
                                                                   prose=prose) and p not in figures]]
        report["people"] = [p.get("code") for p in people]
        if here and not people:
            # Everyone present is cleared of the blow: say what it named (attack_target_unknown_noun).
            noun = unknown_creature(line, here, shown) or unknown_body(line, here, prose)
            if noun:
                report["unknown_noun"] = noun
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
