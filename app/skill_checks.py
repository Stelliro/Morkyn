"""
Dice rolls, skill checks, events, and a durable skill library.

Design:
  - Optional system (toggle dice_checks_enabled).
  - Attribute can fail while a specialized skill still yields partial info.
  - Failures / fumbles can produce bad outcomes (context + GM).
  - New skills are compared to similar catalog entries and kept for future runs.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
from pathlib import Path
from typing import Any


# --- built-in catalog --------------------------------------------------------

# Categories cover general RPG + Mørkyn multi-genre (fantasy, tech, social, travel).
BUILTIN_SKILLS: list[dict[str, Any]] = [
    # Physical
    {"code": "strength", "name": "Strength", "category": "physical", "attribute": "strength", "secondary": "constitution", "tags": ["force", "lift", "break"], "base_dc": 12, "description": "Raw force, lifting, breaking, shoving."},
    {"code": "constitution", "name": "Constitution", "category": "physical", "attribute": "constitution", "secondary": "strength", "tags": ["endurance", "poison", "fatigue"], "base_dc": 12, "description": "Endurance, resistance to poison, cold, fatigue."},
    {"code": "athletics", "name": "Athletics", "category": "physical", "attribute": "strength", "secondary": "constitution", "tags": ["climb", "swim", "run"], "base_dc": 12, "description": "Climbing, swimming, running, jumping."},
    {"code": "acrobatics", "name": "Acrobatics", "category": "physical", "attribute": "dexterity", "secondary": "strength", "tags": ["balance", "tumble", "dodge"], "base_dc": 13, "description": "Balance, tumbling, landing, tightrope motion."},
    {"code": "stealth", "name": "Stealth", "category": "physical", "attribute": "dexterity", "secondary": "wisdom", "tags": ["hide", "sneak", "shadow"], "base_dc": 13, "description": "Hiding, silent movement, avoiding notice."},
    {"code": "sleight_of_hand", "name": "Sleight of Hand", "category": "physical", "attribute": "dexterity", "secondary": "intelligence", "tags": ["pickpocket", "palming", "tricks"], "base_dc": 14, "description": "Palming, pickpocketing, plant/switch objects."},
    {"code": "survival", "name": "Survival", "category": "physical", "attribute": "wisdom", "secondary": "constitution", "tags": ["track", "camp", "forage"], "base_dc": 12, "description": "Tracking, foraging, weather, wild hazards."},
    {"code": "medicine", "name": "Medicine", "category": "physical", "attribute": "wisdom", "secondary": "intelligence", "tags": ["first_aid", "diagnosis", "stabilize"], "base_dc": 13, "description": "First aid, diagnosis, stabilize wounds."},
    # Mental
    {"code": "intelligence", "name": "Intelligence", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["logic", "recall", "analysis"], "base_dc": 12, "description": "Raw analysis, recall, puzzle logic."},
    {"code": "wisdom", "name": "Wisdom", "category": "mental", "attribute": "wisdom", "secondary": "intelligence", "tags": ["judgment", "intuition"], "base_dc": 12, "description": "Judgment, gut read, practical sense."},
    {"code": "perception", "name": "Perception", "category": "mental", "attribute": "wisdom", "secondary": "intelligence", "tags": ["notice", "spot", "listen"], "base_dc": 12, "description": "Noticing details, sounds, motion, traps."},
    {"code": "investigation", "name": "Investigation", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["search", "clue", "deduce"], "base_dc": 13, "description": "Active search, connecting clues, reconstruction."},
    {"code": "symbol_lore", "name": "Symbol Lore", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["runes", "glyphs", "sigils", "symbols"], "base_dc": 14, "description": "Reading glyphs, runes, heraldic marks, occult symbols."},
    {"code": "arcana", "name": "Arcana", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["magic", "spell", "ward"], "base_dc": 14, "description": "Magical theory, wards, spell residue."},
    {"code": "history", "name": "History", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["past", "dates", "lineage"], "base_dc": 12, "description": "Past events, houses, wars, old maps."},
    {"code": "religion", "name": "Religion / Rites", "category": "mental", "attribute": "wisdom", "secondary": "intelligence", "tags": ["faith", "rite", "omen"], "base_dc": 13, "description": "Rites, omens, cult practice, sacred law."},
    {"code": "nature", "name": "Nature", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["plants", "beasts", "terrain"], "base_dc": 12, "description": "Plants, beasts, weather patterns, ecology."},
    {"code": "memory", "name": "Memory", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["recall", "face", "phrase"], "base_dc": 12, "description": "Precise recall of faces, phrases, routes."},
    # Social / speech
    {"code": "persuasion", "name": "Persuasion / Speech", "category": "social", "attribute": "charisma", "secondary": "wisdom", "tags": ["speech", "convince", "negotiate"], "base_dc": 12, "description": "Honest persuasion, negotiation, calm speech."},
    {"code": "deception", "name": "Deception", "category": "social", "attribute": "charisma", "secondary": "intelligence", "tags": ["lie", "bluff", "con"], "base_dc": 13, "description": "Lies, bluffs, false identity, misdirection."},
    {"code": "intimidation", "name": "Intimidation", "category": "social", "attribute": "charisma", "secondary": "strength", "tags": ["threat", "pressure"], "base_dc": 12, "description": "Threats, pressure, imposing presence."},
    {"code": "insight", "name": "Insight", "category": "social", "attribute": "wisdom", "secondary": "charisma", "tags": ["read", "motive", "tell"], "base_dc": 13, "description": "Reading motives, tells, half-truths."},
    {"code": "performance", "name": "Performance", "category": "social", "attribute": "charisma", "secondary": "dexterity", "tags": ["song", "act", "story"], "base_dc": 12, "description": "Song, acting, storytelling, stagecraft."},
    {"code": "etiquette", "name": "Etiquette", "category": "social", "attribute": "charisma", "secondary": "intelligence", "tags": ["court", "manners", "protocol"], "base_dc": 13, "description": "Court manners, protocol, formal address."},
    {"code": "streetwise", "name": "Streetwise", "category": "social", "attribute": "wisdom", "secondary": "charisma", "tags": ["rumor", "underworld", "fence"], "base_dc": 12, "description": "Rumors, fences, gangs, city undercurrents."},
    # Craft / tech
    {"code": "craft", "name": "Craft", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["make", "repair", "forge"], "base_dc": 13, "description": "Making and repairing physical goods."},
    {"code": "lockpicking", "name": "Lockpicking", "category": "craft", "attribute": "dexterity", "secondary": "intelligence", "tags": ["lock", "pick", "bypass"], "base_dc": 14, "description": "Locks, latches, simple mechanical seals."},
    {"code": "tinkering", "name": "Tinkering", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["gadget", "mechanism", "jury_rig"], "base_dc": 13, "description": "Mechanisms, gadgets, jury-rigs."},
    {"code": "hacking", "name": "Hacking / Systems", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["console", "network", "code"], "base_dc": 14, "description": "Consoles, networks, access codes (sci-fi / system worlds)."},
    {"code": "vehicles", "name": "Vehicles / Piloting", "category": "craft", "attribute": "dexterity", "secondary": "intelligence", "tags": ["drive", "pilot", "ride"], "base_dc": 12, "description": "Carts, mounts, bikes, ships, craft."},
    {"code": "navigation", "name": "Navigation", "category": "craft", "attribute": "wisdom", "secondary": "intelligence", "tags": ["map", "stars", "route"], "base_dc": 12, "description": "Maps, stars, route planning, dead reckoning."},
    # Combat
    {"code": "melee", "name": "Melee", "category": "combat", "attribute": "strength", "secondary": "dexterity", "tags": ["blade", "brawl", "strike"], "base_dc": 12, "description": "Close combat attacks and contests."},
    {"code": "ranged", "name": "Ranged", "category": "combat", "attribute": "dexterity", "secondary": "wisdom", "tags": ["bow", "gun", "throw"], "base_dc": 12, "description": "Bows, thrown weapons, firearms if present."},
    {"code": "defense", "name": "Defense", "category": "combat", "attribute": "dexterity", "secondary": "constitution", "tags": ["block", "parry", "guard"], "base_dc": 12, "description": "Blocking, parrying, holding a line."},
    {"code": "tactics", "name": "Tactics", "category": "combat", "attribute": "intelligence", "secondary": "wisdom", "tags": ["plan", "ambush", "formation"], "base_dc": 13, "description": "Battlefield reads, ambush setup, formation calls."},
    # Events / encounters (meta checks the GM can call)
    {"code": "random_encounter", "name": "Random Encounter", "category": "encounter", "attribute": "wisdom", "secondary": "dexterity", "tags": ["event", "road", "risk"], "base_dc": 12, "description": "Whether the road/event table produces trouble or opportunity."},
    {"code": "ambush_sense", "name": "Ambush Sense", "category": "encounter", "attribute": "wisdom", "secondary": "dexterity", "tags": ["ambush", "alert"], "base_dc": 13, "description": "Spotting or avoiding ambushes and sudden pressure."},
    {"code": "pursuit", "name": "Pursuit / Chase", "category": "encounter", "attribute": "constitution", "secondary": "dexterity", "tags": ["chase", "flee", "catch"], "base_dc": 13, "description": "Chases, escapes, and hunting someone through terrain."},
    {"code": "hazard", "name": "Hazard Avoidance", "category": "event", "attribute": "dexterity", "secondary": "wisdom", "tags": ["trap", "collapse", "spill"], "base_dc": 13, "description": "Traps, collapses, sudden environmental danger."},
    {"code": "discovery", "name": "Discovery", "category": "event", "attribute": "intelligence", "secondary": "wisdom", "tags": ["find", "ruin", "cache"], "base_dc": 13, "description": "Finding hidden places, caches, or story hooks while exploring."},
    {"code": "omen", "name": "Omen Reading", "category": "event", "attribute": "wisdom", "secondary": "intelligence", "tags": ["omen", "dream", "sign"], "base_dc": 14, "description": "Interpreting omens, dreams, and diegetic system signs."},
    {"code": "luck", "name": "Luck", "category": "general", "attribute": "charisma", "secondary": "wisdom", "tags": ["chance", "fate", "gamble"], "base_dc": 12, "description": "Pure chance when no skill cleanly applies."},
    {"code": "general", "name": "General Check", "category": "general", "attribute": "intelligence", "secondary": "wisdom", "tags": ["any", "fallback"], "base_dc": 12, "description": "Fallback when no specialized skill fits."},
]

CATEGORIES = [
    {"id": "physical", "label": "Physical", "blurb": "Body, endurance, stealth, survival."},
    {"id": "mental", "label": "Mental", "blurb": "Analysis, lore, perception, symbols."},
    {"id": "social", "label": "Social / Speech", "blurb": "Talk, read people, etiquette, street."},
    {"id": "craft", "label": "Craft / Tech", "blurb": "Tools, systems, vehicles, locks."},
    {"id": "combat", "label": "Combat", "blurb": "Fight, defend, tactics."},
    {"id": "event", "label": "Events", "blurb": "Hazards, discovery, omens."},
    {"id": "encounter", "label": "Encounters", "blurb": "Road risk, ambush, pursuit."},
    {"id": "general", "label": "General", "blurb": "Luck and fallback checks."},
]

DIFFICULTY_DC_SHIFT = {
    "trivial": -4,
    "easy": -2,
    "normal": 0,
    "hard": 2,
    "brutal": 4,
    "legendary": 6,
}

OUTCOME_RANK = {
    "critical_failure": 0,
    "failure": 1,
    "partial": 2,
    "success": 3,
    "critical_success": 4,
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _codeify(name: str) -> str:
    raw = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")
    return (raw or "skill")[:64]


def default_check_settings() -> dict[str, Any]:
    return {
        "dice_checks_enabled": False,
        "dice_sides": 20,
        "check_difficulty": "normal",
        "show_rolls_in_ui": True,
        "partial_on_specialized_skill": True,
        "negative_outcomes": True,
        "crit_on_natural_max": True,
        "fumble_on_natural_1": True,
        "attribute_floor_for_partial": 6,
        "specialized_skill_partial_threshold": 2,
        "event_check_frequency": "normal",  # rare / normal / frequent
        "encounter_check_frequency": "normal",
        "enabled_categories": [c["id"] for c in CATEGORIES],
        "enabled_skill_codes": [s["code"] for s in BUILTIN_SKILLS],
        "custom_check_notes": "",
    }


def merge_check_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_check_settings()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key, value in raw.items():
        if key in out or key in {
            "dice_checks_enabled",
            "dice_sides",
            "check_difficulty",
            "show_rolls_in_ui",
            "partial_on_specialized_skill",
            "negative_outcomes",
            "crit_on_natural_max",
            "fumble_on_natural_1",
            "attribute_floor_for_partial",
            "specialized_skill_partial_threshold",
            "event_check_frequency",
            "encounter_check_frequency",
            "enabled_categories",
            "enabled_skill_codes",
            "custom_check_notes",
        }:
            out[key] = value
    # normalize types
    out["dice_checks_enabled"] = bool(out.get("dice_checks_enabled"))
    try:
        out["dice_sides"] = max(2, min(100, int(out.get("dice_sides") or 20)))
    except (TypeError, ValueError):
        out["dice_sides"] = 20
    out["check_difficulty"] = str(out.get("check_difficulty") or "normal").lower()
    if out["check_difficulty"] not in DIFFICULTY_DC_SHIFT:
        out["check_difficulty"] = "normal"
    out["show_rolls_in_ui"] = bool(out.get("show_rolls_in_ui", True))
    out["partial_on_specialized_skill"] = bool(out.get("partial_on_specialized_skill", True))
    out["negative_outcomes"] = bool(out.get("negative_outcomes", True))
    out["crit_on_natural_max"] = bool(out.get("crit_on_natural_max", True))
    out["fumble_on_natural_1"] = bool(out.get("fumble_on_natural_1", True))
    try:
        out["attribute_floor_for_partial"] = max(1, min(20, int(out.get("attribute_floor_for_partial") or 6)))
    except (TypeError, ValueError):
        out["attribute_floor_for_partial"] = 6
    try:
        out["specialized_skill_partial_threshold"] = max(1, min(20, int(out.get("specialized_skill_partial_threshold") or 2)))
    except (TypeError, ValueError):
        out["specialized_skill_partial_threshold"] = 2
    freq_ok = {"rare", "normal", "frequent", "off"}
    for fk in ("event_check_frequency", "encounter_check_frequency"):
        val = str(out.get(fk) or "normal").lower()
        out[fk] = val if val in freq_ok else "normal"
    cats = out.get("enabled_categories")
    if isinstance(cats, list) and cats:
        out["enabled_categories"] = [str(c) for c in cats]
    else:
        out["enabled_categories"] = [c["id"] for c in CATEGORIES]
    codes = out.get("enabled_skill_codes")
    if isinstance(codes, list) and codes:
        out["enabled_skill_codes"] = [str(c) for c in codes]
    else:
        out["enabled_skill_codes"] = [s["code"] for s in BUILTIN_SKILLS]
    out["custom_check_notes"] = str(out.get("custom_check_notes") or "")[:1200]
    return out


def settings_from_setup(options: dict[str, Any] | None) -> dict[str, Any]:
    """Pull check settings from setup form / playthrough options."""
    opts = options or {}
    # Nested object preferred
    nested = opts.get("skill_check_settings") if isinstance(opts.get("skill_check_settings"), dict) else {}
    raw = {**nested}

    def _bool(name: str, default: bool = False) -> bool:
        if name in raw:
            return bool(raw[name])
        if name in opts:
            val = opts[name]
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in {"1", "true", "yes", "on"}
        return default

    raw["dice_checks_enabled"] = _bool("dice_checks_enabled", False)
    for key in (
        "show_rolls_in_ui",
        "partial_on_specialized_skill",
        "negative_outcomes",
        "crit_on_natural_max",
        "fumble_on_natural_1",
    ):
        if key in opts or key in raw:
            raw[key] = _bool(key, bool(default_check_settings().get(key)))
    for key in (
        "dice_sides",
        "check_difficulty",
        "attribute_floor_for_partial",
        "specialized_skill_partial_threshold",
        "event_check_frequency",
        "encounter_check_frequency",
        "custom_check_notes",
    ):
        if key in opts and key not in raw:
            raw[key] = opts[key]
    # multi-select categories / skills from form (comma lists or arrays)
    for key in ("enabled_categories", "enabled_skill_codes"):
        if key in opts and key not in raw:
            val = opts[key]
            if isinstance(val, str):
                raw[key] = [p.strip() for p in val.split(",") if p.strip()]
            else:
                raw[key] = val
    return merge_check_settings(raw)


# --- library persistence -----------------------------------------------------


def _library_path() -> Path:
    root = Path(os.getenv("AI_RPG_SKILL_LIBRARY") or (Path("data") / "skill_library.json"))
    return root


def _skill_row(raw: dict[str, Any], *, source: str = "built-in") -> dict[str, Any]:
    name = str(raw.get("name") or raw.get("code") or "Skill").strip()[:80]
    code = str(raw.get("code") or _codeify(name))[:64]
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    related = raw.get("related_codes") or []
    if isinstance(related, str):
        related = [t.strip() for t in related.split(",") if t.strip()]
    try:
        base_dc = int(raw.get("base_dc") or 12)
    except (TypeError, ValueError):
        base_dc = 12
    return {
        "code": code,
        "name": name,
        "category": str(raw.get("category") or "general")[:40],
        "attribute": str(raw.get("attribute") or raw.get("attribute_primary") or "intelligence")[:40],
        "secondary": str(raw.get("secondary") or raw.get("attribute_secondary") or "wisdom")[:40],
        "tags": [str(t)[:40] for t in tags][:16],
        "related_codes": [str(t)[:64] for t in related][:12],
        "base_dc": max(5, min(30, base_dc)),
        "description": str(raw.get("description") or "")[:400],
        "enabled": bool(raw.get("enabled", True)),
        "source": str(raw.get("source") or source)[:40],
        "times_seen": int(raw.get("times_seen") or 0),
        "adjusted_from": str(raw.get("adjusted_from") or "")[:64],
        "updated_at": str(raw.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%S")),
    }


def load_skill_library() -> list[dict[str, Any]]:
    path = _library_path()
    built = [_skill_row(s, source="built-in") for s in BUILTIN_SKILLS]
    by_code = {s["code"]: s for s in built}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw.get("skills") if isinstance(raw, dict) else raw
            for item in items or []:
                if not isinstance(item, dict):
                    continue
                row = _skill_row(item, source=str(item.get("source") or "user"))
                # Built-ins win on code identity for core fields but keep times_seen / enabled from file.
                if row["code"] in by_code and row["source"] != "built-in":
                    base = dict(by_code[row["code"]])
                    base["enabled"] = row.get("enabled", base["enabled"])
                    base["times_seen"] = max(int(base.get("times_seen") or 0), int(row.get("times_seen") or 0))
                    base["related_codes"] = list(dict.fromkeys((base.get("related_codes") or []) + (row.get("related_codes") or [])))[:12]
                    by_code[row["code"]] = base
                else:
                    by_code[row["code"]] = row
        except Exception:
            pass
    return sorted(by_code.values(), key=lambda s: (s.get("category") or "", s.get("name") or ""))


def save_skill_library(skills: list[dict[str, Any]]) -> Path:
    path = _library_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": "morkyn-skill-library-v1",
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "skills": [_skill_row(s, source=str(s.get("source") or "user")) for s in skills if isinstance(s, dict)],
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def skill_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    """0..1 similarity for merge / adjust decisions."""
    score = 0.0
    if _norm(a.get("name") or "") and _norm(a.get("name") or "") == _norm(b.get("name") or ""):
        return 1.0
    if a.get("code") and a.get("code") == b.get("code"):
        return 1.0
    if a.get("category") and a.get("category") == b.get("category"):
        score += 0.25
    if a.get("attribute") and a.get("attribute") == b.get("attribute"):
        score += 0.2
    tags_a = {_norm(t) for t in (a.get("tags") or []) if t}
    tags_b = {_norm(t) for t in (b.get("tags") or []) if t}
    if tags_a and tags_b:
        score += 0.35 * (len(tags_a & tags_b) / max(1, len(tags_a | tags_b)))
    # token overlap on names
    na = set(_norm(a.get("name") or "").split())
    nb = set(_norm(b.get("name") or "").split())
    if na and nb:
        score += 0.2 * (len(na & nb) / max(1, len(na | nb)))
    return min(1.0, score)


def find_similar_skills(candidate: dict[str, Any], library: list[dict[str, Any]] | None = None, *, limit: int = 5) -> list[dict[str, Any]]:
    lib = library if library is not None else load_skill_library()
    scored = []
    for skill in lib:
        if skill.get("code") == candidate.get("code"):
            continue
        sim = skill_similarity(candidate, skill)
        if sim >= 0.35:
            scored.append({**skill, "similarity": round(sim, 3)})
    scored.sort(key=lambda s: s.get("similarity") or 0, reverse=True)
    return scored[:limit]


def register_or_adjust_skill(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Add a skill from play or settings. If similar skills exist, inherit base_dc /
    related links and record adjusted_from.
    """
    library = load_skill_library()
    row = _skill_row(payload, source=str(payload.get("source") or "playthrough"))
    similar = find_similar_skills(row, library, limit=5)
    if similar:
        best = similar[0]
        # Pull DC toward peers so new skills don't spawn wildly easy/hard.
        peer_dcs = [int(s.get("base_dc") or 12) for s in similar[:3]]
        avg = sum(peer_dcs) / max(1, len(peer_dcs))
        row["base_dc"] = max(5, min(30, int(round((row["base_dc"] + avg) / 2))))
        row["related_codes"] = list(
            dict.fromkeys(
                list(row.get("related_codes") or [])
                + [s["code"] for s in similar if s.get("code")]
                + list(best.get("related_codes") or [])
            )
        )[:12]
        if not row.get("category") or row["category"] == "general":
            row["category"] = best.get("category") or row["category"]
        row["adjusted_from"] = str(best.get("code") or "")
        if not row.get("description") and best.get("description"):
            row["description"] = f"Related to {best.get('name')}: {best.get('description')}"[:400]

    existing = next((s for s in library if s.get("code") == row["code"]), None)
    if existing:
        existing["times_seen"] = int(existing.get("times_seen") or 0) + 1
        existing["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        if row.get("description") and len(row["description"]) > len(str(existing.get("description") or "")):
            existing["description"] = row["description"]
        existing["related_codes"] = list(dict.fromkeys((existing.get("related_codes") or []) + (row.get("related_codes") or [])))[:12]
        existing["base_dc"] = row["base_dc"]
        if row.get("adjusted_from"):
            existing["adjusted_from"] = row["adjusted_from"]
        save_skill_library(library)
        return {"skill": existing, "created": False, "similar": similar}
    row["times_seen"] = 1
    library.append(row)
    save_skill_library(library)
    return {"skill": row, "created": True, "similar": similar}


def set_skill_enabled(code: str, enabled: bool) -> dict[str, Any] | None:
    library = load_skill_library()
    for skill in library:
        if skill.get("code") == code:
            skill["enabled"] = bool(enabled)
            skill["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            save_skill_library(library)
            return skill
    return None


# --- resolution --------------------------------------------------------------


def _attr_score(stats: dict[str, Any] | None, key: str) -> int:
    if not isinstance(stats, dict):
        return 10
    aliases = {
        "strength": {"strength", "str", "might", "power"},
        "dexterity": {"dexterity", "dex", "agility", "speed"},
        "constitution": {"constitution", "con", "endurance", "vitality"},
        "intelligence": {"intelligence", "int", "intellect", "mind"},
        "wisdom": {"wisdom", "wis", "insight", "perception"},
        "charisma": {"charisma", "cha", "presence", "speech"},
    }
    wanted = aliases.get((key or "").lower(), { (key or "").lower() })
    for name, value in stats.items():
        if str(name).strip().lower() in wanted or re.sub(r"[^a-z]", "", str(name).lower()) in wanted:
            try:
                return max(1, min(30, int(value)))
            except (TypeError, ValueError):
                continue
    return 10


def _skill_rank(skills: list[dict[str, Any]] | None, code_or_name: str) -> int:
    if not skills:
        return 0
    needle = _norm(code_or_name)
    code = _codeify(code_or_name)
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        if _codeify(str(skill.get("code") or skill.get("name") or "")) == code:
            try:
                return max(0, min(20, int(skill.get("level") or skill.get("rank") or skill.get("value") or 0)))
            except (TypeError, ValueError):
                return 1
        if _norm(str(skill.get("name") or "")) == needle:
            try:
                return max(0, min(20, int(skill.get("level") or skill.get("rank") or skill.get("value") or 0)))
            except (TypeError, ValueError):
                return 1
    return 0


def attribute_modifier(score: int) -> int:
    """Mild 1..30 curve → roughly -4..+8, centered near 10."""
    return max(-5, min(10, (int(score) - 10) // 2))


def resolve_check(
    *,
    skill_code: str = "general",
    difficulty: str | None = None,
    dc: int | None = None,
    player_stats: dict[str, Any] | None = None,
    player_skills: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    context_note: str = "",
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """
    Roll a check. Specialized skills can salvage partial success when the linked
    attribute is low but skill rank is enough.
    """
    cfg = merge_check_settings(settings)
    if not cfg.get("dice_checks_enabled"):
        return {
            "enabled": False,
            "outcome": "narrative",
            "detail": "Dice checks are disabled; resolve narratively.",
            "context_note": context_note,
        }

    library = {s["code"]: s for s in load_skill_library()}
    skill = library.get(skill_code) or library.get(_codeify(skill_code))
    if not skill:
        # ad-hoc skill: register lightly
        reg = register_or_adjust_skill({"name": skill_code, "source": "playthrough"})
        skill = reg["skill"]

    sides = int(cfg["dice_sides"])
    diff = (difficulty or cfg.get("check_difficulty") or "normal").lower()
    shift = DIFFICULTY_DC_SHIFT.get(diff, 0)
    target_dc = int(dc) if dc is not None else int(skill.get("base_dc") or 12) + shift

    attr_key = str(skill.get("attribute") or "intelligence")
    attr_score = _attr_score(player_stats, attr_key)
    attr_mod = attribute_modifier(attr_score)
    skill_rank = _skill_rank(player_skills, skill.get("code") or skill.get("name") or "")
    skill_mod = skill_rank  # 1:1 rank for v1 simplicity
    total_mod = attr_mod + skill_mod

    roller = rng or random.Random()
    natural = roller.randint(1, sides)
    total = natural + total_mod

    crit = bool(cfg.get("crit_on_natural_max")) and natural == sides
    fumble = bool(cfg.get("fumble_on_natural_1")) and natural == 1

    # Specialized salvage: low attribute, enough skill → partial instead of hard fail
    specialized_partial = False
    if (
        cfg.get("partial_on_specialized_skill")
        and skill_rank >= int(cfg.get("specialized_skill_partial_threshold") or 2)
        and attr_score < int(cfg.get("attribute_floor_for_partial") or 6)
        and total < target_dc
        and not fumble
    ):
        specialized_partial = True

    if fumble:
        outcome = "critical_failure"
    elif crit and total >= target_dc:
        outcome = "critical_success"
    elif specialized_partial:
        outcome = "partial"
    elif total >= target_dc + max(4, sides // 5):
        outcome = "critical_success" if crit else "success"
    elif total >= target_dc:
        outcome = "success"
    elif total >= target_dc - 3:
        outcome = "partial" if cfg.get("partial_on_specialized_skill") else "failure"
    else:
        outcome = "failure"

    negative = bool(cfg.get("negative_outcomes")) and outcome in {"failure", "critical_failure"}
    guidance = {
        "critical_success": "Full clear success; extra useful detail or a clean advantage is appropriate.",
        "success": "The check works as intended; grant the requested info or effect.",
        "partial": "Incomplete result: specialized skill or near-miss yields something useful but incomplete, delayed, risky, or costly.",
        "failure": "The attempt fails. If negative outcomes are on, apply a setback appropriate to context.",
        "critical_failure": "Bad break: complication, wrong reading, injury risk, alarm, or lost opportunity.",
    }

    return {
        "enabled": True,
        "skill": {
            "code": skill.get("code"),
            "name": skill.get("name"),
            "category": skill.get("category"),
            "attribute": attr_key,
        },
        "dice": f"d{sides}",
        "natural": natural,
        "modifier": total_mod,
        "attribute_score": attr_score,
        "attribute_mod": attr_mod,
        "skill_rank": skill_rank,
        "skill_mod": skill_mod,
        "total": total,
        "dc": target_dc,
        "difficulty": diff,
        "outcome": outcome,
        "margin": total - target_dc,
        "specialized_partial": specialized_partial,
        "negative_outcome_suggested": negative,
        "crit": crit,
        "fumble": fumble,
        "guidance": guidance.get(outcome, ""),
        "context_note": str(context_note or "")[:400],
        "display": f"[{skill.get('name')}] d{sides}:{natural}{total_mod:+d} = {total} vs DC {target_dc} → {outcome.replace('_', ' ')}",
    }


def catalog_public() -> dict[str, Any]:
    skills = load_skill_library()
    return {
        "categories": CATEGORIES,
        "skills": skills,
        "defaults": default_check_settings(),
        "difficulty_dc_shift": DIFFICULTY_DC_SHIFT,
        "outcomes": list(OUTCOME_RANK.keys()),
    }


def gm_context_block(settings: dict[str, Any] | None, library: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Compact packet for prompt context / playthrough options."""
    cfg = merge_check_settings(settings)
    if not cfg.get("dice_checks_enabled"):
        return {"dice_checks_enabled": False}
    lib = library if library is not None else load_skill_library()
    enabled_codes = set(cfg.get("enabled_skill_codes") or [])
    enabled_cats = set(cfg.get("enabled_categories") or [])
    active = [
        {
            "code": s["code"],
            "name": s["name"],
            "category": s["category"],
            "attribute": s["attribute"],
            "base_dc": s["base_dc"],
        }
        for s in lib
        if s.get("enabled") and (not enabled_codes or s["code"] in enabled_codes) and (not enabled_cats or s.get("category") in enabled_cats)
    ]
    return {
        "dice_checks_enabled": True,
        "dice_sides": cfg["dice_sides"],
        "check_difficulty": cfg["check_difficulty"],
        "partial_on_specialized_skill": cfg["partial_on_specialized_skill"],
        "negative_outcomes": cfg["negative_outcomes"],
        "event_check_frequency": cfg["event_check_frequency"],
        "encounter_check_frequency": cfg["encounter_check_frequency"],
        "custom_check_notes": cfg.get("custom_check_notes") or "",
        "rules": [
            "When a check matters (inspect symbols, force a door, talk down a guard), call for a skill check by code.",
            "If the linked attribute is low but a specialized skill rank is present, prefer partial success with incomplete info rather than total blank.",
            "On failure/critical failure with negative_outcomes, apply a concrete setback (wrong reading, alarm, injury risk, lost time, burned favor).",
            "New skills discovered in play should be registered and compared to similar catalog skills for DC balance.",
        ],
        "active_skills": active[:80],
    }
