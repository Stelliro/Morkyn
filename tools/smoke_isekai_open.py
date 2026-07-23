"""Isekai feel smoke: Start with system+weak seed → opening → up to 3 turns.

Uses local Ollama when available. Without Ollama, still verifies setup seeding
(weak skill, dice defaults) and exit 0 after offline checks.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ollama_up(base: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def narration_from(payload: dict, state: dict) -> str:
    narr = payload.get("narration") or payload.get("latest_narration") or payload.get("opening_narration") or ""
    if not narr and isinstance(payload.get("turn"), dict):
        narr = payload["turn"].get("narration") or ""
    if not narr:
        for entry in reversed(state.get("history") or []):
            if entry.get("content"):
                return str(entry.get("content"))
    return str(narr or "")


def main() -> int:
    temp = Path(tempfile.mkdtemp(prefix="morkyn_isekai_smoke_"))
    print("temp", temp, flush=True)
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    model = os.getenv("PLAYTEST_OLLAMA_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": ollama_base,
        "OLLAMA_MODEL": model,
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
    from app.setup_composer import apply_keyword_intent, intent_to_field_overrides, session_theme_from_intent
    from app.world import get_state, play_turn, start_playthrough_with_opening

    idea = (
        "Isekai dark fantasy RPG: ordinary human starts near-useless with one weak skill that compounds; "
        "subtle system UI; fair DM, no chosen-one autopilot; local stakes first."
    )
    intent = apply_keyword_intent(idea)
    overrides = intent_to_field_overrides(intent)
    theme = session_theme_from_intent(intent)

    setup = {
        "player_name": "Ren",
        "player_public_name": "",
        "player_title": "",
        "player_age": "24",
        "player_sex": "male",
        "previous_life_age": "31",
        "previous_life_sex": "male",
        "backstory_mode": overrides.get("backstory_mode") or "transmigrated",
        "character_backstory": (
            "Died on a rain-slick crosswalk after a night shift; woke in a new body near a harbor gate "
            "with most former-life memories intact and no local proof of identity."
        ),
        "memory_policy": overrides.get("memory_policy") or "remembers former life",
        "difficulty": overrides.get("difficulty") or "normal",
        "narration_detail": "balanced",
        "world_style": overrides.get("world_style") or "isekai dark fantasy",
        "custom_style": "Isekai RPG lean; fair DM; no auto-win.",
        "start_location": "Mosswake Gate",
        "leveling_system": True,
        "game_system": True,
        "system_style": overrides.get("system_style") or "subtle blue-window system",
        "special_ability_origin": "acquired",
        "special_abilities": [],
        "skill_style": overrides.get("skill_style") or "training-heavy",
        "skill_levels_enabled": True,
        "new_skill_frequency": overrides.get("new_skill_frequency") or "frequent",
        "proficiency_system": True,
        "proficiency_access": "learned",
        "skill_growth_speed": overrides.get("skill_growth_speed") or "very fast",
        "proficiency_growth_speed": "fast",
        "xp_growth_speed": "fast",
        "custom_skills": overrides.get("custom_skills")
        or "weak seed skill: Observation (near-useless). Compounds through practice.",
        "dice_checks_enabled": overrides.get("dice_checks_enabled", True),
        "check_difficulty": overrides.get("check_difficulty") or "normal",
        "event_check_frequency": overrides.get("event_check_frequency") or "normal",
        "encounter_check_frequency": overrides.get("encounter_check_frequency") or "normal",
        "unskilled_mishaps": True,
        "auto_check_on_risky_actions": True,
        "show_rolls_in_ui": True,
        "world_races": "human",
        "quest_style": "job board and personal mysteries",
        "economy": "scarce coin markets",
        "session_theme": theme,
    }

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": ollama_base,
            "ollama_model": model,
            "response_token_cap": 900,
            "response_token_hard_cap": 1400,
        }
    )

    notes: list[str] = []
    print("ISEKAI setup seed check...", flush=True)
    # Start always runs opening; if Ollama down, may fallback.
    t0 = time.perf_counter()
    opening = start_playthrough_with_opening(setup)
    t_open = time.perf_counter() - t0
    state = get_state(include_hidden=True)
    opts = (state.get("settings") or {}).get("playthrough_options") or {}
    skills = state.get("skills") or state.get("player_skills") or []
    skill_names = [str(s.get("name") or "").lower() for s in skills if isinstance(s, dict)]
    open_narr = narration_from(opening if isinstance(opening, dict) else {}, state)

    seed_ok = any("observation" in n for n in skill_names) or bool(opts.get("weak_skill_seed"))
    dice_ok = bool(opts.get("dice_checks_enabled") or (opts.get("skill_check_settings") or {}).get("dice_checks_enabled"))
    print(
        f"opening {t_open:.1f}s fallback={bool(opening.get('used_fallback'))} "
        f"narr_len={len(open_narr)} seed_ok={seed_ok} dice_ok={dice_ok}",
        flush=True,
    )
    print("opening preview:", open_narr[:320], flush=True)
    if not seed_ok:
        notes.append("FAIL: weak skill seed missing after start")
    if not dice_ok:
        notes.append("FAIL: dice_checks_enabled not set for isekai/system start")
    if opts.get("game_system") and open_narr and "STATUS" not in open_narr and "skill" not in open_narr.lower():
        # Soft note — model may phrase differently
        notes.append("NOTE: opening narration may lack diegetic system window wording")

    live = ollama_up(ollama_base)
    turns = [
        "I stay still and carefully look around the gate, trying to use that faint Observation sense.",
        "I ask a nearby worker what this place is called and how a stranger finds cheap shelter.",
        "I check whether any notice board or job posting is safe to approach without looking rich.",
    ]
    if not live:
        notes.append("SKIP: Ollama not reachable — only offline seed checks ran")
        print("\n".join(notes), flush=True)
        report = {"ok": seed_ok and dice_ok, "notes": notes, "opening_len": len(open_narr), "live": False}
        (temp / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("report", temp / "report.json", flush=True)
        return 0 if seed_ok and dice_ok else 1

    for i, action in enumerate(turns, 1):
        print(f"ISEKAI turn{i}...", flush=True)
        t1 = time.perf_counter()
        try:
            result = play_turn(action)
        except Exception as exc:
            notes.append(f"FAIL turn{i}: {exc}")
            print("error", exc, flush=True)
            break
        dt = time.perf_counter() - t1
        state = get_state(include_hidden=True)
        narr = narration_from(result if isinstance(result, dict) else {}, state)
        print(
            f"turn{i} {dt:.1f}s fallback={bool(result.get('used_fallback'))} narr_len={len(narr)}",
            flush=True,
        )
        print("preview:", narr[:220], flush=True)
        if len(narr) < 200:
            notes.append(f"NOTE turn{i}: short narration ({len(narr)} chars)")

    report = {
        "ok": seed_ok and dice_ok and not any(n.startswith("FAIL") for n in notes),
        "notes": notes,
        "opening_len": len(open_narr),
        "live": True,
        "model": model,
    }
    (temp / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("notes:", notes or ["none"], flush=True)
    print("report", temp / "report.json", flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
