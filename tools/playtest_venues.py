"""
Live probe: are venues (shops, inns, smithies) persistent, re-enterable places?

Answers four questions the flat `locations` table cannot answer on its own:

  1. Entering a shop on a square -- does any durable state exist afterwards?
  2. Standing on that square, can the player go back into the same shop, or does
     a second visit mint a duplicate place?
  3. Standing somewhere else entirely, can the player "return to the shop"? Should
     they be able to in one move?
  4. Is there any notion of opening hours, or of some shop kinds being rarer than
     others?

The script drives a scripted action sequence rather than free play so the same
beats run every time, and dumps the `locations` table after every turn.

    python tools/playtest_venues.py

Env:
    PLAYTEST_OLLAMA_MODEL   default qwen2.5:7b-instruct
    OLLAMA_BASE_URL         default http://127.0.0.1:11434
    PLAYTEST_OUT            optional path for the JSON report
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Each step: (label, player input, what we are checking)
SCRIPT: list[tuple[str, str, str]] = [
    ("find_shop", "I look around the square for an apothecary and step inside it.",
     "does entering a venue create durable state?"),
    ("inside_act", "I ask the apothecary keeper what remedies they stock.",
     "is the player actually inside the venue?"),
    ("step_out", "I step back out of the apothecary onto the square.",
     "does leaving return the player to the square?"),
    ("re_enter_local", "I go back inside the same apothecary.",
     "re-entry from the square: same place or a duplicate?"),
    ("leave_town", "I leave the square and take the east road out of town.",
     "move away so the next step is a distant return"),
    ("distant_act", "I keep walking east along the road, watching the treeline.",
     "put real distance between player and the venue"),
    ("return_distant", "I head all the way back to that apothecary I visited earlier.",
     "distant return: does it move there, and is it the same place?"),
    ("hours_probe", "I try the apothecary door late at night to see if it is still open.",
     "is there any opening-hours concept at all?"),
]

SETUP = {
    "player_name": "Ash",
    "player_sex": "unspecified",
    "backstory_mode": "known",
    "character_backstory": "A road courier carrying a sealed letter and old debts.",
    "memory_policy": "known",
    "difficulty": "normal",
    "narration_detail": "balanced",
    "world_style": "frontier dark fantasy",
    "start_location": "Brimmer Square",
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


def main() -> int:
    model = os.getenv("PLAYTEST_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    temp = Path(tempfile.mkdtemp(prefix="morkyn_venues_"))
    for key, val in {
        "AI_RPG_DB": str(temp / "world.db"),
        "AI_RPG_SOURCE_INDEX": str(temp / "source_index"),
        "AI_RPG_HISTORY_SUMMARY": str(temp / "history.jsonl"),
        "AI_RPG_CONSOLIDATED_FACTS": str(temp / "facts.jsonl"),
        "AI_RPG_CAMPAIGN_SLOTS": str(temp / "slots"),
        "AI_RPG_MODEL_TRACE_DIR": str(temp / "traces"),
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
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app import venues
    from app.db import connect, init_db
    from app.llm import update_model_config
    from app.world import get_state, play_turn, start_playthrough_with_opening

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": model,
            "response_token_cap": 1500,
            "response_token_hard_cap": 2000,
        }
    )

    def locations() -> list[dict]:
        with connect() as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, code, name, visit_count, parent_id, kind, "
                    "open_minute, close_minute, keeper_npc_id FROM locations ORDER BY id"
                )
            ]
            names = {row["id"]: row["name"] for row in rows}
            keepers = {int(r["id"]): str(r["name"] or "") for r in conn.execute("SELECT id, name FROM npcs")}
            for row in rows:
                row["parent"] = names.get(int(row["parent_id"] or 0), "")
                row["keeper"] = keepers.get(int(row["keeper_npc_id"] or 0), "")
            return rows

    print(f"model     : {model}")
    print(f"workspace : {temp}", flush=True)

    start_playthrough_with_opening(SETUP)
    state = get_state(include_hidden=True)
    print(f"start     : {(state.get('current_location') or {}).get('name')}\n", flush=True)

    rows: list[dict] = []
    for index, (label, action, question) in enumerate(SCRIPT, start=1):
        t0 = time.perf_counter()
        payload = play_turn(action)
        state = get_state(include_hidden=True)
        elapsed = time.perf_counter() - t0
        here = state.get("current_location") or {}
        narration = _narration_of(payload, state)
        locs = locations()
        rows.append(
            {
                "step": index,
                "label": label,
                "question": question,
                "action": action,
                "seconds": round(elapsed, 1),
                "location_code": here.get("code"),
                "location_name": here.get("name"),
                "location_count": len(locs),
                "locations": locs,
                "narration": narration,
            }
        )
        print(
            f"[{index}] {label:16s} {elapsed:5.1f}s  here={str(here.get('name'))[:28]:28s} "
            f"places={len(locs)}",
            flush=True,
        )

    print("\n" + "=" * 74)
    print("LOCATIONS AT END")
    print("=" * 74)
    final = locations()
    for row in final:
        inside = f"  inside {row['parent']}" if row["parent"] else ""
        kind = f"  [{row['kind']}]" if row["kind"] else ""
        hours = ("  " + venues.describe_hours(row["open_minute"], row["close_minute"])) if row["kind"] else ""
        keeper = f"  keeper={row['keeper']}" if row["keeper"] else ""
        print(f"    {row['code']:5s} {row['name'][:30]:30s} visits={row['visit_count']}{kind}{inside}{hours}{keeper}")

    print("\n" + "=" * 74)
    print("=" * 74)
    print("VERDICT")
    print("=" * 74)
    interiors = [row for row in final if row["parent"]]
    orphans = [row for row in final if row["kind"] and not row["parent"]]
    print(f"    venues created as real interiors : {len(interiors)}")
    print(f"    venue rows with no parent        : {len(orphans)}  (should be 0)")
    print(f"    venues with a bound keeper       : {sum(1 for r in interiors if r['keeper'])}/{len(interiors)}")
    for row in rows:
        if row["label"] in ("find_shop", "re_enter_local", "return_distant", "hours_probe"):
            print(f"    {row['label']:16s} ended at {row['location_name']}")

    print("STEP BY STEP")
    print("=" * 74)
    for row in rows:
        print(f"[{row['step']}] {row['label']}  -- {row['question']}")
        print(f"    input : {row['action']}")
        print(f"    ended at: {row['location_name']}  (places now {row['location_count']})")
        print()

    out = os.getenv("PLAYTEST_OUT")
    if out:
        Path(out).write_text(json.dumps({"model": model, "rows": rows}, indent=2), encoding="utf-8")
        print(f"report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
