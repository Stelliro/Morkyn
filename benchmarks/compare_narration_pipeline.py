"""
Compare baseline generate_turn vs AI_RPG_NARRATION_PIPELINE=1 on opening + N turns.

Writes under benchmarks/reports/.
Requires local Ollama.

  python benchmarks/compare_narration_pipeline.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
ROOT = BENCH.parent
REPORT_DIR = BENCH / "reports"


def _setup() -> dict:
    return {
        "player_name": "Ashen Courier",
        "player_public_name": "the Ashbound",
        "player_title": "Courier",
        "player_age": "27",
        "player_sex": "unspecified",
        "previous_life_age": "",
        "previous_life_sex": "",
        "backstory_mode": "known",
        "character_backstory": "A road courier carrying a sealed letter and old debts.",
        "memory_policy": "known",
        "difficulty": "normal",
        "narration_detail": "balanced",
        "world_style": "frontier dark fantasy",
        "custom_style": "",
        "start_location": "Mosswake Gate",
        "leveling_system": True,
        "game_system": False,
        "system_style": "subtle blue-window system",
        "special_ability_origin": "none",
        "special_ability": False,
        "special_abilities": [],
        "skill_style": "standard",
        "skill_levels_enabled": True,
        "new_skill_frequency": "normal",
        "proficiency_system": True,
        "proficiency_access": "learned",
        "skill_growth_speed": "normal",
        "proficiency_growth_speed": "normal",
        "xp_growth_speed": "normal",
        "custom_skills": "",
    }


def _preview(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    turn = payload.get("turn") if isinstance(payload.get("turn"), dict) else payload
    for key in ("narration", "latest_narration", "opening_narration"):
        if turn.get(key):
            return str(turn.get(key))[:1200]
    segs = turn.get("narration_segments")
    if isinstance(segs, list):
        text = "\n\n".join(str(s.get("text") or "") for s in segs if isinstance(s, dict)).strip()
        if text:
            return text[:1200]
    return ""


def _narr_len(payload: dict) -> int:
    return len(_preview(payload))


def _run_mode(label: str, pipeline_on: bool, turns: int) -> dict:
    temp = Path(tempfile.mkdtemp(prefix=f"morkyn_cmp_{label}_"))
    # Isolate env for this mode
    env_keys = {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "OLLAMA_MODEL": os.getenv("GROK_BENCH_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:8b")),
        "OLLAMA_CONTEXT_TOKENS": os.getenv("OLLAMA_CONTEXT_TOKENS", "32768"),
        "OLLAMA_THINK": os.getenv("OLLAMA_THINK", "0"),
        "AI_RPG_OLLAMA_TIMEOUT": os.getenv("AI_RPG_OLLAMA_TIMEOUT", "600"),
        "AI_RPG_TURN_DRAFT_TIMEOUT": os.getenv("AI_RPG_TURN_DRAFT_TIMEOUT", "600"),
        "AI_RPG_TURN_VERIFY_TIMEOUT": os.getenv("AI_RPG_TURN_VERIFY_TIMEOUT", "480"),
        "AI_RPG_NARRATION_PIPELINE": "1" if pipeline_on else "0",
        "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1" if pipeline_on else "0",
        "AI_RPG_DSL_SKIP_VERIFY": os.getenv("AI_RPG_DSL_SKIP_VERIFY", "0"),
    }
    for key, val in env_keys.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(exist_ok=True)
    (temp / "traces").mkdir(exist_ok=True)
    (temp / "slots").mkdir(exist_ok=True)

    # Re-import modules so env and config bind cleanly is hard mid-process;
    # world/llm read env at call time for most paths. Re-init db paths via env before import use.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    # Fresh imports of app modules that cache little; force llm config update.
    from app import llm as llm_mod
    from app.db import init_db
    from app.llm import get_model_config, test_model_connection, update_model_config
    from app.world import get_state, play_turn, start_playthrough_with_opening

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": os.environ["OLLAMA_MODEL"],
            "response_token_cap": int(os.getenv("AI_RPG_MAX_RESPONSE_TOKENS", "1000")),
            "response_token_hard_cap": int(os.getenv("AI_RPG_RESPONSE_HARD_CAP_TOKENS", "1500")),
        }
    )
    conn = test_model_connection()
    print(f"\n=== MODE {label} pipeline={pipeline_on} pipeline_enabled()={llm_mod.pipeline_enabled()} ===", flush=True)
    print(f"connection ok={conn.get('ok')} model={get_model_config().get('ollama_model')}", flush=True)
    if not conn.get("ok"):
        return {"label": label, "error": "model connection failed", "connection": conn, "temp": str(temp)}

    actions = [
        "I survey Mosswake Gate carefully, note exits and watchers, and ask a nearby merchant what trouble has been happening.",
        "I thank them, secure the sealed letter in my satchel, and walk toward the most suspicious alley while staying alert.",
    ][: max(0, turns)]

    steps: list[dict] = []
    t_run = time.perf_counter()

    print("OPENING...", flush=True)
    t0 = time.perf_counter()
    opening = start_playthrough_with_opening(_setup())
    elapsed = time.perf_counter() - t0
    state = get_state(include_hidden=True)
    narr = _preview(opening if isinstance(opening, dict) else {})
    step = {
        "label": "opening",
        "seconds": round(elapsed, 2),
        "used_fallback": bool(opening.get("used_fallback")) if isinstance(opening, dict) else False,
        "fallback_reason": (opening.get("fallback_reason") or "") if isinstance(opening, dict) else "",
        "narration_chars": len(narr),
        "narration_preview": narr[:500],
        "pipeline_meta": (opening.get("turn") or opening).get("_narration_pipeline")
        if isinstance(opening, dict)
        else None,
        "model_usage_phases": [
            u.get("phase")
            for u in ((opening.get("turn") or {}).get("_model_usage") or opening.get("_model_usage") or [])
            if isinstance(u, dict)
        ][:20],
    }
    # usage may live on turn
    turn_obj = opening.get("turn") if isinstance(opening, dict) else None
    if isinstance(turn_obj, dict):
        step["pipeline_meta"] = turn_obj.get("_narration_pipeline") or step.get("pipeline_meta")
        step["model_usage_phases"] = [u.get("phase") for u in (turn_obj.get("_model_usage") or []) if isinstance(u, dict)][:24]
        step["narration_chars"] = len(str(turn_obj.get("narration") or narr))
        segs = turn_obj.get("narration_segments") or []
        step["segment_count"] = len(segs) if isinstance(segs, list) else 0
    steps.append(step)
    print(
        f"  opening {elapsed:.1f}s fallback={step['used_fallback']} chars={step['narration_chars']} "
        f"segs={step.get('segment_count')} pipeline={bool(step.get('pipeline_meta'))}",
        flush=True,
    )
    print("  preview:", narr[:220].replace("\n", " "), flush=True)

    for i, action in enumerate(actions, start=1):
        print(f"TURN {i}: {action[:80]}...", flush=True)
        t1 = time.perf_counter()
        result = play_turn(action)
        elapsed = time.perf_counter() - t1
        narr = _preview(result if isinstance(result, dict) else {})
        turn_obj = result.get("turn") if isinstance(result, dict) else {}
        if not isinstance(turn_obj, dict):
            turn_obj = {}
        step = {
            "label": f"turn_{i}",
            "action": action,
            "seconds": round(elapsed, 2),
            "used_fallback": bool(result.get("used_fallback")) if isinstance(result, dict) else False,
            "fallback_reason": (result.get("fallback_reason") or "") if isinstance(result, dict) else "",
            "narration_chars": len(str(turn_obj.get("narration") or narr)),
            "segment_count": len(turn_obj.get("narration_segments") or [])
            if isinstance(turn_obj.get("narration_segments"), list)
            else 0,
            "narration_preview": narr[:500],
            "pipeline_meta": turn_obj.get("_narration_pipeline"),
            "model_usage_phases": [u.get("phase") for u in (turn_obj.get("_model_usage") or []) if isinstance(u, dict)][:30],
            "location": ((get_state(include_hidden=True).get("current_location") or {}).get("name")),
        }
        steps.append(step)
        print(
            f"  turn {i} {elapsed:.1f}s fallback={step['used_fallback']} chars={step['narration_chars']} "
            f"segs={step['segment_count']} pipeline={bool(step.get('pipeline_meta'))}",
            flush=True,
        )
        print("  preview:", narr[:220].replace("\n", " "), flush=True)

    return {
        "label": label,
        "pipeline_on": pipeline_on,
        "temp": str(temp),
        "model": get_model_config(),
        "total_seconds": round(time.perf_counter() - t_run, 2),
        "steps": steps,
        "fallback_count": sum(1 for s in steps if s.get("used_fallback")),
        "mean_chars": round(sum(s.get("narration_chars") or 0 for s in steps) / max(1, len(steps)), 1),
        "mean_seconds": round(sum(s.get("seconds") or 0 for s in steps) / max(1, len(steps)), 2),
    }


def main() -> int:
    turns = max(0, int(os.getenv("GROK_BENCH_COMPARE_TURNS", "2")))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = REPORT_DIR / f"compare-pipeline-{stamp}.json"

    print("benchmarks narration pipeline comparison", flush=True)
    print(f"turns_after_opening={turns} model={os.getenv('GROK_BENCH_MODEL', os.getenv('OLLAMA_MODEL', 'qwen3:8b'))}", flush=True)

    baseline = _run_mode("baseline", pipeline_on=False, turns=turns)
    pipeline = _run_mode("pipeline", pipeline_on=True, turns=turns)

    report = {
        "benchmark": "narration pipeline comparison",
        "started_stamp": stamp,
        "turns_after_opening": turns,
        "baseline": baseline,
        "pipeline": pipeline,
        "delta": {
            "total_seconds": round((pipeline.get("total_seconds") or 0) - (baseline.get("total_seconds") or 0), 2),
            "mean_chars": round((pipeline.get("mean_chars") or 0) - (baseline.get("mean_chars") or 0), 1),
            "mean_seconds": round((pipeline.get("mean_seconds") or 0) - (baseline.get("mean_seconds") or 0), 2),
            "fallback_count": (pipeline.get("fallback_count") or 0) - (baseline.get("fallback_count") or 0),
        },
    }
    out_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    print("\n=== SUMMARY ===", flush=True)
    print(json.dumps({"baseline": {k: baseline.get(k) for k in ("total_seconds", "mean_chars", "mean_seconds", "fallback_count")},
                      "pipeline": {k: pipeline.get(k) for k in ("total_seconds", "mean_chars", "mean_seconds", "fallback_count")},
                      "delta": report["delta"]}, indent=2), flush=True)
    print("report:", out_path, flush=True)
    return 0 if not baseline.get("error") and not pipeline.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
