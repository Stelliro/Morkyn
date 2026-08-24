"""
benchmarks — GENRE FIDELITY and VARIETY across lore settings.

Every previous probe in this repo ran one world: "frontier dark fantasy",
same setup dict, same start location. So nothing ever asked the two questions
that matter for a game whose whole premise is "any setting you like":

  1. Does a futuristic world actually play futuristic, or does it quietly
     staff a space station with ferrymen and coopers?
  2. Are two randomized worlds different worlds, or the same world with the
     serial numbers filed off?

What it reports
---------------
  genre fidelity     out-of-genre vocabulary in the prose, per genre, with the
                     offending sentences printed so they can be read rather
                     than counted (this lexicon is a signal, not a verdict)
  seeded roles       occupations the SERVER invents for prose-only faces,
                     checked against the genre. Deterministic, no model.
  cross-genre        pairwise trigram overlap between genres. Two settings
                     that share a lot of language are the same story reskinned
  repeat runs        the same genre twice, different seeds: do names, places
                     and NPCs differ, or does it tell one story every time
  randomizer         N live randomizations: distinct values per field, and
                     near-duplicate detection across whole setups

Run from repo root (Ollama must be running):
  python benchmarks/run_genre_variety.py

Env:
  GENRE_TURNS       turns per world (default 5)
  GENRE_MODEL       default qwen3:8b (or OLLAMA_MODEL)
  GENRE_RANDOMIZE   live randomizer samples (default 6, 0 to skip)
  GENRE_ONLY        comma-separated genre ids; default all. Cross-genre overlap
                    needs at least two, and the repeat run needs its own id.
  OLLAMA_BASE_URL   default http://127.0.0.1:11434

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
from itertools import combinations
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
# The worlds under test. Each is a plausible thing a player would actually
# type, not a keyword salad, because the setup pipeline reads these as prose.
# `forbidden` is vocabulary that should not appear if the setting landed;
# `expected` is vocabulary that should.
# --------------------------------------------------------------------------
GENRES: list[dict] = [
    {
        "id": "medieval",
        "world_style": "grounded medieval realism, no magic",
        "start_location": "Aldbury Market Cross",
        "backstory": "A wool merchant's factor walking the roads between market towns.",
        "expected": ("cart", "market", "road", "coin", "inn", "horse", "field", "smith"),
        "forbidden": (
            "laser", "cyber", "android", "plasma", "starship", "spaceship", "computer",
            "neural", "reactor", "hologram", "blaster", "nanite", "terminal", "elevator",
            "radio", "engine", "circuit", "drone", "server", "datapad", "railgun",
        ),
    },
    {
        "id": "high_fantasy",
        "world_style": "high fantasy with open magic and old empires",
        "start_location": "The Sunken Colonnade",
        "backstory": "A hedge-mage carrying a debt to a spirit they cannot name.",
        "expected": ("magic", "spell", "rune", "spirit", "sigil", "ward", "arcane", "enchant"),
        "forbidden": (
            "laser", "cyber", "android", "plasma", "starship", "computer", "neural",
            "hologram", "blaster", "nanite", "datapad", "railgun", "circuit", "drone",
        ),
    },
    {
        "id": "space_opera",
        "world_style": "far-future interstellar civilisation, faster-than-light travel, no magic",
        "start_location": "Docking Bay Seven, Ceres Transfer Station",
        "backstory": "A courier running sealed data between stations, one jump ahead of a debt.",
        "expected": (
            "station", "ship", "airlock", "hull", "console", "deck", "system", "cargo",
            "orbit", "reactor", "comm", "suit",
        ),
        "forbidden": (
            "sword", "castle", "knight", "wizard", "dragon", "blacksmith", "peasant",
            "lute", "chainmail", "cobblestone", "torchlight", "sorcerer", "spellbook",
            "ferryman", "cooper", "chandler", "tanner", "scribe", "goatherd",
            "charcoal burner", "net mender", "boatwright", "wine seller", "toll keeper",
            "bargeman", "stablehand", "drover", "roofer", "eel fisher", "salt carrier",
            "woodcutter", "trapper", "peddler", "rag picker", "well keeper", "mudlark",
        ),
    },
    {
        "id": "cyberpunk",
        "world_style": "near-future cyberpunk megacity, corporate rule, street-level crime",
        "start_location": "Sublevel Four, Kowloon Stack",
        "backstory": "A courier with a cranial data shunt and a debt to the wrong clinic.",
        "expected": (
            "corp", "data", "neon", "implant", "deck", "net", "chrome", "rain",
            "screen", "credit", "signal",
        ),
        "forbidden": (
            "sword", "castle", "knight", "wizard", "dragon", "blacksmith", "peasant",
            "lute", "chainmail", "sorcerer", "spellbook", "ferryman", "cooper",
            "chandler", "goatherd", "charcoal burner", "net mender", "boatwright",
            "toll keeper", "wine seller", "bargeman", "stablehand", "drover", "roofer",
            "eel fisher", "salt carrier", "woodcutter", "trapper", "mudlark",
        ),
    },
    {
        "id": "post_apoc",
        "world_style": "post-collapse wasteland eighty years after the grid died",
        "start_location": "The Overpass Camp",
        "backstory": "A water-runner carrying a filter cartridge worth more than they are.",
        "expected": ("water", "rust", "scrap", "ruin", "camp", "filter", "dust", "salvage"),
        "forbidden": ("wizard", "dragon", "spellbook", "sorcerer", "starship", "hyperspace"),
    },
    {
        "id": "weird_west",
        "world_style": "1880s frontier west with quiet, unexplained wrongness",
        "start_location": "Calico Junction Depot",
        "backstory": "A line-rider carrying a letter nobody will sign for.",
        "expected": ("rail", "dust", "saloon", "revolver", "horse", "depot", "town", "rifle"),
        "forbidden": (
            "starship", "android", "hyperspace", "cyber", "dragon", "wizard",
            "spellbook", "chainmail", "cooper", "chandler",
        ),
    },
]

# One genre is run twice with a different seed to answer "is it the same story
# every time?". Space opera, because it is furthest from the repo's default.
REPEAT_GENRE = "space_opera"

TURN_SCRIPT = [
    "I look around and take in where I actually am.",
    "I speak to whoever is nearest and ask what work there is.",
    "I check what I am carrying.",
    "I head somewhere else in this place and see what is there.",
    "I ask about the biggest trouble around here lately.",
    "I look for a way onward and take it.",
    "I examine something here that does not belong.",
    "I introduce myself to someone new.",
]

_WORD_RE = re.compile(r"[a-z0-9']+")


def _trigrams(text: str) -> set[tuple[str, str, str]]:
    words = _WORD_RE.findall(str(text or "").lower())
    return {tuple(words[i : i + 3]) for i in range(max(0, len(words) - 2))}


def _overlap(a: str, b: str) -> float:
    ta, tb = _trigrams(a), _trigrams(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


# Ordinary English inflections, so a genre word still counts when the prose
# declines it. Substring matching is still refused -- it scores "neve" inside
# "never" -- but exact-form matching was scoring zero for real hits: a
# high-fantasy run that wrote "nothing feels particularly MAGICAL" and "the
# SPIRITS don't forgive what's owed" was recorded as 0/8 on its own vocabulary.
# Rescoring every stored report, every world gained 1-3 words and the ordering
# between runs changed, so this was not a rounding difference.
#
# "-ment" is deliberately absent: it would score "shipment" as the word "ship",
# and a space-opera log says shipment constantly while meaning cargo. The only
# expected word that wants it is "enchant", which still matches enchanted /
# enchanting / enchants -- losing the bare noun is the cheaper error.
_INFLECTIONS = r"(?:s|es|ed|ing|al|ers?)?"


def _word_present(needle: str, low_text: str) -> bool:
    """Whole-word match, allowing ordinary inflections of the same word."""
    return (
        re.search(rf"(?<![a-z]){re.escape(needle.lower())}{_INFLECTIONS}(?![a-z])", low_text)
        is not None
    )


def _lexicon_hits(text: str, words) -> list[tuple[str, str]]:
    """Return (word, sentence) for each out-of-genre term, so it can be read."""
    hits: list[tuple[str, str]] = []
    for sentence in re.split(r"(?<=[.!?])\s+", str(text or "")):
        low = sentence.lower()
        for word in words:
            if _word_present(word, low):
                hits.append((word, sentence.strip()[:160]))
    return hits


def _narration_of(payload: dict, state: dict) -> str:
    """Where the prose for a turn actually lives.

    play_turn's payload does not carry it at the top level on every path, and
    the opening scene is a journal row rather than a state key. Reading
    payload["narration"] alone records an empty string for every turn and every
    downstream metric silently measures nothing.
    """
    for key in ("narration", "latest_narration", "opening_narration"):
        text = str((payload or {}).get(key) or "")
        if text:
            return text
    turn = (payload or {}).get("turn")
    if isinstance(turn, dict) and turn.get("narration"):
        return str(turn["narration"])
    for entry in reversed((state or {}).get("history") or []):
        if str(entry.get("kind") or "") == "narration" and entry.get("content"):
            return str(entry["content"])
    return ""


def _log(handle, message: str) -> None:
    print(message, flush=True)
    handle.write(message + "\n")
    handle.flush()


def main() -> int:
    turns = _env_int("GENRE_TURNS", 5)
    samples = _env_int("GENRE_RANDOMIZE", 6)
    model = os.getenv("GENRE_MODEL") or os.getenv("OLLAMA_MODEL") or "qwen3:8b"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"genre-report-{stamp}.json"
    log = (REPORT_DIR / f"genre-{stamp}.log").open("w", encoding="utf-8")

    report: dict = {
        "benchmark": "genre_variety",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "turns_per_world": turns,
        "worlds": [],
        "randomizer": {},
        "summary": {},
    }

    _log(log, "=" * 72)
    _log(log, f" genre variety  model={model}  turns/world={turns}")
    _log(log, "=" * 72)

    only = [p.strip() for p in (os.getenv("GENRE_ONLY") or "").split(",") if p.strip()]
    selected = [g for g in GENRES if not only or g["id"] in only]
    if only and not selected:
        raise SystemExit(
            f"GENRE_ONLY={only} matched nothing. Known ids: {[g['id'] for g in GENRES]}"
        )
    plan = [(g, 0) for g in selected]
    repeat = next((g for g in selected if g["id"] == REPEAT_GENRE), None)
    if repeat:
        plan.append((repeat, 1))

    for genre, run_index in plan:
        label = genre["id"] if not run_index else f"{genre['id']}#2"
        temp = Path(tempfile.mkdtemp(prefix=f"morkyn_genre_{genre['id']}_"))
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
            # Generous, for the same reason the continuity probe is: a timeout
            # here would swap a real turn for canned prose and corrupt the
            # measurement. The shipped defaults are pinned by unit tests.
            "AI_RPG_OLLAMA_TIMEOUT": "900",
            "AI_RPG_TURN_DRAFT_TIMEOUT": "900",
            "AI_RPG_TURN_VERIFY_TIMEOUT": "600",
        }.items():
            os.environ[key] = val
        for sub in ("source_index", "traces", "slots", "packs"):
            (temp / sub).mkdir(exist_ok=True)

        sys.path.insert(0, str(REPO_ROOT))
        for name in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
            del sys.modules[name]
        from app import llm  # noqa: E402
        from app.db import connect, init_db  # noqa: E402
        from app.world import get_state, play_turn, start_playthrough_with_opening  # noqa: E402

        init_db()
        llm.update_model_config(
            {
                "provider": "ollama",
                "ollama_base_url": os.environ["OLLAMA_BASE_URL"],
                "ollama_model": model,
                "response_token_cap": 1200,
                "response_token_hard_cap": 1600,
            }
        )

        setup = {
            "player_name": "Wren Calloway" if run_index else "Ash Vale",
            "player_sex": "unspecified",
            "backstory_mode": "known",
            "character_backstory": genre["backstory"],
            "memory_policy": "known",
            "difficulty": "normal",
            "narration_detail": "balanced",
            "world_style": genre["world_style"],
            "start_location": genre["start_location"],
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

        _log(log, f"\n--- {label}: {genre['world_style'][:60]}")
        world = {
            "id": genre["id"],
            "label": label,
            "run_index": run_index,
            "world_style": genre["world_style"],
            "turns": [],
            "error": "",
        }
        t0 = time.perf_counter()
        try:
            start_playthrough_with_opening(setup)
            state = get_state(include_hidden=True)
            opening = _narration_of({}, state)
            world["opening"] = opening
            _log(log, f"    opening {len(opening)} chars at "
                      f"{(state.get('current_location') or {}).get('name')!r}")

            for index in range(turns):
                action = TURN_SCRIPT[index % len(TURN_SCRIPT)]
                started = time.perf_counter()
                payload = {}
                try:
                    payload = play_turn(action)
                    fallback = bool((payload or {}).get("used_fallback"))
                except Exception as exc:  # pragma: no cover - live model
                    fallback = True
                    _log(log, f"    turn {index + 1} ERROR {exc}")
                state = get_state(include_hidden=True)
                narration = _narration_of(payload, state)
                world["turns"].append(
                    {
                        "action": action,
                        "narration": narration,
                        "seconds": round(time.perf_counter() - started, 1),
                        "used_fallback": fallback,
                        "location": (state.get("current_location") or {}).get("name"),
                    }
                )
                _log(log, f"    [{index + 1}/{turns}] {round(time.perf_counter() - started):4d}s "
                          f"len={len(narration):5d} fb={int(fallback)} "
                          f"loc={(state.get('current_location') or {}).get('name')}")

            with connect() as conn:
                world["npcs"] = [
                    {"name": r["name"], "role": r["role"]}
                    for r in conn.execute("SELECT name, role FROM npcs")
                ]
                world["locations"] = [
                    r["name"] for r in conn.execute("SELECT name FROM locations")
                ]
                world["items"] = [
                    r["name"] for r in conn.execute("SELECT name FROM inventory")
                ]
        except Exception as exc:  # pragma: no cover - live model
            world["error"] = f"{type(exc).__name__}: {exc}"
            _log(log, f"    FAILED: {world['error']}")
            _log(log, traceback.format_exc()[:1200])

        world["elapsed_seconds"] = round(time.perf_counter() - t0, 1)
        prose = " ".join(t["narration"] for t in world["turns"])
        blob = f"{world.get('opening', '')} {prose}"
        world["forbidden_hits"] = _lexicon_hits(blob, genre["forbidden"])
        world["expected_hits"] = sorted(
            {w for w in genre["expected"] if _word_present(w, blob.lower())}
        )
        # The server's own inventions, judged separately from the model's prose.
        role_text = " ".join(n["role"] or "" for n in world.get("npcs", []))
        world["forbidden_roles"] = _lexicon_hits(role_text, genre["forbidden"])
        report["worlds"].append(world)
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

        _log(log, f"    genre words present : {world['expected_hits']}")
        if world["forbidden_hits"]:
            _log(log, f"    OUT-OF-GENRE PROSE  : {len(world['forbidden_hits'])}")
            for word, sentence in world["forbidden_hits"][:5]:
                _log(log, f"        {word!r}: {sentence}")
        if world["forbidden_roles"]:
            _log(log, f"    OUT-OF-GENRE ROLES  : "
                      f"{sorted({w for w, _ in world['forbidden_roles']})}")

    # --- live randomizer variety -------------------------------------------
    if samples > 0:
        _log(log, f"\n--- randomizer: {samples} live 'world' randomizations")
        from app import llm  # noqa: E402

        rows: list[dict] = []
        for index in range(samples):
            try:
                result = llm.generate_setup_randomization("world", {}) or {}
                # Two shapes from one endpoint: the model path returns the
                # fields at the top level, the deterministic fallback wraps
                # them in {"fields": ...}. static/app.js coalesces the same way.
                fields = result.get("fields") if isinstance(result.get("fields"), dict) else result
                fields = {
                    k: v for k, v in (fields or {}).items()
                    if not k.startswith("_") and k not in {"fallback_used", "fallback_reason"}
                }
                rows.append(fields)
                _log(log, f"    [{index + 1}/{samples}] style="
                          f"{str(fields.get('world_style'))[:56]!r}")
            except Exception as exc:  # pragma: no cover - live model
                _log(log, f"    [{index + 1}/{samples}] FAILED {type(exc).__name__}: {exc}")
        report["randomizer"] = {"samples": rows}

    report["summary"] = _summarize(report)
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, default=str), encoding="utf-8")

    _log(log, "\n" + "=" * 72)
    _log(log, " RESULT")
    _log(log, "=" * 72)
    for key, value in report["summary"].items():
        if isinstance(value, list) and len(str(value)) > 400:
            _log(log, f"  {key}:")
            for entry in value:
                _log(log, f"      {entry}")
        else:
            _log(log, f"  {key:28s} {value}")
    _log(log, f"\n  report : {report_path}")
    log.close()
    return 0


def _summarize(report: dict) -> dict:
    worlds = [w for w in report["worlds"] if not w.get("error")]
    out: dict = {
        "worlds_run": len(report["worlds"]),
        "worlds_failed": sum(1 for w in report["worlds"] if w.get("error")),
        "fallback_turns": sum(
            1 for w in report["worlds"] for t in w["turns"] if t.get("used_fallback")
        ),
    }

    fidelity = []
    for world in worlds:
        fidelity.append(
            f"{world['label']:14s} genre_words={len(world['expected_hits'])}/"
            f"{len(next(g for g in GENRES if g['id'] == world['id'])['expected'])} "
            f"out_of_genre_prose={len(world['forbidden_hits'])} "
            f"out_of_genre_roles={len(world['forbidden_roles'])}"
        )
    out["fidelity"] = fidelity
    out["worlds_with_out_of_genre_prose"] = sum(1 for w in worlds if w["forbidden_hits"])
    out["worlds_with_out_of_genre_roles"] = sum(1 for w in worlds if w["forbidden_roles"])

    # Cross-genre prose overlap: two settings sharing language are one story.
    pairs = []
    for a, b in combinations(worlds, 2):
        pa = f"{a.get('opening','')} " + " ".join(t["narration"] for t in a["turns"])
        pb = f"{b.get('opening','')} " + " ".join(t["narration"] for t in b["turns"])
        pairs.append((round(_overlap(pa, pb), 4), a["label"], b["label"]))
    pairs.sort(reverse=True)
    out["max_cross_world_overlap"] = pairs[0][0] if pairs else 0.0
    out["most_similar_pairs"] = [f"{s:.4f}  {a} vs {b}" for s, a, b in pairs[:5]]

    # Name reuse across worlds: the same cast wearing different hats.
    shared = []
    for a, b in combinations(worlds, 2):
        na = {n["name"] for n in a.get("npcs", [])}
        nb = {n["name"] for n in b.get("npcs", [])}
        common = na & nb
        if common:
            shared.append(f"{a['label']} / {b['label']}: {sorted(common)}")
    out["worlds_sharing_npc_names"] = shared

    # Same genre twice: different world, or one story told twice?
    repeats = [w for w in worlds if w["id"] == REPEAT_GENRE]
    if len(repeats) == 2:
        first, second = repeats
        pa = f"{first.get('opening','')} " + " ".join(t["narration"] for t in first["turns"])
        pb = f"{second.get('opening','')} " + " ".join(t["narration"] for t in second["turns"])
        out["repeat_run_overlap"] = round(_overlap(pa, pb), 4)
        out["repeat_shared_locations"] = sorted(
            set(first.get("locations", [])) & set(second.get("locations", []))
        )
        out["repeat_shared_npcs"] = sorted(
            {n["name"] for n in first.get("npcs", [])}
            & {n["name"] for n in second.get("npcs", [])}
        )

    rows = (report.get("randomizer") or {}).get("samples") or []
    if rows:
        keys = sorted({k for r in rows for k in r if not k.startswith("_")})
        thin = []
        for key in keys:
            seen = [str(r.get(key, ""))[:80] for r in rows]
            distinct = len(set(seen))
            if distinct <= max(2, len(rows) // 3):
                thin.append(f"{key}: {distinct}/{len(rows)} distinct")
        out["randomizer_samples"] = len(rows)
        out["randomizer_thin_fields"] = thin
        styles = [str(r.get("world_style", ""))[:80] for r in rows]
        out["randomizer_distinct_styles"] = f"{len(set(styles))}/{len(styles)}"
        dupes = []
        for (i, a), (j, b) in combinations(list(enumerate(rows)), 2):
            sim = _overlap(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
            if sim >= 0.5:
                dupes.append(f"samples {i + 1}/{j + 1} overlap {sim:.2f}")
        out["randomizer_near_duplicates"] = dupes
    return out


if __name__ == "__main__":
    raise SystemExit(main())
