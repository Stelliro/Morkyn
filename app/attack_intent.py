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
    return f'{name} is here. The player wrote: "{line}"\n\nDoes the player try to hurt or kill {name}? Answer yes or no.'


def ask_attack_check(name: str, line: str) -> str:
    return f'{name} is here. The player wrote: "{line}"\n\nIs the player peaceful toward {name}? Answer yes or no.'


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
    for person in people:
        name = str(person.get("name") or "").strip()
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


def decide(
    model_input: str,
    context: dict[str, Any] | None,
    inferred: dict[str, Any] | None,
    ask: Ask | None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """The attack check for this line, or None, and the report of the asks.

    A blow the trigger tables already aimed at a person (an "attack" key, or a
    melee / ranged check with that person as its npc_ref) is not asked about
    again: it is marked as the attack on that person. Otherwise each person
    here is asked about, and a confirmed target gets an attack check: the
    inferred melee / ranged check aimed at them when there was one (returned
    with "replaces_inferred"), else a new one.
    """
    started = time.time()
    report: dict[str, Any] = {"asks": [], "unconfirmed": [], "target": None}
    inferred = inferred if isinstance(inferred, dict) else None
    try:
        if inferred and inferred.get("skill_code") in ATTACK_SKILLS:
            ref = inferred.get("npc_ref") if isinstance(inferred.get("npc_ref"), dict) else {}
            if ref.get("code"):
                inferred["attack"] = {"code": str(ref.get("code")), "name": _clean(ref.get("name"))}
                report["target"] = inferred["attack"]
                report["from"] = "trigger"
                return None, report
        if ask is None:
            report["skipped"] = "no_model"
            return None, report
        line = player_line(model_input)
        people = people_here(context)
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
