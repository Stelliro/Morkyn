"""The engine writes the attack's result line (#129, #186; CLAUDE.md, Design decisions, 2026-10-24).

Stell's decision ("Transactions and items are read by their own agent", on
attacks): the roll comes first, the engine writes the attack's result line
itself from the roll and the weapon, the narrator writes the scene around it,
and when the draft leaves the line out or contradicts it the engine puts its
own line in. No model rewrite, no extra model call, no new narrator text.

Every rolled attack gets the line: a melee or ranged check the engine rolled
with an attack target (app/attack_intent.py marks it), or such a check with no
target when the player's line names one the records now hold (merge1 T4, F186:
'i shoot the closest ghoul' rolled before the ghouls were on the roster; the
prose had the player charge and never shoot, so the hit on Ghoul 1 [[D]] was
nowhere).

Whether the draft already shows the outcome is read by the engine, not asked:

* An attack sentence is one where the player acts with an attack word
  ("you ... shoot", "you squeeze the trigger", "you miss") or one that opens
  on what the player sent ("The bullet ...", "Your blow ..."). Its passage is
  that sentence and the next two of its paragraph.
* The outcome a passage states is its last hit, graze or miss word ("flies
  true, but ... passes harmlessly wide" is a miss). Quoted words count: the
  person shot at may say it ("You almost hit me!").
* Shown: a passage that names the target (its code, a name only it has, or
  the kind of a numbered figure, "the ghoul") states an outcome that agrees
  with the roll's band. Nothing changes.
* Contradicted: the passage that names the target states the opposite (a miss
  on a success, a hit or a kill on a failure). When one sentence of it states
  the opposite, and it holds no quote, that sentence gives way to the engine
  line (the narrow repair); otherwise the line goes in after the passage and
  the prose stays as written.
* Not shown: the line goes after the attack passage (the target unnamed or no
  outcome stated), else after the first sentence that names the target, else
  after the player's last act, else at the end (before a closing question).

Every insertion, replacement and "already shown" is noted in the turn ledger.
The summary carries the line (interpreter.summary).
"""
from __future__ import annotations

import random
import re
from typing import Any

HIT = "hit"
GRAZE = "glancing_hit"
MISS = "miss"

# What the roll's band allows a passage to say; anything else is the opposite.
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
_NOT_A_BLOW = r"eyes?|gaze|look|attention|glance|mind|thoughts?|heart|breath|voice|words?"
_GAZE_RE = re.compile(rf"\b(?:your|his|her|their)\s+(?:{_NOT_A_BLOW})\b", re.I)
_ATTACK_RE = re.compile(
    rf"\b(?:you|your(?!\s+(?:{_NOT_A_BLOW})\b))\b[^.;!?]{{0,48}}?\b(?:{_ATTACK})\b", re.I
)
_SENT_RE = re.compile(rf"^\W*(?:the|your)\s+(?:\w+\s+)?(?:{_SENT})\b", re.I)

# Outcome words, longest first so "almost hit" is a miss and "falls short" is no fall.
_OUTCOMES: list[tuple[str, str]] = [
    (MISS, r"almost hit|nearly hit|barely miss\w*|falls? short|fell short|goes? wide|went wide|wide of|"
           r"miss|misses|missed|missing|whistles? past|whizz\w* past|harmlessly|deflect\w*|dodges?|dodged|"
           r"ducks?|ducked|sidesteps?|sidestepped|no mark|thin air|off target"),
    (GRAZE, r"graze[sd]?|grazing|nicks?|nicked|clips?|clipped|glances? off|glancing|scratch\w*|only grazes"),
    (HIT, r"hits?|hitting|finds? (?:its|their|his|her) mark|struck|striking|slams? into|slammed into|"
          r"tears? into|tore into|punch\w* through|connects?|connected|lands? (?:on|square|hard|clean)|landed|"
          r"square in|catches|caught (?:him|her|it|them)|buries|sinks? into|sank into|wounds?|wounded|"
          r"staggers?|staggered|crumples?|crumpled|collapses?|collapsed|collapsing|drops? (?:him|her|it|them)|"
          r"kills?|killed|dead|corpse|lifeless|reels?|reeled"),
]
_OUTCOME_RE = re.compile(
    "|".join(f"(?P<{kind.replace('glancing_hit', 'graze')}{i}>\\b(?:{words})\\b)" for i, (kind, words) in enumerate(_OUTCOMES)),
    re.I,
)
_GROUP_KIND = {f"{kind.replace('glancing_hit', 'graze')}{i}": kind for i, (kind, _w) in enumerate(_OUTCOMES)}

PASSAGE_SENTENCES = 3


def outcome_of(text: str) -> str:
    """The last outcome word in the text, as hit / glancing_hit / miss, or "" (no outcome stated)."""
    found = ""
    at = -1
    for match in _OUTCOME_RE.finditer(str(text or "")):
        if match.start() >= at:
            at = match.start()
            found = _GROUP_KIND.get(match.lastgroup or "", "")
    return found


_QUOTED_RE = re.compile(r"\"[^\"]*\"|“[^”]*”|\"[^\"]*$|“[^”]*$")


def is_attack_sentence(sentence: str) -> bool:
    """The player attacks in it ("you shoot", "you miss"), or it opens on what the player sent ("The bullet").

    Quoted words are someone speaking ("I need you to shoot straight."), never the act itself.
    """
    text = _QUOTED_RE.sub(" ", str(sentence or ""))
    return bool(_ATTACK_RE.search(text) or _SENT_RE.search(text))


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
# Reading the draft and putting the line in
# ---------------------------------------------------------------------------


def _para_index(text: str, at: int) -> int:
    return len(re.findall(r"\n\s*\n", text[:at]))


def _kind_re(row: dict[str, Any]) -> re.Pattern[str] | None:
    """The kind of a numbered figure as a whole singular word ("ghoul", never "ghouls")."""
    from app.unnamed import numbered_name

    _name, kind = numbered_name(row)
    if not kind:
        return None
    return re.compile(r"(?<![A-Za-z])" + re.escape(kind.lower()) + r"(?![A-Za-z])", re.I)


def names_target(sentence: str, row: dict[str, Any], match: Any) -> bool:
    if match.names(sentence, row):
        return True
    pattern = _kind_re(row)
    return bool(pattern and pattern.search(sentence))


def _has_quote(sentence: str) -> bool:
    return any(mark in sentence for mark in ('"', "“", "”"))


def read(text: str, row: dict[str, Any], landed: str, match: Any) -> dict[str, Any]:
    """What the draft shows of this attack: {"state": shown|contradicted|unshown, where to put the line, ...}."""
    from app.interpreter import _hook, players_own, units

    body = str(text or "")
    every = [u for u in units(body) if u[2].strip()]
    paras = [_para_index(body, u[0]) for u in every]
    passages: list[list[int]] = []
    for i, unit in enumerate(every):
        if not is_attack_sentence(unit[2]):
            continue
        span = [i]
        for j in range(i + 1, min(len(every), i + PASSAGE_SENTENCES)):
            if paras[j] != paras[i]:
                break
            span.append(j)
        passages.append(span)
    agree = AGREES.get(landed, set())
    named_passages = [p for p in passages if any(names_target(every[k][2], row, match) for k in p)]
    for span in named_passages:
        said = outcome_of(" ".join(every[k][2] for k in span))
        if said and said in agree:
            return {"state": "shown", "sentence": every[span[0]][2]}
    # Where the attack passage states no outcome, the sentences that name the
    # target say how it went ("Beth [[B]]'s wide, dead eyes stare up"), the last one stated.
    # Only after an attack sentence: with none, the scene shows no attack ("Your gaze lands on Beth").
    first_attack = passages[0][0] if passages else len(every)
    target_units = [k for k in range(first_attack, len(every)) if names_target(every[k][2], row, match)]
    stated = [k for k in target_units if outcome_of(every[k][2]) and not _GAZE_RE.search(every[k][2])]
    span_said = next((p for p in named_passages if outcome_of(" ".join(every[k][2] for k in p))), None)
    if span_said is None and stated and outcome_of(every[stated[-1]][2]) in agree:
        return {"state": "shown", "sentence": every[stated[-1]][2]}
    if span_said is not None or stated:
        # "The one sentence stating the opposite" is counted over every sentence from the attack on
        # in the paragraphs that name the target or hold the attack: "her lifeless upper body
        # collapses" says it as much as the sentence with her name does.
        start = min([*(span_said or []), *target_units, *([first_attack] if passages else [])])
        in_paras = {paras[k] for k in [*(span_said or []), *target_units]}
        pool = [k for k in range(start, len(every)) if paras[k] in in_paras]
        opposite = [k for k in pool if (outcome_of(every[k][2]) or "") not in ("", *agree)]
        if len(opposite) == 1 and not _has_quote(every[opposite[0]][2]):
            k = opposite[0]
            return {"state": "contradicted", "action": "replaced", "start": every[k][0], "end": every[k][1],
                    "sentence": every[k][2]}
        anchor = span_said or (named_passages[0] if named_passages else passages[0] if passages else [target_units[0]])
        return {"state": "contradicted", "action": "inserted", "after": every[anchor[-1]][1],
                "sentences": [every[k][2] for k in opposite]}
    if named_passages:
        return {"state": "unshown", "action": "inserted", "after": every[named_passages[0][-1]][1], "where": "attack"}
    if passages:
        return {"state": "unshown", "action": "inserted", "after": every[passages[0][-1]][1], "where": "attack_unnamed"}
    first = next((u for u in every if names_target(u[2], row, match)), None)
    if first is not None and not _hook(first[2]):
        return {"state": "unshown", "action": "inserted", "after": first[1], "where": "target"}
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


def replace_span(text: str, start: int, end: int, line: str) -> str:
    return text[:start] + line + text[end:]
