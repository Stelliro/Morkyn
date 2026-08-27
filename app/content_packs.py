"""
Content packs: add, remove, and reconfigure game content without touching code.

A pack is one JSON file. It can define skills, powers (activatable abilities),
items, encounter tables, and magnitude (dice) tables. Packs are additive and
removable: every entry a pack contributes is recorded in
``content_pack_entries``, so uninstalling takes exactly its own content back
out and leaves everything else alone.

The point of the format is that it can be handed to *any* competent LLM with
no knowledge of Mørkyn. :func:`authoring_bundle` emits the schema, the field
semantics, the database contract (which column each field lands in), the hard
rules, and worked examples in one payload — paste that into a chat, ask for a
pack, drop the result in ``data/packs/``.

Load order, lowest priority first:

    built-in Python catalog  ->  built-in packs  ->  user packs (data/packs)

Later entries override earlier ones by ``code``. A pack can therefore retune a
built-in skill's DC, or disable it outright with ``"enabled": false``, without
editing ``app/skill_checks.py``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.db import connect, row_to_dict, rows_to_dicts
from app.rng import (
    BANDS,
    known_magnitude_kinds,
    normalize_band,
    set_magnitude_overrides,
    validate_notation,
)

PACK_FORMAT = "morkyn-content-pack-v1"
ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PACK_DIR = ROOT / "content" / "packs"

SECTIONS = ("skills", "powers", "items", "encounter_tables", "magnitude_tables")
"""The five content buckets a pack may define.

UNUSED as of 2026-08-27: nothing outside this line references it. The real
section handling is spelled out per-bucket inside `validate_pack`. Kept as a
readable summary of the pack shape; delete it or wire `validate_pack` to it,
but do not assume it is enforcing anything today.
"""

# Canonical attribute keys. Packs must use these; aliases are normalized.
STAT_KEYS = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)
STAT_ALIASES = {
    "str": "strength", "might": "strength", "power": "strength",
    "dex": "dexterity", "agility": "dexterity", "speed": "dexterity",
    "con": "constitution", "endurance": "constitution", "vitality": "constitution", "stamina": "constitution",
    "int": "intelligence", "intellect": "intelligence", "mind": "intelligence",
    "wis": "wisdom", "insight": "wisdom", "awareness": "wisdom",
    "cha": "charisma", "presence": "charisma", "speech": "charisma",
}

SKILL_CATEGORIES = (
    "physical", "mental", "social", "craft", "combat", "event", "encounter", "general",
)
"""Skill categories a pack may declare. Enforced as a WARNING, not an error.

Deliberately soft -- `_validate_skill` appends to `warnings` and stores the
value as written, so a pack declaring `category: "stealthy"` installs cleanly.

The consequence is worth knowing, because it is silent: `search_skills` and
`gm_context_block` both filter on `enabled_categories`, which defaults to
exactly these eight. A skill whose category is off-roster therefore never
appears in skill search or in the GM context block -- the pack loads, the
warning scrolls past, and the skill is simply invisible.

This list is duplicated as `skill_checks.CATEGORIES` (by `id`). The two are
identical today and `tests/test_content_pack_rosters.py` locks them together;
the attribute alias tables drifted exactly this way before being merged.
"""

ACTIVATIONS = ("active", "passive", "triggered")
"""How a power fires. Enforced as a hard ERROR on anything else.

`active` = spent deliberately, `passive` = always on, `triggered` = fires on a
condition. An unknown value fails validation with a fix naming all three, so a
pack cannot install a power the engine has no rule for.
"""

RESOURCE_KEYS = ("health", "energy", "mana", "fatigue", "gold")
"""Resources a power may cost. Enforced as a hard ERROR on anything else.

Unlike `STAT_KEYS` there is no alias table here, so near-misses a pack author
would consider obvious -- "stamina", "grit", "focus" -- are rejected outright
rather than mapped. That is the safe direction (a refusal is visible, a silent
remap is not), but it does mean the error message is the only guidance an
author gets.
"""

_CACHE: dict[str, Any] = {}


# --- small helpers -----------------------------------------------------------

def user_pack_dir() -> Path:
    return Path(os.getenv("AI_RPG_PACK_DIR") or (ROOT / "data" / "packs"))


def _codeify(value: Any, fallback: str = "entry") -> str:
    raw = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return (raw or fallback)[:64]


def normalize_stat_key(value: Any) -> str:
    text = re.sub(r"[^a-z]", "", str(value or "").lower())
    if text in STAT_KEYS:
        return text
    return STAT_ALIASES.get(text, "")


def _checksum(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return [value]


def _clamp(value: Any, low: float, high: float, default: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


# --- validation --------------------------------------------------------------

class PackError(ValueError):
    """Raised when a pack cannot be installed."""


def _err(errors: list[dict[str, str]], path: str, message: str, fix: str = "") -> None:
    errors.append({"path": path, "message": message, "fix": fix})


def _validate_roll_profile(raw: Any, path: str, errors: list[dict[str, str]]) -> dict[str, int]:
    """``{"melee": 2, "stealth": -1}`` — skill code -> flat modifier."""
    out: dict[str, int] = {}
    if raw in (None, "", {}):
        return out
    if not isinstance(raw, dict):
        _err(errors, path, "roll_profile must be an object", 'Use {"melee": 2}')
        return out
    for key, value in raw.items():
        code = _codeify(key)
        if not code:
            _err(errors, f"{path}.{key}", "empty skill code in roll_profile")
            continue
        try:
            mod = int(value)
        except (TypeError, ValueError):
            _err(errors, f"{path}.{key}", f"modifier {value!r} is not an integer", "Use a whole number like 2 or -1")
            continue
        if abs(mod) > 12:
            _err(
                errors,
                f"{path}.{key}",
                f"modifier {mod} is outside the sane range (-12..12)",
                "Large bonuses break the d20 curve; use a power or an item rarity instead",
            )
            continue
        out[code] = mod
    return out


def _validate_stat_links(raw: Any, path: str, errors: list[dict[str, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    if raw in (None, "", {}):
        return out
    if not isinstance(raw, dict):
        _err(errors, path, "stat_links must be an object", 'Use {"strength": 1}')
        return out
    for key, value in raw.items():
        stat = normalize_stat_key(key)
        if not stat:
            _err(
                errors,
                f"{path}.{key}",
                f"unknown stat {key!r}",
                f"Use one of: {', '.join(STAT_KEYS)}",
            )
            continue
        try:
            mod = int(value)
        except (TypeError, ValueError):
            _err(errors, f"{path}.{key}", f"stat modifier {value!r} is not an integer")
            continue
        out[stat] = max(-10, min(10, mod))
    return out


def _validate_resource_cost(raw: Any, path: str, errors: list[dict[str, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    if raw in (None, "", {}):
        return out
    if not isinstance(raw, dict):
        _err(errors, path, "resource_cost must be an object", 'Use {"mana": 8}')
        return out
    for key, value in raw.items():
        res = re.sub(r"[^a-z]", "", str(key).lower())
        if res not in RESOURCE_KEYS:
            _err(errors, f"{path}.{key}", f"unknown resource {key!r}", f"Use one of: {', '.join(RESOURCE_KEYS)}")
            continue
        try:
            out[res] = max(0, min(9999, int(value)))
        except (TypeError, ValueError):
            _err(errors, f"{path}.{key}", f"cost {value!r} is not an integer")
    return out


def _validate_magnitude(raw: Any, path: str, errors: list[dict[str, str]]) -> dict[str, str]:
    if raw in (None, "", {}):
        return {}
    if not isinstance(raw, dict):
        _err(errors, path, "magnitude must be an object", 'Use {"kind": "damage", "band": "moderate"}')
        return {}
    kind = str(raw.get("kind") or "").strip().lower()
    band = normalize_band(raw.get("band"), default="")
    known = known_magnitude_kinds()
    if kind and kind not in known:
        _err(errors, f"{path}.kind", f"unknown magnitude kind {kind!r}", f"Use one of: {', '.join(known)}")
        kind = ""
    if not band:
        _err(errors, f"{path}.band", "missing or unrecognized band", f"Use one of: {', '.join(BANDS)}")
        return {}
    if not kind:
        return {}
    return {"kind": kind, "band": band}


def _validate_skill(raw: Any, index: int, errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> dict[str, Any] | None:
    path = f"skills[{index}]"
    if not isinstance(raw, dict):
        _err(errors, path, "skill entry must be an object")
        return None
    name = str(raw.get("name") or "").strip()
    code = _codeify(raw.get("code") or name)
    if not name and not code:
        _err(errors, path, "skill needs a name or code", 'Add "name": "Lockpicking"')
        return None
    name = name or code.replace("_", " ").title()

    category = str(raw.get("category") or "general").strip().lower()
    if category not in SKILL_CATEGORIES:
        warnings.append({
            "path": f"{path}.category",
            "message": f"unusual category {category!r}",
            "fix": f"Known categories: {', '.join(SKILL_CATEGORIES)}",
        })

    attribute = normalize_stat_key(raw.get("attribute"))
    if not attribute:
        _err(
            errors,
            f"{path}.attribute",
            f"missing/unknown attribute {raw.get('attribute')!r}",
            f"Every skill rolls off one attribute. Use one of: {', '.join(STAT_KEYS)}",
        )
        attribute = "intelligence"
    secondary = normalize_stat_key(raw.get("secondary")) or "wisdom"

    try:
        base_dc = int(raw.get("base_dc") or 12)
    except (TypeError, ValueError):
        _err(errors, f"{path}.base_dc", f"base_dc {raw.get('base_dc')!r} is not an integer")
        base_dc = 12
    if not 5 <= base_dc <= 30:
        _err(
            errors,
            f"{path}.base_dc",
            f"base_dc {base_dc} outside 5..30",
            "10=easy, 12=normal, 14=tricky, 16=hard, 20+=expert only",
        )
        base_dc = max(5, min(30, base_dc))

    triggers: list[str] = []
    for i, trigger in enumerate(_as_list(raw.get("triggers"))):
        text = str(trigger).strip().lower()
        if not text:
            continue
        if len(text) > 120:
            _err(errors, f"{path}.triggers[{i}]", "trigger phrase too long (max 120)")
            continue
        try:
            re.compile(text)
        except re.error as exc:
            _err(
                errors,
                f"{path}.triggers[{i}]",
                f"invalid regex: {exc}",
                "Triggers are lowercase regex fragments, e.g. \\b(pick|unlock)\\b",
            )
            continue
        triggers.append(text)

    growth = raw.get("growth") if isinstance(raw.get("growth"), dict) else {}
    growth_band = normalize_band(growth.get("band"), default="small") if growth else "small"
    growth_on = [
        str(o).strip().lower()
        for o in _as_list(growth.get("on") or ["success", "critical_success"])
        if str(o).strip()
    ]

    return {
        "code": code,
        "name": name[:80],
        "category": category[:40],
        "attribute": attribute,
        "secondary": secondary,
        "tags": [str(t)[:40] for t in _as_list(raw.get("tags"))][:16],
        "related_codes": [_codeify(c) for c in _as_list(raw.get("related_codes"))][:12],
        "base_dc": base_dc,
        "description": str(raw.get("description") or "")[:400],
        "enabled": bool(raw.get("enabled", True)),
        "triggers": triggers[:24],
        "opposed_by": _codeify(raw.get("opposed_by")) if raw.get("opposed_by") else "",
        "growth": {"band": growth_band, "on": growth_on},
        "source": "pack",
    }


def _validate_power(raw: Any, index: int, errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> dict[str, Any] | None:
    path = f"powers[{index}]"
    if not isinstance(raw, dict):
        _err(errors, path, "power entry must be an object")
        return None
    name = str(raw.get("name") or "").strip()
    code = str(raw.get("code") or "").strip() or f"AB_{_codeify(name)}"
    code = re.sub(r"[^A-Za-z0-9_]", "", code)[:64]
    if not name:
        _err(errors, path, "power needs a name", 'Add "name": "Flame Hand"')
        return None
    if not code:
        _err(errors, f"{path}.code", "power needs a code", 'Use "code": "AB_flame_hand"')
        return None

    activation = str(raw.get("activation") or "active").strip().lower()
    if activation not in ACTIVATIONS:
        _err(
            errors,
            f"{path}.activation",
            f"unknown activation {activation!r}",
            f"Use one of: {', '.join(ACTIVATIONS)}",
        )
        activation = "active"

    cooldown = int(_clamp(raw.get("cooldown_turns"), 0, 200, 0))
    resource_cost = _validate_resource_cost(raw.get("resource_cost"), f"{path}.resource_cost", errors)
    roll_profile = _validate_roll_profile(raw.get("roll_profile"), f"{path}.roll_profile", errors)
    magnitude = _validate_magnitude(raw.get("magnitude"), f"{path}.magnitude", errors)

    if activation == "active" and not resource_cost and not cooldown:
        warnings.append({
            "path": path,
            "message": "active power with no resource_cost and no cooldown_turns",
            "fix": "Free unlimited powers trivialize play; add a cost or a cooldown",
        })
    if activation == "passive" and (resource_cost or cooldown):
        warnings.append({
            "path": path,
            "message": "passive power declares a cost or cooldown",
            "fix": "Passives are always-on; costs are ignored for them",
        })

    return {
        "code": code,
        "name": name[:80],
        "description": str(raw.get("description") or "")[:600],
        "base_description": str(raw.get("base_description") or raw.get("description") or "")[:600],
        "activation": activation,
        "read_only": bool(raw.get("read_only", True)),
        "locked": bool(raw.get("locked", False)),
        "prerequisites": str(raw.get("prerequisites") or "")[:400],
        "resource_cost": resource_cost,
        "cooldown_turns": cooldown,
        "roll_profile": roll_profile,
        "magnitude": magnitude,
        "power_type": str(raw.get("power_type") or "linear")[:40],
        "growth_math": str(raw.get("growth_math") or "")[:600],
        "tags": [str(t)[:40] for t in _as_list(raw.get("tags"))][:16],
        "source": "pack",
    }


def _validate_item(
    raw: Any,
    index: int,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
    power_codes: set[str],
) -> dict[str, Any] | None:
    path = f"items[{index}]"
    if not isinstance(raw, dict):
        _err(errors, path, "item entry must be an object")
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        _err(errors, path, "item needs a name", 'Add "name": "Iron Sword"')
        return None
    code = re.sub(r"[^A-Za-z0-9_]", "", str(raw.get("code") or f"IT_{_codeify(name)}"))[:64]

    granted = [str(c).strip() for c in _as_list(raw.get("power_codes")) if str(c).strip()]
    for i, ref in enumerate(granted):
        if ref not in power_codes:
            warnings.append({
                "path": f"{path}.power_codes[{i}]",
                "message": f"power {ref!r} is not defined in this pack",
                "fix": "Define it under \"powers\", or make sure another installed pack provides it",
            })

    return {
        "code": code,
        "name": name[:120],
        "description": str(raw.get("description") or "")[:400],
        "item_type": str(raw.get("item_type") or "misc")[:80],
        "rarity": str(raw.get("rarity") or "common")[:40],
        "weight": _clamp(raw.get("weight"), 0.0, 500.0, 1.0),
        "slot_size": int(_clamp(raw.get("slot_size"), 0, 40, 1)),
        "stack_limit": int(_clamp(raw.get("stack_limit"), 1, 9999, 20)),
        "equip_slot": str(raw.get("equip_slot") or "")[:40],
        "stat_links": _validate_stat_links(raw.get("stat_links") or raw.get("stat_modifiers"), f"{path}.stat_links", errors),
        "power_codes": granted[:12],
        "roll_profile": _validate_roll_profile(raw.get("roll_profile"), f"{path}.roll_profile", errors),
        "enchantments": [str(e)[:80] for e in _as_list(raw.get("enchantments"))][:12],
        "carry_modifier": _clamp(raw.get("carry_modifier"), 0.5, 2.0, 1.0),
        "container_bonus_weight": _clamp(raw.get("container_bonus_weight"), 0, 5000, 0),
        "container_bonus_slots": int(_clamp(raw.get("container_bonus_slots"), 0, 500, 0)),
        "dimensional_space": bool(raw.get("dimensional_space", False)),
        "tags": [str(t)[:40] for t in _as_list(raw.get("tags"))][:16],
        "source": "pack",
    }


def _validate_encounter_tables(raw: Any, errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> dict[str, Any]:
    if raw in (None, {}, []):
        return {}
    if not isinstance(raw, dict):
        _err(errors, "encounter_tables", "encounter_tables must be an object with 'terrain' and/or 'kinds'")
        return {}

    out: dict[str, Any] = {}
    terrain_raw = raw.get("terrain")
    if terrain_raw is not None:
        if not isinstance(terrain_raw, dict):
            _err(errors, "encounter_tables.terrain", "terrain must be an object keyed by tile state")
        else:
            terrain: dict[str, Any] = {}
            for state, spec in terrain_raw.items():
                spath = f"encounter_tables.terrain.{state}"
                if not isinstance(spec, dict):
                    _err(errors, spath, "terrain entry must be an object")
                    continue
                chance = _clamp(spec.get("base_chance"), 0.0, 0.95, 0.10)
                kinds_raw = spec.get("kinds") if isinstance(spec.get("kinds"), dict) else {}
                kinds: dict[str, float] = {}
                for kind, weight in kinds_raw.items():
                    try:
                        w = float(weight)
                    except (TypeError, ValueError):
                        _err(errors, f"{spath}.kinds.{kind}", f"weight {weight!r} is not a number")
                        continue
                    if w < 0:
                        _err(errors, f"{spath}.kinds.{kind}", "weight must be >= 0")
                        continue
                    kinds[_codeify(kind)] = w
                if not kinds:
                    warnings.append({
                        "path": spath,
                        "message": "terrain entry has no kind weights",
                        "fix": 'Add "kinds": {"bandit_ambush": 30, "wild_threat": 50}',
                    })
                terrain[_codeify(state)] = {"base_chance": round(chance, 4), "kinds": kinds}
            out["terrain"] = terrain

    kinds_raw = raw.get("kinds")
    if kinds_raw is not None:
        if not isinstance(kinds_raw, dict):
            _err(errors, "encounter_tables.kinds", "kinds must be an object keyed by encounter kind")
        else:
            kinds_out: dict[str, Any] = {}
            for kind, spec in kinds_raw.items():
                kpath = f"encounter_tables.kinds.{kind}"
                if not isinstance(spec, dict):
                    _err(errors, kpath, "kind entry must be an object")
                    continue
                kinds_out[_codeify(kind)] = {
                    "label": str(spec.get("label") or kind)[:80],
                    "hostile": bool(spec.get("hostile", False)),
                    "wary": bool(spec.get("wary", False)),
                    "avoid_skill": _codeify(spec.get("avoid_skill")) if spec.get("avoid_skill") else "perception",
                    "count_band": normalize_band(spec.get("count_band"), default="small"),
                    "threat_band": normalize_band(spec.get("threat_band"), default="moderate"),
                    "participant_tier": str(spec.get("participant_tier") or "nameless")[:40],
                    "summary": str(spec.get("summary") or "")[:240],
                }
            out["kinds"] = kinds_out
    return out


def _validate_magnitude_tables(raw: Any, errors: list[dict[str, str]], warnings: list[dict[str, str]]) -> dict[str, Any]:
    if raw in (None, {}, []):
        return {}
    if not isinstance(raw, dict):
        _err(errors, "magnitude_tables", "magnitude_tables must be an object keyed by magnitude kind")
        return {}
    out: dict[str, Any] = {}
    for kind, spec in raw.items():
        kpath = f"magnitude_tables.{kind}"
        if not isinstance(spec, dict):
            _err(errors, kpath, "magnitude table must be an object")
            continue
        bands_raw = spec.get("bands") if isinstance(spec.get("bands"), dict) else {}
        bands: dict[str, str] = {}
        for band, notation in bands_raw.items():
            canon = normalize_band(band, default="")
            if not canon:
                _err(errors, f"{kpath}.bands.{band}", f"unknown band {band!r}", f"Use one of: {', '.join(BANDS)}")
                continue
            if not isinstance(notation, str) or not validate_notation(notation):
                _err(
                    errors,
                    f"{kpath}.bands.{band}",
                    f"invalid dice notation {notation!r}",
                    'Use forms like "2d6+3", "1d4", "4d6kh3", or a flat "5"',
                )
                continue
            bands[canon] = notation
        if not bands:
            warnings.append({"path": kpath, "message": "magnitude table defines no valid bands"})
            continue
        entry: dict[str, Any] = {"bands": bands}
        if spec.get("scale") is not None:
            scale = str(spec.get("scale")).strip().lower()
            if scale not in ("none", "level", "level_soft"):
                _err(errors, f"{kpath}.scale", f"unknown scale {scale!r}", "Use none, level, or level_soft")
            else:
                entry["scale"] = scale
        for numeric in ("min", "max"):
            if spec.get(numeric) is not None:
                try:
                    entry[numeric] = int(spec[numeric])
                except (TypeError, ValueError):
                    _err(errors, f"{kpath}.{numeric}", f"{numeric} must be an integer")
        out[_codeify(kind)] = entry
    return out


def validate_pack(payload: Any) -> dict[str, Any]:
    """
    Check a pack and return a normalized copy plus precise problems.

    Errors carry a JSON path and a suggested fix so an authoring LLM can be
    handed the response verbatim and asked to correct its own output.
    """
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not isinstance(payload, dict):
        return {
            "ok": False,
            "errors": [{"path": "", "message": "pack must be a JSON object", "fix": "Wrap everything in { }"}],
            "warnings": [],
            "pack": None,
        }

    fmt = str(payload.get("format") or "").strip()
    if fmt != PACK_FORMAT:
        _err(
            errors,
            "format",
            f"format must be {PACK_FORMAT!r} (got {fmt!r})",
            f'Set "format": "{PACK_FORMAT}"',
        )

    pack_id = _codeify(payload.get("id") or payload.get("label"), fallback="")
    if not pack_id:
        _err(
            errors,
            "id",
            "pack needs an id (snake_case, unique)",
            'Add "id": "my_pack". Installing a pack with an existing id replaces that pack.',
        )

    powers: list[dict[str, Any]] = []
    for i, raw in enumerate(_as_list(payload.get("powers"))):
        entry = _validate_power(raw, i, errors, warnings)
        if entry:
            powers.append(entry)
    power_codes = {p["code"] for p in powers}

    skills: list[dict[str, Any]] = []
    for i, raw in enumerate(_as_list(payload.get("skills"))):
        entry = _validate_skill(raw, i, errors, warnings)
        if entry:
            skills.append(entry)

    items: list[dict[str, Any]] = []
    for i, raw in enumerate(_as_list(payload.get("items"))):
        entry = _validate_item(raw, i, errors, warnings, power_codes)
        if entry:
            items.append(entry)

    # roll_profile keys should point at skills that exist somewhere.
    local_skill_codes = {s["code"] for s in skills}
    for bucket, entries in (("powers", powers), ("items", items)):
        for i, entry in enumerate(entries):
            for skill_code in (entry.get("roll_profile") or {}):
                if skill_code in local_skill_codes:
                    continue
                warnings.append({
                    "path": f"{bucket}[{i}].roll_profile.{skill_code}",
                    "message": f"roll_profile targets skill {skill_code!r} not defined in this pack",
                    "fix": "Fine if a built-in or another pack defines it; otherwise the modifier never applies",
                })

    encounter_tables = _validate_encounter_tables(payload.get("encounter_tables"), errors, warnings)
    magnitude_tables = _validate_magnitude_tables(payload.get("magnitude_tables"), errors, warnings)

    for section in ("skills", "powers", "items"):
        seen: set[str] = set()
        for entry in {"skills": skills, "powers": powers, "items": items}[section]:
            code = entry["code"]
            if code in seen:
                _err(
                    errors,
                    f"{section}",
                    f"duplicate code {code!r} inside this pack",
                    "Each code must be unique within a pack",
                )
            seen.add(code)

    if not any((skills, powers, items, encounter_tables, magnitude_tables)):
        warnings.append({"path": "", "message": "pack defines no content", "fix": "Add at least one section"})

    normalized = {
        "format": PACK_FORMAT,
        "id": pack_id,
        "label": str(payload.get("label") or pack_id.replace("_", " ").title())[:120],
        "version": str(payload.get("version") or "1")[:40],
        "author": str(payload.get("author") or "")[:120],
        "description": str(payload.get("description") or "")[:1000],
        "skills": skills,
        "powers": powers,
        "items": items,
        "encounter_tables": encounter_tables,
        "magnitude_tables": magnitude_tables,
    }

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "pack": normalized,
        "counts": {
            "skills": len(skills),
            "powers": len(powers),
            "items": len(items),
            "encounter_terrain": len((encounter_tables.get("terrain") or {})),
            "encounter_kinds": len((encounter_tables.get("kinds") or {})),
            "magnitude_tables": len(magnitude_tables),
        },
    }


# --- install / remove --------------------------------------------------------

def _invalidate() -> None:
    _CACHE.clear()


def install_pack(
    payload: Any,
    *,
    source: str = "user",
    builtin: bool = False,
    write_file: bool = True,
) -> dict[str, Any]:
    """Validate then persist a pack. Re-installing the same id replaces it."""
    report = validate_pack(payload)
    if not report["ok"]:
        raise PackError(json.dumps({"errors": report["errors"]}, ensure_ascii=True)[:4000])

    pack = report["pack"]
    pack_id = pack["id"]
    checksum = _checksum(pack)
    blob = json.dumps(pack, ensure_ascii=True, separators=(",", ":"))

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO content_packs
              (id, label, version, author, description, source, enabled, builtin, checksum, payload, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
              label=excluded.label,
              version=excluded.version,
              author=excluded.author,
              description=excluded.description,
              source=excluded.source,
              builtin=excluded.builtin,
              checksum=excluded.checksum,
              payload=excluded.payload,
              updated_at=CURRENT_TIMESTAMP
            """,
            (
                pack_id,
                pack["label"],
                pack["version"],
                pack["author"],
                pack["description"],
                source,
                1 if builtin else 0,
                checksum,
                blob,
            ),
        )
        conn.execute("DELETE FROM content_pack_entries WHERE pack_id = ?", (pack_id,))
        for section in ("skills", "powers", "items"):
            for entry in pack.get(section) or []:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO content_pack_entries
                      (pack_id, section, entry_code, entry_name, payload)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pack_id,
                        section,
                        entry["code"],
                        entry.get("name") or "",
                        json.dumps(entry, ensure_ascii=True)[:8000],
                    ),
                )

    if write_file and not builtin:
        try:
            target_dir = user_pack_dir()
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / f"{pack_id}.json").write_text(
                json.dumps(pack, ensure_ascii=True, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    _invalidate()
    return {
        "installed": True,
        "pack_id": pack_id,
        "checksum": checksum,
        "counts": report["counts"],
        "warnings": report["warnings"],
    }


def remove_pack(pack_id: str, *, delete_file: bool = True) -> dict[str, Any]:
    """
    Uninstall a pack and everything it contributed.

    Built-in packs can be disabled but not removed, so a bad uninstall can
    never leave the game with no skill catalog at all.
    """
    pack_id = _codeify(pack_id)
    with connect() as conn:
        row = conn.execute("SELECT * FROM content_packs WHERE id = ?", (pack_id,)).fetchone()
        if not row:
            return {"removed": False, "reason": "not_installed", "pack_id": pack_id}
        if int(row["builtin"] or 0):
            return {
                "removed": False,
                "reason": "builtin",
                "pack_id": pack_id,
                "hint": "Built-in packs can be disabled with set_pack_enabled(), not removed.",
            }
        entries = conn.execute(
            "SELECT COUNT(*) AS n FROM content_pack_entries WHERE pack_id = ?", (pack_id,)
        ).fetchone()
        conn.execute("DELETE FROM content_pack_entries WHERE pack_id = ?", (pack_id,))
        conn.execute("DELETE FROM content_packs WHERE id = ?", (pack_id,))
        # Detach anything in live play that referenced this pack, rather than
        # deleting the player's items/powers out from under them.
        conn.execute("UPDATE inventory SET pack_id = '' WHERE pack_id = ?", (pack_id,))
        conn.execute("UPDATE abilities SET pack_id = '' WHERE pack_id = ?", (pack_id,))
        removed_entries = int((entries or {"n": 0})["n"])

    if delete_file:
        try:
            path = user_pack_dir() / f"{pack_id}.json"
            if path.is_file():
                path.unlink()
        except OSError:
            pass

    _invalidate()
    return {"removed": True, "pack_id": pack_id, "entries_removed": removed_entries}


def set_pack_enabled(pack_id: str, enabled: bool) -> dict[str, Any]:
    pack_id = _codeify(pack_id)
    with connect() as conn:
        cur = conn.execute(
            "UPDATE content_packs SET enabled = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (1 if enabled else 0, pack_id),
        )
        if not cur.rowcount:
            return {"ok": False, "reason": "not_installed", "pack_id": pack_id}
    _invalidate()
    return {"ok": True, "pack_id": pack_id, "enabled": bool(enabled)}


def list_packs(*, include_payload: bool = False) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM content_packs ORDER BY builtin DESC, id"
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = row_to_dict(row) or {}
        payload = {}
        try:
            payload = json.loads(item.pop("payload", "{}") or "{}")
        except json.JSONDecodeError:
            payload = {}
        item["enabled"] = bool(item.get("enabled"))
        item["builtin"] = bool(item.get("builtin"))
        item["counts"] = {
            "skills": len(payload.get("skills") or []),
            "powers": len(payload.get("powers") or []),
            "items": len(payload.get("items") or []),
            "encounter_terrain": len((payload.get("encounter_tables") or {}).get("terrain") or {}),
            "encounter_kinds": len((payload.get("encounter_tables") or {}).get("kinds") or {}),
            "magnitude_tables": len(payload.get("magnitude_tables") or {}),
        }
        if include_payload:
            item["payload"] = payload
        out.append(item)
    return out


def export_pack(pack_id: str) -> dict[str, Any] | None:
    """Get a pack back out as authored JSON — for editing or sharing."""
    pack_id = _codeify(pack_id)
    with connect() as conn:
        row = conn.execute("SELECT payload FROM content_packs WHERE id = ?", (pack_id,)).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["payload"] or "{}")
    except json.JSONDecodeError:
        return None


def install_pack_file(path: str | Path, *, builtin: bool = False) -> dict[str, Any]:
    file_path = Path(path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    return install_pack(
        payload,
        source=f"file:{file_path.name}",
        builtin=builtin,
        write_file=not builtin,
    )


def sync_packs_from_disk() -> dict[str, Any]:
    """
    Load built-in packs then user packs from disk.

    Called at startup so dropping a JSON file into ``data/packs/`` is all the
    installation a user has to do.
    """
    loaded: list[str] = []
    failed: list[dict[str, str]] = []
    for directory, builtin in ((BUILTIN_PACK_DIR, True), (user_pack_dir(), False)):
        if not directory.is_dir():
            continue
        for file_path in sorted(directory.glob("*.json")):
            try:
                result = install_pack_file(file_path, builtin=builtin)
                loaded.append(str(result.get("pack_id")))
            except Exception as exc:
                failed.append({"file": file_path.name, "error": str(exc)[:400]})
    _invalidate()
    return {"loaded": loaded, "failed": failed}


# --- active content accessors ------------------------------------------------

def _enabled_payloads() -> list[dict[str, Any]]:
    cached = _CACHE.get("payloads")
    if cached is not None:
        return cached
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM content_packs WHERE enabled = 1 ORDER BY builtin DESC, id"
            ).fetchall()
    except sqlite3.Error:
        rows = []
    payloads: list[dict[str, Any]] = []
    for row in rows:
        try:
            payloads.append(json.loads(row["payload"] or "{}"))
        except json.JSONDecodeError:
            continue
    _CACHE["payloads"] = payloads
    return payloads


def active_skills() -> dict[str, dict[str, Any]]:
    """Skill overrides/additions by code, later packs winning."""
    if "skills" in _CACHE:
        return _CACHE["skills"]
    merged: dict[str, dict[str, Any]] = {}
    for payload in _enabled_payloads():
        for entry in payload.get("skills") or []:
            if isinstance(entry, dict) and entry.get("code"):
                merged[entry["code"]] = entry
    _CACHE["skills"] = merged
    return merged


def active_powers() -> dict[str, dict[str, Any]]:
    if "powers" in _CACHE:
        return _CACHE["powers"]
    merged: dict[str, dict[str, Any]] = {}
    for payload in _enabled_payloads():
        for entry in payload.get("powers") or []:
            if isinstance(entry, dict) and entry.get("code"):
                merged[entry["code"]] = entry
    _CACHE["powers"] = merged
    return merged


def active_items() -> dict[str, dict[str, Any]]:
    if "items" in _CACHE:
        return _CACHE["items"]
    merged: dict[str, dict[str, Any]] = {}
    for payload in _enabled_payloads():
        for entry in payload.get("items") or []:
            if isinstance(entry, dict) and entry.get("code"):
                merged[entry["code"]] = entry
    _CACHE["items"] = merged
    return merged


def active_encounter_tables() -> dict[str, Any]:
    if "encounter" in _CACHE:
        return _CACHE["encounter"]
    terrain: dict[str, Any] = {}
    kinds: dict[str, Any] = {}
    for payload in _enabled_payloads():
        tables = payload.get("encounter_tables") or {}
        terrain.update(tables.get("terrain") or {})
        kinds.update(tables.get("kinds") or {})
    merged = {"terrain": terrain, "kinds": kinds}
    _CACHE["encounter"] = merged
    return merged


def active_magnitude_tables() -> dict[str, Any]:
    if "magnitude" in _CACHE:
        return _CACHE["magnitude"]
    merged: dict[str, Any] = {}
    for payload in _enabled_payloads():
        merged.update(payload.get("magnitude_tables") or {})
    _CACHE["magnitude"] = merged
    return merged


def apply_active_packs() -> dict[str, Any]:
    """Push pack-provided tables into the modules that consume them."""
    magnitude = active_magnitude_tables()
    set_magnitude_overrides(magnitude)
    return {
        "skills": len(active_skills()),
        "powers": len(active_powers()),
        "items": len(active_items()),
        "magnitude_tables": len(magnitude),
        "encounter_terrain": len(active_encounter_tables().get("terrain") or {}),
    }


def skill_triggers() -> list[tuple[str, str]]:
    """(regex, skill_code) pairs contributed by packs, for auto check inference."""
    pairs: list[tuple[str, str]] = []
    for code, entry in active_skills().items():
        if not entry.get("enabled", True):
            continue
        for trigger in entry.get("triggers") or []:
            pairs.append((str(trigger), code))
    return pairs


def disabled_skill_codes() -> set[str]:
    """Codes a pack explicitly switched off (including built-ins)."""
    return {
        code
        for code, entry in active_skills().items()
        if not entry.get("enabled", True)
    }


def pack_entry_owner(section: str, code: str) -> str:
    """Which pack contributed this entry (empty when it is a built-in)."""
    try:
        with connect() as conn:
            row = conn.execute(
                "SELECT pack_id FROM content_pack_entries WHERE section = ? AND entry_code = ? LIMIT 1",
                (str(section), str(code)),
            ).fetchone()
    except sqlite3.Error:
        return ""
    return str(row["pack_id"]) if row else ""


# --- authoring bundle: everything an outside LLM needs -----------------------

EXAMPLE_PACK: dict[str, Any] = {
    "format": PACK_FORMAT,
    "id": "riverlands_kit",
    "label": "Riverlands Kit",
    "version": "1.0.0",
    "author": "example",
    "description": "A small themed pack: one skill, one power, one item that ties them together.",
    "skills": [
        {
            "code": "poling",
            "name": "Poling",
            "category": "craft",
            "attribute": "strength",
            "secondary": "dexterity",
            "tags": ["boat", "river", "punt"],
            "base_dc": 12,
            "description": "Pushing a flat boat upriver with a pole without losing the line.",
            "triggers": [r"\b(pole|punt|push the (boat|barge|raft))\b"],
            "growth": {"band": "small", "on": ["success", "critical_success"]},
        }
    ],
    "powers": [
        {
            "code": "AB_river_read",
            "name": "River Read",
            "description": "Read the current for a heartbeat and know where the channel runs.",
            "activation": "active",
            "read_only": True,
            "resource_cost": {"energy": 2},
            "cooldown_turns": 1,
            "roll_profile": {"poling": 2, "navigation": 1},
            "magnitude": {"kind": "duration_minutes", "band": "small"},
            "prerequisites": "Has poled a river at least once",
        }
    ],
    "items": [
        {
            "code": "IT_river_pole",
            "name": "Ironshod River Pole",
            "item_type": "tool",
            "rarity": "uncommon",
            "weight": 4.0,
            "slot_size": 2,
            "stack_limit": 1,
            "equip_slot": "main_hand",
            "description": "A long ash pole with an iron foot, worn smooth at the grip.",
            "stat_links": {"strength": 1},
            "power_codes": ["AB_river_read"],
            "roll_profile": {"poling": 2, "athletics": 1},
        }
    ],
    "encounter_tables": {
        "terrain": {
            "swamp": {
                "base_chance": 0.18,
                "kinds": {"wild_threat": 55, "bandit_ambush": 15, "traveler": 10, "hidden_base": 20},
            }
        },
        "kinds": {
            "wild_threat": {
                "label": "Something in the reeds",
                "hostile": True,
                "avoid_skill": "perception",
                "count_band": "small",
                "threat_band": "moderate",
            }
        },
    },
    "magnitude_tables": {},
}


def field_reference() -> dict[str, Any]:
    """
    Field-by-field semantics *and* where each field lands in SQLite.

    The DB column mapping matters: an authoring LLM that knows a field becomes
    ``inventory.roll_profile`` understands why it must be a flat modifier map
    and not prose.
    """
    return {
        "skills": {
            "_stored_in": "skill library (data/skill_library.json) + content_pack_entries",
            "code": "stable snake_case id. Reusing a built-in code overrides that built-in.",
            "name": "display name",
            "category": f"one of {list(SKILL_CATEGORIES)}",
            "attribute": f"the stat this rolls off; one of {list(STAT_KEYS)}",
            "secondary": "supporting stat, same vocabulary",
            "base_dc": "5..30 difficulty floor. 10 easy, 12 normal, 14 tricky, 16 hard, 20+ expert",
            "tags": "free keywords used for similarity when new skills appear in play",
            "triggers": "lowercase regex fragments; when player input matches, the server auto-rolls this skill",
            "opposed_by": "skill code an opponent rolls against this one, when contested",
            "growth": '{"band": "small", "on": ["success"]} — how fast rank grows and on which outcomes',
            "enabled": "false removes the skill from play, including built-ins",
        },
        "powers": {
            "_stored_in": "abilities table (code, name, description, activation, read_only, roll_profile, magnitude_band, magnitude_kind, resource_cost, prerequisites, locked)",
            "code": "stable id, conventionally AB_ prefixed",
            "activation": f"one of {list(ACTIVATIONS)}. active = spent deliberately, passive = always on, triggered = fires on a condition",
            "read_only": "true means the narrator may never restate or rescale this power; the server owns its numbers",
            "resource_cost": f"integer cost per use, keys from {list(RESOURCE_KEYS)}",
            "cooldown_turns": "turns before it can be used again",
            "roll_profile": "skill_code -> flat modifier applied to dice checks while this power is active/equipped",
            "magnitude": '{"kind": "damage", "band": "moderate"} — what the server rolls when this power resolves',
            "prerequisites": "plain text gate; the narrator may hint at it but not bypass it",
            "locked": "true means it exists but cannot be used yet",
        },
        "items": {
            "_stored_in": "inventory table (name, description, item_type, rarity, weight, slot_size, stack_limit, stat_links, power_codes, roll_profile, enchantments, carry_modifier, container_bonus_*, dimensional_space)",
            "stat_links": f"canonical stat bonuses while equipped, keys from {list(STAT_KEYS)}. Folded into player.effective_stats automatically.",
            "power_codes": "array of power codes this item grants while equipped. The item points at powers; it does not redefine them.",
            "roll_profile": "skill_code -> flat modifier applied to dice checks while equipped. This is how gear affects rolls without the narrator doing math.",
            "equip_slot": "which equipment slot it wants (main_hand, off_hand, head, body, back, ring, neck, ...)",
            "dimensional_space": "true makes packed slots effectively unlimited. Should be rare and expensive.",
        },
        "encounter_tables": {
            "_stored_in": "consulted live by app/encounters.py",
            "terrain.<tile_state>.base_chance": "0..0.95 chance of any encounter per hour of exposure on that terrain",
            "terrain.<tile_state>.kinds": "relative weights for which kind fires when one does",
            "kinds.<kind>.hostile": "true means it starts as a threat rather than a meeting",
            "kinds.<kind>.avoid_skill": "skill the player passively rolls to spot/avoid it first",
            "kinds.<kind>.count_band": "band for how many participants the server rolls",
            "kinds.<kind>.threat_band": "band for how dangerous the server rolls it",
        },
        "magnitude_tables": {
            "_stored_in": "app/rng.py overrides",
            "<kind>.bands.<band>": 'dice notation, e.g. "2d6+3". Kinds: ' + ", ".join(known_magnitude_kinds()),
            "<kind>.scale": "none | level | level_soft — how the result grows with player level",
            "<kind>.min / .max": "hard clamps applied after scaling",
        },
    }


AUTHORING_RULES: list[str] = [
    "Return ONE JSON object and nothing else. No markdown fences, no commentary.",
    f'"format" must be exactly "{PACK_FORMAT}".',
    "Never write a number for a reward, cost, count, or damage in narrative fields. Numbers belong only in the declared numeric fields listed in the field reference.",
    "Magnitudes are bands, never amounts: " + ", ".join(BANDS) + ".",
    "Powers are read-only rules. Define what a power does once, here; nothing in play may rescale it.",
    "Items point at powers by code (power_codes). Do not copy a power's text into an item.",
    "roll_profile modifiers stay within -12..12. A +3 sword is already strong on a d20.",
    "Stat keys are exactly: " + ", ".join(STAT_KEYS) + ". No custom attributes.",
    "Every skill must name one attribute it rolls off, or the dice system cannot resolve it.",
    "Reusing an existing code overrides that entry; use a new code when you mean to add rather than replace.",
    'Set "enabled": false on a skill to remove it from play, including built-in skills.',
    "Prefer few, well-differentiated entries over many near-duplicates. Similar skills get merged by DC averaging and become noise.",
    "Triggers are lowercase regex fragments matched against raw player input. Keep them specific; a greedy trigger will hijack unrelated turns.",
    "Do not invent new top-level sections. Unknown keys are dropped silently.",
]


def authoring_bundle(*, include_catalog: bool = True) -> dict[str, Any]:
    """
    Self-contained instructions for an LLM that has never seen this project.

    Hand the whole thing to a model with: "Write me a Mørkyn content pack that
    does X, following this specification exactly."
    """
    bundle: dict[str, Any] = {
        "what_this_is": (
            "Mørkyn is a local-first RPG where SQLite is the source of truth and a small "
            "local language model only narrates. All quantities are rolled by the server. "
            "A content pack is one JSON file that adds or replaces skills, powers, items, "
            "encounter tables, and dice tables without any code changes."
        ),
        "format": PACK_FORMAT,
        "install": (
            "Save the JSON as data/packs/<your_pack_id>.json and restart, or POST it to "
            "/api/content-packs/install. Remove it with /api/content-packs/remove or by "
            "deleting the file and restarting."
        ),
        "hard_rules": AUTHORING_RULES,
        "bands": list(BANDS),
        "stat_keys": list(STAT_KEYS),
        "skill_categories": list(SKILL_CATEGORIES),
        "activations": list(ACTIVATIONS),
        "resource_keys": list(RESOURCE_KEYS),
        "magnitude_kinds": known_magnitude_kinds(),
        "field_reference": field_reference(),
        "example_pack": EXAMPLE_PACK,
        "validation": (
            "POST the pack to /api/content-packs/validate before installing. The response "
            "lists errors as {path, message, fix}. Feed that response straight back to the "
            "authoring model and ask it to correct the same JSON."
        ),
    }
    if include_catalog:
        bundle["existing_codes"] = existing_codes()
    return bundle


def existing_codes() -> dict[str, Any]:
    """Codes already in use, so an authoring LLM can avoid or deliberately override them."""
    out: dict[str, Any] = {"skills": [], "powers": [], "items": []}
    try:
        from app.skill_checks import BUILTIN_SKILLS

        out["skills"] = sorted({s["code"] for s in BUILTIN_SKILLS} | set(active_skills()))
    except Exception:
        out["skills"] = sorted(active_skills())
    out["powers"] = sorted(active_powers())
    out["items"] = sorted(active_items())
    try:
        with connect() as conn:
            out["live_abilities"] = [
                {"code": r["code"], "name": r["name"]}
                for r in conn.execute("SELECT code, name FROM abilities ORDER BY id LIMIT 200").fetchall()
            ]
    except sqlite3.Error:
        out["live_abilities"] = []
    return out
