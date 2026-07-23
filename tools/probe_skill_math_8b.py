"""Generate several themed setups with qwen3:8b and score skill / growth math quality.

Usage:
  python tools/probe_skill_math_8b.py

Writes:
  docs/showcase/skill-math-probe-latest.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

THEMES = [
    {
        "id": "isekai_compound",
        "theme": "isekai_rpg",
        "idea": (
            "isekai, simple nearly useless seed skill with overpowered compounding growth, "
            "easy-medium difficulty, keep an edge, fair DM, no harem, no free OP start"
        ),
        "expect": {
            "compounding": True,
            "weak_seed": True,
            "need_growth_math": True,
            "dice_systemish": True,
        },
    },
    {
        "id": "system_apoc",
        "theme": "system_rpg",
        "idea": (
            "system apocalypse after the sky broke; status windows; hard difficulty; "
            "training-heavy skills; no free power spikes; political scavenger factions"
        ),
        "expect": {
            "compounding": False,
            "weak_seed": False,
            "need_growth_math": True,
            "dice_systemish": True,
        },
    },
    {
        "id": "grim_harbor",
        "theme": "grimdark",
        "idea": (
            "I wake in a rationed harbor city after a desk-job death. No destiny. "
            "Work, debt, nearly useless filing habit that only compounds if I risk real mistakes. "
            "Hard but fair, lasting injuries, scarce loot."
        ),
        "expect": {
            "compounding": True,
            "weak_seed": True,
            "need_growth_math": True,
            "dice_systemish": False,
        },
    },
    {
        "id": "cozy_river",
        "theme": "default",
        "idea": (
            "gentle pastoral mystery around a river village; soft danger, community ties, "
            "easy difficulty, low power fantasy, skills matter for craft and social reads"
        ),
        "expect": {
            "compounding": False,
            "weak_seed": False,
            "need_growth_math": False,
            "dice_systemish": False,
        },
    },
    {
        "id": "wuxia_sect",
        "theme": "default",
        "idea": (
            "wuxia sect politics and face culture; cultivation is slow and costly; "
            "normal difficulty; reputation and debts matter more than raw levels"
        ),
        "expect": {
            "compounding": False,
            "weak_seed": False,
            "need_growth_math": True,
            "dice_systemish": False,
        },
    },
]

# Core fields to generate after compose
FIELD_GROUPS = [
    "field:world_style",
    "field:tone",
    "field:difficulty",
    "field:game_system",
    "field:skill_style",
    "field:custom_skills",
    "field:skill_growth_speed",
    "field:proficiency_growth_speed",
    "field:xp_growth_speed",
    "field:rank_scale",
    "field:death_rules",
    "field:loot_rarity",
    "special_abilities",
]


def _has_calculable_math(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if len(raw) < 24:
        return False
    markers = (
        "xp",
        "rank",
        "threshold",
        "level",
        "×",
        "x0.",
        "x1",
        "x2",
        "x3",
        "*",
        "^",
        "%",
        "bonus",
        "soft cap",
        "per-use",
        "per use",
        "multiplier",
        "formula",
        "to_next",
        "to next",
    )
    digit = any(ch.isdigit() for ch in raw)
    return digit and any(m in raw for m in markers)


def _extract_numbers(text: str) -> list[float]:
    vals: list[float] = []
    for m in re.finditer(r"(?<![A-Za-z])(\d+(?:\.\d+)?)(?![A-Za-z])", text or ""):
        try:
            vals.append(float(m.group(1)))
        except ValueError:
            continue
    return vals


def _math_structure_score(math_text: str) -> dict[str, Any]:
    """Heuristic DM-usability score for a growth_math string (0-10)."""
    text = str(math_text or "").strip()
    checks = {
        "has_digits": bool(re.search(r"\d", text)),
        "has_xp_curve": bool(re.search(r"xp[_\s-]*to[_\s-]*next|threshold|rank\s*[→\->]|@\d+", text, re.I)),
        "has_per_use": bool(re.search(r"\d+\s*[-–]\s*\d+|grants?\s+\d|practice\s+\d|use\s+\d", text, re.I)),
        "has_risk_mult": bool(re.search(r"risk|contested|life[- ]?risk|×\s*\d|x\s*\d|safe", text, re.I)),
        "has_soft_cap": bool(re.search(r"soft\s*cap|after\s*[A-F0-9]|breakthrough|mentor|×0\.\d|x0\.\d", text, re.I)),
        "has_rank_bonus": bool(re.search(r"\+?\d+\s*(domain|check|bonus|%)|per\s*rank|rank\s*(bonus|above)", text, re.I)),
        "not_vague": not bool(re.search(r"^(gets stronger|improves over time|grows with use)\.?$", text, re.I)),
        "length_ok": 40 <= len(text) <= 800,
        "calculable": _has_calculable_math(text),
    }
    nums = _extract_numbers(text)
    # Sanity: thresholds should generally increase if multiple large ints
    large = sorted(n for n in nums if n >= 20)
    increasing = True
    if len(large) >= 3:
        increasing = all(large[i] <= large[i + 1] * 1.05 for i in range(len(large) - 1)) or all(
            large[i] <= large[i + 1] for i in range(min(3, len(large) - 1))
        )
    checks["thresholds_sensible"] = increasing if large else True

    weight = {
        "has_digits": 1.0,
        "has_xp_curve": 1.5,
        "has_per_use": 1.5,
        "has_risk_mult": 1.0,
        "has_soft_cap": 1.0,
        "has_rank_bonus": 1.0,
        "not_vague": 1.0,
        "length_ok": 0.5,
        "calculable": 1.5,
        "thresholds_sensible": 1.0,
    }
    earned = sum(weight[k] for k, ok in checks.items() if ok)
    total = sum(weight.values())
    score10 = round(10 * earned / total, 1)
    return {"score_10": score10, "checks": checks, "numbers": nums[:20], "text": text[:800]}


def _score_package(entry: dict[str, Any], fields: dict[str, Any], abilities: list[dict], expect: dict) -> dict[str, Any]:
    notes: list[str] = []
    scores: dict[str, float] = {}

    # Intent alignment
    intent = entry.get("intent") or {}
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    growth = str(pf.get("growth") or "").lower()
    start = str(pf.get("start_power") or "").lower()
    genre = str(intent.get("genre") or fields.get("world_style") or "").lower()
    difficulty = str(intent.get("difficulty") or fields.get("difficulty") or "").lower()

    theme_align = 7.0
    if expect.get("compounding") and growth not in {"compounding", "snowball", "exponential"}:
        # soft fail if custom_skills still encodes compound
        cs = str(fields.get("custom_skills") or "").lower()
        if "compound" in cs or "xp_to_next" in cs or "rank" in cs:
            notes.append("intent growth not marked compounding but custom_skills has growth language")
            theme_align = 6.0
        else:
            notes.append(f"expected compounding growth; intent.growth={growth!r}")
            theme_align = 4.0
    if expect.get("weak_seed") and start not in {"near_useless", "weak", "low", "useless"}:
        cs = str(fields.get("custom_skills") or "").lower()
        if any(w in cs for w in ("near-useless", "near useless", "weak", "rank f", "barely")):
            notes.append("weak seed via custom_skills language")
            theme_align = min(theme_align, 7.0)
        else:
            notes.append(f"expected weak seed; start_power={start!r}")
            theme_align = min(theme_align, 5.0)
    if entry.get("id") == "cozy_river" and difficulty in {"hard", "brutal"}:
        notes.append(f"cozy theme but difficulty={difficulty}")
        theme_align = min(theme_align, 5.0)
    if entry.get("id") == "system_apoc" and difficulty in {"easy"}:
        notes.append("system apoc rolled easy")
        theme_align = min(theme_align, 5.5)
    scores["theme_alignment"] = theme_align

    # Skill settings presence
    skill_fields_ok = 0
    for k in ("custom_skills", "skill_style", "skill_growth_speed", "rank_scale", "difficulty"):
        if str(fields.get(k) or "").strip():
            skill_fields_ok += 1
    scores["skill_settings"] = round(10 * skill_fields_ok / 5, 1)

    # Growth math on abilities
    math_scores: list[dict[str, Any]] = []
    for ab in abilities:
        if not isinstance(ab, dict):
            continue
        m = _math_structure_score(str(ab.get("growth_math") or ""))
        m["ability"] = str(ab.get("name") or "?")
        m["description"] = str(ab.get("description") or "")[:160]
        math_scores.append(m)

    if not math_scores and expect.get("need_growth_math"):
        scores["growth_math"] = 2.0
        notes.append("no special_abilities with growth_math")
    elif not math_scores:
        scores["growth_math"] = 7.0  # cozy may omit powers
        notes.append("no abilities (acceptable for low-power theme)")
    else:
        avg = sum(m["score_10"] for m in math_scores) / len(math_scores)
        # Fallback template sniff: exact sample match is ok but less original
        from app.llm import GROWTH_MATH_SAMPLES

        template_hits = sum(1 for m in math_scores if m["text"] in GROWTH_MATH_SAMPLES)
        if template_hits == len(math_scores) and expect.get("need_growth_math"):
            notes.append("all growth_math look like stock samples (fallback?)")
            avg = min(avg, 6.5)
        scores["growth_math"] = round(avg, 1)

    # custom_skills coherence with math
    cs = str(fields.get("custom_skills") or "")
    cs_score = 5.0
    if _has_calculable_math(cs):
        cs_score = 8.5
        notes.append("custom_skills includes calculable math (good for seeds)")
    elif expect.get("need_growth_math") and math_scores:
        # math on ability is enough
        cs_score = 7.5
    elif cs.strip():
        cs_score = 6.5
    else:
        cs_score = 4.0 if expect.get("need_growth_math") else 7.0
    scores["custom_skills"] = cs_score

    # Skill-check engine unit checks (formula: total = natural + attr_mod + skill_rank)
    from app.skill_checks import attribute_modifier, resolve_check, settings_from_setup

    setup_opts = {
        **fields,
        "session_theme": entry.get("session_theme") or {},
        "dice_checks_enabled": True,
        "contested_checks": True,
        "power_rng": False,  # deterministic DC
        "show_rolls_in_ui": True,
        "unskilled_mishaps": True,
        "fumble_on_natural_1": True,
    }
    check_settings = settings_from_setup(setup_opts)
    import random

    player_stats = {
        "strength": 12,
        "dexterity": 10,
        "constitution": 11,
        "intelligence": 14,
        "wisdom": 9,
        "charisma": 8,
    }
    player_skills = [
        {"code": "symbol_lore", "rank": 3},
        {"code": "melee", "rank": 0},
        {"code": "persuasion", "rank": 2},
    ]
    try:
        r1 = resolve_check(
            skill_code="symbol_lore",
            player_stats=player_stats,
            player_skills=player_skills,
            settings=check_settings,
            difficulty=str(fields.get("difficulty") or "normal"),
            rng=random.Random(42),
        )
        total = r1.get("total")
        natural = r1.get("natural")
        attr_mod = r1.get("attribute_mod")
        skill_rank = r1.get("skill_rank")
        engine_ok = True
        engine_notes = []
        # INT 14 → mod +2; symbol_lore rank 3 → total_mod +5
        expect_attr = attribute_modifier(14)
        if attr_mod != expect_attr:
            engine_ok = False
            engine_notes.append(f"attr_mod={attr_mod} expected {expect_attr} for INT 14")
        if skill_rank != 3:
            engine_ok = False
            engine_notes.append(f"skill_rank={skill_rank} expected 3")
        if (
            isinstance(natural, int)
            and isinstance(attr_mod, (int, float))
            and isinstance(skill_rank, (int, float))
            and total is not None
        ):
            expected_total = int(natural) + int(attr_mod) + int(skill_rank)
            if int(total) != expected_total:
                engine_ok = False
                engine_notes.append(
                    f"total={total} != natural({natural})+attr({attr_mod})+skill({skill_rank})={expected_total}"
                )
        # Contested DC should exceed static base when opposition is strong
        r_cont = resolve_check(
            skill_code="melee",
            player_stats=player_stats,
            player_skills=player_skills,
            settings=check_settings,
            difficulty="hard",
            opposition={"name": "Harbor Guard", "strength": 18, "level": 8, "defense": 16},
            weapon_or_tool="rusty sword",
            rng=random.Random(7),
        )
        r_static = resolve_check(
            skill_code="melee",
            player_stats=player_stats,
            player_skills=player_skills,
            settings={**check_settings, "contested_checks": False, "power_rng": False},
            difficulty="hard",
            weapon_or_tool="rusty sword",
            rng=random.Random(7),
        )
        if (r_cont.get("dc") or 0) < (r_static.get("dc") or 0):
            engine_notes.append(
                f"contested DC {r_cont.get('dc')} unexpectedly < static {r_static.get('dc')}"
            )
        scores["engine_math"] = 9.5 if engine_ok and not engine_notes else (7.0 if engine_ok else 4.0)
        if engine_notes:
            notes.extend(engine_notes)
        engine_samples = {
            "symbol_lore": {
                "natural": natural,
                "total": total,
                "dc": r1.get("dc"),
                "degree": r1.get("degree"),
                "outcome": r1.get("outcome"),
                "attribute_mod": attr_mod,
                "skill_rank": skill_rank,
                "lines": (r1.get("lines") or [])[:2],
            },
            "melee_contested": {
                "natural": r_cont.get("natural"),
                "total": r_cont.get("total"),
                "dc": r_cont.get("dc"),
                "dc_source": r_cont.get("dc_source"),
                "degree": r_cont.get("degree"),
                "unskilled": r_cont.get("unskilled"),
                "mishap": r_cont.get("mishap"),
            },
            "melee_static_hard": {
                "dc": r_static.get("dc"),
                "degree": r_static.get("degree"),
            },
        }
    except Exception as exc:
        scores["engine_math"] = 0.0
        engine_samples = {"error": str(exc)}
        notes.append(f"engine resolve failed: {exc}")

    overall = round(sum(scores.values()) / max(1, len(scores)), 1)
    return {
        "scores": scores,
        "overall_10": overall,
        "notes": notes,
        "math_details": math_scores,
        "engine_samples": engine_samples,
        "intent_snapshot": {
            "genre": intent.get("genre"),
            "difficulty": intent.get("difficulty") or fields.get("difficulty"),
            "isekai": intent.get("isekai"),
            "adapter_hint": intent.get("adapter_hint"),
            "power_fantasy": pf,
            "tone": intent.get("tone") or fields.get("tone"),
        },
    }


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_skill_math_"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "OLLAMA_MODEL": os.getenv("PLAYTEST_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:8b")),
        "OLLAMA_THINK": "0",
        "AI_RPG_OLLAMA_TIMEOUT": "360",
        "AI_RPG_SETUP_RANDOMIZER_TIMEOUT": "180",
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir()
    (temp / "traces").mkdir()
    sys.path.insert(0, str(ROOT))

    from app.db import init_db
    from app.llm import compose_setup_intent, generate_setup_randomization, update_model_config
    from app.setup_composer import intent_to_field_overrides, sanitize_setup_fields

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": os.environ["OLLAMA_MODEL"],
            "response_token_cap": 900,
            "response_token_hard_cap": 1400,
        }
    )

    print(f"model={os.environ['OLLAMA_MODEL']} temp={temp}", flush=True)
    report: list[dict[str, Any]] = []

    for entry in THEMES:
        pid = entry["id"]
        idea = entry["idea"]
        print(f"\n======== {pid} ({entry['theme']}) ========", flush=True)
        print(f"idea: {idea[:120]}...", flush=True)
        row: dict[str, Any] = {
            "id": pid,
            "theme": entry["theme"],
            "idea": idea,
            "fields": {},
            "abilities": [],
            "errors": [],
            "timings_s": {},
        }
        t0 = time.perf_counter()
        try:
            composed = compose_setup_intent(idea, {})
        except Exception as exc:
            row["errors"].append(f"compose: {exc}")
            composed = {}
        row["timings_s"]["compose"] = round(time.perf_counter() - t0, 1)
        intent = composed.get("intent") if isinstance(composed, dict) else {}
        theme = composed.get("session_theme") if isinstance(composed, dict) else {}
        source = composed.get("source") if isinstance(composed, dict) else "?"
        overrides = intent_to_field_overrides(intent or {})
        row["source"] = source
        row["intent"] = intent
        row["session_theme"] = theme
        row["field_overrides"] = overrides
        print(
            f"compose {row['timings_s']['compose']}s source={source} "
            f"genre={(intent or {}).get('genre')} diff={(intent or {}).get('difficulty')} "
            f"adapter={(intent or {}).get('adapter_hint')}",
            flush=True,
        )

        current: dict[str, Any] = {
            **overrides,
            "_randomize_idea": idea,
            "_compose_intent": intent,
            "_locked_fields": [],
            "_locked_values": {},
            "session_theme": theme or {"adapter_hint": entry["theme"]},
        }
        generated: dict[str, Any] = dict(overrides)

        for group in FIELD_GROUPS:
            t1 = time.perf_counter()
            try:
                payload = generate_setup_randomization(group, {**current, **generated})
                fields = payload.get("fields") if isinstance(payload, dict) else None
                if group == "special_abilities":
                    abs_list = None
                    if isinstance(payload, dict):
                        abs_list = payload.get("special_abilities")
                        if abs_list is None and isinstance(fields, dict):
                            abs_list = fields.get("special_abilities")
                    if isinstance(abs_list, list):
                        generated["special_abilities"] = abs_list
                        row["abilities"] = abs_list
                elif isinstance(fields, dict):
                    generated.update({k: v for k, v in fields.items() if v is not None})
                elif isinstance(payload, dict):
                    # direct field key
                    field_name = group.split(":", 1)[-1]
                    if field_name in payload:
                        generated[field_name] = payload[field_name]
                print(f"  {group}: {time.perf_counter()-t1:.1f}s", flush=True)
            except Exception as exc:
                row["errors"].append(f"{group}: {exc}")
                print(f"  {group} FAIL {exc}", flush=True)
            row["timings_s"][group] = round(time.perf_counter() - t1, 1)

        cleaned, dirty = sanitize_setup_fields(
            generated,
            idea=idea,
            context={**current, **generated, "_compose_intent": intent},
        )
        row["fields"] = cleaned
        row["dirty"] = dirty
        if isinstance(cleaned.get("special_abilities"), list):
            row["abilities"] = cleaned["special_abilities"]
        abilities = row["abilities"] if isinstance(row["abilities"], list) else []

        # Print samples
        for k in (
            "difficulty",
            "game_system",
            "world_style",
            "tone",
            "skill_style",
            "skill_growth_speed",
            "rank_scale",
            "custom_skills",
            "death_rules",
        ):
            if cleaned.get(k) is not None:
                print(f"  {k}: {str(cleaned[k])[:180]!r}", flush=True)
        for ab in abilities[:3]:
            if isinstance(ab, dict):
                print(
                    f"  ability: {ab.get('name')!r} math={str(ab.get('growth_math') or '')[:160]!r}",
                    flush=True,
                )

        scoring = _score_package(row, cleaned, abilities, entry["expect"])
        row["scoring"] = scoring
        print(
            f"  SCORE overall={scoring['overall_10']}/10 "
            f"math={scoring['scores'].get('growth_math')} "
            f"engine={scoring['scores'].get('engine_math')} "
            f"theme={scoring['scores'].get('theme_alignment')}",
            flush=True,
        )
        for n in scoring.get("notes") or []:
            print(f"    note: {n}", flush=True)
        row["wall_s"] = round(time.perf_counter() - t0, 1)
        report.append(row)

    # Aggregate
    overalls = [r["scoring"]["overall_10"] for r in report if r.get("scoring")]
    agg = {
        "model": os.environ["OLLAMA_MODEL"],
        "packages": len(report),
        "mean_overall_10": round(sum(overalls) / len(overalls), 1) if overalls else 0,
        "min_overall_10": min(overalls) if overalls else 0,
        "max_overall_10": max(overalls) if overalls else 0,
        "by_id": {r["id"]: r.get("scoring", {}).get("overall_10") for r in report},
        "math_means": {},
        "errors_total": sum(len(r.get("errors") or []) for r in report),
    }
    math_vals = []
    for r in report:
        sc = (r.get("scoring") or {}).get("scores") or {}
        if "growth_math" in sc:
            math_vals.append(sc["growth_math"])
    agg["math_means"]["growth_math"] = round(sum(math_vals) / len(math_vals), 1) if math_vals else 0
    engine_vals = [
        ((r.get("scoring") or {}).get("scores") or {}).get("engine_math")
        for r in report
        if ((r.get("scoring") or {}).get("scores") or {}).get("engine_math") is not None
    ]
    agg["math_means"]["engine_math"] = round(sum(engine_vals) / len(engine_vals), 1) if engine_vals else 0

    out = {
        "summary": agg,
        "packages": report,
    }
    dest = ROOT / "docs" / "showcase" / "skill-math-probe-latest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    (temp / "skill_math_probe.json").write_text(json.dumps(out, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

    print("\n======== SUMMARY ========", flush=True)
    print(json.dumps(agg, indent=2), flush=True)
    print(f"report: {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
