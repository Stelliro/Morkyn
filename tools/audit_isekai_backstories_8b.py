"""Generate diverse isekai/transmigration origins+backstories on qwen3:8b and audit holes.

Usage:
  python tools/audit_isekai_backstories_8b.py
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

# Distinct origin archetypes the pipeline must support
ORIGINS = [
    {
        "id": "truck_kun_summon",
        "idea": "isekai truck accident, woke on a dirt road in a fantasy compound, ordinary to overpowered",
        "expect_mode": ("transmigrated", "known"),
        "expect_markers": ("died", "woke", "another world", "road", "truck", "accident", "portal", "transported"),
        "world_style": "Mundane isekai compound",
    },
    {
        "id": "body_transmigration",
        "idea": "transmigrated into the body of a debt-ridden compound clerk, former office life memories, no free power",
        "expect_mode": ("transmigrated",),
        "expect_markers": ("body", "clerk", "debt", "office", "remember", "this body", "woke in"),
        "world_style": "Mundane isekai compound",
    },
    {
        "id": "reincarnated_childhood",
        "idea": "reincarnated as a village child years ago, grew up local, remembers fragments of modern life",
        "expect_mode": ("reincarnated",),
        "expect_markers": ("reborn", "reincarnat", "grew up", "child", "years", "village", "fragment"),
        "world_style": "low magic frontier kingdom",
    },
    {
        "id": "summoned_ritual",
        "idea": "summoned by a failed ritual into a sect outer court, still wearing city clothes, hard fair",
        "expect_mode": ("transmigrated", "known"),
        "expect_markers": ("summon", "ritual", "sect", "clothes", "city"),
        "world_style": "wuxia mountain sect",
    },
    {
        "id": "near_future_tech_drop",
        "idea": "near-future maintenance tech died on the job, isekai into cultivation compound, transmigrated",
        "expect_mode": ("transmigrated",),
        "expect_markers": ("maintenance", "technician", "died", "woke", "repair", "city", "compound", "mender", "yard"),
        "world_style": "Mundane isekai compound",
    },
    {
        "id": "desk_job_portal",
        "idea": "died at a desk job and woke in another world last night, pure isekai arrival",
        "expect_mode": ("transmigrated", "known"),
        "expect_markers": ("desk", "died", "woke", "another world", "last night", "office"),
        "world_style": "isekai dark fantasy",
    },
]


def audit_package(row: dict[str, Any], expect: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    mode = str(row.get("backstory_mode") or "").lower()
    memory = str(row.get("memory_policy") or "").lower()
    story = str(row.get("character_backstory") or "").strip()
    story_l = story.lower()
    prev_age = str(row.get("previous_life_age") or "").strip()
    prev_sex = str(row.get("previous_life_sex") or "").strip()

    if len(story) < 140:
        findings.append({"sev": "bug", "code": "story_too_short", "detail": story[:100]})
    if re.search(r"\bI\b|\bmy\b|\bI'm\b|\bI've\b", story) and not re.search(r"\bthey\b|\btheir\b", story_l):
        findings.append({"sev": "wrong", "code": "first_person_backstory", "detail": story[:80]})
    if story_l.count("another world") + story_l.count("new world") >= 3:
        findings.append({"sev": "wrong", "code": "vague_world_spam", "detail": "repeats 'another world'"})

    # Mode coherence
    expect_modes = expect.get("expect_mode") or ()
    if expect_modes and not any(m in mode for m in expect_modes):
        findings.append(
            {
                "sev": "hole",
                "code": "mode_mismatch",
                "detail": f"mode={mode!r} expected one of {expect_modes}",
            }
        )

    # Reincarnated should imply lived/grew up here, not pure truck-kun last night
    if "reincarnat" in mode:
        if not any(m in story_l for m in ("grew up", "years", "child", "raised", "born in", "village", "childhood")):
            findings.append({"sev": "hole", "code": "reincarnated_without_this_life", "detail": story[:120]})
        if re.search(r"woke (on|up).{0,40}(last night|this morning|dirt road)", story_l):
            findings.append({"sev": "wrong", "code": "reincarnated_reads_as_fresh_arrival", "detail": story[:120]})

    # Transmigrated / pure isekai should mention arrival or body change or death
    if "transmigrat" in mode or "isekai" in expect.get("id", ""):
        arrivalish = any(
            m in story_l
            for m in (
                "died",
                "woke",
                "summon",
                "portal",
                "transmigrat",
                "transported",
                "another world",
                "this body",
                "into the body",
                "opened my eyes",
                "opened their eyes",
            )
        )
        if not arrivalish and "reincarnat" not in mode:
            findings.append({"sev": "hole", "code": "transmigrated_missing_arrival", "detail": story[:140]})

    # Memory policy vs story
    if "remembers former life" in memory:
        if not any(m in story_l for m in ("former", "previous", "before dying", "old life", "remember", "memory", "desk", "office", "city", "modern")):
            # still ok if death/woke with intact job details
            if not any(m in story_l for m in ("died", "technician", "clerk", "student", "job")):
                findings.append({"sev": "hole", "code": "memory_full_but_no_former_detail", "detail": memory})
    if memory in {"known", "ordinary memory"} and any(m in story_l for m in ("fragment", "half-memor", "barely remember")):
        findings.append({"sev": "hole", "code": "memory_clear_but_story_fragmented", "detail": memory})

    # Expect marker coverage (at least one family of markers)
    markers = expect.get("expect_markers") or ()
    if markers and not any(m in story_l for m in markers):
        findings.append(
            {
                "sev": "hole",
                "code": "missing_origin_markers",
                "detail": f"none of {markers[:6]} in story",
            }
        )

    # Previous life fields
    if any(m in mode for m in ("transmigrat", "reincarnat")):
        # optional but if filled must look like ages
        if prev_age and not re.search(r"\d", prev_age):
            findings.append({"sev": "bug", "code": "previous_life_age_not_numeric", "detail": prev_age})

    # Misconceptions / cliches
    if re.search(r"\b(chosen one|destined hero|level 99|all skills unlocked)\b", story_l):
        findings.append({"sev": "wrong", "code": "chosen_one_cliche", "detail": story[:100]})
    if re.search(r"\b(noble bloodline|secret heir|revenge for my family)\b", story_l):
        findings.append({"sev": "wrong", "code": "default_noble_revenge", "detail": story[:100]})

    # Local job + earth job confusion without framing
    has_earth = any(m in story_l for m in ("office", "desk", "tokyo", "smartphone", "subway", "near-future", "maintenance tech"))
    has_local = any(m in story_l for m in ("compound", "sect", "guild", "village", "yard mender", "canal"))
    if has_earth and has_local:
        framed = any(m in story_l for m in ("former", "previous", "before", "died", "woke", "memory", "dream", "this life", "this body"))
        if not framed:
            findings.append({"sev": "wrong", "code": "earth_and_local_unframed", "detail": "both lives mentioned without transition"})

    return findings


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_bs_audit_"))
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
        "AI_RPG_SETUP_RANDOMIZER_TIMEOUT": "200",
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    (temp / "traces").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.db import init_db
    from app.llm import compose_setup_intent, generate_setup_randomization, test_model_connection, update_model_config
    from app.setup_composer import intent_to_field_overrides, sanitize_setup_fields
    from app.starter_logic import fact_check_starter_loadout

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
    conn = test_model_connection()
    print(f"model={os.environ['OLLAMA_MODEL']} ok={conn.get('ok')}", flush=True)
    if not conn.get("ok"):
        return 2

    report: dict[str, Any] = {"model": os.environ["OLLAMA_MODEL"], "scenarios": [], "summary": {}}
    totals = {"bugs": 0, "wrong": 0, "holes": 0}

    for origin in ORIGINS:
        print(f"\n======== {origin['id']} ========", flush=True)
        row: dict[str, Any] = {"id": origin["id"], "idea": origin["idea"], "errors": [], "findings": []}
        t0 = time.perf_counter()
        try:
            composed = compose_setup_intent(origin["idea"], {})
        except Exception as exc:
            composed = {}
            row["errors"].append(f"compose:{exc}")
        intent = composed.get("intent") if isinstance(composed, dict) else {}
        overrides = intent_to_field_overrides(intent or {})
        row["compose_s"] = round(time.perf_counter() - t0, 1)
        row["intent"] = {
            "isekai": (intent or {}).get("isekai"),
            "portal_or_rebirth": (intent or {}).get("portal_or_rebirth"),
            "genre": (intent or {}).get("genre"),
            "adapter_hint": (intent or {}).get("adapter_hint"),
        }
        row["overrides"] = {
            k: overrides.get(k)
            for k in ("backstory_mode", "memory_policy", "world_style", "special_ability_origin")
            if k in overrides
        }
        print(f"  compose {row['compose_s']}s intent={row['intent']} overrides={row['overrides']}", flush=True)

        current = {
            **overrides,
            "_randomize_idea": origin["idea"],
            "_compose_intent": intent,
            "_locked_fields": [],
            "world_style": overrides.get("world_style") or origin["world_style"],
            "backstory_mode": overrides.get("backstory_mode") or "transmigrated",
            "memory_policy": overrides.get("memory_policy") or "remembers former life",
        }

        # Generate identity package (character group has mode+story) then single-field backstory if thin
        t1 = time.perf_counter()
        try:
            # mode
            for group in ("field:backstory_mode", "field:memory_policy", "field:character_backstory", "field:previous_life_age", "field:previous_life_sex"):
                try:
                    payload = generate_setup_randomization(group, current)
                    fields = payload.get("fields") if isinstance(payload, dict) else None
                    if isinstance(fields, dict):
                        current.update({k: v for k, v in fields.items() if v is not None})
                    else:
                        for k, v in (payload or {}).items():
                            if k.startswith("_") or k in {"notes", "quality_gate"}:
                                continue
                            if v is not None:
                                current[k] = v
                except Exception as exc:
                    row["errors"].append(f"{group}:{exc}")
            print(f"  gen {time.perf_counter()-t1:.1f}s", flush=True)
        except Exception as exc:
            row["errors"].append(f"gen:{exc}")

        cleaned, dirty = sanitize_setup_fields(
            {
                "backstory_mode": current.get("backstory_mode"),
                "memory_policy": current.get("memory_policy"),
                "character_backstory": current.get("character_backstory"),
                "previous_life_age": current.get("previous_life_age"),
                "previous_life_sex": current.get("previous_life_sex"),
                "starter_equipment": current.get("starter_equipment")
                or "frayed maintenance vest, small tool pouch, water flask, cracked gloves, worn boots",
                "appearance": current.get("appearance") or "torso: frayed maintenance vest; feet: worn boots",
                "world_style": current.get("world_style") or origin["world_style"],
                "tech_level": current.get("tech_level") or "medieval",
            },
            idea=origin["idea"],
            context={"_compose_intent": intent, **current},
        )
        row["backstory_mode"] = cleaned.get("backstory_mode")
        row["memory_policy"] = cleaned.get("memory_policy")
        row["character_backstory"] = cleaned.get("character_backstory")
        row["previous_life_age"] = cleaned.get("previous_life_age")
        row["previous_life_sex"] = cleaned.get("previous_life_sex")
        row["starter_equipment"] = cleaned.get("starter_equipment")
        row["dirty"] = dirty

        # Starter logic may rewrite origin
        try:
            fc = fact_check_starter_loadout(
                starter_equipment=str(cleaned.get("starter_equipment") or ""),
                appearance=str(cleaned.get("appearance") or ""),
                backstory_mode=str(cleaned.get("backstory_mode") or ""),
                memory_policy=str(cleaned.get("memory_policy") or ""),
                character_backstory=str(cleaned.get("character_backstory") or ""),
                intent=intent if isinstance(intent, dict) else {"isekai": True},
                world_style=str(cleaned.get("world_style") or origin["world_style"]),
                tech_level=str(cleaned.get("tech_level") or "medieval"),
                magic_level="cultivation",
                apply_fixes=True,
            )
            row["after_starter_logic"] = {
                "arrival": (fc.get("arrival") or {}).get("arrival"),
                "vibe": fc.get("vibe"),
                "character_backstory": fc.get("character_backstory"),
                "backstory_mode": fc.get("backstory_mode"),
                "memory_policy": fc.get("memory_policy"),
                "starter_equipment": fc.get("starter_equipment"),
            }
            # Prefer post-harmonize story for audit of final package
            row["final_story"] = fc.get("character_backstory") or row["character_backstory"]
            row["final_mode"] = fc.get("backstory_mode") or row["backstory_mode"]
            row["final_memory"] = fc.get("memory_policy") or row["memory_policy"]
        except Exception as exc:
            row["errors"].append(f"starter_logic:{exc}")
            row["final_story"] = row["character_backstory"]
            row["final_mode"] = row["backstory_mode"]
            row["final_memory"] = row["memory_policy"]

        audit_row = {
            "backstory_mode": row.get("final_mode"),
            "memory_policy": row.get("final_memory"),
            "character_backstory": row.get("final_story"),
            "previous_life_age": row.get("previous_life_age"),
            "previous_life_sex": row.get("previous_life_sex"),
        }
        findings = audit_package(audit_row, origin)
        # Also audit pre-harmonize if different
        if (row.get("character_backstory") or "") != (row.get("final_story") or ""):
            pre = audit_package(
                {
                    "backstory_mode": row.get("backstory_mode"),
                    "memory_policy": row.get("memory_policy"),
                    "character_backstory": row.get("character_backstory"),
                },
                origin,
            )
            for fnd in pre:
                fnd["phase"] = "pre_starter_logic"
                findings.append(fnd)

        row["findings"] = findings
        for fnd in findings:
            key = {"bug": "bugs", "wrong": "wrong", "hole": "holes"}.get(fnd["sev"], "holes")
            totals[key] = totals.get(key, 0) + 1

        print(f"  mode={row.get('final_mode')} memory={row.get('final_memory')}", flush=True)
        print(f"  story: {str(row.get('final_story') or '')[:220]}", flush=True)
        for fnd in findings:
            print(f"    [{fnd['sev']}] {fnd['code']}: {fnd.get('detail','')[:100]}", flush=True)

        report["scenarios"].append(row)

    report["summary"] = totals
    out = ROOT / "docs" / "showcase" / "isekai-backstory-audit-latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nSUMMARY", totals, "->", out, flush=True)
    return 0 if totals.get("bugs", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
