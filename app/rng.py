"""
Deterministic dice + magnitude authority.

Why this module exists
----------------------
Local 8B models are bad at arithmetic and worse at *restraint*: asked for an XP
number they will happily mint 250, then 400 next turn. Every "how many" and
"how much" decision therefore belongs here, not in the model.

The contract is:

    model says WHAT and HOW BIG (a band)  ->  this module says HOW MUCH (a number)

Bands are the only vocabulary the model needs: ``none, trivial, small,
moderate, large, huge``. The band table, the dice notation behind each band,
and the scaling rules all live server-side and are content-pack overridable.

Everything is deterministic: rolls are seeded from (campaign seed, turn, tag,
sequence), so a rewind + regenerate reproduces the same dice. Every roll is
written to the ``dice_rolls`` table so a player can audit exactly why they got
7 gold instead of 70.

This module deliberately imports nothing from ``app.world`` — it takes plain
dicts — so it can be used from world, tile_world, encounters, and tests without
import cycles.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sqlite3
from typing import Any, Iterable

from app.db import connect, db_path

# --- band vocabulary ---------------------------------------------------------

BANDS: tuple[str, ...] = ("none", "trivial", "small", "moderate", "large", "huge")
BAND_INDEX = {band: i for i, band in enumerate(BANDS)}

# Words a model (or a human writing a pack) might use instead of the canonical
# band. Kept generous on purpose: normalizing junk is cheaper than a retry.
BAND_ALIASES: dict[str, str] = {
    "": "none",
    "0": "none",
    "zero": "none",
    "nothing": "none",
    "no": "none",
    "false": "none",
    "tiny": "trivial",
    "minimal": "trivial",
    "negligible": "trivial",
    "minor": "small",
    "slight": "small",
    "little": "small",
    "low": "small",
    "medium": "moderate",
    "normal": "moderate",
    "standard": "moderate",
    "mid": "moderate",
    "average": "moderate",
    "big": "large",
    "major": "large",
    "high": "large",
    "significant": "large",
    "massive": "huge",
    "extreme": "huge",
    "enormous": "huge",
    "legendary": "huge",
    "epic": "huge",
}


def normalize_band(value: Any, default: str = "none") -> str:
    """Coerce anything band-ish into a canonical band name."""
    if value is None:
        return default
    if isinstance(value, bool):
        return "small" if value else "none"
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in BAND_INDEX:
        return text
    if text in BAND_ALIASES:
        return BAND_ALIASES[text]
    # "small_gain", "moderate xp" and friends
    for band in BANDS:
        if band in text:
            return band
    for alias, band in BAND_ALIASES.items():
        if alias and alias in text:
            return band
    return default


def band_shift(band: str, steps: int) -> str:
    """Move a band up/down the ladder, clamped at the ends."""
    idx = BAND_INDEX.get(normalize_band(band), 0)
    return BANDS[max(0, min(len(BANDS) - 1, idx + int(steps)))]


# --- dice notation -----------------------------------------------------------

_DICE_RE = re.compile(
    r"^\s*(?P<count>\d*)\s*d\s*(?P<faces>\d+)"
    r"(?:\s*(?P<keep>kh|kl)\s*(?P<keep_n>\d+))?"
    r"(?:\s*(?P<sign>[+-])\s*(?P<mod>\d+))?\s*$",
    re.IGNORECASE,
)
_FLAT_RE = re.compile(r"^\s*(?P<sign>[+-])?\s*(?P<value>\d+)\s*$")

MAX_DICE_COUNT = 40
MAX_DICE_FACES = 1000


class DiceError(ValueError):
    """Raised when dice notation cannot be parsed."""


def roll_dice(notation: str, rng: random.Random) -> dict[str, Any]:
    """
    Roll ``NdF``, ``NdF+M``, ``NdFkh2`` or a flat integer.

    Returns a full audit record rather than a bare number, because the UI and
    the model trace both want to show the work.
    """
    text = str(notation or "0").strip()
    flat = _FLAT_RE.match(text)
    if flat:
        value = int(flat.group("value"))
        if flat.group("sign") == "-":
            value = -value
        return {
            "notation": text,
            "count": 0,
            "faces": 0,
            "rolls": [],
            "kept": [],
            "modifier": value,
            "total": value,
        }

    match = _DICE_RE.match(text)
    if not match:
        raise DiceError(f"Unparseable dice notation: {notation!r}")

    count = int(match.group("count") or 1)
    faces = int(match.group("faces"))
    if count < 1 or count > MAX_DICE_COUNT:
        raise DiceError(f"Dice count out of range in {notation!r} (1..{MAX_DICE_COUNT})")
    if faces < 2 or faces > MAX_DICE_FACES:
        raise DiceError(f"Dice faces out of range in {notation!r} (2..{MAX_DICE_FACES})")

    rolls = [rng.randint(1, faces) for _ in range(count)]
    kept = list(rolls)
    keep_mode = (match.group("keep") or "").lower()
    if keep_mode:
        keep_n = max(1, min(count, int(match.group("keep_n") or 1)))
        ordered = sorted(rolls, reverse=(keep_mode == "kh"))
        kept = ordered[:keep_n]

    modifier = 0
    if match.group("mod"):
        modifier = int(match.group("mod"))
        if match.group("sign") == "-":
            modifier = -modifier

    return {
        "notation": text,
        "count": count,
        "faces": faces,
        "rolls": rolls,
        "kept": kept,
        "modifier": modifier,
        "total": sum(kept) + modifier,
    }


def validate_notation(notation: str) -> bool:
    """True when ``notation`` is rollable. Used by pack validation."""
    try:
        roll_dice(notation, random.Random(0))
        return True
    except DiceError:
        return False


# --- deterministic seeding ---------------------------------------------------

def seed_from(*parts: Any) -> int:
    """
    Stable 63-bit seed from arbitrary parts.

    Uses blake2b rather than :func:`hash` because Python string hashing is
    randomized per process — a rewind in a fresh process must reproduce the
    same dice.
    """
    payload = "|".join(str(p) for p in parts).encode("utf-8", "replace")
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFFFFFFFFFFFFFF


_SEED_CACHE: dict[str, int] = {}


def reset_seed_cache() -> None:
    """Drop the memoized campaign seed — call after import/load of a world."""
    _SEED_CACHE.clear()


def campaign_seed(conn: sqlite3.Connection | None = None) -> int:
    """
    Per-campaign root seed, created once and stored in ``settings``.

    Everything else derives from this, so exporting a world exports its luck.

    Memoized per database path. Callers that already hold a connection MUST
    pass it: opening a second connection while an outer write transaction is
    open makes SQLite block on its busy timeout, which turned a 1.9s benchmark
    into a 117s one.
    """
    key = str(db_path())
    if key in _SEED_CACHE:
        return _SEED_CACHE[key]
    if conn is None:
        with connect() as owned:
            return campaign_seed(owned)
    row = conn.execute("SELECT value FROM settings WHERE key = 'campaign_rng_seed'").fetchone()
    if row:
        for parse in (lambda v: int(json.loads(v)), lambda v: int(str(v))):
            try:
                seed = parse(row["value"])
                _SEED_CACHE[key] = seed
                return seed
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
    seed = seed_from(os.urandom(16).hex())
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('campaign_rng_seed', ?)",
        (json.dumps(seed),),
    )
    _SEED_CACHE[key] = seed
    return seed


def rng_for(tag: str, *, turn: int = 0, seed: int | None = None, salt: Any = "") -> random.Random:
    """A Random seeded for one specific decision."""
    root = seed if seed is not None else campaign_seed()
    return random.Random(seed_from(root, turn, tag, salt))


# --- magnitude tables --------------------------------------------------------

# scale modes:
#   none        value stands alone
#   level       grows roughly linearly with player level
#   level_soft  grows with sqrt(level) — for things that must not run away
SCALE_MODES = ("none", "level", "level_soft")

DEFAULT_MAGNITUDE_TABLES: dict[str, dict[str, Any]] = {
    "xp": {
        "scale": "level",
        "min": 0,
        "max": 500,
        "difficulty_axis": "reward",
        "growth_key": "xp_growth_speed",
        "bands": {
            "none": "0",
            "trivial": "1d3",
            "small": "1d6+2",
            "moderate": "2d6+6",
            "large": "3d8+16",
            "huge": "4d10+40",
        },
    },
    "gold": {
        "scale": "level_soft",
        "min": -50_000,
        "max": 5_000,
        "difficulty_axis": "reward",
        "bands": {
            "none": "0",
            "trivial": "1d4",
            "small": "2d6+3",
            "moderate": "4d10+12",
            "large": "6d20+60",
            "huge": "10d30+250",
        },
    },
    "damage": {
        "scale": "level_soft",
        "min": 0,
        "max": 200,
        "difficulty_axis": "threat",
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1d4",
            "moderate": "2d6",
            "large": "4d8+4",
            "huge": "8d10+20",
        },
    },
    "heal": {
        "scale": "level_soft",
        "min": 0,
        "max": 200,
        "difficulty_axis": "reward",
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1d4+1",
            "moderate": "2d6+3",
            "large": "4d8+8",
            "huge": "6d10+25",
        },
    },
    "item_count": {
        "scale": "none",
        "min": 0,
        "max": 99,
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1d2",
            "moderate": "1d4+1",
            "large": "2d6+3",
            "huge": "4d10+10",
        },
    },
    "trust": {
        "scale": "none",
        "min": -25,
        "max": 25,
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1d2",
            "moderate": "1d4+1",
            "large": "1d6+4",
            "huge": "2d6+8",
        },
    },
    "karma": {
        "scale": "none",
        "min": -25,
        "max": 25,
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1d2+1",
            "moderate": "1d4+2",
            "large": "1d6+5",
            "huge": "2d6+10",
        },
    },
    "fame": {
        "scale": "none",
        "min": 0,
        "max": 80,
        "bands": {
            "none": "0",
            "trivial": "1d3",
            "small": "1d6+4",
            "moderate": "2d6+12",
            "large": "3d8+26",
            "huge": "4d10+45",
        },
    },
    "skill_gain": {
        "scale": "none",
        "min": 0,
        "max": 5,
        "growth_key": "skill_growth_speed",
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1",
            "moderate": "1d2",
            "large": "1d2+1",
            "huge": "1d3+1",
        },
    },
    "duration_minutes": {
        "scale": "none",
        "min": 0,
        "max": 1440,
        "bands": {
            "none": "0",
            "trivial": "1d5",
            "small": "2d10+5",
            "moderate": "3d20+20",
            "large": "4d30+90",
            "huge": "6d60+240",
        },
    },
    "count_people": {
        "scale": "none",
        "min": 0,
        "max": 40,
        "bands": {
            "none": "0",
            "trivial": "1",
            "small": "1d2",
            "moderate": "1d3+1",
            "large": "2d4+2",
            "huge": "3d6+6",
        },
    },
}

# Difficulty pulls rewards down and threats up (or the reverse on easy).
DIFFICULTY_MULT: dict[str, dict[str, float]] = {
    "easy": {"reward": 1.15, "threat": 0.7},
    "normal": {"reward": 1.0, "threat": 1.0},
    "hard": {"reward": 0.85, "threat": 1.3},
    "brutal": {"reward": 0.7, "threat": 1.6},
}

GROWTH_SPEED_MULT: dict[str, float] = {
    "very_slow": 0.35,
    "slow": 0.6,
    "normal": 1.0,
    "fast": 1.5,
    "very_fast": 2.2,
}

# Populated by app.content_packs when packs are installed.
_TABLE_OVERRIDES: dict[str, dict[str, Any]] = {}


def set_magnitude_overrides(tables: dict[str, Any] | None) -> None:
    """Install pack-provided magnitude tables (merged over the defaults)."""
    global _TABLE_OVERRIDES
    _TABLE_OVERRIDES = {}
    if not isinstance(tables, dict):
        return
    for kind, spec in tables.items():
        if isinstance(spec, dict):
            _TABLE_OVERRIDES[str(kind)] = spec


def magnitude_table(kind: str) -> dict[str, Any]:
    """Effective table for ``kind`` with pack overrides merged in."""
    base = dict(DEFAULT_MAGNITUDE_TABLES.get(kind) or DEFAULT_MAGNITUDE_TABLES["item_count"])
    override = _TABLE_OVERRIDES.get(kind)
    if override:
        bands = dict(base.get("bands") or {})
        bands.update({k: v for k, v in (override.get("bands") or {}).items() if isinstance(v, str)})
        base.update({k: v for k, v in override.items() if k != "bands"})
        base["bands"] = bands
    return base


def known_magnitude_kinds() -> list[str]:
    return sorted(set(DEFAULT_MAGNITUDE_TABLES) | set(_TABLE_OVERRIDES))


def _norm_speed(value: Any) -> str:
    text = str(value or "normal").strip().lower().replace("-", "_").replace(" ", "_")
    return text if text in GROWTH_SPEED_MULT else "normal"


def _scale_factor(mode: str, level: int) -> float:
    level = max(1, int(level or 1))
    if mode == "level":
        return 1.0 + (level - 1) * 0.15
    if mode == "level_soft":
        return 1.0 + ((level - 1) ** 0.5) * 0.22
    return 1.0


# --- the main entry point ----------------------------------------------------

def resolve_magnitude(
    kind: str,
    band: Any,
    *,
    level: int = 1,
    difficulty: str = "normal",
    options: dict[str, Any] | None = None,
    multiplier: float = 1.0,
    negative: bool = False,
    rng: random.Random | None = None,
    turn: int = 0,
    tag: str = "",
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Turn a qualitative band into a concrete number.

    This is the single place a "how much" answer is allowed to come from.
    Returns the full audit record; callers usually want ``["value"]`` and
    should hand the whole dict to :func:`record_roll` for the trace.
    """
    opts = options if isinstance(options, dict) else {}
    kind = str(kind or "item_count")
    table = magnitude_table(kind)
    canon_band = normalize_band(band)
    notation = str((table.get("bands") or {}).get(canon_band) or "0")

    roller = rng or rng_for(f"magnitude:{kind}", turn=turn, seed=seed, salt=tag or canon_band)
    detail = roll_dice(notation, roller)

    factor = _scale_factor(str(table.get("scale") or "none"), level)

    axis = str(table.get("difficulty_axis") or "")
    if axis:
        diff = str(difficulty or opts.get("difficulty") or "normal").strip().lower()
        factor *= (DIFFICULTY_MULT.get(diff) or DIFFICULTY_MULT["normal"]).get(axis, 1.0)

    growth_key = str(table.get("growth_key") or "")
    if growth_key:
        factor *= GROWTH_SPEED_MULT[_norm_speed(opts.get(growth_key))]
        explicit = opts.get(growth_key.replace("_speed", "_multiplier"))
        if explicit:
            try:
                factor *= max(0.05, min(10.0, float(explicit)))
            except (TypeError, ValueError):
                pass

    try:
        factor *= max(0.0, float(multiplier))
    except (TypeError, ValueError):
        pass

    raw_total = int(detail["total"])
    value = int(round(raw_total * factor))
    # A non-"none" band must never silently round away to nothing.
    if canon_band != "none" and raw_total > 0 and value <= 0:
        value = 1
    low = int(table.get("min", -1_000_000))
    high = int(table.get("max", 1_000_000))
    if negative:
        # Clamp the *magnitude* first, then negate. Clamping after negation
        # silently zeroed every loss on tables with a floor of 0 (damage,
        # fame, item_count), so "-moderate health" meant no damage at all.
        magnitude = min(abs(value), high if high > 0 else abs(low))
        value = -magnitude
        if low < 0:
            value = max(low, value)
    else:
        value = max(low, min(high, value))

    return {
        "kind": kind,
        "band": canon_band,
        "notation": notation,
        "rolls": detail["rolls"],
        "kept": detail["kept"],
        "modifier": detail["modifier"],
        "raw_total": raw_total,
        "scale": str(table.get("scale") or "none"),
        "factor": round(factor, 4),
        "level": max(1, int(level or 1)),
        "difficulty": str(difficulty or "normal"),
        "value": value,
        "clamped_to": [low, high],
        "tag": tag or kind,
        "turn": int(turn or 0),
    }


# --- reverse direction: numbers back into bands ------------------------------

def band_from_number(kind: str, value: Any, *, level: int = 1) -> str:
    """
    Bucket a raw number into the nearest band.

    Used when a model ignores the band contract and sends ``xp_delta: 250``
    anyway. Rather than trusting or rejecting it, we read it as an *intent*
    ("they wanted something large"), then re-roll that band properly. That
    keeps old prompts, cached clients, and third-party agents working while
    still moving the arithmetic server-side.
    """
    try:
        number = abs(float(value))
    except (TypeError, ValueError):
        return "none"
    if number <= 0:
        return "none"

    table = magnitude_table(kind)
    factor = _scale_factor(str(table.get("scale") or "none"), level)
    best_band = "trivial"
    best_gap = None
    for band in BANDS:
        if band == "none":
            continue
        notation = str((table.get("bands") or {}).get(band) or "0")
        try:
            detail = roll_dice(notation, random.Random(0))
        except DiceError:
            continue
        # Expected value of NdF is count*(F+1)/2, plus modifier.
        expected = detail["modifier"]
        if detail["count"]:
            kept_n = len(detail["kept"]) or detail["count"]
            expected += kept_n * (detail["faces"] + 1) / 2.0
        expected = max(0.5, expected * factor)
        gap = abs(number - expected) / expected
        if best_gap is None or gap < best_gap:
            best_gap = gap
            best_band = band
    return best_band


# --- audit trail -------------------------------------------------------------

def record_roll(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    *,
    turn: int = 0,
    source: str = "",
    inputs: dict[str, Any] | None = None,
) -> None:
    """Append one roll to the audit table. Never raises into gameplay."""
    try:
        conn.execute(
            """
            INSERT INTO dice_rolls
              (turn, tag, kind, notation, rolls, modifier, raw_total, value, band, seed, inputs, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(result.get("turn") or turn or 0),
                str(result.get("tag") or "")[:80],
                str(result.get("kind") or "")[:40],
                str(result.get("notation") or "")[:40],
                json.dumps(result.get("rolls") or [])[:400],
                int(result.get("modifier") or 0),
                int(result.get("raw_total") or 0),
                int(result.get("value") or 0),
                str(result.get("band") or "")[:20],
                int(result.get("seed") or 0),
                json.dumps(inputs or {}, ensure_ascii=True)[:2000],
                str(source or "")[:60],
            ),
        )
    except Exception:
        pass


def record_rolls(
    conn: sqlite3.Connection,
    results: Iterable[dict[str, Any]],
    *,
    turn: int = 0,
    source: str = "",
) -> None:
    for result in results or []:
        if isinstance(result, dict):
            record_roll(conn, result, turn=turn, source=source)


def recent_rolls(limit: int = 40, turn: int | None = None) -> list[dict[str, Any]]:
    """Audit feed for the UI / debug pane."""
    limit = max(1, min(500, int(limit)))
    with connect() as conn:
        if turn is None:
            rows = conn.execute(
                "SELECT * FROM dice_rolls ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM dice_rolls WHERE turn = ? ORDER BY id DESC LIMIT ?",
                (int(turn), limit),
            ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = {key: row[key] for key in row.keys()}
        for json_key in ("rolls", "inputs"):
            try:
                item[json_key] = json.loads(item.get(json_key) or ("[]" if json_key == "rolls" else "{}"))
            except json.JSONDecodeError:
                item[json_key] = [] if json_key == "rolls" else {}
        out.append(item)
    return out


def explain(result: dict[str, Any]) -> str:
    """One human-readable line for the roll banner / journal."""
    if not isinstance(result, dict):
        return ""
    rolls = result.get("rolls") or []
    bits = f"{result.get('notation')}"
    if rolls:
        bits += f" [{', '.join(str(r) for r in rolls)}]"
    mod = int(result.get("modifier") or 0)
    if mod:
        bits += f" {mod:+d}"
    factor = float(result.get("factor") or 1.0)
    if abs(factor - 1.0) > 0.01:
        bits += f" x{factor:.2f}"
    return f"{result.get('kind')} ({result.get('band')}): {bits} = {result.get('value')}"


# --- prompt-facing summary ---------------------------------------------------

def band_contract_block() -> dict[str, Any]:
    """
    Compact packet describing the band contract for prompt context.

    Deliberately tiny: the model needs the vocabulary, not the tables. Showing
    it the dice would invite it to do the arithmetic itself.
    """
    return {
        "how_much_is_decided_by": "server",
        "bands": list(BANDS),
        "kinds": known_magnitude_kinds(),
        "rules": [
            "Never write a number for a reward, cost, count, or damage. Write a band.",
            "Use xp_band, gold_band, health_band, quantity_band, trust_band, fame_band instead of *_delta fields.",
            "Bands describe intent only: 'small' means a small gain of whatever kind fits the scene.",
            "The app rolls dice for the actual amount using player level, difficulty, and growth settings.",
            "If you write a raw number anyway it is read as a band hint and re-rolled, so prefer the band.",
        ],
    }
