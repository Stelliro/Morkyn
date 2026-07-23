"""Probe setup compose + key-field generation for several idea prompts.

Reports intent, overrides, sample generated fields, and a crude originality rubric
(anti harem / free-OP / chosen-one).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PROMPTS = [
    {
        "id": "primary_isekai",
        "idea": (
            "isekai, simple or near useless skill with overpowered compounding skill increase, "
            "easy-medium difficulty, keep an edge, not too hard"
        ),
        "want": "Original isekai, weak seed + compound, fair edge, NOT harem/lovey/free-OP MC",
    },
    {
        "id": "grim_port",
        "idea": (
            "I wake in a rationed harbor city after dying at a desk job. No destiny, no harem. "
            "Work, debt, and a nearly useless filing habit that only compounds if I risk real mistakes. "
            "Hard but fair, lasting injuries, scarce loot."
        ),
        "want": "Grounded transmigration, labor/debt stakes",
    },
    {
        "id": "cozy_mystery",
        "idea": (
            "gentle pastoral mystery around a river village; soft danger, community ties, "
            "easy difficulty, no game system windows, no power fantasy"
        ),
        "want": "Cozy low-stakes, not isekai grind",
    },
    {
        "id": "system_apoc",
        "idea": (
            "system apocalypse: status windows after the sky broke, hard difficulty, "
            "training-heavy skills, no free power spikes, political scavenger factions"
        ),
        "want": "System RPG without OP turbo start",
    },
    {
        "id": "wuxia_face",
        "idea": (
            "wuxia sect politics and face culture; cultivation is slow and costly; "
            "normal difficulty; reputation and debts matter more than levels"
        ),
        "want": "Sect politics, not isekai template",
    },
]

# Fields that show "soul" of the setup for review
SAMPLE_FIELDS = [
    "world_style",
    "tone",
    "custom_style",
    "start_location",
    "character_backstory",
    "custom_skills",
    "quest_style",
    "faction_pressure",
    "difficulty",
    "game_system",
    "system_style",
    "death_rules",
    "loot_rarity",
    "skill_style",
]

TROPE_PATTERNS = [
    (r"\bharem\b", "harem"),
    (r"\bharem\b|\bconcubine|\bwives?\b.*\bharem", "harem-adjacent"),
    (r"\bchosen\s*one\b|\bdestined\b|\bprophec", "chosen-one"),
    (r"\bop\s*mc\b|\boverpowered\s+(mc|hero|protagonist)|starts?\s+strong", "op-mc"),
    (r"\blove\s*interest|\bromance\s+focus|\bfalling\s+in\s+love", "romance-forward"),
    (r"\bgod[- ]?mode\b|\binstant\s+mastery\b|\blevel\s*99\b", "god-mode"),
    (r"\bnoble\s+blood|\breincarnat(?:ed|ion)\s+as\s+(?:a\s+)?(?:prince|princess|duke)", "noble-rebirth"),
]


def score_blob(text: str) -> dict:
    hits = []
    for pat, label in TROPE_PATTERNS:
        if re.search(pat, text or "", re.I):
            hits.append(label)
    # originality heuristics (positive)
    positives = []
    for pat, label in [
        (r"\bdebt\b|\bration|\bharbor|\bdock|\bguild\s+pressure", "local-stakes"),
        (r"\bnear[- ]?useless|weak\s+seed|observation|compound", "weak-seed-growth"),
        (r"\bfair\b|\bagency\b|\bno\s+chosen", "dm-fair"),
        (r"\binjur|\bscarce\b|\bedge\b", "edge"),
    ]:
        if re.search(pat, text or "", re.I):
            positives.append(label)
    return {"trope_hits": sorted(set(hits)), "good_signals": sorted(set(positives))}


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_prompt_probe_"))
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
        "AI_RPG_OLLAMA_TIMEOUT": "300",
        "AI_RPG_SETUP_RANDOMIZER_TIMEOUT": "120",
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
            "response_token_cap": 700,
            "response_token_hard_cap": 1100,
        }
    )

    report: list[dict] = []
    print(f"model={os.environ['OLLAMA_MODEL']} temp={temp}", flush=True)

    for entry in PROMPTS:
        pid, idea, want = entry["id"], entry["idea"], entry["want"]
        print(f"\n======== {pid} ========", flush=True)
        print(f"idea: {idea}", flush=True)
        row: dict = {"id": pid, "idea": idea, "want": want, "fields": {}, "errors": []}
        t0 = time.perf_counter()
        try:
            composed = compose_setup_intent(idea, {})
        except Exception as exc:
            row["errors"].append(f"compose: {exc}")
            composed = {}
        intent = composed.get("intent") if isinstance(composed, dict) else {}
        theme = composed.get("session_theme") if isinstance(composed, dict) else {}
        source = composed.get("source") if isinstance(composed, dict) else "?"
        overrides = intent_to_field_overrides(intent or {})
        row["compose_s"] = round(time.perf_counter() - t0, 1)
        row["source"] = source
        row["intent"] = intent
        row["session_theme"] = theme
        row["field_overrides"] = overrides
        print(f"compose {row['compose_s']}s source={source}", flush=True)
        print(
            "intent:",
            json.dumps(
                {
                    "genre": (intent or {}).get("genre"),
                    "isekai": (intent or {}).get("isekai"),
                    "difficulty": (intent or {}).get("difficulty"),
                    "edge": (intent or {}).get("edge"),
                    "adapter_hint": (intent or {}).get("adapter_hint"),
                    "tone": (intent or {}).get("tone"),
                    "power_fantasy": (intent or {}).get("power_fantasy"),
                    "dm_stance": (intent or {}).get("dm_stance"),
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        print("overrides:", json.dumps(overrides, ensure_ascii=True)[:500], flush=True)

        # Seed setup with overrides, then generate sample fields.
        current = {
            **overrides,
            "_randomize_idea": idea,
            "_compose_intent": intent,
            "_locked_fields": [],
            "_locked_values": {},
        }
        generated: dict = dict(overrides)
        for field in SAMPLE_FIELDS:
            if field in overrides and field not in (
                "character_backstory",
                "custom_style",
                "start_location",
                "world_style",
                "tone",
            ):
                # keep hard overrides; still refresh prose-ish ones below
                if field not in ("world_style", "tone", "custom_style", "character_backstory", "custom_skills", "start_location"):
                    continue
            # Always (re)generate these for flavor samples when not enum locks
            if field in overrides and field in (
                "difficulty",
                "game_system",
                "skill_style",
                "death_rules",
                "loot_rarity",
                "quest_style",
                "faction_pressure",
                "system_style",
            ):
                generated[field] = overrides[field]
                continue
            t1 = time.perf_counter()
            try:
                payload = generate_setup_randomization(
                    f"field:{field}",
                    {**current, **generated},
                )
                fields = payload.get("fields") if isinstance(payload, dict) else payload
                if isinstance(fields, dict) and field in fields:
                    generated[field] = fields[field]
                elif isinstance(payload, dict) and field in payload:
                    generated[field] = payload[field]
                print(f"  field {field}: {time.perf_counter()-t1:.1f}s", flush=True)
            except Exception as exc:
                row["errors"].append(f"{field}: {exc}")
                print(f"  field {field} FAIL {exc}", flush=True)

        cleaned, dirty = sanitize_setup_fields(
            generated,
            idea=idea,
            context={**current, **generated, "_compose_intent": intent},
        )
        row["fields"] = cleaned
        row["dirty"] = dirty
        blob = json.dumps(cleaned, ensure_ascii=True) + " " + json.dumps(intent or {}, ensure_ascii=True)
        row["rubric"] = score_blob(blob)
        print("sample fields:", flush=True)
        for k in (
            "difficulty",
            "game_system",
            "world_style",
            "tone",
            "custom_skills",
            "death_rules",
            "loot_rarity",
            "start_location",
            "quest_style",
            "faction_pressure",
        ):
            if k in cleaned:
                print(f"  {k}: {cleaned[k]!r}"[:200], flush=True)
        if cleaned.get("character_backstory"):
            print(f"  backstory: {str(cleaned['character_backstory'])[:280]}", flush=True)
        if cleaned.get("custom_style"):
            print(f"  custom_style: {str(cleaned['custom_style'])[:220]}", flush=True)
        print("rubric:", row["rubric"], "dirty:", list(dirty.keys()), flush=True)
        report.append(row)

    out = temp / "prompt_probe_report.json"
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    # also copy to repo docs for user
    dest = ROOT / "docs" / "showcase" / "prompt-probe-latest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    print(f"\nreport {out}", flush=True)
    print(f"copy {dest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
