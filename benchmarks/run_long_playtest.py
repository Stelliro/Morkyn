"""
benchmarks — long backend playthrough against local Ollama.

Isolated temp world data. Writes live logs + final report under
benchmarks/reports/ only.

Run from repo root:
  python benchmarks/run_long_playtest.py

Env:
  GROK_BENCH_TURNS          default 100
  GROK_BENCH_MODEL          default qwen3:8b (or PLAYTEST_OLLAMA_MODEL / OLLAMA_MODEL)
  GROK_BENCH_ABORT_FAILS    consecutive hard failures before abort (default 5)
  OLLAMA_BASE_URL           default http://127.0.0.1:11434
  OLLAMA_THINK              default 0
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

BENCH_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BENCH_ROOT.parent
REPORT_DIR = BENCH_ROOT / "reports"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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
    history = payload.get("history") or []
    for entry in reversed(history):
        if str(entry.get("kind") or "") in {"narration", "opening", "continue", "player", "system"}:
            content = str(entry.get("content") or "")
            if content:
                return content[:900]
    return ""


def _location_name(state: dict) -> str:
    loc = state.get("current_location") if isinstance(state, dict) else None
    if isinstance(loc, dict):
        return str(loc.get("name") or loc.get("code") or "")
    return ""


def _player_snapshot(state: dict) -> dict:
    player = state.get("player") if isinstance(state.get("player"), dict) else {}
    return {
        "name": player.get("name"),
        "health": player.get("health"),
        "max_health": player.get("max_health"),
        "level": player.get("level"),
        "xp": player.get("xp"),
        "gold": player.get("gold"),
        "location": _location_name(state),
    }


def _choose_action(turn_index: int, state: dict) -> str:
    """Rotate through a long, varied action script. Prefer state-aware lines when possible."""
    location = _location_name(state) or "here"
    inventory = state.get("inventory") or []
    npcs = []
    for loc in state.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        if str(loc.get("name") or "") == location or loc.get("id") == (state.get("current_location") or {}).get("id"):
            npcs = loc.get("npcs") or []
            break
    npc_name = ""
    if npcs and isinstance(npcs[0], dict):
        npc_name = str(npcs[0].get("name") or npcs[0].get("code") or "").strip()
    item_name = ""
    if inventory and isinstance(inventory[0], dict):
        item_name = str(inventory[0].get("name") or inventory[0].get("code") or "").strip()

    script = [
        f"I carefully survey {location}, noting exits, cover, and anyone watching me.",
        f"I ask {npc_name or 'someone nearby'} what trouble has been happening here lately.",
        "I check my satchel, count what I am carrying, and secure anything valuable.",
        f"I buy a cheap travel ration or water if available in {location}, otherwise I keep moving.",
        "I listen for rumors about bandits, debt collectors, or sealed letters.",
        f"I walk a short way toward the most suspicious path from {location}, staying alert.",
        "I keep my hand near my satchel, pause, and only advance as far as I can still retreat.",
        "I try to learn one useful name, place, or debt connected to my courier work.",
        "I rest for a few minutes in a safer corner and watch the crowd without drawing attention.",
        "I look for work a courier could take: messages, package runs, or quiet deliveries.",
        f"I examine any posted notices or marks near {location} and commit one detail to memory.",
        "I test a simple social approach: polite, brief, and ready to leave if it turns hostile.",
        "I search the ground and edges of the path for tracks, blood, or dropped gear.",
        "I circle back toward open ground if I feel boxed in, prioritizing exits over curiosity.",
        f"I use {item_name or 'what little gear I have'} carefully if it helps me stay fed or unnoticed.",
        "I ask about safe lodging for one night and what it costs in coin or favor.",
        "I follow a lead only one step further, then stop to reassess before committing.",
        "I try to avoid a fight: distance, cover, and a clear route out matter more than pride.",
        "I take a moment to restate my goal: deliver the sealed letter and survive the debts around it.",
        "I move to a new nearby location if the scene has gone cold, or dig one layer deeper if it has not.",
    ]
    return script[(turn_index - 1) % len(script)]


def _setup_payload() -> dict:
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
        "custom_style": "Long-run benchmark: keep locations, NPCs, and inventory consistent; prefer grounded frontier pressure over soft resets.",
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
        "tone": "tense frontier",
        "economy": "scarce coin and favors",
        "magic_level": "low and dangerous",
        "tech_level": "late medieval with rare relics",
        "npc_density": "moderate",
        "quest_style": "rumors and personal debts",
        "faction_pressure": "merchant houses and road wardens",
        "death_rules": "severe injury and debt before instant death",
        "loot_rarity": "mundane common, enchanted rare",
        "inventory_weight_limit": 30,
        "inventory_slot_limit": 12,
        "inventory_rules": "",
    }


def _log(fp, message: str) -> None:
    line = message if message.endswith("\n") else message + "\n"
    fp.write(line)
    fp.flush()
    print(message, flush=True)


def main() -> int:
    target_turns = max(1, _env_int("GROK_BENCH_TURNS", 100))
    abort_fails = max(1, _env_int("GROK_BENCH_ABORT_FAILS", 5))
    model = (
        os.getenv("GROK_BENCH_MODEL")
        or os.getenv("PLAYTEST_OLLAMA_MODEL")
        or os.getenv("OLLAMA_MODEL")
        or "qwen3:8b"
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    live_log = REPORT_DIR / f"live-{stamp}.log"
    jsonl_path = REPORT_DIR / f"turns-{stamp}.jsonl"
    report_path = REPORT_DIR / f"report-{stamp}.json"

    temp = Path(tempfile.mkdtemp(prefix="morkyn_grok_bench_"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "OLLAMA_MODEL": model,
        "OLLAMA_CONTEXT_TOKENS": os.getenv("OLLAMA_CONTEXT_TOKENS", "32768"),
        "OLLAMA_THINK": os.getenv("OLLAMA_THINK", "0"),
        "AI_RPG_OLLAMA_TIMEOUT": os.getenv("AI_RPG_OLLAMA_TIMEOUT", "600"),
        "AI_RPG_TURN_DRAFT_TIMEOUT": os.getenv("AI_RPG_TURN_DRAFT_TIMEOUT", "600"),
        "AI_RPG_TURN_VERIFY_TIMEOUT": os.getenv("AI_RPG_TURN_VERIFY_TIMEOUT", "480"),
        "AI_RPG_FAST_VERIFICATION": os.getenv("AI_RPG_FAST_VERIFICATION", "1"),
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(exist_ok=True)
    (temp / "traces").mkdir(exist_ok=True)
    (temp / "slots").mkdir(exist_ok=True)

    sys.path.insert(0, str(REPO_ROOT))

    report: dict = {
        "benchmark": "benchmarks",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "target_turns": target_turns,
        "temp_dir": str(temp),
        "paths": {
            "live_log": str(live_log),
            "jsonl": str(jsonl_path),
            "report": str(report_path),
        },
        "model": {},
        "opening": None,
        "turns": [],
        "summary": {},
    }

    consecutive_fails = 0
    fallback_count = 0
    error_count = 0
    short_narration_count = 0
    t_run = time.perf_counter()

    with live_log.open("w", encoding="utf-8") as log, jsonl_path.open("w", encoding="utf-8") as jsonl:
        _log(log, f"benchmarks long playtest")
        _log(log, f"target_turns={target_turns} model={model}")
        _log(log, f"temp={temp}")
        _log(log, f"reports={REPORT_DIR}")

        from app.db import init_db
        from app.llm import get_model_config, test_model_connection, update_model_config
        from app.world import get_state, play_turn, start_playthrough_with_opening

        init_db()
        update_model_config(
            {
                "provider": "ollama",
                "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
                "ollama_model": model,
                "response_token_cap": 1000,
                "response_token_hard_cap": 1500,
            }
        )
        report["model"] = get_model_config()
        conn = test_model_connection()
        _log(log, f"connection={json.dumps(conn, ensure_ascii=True)[:500]}")
        if not conn.get("ok"):
            _log(log, "ABORT: model connection failed")
            report["summary"] = {"aborted": True, "reason": "model connection failed", "connection": conn}
            report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
            return 2

        # --- Opening ---
        _log(log, "\n=== OPENING ===")
        t0 = time.perf_counter()
        try:
            opening = start_playthrough_with_opening(_setup_payload())
            opening_err = None
        except Exception as exc:
            opening = {}
            opening_err = f"{type(exc).__name__}: {exc}"
            _log(log, opening_err)
            _log(log, traceback.format_exc())
        elapsed = time.perf_counter() - t0
        state = get_state(include_hidden=True) if not opening_err else {}
        opening_row = {
            "label": "opening",
            "seconds": round(elapsed, 2),
            "error": opening_err,
            "used_fallback": bool(opening.get("used_fallback")) if isinstance(opening, dict) else False,
            "fallback_reason": (opening.get("fallback_reason") or opening.get("fallback_notice") or "") if isinstance(opening, dict) else "",
            "narration_preview": _preview(opening if isinstance(opening, dict) else {}) or _preview(state),
            "player": _player_snapshot(state) if state else {},
            "location": _location_name(state),
            "inventory_count": len(state.get("inventory") or []) if state else 0,
            "event_count": len(state.get("events") or []) if state else 0,
            "npc_count": sum(len(loc.get("npcs") or []) for loc in (state.get("locations") or []) if isinstance(loc, dict)) if state else 0,
        }
        report["opening"] = opening_row
        jsonl.write(json.dumps(opening_row, ensure_ascii=True, default=str) + "\n")
        jsonl.flush()
        if opening_row["used_fallback"]:
            fallback_count += 1
        if opening_err:
            error_count += 1
            consecutive_fails += 1
        elif len(opening_row["narration_preview"]) < 80:
            short_narration_count += 1
            consecutive_fails += 1
        else:
            consecutive_fails = 0
        _log(
            log,
            f"opening {elapsed:.1f}s fallback={opening_row['used_fallback']} "
            f"loc={opening_row['location']!r} narr_len={len(opening_row['narration_preview'])}",
        )
        if opening_row["narration_preview"]:
            _log(log, "preview: " + opening_row["narration_preview"][:320])
        if opening_err and consecutive_fails >= abort_fails:
            report["summary"] = {"aborted": True, "reason": "opening failed", "error": opening_err}
            report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
            return 3

        # --- Player turns ---
        for i in range(1, target_turns + 1):
            state = get_state(include_hidden=True)
            action = _choose_action(i, state)
            _log(log, f"\n=== TURN {i}/{target_turns} ===")
            _log(log, f"action: {action}")
            t1 = time.perf_counter()
            err = None
            result: dict = {}
            try:
                result = play_turn(action)
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                _log(log, err)
                _log(log, traceback.format_exc())
            elapsed = time.perf_counter() - t1
            state = get_state(include_hidden=True)
            narr = _preview(result if isinstance(result, dict) else {}) or _preview(state)
            row = {
                "label": f"turn_{i}",
                "turn_index": i,
                "action": action,
                "seconds": round(elapsed, 2),
                "error": err,
                "used_fallback": bool(result.get("used_fallback")) if isinstance(result, dict) else False,
                "fallback_reason": (result.get("fallback_reason") or result.get("fallback_notice") or "") if isinstance(result, dict) else "",
                "narration_preview": narr,
                "narration_len": len(narr),
                "player": _player_snapshot(state),
                "location": _location_name(state),
                "inventory_count": len(state.get("inventory") or []),
                "event_count": len(state.get("events") or []),
                "npc_count": sum(len(loc.get("npcs") or []) for loc in (state.get("locations") or []) if isinstance(loc, dict)),
                "turn_summaries": len(state.get("turn_summaries") or []),
                "elapsed_total": round(time.perf_counter() - t_run, 2),
            }
            report["turns"].append(row)
            jsonl.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
            jsonl.flush()

            if row["used_fallback"]:
                fallback_count += 1
            hard_fail = bool(err) or len(narr) < 40
            if hard_fail:
                consecutive_fails += 1
                if err:
                    error_count += 1
                if len(narr) < 80:
                    short_narration_count += 1
            else:
                consecutive_fails = 0
                if len(narr) < 80:
                    short_narration_count += 1

            mean_so_far = (time.perf_counter() - t_run) / (i + 1)  # opening + i turns
            eta = mean_so_far * (target_turns - i)
            _log(
                log,
                f"turn {i} {elapsed:.1f}s fallback={row['used_fallback']} err={bool(err)} "
                f"loc={row['location']!r} inv={row['inventory_count']} events={row['event_count']} "
                f"npcs={row['npc_count']} narr_len={row['narration_len']} "
                f"mean/step={mean_so_far:.0f}s eta~{eta/60:.1f}m",
            )
            if narr:
                _log(log, "preview: " + narr[:280])

            # Checkpoint full report every 5 turns
            if i % 5 == 0 or i == target_turns:
                report["summary"] = {
                    "completed_turns": i,
                    "target_turns": target_turns,
                    "fallback_count": fallback_count,
                    "error_count": error_count,
                    "short_narration_count": short_narration_count,
                    "consecutive_fails": consecutive_fails,
                    "elapsed_seconds": round(time.perf_counter() - t_run, 2),
                    "in_progress": i < target_turns,
                }
                report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

            if consecutive_fails >= abort_fails:
                _log(log, f"ABORT: {consecutive_fails} consecutive hard failures")
                report["summary"]["aborted"] = True
                report["summary"]["reason"] = f"{consecutive_fails} consecutive hard failures"
                report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
                return 4

        total = time.perf_counter() - t_run
        times = [float(r.get("seconds") or 0) for r in report["turns"]]
        if report.get("opening"):
            times = [float(report["opening"].get("seconds") or 0)] + times
        locations = [r.get("location") for r in report["turns"] if r.get("location")]
        report["summary"] = {
            "completed_turns": len(report["turns"]),
            "target_turns": target_turns,
            "fallback_count": fallback_count,
            "error_count": error_count,
            "short_narration_count": short_narration_count,
            "elapsed_seconds": round(total, 2),
            "mean_step_seconds": round(sum(times) / max(1, len(times)), 2),
            "unique_locations": sorted(set(locations)),
            "location_count": len(set(locations)),
            "final_player": _player_snapshot(get_state(include_hidden=True)),
            "aborted": False,
            "in_progress": False,
            "ok": error_count == 0 and fallback_count == 0,
        }
        report["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
        _log(log, "\n=== DONE ===")
        _log(log, json.dumps(report["summary"], ensure_ascii=True, indent=2))
        _log(log, f"report: {report_path}")
        _log(log, f"jsonl: {jsonl_path}")
        return 0 if report["summary"].get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
