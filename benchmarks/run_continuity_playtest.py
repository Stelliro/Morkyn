"""
benchmarks — long-run CONTINUITY playtest against a local model.

`run_long_playtest.py` answers "does it survive 100 turns?". This one answers
"does it still know who it is on turn 100?" — memory, identity stability, and
whether the narration stays anchored to what actually happened.

The method is planted facts, not vibes. At known turns the *player* asserts a
specific, checkable detail ("the letter is addressed to Corvin Marrow"). Much
later, another turn asks for that detail back. Recall is then a string test
against the narration, not a judgement call. Everything else is measured off
the database and the journal, so no scoring depends on a second model.

What it reports:
  recall        planted facts recovered on probe turns, by distance in turns
  identity      NPC code -> name flips, and player name/location drift
  grounding     narration that claims a state change SQLite did not record
  repetition    trigram overlap against recent turns (loop detection)
  voice         second-person rate, narration length drift
  health        fallback rate, self-check pass rate, latency and context growth

Run from repo root (Ollama must be running):
  python benchmarks/run_continuity_playtest.py

Env:
  CONTINUITY_TURNS      default 100
  CONTINUITY_MODEL      default qwen3:8b (or OLLAMA_MODEL)
  OLLAMA_BASE_URL       default http://127.0.0.1:11434
  CONTINUITY_ABORT      consecutive hard failures before abort (default 6)

Deliberately does NOT pin OLLAMA_CONTEXT_TOKENS: this run should reflect the
context a real player gets from the shipped default.
"""
from __future__ import annotations

import json
import os
import re
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
    try:
        return int(str(raw).strip()) if raw and str(raw).strip() else default
    except ValueError:
        return default


# --------------------------------------------------------------------------
# Planted facts. Each is asserted by the player on `plant_turn`, then asked for
# again on every turn in `probe_turns`. `tokens` are what recall looks like in
# the narration; `any_of` groups count as recalled when any member appears.
# --------------------------------------------------------------------------
FACTS: list[dict] = [
    {
        "id": "letter",
        "plant_turn": 2,
        "plant": (
            "I say my name aloud so it is heard: Ash Vale. I explain that I carry a sealed "
            "letter addressed to a man named Corvin Marrow, and that it must not be opened."
        ),
        "probe_turns": [26, 58, 94],
        "probe": (
            "I take out the sealed letter and read the name written on it aloud, "
            "so there is no confusion about who it is for."
        ),
        "tokens": ["Corvin Marrow", "Corvin"],
    },
    {
        "id": "ribbon",
        "plant_turn": 6,
        "plant": (
            "I tie a red ribbon around my left wrist and explain that it is a keepsake "
            "from my sister Neve, who I have not seen in years."
        ),
        "probe_turns": [34, 70],
        "probe": (
            "Someone notices what is tied around my left wrist and asks about it. "
            "I tell them exactly what it is and who it came from."
        ),
        "tokens": ["Neve", "red ribbon", "ribbon"],
    },
    {
        "id": "token",
        "plant_turn": 11,
        "plant": (
            "I bury a copper token beneath the third stone from the doorway here, "
            "and I fix the spot in my memory so I can find it again."
        ),
        "probe_turns": [47, 82],
        "probe": (
            "I go back to the place where I buried the copper token, count the stones "
            "from the doorway, and dig it up."
        ),
        "tokens": ["copper token", "copper", "third stone"],
    },
    {
        "id": "debt",
        "plant_turn": 17,
        "plant": (
            "I admit out loud that I owe eleven silver to a lender called Hask, "
            "and that the debt comes due at the next full moon."
        ),
        "probe_turns": [55, 88],
        "probe": "I am asked what debts I carry. I answer honestly: who I owe, how much, and when.",
        "tokens": ["Hask", "eleven silver", "eleven"],
    },
    {
        "id": "fear",
        "plant_turn": 23,
        "plant": "I confess that I am deathly afraid of deep water and have never learned to swim.",
        "probe_turns": [66, 97],
        "probe": (
            "Someone suggests crossing deep water. I explain why that is a problem for me "
            "in particular."
        ),
        "tokens": ["swim", "water", "afraid"],
    },
]

# Filler actions between plants and probes. Deliberately generic so they work in
# any location the model invents, and varied so repetition is the model's doing.
#
# The first version of this list produced a world of five locations across 100
# turns and read like a movement bug. It was not: 86% of travel-intent turns did
# move the player. The script simply never asked to go anywhere -- "walk a short
# way along the most promising path" correctly yields a short local step. The
# committed travel lines are explicit about leaving, so world growth is actually
# exercised instead of merely hoped for.
FILLER = [
    "I survey where I am, noting exits, cover, and who is watching me.",
    "I ask someone nearby what trouble has been happening here lately.",
    "I count what I am carrying and secure anything valuable.",
    "I listen for rumors about the roads, debts, or sealed letters.",
    "I take the road out of here and travel until the country changes.",
    "I look for honest work a courier could take.",
    "I read any posted notice or mark and commit one detail to memory.",
    "I rest a while somewhere safer and watch the crowd.",
    "I try to learn one useful name or place connected to my errand.",
    "I follow the road onward to the next settlement and do not turn back.",
    "I approach the nearest person politely and introduce myself.",
    "I examine something here that does not quite belong.",
    "I ask directions toward the next settlement along my route.",
    "I leave this place behind and walk on until I reach somewhere new.",
    "I take stock of my injuries and how tired I am.",
    "I trade a small courtesy for a piece of local news.",
]


def _action_for(turn: int) -> tuple[str, str, str]:
    """Return (action, kind, fact_id) for this turn."""
    for fact in FACTS:
        if turn == fact["plant_turn"]:
            return fact["plant"], "plant", fact["id"]
        if turn in fact["probe_turns"]:
            return fact["probe"], "probe", fact["id"]
    return FILLER[turn % len(FILLER)], "filler", ""


# --------------------------------------------------------------------------
# Measurement helpers
# --------------------------------------------------------------------------
_WORD_RE = re.compile(r"[a-z0-9']+")


def _trigrams(text: str) -> set[tuple[str, str, str]]:
    words = _WORD_RE.findall(str(text or "").lower())
    return {tuple(words[i : i + 3]) for i in range(max(0, len(words) - 2))}


def _overlap(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _second_person_rate(text: str) -> float:
    words = _WORD_RE.findall(str(text or "").lower())
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in {"you", "your", "yours", "yourself"})
    return hits / len(words)


# Prose that claims the player acquired something.
#
# A loose /you (take|pick up|receive)/ is useless here: English is full of
# "you take a slow breath", "you take stock", "you take in your surroundings",
# and "you take out the letter you already carry". A first pass flagged 15 of
# 100 turns and every single one was an idiom. So: acquisition-only verbs, or
# take/accept with a determiner and a concrete object noun.
_GAIN_RE = re.compile(
    r"\byou\s+(?:pick up|picks up|pockets?|are handed|now carry|receives?)\b"
    r"|\byou\s+(?:accepts?|takes?)\s+(?:the|a|an|his|her|their)\s+"
    r"(?!slow\b|deep\b|steady\b|long\b|careful\b|moment\b|step\b|breath\b|stock\b)"
    r"(?:[a-z\-]+\s+){0,2}?(?:letter|coin|token|blade|knife|purse|pouch|bundle|ration|rope|"
    r"lantern|cloak|ring|key|map|parcel|package|charm|amulet|flask|waterskin|bread|silver|"
    r"copper|gold)\b",
    re.I,
)

_NPC_REF_RE = re.compile(r"([A-Z][a-z]+)\s*\[\[([A-Z]{1,3})\]\]")
_PRONOUN_RE = re.compile(r"\b(he|him|his|she|her|hers|they|them|their)\b", re.I)
_MASC = {"he", "him", "his"}
_FEM = {"she", "her", "hers"}


def _pronoun_consistency(narrations: list[str]) -> dict:
    """Per-NPC pronoun usage, counted only in sentences naming exactly one NPC.

    Windowing "N characters after the name" produces nonsense as soon as two
    characters share a paragraph, so restrict to unambiguous sentences.
    """
    from collections import Counter, defaultdict

    per: dict[str, Counter] = defaultdict(Counter)
    for text in narrations:
        for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
            found = _NPC_REF_RE.findall(sentence)
            if len(found) != 1:
                continue
            who = f"{found[0][0]}[{found[0][1]}]"
            for pronoun in _PRONOUN_RE.findall(sentence):
                per[who][pronoun.lower()] += 1

    gender_flips, register_mixes, detail = 0, 0, []
    for who, counts in per.items():
        masc = sum(counts[p] for p in _MASC)
        fem = sum(counts[p] for p in _FEM)
        neutral = sum(counts[p] for p in ("they", "them", "their"))
        if masc and fem:
            gender_flips += 1
        elif (masc or fem) and neutral:
            register_mixes += 1
        if masc or fem or neutral:
            detail.append({"npc": who, "masc": masc, "fem": fem, "neutral": neutral})
    detail.sort(key=lambda d: -(d["masc"] + d["fem"] + d["neutral"]))
    return {
        "npc_gender_flips": gender_flips,
        "npc_register_mixes": register_mixes,
        "pronoun_detail": detail[:8],
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


def _npc_map(state: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for loc in state.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        for npc in loc.get("npcs") or []:
            if isinstance(npc, dict) and npc.get("code"):
                out[str(npc["code"]).upper()] = str(npc.get("name") or "")
    for npc in state.get("npcs") or []:
        if isinstance(npc, dict) and npc.get("code"):
            out.setdefault(str(npc["code"]).upper(), str(npc.get("name") or ""))
    return out


def _inventory_names(state: dict) -> set[str]:
    return {
        str(i.get("name") or "").strip().lower()
        for i in (state.get("inventory") or [])
        if isinstance(i, dict) and i.get("name")
    }


def _log(handle, line: str) -> None:
    print(line, flush=True)
    handle.write(line + "\n")
    handle.flush()


def main() -> int:
    target = _env_int("CONTINUITY_TURNS", 100)
    abort_after = _env_int("CONTINUITY_ABORT", 6)
    model = os.getenv("CONTINUITY_MODEL") or os.getenv("OLLAMA_MODEL") or "qwen3:8b"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    live_log = REPORT_DIR / f"continuity-{stamp}.log"
    jsonl_path = REPORT_DIR / f"continuity-turns-{stamp}.jsonl"
    report_path = REPORT_DIR / f"continuity-report-{stamp}.json"

    temp = Path(tempfile.mkdtemp(prefix="morkyn_continuity_"))
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
        "OLLAMA_THINK": os.getenv("OLLAMA_THINK", "0"),
        "AI_RPG_OLLAMA_TIMEOUT": os.getenv("AI_RPG_OLLAMA_TIMEOUT", "900"),
        "AI_RPG_TURN_DRAFT_TIMEOUT": os.getenv("AI_RPG_TURN_DRAFT_TIMEOUT", "900"),
        "AI_RPG_TURN_VERIFY_TIMEOUT": os.getenv("AI_RPG_TURN_VERIFY_TIMEOUT", "600"),
    }.items():
        os.environ[key] = val
    for sub in ("source_index", "traces", "slots", "packs"):
        (temp / sub).mkdir(exist_ok=True)

    sys.path.insert(0, str(REPO_ROOT))

    from app import llm  # noqa: E402
    from app.db import connect, init_db  # noqa: E402
    from app.llm import update_model_config  # noqa: E402
    from app.world import get_state, play_turn, start_playthrough_with_opening  # noqa: E402

    setup = {
        "player_name": "Ash Vale",
        "player_sex": "unspecified",
        "backstory_mode": "known",
        "character_backstory": (
            "A courier on the long roads, carrying a sealed letter and older debts."
        ),
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

    init_db()
    update_model_config(
        {
            "provider": "ollama",
            "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
            "ollama_model": model,
            "response_token_cap": 1200,
            "response_token_hard_cap": 1600,
        }
    )

    context_window = llm.context_window_tokens()
    system_prompt, _verify, degraded = llm.fitting_system_prompts({"provider": "ollama"})

    report: dict = {
        "benchmark": "continuity",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "target_turns": target,
        "context_window": context_window,
        "system_contract_tokens": llm.estimated_tokens(system_prompt),
        "contract_degraded": degraded,
        "temp_dir": str(temp),
        "facts": [{k: v for k, v in f.items() if k != "plant"} for f in FACTS],
        "turns": [],
        "summary": {},
    }

    log = live_log.open("w", encoding="utf-8")
    jsonl = jsonl_path.open("w", encoding="utf-8")

    _log(log, "=" * 72)
    _log(log, f" continuity playtest  model={model}  turns={target}")
    _log(log, f" context_window={context_window}  contract={report['system_contract_tokens']} tok"
              f"  degraded={degraded}")
    _log(log, f" workspace={temp}")
    _log(log, "=" * 72)

    t_run = time.perf_counter()
    start_playthrough_with_opening(setup)
    state = get_state(include_hidden=True)
    opening = _narration_of({}, state)
    _log(log, f"opening: {len(opening)} chars at {(state.get('current_location') or {}).get('name')!r}")

    narrations: list[str] = []
    npc_names_seen: dict[str, set[str]] = {}
    identity_flips: list[dict] = []
    locations: list[str] = []
    ungrounded_gains: list[int] = []
    fallback_count = 0
    error_count = 0
    consecutive_fails = 0
    recall_results: list[dict] = []

    prev_inventory = _inventory_names(state)

    for turn in range(1, target + 1):
        action, kind, fact_id = _action_for(turn)
        t1 = time.perf_counter()
        err = None
        payload: dict = {}
        try:
            payload = play_turn(action)
        except Exception as exc:  # noqa: BLE001 - benchmark must survive any turn
            err = f"{type(exc).__name__}: {exc}"
            _log(log, "ERROR " + err)
            _log(log, traceback.format_exc(limit=3))
        elapsed = time.perf_counter() - t1

        state = get_state(include_hidden=True)
        narration = _narration_of(payload, state)
        here = str((state.get("current_location") or {}).get("name") or "")
        locations.append(here)

        # --- identity stability -------------------------------------------
        for code, name in _npc_map(state).items():
            if not name:
                continue
            seen = npc_names_seen.setdefault(code, set())
            if seen and name not in seen:
                identity_flips.append({"turn": turn, "code": code, "was": sorted(seen), "now": name})
            seen.add(name)

        # --- grounding: prose claims a pickup, inventory did not move ------
        inventory_now = _inventory_names(state)
        if _GAIN_RE.search(narration) and inventory_now == prev_inventory:
            ungrounded_gains.append(turn)
        prev_inventory = inventory_now

        # --- repetition against the last 5 turns ---------------------------
        recent = narrations[-5:]
        max_overlap = max((_overlap(narration, prev) for prev in recent), default=0.0)

        used_fallback = bool(payload.get("used_fallback")) if isinstance(payload, dict) else False
        if used_fallback:
            fallback_count += 1
        if err:
            error_count += 1

        # --- recall scoring on probe turns ---------------------------------
        recall_row = None
        if kind == "probe":
            fact = next(f for f in FACTS if f["id"] == fact_id)
            low = narration.lower()
            hits = [t for t in fact["tokens"] if t.lower() in low]
            recall_row = {
                "turn": turn,
                "fact": fact_id,
                "planted_turn": fact["plant_turn"],
                "distance": turn - fact["plant_turn"],
                "recalled": bool(hits),
                "exact": fact["tokens"][0].lower() in low,
                "hits": hits,
                "narration": narration,
            }
            recall_results.append(recall_row)

        narrations.append(narration)

        row = {
            "turn": turn,
            "kind": kind,
            "fact": fact_id,
            "action": action,
            "seconds": round(elapsed, 2),
            "error": err,
            "used_fallback": used_fallback,
            "location": here,
            "narration_len": len(narration),
            "narration": narration,
            "second_person_rate": round(_second_person_rate(narration), 4),
            "max_overlap_recent": round(max_overlap, 4),
            "inventory_count": len(state.get("inventory") or []),
            "npc_count": len(_npc_map(state)),
            "turn_summaries": len(state.get("turn_summaries") or []),
            "player_level": (state.get("player") or {}).get("level"),
            "player_gold": (state.get("player") or {}).get("gold"),
            # Naming authority: which name answered, from where, and whether the
            # prose had to be repaired to say it.
            "naming": (payload or {}).get("naming") or {},
            # Remembered specifics the prose owed this turn, and whether it said
            # them. Distinct from "recall" below, which is the planted-fact probe.
            "recall_contract": (payload or {}).get("recall") or {},
        }
        if recall_row:
            row["recall"] = {k: v for k, v in recall_row.items() if k != "narration"}
        report["turns"].append(row)
        jsonl.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
        jsonl.flush()

        hard_fail = bool(err) or len(narration) < 40
        consecutive_fails = consecutive_fails + 1 if hard_fail else 0

        mean = (time.perf_counter() - t_run) / turn
        eta = mean * (target - turn)
        marker = {"plant": "PLANT", "probe": "PROBE", "filler": "     "}[kind]
        _log(
            log,
            f"[{turn:3d}/{target}] {marker} {elapsed:5.1f}s  loc={here[:22]:22s} "
            f"npc={row['npc_count']:2d} inv={row['inventory_count']:2d} "
            f"rep={max_overlap:.2f} len={row['narration_len']:4d} "
            f"fb={int(used_fallback)} eta~{eta/60:.0f}m",
        )
        if recall_row:
            verdict = "RECALLED" if recall_row["recalled"] else "FORGOTTEN"
            _log(log, f"          -> {fact_id} planted t{recall_row['planted_turn']} "
                      f"(+{recall_row['distance']}): {verdict} {recall_row['hits']}")

        if turn % 5 == 0 or turn == target:
            report["summary"] = _summarize(
                report, narrations, locations, identity_flips, ungrounded_gains,
                recall_results, fallback_count, error_count, t_run, turn, target,
            )
            report_path.write_text(
                json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8"
            )

        if consecutive_fails >= abort_after:
            _log(log, f"ABORT: {consecutive_fails} consecutive hard failures")
            break

    # --- final journal-side checks -----------------------------------------
    with connect() as conn:
        self_checks = [
            str(r[0]) for r in conn.execute("SELECT content FROM journal WHERE kind='self_check'")
        ]
        journal_total = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        npc_rows = [dict(r) for r in conn.execute("SELECT name, pronouns FROM npcs")]
        ledger_rows = [
            dict(r) for r in conn.execute("SELECT subject, name, source FROM name_ledger")
        ]
    passed = sum(1 for c in self_checks if '"passed": true' in c.lower())

    summary = _summarize(
        report, narrations, locations, identity_flips, ungrounded_gains,
        recall_results, fallback_count, error_count, t_run, len(narrations), target,
    )
    summary.update(_pronoun_consistency(narrations))
    naming_turns = [t for t in report["turns"] if (t.get("naming") or {}).get("name")]
    summary["naming_demands"] = len(naming_turns)
    summary["naming_repaired"] = sum(1 for t in naming_turns if (t["naming"] or {}).get("repaired"))
    summary["naming_from_history_or_ledger"] = sum(
        1 for t in naming_turns if (t["naming"] or {}).get("source") in {"history", "ledger", "player"}
    )
    summary["naming_minted"] = sum(1 for t in naming_turns if (t["naming"] or {}).get("source") == "minted")
    recall_turns = [t for t in report["turns"] if (t.get("recall_contract") or {}).get("required")]
    summary["recall_contracts"] = len(recall_turns)
    summary["recall_specifics_stated"] = sum(
        1 for t in recall_turns if (t["recall_contract"] or {}).get("stated")
    )
    summary["recall_specifics_missing"] = sum(
        1 for t in recall_turns if (t["recall_contract"] or {}).get("missing")
    )
    summary["npcs_total"] = len(npc_rows)
    summary["npcs_pronouns_pinned"] = sum(1 for n in npc_rows if str(n.get("pronouns") or "").strip())
    summary["name_ledger"] = ledger_rows[:10]
    summary["self_check_rows"] = len(self_checks)
    summary["self_check_passed"] = passed
    summary["journal_rows"] = journal_total
    report["summary"] = summary
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

    _log(log, "\n" + "=" * 72)
    _log(log, " RESULT")
    _log(log, "=" * 72)
    for key, val in summary.items():
        _log(log, f"  {key:26s} {val}")
    _log(log, "\n  recall detail:")
    for r in recall_results:
        _log(log, f"    t{r['turn']:3d} {r['fact']:8s} +{r['distance']:3d} turns  "
                  f"{'RECALLED' if r['recalled'] else 'FORGOTTEN':9s} {r['hits']}")
    _log(log, f"\n  report : {report_path}")
    _log(log, f"  turns  : {jsonl_path}")

    log.close()
    jsonl.close()
    return 0


def _summarize(report, narrations, locations, identity_flips, ungrounded_gains,
               recall_results, fallback_count, error_count, t_run, done, target) -> dict:
    overlaps = [t["max_overlap_recent"] for t in report["turns"]]
    lengths = [t["narration_len"] for t in report["turns"]]
    seconds = [t["seconds"] for t in report["turns"]]
    sp = [t["second_person_rate"] for t in report["turns"]]
    half = max(1, len(seconds) // 2)
    recalled = sum(1 for r in recall_results if r["recalled"])
    return {
        "completed_turns": done,
        "target_turns": target,
        "elapsed_minutes": round((time.perf_counter() - t_run) / 60, 1),
        "fallback_turns": fallback_count,
        "error_turns": error_count,
        "recall_probes": len(recall_results),
        "recall_hits": recalled,
        "recall_rate": round(recalled / len(recall_results), 3) if recall_results else None,
        "npc_identity_flips": len(identity_flips),
        "identity_flip_detail": identity_flips[:10],
        "ungrounded_pickup_turns": len(ungrounded_gains),
        "distinct_locations": len(set(locations)),
        "location_changes": sum(1 for a, b in zip(locations, locations[1:]) if a != b),
        "location_oscillations": sum(
            1 for i in range(2, len(locations))
            if locations[i] == locations[i - 2] and locations[i] != locations[i - 1]
        ),
        "mean_repetition": round(sum(overlaps) / len(overlaps), 4) if overlaps else 0,
        "max_repetition": round(max(overlaps), 4) if overlaps else 0,
        "repetition_over_0_35": sum(1 for o in overlaps if o > 0.35),
        "mean_narration_len": round(sum(lengths) / len(lengths)) if lengths else 0,
        "mean_second_person": round(sum(sp) / len(sp), 4) if sp else 0,
        "turns_without_second_person": sum(1 for r in sp if r == 0),
        "mean_seconds": round(sum(seconds) / len(seconds), 1) if seconds else 0,
        "mean_seconds_first_half": round(sum(seconds[:half]) / half, 1) if seconds else 0,
        "mean_seconds_second_half": round(sum(seconds[half:]) / max(1, len(seconds) - half), 1) if seconds else 0,
        "in_progress": done < target,
    }


if __name__ == "__main__":
    raise SystemExit(main())
