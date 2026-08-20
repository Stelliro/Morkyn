"""
Long-run 7B consistency probe: does output quality decay as the world fills up?

The worry this answers: SQLite keeps accumulating summaries, events, NPCs,
conversations and source-index hits, all of which get packed into the turn
prompt. If that packet grows without bound, a 7B's remaining generation budget
shrinks and narration gets shorter and worse over time — the database starving
the model.

Per turn it records narration length, prompt size, generation time, and the
byte size of every context slice, then reports trends across the run.

    python tools/playtest_7b_longrun.py

Env:
    PLAYTEST_OLLAMA_MODEL   default qwen2.5:7b-instruct
    PLAYTEST_TURNS          default 30
    OLLAMA_BASE_URL         default http://127.0.0.1:11434
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A realistic mixed playthrough: talk, move, search, trade, rest, fight, lore.
# Cycled so later turns are comparable in kind to earlier ones — otherwise a
# length trend could just be "the questions got easier".
ACTIONS = [
    "I look around and ask a nearby merchant what trouble has been happening lately.",
    "I offer to help carry crates in exchange for news about the road east.",
    "I check my pack, then head for the east road out of town.",
    "I keep walking east, watching the treeline for movement.",
    "I search the roadside for anything a traveler might have dropped.",
    "I make camp off the road and rest until first light.",
    "I ask the nearest person what they know about the old ruins.",
    "I inspect the strange markings on the stones nearby.",
    "I try to barter for supplies with whatever I am carrying.",
    "I follow the road north toward the next settlement.",
    "I listen at the door before going any further.",
    "I draw my weapon and prepare for whatever is ahead.",
]


def _setup() -> dict:
    return {
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


def _narration_of(payload: dict, state: dict) -> str:
    for key in ("narration", "latest_narration", "opening_narration"):
        text = str((payload or {}).get(key) or "")
        if text:
            return text
    turn = (payload or {}).get("turn")
    if isinstance(turn, dict) and turn.get("narration"):
        return str(turn["narration"])
    for entry in reversed(state.get("history") or []):
        if str(entry.get("kind") or "") == "narration" and entry.get("content"):
            return str(entry["content"])
    return ""


def _trace_for_turn(trace_dir: Path, turn_no: int) -> dict | None:
    for path in sorted(trace_dir.glob("*.json")):
        try:
            trace = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if int(trace.get("turn") or -1) == turn_no:
            return trace
    return None


def _prompt_metrics(trace: dict | None) -> dict:
    """Prompt size for the draft call, plus per-slice context byte sizes."""
    if not trace:
        return {}
    out: dict = {"slices": {}}
    for entry in trace.get("model_trace") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("event") == "request" and entry.get("phase") in ("draft", "draft_dsl"):
            out["prompt_chars"] = entry.get("prompt_chars")
            out["prompt_tokens"] = entry.get("prompt_estimated_tokens")
            out["requested_max_tokens"] = entry.get("requested_max_tokens")
            budget = entry.get("token_budget")
            if isinstance(budget, dict):
                out["budget"] = budget
            break
    context = trace.get("prompt_context")
    if isinstance(context, dict):
        for key, value in context.items():
            try:
                out["slices"][key] = len(json.dumps(value, ensure_ascii=True, default=str))
            except Exception:
                out["slices"][key] = 0
    return out


def _trend(values: list[float]) -> float:
    """Least-squares slope per turn. Negative = shrinking over the run."""
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if not denom:
        return 0.0
    return sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n)) / denom


def _third_means(values: list[float]) -> tuple[float, float]:
    if len(values) < 6:
        return (statistics.fmean(values) if values else 0.0, statistics.fmean(values) if values else 0.0)
    cut = max(1, len(values) // 3)
    return statistics.fmean(values[:cut]), statistics.fmean(values[-cut:])


def main() -> int:
    model = os.getenv("PLAYTEST_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    turns = int(os.getenv("PLAYTEST_TURNS", "30"))
    temp = Path(tempfile.mkdtemp(prefix="morkyn_longrun_"))
    trace_dir = temp / "traces"
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(trace_dir),
        "AI_RPG_PACK_DIR": str(temp / "packs"),
        "AI_RPG_SKILL_LIBRARY": str(temp / "skill_library.json"),
        "AI_RPG_MODEL_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        "OLLAMA_MODEL": model,
        "OLLAMA_CONTEXT_TOKENS": os.getenv("OLLAMA_CONTEXT_TOKENS", "32768"),
        "OLLAMA_THINK": "0",
        "AI_RPG_OLLAMA_TIMEOUT": "600",
        "AI_RPG_TURN_DRAFT_TIMEOUT": "600",
        "AI_RPG_TURN_VERIFY_TIMEOUT": "480",
        # Keep every trace: the whole point is comparing turn 1 with turn N.
        "AI_RPG_MODEL_TRACE_KEEP": str(turns + 10),
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.db import connect, init_db
    from app.llm import update_model_config
    from app.world import get_state, play_turn, start_playthrough_with_opening

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": model,
            # App defaults, not the smoke script's low caps: the verify and
            # depth-retry passes emit a whole turn JSON and truncate under 1200.
            "response_token_cap": int(os.getenv("PLAYTEST_TOKEN_CAP", "1500")),
            "response_token_hard_cap": int(os.getenv("PLAYTEST_TOKEN_HARD_CAP", "2000")),
        }
    )

    print(f"model     : {model}")
    print(f"turns     : {turns}")
    print(f"workspace : {temp}", flush=True)

    rows: list[dict] = []
    started = time.perf_counter()

    t0 = time.perf_counter()
    opening = start_playthrough_with_opening(_setup())
    state = get_state(include_hidden=True)
    open_chars = len(_narration_of(opening, state))
    print(
        f"\n{'turn':>4} {'chars':>6} {'ptok':>7} {'sec':>6} {'db_rows':>8} "
        f"{'fb':>3}  action",
        flush=True,
    )
    print(f"{'open':>4} {open_chars:>6} {'-':>7} {time.perf_counter() - t0:>6.1f} "
          f"{'-':>8} {str(bool(opening.get('used_fallback')))[:1]:>3}", flush=True)

    def _db_rows(conn) -> int:
        total = 0
        for table in ("turn_summaries", "events", "npcs", "conversations", "journal", "gm_events"):
            try:
                total += int(conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] or 0)
            except Exception:
                pass
        return total

    for i in range(turns):
        action = ACTIONS[i % len(ACTIONS)]
        t0 = time.perf_counter()
        try:
            result = play_turn(action)
        except Exception as exc:
            print(f"{i + 1:>4} EXCEPTION {type(exc).__name__}: {exc}", flush=True)
            rows.append({"turn": i + 1, "error": f"{type(exc).__name__}: {exc}"})
            continue
        elapsed = time.perf_counter() - t0
        state = get_state(include_hidden=True)
        chars = len(_narration_of(result, state))
        fallback = bool(result.get("used_fallback"))

        db_turn = int((state.get("turn") or 0))
        metrics = _prompt_metrics(_trace_for_turn(trace_dir, db_turn))
        with connect() as conn:
            row_total = _db_rows(conn)

        rows.append(
            {
                "turn": i + 1,
                "db_turn": db_turn,
                "action": action,
                "chars": chars,
                "seconds": round(elapsed, 1),
                "fallback": fallback,
                "prompt_chars": metrics.get("prompt_chars"),
                "prompt_tokens": metrics.get("prompt_tokens"),
                "requested_max_tokens": metrics.get("requested_max_tokens"),
                "db_rows": row_total,
                "slices": metrics.get("slices") or {},
            }
        )
        ptok = metrics.get("prompt_tokens")
        print(
            f"{i + 1:>4} {chars:>6} {str(ptok or '-'):>7} {elapsed:>6.1f} "
            f"{row_total:>8} {str(fallback)[:1]:>3}  {action[:44]}",
            flush=True,
        )

    total_time = time.perf_counter() - started

    # ------------------------------------------------------------------ report
    ok = [r for r in rows if not r.get("error")]
    chars = [float(r["chars"]) for r in ok]
    ptoks = [float(r["prompt_tokens"]) for r in ok if r.get("prompt_tokens")]
    secs = [float(r["seconds"]) for r in ok]

    print("\n" + "=" * 66)
    print("CONSISTENCY OVER TIME")
    print("=" * 66)

    def report(label: str, values: list[float], unit: str = "") -> dict:
        if not values:
            print(f"{label:22s} (no data)")
            return {}
        first, last = _third_means(values)
        slope = _trend(values)
        drift = (last - first) / first * 100 if first else 0.0
        print(
            f"{label:22s} first-third {first:8.0f}{unit}  last-third {last:8.0f}{unit}  "
            f"drift {drift:+6.1f}%  slope {slope:+7.2f}/turn"
        )
        return {"first_third": round(first, 1), "last_third": round(last, 1),
                "drift_percent": round(drift, 1), "slope_per_turn": round(slope, 2)}

    summary = {
        "chars": report("narration chars", chars),
        "prompt_tokens": report("prompt tokens", ptoks),
        "seconds": report("turn seconds", secs),
    }

    if chars:
        below = sum(1 for c in chars if c < 1000)
        print(f"\nturns below 1000-char floor : {below}/{len(chars)} ({100.0 * below / len(chars):.0f}%)")
        print(f"min / median / max chars     : {min(chars):.0f} / {statistics.median(chars):.0f} / {max(chars):.0f}")
        summary["below_floor"] = below
        summary["chars_min"] = min(chars)
        summary["chars_median"] = statistics.median(chars)
        summary["chars_max"] = max(chars)

    fallbacks = sum(1 for r in ok if r["fallback"])
    errors = [r for r in rows if r.get("error")]
    print(f"fallbacks                    : {fallbacks}/{len(ok)}")
    print(f"exceptions                   : {len(errors)}")

    # ------------------------------------------------- what is filling context
    print("\n" + "=" * 66)
    print("CONTEXT COMPOSITION — is the database crowding the window?")
    print("=" * 66)
    with_slices = [r for r in ok if r.get("slices")]
    growth: dict[str, dict] = {}
    if len(with_slices) >= 4:
        cut = max(1, len(with_slices) // 3)
        early = with_slices[:cut]
        late = with_slices[-cut:]
        keys = set()
        for r in with_slices:
            keys.update(r["slices"].keys())
        for key in keys:
            e = statistics.fmean([r["slices"].get(key, 0) for r in early])
            l = statistics.fmean([r["slices"].get(key, 0) for r in late])
            growth[key] = {"early_bytes": round(e), "late_bytes": round(l), "delta": round(l - e)}
        ranked = sorted(growth.items(), key=lambda kv: kv[1]["delta"], reverse=True)
        total_early = sum(v["early_bytes"] for v in growth.values())
        total_late = sum(v["late_bytes"] for v in growth.values())
        print(f"total context   {total_early:>8} -> {total_late:>8} bytes "
              f"({(total_late - total_early) / max(1, total_early) * 100:+.1f}%)\n")
        print(f"{'slice':28s} {'early':>9} {'late':>9} {'growth':>9}")
        for key, val in ranked[:14]:
            if val["delta"] == 0 and val["late_bytes"] == 0:
                continue
            print(f"{key[:28]:28s} {val['early_bytes']:>9} {val['late_bytes']:>9} {val['delta']:>+9}")
        summary["context_total_early"] = total_early
        summary["context_total_late"] = total_late

    verdict = []
    if summary.get("chars", {}).get("drift_percent", 0) < -20:
        verdict.append("NARRATION SHRINKING: output length falls materially over the run.")
    elif summary.get("chars"):
        verdict.append("Narration length holds up across the run.")
    if summary.get("prompt_tokens", {}).get("drift_percent", 0) > 50:
        verdict.append("CONTEXT BLOAT: prompt grows sharply; check the largest slices above.")
    elif ptoks:
        verdict.append("Prompt size stays bounded.")
    if fallbacks:
        verdict.append(f"{fallbacks} fallback(s) occurred.")

    print("\n" + "=" * 66)
    print("VERDICT")
    print("=" * 66)
    for line in verdict:
        print(" -", line)
    print(f"\ntotal wall time: {total_time / 60:.1f} min")

    out = ROOT / "data" / "playtest_reports" / f"longrun-{model.replace(':', '-')}-{turns}t.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"model": model, "turns": turns, "summary": summary, "growth": growth, "rows": rows},
            ensure_ascii=True, indent=2, default=str,
        ),
        encoding="utf-8",
    )
    print(f"report: {out}")
    return 0 if fallbacks == 0 and not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
