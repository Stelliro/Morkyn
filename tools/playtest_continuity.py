"""
Live 7B probe for turn-to-turn continuity: movement, narrative voice, NPC names.

The 30-turn baseline that motivated these fixes recorded zero MOVE ops across
eight travel actions, 11/30 narrations in third person, and an NPC stored under
the literal name "Woman". This harness measures all three against a live model,
alongside the story-health numbers (length, pacing, fallbacks) so a continuity
fix that quietly flattened the prose would still show up.

    python tools/playtest_continuity.py

Env:
    PLAYTEST_OLLAMA_MODEL   default qwen2.5:7b-instruct
    PLAYTEST_TURNS          default 24
    OLLAMA_BASE_URL         default http://127.0.0.1:11434
    PLAYTEST_OUT            optional path for the JSON report
"""
from __future__ import annotations

import json
import os
import re
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Deliberately travel-heavy relative to the old probe: movement is the thing
# under test, and the baseline never moved once. Still mixed, so a length or
# quality regression from the extra constraints would show.
ACTIONS = [
    "I look around and ask a nearby merchant what trouble has been happening lately.",
    "I check my pack, then head for the east road out of town.",
    "I keep walking east, watching the treeline for movement.",
    "I search the roadside for anything a traveler might have dropped.",
    "I follow the road north toward the next settlement.",
    "I ask the nearest person what they know about the old ruins.",
    "I make camp off the road and rest until first light.",
    "I go inside the nearest building and look for whoever is in charge.",
    "I try to barter for supplies with whatever I am carrying.",
    "I inspect the strange markings on the stones nearby.",
    "I leave and take the track down toward the water.",
    "I listen at the door before going any further.",
]

# Endings that hand the turn back to the player instead of resolving their action.
# The dominant cause of travel turns that never travelled: the model closes with
# "Do you approach the figure, or continue toward the ruins? The choice is yours."
MENU_ENDING_RE = re.compile(
    # Two menu shapes, kept tight so the number stays trustworthy:
    #   1. a direct question back to the player ("Or do you continue...?")
    #   2. an explicit either/or of *actions*, needing could/might on both sides
    # "You could use the map to navigate better or find hidden treasures" is a
    # description of value, not two offered actions, and must not count.
    r"(the\s+choice\s+is\s+yours"
    r"|what\s+(?:will|do)\s+you\s+do"
    r"|(?:or[,]?\s+)?do\s+you\s+(?:approach|continue|go|take|head|push|turn|follow|"
    r"enter|stay|wait|choose|press|seek|leave|return)\b[^.?!]{0,200}\?"
    r"|you\s+(?:could|might)\s+(?:either\s+)?[^.?!]{0,120}?\bor\s+(?:you\s+)?"
    r"(?:could|might|can)\b[^.?!]{0,120}[.?!]"
    r"|which\s+(?:path|way)\s+(?:will|do)\s+you)",
    re.I,
)

# Anything whose whole name is a description rather than a person.
GENERIC_NAME_RE = re.compile(
    r"^(the\s+|a\s+|an\s+)?((old|young|tall|short|hooded|cloaked|masked|grizzled|"
    r"scarred|mysterious|strange|nameless|unknown|armed|armored)\s+)*"
    r"(man|woman|boy|girl|person|figure|stranger|guard|merchant|soldier|villager|"
    r"traveler|traveller|local|elder|youth|newcomer|bystander|passerby)$",
    re.I,
)


def _unquoted(text: str) -> str:
    """
    Strip quoted dialogue before menu detection.

    An NPC asking "Could you trade for those maps?" is a character speaking —
    good writing, not the narrator handing the turn back. Counting it inflated
    the menu rate by two turns in twenty-four.
    """
    return re.sub(r"[“\"][^”\"]{0,400}[”\"]", " ", str(text or ""))


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


def _ops_emitted(trace: dict | None) -> list[str]:
    """
    Opcodes the model actually wrote, read from raw draft output only.

    Scanning the whole trace file counts the prompt's own opcode list and the
    server's post-roll turn object, which inflates every census.
    """
    if not trace:
        return []
    ops: list[str] = []
    for entry in trace.get("model_trace") or []:
        if not isinstance(entry, dict) or entry.get("phase") not in ("draft", "draft_dsl"):
            continue
        raw = str(entry.get("raw_content") or "")
        if not raw:
            continue
        _, _, ops_block = raw.partition("===OPS===")
        for line in (ops_block or "").splitlines():
            token = line.strip().split(" ")[0].strip()
            if token and token.isupper() and token.isalpha() or (token and re.fullmatch(r"[A-Z_]+", token)):
                ops.append(token)
    return ops


def _trend(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(values) / n
    denom = sum((x - mx) ** 2 for x in xs)
    return 0.0 if not denom else sum((xs[i] - mx) * (values[i] - my) for i in range(n)) / denom


def main() -> int:
    model = os.getenv("PLAYTEST_OLLAMA_MODEL", "qwen2.5:7b-instruct")
    turns = int(os.getenv("PLAYTEST_TURNS", "24"))
    temp = Path(tempfile.mkdtemp(prefix="morkyn_continuity_"))
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
        "AI_RPG_MODEL_TRACE_KEEP": str(turns + 10),
    }.items():
        os.environ[key] = val
    (temp / "source_index").mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT))

    from app.db import connect, init_db
    from app.llm import update_model_config
    from app.world import get_state, play_turn, start_playthrough_with_opening, travel_intent

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": model,
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
    print(f"\nopening   : {len(_narration_of(opening, state))} chars in {time.perf_counter() - t0:.1f}s", flush=True)

    print(
        f"\n{'turn':>4} {'chars':>6} {'sec':>6} {'loc':>4} {'movement':>12} "
        f"{'2p':>3} {'drift':>5} {'fb':>3}  action",
        flush=True,
    )

    for i in range(turns):
        action = ACTIONS[i % len(ACTIONS)]
        t0 = time.perf_counter()
        try:
            result = play_turn(action)
        except Exception as exc:
            print(f"{i + 1:>4} EXCEPTION {type(exc).__name__}: {exc}", flush=True)
            rows.append({"turn": i + 1, "action": action, "error": f"{type(exc).__name__}: {exc}"})
            continue
        elapsed = time.perf_counter() - t0
        state = get_state(include_hidden=True)
        narration = _narration_of(result, state)
        movement = result.get("movement") or {}
        voice = result.get("voice_check") or {}
        db_turn = int(state.get("turn") or 0)
        ops = _ops_emitted(_trace_for_turn(trace_dir, db_turn))

        with connect() as conn:
            loc_count = int(conn.execute("SELECT COUNT(*) AS n FROM locations").fetchone()["n"] or 0)
            here = conn.execute(
                "SELECT l.code, l.name FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
            ).fetchone()

        rows.append(
            {
                "turn": i + 1,
                "db_turn": db_turn,
                "action": action,
                "chars": len(narration),
                "seconds": round(elapsed, 1),
                "fallback": bool(result.get("used_fallback")),
                "travel_action": travel_intent(action),
                "movement_status": movement.get("status"),
                "movement_rule": movement.get("rule"),
                "movement_dest": movement.get("destination"),
                "prose_mismatch": movement.get("prose_mismatch"),
                "location_code": here["code"] if here else "",
                "location_name": here["name"] if here else "",
                "location_count": loc_count,
                "voice_drift": bool(voice.get("drift")),
                "second_person_refs": int(voice.get("second_person_refs") or 0),
                "name_as_subject": int(voice.get("player_name_as_subject") or 0),
                "pronoun_mix": voice.get("pronoun_mix") or {},
                "ops": ops,
                "menu_ending": bool(MENU_ENDING_RE.search(_unquoted(narration)[-500:])),
                "narration": narration,
            }
        )
        print(
            f"{i + 1:>4} {len(narration):>6} {elapsed:>6.1f} {(here['code'] if here else '?'):>4} "
            f"{str(movement.get('status') or '-'):>12} {int(voice.get('second_person_refs') or 0):>3} "
            f"{('Y' if voice.get('drift') else '.'):>5} {str(bool(result.get('used_fallback')))[:1]:>3}  {action[:40]}",
            flush=True,
        )

    total_time = time.perf_counter() - started
    ok = [r for r in rows if not r.get("error")]

    # ------------------------------------------------------------------ report
    print("\n" + "=" * 70)
    print("STORY HEALTH")
    print("=" * 70)
    chars = [float(r["chars"]) for r in ok]
    secs = [float(r["seconds"]) for r in ok]
    if chars:
        below = sum(1 for c in chars if c < 1000)
        print(f"narration chars  min/median/max : {min(chars):.0f} / {statistics.median(chars):.0f} / {max(chars):.0f}")
        print(f"below 1000-char floor           : {below}/{len(chars)} ({100.0 * below / len(chars):.0f}%)")
        print(f"length trend                    : {_trend(chars):+.1f} chars/turn")
        print(f"mean turn time                  : {statistics.fmean(secs):.1f}s   total {total_time / 60:.1f} min")
    print(f"fallbacks / exceptions          : {sum(1 for r in ok if r['fallback'])} / {len(rows) - len(ok)}")
    menus = [r for r in ok if r["menu_ending"]]
    print(f"turns ending in a choice menu   : {len(menus)}/{len(ok)} "
          f"({100.0 * len(menus) / max(1, len(ok)):.0f}%)   <- hands the turn back unplayed")

    print("\n" + "=" * 70)
    print("MOVEMENT  (baseline: 0 MOVE ops, 1 location, 8 travel turns wasted)")
    print("=" * 70)
    travel_rows = [r for r in ok if r["travel_action"]]
    status_counts = Counter(r["movement_status"] for r in travel_rows)
    rule_counts = Counter(r["movement_rule"] for r in travel_rows if r.get("movement_rule"))
    move_ops = sum(r["ops"].count("MOVE") for r in ok)
    locnew_ops = sum(r["ops"].count("LOC_NEW") for r in ok)
    print(f"travel turns                    : {len(travel_rows)}/{len(ok)}")
    print(f"model emitted MOVE / LOC_NEW    : {move_ops} / {locnew_ops}")
    for status in ("model", "repaired", "unresolved"):
        print(f"  {status:28s}: {status_counts.get(status, 0)}")
    if rule_counts:
        print(f"  repair rules used             : {dict(rule_counts)}")
    resolved = status_counts.get("model", 0) + status_counts.get("repaired", 0)
    if travel_rows:
        print(f"travel turns that moved         : {resolved}/{len(travel_rows)} "
              f"({100.0 * resolved / len(travel_rows):.0f}%)")
    false_moves = [r for r in ok if not r["travel_action"] and r["movement_status"] in ("repaired",)]
    print(f"non-travel turns wrongly moved  : {len(false_moves)}")
    mismatch = [r for r in ok if r.get("prose_mismatch")]
    print(f"destination never named in prose: {len(mismatch)}   "
          f"{[ (r['turn'], r['prose_mismatch']) for r in mismatch ]}")
    with connect() as conn:
        locs = conn.execute("SELECT code, name, visit_count FROM locations ORDER BY id").fetchall()
    print(f"locations in world              : {len(locs)}")
    for loc in locs:
        print(f"    {loc['code']:<5} {loc['name'][:34]:<34} visits={loc['visit_count']}")

    print("\n" + "=" * 70)
    print("NARRATIVE VOICE  (baseline: 11/30 third person, 21 he vs 12 she)")
    print("=" * 70)
    drift = [r for r in ok if r["voice_drift"]]
    subj = sum(r["name_as_subject"] for r in ok)
    mix = Counter()
    for r in ok:
        for key, val in (r["pronoun_mix"] or {}).items():
            mix[key] += int(val or 0)
    print(f"turns with person drift         : {len(drift)}/{len(ok)}")
    print(f"player name used as subject     : {subj}")
    print(f"mean 'you/your' per turn        : "
          f"{statistics.fmean([r['second_person_refs'] for r in ok]) if ok else 0:.1f}")
    print(f"pronoun totals across run       : {dict(mix)}")

    print("\n" + "=" * 70)
    print("NPC NAMES  (baseline: one NPC literally named 'Woman')")
    print("=" * 70)
    with connect() as conn:
        npcs = conn.execute("SELECT code, name, role FROM npcs ORDER BY id").fetchall()
    generic = [n for n in npcs if GENERIC_NAME_RE.match(str(n["name"] or "").strip())]
    roles = Counter(str(n["role"] or "").strip().lower() for n in npcs)
    appearance_roles = [r for r in roles if any(
        w in r for w in ("hooded", "cloaked", "masked", "robed", "veiled", "stranger", "figure")
    )]
    print(f"npcs created                    : {len(npcs)}")
    print(f"description-only names          : {len(generic)}")
    print(f"distinct roles                  : {len(roles)}/{len(npcs)}   "
          f"most common: {roles.most_common(3)}")
    print(f"appearance-as-role              : {sum(roles[r] for r in appearance_roles)}   {appearance_roles}")
    for npc in npcs:
        flag = "  <-- GENERIC" if npc in generic else ""
        print(f"    {npc['code']:<4} {str(npc['name'])[:26]:<26} {str(npc['role'])[:20]:<20}{flag}")

    print("\n" + "=" * 70)
    print("OPCODE CENSUS  (model-emitted only)")
    print("=" * 70)
    census = Counter()
    for r in ok:
        census.update(r["ops"])
    for op, n in census.most_common(18):
        print(f"    {op:<12} {n}")

    out_path = Path(os.getenv("PLAYTEST_OUT", temp / "continuity_report.json"))
    out_path.write_text(
        json.dumps(
            {
                "model": model,
                "turns": turns,
                "workspace": str(temp),
                "rows": rows,
                "locations": [dict(l) for l in locs],
                "npcs": [dict(n) for n in npcs],
                "opcode_census": dict(census),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    print(f"\nreport: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
