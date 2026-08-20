"""
Live 7B playtest for the dice/band, pack, and danger systems.

Runs a real opening plus several real turns against a local Ollama 7B model and
reports on what the *model actually emitted* — specifically whether a small
model honours the band contract instead of writing raw numbers, and whether the
server rolled every amount.

Run from repo root:

    python tools/playtest_7b_bands.py

Env:
    PLAYTEST_OLLAMA_MODEL   default qwen2.5:7b-instruct
    PLAYTEST_TURNS          default 4
    OLLAMA_BASE_URL         default http://127.0.0.1:11434
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

# Amount fields the model is no longer supposed to fill in itself.
NUMERIC_FIELDS = (
    "xp_delta", "gold_delta", "health_delta", "karma_delta",
    "quantity_delta", "trust_delta", "fame_score", "delta",
)
BAND_FIELDS = (
    "xp_band", "gold_band", "health_band", "karma_band",
    "quantity_band", "trust_band", "fame_band", "delta_band",
)

PLAYER_ACTIONS = [
    "I look around the gate square and ask a nearby merchant what trouble has been happening lately.",
    "I offer to help the merchant carry crates in exchange for news about the road east.",
    "I check my pack, then head for the east road out of town.",
    "I keep walking east, watching the treeline for movement.",
    "I make camp off the road and rest until first light.",
    "I search the roadside for anything the last traveler dropped.",
]


def _narration_of(payload: dict, state: dict) -> str:
    """Narration lives on the payload for openings and in history for turns."""
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
        "dice_checks_enabled": True,
    }


BANDS = ("none", "trivial", "small", "moderate", "large", "huge")

# NAR+OPS opcodes that carry an amount. The 7B path drafts in the DSL, so band
# compliance has to be measured on `XP small` lines as well as JSON fields.
DSL_AMOUNT_OPS = ("XP", "GOLD", "HP", "KARMA")


def _model_outputs(trace: dict) -> list[str]:
    """
    Only what the model actually generated.

    Scanning whole trace files is wrong: they embed the prompt (which contains
    the literal spec text `QTY <band>`) and the applied `final_turn` (which
    contains server-rolled `health_delta` numbers). Both inflate the counts and
    make compliance look worse and better than it is at the same time.
    """
    out: list[str] = []
    for entry in trace.get("model_trace") or []:
        if isinstance(entry, dict) and entry.get("raw_content"):
            out.append(str(entry["raw_content"]))
    return out


def _scan_raw_model_output(trace_dir: Path) -> dict:
    """Count band vs raw-number usage in the model's own output."""
    stats = {
        "traces": 0,
        "responses": 0,
        "bands_emitted": {},
        "numbers_emitted": {},
        "band_values_seen": set(),
        "amount_ops_seen": [],
    }
    for path in sorted(trace_dir.glob("*.json")):
        try:
            trace = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        stats["traces"] += 1

        for raw in _model_outputs(trace):
            stats["responses"] += 1

            # --- JSON draft form --------------------------------------------
            for field in BAND_FIELDS:
                for hit in re.findall(rf'"{field}"\s*:\s*"([^"]*)"', raw):
                    stats["bands_emitted"][field] = stats["bands_emitted"].get(field, 0) + 1
                    stats["band_values_seen"].add(hit.lower().lstrip("-"))
            for field in NUMERIC_FIELDS:
                for hit in re.findall(rf'"{field}"\s*:\s*(-?\d+)', raw):
                    if int(hit) != 0:
                        stats["numbers_emitted"][field] = stats["numbers_emitted"].get(field, 0) + 1

            # --- NAR+OPS draft form -----------------------------------------
            if "===OPS===" not in raw:
                continue
            ops_block = raw.split("===OPS===")[-1]
            for line in ops_block.splitlines():
                line = line.strip()
                m = re.match(rf"^({'|'.join(DSL_AMOUNT_OPS)})\s+(-?\S+)", line)
                if m:
                    op, token = m.group(1), m.group(2).lower().lstrip("-")
                    stats["amount_ops_seen"].append(line[:70])
                    if token in BANDS:
                        stats["bands_emitted"][f"DSL:{op}"] = stats["bands_emitted"].get(f"DSL:{op}", 0) + 1
                        stats["band_values_seen"].add(token)
                    elif re.fullmatch(r"\d+", token):
                        stats["numbers_emitted"][f"DSL:{op}"] = stats["numbers_emitted"].get(f"DSL:{op}", 0) + 1
                qty = re.search(r"\bQTY\s+(-?\S+)", line)
                if qty:
                    token = qty.group(1).lower().lstrip("-").strip('"')
                    stats["amount_ops_seen"].append(line[:70])
                    if token in BANDS:
                        stats["bands_emitted"]["DSL:QTY"] = stats["bands_emitted"].get("DSL:QTY", 0) + 1
                        stats["band_values_seen"].add(token)
                    elif re.fullmatch(r"\d+", token):
                        stats["numbers_emitted"]["DSL:QTY"] = stats["numbers_emitted"].get("DSL:QTY", 0) + 1

    stats["band_values_seen"] = sorted(stats["band_values_seen"])
    stats["amount_ops_seen"] = sorted(set(stats["amount_ops_seen"]))[:40]
    return stats


def main() -> int:
    model = os.getenv("PLAYTEST_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    turns = int(os.getenv("PLAYTEST_TURNS", "4"))
    temp = Path(tempfile.mkdtemp(prefix="morkyn_7b_bands_"))
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
        "AI_RPG_OLLAMA_TIMEOUT": os.getenv("AI_RPG_OLLAMA_TIMEOUT", "600"),
        "AI_RPG_TURN_DRAFT_TIMEOUT": os.getenv("AI_RPG_TURN_DRAFT_TIMEOUT", "600"),
        "AI_RPG_TURN_VERIFY_TIMEOUT": os.getenv("AI_RPG_TURN_VERIFY_TIMEOUT", "480"),
        "AI_RPG_MODEL_TRACE_KEEP": "80",
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.content_packs import EXAMPLE_PACK, apply_active_packs, install_pack, remove_pack
    from app.db import init_db
    from app.llm import update_model_config
    from app.rng import recent_rolls
    from app.world import get_state, play_turn, start_playthrough_with_opening

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

    print(f"model      : {model}")
    print(f"workspace  : {temp}")

    # A pack must be installable against a live campaign without disturbing it.
    install_pack(EXAMPLE_PACK)
    apply_active_packs()
    print("pack       : riverlands_kit installed")

    report: dict = {"model": model, "turns": [], "errors": []}

    print("\n--- opening ---", flush=True)
    t0 = time.perf_counter()
    opening = start_playthrough_with_opening(_setup())
    elapsed = time.perf_counter() - t0
    state = get_state(include_hidden=True)
    narration = _narration_of(opening, state)
    fallback = bool(opening.get("used_fallback"))
    print(f"opening    : {elapsed:.1f}s fallback={fallback} chars={len(narration)}")
    if fallback:
        print(f"  reason   : {str(opening.get('fallback_reason'))[:200]}")
        report["errors"].append(f"opening fallback: {opening.get('fallback_reason')}")
    print(f"  preview  : {narration[:220]}")
    report["opening"] = {
        "seconds": round(elapsed, 1),
        "fallback": fallback,
        "chars": len(narration),
        "reason": str(opening.get("fallback_reason") or "")[:300],
    }

    for i in range(turns):
        action = PLAYER_ACTIONS[i % len(PLAYER_ACTIONS)]
        print(f"\n--- turn {i + 1} ---", flush=True)
        print(f"action     : {action[:90]}")
        t0 = time.perf_counter()
        try:
            result = play_turn(action)
        except Exception as exc:
            print(f"  EXCEPTION: {type(exc).__name__}: {exc}")
            report["errors"].append(f"turn {i + 1} raised {type(exc).__name__}: {exc}")
            continue
        elapsed = time.perf_counter() - t0
        state = get_state(include_hidden=True)
        narration = _narration_of(result, state)
        fallback = bool(result.get("used_fallback"))
        # play_turn surfaces the turn's rolls at the payload top level.
        band_rolls = (result.get("dice_rolls") or {}) if isinstance(result, dict) else {}
        if not band_rolls:
            band_rolls = ((result.get("state") or {}).get("dice_rolls") or {}) if isinstance(result, dict) else {}
        lines = band_rolls.get("lines") or []
        player = state.get("player") or {}
        print(f"time       : {elapsed:.1f}s fallback={fallback} chars={len(narration)}")
        if fallback:
            print(f"  reason   : {str(result.get('fallback_reason'))[:200]}")
            report["errors"].append(f"turn {i + 1} fallback: {result.get('fallback_reason')}")
        print(f"band mode  : {band_rolls.get('mode')}  rolls={len(lines)}")
        for line in lines:
            print(f"  dice     : {line}")
        print(f"player     : hp={player.get('health')}/{player.get('max_health')} "
              f"xp={player.get('xp')} gold={player.get('gold')} lvl={player.get('level')}")
        print(f"  preview  : {narration[:200]}")
        report["turns"].append(
            {
                "n": i + 1,
                "action": action,
                "seconds": round(elapsed, 1),
                "fallback": fallback,
                "reason": str(result.get("fallback_reason") or "")[:300],
                "chars": len(narration),
                "band_mode": band_rolls.get("mode"),
                "dice_lines": lines,
                "xp": player.get("xp"),
                "gold": player.get("gold"),
                "health": player.get("health"),
            }
        )

    # --- what did the model actually emit? ----------------------------------
    print("\n--- band contract compliance (raw model output) ---")
    scan = _scan_raw_model_output(trace_dir)
    total_bands = sum(scan["bands_emitted"].values())
    total_numbers = sum(scan["numbers_emitted"].values())
    print(f"traces read       : {scan['traces']}")
    print(f"band fields used  : {total_bands}  {scan['bands_emitted'] or ''}")
    print(f"raw numbers used  : {total_numbers}  {scan['numbers_emitted'] or ''}")
    print(f"band values seen  : {scan['band_values_seen']}")
    if total_bands + total_numbers:
        rate = 100.0 * total_bands / (total_bands + total_numbers)
        print(f"band compliance   : {rate:.0f}%")
        report["band_compliance_percent"] = round(rate, 1)
    report["scan"] = {k: v for k, v in scan.items()}

    print("\n--- dice audit ---")
    rolls = recent_rolls(limit=40)
    print(f"rolls recorded    : {len(rolls)}")
    for roll in rolls[:10]:
        print(f"  t{roll['turn']} {roll['kind']:12s} {roll['band']:10s} "
              f"{roll['notation']:10s} -> {roll['value']}")

    print("\n--- danger model ---")
    try:
        from app import encounters as enc

        snapshot = enc.player_snapshot()
        from app.world import get_weather, get_world_time

        assessment = enc.assess_danger(
            terrain="forest",
            weather=get_weather(),
            world_time=get_world_time(),
            player=snapshot.get("player"),
            skills=snapshot.get("skills"),
            resources=snapshot.get("resources"),
            inventory_summary=snapshot.get("inventory_summary"),
            options=snapshot.get("options"),
        )
        print(f"forest danger     : {assessment['danger']} ({assessment['band']}) "
              f"env={assessment['environment']} x{assessment['player_multiplier']}")
        report["danger"] = {
            "danger": assessment["danger"],
            "band": assessment["band"],
            "environment": assessment["environment"],
            "multiplier": assessment["player_multiplier"],
        }
    except Exception as exc:
        print(f"  danger model FAILED: {type(exc).__name__}: {exc}")
        report["errors"].append(f"danger model: {exc}")

    # Pack removal must be clean even after live play.
    removed = remove_pack("riverlands_kit")
    print(f"\npack removal      : {removed}")
    report["pack_removal"] = removed

    fallbacks = sum(1 for t in report["turns"] if t["fallback"]) + (1 if report["opening"]["fallback"] else 0)
    print("\n=== SUMMARY ===")
    print(f"model             : {model}")
    print(f"turns run         : {len(report['turns'])}")
    print(f"fallbacks         : {fallbacks}")
    print(f"errors            : {len(report['errors'])}")
    for err in report["errors"]:
        print(f"  ! {err[:200]}")
    if report["turns"]:
        avg = sum(t["seconds"] for t in report["turns"]) / len(report["turns"])
        print(f"mean turn time    : {avg:.1f}s")
        report["mean_turn_seconds"] = round(avg, 1)
    report["fallbacks"] = fallbacks

    out = ROOT / "data" / "playtest_reports" / f"7b-bands-{model.replace(':', '-').replace('/', '-')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    print(f"report            : {out}")

    return 0 if fallbacks == 0 and not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
