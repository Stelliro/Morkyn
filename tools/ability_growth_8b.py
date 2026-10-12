"""Generate abilities on the real 8B model through the game's pipeline, check their math, and level them.

    python tools/ability_growth_8b.py                       # every theme, 25 abilities each
    python tools/ability_growth_8b.py --themes op_mc wuxia --per-theme 10 --stages 4
    python tools/ability_growth_8b.py --skip-stages --skip-turns   # generation + math audit only

Three parts, per theme:

1. Generation: `llm.generate_setup_randomization("special_abilities", ...)`, the same
   call the setup page makes (prompt, quality gate, retries, growth-math optimizer,
   dedupe), cycling count / start power / growth / difficulty so one theme sees
   several parameter sets. Each ability records whether the model wrote it or a
   fallback / stock growth-math sample replaced it.
2. Math audit: the growth_math text is parsed (thresholds, XP_to_next formulas,
   per-use XP, risk multipliers, soft caps, per-rank effect) and checked for
   internal consistency and for how many uses each stage takes. The engine's
   `stamp_resource_cost` + `apply_ability_use` charge the cost; the harness compares
   that with the cost text.
3. Stages: the engine has no ability ranks, so the harness steps each ability through
   `--stages` sessions. Each session the 8B model is asked to apply the ability's own
   growth_math (uses, risk); the parsed math checks its arithmetic and rank calls.
   `--turns` real `play_turn` calls per theme then show whether a live game changes
   an ability at all (JSON draft mode; the default DSL mode always sends no updates).

Everything runs in a temporary data dir (`isolated_data_env`). Results go to
data/ability_runs/<stamp>/ (gitignored): abilities.jsonl, stages.jsonl, turns.jsonl,
summary.json, summary.md. Rerun after changing abilities to compare.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import math
import operator
import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

DEFAULT_MODEL = r"D:\morkyn-stage-models\Qwen3-8B-Q4_K_M.gguf"

# Ideas are the game's own director presets (static/app.js DIRECTOR_PRESETS_BUILTIN).
THEMES: dict[str, dict[str, Any]] = {
    "op_mc": {
        "label": "Overpowered",
        "idea": (
            "Overpowered progression in any setting: start ordinary with one weak compounding seed power that "
            "snowballs toward late-game OP (rank F up through S/SS/SSS). Growth Math makes the climb calculable; "
            "passives allowed; more powers can unlock later. Normal difficulty; mythic progression tone; local "
            "stakes early; fair DM."
        ),
        "magic_level": "cultivation",
    },
    "apocalypse": {
        "label": "System apocalypse",
        "idea": (
            "System apocalypse: gates open over a modern city, monsters pour out, and survivors get a level up "
            "system window. Brutal difficulty; survival pressure tone; weak start, steady growth; barter-heavy "
            "economy; loot earned and uncommon. The first days decide who lives."
        ),
        "magic_level": "rare",
    },
    "wuxia": {
        "label": "Wuxia",
        "idea": (
            "Wuxia sect politics: cultivation realms, sect rivalries, qi techniques, face and debts of honor. Hard "
            "difficulty; mythic progression tone; magic as cultivation; guild-controlled economy; loot earned and "
            "uncommon. Breakthroughs are earned through training and risk."
        ),
        "magic_level": "cultivation",
    },
    "cyberpunk": {
        "label": "Cyberpunk",
        "idea": (
            "Near-future cyberpunk megacity: megacorps, neon streets, chrome, debt, fixers. Hard difficulty; no "
            "magic, high tech; grounded adventure with noir jobs; coin-driven economy; loot earned and uncommon. "
            "Tech and social leverage over brawn."
        ),
        "magic_level": "none",
    },
    "gothic": {
        "label": "Gothic",
        "idea": (
            "Gothic horror: a haunted manor, a vampire blood court, crypts, dark romance, debts paid in years. Hard "
            "difficulty; grim road story tone; magic forbidden and costly; coin-driven economy; loot earned and "
            "uncommon. Dread over gore; invitations matter; daylight is a resource."
        ),
        "magic_level": "forbidden",
    },
    "hearth": {
        "label": "Hearth (cozy)",
        "idea": (
            "Cozy low-stakes fantasy: a small village, a shop or farm to run, festivals, neighbors with problems, "
            "gentle mysteries. Easy difficulty; grounded adventure tone; magic common utility; barter-heavy "
            "economy. No war, no doom; stakes are personal and reversible."
        ),
        "magic_level": "common utility",
    },
}

# Parameter sets cycled per batch, so each theme is generated under several.
VARIANTS: list[dict[str, Any]] = [
    {"count": (1, 1), "start_power": "near_useless", "growth": "compounding", "difficulty": "normal"},
    {"count": (2, 3), "start_power": "ordinary", "growth": "steady", "difficulty": "hard"},
    {"count": (3, 4), "start_power": "ordinary", "growth": "steady", "difficulty": "easy"},
    {"count": (1, 2), "start_power": "strong", "growth": "steady", "difficulty": "normal"},
    {"count": (2, 4), "start_power": "weak", "growth": "compounding", "difficulty": "hard"},
]


# --- growth_math parsing ---------------------------------------------------------

RANK_LADDER = ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]
_NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"


def _num(text: str) -> float:
    return float(str(text).replace(",", ""))


_ALLOWED = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _safe_eval(expr: str, n: float) -> float | None:
    """Evaluate a small arithmetic formula in one variable n. None if it is not one."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id == "n":
            return float(n)
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
            return _ALLOWED[type(node.op)](ev(node.operand))
        raise ValueError("unsupported")

    try:
        value = ev(tree)
    except Exception:
        return None
    return value if math.isfinite(value) else None


def _formula(text: str) -> tuple[str, str] | None:
    """(raw, python) for an XP_to_next style formula, in terms of n (rank/level index)."""
    m = re.search(r"xp[\s_-]*(?:to[\s_-]*next|needed|required|cost)?\s*(?:\(\s*\w+\s*\))?\s*[=:]\s*([^;\n]+)", text, re.I)
    if not m:
        return None
    raw = m.group(1).strip().rstrip(".")
    raw = re.split(r"\s+(?:per|for|where|with|until|then|and)\s+|\(F|\(rank|,\s*(?=[a-z])", raw, maxsplit=1)[0]
    expr = raw.replace("×", "*").replace("^", "**").replace("·", "*")
    expr = re.sub(r"\b(rank_index|rank|level|lvl|tier|stage|n|r|l|L)\b", "n", expr)
    expr = re.sub(r"(\d)\s*n\b", r"\1*n", expr)
    expr = re.sub(r"[^0-9n+\-*/(). ]", "", expr).strip()
    if "n" not in expr or not expr:
        return None
    return raw, expr


def _thresholds(text: str) -> list[tuple[str, float]]:
    """Rank or level thresholds in the order written: [(label, xp), ...]."""
    out: list[tuple[str, float]] = []
    for m in re.finditer(rf"\b([A-F]|S{{1,3}}|\d+)\s*(?:→|->|to)\s*([A-F]|S{{1,3}}|\d+)\s*@\s*{_NUM}", text):
        out.append((m.group(2), _num(m.group(3))))
    if len(out) >= 2:
        return out
    out = []
    seq = re.findall(rf"(?<![A-Za-z])(F|E|D|C|B|A|S|SS|SSS)\s?{_NUM}\b", text)
    if len(seq) >= 3:
        return [(lab, _num(v)) for lab, v in seq]
    out = []
    for m in re.finditer(rf"\b(?:level|lvl|rank|tier|stage|L)\s*(\d+)\s*(?:@|at|:|=|needs|requires)\s*{_NUM}\s*(?:xp|exp)?", text, re.I):
        out.append((m.group(1), _num(m.group(2))))
    if len(out) >= 2:
        return out
    # "10 XP to unlock the first echo, 20 XP for a second echo"
    out = []
    for m in re.finditer(rf"{_NUM}\s*xp\s*(?:to\s*(?:unlock|reach|gain)|for)\s*(?:the\s*|a\s*)?(first|second|third|fourth|fifth|sixth|\d+(?:st|nd|rd|th)?)",
                         text, re.I):
        out.append((m.group(2).lower(), _num(m.group(1))))
    return out if len(out) >= 2 else []


def shape(text: str) -> str:
    """growth_math with every number masked: the same template with new numbers has the same shape."""
    return re.sub(r"\d+(?:[.,]\d+)?", "#", str(text or "").lower()).strip()


def _per_use(text: str) -> tuple[float, float] | None:
    pats = [
        rf"{_NUM}\s*[-–]\s*{_NUM}\s*xp",
        rf"(?:use|success|practice|grants?|gain|earns?)\D{{0,20}}{_NUM}\s*[-–]\s*{_NUM}",
        rf"{_NUM}\s*xp\s*(?:per|each|/)\s*(?:use|success|practice|session|attempt)",
        rf"(?:per|each)\s*(?:use|success)\D{{0,12}}{_NUM}\s*xp",
        rf"(?:practice|use|success|training|attempt)\s*{_NUM}\s*xp",
    ]
    for p in pats:
        m = re.search(p, text, re.I)
        if m:
            vals = [_num(g) for g in m.groups() if g]
            return (min(vals), max(vals)) if len(vals) >= 2 else (vals[0], vals[0])
    return None


def _risk(text: str) -> list[float]:
    m = re.search(r"risk\s*\(?\s*(\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)+)", text, re.I)
    if m:
        return [float(x) for x in re.split(r"\s*/\s*", m.group(1))]
    return [float(x) for x in re.findall(r"[×x]\s*(\d+(?:\.\d+)?)\s*(?:for|on|if)?\s*(?:risk|contested|danger)", text, re.I)]


def audit_growth_math(text: str, power_type: str, stock: list[str]) -> dict[str, Any]:
    t = str(text or "")
    issues: list[str] = []
    th = _thresholds(t)
    fm = _formula(t)
    pu = _per_use(t)
    risk = _risk(t)
    softcap = [float(x) for x in re.findall(r"[×x]\s*(0\.\d+)", t)]
    # Per-rank effect growth: "+8% per level", "+14–22% effect", "1.22^ranks", "×1.3 per rank".
    effect = re.findall(
        r"\+?\d+(?:\.\d+)?(?:\s*[–-]\s*\d+(?:\.\d+)?)?\s*%|\d\.\d+\s*\^\s*\(?\s*(?:rank|level|n)|[×x]\s*1\.\d+\s*(?:per|each|/)\s*(?:rank|level)",
        t, re.I)
    best_stock = max((difflib.SequenceMatcher(None, t.lower(), s.lower(), autojunk=False).ratio() for s in stock), default=0.0)
    best_shape = max((difflib.SequenceMatcher(None, shape(t), shape(s), autojunk=False).ratio() for s in stock), default=0.0)
    formula_values: list[float] = []
    if fm:
        for n in range(1, 9):
            v = _safe_eval(fm[1], n)
            if v is None:
                formula_values = []
                break
            formula_values.append(round(v, 1))
        if not formula_values:
            issues.append("formula_not_evaluable")
    if not th and not formula_values:
        issues.append("no_computable_curve")
    values = [v for _, v in th]
    if len(values) >= 2 and any(b <= a for a, b in zip(values, values[1:])):
        issues.append("thresholds_not_increasing")
    consistency = None
    if len(values) >= 3 and len(formula_values) >= 3:
        k = min(len(values), len(formula_values), 6)
        cumulative = values[:k]
        steps = [values[0]] + [b - a for a, b in zip(values, values[1:])][: k - 1]
        f = formula_values[:k]

        def close(a: list[float], b: list[float]) -> float:
            return sum(1 for x, y in zip(a, b) if y and abs(x - y) / max(abs(y), 1) <= 0.3) / len(a)

        consistency = round(max(close(f, cumulative), close(f, steps)), 2)
        if consistency < 0.5:
            issues.append("formula_contradicts_thresholds")
    if not pu:
        issues.append("no_per_use_xp")
    if power_type == "compounding" and not effect and not re.search(r"\^\s*\(?\s*(rank|level|n)|compound", t, re.I):
        issues.append("compounding_without_compounding_effect")
    if best_stock >= 0.85:
        issues.append("copied_stock_example")
    elif best_shape >= 0.8:
        issues.append("stock_template_new_numbers")
    # How many uses each stage takes at the lowest risk tier.
    stage_uses: list[dict[str, Any]] = []
    # (label, cumulative xp) per stage above the start; a 0-XP entry ("F0") is the starting rank.
    curve: list[tuple[str, float]] = [(lab, v) for lab, v in th if v > 0]
    if not curve and formula_values:
        acc = 0.0
        for i, v in enumerate(formula_values[:6]):
            acc += v
            curve.append((str(i + 2), acc))
    if pu and curve:
        per = (pu[0] + pu[1]) / 2 or 1
        for label, xp in curve[:8]:
            stage_uses.append({"stage": label, "xp": xp, "uses_at_low_risk": math.ceil(xp / per)})
        if stage_uses and stage_uses[0]["uses_at_low_risk"] < 2:
            issues.append("first_stage_trivial")
        if stage_uses and stage_uses[-1]["uses_at_low_risk"] > 20000:
            issues.append("top_stage_unreachable")
    return {
        "issues": issues,
        "thresholds": th,
        "formula": fm[0] if fm else "",
        "formula_values": formula_values,
        "formula_threshold_agreement": consistency,
        "per_use_xp": pu,
        "risk_multipliers": risk,
        "soft_cap_multipliers": softcap,
        "has_effect_scaling": bool(effect),
        "stock_similarity": round(best_stock, 2),
        "stock_shape_similarity": round(best_shape, 2),
        "stage_uses": stage_uses,
    }


# --- helpers ---------------------------------------------------------------------

def jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def isolate(model: str) -> Path:
    from playtest_setup_presets import isolated_data_env

    temp = Path(tempfile.mkdtemp(prefix="morkyn_ability_run_"))
    os.environ.update(isolated_data_env(str(temp)))
    for sub in ("source_index", "model_traces"):
        (temp / sub).mkdir(exist_ok=True)
    os.environ.update({
        "AI_RPG_MODEL_PROVIDER": "mle",
        "MLE_MODEL": model,
        "AI_RPG_MLE_TIMEOUT": "420",
        "AI_RPG_SETUP_RANDOMIZER_TIMEOUT": "300",
    })
    return temp


# --- part 1 + 2: generation and audit ---------------------------------------------------

def generate_theme(theme_id: str, spec: dict[str, Any], per_theme: int, out: Path) -> list[dict[str, Any]]:
    from app.llm import GROWTH_MATH_SAMPLES, compose_setup_intent, generate_setup_randomization
    from app.player_resources import magic_allows_mana, stamp_resource_cost
    from app.setup_composer import intent_to_field_overrides

    t0 = time.perf_counter()
    try:
        composed = compose_setup_intent(spec["idea"], {})
    except Exception as exc:  # the composer has a keyword fallback; keep going
        log(f"{theme_id}: compose failed ({exc}); keyword intent only")
        composed = {}
    intent = dict(composed.get("intent") or {}) if isinstance(composed, dict) else {}
    session_theme = composed.get("session_theme") if isinstance(composed, dict) else {}
    log(f"{theme_id}: composed in {time.perf_counter() - t0:.0f}s adapter={intent.get('adapter_hint')} "
        f"growth={(intent.get('power_fantasy') or {}).get('growth')}")
    collected: list[dict[str, Any]] = []
    batch = 0
    while len(collected) < per_theme and batch < per_theme:
        variant = VARIANTS[batch % len(VARIANTS)]
        batch += 1
        pf = dict(intent.get("power_fantasy") or {})
        pf.update({"start_power": variant["start_power"], "growth": variant["growth"]})
        batch_intent = {**intent, "power_fantasy": pf, "difficulty": variant["difficulty"]}
        overrides = intent_to_field_overrides(batch_intent)
        current = {
            **overrides,
            "difficulty": variant["difficulty"],
            "magic_level": spec["magic_level"],
            "_randomize_idea": spec["idea"],
            "_compose_intent": batch_intent,
            "_locked_fields": [],
            "_locked_values": {},
            "session_theme": session_theme or {},
            "_field_context": {"count_min": variant["count"][0], "count_max": variant["count"][1], "quantity_locked": False},
        }
        t1 = time.perf_counter()
        error = ""
        try:
            payload = generate_setup_randomization("special_abilities", current)
        except Exception as exc:
            payload, error = {}, f"{exc.__class__.__name__}: {exc}"
        seconds = round(time.perf_counter() - t1, 1)
        abilities = payload.get("special_abilities") if isinstance(payload, dict) else None
        abilities = abilities if isinstance(abilities, list) else []
        fallback = bool(payload.get("fallback_used")) if isinstance(payload, dict) else False
        log(f"{theme_id}: batch {batch} {variant['start_power']}/{variant['growth']}/{variant['difficulty']} "
            f"count {variant['count']} -> {len(abilities)} in {seconds}s{' FALLBACK' if fallback else ''}{' ERROR ' + error if error else ''}")
        magic_ok = magic_allows_mana(spec["magic_level"])
        for ab in abilities:
            if not isinstance(ab, dict):
                continue
            power_type = str(ab.get("power_type") or "linear")
            stamped = stamp_resource_cost(ab, magic_ok=magic_ok)
            cost_text = str(ab.get("cost") or "")
            charged = stamped.get("resource_cost") or {}
            cost_issues = []
            if re.search(r"\bmana\b", cost_text, re.I) and not magic_ok:
                cost_issues.append("mana_cost_in_no_magic_world")
            text_nums = {int(float(x)) for x in re.findall(r"\b(\d+(?:\.\d+)?)\b", cost_text)}
            engine_nums = {int(v) for k, v in charged.items() if isinstance(v, (int, float)) and v}
            if text_nums and not (text_nums & engine_nums):
                cost_issues.append("engine_charges_other_numbers_than_cost_text")
            row = {
                "theme": theme_id,
                "batch": batch,
                "variant": {**variant, "count": list(variant["count"])},
                "seconds": seconds,
                "fallback_used": fallback,
                "fallback_reason": payload.get("fallback_reason") if isinstance(payload, dict) else "",
                "name": ab.get("name"),
                "power_type": power_type,
                "locked": ab.get("locked"),
                "description": ab.get("description"),
                "prerequisites": ab.get("prerequisites"),
                "cost": cost_text,
                "growth_math": ab.get("growth_math"),
                "engine_resource_cost": charged,
                "cost_issues": cost_issues,
                "math": audit_growth_math(str(ab.get("growth_math") or ""), power_type, GROWTH_MATH_SAMPLES),
            }
            collected.append(row)
            jsonl(out / "abilities.jsonl", row)
        if error:
            jsonl(out / "abilities.jsonl", {"theme": theme_id, "batch": batch, "error": error, "seconds": seconds})
    return collected


def engine_use_check(theme_id: str, spec: dict[str, Any], rows: list[dict[str, Any]], out: Path) -> None:
    """Start a game with the theme's abilities and spend each one through apply_ability_use until it blocks."""
    from app import world
    from app.db import connect, init_db
    from app.player_resources import apply_ability_use

    init_db()
    seen: set[str] = set()
    abilities = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            abilities.append({k: r.get(k) for k in ("name", "description", "prerequisites", "cost", "growth_math", "power_type")}
                             | {"locked": False})
    try:
        world.start_playthrough({
            "player_name": "Probe", "start_location": "Low Gate", "special_ability_origin": "both",
            "magic_level": spec["magic_level"], "special_abilities": abilities,
        })
    except Exception as exc:
        jsonl(out / "engine.jsonl", {"theme": theme_id, "error": f"start_playthrough: {exc}"})
        return
    conn = connect()
    try:
        stored = [dict(r) for r in conn.execute("SELECT * FROM abilities").fetchall()]
        sent_types = {a["name"].lower(): a.get("power_type") for a in abilities}
        for ab in stored:
            uses, reasons, minute, rank_ups = 0, [], 0, 0
            for _ in range(12):
                res = apply_ability_use(conn, ab, options={"magic_level": spec["magic_level"]},
                                        world_time={"day": 1, "minute": minute}, turn=uses + 1)
                if not res.get("ok"):
                    reasons = res.get("reasons") or []
                    break
                uses += 1
                minute += 5
                rank_ups += sum(1 for e in (res.get("growth") or {}).get("events") or [] if e.get("type") == "rank_up")
            conn.commit()
            after = conn.execute("SELECT growth, growth_state FROM abilities WHERE id = ?", (ab["id"],)).fetchone()
            growth = json.loads(after["growth"] or "{}") if after else {}
            jsonl(out / "engine.jsonl", {
                "theme": theme_id, "name": ab["name"],
                "power_type_sent": sent_types.get(str(ab["name"]).lower()), "power_type_stored": ab.get("power_type"),
                "locked_after_start": ab.get("locked"), "resource_cost": ab.get("resource_cost"),
                "uses_before_block": uses, "blocked_by": reasons,
                # Engine growth (two-part system): template, the state after these uses, rank-ups seen.
                "growth_template": growth.get("template"), "growth_seed": {k: growth.get(k) for k in ("pace", "start", "grows")},
                "growth_state_after": json.loads(after["growth_state"] or "{}") if after else {},
                "rank_ups": rank_ups,
            })
    finally:
        conn.close()


# --- part 3: stages ------------------------------------------------------------------

STAGE_SYSTEM = (
    "You are the rules engine of a tabletop RPG. Apply the ability's growth_math exactly as written: no "
    "flavor, no rounding beyond what the math says. Show the arithmetic in 'work'. Reply with JSON only."
)


def _stage_label(thresholds: list[tuple[str, float]], xp: float) -> str | None:
    if not thresholds:
        return None
    label = None
    first = thresholds[0][0]
    for lab, need in thresholds:
        if xp >= need:
            label = lab
    if label is None:
        # Below the first threshold: the rank before it (F when the ladder starts at E, else level 1).
        if first in RANK_LADDER and RANK_LADDER.index(first) > 0:
            return RANK_LADDER[RANK_LADDER.index(first) - 1]
        return "1" if first.isdigit() else first
    return label


def level_ability(row: dict[str, Any], stages: int, out: Path) -> None:
    from app.llm import _chat_json

    math_info = row["math"]
    thresholds = [(str(a), float(b)) for a, b in math_info.get("thresholds") or []]
    per_use = math_info.get("per_use_xp")
    risk_tiers = math_info.get("risk_multipliers") or [1.0]
    # Session sizes aimed at the next stage when the math says how far it is; otherwise a doubling ladder.
    targets = [s["uses_at_low_risk"] for s in math_info.get("stage_uses") or []]
    state = {"rank": None, "xp_total": 0.0}
    rng = random.Random(f"{row['theme']}:{row['name']}")
    used_so_far = 0
    for step in range(1, stages + 1):
        if targets and step <= len(targets):
            # Enough low-risk uses to reach this stage, from the math's own curve.
            uses = max(1, min(400, targets[step - 1] - used_so_far))
        else:
            uses = [6, 15, 40, 100, 250, 600][min(step - 1, 5)]
        used_so_far += uses
        tier_index = rng.randrange(len(risk_tiers)) if risk_tiers else 0
        risk_word = ["safe practice", "contested", "dangerous", "life-risk", "extreme"][min(tier_index, 4)]
        user = json.dumps({
            "ability": {"name": row["name"], "power_type": row["power_type"], "growth_math": row["growth_math"]},
            "state_before": {"rank_or_level": state["rank"] or "starting", "xp_total": state["xp_total"]},
            "session": {"uses": uses, "successful_uses": uses, "risk": risk_word, "risk_tier": tier_index + 1},
            "return": {
                "xp_per_use": "number", "xp_gained": "number", "xp_total": "number",
                "rank_or_level": "label after this session", "xp_to_next": "number", "ranked_up": "bool",
                "effect_now": "short: what the ability does at this rank, with numbers", "work": "the arithmetic",
            },
        }, ensure_ascii=False)
        t0 = time.perf_counter()
        error = ""
        try:
            reply = _chat_json(STAGE_SYSTEM, user, timeout=300, phase="ability_stage_probe", max_tokens=700)
        except Exception as exc:
            reply, error = {}, f"{exc.__class__.__name__}: {exc}"
        seconds = round(time.perf_counter() - t0, 1)
        checks: dict[str, Any] = {}

        def num(key: str) -> float | None:
            try:
                return float(str(reply.get(key)).replace(",", ""))
            except (TypeError, ValueError):
                return None

        gained, total = num("xp_gained"), num("xp_total")
        if gained is not None and total is not None:
            checks["total_adds_up"] = abs(state["xp_total"] + gained - total) <= max(1.0, 0.01 * total)
        if per_use and gained is not None:
            mult = risk_tiers[tier_index] if risk_tiers else 1.0
            lo, hi = per_use[0] * uses * min(1.0, mult), per_use[1] * uses * max(1.0, mult) * 2  # crit / bonus slack
            checks["gain_within_per_use_math"] = lo * 0.5 <= gained <= hi
        label = str(reply.get("rank_or_level") or "").strip()
        expected = _stage_label(thresholds, total) if total is not None else None
        formula_values = math_info.get("formula_values") or []
        if not thresholds and formula_values and total is not None:
            # Levels from an XP_to_next formula. The math rarely says whether play starts at
            # level 0 or 1, so either reading counts; the level the reply names must be one of them.
            def level_for(start: int) -> int:
                level, need_acc = start, 0.0
                for v in formula_values:
                    need_acc += v
                    if total >= need_acc:
                        level += 1
                    else:
                        break
                return level

            said = re.findall(r"\d+", label)
            if said:
                options = {level_for(0), level_for(1)}
                checks["level_matches_formula"] = int(said[0]) in options
                checks["expected_level"] = sorted(options)
        if expected and label:
            checks["rank_matches_thresholds"] = expected.lower() in label.lower().split() or label.lower().startswith(expected.lower())
            checks["expected_rank"] = expected
        if state["rank"] and label and thresholds:
            order = [lab.lower() for lab, _ in thresholds]

            def pos(text: str) -> int:
                head = text.lower().replace("rank", "").replace("level", "").split()
                return order.index(head[0]) if head and head[0] in order else -1

            before_pos, after_pos = pos(state["rank"]), pos(label)
            if before_pos >= 0 and after_pos >= 0:
                checks["no_rank_regression"] = after_pos >= before_pos
        jsonl(out / "stages.jsonl", {
            "theme": row["theme"], "name": row["name"], "power_type": row["power_type"], "step": step,
            "uses": uses, "risk_tier": tier_index + 1, "seconds": seconds, "error": error,
            "state_before": dict(state), "reply": reply, "checks": checks,
        })
        if total is not None:
            state["xp_total"] = total
        if label:
            state["rank"] = label


# --- part 3b: real turns -----------------------------------------------------------------

def _find(value: Any, key: str) -> Any:
    """First value stored under `key` anywhere in a nested payload."""
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for v in value.values():
            found = _find(v, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for v in value:
            found = _find(v, key)
            if found is not None:
                return found
    return None


def real_turns(theme_id: str, spec: dict[str, Any], rows: list[dict[str, Any]], turns: int, out: Path) -> None:
    """Live turns using the theme's first (seed) ability: default DSL mode, then one JSON-mode turn."""
    from app import world
    from app.db import connect, init_db

    if not rows:
        return
    os.environ["AI_RPG_DRAFT_MODE"] = "dsl"
    init_db()
    first = rows[0]
    try:
        world.start_playthrough_with_opening({
            "player_name": "Probe", "start_location": "Low Gate", "special_ability_origin": "both",
            "magic_level": spec["magic_level"], "difficulty": first["variant"]["difficulty"],
            "special_abilities": [{k: first.get(k) for k in ("name", "description", "prerequisites", "cost", "growth_math", "power_type")} | {"locked": False}],
        })
    except Exception as exc:
        jsonl(out / "turns.jsonl", {"theme": theme_id, "error": f"opening: {exc}"})
        return

    def snapshot() -> dict[str, Any]:
        conn = connect()
        try:
            r = conn.execute("SELECT description, additions, growth_math, power_type, locked, prerequisites FROM abilities WHERE name = ?",
                             (first["name"],)).fetchone()
            return dict(r) if r else {}
        finally:
            conn.close()

    start = snapshot()
    locked_at_start = bool(start.get("locked"))
    if locked_at_start:
        # The start re-rolls locks; a locked seed cannot be used at all, so unlock it for the test.
        conn = connect()
        try:
            with conn:
                conn.execute("UPDATE abilities SET locked = 0 WHERE name = ?", (first["name"],))
        finally:
            conn.close()
    jsonl(out / "turns.jsonl", {"theme": theme_id, "ability": first["name"], "power_type": first["power_type"],
                                "locked_at_start": locked_at_start, "prerequisites": start.get("prerequisites")})

    plan = [("dsl", i) for i in range(1, turns + 1)] + [("json", turns + 1)]
    for mode, i in plan:
        os.environ["AI_RPG_DRAFT_MODE"] = mode
        before = snapshot()
        t0 = time.perf_counter()
        line = f"I use {first['name']} again, pushing it harder each time to train it."
        try:
            payload = world.play_turn(line)
            error = ""
        except Exception as exc:
            payload, error = {}, f"{exc.__class__.__name__}: {exc}"
        after = snapshot()
        narration = _find(payload, "narration")
        jsonl(out / "turns.jsonl", {
            "theme": theme_id, "turn": i, "draft_mode": mode, "ability": first["name"],
            "seconds": round(time.perf_counter() - t0, 1), "error": error,
            "used_fallback": bool(_find(payload, "used_fallback")),
            "ability_updates_in_payload": _find(payload, "ability_updates"),
            "ability_changed": before != after, "before": before, "after": after,
            "narration": str(narration or "")[:700],
        })
        log(f"{theme_id}: {mode} turn {i} {'changed' if before != after else 'unchanged'} in {time.perf_counter() - t0:.0f}s"
            f"{' (no narration)' if not narration else ''}")
    os.environ["AI_RPG_DRAFT_MODE"] = "dsl"


# --- summary --------------------------------------------------------------------------

def summarize(out: Path) -> dict[str, Any]:
    def read(name: str) -> list[dict[str, Any]]:
        path = out / name
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    from app.llm import GROWTH_MATH_SAMPLES

    abilities = [r for r in read("abilities.jsonl") if "name" in r]
    # Re-audit from the stored text, so a better checker also reads old runs.
    for r in abilities:
        r["math"] = audit_growth_math(str(r.get("growth_math") or ""), str(r.get("power_type") or ""), GROWTH_MATH_SAMPLES)
    stages = read("stages.jsonl")
    engine = read("engine.jsonl")
    turns = read("turns.jsonl")
    summary: dict[str, Any] = {"themes": {}}
    for theme in sorted({r["theme"] for r in abilities}):
        rows = [r for r in abilities if r["theme"] == theme]
        issues: dict[str, int] = {}
        for r in rows:
            for issue in r["math"]["issues"] + r["cost_issues"]:
                issues[issue] = issues.get(issue, 0) + 1
        st = [s for s in stages if s["theme"] == theme]
        check_rates: dict[str, str] = {}
        for key in ("total_adds_up", "gain_within_per_use_math", "rank_matches_thresholds", "level_matches_formula", "no_rank_regression"):
            vals = [s["checks"][key] for s in st if key in s.get("checks", {})]
            if vals:
                check_rates[key] = f"{sum(vals)}/{len(vals)}"
        en = [e for e in engine if e.get("theme") == theme and "name" in e]
        tu = [t for t in turns if t.get("theme") == theme and "turn" in t]
        # Group growth_math by template: same text once numbers are masked, allowing a changed noun.
        groups: list[list[str]] = []
        for r in rows:
            s = shape(r.get("growth_math"))
            for g in groups:
                if difflib.SequenceMatcher(None, s, g[0], autojunk=False).ratio() >= 0.8:
                    g.append(s)
                    break
            else:
                groups.append([s])
        summary["themes"][theme] = {
            "abilities": len(rows),
            "distinct_names": len({str(r["name"]).lower() for r in rows}),
            "distinct_math_templates": len(groups),
            "abilities_sharing_a_template": sum(len(g) for g in groups if len(g) > 1),
            "from_fallback": sum(1 for r in rows if r["fallback_used"]),
            "power_types": {p: sum(1 for r in rows if r["power_type"] == p) for p in sorted({r["power_type"] for r in rows})},
            "math_clean": sum(1 for r in rows if not r["math"]["issues"]),
            "issues": dict(sorted(issues.items(), key=lambda kv: -kv[1])),
            "median_gen_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2] if rows else None,
            "stage_checks": check_rates,
            "stage_errors": sum(1 for s in st if s.get("error")),
            "engine_power_type_lost": sum(1 for e in en if e.get("power_type_sent") and e.get("power_type_sent") != e.get("power_type_stored")),
            "engine_never_blocked_in_12_uses": sum(1 for e in en if e.get("uses_before_block") == 12),
            "engine_locked_after_start": f"{sum(1 for e in en if e.get('locked_after_start'))}/{len(en)}",
            "engine_growth_templates": {t: sum(1 for e in en if e.get("growth_template") == t)
                                        for t in sorted({e.get("growth_template") for e in en if e.get("growth_template")})},
            "engine_seeds_with_grows": sum(1 for e in en if (e.get("growth_seed") or {}).get("grows")),
            "engine_rank_ups_in_12_uses": sum(int(e.get("rank_ups") or 0) for e in en),
            "seed_locked_at_start": any(t.get("locked_at_start") for t in turns if t.get("theme") == theme and "locked_at_start" in t),
            "real_turns": len(tu),
            "real_turns_ability_changed": sum(1 for t in tu if t.get("ability_changed")),
            "dsl_turns_without_narration": sum(1 for t in tu if t.get("draft_mode") == "dsl" and not t.get("narration")),
            "json_turns_fallback": sum(1 for t in tu if t.get("draft_mode") == "json" and (t.get("used_fallback") or not t.get("narration"))),
        }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = ["# Ability growth run", "", f"Output: `{out}`", ""]
    for theme, s in summary["themes"].items():
        lines += [f"## {theme}", "", "```json", json.dumps(s, indent=2), "```", ""]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--themes", nargs="*", default=list(THEMES))
    ap.add_argument("--per-theme", type=int, default=25)
    ap.add_argument("--stages", type=int, default=5)
    ap.add_argument("--stage-sample", type=int, default=0, help="level only this many abilities per theme (0 = all)")
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--model", default=os.getenv("PLAYTEST_MLE_MODEL", DEFAULT_MODEL))
    ap.add_argument("--out", default="")
    ap.add_argument("--skip-stages", action="store_true")
    ap.add_argument("--skip-turns", action="store_true")
    ap.add_argument("--summarize", default="", help="only rebuild the summary of an existing run dir")
    args = ap.parse_args()
    if args.summarize:
        print(json.dumps(summarize(Path(args.summarize)), indent=2))
        return 0
    if not Path(args.model).is_file():
        print(f"model not found: {args.model}")
        return 2
    out = Path(args.out) if args.out else ROOT / "data" / "ability_runs" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    temp = isolate(args.model)
    from app.db import init_db
    from app.llm import update_model_config

    init_db()
    update_model_config({"provider": "mle", "mle_model": args.model})
    (out / "run.json").write_text(json.dumps({**vars(args), "temp_data": str(temp)}, indent=2), encoding="utf-8")
    log(f"model={args.model} out={out} temp={temp}")
    for theme_id in args.themes:
        spec = THEMES[theme_id]
        rows = generate_theme(theme_id, spec, args.per_theme, out)
        engine_use_check(theme_id, spec, rows, out)
        if not args.skip_stages:
            pick = rows if not args.stage_sample else rows[: args.stage_sample]
            for i, row in enumerate(pick, 1):
                log(f"{theme_id}: leveling {i}/{len(pick)} {row['name']!r}")
                level_ability(row, args.stages, out)
        if not args.skip_turns:
            real_turns(theme_id, spec, rows, args.turns, out)
        summarize(out)
    print(json.dumps(summarize(out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
