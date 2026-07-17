"""
Timed multi-turn playtest against a local Ollama model.
Writes a JSON report under data/playtest_reports/.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "data" / "playtest_reports"


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_playtest_"))
    db_path = temp / "world.db"
    source_index = temp / "source_index"
    history = temp / "history.jsonl"
    facts = temp / "facts.jsonl"
    slots = temp / "slots"
    traces = temp / "traces"
    source_index.mkdir()
    traces.mkdir()

    os.environ["AI_RPG_DB"] = str(db_path)
    os.environ["AI_RPG_SOURCE_INDEX"] = str(source_index)
    os.environ["AI_RPG_HISTORY_SUMMARY"] = str(history)
    os.environ["AI_RPG_CONSOLIDATED_FACTS"] = str(facts)
    os.environ["AI_RPG_CAMPAIGN_SLOTS"] = str(slots)
    os.environ["AI_RPG_MODEL_TRACE_DIR"] = str(traces)
    os.environ["AI_RPG_MODEL_PROVIDER"] = "ollama"
    os.environ["OLLAMA_BASE_URL"] = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    os.environ["OLLAMA_MODEL"] = os.getenv("PLAYTEST_OLLAMA_MODEL", "qwen3:8b")
    # Local 8B models commonly support larger windows than the 8k default.
    os.environ.setdefault("OLLAMA_CONTEXT_TOKENS", "32768")
    # Qwen3-style models otherwise fill message.thinking and leave content empty.
    os.environ.setdefault("OLLAMA_THINK", "0")
    # Keep timeouts generous for local 8B
    os.environ.setdefault("AI_RPG_OLLAMA_TIMEOUT", "600")
    os.environ.setdefault("AI_RPG_TURN_DRAFT_TIMEOUT", "600")
    os.environ.setdefault("AI_RPG_TURN_VERIFY_TIMEOUT", "480")

    sys.path.insert(0, str(ROOT))
    from app.db import init_db
    from app.llm import get_model_config, test_model_connection, update_model_config
    from app.world import get_state, play_turn, start_playthrough_with_opening

    print("Temp data:", temp)
    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": os.environ["OLLAMA_MODEL"],
            "response_token_cap": 1200,
            "response_token_hard_cap": 1800,
        }
    )
    print("Model config:", json.dumps(get_model_config(), indent=2))
    print("Connection test:", test_model_connection())

    setup = {
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
        "special_ability_locked": False,
        "special_ability_name": "",
        "special_ability_description": "",
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

    report: dict = {
        "model": get_model_config(),
        "temp_dir": str(temp),
        "turns": [],
        "coherence_notes": [],
    }

    t0 = time.perf_counter()
    print("\n=== OPENING / SETUP ===")
    opening = start_playthrough_with_opening(setup)
    opening_s = time.perf_counter() - t0
    opening_meta = {
        "label": "opening",
        "seconds": round(opening_s, 2),
        "used_fallback": bool(opening.get("used_fallback")),
        "fallback_reason": opening.get("fallback_reason") or opening.get("fallback_notice") or "",
        "model_usage": opening.get("model_usage") or opening.get("_model_usage") or [],
        "narration_preview": _preview(opening),
        "location": (opening.get("current_location") or {}).get("name"),
        "token_budget": (opening.get("model_budget") or {}),
    }
    # model usage may be only in logs on state
    state = get_state(include_hidden=True)
    opening_meta["model_logs"] = state.get("model_logs") or []
    opening_meta["model_budget"] = state.get("model_budget") or {}
    report["turns"].append(opening_meta)
    print(f"Opening done in {opening_s:.1f}s fallback={opening_meta['used_fallback']}")
    print("Narration:", opening_meta["narration_preview"][:400])

    actions = [
        "I scan the gate square carefully, note guards and exits, and ask a nearby merchant what trouble has been happening lately.",
        "I thank them, buy a cheap travel ration if available, and walk toward the most suspicious alley while staying alert.",
        "I keep my hand near my satchel, listen at the alley mouth for a moment, then step in only as far as I can still retreat.",
    ]

    for i, action in enumerate(actions, start=1):
        print(f"\n=== TURN {i} ===")
        print("Action:", action)
        t1 = time.perf_counter()
        result = play_turn(action)
        elapsed = time.perf_counter() - t1
        state = get_state(include_hidden=True)
        turn_meta = {
            "label": f"turn_{i}",
            "action": action,
            "seconds": round(elapsed, 2),
            "used_fallback": bool(result.get("used_fallback")),
            "fallback_reason": result.get("fallback_reason") or result.get("fallback_notice") or "",
            "model_usage": result.get("model_usage") or result.get("_model_usage") or [],
            "model_logs": (state.get("model_logs") or [])[:12],
            "model_budget": state.get("model_budget") or {},
            "narration_preview": _preview(result if isinstance(result, dict) else state),
            "location": (state.get("current_location") or {}).get("name"),
            "turn_summaries_tail": [
                {"turn": s.get("turn"), "summary": str(s.get("summary") or "")[:180]}
                for s in (state.get("turn_summaries") or [])[-4:]
            ],
            "relevant_npc_count": sum(len(loc.get("npcs") or []) for loc in (state.get("locations") or [])),
            "event_count": len(state.get("events") or []),
            "inventory_count": len(state.get("inventory") or []),
        }
        report["turns"].append(turn_meta)
        print(f"Turn {i} done in {elapsed:.1f}s fallback={turn_meta['used_fallback']}")
        print("Location:", turn_meta["location"])
        print("Narration:", turn_meta["narration_preview"][:500])
        usage = turn_meta["model_usage"] or turn_meta["model_logs"]
        if usage:
            print("Usage/logs sample:", json.dumps(usage[:6], ensure_ascii=True)[:800])

    report["total_seconds"] = round(time.perf_counter() - t0, 2)
    report["coherence_notes"] = _coherence_check(report)
    report["optimization_ideas"] = _optimization_ideas(report)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = REPORT_DIR / f"playtest-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    print("\n=== REPORT ===", out)
    print("Total seconds:", report["total_seconds"])
    print("Coherence notes:")
    for note in report["coherence_notes"]:
        print(" -", note)
    print("Optimization ideas:")
    for note in report["optimization_ideas"]:
        print(" -", note)

    # Keep temp dir path in report; optional cleanup
    # shutil.rmtree(temp, ignore_errors=True)
    return 0


def _preview(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    turn = payload.get("turn") if isinstance(payload.get("turn"), dict) else None
    if turn:
        text = _preview(turn)
        if text:
            return text
    for key in ("narration", "latest_narration", "response", "opening_narration"):
        if payload.get(key):
            return str(payload.get(key))[:900]
    segs = payload.get("narration_segments")
    if isinstance(segs, list):
        text = "\n".join(str(s.get("text") or "") for s in segs if isinstance(s, dict)).strip()
        if text:
            return text[:900]
    # From full state after turn, history tail
    history = payload.get("history") or []
    for entry in reversed(history):
        if str(entry.get("kind") or "") in {"narration", "opening", "continue", "player", "system"}:
            content = str(entry.get("content") or "")
            if content:
                return content[:900]
    return ""


def _coherence_check(report: dict) -> list[str]:
    notes: list[str] = []
    previews = [t.get("narration_preview") or "" for t in report.get("turns") or []]
    if any(len(p) < 80 for p in previews):
        notes.append("One or more turns produced very short or empty narration previews.")
    if any(t.get("used_fallback") for t in report.get("turns") or []):
        notes.append("At least one turn used deterministic fallback instead of full model output.")
    # simple repetition check across successive previews
    for i in range(1, len(previews)):
        a = set(previews[i - 1].lower().split())
        b = set(previews[i].lower().split())
        if a and b:
            overlap = len(a & b) / max(1, len(a | b))
            if overlap > 0.55:
                notes.append(f"High lexical overlap between turn {i} and {i+1} ({overlap:.0%}) — possible repetition.")
    locations = [t.get("location") for t in report.get("turns") or [] if t.get("location")]
    if locations and len(set(locations)) == 1:
        notes.append(f"All observed turns remained at location '{locations[0]}' (fine if player did not leave).")
    if not notes:
        notes.append("No major automated coherence red flags; manual reading of previews recommended.")
    return notes


def _optimization_ideas(report: dict) -> list[str]:
    ideas: list[str] = []
    times = [float(t.get("seconds") or 0) for t in report.get("turns") or []]
    if times:
        ideas.append(f"Observed wall times (s): {', '.join(f'{x:.1f}' for x in times)}; mean {sum(times)/len(times):.1f}s.")
    # Inspect token estimates
    est = []
    phases = {}
    for t in report.get("turns") or []:
        for entry in (t.get("model_usage") or []) + (t.get("model_logs") or []):
            if not isinstance(entry, dict):
                continue
            tok = entry.get("estimated_tokens")
            phase = str(entry.get("phase") or "unknown")
            if tok is not None:
                try:
                    tok_i = int(tok)
                except (TypeError, ValueError):
                    continue
                est.append(tok_i)
                phases.setdefault(phase, []).append(tok_i)
    if est:
        ideas.append(f"Estimated prompt tokens across logged phases: min {min(est)}, max {max(est)}, mean {sum(est)//len(est)}.")
        for phase, vals in sorted(phases.items()):
            ideas.append(f"  phase '{phase}': n={len(vals)} mean_tokens={sum(vals)//len(vals)} max={max(vals)}")
    ideas.append("Likely safe cuts if turns are slow: skip or narrow verifier on high-certainty low-risk turns (already partially implemented); reduce draft max tokens for 'balanced' narration; shrink handoff context optional roots.")
    ideas.append("Avoid cutting: entity codes, current location NPCs/events, mechanics_context for combat, and recent turn_summaries.")
    ideas.append("If draft+verify both run every turn on 8B, expect multi-minute turns; measure whether verify_skipped_certainty ever triggers.")
    return ideas


if __name__ == "__main__":
    raise SystemExit(main())
