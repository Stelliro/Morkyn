"""Ability growth: the model picks a template and a seed, the engine does every number.

Part one, the model's input (the "seed"), never a number:
    template  compounding | linear | soft_cap | breakthrough | passive | item_bound | flat
              (the ability's power_type)
    pace      slow | steady | fast        how quickly ranks come
    start     weak | ordinary | strong    where on the ladder the power begins
    grows     a few words: what gets stronger ("reach of the echo")

Part two, the engine's output (`expand`): the rank ladder (the world's rank_scale
labels), cumulative XP to reach each rank, XP per use and the risk multipliers,
soft caps or breakthrough gates, and the effect multiplier per rank. `render_text`
writes the growth_math text from that, so the text can never disagree with
itself; `award` applies uses during play and ranks the ability up.

Why: on Qwen3 8B the model-written growth math copied the prompt's stock examples
(17-24 of 26 per theme), contradicted its own thresholds, and took several retries
per batch; asked to apply it, the model named the right rank 28% of the time
(tools/ability_growth_8b.py, 2026-10-12). The model is good at fiction and at
picking from a short list; the engine is good at arithmetic.
"""
from __future__ import annotations

import math
import random
import re
from typing import Any

DEFAULT_LADDER = ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]

TEMPLATES: dict[str, dict[str, Any]] = {
    # step(n): XP from rank n-1 to rank n (n = 1 is the first step up).
    "compounding": {
        "label": "Compounding",
        "step": ("power", 40.0, 1.55),
        "xp_per_use": (5, 11),
        "risk": (1, 2, 3, 5),
        "effect": ("mult", 1.3),  # about x8 by SSS on a nine-rung ladder
        "soft_cap": (0.45, 0.55),  # after 45% of the ladder, XP x0.55 unless the use was dangerous
        "summary": "weak at first; every rank multiplies the effect, so the late ranks are huge",
    },
    "linear": {
        "label": "Steady",
        "step": ("linear", 40.0, 25.0),
        "xp_per_use": (5, 10),
        "risk": (1, 2, 3),
        "effect": ("add", 0.08),
        "summary": "the same small gain every rank; easy to plan",
    },
    "soft_cap": {
        "label": "Soft cap",
        "step": ("power", 35.0, 1.45),
        "xp_per_use": (5, 10),
        "risk": (1, 2, 3, 4),
        "effect": ("add", 0.12),
        "soft_cap": (0.5, 0.4),
        "summary": "quick early ranks, then practice slows hard; only danger keeps it moving",
    },
    "breakthrough": {
        "label": "Breakthrough",
        "step": ("power", 45.0, 1.5),
        "xp_per_use": (4, 9),
        "risk": (1, 2, 3, 4),
        "effect": ("add", 0.06),
        "breakthrough_every": 3,  # every third rank is a wall that only a dangerous use breaks
        "breakthrough_mult": 1.35,
        "summary": "plateaus at every third rank until a dangerous use breaks through, then jumps",
    },
    "passive": {
        "label": "Passive",
        "step": ("power", 30.0, 1.4),
        "xp_per_use": (2, 6),
        "risk": (1, 2, 3),
        "effect": ("add", 0.10),
        "summary": "always on; grows from scenes where it matters, slowly",
    },
    "item_bound": {
        "label": "Item-bound",
        "step": ("linear", 35.0, 20.0),
        "xp_per_use": (4, 10),
        "risk": (1, 2, 3),
        "effect": ("add", 0.10),
        "needs_item": True,
        "summary": "grows only while its item is used; without it, progress stops",
    },
    "flat": {
        "label": "Flat",
        "step": None,
        "summary": "a fixed gift: it does not rank up",
    },
}

TEMPLATE_ALIASES = {
    "compound": "compounding", "compounding": "compounding", "exponential": "compounding", "snowball": "compounding",
    "op": "compounding", "linear": "linear", "steady": "linear", "standard": "linear",
    "soft_cap": "soft_cap", "soft cap": "soft_cap", "softcap": "soft_cap", "plateau": "soft_cap",
    "breakthrough": "breakthrough", "realm": "breakthrough", "cultivation": "breakthrough",
    "passive": "passive", "aura": "passive", "always_on": "passive", "trait": "passive",
    "item_bound": "item_bound", "item bound": "item_bound", "item": "item_bound", "gear": "item_bound",
    "flat": "flat", "fixed": "flat", "static": "flat", "none": "flat",
}
PACES = {"slow": 1.4, "steady": 1.0, "fast": 0.7}
PACE_ALIASES = {"very slow": "slow", "slower": "slow", "normal": "steady", "medium": "steady", "quick": "fast", "very fast": "fast", "rapid": "fast"}
STARTS = {"weak": 0, "ordinary": 1, "strong": 2}
START_ALIASES = {"near_useless": "weak", "near useless": "weak", "useless": "weak", "low": "weak", "normal": "ordinary",
                 "average": "ordinary", "already strong": "strong", "high": "strong", "overpowered": "strong"}
DIFFICULTY = {"easy": 0.85, "normal": 1.0, "hard": 1.2, "brutal": 1.4}
RISK_NAMES = ["safe practice", "contested", "dangerous", "life-risk"]


def _word(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower().replace("-", " "))


def template_id(value: Any) -> str:
    word = _word(value).replace(" ", "_")
    return TEMPLATE_ALIASES.get(word, TEMPLATE_ALIASES.get(word.replace("_", " "), "linear"))


def ladder_from(rank_scale: Any) -> list[str]:
    labels = [p.strip() for p in re.split(r"[,/|;]", str(rank_scale or "")) if p.strip()]
    return labels if len(labels) >= 3 else list(DEFAULT_LADDER)


def normalize_seed(ability: dict[str, Any] | None, *, default_pace: str = "", default_start: str = "") -> dict[str, str]:
    """The model's seed from an ability card. Accepts a `growth` object or flat growth_* keys."""
    ab = ability if isinstance(ability, dict) else {}
    seed = ab.get("growth") if isinstance(ab.get("growth"), dict) else {}
    template = template_id(seed.get("template") or ab.get("power_type"))
    pace = _word(seed.get("pace") or ab.get("growth_pace") or default_pace)
    pace = PACE_ALIASES.get(pace, pace)
    start = _word(seed.get("start") or ab.get("growth_start") or default_start)
    start = START_ALIASES.get(start, start)
    grows = re.sub(r"\s+", " ", str(seed.get("grows") or ab.get("growth_grows") or "").strip())
    grows = re.sub(r"\d", "", grows)[:80].strip(" .;,")  # the seed carries no numbers
    return {
        "template": template,
        "pace": pace if pace in PACES else "steady",
        "start": start if start in STARTS else ("weak" if template == "compounding" else "ordinary"),
        "grows": grows,
    }


def _nice(value: float) -> int:
    step = 5 if value < 200 else 10 if value < 1000 else 50
    return max(5, int(round(value / step) * step))


def expand(seed: dict[str, str], *, rank_scale: Any = "", difficulty: str = "normal") -> dict[str, Any]:
    """Every number for one ability, from its seed and the world's settings."""
    template = template_id(seed.get("template"))
    spec = TEMPLATES[template]
    labels = ladder_from(rank_scale)
    growth: dict[str, Any] = {
        "version": 1,
        "template": template,
        "pace": seed.get("pace") or "steady",
        "start": seed.get("start") or "ordinary",
        "grows": seed.get("grows") or "",
        "labels": labels,
    }
    if not spec.get("step"):
        growth.update({"thresholds": [], "start_index": 0, "flat": True})
        return growth
    scale = PACES.get(growth["pace"], 1.0) * DIFFICULTY.get(_word(difficulty), 1.0)
    kind, a, b = spec["step"]
    thresholds = [0]
    for n in range(1, len(labels)):
        raw = a * n ** b if kind == "power" else a + b * (n - 1)
        thresholds.append(thresholds[-1] + _nice(raw * scale))
    start_index = min(STARTS.get(growth["start"], 1), len(labels) - 3)
    growth.update({
        "thresholds": thresholds,
        "start_index": max(0, start_index),
        "xp_per_use": list(spec["xp_per_use"]),
        "risk": list(spec["risk"]),
        "effect": list(spec["effect"]),
        "needs_item": bool(spec.get("needs_item")),
    })
    if spec.get("soft_cap"):
        after, mult = spec["soft_cap"]
        growth["soft_cap"] = {"from_index": max(1, math.ceil((len(labels) - 1) * after)), "xp_mult": mult}
    if spec.get("breakthrough_every"):
        every = int(spec["breakthrough_every"])
        growth["breakthrough_at"] = [i for i in range(every, len(labels)) if i % every == 0]
        growth["breakthrough_mult"] = spec["breakthrough_mult"]
    return growth


def effect_multiplier(growth: dict[str, Any], index: int) -> float:
    """How strong the ability is at a rank, relative to its starting rank (1.0 = as described)."""
    if growth.get("flat") or not growth.get("effect"):
        return 1.0
    start = int(growth.get("start_index") or 0)
    kind, per = growth["effect"]
    value = 1.0
    for i in range(start + 1, index + 1):
        value = value * per if kind == "mult" else value + per
        if i in (growth.get("breakthrough_at") or []):
            value *= float(growth.get("breakthrough_mult") or 1.0)
    for i in range(index + 1, start + 1):  # below the start rank (not normally reached)
        value = value / per if kind == "mult" else value - per
    return round(max(0.1, value), 2)


def new_state(growth: dict[str, Any]) -> dict[str, Any]:
    start = int(growth.get("start_index") or 0)
    thresholds = growth.get("thresholds") or [0]
    return {"index": start, "xp": float(thresholds[start] if start < len(thresholds) else 0), "uses": 0}


def risk_multiplier(growth: dict[str, Any], tier: int) -> float:
    risks = growth.get("risk") or [1]
    return float(risks[max(0, min(len(risks), int(tier or 1)) - 1)])


def award(growth: dict[str, Any], state: dict[str, Any] | None, *, uses: int = 1, risk: int = 1,
          rng: random.Random | None = None, item_ok: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Apply `uses` uses at a risk tier (1 safe .. 4 life-risk). Returns (new state, events)."""
    st = dict(state) if isinstance(state, dict) else new_state(growth)
    st["uses"] = int(st.get("uses") or 0) + max(0, int(uses))
    events: list[dict[str, Any]] = []
    thresholds = growth.get("thresholds") or []
    if growth.get("flat") or len(thresholds) < 2:
        return st, events
    if growth.get("needs_item") and not item_ok:
        events.append({"type": "no_item"})
        return st, events
    rng = rng or random.Random()
    lo, hi = growth.get("xp_per_use") or (1, 1)
    labels = growth.get("labels") or DEFAULT_LADDER
    tier = max(1, min(4, int(risk or 1)))
    soft = growth.get("soft_cap") or {}
    walls = set(growth.get("breakthrough_at") or [])
    index, xp = int(st.get("index") or 0), float(st.get("xp") or 0.0)
    plateau_hit = False
    for _ in range(max(0, int(uses))):
        if index >= len(thresholds) - 1:
            break
        gain = rng.randint(int(lo), int(hi)) * risk_multiplier(growth, tier)
        if soft and index >= int(soft.get("from_index", 99)) and tier < 3:
            gain *= float(soft.get("xp_mult", 1.0))
        xp += gain
        nxt = index + 1
        if nxt in walls and tier < 3 and xp >= thresholds[nxt]:
            xp = thresholds[nxt] - 1  # the wall: only a dangerous use breaks through
            plateau_hit = True
        while index < len(thresholds) - 1 and xp >= thresholds[index + 1]:
            index += 1
            events.append({
                "type": "rank_up", "to_index": index, "to": labels[index] if index < len(labels) else str(index),
                "breakthrough": index in walls, "effect_multiplier": effect_multiplier(growth, index),
            })
    st.update({"index": index, "xp": round(xp, 1)})
    if plateau_hit and not any(e["type"] == "rank_up" for e in events):
        events.append({"type": "plateau", "at": labels[index] if index < len(labels) else str(index)})
    return st, events


def _fmt(n: float) -> str:
    n = float(n)
    return f"{int(n):,}" if n.is_integer() else f"{n:,.2f}".rstrip("0").rstrip(".")


def render_text(growth: dict[str, Any], *, name: str = "") -> str:
    """growth_math, written by the engine. Every number here comes from `growth`."""
    template = growth.get("template") or "linear"
    spec = TEMPLATES.get(template, TEMPLATES["linear"])
    labels = growth.get("labels") or DEFAULT_LADDER
    grows = f" Grows: {growth['grows']}." if growth.get("grows") else ""
    if growth.get("flat") or not growth.get("thresholds"):
        return f"{spec['label']}: {spec['summary']}; the effect stays as described.{grows}"
    th = growth["thresholds"]
    start = int(growth.get("start_index") or 0)
    steps = ", ".join(f"{labels[i]} {_fmt(th[i])}" for i in range(start + 1, len(th)))
    lo, hi = growth["xp_per_use"]
    risks = growth.get("risk") or [1]
    risk_txt = ", ".join(f"{RISK_NAMES[i]} x{_fmt(r)}" for i, r in enumerate(risks[:4]))
    parts = [
        f"{spec['label']} ({spec['summary']}).",
        f"Starts at {labels[start]}. XP to reach: {steps}.",
        f"Each use: {lo}-{hi} XP x risk ({risk_txt}).",
    ]
    soft = growth.get("soft_cap")
    if soft:
        parts.append(f"From {labels[soft['from_index']]} on, safe or contested uses earn x{_fmt(soft['xp_mult'])} XP.")
    walls = growth.get("breakthrough_at") or []
    if walls:
        parts.append(f"Walls before {', '.join(labels[i] for i in walls)}: only a dangerous use breaks through "
                     f"(x{_fmt(growth.get('breakthrough_mult') or 1)} effect when it does).")
    if growth.get("needs_item"):
        parts.append("Earns XP only while its item is used.")
    kind, per = growth["effect"]
    top = effect_multiplier(growth, len(labels) - 1)
    per_txt = f"x{_fmt(per)} per rank" if kind == "mult" else f"+{int(round(per * 100))}% per rank"
    parts.append(f"Effect: {per_txt} above {labels[start]} (x{_fmt(top)} at {labels[-1]}).{grows}")
    return " ".join(parts)


def describe_state(growth: dict[str, Any], state: dict[str, Any] | None, *, name: str = "") -> str:
    """One line the storyteller reads: rank, progress, strength now. No arithmetic left to do."""
    labels = growth.get("labels") or DEFAULT_LADDER
    if growth.get("flat") or not growth.get("thresholds"):
        return f"{name}: fixed, does not rank up."
    st = state if isinstance(state, dict) else new_state(growth)
    index = int(st.get("index") or 0)
    th = growth["thresholds"]
    label = labels[index] if index < len(labels) else str(index)
    mult = effect_multiplier(growth, index)
    strength = "as described" if mult == 1.0 else f"x{_fmt(mult)} the described effect"
    if index >= len(th) - 1:
        progress = "top rank"
    else:
        progress = f"{_fmt(st.get('xp') or 0)}/{_fmt(th[index + 1])} XP to {labels[index + 1]}"
        if index + 1 in (growth.get("breakthrough_at") or []):
            progress += " (a wall: needs a dangerous use)"
    grows = f"; grows: {growth['grows']}" if growth.get("grows") else ""
    return f"{name}: rank {label}, {progress}; strength {strength}{grows}."


def build(ability: dict[str, Any], *, rank_scale: Any = "", difficulty: str = "normal",
          default_pace: str = "", default_start: str = "") -> dict[str, Any]:
    """Seed -> growth -> growth_math, on a copy of the ability card."""
    out = dict(ability or {})
    seed = normalize_seed(out, default_pace=default_pace, default_start=default_start)
    growth = expand(seed, rank_scale=rank_scale, difficulty=difficulty)
    out["power_type"] = seed["template"]
    out["growth"] = seed
    out["growth_spec"] = growth
    out["growth_math"] = render_text(growth, name=str(out.get("name") or ""))
    return out
