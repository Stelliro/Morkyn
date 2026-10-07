"""
Player resources: energy (stamina), fatigue, mana.

Server-enforced pools for travel, wait/meditate/sleep, and (later) power costs.
Formulas live here so world/main/UI stay thin.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

# Ordinary human baseline
BASE_ENERGY = 20
BASE_FATIGUE_CAP = 20
MAX_FATIGUE_HARD = 80
MIN_ENERGY = 10
MAX_ENERGY_HARD = 40

# Playthrough option knobs (merged with playthrough_options.resource_settings)
DEFAULT_RESOURCE_SETTINGS: dict[str, Any] = {
    "travel_hard_block": True,  # cannot walk if energy < step cost
    "collapse_at_full_fatigue": True,  # soft collapse band effects
    "action_energy_enabled": True,  # free-text actions drain energy
    "drain_scale": 1.0,  # global multiplier on spends
    "zero_energy_blocks_physical": True,  # combat/sneak/climb blocked at 0 energy
}

# Distinct structured cost shapes for multi-ability batches (rotated when clones collide)
RESOURCE_COST_SHAPES_MILD: list[dict[str, int]] = [
    {"energy": 0, "mana": 1, "fatigue": 0, "health": 0, "cooldown_minutes": 0},
    {"energy": 1, "mana": 0, "fatigue": 0, "health": 0, "cooldown_minutes": 0},
    {"energy": 0, "mana": 0, "fatigue": 1, "health": 0, "cooldown_minutes": 10},
    {"energy": 1, "mana": 1, "fatigue": 0, "health": 0, "cooldown_minutes": 0},
    {"energy": 2, "mana": 0, "fatigue": 0, "health": 0, "cooldown_minutes": 15},
]
RESOURCE_COST_SHAPES_MODERATE: list[dict[str, int]] = [
    {"energy": 2, "mana": 3, "fatigue": 0, "health": 0, "cooldown_minutes": 30},
    {"energy": 4, "mana": 0, "fatigue": 1, "health": 0, "cooldown_minutes": 20},
    {"energy": 1, "mana": 5, "fatigue": 0, "health": 0, "cooldown_minutes": 60},
    {"energy": 3, "mana": 2, "fatigue": 1, "health": 0, "cooldown_minutes": 45},
    {"energy": 2, "mana": 0, "fatigue": 2, "health": 0, "cooldown_minutes": 30},
    {"energy": 0, "mana": 4, "fatigue": 0, "health": 1, "cooldown_minutes": 60},
]
RESOURCE_COST_SHAPES_STRONG: list[dict[str, int]] = [
    {"energy": 4, "mana": 8, "fatigue": 2, "health": 0, "cooldown_minutes": 180},
    {"energy": 6, "mana": 0, "fatigue": 3, "health": 0, "cooldown_minutes": 120},
    {"energy": 2, "mana": 10, "fatigue": 1, "health": 1, "cooldown_minutes": 240},
    {"energy": 5, "mana": 5, "fatigue": 2, "health": 0, "cooldown_minutes": 180},
    {"energy": 3, "mana": 6, "fatigue": 1, "health": 2, "cooldown_minutes": 360},
]

TERRAIN_MULT: dict[str, float] = {
    "road": 0.6,
    "path": 0.6,
    "trail": 0.65,
    "settlement": 0.7,
    "city": 0.7,
    "town": 0.7,
    "plains": 1.0,
    "field": 1.0,
    "grass": 1.0,
    "forest": 1.4,
    "woods": 1.4,
    "hill": 1.5,
    "hills": 1.5,
    "mountain": 2.0,
    "mountains": 2.0,
    "cliff": 2.0,
    "swamp": 1.8,
    "marsh": 1.8,
    "ruin": 1.3,
    "ruins": 1.3,
    "void": 1.3,
    "dungeon": 1.35,
    "water": 1.6,
    "desert": 1.5,
}


def _clamp(n: float | int, lo: float | int, hi: float | int) -> int:
    return int(max(lo, min(hi, round(float(n)))))


def _float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _attr(stats: dict[str, Any] | None, key: str, default: int = 10) -> int:
    if not isinstance(stats, dict):
        return default
    for k in (key, key.lower(), key[:3]):
        if k in stats:
            return _int(stats.get(k), default)
    # common aliases
    aliases = {
        "constitution": ("con", "endurance", "vitality"),
        "strength": ("str", "might"),
        "dexterity": ("dex", "agility"),
    }
    for alt in aliases.get(key, ()):
        if alt in stats:
            return _int(stats.get(alt), default)
    return default


def magic_allows_mana(magic_level: str = "", options: dict[str, Any] | None = None) -> bool:
    opts = options if isinstance(options, dict) else {}
    ml = str(magic_level or opts.get("magic_level") or "").strip().lower()
    if any(x in ml for x in ("none", "no magic", "off", "absent", "zero", "disabled")):
        return False
    # system UI worlds may still use "mana" as focus even if low magic
    if opts.get("game_system") and not ml:
        return True
    return bool(ml) or bool(opts.get("game_system"))


def life_force_score(
    *,
    level: int = 1,
    max_energy: int = BASE_ENERGY,
    stats: dict[str, Any] | None = None,
    magic_level: str = "",
    options: dict[str, Any] | None = None,
) -> int:
    """How much 'life force' raises fatigue hard cap above ordinary 20."""
    con = _attr(stats, "constitution", 10)
    level = max(1, _int(level, 1))
    score = 0
    score += max(0, level - 1)
    score += max(0, con - 10) // 2
    score += max(0, _int(max_energy, BASE_ENERGY) - BASE_ENERGY) // 2
    ml = str(magic_level or (options or {}).get("magic_level") or "").lower()
    if any(x in ml for x in ("cultivat", "common", "high")):
        score += 2 + level // 2
    elif "rare" in ml:
        score += min(2, level // 3)
    return max(0, score)


def max_fatigue_for_life_force(life_force: int) -> int:
    """Ordinary hard ceiling 20; rises with life force."""
    return _clamp(BASE_FATIGUE_CAP + max(0, int(life_force)), BASE_FATIGUE_CAP, MAX_FATIGUE_HARD)


def default_resource_caps(
    options: dict[str, Any] | None = None,
    *,
    player: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, int]:
    opts = options if isinstance(options, dict) else {}
    player = player if isinstance(player, dict) else {}
    stats = stats if isinstance(stats, dict) else (player.get("effective_stats") if isinstance(player.get("effective_stats"), dict) else {})
    con = _attr(stats, "constitution", 10)
    level = max(1, _int(player.get("level"), 1))

    max_energy = _clamp(16 + max(0, con - 10) + level // 2, MIN_ENERGY, MAX_ENERGY_HARD)
    # Prefer existing max if already higher from growth
    if player.get("max_energy"):
        max_energy = max(max_energy, _int(player.get("max_energy"), max_energy))

    mana_ok = magic_allows_mana(str(opts.get("magic_level") or ""), opts)
    if not mana_ok:
        max_mana = 0
    else:
        ml = str(opts.get("magic_level") or "").lower()
        if any(x in ml for x in ("cultivat", "common", "high")):
            max_mana = 16 + 2 * level
        else:
            max_mana = 10 + level
        max_mana = _clamp(max_mana, 0, 80)

    lf = life_force_score(
        level=level,
        max_energy=max_energy,
        stats=stats,
        magic_level=str(opts.get("magic_level") or ""),
        options=opts,
    )
    max_fatigue = max_fatigue_for_life_force(lf)

    return {
        "max_energy": max_energy,
        "max_mana": max_mana,
        "max_fatigue": max_fatigue,
        "life_force": lf,
    }


def fatigue_stamina_mult(fatigue: int, max_fatigue: int) -> float:
    ratio = max(0.0, min(1.0, _float(fatigue) / max(1.0, _float(max_fatigue))))
    return 1.0 + 0.75 * ratio


def fatigue_fill_ratio(fatigue: int, max_fatigue: int) -> float:
    return max(0.0, min(1.0, _float(fatigue) / max(1.0, _float(max_fatigue))))


def attr_mods(stats: dict[str, Any] | None = None) -> dict[str, float]:
    con = _attr(stats, "constitution", 10)
    strength = _attr(stats, "strength", 10)
    dex = _attr(stats, "dexterity", 10)
    return {
        "con_mod": (con - 10) / 10.0,
        "str_mod": (strength - 10) / 10.0,
        "dex_mod": (dex - 10) / 10.0,
        "constitution": con,
        "strength": strength,
        "dexterity": dex,
    }


def terrain_multiplier(terrain: str = "") -> float:
    t = re.sub(r"\s+", " ", str(terrain or "").strip().lower())
    if not t:
        return 1.0
    for key, mult in TERRAIN_MULT.items():
        if key in t:
            return mult
    return 1.0


def is_rough_terrain(terrain: str = "") -> bool:
    t = str(terrain or "").lower()
    return any(k in t for k in ("forest", "mountain", "hill", "swamp", "marsh", "desert", "cliff", "ruin", "void", "dungeon"))


def travel_resource_delta(
    *,
    terrain: str = "",
    minutes: int = 0,
    load_ratio: float = 0.4,
    weather_mult: float = 1.0,
    fatigue: int = 0,
    max_fatigue: int = BASE_FATIGUE_CAP,
    stats: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Energy cost + fatigue gain for a travel step."""
    minutes = max(0, _int(minutes, 0))
    if minutes <= 0:
        return {"energy": 0, "fatigue": 0, "mana": 0}

    mods = attr_mods(stats)
    con_mod, str_mod, dex_mod = mods["con_mod"], mods["str_mod"], mods["dex_mod"]
    tmult = terrain_multiplier(terrain)
    wmult = max(0.5, min(2.5, _float(weather_mult, 1.0)))
    base = tmult * (minutes / 10.0) * wmult

    load_mult = max(0.5, min(2.2, _float(load_ratio, 0.4) / max(0.25, 1.0 + 0.4 * str_mod)))
    travel_attr = max(0.6, min(1.35, 1.0 - 0.15 * dex_mod - 0.10 * con_mod))
    fat_mult = fatigue_stamina_mult(fatigue, max_fatigue)
    fatigue_gain_mult = max(0.45, min(1.4, 1.0 - 0.35 * con_mod))

    energy_exact = max(0.0, base * load_mult * travel_attr * fat_mult)
    # The 1-point floor is for rough ground only (playtest #80): on a street
    # it charged 1 for every 5-minute walk, about four times the formula, and
    # emptied a fresh character by mid-morning. Road and city walks pay their
    # fractional cost through the carry ledger instead.
    if minutes >= 5 and energy_exact < 1.0 and is_rough_terrain(terrain):
        energy_exact = 1.0
    rough = 1.0 if is_rough_terrain(terrain) else 0.4
    fatigue_exact = max(0.0, base * rough * fatigue_gain_mult * load_mult)

    return {
        "energy": max(0, int(round(energy_exact))),
        "fatigue": max(0, int(round(fatigue_exact))),
        "energy_exact": round(energy_exact, 4),  # type: ignore[dict-item]
        "fatigue_exact": round(fatigue_exact, 4),  # type: ignore[dict-item]
        "mana": 0,
        "terrain_mult": tmult,  # type: ignore[dict-item]
        "fatigue_stamina_mult": fat_mult,  # type: ignore[dict-item]
    }


def regen_deltas(
    *,
    minutes: int,
    kind: str = "wait",
    max_energy: int = BASE_ENERGY,
    max_mana: int = 0,
    max_fatigue: int = BASE_FATIGUE_CAP,
    energy: int = 0,
    mana: int = 0,
    fatigue: int = 0,
    stats: dict[str, Any] | None = None,
) -> dict[str, int]:
    """
    Returns deltas to *apply* (energy/mana positive = restore; fatigue positive = reduce fatigue).
    Caller applies: energy+=d_e, mana+=d_m, fatigue-=d_f
    """
    minutes = max(0, _int(minutes, 0))
    kind_l = str(kind or "wait").strip().lower()
    if kind_l in {"meditate", "meditation", "cultivate", "breathe"}:
        kind_l = "meditate"
    elif kind_l in {"sleep", "rest", "nap", "dawn", "until_dawn"}:
        kind_l = "sleep"
    else:
        kind_l = "wait"

    mods = attr_mods(stats)
    con_factor = 1.0 + 0.1 * mods["con_mod"]
    mana_ok = max_mana > 0

    if kind_l == "meditate":
        d_e = minutes / 12.0 * con_factor
        d_m = (minutes / 10.0 * con_factor) if mana_ok else 0.0
        d_f = minutes / 25.0 * con_factor
    elif kind_l == "sleep":
        if minutes >= 360:
            d_e = max(max_energy * 0.85, minutes / 8.0)
            d_m = ((max_mana * 0.7) + minutes / 15.0) if mana_ok else 0.0
            d_f = max(max_fatigue * 0.6, minutes / 12.0 * con_factor)
        else:
            d_e = minutes / 10.0 * con_factor
            d_m = (minutes / 16.0 * con_factor) if mana_ok else 0.0
            d_f = minutes / 20.0 * con_factor
    else:
        d_e = minutes / 18.0 * con_factor
        d_m = (minutes / 28.0 * con_factor) if mana_ok else 0.0
        d_f = minutes / 45.0 * con_factor

    # Don't overshoot caps in delta form
    d_e = min(d_e, max(0, max_energy - energy))
    d_m = min(d_m, max(0, max_mana - mana)) if mana_ok else 0.0
    d_f = min(d_f, max(0, fatigue))

    return {
        "energy": max(0, int(round(d_e))),
        "mana": max(0, int(round(d_m))),
        "fatigue": max(0, int(round(d_f))),  # amount to subtract from fatigue
        # Unrounded, for the carry ledger (playtest #80): a 6-minute talk is a
        # third of a point, which rounding would throw away every time.
        "energy_exact": round(max(0.0, d_e), 4),  # type: ignore[dict-item]
        "mana_exact": round(max(0.0, d_m), 4),  # type: ignore[dict-item]
        "fatigue_exact": round(max(0.0, d_f), 4),  # type: ignore[dict-item]
        "kind": kind_l,  # type: ignore[dict-item]
    }


def fatigue_band(fatigue: int, max_fatigue: int) -> str:
    """How full the fatigue bar is, on its own (the Fatigue stat's label)."""
    ratio = fatigue_fill_ratio(fatigue, max_fatigue)
    return "critical" if ratio >= 1.0 else "heavy" if ratio >= 0.75 else "tired" if ratio >= 0.5 else "fresh"


def condition_band(energy: int, max_energy: int, fatigue: int, max_fatigue: int) -> str:
    """The player's one overall condition: empty energy or a full fatigue bar is critical.

    Playtest #80: resources.band read fatigue only and collapse.band read energy
    too, so the same turn told the model "fresh" and "critical" at 0 energy.
    Both now come from here; the fatigue-only reading is fatigue_band.
    """
    if _int(energy, 0) <= 0:
        return "critical"
    return fatigue_band(fatigue, max_fatigue)


def normalize_resource_row(row: dict[str, Any] | None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a full resources dict from a player row (+ options for caps)."""
    row = row if isinstance(row, dict) else {}
    caps = default_resource_caps(options, player=row, stats=row.get("effective_stats") if isinstance(row.get("effective_stats"), dict) else None)
    max_energy = max(caps["max_energy"], _int(row.get("max_energy"), caps["max_energy"]))
    max_mana = caps["max_mana"] if magic_allows_mana(str((options or {}).get("magic_level") or ""), options) else 0
    if row.get("max_mana") is not None and magic_allows_mana(str((options or {}).get("magic_level") or ""), options):
        max_mana = max(0, _int(row.get("max_mana"), max_mana))
    max_fatigue = max(caps["max_fatigue"], _int(row.get("max_fatigue"), caps["max_fatigue"]))

    energy = _int(row.get("energy"), max_energy)
    mana = _int(row.get("mana"), max_mana)
    fatigue = _int(row.get("fatigue"), 0)

    energy = _clamp(energy, 0, max_energy)
    mana = _clamp(mana, 0, max(0, max_mana))
    fatigue = _clamp(fatigue, 0, max_fatigue)

    ratio = fatigue_fill_ratio(fatigue, max_fatigue)
    return {
        "energy": energy,
        "max_energy": max_energy,
        "mana": mana,
        "max_mana": max_mana,
        "fatigue": fatigue,
        "max_fatigue": max_fatigue,
        "life_force": caps.get("life_force", 0),
        "fatigue_ratio": round(ratio, 3),
        "fatigue_stamina_mult": round(fatigue_stamina_mult(fatigue, max_fatigue), 3),
        "mana_enabled": max_mana > 0,
        "band": condition_band(energy, max_energy, fatigue, max_fatigue),
        "fatigue_band": fatigue_band(fatigue, max_fatigue),
    }


def get_player_resources(conn, options: dict[str, Any] | None = None) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    data = dict(row) if row is not None else {}
    # sqlite Row → dict
    try:
        data = {k: data[k] for k in data.keys()}
    except Exception:
        data = dict(data) if data else {}
    return normalize_resource_row(data, options)


def set_player_resources(
    conn,
    *,
    energy: int | None = None,
    max_energy: int | None = None,
    mana: int | None = None,
    max_mana: int | None = None,
    fatigue: int | None = None,
    max_fatigue: int | None = None,
) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    if not row:
        return {}
    cur = {k: row[k] for k in row.keys()}
    me = _int(max_energy, _int(cur.get("max_energy"), BASE_ENERGY))
    mm = _int(max_mana, _int(cur.get("max_mana"), 0))
    mf = _int(max_fatigue, _int(cur.get("max_fatigue"), BASE_FATIGUE_CAP))
    e = _clamp(_int(energy, _int(cur.get("energy"), me)), 0, max(1, me))
    m = _clamp(_int(mana, _int(cur.get("mana"), 0)), 0, max(0, mm))
    f = _clamp(_int(fatigue, _int(cur.get("fatigue"), 0)), 0, max(1, mf))
    conn.execute(
        """
        UPDATE player SET
          energy = ?, max_energy = ?,
          mana = ?, max_mana = ?,
          fatigue = ?, max_fatigue = ?
        WHERE id = 1
        """,
        (e, me, m, mm, f, mf),
    )
    return {
        "energy": e,
        "max_energy": me,
        "mana": m,
        "max_mana": mm,
        "fatigue": f,
        "max_fatigue": mf,
    }


def seed_player_resources(conn, options: dict[str, Any] | None = None, player: dict[str, Any] | None = None) -> dict[str, Any]:
    caps = default_resource_caps(options, player=player)
    return set_player_resources(
        conn,
        energy=caps["max_energy"],
        max_energy=caps["max_energy"],
        mana=caps["max_mana"],
        max_mana=caps["max_mana"],
        fatigue=0,
        max_fatigue=caps["max_fatigue"],
    )


def ensure_player_resources(
    conn,
    options: dict[str, Any] | None = None,
    *,
    player: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Raise resource caps to formula minimums (migration / mid-run growth).
    Does not lower current pools; fills mana to max when first enabling mana.
    """
    row = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    if not row:
        return {}
    cur = {k: row[k] for k in row.keys()}
    if isinstance(player, dict):
        cur = {**cur, **{k: v for k, v in player.items() if v is not None}}
    if stats is None and isinstance(cur.get("effective_stats"), dict):
        # effective_stats is an equipment bonus map, not a 1..30 score.
        from app.skill_checks import scores_from_gear_bonuses

        stats = scores_from_gear_bonuses(cur.get("effective_stats"))
    caps = default_resource_caps(options, player=cur, stats=stats)

    me = max(_int(cur.get("max_energy"), 0), caps["max_energy"])
    mm = max(_int(cur.get("max_mana"), 0), caps["max_mana"])
    mf = max(_int(cur.get("max_fatigue"), 0), caps["max_fatigue"])

    prev_me = _int(cur.get("max_energy"), 0)
    prev_mm = _int(cur.get("max_mana"), 0)
    e = _int(cur.get("energy"), me)
    m = _int(cur.get("mana"), 0)
    f = _int(cur.get("fatigue"), 0)

    # Fresh migrate: energy left at 0 with default max only if never played — leave as-is if spent.
    if prev_me <= 0 and e <= 0:
        e = me
    # First time mana becomes available: start full.
    if prev_mm <= 0 and mm > 0 and m <= 0:
        m = mm

    e = _clamp(e, 0, me)
    m = _clamp(m, 0, max(0, mm))
    f = _clamp(f, 0, mf)
    set_player_resources(
        conn,
        energy=e,
        max_energy=me,
        mana=m,
        max_mana=mm,
        fatigue=f,
        max_fatigue=mf,
    )
    return get_player_resources(conn, options)


def spend_resources(
    conn,
    *,
    energy: int = 0,
    mana: int = 0,
    fatigue: int = 0,
    health: int = 0,
    options: dict[str, Any] | None = None,
    hard_block: bool = False,
) -> dict[str, Any]:
    """
    Apply spends. fatigue here is fatigue *gain*.
    health is optional HP loss (powers).
    """
    before = get_player_resources(conn, options)
    need_e = max(0, _int(energy, 0))
    need_m = max(0, _int(mana, 0))
    gain_f = max(0, _int(fatigue, 0))
    lose_h = max(0, _int(health, 0))

    blocked = False
    reasons: list[str] = []
    if need_e > before["energy"]:
        reasons.append("insufficient_energy")
        blocked = True
    if need_m > before["mana"]:
        reasons.append("insufficient_mana")
        blocked = True
    if lose_h:
        row = conn.execute("SELECT health FROM player WHERE id = 1").fetchone()
        hp = _int(row["health"] if row else 0, 0)
        if lose_h > hp:
            reasons.append("insufficient_health")
            blocked = True

    if blocked and hard_block:
        return {"ok": False, "blocked": True, "reasons": reasons, "before": before, "after": before}

    # Soft: spend what we can / allow injury path
    new_e = max(0, before["energy"] - need_e)
    new_m = max(0, before["mana"] - need_m)
    new_f = min(before["max_fatigue"], before["fatigue"] + gain_f)
    after = set_player_resources(
        conn,
        energy=new_e,
        max_energy=before["max_energy"],
        mana=new_m,
        max_mana=before["max_mana"],
        fatigue=new_f,
        max_fatigue=before["max_fatigue"],
    )
    health_after = None
    if lose_h:
        row = conn.execute("SELECT health, max_health FROM player WHERE id = 1").fetchone()
        if row:
            hp = max(0, _int(row["health"], 0) - lose_h)
            conn.execute("UPDATE player SET health = ? WHERE id = 1", (hp,))
            health_after = hp

    full = get_player_resources(conn, options)
    return {
        "ok": not (blocked and hard_block),
        "blocked": blocked and hard_block,
        "soft_blocked": blocked and not hard_block,
        "reasons": reasons,
        "before": before,
        "after": full,
        "deltas": {"energy": -need_e, "mana": -need_m, "fatigue": gain_f, "health": -lose_h if lose_h else 0},
        "health_after": health_after,
    }


# --- fractional carry ledger (playtest #80) ----------------------------------
#
# Pools are whole numbers, but a 5-minute street walk costs about a fifth of a
# point and a 6-minute talk restores a third. Rounding each one on its own made
# every short walk cost 1 (the old floor) or 0, and made light activity restore
# nothing. Every spend and restore of energy, fatigue and mana goes through this
# one ledger: the sub-point remainder is kept in settings and only whole points
# move the pools. Positive = spend energy/mana or gain fatigue; negative = restore.

RESOURCE_CARRY_KEY = "resource_carry"


def load_resource_carry(conn) -> dict[str, float]:
    """The stored sub-point remainders; a missing key (older saves) reads as zero."""
    carry = {"energy": 0.0, "fatigue": 0.0, "mana": 0.0}
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (RESOURCE_CARRY_KEY,)).fetchone()
        raw = json.loads(row[0]) if row is not None and row[0] else {}
    except Exception:
        raw = {}
    if isinstance(raw, dict):
        for key in carry:
            carry[key] = max(-0.9999, min(0.9999, _float(raw.get(key), 0.0)))
    return carry


def save_resource_carry(conn, carry: dict[str, float]) -> None:
    value = json.dumps({k: round(_float(v, 0.0), 4) for k, v in (carry or {}).items()})
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (RESOURCE_CARRY_KEY, value),
    )


def _settle(carry: float, amount: float) -> tuple[int, float]:
    total = _float(carry, 0.0) + _float(amount, 0.0)
    whole = int(math.floor(total + 1e-9)) if total >= 0 else -int(math.floor(-total + 1e-9))
    return whole, round(total - whole, 4)


def settle_resource_carry(
    conn,
    *,
    energy: float = 0.0,
    fatigue: float = 0.0,
    mana: float = 0.0,
    write: bool = True,
) -> dict[str, Any]:
    """Whole points to move now for these exact amounts, keeping the remainder.

    write=False previews (the travel hard-block gate) without touching the ledger.
    """
    carry = load_resource_carry(conn)
    out: dict[str, Any] = {}
    new_carry = dict(carry)
    for key, amount in (("energy", energy), ("fatigue", fatigue), ("mana", mana)):
        whole, rest = _settle(carry[key], amount)
        out[key] = whole
        new_carry[key] = rest
    if write:
        save_resource_carry(conn, new_carry)
    out["carry"] = new_carry
    return out


def apply_regen(
    conn,
    *,
    minutes: int,
    kind: str = "wait",
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    before = get_player_resources(conn, options)
    d = regen_deltas(
        minutes=minutes,
        kind=kind,
        max_energy=before["max_energy"],
        max_mana=before["max_mana"],
        max_fatigue=before["max_fatigue"],
        energy=before["energy"],
        mana=before["mana"],
        fatigue=before["fatigue"],
    )
    # Restores go through the carry ledger, so short rests add up (playtest #80).
    settled = settle_resource_carry(
        conn,
        energy=-_float(d.get("energy_exact"), d["energy"]),
        mana=-_float(d.get("mana_exact"), d["mana"]),
        fatigue=-_float(d.get("fatigue_exact"), d["fatigue"]),
    )
    gain_e = max(0, -int(settled["energy"]))
    gain_m = max(0, -int(settled["mana"]))
    ease_f = max(0, -int(settled["fatigue"]))
    after = set_player_resources(
        conn,
        energy=before["energy"] + gain_e,
        max_energy=before["max_energy"],
        mana=before["mana"] + gain_m,
        max_mana=before["max_mana"],
        fatigue=max(0, before["fatigue"] - ease_f),
        max_fatigue=before["max_fatigue"],
    )
    full = get_player_resources(conn, options)
    return {
        "ok": True,
        "kind": d.get("kind") or kind,
        "minutes": minutes,
        "before": before,
        "after": full,
        "deltas": {
            "energy": full["energy"] - before["energy"],
            "mana": full["mana"] - before["mana"],
            "fatigue": full["fatigue"] - before["fatigue"],
        },
    }


def preview_travel_spend(
    conn,
    *,
    terrain: str = "",
    minutes: int = 0,
    load_ratio: float = 0.4,
    weather_mult: float = 1.0,
    options: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    hard_block: bool | None = None,
) -> dict[str, Any]:
    """What a walk of ``minutes`` would cost, and whether it is blocked. Writes nothing.

    apply_travel_spend spends exactly this when it is not blocked; a town walk
    previews first so a block leaves the position and the clock untouched
    (docs/TownGrid.md 4.3).
    """
    cfg = resource_settings(options)
    if hard_block is None:
        hard_block = bool(cfg.get("travel_hard_block"))
    scale = float(cfg.get("drain_scale") or 1.0)

    before = get_player_resources(conn, options)
    col = collapse_state(before)
    delta = travel_resource_delta(
        terrain=terrain,
        minutes=minutes,
        load_ratio=load_ratio,
        weather_mult=weather_mult * (float(col.get("action_cost_mult") or 1.0) if cfg.get("collapse_at_full_fatigue") else 1.0),
        fatigue=before["fatigue"],
        max_fatigue=before["max_fatigue"],
        stats=stats,
    )
    # drain_scale applies to the exact cost; the whole points due now come from
    # the carry ledger, so a run of short street walks adds up to its real cost
    # instead of 1 each (playtest #80). This is a preview: the ledger is unchanged.
    delta = dict(delta)
    delta["energy_exact"] = round(_float(delta.get("energy_exact"), delta.get("energy") or 0) * scale, 4)
    delta["fatigue_exact"] = round(_float(delta.get("fatigue_exact"), delta.get("fatigue") or 0) * scale, 4)
    settled = settle_resource_carry(conn, energy=delta["energy_exact"], fatigue=delta["fatigue_exact"], write=False)
    delta["energy"] = max(0, int(settled["energy"]))
    delta["fatigue"] = max(0, int(settled["fatigue"]))
    delta["carry_after"] = settled["carry"]

    need_e = int(delta.get("energy") or 0)
    if hard_block and need_e > before["energy"]:
        return {
            "ok": False,
            "blocked": True,
            "soft_blocked": False,
            "reasons": ["insufficient_energy"] + (["zero_energy"] if before["energy"] <= 0 else []),
            "before": before,
            "after": before,
            "deltas": {"energy": 0, "mana": 0, "fatigue": 0, "health": 0},
            "travel": delta,
            "collapse": col,
        }
    return {"ok": True, "blocked": False, "reasons": [], "before": before, "travel": delta, "collapse": col}


def apply_travel_spend(
    conn,
    *,
    terrain: str = "",
    minutes: int = 0,
    load_ratio: float = 0.4,
    weather_mult: float = 1.0,
    options: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    hard_block: bool | None = None,
) -> dict[str, Any]:
    preview = preview_travel_spend(
        conn,
        terrain=terrain,
        minutes=minutes,
        load_ratio=load_ratio,
        weather_mult=weather_mult,
        options=options,
        stats=stats,
        hard_block=hard_block,
    )
    if preview["blocked"]:
        return preview
    before = preview["before"]
    delta = preview["travel"]
    need_e = int(delta.get("energy") or 0)
    if isinstance(delta.get("carry_after"), dict):
        save_resource_carry(conn, delta["carry_after"])

    result = spend_resources(
        conn,
        energy=need_e,
        fatigue=int(delta.get("fatigue") or 0),
        mana=0,
        options=options,
        hard_block=False,
    )
    after = result.get("after") or get_player_resources(conn, options)
    return result | {"travel": delta, "collapse": collapse_state(after), "ok": True, "blocked": False}


def resources_prompt_block(resources: dict[str, Any] | None) -> str:
    if not isinstance(resources, dict):
        return ""
    lines = [
        "Player resources (server truth):",
        f"- Energy/stamina: {resources.get('energy')}/{resources.get('max_energy')}",
        f"- Fatigue: {resources.get('fatigue')}/{resources.get('max_fatigue')} (band={resources.get('fatigue_band') or resources.get('band')}; stamina mult×{resources.get('fatigue_stamina_mult')})",
        f"- Condition: {resources.get('band')}",
    ]
    if resources.get("mana_enabled") or _int(resources.get("max_mana"), 0) > 0:
        lines.append(f"- Mana/focus: {resources.get('mana')}/{resources.get('max_mana')}")
    else:
        lines.append("- Mana/focus: unavailable in this world (max 0).")
    lines.append(
        "Travel/wait/meditate/sleep may already have changed these this beat if mechanics_context.resources is set. "
        "Do not invent free long rests. Do not cast magic that needs mana when mana is 0."
    )
    return "\n".join(lines)


# --- power cost stamping + use gating (PR2) -----------------------------------

WORLD_DAY_MINUTES = 24 * 60


def estimate_power_tier(ability: dict[str, Any] | None) -> str:
    try:
        from app.llm import estimate_ability_opening_strength

        return estimate_ability_opening_strength(ability)
    except Exception:
        return "moderate"


def parse_resource_cost(value: Any) -> dict[str, Any]:
    """Normalize resource_cost from dict/json/string into a clean cost dict."""
    if isinstance(value, str) and value.strip():
        try:
            value = json.loads(value)
        except Exception:
            value = {}
    if not isinstance(value, dict):
        value = {}
    debuffs = value.get("debuffs") if isinstance(value.get("debuffs"), list) else []
    clean_debuffs: list[Any] = []
    for d in debuffs[:8]:
        if isinstance(d, str) and d.strip():
            clean_debuffs.append(d.strip()[:80])
        elif isinstance(d, dict) and (d.get("name") or d.get("summary")):
            clean_debuffs.append(
                {
                    "name": str(d.get("name") or d.get("summary") or "debuff")[:80],
                    "summary": str(d.get("summary") or "")[:200],
                    "minutes": max(0, _int(d.get("minutes"), 0)),
                }
            )
    return {
        "energy": max(0, _int(value.get("energy"), 0)),
        "mana": max(0, _int(value.get("mana"), 0)),
        "fatigue": max(0, _int(value.get("fatigue"), 0)),
        "health": max(0, _int(value.get("health"), 0)),
        "cooldown_minutes": max(0, _int(value.get("cooldown_minutes"), 0)),
        "debuffs": clean_debuffs,
    }


def format_resource_cost(cost: dict[str, Any] | None) -> str:
    """Human-readable cost line for UI / cost field."""
    c = parse_resource_cost(cost)
    parts: list[str] = []
    if c["energy"]:
        parts.append(f"{c['energy']} energy")
    if c["mana"]:
        parts.append(f"{c['mana']} mana")
    if c["fatigue"]:
        parts.append(f"+{c['fatigue']} fatigue")
    if c["health"]:
        parts.append(f"{c['health']} health")
    if c["cooldown_minutes"]:
        mins = c["cooldown_minutes"]
        if mins >= 60 and mins % 60 == 0:
            parts.append(f"{mins // 60}h cooldown")
        else:
            parts.append(f"{mins}m cooldown")
    for d in c.get("debuffs") or []:
        if isinstance(d, str):
            parts.append(f"debuff: {d}")
        elif isinstance(d, dict) and d.get("name"):
            parts.append(f"debuff: {d['name']}")
    return "; ".join(parts) if parts else "no resource cost"


def merge_text_cost(cost: dict[str, Any] | None, text: Any) -> dict[str, Any]:
    """The structured cost raised to every amount the free-text cost states.

    One reader for "2 energy; 3 mana; 30-minute cooldown", used by
    stamp_resource_cost and by llm.py when it rewrites an ability's cost, so the
    card text and the charged cost cannot disagree (playtest #80).
    """
    out = parse_resource_cost(cost)
    text_cost = str(text or "").lower()
    m = re.search(r"\b(\d+)\s*mana\b", text_cost)
    if m:
        out["mana"] = max(out["mana"], _int(m.group(1), 0))
    m = re.search(r"\b(\d+)\s*(energy|stamina)\b", text_cost)
    if m:
        out["energy"] = max(out["energy"], _int(m.group(1), 0))
    m = re.search(r"\b(\d+)\s*(hp|health|life)\b", text_cost)
    if m:
        out["health"] = max(out["health"], _int(m.group(1), 0))
    m = re.search(r"\+?\b(\d+)\s*fatigue\b", text_cost)
    if m:
        out["fatigue"] = max(out["fatigue"], _int(m.group(1), 0))
    # "30m cooldown", "30 min cooldown" and the hyphenated "30-minute cooldown"
    # llm.py writes, which the old pattern missed.
    m = re.search(r"\b(\d+)[\s-]*m(in(ute)?s?)?[\s-]*cooldown\b", text_cost)
    if m:
        out["cooldown_minutes"] = max(out["cooldown_minutes"], _int(m.group(1), 0))
    m = re.search(r"\b(\d+)[\s-]*h(ou)?r?s?[\s-]*cooldown\b", text_cost)
    if m:
        out["cooldown_minutes"] = max(out["cooldown_minutes"], _int(m.group(1), 0) * 60)
    return out


def stamp_resource_cost(
    ability: dict[str, Any] | None,
    *,
    magic_ok: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    """Ensure ability has a structured resource_cost scaled to power tier."""
    if not isinstance(ability, dict):
        return {}
    out = dict(ability)
    existing = parse_resource_cost(out.get("resource_cost"))
    has_existing = any(existing[k] for k in ("energy", "mana", "fatigue", "health", "cooldown_minutes")) or bool(
        existing.get("debuffs")
    )

    tier = estimate_power_tier(out)
    blob = f"{out.get('name') or ''} {out.get('description') or ''} {out.get('cost') or ''}".lower()
    cost = dict(existing)

    # The card's own cost text is always read and merged field by field
    # (playtest #80). It used to be read only when the structured cost was
    # empty, so a stored cost holding just a cooldown hid "2 energy; 3 mana"
    # and the power was used for free. Runs on every read, so stored rows are
    # corrected at use time without a migration.
    cost = merge_text_cost(cost, out.get("cost"))

    # If empty (or force), stamp from fiction + tier
    if force or not has_existing:
        if not any(cost[k] for k in ("energy", "mana", "fatigue", "health", "cooldown_minutes")):
            magic_words = (
                "spell", "mana", "arcane", "cultivat", "magic", "focus", "system",
                "cantrip", "incant", "enchant", "sorcer", "wizard", "cast ",
                "glow", "candle", "light a", "ignite", "conjure", "channel",
            )
            physical_words = (
                "strike", "slash", "dash", "climb", "shield", "physical",
                "punch", "kick", "grapple", "sprint", "parry", "blade",
            )
            if magic_ok and any(w in blob for w in magic_words):
                cost["mana"] = 1 if tier == "mild" else 4 if tier == "moderate" else 8
                cost["energy"] = 0 if tier == "mild" else 1
            elif any(w in blob for w in physical_words):
                cost["energy"] = 2 if tier == "mild" else 4 if tier == "moderate" else 6
                cost["fatigue"] = 0 if tier == "mild" else 1
            else:
                cost["energy"] = 1 if tier == "mild" else 2
                if magic_ok and tier != "mild":
                    cost["mana"] = 1

            if any(w in blob for w in ("blood", "life force", "soul-burn", "soul burn")):
                cost["health"] = 1 if tier != "strong" else 2

            # Cooldowns proportional to power — never week for mild
            if tier == "mild":
                cost["cooldown_minutes"] = 0
            elif tier == "moderate" and any(w in blob for w in ("rare", "oath", "battlefield")):
                cost["cooldown_minutes"] = 60
            elif tier == "strong":
                cost["cooldown_minutes"] = 180 if "ritual" not in blob else 360

    # Clamp absurd CDs
    if tier == "mild" and cost["cooldown_minutes"] > 60:
        cost["cooldown_minutes"] = 0
    if tier == "moderate" and cost["cooldown_minutes"] > 24 * 60:
        cost["cooldown_minutes"] = 6 * 60
    if tier != "strong" and cost["cooldown_minutes"] >= 7 * 24 * 60:
        cost["cooldown_minutes"] = 24 * 60
    if not magic_ok and cost["mana"] > 0:
        cost["energy"] = max(cost["energy"], cost["mana"])
        cost["mana"] = 0
    if str(out.get("power_type") or "").lower() == "passive":
        cost = {"energy": 0, "mana": 0, "fatigue": 0, "health": 0, "cooldown_minutes": 0, "debuffs": []}

    cost = parse_resource_cost(cost)
    out["resource_cost"] = cost
    out["_power_tier"] = tier
    # Fill empty free-text cost from structured cost for display
    free = str(out.get("cost") or "").strip().lower()
    if not free or free in {"no cost", "model decides", "none", "n/a", "[]"}:
        out["cost"] = format_resource_cost(cost)
    return out


def stamp_abilities(
    abilities: list[dict[str, Any]] | None,
    *,
    magic_ok: bool = True,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ab in abilities or []:
        if isinstance(ab, dict):
            out.append(stamp_resource_cost(ab, magic_ok=magic_ok))
    return diversify_resource_costs(out, magic_ok=magic_ok)


def resource_cost_fingerprint(cost: dict[str, Any] | None) -> str:
    c = parse_resource_cost(cost)
    # Bucket cooldowns so 30 vs 45 still diversify if other axes match
    cd = c["cooldown_minutes"]
    if cd <= 0:
        cd_b = "0"
    elif cd <= 15:
        cd_b = "15"
    elif cd <= 60:
        cd_b = "60"
    elif cd <= 180:
        cd_b = "180"
    else:
        cd_b = "long"
    deb = 1 if c.get("debuffs") else 0
    return f"e{c['energy']}-m{c['mana']}-f{c['fatigue']}-h{c['health']}-cd{cd_b}-d{deb}"


def diversify_resource_costs(
    abilities: list[dict[str, Any]] | None,
    *,
    magic_ok: bool = True,
    force: bool = False,
) -> list[dict[str, Any]]:
    """
    Ensure multi-ability batches do not share the same resource_cost shape.
    Rotates through tier-appropriate shape pools. Also refreshes free-text cost.
    """
    if not isinstance(abilities, list) or not abilities:
        return []
    stamped = [stamp_resource_cost(a, magic_ok=magic_ok) if isinstance(a, dict) else a for a in abilities]
    if len([a for a in stamped if isinstance(a, dict)]) < 2 and not force:
        # Still normalize cost text
        out_single: list[dict[str, Any]] = []
        for a in stamped:
            if isinstance(a, dict):
                a = dict(a)
                a["cost"] = format_resource_cost(a.get("resource_cost"))
                out_single.append(a)
        return out_single if out_single else list(stamped)  # type: ignore[arg-type]

    seen: set[str] = set()
    pool_idx = {"mild": 0, "moderate": 0, "strong": 0}
    out: list[dict[str, Any]] = []
    for ab in stamped:
        if not isinstance(ab, dict):
            continue
        next_ab = dict(ab)
        if str(next_ab.get("power_type") or "").lower() == "passive":
            next_ab["resource_cost"] = parse_resource_cost({})
            next_ab["cost"] = format_resource_cost(next_ab["resource_cost"])
            out.append(next_ab)
            continue

        cost = parse_resource_cost(next_ab.get("resource_cost"))
        if not magic_ok and cost["mana"] > 0:
            cost["energy"] = max(cost["energy"], cost["mana"])
            cost["mana"] = 0
        fp = resource_cost_fingerprint(cost)
        tier = str(next_ab.get("_power_tier") or estimate_power_tier(next_ab) or "moderate")
        if tier not in pool_idx:
            tier = "moderate"
        shapes = (
            RESOURCE_COST_SHAPES_MILD
            if tier == "mild"
            else RESOURCE_COST_SHAPES_STRONG
            if tier == "strong"
            else RESOURCE_COST_SHAPES_MODERATE
        )
        if fp in seen or (force and fp in seen):
            # Find a shape not yet used
            picked = None
            for _ in range(len(shapes) + 2):
                cand = dict(shapes[pool_idx[tier] % len(shapes)])
                pool_idx[tier] += 1
                if not magic_ok and cand.get("mana", 0) > 0:
                    cand["energy"] = max(int(cand.get("energy") or 0), int(cand.get("mana") or 0))
                    cand["mana"] = 0
                cand = parse_resource_cost(cand)
                cfp = resource_cost_fingerprint(cand)
                if cfp not in seen:
                    picked = cand
                    fp = cfp
                    break
            if picked is None:
                # Force uniqueness with a small energy bump
                cost = parse_resource_cost(cost)
                cost["energy"] = int(cost["energy"]) + 1 + len(seen)
                cost["cooldown_minutes"] = int(cost["cooldown_minutes"]) + 5 * (len(seen) + 1)
                if not magic_ok:
                    cost["mana"] = 0
                picked = parse_resource_cost(cost)
                fp = resource_cost_fingerprint(picked)
            cost = picked
            next_ab["resource_cost"] = cost
            next_ab["cost"] = format_resource_cost(cost)
            next_ab["_resource_cost_diversified"] = True
        else:
            next_ab["resource_cost"] = cost
            free = str(next_ab.get("cost") or "").strip().lower()
            if not free or free in {"no cost", "model decides", "none", "n/a", "[]"} or next_ab.get("_cost_diversified"):
                next_ab["cost"] = format_resource_cost(cost)
        if fp:
            seen.add(fp)
        out.append(next_ab)
    return out


def resource_settings(options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge DEFAULT_RESOURCE_SETTINGS with playthrough_options.resource_settings."""
    opts = options if isinstance(options, dict) else {}
    raw = opts.get("resource_settings") if isinstance(opts.get("resource_settings"), dict) else {}
    # Also allow flat keys on options
    merged = dict(DEFAULT_RESOURCE_SETTINGS)
    for k in DEFAULT_RESOURCE_SETTINGS:
        if k in opts and opts[k] is not None:
            merged[k] = opts[k]
        if k in raw and raw[k] is not None:
            merged[k] = raw[k]
    try:
        merged["drain_scale"] = max(0.25, min(3.0, float(merged.get("drain_scale") or 1.0)))
    except (TypeError, ValueError):
        merged["drain_scale"] = 1.0
    for flag in (
        "travel_hard_block",
        "collapse_at_full_fatigue",
        "action_energy_enabled",
        "zero_energy_blocks_physical",
    ):
        merged[flag] = bool(merged.get(flag))
    return merged


def collapse_state(resources: dict[str, Any] | None) -> dict[str, Any]:
    """Soft-collapse effects when exhausted (energy empty / fatigue full)."""
    res = resources if isinstance(resources, dict) else {}
    energy = _int(res.get("energy"), 0)
    max_e = max(1, _int(res.get("max_energy"), BASE_ENERGY))
    fatigue = _int(res.get("fatigue"), 0)
    max_f = max(1, _int(res.get("max_fatigue"), BASE_FATIGUE_CAP))
    ratio = fatigue_fill_ratio(fatigue, max_f)
    band = condition_band(energy, max_e, fatigue, max_f)  # the same band resources carry (playtest #80)
    effects: list[str] = []
    action_mult = 1.0
    if energy <= 0:
        effects.append("zero_energy")
        action_mult = max(action_mult, 1.5)
    if ratio >= 1.0:
        effects.append("full_fatigue")
        action_mult = max(action_mult, 1.75)
    elif ratio >= 0.75:
        effects.append("heavy_fatigue")
        action_mult = max(action_mult, 1.25)
    if energy <= max(1, max_e // 10) and energy > 0:
        effects.append("low_energy")
        action_mult = max(action_mult, 1.15)
    return {
        "band": band,
        "effects": effects,
        "action_cost_mult": round(action_mult, 3),
        "blocks_physical": energy <= 0,
        "needs_rest": energy <= 0 or ratio >= 1.0,
        "energy": energy,
        "fatigue_ratio": round(ratio, 3),
    }


# Kinds that cost nothing and let the body recover at the waiting rate over
# their minutes (playtest #80): talking in a shop is not exertion.
LIGHT_ACTION_KINDS = frozenset({"none", "talk", "rest", "wait", "sleep", "meditate"})


def action_kind_from_text(player_input: str) -> str:
    text = (player_input or "").lower().strip()
    if not text or text.startswith("__"):
        return "none"
    if re.search(r"\b(attack|fight|combat|chase|flee|strike|slash|punch|kick)\b", text):
        return "combat"
    if re.search(r"\b(cast|spell|invoke|channel|ability|power)\b", text):
        return "ability"
    # A declared act is costed by the same reading that rolls its check
    # (playtest #85a: "i polish the blades" was "general", 0.4 energy, like a
    # glance, because polish was in the act table and not in this one).
    try:
        from app.prose_state import act_rules

        act = act_rules(player_input)
    except Exception:
        act = None
    if act:
        return str(act["kind"])
    # Hands-on labour is physical work, not study: "fix a rusty sword" at a
    # forge was costed as nothing at 0 energy (playtest #80). Verbs only: the
    # noun "Forge" is a shop name ("I go into Blind Owl Forge").
    if re.search(r"\b(fix|fixing|mend|mending|repair|repairing|forging|smithing|hammering|dig|digging|chop|chopping|haul|hauling|lift|lifting)\b", text):
        return "physical"
    if re.search(r"\b(search|investigate|examine|study|read|craft|forage)\b", text):
        return "investigate"
    if re.search(r"\b(talk|ask|speak|persuade|negotiate|lie|intimidate|greet|chat)\b", text):
        return "talk"
    if re.search(r"\b(sneak|hide|climb|swim|force|break|lockpick|steal)\b", text):
        return "physical"
    if re.search(r"\b(train|practice|drill|exercise)\b", text):
        return "train"
    if re.search(r"\b(rest|sleep|meditat|eat|drink|bandage|wait)\b", text):
        return "rest"
    if re.search(r"\b(walk|run|travel|go to|head toward)\b", text):
        return "travel"
    return "general"


def action_resource_delta(
    *,
    kind: str = "general",
    minutes: int = 6,
    stats: dict[str, Any] | None = None,
    fatigue: int = 0,
    max_fatigue: int = BASE_FATIGUE_CAP,
    drain_scale: float = 1.0,
    collapse_mult: float = 1.0,
) -> dict[str, int]:
    """Energy/fatigue cost for free-text action kinds (not ability-stamped costs).

    ``energy``/``fatigue`` are rounded for display; apply_action_spend charges
    ``energy_exact``/``fatigue_exact`` through the carry ledger (playtest #80).
    """
    kind_l = str(kind or "general").lower()
    if kind_l in LIGHT_ACTION_KINDS:
        return {"energy": 0, "fatigue": 0, "mana": 0, "energy_exact": 0.0, "fatigue_exact": 0.0, "kind": kind_l}  # type: ignore[dict-item]
    if kind_l == "ability":
        # Ability path spends via apply_ability_use; only tiny baseline if unmatched
        base_e, base_f = 0.0, 0.0
    elif kind_l == "combat":
        base_e, base_f = 2.0, 1.0
    elif kind_l == "physical":
        base_e, base_f = 2.0, 1.0
    elif kind_l == "train":
        base_e, base_f = 2.0, 1.0
    elif kind_l == "travel":
        # Movement energy is charged by the walk the engine actually makes
        # (_spend_travel, docs/TownGrid.md 4.3). Charging the line as well paid
        # twice, and paid for moves that never happened (playtest #80).
        base_e, base_f = 0.0, 0.0
    elif kind_l == "journey":
        # A typed move outside a town: the legacy MOVE path charges no walk,
        # so the line pays its old travel point (playtest #80 review).
        base_e, base_f = 1.0, 0.0
    else:
        # investigate / general: looking, handling, small errands. They were a
        # whole point per 6-minute beat, five times a street walk's rate, and a
        # morning of them emptied the pool (playtest #80).
        base_e, base_f = 0.4, 0.0

    mods = attr_mods(stats)
    minutes = max(0, _int(minutes, 0))
    time_factor = 1.0 + max(0, minutes - 6) / 30.0
    fat_mult = fatigue_stamina_mult(fatigue, max_fatigue)
    con_ease = max(0.7, min(1.2, 1.0 - 0.12 * mods["con_mod"]))
    scale = max(0.25, min(3.0, _float(drain_scale, 1.0))) * max(1.0, _float(collapse_mult, 1.0))

    energy_exact = max(0.0, base_e * time_factor * fat_mult * con_ease * scale)
    fatigue_exact = max(0.0, base_f * time_factor * con_ease * scale)
    # Long combat always at least 1 energy
    if kind_l == "combat" and minutes >= 5 and energy_exact < 1.0 and scale > 0:
        energy_exact = 1.0
    return {
        "energy": max(0, int(round(energy_exact))),
        "fatigue": max(0, int(round(fatigue_exact))),
        "energy_exact": round(energy_exact, 4),  # type: ignore[dict-item]
        "fatigue_exact": round(fatigue_exact, 4),  # type: ignore[dict-item]
        "mana": 0,
        "kind": kind_l,  # type: ignore[dict-item]
    }


def can_afford_energy(
    resources: dict[str, Any] | None,
    energy_cost: int,
    *,
    hard_block: bool = True,
) -> dict[str, Any]:
    res = resources if isinstance(resources, dict) else {}
    have = _int(res.get("energy"), 0)
    need = max(0, _int(energy_cost, 0))
    ok = have >= need if hard_block else True
    reasons = []
    if have < need:
        reasons.append("insufficient_energy")
    if have <= 0 and need > 0:
        reasons.append("zero_energy")
    return {"ok": ok, "have": have, "need": need, "reasons": reasons}


def apply_action_spend(
    conn,
    *,
    kind: str = "general",
    minutes: int = 6,
    options: dict[str, Any] | None = None,
    stats: dict[str, Any] | None = None,
    hard_block: bool = False,
) -> dict[str, Any]:
    """Spend energy/fatigue for a free-text action. Respects resource_settings + collapse.

    Light kinds (LIGHT_ACTION_KINDS) cost nothing and recover at the waiting
    rate over the action's minutes, through the same carry ledger as walks
    (playtest #80): a morning of talk is no longer a slow drain to zero.
    """
    cfg = resource_settings(options)
    kind = str(kind or "general").lower()
    if kind in LIGHT_ACTION_KINDS and minutes > 0:
        # A typed rest or meditation recovers at the Wait control's rate for
        # the same act; talk recovers at the waiting rate.
        regen_kind = kind if kind in {"rest", "sleep", "meditate"} else "wait"
        regen = apply_regen(conn, minutes=int(minutes), kind=regen_kind, options=options)
        after = regen.get("after") or get_player_resources(conn, options)
        return {
            "ok": True,
            "blocked": False,
            "reasons": [],
            "collapse": collapse_state(after),
            "delta": {"energy": 0, "fatigue": 0, "mana": 0, "kind": kind, "recovered": regen.get("deltas")},
            "before": regen.get("before") or after,
            "after": after,
            "deltas": regen.get("deltas"),
            "kind": kind,
        }
    if not cfg.get("action_energy_enabled"):
        before = get_player_resources(conn, options)
        return {"ok": True, "skipped": True, "before": before, "after": before, "deltas": {"energy": 0, "fatigue": 0, "mana": 0}}

    before = get_player_resources(conn, options)
    col = collapse_state(before)
    if cfg.get("zero_energy_blocks_physical") and col.get("blocks_physical"):
        # Not a town walk: that is gated by its own cost in preview_travel_spend,
        # which is the only thing that charges it (playtest #80). A journey
        # outside a town has no such walk, so it keeps the gate.
        if kind in {"combat", "physical", "train", "journey"}:
            return {
                "ok": False,
                "blocked": True,
                "reasons": ["zero_energy", "needs_rest"],
                "collapse": col,
                "before": before,
                "after": before,
                "kind": kind,
            }

    delta = action_resource_delta(
        kind=kind,
        minutes=minutes,
        stats=stats,
        fatigue=before["fatigue"],
        max_fatigue=before["max_fatigue"],
        drain_scale=float(cfg.get("drain_scale") or 1.0),
        collapse_mult=float(col.get("action_cost_mult") or 1.0) if cfg.get("collapse_at_full_fatigue") else 1.0,
    )
    settled = settle_resource_carry(
        conn,
        energy=_float(delta.get("energy_exact"), delta.get("energy") or 0),
        fatigue=_float(delta.get("fatigue_exact"), delta.get("fatigue") or 0),
        write=False,
    )
    need_e = max(0, int(settled["energy"]))
    delta = dict(delta) | {"energy": need_e, "fatigue": max(0, int(settled["fatigue"]))}
    afford = can_afford_energy(before, need_e, hard_block=hard_block and kind in {"combat", "physical", "train"})
    if not afford["ok"]:
        return {
            "ok": False,
            "blocked": True,
            "reasons": afford["reasons"],
            "collapse": col,
            "delta": delta,
            "before": before,
            "after": before,
            "kind": kind,
        }

    save_resource_carry(conn, settled["carry"])
    spend = spend_resources(
        conn,
        energy=need_e,
        fatigue=int(delta.get("fatigue") or 0),
        mana=0,
        options=options,
        hard_block=False,
    )
    after = spend.get("after") or get_player_resources(conn, options)
    return {
        "ok": True,
        "blocked": False,
        "soft_blocked": spend.get("soft_blocked"),
        "reasons": spend.get("reasons") or [],
        "collapse": collapse_state(after),
        "delta": delta,
        "before": before,
        "after": after,
        "deltas": spend.get("deltas"),
        "kind": kind,
    }


def world_abs_minutes(world_time: dict[str, Any] | None) -> int:
    wt = world_time if isinstance(world_time, dict) else {}
    day = max(1, _int(wt.get("day"), 1))
    minute = max(0, _int(wt.get("minute"), 0))
    return (day - 1) * WORLD_DAY_MINUTES + minute


def ability_cooldown_key(ability: dict[str, Any] | None) -> str:
    if not isinstance(ability, dict):
        return ""
    if ability.get("id") is not None:
        return f"id:{ability.get('id')}"
    name = str(ability.get("name") or "").strip().lower()
    return f"name:{name}" if name else ""


def load_ability_cooldowns(settings: dict[str, Any] | None) -> dict[str, Any]:
    raw = (settings or {}).get("ability_cooldowns")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except Exception:
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


def cooldown_status(
    ability: dict[str, Any] | None,
    cooldowns: dict[str, Any] | None,
    *,
    world_time: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = ability_cooldown_key(ability)
    now = world_abs_minutes(world_time)
    entry = (cooldowns or {}).get(key) if key else None
    if not isinstance(entry, dict):
        # also try by bare name
        name = str((ability or {}).get("name") or "").strip().lower()
        entry = (cooldowns or {}).get(name) if name else None
    if not isinstance(entry, dict):
        return {"ready": True, "remaining_minutes": 0, "ready_at_abs": 0, "key": key}
    ready_at = max(0, _int(entry.get("ready_at_abs"), 0))
    remaining = max(0, ready_at - now)
    return {
        "ready": remaining <= 0,
        "remaining_minutes": remaining,
        "ready_at_abs": ready_at,
        "key": key,
        "last_used_turn": entry.get("last_used_turn"),
    }


def enrich_ability_runtime(
    ability: dict[str, Any] | None,
    *,
    magic_ok: bool = True,
    cooldowns: dict[str, Any] | None = None,
    world_time: dict[str, Any] | None = None,
    resources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp cost + attach can_use / cooldown / afford for UI and mechanics."""
    if not isinstance(ability, dict):
        return {}
    out = stamp_resource_cost(ability, magic_ok=magic_ok)
    cost = parse_resource_cost(out.get("resource_cost"))
    cd = cooldown_status(out, cooldowns, world_time=world_time)
    locked = bool(out.get("locked"))
    res = resources if isinstance(resources, dict) else {}
    reasons: list[str] = []
    if locked:
        reasons.append("locked")
    if not cd["ready"]:
        reasons.append("cooldown")
    if cost["energy"] and _int(res.get("energy"), 0) < cost["energy"]:
        reasons.append("insufficient_energy")
    if cost["mana"] and _int(res.get("mana"), 0) < cost["mana"]:
        reasons.append("insufficient_mana")
    if cost["health"]:
        # health lives on player, may be passed via resources.health
        hp = _int(res.get("health"), 999)
        if hp < cost["health"]:
            reasons.append("insufficient_health")
    # Fatigue is a gain, not a spend gate (unless already at hard cap and would waste)
    out["resource_cost"] = cost
    out["cooldown"] = cd
    out["can_use"] = not reasons
    out["block_reasons"] = reasons
    return out


def match_ability_from_input(
    player_input: str,
    abilities: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Longest-name match of an ability mentioned as a whole token."""
    text = str(player_input or "").strip().lower()
    if not text or not abilities:
        return None
    candidates: list[tuple[int, dict[str, Any]]] = []
    for ab in abilities:
        if not isinstance(ab, dict):
            continue
        name = str(ab.get("name") or "").strip()
        if len(name) < 3:
            continue
        if re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", text):
            candidates.append((len(name), ab))
    if not candidates:
        # verb + "my power/ability/spell" alone → first unlocked active
        if re.search(r"\b(use|cast|activate|invoke|channel|trigger)\b.{0,40}\b(ability|power|spell|skill)\b", text):
            for ab in abilities:
                if isinstance(ab, dict) and not ab.get("locked") and str(ab.get("power_type") or "").lower() != "passive":
                    return ab
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def apply_ability_use(
    conn,
    ability: dict[str, Any] | None,
    *,
    options: dict[str, Any] | None = None,
    world_time: dict[str, Any] | None = None,
    turn: int = 0,
    hard_block: bool = True,
    settings_get=None,
    settings_set=None,
) -> dict[str, Any]:
    """
    Gate + spend resources for an ability use.
    settings_get/settings_set optional callables for cooldown persistence:
      settings_get() -> dict, settings_set(key, value)
    If omitted, cooldowns are read/written via settings table on conn.
    """
    if not isinstance(ability, dict) or not ability.get("name"):
        return {"ok": False, "blocked": True, "reasons": ["no_ability"]}

    magic_ok = magic_allows_mana(str((options or {}).get("magic_level") or ""), options)
    stamped = stamp_resource_cost(ability, magic_ok=magic_ok)
    cost = parse_resource_cost(stamped.get("resource_cost"))

    # Cooldowns
    if settings_get is None:

        def settings_get():  # type: ignore[misc]
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            out: dict[str, Any] = {}
            for r in rows:
                k = r["key"] if isinstance(r, dict) or hasattr(r, "keys") else r[0]
                v = r["value"] if isinstance(r, dict) or hasattr(r, "keys") else r[1]
                try:
                    out[str(k)] = json.loads(v) if isinstance(v, str) and v[:1] in "{[" else v
                except Exception:
                    out[str(k)] = v
            return out

    if settings_set is None:

        def settings_set(key: str, value: Any):  # type: ignore[misc]
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, json.dumps(value, ensure_ascii=True) if not isinstance(value, str) else value),
            )

    settings = settings_get() if callable(settings_get) else {}
    cds = load_ability_cooldowns(settings if isinstance(settings, dict) else {})
    cd = cooldown_status(stamped, cds, world_time=world_time)

    reasons: list[str] = []
    if bool(stamped.get("locked")):
        reasons.append("locked")
    if not cd["ready"]:
        reasons.append("cooldown")

    # Check afford before spend
    before = get_player_resources(conn, options)
    if cost["energy"] > before["energy"]:
        reasons.append("insufficient_energy")
    if cost["mana"] > before["mana"]:
        reasons.append("insufficient_mana")
    row = conn.execute("SELECT health FROM player WHERE id = 1").fetchone()
    hp = _int(row["health"] if row else 0, 0)
    if cost["health"] > hp:
        reasons.append("insufficient_health")

    if reasons and hard_block:
        return {
            "ok": False,
            "blocked": True,
            "reasons": reasons,
            "ability": stamped.get("name"),
            "cost": cost,
            "cooldown": cd,
            "before": before,
            "after": before,
        }

    # Spend pools
    spend = spend_resources(
        conn,
        energy=cost["energy"],
        mana=cost["mana"],
        fatigue=cost["fatigue"],
        health=cost["health"],
        options=options,
        hard_block=False,
    )

    # Set cooldown
    now = world_abs_minutes(world_time)
    key = ability_cooldown_key(stamped) or str(stamped.get("name") or "").lower()
    if cost["cooldown_minutes"] > 0 and key:
        cds[key] = {
            "ready_at_abs": now + cost["cooldown_minutes"],
            "last_used_turn": turn,
            "name": stamped.get("name"),
        }
        settings_set("ability_cooldowns", cds)

    # Debuffs → player_conditions
    applied_debuffs: list[dict[str, Any]] = []
    for d in cost.get("debuffs") or []:
        if isinstance(d, str):
            entry = {
                "id": f"power_{re.sub(r'[^a-z0-9]+', '_', d.lower())[:40]}_{turn}",
                "name": d[:80],
                "summary": f"From {stamped.get('name')}",
                "source": "ability",
                "ability": stamped.get("name"),
                "turn": turn,
                "minutes": 0,
            }
        elif isinstance(d, dict):
            entry = {
                "id": f"power_{re.sub(r'[^a-z0-9]+', '_', str(d.get('name') or 'debuff').lower())[:40]}_{turn}",
                "name": str(d.get("name") or "debuff")[:80],
                "summary": str(d.get("summary") or f"From {stamped.get('name')}")[:200],
                "source": "ability",
                "ability": stamped.get("name"),
                "turn": turn,
                "minutes": max(0, _int(d.get("minutes"), 0)),
            }
        else:
            continue
        applied_debuffs.append(entry)

    if applied_debuffs:
        raw = settings.get("player_conditions") if isinstance(settings, dict) else None
        existing: list[Any] = []
        if isinstance(raw, list):
            existing = list(raw)
        elif isinstance(raw, str) and raw.strip():
            try:
                existing = json.loads(raw)
            except Exception:
                existing = []
        if not isinstance(existing, list):
            existing = []
        existing.extend(applied_debuffs)
        settings_set("player_conditions", existing[-40:])

    after = get_player_resources(conn, options)
    return {
        "ok": True,
        "blocked": False,
        "soft_blocked": bool(reasons) and not hard_block,
        "reasons": reasons,
        "ability": stamped.get("name"),
        "ability_id": stamped.get("id"),
        "cost": cost,
        "cooldown": {
            "ready": False if cost["cooldown_minutes"] > 0 else True,
            "remaining_minutes": cost["cooldown_minutes"],
            "ready_at_abs": now + cost["cooldown_minutes"] if cost["cooldown_minutes"] else 0,
        },
        "debuffs": applied_debuffs,
        "before": before,
        "after": after,
        "spend": spend.get("deltas"),
        "health_after": spend.get("health_after"),
    }


def ability_use_prompt_block(use: dict[str, Any] | None) -> str:
    if not isinstance(use, dict):
        return ""
    if use.get("blocked"):
        reasons = ", ".join(use.get("reasons") or []) or "unknown"
        return (
            f"Ability use BLOCKED ({use.get('ability') or '?'}): {reasons}. "
            f"Cost would be {format_resource_cost(use.get('cost'))}. "
            "Narrate failure or inability — do not grant the power's full effect."
        )
    cost = format_resource_cost(use.get("cost"))
    d = use.get("spend") or {}
    lines = [
        f"Ability used (server resolved): {use.get('ability')}",
        f"- Cost applied: {cost}",
        f"- Spend deltas: energy {d.get('energy', 0)}, mana {d.get('mana', 0)}, "
        f"fatigue +{abs(d.get('fatigue', 0)) if d.get('fatigue') else 0}, health {d.get('health', 0)}",
    ]
    cd = use.get("cooldown") or {}
    if cd.get("remaining_minutes"):
        lines.append(f"- Cooldown: {cd.get('remaining_minutes')} minutes until ready again.")
    if use.get("debuffs"):
        names = [str(x.get("name") if isinstance(x, dict) else x) for x in use["debuffs"]]
        lines.append(f"- Debuffs applied: {', '.join(names)}")
    lines.append("Do not refund this cost. Do not ignore the cooldown.")
    return "\n".join(lines)
