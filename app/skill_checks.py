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
    {"code": "disguise", "name": "Disguise", "category": "social", "attribute": "charisma", "secondary": "dexterity", "tags": ["costume", "impersonate", "mask"], "base_dc": 14, "description": "Costumes, false roles, blending into a crowd or court."},
    {"code": "gambling", "name": "Gambling", "category": "social", "attribute": "charisma", "secondary": "intelligence", "tags": ["cards", "dice", "wager"], "base_dc": 13, "description": "Games of chance, reading a table, knowing when to fold."},
    {"code": "appraise", "name": "Appraise", "category": "social", "attribute": "intelligence", "secondary": "wisdom", "tags": ["value", "forge", "price"], "base_dc": 13, "description": "Judging value, fakes, and market price of goods."},
    # Craft / tech
    {"code": "craft", "name": "Craft", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["make", "repair", "forge"], "base_dc": 13, "description": "Making and repairing physical goods."},
    {"code": "smithing", "name": "Smithing", "category": "craft", "attribute": "strength", "secondary": "intelligence", "tags": ["forge", "metal", "hammer"], "base_dc": 14, "description": "Working metal, edges, fittings, and forge heat."},
    {"code": "cooking", "name": "Cooking", "category": "craft", "attribute": "wisdom", "secondary": "intelligence", "tags": ["food", "preserve", "campfire"], "base_dc": 12, "description": "Preparing meals, preserving food, campfire cookery."},
    {"code": "animal_handling", "name": "Animal Handling", "category": "craft", "attribute": "wisdom", "secondary": "charisma", "tags": ["mount", "herd", "tame"], "base_dc": 12, "description": "Calming, directing, or reading beasts and mounts."},
    {"code": "farming", "name": "Farming", "category": "craft", "attribute": "constitution", "secondary": "wisdom", "tags": ["crop", "soil", "harvest"], "base_dc": 12, "description": "Crops, soil, seasons, and rural labor."},
    {"code": "mining", "name": "Mining", "category": "craft", "attribute": "strength", "secondary": "constitution", "tags": ["ore", "tunnel", "dig"], "base_dc": 13, "description": "Digging, ore sense, tunnel safety."},
    {"code": "lockpicking", "name": "Lockpicking", "category": "craft", "attribute": "dexterity", "secondary": "intelligence", "tags": ["lock", "pick", "bypass"], "base_dc": 14, "description": "Locks, latches, simple mechanical seals."},
    {"code": "tinkering", "name": "Tinkering", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["gadget", "mechanism", "jury_rig"], "base_dc": 13, "description": "Mechanisms, gadgets, jury-rigs."},
    {"code": "hacking", "name": "Hacking / Systems", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["console", "network", "code"], "base_dc": 14, "description": "Consoles, networks, access codes (sci-fi / system worlds)."},
    {"code": "vehicles", "name": "Vehicles / Piloting", "category": "craft", "attribute": "dexterity", "secondary": "intelligence", "tags": ["drive", "pilot", "ride"], "base_dc": 12, "description": "Carts, mounts, bikes, ships, craft."},
    {"code": "navigation", "name": "Navigation", "category": "craft", "attribute": "wisdom", "secondary": "intelligence", "tags": ["map", "stars", "route"], "base_dc": 12, "description": "Maps, stars, route planning, dead reckoning."},
    {"code": "cartography", "name": "Cartography", "category": "craft", "attribute": "intelligence", "secondary": "wisdom", "tags": ["map", "sketch", "survey"], "base_dc": 13, "description": "Drawing maps, surveying landmarks, correcting charts."},
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
    # Occult / support (for wild seed domains that graduate into catalog skills)
    {"code": "healing", "name": "Healing Arts", "category": "physical", "attribute": "wisdom", "secondary": "intelligence", "tags": ["heal", "triage", "bandage", "support"], "base_dc": 13, "description": "Stabilizing wounds, triage, field medicine, recovery rites."},
    {"code": "support", "name": "Support Craft", "category": "social", "attribute": "wisdom", "secondary": "charisma", "tags": ["buff", "rally", "aid", "cover"], "base_dc": 12, "description": "Rallying allies, covering, pacing a fight, non-damage help."},
    {"code": "summoning", "name": "Summoning", "category": "mental", "attribute": "charisma", "secondary": "wisdom", "tags": ["summon", "spirit", "pact", "call"], "base_dc": 14, "description": "Calling minor spirits, familiars, or bound helpers."},
    {"code": "necromancy", "name": "Necromancy", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["undead", "bone", "grave", "soul"], "base_dc": 15, "description": "Grave rites, bone sense, restless dead, soul residue."},
    {"code": "exorcism", "name": "Exorcism", "category": "mental", "attribute": "wisdom", "secondary": "charisma", "tags": ["banish", "cleanse", "ward", "spirit"], "base_dc": 14, "description": "Driving out unclean presence, blessing, salt and prayer."},
    {"code": "alchemy", "name": "Alchemy", "category": "craft", "attribute": "intelligence", "secondary": "dexterity", "tags": ["potion", "reagent", "brew"], "base_dc": 14, "description": "Brews, reagents, unstable mixtures, antidotes."},
    {"code": "ritual", "name": "Ritual", "category": "mental", "attribute": "intelligence", "secondary": "wisdom", "tags": ["circle", "rite", "ceremony"], "base_dc": 14, "description": "Circles, ceremonies, multi-step magical procedures."},
    {"code": "weapon_art", "name": "Weapon Art", "category": "combat", "attribute": "dexterity", "secondary": "strength", "tags": ["weapon", "form", "kata", "style"], "base_dc": 13, "description": "Specialized forms bound to a weapon type or named blade."},
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
        # On by default so talk/sneak/force actions get server-side rolls.
        "dice_checks_enabled": True,
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
        # Contested / power curve
        "contested_checks": True,
        "power_rng": True,
        "power_variance": 3,
        "unskilled_mishaps": True,
        "unskilled_rank_threshold": 1,
        "severe_mishap_on_crit_fail": True,
        "auto_check_on_risky_actions": True,
        # Craft and trade work with no matching or related proficiency rolls at
        # this penalty (playtest #85a). Talk and look are not trained-only.
        "untrained_penalty": 2,
        # Always attempt a social reaction when the player opens talk
        "auto_social_on_talk": True,
        "degree_flavor": True,
        "append_roll_to_narration": False,
    }


def merge_check_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    base = default_check_settings()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    for key, value in raw.items():
        if key in base or key in {
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
            "contested_checks",
            "power_rng",
            "power_variance",
            "unskilled_mishaps",
            "unskilled_rank_threshold",
            "severe_mishap_on_crit_fail",
            "auto_check_on_risky_actions",
            "degree_flavor",
            "append_roll_to_narration",
            "untrained_penalty",
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
    for bkey in (
        "show_rolls_in_ui",
        "partial_on_specialized_skill",
        "negative_outcomes",
        "crit_on_natural_max",
        "fumble_on_natural_1",
        "contested_checks",
        "power_rng",
        "unskilled_mishaps",
        "severe_mishap_on_crit_fail",
        "auto_check_on_risky_actions",
        "degree_flavor",
        "append_roll_to_narration",
    ):
        out[bkey] = bool(out.get(bkey, base.get(bkey)))
    try:
        out["attribute_floor_for_partial"] = max(1, min(20, int(out.get("attribute_floor_for_partial") or 6)))
    except (TypeError, ValueError):
        out["attribute_floor_for_partial"] = 6
    try:
        out["specialized_skill_partial_threshold"] = max(1, min(20, int(out.get("specialized_skill_partial_threshold") or 2)))
    except (TypeError, ValueError):
        out["specialized_skill_partial_threshold"] = 2
    try:
        out["power_variance"] = max(0, min(10, int(out.get("power_variance") or 3)))
    except (TypeError, ValueError):
        out["power_variance"] = 3
    try:
        out["unskilled_rank_threshold"] = max(0, min(10, int(out.get("unskilled_rank_threshold") or 1)))
    except (TypeError, ValueError):
        out["unskilled_rank_threshold"] = 1
    try:
        out["untrained_penalty"] = max(0, min(6, int(out.get("untrained_penalty"))))
    except (TypeError, ValueError):
        out["untrained_penalty"] = 2
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
        if raw.get(name) is not None:
            return bool(raw[name])
        if opts.get(name) is not None:
            val = opts[name]
            if isinstance(val, bool):
                return val
            return str(val).strip().lower() in {"1", "true", "yes", "on"}
        return default

    # System / isekai playthroughs default dice on unless the user explicitly left them off.
    theme = opts.get("session_theme") if isinstance(opts.get("session_theme"), dict) else {}
    systemish = bool(opts.get("game_system")) or bool(theme.get("isekai")) or str(theme.get("adapter_hint") or "") in {
        "isekai_rpg",
        "system_rpg",
    }
    # A None is "the client did not say" (playtest #85a): SetupRequest used to
    # fill a missing toggle with a hard False, so this default never ran and
    # the player's own "On" was thrown away by a payload that omitted it.
    dice_default = bool(
        systemish and opts.get("dice_checks_enabled") is None and raw.get("dice_checks_enabled") is None
    )
    raw["dice_checks_enabled"] = _bool("dice_checks_enabled", dice_default)
    # Align check difficulty with playthrough difficulty when not set.
    if "check_difficulty" not in raw and "check_difficulty" not in opts:
        play_diff = str(opts.get("difficulty") or "normal").lower()
        if play_diff in DIFFICULTY_DC_SHIFT:
            raw["check_difficulty"] = play_diff
    if systemish and raw.get("dice_checks_enabled"):
        raw.setdefault("unskilled_mishaps", True)
        raw.setdefault("auto_check_on_risky_actions", True)
        raw.setdefault("show_rolls_in_ui", True)
        if str(opts.get("difficulty") or "").lower() in ("hard", "brutal"):
            raw.setdefault("event_check_frequency", "frequent")
    for key in (
        "show_rolls_in_ui",
        "partial_on_specialized_skill",
        "negative_outcomes",
        "crit_on_natural_max",
        "fumble_on_natural_1",
        "contested_checks",
        "power_rng",
        "unskilled_mishaps",
        "severe_mishap_on_crit_fail",
        "auto_check_on_risky_actions",
        "degree_flavor",
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
        "power_variance",
        "unskilled_rank_threshold",
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
    name = humanize_skill_name(str(raw.get("name") or raw.get("code") or "Skill").strip())
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


def _pack_skill_overlay() -> dict[str, dict[str, Any]]:
    """Skills contributed by installed content packs (empty when none/unavailable)."""
    try:
        from app.content_packs import active_skills

        return active_skills()
    except Exception:
        return {}


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

    # Content packs win last: they may retune a built-in's DC/attribute or
    # switch it off entirely with "enabled": false.
    for code, entry in _pack_skill_overlay().items():
        row = _skill_row(entry, source=str(entry.get("source") or "pack"))
        existing = by_code.get(code)
        if existing:
            row["times_seen"] = max(int(existing.get("times_seen") or 0), int(row.get("times_seen") or 0))
        row["triggers"] = list(entry.get("triggers") or [])
        row["opposed_by"] = str(entry.get("opposed_by") or "")
        row["growth"] = entry.get("growth") if isinstance(entry.get("growth"), dict) else {}
        by_code[code] = row

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
    # `_skill_row` defaults category to "general" and attribute to
    # "intelligence" for anything minted in play, so scoring those fields
    # measured our own defaults rather than the skill: every new skill matched
    # every general/intelligence skill at 0.45 against a 0.35 threshold. Only
    # count them when the candidate actually chose them.
    if a.get("category") and a.get("category") != "general" and a.get("category") == b.get("category"):
        score += 0.25
    if a.get("attribute") and a.get("attribute") != "intelligence" and a.get("attribute") == b.get("attribute"):
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


_NAME_SMALL_WORDS = {"of", "the", "a", "an", "in", "on", "at", "to", "and", "or", "for"}


def humanize_skill_name(raw: str) -> str:
    """Turn pick_lock into Pick Lock. Names that already carry case are left alone.

    `resolve_check` mints with the model's raw string as the name, so the
    library filled up with entries called "pick_lock" and "hotwire the truck" --
    and the UI renders that name directly.
    """
    text = str(raw or "").replace("_", " ").strip()
    if not text:
        return "Skill"
    if text != text.lower():
        return text[:80]
    words = [w for w in text.split() if w]
    out = [w if i and w in _NAME_SMALL_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words)]
    return " ".join(out)[:80]


def _unambiguous_tag_index(library: list[dict[str, Any]]) -> dict[str, str]:
    """Tag -> code, keeping only tags owned by exactly one skill.

    Eight tags are shared (recall, ward, rite, omen, forge, map, ambush,
    spirit). Letting a shared tag pick a winner is a coin flip presented as a
    decision, so they are dropped instead.
    """
    owners: dict[str, set[str]] = {}
    for skill in library:
        code = skill.get("code")
        if not code:
            continue
        for tag in skill.get("tags") or []:
            owners.setdefault(_norm(str(tag)), set()).add(code)
    return {tag: next(iter(codes)) for tag, codes in owners.items() if len(codes) == 1}


def resolve_skill_code(text: Any, library: list[dict[str, Any]] | None = None) -> str | None:
    """Canonical skill code for model-supplied text, or None if genuinely new.

    The narrator writes this field as free prose and is never shown the
    catalogue, so "pick the lock" used to miss `lockpicking` -- which was in the
    library the whole time with "lock" among its tags -- and mint a phantom that
    rolled INTELLIGENCE.

    Whole-word matching only. The theme detector shipped `picking` matching
    `king` and `sector` matching `sect`; that shortcut does not come back here.
    Returns None rather than guessing: an honest miss mints a new skill, a
    wrong guess rolls the wrong attribute forever.
    """
    raw = str(text or "").strip()
    if not raw:
        return None
    lib = library if library is not None else load_skill_library()
    by_code = {s.get("code"): s for s in lib if s.get("code")}
    if raw in by_code:
        return raw
    coded = _codeify(raw)
    if coded in by_code:
        return coded
    normalized = _norm(raw)
    for skill in lib:
        if normalized and _norm(str(skill.get("name") or "")) == normalized:
            return skill.get("code")
    tags = _unambiguous_tag_index(lib)
    if normalized in tags:
        return tags[normalized]
    hits = {tags[word] for word in re.findall("[a-z0-9]+", normalized) if word in tags}
    if len(hits) == 1:
        return hits.pop()
    traded = {TRADE_ALIASES[word] for word in normalized.split() if word in TRADE_ALIASES}
    traded = {code for code in traded if code in by_code}
    if len(traded) == 1:
        return traded.pop()
    inferred = infer_check_from_action(raw)
    if inferred and inferred.get("skill_code") in by_code:
        return str(inferred["skill_code"])
    return None


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
        # No description graft. `best` is chosen by skill_similarity, which used
        # to score category and attribute -- fields _skill_row had just
        # defaulted to "general"/"intelligence". That is 0.45 against a 0.35
        # threshold from the defaults alone, so every minted skill matched a
        # general-category skill and inherited its text: "void_surgery" came out
        # described as "Related to General Check: Fallback when no specialized
        # skill fits." An empty description is honest; a borrowed one is not.

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


# Aliases this module needs that `content_packs.STAT_ALIASES` does not carry.
# The two tables used to be independent copies covering the same six stats with
# different words -- content_packs had "awareness" and "stamina", this one had
# "perception" -- so the same NPC stat key resolved differently depending on
# which code path read it. content_packs is now the source and this is the
# delta, so neither loses a word.
_EXTRA_STAT_ALIASES = {"perception": "wisdom"}


def _stat_alias_groups() -> dict[str, set[str]]:
    """canonical stat -> every spelling that resolves to it."""
    try:
        from app.content_packs import STAT_ALIASES, STAT_KEYS

        pairs = dict(STAT_ALIASES)
        canon = list(STAT_KEYS)
    except Exception:  # pragma: no cover - content_packs is optional at import
        pairs, canon = {}, ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]
    pairs.update(_EXTRA_STAT_ALIASES)
    groups = {c: {c} for c in canon}
    for alias, target in pairs.items():
        groups.setdefault(target, {target}).add(alias)
    return groups


def canonical_stat_key(key: str) -> str:
    """Resolve a stat spelling onto one of the six canonical attributes.

    The group table is keyed by canonical name and was only ever matched
    against the *stats dict* keys, so a skill or pack declaring its attribute as
    "awareness" or "stamina" matched nothing and scored the default 10 -- a
    roster that existed but was never consulted from this direction.
    """
    low = str(key or "").strip().lower()
    for canon, spellings in _stat_alias_groups().items():
        if low == canon or low in spellings:
            return canon
    return low


def _attr_score(stats: dict[str, Any] | None, key: str) -> int:
    if not isinstance(stats, dict):
        return 10
    aliases = _stat_alias_groups()
    canon = canonical_stat_key(key)
    wanted = aliases.get(canon, {canon})
    for name, value in stats.items():
        if str(name).strip().lower() in wanted or re.sub(r"[^a-z]", "", str(name).lower()) in wanted:
            try:
                return max(1, min(30, int(value)))
            except (TypeError, ValueError):
                continue
    return 10


_CANON_SCORE_ATTRIBUTES = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)


def scores_from_gear_bonuses(bonuses: dict[str, Any] | None) -> dict[str, int]:
    """Turn an equipment bonus map into 1..30 scores centered on 10.

    Missing attributes are omitted so score readers keep their default of 10.
    Defense, dodge, and notes are not ability scores and are dropped. Callers
    that already hold absolute scores must not pass them through here.
    """
    if not isinstance(bonuses, dict) or not bonuses:
        return {}
    groups = _stat_alias_groups()
    spell_to_canon: dict[str, str] = {}
    for canon in _CANON_SCORE_ATTRIBUTES:
        for spelling in groups.get(canon, {canon}):
            spell_to_canon[str(spelling).strip().lower()] = canon
    totals: dict[str, float] = {}
    for raw_key, raw_value in bonuses.items():
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            continue
        key = str(raw_key or "").strip().lower().replace(" ", "_")
        canon = spell_to_canon.get(key)
        if not canon:
            continue
        totals[canon] = totals.get(canon, 0.0) + float(raw_value)
    out: dict[str, int] = {}
    for canon, bonus in totals.items():
        out[canon] = max(1, min(30, int(round(10 + bonus))))
    return out


def player_with_gear_scores(player: dict[str, Any] | None) -> dict[str, Any]:
    """Copy of a player dict whose effective_stats are scores, not bonuses.

    The caller's map is left alone so combat and carry weight still see the
    raw strength bonus. Only encounter awareness should use the copy.
    """
    view = dict(player) if isinstance(player, dict) else {}
    bonuses = view.get("effective_stats")
    if isinstance(bonuses, dict):
        view["effective_stats"] = scores_from_gear_bonuses(bonuses)
    return view


# Trade words a player skill's name or its "tracked by" note uses, for the
# catalog skill they practise (playtest #85a). Setup writes free names --
# "Rigging ... tracked by carpentry", "Storytelling ... tracked by performance"
# -- and the check matched only an exact catalog name, so every one of them
# counted as 0 and a carpenter rolled a craft check as a stranger to tools.
TRADE_ALIASES: dict[str, str] = {
    "carpentry": "craft",
    "carpenter": "craft",
    "woodwork": "craft",
    "woodworking": "craft",
    "joinery": "craft",
    "rigging": "craft",
    "whittling": "craft",
    "sewing": "craft",
    "tailoring": "craft",
    "leatherwork": "craft",
    "crafting": "craft",
    "blacksmith": "smithing",
    "blacksmithing": "smithing",
    "metalwork": "smithing",
    "metalworking": "smithing",
    "armorer": "smithing",
    "armourer": "smithing",
    "smith": "smithing",
    "smithy": "smithing",
    "storytelling": "performance",
    "stagecraft": "performance",
    "acting": "performance",
    "singing": "performance",
    "music": "performance",
    "herbalism": "nature",
    "herbs": "nature",
    "mechanics": "tinkering",
    "clockwork": "tinkering",
    "engineering": "tinkering",
    "baking": "cooking",
    "brewing": "cooking",
    "labour": "athletics",
    "labor": "athletics",
    "secure": "craft",
}

# A neighbouring trade gives half its rank and spares the untrained penalty
# (playtest #85a): a carpenter polishing a blade is not a stranger to tools.
RELATED_SKILLS: dict[str, tuple[str, ...]] = {
    "smithing": ("craft", "tinkering"),
    "craft": ("smithing", "tinkering"),
    "tinkering": ("craft", "smithing"),
    "cooking": ("alchemy",),
    "alchemy": ("cooking", "nature"),
    "healing": ("medicine",),
    "medicine": ("healing",),
    "performance": ("persuasion",),
    "persuasion": ("performance", "etiquette"),
    "mining": ("athletics",),
    "athletics": ("strength", "constitution"),
}

# Categories where a check with no proficiency at all takes the untrained
# penalty. Everyone talks, looks and climbs; not everyone works metal.
UNTRAINED_PENALTY_CATEGORIES = frozenset({"craft"})

_TRACKED_BY_RE = re.compile(r"\btracked by\s+([^;]+)", re.I)


def _skill_value(skill: dict[str, Any]) -> int:
    try:
        return max(0, min(20, int(skill.get("level") or skill.get("rank") or skill.get("value") or 0)))
    except (TypeError, ValueError):
        return 1


def player_skill_codes(skill: dict[str, Any], library: list[dict[str, Any]] | None = None) -> set[str]:
    """Catalog codes one player skill practises: its own name, its trade words, and its "tracked by" note."""
    lib = library if library is not None else load_skill_library()
    texts = [str(skill.get("code") or ""), str(skill.get("name") or "")]
    tracked = _TRACKED_BY_RE.search(str(skill.get("notes") or skill.get("tracking") or ""))
    if tracked:
        texts.append(tracked.group(1))
    elif skill.get("tracking"):
        texts.append(str(skill.get("tracking")))
    by_code = {s.get("code") for s in lib if s.get("code")}
    codes: set[str] = set()
    for text in texts:
        if not text.strip():
            continue
        for word in _norm(text).split():
            if TRADE_ALIASES.get(word) in by_code:
                codes.add(TRADE_ALIASES[word])
        coded = _codeify(text)
        if coded in by_code:
            codes.add(coded)
        for row in lib:
            if _norm(str(row.get("name") or "")) == _norm(text):
                codes.add(str(row.get("code")))
    return codes


def best_proficiency(
    skills: list[dict[str, Any]] | None,
    skill_code: str,
    library: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The player's best footing for one catalog skill (playtest #85a).

    {"rank", "source", "match"}: match is "exact" (a skill that is, or is
    tracked as, this one), "related" (a neighbouring trade, half rank rounded
    down) or "untrained" (rank 0, source "").
    """
    code = _codeify(skill_code)
    exact: tuple[int, str] | None = None
    related: tuple[int, str] | None = None
    if skills:
        lib = library if library is not None else load_skill_library()
        neighbours = set(RELATED_SKILLS.get(code, ()))
        # A registered skill's own related_codes count too: the library keeps them.
        for row in lib:
            if row.get("code") == code:
                neighbours.update(str(c) for c in (row.get("related_codes") or []))
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            name = str(skill.get("name") or skill.get("code") or "")
            codes = player_skill_codes(skill, lib)
            value = _skill_value(skill)
            if code in codes or _codeify(name) == code:
                if exact is None or value > exact[0]:
                    exact = (value, name)
            elif codes & neighbours:
                if related is None or value // 2 > related[0]:
                    related = (value // 2, name)
    if exact:
        return {"rank": exact[0], "source": exact[1], "match": "exact"}
    if related:
        return {"rank": related[0], "source": related[1], "match": "related"}
    return {"rank": 0, "source": "", "match": "untrained"}


# Words too common to say anything about a trade or a place.
_HOME_STOPWORDS = frozenset(
    """
    about above after again against along also always among another around away back been before behind being
    below beside between both came come comes could does down during each even ever every from front gave give
    goes going gone have having here into just keep kept know last left like little long made make many more most
    much must near never next night none once only other over own part past people place said same should since
    some still such take than that their them then there these they thing this those through time today together
    toward towards under until upon very want water went were what when where which while whole will with within
    without would year years your yours away hour hours day days first second each because still even home town
    house street side open close small large great good well where right long half under over
    """.split()
)


def _home_stems(text: str, skip: set[str] | None = None) -> set[str]:
    out: set[str] = set()
    for word in re.findall(r"[a-z]+", str(text or "").lower()):
        stem = word[:-1] if word.endswith("s") and not word.endswith("ss") else word
        stem = stem[:7]
        if len(stem) >= 4 and word not in _HOME_STOPWORDS and stem not in _HOME_STOPWORDS and stem not in (skip or set()):
            out.add(stem)
    return out


# Skill categories a background can stand in for: the body, the hands and the
# eye. Talking someone round or fighting is never "home ground".
HOME_GROUND_CATEGORIES = frozenset({"physical", "craft", "mental"})


def home_ground(
    player: dict[str, Any] | None,
    skills: list[dict[str, Any]] | None,
    act_text: str,
    place: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """The character's own trade or home ground, when this act is part of it (Saltmarrow #103).

    A "Flat-runner" whose backstory is running the flats failed 3 of 3 mud-bank
    climbs untrained, with injuries: the title, the backstory and the setup
    proficiencies never reached the check. When the act or the place shares a
    distinctive word with the character's title, backstory or proficiency
    names and notes, the check is routine and the best matching proficiency is
    footing: {"source", "rank", "words"}, or None.
    """
    p = player if isinstance(player, dict) else {}
    name_words = _home_stems(str(p.get("name") or "") + " " + str(p.get("public_name") or ""))
    rows = [s for s in skills or [] if isinstance(s, dict)]
    trade_text = " ".join(
        [str(p.get("title") or ""), str(p.get("backstory") or "")]
        + [f"{s.get('name') or ''} {s.get('notes') or ''}" for s in rows]
    )
    trade = _home_stems(trade_text, name_words)
    if not trade:
        return None
    loc = place if isinstance(place, dict) else {}
    act = re.sub(r'"[^"]*"|“[^”]*”', " ", str(act_text or ""))
    act_hits = _home_stems(act, name_words) & trade
    place_hits = _home_stems(f"{loc.get('name') or ''} {loc.get('summary') or ''}", name_words) & trade
    hits = sorted(act_hits | place_hits)
    if not hits:
        return None
    best: tuple[int, str] | None = None
    for s in rows:
        words = _home_stems(f"{s.get('name') or ''} {s.get('notes') or ''}", name_words)
        if words & set(hits):
            value = _skill_value(s)
            if best is None or value > best[0]:
                best = (value, str(s.get("name") or ""))
    # The ground alone is footing for the body (climbing, running, keeping
    # your feet); a craft or a reading of something needs the act itself to
    # be part of the trade.
    out = {"words": hits[:6], "act": bool(act_hits)}
    if best is None:
        source = str(p.get("title") or "").strip() or "background"
        return {**out, "source": source, "rank": 1}
    return {**out, "source": best[1], "rank": max(1, best[0] // 2)}


def _skill_rank(skills: list[dict[str, Any]] | None, code_or_name: str) -> int:
    if not skills:
        return 0
    needle = _norm(code_or_name)
    code = _codeify(code_or_name)
    for skill in skills:
        if not isinstance(skill, dict):
            continue
        if _codeify(str(skill.get("code") or skill.get("name") or "")) == code:
            return _skill_value(skill)
        if _norm(str(skill.get("name") or "")) == needle:
            return _skill_value(skill)
    # A skill tracked as this one counts as this one (playtest #85a): the
    # rosters were there and the lookup ignored them.
    try:
        found = best_proficiency(skills, code)
    except Exception:
        return 0
    return int(found["rank"]) if found["match"] == "exact" else 0


def attribute_modifier(score: int) -> int:
    """Mild 1..30 curve → roughly -4..+8, centered near 10."""
    return max(-5, min(10, (int(score) - 10) // 2))


def _coerce_profile(raw: Any) -> dict[str, int]:
    """Parse a stored roll_profile ({"melee": 2}) from JSON text or dict."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int] = {}
    for key, value in raw.items():
        code = _codeify(key)
        if not code:
            continue
        try:
            out[code] = max(-12, min(12, int(value)))
        except (TypeError, ValueError):
            continue
    return out


def gear_roll_modifiers(
    inventory: list[dict[str, Any]] | None = None,
    abilities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Collect flat check modifiers from equipped items and always-on powers.

    Items carry ``roll_profile`` ({"melee": 2}) and ``power_codes`` pointing at
    abilities; abilities carry their own ``roll_profile``. Both are read-only
    facts about the world, so the roller can apply them without the narrator
    ever doing arithmetic. Only *equipped* items and *unlocked* powers count —
    the same rule that already governs ``player.effective_stats``.
    """
    totals: dict[str, int] = {}
    sources: list[dict[str, Any]] = []
    granted_codes: set[str] = set()

    for item in inventory or []:
        if not isinstance(item, dict):
            continue
        if not str(item.get("equipped_slot") or "").strip():
            continue
        profile = _coerce_profile(item.get("roll_profile"))
        for code, mod in profile.items():
            totals[code] = totals.get(code, 0) + mod
        if profile:
            sources.append(
                {
                    "kind": "item",
                    "code": item.get("code"),
                    "name": item.get("name"),
                    "profile": profile,
                }
            )
        raw_codes = item.get("power_codes")
        if isinstance(raw_codes, str):
            try:
                raw_codes = json.loads(raw_codes or "[]")
            except json.JSONDecodeError:
                raw_codes = []
        for code in raw_codes or []:
            if str(code).strip():
                granted_codes.add(str(code).strip())

    # Powers an item grants may live in a content pack rather than the live
    # abilities table (that table only holds powers the player has earned).
    # Fold those in so an item's declared powers still shift the dice.
    known_codes = {str(a.get("code") or "") for a in (abilities or []) if isinstance(a, dict)}
    pack_abilities: list[dict[str, Any]] = []
    if granted_codes - known_codes:
        try:
            from app.content_packs import active_powers

            pool = active_powers()
            for code in granted_codes - known_codes:
                entry = pool.get(code)
                if entry:
                    pack_abilities.append({**entry, "code": code})
        except Exception:
            pack_abilities = []

    for ability in list(abilities or []) + pack_abilities:
        if not isinstance(ability, dict):
            continue
        if ability.get("locked"):
            continue
        activation = str(ability.get("activation") or "active").lower()
        code = str(ability.get("code") or "")
        # Passives always apply; item-granted powers apply because the item is
        # equipped; deliberate active powers only apply when actually used, and
        # that path goes through mechanics_context instead.
        if activation != "passive" and code not in granted_codes:
            continue
        profile = _coerce_profile(ability.get("roll_profile"))
        if not profile:
            continue
        for skill_code, mod in profile.items():
            totals[skill_code] = totals.get(skill_code, 0) + mod
        sources.append(
            {
                "kind": "power",
                "code": code,
                "name": ability.get("name"),
                "activation": activation,
                "profile": profile,
            }
        )

    # Stacked gear should not turn a d20 into a formality.
    for code in list(totals):
        totals[code] = max(-15, min(15, totals[code]))
    return {"modifiers": totals, "sources": sources}


def opposition_power(
    opposition: dict[str, Any] | None,
    *,
    attr_key: str = "strength",
    rng: random.Random | None = None,
    power_rng: bool = True,
    power_variance: int = 3,
) -> dict[str, Any]:
    """
    How hard is this? Derived from enemy/object stats + optional RNG sway
    so 'how powerful' something feels is not a fixed constant.
    """
    opp = opposition if isinstance(opposition, dict) else {}
    stats = opp.get("stats") if isinstance(opp.get("stats"), dict) else opp
    score = _attr_score(stats, attr_key)
    # Rank letter bump (F..SSS)
    rank = str(opp.get("rank") or "").strip().upper()
    rank_bonus = {
        "F": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "S": 7, "SS": 9, "SSS": 12,
    }.get(rank, 0)
    # Explicit power score / level / defense if present
    for key in ("power", "threat", "dc_bonus", "defense", "level"):
        try:
            if opp.get(key) is not None:
                score = max(score, int(opp.get(key)))
        except (TypeError, ValueError):
            pass
    base = 8 + attribute_modifier(score) + rank_bonus
    sway = 0
    if power_rng and power_variance > 0:
        roller = rng or random.Random()
        sway = roller.randint(-int(power_variance), int(power_variance))
    total = max(5, min(30, base + sway))
    return {
        "name": str(opp.get("name") or opp.get("label") or "opposition")[:80],
        "attribute": attr_key,
        "stat_score": score,
        "rank": rank or None,
        "base_power": base,
        "power_sway": sway,
        "power_total": total,
    }


DEGREE_FLAVOR = {
    "critical_success": [
        "You make it look effortless — clean, complete, and then some.",
        "Outstanding. The result exceeds what you were aiming for.",
    ],
    "success": [
        "You succeed cleanly.",
        "It works as intended.",
    ],
    "barely": [
        "You just barely scrape through.",
        "It almost fails — then holds at the last breath.",
    ],
    "partial": [
        "You get something, but not everything you wanted.",
        "A fragment of the truth, a half-open door, a costly glimpse.",
    ],
    "failure": [
        "You fail. The moment offers nothing useful.",
        "It does not work; you spend effort and get air.",
    ],
    "bad_nothing": [
        "You do so poorly it is almost as if you had done nothing at all.",
        "Wasted motion. The world does not even bother to answer.",
    ],
    "critical_failure": [
        "Disaster. The attempt turns against you.",
        "A brutal miss — something breaks, bleeds, or betrays you.",
    ],
    "unskilled_mishap": [
        "You are unskilled at wielding this; the tool punishes the hand that holds it wrong.",
        "Without training, the weapon/tool does as much harm to you as to the world.",
    ],
}


def _pick_flavor(key: str, rng: random.Random) -> str:
    options = DEGREE_FLAVOR.get(key) or DEGREE_FLAVOR["failure"]
    return options[rng.randrange(len(options))]


def resolve_check(
    *,
    skill_code: str = "general",
    difficulty: str | None = None,
    dc: int | None = None,
    player_stats: dict[str, Any] | None = None,
    player_skills: list[dict[str, Any]] | None = None,
    opposition: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
    context_note: str = "",
    weapon_or_tool: str = "",
    rng: random.Random | None = None,
    inventory: list[dict[str, Any]] | None = None,
    abilities: list[dict[str, Any]] | None = None,
    roll_modifiers: dict[str, Any] | None = None,
    routine: bool = False,
    home: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    ``home`` is ``home_ground(...)``: on the character's own ground or trade a
    physical, craft or mental check is routine, and an untrained one stands
    on that trade as a related skill (Saltmarrow #103).

    ``routine`` marks everyday work (polishing, sweeping, hauling): the mark is
    two easier and only a natural 1 can hurt (playtest #85a).

    Roll a check with:
      - attribute base + skill modifier + equipped gear/power modifiers
      - DC from skill base, global difficulty, and optional contested opposition power
      - degree bands (barely / bad nothing / unskilled mishap)
      - optional lasting injury suggestions for severe fails

    ``inventory`` and ``abilities`` are optional; when supplied, equipped items
    and passive/granted powers automatically shift the roll via their
    ``roll_profile``. Pass ``roll_modifiers`` to add situational shifts on top.
    """
    cfg = merge_check_settings(settings)
    if not cfg.get("dice_checks_enabled"):
        return {
            "enabled": False,
            "outcome": "narrative",
            "detail": "Dice checks are disabled; resolve narratively.",
            "context_note": context_note,
        }

    lib_rows = load_skill_library()
    library = {s["code"]: s for s in lib_rows}
    # Exact-code lookup only, before: the narrator writes this field as prose and
    # never sees the catalogue, so "pick the lock" missed `lockpicking` and minted
    # a phantom that rolled INTELLIGENCE instead of DEXTERITY.
    resolved = resolve_skill_code(skill_code, lib_rows)
    skill = library.get(resolved) if resolved else None
    if skill and not skill.get("enabled", True):
        # A pack switched this skill off: fall back to the generic check rather
        # than silently rolling a skill the campaign says does not exist.
        skill = library.get("general")
    if not skill:
        reg = register_or_adjust_skill({"name": skill_code, "source": "playthrough"})
        skill = reg["skill"]

    sides = int(cfg["dice_sides"])
    diff = (difficulty or cfg.get("check_difficulty") or "normal").lower()
    shift = DIFFICULTY_DC_SHIFT.get(diff, 0)
    roller = rng or random.Random()

    attr_key = str(skill.get("attribute") or "intelligence")
    attr_score = _attr_score(player_stats, attr_key)
    attr_mod = attribute_modifier(attr_score)
    # The player's own proficiencies, read through their tracking notes and
    # neighbouring trades (playtest #85a), not an exact-name match only.
    footing = best_proficiency(player_skills, str(skill.get("code") or skill.get("name") or ""), lib_rows)
    home_source = ""
    category = str(skill.get("category") or "")
    if (
        isinstance(home, dict)
        and home.get("source")
        and category in HOME_GROUND_CATEGORIES
        and (category == "physical" or home.get("act"))
    ):
        home_source = str(home["source"])
        routine = True
        if footing["match"] == "untrained":
            footing = {"rank": max(1, int(home.get("rank") or 1)), "source": f"{home_source} (home ground)", "match": "related"}
    skill_rank = int(footing["rank"])
    skill_match = str(footing["match"])
    untrained_penalty = 0
    if skill_match == "untrained" and str(skill.get("category") or "") in UNTRAINED_PENALTY_CATEGORIES:
        untrained_penalty = int(cfg.get("untrained_penalty") or 0)
    skill_mod = skill_rank - untrained_penalty
    skill_key = str(skill.get("code") or "")

    # Equipped gear and passive/granted powers shift the roll automatically.
    gear = gear_roll_modifiers(inventory, abilities)
    gear_mod = int((gear["modifiers"] or {}).get(skill_key, 0))
    gear_sources = [
        {**src, "applied": int((src.get("profile") or {}).get(skill_key, 0))}
        for src in gear["sources"]
        if (src.get("profile") or {}).get(skill_key)
    ]

    situational_mod = 0
    situational = _coerce_profile(roll_modifiers)
    if situational:
        situational_mod = int(situational.get(skill_key, 0))

    total_mod = attr_mod + skill_mod + gear_mod + situational_mod
    # A neighbouring trade is footing, even at half of rank 1.
    unskilled = skill_rank < int(cfg.get("unskilled_rank_threshold") or 1) and skill_match != "related"

    # Contested DC: base skill DC + difficulty + opposition power (stats + RNG)
    base_dc = int(skill.get("base_dc") or 12) + shift - (2 if routine else 0)
    opp_info: dict[str, Any] | None = None
    if dc is not None:
        target_dc = int(dc)
        dc_source = "explicit"
    elif cfg.get("contested_checks") and opposition:
        opp_info = opposition_power(
            opposition,
            attr_key=str(opposition.get("contest_attribute") or attr_key),
            rng=roller,
            power_rng=bool(cfg.get("power_rng")),
            power_variance=int(cfg.get("power_variance") or 3),
        )
        # The other side moves the mark around the skill's own base: an average
        # person (power 8: score 10, rank F, no sway) leaves it where a static
        # check would put it, a strong one raises it, a weak one lowers it a
        # little. The old blend, max(base, (base + power) / 1.15), could only
        # raise it, so a guarded nobody was DC 15-20 for a plain question and an
        # untrained speaker needed a natural 15 or better (playtest #88).
        target_dc = max(base_dc - 4, base_dc + int(opp_info["power_total"]) - 8)
        dc_source = "contested"
    else:
        target_dc = base_dc
        dc_source = "static"
        if cfg.get("power_rng"):
            sway = roller.randint(-2, 2)
            target_dc = max(5, target_dc + sway)

    natural = roller.randint(1, sides)
    total = natural + total_mod
    margin = total - target_dc

    crit = bool(cfg.get("crit_on_natural_max")) and natural == sides
    fumble = bool(cfg.get("fumble_on_natural_1")) and natural == 1

    specialized_partial = False
    if (
        cfg.get("partial_on_specialized_skill")
        and skill_rank >= int(cfg.get("specialized_skill_partial_threshold") or 2)
        and attr_score < int(cfg.get("attribute_floor_for_partial") or 6)
        and total < target_dc
        and not fumble
    ):
        specialized_partial = True

    degree = "failure"
    if fumble:
        degree = "critical_failure"
        outcome = "critical_failure"
    elif crit and total >= target_dc:
        degree = "critical_success"
        outcome = "critical_success"
    elif specialized_partial:
        degree = "partial"
        outcome = "partial"
    elif margin >= max(5, sides // 4):
        degree = "critical_success" if crit else "success"
        outcome = "success" if not crit else "critical_success"
    elif margin >= 0:
        degree = "barely" if margin <= 2 else "success"
        outcome = "success"
    elif margin >= -3:
        degree = "partial" if cfg.get("partial_on_specialized_skill") else "failure"
        outcome = "partial" if degree == "partial" else "failure"
    elif margin >= -6:
        degree = "failure"
        outcome = "failure"
    else:
        degree = "bad_nothing"
        outcome = "failure"

    # Routine talk fails at worst: a natural 1 on a plain question is an
    # awkward answer, not a brutal miss (8B run 150, T84: "ask the worker
    # about the missing chest" wrote "something breaks, bleeds, or betrays you").
    if fumble and routine and str(skill.get("category") or "") == "social":
        degree, outcome, fumble = "bad_nothing", "failure", False
    mishap = False
    injury: dict[str, Any] | None = None
    blunder: dict[str, Any] | None = None
    tool = (weapon_or_tool or "").strip() or str((opposition or {}).get("weapon") or "")
    social = str(skill.get("category") or "") == "social"
    # An unskilled miss goes wrong on a natural 1, or on a miss by a lot
    # (degree bad_nothing, margin -7 or worse). A miss by 4 used to count too
    # and was promoted to a critical failure, so an untrained +0 speaker
    # against DC 18 "fumbled" on any roll of 14 or less: 28 of 49 asks in
    # playtest #88. Only the natural 1 is critical now; the rest stays a
    # failure that went badly.
    # A plain question is routine talk: a natural 1 on "ask the worker about
    # the missing chest" wrote "A brutal miss: something breaks, bleeds, or
    # betrays you" (8B run 150, T84). Routine talk fails at worst.
    if (
        cfg.get("unskilled_mishaps")
        and unskilled
        and outcome in {"failure", "critical_failure"}
        and (fumble or (not routine and degree == "bad_nothing"))
        and not (routine and social)
    ):
        mishap = True
        degree = "critical_failure" if fumble else "unskilled_mishap"
        if fumble:
            outcome = "critical_failure"
        # Lasting harm is the natural 1's; a bad miss costs a scratch and no
        # lasting condition. apply_turn stores only lasting injuries.
        lasting = bool(fumble and cfg.get("severe_mishap_on_crit_fail"))
        if social and not opposition:
            # No one on the other side to offend: "Botched Appraise: you
            # misjudge the moment and give offense" on a lone walk across the
            # mud (8B run 8, T1). It stays a bad miss, with no blunder.
            mishap = False
            degree = "bad_nothing" if not fumble else degree
        elif str(skill.get("category") or "") in {"mental", "craft"} and not tool:
            # Looking, searching and recalling break no bones: "Botched
            # Perception: you hurt your leg" for sweeping the dust around a well
            # for footprints (8B run 146, T57). A bad miss finds nothing; only a
            # tool in hand (a lockpick, a lens) can hurt its user. The same for a
            # craft with no tool named: "Botched Cartography: you hurt your side"
            # for laying a marked map on a desk (8B run 147, T81).
            mishap = False
            degree = "bad_nothing" if not fumble else degree
        elif social:
            # Words do not break bones (playtest #88: "Botched Persuasion:
            # you hurt your leg" 28 times). A social fumble is a blunder the
            # other side remembers: the attitude already went cold for it.
            blunder = {
                "kind": "social_blunder",
                "severity": bool(fumble),
                "summary": f"Botched {skill.get('name')}: {roller.choice(_BLUNDER_LINES)}",
            }
        else:
            limb = roller.choice(["leg", "arm", "hand", "side", "eye", "ribs"])
            injury = {
                "kind": "self_injury",
                "limb": limb,
                "severity": bool(fumble),
                "lasting": lasting,
                "health_delta": -roller.randint(2, 6) if fumble else -1,
                "summary": (
                    f"Unskilled with {tool or skill.get('name')}: you injure your own {limb}."
                    if tool or skill.get("category") == "combat"
                    else f"Botched {skill.get('name')}: you hurt your {limb}."
                ),
                "combat_penalty": {
                    "mobility": -2 if limb in {"leg"} else 0,
                    "attack": -2 if limb in {"arm", "hand"} else -1,
                    "defense": -1,
                }
                if lasting
                else {},
            }

    negative = bool(cfg.get("negative_outcomes")) and outcome in {"failure", "critical_failure"}
    flavor = _pick_flavor(degree if cfg.get("degree_flavor") else outcome, roller)
    if mishap and injury:
        flavor = (
            f"{flavor} You are unskilled at wielding {tool or 'this'} — "
            f"you end up taking your own {injury['limb']} into the mess. "
            f"{injury['summary']}"
        )
    elif mishap and blunder:
        flavor = f"{flavor} {blunder['summary']}"

    # The roll says which proficiency it used (playtest #85a).
    if skill_match == "untrained":
        skill_part = f"skill {skill_rank:+d} (untrained)"
    else:
        skill_part = f"skill {skill_rank:+d} ({footing['source']}{', related' if skill_match == 'related' else ''})"
    mod_parts = [f"attr {attr_mod:+d}", skill_part]
    if untrained_penalty:
        mod_parts.append(f"untrained -{untrained_penalty}")
    if gear_mod:
        mod_parts.append(f"gear {gear_mod:+d}")
    if situational_mod:
        mod_parts.append(f"situation {situational_mod:+d}")
    display_lines = [
        f"You rolled {natural} with your base of {attr_score} ({attr_key}) "
        f"and a modifier of {total_mod:+d} ({' + '.join(mod_parts)}).",
        f"Total: {total}  ·  Base success (DC): {target_dc}"
        + (f"  ·  vs {opp_info['name']} power {opp_info['power_total']}" if opp_info else ""),
        f"Result: {outcome.replace('_', ' ')} ({degree.replace('_', ' ')})  ·  margin {margin:+d}",
        flavor,
    ]

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
        "base": attr_score,
        "modifier": total_mod,
        "attribute_score": attr_score,
        "attribute_mod": attr_mod,
        "skill_rank": skill_rank,
        "skill_mod": skill_mod,
        "skill_source": footing["source"],
        "skill_match": skill_match,
        "untrained_penalty": untrained_penalty,
        "routine": bool(routine),
        "home_ground": home_source,
        "gear_mod": gear_mod,
        "gear_sources": gear_sources,
        "situational_mod": situational_mod,
        "total": total,
        "dc": target_dc,
        "base_success": target_dc,
        "dc_source": dc_source,
        "difficulty": diff,
        "opposition": opp_info,
        "outcome": outcome,
        "degree": degree,
        "margin": margin,
        "specialized_partial": specialized_partial,
        "unskilled": unskilled,
        "mishap": mishap,
        "injury": injury,
        "blunder": blunder,
        "negative_outcome_suggested": negative,
        "crit": crit,
        "fumble": fumble,
        "flavor": flavor,
        "lines": display_lines,
        "guidance": flavor,
        "context_note": str(context_note or "")[:400],
        "weapon_or_tool": tool[:80],
        "display": " | ".join(display_lines[:3]),
        "display_block": "\n".join(display_lines),
    }


def _npc_pool_from_context(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    pool: list[dict[str, Any]] = []
    for n in ctx.get("npcs") or []:
        if isinstance(n, dict):
            pool.append(n)
    loc = ctx.get("current_location") or {}
    if isinstance(loc, dict):
        for n in loc.get("npcs") or []:
            if isinstance(n, dict):
                pool.append(n)
    for location in ctx.get("locations") or []:
        if not isinstance(location, dict):
            continue
        if loc.get("id") is not None and location.get("id") != loc.get("id"):
            continue
        for n in location.get("npcs") or []:
            if isinstance(n, dict):
                pool.append(n)
    # de-dupe by code/name
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for n in pool:
        key = str(n.get("code") or n.get("name") or id(n))
        if key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def social_attitude_from_check(
    outcome: str,
    npc: dict[str, Any] | None = None,
) -> str:
    """
    Map social check result + NPC temperament to a reaction label.
    Labels: Warm, Cordial, Neutral, Dismissive, Apprehensive, Condescending,
    Antagonistic, Hostile — not spoken as system titles, for DM direction only.
    """
    npc = npc if isinstance(npc, dict) else {}
    base = str(npc.get("attitude") or "neutral").lower()
    personality = " ".join(
        str(npc.get(k) or "") for k in ("personality", "principles", "dislikes", "likes", "role")
    ).lower()
    rank = outcome if outcome in OUTCOME_RANK else "failure"

    proud = any(w in personality for w in ("proud", "noble", "arrogant", "court", "reeve", "elder", "chief"))
    fearful = any(w in personality for w in ("fear", "timid", "anxious", "nervous", "wary"))
    kind = any(w in personality for w in ("kind", "warm", "gentle", "helpful"))
    hostile_base = base in {"hostile", "antagonistic", "angry"} or str(npc.get("attitude") or "") == "hostile"

    if rank in {"critical_success", "success"}:
        if hostile_base:
            return "Apprehensive"
        if proud:
            return "Cordial"
        if kind:
            return "Warm"
        return "Cordial" if rank == "critical_success" else "Neutral"
    if rank == "partial":
        if proud:
            return "Condescending"
        if fearful:
            return "Apprehensive"
        if hostile_base:
            return "Dismissive"
        return "Dismissive"
    # failure / critical_failure
    if rank == "critical_failure":
        if proud:
            return "Antagonistic"
        if fearful:
            return "Hostile" if hostile_base else "Apprehensive"
        return "Hostile" if hostile_base else "Antagonistic"
    # plain failure
    if proud:
        return "Condescending"
    if fearful:
        return "Apprehensive"
    if hostile_base:
        return "Hostile"
    return "Dismissive"


# "the rusted key in the box's lock", "my key into the lock", "unlock it with the key".
_KEY_IN_LOCK_RE = re.compile(
    r"\b(?:the|my|a|an|this|that|its|his|her)\s+(?:[\w'’-]+\s+){0,2}?keys?\s+(?:in|into|to)\s+"
    r"(?:the\s+|a\s+|its\s+|[\w'’-]+['’]s\s+)?(?:[\w'’-]+\s+){0,2}?locks?\b"
    r"|\bunlock\w*\s+(?:it|them|the\s+[\w'’-]+)\s+with\s+(?:the|my|a|this|that|its)\s+(?:[\w'’-]+\s+){0,2}?keys?\b",
    re.I,
)

SKILL_TRIGGER_PATTERNS: list[tuple[str, str]] = [
    # Striking a flint, a match or a bargain is not a blow (playtest #102).
    (r"\b(attack|strike(?!\s+(?:the\s+|a\s+|an\s+|my\s+|his\s+|her\s+)?(?:flint|match|light|steel|tinder|spark|bell|deal|bargain|camp|tent|sail|chord|note|pose|balance|entry|entries|name|names|line|lines|record|records|word|words|debt|sum|figure|charge|clause|it\s+(?:from|out|off|through)|that\s+(?:entry|name|line|out)|them\s+(?:from|out|off)|(?:[\w'’-]+\s+){0,4}?(?:from|out\s+of|off)\s+(?:the\s+|a\s+|my\s+|his\s+|her\s+|[\w'’-]+['’]s\s+)?(?:[\w'’-]+\s+){0,2}?(?:ledger|books?|records?|tally|roll|list|register|page|slate))\b)|slash|stab|swing|fight|melee)\b", "melee"),
    # The verbs only: "I eat the soup by the fire" rolled ranged (7B run 5, T30),
    # and "bow to her" is a greeting.
    (r"\b(shoot|(?<!the )(?<!by )(?<!a )(?<!of )fire (?:at|on|upon|into|a|an|the|my|arrows?|bolts?|shots?|again)|"
     r"(?<!the )(?<!ship's )(?<!boat's )(?<!her )bow(?!\s+(?:to|before|my|your|his|her|their|deeply|low|out|politely|slightly|in|"
     r"line|lines|rope|ropes|cleat|rail|oar|deck|post|of))|"
     # A boat's bow after the verb is the boat: "take the bow seat" in a skiff
     # rolled ranged and fumbled, "Unskilled with bow" (8B run 147, T7).
     r"(?:draws?|nocks?|aims?|raises?|strings?|readies|ready|lifts?|grabs?|takes?|fires?|loose[sd]?|bends?|unslings?)\s+"
     r"(?:the|my|a|his|her|their)\s+bow\b(?!\s+(?:seat|line|lines|rope|ropes|cleat|rail|oar|deck|post|thwart|section|end|wave|"
     r"of\s+the|of\s+(?:his|her|their|our)))|"
     r"(?:the|her)\s+bow\s+(?:and\s+(?:aim|draw|loose|fire)|at|string|drawn|ready)\b|gun|throw)\b", "ranged"),
    # The player creeping, not the water: "With the water starting to creep back"
    # rolled stealth and a critical failure (8B run 37, T6).
    (r"\b(sneak|hide|stealth)\b|\bi\s+(?:\w+\s+)?creep\b|\bcreep(?:s|ing)?\s+(?:up|along|toward|towards|past|around|closer|"
     r"forward|into|behind|through)\b(?<!water creep)", "stealth"),
    (r"\b(persuade|convince|negotiate)\b", "persuasion"),
    # A price named to someone is a bargain: '"Six gold, there and back, and I
    # pull my own weight on the oars. Do we have a deal?"' rolled nothing (8B
    # run 145, T19). The sum plus a dealing word, in speech or out of it.
    (r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|fifty|a\s+hundred)\s+"
     r"(?:gold|silver|coppers?|coins?|crowns?)\b[\s\S]{0,120}?\b(?:deal|offer|take\s+it|or\s+nothing|and\s+no\s+more|"
     r"there\s+and\s+back|final|last\s+offer|and\s+not\s+a\s+\w+\s+more|or\s+(?:i|we)\s+walk|for\s+(?:both|the\s+lot|all\s+of\s+it)|"
     r"take\s+it\s+or\s+leave\s+it)\b", "persuasion"),
    # "worth" alone is feeling ("no cart's worth you", playtest #102); a
    # price question still asks what something is worth.
    # The noun is not the act: "hold him to the Drowned Hand's side of the
    # bargain" rolled appraise and fumbled it (8B run 146, T24); "I haggle over
    # the pelt" still does.
    (r"\b((?<!\bthe\s)(?<!\ba\s)(?<!\bour\s)(?<!\bhis\s)(?<!\bher\s)(?<!\btheir\s)(?<!\bthis\s)(?<!\bthat\s)bargain|haggle|price|appraise|value of|what'?s? (?:is )?\w+(?: \w+)? worth|worth (?:anything|much|it\?))(?:\b|(?<=\?))", "appraise"),
    # Opening speech / ask / talk → charisma-backed persuasion
    (r"\b(talk|speak|ask|greet|address|approach .+ (and )?(talk|ask|speak)|say (hello|hi)|introduce)\b", "persuasion"),
    # Reclining "lie down/back/low/still/awake/asleep" is rest, not a bluff.
    # The lookahead also sees stemmed variants ("lies down" -> "lie down").
    # The player's lie, not where a thing lies: "until I can see where the
    # Stormcaller lies" rolled deception against the tallyman (8B run 36, T5).
    (r"(?:(?<=\bi\s)|(?<=\ba\s)|(?<=\btell\s)|(?<=\btold\s))lie\b(?!\s+(?:down|back|low|still|awake|asleep|flat|prone|face|on|in|there|here|quiet|beside|next|under|across|along|against|curled|huddled)\b)"
     r"|\b(?:lie|lies|lied|lying)\s+(?:to|about|that|through|my\s+way)\b|\b(bluff|deceive|con)\b", "deception"),
    (r"\b(intimidate|threaten|scare)\b", "intimidation"),
    (r"\b(disguise|costume|impersonat[a-z]*|pretend to be)\b", "disguise"),
    (r"\b(gambl[a-z]*|bet|wager|cards|dice game)\b", "gambling"),
    (r"\b(symbols?|runes?|glyphs?|sigils?|etch\w*)\b", "symbol_lore"),
    # Before bare "read": "read him/her/them/the room" is insight; "read the letter" is not.
    (r"\b(insight|read (him|her|them|the room)|sense motive)\b", "insight"),
    (r"\b(read|inspect|examine|study|analyze)\b", "investigation"),
    (r"\b(search|look for|scan|look around)\b", "perception"),
    # Getting into a boat, a cart or a bed is not a feat (playtest #102).
    # Stairs are walked: "I climb the seawall steps" (8B run 37, T6).
    (r"\b(climb(?!\s+(?:in|into|onto|aboard|out of|down from|back into)\s+(?:the\s+|a\s+|my\s+|his\s+|her\s+)?(?:\w+\s+)?(?:skiff|boat|cart|wagon|bed|saddle|bunk|hammock|carriage|barge|punt|coracle))"
     r"(?!\s+(?:up\s+|down\s+)?(?:the\s+|a\s+|some\s+)?(?:[\w'’-]+\s+){0,2}?(?:step\w*|stair\w*)\b)|jump|swim|lift|force|break|bash|"
     # A dive done, not a dive named: "dive on the wreck", "dive down for it"
     # roll; "The dive. I'll take it." does not (8B run 145, T3 and T9: the
     # dive on the wreck rolled nothing).
     r"(?:dive|dives|dived|dove|diving)\s+(?:on|onto|into|in|down|for|off|to|under|beneath|after|through)|go(?:es)?\s+over\s+the\s+side)\b", "athletics"),
    # Picking a thing up is a take, not a lock: "I pick the crustacean back up"
    # rolled lockpicking (8B run 150, T36).
    (r"\b(lock|pick the(?!\s+(?:[\w'’-]+\s+){0,4}?(?:back\s+)?up\b)|unlock)\b", "lockpicking"),
    (r"\b(heal|bandage|medicine|first aid|triage|splint)\b", "healing"),
    (r"\b(rally|cover (me|them|him|her)|support (ally|friend)|buff)\b", "support"),
    (r"\b(summon|call (a |the )?(spirit|familiar|demon)|pact)\b", "summoning"),
    (r"\b(necro[a-z]*|undead|bone (rite|command)|raise (dead|skeleton)|grave rite)\b", "necromancy"),
    (r"\b(exorc[a-z]*|banish|cleanse spirit|salt circle)\b", "exorcism"),
    (r"\b(alchem[a-z]*|brew potion|reagent|tincture)\b", "alchemy"),
    (r"\b(ritual|draw (a )?circle|ceremony)\b", "ritual"),
    (r"\b(weapon art|kata|form with (my |the )?(sword|spear|bow|axe))\b", "weapon_art"),
    (r"\b(medicine|first aid kit)\b", "medicine"),
    (r"\b(hack|console|terminal|decrypt)\b", "hacking"),
    (r"\b(track|forage|camp|survive)\b", "survival"),
    # Setting or baiting a trap is trapping, survival work: "set it at the
    # mouth of the fresh tunnel, packing earth around the jaws" rolled mining
    # on the word "tunnel" (7B run 30, T6, T10).
    (r"(?=.*\btraps?\b)(?=.*\b(?:set|sets|setting|lay|lays|laying|place|places|placing|bait|baits|baiting)\b)", "survival"),
    # Cooking, not eating: "I eat a few spoonfuls of the stew" rolled cooking,
    # failed it and hurt the player's arm (7B run 18, T6).
    (r"\b(cook (?:a|an|the|some|up|it|them|my|our|dinner|supper|breakfast)|cooking|"
     r"roast (?:a|the|some|it)|stew (?:the|some|it)|prepare (?:a |the |some )?(?:meal|food|stew|supper|breakfast)|"
     r"make (?:a |the |some )?(?:meal|stew|supper|breakfast))\b", "cooking"),
    # The work, not the building: "I glance at the forge behind him" rolled
    # smithing at DC 16 (7B run 12, T1).
    (r"\b(smithing|forge (?:a|an|the|my|it|them|some|new|nails?|blades?|horseshoes?)|"
     r"hammer (?:out|it|the|a)\b|temper (?:the|a|it|my)|work (?:the|at the) (?:forge|anvil|bellows)|at the anvil)\b",
     "smithing"),
    # Handling, not the animal: '"Is that horse going anywhere near the guild
    # today?"' rolled animal handling, a critical failure and a hurt leg (7B
    # run 39, T1). A beast named needs a handling verb on it.
    # Verbs that are also nouns need the beast named: "look into the water
    # without touching it" read "water ... it" as watering an animal (8B run 15, T4).
    (r"\b(?:tame|taming|calm (?:the|a|an|it|him|her|my)|soothe (?:the|a|an|it|him|her)|"
     r"(?:(?:ride|riding|rode|saddle|saddling|bridle|harness|harnessing|groom|grooming|whistle\s+for)"
     r"\s+(?:\w+\s+){0,2}?(?:animal|animals|horse|horses|mare|mule|mules|pony|ponies|donkey|ox|oxen|goat|goats|sheep|"
     r"cow|cows|cattle|hound|hounds|dog|dogs|flock|herd|beast|beasts|mount|mounts|her|him|it|them))|"
     r"(?:mount|mounting|lead|leading|led|feed|feeding|water|watering|shoe|shoeing|herd|herding|drive|driving|handle|"
     r"handling|break|breaking)"
     r"\s+(?:\w+\s+){0,2}?(?:animal|animals|horse|horses|mare|mule|mules|pony|ponies|donkey|ox|oxen|goat|goats|sheep|"
     r"cow|cows|cattle|hound|hounds|dog|dogs|flock|beast|beasts|mounts))\b", "animal_handling"),
    # The craft nouns alone are not the craft (#102 class, 8B run 142 T5: "I
    # carry the rusted compass ... back up to the tally house" rolled
    # navigation and hurt the player). A farm walked across, a map pocketed, a
    # compass carried, a mechanism looked at name a thing; the check wants the
    # thing used: the skill's own verb, or a using verb on the thing.
    (r"\b(?:farm(?:s|ing|ed)\s+(?:the|a|this|our|my|his|her)\b|(?:plow|plough|till|sow|reap|harvest|weed|hoe)(?:s|ing|ed)?\b|"
     r"(?:tend|tending|tends|work|working|works|turn|turning|turns)\s+(?:the|a|this|our|my)\s+(?:\w+\s+)?(?:fields?|crops?|soil|furrows?|rows?|beds?))\b", "farming"),
    # "mine" is usually the possessive ("round Tam's waist, then round mine",
    # playtest #102): only the verb with an object, or the word alone, is mining.
    # A tunnel named is not one dug: "feel which way the tunnel runs" rolled
    # mining (7B run 30, T3). Digging, shoring or cutting one still is.
    (r"(^mine$|\bmine (?:for|the|a|an|out|ore|coal|iron|copper|silver|gold|salt)\b|\b(mining|ore|dig (for|out|a))\b|"
     r"\btunnel(?:s|ing|led|ling)?\s+(?:through|into|under|out)\b|"
     r"\b(?:dig|digs|digging|shore|shores|shoring|brace|braces|bracing|cut|cuts|cutting|widen|widens|widening)\s+"
     r"(?:up\s+)?(?:the|a|an|this|that|our|my)\s+(?:\w+\s+)?tunnels?\b)", "mining"),
    (r"\b(?:cartograph[a-z]*|survey(?:s|ing|ed)?\s+(?:the|a|this|that|our)\b|"
     r"(?:draw|draws|drawing|drew|sketch(?:es|ing|ed)?|make|makes|making|made|update|updates|updating|copy|copies|copying|"
     r"correct|corrects|correcting|mark|marks|marking|redraw|redraws|redrawing)\s+(?:\w+\s+){0,2}?(?:maps?|charts?)\b|"
     r"(?:map|maps|mapping|mapped|chart|charts|charting|charted)\s+(?:out\s+)?(?:the|a|this|these|our|every|each)\b)", "cartography"),
    (r"\b(?:navigat[a-z]*|dead[ -]reckon[a-z]*|tak(?:e|es|ing)\s+(?:a|the|our|my)\s+bearings?|"
     r"(?:read|reads|reading|use|uses|using|check|checks|checking|consult|consults|consulting|follow|follows|following|"
     r"steer|steers|steering|by)\s+(?:\w+\s+){0,2}?(?:compass|stars)\b|"
     r"(?:plot|plots|plotting|chart|charts|charting|find|finds|finding|work(?:s|ing)?\s+out|fix|fixes|fixing)\s+(?:\w+\s+){0,2}?"
     r"(?:course|route|heading|position|bearings?)\b)", "navigation"),
    (r"\b(?:tinker[a-z]*|jury[- ]?rig[a-z]*|"
     r"(?:fix|fixes|fixing|mend|mends|mending|repair|repairs|repairing|rig|rigs|rigging|open|opens|opening|take|takes|taking|"
     r"pull|pulls|pulling|build|builds|building|wind|winds|winding|adjust|adjusts|adjusting)\s+(?:\w+\s+){0,2}?"
     r"(?:gadget|gadgets|mechanism|mechanisms|device|devices|clockwork|gears?|springs?|cogs?|contraption)\b)", "tinkering"),
    (r"\b(drive|pilot|steer|sail)\b", "vehicles"),
    (r"\b(history|lineage|old war|who ruled)\b", "history"),
    (r"\b(nature|plant|beast ecology|weather pattern)\b", "nature"),
    (r"\b(religion|rite|omen|prayer|cult)\b", "religion"),
    (r"\b(arcana|magic theory|ward|spell residue)\b", "arcana"),
    (r"\b(performance|sing|song|act|storytell[a-z]*)\b", "performance"),
    (r"\b(etiquette|court manners|protocol|formal address)\b", "etiquette"),
    # The trade, not the field fence: "I walk over to the field fence where
    # Elsabet is milking" rolled streetwise, a mishap and a blunder (7B run 42, T1).
    (r"\b(streetwise|underworld|gang\s+rumou?r|(?:a|any|local|the\s+local|a\s+good)\s+fence\b(?!\s+(?:post|rail|line|gate|board))|"
     r"fence\s+(?:it|them|these|those|stolen|the\s+goods|goods|loot|the\s+loot))\b", "streetwise"),
    (r"\b(acrobatics|balance|tumble|tightrope)\b", "acrobatics"),
    # "palm" the verb, not the hand: "I count the coins in my palm" rolled
    # sleight of hand (7B run 10, T8).
    (r"\b(sleight|pickpocket|palm (?:it|them|the|a|an|one|his|her|their)|switch the)\b", "sleight_of_hand"),
    (r"\b(tactics|ambush plan|formation)\b", "tactics"),
    (r"\b(defense|parry|block|guard up)\b", "defense"),
]
"""Regex -> built-in skill code, for turning action text into a check.

Hoisted out of `infer_check_from_action` so the same table can resolve a skill
string the model supplied directly. It used to be a local list, so the check
path had no way to reuse it and minted a phantom skill instead.

Every entry is anchored `\\b(...)\\b`. The trailing boundary is deliberate and
must stay: without it "ready" matches read, "between" matches bet, "lieutenant"
matches lie, "control" matches con and "maple" matches map. Inflected player
text ("I'm sneaking past him") is handled by `_trigger_text_variants` below
instead -- de-inflect the sentence, not the pattern.

The `[a-z]*` stems (impersonat, gambl, necro, exorc, alchem, navigat,
cartograph, storytell) were written as prefixes and the trailing `\\b` made
them unmatchable: there is no word boundary between the "t" of "impersonat"
and the "i" of "impersonating", so the entry only ever matched the literal
non-word "impersonat". They are now spelled as the prefixes they always were.
"""

# Emitted stems stop at three characters. Shorter than that is all noise, and
# the "-er" rule that made three risky ("better" -> "bett" -> "bet") is
# deliberately absent: -er/-ist/-or/-y forms are covered by the `[a-z]*` prefix
# stems instead, which cannot reach across an unrelated word the way stripping
# can. What survives at three -- bet, con, map, lie, act, ask, dig -- is only
# reachable from a genuinely inflected form ("betting", "mapped", "asking"),
# never from an unrelated word that merely contains those letters.
_TRIGGER_STEM_MIN = 3
# Doubling is not undone for these -- "stress" is not "stres", "call" is not
# "cal" -- and undoing it there buys nothing anyway.
_DOUBLE_KEEP = frozenset("slfz")
_TRIGGER_WORD_RE = re.compile(r"[a-z]+")


def _word_stems(word: str) -> list[str]:
    """De-inflected forms of one lowercase word, longest-lived first.

    Returns [] when nothing applies, which is the common case and the reason
    this is cheap. Never strips a trailing "y": that is what keeps "ready" from
    becoming "read".
    """
    if word.endswith("ing"):
        base = word[:-3]
    elif word.endswith(("ed", "es")):
        base = word[:-2]
    elif word.endswith("s") and not word.endswith("ss"):
        base = word[:-1]
    else:
        return []
    candidates = [
        base,
        # "persuad" -> "persuade", "hid" -> "hide": the dropped-e forms. This is
        # why the floor is applied per candidate and not to `base` -- "hid" is
        # too short to emit, but the "hide" built from it is the one we want.
        base + "e",
    ]
    # "stabb" -> "stab", "swimm" -> "swim", "scann" -> "scan".
    if len(base) > 1 and base[-1] == base[-2] and base[-1] not in _DOUBLE_KEEP:
        candidates.append(base[:-1])
    seen: list[str] = []
    for candidate in candidates:
        if len(candidate) >= _TRIGGER_STEM_MIN and candidate not in seen:
            seen.append(candidate)
    return seen


def _trigger_text_variants(text: str, *, protect_others: bool = True) -> list[str]:
    """The sentence, plus de-inflected rewrites of it.

    Each variant is a whole coherent sentence rather than the original with
    stems appended, because several triggers are phrases -- "look for",
    "pick the", "cover me". Appending "look" after "looking" would leave
    "looking look for" and the phrase would still not be adjacent; rewriting
    the word in place gives "look for the key" and it matches.

    The original is always first, so nothing that matches today can stop
    matching: the variants only add reach.
    """
    variants = [text]
    stems = {word: _word_stems(word) for word in set(_TRIGGER_WORD_RE.findall(text))}
    if not any(stems.values()):
        return variants
    # A verb someone or something else does stays as typed: "before the tide
    # covers them" de-inflected to "cover them" and rolled support (8B run 146,
    # T49). The "-s" after "the <noun>" or "he/she/it/they" is a third-person
    # verb (or a plural noun), never the player's own act.
    others = {m.start(1) for m in _OTHERS_VERB_RE.finditer(text)} if protect_others else set()
    for depth in range(3):

        def _pick(match: re.Match[str], _d: int = depth) -> str:
            if match.start() in others:
                return match.group(0)
            options = stems.get(match.group(0)) or []
            return options[_d] if _d < len(options) else match.group(0)

        rewritten = _TRIGGER_WORD_RE.sub(_pick, text)
        if rewritten != text and rewritten not in variants:
            variants.append(rewritten)
    return variants


# A word ending in -s right after "the/a/this/his... <word>" or a third-person
# pronoun: another's verb or a plural noun, not the player's act (see
# _trigger_text_variants).
_OTHERS_VERB_RE = re.compile(
    r"\b(?:(?:the|a|an|this|that|these|those|his|her|their|its|our|my|your|some|every|each|no)\s+[a-z]+|he|she|it|they|who|which|that)\s+"
    r"(?:all\s+|always\s+|just\s+|only\s+|still\s+|often\s+|never\s+|soon\s+)?([a-z]{3,}s)\b",
    re.I,
)
# Skills whose trigger is a blow: rolled whoever strikes, so they read the
# de-inflected line without the others-verb protection.
_COMBAT_TRIGGER_SKILLS = frozenset({"melee", "ranged", "defense", "tactics", "weapon_art"})
# A quoted span in the player's line ("..." or “...”).
_SPOKEN_RE = re.compile(r"\"[^\"]*\"|“[^”]*”")
# Skills a line of speech can call for by itself.
_SPEECH_SKILLS = frozenset({"persuasion", "deception", "intimidation", "insight", "etiquette", "performance", "streetwise"})
# Skills whose triggers are nouns, matched with their plurals as typed.
# Lore skills trigger on their nouns as typed, never on a de-inflected verb:
# "feet planted in the mud" became "plant" and rolled nature (8B run 145, T34).
_NOUN_TRIGGER_SKILLS = frozenset({"symbol_lore", "nature", "history", "religion", "arcana"})
# A social verb whose subject is someone else: "they all lie", "the merchants
# cheat", "he threatened me". Only the player's own lie or threat is a check.
_OTHERS_DO_SOCIAL_RE = re.compile(
    r"\b(?:they|he|she|you|it|people|folk|folks|everyone|everybody|nobody|all|both|most|some|others|"
    r"(?!this\b|was\b|is\b|has\b|does\b|as\b)[a-z]{3,}s)\s+(?:all\s+|always\s+|just\s+|only\s+|often\s+|will\s+|would\s+|"
    r"do\s+|did\s+|can\s+|could\s+)?(?:lie|lies|lied|lying|bluff\w*|deceiv\w*|cheat\w*|threaten\w*|cons?)\b"
)

_NEGATED_VERB_RE = re.compile(
    r"\b(?:not|never|no longer|cannot|\w+n['’]t)\s+(?:\w+ly\s+)?(?:going to\s+|try(?:ing)? to\s+)?\w+"
)
_JOB_PAY_RE = re.compile(
    r"\b(?:job|work|contract|reward|bounty|task|notice|posted|pays?|paid|bring\s+(?:it|them)\s+in|deliver\w*|"
    r"when\s+I\s+(?:bring|find|finish|return))\b",
    re.I,
)
_WATCHED_CLAUSE_RE = re.compile(
    r"\b(?:watch|see|notice|count)(?:es|s|ing)?\s+(?:how|whether|if|as)\b[^.,;!?\"“”]*"
    # What a thing might be good for is the reason, not the act: "anything
    # half-buried in the mud that might fetch a price" rolled appraise on a
    # walk out on the flats (8B run 8, T1).
    r"|\b(?:that|which)\s+(?:might|could|would|may|will|should)\b[^.,;!?\"“”]*"
)
# "the mole catcher is digging", "where Tam was hammering": another's act.
_OTHERS_DOING_RE = re.compile(
    r"\b(?:the|a|an|his|her|their|[A-Z][a-z]+)\s+(?:[\w'’-]+\s+){0,3}?(?:is|are|was|were)\s+(?:still\s+|busy\s+)?\w+ing\b"
    # What the player looks at doing something: "I look at the water creeping
    # over the lower district" rolled stealth (7B run 20, T1).
    r"|\b(?:look|looks|looking|watch|watches|watching|see|sees|eye|eyes|study|studies)\s+(?:at\s+)?"
    r"(?:the|a|an|his|her|their)\s+(?:[\w'’-]+\s+){0,3}?\w+ing\b",
)

# Verb forms only: "stab" must not catch "the stable" a player is mucking out.
# The subject of the blow is a thing, not the player: "the blade strikes
# something solid", "the oar hits a plank", "a wave strikes the hull".
_THING_STRIKES_RE = re.compile(
    r"\b(?:the|its|my|his|her|their|an?|that|this)\s+(?:[\w'’-]+\s+)?(?:blade|oar|tip|edge|hull|wave|waves|wind|rain|"
    r"spade|pole|staff|hook|line|rope|wheel|keel|bow|stern|hammer|pick|probe|point|boot|heel)\s+"
    r"(?:strikes|struck|striking|hits|hit|hitting|knocks|knocked|catches|caught)\s+(?:on\s+|against\s+)?"
    r"(?:something|a|an|the|some|solid|hard|stone|rock|wood|metal|iron|bone)\b[^.!?,;]*",
    re.IGNORECASE,
)
_COMBAT_LINE_RE = re.compile(
    r"\b(?:(?:attack|fight|slash|stab|punch|kick|shoot)(?:s|es|ed|ing|bed|bing)?"
    r"|(?:strikes?|striking|struck)\b(?!\s+(?:the\s+|a\s+|an\s+|my\s+|his\s+|her\s+)?(?:flint|match|light|steel|tinder|spark|bell|deal|bargain|camp|tent|sail|chord|note|pose|balance|entry|entries|name|names|line|lines|record|records|word|words|debt|sum|figure|charge|clause|it\s+(?:from|out|off|through)|that\s+(?:entry|name|line|out)|them\s+(?:from|out|off)|(?:[\w'’-]+\s+){0,4}?(?:from|out\s+of|off)\s+(?:the\s+|a\s+|my\s+|his\s+|her\s+|[\w'’-]+['’]s\s+)?(?:[\w'’-]+\s+){0,2}?(?:ledger|books?|records?|tally|roll|list|register|page|slate))\b))\b",
    re.I,
)


_ATTRIBUTION_TAIL_RE = re.compile(
    r",?\s*(?:just\s+|exactly\s+)?(?:as|like)\s+(?:[A-Z][\w'’-]+|she|he|they|the\s+[a-z]+)\s+(?:had\s+)?"
    r"(?:asked|said|told\s+(?:me|us)|wanted|suggested|instructed|advised|put\s+it|described|showed\s+(?:me|us)|promised)\b[^.;,]*",
    re.I,
)


def infer_check_from_action(player_input: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Pick a skill code + optional opposition for auto-checks on player actions."""
    text = (player_input or "").lower()
    if not text or text.startswith("__"):
        return None
    # A declared hands-on act is the check (playtest #85a). "i polish the
    # blades the best i can" was read as an act for the prose and missed by
    # this table, so the work rolled nothing. A fight in the same line still
    # rolls the fight. Read from the player's own line only, never the
    # engine notes after it (#43), and in its own case so "the Forge" stays
    # a name.
    own = re.split(r"\n\s*\n", str(player_input or ""), maxsplit=1)[0].strip()
    # The trigger table reads the same line (playtest #89, Saltmarrow run):
    # the engine's own note after it ("the player is talking to Tam Kemp")
    # rolled a contested persuasion on every turn with anyone present, a
    # silent rope-haul included. A verb the player denies is not an act:
    # "I'm not hiding" rolled stealth and a mishap (#102).
    # What the player watches happen is not the player's act: "watch how fast
    # the water climbs the tiles" rolled athletics (#102).
    text = _WATCHED_CLAUSE_RE.sub(" ", _NEGATED_VERB_RE.sub(" ", own.lower()))
    # An attribution tail is not the player asking (8B run 150, T14).
    text = re.sub(r"\s+(?=[.,;!?])", "", _ATTRIBUTION_TAIL_RE.sub("", text))
    # Words inside the player's quotes are speech, not acts (7B run 6, T3):
    # "...before they pick the lower district clean" rolled lockpicking on a
    # walk to the yard. Speech can still carry a social check (a plea, a
    # threat); hands-on skills are read from the narrated part only.
    own_acts = _SPOKEN_RE.sub(" ", own)
    acted = _SPOKEN_RE.sub(" ", text)
    # Hands-on checks come from what the player does now (app/act_clauses):
    # a plan, a case it waits on, a message for someone or a thing set in the
    # mind rolls nothing ("read the name aloud to fix it in my memory" rolled
    # craft, 8B run 151 T13). Talk is still read from the whole line, and a
    # question asked ("what is the ring worth?") is still a check of what is known.
    try:
        from app.act_clauses import acts_now

        own_acts = acts_now(own_acts, keep_questions=True)
        acted = acts_now(acted, keep_questions=True)
    except Exception:
        pass
    # What someone else is doing is not the player's act: "I walk over to where
    # the mole catcher is digging" rolled athletics (7B run 19, T1).
    own_acts = _OTHERS_DOING_RE.sub(" ", own_acts)
    acted = _OTHERS_DOING_RE.sub(" ", acted)
    # A key in a lock is no picking: "I try the rusted key in the box's lock"
    # rolled lockpicking (8B run 150, T87).
    own_acts = _KEY_IN_LOCK_RE.sub(" ", own_acts)
    acted = _KEY_IN_LOCK_RE.sub(" ", acted)
    # A thing striking a thing is no blow of the player's: "work the hollow
    # with the oar until the blade strikes something solid" rolled melee vs the
    # scarred crewman (8B run 146, T11).
    own_acts = _THING_STRIKES_RE.sub(" ", own_acts)
    acted = _THING_STRIKES_RE.sub(" ", acted)
    # An attribution tail is not the player asking: "search the wreck's hold
    # for anything alive, as Mabel asked" rolled persuasion against Mabel, two
    # places away (8B run 150, T14).
    own_acts = re.sub(r"\s+(?=[.,;!?])", "", _ATTRIBUTION_TAIL_RE.sub("", own_acts))
    acted = re.sub(r"\s+(?=[.,;!?])", "", _ATTRIBUTION_TAIL_RE.sub("", acted))
    text = _THING_STRIKES_RE.sub(" ", text)
    act = None
    if not _COMBAT_LINE_RE.search(own_acts):
        try:
            from app.prose_state import act_rules

            act = act_rules(own_acts) if own_acts.strip() else None
        except Exception:
            act = None
    pairs = list(SKILL_TRIGGER_PATTERNS)
    # Pack triggers are checked first so a campaign can route "pole the barge"
    # to its own skill instead of falling through to a built-in near-match.
    try:
        from app.content_packs import disabled_skill_codes, skill_triggers

        pack_pairs = skill_triggers()
        disabled = disabled_skill_codes()
    except Exception:
        pack_pairs, disabled = [], set()

    skill = None
    from_pack = False
    # Patterns outer, variants inner: table order still decides which skill
    # wins, so a de-inflected match can never outrank an earlier pattern that
    # matched the sentence as typed.
    variants = _trigger_text_variants(text)
    acted_variants = _trigger_text_variants(acted) if acted != text else variants
    combat_variants = _trigger_text_variants(acted, protect_others=False)
    # Others lying is not the player deceiving (7B run 11, T2: "there are three
    # in this town and they all lie" rolled deception, a critical failure).
    social = _OTHERS_DO_SOCIAL_RE.sub(" ", text)
    social_variants = _trigger_text_variants(social) if social != text else variants
    pack_list = list(pack_pairs)
    for index, (pattern, code) in enumerate(pack_list + pairs):
        if code in disabled:
            continue
        try:
            reads = social_variants if code in _SPEECH_SKILLS else acted_variants
            # A blow is a check whoever strikes ("he strikes at the guard"
            # starts the fight); other acts are the player's own only.
            if code in _COMBAT_TRIGGER_SKILLS:
                reads = combat_variants
            # Noun triggers read the line as typed: "which way the tunnel runs"
            # de-inflected to "rune" and rolled symbol lore (7B run 30, T3).
            if code in _NOUN_TRIGGER_SKILLS:
                reads = reads[:1]
            if any(re.search(pattern, variant) for variant in reads):
                skill = code
                from_pack = index < len(pack_list)
                break
        except re.error:
            continue
    if act and act["skill_code"] not in disabled:
        # The act decides the check (#85a), after the pack triggers and the
        # disabled list (#85 review): a campaign that routes "haul the nets"
        # to its own skill still rolls that skill, now as the act.
        act_keys = {"act": act["phrase"], "act_family": act["family"], "routine": bool(act["routine"])}
        if from_pack and skill:
            return {**_check_with_opposition(skill, text, context, own), **act_keys}
        if act["family"] == "perform":
            # A performance is for someone: social, with the NPC it is for.
            return {**_check_with_opposition(act["skill_code"], text, context, own), **act_keys}
        # Work is against the task, not against the smith watching it.
        check = {
            "skill_code": act["skill_code"],
            "opposition": None,
            "weapon_or_tool": "",
            "social": False,
            "npc_ref": None,
            **act_keys,
        }
        # Work and talk in one line keep both rolls (#85 review): "i polish
        # the blades and ask Finnian what he pays" also rolls the ask against
        # Finnian, as it did before the act took the turn's check.
        if skill and skill != act["skill_code"]:
            also = _check_with_opposition(skill, text, context, own)
            if also.get("social"):
                check["also_check"] = also
        return check
    # "What's it worth when I bring it in?" asks about a job's pay, not the
    # value of a thing in hand (7B Saltmarrow T6: a failed appraise and a
    # speech blunder on a question about the reward).
    if skill == "appraise" and _JOB_PAY_RE.search(text) and not re.search(r"\b(?:apprais\w*|value\s+of|haggl\w*|bargain\w*)\b", text):
        skill = None
    # Reading a plain notice, letter or posting is routine (#102; 7B run 8, T3:
    # investigation DC15 to read a job posting; run 5 T44, T67, T80). A text
    # that is hard to read (faded, in cipher, old marks) still takes a check.
    if skill == "investigation" and _PLAIN_READ_RE.search(acted) and not _HARD_TEXT_RE.search(acted):
        from app import turn_ledger

        turn_ledger.note("check", "routine_read_no_check", line=own_acts[:200])
        skill = None
    if not skill:
        return None
    check = _check_with_opposition(skill, text, context, own)
    # A plain question or greeting is everyday speech, not a persuasion attempt
    # (playtest #88): "ask Vael about the seal" rolled an untrained contested
    # check against the NPC's power every turn, and the misses were read as
    # mishaps. Routine: two easier, and only a natural 1 can go badly. A line
    # that pushes (convince, demand, haggle, plead) keeps the full roll.
    if skill == "persuasion" and not any(_PERSUADE_RE.search(variant) or _PRICE_OFFER_RE.search(variant) for variant in variants):
        check["routine"] = True
        check["plain_talk"] = True
    return check


# A sum named with a dealing word: the player is bargaining, so the roll is the
# full one, not a routine greeting (8B run 145, T19).
_PRICE_OFFER_RE = re.compile(
    # Within the same breath of speech, across a full stop: '"... I set six
    # gold coins on his counter. Six for both, or I walk."' (8B run 146, T16).
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|thirty|fifty|a\s+hundred)\s+"
    r"(?:gold|silver|coppers?|coins?|crowns?)\b[\s\S]{0,120}?\b(?:deal|offer|take\s+it|or\s+nothing|and\s+no\s+more|"
    r"there\s+and\s+back|final|last\s+offer|or\s+(?:i|we)\s+walk|for\s+(?:both|the\s+lot|all\s+of\s+it)|take\s+it\s+or\s+leave\s+it)\b",
    re.I,
)


_PLAIN_READ_RE = re.compile(
    r"\bread\w*\b[^.?!]{0,50}\b(?:notice|posting|post|sign|letter|note|parchment|board|poster|list|menu|tally|"
    r"ledger|message|label|bill|placard|price)s?\b"
    # The thing first: "I take the note he holds out and read it" (7B run 24, T3).
    r"|\b(?:notice|posting|sign|letter|note|parchment|poster|message|label|bill|placard)s?\b[^.?!]{0,50}\bread\s+(?:it|them)\b"
)
_HARD_TEXT_RE = re.compile(
    r"\b(?:decipher\w*|cipher|code|coded|symbols?|runes?|glyphs?|marks|faded|smudged|torn|water-?stained|"
    r"hidden|secret|old\s+tongue|foreign|scrawl\w*)\b"
)


# Speech that leans on someone: the full roll. Anything else that the talk
# pattern catches (ask, greet, say hello) is routine.
_PERSUADE_RE = re.compile(
    r"\b(persuade|convinc\w*|negotiat\w*|haggl\w*|bargain\w*|plead\w*|beg|demand\w*|insist\w*|press\w*|argu\w*|"
    r"talk \w+ (into|out of)|win \w+ over)\b"
)

# How a social fumble goes wrong. The attitude already turned cold for it;
# this is the line the prose can show.
_BLUNDER_LINES = (
    "the words come out wrong.",
    "you say the one thing they did not want to hear.",
    "you talk over them and lose the moment.",
    "you misjudge the moment and give offense.",
    "you push when you should have waited.",
    "you let slip more than you meant to.",
)


def _line_names_npc(text: str, npc: dict[str, Any]) -> bool:
    """The full name, the first name as a word, or the [[code]] tag."""
    name = str(npc.get("name") or "").lower().strip()
    code = str(npc.get("code") or "").lower().strip()
    if not name and not code:
        return False
    if name and name in text:
        return True
    first = name.split()[0] if name else ""
    if len(first) >= 3 and re.search(rf"\b{re.escape(first)}\b", text):
        return True
    return bool(code) and f"[[{code}]]" in text


# Skills rolled against someone: the social set and the sneaking hand.
_CONTESTED_SKILLS = frozenset({
    "persuasion", "deception", "intimidation", "insight", "etiquette", "performance", "streetwise",
    "stealth", "sleight_of_hand", "pickpocket", "disguise", "grapple", "wrestling",
})


_NOT_A_PERSON_WORD = frozenset({
    "The", "A", "An", "At", "In", "On", "To", "By", "For", "Of", "And", "But", "Then", "When", "While", "After",
    "Before", "Inn", "Hall", "House", "Wharf", "Dock", "Docks", "Harbour", "Harbor", "Street", "Road", "Lane", "Square",
    "Market", "Gate", "Bay", "Mouth", "Wake", "Flats", "Shore", "Town", "Guild", "Captain", "Drowned", "Old", "New",
    "Salvage", "Tally", "Store", "Shop", "Yard", "Bridge", "Tower", "Keep", "Church", "Chapel",
})


def _names_unknown_person(src: str, pool: list[dict[str, Any]], ctx: dict[str, Any]) -> bool:
    """The line names someone in full whom the engine does not hold (two capitalised words, no place word)."""
    known: set[str] = set()
    for npc in pool:
        known.update(w.lower() for w in str(npc.get("name") or "").split())
    for location in ctx.get("locations") or []:
        if isinstance(location, dict):
            for npc in location.get("npcs") or []:
                if isinstance(npc, dict):
                    known.update(w.lower() for w in str(npc.get("name") or "").split())
            known.update(w.lower() for w in str(location.get("name") or "").split())
    current = ctx.get("current_location") if isinstance(ctx.get("current_location"), dict) else {}
    known.update(w.lower() for w in str(current.get("name") or "").split())
    for first, last in re.findall(r"\b([A-Z][a-z]{2,})\s+([A-Z][a-z]{2,})\b", str(src or "")):
        if first in _NOT_A_PERSON_WORD or last in _NOT_A_PERSON_WORD:
            continue
        if first.lower() in known or last.lower() in known:
            continue
        return True
    return False


def _check_with_opposition(skill: str, text: str, context: dict[str, Any] | None, cased: str = "") -> dict[str, Any]:
    """One inferred check for ``skill``: the opposing NPC or foe the line names, and the tool."""
    opposition: dict[str, Any] = {}
    ctx = context or {}
    matched_npc: dict[str, Any] | None = None
    # Prefer combat target / local NPC as opposition when present.
    mech = ctx.get("mechanics_context") if isinstance(ctx.get("mechanics_context"), dict) else {}
    combat = mech.get("combat") if isinstance(mech.get("combat"), dict) else {}
    target = combat.get("target") if isinstance(combat.get("target"), dict) else None
    if target:
        matched_npc = target
        opposition = {
            "name": target.get("name") or "foe",
            "rank": target.get("rank"),
            "stats": target.get("stat_profile") or target.get("stats") or {},
            "defense": target.get("defense") or (target.get("combat_profile") or {}).get("defense"),
            "level": target.get("level"),
            "power": target.get("attack_max") or target.get("power"),
        }
    else:
        # The dead are nobody's other side (#164: "i say hi to Dr. Theo" rolled
        # persuasion against him a turn after his death and wrote his attitude).
        pool = [n for n in _npc_pool_from_context(ctx) if not int(n.get("died_turn") or 0) > 0]
        # The engine's own record of who is in the scene this turn
        # (conversation.resolve: "present" is the scene's members here, plus
        # whoever the line addresses). Someone the engine does not place here
        # is never the other side of a roll: the partner left at the gate, the
        # person asked after who is elsewhere, the companion when the line asks
        # someone else (playtest #89, reopened twice; 7B run 5: Bryony, Warin,
        # Verity, Abel absent). With no scene record yet (a fresh game, a
        # harness without one) the location's roster stands in.
        conv = ctx.get("conversation_turn") if isinstance(ctx.get("conversation_turn"), dict) else None
        scene_here: set[str] | None = None
        if conv is not None and isinstance(conv.get("present"), list):
            scene_here = {str(c).upper() for c in conv.get("present") or [] if c}
            scene_here |= {str(c).upper() for c in conv.get("addressed") or [] if c}
        names_absent = False
        # Someone the line calls on who is known elsewhere (not at this place at
        # all) is not here either: "go down to the dock to find Orme and ask"
        # from the inn rolled against Hilde the innkeeper, the one person in the
        # scene record (8B run 145, T28).
        here_codes = {str(n.get("code") or "").upper() for n in pool}
        for location in ctx.get("locations") or []:
            if not isinstance(location, dict):
                continue
            for npc in location.get("npcs") or []:
                if isinstance(npc, dict) and str(npc.get("code") or "").upper() not in here_codes and _line_names_npc((cased or text).lower(), npc):
                    names_absent = True
        if scene_here:
            absent = [n for n in pool if str(n.get("code") or "").upper() not in scene_here]
            if absent:
                # A line that calls on someone who is not here rolls against
                # nobody, not against whoever happens to be the one person left.
                names_absent = names_absent or any(_line_names_npc((cased or text).lower(), n) for n in absent)
                try:
                    from app import turn_ledger

                    turn_ledger.note(
                        "check", "absent_not_an_opponent",
                        names=[str(n.get("name") or n.get("code") or "") for n in absent][:6],
                        named_in_line=names_absent,
                    )
                except Exception:
                    pass
            pool = [n for n in pool if str(n.get("code") or "").upper() in scene_here]
            # Two people named, one addressed: '"Forty-six for what, Veyra? ...
            # what I read in Rolf's book"' rolled against Rolf, first in the
            # roster (8B run 146, T72). The one the line speaks to comes first.
            addressed = {str(c).upper() for c in conv.get("addressed") or [] if c} if conv is not None else set()
            if addressed:
                pool.sort(key=lambda n: str(n.get("code") or "").upper() not in addressed)
        # "I keep my eyes on the man in the skiff, not Emrys. 'I asked him.
        # Tobin, what is under the tarpaulin?'" rolled persuasion vs Emrys (7B
        # run 36, T6). A name the line turns away from is not the other side,
        # and a line that calls on someone the engine does not hold yet has no
        # one known on the other side.
        # Left behind is turned away from too: "I leave Brida at the gate and
        # walk to the guild hall ... ask the clerk" rolled vs Brida (8B run 5, T5).
        # Both patterns read names by their capital, so they need the line as
        # typed: infer_check_from_action passes it lowercased, and in play
        # "I leave Mira at the well and walk up to the reeve's office" still
        # rolled against Mira (8B run 15, T6; the run 5 test passed the cased line).
        src = cased or text
        # A leave-taking is not an address: "thank Mira, and go out to find Eda
        # Jessop ... to ask" rolled against Mira (8B run 147, T54).
        named_text = re.sub(r"\b(?:not|instead\s+of|rather\s+than|ignoring|leave|leaving|left|away\s+from|thank|thanks|thanking|"
                            # "Thanks, Humphrey." with its comma (8B run 154, T4).
                            r"nod(?:s|ded|ding)?\s+to|wav(?:e|es|ed|ing)\s+to|bid(?:s|ding)?|bow(?:s|ed|ing)?\s+to)[,\s]+(?:at\s+|to\s+|on\s+)?[A-Z][\w'’-]+",
                            " ", src)
        # Asked after is not asked: "ask the nearest dockhand where Elara Veyne
        # can be found" rolled against Elara, who was not there (8B run 146,
        # T77). The person a question is about is not its other side.
        named_text = re.sub(r"\b(?:where|whereabouts\s+of|find\w*|about|after|looking\s+for|search\w*\s+for|news\s+of|word\s+of|"
                            # The debtor named in a question put to someone else: "ask Mira whether
                            # the guild wants that bread debt collected from Dunmore" rolled against
                            # Dunmore (8B run 147, T89).
                            r"(?:collect\w*|owed|owes|owing|debt|due|payment|money|coin)\s+(?:by|from|of|to)|"
                            r"(?:bonus|reward|price|fee|pay|warrant)\s+for|against)"
                            r"\s+(?:the\s+)?[A-Z][\w'’-]+(?:\s+[A-Z][\w'’-]+)?", " ", named_text)
        if cased:
            named_text = named_text.lower()
        called = [
            m.group(1)
            for m in re.finditer(r"(?:^|[\"“]|[.!?]\s+)([A-Z][a-z]{2,}),\s+(?:what|who|where|why|how|is|are|do|did|can|will|tell|show|give)\b", src)
        ]
        known_first = {str(n.get("name") or "").split()[0].lower() for n in pool if str(n.get("name") or "").strip()}
        stranger_called = bool(called) and all(c.lower() not in known_first for c in called)
        # Named, then left behind: "I nod to Thorne and leave the tally house,
        # heading down to the harbour to ask the boat owners" rolled against
        # Thorne at his desk (8B run 96, T4). Only a mention after the leaving counts.
        # A walk away does the same: "I thank Veyne with a nod and walk down to the docks" (8B run 99, T4).
        left_at = re.search(
            r"\b(?:leave|leaves|leaving|walk\s+out\s+of|step\s+out\s+of|head\s+out\s+of)\s+the\b"
            r"|\band\s+(?:then\s+)?(?:walk|head|go|make\s+my\s+way|set\s+off|move\s+on|turn\s+away)\b"
            # A new sentence that sets off: '"Isk. Thanks, Humphrey." I head up to
            # the tally house to ask for work' rolled against Humphrey (8B run 154, T4).
            r"|(?:^|[.!?][\"”']?\s+)(?:i|we)\s+(?:then\s+)?(?:walk|head|go|make\s+my\s+way|set\s+off|move\s+on|turn\s+away)\b",
            named_text, re.I,
        )
        # Only a contest has another side: a bystander named in the line is no
        # opponent to a search or a craft ("kick back up to Bennet's boat"
        # rolled perception vs Bennet, 8B run 145 T24).
        contested = skill in _CONTESTED_SKILLS
        for npc in ([] if (stranger_called or not contested) else pool[:12]):
            if left_at and _line_names_npc(named_text, npc) and not _line_names_npc(named_text[left_at.end():], npc):
                continue
            if _line_names_npc(named_text, npc):
                matched_npc = npc
                opposition = {
                    "name": npc.get("name"),
                    "rank": npc.get("rank"),
                    "stats": npc.get("stat_profile") or {},
                    "defense": npc.get("defense"),
                    "attitude": npc.get("attitude"),
                    "presence": npc.get("presence"),
                    "power_rank": npc.get("power_rank"),
                }
                break
        # Talk with no named target: the one the engine decided the player is
        # talking to, or the only person here. The first local in the list was
        # a stale pick, often a listener or someone who had left (playtest #89).
        if not matched_npc and not stranger_called and skill in {"persuasion", "deception", "intimidation", "insight", "etiquette"}:
            conv = ctx.get("conversation_turn") if isinstance(ctx.get("conversation_turn"), dict) else {}
            addressed = [str(c).upper() for c in conv.get("addressed") or []]
            by_code = {str(n.get("code") or "").upper(): n for n in pool if n.get("code")}
            if addressed and addressed[0] in by_code and not (
                left_at
                and _line_names_npc((cased or text).lower(), by_code[addressed[0]])
                and not _line_names_npc(named_text[left_at.end():], by_code[addressed[0]])
            ):
                # The engine resolved who the line is said to; a name left
                # behind earlier in the line changes nothing. Unless the line
                # then leaves: "thank Mira, and go out to find Eda Jessop ... to
                # ask" is said to nobody here (8B run 147, T54).
                matched_npc = by_code[addressed[0]]
            elif not addressed and not names_absent and len(pool) == 1 and not _names_unknown_person(src, pool, ctx):
                # Someone the engine does not know yet, named in full ("look for
                # Oswin Goodwin ... and ask him"), is the other side, not the one
                # person left in the scene record (8B run 146, T28: vs Emery).
                matched_npc = pool[0]
            # The line asks someone by their job ("ask the clerk about the
            # boats"): a stale partner with another job is not the other side.
            asked_role = re.search(r"\b(?:ask|asks|asking|tell|question|press|talk\s+to|speak\s+to)\s+the\s+([a-z][a-z-]{2,})\b", text, re.I)
            if matched_npc and asked_role and asked_role.group(1).lower() not in str(matched_npc.get("role") or "").lower():
                matched_npc = None
            if matched_npc and re.search(rf"\b(?:leave|leaving|left|away\s+from)\s+{re.escape(str(matched_npc.get('name') or '').split()[0])}\b", text, re.I):
                matched_npc = None
            # Leaving the place leaves the partner: "I leave the tally house and
            # head down through town to the bay" rolled against the tallyman
            # still sitting at his desk (8B run 36, T5).
            if matched_npc and re.search(r"\b(?:leave|leaves|leaving|walk\s+out\s+of|step\s+out\s+of|head\s+out\s+of)\s+the\b",
                                         text, re.I):
                matched_npc = None
            if matched_npc:
                opposition = {
                    "name": matched_npc.get("name"),
                    "rank": matched_npc.get("rank"),
                    "stats": matched_npc.get("stat_profile") or {},
                    "attitude": matched_npc.get("attitude"),
                }
    weapon = ""
    # Whole words only, and a boat's bow is not a weapon: "check the knot on the
    # bow line" rolled ranged and hurt the player "unskilled with bow" (7B run 29, T10);
    # "elbow" and "rainbow" held a bow too.
    for w in ("sword", "axe", "spear", "dagger", "bow", "rifle", "hammer", "staff", "blade"):
        if w == "bow" and not re.search(SKILL_TRIGGER_PATTERNS[1][0], text):
            continue
        if re.search(rf"\b{w}\b", text):
            weapon = w
            break
    return {
        "skill_code": skill,
        "opposition": opposition or None,
        "weapon_or_tool": weapon,
        "social": skill in {"persuasion", "deception", "intimidation", "insight", "etiquette", "performance", "streetwise"},
        "npc_ref": {
            "code": (matched_npc or {}).get("code"),
            "name": (matched_npc or {}).get("name"),
            "attitude": (matched_npc or {}).get("attitude"),
            "personality": (matched_npc or {}).get("personality"),
            "role": (matched_npc or {}).get("role"),
            "presence": (matched_npc or {}).get("presence"),
            "power_rank": (matched_npc or {}).get("power_rank"),
            "principles": (matched_npc or {}).get("principles"),
            "dislikes": (matched_npc or {}).get("dislikes"),
            "likes": (matched_npc or {}).get("likes"),
        }
        if matched_npc
        else None,
    }


_ACT_OUTCOME_WORDS = {
    "critical_success": "it goes better than expected: the work is done, and done well",
    "success": "it works: the work is done",
    "partial": "it is only half done or done poorly: someone can see the flaws",
    "failure": "it goes wrong or falls short: the work is not done",
    "critical_failure": "it goes badly wrong: the work is spoiled or the player is hurt",
}


def check_for_clause(player_line: str, skill_code: str) -> str:
    """The player's own words a roll decides, outside quotes, for the narrator (7B run 30, T10).

    A check from a trigger word carries no declared act, so the narrator was
    told only "mining, failure" and wrote both traps set without trouble. The
    clause holding that skill's trigger is the act; otherwise the first clause.
    """
    own = _SPOKEN_RE.sub(" ", str(player_line or ""))
    clauses = [c.strip(" ,") for c in re.split(r"(?<=[.!?;])\s+", own) if c.strip(" ,.")]
    if not clauses:
        return ""
    patterns = [p for p, code in SKILL_TRIGGER_PATTERNS if code == skill_code]
    for clause in clauses:
        low = clause.lower()
        if any(re.search(p, low) for p in patterns):
            return clause[:160]
    return clauses[0][:160]


def act_outcome(checks: Any) -> dict[str, Any] | None:
    """What the dice decided for the player's declared act, for the prose (playtest #85a).

    The draft wrote "Not bad, not bad at all" with no roll behind it. This is
    the engine's answer, written before the prose so the prose can follow it:
    {"act", "skill", "proficiency", "outcome", "degree", "means", "injury"?}.
    """
    for check in checks if isinstance(checks, list) else []:
        if not isinstance(check, dict) or not check.get("act") or check.get("natural") is None:
            continue
        outcome = str(check.get("outcome") or "failure")
        skill = check.get("skill") if isinstance(check.get("skill"), dict) else {}
        match = str(check.get("skill_match") or "")
        source = str(check.get("skill_source") or "")
        out: dict[str, Any] = {
            "act": str(check.get("act"))[:100],
            "skill": str(skill.get("name") or skill.get("code") or ""),
            "proficiency": "untrained" if match == "untrained" or not source else f"{source} ({match})",
            "outcome": outcome,
            "degree": str(check.get("degree") or outcome),
            "means": _ACT_OUTCOME_WORDS.get(outcome, _ACT_OUTCOME_WORDS["failure"]),
        }
        injury = check.get("injury") if isinstance(check.get("injury"), dict) else None
        if injury and injury.get("summary"):
            out["injury"] = str(injury["summary"])[:160]
        blunder = check.get("blunder") if isinstance(check.get("blunder"), dict) else None
        if blunder and blunder.get("summary"):
            out["blunder"] = str(blunder["summary"])[:160]
        return out
    return None


# Any sign of a hurt in the prose: pain, a slip, blood, or the limb itself.
_PROSE_HURT_RE = re.compile(
    r"\b(?:hurt\w*|pain\w*|winc\w+|cut|cuts|bruis\w*|twist\w*|scrap\w*|blood\w*|bleed\w*|ach\w*|stumbl\w*|"
    r"slip\w*|graz\w*|sting\w*|throb\w*|gash\w*|wrench\w*|sprain\w*|jar\w*|bang\w*|smash\w*|crack\w*|sear\w*|"
    r"burn\w*|limp\w*|gasp\w*|yelp\w*|hiss\w*|injur\w*|wound\w*|nick\w*|swell\w*|numb\w*|fall\w*|fell|tumbl\w*|"
    r"botch\w*|fumbl\w*|clumsy|awkward\w*|pinch\w*|snag\w*|tear\w*|tore|torn|strain\w*|jolt\w*|sharp)\b",
    re.I,
)


def prose_shows_hurt(narration: str, injury: dict[str, Any] | None) -> bool:
    """True when the prose shows any hurt at all, or names the hurt limb (7B run 30, T10)."""
    text = str(narration or "")
    if _PROSE_HURT_RE.search(text):
        return True
    limb = str((injury or {}).get("limb") or "").strip()
    return bool(limb) and bool(re.search(rf"\b{re.escape(limb)}\b", text, re.I))


def apply_check_to_turn(turn: dict[str, Any], check: dict[str, Any]) -> dict[str, Any]:
    """Merge a resolved check into turn JSON for apply_turn (injuries, journal, self_check)."""
    result = dict(turn or {})
    checks = list(result.get("skill_checks") or [])
    checks.append(check)
    result["skill_checks"] = checks[-8:]

    injury = check.get("injury") if isinstance(check.get("injury"), dict) else None
    player = dict(result.get("player") or {})
    if injury and injury.get("health_delta"):
        try:
            player["health_delta"] = int(player.get("health_delta") or 0) + int(injury["health_delta"])
        except (TypeError, ValueError):
            pass
        result["player"] = player
        # This amount was rolled by the check above, not guessed by the model.
        # Mark it so band authority passes it through instead of re-rolling
        # a server-computed injury into a different number.
        authored = list(result.get("_server_authored") or [])
        if "player.health_delta" not in authored:
            authored.append("player.health_delta")
        result["_server_authored"] = authored

    journal = list(result.get("journal") or [])
    journal.append(
        {
            "kind": "skill_check",
            "content": check.get("display_block") or check.get("display") or "",
        }
    )
    if injury:
        journal.append(
            {
                "kind": "injury",
                "content": json.dumps(injury, ensure_ascii=True)[:900],
            }
        )
        # A scratch from a bad miss heals on its own; only a natural 1 leaves
        # a condition (playtest #88). Older rolls carry no flag: lasting.
        if injury.get("lasting", True):
            conditions = list(result.get("condition_changes") or [])
            conditions.append(
                {
                    "id": f"inj_{injury.get('limb') or 'wound'}",
                    "name": f"Injured {injury.get('limb') or 'body'}",
                    "summary": injury.get("summary") or "",
                    "penalties": injury.get("combat_penalty") or {},
                    "severe": bool(injury.get("severity") or injury.get("severe")),
                }
            )
            result["condition_changes"] = conditions
    blunder = check.get("blunder") if isinstance(check.get("blunder"), dict) else None
    if blunder:
        journal.append({"kind": "blunder", "content": str(blunder.get("summary") or "")[:300]})
    result["journal"] = journal
    return result


def catalog_public() -> dict[str, Any]:
    skills = load_skill_library()
    return {
        "categories": CATEGORIES,
        "skills": skills,
        "defaults": default_check_settings(),
        "difficulty_dc_shift": DIFFICULTY_DC_SHIFT,
        "outcomes": list(OUTCOME_RANK.keys()),
    }


def search_skills(
    query: str,
    library: list[dict[str, Any]] | None = None,
    *,
    limit: int = 12,
    settings: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Find the skills relevant to one action, ranked by match strength.

    Used instead of shipping the whole catalog into every prompt. Matching is
    deliberately cheap and local: name/code tokens, tags, category, and the
    same trigger regexes that drive auto-checks.
    """
    cfg = merge_check_settings(settings)
    lib = library if library is not None else load_skill_library()
    enabled_codes = set(cfg.get("enabled_skill_codes") or [])
    enabled_cats = set(cfg.get("enabled_categories") or [])
    text = _norm(query)
    tokens = {t for t in text.split() if len(t) > 2}

    scored: list[tuple[float, dict[str, Any]]] = []
    for skill in lib:
        if not skill.get("enabled", True):
            continue
        if enabled_codes and skill.get("code") not in enabled_codes:
            continue
        if enabled_cats and skill.get("category") not in enabled_cats:
            continue
        score = 0.0
        name_tokens = set(_norm(str(skill.get("name") or "")).split())
        code_token = _norm(str(skill.get("code") or "").replace("_", " "))
        if code_token and code_token in text:
            score += 5.0
        if name_tokens & tokens:
            score += 3.0 * len(name_tokens & tokens)
        else:
            # Stem-ish prefix match so "persuade" finds "persuasion" and
            # "sneaking" finds "stealth"'s tag "sneak". Exact tokens rarely
            # line up between natural player phrasing and skill names.
            for want in name_tokens | {code_token}:
                if len(want) < 5:
                    continue
                if any(t[:5] == want[:5] for t in tokens):
                    score += 2.5
                    break
        for tag in skill.get("tags") or []:
            tag_norm = _norm(str(tag))
            if not tag_norm:
                continue
            if tag_norm in text:
                score += 2.0
            elif len(tag_norm) >= 4 and any(t[:4] == tag_norm[:4] for t in tokens):
                score += 1.0
        for trigger in skill.get("triggers") or []:
            try:
                if re.search(str(trigger), text):
                    score += 6.0
            except re.error:
                continue
        if score > 0:
            scored.append((score, skill))

    scored.sort(key=lambda pair: (-pair[0], pair[1].get("name") or ""))
    return [skill for _, skill in scored[: max(1, int(limit))]]


def gm_context_block(
    settings: dict[str, Any] | None,
    library: list[dict[str, Any]] | None = None,
    *,
    query: str = "",
    limit: int = 12,
) -> dict[str, Any]:
    """
    Compact packet for prompt context / playthrough options.

    ``active_skills`` used to carry the entire enabled catalog — 60 entries,
    ~6.4KB, ~1,600 tokens in *every* turn prompt, on a model that mostly does
    not choose skills any more because checks resolve server-side. When a
    ``query`` is supplied the catalog is searched instead of dumped, and only
    the matching skills (plus a small always-useful core) ship.
    """
    cfg = merge_check_settings(settings)
    if not cfg.get("dice_checks_enabled"):
        return {"dice_checks_enabled": False}
    lib = library if library is not None else load_skill_library()
    enabled_codes = set(cfg.get("enabled_skill_codes") or [])
    enabled_cats = set(cfg.get("enabled_categories") or [])

    def _slim(skill: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": skill["code"],
            "name": skill["name"],
            "category": skill["category"],
            "attribute": skill["attribute"],
            "base_dc": skill["base_dc"],
        }

    eligible = [
        s
        for s in lib
        if s.get("enabled")
        and (not enabled_codes or s["code"] in enabled_codes)
        and (not enabled_cats or s.get("category") in enabled_cats)
    ]

    if query:
        matched = search_skills(query, lib, limit=limit, settings=cfg)
        # Always keep a couple of universal fallbacks so the model has a valid
        # code to name even when nothing matched the action.
        core = [s for s in eligible if s.get("code") in {"general", "perception", "persuasion"}]
        seen: set[str] = set()
        active = []
        for skill in matched + core:
            if skill["code"] in seen:
                continue
            seen.add(skill["code"])
            active.append(_slim(skill))
        active = active[: max(1, limit + 3)]
    else:
        active = [_slim(s) for s in eligible]
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
            "Vary skill codes across scenes: do not collapse every social beat to insight/deception or every craft beat to rope/knots/fabric. Prefer the most specific catalog skill (cooking, smithing, navigation, appraise, animal_handling, mining, cartography, etc.).",
            "If the linked attribute is low but a specialized skill rank is present, prefer partial success with incomplete info rather than total blank.",
            "On failure/critical failure with negative_outcomes, apply a concrete setback (wrong reading, alarm, injury risk, lost time, burned favor).",
            "New skills discovered in play should be registered and compared to similar catalog skills for DC balance.",
        ],
        "active_skills": active[:80],
    }
