"""
Long playtest where the game's own "Deeper idea" is the player.

Each turn asks get_input_suggestions(deeper=True) for one idea, the same call
the in-game Deeper idea button makes, then plays that idea as the turn. The
three short Ideas are skipped, so one run tests both the idea generator (does
it read the scene, name real things, avoid repeating itself) and the turn
engine (does it carry a long game the model is steering).

Runs in-process on the real Qwen3 8B with every store isolated, so the live
world.db and saves are never touched. Shipped defaults are kept for the turn
pipeline; only the model, context and image settings are pinned.

    python tools/playtest_deeper_ideas.py               # 100 turns
    python tools/playtest_deeper_ideas.py --turns 10

Output: data/playtest_reports/deeper-ideas-<stamp>/
    progress.jsonl   one line per turn, written as it goes
    report.json      the summary and flags at the end
    data/            the isolated game (world.db, model_traces, ...)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_DB = (ROOT / "data" / "world.db").resolve()
WEIGHTS = Path(os.getenv("PLAYTEST_8B_GGUF", r"D:\morkyn-stage-models\Qwen3-8B-Q4_K_M.gguf"))
REPORT_DIR = ROOT / "data" / "playtest_reports"

sys.path.insert(0, str(ROOT))
from tools.playtest_setup_presets import isolated_data_env  # noqa: E402

SETUP = {
    "player_name": "Mara Quill",
    "player_title": "Courier",
    "player_age": "31",
    "player_sex": "female",
    "backstory_mode": "known",
    "character_backstory": "Mara carried letters between timber landings. She knows one small practical spark and arrived at Redmill Ford in a wool cloak with a belt knife.",
    "memory_policy": "known",
    "difficulty": "normal",
    "narration_detail": "balanced",
    "world_style": "frontier dark fantasy",
    "custom_style": "Common practical magic is ordinary. A lost fight leaves a lasting injury.",
    "start_location": "Redmill Ford",
    "leveling_system": True,
    "game_system": False,
    "system_style": "subtle blue-window system",
    "special_ability": True,
    "special_ability_origin": "innate",
    "special_ability_locked": False,
    "special_abilities": [
        {
            "name": "Hearth Spark",
            "description": "A small practical spark that lights a candle or warms cold hands. It is common utility magic, not a weapon.",
            "locked": False,
            "prerequisites": "",
            "cost": "a little mana",
            "power_type": "linear",
        }
    ],
    "starter_equipment": "wool cloak, belt knife",
    "appearance": "torso: wool cloak; waist: belt knife",
    "relationships_enabled": True,
    "fighting_enabled": True,
    "items_enabled": True,
    "map_travel_enabled": True,
    "skills_enabled": True,
    "quests_enabled": True,
    "factions_enabled": True,
    "economy_enabled": True,
    "dice_checks_enabled": True,
    "auto_check_on_risky_actions": True,
    "skill_style": "standard",
    "npc_density": "moderate",
    "magic_level": "common utility",
    "death_rules": "lasting injuries",
    "economy": "scarce",
    "quest_style": "posted jobs",
    "faction_pressure": "guild control",
    "tone": "grounded adventure",
}

WORD = re.compile(r"[a-z']+")
STOP = set(
    "a an the and or but to of in on at by for with from into onto over under i my me "
    "her his their them they it its is are was be this that what who about as up out "
    "if then so not no do does did ask asks tell tells".split()
)


def words(text: str) -> set[str]:
    return {w for w in WORD.findall(str(text or "").lower()) if w not in STOP and len(w) > 2}


def overlap(a: str, b: str) -> float:
    left, right = words(a), words(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def narration_of(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    turn = payload.get("turn") if isinstance(payload.get("turn"), dict) else None
    for source in ([turn] if turn else []) + [payload]:
        for key in ("narration", "latest_narration", "opening_narration", "response"):
            text = str(source.get(key) or "").strip()
            if text:
                return text
        parts = [
            str(seg.get("text") or "").strip()
            for seg in source.get("narration_segments") or []
            if isinstance(seg, dict) and str(seg.get("text") or "").strip()
        ]
        if parts:
            return "\n".join(parts)
    return ""


def snapshot(state: dict) -> dict:
    player = state.get("player") if isinstance(state.get("player"), dict) else {}
    return {
        "location": (state.get("current_location") or {}).get("name"),
        "level": player.get("level"),
        "xp": player.get("xp"),
        "gold": player.get("gold"),
        "health": player.get("health"),
        "inventory": len(state.get("inventory") or []),
        "quests": len(state.get("quests") or []),
        "events": len(state.get("events") or []),
    }


def known_names(state: dict) -> set[str]:
    """Lowercased names the idea could legitimately point at."""
    names: set[str] = set()
    for loc in state.get("locations") or []:
        if isinstance(loc, dict):
            names.add(str(loc.get("name") or ""))
            for npc in loc.get("npcs") or []:
                if isinstance(npc, dict):
                    names.add(str(npc.get("name") or ""))
    for key in ("inventory", "quests", "events"):
        for row in state.get(key) or []:
            if isinstance(row, dict):
                names.add(str(row.get("name") or row.get("title") or ""))
    return {n.lower() for n in names if n.strip()}


def idea_flags(action: str, why: str, scene: str, state: dict, past: list[str]) -> list[str]:
    flags: list[str] = []
    if not action.strip():
        return ["empty"]
    if "[[" in action or "[[" in why:
        flags.append("raw_code")
    if len(action) > 400:
        flags.append("too_long")
    if not why.strip():
        flags.append("no_why")
    # Grounding: shares a content word with the last scene, or names a known thing.
    low = action.lower()
    if not (words(action) & words(scene)) and not any(name and name in low for name in known_names(state)):
        flags.append("ungrounded")
    recent = [(overlap(action, prior), i) for i, prior in enumerate(past[-6:])]
    if recent and max(recent)[0] >= 0.6:
        flags.append(f"repeats_recent({max(recent)[0]:.0%})")
    return flags


class Run:
    def __init__(self, out: Path):
        self.out = out
        self.progress = out / "progress.jsonl"

    def log(self, event: str, **fields) -> None:
        row = {"t": time.strftime("%H:%M:%S"), "event": event, **fields}
        line = json.dumps(row, ensure_ascii=True, default=str)
        print(line[:600], flush=True)
        with self.progress.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def ask_deeper(get_input_suggestions, LlmError) -> tuple[str, str, str, float]:
    """(action, why, source, seconds). Retries once, then falls back to the short Ideas."""
    started = time.perf_counter()
    errors: list[str] = []
    for _ in range(2):
        try:
            deeper = (get_input_suggestions("", deeper=True) or {}).get("deeper") or {}
            action = str(deeper.get("action") or "").strip()
            if action:
                return action, str(deeper.get("why") or "").strip(), "deeper", time.perf_counter() - started
            errors.append("empty deeper")
        except LlmError as exc:
            errors.append(str(exc)[:200])
    try:
        short = (get_input_suggestions("") or {}).get("suggestions") or []
        first = next((str(s).strip() for s in short if str(s).strip()), "")
        if first:
            return first, "; ".join(errors), "ideas_fallback", time.perf_counter() - started
    except LlmError as exc:
        errors.append(str(exc)[:200])
    return "I look around and take stock.", "; ".join(errors), "stock_fallback", time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--context", default="16384", help="AI_RPG_CONTEXT_TOKENS for the 8B")
    args = parser.parse_args()

    if not WEIGHTS.is_file():
        raise SystemExit(f"8B weights missing: {WEIGHTS}")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = REPORT_DIR / f"deeper-ideas-{stamp}"
    data_dir = out / "data"
    data_dir.mkdir(parents=True)
    os.environ.update(isolated_data_env(str(data_dir)))
    os.environ.update(
        {
            "AI_RPG_MODEL_PROVIDER": "mle",
            "MLE_MODEL": "qwen3:8b",
            "MLE_GGUF": str(WEIGHTS),
            "AI_RPG_CONTEXT_TOKENS": str(args.context),
            "AI_RPG_IMAGE_PROVIDER": "off",
            "AI_RPG_IMAGE_AUTO_LAUNCH": "0",
        }
    )
    os.environ.pop("AI_RPG_LLAMA_CPP_CONTEXT", None)
    if Path(os.environ["AI_RPG_DB"]).resolve() == LIVE_DB:
        raise SystemExit("refusing to run against the live world.db")
    os.chdir(ROOT)

    from app.db import init_db
    from app.llm import LlmError, update_model_config
    from app.mle import resolve_model_path, status
    from app.world import get_input_suggestions, get_state, play_turn, start_playthrough_with_opening

    run = Run(out)
    init_db()
    update_model_config({"provider": "mle", "mle_model": "qwen3:8b"})
    resolved = resolve_model_path("qwen3:8b")
    if resolved is None or resolved.resolve() != WEIGHTS.resolve():
        raise SystemExit(f"story model resolved to {resolved}, not {WEIGHTS}")
    model = status("qwen3:8b")
    run.log("model", file=str(resolved), ok=bool(model.get("ok")), detail=str(model.get("detail") or "")[:200])
    if not model.get("ok"):
        return 1

    started = time.perf_counter()
    opening = start_playthrough_with_opening(dict(SETUP))
    scene = narration_of(opening)
    state = get_state(include_hidden=False)
    run.log("opening", seconds=round(time.perf_counter() - started, 1), narration=scene[:500], **snapshot(state))

    turns: list[dict] = []
    past: list[str] = []
    for n in range(1, args.turns + 1):
        row: dict = {"turn": n}
        try:
            action, why, source, idea_s = ask_deeper(get_input_suggestions, LlmError)
            flags = idea_flags(action, why, scene, state, past)
            past.append(action)
            t1 = time.perf_counter()
            result = play_turn(action)
            turn_s = time.perf_counter() - t1
            new_scene = narration_of(result) or narration_of(get_state(include_hidden=False))
            state = get_state(include_hidden=False)
            if overlap(new_scene, scene) >= 0.55:
                flags.append("narration_repeats_last")
            if len(new_scene) < 80:
                flags.append("short_narration")
            if result.get("used_fallback"):
                flags.append("turn_fallback")
            row.update(
                idea=action,
                why=why,
                idea_source=source,
                idea_s=round(idea_s, 1),
                turn_s=round(turn_s, 1),
                flags=flags,
                narration=new_scene[:700],
                **snapshot(state),
            )
            scene = new_scene
        except Exception as exc:  # keep going; a crash mid-run is itself a finding
            row.update(error=f"{type(exc).__name__}: {exc}"[:400], trace=traceback.format_exc()[-1500:])
        turns.append(row)
        run.log("turn", **row)

    flag_counts: dict[str, int] = {}
    for row in turns:
        for flag in row.get("flags") or []:
            key = flag.split("(")[0]
            flag_counts[key] = flag_counts.get(key, 0) + 1
    timed = [r for r in turns if "turn_s" in r]
    report = {
        "turns_requested": args.turns,
        "turns_played": len(timed),
        "errors": [{"turn": r["turn"], "error": r["error"]} for r in turns if r.get("error")],
        "idea_sources": {
            s: sum(1 for r in timed if r.get("idea_source") == s)
            for s in ("deeper", "ideas_fallback", "stock_fallback")
        },
        "flag_counts": flag_counts,
        "mean_idea_s": round(sum(r["idea_s"] for r in timed) / len(timed), 1) if timed else None,
        "mean_turn_s": round(sum(r["turn_s"] for r in timed) / len(timed), 1) if timed else None,
        "locations_visited": sorted({str(r.get("location")) for r in timed if r.get("location")}),
        "final": snapshot(state),
        "total_minutes": round((time.perf_counter() - started) / 60, 1),
        "data_dir": str(data_dir),
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    run.log("done", **report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
