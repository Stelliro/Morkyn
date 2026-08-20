"""
Server-side danger and encounter resolution.

The old travel roll looked at terrain, weather, and elapsed minutes. That made
a exhausted level-1 character hauling 90kg through a swamp at midnight exactly
as safe as a rested level-20 scout on the same tile at noon.

:func:`assess_danger` builds a single 0..1 danger score out of everything the
database already knows — terrain, weather, clock, the player's stats, skills,
fatigue, carried load, local reputation, notoriety, and what the player has
heard about the area — and shows its work as a list of named factors. The UI
and the model trace can both render that list, so "why did I get ambushed" has
a real answer.

:func:`roll_encounter` then converts that score into an actual event, rolling
*how many* and *how bad* through :mod:`app.rng` rather than asking the model.

Nothing here imports ``app.world`` or ``app.tile_world`` at module scope, so
both are free to call in.
"""
from __future__ import annotations

import random
from typing import Any

from app.rng import normalize_band, resolve_magnitude, rng_for, seed_from

# --- default tables (content packs may override any of these) ----------------

# Per-hour chance of *something* happening on open terrain, before modifiers.
TERRAIN_BASE_DANGER: dict[str, float] = {
    "road": 0.06, "bridge": 0.06,
    "city": 0.05, "town": 0.05, "village": 0.04, "farm": 0.05, "harbor": 0.07,
    "station": 0.05, "colony": 0.05, "shipyard": 0.06,
    "plains": 0.10, "beach": 0.09, "tundra": 0.12, "ice": 0.12,
    "hill": 0.11, "mesa": 0.11,
    "forest": 0.16, "swamp": 0.18, "desert": 0.13,
    "mountain": 0.14, "cliff": 0.15,
    "ruins": 0.20, "wreck": 0.20, "cavern": 0.18, "mushroom": 0.16,
    "dungeon": 0.26, "volcano": 0.24, "lava": 0.24, "ash": 0.18,
    "anomaly": 0.28, "void": 0.14, "nebula": 0.14, "asteroid": 0.15,
    "crystal": 0.16, "monolith": 0.15, "gate": 0.12, "water": 0.14,
}

DEFAULT_KIND_WEIGHTS: dict[str, dict[str, float]] = {
    "road": {"bandit_ambush": 40, "wild_threat": 20, "traveler": 30, "hidden_base": 10},
    "forest": {"bandit_ambush": 22, "wild_threat": 48, "traveler": 8, "hidden_base": 22},
    "swamp": {"bandit_ambush": 18, "wild_threat": 55, "traveler": 7, "hidden_base": 20},
    "plains": {"bandit_ambush": 40, "wild_threat": 35, "traveler": 10, "hidden_base": 15},
    "desert": {"bandit_ambush": 35, "wild_threat": 40, "traveler": 7, "hidden_base": 18},
    "mountain": {"bandit_ambush": 25, "wild_threat": 40, "traveler": 7, "hidden_base": 28},
    "ruins": {"bandit_ambush": 28, "wild_threat": 30, "traveler": 7, "hidden_base": 35},
    "dungeon": {"bandit_ambush": 15, "wild_threat": 45, "traveler": 5, "hidden_base": 35},
    "city": {"bandit_ambush": 45, "wild_threat": 5, "traveler": 30, "hidden_base": 20},
    "town": {"bandit_ambush": 35, "wild_threat": 5, "traveler": 45, "hidden_base": 15},
    "village": {"bandit_ambush": 25, "wild_threat": 10, "traveler": 50, "hidden_base": 15},
}

DEFAULT_KINDS: dict[str, dict[str, Any]] = {
    "bandit_ambush": {
        "label": "Ambush",
        "hostile": True,
        "avoid_skill": "ambush_sense",
        "count_band": "small",
        "threat_band": "moderate",
        "participant_tier": "nameless",
    },
    "wild_threat": {
        "label": "Wild threat",
        "hostile": True,
        "avoid_skill": "perception",
        "count_band": "small",
        "threat_band": "moderate",
        "participant_tier": "nameless",
    },
    "hidden_base": {
        "label": "Hidden camp",
        "hostile": False,
        "wary": True,
        "avoid_skill": "stealth",
        "count_band": "moderate",
        "threat_band": "large",
        "participant_tier": "nameless",
    },
    "traveler": {
        "label": "Fellow traveler",
        "hostile": False,
        "wary": True,
        "avoid_skill": "perception",
        "count_band": "trivial",
        "threat_band": "trivial",
        "participant_tier": "event_worthy",
    },
}

# How much each weather kind pushes danger, scaled by its strength.
WEATHER_DANGER: dict[str, float] = {
    "clear": 0.0,
    "cloudy": 0.01,
    "wind": 0.04,
    "rain": 0.05,
    "heat": 0.05,
    "fog": 0.10,
    "snow": 0.09,
    "storm": 0.13,
}

DIFFICULTY_DANGER: dict[str, float] = {
    "easy": -0.05,
    "normal": 0.0,
    "hard": 0.05,
    "brutal": 0.10,
}

# Exponent applied to the combined player multiplier. Below 1.0 it compresses
# the product so stacked modifiers stay legible instead of saturating the cap.
PLAYER_MULT_DAMPING = 0.55

DANGER_BANDS: tuple[tuple[float, str], ...] = (
    (0.10, "calm"),
    (0.22, "uneasy"),
    (0.40, "dangerous"),
    (1.01, "deadly"),
)

# Skills that reduce exposure when the player actually has ranks in them.
AWARENESS_SKILLS = ("perception", "ambush_sense", "survival", "navigation", "stealth", "streetwise")

SETTLEMENT_STATES = {"city", "town", "village", "farm", "harbor", "station", "colony", "shipyard"}
SAFE_PATH_STATES = {"road", "bridge"}


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _pack_tables() -> dict[str, Any]:
    try:
        from app.content_packs import active_encounter_tables

        return active_encounter_tables() or {}
    except Exception:
        return {}


def terrain_profile(state: str) -> dict[str, Any]:
    """Base chance + kind weights for a tile state, with pack overrides."""
    state = str(state or "plains").lower()
    tables = _pack_tables()
    override = (tables.get("terrain") or {}).get(state)
    if isinstance(override, dict):
        return {
            "base_chance": _f(override.get("base_chance"), 0.10),
            "kinds": dict(override.get("kinds") or DEFAULT_KIND_WEIGHTS.get(state) or DEFAULT_KIND_WEIGHTS["plains"]),
            "source": "pack",
        }
    return {
        "base_chance": TERRAIN_BASE_DANGER.get(state, 0.10),
        "kinds": dict(DEFAULT_KIND_WEIGHTS.get(state) or DEFAULT_KIND_WEIGHTS["plains"]),
        "source": "builtin",
    }


def kind_profile(kind: str) -> dict[str, Any]:
    kind = str(kind or "wild_threat").lower()
    tables = _pack_tables()
    override = (tables.get("kinds") or {}).get(kind)
    base = dict(DEFAULT_KINDS.get(kind) or DEFAULT_KINDS["wild_threat"])
    if isinstance(override, dict):
        base.update(override)
    base.setdefault("label", kind.replace("_", " ").title())
    return base


def _skill_rank(skills: Any, code: str) -> int:
    """Highest matching rank for a skill code/name in the player's skill list."""
    best = 0
    for skill in skills or []:
        if not isinstance(skill, dict):
            continue
        name = str(skill.get("code") or skill.get("name") or "").lower().replace(" ", "_")
        if code in name or name in code:
            best = max(best, _i(skill.get("value") or skill.get("level") or skill.get("rank"), 0))
    return max(0, min(20, best))


def _stat(stats: Any, key: str, default: int = 10) -> int:
    if not isinstance(stats, dict):
        return default
    for name, value in stats.items():
        if str(name).strip().lower().startswith(key[:3]):
            return max(1, min(40, _i(value, default)))
    return default


def danger_band(score: float) -> str:
    for ceiling, label in DANGER_BANDS:
        if score < ceiling:
            return label
    return "deadly"


def player_snapshot(conn=None) -> dict[str, Any]:
    """
    Cheap read of everything :func:`assess_danger` wants about the player.

    Deliberately not ``world.get_state()``: that builds the whole prompt-facing
    world and gets called on every map step. This is four small queries.
    """
    if conn is None:
        from app.db import connect

        with connect() as owned:
            return player_snapshot(owned)

    snapshot: dict[str, Any] = {
        "player": {},
        "skills": [],
        "resources": {},
        "inventory_summary": {},
        "options": {},
        "area_reputation": 0,
    }
    try:
        row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    except Exception:
        return snapshot
    if not row:
        return snapshot
    player = {key: row[key] for key in row.keys()}

    # Equipment stat bonuses, folded the same way get_state() folds them.
    effective: dict[str, int] = {}
    total_weight = 0.0
    try:
        items = conn.execute(
            "SELECT name, quantity, weight, stat_modifiers, stat_links, equipped_slot FROM inventory"
        ).fetchall()
    except Exception:
        items = []
    for item in items:
        try:
            total_weight += _f(item["weight"], 1.0) * max(0, _i(item["quantity"], 0))
        except Exception:
            pass
        if not str(item["equipped_slot"] or "").strip():
            continue
        for column in ("stat_links", "stat_modifiers"):
            raw = item[column] if column in item.keys() else None
            if not raw:
                continue
            try:
                parsed = raw if isinstance(raw, dict) else __import__("json").loads(raw or "{}")
            except Exception:
                continue
            if not isinstance(parsed, dict):
                continue
            for stat, value in parsed.items():
                key = str(stat).strip().lower()
                effective[key] = effective.get(key, 0) + _i(value, 0)
            break

    snapshot["player"] = {
        "level": _i(player.get("level"), 1),
        "health": _i(player.get("health"), 20),
        "max_health": _i(player.get("max_health"), 20),
        "karma": _i(player.get("karma"), 0),
        "effective_stats": effective,
    }
    snapshot["resources"] = {
        "energy": _i(player.get("energy"), 20),
        "max_energy": max(1, _i(player.get("max_energy"), 20)),
        "fatigue": _i(player.get("fatigue"), 0),
        "max_fatigue": max(1, _i(player.get("max_fatigue"), 20)),
        "mana": _i(player.get("mana"), 0),
        "max_mana": _i(player.get("max_mana"), 0),
    }

    try:
        snapshot["skills"] = [
            {"name": r["name"], "value": _i(r["value"], 0)}
            for r in conn.execute("SELECT name, value FROM player_skills").fetchall()
        ]
    except Exception:
        snapshot["skills"] = []

    # Capacity mirrors world._inventory_summary's default; close enough for a
    # danger modifier, and it never blocks travel on its own.
    capacity = 60.0 + (_i(effective.get("strength"), 0) * 5.0)
    snapshot["inventory_summary"] = {
        "weight_capacity": max(1.0, capacity),
        "effective_weight": round(total_weight, 2),
    }

    try:
        import json as _json

        raw_options = conn.execute(
            "SELECT value FROM settings WHERE key = 'playthrough_options'"
        ).fetchone()
        if raw_options:
            parsed = _json.loads(raw_options["value"] or "{}")
            if isinstance(parsed, dict):
                snapshot["options"] = parsed
        raw_rep = conn.execute(
            "SELECT value FROM settings WHERE key = 'area_reputation'"
        ).fetchone()
        if raw_rep:
            reps = _json.loads(raw_rep["value"] or "{}")
            if isinstance(reps, dict) and player.get("current_location_id"):
                loc = conn.execute(
                    "SELECT code FROM locations WHERE id = ?", (player["current_location_id"],)
                ).fetchone()
                key = str(loc["code"]) if loc else str(player["current_location_id"])
                snapshot["area_reputation"] = _i(
                    reps.get(key) or reps.get(str(player["current_location_id"])), 0
                )
    except Exception:
        pass

    return snapshot


def assess_danger(
    *,
    terrain: str = "plains",
    weather: dict[str, Any] | None = None,
    world_time: dict[str, Any] | None = None,
    player: dict[str, Any] | None = None,
    skills: list[dict[str, Any]] | None = None,
    resources: dict[str, Any] | None = None,
    inventory_summary: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    settlement: dict[str, Any] | None = None,
    known_danger_nearby: int = 0,
    area_reputation: int = 0,
    on_road: bool = False,
    hidden_base_here: bool = False,
) -> dict[str, Any]:
    """
    Build a 0..1 danger score with a full, human-readable factor breakdown.

    Two-stage on purpose:

    * **Environment** terms are *additive*. Terrain, weather, clock, roads and
      campaign difficulty are properties of the world, and they set the level.
    * **Player** terms are *multiplicative*. Skills, stats, wounds, fatigue,
      load and reputation scale that level up or down.

    Additive player bonuses were the first thing tried and they were wrong: a
    handful of them cancelled a town's entire base risk and every skilled
    character became untouchable. Multiplying means a great scout in a dungeon
    is still in a dungeon — just meaningfully better off than a novice there.

    Every argument is optional; missing information simply contributes nothing,
    so callers can pass whatever slice of state they happen to have.
    """
    player = player if isinstance(player, dict) else {}
    options = options if isinstance(options, dict) else {}
    resources = resources if isinstance(resources, dict) else {}
    weather = weather if isinstance(weather, dict) else {}
    world_time = world_time if isinstance(world_time, dict) else {}
    inventory_summary = inventory_summary if isinstance(inventory_summary, dict) else {}

    state = str(terrain or "plains").lower()
    profile = terrain_profile(state)
    base = float(profile["base_chance"])
    factors: list[dict[str, Any]] = [
        {"name": "terrain", "delta": round(base, 4), "detail": f"{state} baseline ({profile['source']})"}
    ]
    score = base
    player_mult = 1.0

    def add(name: str, delta: float, detail: str) -> None:
        """Environmental term: shifts the baseline level of risk."""
        nonlocal score
        if abs(delta) < 0.0005:
            return
        score += delta
        factors.append({"name": name, "delta": round(delta, 4), "detail": detail})

    def scale(name: str, mult: float, detail: str) -> None:
        """Player-side term: scales whatever the environment already set."""
        nonlocal player_mult
        if abs(mult - 1.0) < 0.005:
            return
        player_mult *= mult
        factors.append({"name": name, "mult": round(mult, 4), "detail": detail})

    # --- environment ---------------------------------------------------------
    kind = str(weather.get("kind") or "clear").lower()
    strength = max(0.0, min(1.0, _f(weather.get("strength"), 0.0)))
    add(
        "weather",
        WEATHER_DANGER.get(kind, 0.0) * (0.45 + 0.55 * strength),
        f"{weather.get('label') or kind} (strength {strength:.2f})",
    )

    hour = _i(world_time.get("hour"), 12)
    if hour >= 22 or hour < 5:
        add("night", 0.06 if state in SETTLEMENT_STATES else 0.09, f"hour {hour:02d}: night")
    elif 5 <= hour < 8:
        add("dawn", 0.02, f"hour {hour:02d}: dawn")
    elif 10 <= hour < 15:
        add("daylight", -0.03, f"hour {hour:02d}: full daylight")

    if on_road or state in SAFE_PATH_STATES:
        add("road", -0.03, "travelled route: fewer surprises, more banditry share")
    if state in SETTLEMENT_STATES or settlement:
        add("settlement", -0.04, "inhabited ground with witnesses")
    if hidden_base_here:
        add("hidden_base", 0.18, "standing on an undiscovered camp")

    difficulty = str(options.get("difficulty") or "normal").strip().lower()
    add("difficulty", DIFFICULTY_DANGER.get(difficulty, 0.0), f"campaign difficulty: {difficulty}")

    density = str(options.get("npc_density") or "").lower()
    if "sparse" in density:
        add("sparse_world", -0.02, "sparse NPC density")
    elif "dense" in density or "faction" in density:
        add("dense_world", 0.02, "dense/faction NPC density")

    environment = max(0.01, min(0.95, score))

    # --- the player (multiplicative) -----------------------------------------
    stats = player.get("effective_stats") if isinstance(player.get("effective_stats"), dict) else player.get("stats")
    wisdom = _stat(stats, "wisdom")
    dexterity = _stat(stats, "dexterity")
    # +/-10 points of wisdom is worth roughly +/-25%; dexterity counts half.
    awareness = ((wisdom - 10) + (dexterity - 10) * 0.5) * 0.025
    scale("awareness_stats", 1.0 - max(-0.45, min(0.45, awareness)), f"wisdom {wisdom}, dexterity {dexterity}")

    best_skill = 0
    best_skill_name = ""
    for code in AWARENESS_SKILLS:
        rank = _skill_rank(skills, code)
        if rank > best_skill:
            best_skill, best_skill_name = rank, code
    if best_skill:
        # Ranks have diminishing returns and can never fully hide you.
        scale("field_skill", max(0.55, 1.0 - best_skill * 0.045), f"{best_skill_name} rank {best_skill}")

    level = max(1, _i(player.get("level"), 1))
    if base >= 0.16 and level <= 3:
        scale("out_of_depth", 1.35, f"level {level} in high-risk terrain")
    elif level >= 10 and base < 0.16:
        scale("seasoned", 0.8, f"level {level} on ordinary ground")

    # --- condition -----------------------------------------------------------
    max_energy = max(1, _i(resources.get("max_energy"), 20))
    energy_ratio = max(0.0, min(1.0, _i(resources.get("energy"), max_energy) / max_energy))
    if energy_ratio < 0.5:
        scale("tired", 1.0 + (0.5 - energy_ratio) * 0.9, f"energy {energy_ratio:.0%}")

    max_fatigue = max(1, _i(resources.get("max_fatigue"), 20))
    fatigue_ratio = max(0.0, min(1.0, _i(resources.get("fatigue"), 0) / max_fatigue))
    if fatigue_ratio > 0.4:
        scale("fatigue", 1.0 + (fatigue_ratio - 0.4) * 1.1, f"fatigue {fatigue_ratio:.0%}")

    max_health = max(1, _i(player.get("max_health"), 20))
    health_ratio = max(0.0, min(1.0, _i(player.get("health"), max_health) / max_health))
    if health_ratio < 0.5:
        scale("wounded", 1.0 + (0.5 - health_ratio) * 0.8, f"health {health_ratio:.0%}")

    capacity = max(1.0, _f(inventory_summary.get("weight_capacity"), 60.0))
    carried = max(0.0, _f(inventory_summary.get("effective_weight"), 0.0))
    load_ratio = carried / capacity
    if load_ratio > 0.75:
        scale("overloaded", 1.0 + min(0.6, (load_ratio - 0.75) * 1.2), f"carrying {load_ratio:.0%} of capacity")

    # --- social standing -----------------------------------------------------
    karma = _i(player.get("karma"), 0)
    if karma <= -200:
        scale("infamy", 1.0 + min(0.5, abs(karma) / 1000.0), f"karma {karma}: trouble seeks you")
    rep = max(-100, min(100, _i(area_reputation, 0)))
    if rep < -20:
        scale("local_hostility", 1.0 + min(0.4, abs(rep) / 250.0), f"area reputation {rep}")
    elif rep > 40:
        scale("local_goodwill", max(0.8, 1.0 - rep / 500.0), f"area reputation {rep}")

    # --- what the player already knows --------------------------------------
    if known_danger_nearby > 0:
        scale(
            "forewarned",
            max(0.7, 1.0 - known_danger_nearby * 0.1),
            f"{known_danger_nearby} known danger marker(s) nearby: you route around them",
        )

    # Raw products compound hard — six mild penalties multiplied out to ~6.5x
    # and pinned every unlucky character to the cap, erasing the difference
    # between "having a bad day" and "about to die". Damping the aggregate in
    # log space keeps the ordering while leaving headroom at the extremes.
    raw_mult = player_mult
    player_mult = max(0.4, min(2.6, raw_mult ** PLAYER_MULT_DAMPING))
    final = max(0.005, min(0.95, environment * player_mult))

    return {
        "danger": round(final, 4),
        "band": danger_band(final),
        "base": round(base, 4),
        "environment": round(environment, 4),
        "player_multiplier": round(player_mult, 4),
        "player_multiplier_raw": round(raw_mult, 4),
        "terrain": state,
        "factors": factors,
        "kind_weights": profile["kinds"],
        "inputs": {
            "level": level,
            "energy_ratio": round(energy_ratio, 3),
            "fatigue_ratio": round(fatigue_ratio, 3),
            "health_ratio": round(health_ratio, 3),
            "load_ratio": round(load_ratio, 3),
            "hour": hour,
            "weather": kind,
            "weather_strength": strength,
            "area_reputation": rep,
            "best_awareness_skill": best_skill_name,
            "best_awareness_rank": best_skill,
        },
    }


def _pick_kind(weights: dict[str, float], rng: random.Random) -> str:
    usable = {k: max(0.0, _f(v, 0.0)) for k, v in (weights or {}).items()}
    total = sum(usable.values())
    if total <= 0:
        return "wild_threat"
    roll = rng.random() * total
    acc = 0.0
    for kind, weight in usable.items():
        acc += weight
        if roll <= acc:
            return kind
    return list(usable)[-1]


def roll_encounter(
    assessment: dict[str, Any],
    *,
    minutes: int = 10,
    seed: int | None = None,
    turn: int = 0,
    player: dict[str, Any] | None = None,
    skills: list[dict[str, Any]] | None = None,
    options: dict[str, Any] | None = None,
    forced_kind: str = "",
) -> dict[str, Any]:
    """
    Convert a danger assessment into a concrete encounter (or quiet passage).

    Exposure compounds with time: ``p = 1 - (1 - danger) ** hours``. A five
    minute step through a deadly swamp is survivable; four hours of it is not.

    When something does fire, the player gets a passive awareness roll against
    it. Beating it means ``forewarned`` (you see them first) rather than
    ``surprised`` — the difference between an ambush and a standoff.
    """
    player = player if isinstance(player, dict) else {}
    options = options if isinstance(options, dict) else {}
    danger = max(0.0, min(0.95, _f(assessment.get("danger"), 0.10)))
    minutes = max(1, _i(minutes, 10))
    hours = minutes / 60.0

    # Even a one-tile step is a real slice of exposure, not a rounding error.
    exposure = max(0.12, hours)
    chance = 1.0 - (1.0 - danger) ** exposure
    chance = max(0.002, min(0.85, chance))

    rng = rng_for("encounter", turn=turn, seed=seed, salt=f"{minutes}:{assessment.get('terrain')}")
    natural = rng.random()
    happened = forced_kind != "" or natural < chance

    result: dict[str, Any] = {
        "happened": bool(happened),
        "kind": "none",
        "chance": round(chance, 4),
        "roll": round(natural, 4),
        "danger": danger,
        "danger_band": assessment.get("band"),
        "terrain": assessment.get("terrain"),
        "minutes": minutes,
        "hours": round(hours, 4),
        "factors": assessment.get("factors") or [],
    }
    if not happened:
        return result

    kind = forced_kind or _pick_kind(assessment.get("kind_weights") or {}, rng)
    profile = kind_profile(kind)
    level = max(1, _i(player.get("level"), 1))
    difficulty = str(options.get("difficulty") or "normal")

    count_roll = resolve_magnitude(
        "count_people",
        profile.get("count_band") or "small",
        level=level,
        difficulty=difficulty,
        options=options,
        rng=rng,
        turn=turn,
        tag=f"encounter_count:{kind}",
    )
    threat_roll = resolve_magnitude(
        "damage",
        profile.get("threat_band") or "moderate",
        level=level,
        difficulty=difficulty,
        options=options,
        rng=rng,
        turn=turn,
        tag=f"encounter_threat:{kind}",
    )

    # Passive awareness: your skills decide whether you walk into it blind.
    avoid_skill = str(profile.get("avoid_skill") or "perception")
    awareness_rank = _skill_rank(skills, avoid_skill)
    stats = player.get("effective_stats") if isinstance(player.get("effective_stats"), dict) else player.get("stats")
    awareness_mod = (_stat(stats, "wisdom") - 10) // 2 + awareness_rank
    notice_dc = 10 + int(round(danger * 12))
    notice_natural = rng.randint(1, 20)
    notice_total = notice_natural + awareness_mod
    noticed = notice_total >= notice_dc

    # A clean read on a non-hostile meeting means it simply does not become an
    # incident: you saw them coming and stepped off the path.
    avoided = noticed and not profile.get("hostile") and notice_total >= notice_dc + 6

    result.update(
        {
            "kind": kind,
            "label": profile.get("label"),
            "hostile_default": bool(profile.get("hostile")),
            "wary_not_evil": bool(profile.get("wary")) and not profile.get("hostile"),
            "participant_tier": profile.get("participant_tier") or "nameless",
            "count": max(1, int(count_roll["value"])),
            "count_roll": count_roll,
            "threat": int(threat_roll["value"]),
            "threat_roll": threat_roll,
            "threat_band": profile.get("threat_band"),
            "awareness": {
                "skill": avoid_skill,
                "rank": awareness_rank,
                "modifier": awareness_mod,
                "natural": notice_natural,
                "total": notice_total,
                "dc": notice_dc,
                "noticed": bool(noticed),
            },
            "surprise": "forewarned" if noticed else "surprised",
            "avoided": bool(avoided),
            "happened": not avoided,
            "outcome_seed": rng.randint(1, 999999),
        }
    )
    if avoided:
        result["kind"] = "none"
        result["avoided_kind"] = kind
    return result


def encounter_summary_line(result: dict[str, Any]) -> str:
    """One journal-safe line describing the roll, for the audit trail."""
    if not isinstance(result, dict):
        return ""
    if result.get("avoided"):
        return (
            f"Spotted {result.get('avoided_kind')} early "
            f"({result.get('awareness', {}).get('total')} vs DC {result.get('awareness', {}).get('dc')}) "
            f"and avoided it."
        )
    if not result.get("happened"):
        return (
            f"Quiet passage: danger {result.get('danger')} ({result.get('danger_band')}), "
            f"chance {result.get('chance')}, roll {result.get('roll')}."
        )
    awareness = result.get("awareness") or {}
    return (
        f"{result.get('label') or result.get('kind')}: {result.get('count')} participant(s), "
        f"threat {result.get('threat')}, {result.get('surprise')} "
        f"(awareness {awareness.get('total')} vs DC {awareness.get('dc')})."
    )


def _factor_weight(factor: dict[str, Any]) -> float:
    """Comparable magnitude for additive and multiplicative factors alike."""
    if "mult" in factor:
        return abs(_f(factor.get("mult"), 1.0) - 1.0)
    return abs(_f(factor.get("delta"), 0.0))


def _factor_raises(factor: dict[str, Any]) -> bool:
    if "mult" in factor:
        return _f(factor.get("mult"), 1.0) > 1.0
    return _f(factor.get("delta"), 0.0) > 0


def top_factors(assessment: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    """The handful of factors that moved the needle most — for prompt context."""
    factors = [f for f in (assessment.get("factors") or []) if isinstance(f, dict)]
    factors.sort(key=_factor_weight, reverse=True)
    return factors[:limit]


def danger_context_block(assessment: dict[str, Any]) -> dict[str, Any]:
    """
    Compact packet for the narrator.

    Gives the *feel* (band + why) and withholds the arithmetic, so the model
    describes tension instead of reciting probabilities at the player.
    """
    if not isinstance(assessment, dict):
        return {}
    return {
        "band": assessment.get("band"),
        "terrain": assessment.get("terrain"),
        "reasons": [f["detail"] for f in top_factors(assessment, 6) if _factor_raises(f)][:4],
        "reliefs": [f["detail"] for f in top_factors(assessment, 8) if not _factor_raises(f)][:3],
        "note": "Danger is server-simulated. Convey it as atmosphere; never quote numbers or odds to the player.",
    }
