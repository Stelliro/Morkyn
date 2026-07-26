"""Generate skills/abilities with qwen3:8b and audit for holes, bugs, and wrongness.

Usage:
  python tools/audit_skills_8b.py

Writes:
  docs/showcase/skill-8b-audit-latest.json
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

SCENARIOS = [
    {
        "id": "isekai_weak_seed",
        "idea": (
            "isekai ordinary to overpowered; nearly useless seed skill that compounds; "
            "fair DM; no free arsenal; subtle system window"
        ),
        "origin": "acquired",
        "count_min": 1,
        "count_max": 2,
        "world_style": "Mundane isekai compound",
        "magic_level": "cultivation",
        "one_skillish": True,
    },
    {
        "id": "grim_work",
        "idea": "grim harbor work, debt, filing habit, hard fair, no destiny",
        "origin": "innate",
        "count_min": 1,
        "count_max": 2,
        "world_style": "rationed harbor city",
        "magic_level": "rare",
        "one_skillish": False,
    },
    {
        "id": "wuxia_both",
        "idea": "wuxia sect politics, slow cultivation, reputation debts",
        "origin": "both",
        "count_min": 2,
        "count_max": 3,
        "world_style": "wuxia mountain sect",
        "magic_level": "cultivation",
        "one_skillish": False,
    },
    {
        "id": "cozy_craft",
        "idea": "gentle river village mystery, craft and social skills matter, easy",
        "origin": "acquired",
        "count_min": 1,
        "count_max": 2,
        "world_style": "pastoral river village",
        "magic_level": "rare",
        "one_skillish": False,
    },
]


def _audit_ability(ab: dict[str, Any], *, origin: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    name = str(ab.get("name") or "")
    desc = str(ab.get("description") or "")
    cost = str(ab.get("cost") or "")
    prereq = str(ab.get("prerequisites") or "")
    math = str(ab.get("growth_math") or "")
    locked = bool(ab.get("locked"))
    low_all = f"{name} {desc} {cost} {prereq} {math}".lower()

    # Structural bugs
    if prereq.strip() in {"[]", "{}", "null", "None"} or re.fullmatch(r"\[\s*\]", prereq.strip()):
        findings.append({"sev": "bug", "code": "prereq_json_placeholder", "detail": repr(prereq)})
    if isinstance(ab.get("prerequisites"), (list, dict)):
        findings.append({"sev": "bug", "code": "prereq_not_string", "detail": type(ab.get("prerequisites")).__name__})
    if locked and len(prereq.strip()) < 8:
        findings.append({"sev": "bug", "code": "locked_empty_prereq", "detail": f"locked={locked} prereq={prereq!r}"})
    if not name.strip():
        findings.append({"sev": "bug", "code": "missing_name", "detail": ""})
    if len(desc.strip()) < 36:
        findings.append({"sev": "wrong", "code": "thin_description", "detail": desc[:80]})

    # Timing / cost contradictions (lightweight)
    if re.search(r"once per day", desc, re.I) and re.search(r"once per hour|1 hour|every hour", cost, re.I):
        findings.append({"sev": "bug", "code": "use_limit_vs_recharge", "detail": "desc once/day vs cost hour"})
    if re.search(r"\bno cost\b|\bfree\b", cost, re.I) and re.search(
        r"\b(kill|invulnerab|dominate|annihilat|instant)\b", desc, re.I
    ):
        findings.append({"sev": "wrong", "code": "strong_power_free", "detail": "strong wording with free cost"})

    # Mild power wrongly locked
    mildish = any(
        x in low_all
        for x in (
            "minor distraction",
            "briefly",
            "mimic",
            "once per day",
            "slight ",
            "small ",
            "utility",
        )
    ) and not any(x in low_all for x in ("invulnerab", "instant kill", "mind control", "always on"))
    if mildish and locked and (not prereq.strip() or prereq.strip() in {"[]"} or "training, a mentor" in prereq.lower()):
        findings.append(
            {
                "sev": "wrong",
                "code": "mild_locked_generic",
                "detail": "mild utility locked behind empty/generic prereq",
            }
        )

    # Growth math quality
    if len(math.strip()) < 24:
        findings.append({"sev": "hole", "code": "growth_math_missing", "detail": math[:60]})
    elif not re.search(r"\d", math):
        findings.append({"sev": "hole", "code": "growth_math_no_numbers", "detail": math[:100]})
    elif not re.search(r"xp|rank|threshold|level|bonus|%|×|x\d", math, re.I):
        findings.append({"sev": "hole", "code": "growth_math_not_calculable", "detail": math[:120]})

    # Meta / template leaks
    if re.search(r"\b(op mc|one.skill frame|quality gate|growth_math|power_type)\b", desc, re.I):
        findings.append({"sev": "bug", "code": "meta_leak_in_description", "detail": desc[:100]})
    if re.search(r"barely useful at f rank;\s*practice and risk compound", desc, re.I):
        findings.append({"sev": "wrong", "code": "boilerplate_description", "detail": ""})
    if re.search(r"spend\s+1\s+hour\s+each\s+(day|dawn)", cost, re.I):
        findings.append({"sev": "wrong", "code": "maintenance_hour_template", "detail": cost[:100]})

    # Origin mismatch vibes
    if origin == "innate" and locked and "awaken" not in prereq.lower() and "remnant" not in prereq.lower():
        findings.append({"sev": "hole", "code": "innate_locked_odd", "detail": prereq[:80]})

    # Overpowered seed language for ordinary start
    if re.search(r"\b(sss|ss-rank|god.?slay|auto.?win|unlimited)\b", desc, re.I):
        findings.append({"sev": "wrong", "code": "overtuned_opening_fiction", "detail": desc[:120]})

    return findings


def _audit_custom_skills(text: str, *, one_skillish: bool) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    raw = str(text or "").strip()
    if not raw:
        findings.append({"sev": "hole", "code": "custom_skills_empty", "detail": ""})
        return findings
    low = raw.lower()
    if one_skillish and "weak seed" not in low and "seed skill" not in low and "rank f" not in low:
        findings.append({"sev": "hole", "code": "missing_weak_seed_frame", "detail": raw[:160]})
    if one_skillish and not re.search(r"\d", raw) and "xp" not in low:
        findings.append({"sev": "hole", "code": "seed_skills_no_math", "detail": raw[:160]})
    if re.search(r"\b(all skills unlocked|level 99|destined hero)\b", low):
        findings.append({"sev": "wrong", "code": "free_power_slogan", "detail": raw[:120]})
    return findings


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_skill_audit_"))
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
        "AI_RPG_OLLAMA_TIMEOUT": "420",
        "AI_RPG_SETUP_RANDOMIZER_TIMEOUT": "240",
        "AI_RPG_DEBUG": "1",
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    (temp / "traces").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.db import init_db
    from app.llm import (
        estimate_ability_opening_strength,
        generate_setup_randomization,
        normalize_ability_lock_and_prerequisites,
        quality_gate_abilities,
        test_model_connection,
        update_model_config,
    )

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": os.environ["OLLAMA_MODEL"],
            "response_token_cap": 1000,
            "response_token_hard_cap": 1600,
        }
    )
    conn = test_model_connection()
    print(f"model={os.environ['OLLAMA_MODEL']} conn={conn} temp={temp}", flush=True)
    if not conn.get("ok"):
        print("MODEL CONNECTION FAILED", conn, flush=True)
        return 2

    report: dict[str, Any] = {
        "model": os.environ["OLLAMA_MODEL"],
        "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scenarios": [],
        "summary": {"bugs": 0, "wrong": 0, "holes": 0, "abilities": 0},
    }

    for sc in SCENARIOS:
        print(f"\n======== {sc['id']} ========", flush=True)
        row: dict[str, Any] = {
            "id": sc["id"],
            "idea": sc["idea"],
            "origin": sc["origin"],
            "abilities_raw": [],
            "abilities_normalized": [],
            "custom_skills": "",
            "quality_gate": {},
            "findings": [],
            "errors": [],
            "timings_s": {},
        }
        current = {
            "_randomize_idea": sc["idea"],
            "_compose_intent": {
                "isekai": "isekai" in sc["idea"].lower(),
                "genre": sc["world_style"],
                "power_fantasy": {
                    "start_power": "near_useless" if sc.get("one_skillish") else "ordinary",
                    "growth": "compounding" if sc.get("one_skillish") else "steady",
                    "system_ui": "system" in sc["idea"].lower(),
                },
            },
            "_locked_fields": [],
            "_locked_values": {},
            "world_style": sc["world_style"],
            "magic_level": sc["magic_level"],
            "special_ability_origin": sc["origin"],
            "difficulty": "normal",
            "tone": "grounded adventure",
            "game_system": True,
            "skill_style": "standard",
            "_field_context": {
                "ability_origin": sc["origin"],
                "count_min": sc["count_min"],
                "count_max": sc["count_max"],
                "quantity_locked": False,
                "one_skillish": bool(sc.get("one_skillish")),
            },
        }

        # custom_skills
        t0 = time.perf_counter()
        try:
            cs_payload = generate_setup_randomization("field:custom_skills", current)
            fields = cs_payload.get("fields") if isinstance(cs_payload, dict) else {}
            if isinstance(fields, dict) and fields.get("custom_skills"):
                row["custom_skills"] = str(fields.get("custom_skills") or "")
            elif isinstance(cs_payload, dict) and cs_payload.get("custom_skills"):
                row["custom_skills"] = str(cs_payload.get("custom_skills") or "")
            print(f"  custom_skills {time.perf_counter()-t0:.1f}s len={len(row['custom_skills'])}", flush=True)
        except Exception as exc:
            row["errors"].append(f"custom_skills: {exc}")
            print(f"  custom_skills FAIL {exc}", flush=True)
        row["timings_s"]["custom_skills"] = round(time.perf_counter() - t0, 1)
        current["custom_skills"] = row["custom_skills"]

        # special_abilities
        t1 = time.perf_counter()
        try:
            ab_payload = generate_setup_randomization("special_abilities", current)
            abs_list = None
            if isinstance(ab_payload, dict):
                abs_list = ab_payload.get("special_abilities")
                fields = ab_payload.get("fields")
                if abs_list is None and isinstance(fields, dict):
                    abs_list = fields.get("special_abilities")
            if not isinstance(abs_list, list):
                abs_list = []
            row["abilities_raw"] = abs_list
            print(f"  special_abilities {time.perf_counter()-t1:.1f}s n={len(abs_list)}", flush=True)
            for ab in abs_list:
                if isinstance(ab, dict):
                    print(
                        f"    - {ab.get('name')!r} locked={ab.get('locked')} "
                        f"prereq={str(ab.get('prerequisites') or '')[:50]!r}",
                        flush=True,
                    )
        except Exception as exc:
            row["errors"].append(f"special_abilities: {exc}")
            print(f"  special_abilities FAIL {exc}", flush=True)
            abs_list = []
        row["timings_s"]["special_abilities"] = round(time.perf_counter() - t1, 1)

        # Quality gate + normalize
        gate = quality_gate_abilities(
            abs_list,
            one_skillish=bool(sc.get("one_skillish")),
            origin=sc["origin"],
            require_strong_math=bool(sc.get("one_skillish")),
            auto_repair=True,
        )
        row["quality_gate"] = {
            "ok": gate.get("ok"),
            "score": gate.get("score"),
            "denial_summary": gate.get("denial_summary"),
        }
        repaired = gate.get("abilities") if isinstance(gate.get("abilities"), list) else abs_list
        normalized = []
        for ab in repaired:
            if not isinstance(ab, dict):
                continue
            n = normalize_ability_lock_and_prerequisites(ab, origin=sc["origin"])
            n["_opening_strength"] = estimate_ability_opening_strength(n)
            normalized.append(n)
        row["abilities_normalized"] = normalized

        # Audit
        findings: list[dict[str, str]] = []
        findings.extend(_audit_custom_skills(row["custom_skills"], one_skillish=bool(sc.get("one_skillish"))))
        if not normalized and sc["origin"] != "none":
            findings.append({"sev": "bug", "code": "no_abilities_returned", "detail": "expected abilities"})
        for ab in normalized:
            findings.extend(_audit_ability(ab, origin=sc["origin"]))
        # Batch-level
        names = [str(a.get("name") or "").lower() for a in normalized]
        if len(names) != len(set(names)):
            findings.append({"sev": "bug", "code": "duplicate_ability_names", "detail": str(names)})
        costs = [re.sub(r"\s+", " ", str(a.get("cost") or "").lower())[:50] for a in normalized]
        if len(costs) >= 2 and len(set(costs)) == 1 and costs[0]:
            findings.append({"sev": "wrong", "code": "identical_costs", "detail": costs[0]})
        prereqs = [re.sub(r"\s+", " ", str(a.get("prerequisites") or "").lower())[:60] for a in normalized if str(a.get("prerequisites") or "").strip()]
        if len(prereqs) >= 2 and len(set(prereqs)) == 1:
            findings.append({"sev": "hole", "code": "identical_prereqs", "detail": prereqs[0]})

        row["findings"] = findings
        for fnd in findings:
            sev = fnd.get("sev") or "hole"
            report["summary"][sev if sev in report["summary"] else "holes"] = report["summary"].get(
                sev if sev in {"bugs", "wrong", "holes"} else "holes", 0
            )
            # map sev names
            key = {"bug": "bugs", "wrong": "wrong", "hole": "holes"}.get(sev, "holes")
            report["summary"][key] = int(report["summary"].get(key) or 0) + 1
        report["summary"]["abilities"] = int(report["summary"].get("abilities") or 0) + len(normalized)

        print(f"  gate ok={gate.get('ok')} score={gate.get('score')} findings={len(findings)}", flush=True)
        for fnd in findings:
            print(f"    [{fnd['sev']}] {fnd['code']}: {fnd.get('detail','')[:100]}", flush=True)

        report["scenarios"].append(row)

    out = ROOT / "docs" / "showcase" / "skill-8b-audit-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out}", flush=True)
    print("SUMMARY", json.dumps(report["summary"]), flush=True)
    return 0 if report["summary"].get("bugs", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
