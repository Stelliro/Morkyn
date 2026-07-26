"""
Full setup randomize (field-by-field, same path as UI Confirm Randomize)
then multi-turn play as the player vs local 8B DM.

Uses the live HTTP API on AI_RPG_BASE (default http://127.0.0.1:8000).
Writes data/playtest_reports/full-random-play-<stamp>.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = os.getenv("AI_RPG_BASE", "http://127.0.0.1:8000").rstrip("/")
TIMEOUT = int(os.getenv("PLAYTEST_HTTP_TIMEOUT", "600"))
# Optional idea seed (empty = pure cold randomize)
IDEA = os.getenv(
    "PLAYTEST_IDEA",
    "grounded frontier adventure with local stakes, fair DM, modest starting power",
).strip()[:400]
MAX_TURNS = int(os.getenv("PLAYTEST_TURNS", "5"))
REPORT_DIR = ROOT / "data" / "playtest_reports"


def http_json(method: str, path: str, body: dict | None = None, timeout: int = TIMEOUT) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail[:800]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} -> {exc}") from exc


def merge_fields(current: dict, payload: dict) -> None:
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else None
    if fields:
        for k, v in fields.items():
            if v is None:
                continue
            current[k] = v
    else:
        for k, v in payload.items():
            if k.startswith("_") or k in {"notes", "locked_setup", "current_setup", "return_fields", "rules", "task"}:
                continue
            if v is None:
                continue
            current[k] = v
    if "special_abilities" in payload and isinstance(payload["special_abilities"], list):
        current["special_abilities"] = payload["special_abilities"]
    # Nested fields.special_abilities
    if fields and isinstance(fields.get("special_abilities"), list):
        current["special_abilities"] = fields["special_abilities"]


def narration_of(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("narration", "latest_narration", "opening_narration"):
        if payload.get(key):
            return str(payload[key])
    turn = payload.get("turn")
    if isinstance(turn, dict) and turn.get("narration"):
        return str(turn["narration"])
    history = payload.get("history")
    if isinstance(history, list):
        for entry in reversed(history):
            if isinstance(entry, dict) and entry.get("role") in {"assistant", "dm", "narrator", None}:
                text = entry.get("content") or entry.get("text")
                if text:
                    return str(text)
    return ""


def setup_payload_from_current(current: dict) -> dict:
    """Build /api/setup body from randomized current dict + defaults."""
    abilities = current.get("special_abilities") if isinstance(current.get("special_abilities"), list) else []
    origin = str(current.get("special_ability_origin") or "none")
    if origin == "none":
        abilities = []
    first = abilities[0] if abilities else {}
    return {
        "player_name": str(current.get("player_name") or "Wanderer")[:80],
        "player_public_name": str(current.get("player_public_name") or "")[:100],
        "player_title": str(current.get("player_title") or "")[:100],
        "player_age": str(current.get("player_age") or "")[:60],
        "player_sex": str(current.get("player_sex") or "")[:80],
        "previous_life_age": str(current.get("previous_life_age") or "")[:60],
        "previous_life_sex": str(current.get("previous_life_sex") or "")[:80],
        "backstory_mode": str(current.get("backstory_mode") or "known")[:60],
        "character_backstory": str(current.get("character_backstory") or "")[:1600],
        "hair": str(current.get("hair") or "")[:120],
        "facial_features": str(current.get("facial_features") or "")[:300],
        "appearance": str(current.get("appearance") or "")[:400],
        "starter_equipment": str(current.get("starter_equipment") or "")[:500],
        "memory_policy": str(current.get("memory_policy") or "known")[:80],
        "difficulty": str(current.get("difficulty") or "normal")[:60],
        "narration_detail": str(current.get("narration_detail") or "rich")[:120],
        "world_style": str(current.get("world_style") or "frontier dark fantasy")[:120],
        "custom_style": str(current.get("custom_style") or "")[:800],
        "start_location": str(current.get("start_location") or "Mosswake Gate")[:100],
        "leveling_system": bool(current.get("leveling_system", True)),
        "game_system": bool(current.get("game_system", False)),
        "system_style": str(current.get("system_style") or "subtle blue-window system")[:120],
        "special_ability_origin": origin[:40],
        "special_ability": bool(abilities),
        "special_ability_locked": bool(first.get("locked")) if first else False,
        "special_ability_name": str(first.get("name") or "")[:100],
        "special_ability_description": str(first.get("description") or "")[:800],
        "special_abilities": abilities,
        "skill_style": str(current.get("skill_style") or "standard")[:60],
        "skill_levels_enabled": bool(current.get("skill_levels_enabled", True)),
        "new_skill_frequency": str(current.get("new_skill_frequency") or "normal")[:80],
        "proficiency_system": bool(current.get("proficiency_system", True)),
        "proficiency_access": str(current.get("proficiency_access") or "learned")[:80],
        "skill_growth_speed": str(current.get("skill_growth_speed") or "normal")[:80],
        "proficiency_growth_speed": str(current.get("proficiency_growth_speed") or "normal")[:80],
        "xp_growth_speed": str(current.get("xp_growth_speed") or "normal")[:80],
        "custom_skills": str(current.get("custom_skills") or "")[:1200],
        "death_rules": str(current.get("death_rules") or "downed, not deleted")[:80],
        "npc_stat_scaling": str(current.get("npc_stat_scaling") or "relative ranks")[:80],
        "npc_skill_frequency": str(current.get("npc_skill_frequency") or "some trained NPCs")[:100],
        "rank_scale": str(current.get("rank_scale") or "F,E,D,C,B,A,S,SS,SSS")[:100],
        "economy": str(current.get("economy") or "scarce")[:80],
        "loot_rarity": str(current.get("loot_rarity") or "earned and uncommon")[:80],
        "inventory_weight_limit": int(current.get("inventory_weight_limit") or 60),
        "inventory_slot_limit": int(current.get("inventory_slot_limit") or 24),
        "inventory_rules": str(current.get("inventory_rules") or "")[:900],
        "magic_level": str(current.get("magic_level") or "rare")[:80],
        "world_races": str(current.get("world_races") or "human")[:120],
        "race_magic_enabled": bool(current.get("race_magic_enabled", False)),
        "race_magic_rarity": str(current.get("race_magic_rarity") or "same as world magic")[:100],
        "race_magic_rules": str(current.get("race_magic_rules") or "")[:1200],
        "race_ability_rules": str(current.get("race_ability_rules") or "")[:1200],
        "tech_level": str(current.get("tech_level") or "iron age")[:80],
        "tone": str(current.get("tone") or "grounded adventure")[:100],
        "npc_density": str(current.get("npc_density") or "moderate")[:80],
        "quest_style": str(current.get("quest_style") or "emergent")[:100],
        "faction_pressure": str(current.get("faction_pressure") or "local disputes")[:100],
        "session_theme": current.get("session_theme") if isinstance(current.get("session_theme"), dict) else None,
        "compose_intent": current.get("_compose_intent") if isinstance(current.get("_compose_intent"), dict) else None,
    }


PLAYER_TURNS = [
    "I take a slow look around where I am — sights, sounds, people, exits — and note anything that looks like trouble or opportunity.",
    "I approach the nearest person who seems approachable and ask what this place is and what work or news locals care about right now.",
    "I carefully check my pockets and what I am carrying, then try one small practical action that fits my skills or gear without picking a fight.",
    "I follow up on the most interesting lead from what I just learned — ask one more pointed question or investigate one concrete detail.",
    "I try to make a short-term plan: find shelter, food, or a safe place to sleep before night, and act on the first step.",
]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report: dict = {
        "stamp": stamp,
        "base": BASE,
        "idea": IDEA,
        "randomize": [],
        "setup_summary": {},
        "opening": {},
        "turns": [],
        "coherence_notes": [],
        "play_quality": {},
    }
    print(f"BASE {BASE}", flush=True)
    print(f"IDEA {IDEA!r}", flush=True)

    # Health
    try:
        state0 = http_json("GET", "/api/state", timeout=30)
        print("state ok, keys:", list(state0.keys())[:12], flush=True)
    except Exception as exc:
        print("FAIL cannot reach API:", exc, flush=True)
        return 1

    # Composer field order
    composer = http_json("GET", "/api/setup/composer", timeout=60)
    field_order = list(composer.get("field_order") or [])
    if not field_order:
        print("FAIL empty field_order", flush=True)
        return 1
    print(f"fields to randomize: {len(field_order)}", flush=True)

    current: dict = {
        "_locked_fields": [],
        "_locked_values": {},
        "_included_fields": [],
    }

    # Compose intent from idea (director seed)
    t0 = time.perf_counter()
    try:
        composed = http_json(
            "POST",
            "/api/setup/compose-intent",
            {"idea": IDEA, "current": current},
            timeout=TIMEOUT,
        )
        intent = composed.get("intent") if isinstance(composed.get("intent"), dict) else {}
        theme = composed.get("session_theme") if isinstance(composed.get("session_theme"), dict) else {}
        overrides = composed.get("field_overrides") if isinstance(composed.get("field_overrides"), dict) else {}
        current["_compose_intent"] = intent
        current["_randomize_idea"] = IDEA
        if theme:
            current["session_theme"] = theme
        for k, v in overrides.items():
            current[k] = v
        report["compose"] = {
            "seconds": round(time.perf_counter() - t0, 2),
            "intent": intent,
            "session_theme": theme,
            "overrides": overrides,
        }
        print(
            f"compose {report['compose']['seconds']}s genre={intent.get('genre')!r} "
            f"isekai={intent.get('isekai')} overrides={list(overrides.keys())}",
            flush=True,
        )
    except Exception as exc:
        report["compose"] = {"error": str(exc), "seconds": round(time.perf_counter() - t0, 2)}
        print("compose failed (continuing pure randomize):", exc, flush=True)

    # Field-by-field randomize (mirrors UI Confirm Randomize walk)
    for idx, name in enumerate(field_order, 1):
        # Skip dependent empties lightly
        if name in {"previous_life_age", "previous_life_sex"}:
            mode = str(current.get("backstory_mode") or "").lower()
            if not any(m in mode for m in ("reincarn", "transmigr", "reborn", "former")):
                print(f"[{idx}/{len(field_order)}] skip {name} (no former life)", flush=True)
                continue
        if name in {"race_magic_rarity", "race_magic_rules"} and not current.get("race_magic_enabled"):
            print(f"[{idx}/{len(field_order)}] skip {name} (race magic off)", flush=True)
            continue
        if name == "system_style" and not current.get("game_system"):
            print(f"[{idx}/{len(field_order)}] skip {name} (game system off)", flush=True)
            continue
        if name == "special_abilities" and str(current.get("special_ability_origin") or "none").lower() == "none":
            current["special_abilities"] = []
            print(f"[{idx}/{len(field_order)}] skip special_abilities (origin none)", flush=True)
            continue

        snap = dict(current)
        snap["_active_field"] = name
        snap["_field_context"] = _field_context_for(name, current)
        snap["_included_fields"] = list(field_order[:idx])
        t1 = time.perf_counter()
        err = None
        payload: dict = {}
        try:
            payload = http_json(
                "POST",
                "/api/randomize-setup",
                {"group": f"field:{name}", "current": snap},
                timeout=TIMEOUT,
            )
            merge_fields(current, payload)
        except Exception as exc:
            err = str(exc)
            print(f"[{idx}/{len(field_order)}] FAIL {name}: {err[:200]}", flush=True)
        dt = round(time.perf_counter() - t1, 2)
        preview = current.get(name)
        if name == "special_abilities":
            abs_list = current.get("special_abilities") if isinstance(current.get("special_abilities"), list) else []
            preview = [{"name": a.get("name"), "locked": a.get("locked"), "power_type": a.get("power_type")} for a in abs_list if isinstance(a, dict)]
        elif isinstance(preview, str) and len(preview) > 120:
            preview = preview[:120] + "…"
        row = {"field": name, "seconds": dt, "error": err, "value": preview}
        report["randomize"].append(row)
        print(f"[{idx}/{len(field_order)}] {name} {dt}s -> {preview!r}"[:220], flush=True)

    report["setup_summary"] = {
        "player_name": current.get("player_name"),
        "backstory_mode": current.get("backstory_mode"),
        "difficulty": current.get("difficulty"),
        "world_style": current.get("world_style"),
        "tone": current.get("tone"),
        "start_location": current.get("start_location"),
        "special_ability_origin": current.get("special_ability_origin"),
        "special_abilities": current.get("special_abilities"),
        "custom_skills": current.get("custom_skills"),
        "game_system": current.get("game_system"),
        "character_backstory": (str(current.get("character_backstory") or "")[:400]),
        "appearance": current.get("appearance"),
        "starter_equipment": current.get("starter_equipment"),
    }

    # Start playthrough
    setup_body = setup_payload_from_current(current)
    print("\n=== START PLAYTHROUGH ===", flush=True)
    t2 = time.perf_counter()
    try:
        opening = http_json("POST", "/api/setup", setup_body, timeout=TIMEOUT)
        open_narr = narration_of(opening)
        report["opening"] = {
            "seconds": round(time.perf_counter() - t2, 2),
            "used_fallback": bool(opening.get("used_fallback")),
            "fallback_reason": opening.get("fallback_reason") or "",
            "narration": open_narr,
            "narr_len": len(open_narr),
            "location": (opening.get("current_location") or {}).get("name")
            if isinstance(opening.get("current_location"), dict)
            else opening.get("location"),
        }
        print(
            f"opening {report['opening']['seconds']}s fallback={report['opening']['used_fallback']} "
            f"len={report['opening']['narr_len']}",
            flush=True,
        )
        print("OPENING:\n", open_narr[:900], "\n", flush=True)
    except Exception as exc:
        report["opening"] = {"error": str(exc), "seconds": round(time.perf_counter() - t2, 2)}
        print("START FAIL", exc, flush=True)
        _write(report, stamp)
        return 2

    # Play turns
    for i, action in enumerate(PLAYER_TURNS[:MAX_TURNS], 1):
        print(f"\n=== PLAYER TURN {i} ===\n> {action}", flush=True)
        t3 = time.perf_counter()
        try:
            result = http_json("POST", "/api/turn", {"text": action}, timeout=TIMEOUT)
            narr = narration_of(result)
            # Prefer state after turn
            try:
                state = http_json("GET", "/api/state", timeout=60)
            except Exception:
                state = result
            loc = ""
            if isinstance(state.get("current_location"), dict):
                loc = state["current_location"].get("name") or ""
            player = state.get("player") if isinstance(state.get("player"), dict) else {}
            row = {
                "n": i,
                "input": action,
                "seconds": round(time.perf_counter() - t3, 2),
                "used_fallback": bool(result.get("used_fallback")),
                "fallback_reason": result.get("fallback_reason") or "",
                "narration": narr,
                "narr_len": len(narr),
                "location": loc,
                "player_level": player.get("level"),
                "player_hp": player.get("health"),
                "player_gold": player.get("gold"),
            }
            report["turns"].append(row)
            print(
                f"turn{i} {row['seconds']}s fallback={row['used_fallback']} len={row['narr_len']} loc={loc!r}",
                flush=True,
            )
            print(narr[:700], "\n", flush=True)
        except Exception as exc:
            report["turns"].append({"n": i, "input": action, "error": str(exc)})
            print("TURN FAIL", exc, flush=True)
            break

    # Lightweight coherence heuristics
    report["coherence_notes"] = _coherence_notes(report)
    report["play_quality"] = _play_quality(report)
    path = _write(report, stamp)
    print("\n=== REPORT ===", path, flush=True)
    print(json.dumps(report["play_quality"], indent=2), flush=True)
    for note in report["coherence_notes"]:
        print("-", note, flush=True)
    bad = any(t.get("error") or t.get("used_fallback") for t in report["turns"]) or report["opening"].get(
        "used_fallback"
    )
    return 2 if bad else 0


def _field_context_for(name: str, current: dict) -> dict:
    if name == "special_abilities":
        origin = str(current.get("special_ability_origin") or "none")
        existing = current.get("special_abilities") if isinstance(current.get("special_abilities"), list) else []
        return {
            "type": "special_abilities",
            "ability_origin": origin,
            "origin_label": origin,
            "existing_count": len(existing),
            "quantity_locked": False,
            "requested_count": None,
            "count_min": 1,
            "count_max": 4,
            "roll_rule": "Choose count 1-4; respect origin.",
        }
    return {"type": "field", "value": current.get(name)}


def _coherence_notes(report: dict) -> list[str]:
    notes: list[str] = []
    setup = report.get("setup_summary") or {}
    opening = str((report.get("opening") or {}).get("narration") or "")
    turns = report.get("turns") or []
    name = str(setup.get("player_name") or "").strip()
    place = str(setup.get("start_location") or "").strip()
    world = str(setup.get("world_style") or "").strip().lower()
    backstory = str(setup.get("character_backstory") or "").lower()
    if name and name.lower() not in opening.lower() and len(name) > 2:
        # Opening may avoid name-dropping; soft note
        notes.append(f"soft: player name {name!r} not mentioned in opening (may be intentional)")
    if place and place.lower() not in opening.lower() and len(place) > 3:
        notes.append(f"soft: start_location {place!r} not named in opening text")
    if (report.get("opening") or {}).get("used_fallback"):
        notes.append("hard: opening used fallback narration")
    for t in turns:
        if t.get("used_fallback"):
            notes.append(f"hard: turn {t.get('n')} used fallback ({(t.get('fallback_reason') or '')[:100]})")
        if t.get("error"):
            notes.append(f"hard: turn {t.get('n')} error: {t.get('error')}")
        narr = str(t.get("narration") or "")
        if t.get("narr_len", 0) and t["narr_len"] < 400:
            notes.append(f"soft: turn {t.get('n')} short narration ({t['narr_len']} chars)")
        if t.get("narr_len", 0) > 3500:
            notes.append(f"soft: turn {t.get('n')} very long narration ({t['narr_len']} chars)")
    # Ability origin vs list
    origin = str(setup.get("special_ability_origin") or "none")
    abs_list = setup.get("special_abilities") if isinstance(setup.get("special_abilities"), list) else []
    if origin == "none" and abs_list:
        notes.append("hard: origin none but abilities present in setup summary")
    if origin != "none" and not abs_list:
        notes.append("soft: origin non-none but zero abilities after randomize")
    # Backstory isekai vs mode
    mode = str(setup.get("backstory_mode") or "").lower()
    if "reincarn" in mode or "transmigr" in mode:
        if not any(w in backstory for w in ("died", "death", "woke", "another world", "former", "reincarn", "transmigr")):
            notes.append("soft: reincarn/transmigr mode but backstory lacks arrival/death cues")
    # World leakage into unrelated fields (slogan paste)
    if world and len(world) > 8:
        for key in ("economy", "quest_style", "faction_pressure"):
            val = str(setup.get(key) or "").lower()
            if "compound" in val or "near-useless" in val or "one-skill" in val:
                notes.append(f"hard: growth slogan leaked into {key}: {val[:80]}")
    # Continuity: location drift without travel intent
    locs = [str(t.get("location") or "") for t in turns if t.get("location")]
    if len(set(locs)) > 3:
        notes.append(f"soft: many location changes across {len(locs)} turns: {locs}")
    return notes


def _play_quality(report: dict) -> dict:
    turns = report.get("turns") or []
    open_ok = not (report.get("opening") or {}).get("used_fallback") and not (report.get("opening") or {}).get("error")
    turn_ok = sum(1 for t in turns if not t.get("error") and not t.get("used_fallback"))
    narr_lens = [t.get("narr_len") or 0 for t in turns if not t.get("error")]
    avg_len = round(sum(narr_lens) / len(narr_lens), 1) if narr_lens else 0
    hard = sum(1 for n in report.get("coherence_notes") or [] if n.startswith("hard:"))
    soft = sum(1 for n in report.get("coherence_notes") or [] if n.startswith("soft:"))
    rand_errs = sum(1 for r in report.get("randomize") or [] if r.get("error"))
    rand_n = len(report.get("randomize") or [])
    return {
        "opening_ok": open_ok,
        "turns_ok": f"{turn_ok}/{len(turns)}",
        "avg_turn_narr_chars": avg_len,
        "randomize_errors": f"{rand_errs}/{rand_n}",
        "hard_issues": hard,
        "soft_issues": soft,
        "verdict": (
            "solid"
            if open_ok and turn_ok == len(turns) and hard == 0
            else "playable_with_issues"
            if open_ok and turn_ok >= max(1, len(turns) - 1)
            else "weak"
        ),
    }


def _write(report: dict, stamp: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"full-random-play-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    return path


if __name__ == "__main__":
    sys.exit(main())
