"""How much a persuasion attempt asks of the person: the ask-weight helper.

Stell (2026-10-21): "we need to give persuasion attempts at simpler questions a
boost as people are more likely to answer simpler questions. this likely means
we need to assign an agent to specifically clarify the difficulty of the
persuasion attempt."

Engine first (CLAUDE.md): the engine has already found the social check and the
person it is aimed at; one small model ask rates what the player's line asks of
that person, and the engine turns the rating into the check's difficulty:

    free      anyone would answer it                      -> trivial  (DC -4)
    ordinary  usually shared, costs them little            -> easy     (DC -2)
    personal  private, costly or risky for them             -> normal   (DC  0)
    against   against their interest, loyalty or the law   -> hard     (DC +2)

The model is asked one concrete question, how many people in that person's
place would refuse (none / few / many / most), and is not shown the person's
mood: the engine applies the attitude itself, one step (friendly eases only
free and ordinary asks, hostile raises any). A missing or unusable reply
changes nothing: the check rolls as it did before. No examples in the ask (the
local models paste them). Live on Qwen3 8B: about 2 s an ask once loaded.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

PHASE = "ask_weight"
MAX_TOKENS = 60

WEIGHTS = ("free", "ordinary", "personal", "against")
_LADDER = ("trivial", "easy", "normal", "hard", "brutal")
_BASE_STEP = {"free": 0, "ordinary": 1, "personal": 2, "against": 3}
_FRIENDLY = {"friendly", "warm", "trusting", "ally", "allied", "admiring", "devoted", "helpful"}
_HOSTILE = {"hostile", "angry", "suspicious", "wary", "distrustful", "resentful", "cold", "enemy", "fearful"}

# One concrete question the engine maps to a weight. Live on the 8B
# (2026-10-21): a four-way category choice rated handing over the strongroom key
# "personal" while its own reason said it broke her duty, and three yes/no
# questions rated everything "free". "How many would refuse" is the simpler
# judgment (CLAUDE.md: a task the model gets wrong is made simpler).
_REFUSE_TO_WEIGHT = {"none": "free", "few": "ordinary", "many": "personal", "most": "against"}
_SYSTEM = (
    "You judge one request in a role-playing game. Read what the player says or does and who it is aimed at. "
    "Picture a hundred ordinary people in that person's place, with their job and their loyalties, meeting a "
    "stranger. How many of them would refuse? Judge the request itself, not how politely it is put. "
    "Answer one word: none, few, many or most. Answer only JSON: {\"refuse\": \"...\", \"why\": \"...\"} "
    "with a short why."
)

Ask = Callable[..., Any]


def build_ask(line: str, person: dict[str, Any] | None) -> tuple[str, str]:
    """(system, user) for the rating ask."""
    who = person or {}
    payload = {
        "player_line": str(line or "")[:500],
        "aimed_at": {
            key: str(who.get(key) or "")[:80]
            # Not the attitude: the engine applies it (difficulty_for), so the
            # model rates the request alone and mood is never counted twice.
            for key in ("name", "role")
            if str(who.get(key) or "").strip()
        } or "whoever is listening",
        "return": {"refuse": "none | few | many | most", "why": "one short sentence"},
    }
    return _SYSTEM, json.dumps(payload, ensure_ascii=True)


def parse_weight(raw: Any) -> tuple[str, str]:
    """(weight, why) from the reply; ("", "") when it is unusable.

    "refuse": none / few / many / most maps to free / ordinary / personal /
    against. A reply that names a weight word instead is read as that weight.
    """
    data = raw if isinstance(raw, dict) else None
    text = ""
    if data is None:
        text = str(raw or "")
        try:
            data = json.loads(text[text.find("{"): text.rfind("}") + 1]) if "{" in text else None
        except Exception:
            data = None
    if isinstance(data, dict):
        why = str(data.get("why") or "").strip()[:200]
        refuse = re.search(r"\b(none|few|many|most)\b", str(data.get("refuse") or "").strip().lower())
        if refuse:
            return _REFUSE_TO_WEIGHT[refuse.group(1)], why
        word = str(data.get("weight") or "").strip().lower()
    else:
        word, why = text.strip().lower(), ""
    found = re.search(r"\b(" + "|".join(WEIGHTS) + r")\b", word)
    return (found.group(1), why) if found else ("", "")


def difficulty_for(weight: str, attitude: str = "") -> str:
    """The check difficulty for a rated ask, moved one step by the person's attitude."""
    if weight not in _BASE_STEP:
        return ""
    step = _BASE_STEP[weight]
    mood = str(attitude or "").strip().lower()
    # A friend answers a small question more readily, but does not break their
    # duty for you more cheaply: friendliness eases free and ordinary asks only.
    if mood in _FRIENDLY and weight in {"free", "ordinary"}:
        step -= 1
    elif mood in _HOSTILE:
        step += 1
    return _LADDER[max(0, min(len(_LADDER) - 1, step))]


def rate(line: str, person: dict[str, Any] | None, ask: Ask | None) -> dict[str, Any]:
    """{"weight", "difficulty", "why"} for the player's line, or {} when there is no usable rating."""
    if ask is None or not str(line or "").strip():
        return {}
    system, user = build_ask(line, person)
    try:
        raw = ask(system, user, max_tokens=MAX_TOKENS, phase=PHASE)
    except Exception as exc:
        return {"error": f"{exc.__class__.__name__}: {exc}"[:200]}
    weight, why = parse_weight(raw)
    if not weight:
        return {"error": "no weight in the reply", "raw": str(raw)[:200]}
    attitude = str((person or {}).get("attitude") or "")
    return {"weight": weight, "difficulty": difficulty_for(weight, attitude), "why": why, "attitude": attitude}


def model_ask() -> Ask:
    """The turn's own model, through the same JSON call the quest checks use."""

    def ask(system: str, user: str, *, max_tokens: int, phase: str) -> Any:
        from app.llm import _chat_json

        return _chat_json(system, user, timeout=60, usage=[], phase=phase, max_tokens=max_tokens, trace=[])

    return ask
