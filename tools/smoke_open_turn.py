"""Minimal smoke: opening + one turn against local Ollama."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_smoke4_"))
    print("temp", temp, flush=True)
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
        "OLLAMA_CONTEXT_TOKENS": os.getenv("OLLAMA_CONTEXT_TOKENS", "32768"),
        "OLLAMA_THINK": os.getenv("OLLAMA_THINK", "0"),
        "AI_RPG_OLLAMA_TIMEOUT": os.getenv("AI_RPG_OLLAMA_TIMEOUT", "300"),
        "AI_RPG_TURN_DRAFT_TIMEOUT": os.getenv("AI_RPG_TURN_DRAFT_TIMEOUT", "300"),
        "AI_RPG_TURN_VERIFY_TIMEOUT": os.getenv("AI_RPG_TURN_VERIFY_TIMEOUT", "240"),
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir()
    (temp / "traces").mkdir()
    sys.path.insert(0, str(ROOT))

    from app.db import init_db
    from app.llm import update_model_config
    from app.world import get_state, play_turn, start_playthrough_with_opening

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": os.environ["OLLAMA_MODEL"],
            "response_token_cap": 800,
            "response_token_hard_cap": 1200,
        }
    )

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

    def narration_from(payload: dict, state: dict) -> str:
        narr = payload.get("narration") or payload.get("latest_narration") or payload.get("opening_narration") or ""
        if not narr and isinstance(payload.get("turn"), dict):
            narr = payload["turn"].get("narration") or ""
        if not narr:
            for entry in reversed(state.get("history") or []):
                if entry.get("content"):
                    return str(entry.get("content"))
        return str(narr or "")

    print("SMOKE4 opening...", flush=True)
    t0 = time.perf_counter()
    opening = start_playthrough_with_opening(setup)
    t_open = time.perf_counter() - t0
    state = get_state(include_hidden=True)
    open_narr = narration_from(opening if isinstance(opening, dict) else {}, state)
    print(
        f"opening {t_open:.1f}s fallback={bool(opening.get('used_fallback'))} "
        f"narr_len={len(open_narr)}",
        flush=True,
    )
    print("opening preview:", open_narr[:280], flush=True)

    print("SMOKE4 turn1...", flush=True)
    t1 = time.perf_counter()
    result = play_turn(
        "I look around the gate square and ask a nearby merchant what trouble has been happening lately."
    )
    t_turn = time.perf_counter() - t1
    state = get_state(include_hidden=True)
    narr = narration_from(result if isinstance(result, dict) else {}, state)
    phases = [e.get("phase") for e in (state.get("model_logs") or [])]
    print(
        f"turn1 {t_turn:.1f}s fallback={bool(result.get('used_fallback'))} "
        f"reason={(result.get('fallback_reason') or '')[:120]}",
        flush=True,
    )
    print("turn preview:", narr[:400], flush=True)
    print("location", (state.get("current_location") or {}).get("name"), flush=True)
    print("phases", phases, flush=True)
    print("total", round(t_open + t_turn, 1), "s", flush=True)

    report = {
        "opening_s": round(t_open, 2),
        "turn1_s": round(t_turn, 2),
        "total_s": round(t_open + t_turn, 2),
        "opening_fallback": bool(opening.get("used_fallback")),
        "turn_fallback": bool(result.get("used_fallback")),
        "turn_reason": result.get("fallback_reason") or "",
        "opening_narration": open_narr[:900],
        "turn_narration": narr[:900],
        "location": (state.get("current_location") or {}).get("name"),
        "phases": phases,
        "budget": state.get("model_budget"),
        "model_logs": (state.get("model_logs") or [])[:16],
    }
    out = ROOT / "data" / "playtest_reports" / "smoke4-open-turn.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    print("wrote", out, flush=True)
    return 0 if not report["opening_fallback"] and not report["turn_fallback"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
