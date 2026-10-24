"""The engine writes the attack's result line (#129, #186; CLAUDE.md, Design decisions, 2026-10-24).

Stell's decision ("Transactions and items are read by their own agent", on
attacks): the roll comes first, the engine writes the attack's result line
itself from the roll and the weapon, the narrator writes the scene around it,
and when the draft leaves the line out or contradicts it the engine puts its
own line in. No model rewrite, no extra model call, no new narrator text, and
never a sentence dropped: the line is only ever inserted (CLAUDE.md: a trim
is last, and only for what breaks the game; round 1's one-sentence replace
deleted the ghoul's counterattack and the player's dodge).

Every rolled attack gets the line: a melee or ranged check the engine rolled
with an attack target (app/attack_intent.py marks it), or such a check with no
target when the player's line names one the records now hold (merge1 T4, F186:
'i shoot the closest ghoul' rolled before the ghouls were on the roster). A
hit the engine never applied is not written: an untargeted roll is resolved
against the row first (``resolve``, the combat math following the check), and
with nothing to resolve against there is no line.

Whether the draft already shows the outcome is read by the engine, by grammar:

* An attack sentence is one where the player acts with an attack word
  ("you ... shoot", "you squeeze the trigger", "you miss") or one that opens
  on what the player sent ("The bullet ...", "Your blow ..."). Its passage is
  that sentence and the next two of its paragraph, stopping before a sentence
  where the player attacks someone else.
* Only a clause whose subject is the player's attack or what it sent states
  the outcome: "you", "your shot", "the bullet", "your knuckles", or a clause
  carrying that subject on ("... and miss the ghoul", "It streaks ...,
  striking Nate"). The target's own acts ("It rakes its claws and hits you"),
  the player's defence ("you dodge its claws"), a description ("its dead
  eyes"), a passive ("you are struck") and quoted speech ("You missed!")
  never count.
* The clause's object must be the target (its code, a name only it has, or
  its kind when it is the only living one of that kind here), a pronoun, or
  nothing. "you hit the ground", "hits the ghoul [[E]]" for a roll at [[D]],
  and "passes wide of the mark" state nothing about this attack. With two
  attacks rolled this turn a clause with no object counts only where the
  target is named.
* Shown: the last such clause agrees with the roll's band. Nothing changes.
* Contradicted: it states the opposite (a miss on a success, a hit or a kill
  on a failure). The line goes in after the passage and the prose stays; the
  death itself is for the refused-death path (app/interpreter.py).
* Not shown: the line goes after the attack sentence, else after the first
  sentence that names the target, else after the player's last act, else at
  the end (before a closing question).

Every insertion and "already shown" is noted in the turn ledger; the summary
carries the line (interpreter.summary).
"""
from __future__ import annotations

import random
import re
from typing import Any

HIT = "hit"
GRAZE = "glancing_hit"
MISS = "miss"

# What the roll's band allows a clause to say; anything else is the opposite.
AGREES = {HIT: {HIT}, GRAZE: {GRAZE, HIT}, MISS: {MISS}}

# The words a scene uses for an attack (an act or what it sent). Grammar decides
# whose act it is (below): these alone never make an attack sentence.
_ATTACK = (
    r"shoot|shoots|shooting|shot|shots|fire|fires|fired|firing|trigger|squeeze|squeezes|"
    r"swing|swings|swung|stab|stabs|stabbed|slash|slashes|slashed|punch|punches|punched|"
    r"kick|kicks|kicked|thrust|thrusts|lunge|lunges|lunged|strike|strikes|struck|"
    r"hit|hits|miss|misses|missed|aim at|blow|blows|"
    # what the player's weapon does in the engine's own line ("Your crowbar lands on ...")
    r"lands|connects|catches|slams|finds its mark|grazes|glances|clips|nicks|goes wide|goes far wide|falls short"
)
_SENT = r"shot|bullet|round|bolt|arrow|blast|blow|strike|swing|punch|fist|blade|knife|slug|shell|beam"
# "you ... shoot" in one clause (no full stop or semicolon between), or a sentence opening on what was sent.
# "Your gaze lands on her" is no blow: the player's eyes, mind or breath never attack.
_NOT_A_BLOW = r"eyes?|gaze|look|attention|glance|mind|thoughts?|heart|breath|voice|words?|armor|armour|shield|shields"
_GAZE_RE = re.compile(rf"\b(?:your|his|her|their)\s+(?:{_NOT_A_BLOW})\b", re.I)
_ATTACK_RE = re.compile(
    rf"\b(?:you|your(?!\s+(?:{_NOT_A_BLOW})\b))\b[^.;!?]{{0,48}}?\b(?:{_ATTACK})\b", re.I
)
_SENT_RE = re.compile(rf"^\W*(?:the|your)\s+(?:\w+\s+)?(?:{_SENT})\b", re.I)

# Outcome words, longest first so "almost hit" is a miss. Only the attack's own
# doing: the target's evasion ("ducks", "sidesteps") and reaction ("staggers",
# "collapses") are the target's clauses and are never read (the subject rule).
_OUTCOMES: list[tuple[str, str]] = [
    (MISS, r"almost hit|nearly hit|barely miss\w*|falls? short|fell short|goes? wide|went wide|wide of|"
           r"miss|misses|missed|missing|whistles? past|whizz\w* past|harmlessly|no mark|thin air|off target"),
    (GRAZE, r"only grazes|graze[sd]?|grazing|nicks?|nicked|clips?|clipped|glances? off|glancing|scratch\w*"),
    (HIT, r"hits?|hitting|finds? (?:its|their|his|her) mark|struck|striking|slams? into|slammed into|"
          r"tears? into|tore into|punch\w* through|connects?|connected|lands? (?:on|square|hard|clean)|landed|"
          r"square in|catches|caught (?:him|her|it|them)|buries|sinks? into|sank into|wounds?|wounded|"
          r"drops? (?:him|her|it|them)|kills?|killed|dead"),
]
_OUTCOME_RE = re.compile(
    "|".join(f"(?P<{kind.replace('glancing_hit', 'graze')}{i}>\\b(?:{words})\\b)" for i, (kind, words) in enumerate(_OUTCOMES)),
    re.I,
)
_GROUP_KIND = {f"{kind.replace('glancing_hit', 'graze')}{i}": kind for i, (kind, _w) in enumerate(_OUTCOMES)}
# An outcome word after a determiner is a noun ("your armor takes the hit", "a miss").
_NOUN_BEFORE_RE = re.compile(r"\b(?:the|a|an|his|her|its|their|your|my|each|every|one|another)\s*$", re.I)

PASSAGE_SENTENCES = 3

# Clause joints: punctuation and the conjunctions that open a new clause.
_CLAUSE_SPLIT_RE = re.compile(r"\s*(?:;|,|—|–|\s+(?:and|but|then|as|while|before|after|until|so)\s+)\s*", re.I)
_PLAYER_WORDS = frozenset({"you", "you're", "you've", "you'd", "you'll", "you’re", "you’ve", "you’d", "you’ll"})
_PASSIVE_RE = re.compile(r"^you(?:'re|’re)?\s+(?:are|were|get|got|is)\b", re.I)
_OTHER_PRONOUNS = frozenset({"he", "she", "they", "his", "her", "their", "him", "them", "someone", "something", "nothing"})
_ELLIPSIS_RE = re.compile(r"^the\s+(?:first|second|third|fourth|next|other|last)\s+(\w+(?:\s+\w+)?)", re.I)
# Words an outcome phrase may run on with before its object ("lands square on", "harmlessly wide of").
_OBJECT_LEAD = frozenset({
    "on", "into", "through", "of", "at", "past", "in", "across", "toward", "towards", "with", "off", "from",
    "against", "wide", "short", "square", "hard", "clean", "true", "far", "just", "only", "barely", "home",
    "high", "low", "away", "back", "again", "twice", "once", "by",
})
_OBJECT_NP_RE = re.compile(r"^(?:the|a|an|that|this|those|these|his|her|its|their|some|another|one|two|three|\[\[|[A-Z])", re.I)
_OBJECT_PRONOUNS = frozenset({"him", "her", "it", "them", "his", "its", "their", "himself", "herself", "itself", "themselves"})
_OBJECT_PLAYER = frozenset({"you", "your", "yourself", "yours"})
_QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”|\"[^\"]*$|“[^”]*$")


def _outcomes_in(text: str) -> list[tuple[str, int, int]]:
    """(kind, start, end) of every outcome word in the text that is a verb, not a noun after "the" or "a"."""
    out: list[tuple[str, int, int]] = []
    for match in _OUTCOME_RE.finditer(str(text or "")):
        if _NOUN_BEFORE_RE.search(text[: match.start()]):
            continue
        out.append((_GROUP_KIND.get(match.lastgroup or "", ""), match.start(), match.end()))
    return out


def outcome_of(text: str) -> str:
    """The last outcome word in the text, as hit / glancing_hit / miss, or "" (no outcome stated)."""
    found = _outcomes_in(text)
    return found[-1][0] if found else ""


def is_attack_sentence(sentence: str, weapon: str = "") -> bool:
    """The player attacks in it ("you shoot", "you miss"), or it opens on what the player sent ("The bullet").

    Quoted words are someone speaking ("I need you to shoot straight."), never the act itself.
    """
    text = _QUOTED_RE.sub(" ", str(sentence or ""))
    if _ATTACK_RE.search(text) or _SENT_RE.search(text):
        return True
    word = _weapon_word(weapon)
    return bool(word and re.match(rf"^\W*(?:the|your)\s+(?:\w+\s+)?{re.escape(word)}\b", text, re.I))


def players_attack_sentence(sentence: str) -> bool:
    """The player acts in it with an attack word ("you shoot the raider"): a new act, not what a shot did."""
    return bool(_ATTACK_RE.search(_QUOTED_RE.sub(" ", str(sentence or ""))))


# ---------------------------------------------------------------------------
# The line itself: from the band, the weapon and the target, drawn from a pool
# ---------------------------------------------------------------------------

# {N} is what the player sent ("Your shot"), {T} the target's label. Every line
# reads as an attack sentence with an outcome word of its own band (so the
# engine's own line is "shown" when it reads the scene again).
_POOLS: dict[str, list[str]] = {
    "critical_success": ["{N} hits {T} hard and true.", "{N} lands square on {T}.", "{N} catches {T} full on.",
                         "{N} slams into {T}."],
    "success": ["{N} hits {T}.", "{N} lands on {T}.", "{N} connects with {T}.", "{N} finds its mark on {T}."],
    "partial": ["{N} only grazes {T}.", "{N} glances off {T}.", "{N} just clips {T}.", "{N} nicks {T}."],
    "failure": ["{N} misses {T}.", "{N} goes wide of {T}.", "{N} falls short of {T}.", "{N} misses {T} by a hair."],
    "critical_failure": ["{N} misses {T} badly.", "{N} goes far wide of {T}.", "{N} misses {T} by a long way.",
                         "{N} goes wide of {T}, nowhere near."],
}
_BAND_LANDS = {"critical_success": HIT, "success": HIT, "partial": GRAZE, "failure": MISS, "critical_failure": MISS}


def _weapon_word(weapon: str) -> str:
    text = re.sub(r"\s*\[\[[^\]]*\]\]", "", str(weapon or "")).strip(" .,;:")
    if not text or text.lower() in {"unarmed", "none", "fists", "hands", "bare hands"} or len(text) > 40:
        return ""
    return text[:1].lower() + text[1:] if not text[:2].isupper() else text


def senders(skill: str, weapon: str) -> list[str]:
    """What the line says the player sent: "Your shot", "The shot from your rifle", "Your crowbar", "Your fist"."""
    word = _weapon_word(weapon)
    if skill == "ranged":
        return ["Your shot", *([f"The shot from your {word}"] if word else [])]
    if word:
        return [f"Your {word}", f"Your blow with the {word}"]
    return ["Your blow", "Your fist", "Your strike"]


def line_for(check: dict[str, Any] | None, label: str, weapon: str = "") -> str:
    """The engine's result line for a rolled attack: band, weapon and target, the wording drawn from a pool.

    The draw is seeded by the roll and the target, so the same roll reads the
    same on a replay and different rolls read differently. "" when it is no
    rolled attack or there is no label.
    """
    if not isinstance(check, dict) or check.get("natural") is None:
        return ""
    band = str(check.get("outcome") or "")
    label = str(label or "").strip()
    if band not in _POOLS or not label:
        return ""
    skill = check.get("skill") if isinstance(check.get("skill"), dict) else {}
    code = str(skill.get("code") or check.get("skill_code") or "")
    pick = random.Random(f"{label}|{band}|{check.get('natural')}|{check.get('total')}|{code}")
    sent = pick.choice(senders(code, weapon))
    return pick.choice(_POOLS[band]).format(N=sent, T=label)


def lands_of(check: dict[str, Any] | None) -> str:
    return _BAND_LANDS.get(str((check or {}).get("outcome") or ""), "") if isinstance(check, dict) else ""


# ---------------------------------------------------------------------------
# The combat math for a target found after the draft (one roll decides, #129)
# ---------------------------------------------------------------------------


def _profile_for(row: dict[str, Any], combat: dict[str, Any]) -> dict[str, Any]:
    """The target's combat profile: the combat block's candidate record, else the row's own columns."""
    code = str(row.get("code") or "").upper()
    for cand in combat.get("target_candidates") or []:
        if isinstance(cand, dict) and str(cand.get("code") or "").upper() == code and isinstance(cand.get("combat_profile"), dict):
            return dict(cand["combat_profile"])
    out: dict[str, Any] = {}
    for key in ("health", "max_health", "attack_min", "attack_max", "defense", "dodge"):
        try:
            out[key] = int(row.get(key) or 0)
        except (TypeError, ValueError):
            out[key] = 0
    out["initialized"] = out["max_health"] > 0
    return out


def resolve(check: dict[str, Any], row: dict[str, Any], combat: Any, seed: str = "") -> dict[str, Any] | None:
    """The combat resolution for a rolled attack on ``row`` decided after the draft, or None when it cannot be.

    The check's band says whether the blow lands (attack_intent.LANDS, as
    world._combat_follows_attack_check); the damage is the combat block's own
    attack range rolled with the engine's seeded dice against the target's
    defense (as world._resolve_player_attack). None when the turn has no
    combat block with the player's attack, or the row has no health to lose:
    then no line is written (no hit without the hit applied).
    """
    if not isinstance(combat, dict) or not isinstance(row, dict):
        return None
    attack = combat.get("player_attack") if isinstance(combat.get("player_attack"), dict) else None
    if not attack:
        return None
    landed = lands_of(check)
    if not landed:
        return None
    profile = _profile_for(row, combat)
    max_health = max(0, int(profile.get("max_health") or 0))
    if max_health <= 0:
        return None
    health_value = profile.get("health")
    before = max(0, int(health_value if health_value is not None else max_health))
    low = max(1, int(attack.get("attack_min") or 1))
    high = max(low, int(attack.get("attack_max") or low))
    roller = random.Random(f"{seed}|{row.get('code')}|{check.get('natural')}|{check.get('total')}|{before}")
    raw = roller.randint(low, high)
    if landed == MISS:
        damage = 0
    else:
        damage = max(1, raw - max(0, int(profile.get("defense") or 0) // 4))
        if landed == GRAZE:
            damage = max(1, damage // 2)
    after = max(0, min(before - damage, max(before, max_health)))
    return {
        "outcome": landed,
        "raw_damage_roll": raw,
        "damage": damage,
        "target_health_before": before,
        "target_health_after": after,
        "target_defeated": after == 0 and before > 0,
        "decided_by": "attack_check_after_draft",
        "profile": profile,
    }


def combat_after_draft(combat: dict[str, Any], row: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    """The turn's combat block resolved on the target found after the draft (world applies it)."""
    profile = resolution.get("profile") if isinstance(resolution.get("profile"), dict) else {}
    out = dict(combat)
    out["status"] = "resolved_player_attack"
    out["target"] = {
        "code": row.get("code"), "name": row.get("name"), "rank": row.get("rank"), "attitude": row.get("attitude"),
        "combat_profile": profile,
    }
    out["resolution"] = {k: v for k, v in resolution.items() if k != "profile"}
    out["resolved_after_draft"] = True
    return out


# ---------------------------------------------------------------------------
# Reading the draft and putting the line in
# ---------------------------------------------------------------------------


def _para_index(text: str, at: int) -> int:
    return len(re.findall(r"\n\s*\n", text[:at]))


def _kind_word_re(row: dict[str, Any]) -> re.Pattern[str] | None:
    from app.unnamed import numbered_name

    _name, kind = numbered_name(row)
    if not kind:
        return None
    return re.compile(r"(?<![A-Za-z])" + re.escape(kind.lower()) + r"(?![A-Za-z])", re.I)


def _only_of_its_kind_here(row: dict[str, Any], records: dict[str, Any] | None, match: Any) -> bool:
    """A numbered figure whose kind no other living figure at the player's place shares."""
    from app.interpreter import is_dead
    from app.unnamed import numbered_name

    _name, kind = numbered_name(row)
    if not kind:
        return False
    here = int((records or {}).get("here_id") or 0)
    for other in getattr(match, "people", []) or []:
        if other is row or is_dead(other):
            continue
        if here and int(other.get("location_id") or 0) and int(other.get("location_id") or 0) != here:
            continue
        if numbered_name(other)[1].lower() == kind.lower():
            return False
    return True


def names_target(text: str, row: dict[str, Any], match: Any, records: dict[str, Any] | None = None) -> bool:
    """The text names the target: its code, a name only it has, or its kind when it is the only living one of that kind here."""
    if match.names(text, row):
        return True
    pattern = _kind_word_re(row)
    return bool(pattern and pattern.search(text) and _only_of_its_kind_here(row, records, match))


def _names_another(text: str, row: dict[str, Any], match: Any, records: dict[str, Any] | None) -> bool:
    from app.interpreter import is_dead

    for other in getattr(match, "people", []) or []:
        if other is row or is_dead(other) or str(other.get("code") or "").upper() == str(row.get("code") or "").upper():
            continue
        if names_target(text, other, match, records):
            return True
    return False


def _clauses(sentence: str) -> list[str]:
    text = _QUOTED_RE.sub(" ", str(sentence or ""))
    return [c.strip() for c in _CLAUSE_SPLIT_RE.split(text) if c and c.strip()]


def _subject_kind(clause: str, prev: str, weapon: str) -> str:
    """"attack" (the player, or what they sent), "other" (someone or something else), "none", or the clause carried on."""
    text = clause.strip().lstrip("\"“”'‘’ ")
    head = re.match(r"([A-Za-z’']+)(?:\s+([A-Za-z’'-]+))?", text)
    if not head:
        return prev
    first = head.group(1).lower()
    second = (head.group(2) or "").lower()
    if first in _PLAYER_WORDS:
        return "other" if _PASSIVE_RE.match(text) else "attack"
    if first == "your":
        return "none" if re.fullmatch(_NOT_A_BLOW, second, re.I) else "attack"
    word = _weapon_word(weapon)
    if first in {"the", "a", "an"}:
        if re.match(rf"(?:the|a|an)\s+(?:[A-Za-z-]+\s+)?(?:{_SENT}{'|' + re.escape(word) if word else ''})\b", text, re.I):
            return "attack"
        ellipsis = _ELLIPSIS_RE.match(text)
        if ellipsis and _outcomes_in(ellipsis.group(1)):
            return prev  # "The second misses the raider": the second shot
        return "other"
    if first in {"it", "they"}:
        return "attack" if prev == "attack" else "other"
    if first in _OTHER_PRONOUNS:
        return "other"
    if head.group(1)[:1].islower():
        return prev  # a clause carried on: "... and miss the ghoul", ", striking Nate"
    return "other"


def _object_ok(rest: str, row: dict[str, Any], match: Any, records: dict[str, Any] | None, no_object_ok: bool) -> bool:
    """The outcome clause's object is the target, a pronoun or nothing; never the player or something else."""
    words = str(rest or "").strip().lstrip(",;:").split()
    while words and (words[0].lower() in _OBJECT_LEAD or (words[0].lower().endswith("ly") and len(words[0]) > 3)):
        words.pop(0)
    if not words:
        return no_object_ok
    first = re.sub(r"[^\w\[\]’']", "", words[0]).lower()
    if first in _OBJECT_PLAYER:
        return False
    if first in _OBJECT_PRONOUNS:
        return no_object_ok or names_target(" ".join(words), row, match, records)
    if _OBJECT_NP_RE.match(words[0]):
        return names_target(" ".join(words), row, match, records)
    return no_object_ok


def _stated(sentences: list[str], row: dict[str, Any], match: Any, records: dict[str, Any] | None,
            weapon: str, single: bool, named_in_passage: bool) -> str:
    """The last outcome the passage's attack clauses state about this target, or ""."""
    prev = "none"
    said = ""
    for sentence in sentences:
        named_here = named_in_passage or names_target(sentence, row, match, records)
        for clause in _clauses(sentence):
            kind = _subject_kind(clause, prev, weapon)
            prev = kind
            if kind != "attack":
                continue
            for outcome, _start, end in _outcomes_in(clause):
                if _object_ok(clause[end:], row, match, records, single or named_here):
                    said = outcome
    return said


def read(text: str, row: dict[str, Any], landed: str, match: Any, records: dict[str, Any] | None = None,
         attacks: int = 1, weapon: str = "") -> dict[str, Any]:
    """What the draft shows of this attack: {"state": shown|contradicted|unshown, where the line goes, ...}."""
    from app.interpreter import _hook, players_own, units

    body = str(text or "")
    every = [u for u in units(body) if u[2].strip()]
    paras = [_para_index(body, u[0]) for u in every]
    passages: list[list[int]] = []
    covered: set[int] = set()
    for i, unit in enumerate(every):
        if i in covered or not is_attack_sentence(unit[2], weapon):
            continue
        span = [i]
        for j in range(i + 1, min(len(every), i + PASSAGE_SENTENCES)):
            if paras[j] != paras[i]:
                break
            # The next attack on someone else ends this one's passage (two attacks in one turn).
            if players_attack_sentence(every[j][2]) and _names_another(every[j][2], row, match, records) \
                    and not names_target(every[j][2], row, match, records):
                break
            span.append(j)
        covered.update(span)
        passages.append(span)
    agree = AGREES.get(landed, set())
    single = attacks <= 1
    decided: list[tuple[list[int], str, bool]] = []
    for span in passages:
        sentences = [every[k][2] for k in span]
        named = any(names_target(s, row, match, records) for s in sentences)
        said = _stated(sentences, row, match, records, weapon, single, named)
        if said:
            decided.append((span, said, named))
    chosen = next((d for d in reversed(decided) if d[2]), None) or (decided[-1] if decided else None)
    if chosen is not None:
        span, said, _named = chosen
        if said in agree:
            return {"state": "shown", "sentence": every[span[0]][2]}
        return {"state": "contradicted", "action": "inserted", "after": every[span[-1]][1], "where": "passage",
                "sentences": [every[k][2] for k in span]}
    if passages:
        first = next((p for p in passages if any(names_target(every[k][2], row, match, records) for k in p)), passages[0])
        return {"state": "unshown", "action": "inserted", "after": every[first[0]][1], "where": "attack"}
    named_first = next((u for u in every if names_target(u[2], row, match, records)), None)
    if named_first is not None and not _hook(named_first[2]):
        return {"state": "unshown", "action": "inserted", "after": named_first[1], "where": "target"}
    act = next((u for u in reversed(every) if players_own(u[2], []) and not _hook(u[2])), None)
    if act is not None:
        return {"state": "unshown", "action": "inserted", "after": act[1], "where": "act"}
    return {"state": "unshown", "action": "end", "where": "end"}


def insert_after(text: str, at: int, line: str) -> str:
    head = text[:at].rstrip(" \t")
    tail = text[at:]
    if not tail.strip():
        return f"{head} {line}".strip()
    rest = tail.lstrip(" \t")
    joiner = "" if rest.startswith("\n") else " "
    return f"{head} {line}{joiner}{rest}"
