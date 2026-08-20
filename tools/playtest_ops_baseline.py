"""
Minimal opening + N turns against local Ollama, writing traces only.

Deliberately uses no band/pack APIs so it runs against both the current tree
and the pre-band baseline, letting `check_trace_ops_survival.py` compare how
many drafted amount ops survive into the applied turn in each.

    python tools/playtest_ops_baseline.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ACTIONS = [
    "I look around the gate square and ask a nearby merchant what trouble has been happening lately.",
    "I offer to help the merchant carry crates in exchange for news about the road east.",
    "I check my pack, then head for the east road out of town.",
    "I keep walking east, watching the treeline for movement.",
]


def main() -> int:
    model = os.getenv("PLAYTEST_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    turns = int(os.getenv("PLAYTEST_TURNS", "4"))
    temp = Path(tempfile.mkdtemp(prefix="morkyn_opsbase_"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        "AI_RPG_SKILL_LIBRARY": str(temp / "skill_library.json"),
        "AI_RPG_PACK_DIR": str(temp / "packs"),
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "OLLAMA_MODEL": model,
        "OLLAMA_CONTEXT_TOKENS": "32768",
        "OLLAMA_THINK": "0",
        "AI_RPG_OLLAMA_TIMEOUT": "600",
        "AI_RPG_TURN_DRAFT_TIMEOUT": "600",
        "AI_RPG_TURN_VERIFY_TIMEOUT": "480",
        "AI_RPG_MODEL_TRACE_KEEP": "80",
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    (temp / "traces").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.db import init_db
    from app.llm import update_model_config
    from app.world import play_turn, start_playthrough_with_opening

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": model,
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
        "backstory_mode": "known",
        "character_backstory": "A road courier carrying a sealed letter and old debts.",
        "memory_policy": "known",
        "difficulty": "normal",
        "narration_detail": "balanced",
        "world_style": "frontier dark fantasy",
        "start_location": "Mosswake Gate",
        "leveling_system": True,
        "game_system": False,
        "skill_style": "standard",
        "skill_levels_enabled": True,
        "new_skill_frequency": "normal",
        "proficiency_system": True,
        "proficiency_access": "learned",
        "skill_growth_speed": "normal",
        "xp_growth_speed": "normal",
        "special_abilities": [],
        "custom_skills": "",
        "dice_checks_enabled": True,
    }

    print(f"model {model}\ntraces {temp / 'traces'}", flush=True)
    t0 = time.perf_counter()
    opening = start_playthrough_with_opening(setup)
    print(f"opening {time.perf_counter() - t0:.1f}s fallback={bool(opening.get('used_fallback'))}", flush=True)

    for i in range(turns):
        t = time.perf_counter()
        result = play_turn(ACTIONS[i % len(ACTIONS)])
        print(
            f"turn{i + 1} {time.perf_counter() - t:.1f}s fallback={bool(result.get('used_fallback'))}",
            flush=True,
        )
    print(f"TRACE_DIR={temp / 'traces'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
