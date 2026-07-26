"""Setup composer tree: load-order phases, field contracts, intent compile helpers.

The Randomize walk is a dependency tree, not a flat stamp of the idea box.
Phase order is topological; each field only receives matching intent keys.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from typing import Any


# ---------------------------------------------------------------------------
# Field contracts — kind + what intent may touch + paste bans
# ---------------------------------------------------------------------------

FIELD_CONTRACTS: dict[str, dict[str, Any]] = {
    "world_style": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "isekai", "tone", "keywords", "adapter_hint"],
        "forbidden": "Do not paste the full player idea slogan. Return a setting/genre phrase only.",
    },
    "tone": {
        "kind": "short_phrase",
        "intent_keys": ["tone", "genre"],
        "forbidden": "Return only mood/tone, not abilities or difficulty slogans.",
    },
    "tech_level": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords"],
        "forbidden": "Return tech era only.",
    },
    "magic_level": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "power_fantasy", "keywords"],
        "forbidden": "Return magic prevalence only.",
    },
    "custom_style": {
        "kind": "prose",
        "intent_keys": ["genre", "isekai", "edge", "power_fantasy", "tone", "keywords", "dm_stance", "style_notes"],
        "forbidden": (
            "World constraints, genre lean, and DM stance only. "
            "Do not paste skill timers (1-hour delay, cooldowns), ability lists, or the full idea slogan. "
            "Put growth timers in custom_skills / skill growth fields instead."
        ),
        "examples": [
            "Isekai coastal fantasy with a readable system UI when game_system is on. Fair pressure, no auto-win.",
        ],
        "ban_growth_timers": True,
    },
    "economy": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "edge", "difficulty"],
        "forbidden": (
            "Economy structure only: how goods/money move (scarce, coin-driven, barter-heavy, guild markets). "
            "Never mention skills, compounding, level delays, abilities, or power fantasy."
        ),
        "examples": ["scarce dock markets", "coin-driven harbor trade", "barter-heavy coastal exchange"],
        "ban_growth_slogans": True,
    },
    "world_races": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords"],
        "forbidden": (
            "Peoples/species list only (e.g. human; human, elf, beastfolk). "
            "Never power labels like 'Low-Power Human' or skill/growth slogans."
        ),
        "examples": ["human", "human, elf, dwarf", "human, riverfolk, beastfolk"],
        "ban_growth_slogans": True,
    },
    "race_magic_enabled": {
        "kind": "boolean",
        "intent_keys": ["genre", "power_fantasy"],
        "forbidden": "",
    },
    "race_magic_rarity": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "power_fantasy"],
        "forbidden": "Rarity phrase only.",
    },
    "race_magic_rules": {
        "kind": "prose",
        "intent_keys": ["genre", "keywords"],
        "forbidden": (
            "Per-race magic access only: who can cast, training vs innate, taboos. "
            "Never paste global skill compounding delays, cooldowns, or player power fantasy."
        ),
        "examples": [
            "Humans need formal training; elves inherit low glamour; beastfolk rarely cast but sense spirits.",
        ],
        "ban_growth_slogans": True,
        "ban_growth_timers": True,
    },
    "race_ability_rules": {
        "kind": "prose",
        "intent_keys": ["genre", "keywords"],
        "forbidden": (
            "Per-race innate/learned non-spell abilities only. "
            "Never paste 'near-useless skill compounds' or global level-delay timers for all races."
        ),
        "examples": [
            "Humans learn broadly; elves sense old growth; beastfolk inherit heightened senses. Innate gifts start modest.",
        ],
        "ban_growth_slogans": True,
        "ban_growth_timers": True,
    },
    "difficulty": {
        "kind": "enum",
        "allowed_values": ["easy", "normal", "hard", "brutal"],
        "intent_keys": ["difficulty", "edge"],
        "forbidden": "Return only easy, normal, hard, or brutal. Never paste slogans like 'compounding edge'.",
    },
    "death_rules": {
        "kind": "short_phrase",
        "intent_keys": ["difficulty", "edge", "dm_stance"],
        "forbidden": "Death/injury policy only.",
    },
    "narration_detail": {
        "kind": "enum",
        "allowed_values": ["concise", "balanced", "rich", "expansive"],
        "intent_keys": ["tone"],
        "forbidden": "Prose detail preference only.",
    },
    "loot_rarity": {
        "kind": "short_phrase",
        "intent_keys": ["difficulty", "edge", "power_fantasy", "genre"],
        "forbidden": "Loot frequency policy only.",
    },
    "inventory_weight_limit": {
        "kind": "number",
        "intent_keys": ["difficulty", "edge"],
        "forbidden": "Numeric weight limit only.",
    },
    "inventory_slot_limit": {
        "kind": "number",
        "intent_keys": ["difficulty"],
        "forbidden": "Numeric slot limit only.",
    },
    "inventory_rules": {
        "kind": "prose",
        "intent_keys": ["genre", "edge", "power_fantasy"],
        "forbidden": "Carry/equipment rules only.",
    },
    "leveling_system": {
        "kind": "boolean",
        "intent_keys": ["power_fantasy", "genre", "isekai"],
        "forbidden": "",
    },
    "xp_growth_speed": {
        "kind": "enum",
        "allowed_values": ["very slow", "slow", "normal", "fast", "very fast"],
        "intent_keys": ["power_fantasy", "difficulty"],
        "forbidden": "Growth speed label only.",
    },
    "game_system": {
        "kind": "boolean",
        "intent_keys": ["power_fantasy", "isekai", "adapter_hint"],
        "forbidden": "",
    },
    "system_style": {
        "kind": "short_phrase",
        "intent_keys": ["power_fantasy", "isekai", "genre", "adapter_hint"],
        "forbidden": "System UI flavor only (status window style), not ability text.",
    },
    "proficiency_system": {
        "kind": "boolean",
        "intent_keys": ["power_fantasy", "genre"],
        "forbidden": "",
    },
    "skill_levels_enabled": {
        "kind": "boolean",
        "intent_keys": ["power_fantasy"],
        "forbidden": "",
    },
    "skill_style": {
        "kind": "short_phrase",
        "intent_keys": ["power_fantasy", "difficulty"],
        "forbidden": (
            "Short skill-learning policy only (standard, generous, training-heavy, strict, or one short custom rule). "
            "Do not paste full ability descriptions or quest/faction text."
        ),
        "examples": ["standard", "training-heavy", "generous discovery with practice"],
        "max_len": 80,
    },
    "proficiency_access": {
        "kind": "short_phrase",
        "intent_keys": ["power_fantasy", "difficulty"],
        "forbidden": "Access rule only.",
    },
    "new_skill_frequency": {
        "kind": "enum",
        "allowed_values": ["very rare", "rare", "normal", "frequent", "very frequent"],
        "intent_keys": ["power_fantasy"],
        "forbidden": "Frequency label only.",
    },
    "skill_growth_speed": {
        "kind": "enum",
        "allowed_values": ["very slow", "slow", "normal", "fast", "very fast"],
        "intent_keys": ["power_fantasy"],
        "forbidden": "Growth speed label only.",
    },
    "proficiency_growth_speed": {
        "kind": "enum",
        "allowed_values": ["very slow", "slow", "normal", "fast", "very fast"],
        "intent_keys": ["power_fantasy"],
        "forbidden": "Growth speed label only.",
    },
    "custom_skills": {
        "kind": "list_custom",
        "intent_keys": ["power_fantasy", "keywords", "genre"],
        "forbidden": (
            "Comma-separated skill rules only; not a full idea dump. "
            "Put long XP/rank formulas on ability growth_math instead of here."
        ),
    },
    "npc_density": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "tone"],
        "forbidden": "How crowded scenes feel only (sparse, moderate, dense, faction-heavy). No skill growth slogans.",
        "examples": ["sparse", "moderate", "dense with faction patrols"],
        "ban_growth_slogans": True,
    },
    "quest_style": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "isekai", "keywords", "tone"],
        "forbidden": (
            "Quest STRUCTURE only: how work/hooks arrive (emergent, job board, faction chains, personal mysteries). "
            "Never describe player skills, compounding, near-useless abilities, or power fantasy."
        ),
        "examples": [
            "emergent local work",
            "job board and personal mysteries",
            "faction errands with side mysteries",
        ],
        "ban_growth_slogans": True,
        "max_len": 90,
    },
    "faction_pressure": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "tone", "keywords"],
        "forbidden": (
            "Who squeezes the world socially/politically only (guilds, cults, military, local disputes). "
            "Never describe player skill growth or delayed compounding."
        ),
        "examples": [
            "local disputes",
            "guild control and harbor politics",
            "hidden cults under coastal guilds",
        ],
        "ban_growth_slogans": True,
        "max_len": 90,
    },
    "npc_stat_scaling": {
        "kind": "short_phrase",
        "intent_keys": ["difficulty", "edge"],
        "forbidden": (
            "NPC rank pressure only relative to the player (mostly weaker, near player, elite-heavy, relative ranks). "
            "Never paste level-delay timers or player skill compounding rules."
        ),
        "examples": ["relative ranks", "mostly weaker", "near player", "elite-heavy later"],
        "ban_growth_slogans": True,
        "ban_growth_timers": True,
    },
    "npc_skill_frequency": {
        "kind": "short_phrase",
        "intent_keys": ["difficulty"],
        "forbidden": (
            "How often NPCs have special skills only (rare specialists, many trained NPCs). "
            "Not player skill growth or ability slogans."
        ),
        "examples": ["some trained NPCs", "rare specialists", "occasional trainers"],
        "ban_growth_slogans": True,
    },
    "rank_scale": {
        "kind": "short_phrase",
        "intent_keys": ["isekai", "genre"],
        "forbidden": "Rank ladder string only (e.g. F,E,D,C,B,A,S,SS,SSS). Never paste ability prose or growth slogans.",
        "examples": ["F,E,D,C,B,A,S,SS,SSS", "D,C,B,A,S"],
        "ban_growth_slogans": True,
        "max_len": 60,
    },
    "backstory_mode": {
        "kind": "short_phrase",
        "intent_keys": ["isekai", "portal_or_rebirth", "genre"],
        "forbidden": "Backstory mode only (known, reincarnated, transmigrated, etc).",
    },
    "memory_policy": {
        "kind": "short_phrase",
        "intent_keys": ["isekai", "portal_or_rebirth", "genre"],
        "forbidden": "Memory policy only.",
    },
    "character_backstory": {
        "kind": "prose",
        "intent_keys": ["isekai", "portal_or_rebirth", "genre", "power_fantasy", "keywords", "tone"],
        "forbidden": (
            "Concrete third-person character history only; not a setup slogan, skill dump, or power-fantasy essay. "
            "If backstory_mode is transmigrated: MUST cover (1) life before transport, (2) how they were transported, "
            "(3) start at the moment of arrival or just before — not a full native plot already living in the new world. "
            "Do not invent disgraced nobles / festival guests / local quest hooks as if they were always from this world. "
            "Do not paste skill names, compounding math, or Guest Right-style ability blurbs into the backstory."
        ),
    },
    "hair": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords", "tone"],
        "forbidden": "Hair only: length, color, style. Not face, clothes, or backstory.",
        "examples": [
            "short brown hair",
            "long black braid",
            "messy copper curls",
            "cropped black hair",
            "shoulder-length ash blonde",
            "tight cornrows",
            "bald with stubble shadow",
            "white undercut",
        ],
    },
    "facial_features": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords", "tone", "power_fantasy"],
        "forbidden": (
            "Face only for portraits: eyes, freckles, scars, jaw, brows, marks. "
            "Not hair (use hair field), not clothes, not personality essays."
        ),
        "examples": [
            "green eyes, light freckles, soft jaw",
            "dark brown eyes, thin scar on left cheek",
            "amber eyes, high cheekbones, crooked smile",
            "blue-grey eyes, deep-set, narrow nose",
            "black eyes, round face, small burn near temple",
        ],
    },
    "appearance": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "power_fantasy", "keywords", "tone", "isekai"],
        "forbidden": (
            "Clothing / worn gear only. Prefer zone:item (torso/feet…). "
            "Put hair in hair field and face details in facial_features. "
            "Not a backstory essay or skill slogans."
        ),
        "examples": [
            "torso: travel-stained coat; feet: dusty boots; waist: rope coil",
            "torso: plain work tunic; hands: work gloves; feet: practical boots",
            "torso: frayed cloak; legs: patched trousers; bag: worn satchel",
            "torso: secondhand hoodie; feet: scuffed sneakers; bag: messenger bag",
        ],
    },
    "starter_equipment": {
        "kind": "list_custom",
        "intent_keys": [
            "genre",
            "power_fantasy",
            "keywords",
            "tone",
            "difficulty",
            "isekai",
            "portal_or_rebirth",
        ],
        "forbidden": (
            "Comma-separated items the player already owns the moment Start is pressed. "
            "Must match origin + world vibe + arrival: pure isekai = thin clothes/pockets only; "
            "reincarnated/transmigrated local life = modest this-life kit only; "
            "never modern Earth maintenance kits in low-tech fantasy without localizing origin. "
            "No free shields/swords/armor/god gifts at isekai arrival — those come AFTER Start. "
            "No legendaries. Prefer thin ordinary kits over packing every useful item."
        ),
        "examples": [
            "patched work vest, work gloves, worn boots, copper coins",
            "travel cloak, empty satchel, wooden charm, water skin",
            "plain tunic, scuffed boots, coin purse, heel of bread",
        ],
    },
    "player_name": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords"],
        "forbidden": "A playable name only.",
    },
    "player_public_name": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords"],
        "forbidden": "Alias only; blank is normal.",
    },
    "player_title": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "power_fantasy"],
        "forbidden": "Title only; blank is normal.",
    },
    "player_age": {
        "kind": "short_phrase",
        "intent_keys": ["isekai", "portal_or_rebirth"],
        "forbidden": "Age only.",
    },
    "player_sex": {
        "kind": "short_phrase",
        "intent_keys": [],
        "forbidden": (
            "Sex/body category only. Prefer male or female for ordinary humanoids. "
            "Blank is valid. Sexless/constructed or varies-by-form only when the world/body clearly supports it."
        ),
        "examples": ["female", "male", ""],
    },
    "previous_life_age": {
        "kind": "short_phrase",
        "intent_keys": ["isekai", "portal_or_rebirth"],
        "forbidden": "Former-life age only when relevant.",
    },
    "previous_life_sex": {
        "kind": "short_phrase",
        "intent_keys": ["isekai", "portal_or_rebirth"],
        "forbidden": (
            "Former-life sex only when relevant. Prefer male/female for ordinary former lives; "
            "exotic categories only when the former body is clearly nonstandard."
        ),
        "examples": ["female", "male", ""],
    },
    "start_location": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords", "isekai"],
        "forbidden": "Place name only.",
    },
    "special_ability_origin": {
        "kind": "enum",
        "allowed_values": ["none", "acquired", "innate", "both"],
        "intent_keys": ["power_fantasy", "isekai"],
        "forbidden": "Return only none, acquired, innate, or both.",
    },
    "special_abilities": {
        "kind": "abilities",
        "intent_keys": ["power_fantasy", "keywords", "genre", "isekai"],
        "forbidden": "Ability list only; respect start_power and growth from intent.",
    },
}


# ---------------------------------------------------------------------------
# Phase tree — depends_on defines load order
# ---------------------------------------------------------------------------

SETUP_COMPOSER_PHASES: list[dict[str, Any]] = [
    {
        "id": "intent",
        "label": "Intent",
        "fields": [],
        "depends_on": [],
    },
    {
        "id": "world_frame",
        "label": "World frame",
        "fields": ["world_style", "tone", "tech_level", "magic_level", "economy", "custom_style"],
        "depends_on": ["intent"],
    },
    {
        "id": "world_peoples",
        "label": "Peoples & magic access",
        "fields": [
            "world_races",
            "race_magic_enabled",
            "race_magic_rarity",
            "race_magic_rules",
            "race_ability_rules",
        ],
        "depends_on": ["world_frame"],
    },
    {
        "id": "difficulty_edge",
        "label": "Difficulty & edge",
        "fields": [
            "difficulty",
            "death_rules",
            "narration_detail",
            "loot_rarity",
            "inventory_weight_limit",
            "inventory_slot_limit",
            "inventory_rules",
        ],
        "depends_on": ["world_frame"],
    },
    {
        "id": "progression",
        "label": "Progression fantasy",
        "fields": [
            "leveling_system",
            "xp_growth_speed",
            "game_system",
            "system_style",
            "proficiency_system",
            "skill_levels_enabled",
            "skill_style",
            "proficiency_access",
            "new_skill_frequency",
            "skill_growth_speed",
            "proficiency_growth_speed",
            "custom_skills",
        ],
        "depends_on": ["difficulty_edge", "world_frame"],
    },
    {
        "id": "people",
        "label": "Social world",
        "fields": [
            "npc_density",
            "quest_style",
            "faction_pressure",
            "npc_stat_scaling",
            "npc_skill_frequency",
            "rank_scale",
        ],
        "depends_on": ["world_frame", "difficulty_edge"],
    },
    {
        "id": "identity",
        "label": "Character identity",
        "fields": [
            "backstory_mode",
            "memory_policy",
            "character_backstory",
            "hair",
            "facial_features",
            "appearance",
            "starter_equipment",
            "player_name",
            "player_public_name",
            "player_title",
            "player_age",
            "player_sex",
            "previous_life_age",
            "previous_life_sex",
            "start_location",
        ],
        "depends_on": ["world_frame", "world_peoples"],
    },
    {
        "id": "powers",
        "label": "Powers",
        "fields": ["special_ability_origin", "special_abilities"],
        "depends_on": ["identity", "progression", "world_peoples"],
    },
]


def _topo_phases() -> list[dict[str, Any]]:
    by_id = {p["id"]: p for p in SETUP_COMPOSER_PHASES}
    declaration = [p["id"] for p in SETUP_COMPOSER_PHASES]
    ordered: list[dict[str, Any]] = []
    remaining = set(by_id)
    while remaining:
        ready = [
            pid
            for pid in declaration
            if pid in remaining
            and all(dep not in remaining for dep in (by_id[pid].get("depends_on") or []))
        ]
        if not ready:
            # Cycle guard — append rest in declaration order
            ready = [pid for pid in declaration if pid in remaining]
        for pid in ready:
            ordered.append(by_id[pid])
            remaining.discard(pid)
    return ordered


def composer_field_order() -> list[str]:
    """Flatten phases into the single load order for Randomize walks."""
    seen: set[str] = set()
    order: list[str] = []
    for phase in _topo_phases():
        for field in phase.get("fields") or []:
            if field in FIELD_CONTRACTS and field not in seen:
                order.append(field)
                seen.add(field)
    # Any contract fields missing from phases still append (safety)
    for field in FIELD_CONTRACTS:
        if field not in seen:
            order.append(field)
            seen.add(field)
    return order


COMPOSER_FIELD_ORDER = composer_field_order()


def field_contract(field: str) -> dict[str, Any]:
    return dict(FIELD_CONTRACTS.get(field) or {"kind": "short_phrase", "intent_keys": [], "forbidden": ""})


def intent_slice_for_field(intent: dict[str, Any] | None, field: str) -> dict[str, Any]:
    """Only pass intent keys this field is allowed to read."""
    if not intent or not isinstance(intent, dict):
        return {}
    keys = field_contract(field).get("intent_keys") or []
    return {k: intent[k] for k in keys if k in intent and intent[k] not in (None, "", [], {})}


def composer_tree_public() -> dict[str, Any]:
    return {
        "phases": [
            {
                "id": p["id"],
                "label": p["label"],
                "fields": list(p.get("fields") or []),
                "depends_on": list(p.get("depends_on") or []),
            }
            for p in _topo_phases()
        ],
        "field_order": list(COMPOSER_FIELD_ORDER),
        "contracts": {name: field_contract(name) for name in COMPOSER_FIELD_ORDER},
    }


# ---------------------------------------------------------------------------
# Intent defaults + keyword overrides (deterministic, always run)
# ---------------------------------------------------------------------------

DEFAULT_INTENT: dict[str, Any] = {
    "genre": "",
    "isekai": False,
    "portal_or_rebirth": "ambiguous",
    "difficulty": "normal",
    "edge": "",
    "power_fantasy": {
        "start_power": "ordinary",
        "growth": "steady",
        "system_ui": False,
        "skill_summary": "",
    },
    "tone": "",
    "keywords": [],
    "adapter_hint": "default",
    "dm_stance": "fair pressure, player agency, no chosen-one autopilot",
    "style_notes": "",
    "raw_idea": "",
}


def empty_intent(idea: str = "") -> dict[str, Any]:
    plan = dict(DEFAULT_INTENT)
    plan["power_fantasy"] = dict(DEFAULT_INTENT["power_fantasy"])
    plan["keywords"] = []
    plan["raw_idea"] = str(idea or "").strip()[:400]
    return plan


def _normalize_difficulty(value: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "normal"
    if "brutal" in text or "deadly" in text:
        return "brutal"
    if re.search(r"\bhard\b", text) or "difficult" in text:
        return "hard"
    if "easy-medium" in text or "easy medium" in text or "medium-easy" in text:
        return "normal"  # form enum: map mid to normal; edge notes keep medium feel
    if re.search(r"\beasy\b", text) or "beginner" in text:
        return "easy"
    if "medium" in text or "moderate" in text or "normal" in text:
        return "normal"
    return "normal"


def apply_keyword_intent(idea: str, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic keyword pass — runs before/after LLM intent compile."""
    out = empty_intent(idea) if plan is None else {**empty_intent(idea), **plan}
    if not isinstance(out.get("power_fantasy"), dict):
        out["power_fantasy"] = dict(DEFAULT_INTENT["power_fantasy"])
    else:
        out["power_fantasy"] = {**DEFAULT_INTENT["power_fantasy"], **out["power_fantasy"]}
    text = str(idea or "").strip().lower()
    if not text:
        return out
    out["raw_idea"] = str(idea or "").strip()[:400]

    # Isekai / portal / summon / truck-kun (broad markers — not only "summoned to")
    if any(
        k in text
        for k in (
            "isekai",
            "another world",
            "other world",
            "transmigrat",
            "reincarnat",
            "summoned",
            "summoning",
            "transported to",
            "transported into",
            "truck-kun",
            "truck accident",
            "woke in another",
            "woke up in another",
            "into a fantasy",
        )
    ):
        out["isekai"] = True
        out["adapter_hint"] = "isekai_rpg"
        if ("reincarn" in text or "reborn" in text) and any(
            m in text for m in ("grew up", "child", "years", "village", "childhood", "same world")
        ):
            out["portal_or_rebirth"] = "same_world_rebirth"
        elif any(m in text for m in ("into the body", "into a body", "possess", "body of a", "this body")):
            out["portal_or_rebirth"] = "body_transmigration"
        elif any(m in text for m in ("summon", "ritual", "portal", "truck", "transported", "desk job", "died and woke")):
            out["portal_or_rebirth"] = "other_world"
        elif "reincarn" in text or "reborn" in text:
            out["portal_or_rebirth"] = "same_world_rebirth" if "same world" in text else "other_world"
        elif "transmigrat" in text:
            out["portal_or_rebirth"] = "other_world"
        if not out.get("genre"):
            out["genre"] = "isekai dark fantasy" if "dark" in text else "isekai fantasy"

    # System UI
    if any(k in text for k in ("system", "status window", "skill ui", "blue window", "game system", "status panel", "level up")):
        out["power_fantasy"]["system_ui"] = True
        if out.get("adapter_hint") in ("", "default"):
            out["adapter_hint"] = "system_rpg"

    # Power fantasy growth (OP MC preset steers here)
    if any(
        k in text
        for k in (
            "compounding",
            "compounds",
            "compound",
            "exponential",
            "snowball",
            "stacking growth",
            "op later",
            "op mc",
            "op-mc",
            "late-game op",
            "late game op",
        )
    ):
        out["power_fantasy"]["growth"] = "compounding"
    if any(
        k in text
        for k in (
            "near useless",
            "useless skill",
            "weak start",
            "starts weak",
            "powerless",
            "bottom tier",
            "rank f",
            "ordinary start",
            "start ordinary",
            "op mc",
            "op-mc",
        )
    ):
        out["power_fantasy"]["start_power"] = "near_useless"
    elif any(k in text for k in ("overpowered", "already strong", "starts strong")):
        out["power_fantasy"]["start_power"] = "strong"
    # Isekai + compounding implies weak start + system UI unless the idea says strong.
    if out.get("isekai") and out["power_fantasy"].get("growth") == "compounding":
        if out["power_fantasy"].get("start_power") == "ordinary":
            out["power_fantasy"]["start_power"] = "near_useless"
        out["power_fantasy"]["system_ui"] = True

    # Difficulty
    if "easy-medium" in text or "easy medium" in text:
        out["difficulty"] = "normal"
        out["edge"] = out.get("edge") or "slightly forgiving early pressure"
    elif re.search(r"\beasy\b", text):
        out["difficulty"] = "easy"
    elif re.search(r"\bhard\b", text) or "brutal" in text:
        out["difficulty"] = "brutal" if "brutal" in text else "hard"

    # Edge / injuries
    if any(k in text for k in ("lasting injur", "scarce loot", "permadeath", "hard edge", "harsh")):
        edge_bits = []
        if "injur" in text:
            edge_bits.append("lasting injuries")
        if "scarce" in text or "loot" in text:
            edge_bits.append("scarce rare loot")
        if "permadeath" in text:
            edge_bits.append("permadeath threat")
        if edge_bits:
            out["edge"] = ", ".join(edge_bits)

    # Tone snippets
    if "curious" in text or "hopeful" in text or "tense" in text:
        bits = [w for w in ("curious", "tense", "hopeful") if w in text]
        if bits and not out.get("tone"):
            out["tone"] = ", ".join(bits)

    # Keyword harvest (simple content nouns)
    keyword_hits = []
    for token in (
        "library",
        "fragments",
        "veil",
        "ruins",
        "academy",
        "dungeon",
        "sect",
        "guild",
        "cultivation",
        "system",
        "skill",
        "status",
    ):
        if token in text and token not in keyword_hits:
            keyword_hits.append(token)
    if keyword_hits:
        existing = [str(k) for k in (out.get("keywords") or []) if k]
        merged = existing[:]
        for k in keyword_hits:
            if k not in merged:
                merged.append(k)
        out["keywords"] = merged[:12]

    # Skill summary from idea (OP MC / legacy one-skill wording)
    if any(
        m in text
        for m in (
            "one weak skill",
            "single skill",
            "one skill",
            "op mc",
            "op-mc",
            "snowball",
            "compounding",
        )
    ):
        out["power_fantasy"]["skill_summary"] = out["power_fantasy"].get("skill_summary") or (
            "one weak OP-MC seed power that compounds toward late power; more powers may unlock later"
        )

    out["difficulty"] = _normalize_difficulty(out.get("difficulty") or "normal")
    if out.get("isekai") and not out.get("dm_stance"):
        out["dm_stance"] = "fair pressure, player agency, isekai flavor without auto-win or chosen-one autopilot"
    elif not out.get("dm_stance"):
        out["dm_stance"] = DEFAULT_INTENT["dm_stance"]

    return out


def merge_intent_plans(base: dict[str, Any], llm_plan: dict[str, Any] | None) -> dict[str, Any]:
    """Keyword plan is the floor; LLM may refine but not erase hard keyword flags."""
    out = apply_keyword_intent(str(base.get("raw_idea") or ""), base)
    if not llm_plan or not isinstance(llm_plan, dict):
        return out
    for key in ("genre", "portal_or_rebirth", "tone", "edge", "adapter_hint", "dm_stance", "style_notes"):
        val = llm_plan.get(key)
        if isinstance(val, str) and val.strip():
            # Keyword isekai adapter wins over LLM genre drift (e.g. grimdark).
            if key == "adapter_hint" and out.get("isekai"):
                continue
            if key == "adapter_hint" and out.get("adapter_hint") not in ("", "default", None) and val.strip().lower() in (
                "default",
                "",
            ):
                continue
            out[key] = val.strip()[:200]
    if "isekai" in llm_plan:
        out["isekai"] = bool(llm_plan["isekai"]) or bool(out.get("isekai"))
    # Re-assert adapter after isekai merge
    if out.get("isekai") and out.get("adapter_hint") in ("", "default", "grimdark", None):
        out["adapter_hint"] = "isekai_rpg"
    elif out.get("isekai"):
        out["adapter_hint"] = "isekai_rpg"
    if llm_plan.get("difficulty"):
        out["difficulty"] = _normalize_difficulty(str(llm_plan["difficulty"]))
    pf = llm_plan.get("power_fantasy")
    if isinstance(pf, dict):
        merged_pf = dict(out.get("power_fantasy") or {})
        for k, v in pf.items():
            if v is None or v == "":
                continue
            if k == "system_ui":
                merged_pf[k] = bool(v) or bool(merged_pf.get("system_ui"))
            elif k == "growth" and merged_pf.get("growth") == "compounding":
                continue  # keyword compounding wins
            elif k == "start_power" and merged_pf.get("start_power") == "near_useless":
                continue
            else:
                merged_pf[k] = v if not isinstance(v, str) else v.strip()[:240]
        out["power_fantasy"] = merged_pf
    kws = llm_plan.get("keywords")
    if isinstance(kws, list):
        existing = [str(k) for k in (out.get("keywords") or []) if k]
        for k in kws:
            s = str(k).strip()[:40]
            if s and s.lower() not in {e.lower() for e in existing}:
                existing.append(s)
        out["keywords"] = existing[:12]
    return out


def adapter_hint_systemish(intent: dict[str, Any] | None) -> bool:
    hint = str((intent or {}).get("adapter_hint") or "").lower()
    return hint in {"system_rpg", "isekai_rpg"}


def intent_to_field_overrides(intent: dict[str, Any], locked: set[str] | None = None) -> dict[str, Any]:
    """Deterministic setup field values derived from intent (applied before LLM walk)."""
    locked = locked or set()
    fields: dict[str, Any] = {}
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    growth = str(pf.get("growth") or "steady").lower()
    start_power = str(pf.get("start_power") or "ordinary").lower()
    system_ui = bool(pf.get("system_ui"))
    isekai = bool(intent.get("isekai"))
    difficulty = _normalize_difficulty(intent.get("difficulty") or "normal")

    def set_if_free(name: str, value: Any) -> None:
        if name not in locked:
            fields[name] = value

    set_if_free("difficulty", difficulty)

    if system_ui or isekai:
        set_if_free("game_system", True)
        if isekai:
            set_if_free("system_style", "subtle blue-window system")
            set_if_free("leveling_system", True)
            set_if_free("skill_levels_enabled", True)

    if growth == "compounding":
        set_if_free("skill_growth_speed", "very fast")
        set_if_free("proficiency_growth_speed", "fast")
        set_if_free("xp_growth_speed", "fast")
        # Opening is thin; later play may unlock more powers/passives (not a permanent one-skill ban)
        set_if_free("new_skill_frequency", "normal")
        set_if_free("skill_levels_enabled", True)
        set_if_free("proficiency_system", True)
        set_if_free("skill_style", "training-heavy")
        # Must open ability origin so special_abilities randomize is not skipped (default UI is None)
        set_if_free("special_ability_origin", "acquired")
        # Structural skeleton only — LLM expands domain + concrete math during custom_skills roll.
        # Never hardcode Observation/weather domains here.
        set_if_free(
            "custom_skills",
            "OP_MC_FRAME: start with one weak seed power (domain chosen later; never default weather/observation); "
            "near-useless rank F / level 1; Growth Math must compound toward late OP (ladder through S/SS/SSS, "
            "risk mult, soft caps, breakthroughs, rank→bonus, late multipliers); passives allowed as always-on "
            "ranks; more powers may unlock later via play — only the opening kit is thin; track via subtle system "
            "UI when on, else DM notes; no free second combat toolkit at Start",
        )
        if not str(pf.get("skill_summary") or "").strip():
            # Stash on intent for UI / later ability alignment (not a form field)
            intent.setdefault("power_fantasy", {})
            if isinstance(intent.get("power_fantasy"), dict):
                intent["power_fantasy"]["skill_summary"] = (
                    "OP MC seed: weak start, calculable snowball to late OP, passives OK, more powers later"
                )

    if start_power in ("near_useless", "weak"):
        set_if_free("special_ability_origin", "acquired")
        # abilities filled later by walk; origin acquired + locked weak seed
        if "custom_skills" not in fields and "custom_skills" not in locked:
            set_if_free(
                "custom_skills",
                "OP_MC_FRAME: one weak seed power at start (domain varies); compounds toward OP with Growth Math; "
                "passives OK; additional powers may unlock later; no broad toolkit at Start",
            )

    # System / isekai runs get optional mechanical friction on the Checks tab.
    if system_ui or isekai or adapter_hint_systemish(intent):
        set_if_free("dice_checks_enabled", True)
        set_if_free("check_difficulty", difficulty if difficulty in ("easy", "normal", "hard", "brutal") else "normal")
        set_if_free("unskilled_mishaps", True)
        set_if_free("auto_check_on_risky_actions", True)
        set_if_free("show_rolls_in_ui", True)
        if difficulty in ("hard", "brutal"):
            set_if_free("event_check_frequency", "frequent")
            set_if_free("encounter_check_frequency", "normal")
        elif difficulty == "easy":
            set_if_free("event_check_frequency", "rare")
            set_if_free("encounter_check_frequency", "rare")
        else:
            set_if_free("event_check_frequency", "normal")
            set_if_free("encounter_check_frequency", "normal")

    if isekai:
        portal = str(intent.get("portal_or_rebirth") or "other_world")
        if portal == "same_world_rebirth":
            set_if_free("backstory_mode", "reincarnated")
            # Childhood rebirth usually starts with fragments, not perfect recall
            set_if_free("memory_policy", "former life fragments")
        elif portal == "body_transmigration":
            set_if_free("backstory_mode", "transmigrated")
            set_if_free("memory_policy", "former life fragments")
        else:
            set_if_free("backstory_mode", "transmigrated")
            set_if_free("memory_policy", "remembers former life")
        # Structural seeds — never skill slogans (growth lives in custom_skills).
        set_if_free("quest_style", "job board and personal mysteries")
        set_if_free("faction_pressure", "local disputes under guild pressure")
        set_if_free("economy", "scarce coin markets")
        set_if_free("npc_stat_scaling", "mostly weaker early, relative ranks later")
        set_if_free("npc_skill_frequency", "rare specialists and occasional trainers")
        set_if_free("world_races", "human")
        set_if_free("rank_scale", "F,E,D,C,B,A,S,SS,SSS")
        if growth == "compounding":
            set_if_free("skill_style", "training-heavy")
        # world_style: only a setting phrase, never a slogan title from genre
        genre = str(intent.get("genre") or "").strip()
        if genre and "world_style" not in locked:
            gl = genre.lower()
            if (
                len(genre) <= 48
                and "fair edge" not in gl
                and "op mc" not in gl
                and not gl.endswith(" edge")
            ):
                set_if_free("world_style", genre[:80])
            else:
                set_if_free("world_style", "isekai fantasy compound")

    edge = str(intent.get("edge") or "").lower()
    if "injur" in edge:
        set_if_free("death_rules", "lasting injuries")
    if "permadeath" in edge:
        set_if_free("death_rules", "permadeath threat")
    if "scarce" in edge or "loot" in edge:
        set_if_free("loot_rarity", "scarce mundane")

    genre = str(intent.get("genre") or "").strip()
    if genre and "world_style" not in locked and "world_style" not in fields:
        gl = genre.lower()
        if (
            len(genre) <= 48
            and "fair edge" not in gl
            and "op mc" not in gl
            and not gl.endswith(" edge")
            and any(m in gl for m in ("fantasy", "isekai", "kingdom", "sect", "cyber", "city", "harbor", "frontier", "cultivat"))
        ):
            fields["world_style"] = genre[:80]
        elif isekai:
            fields["world_style"] = "isekai fantasy compound"

    tone = str(intent.get("tone") or "").strip()
    if tone and "tone" not in locked:
        fields["tone"] = tone[:100]

    # Soft style note for custom_style seed
    style_bits = []
    if isekai:
        style_bits.append("Isekai RPG lean: status/skill progression may be diegetic when the system UI is on.")
    if system_ui:
        style_bits.append("A readable game-system window can appear in-world without breaking immersion.")
    if growth == "compounding":
        style_bits.append("Power fantasy: start weak, growth compounds through play, never auto-win.")
    dm = str(intent.get("dm_stance") or "").strip()
    if dm:
        style_bits.append(f"DM stance: {dm}")
    notes = str(intent.get("style_notes") or "").strip()
    if notes:
        style_bits.append(notes)
    if style_bits and "custom_style" not in locked:
        fields["custom_style"] = " ".join(style_bits)[:800]

    return fields


def session_theme_from_intent(intent: dict[str, Any] | None) -> dict[str, Any]:
    """Durable playthrough bias stored in playthrough_options.session_theme."""
    if not intent or not isinstance(intent, dict):
        return {}
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    return {
        "adapter_hint": str(intent.get("adapter_hint") or "default")[:80],
        "genre": str(intent.get("genre") or "")[:120],
        "isekai": bool(intent.get("isekai")),
        "dm_stance": str(intent.get("dm_stance") or DEFAULT_INTENT["dm_stance"])[:240],
        "power_fantasy": {
            "start_power": str(pf.get("start_power") or "ordinary")[:80],
            "growth": str(pf.get("growth") or "steady")[:80],
            "system_ui": bool(pf.get("system_ui")),
            "skill_summary": str(pf.get("skill_summary") or "")[:200],
        },
        "tone": str(intent.get("tone") or "")[:120],
        "edge": str(intent.get("edge") or "")[:200],
        "keywords": [str(k)[:40] for k in (intent.get("keywords") or []) if k][:12],
        "style_notes": str(intent.get("style_notes") or intent.get("raw_idea") or "")[:400],
        "theme_model": str(intent.get("theme_model") or "")[:120],  # optional LoRA/model override name
    }


def theme_prompt_block(
    session_theme: dict[str, Any] | None,
    playthrough_options: dict[str, Any] | None = None,
) -> str:
    """Secondary system-prompt injection: genre lean, DM core first."""
    if not session_theme or not isinstance(session_theme, dict):
        return ""
    if not any(session_theme.get(k) for k in ("genre", "adapter_hint", "isekai", "style_notes", "power_fantasy", "dm_stance", "edge")):
        return ""
    opts = playthrough_options if isinstance(playthrough_options, dict) else {}
    pf = session_theme.get("power_fantasy") if isinstance(session_theme.get("power_fantasy"), dict) else {}
    lines = [
        "Session theme bias (secondary to DM fairness, world_state, and clear prose):",
        f"- Keep DM mindset: {session_theme.get('dm_stance') or DEFAULT_INTENT['dm_stance']}",
        "- Player agency and fair consequences always beat genre pastiche.",
        "- Do not abandon mechanics_context, entity codes, or inventory truth for theme flavor.",
        "- Theme must not invert word order, force rare synonyms, or make sentences hard to scan. "
        "Clear subject–verb–object prose first; flavor second.",
    ]
    genre = str(session_theme.get("genre") or "").strip()
    adapter = str(session_theme.get("adapter_hint") or "").strip()
    if genre or adapter:
        lean = genre or adapter
        lines.append(f"- Genre lean: {lean}")
    if session_theme.get("isekai") or adapter == "isekai_rpg":
        lines.append(
            "- Isekai RPG texture is welcome (new-world disorientation, skill/status framing when game_system is true) "
            "but never force chosen-one destiny or auto-win power spikes."
        )
    if pf:
        start = pf.get("start_power") or "ordinary"
        growth = pf.get("growth") or "steady"
        lines.append(f"- Power fantasy constraints: start_power={start}, growth={growth}.")
        if pf.get("system_ui") or opts.get("game_system"):
            lines.append(
                "- System UI may appear diegetically when playthrough_options.game_system is true; "
                "keep windows short (2–6 lines), readable in-world, never a rules dump."
            )
        skill = str(pf.get("skill_summary") or "").strip()
        if skill:
            lines.append(f"- Skill fantasy note: {skill}")
        if str(start).lower() in ("near_useless", "weak"):
            lines.append(
                "- The player starts weak: do not grant power spikes, free victories, or a toolbox of starting skills."
            )
    difficulty = str(opts.get("difficulty") or "").strip().lower() or "normal"
    edge = str(session_theme.get("edge") or opts.get("edge") or "").strip()
    stakes = _stakes_line(difficulty, edge)
    if stakes:
        lines.append(f"- Stakes: {stakes}")
    tone = str(session_theme.get("tone") or "").strip()
    if tone:
        lines.append(f"- Tone lean: {tone}")
    if edge:
        lines.append(f"- Edge: {edge}")
    notes = str(session_theme.get("style_notes") or "").strip()
    if notes:
        # Cap hard — long style dumps from Randomize ideas used to warp local-model diction.
        lines.append(
            f"- Style notes (light touch only, never override clear prose): {notes[:120]}"
        )
    # Collect over-indexed setup words so the model deliberately under-uses them.
    slogan_bits: list[str] = []
    for raw in (genre, tone, edge, notes, str(pf.get("skill_summary") or "")):
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", raw or ""):
            t = token.lower()
            if t in {
                "with",
                "from",
                "that",
                "this",
                "have",
                "will",
                "your",
                "into",
                "when",
                "only",
                "more",
                "than",
                "over",
                "under",
                "through",
                "about",
                "after",
                "before",
                "world",
                "player",
                "story",
                "game",
            }:
                continue
            slogan_bits.append(t)
    # Keep unique, order-stable, short list
    seen_s: set[str] = set()
    slogans: list[str] = []
    for t in slogan_bits:
        if t in seen_s:
            continue
        seen_s.add(t)
        slogans.append(t)
        if len(slogans) >= 10:
            break
    if slogans:
        lines.append(
            "- Do not re-use these setup slogan words every turn (theme constraints, not catchphrases): "
            + ", ".join(slogans)
            + ". Invent fresh scene-specific wording instead."
        )
    lines.append(
        "- Narrator personality: dry grounded DM — concrete, lightly wry, never preachy; "
        "do not recite genre labels or power-fantasy slogans as prose filler."
    )
    return "\n".join(lines)


def _stakes_line(difficulty: str, edge: str) -> str:
    d = (difficulty or "normal").lower()
    edge_l = (edge or "").lower()
    base = {
        "easy": "Local pressure, forgiving early mistakes; danger exists but rarely deletes progress.",
        "normal": "Concrete local stakes with fair costs; curiosity and caution both matter.",
        "hard": "Sharp local danger, scarce help, and mistakes leave marks.",
        "brutal": "High early risk, scarce safety nets, lasting consequences when the player presses hard.",
    }.get(d, "Concrete local stakes with fair costs.")
    bits = [base]
    if "injur" in edge_l:
        bits.append("Injuries can linger.")
    if "scarce" in edge_l or "loot" in edge_l:
        bits.append("Useful loot stays uncommon.")
    if "permadeath" in edge_l:
        bits.append("Death is a real threat, not a slap on the wrist.")
    return " ".join(bits)


def opening_feel_prompt_block(
    session_theme: dict[str, Any] | None = None,
    playthrough_options: dict[str, Any] | None = None,
) -> str:
    """Opening-only instructions: system window once, weak skill seed, stakes match difficulty."""
    opts = playthrough_options if isinstance(playthrough_options, dict) else {}
    theme = session_theme if isinstance(session_theme, dict) else {}
    pf = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}
    if not pf and isinstance(opts.get("session_theme"), dict):
        theme = opts.get("session_theme") or {}
        pf = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}

    game_system = bool(opts.get("game_system"))
    system_style = str(opts.get("system_style") or "subtle blue-window system").strip()
    system_ui = bool(pf.get("system_ui")) or game_system
    start_power = str(pf.get("start_power") or "ordinary").lower()
    growth = str(pf.get("growth") or "steady").lower()
    skill_summary = str(pf.get("skill_summary") or "").strip()
    custom_skills = str(opts.get("custom_skills") or "").strip()
    difficulty = str(opts.get("difficulty") or "normal").lower()
    isekai = bool(theme.get("isekai") or (str(theme.get("adapter_hint") or "") == "isekai_rpg"))

    lines = [
        "Opening scene feel (turn_kind=opening_scene only):",
        "- Establish an immediate, playable situation with 2–4 concrete hooks; do not choose for the player.",
        "- Keep the first scene local and personal before world-ending stakes.",
    ]
    stakes = _stakes_line(difficulty, str(theme.get("edge") or ""))
    if stakes:
        lines.append(f"- Match opening pressure to difficulty: {stakes}")
    if isekai:
        lines.append(
            "- Isekai texture welcome: mild new-world disorientation, practical first problems "
            "(language, work, shelter, local rules) — never chosen-one destiny."
        )
    if game_system and system_ui:
        lines.append(
            f"- Once only in this opening: show a short diegetic system window in the style of "
            f"'{system_style}' (status/skill glimpse, 2–6 lines). Embed it in narration as something the "
            "character perceives — not a meta rules essay. Do not spam windows every paragraph."
        )
    seed = weak_skill_seed_spec(opts, theme)
    if seed:
        lines.append(
            f"- Weak skill seed is already on the player sheet as '{seed['name']}' "
            f"(value {seed['value']}). Make it visible once in the opening "
            "(system window, internal recognition, or a tiny practical moment). "
            "It must feel nearly useless now; do not invent extra free starting skills."
        )
    elif start_power in ("near_useless", "weak") or growth == "compounding":
        lines.append(
            "- Power fantasy start: the player is weak. If custom_skills names a seed proficiency, "
            "hint it once; otherwise show emptiness of power, not a skill menu."
        )
        if skill_summary:
            lines.append(f"- Skill fantasy hint: {skill_summary[:160]}")
        if custom_skills:
            lines.append(f"- custom_skills context: {custom_skills[:200]}")
    lines.append(
        "- Do not invent a full starting skill list (speech/combat/stealth/etc.). "
        "Only the weak seed (if present) or custom_skills-named starts are allowed at opening."
    )
    return "\n".join(lines)


# Domains that models/fallbacks over-use. Never force these as the default seed.
OVERUSED_SEED_DOMAINS = frozenset(
    {
        "observation",
        "weather",
        "sandstorm",
        "storm sense",
        "storm",
        "ropework",
        "rope work",
        "rope",
        "knot",
        "knots",
        "knot-work",
        "knot work",
        "fabric",
        "thread",
        "thread sense",
        "sewing",
        "barter",
        "trade",
        "trade/barter",
        "haggle",
        "lie detection",
        "lie-detect",
        "lie sense",
        "footstep",
        "footsteps",
        "footwork",
        "quiet footwork",
        "tracking footprints",
        "track footprints",
        "footprints",
    }
)

def _seed(
    name: str,
    hint: str,
    *,
    tier: str = "simple",
    lane: str = "mundane",
    requires: str = "",
    compounds_to: str = "",
) -> dict[str, str]:
    """One weak-seed domain: obscure OK, but always playable at F and worth ranking up."""
    return {
        "name": name,
        "hint": hint,
        "tier": tier,  # simple | advanced
        "lane": lane,  # mundane|tool|weapon|support|summon|necro|arcane|hybrid|tech
        "requires": requires,  # tool/weapon/focus needed to express power
        "compounds_to": compounds_to,  # late-game fantasy payoff
    }


# Wide seed pool for weak/compounding starts — obscure, usable, both simple and advanced.
# F rank = nearly useless but *actionable*; high rank = wild payoff (never dead weight).
SEED_SKILL_DOMAIN_POOL: list[dict[str, str]] = [
    # ── Simple mundane labor / body ──────────────────────────────────────
    _seed("Hauling", "awkward loads ride better — fewer dropped crates", compounds_to="superhuman burden carry / siege logistics"),
    _seed("Digging", "shovel work in soft earth; slow trenches", requires="shovel or spade", compounds_to="tunnel craft / earth-shaping"),
    _seed("Scaffold Sense", "feel when a board or ladder is about to give", compounds_to="structural prophecy / collapse denial"),
    _seed("Breath Hold", "one extra lungful in smoke or water", compounds_to="void lung / deep-current survival"),
    _seed("Cold Tolerance", "slight edge against chill", compounds_to="frost skin / winter dominion"),
    _seed("Heat Tolerance", "last longer near forges or desert noon", compounds_to="cinder blood / forge walking"),
    _seed("Pain Metering", "rate how bad a wound is, not ignore it", lane="support", compounds_to="pain redirect / combat triage aura"),
    _seed("Load Balance", "stack carts so they tip less", compounds_to="perfect mass sense / anti-topple field"),
    _seed("Grip Oil", "hands stay sticky-dry on wet wood or steel", compounds_to="impossible cling / wall-run grips"),
    _seed("Sleep Debt", "nap 10 minutes that count as 30 — once a day", lane="support", compounds_to="battlefield micro-rest / party recovery pulse"),
    # ── Simple tools (need the tool) ─────────────────────────────────────
    _seed("Nail Sense", "know if a nail/peg will hold after one tap", lane="tool", requires="hammer + nail/peg", compounds_to="structure-binding strikes"),
    _seed("Whetstone Habit", "keep an edge dull-useful", lane="tool", requires="whetstone + blade", compounds_to="edge that cuts wards"),
    _seed("Glue Mix", "sticky repairs that fail under real stress at first", lane="tool", requires="adhesive kit", compounds_to="living sealant / bond magic"),
    _seed("Lamp Trimming", "oil lamps, wicks, draft — tiny practical edge", lane="tool", requires="oil lamp", compounds_to="soul-flame lamps / light as weapon"),
    _seed("Tin Patch", "hammer a thin patch over a leak or crack", lane="tool", requires="soft metal + mallet", compounds_to="instant plate-skin"),
    _seed("Clay Patch", "seal pots/cracks with wet clay until baked", lane="tool", requires="clay", compounds_to="earth-suture / golem putty"),
    _seed("Wire Twist", "twist soft wire into temporary fasteners", lane="tool", requires="soft wire", compounds_to="wire golem threads / snare nets"),
    _seed("Gear Click", "hear when a simple mechanism is misaligned", lane="tool", requires="clockwork or latch nearby", compounds_to="machine communion"),
    _seed("Rust Reading", "guess how long iron has been wet/ruined", lane="tool", compounds_to="rust command / iron plague"),
    _seed("Key Blank", "file a soft blank toward a simple lock's shape", lane="tool", requires="blank key + files", tier="simple", compounds_to="skeleton-key intuition / lock dominion"),
    _seed("Lens Polish", "clean a lens so smears stop lying to you", lane="tool", requires="glass lens or monocle", compounds_to="true-sight optics"),
    _seed("Mortar Pestle", "crush herbs/minerals into usable grit", lane="tool", requires="mortar & pestle", compounds_to="alchemy catalyst mastery"),
    _seed("Quill Steady", "write one clean line under stress", lane="tool", requires="quill/ink", compounds_to="living contract script / word-binding"),
    _seed("Bell Tone", "ring a small bell at a pitch that carries oddly far", lane="tool", requires="hand bell", compounds_to="ward-shatter chime / rally peal"),
    _seed("Mirror Flash", "angle a mirror for a one-second signal flash", lane="tool", requires="hand mirror", compounds_to="light-blade / soul reflection"),
    _seed("Candle Count", "burn time guess for one candle within a few minutes", lane="tool", requires="candle", compounds_to="time-dilating flame"),
    _seed("Needle Point", "push a needle through tough hide without snapping it", lane="tool", requires="needle", compounds_to="acupuncture seals / curse stitches"),
    _seed("Chisel Line", "cut one straight groove in soft stone or wood", lane="tool", requires="chisel", compounds_to="rune-cutting / earth-scribe"),
    # ── Field / travel ───────────────────────────────────────────────────
    _seed("Trail Mud", "read soft ground for recent traffic — incomplete", compounds_to="omni-track / path rewrite"),
    _seed("River Smell", "find water or damp air a little earlier", compounds_to="aquifer call / flood sense"),
    _seed("Camp Ash", "judge how old a cold fire is", compounds_to="ash divination / ember resurrection"),
    _seed("Star Slice", "one constellation useful for rough direction", compounds_to="star-path stepping"),
    _seed("Pack Order", "repack so the load rides quieter", compounds_to="dimensional pack logic"),
    _seed("Saddle Fit", "notice a bad mount strap before a fall", lane="tool", requires="saddle or harness", compounds_to="perfect mount bond"),
    _seed("Ferry Timing", "guess tide/current windows poorly at first", compounds_to="current throne / tide step"),
    _seed("Dust Sign", "see dust kicked far off", compounds_to="horizon radar"),
    _seed("Moss Side", "guess north from moss/lichen — often wrong at F", compounds_to="living compass / ley north"),
    _seed("Echo Vault", "clap once; rough sense of a cave's depth", compounds_to="sonar dominion / stone voice"),
    # ── Animals / food ───────────────────────────────────────────────────
    _seed("Herd Calm", "soothe one nervous animal briefly", compounds_to="beast legion command"),
    _seed("Bait Guess", "pick mediocre bait for fish/traps", compounds_to="lure that pulls spirits"),
    _seed("Spoilage Nose", "smell food going bad a day early", lane="support", compounds_to="decay clock / anti-rot field"),
    _seed("Herb Thumb", "common field herbs; often wrong species at F", lane="support", compounds_to="panacea botany"),
    _seed("Smoke Cure", "keep meat/smoke from total waste", lane="tool", requires="smoke rack or fire", compounds_to="preservation magic"),
    _seed("Beehive Distance", "hear/feel a hive before walking into it", compounds_to="swarm pact"),
    _seed("Bone Broth", "boil scraps into something that stops shakes", lane="support", requires="pot + fire", compounds_to="restorative feast alchemy"),
    _seed("Feather Read", "guess a bird's mood from posture", compounds_to="avian scout network"),
    # ── Social / urban (not lie-detect spam) ──────────────────────────────
    _seed("Queue Sense", "pick the faster line or less angry clerk", compounds_to="bureaucracy dominion"),
    _seed("Coin Ring", "tap-test cheap fakes — misses good forgeries", lane="tool", requires="coin to tap", compounds_to="true-value sight"),
    _seed("Door Knock", "read household mood from how a door is answered", compounds_to="threshold mastery"),
    _seed("Market Echo", "overhear price gossip; often outdated", compounds_to="market prophecy"),
    _seed("Name Catch", "retain one new name per scene reliably", compounds_to="true-name ledger"),
    _seed("Accent Mirror", "slight local pronunciation mimic — comic at F", compounds_to="perfect persona mask"),
    _seed("Favor Debt", "instinct for who still owes whom", compounds_to="debt chains as power"),
    _seed("Crowd Drift", "move with a throng without being shoved flat", compounds_to="mob current ride"),
    _seed("Toast Timing", "raise a cup at the socially correct second", lane="support", compounds_to="oath-binding toasts"),
    _seed("Seat Rank", "guess who outranks whom from seating alone", compounds_to="hierarchy rewrite presence"),
    # ── Perception niches ────────────────────────────────────────────────
    _seed("Ink Memory", "recall one short written line for a day", compounds_to="living library mind"),
    _seed("Echo Count", "guess room size from a clap or footfall", compounds_to="space-map pulse"),
    _seed("Lamp Glare", "recover sight a beat faster after bright light", compounds_to="flash immunity / solar glare strike"),
    _seed("Draft Feel", "sense air leaks, secret gaps, open flues", compounds_to="breath of hidden rooms"),
    _seed("Glass Ring", "tap glass/ceramic for cracks", lane="tool", requires="tap tool", compounds_to="shatter command"),
    _seed("Salt Taste", "detect brine, sweat, or cheap adulterants", compounds_to="blood-salt truth / purification"),
    _seed("Pulse Count", "count another person's pulse if you can touch a wrist", lane="support", requires="touch", compounds_to="heartbeat dominion / calm or panic"),
    # ── Support / healing (simple → advanced) ────────────────────────────
    _seed("Pressure Point", "slow a bleed with correct finger pressure", lane="support", tier="simple", compounds_to="meridian combat medicine"),
    _seed("Clean Cloth", "keep one bandage cleaner than it should be", lane="support", requires="cloth bandage", compounds_to="antiseptic aura / holy wrap"),
    _seed("Splint Stick", "bind a limb with sticks so it hurts less to move", lane="support", requires="splints + wrap", compounds_to="bone-knit field"),
    _seed("Triage Sort", "pick who needs help first in a mess of injured", lane="support", tier="simple", compounds_to="mass-casualty miracle triage"),
    _seed("Fever Cloth", "cool a fever with wet cloth + timing", lane="support", requires="water + cloth", compounds_to="plaguebreak touch"),
    _seed("Stitch Calm", "sew a shallow cut without fainting the patient", lane="support", requires="needle + thread", compounds_to="flesh-suture magic"),
    _seed("Antidote Guess", "pick a common counter for mild poison — often wrong", lane="support", tier="simple", compounds_to="universal antidote craft"),
    _seed("Rest Circle", "draw a quiet camp circle that helps allies sleep", lane="support", tier="simple", compounds_to="sanctuary dome"),
    _seed("Rally Word", "one short phrase that steadies a shaken ally", lane="support", tier="simple", compounds_to="battle-hymn dominion"),
    _seed("Shield Cover", "angle a shield so an ally takes less splash", lane="support", requires="shield", compounds_to="aegis projection"),
    _seed("Mana Sip", "share a thimble of stamina/mana with a touch — tiny at F", lane="support", tier="advanced", compounds_to="party resource lattice"),
    _seed("Life Thread", "feel if a downed body still has a life-thread", lane="support", tier="advanced", compounds_to="pull souls back from the brink"),
    _seed("Purge Touch", "nudge mild disease/curse residue off skin — unreliable", lane="support", tier="advanced", compounds_to="exorcist cleanse"),
    _seed("Chorus Heal", "hum a tone that eases aches in listeners nearby", lane="support", tier="advanced", requires="voice", compounds_to="cathedral restoration song"),
    _seed("Blood Seal", "press a drop of blood to seal a minor cut faster", lane="support", tier="advanced", requires="own blood + focus", compounds_to="blood-rite regeneration"),
    _seed("Ward Cradle", "hold a crude ward over a sleeping ally for minutes", lane="support", tier="advanced", compounds_to="fortress of rest"),
    # ── Weapon-specific (need that weapon class) ─────────────────────────
    _seed("Spear Line", "keep a spear point from wobbling on the thrust", lane="weapon", requires="spear/polearm", compounds_to="horizon pierce / formation spear arts"),
    _seed("Axe Nest", "set an axe head so it doesn't twist in the cut", lane="weapon", requires="axe", compounds_to="cleave that splits wards"),
    _seed("Bow Breath", "release on the exhale — groups shots tighter", lane="weapon", requires="bow", compounds_to="seeking shafts / sky-piercer"),
    _seed("Dagger Slip", "draw a dagger without snagging the sheath", lane="weapon", requires="dagger", compounds_to="shadow-cut / vein-scribe"),
    _seed("Hammer Beat", "find the sweet spot on a hammer face", lane="weapon", requires="warhammer/maul", compounds_to="shockwave blows"),
    _seed("Staff Circle", "spin a staff once without smacking yourself", lane="weapon", requires="staff", compounds_to="orbitting barrier staff"),
    _seed("Whip Crack", "make a whip pop without hitting yourself", lane="weapon", requires="whip", compounds_to="space-fold lash"),
    _seed("Chain Rattle", "control a short chain swing without self-wrap", lane="weapon", requires="chain weapon", compounds_to="living chain serpent"),
    _seed("Shield Bash Angle", "bash with the rim, not the face, on purpose", lane="weapon", requires="shield", compounds_to="meteor bash / wall break"),
    _seed("Sling Pocket", "seat a stone in a sling pouch correctly", lane="weapon", requires="sling", compounds_to="meteor stones"),
    _seed("Rapier Tip", "keep point-control on a light blade for one exchange", lane="weapon", requires="rapier/foil", compounds_to="needle of light"),
    _seed("Gun Oil", "keep a firearm from jamming once in wet weather", lane="weapon", requires="firearm + oil kit", tier="simple", compounds_to="bullet-curving marksmanship"),
    _seed("Net Cast", "throw a net that mostly opens", lane="weapon", requires="net", compounds_to="binding constellation net"),
    _seed("Scythe Sweep", "sweep low without burying the blade in dirt", lane="weapon", requires="scythe", compounds_to="harvest that reaps spirits"),
    _seed("Twin Balance", "hold two light weapons without crossing wrists", lane="weapon", requires="paired light weapons", tier="advanced", compounds_to="mirror-blade dance"),
    _seed("Greatsword Stop", "stop a heavy swing without spinning yourself", lane="weapon", requires="greatsword", tier="advanced", compounds_to="horizon cleave"),
    # ── Simple weird / hybrid ────────────────────────────────────────────
    _seed("Shadow Edge", "notice where your shadow touches another person's", lane="hybrid", compounds_to="shadow merge / umbral blade"),
    _seed("Coin Flip Bias", "feel when a flip is slightly unfair — not control it yet", lane="hybrid", compounds_to="fate dice sovereignty"),
    _seed("Door Hinge", "oil/know a hinge so it screams less", lane="tool", requires="oil", compounds_to="portal hinge walking"),
    _seed("Color Blindspot", "spot one dye color others mix up in this region", compounds_to="true-spectrum sight"),
    _seed("Lefthand Mirror", "do a simple task slightly better left-handed once", compounds_to="bilateral god-body"),
    _seed("Joke Timing", "land one dry joke that breaks tension — sometimes", lane="support", compounds_to="morale dominion / fear-break laughter"),
    _seed("Map Crease", "fold a map so the right road shows first", lane="tool", requires="map", compounds_to="living cartography"),
    _seed("Salt Circle", "pour a salt line that *mostly* stays unbroken", lane="arcane", requires="salt", compounds_to="banishment fortress"),
    _seed("Candle Whisper", "flame leans toward the larger lie in the room — unreliable", lane="arcane", requires="candle", compounds_to="truthfire oracle"),
    _seed("Pocket Weight", "guess if a pocket holds coin, key, or blade by hang", compounds_to="inventory x-ray"),
    # ── Arcane / system (advanced-leaning, still F-weak) ────────────────
    _seed("Residue Glow", "faint sense of spent magic on objects — unreliable", lane="arcane", compounds_to="ley cartography / magic forensics"),
    _seed("Omen Nudge", "one wrong/right gut twitch per day", lane="arcane", compounds_to="fate editing"),
    _seed("Ward Itch", "skin prickle near crude wards only", lane="arcane", compounds_to="ward craft / ward break"),
    _seed("Dream Tag", "wake remembering one useful dream detail", lane="arcane", compounds_to="dreamwalk dominion"),
    _seed("Rune Scratch", "copy one simple mark that *almost* holds power", lane="arcane", tier="advanced", requires="stylus + surface", compounds_to="world-script runes"),
    _seed("Mana Leak", "feel when a spell is about to fizzle nearby", lane="arcane", tier="advanced", compounds_to="mana theft / spell catch"),
    _seed("Focus Crack", "sense hairline cracks in a magic focus", lane="arcane", requires="touch a focus/crystal", compounds_to="focus forge / crystal thrall"),
    _seed("Chant Breath", "hold a one-word chant without going flat", lane="arcane", requires="voice", compounds_to="word of unmaking"),
    _seed("Circle Chalk", "draw a circle that stays round under stress", lane="arcane", requires="chalk", compounds_to="reality cages"),
    _seed("Sigil Smudge", "intentionally smudge a hostile mark to weaken it 10%", lane="arcane", tier="advanced", compounds_to="anti-sigil crusade"),
    _seed("Element Taste", "tongue-tip sense of fire/water/earth/air residue", lane="arcane", tier="advanced", compounds_to="elemental throne"),
    _seed("Contract Ink", "spot when a written deal has a hidden clause — vague", lane="arcane", tier="advanced", compounds_to="pact sovereignty"),
    _seed("Star Ink", "map one night-sky pattern onto a page correctly", lane="arcane", requires="ink + night sky", compounds_to="constellation magic"),
    _seed("Echo Spell", "repeat the last syllable of someone else's cantrip", lane="arcane", tier="advanced", compounds_to="spell echo legion"),
    _seed("Glass Soul", "store a thimble of emotion in a bottle until opened", lane="arcane", tier="advanced", requires="small bottle", compounds_to="emotion armory"),
    # ── Summoning spectrum ───────────────────────────────────────────────
    _seed("Name Whisper", "whisper a half-remembered name; something *might* listen", lane="summon", tier="simple", compounds_to="true-name summons"),
    _seed("Crumb Offering", "leave crumbs; a pest spirit might nibble and linger", lane="summon", tier="simple", requires="food scrap", compounds_to="feast-bound armies"),
    _seed("Shadow Pup", "pull a palm-sized shadow-critter that flees if stared at", lane="summon", tier="simple", compounds_to="shadow legion"),
    _seed("Candle Servant", "a flame-sprite keeps one candle lit against wind", lane="summon", requires="candle", compounds_to="infernal retinue"),
    _seed("Paper Bird", "fold a bird that glides 3 meters with a note", lane="summon", requires="paper", compounds_to="origami war-flock"),
    _seed("Bone Whistle", "whistle through bone; bones nearby rattle once", lane="summon", requires="bone whistle", compounds_to="osseous choir"),
    _seed("Ink Familiar", "a blot of ink forms an eye that lasts seconds", lane="summon", tier="advanced", requires="ink", compounds_to="living grimoire familiar"),
    _seed("Door Knock Spirit", "knock thrice; a threshold spirit answers *sometimes*", lane="summon", tier="advanced", compounds_to="gate court diplomacy"),
    _seed("Pact Scratch", "cut a finger; a minor entity signs a day-long favor", lane="summon", tier="advanced", requires="blood + focus", compounds_to="archdemon contracts"),
    _seed("Echo Twin", "spawn a silent afterimage that holds a pose 2 seconds", lane="summon", tier="advanced", compounds_to="army of selves"),
    _seed("Rain Caller", "coax a single extra raindrop from a wet sky", lane="summon", tier="simple", compounds_to="storm throne"),
    _seed("Root Handshake", "touch a plant; feel if something intelligent sleeps in it", lane="summon", compounds_to="forest avatar call"),
    _seed("Coin Vassal", "spin a coin; a luck-sprite may bias the next flip", lane="summon", requires="coin", compounds_to="fortune court"),
    _seed("Mask Guest", "wear a mask; invite a personality that isn't quite yours", lane="summon", tier="advanced", requires="mask", compounds_to="pantheon mask legion"),
    _seed("Lantern Guide", "a pale light leads 10 steps toward safety — or a trap", lane="summon", requires="lantern", compounds_to="psychopomp convoy"),
    _seed("Swarm Hum", "hum until insects gather in a fist-sized cloud", lane="summon", tier="advanced", compounds_to="plague swarm crown"),
    # ── Necromancy spectrum (usable, not pure edgelord) ─────────────────
    _seed("Grave Chill", "hands go cold near recent death — unreliable range", lane="necro", tier="simple", compounds_to="death radar / reaper cartography"),
    _seed("Bone Sort", "tell animal bone from humanish at a glance — sometimes wrong", lane="necro", tier="simple", compounds_to="bone architecture"),
    _seed("Last Breath", "smell whether a corpse died scared, calm, or fighting", lane="necro", tier="simple", compounds_to="death-scene reconstruction"),
    _seed("Marrow Tap", "tap bone; hear a hollow vs solid note", lane="necro", requires="bone", compounds_to="osseomancy constructs"),
    _seed("Ash Name", "speak a dead person's name over ash; ash stirs", lane="necro", requires="ash + true name fragment", compounds_to="name-bound revenants"),
    _seed("Shroud Fold", "fold burial cloth so it settles without wrinkling", lane="necro", requires="shroud/cloth", compounds_to="soul-binding shrouds"),
    _seed("Quiet Wake", "sit vigil; restless dead nearby calm for minutes", lane="necro", tier="advanced", compounds_to="necropolis peace / undead diplomacy"),
    _seed("Finger Candle", "light a finger-flame on a knucklebone — tiny heat", lane="necro", requires="knucklebone", compounds_to="soulfire pyre"),
    _seed("Debt of the Dead", "sense if a corpse was owed coin or blood", lane="necro", tier="advanced", compounds_to="ghost debt armies"),
    _seed("Pale Stitch", "stitch a corpse's lips/eyes with ceremony — slows haunt risk", lane="necro", requires="needle + corpse", compounds_to="full reanimation arts"),
    _seed("Rattle Command", "rattle bones in rhythm; one bone twitches", lane="necro", tier="advanced", requires="bones", compounds_to="skeleton cohorts"),
    _seed("Memory Moss", "moss on a grave whispers one true fact if asked kindly", lane="necro", tier="advanced", compounds_to="cemetery oracle network"),
    _seed("Cold Ledger", "count how many have died in a room over years — rough", lane="necro", compounds_to="mass-death chronicle magic"),
    _seed("Soul Lint", "pluck faint residue of a soul from a keepsake", lane="necro", tier="advanced", requires="keepsake", compounds_to="soulforge / phylactery craft"),
    _seed("Dirge Hum", "hum a funeral note that slows decay for an hour", lane="necro", tier="advanced", compounds_to="antirot field / mummy arts"),
    # ── Tech / modern-leaning ────────────────────────────────────────────
    _seed("Wire Trace", "follow a cable or pipe with a finger", lane="tech", compounds_to="network dominion"),
    _seed("Dial Guess", "set a simple dial near the right mark", lane="tech", compounds_to="perfect calibration god"),
    _seed("Static Tick", "feel charged devices or bad grounding", lane="tech", compounds_to="lightning machine soul"),
    _seed("Label Decode", "half-read foreign labels from context", lane="tech", compounds_to="universal interface"),
    _seed("Solder Kiss", "make one cold-solder joint that sometimes holds", lane="tech", requires="solder kit", compounds_to="circuit life-binding"),
    _seed("Boot Sequence", "power-cycle a device in the least stupid order", lane="tech", compounds_to="machine resurrection"),
    _seed("Signal Ghost", "hear a faint channel in static — maybe music, maybe code", lane="tech", tier="advanced", compounds_to="spectrum throne"),
    # ── Combat-adjacent body ─────────────────────────────────────────────
    _seed("Guard Angle", "hold a stick/shield at a less stupid angle", lane="weapon", compounds_to="perfect guard domain"),
    _seed("Throw Line", "lob a small object closer to where you meant", compounds_to="orbital throw arts"),
    _seed("Brace Fall", "take a tumble with fewer broken things", compounds_to="impact null"),
    _seed("Distance Pace", "count paces for short distances roughly", compounds_to="spatial lockstep"),
    _seed("Clinch Escape", "know one dumb way out of a grab", compounds_to="untouchable flow"),
    _seed("Blind Guard", "cover the right organ when you can't see the strike", compounds_to="pre-cognitive block"),
    # ── Wild advanced hybrids (still F-usable hooks) ─────────────────────
    _seed("Blood Compass", "a drop of blood on water points vaguely toward its owner", lane="hybrid", tier="advanced", requires="blood + water", compounds_to="world-hunt blood magic"),
    _seed("Mirror Debt", "owe your reflection one favor; it helps once", lane="hybrid", tier="advanced", requires="mirror", compounds_to="reflection army"),
    _seed("Second Shadow", "cast two shadows for a breath under one light", lane="hybrid", tier="advanced", compounds_to="multiplicity body"),
    _seed("Hunger Bargain", "skip a meal; gain a tiny edge on the next desperate act", lane="hybrid", compounds_to="ascetic war-god path"),
    _seed("Scar Library", "each scar stores one fact you can reread by touch", lane="hybrid", tier="advanced", compounds_to="body grimoire"),
    _seed("Guest Right", "break bread; hostilities pause for a short formal beat", lane="support", tier="advanced", requires="shared food", compounds_to="diplomatic sanctuary law"),
    _seed("Oath Splinter", "hear when an oath nearby is about to crack", lane="arcane", tier="advanced", compounds_to="oath forge / oath break"),
    _seed("Tide Bone", "carry a bone that aches before storms or ambushes", lane="hybrid", requires="carried bone", compounds_to="disaster oracle"),
    _seed("Empty Chair", "set a place for the absent; luck leans toward reunion or omen", lane="summon", tier="advanced", compounds_to="call across worlds"),
    _seed("Weapon Name", "whisper a name to your weapon; it answers with a twitch", lane="weapon", tier="advanced", requires="named weapon bond", compounds_to="legendary ego-weapon"),
    _seed("Choir Blade", "two allies strike on your count for a tiny damage sync", lane="support", tier="advanced", compounds_to="legion tempo warfare"),
    _seed("Grave Garden", "grow one flower from soil mixed with ash", lane="necro", tier="advanced", compounds_to="necromantic ecology"),
    _seed("Summoner's Patience", "wait motionless; a minor spirit is likelier to approach", lane="summon", tier="advanced", compounds_to="court of waiting gods"),
    _seed("Healer's Vice", "hurt yourself a little to stabilize another a little", lane="support", tier="advanced", compounds_to="life-transfer throne"),
    _seed("Blacksmith Prayer", "quench metal while speaking a short blessing — 10% fewer cracks", lane="tool", requires="forge + quench", compounds_to="relic forging"),
    _seed("Apothecary Gamble", "mix two safe reagents; third effect is random mild", lane="support", requires="reagent kit", compounds_to="chaos pharmacy mastery"),
    _seed("Exorcist Salt", "throw salt that stings unclean things slightly more", lane="arcane", requires="salt", compounds_to="banishment liturgy"),
    _seed("Necro Suture", "stitch living tissue with thread that once bound a corpse", lane="necro", tier="advanced", requires="grave thread + needle", compounds_to="undying fleshcraft"),
    _seed("Familiar Bond", "share hunger with a small animal for one meal", lane="summon", compounds_to="soul-linked familiar empire"),
    _seed("Spell Steal Spark", "snuff a cantrip-level spark mid-air once in a while", lane="arcane", tier="advanced", compounds_to="archmage countersteal"),
    _seed("Barrier Hum", "hum to thicken air in front of one ally by a breath", lane="support", tier="advanced", compounds_to="force-wall orchestra"),
    _seed("Poison Garden", "grow one toxic plant that won't kill you if you're careful", lane="hybrid", compounds_to="venom ecology control"),
    _seed("Light Eater", "swallow candlelight — room dims slightly for seconds", lane="arcane", requires="flame source", compounds_to="void photophage"),
    _seed("Anchor Nail", "drive a nail that makes a small object harder to move", lane="tool", requires="nail + hammer", compounds_to="reality anchors"),
    _seed("Soul Ledger", "write a living person's name; feel their general health band", lane="support", tier="advanced", requires="true name + ink", compounds_to="census of souls"),
]

# Drop any accidental empties / fix entries that used invalid kwargs in older drafts.
SEED_SKILL_DOMAIN_POOL = [
    {k: v for k, v in d.items() if k != "lane_note" and v is not None}
    for d in SEED_SKILL_DOMAIN_POOL
    if d.get("name")
]


def seed_skill_domain_names() -> list[str]:
    return [str(d.get("name") or "").strip() for d in SEED_SKILL_DOMAIN_POOL if d.get("name")]


def is_overused_seed_domain(name: str) -> bool:
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    if not n:
        return False
    if n in OVERUSED_SEED_DOMAINS:
        return True
    for bad in OVERUSED_SEED_DOMAINS:
        if bad in n or n in bad:
            return True
    return False


def pick_seed_skill_domain(
    *,
    avoid: list[str] | None = None,
    world_style: str = "",
    genre: str = "",
    rng: random.Random | None = None,
    salt: str = "",
    prefer_lane: str = "",
    prefer_tier: str = "",
) -> dict[str, str]:
    """Pick a fresh weak-seed domain. Biases lightly by world_style / lane / tier."""
    r = rng or random.Random()
    if salt:
        # Stable-but-different pick when salt changes (setup rolls, map seeds).
        digest = hashlib.sha256(f"{salt}|{world_style}|{genre}|{prefer_lane}|{prefer_tier}".encode("utf-8")).hexdigest()
        r = random.Random(int(digest[:16], 16))

    avoid_l = {re.sub(r"\s+", " ", a.strip().lower()) for a in (avoid or []) if a}
    pool = [
        d
        for d in SEED_SKILL_DOMAIN_POOL
        if d.get("name")
        and not is_overused_seed_domain(str(d["name"]))
        and str(d["name"]).strip().lower() not in avoid_l
    ]
    if not pool:
        pool = [d for d in SEED_SKILL_DOMAIN_POOL if d.get("name")]

    style = f"{world_style} {genre}".lower()
    preferred: list[dict[str, str]] = []

    def _lane(*lanes: str) -> list[dict[str, str]]:
        want = {x.lower() for x in lanes}
        return [d for d in pool if str(d.get("lane") or "").lower() in want]

    def _names(*names: str) -> list[dict[str, str]]:
        want = set(names)
        return [d for d in pool if d.get("name") in want]

    # ~half the time roll a random lane so wild combos show up even in "normal" worlds.
    if prefer_lane:
        preferred = _lane(prefer_lane)
    elif r.random() < 0.42:
        lane_roll = r.choice(
            [
                "mundane",
                "tool",
                "weapon",
                "support",
                "summon",
                "necro",
                "arcane",
                "hybrid",
                "tech",
            ]
        )
        preferred = _lane(lane_roll)
    elif any(w in style for w in ("necro", "undead", "grave", "gothic", "death")):
        preferred = _lane("necro", "summon", "hybrid")
    elif any(w in style for w in ("summon", "demon", "spirit", "shaman", "pact")):
        preferred = _lane("summon", "arcane", "hybrid")
    elif any(w in style for w in ("heal", "temple", "cleric", "support", "monk")):
        preferred = _lane("support", "arcane")
    elif any(w in style for w in ("sea", "coast", "harbor", "pirate", "island")):
        preferred = _names("Ferry Timing", "River Smell", "Breath Hold", "Saddle Fit", "Salt Taste", "Tide Bone", "Rain Caller", "Bone Whistle")
        preferred += _lane("summon")
    elif any(w in style for w in ("desert", "ash", "volcan", "dune")):
        preferred = _names("Heat Tolerance", "Dust Sign", "Trail Mud", "Camp Ash", "Light Eater", "Ash Name")
    elif any(w in style for w in ("city", "urban", "noir", "guild", "court")):
        preferred = _lane("mundane", "support", "tool") + _names("Queue Sense", "Coin Ring", "Contract Ink", "Seat Rank")
    elif any(w in style for w in ("forest", "wild", "frontier", "road")):
        preferred = _names("Trail Mud", "Camp Ash", "Herb Thumb", "Herd Calm", "Root Handshake", "Poison Garden")
    elif any(w in style for w in ("tech", "cyber", "space", "sci", "mecha", "industrial")):
        preferred = _lane("tech", "tool")
    elif any(w in style for w in ("magic", "cultiv", "arcane", "witch", "rune", "isekai")):
        preferred = _lane("arcane", "summon", "support", "hybrid")
    elif any(w in style for w in ("war", "soldier", "knight", "gladiator", "military")):
        preferred = _lane("weapon", "support")

    # Tier spice: sometimes force simple obscure, sometimes advanced crazy.
    tier_pick = (prefer_tier or "").lower()
    if not tier_pick:
        roll = r.random()
        if roll < 0.38:
            tier_pick = "simple"
        elif roll < 0.76:
            tier_pick = "advanced"
        # else: any tier
    if tier_pick in {"simple", "advanced"}:
        tiered = [d for d in (preferred or pool) if str(d.get("tier") or "simple") == tier_pick]
        if tiered:
            preferred = tiered

    # 50% prefer style/lane match when available so domains still feel world-fit without monotony.
    if preferred and r.random() < 0.5:
        choice = dict(r.choice(preferred))
    else:
        choice = dict(r.choice(pool))
    # Keep `hint` player-facing clean. Stash LLM-only guidance separately so UI
    # never shows "advanced tier; arcane lane; compounds toward: …".
    clean_hint = str(choice.get("hint") or "").strip().rstrip(".")
    choice["hint"] = clean_hint
    prompt_bits = [clean_hint] if clean_hint else []
    if choice.get("requires"):
        prompt_bits.append(f"tool/focus: {choice['requires']}")
    if choice.get("compounds_to"):
        prompt_bits.append(f"late payoff (fiction only, not starting power): {choice['compounds_to']}")
    if choice.get("tier"):
        prompt_bits.append(f"design tier={choice['tier']}")
    if choice.get("lane"):
        prompt_bits.append(f"design lane={choice['lane']}")
    choice["prompt_hint"] = "; ".join(prompt_bits)
    return choice


def player_facing_domain_description(domain: dict[str, Any] | None) -> str:
    """Write a setup-card description from a seed domain — no meta labels."""
    if not isinstance(domain, dict):
        return "A thin practical edge that is barely useful until practiced."
    name = str(domain.get("name") or "Seed").strip()
    # Prefer raw pool hint, never prompt_hint (which can carry design tags).
    hint = str(domain.get("hint") or "").strip().rstrip(".")
    # Strip any leaked design tags if a caller mutated hint earlier.
    hint = re.sub(
        r"\s*;\s*(?:compounds toward|requires|advanced tier|simple tier|design tier|design lane|arcane lane|mundane lane|tool lane|weapon lane|support lane|summon lane|necro lane|hybrid lane|tech lane)[^;]*",
        "",
        hint,
        flags=re.I,
    ).strip(" ;.")
    req = str(domain.get("requires") or "").strip()
    late = str(domain.get("compounds_to") or "").strip()
    # Opening sentence: concrete effect, weak and limited.
    if hint:
        body = hint[0].upper() + hint[1:] if hint else hint
        # If hint is a fragment ("hear when…"), frame it as a weak sense/act.
        if not re.match(r"^(You|When|A |An |The |Briefly|Once|Can |May )", body, re.I):
            body = f"You can {body[0].lower() + body[1:] if body else 'sense a faint edge'}."
        else:
            if not body.endswith("."):
                body += "."
    else:
        body = f"{name} is a faint, unreliable aptitude — barely more than a habit at first."
    if req:
        body += f" It only answers cleanly when you have {req}."
    body += " At F rank the effect is brief, incomplete, or easy to miss."
    if late:
        body += f" With practice it may grow toward {late} — never as a free start."
    return body[:800]


def weak_skill_seed_spec(
    playthrough_options: dict[str, Any] | None = None,
    session_theme: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    When setup wants a near-useless start / compounding seed, return one skill row to insert.
    Prefer an explicit name in custom_skills or the first special ability; else a fresh domain
    from SEED_SKILL_DOMAIN_POOL (never a fixed Observation / knot / barter default).
    """
    opts = playthrough_options if isinstance(playthrough_options, dict) else {}
    theme = session_theme if isinstance(session_theme, dict) else {}
    if not theme and isinstance(opts.get("session_theme"), dict):
        theme = opts["session_theme"]
    pf = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}
    start = str(pf.get("start_power") or "").lower()
    growth = str(pf.get("growth") or "").lower()
    custom = str(opts.get("custom_skills") or "")
    custom_l = custom.lower()
    wants_seed = (
        start in ("near_useless", "weak")
        or growth == "compounding"
        or "weak seed" in custom_l
        or "near-useless" in custom_l
        or "near useless" in custom_l
        or "almost no useful" in custom_l
        or "op_mc_frame" in custom_l
        or "one_skill_frame" in custom_l
    )
    if not wants_seed:
        return None

    name = ""
    # Named seed: "weak seed skill: Foo" / "One weak seed skill: Digging"
    m = re.search(
        r"(?:weak\s+seed\s+(?:skill|proficiency)?|seed\s+skill|seed\s+proficiency)\s*[:\-–]?\s*([A-Za-z][A-Za-z0-9 \-]{1,40})",
        custom,
        re.I,
    )
    if m:
        name = m.group(1).strip().rstrip(".;,")
    if not name:
        m2 = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*\((?:near[- ]?useless|F\b|weak)", custom)
        if m2:
            name = m2.group(1).strip()
    # "Seed skill Digging rank F" / "Seed skill: Hauling"
    if not name:
        m2b = re.search(
            r"\bseed\s+(?:skill|power|domain|proficiency)\s*[:\-–]?\s*([A-Z][A-Za-z0-9 \-]{1,40})",
            custom,
        )
        if m2b:
            name = m2b.group(1).strip().rstrip(".;,")
    if not name:
        summary = str(pf.get("skill_summary") or "").strip()
        m3 = re.search(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)?)\b", summary)
        if m3 and m3.group(1).lower() not in {"the", "and", "with", "weak", "seed", "power", "start"}:
            name = m3.group(1)
    # Prefer the rolled special ability name when custom_skills is still a skeleton frame.
    if not name or is_overused_seed_domain(name) or name.lower() in {
        "start",
        "power",
        "domain",
        "chosen",
        "later",
        "never",
        "default",
        "weather",
    }:
        abilities = opts.get("special_abilities")
        if isinstance(abilities, list) and abilities:
            a0 = abilities[0] if isinstance(abilities[0], dict) else {}
            aname = str(a0.get("name") or "").strip()
            if aname and not is_overused_seed_domain(aname):
                name = aname
    domain: dict[str, str] = {}
    if not name or is_overused_seed_domain(name):
        domain = pick_seed_skill_domain(
            world_style=str(opts.get("world_style") or theme.get("genre") or ""),
            genre=str(theme.get("genre") or ""),
            salt=f"{time.time_ns()}|{custom[:40]}|{opts.get('player_name') or ''}",
        )
        name = str(domain.get("name") or "Digging")
        hint = str(domain.get("hint") or "")
    else:
        hint = ""

    # Strip design tags if hint was ever mutated for the LLM.
    clean_hint = re.sub(
        r"\s*;\s*(?:compounds toward|requires|advanced tier|simple tier|design tier|design lane|"
        r"arcane lane|mundane lane|tool lane|weapon lane|support lane|summon lane|necro lane|"
        r"hybrid lane|tech lane)[^;]*",
        "",
        str(hint or ""),
        flags=re.I,
    ).strip(" ;.")
    notes = (
        "Weak opening seed: nearly useless now; can compound through careful practice, training, and risk. "
        "Not a free power spike."
        + (f" Effect: {clean_hint}." if clean_hint else "")
    )[:700]
    hint = clean_hint
    out: dict[str, Any] = {
        "name": name[:80],
        "value": 1,
        "notes": notes,
        "domain_hint": hint,
    }
    if domain:
        if domain.get("requires"):
            out["requires"] = domain["requires"]
        if domain.get("compounds_to"):
            out["compounds_to"] = domain["compounds_to"]
        if domain.get("tier"):
            out["tier"] = domain["tier"]
        if domain.get("lane"):
            out["lane"] = domain["lane"]
    return out


# Fields that must never carry player skill / power-fantasy slogans.
STRUCTURE_FIELDS = frozenset(
    {
        "quest_style",
        "faction_pressure",
        "economy",
        "npc_stat_scaling",
        "npc_skill_frequency",
        "npc_density",
        "rank_scale",
        "world_races",
        "difficulty",
        "death_rules",
        "loot_rarity",
        "tone",
        "tech_level",
        "magic_level",
        "system_style",
    }
)

# Fields where growth language is OK (skill fantasy lives here).
GROWTH_HOME_FIELDS = frozenset(
    {
        "custom_skills",
        "special_abilities",
        "skill_growth_speed",
        "proficiency_growth_speed",
        "xp_growth_speed",
        "new_skill_frequency",
        "skill_style",
        "special_ability_origin",
    }
)

GROWTH_SLOGAN_RE = re.compile(
    r"("
    r"compound(?:ing|s)?|"
    r"near[- ]?useless|"
    r"weak\s+seed|"
    r"snowball|"
    r"overpowered|"
    r"power\s*fantasy|"
    r"skill\s+that\s+|"
    r"simple,?\s+near|"
    r"delayed\s+growth|"
    r"hint(?:s)?\s+at\s+overpowered|"
    r"one\s+weak\s+skill|"
    r"useless\s+skill|"
    r"level\s+delay|"
    r"per\s+level|"
    r"1[- ]?hour|"
    r"24[- ]?hour|"
    r"cooldown\s+after|"
    r"max\s+level"
    r")",
    re.I,
)

GROWTH_TIMER_RE = re.compile(
    r"("
    r"\d+\s*[- ]?(hour|hr|minute|min|day)s?|"
    r"cooldown|"
    r"per\s+level|"
    r"delay(?:ed)?\s+(?:compound|growth|level)|"
    r"skill\s+compound"
    r")",
    re.I,
)

POWER_LABEL_RACE_RE = re.compile(
    r"("
    r"low[- ]?power|"
    r"high[- ]?power|"
    r"op\b|"
    r"overpowered|"
    r"near[- ]?useless|"
    r"compound"
    r")",
    re.I,
)


def _value_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def has_growth_slogan(text: str) -> bool:
    return bool(GROWTH_SLOGAN_RE.search(text or ""))


def has_growth_timer(text: str) -> bool:
    return bool(GROWTH_TIMER_RE.search(text or ""))


def looks_like_slogan_paste(field: str, value: Any, idea: str = "") -> bool:
    """Heuristic: field received the full idea text or a mis-slotted growth slogan."""
    return bool(field_contamination_reasons(field, value, idea))


def field_contamination_reasons(field: str, value: Any, idea: str = "") -> list[str]:
    """Return reasons a value is invalid for this field (empty = clean)."""
    text = _value_text(value)
    if not text:
        return []
    reasons: list[str] = []
    contract = field_contract(field)
    kind = contract.get("kind")
    idea_l = str(idea or "").strip().lower()
    text_l = text.lower()

    if kind in ("boolean", "number"):
        return []

    if kind == "enum":
        allowed = [str(a).lower() for a in (contract.get("allowed_values") or [])]
        if allowed and text_l not in allowed:
            # Allow close matches for multi-word enums already handled upstream
            if not any(text_l == a or text_l.startswith(a) for a in allowed):
                reasons.append("not_an_allowed_enum")
        return reasons

    max_len = int(contract.get("max_len") or 0)
    if max_len and len(text) > max_len and field in STRUCTURE_FIELDS:
        reasons.append("too_long_for_structure_field")

    if idea_l and len(idea_l) >= 24:
        if text_l == idea_l or (len(text) > 40 and idea_l[:40] in text_l):
            reasons.append("full_idea_paste")

    ban_growth = bool(contract.get("ban_growth_slogans")) or field in STRUCTURE_FIELDS
    ban_timers = bool(contract.get("ban_growth_timers"))
    if field in GROWTH_HOME_FIELDS:
        ban_growth = False
        # skill_style may mention compounding briefly but not ability essays
        if field == "skill_style" and len(text) > 90 and has_growth_slogan(text):
            reasons.append("skill_style_too_essay_like")
    else:
        if ban_growth and has_growth_slogan(text):
            reasons.append("growth_slogan_in_wrong_field")
        if ban_timers and has_growth_timer(text):
            reasons.append("growth_timer_in_wrong_field")

    if field == "world_races" and POWER_LABEL_RACE_RE.search(text):
        reasons.append("power_label_as_race")

    if field in ("quest_style", "faction_pressure", "economy"):
        # These should not look like ability descriptions
        if re.search(r"\b(ability|mastery|fishing rod|train(?:ing|s)? to become)\b", text_l):
            reasons.append("ability_language_in_structure_field")
        if text_l.startswith("start with") and "skill" in text_l:
            reasons.append("skill_seed_in_structure_field")

    if field in ("race_magic_rules", "race_ability_rules"):
        if has_growth_timer(text) or (has_growth_slogan(text) and "race" not in text_l[:40]):
            # If the whole blurb is about compounding levels, reject
            if has_growth_timer(text) or "compound" in text_l:
                reasons.append("global_growth_dumped_into_race_rules")

    if field == "custom_style":
        # Reject if almost only timer/skill math with no world framing
        if has_growth_timer(text) and not any(
            k in text_l for k in ("isekai", "world", "dm", "genre", "setting", "system ui", "agency", "tone")
        ):
            reasons.append("custom_style_is_only_growth_timer")

    if field == "rank_scale" and ("," not in text and " " in text and len(text) > 40):
        reasons.append("rank_scale_not_ladder")

    return reasons


def field_is_contaminated(field: str, value: Any, idea: str = "") -> bool:
    return bool(field_contamination_reasons(field, value, idea))


# ---------------------------------------------------------------------------
# Cross-field consistency: race rules ↔ world_races; memory ↔ backstory
# ---------------------------------------------------------------------------

# (regex, canonical root) — used to detect race names mentioned in free prose.
_RACE_MENTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bhumans?\b", re.I), "human"),
    (re.compile(r"\belves\b|\belven\b|\belf\b", re.I), "elf"),
    (re.compile(r"\bdwarves\b|\bdwarven\b|\bdwarf\b", re.I), "dwarf"),
    (re.compile(r"\borcs?\b|\borcish\b", re.I), "orc"),
    (re.compile(r"\bbeast[- ]?folks?\b|\bbeastkins?\b", re.I), "beastfolk"),
    (re.compile(r"\bhalflings?\b", re.I), "halfling"),
    (re.compile(r"\bgoblins?\b", re.I), "goblin"),
    (re.compile(r"\bdragonkins?\b|\bdragonborn\b", re.I), "dragonkin"),
    (re.compile(r"\btieflings?\b", re.I), "tiefling"),
    (re.compile(r"\bgnomes?\b", re.I), "gnome"),
    (re.compile(r"\bfae\b|\bfairy\b|\bfairies\b", re.I), "fae"),
    (re.compile(r"\bmerfolks?\b|\bmermaids?\b", re.I), "merfolk"),
    (re.compile(r"\blizardfolks?\b", re.I), "lizardfolk"),
    (re.compile(r"\bvampires?\b", re.I), "vampire"),
    (re.compile(r"\bundead\b", re.I), "undead"),
    (re.compile(r"\bgiants?\b", re.I), "giant"),
    (re.compile(r"\btrolls?\b", re.I), "troll"),
    (re.compile(r"\byokai\b|\boni\b|\bkitsune\b", re.I), "yokai"),
    (re.compile(r"\briverfolks?\b|\briverkins?\b", re.I), "riverfolk"),
    (re.compile(r"\bstonekins?\b", re.I), "stonekin"),
    (re.compile(r"\bcats?folks?\b|\bwolfkins?\b", re.I), "beastfolk"),
]

_FRAGMENT_MEMORY_RE = re.compile(
    r"("
    r"fragment(?:ed|s)?|"
    r"amnesia|"
    r"barely\s+remember|"
    r"cannot\s+remember|"
    r"can'?t\s+remember|"
    r"few\s+memories|"
    r"only\s+scraps|"
    r"incomplete\s+memor|"
    r"memories?\s+(?:are\s+)?(?:lost|foggy|hazy|blurred)|"
    r"blank\s+past|"
    r"doesn'?t\s+remember|"
    r"no\s+memory\s+of|"
    r"former\s+life\s+fragments"
    r")",
    re.I,
)

_INTACT_MEMORY_RE = re.compile(
    r"("
    r"memor(?:y|ies)\s+intact|"
    r"most\s+memor(?:y|ies)\s+intact|"
    r"remembers?\s+(?:almost\s+)?everything|"
    r"full\s+memory|"
    r"clear\s+memor|"
    r"remembers?\s+former\s+life|"
    r"former\s+life\s+(?:is\s+)?(?:fully\s+)?known"
    r")",
    re.I,
)

_FORMER_LIFE_RE = re.compile(
    r"("
    r"former\s+life|"
    r"previous\s+life|"
    r"past\s+life|"
    r"other\s+world|"
    r"another\s+world|"
    r"reincarnat|"
    r"transmigrat|"
    r"isekai|"
    r"died\s+in|"
    r"woke\s+(?:up\s+)?in\s+this\s+world|"
    r"born\s+somewhere\s+else|"
    r"two\s+lives"
    r")",
    re.I,
)

_FORMER_MODE_RE = re.compile(r"reincarnat|transmigrat|reborn|isekai", re.I)


def parse_world_races(value: Any) -> list[str]:
    """Split world_races into ordered unique labels."""
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
    else:
        text = str(value or "").strip()
        if not text:
            return []
        text = re.sub(r"\s+and\s+", ",", text, flags=re.I)
        parts = [p.strip() for p in re.split(r"[,;/|]+", text) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(part[:60])
        if len(out) >= 12:
            break
    return out


def _race_roots_from_labels(labels: list[str]) -> set[str]:
    roots: set[str] = set()
    for label in labels:
        token = re.sub(r"[^a-z0-9\s\-]", "", label.lower()).strip()
        if not token:
            continue
        roots.add(token)
        roots.add(token.replace("-", " ").replace(" ", ""))
        first = token.split()[0]
        roots.add(first)
        if first.endswith("ves") and len(first) > 4:
            roots.add(first[:-3] + "f")  # elves → elf
        elif first.endswith("ies") and len(first) > 4:
            roots.add(first[:-3] + "y")
        elif first.endswith("s") and len(first) > 3 and not first.endswith("ss"):
            roots.add(first[:-1])
        # Map common plurals / aliases onto detect roots
        for _pat, root in _RACE_MENTION_PATTERNS:
            if root in token or token in root or first == root or first.rstrip("s") == root:
                roots.add(root)
    return roots


def mentioned_race_roots(text: str) -> set[str]:
    found: set[str] = set()
    blob = text or ""
    for pattern, root in _RACE_MENTION_PATTERNS:
        if pattern.search(blob):
            found.add(root)
    return found


def race_rules_mismatch_reasons(world_races: Any, rules_text: Any) -> list[str]:
    """Flag race rule prose that invents peoples not listed in world_races."""
    text = _value_text(rules_text)
    if not text or len(text) < 12:
        return []
    labels = parse_world_races(world_races)
    if not labels:
        return []
    allowed = _race_roots_from_labels(labels)
    mentioned = mentioned_race_roots(text)
    if not mentioned:
        return []
    foreign = {r for r in mentioned if r not in allowed and not any(r in a or a in r for a in allowed)}
    allowed_hit = {r for r in mentioned if r in allowed or any(r in a or a in r for a in allowed)}
    reasons: list[str] = []
    # Rules talk about foreign peoples and never acknowledge listed races.
    if foreign and not allowed_hit:
        reasons.append("race_rules_foreign_races")
    # Single-race world but multi-race essay.
    if len(labels) == 1 and len(foreign) >= 2:
        if "race_rules_foreign_races" not in reasons:
            reasons.append("race_rules_foreign_races")
    # Multi-race world with several listed races ignored while others invent.
    if len(labels) >= 2 and foreign and len(allowed_hit) == 0:
        if "race_rules_foreign_races" not in reasons:
            reasons.append("race_rules_foreign_races")
    return reasons


def rebuild_race_rules(field: str, world_races: Any, context: dict[str, Any] | None = None) -> str:
    """Deterministic race-rules text constrained to world_races."""
    races = parse_world_races(world_races)
    if not races:
        races = ["human"]
    only_human = len(races) == 1 and races[0].lower().rstrip("s") == "human"
    if field == "race_magic_rules":
        if only_human:
            return (
                "Humans need formal training for most casting. Gifted individuals may hold rare innate sparks, "
                "but overall magic stays limited unless the setting says otherwise."
            )
        bits: list[str] = []
        for race in races:
            rl = race.lower()
            if "human" in rl:
                bits.append(f"{race} usually need formal training for reliable magic.")
            elif "elf" in rl:
                bits.append(f"{race} often inherit low glamour and still need discipline for stronger casting.")
            elif "dwarf" in rl:
                bits.append(f"{race} favor rune-craft and earth-bound rites over flashy spellwork.")
            elif "beast" in rl or "folk" in rl or "kin" in rl:
                bits.append(f"{race} rarely cast spells but may sense spirits and wild omen.")
            elif "orc" in rl:
                bits.append(f"{race} treat magic as blood-oaths and war rites more often than academy casting.")
            else:
                bits.append(f"{race}: magic access follows culture and training more than raw bloodline.")
        return " ".join(bits)[:1200]
    # race_ability_rules
    if only_human:
        return (
            "Humans learn broadly through practice. Starting gifts stay small and never replace trained skills."
        )
    bits = []
    for race in races:
        rl = race.lower()
        if "human" in rl:
            bits.append(f"{race} learn broadly through practice.")
        elif "elf" in rl:
            bits.append(f"{race} may sense old growth and long histories.")
        elif "dwarf" in rl:
            bits.append(f"{race} often inherit craft endurance and stone-sense.")
        elif "beast" in rl or "folk" in rl or "kin" in rl:
            bits.append(f"{race} may inherit heightened senses; innate gifts start modest.")
        else:
            bits.append(f"{race}: innate gifts stay modest and never replace skills.")
    return (" ".join(bits) + " Starting racial gifts stay small.")[:1200]


def memory_backstory_mismatch(
    backstory_mode: Any,
    memory_policy: Any,
    character_backstory: Any,
) -> list[str]:
    """Reasons memory_policy conflicts with mode/backstory wording."""
    mode = _value_text(backstory_mode)
    policy = _value_text(memory_policy)
    story = _value_text(character_backstory)
    if not policy and not story and not mode:
        return []
    mode_l = mode.lower()
    policy_l = policy.lower()
    story_l = story.lower()
    former_mode = bool(_FORMER_MODE_RE.search(mode_l))
    former_story = bool(_FORMER_LIFE_RE.search(story_l))
    former = former_mode or former_story
    fragments = bool(_FRAGMENT_MEMORY_RE.search(story_l)) or "fragment" in mode_l
    intact = bool(_INTACT_MEMORY_RE.search(story_l))
    reasons: list[str] = []

    clear_policies = ("known", "ordinary memory")
    fragment_policies = ("former life fragments", "details emerge through choices")
    full_former_policies = ("remembers former life",)

    if fragments and not intact and policy_l in clear_policies:
        reasons.append("memory_policy_too_clear_for_fragmented_backstory")
    if intact and former and any(p in policy_l for p in ("fragment", "details emerge")):
        reasons.append("memory_policy_fragmented_but_backstory_intact")
    if former_mode and policy_l in clear_policies and not former_story and not intact:
        # Reincarnated/transmigrated with only "known" — usually under-specified
        reasons.append("memory_policy_ignores_former_life_mode")
    if ("remembers former life" in policy_l or "former life fragments" in policy_l) and not former:
        reasons.append("memory_policy_claims_former_life_without_backstory")
    if "former life fragments" in policy_l and intact and not fragments:
        reasons.append("memory_policy_fragmented_but_backstory_intact")
    if policy_l in full_former_policies and fragments and not intact:
        reasons.append("memory_policy_full_former_but_backstory_fragmented")

    # Avoid double-flagging empty story with weak mode-only noise
    if not story and not former_mode and reasons == ["memory_policy_claims_former_life_without_backstory"]:
        return reasons
    return reasons


def resolve_memory_policy(
    backstory_mode: Any,
    memory_policy: Any,
    character_backstory: Any,
) -> tuple[str | None, list[str]]:
    """Return (replacement_policy or None, reasons). Prefers adjusting memory_policy."""
    reasons = memory_backstory_mismatch(backstory_mode, memory_policy, character_backstory)
    if not reasons:
        return None, []
    mode = _value_text(backstory_mode)
    story = _value_text(character_backstory)
    mode_l = mode.lower()
    story_l = story.lower()
    former_mode = bool(_FORMER_MODE_RE.search(mode_l))
    former_story = bool(_FORMER_LIFE_RE.search(story_l))
    former = former_mode or former_story
    fragments = bool(_FRAGMENT_MEMORY_RE.search(story_l)) or "fragment" in mode_l
    intact = bool(_INTACT_MEMORY_RE.search(story_l))

    if not former and ("claims_former_life" in " ".join(reasons)):
        return "ordinary memory", reasons
    if fragments and not intact:
        return "former life fragments" if former else "details emerge through choices", reasons
    if former and intact:
        return "remembers former life", reasons
    if former_mode and not fragments:
        return "remembers former life", reasons
    if former and fragments:
        return "former life fragments", reasons
    return "details emerge through choices", reasons


_HAIR_TOKEN_RE = re.compile(
    r"\b("
    r"(?:short|long|cropped|messy|wavy|curly|straight|shoulder[- ]length|waist[- ]length|chin[- ]length|"
    r"bald|shaved|buzzed|undercut|braid(?:ed)?|ponytail|bun|dreadlocks|cornrows|locs|"
    r"silver|white|grey|gray|black|brown|blonde|blond|red|auburn|copper|ash|sandy|platinum|"
    r"ginger|blue|green|pink|purple)\s+"
    r"){0,3}"
    r"(?:hair|braid|braids|ponytail|bun|dreadlocks|locs|cornrows|mane|fringe|bangs)\b"
    r"|"
    r"\bbald\b|\bshaved head\b|\bbuzz cut\b|\bundercut\b",
    re.I,
)
_FACE_ONLY_HINT_RE = re.compile(
    r"\b(eyes?|iris|pupil|brow|brows|eyelid|lids|lash|lashes|freckles?|scar|scars|"
    r"jaw|chin|nose|cheek|cheeks|lip|lips|mouth|dimple|dimples|wrinkle|lines|"
    r"tattoo|tattoos|birthmark|mole|moles|beard|stubble|mustache|moustache|"
    r"glasses|spectacles|monocle)\b",
    re.I,
)


def _split_look_phrases(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    # Split on common list separators; keep parentheticals attached until strip.
    parts = re.split(r"\s*[,;|/]\s*|\s+·\s+", raw)
    out: list[str] = []
    for p in parts:
        t = re.sub(r"^\(+|\)+$", "", p.strip(" ."))
        t = t.strip(" .")
        if t:
            out.append(t)
    return out


def _phrase_is_hair(phrase: str) -> bool:
    p = phrase.strip()
    if not p:
        return False
    if _HAIR_TOKEN_RE.search(p):
        return True
    low = p.lower()
    return low in {"bald", "shaved head", "buzz cut", "undercut"} or low.endswith(" hair")


def _phrase_is_face(phrase: str) -> bool:
    if _phrase_is_hair(phrase):
        return False
    return bool(_FACE_ONLY_HINT_RE.search(phrase))


def _phrase_is_clothing(phrase: str) -> bool:
    low = phrase.lower()
    if ":" in low:  # zone:item
        return True
    return bool(
        re.search(
            r"\b(coat|cloak|tunic|shirt|jacket|hoodie|boots|shoes|gloves|apron|"
            r"trousers|pants|skirt|robe|armor|bag|satchel|belt|scarf|hood)\b",
            low,
        )
    )


def normalize_look_fields(
    fields: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Keep hair / face / clothing in the right fields; strip duplicates across them.

    Fixes LLM slop like facial_features = '(cropped silver hair), grey eyes, tired lids, square jaw'.
    """
    out = dict(fields)
    dirty: dict[str, list[str]] = {}
    merged = {**(context or {}), **out}

    hair_raw = str(out.get("hair", merged.get("hair") or "") or "").strip()
    face_raw = str(out.get("facial_features", merged.get("facial_features") or "") or "").strip()
    app_raw = str(out.get("appearance", merged.get("appearance") or "") or "").strip()

    # Only run when at least one look field is in this batch (or any present in out).
    if not any(k in out for k in ("hair", "facial_features", "appearance")):
        return out, dirty

    hair_bits = _split_look_phrases(hair_raw)
    face_bits = _split_look_phrases(face_raw)
    app_bits = _split_look_phrases(app_raw)

    rescued_hair: list[str] = []
    clean_face: list[str] = []
    clean_app: list[str] = []
    clean_hair: list[str] = []

    for p in hair_bits:
        if _phrase_is_hair(p) or not (_phrase_is_face(p) or _phrase_is_clothing(p)):
            clean_hair.append(p)
        elif _phrase_is_face(p):
            clean_face.append(p)
            dirty.setdefault("hair", []).append("moved_face_phrase_to_facial_features")
        elif _phrase_is_clothing(p):
            clean_app.append(p)
            dirty.setdefault("hair", []).append("moved_clothing_phrase_to_appearance")

    for p in face_bits:
        if _phrase_is_hair(p):
            rescued_hair.append(p)
            dirty.setdefault("facial_features", []).append("moved_hair_phrase_to_hair")
        elif _phrase_is_clothing(p):
            clean_app.append(p)
            dirty.setdefault("facial_features", []).append("moved_clothing_phrase_to_appearance")
        else:
            clean_face.append(p)

    for p in app_bits:
        if _phrase_is_hair(p) and not re.search(r"^\w+:", p):
            rescued_hair.append(p)
            dirty.setdefault("appearance", []).append("moved_hair_phrase_to_hair")
        elif _phrase_is_face(p) and not re.search(r"^\w+:", p):
            clean_face.append(p)
            dirty.setdefault("appearance", []).append("moved_face_phrase_to_facial_features")
        else:
            clean_app.append(p)

    # Merge rescued hair; prefer existing hair field if non-empty after clean
    for p in rescued_hair:
        if p.lower() not in {h.lower() for h in clean_hair}:
            clean_hair.append(p)

    # Dedupe face bits
    seen_f: set[str] = set()
    face_final: list[str] = []
    for p in clean_face:
        k = p.lower()
        if k in seen_f:
            continue
        seen_f.add(k)
        face_final.append(p)

    # Ban the known collapse stack if it's the whole face field
    collapse = "grey eyes, tired lids, square jaw"
    if ", ".join(face_final).lower().strip() == collapse:
        dirty.setdefault("facial_features", []).append("overused_face_stack")
        face_final = ["hazel eyes, faint laugh lines, straight nose"]

    hair_final = ", ".join(clean_hair).strip()
    # Prefer single hair phrase
    if hair_final.count(",") >= 2:
        hair_final = clean_hair[0] if clean_hair else hair_final

    face_joined = ", ".join(face_final).strip()
    app_joined = "; ".join(clean_app).strip() if any(":" in a for a in clean_app) else ", ".join(clean_app).strip()

    if "hair" in out or rescued_hair or dirty.get("hair"):
        if hair_final != hair_raw:
            out["hair"] = hair_final
            dirty.setdefault("hair", []).append("normalized_look_fields")
        elif "hair" in out:
            out["hair"] = hair_final
    if "facial_features" in out or dirty.get("facial_features"):
        if face_joined != face_raw:
            out["facial_features"] = face_joined
            dirty.setdefault("facial_features", []).append("normalized_look_fields")
        elif "facial_features" in out:
            out["facial_features"] = face_joined
    if "appearance" in out or dirty.get("appearance"):
        if app_joined != app_raw:
            out["appearance"] = app_joined
            dirty.setdefault("appearance", []).append("normalized_look_fields")
        elif "appearance" in out:
            out["appearance"] = app_joined

    return out, dirty


# Canonical origin labels (UI + starter_logic classify against these stems).
BACKSTORY_MODE_CANON = (
    "known",
    "hidden",
    "fragmented memories",
    "reincarnated",
    "transmigrated",
    "nameless drifter",
    "amnesia",
)
MEMORY_POLICY_CANON = (
    "known",
    "ordinary memory",
    "details emerge through choices",
    "rumors may be wrong",
    "private details stay private",
    "remembers former life",
    "former life fragments",
)


def normalize_backstory_mode(value: Any, *, story: str = "", idea: str = "") -> str:
    """Collapse free-prose modes into a short canonical mode label."""
    raw = str(value or "").strip()
    blob = f"{raw} {story} {idea}".lower()
    if not raw and not story and not idea:
        return ""
    # Exact / near-exact canon
    low = raw.lower()
    for canon in BACKSTORY_MODE_CANON:
        if low == canon or low.replace("_", " ") == canon:
            return canon
    if any(m in blob for m in ("amnesia", "no memory", "blank slate", "remember nothing")):
        return "amnesia"
    if any(m in blob for m in ("nameless", "no name", "drifter without a name")):
        return "nameless drifter"
    if any(m in blob for m in ("fragmented memor", "memory fragment", "half-memor")):
        # Prefer reincarnated/transmigrated if those also present
        if any(m in blob for m in ("reincarnat", "reborn", "born again")):
            return "reincarnated"
        if any(m in blob for m in ("transmigrat", "summon", "portal", "truck", "another world", "woke in")):
            return "transmigrated"
        return "fragmented memories"
    if any(m in blob for m in ("reincarnat", "reborn", "born again", "second life as a child", "grew up after rebirth")):
        return "reincarnated"
    if any(
        m in blob
        for m in (
            "transmigrat",
            "summon",
            "portal",
            "truck",
            "another world",
            "other world",
            "into the body",
            "into a body",
            "woke on a dirt",
            "woke in a",
            "died at a desk",
            "died on the job",
        )
    ):
        return "transmigrated"
    if any(m in blob for m in ("hidden past", "secret identity", "concealed")):
        return "hidden"
    if low in {"known life", "ordinary", "native", "known past"}:
        return "known"
    # Free-prose mode that is really a backstory sentence — reclassify from story
    if len(raw) > 40 or raw.count(" ") >= 6:
        return normalize_backstory_mode("", story=story or raw, idea=idea) or "known"
    return raw[:60] if raw else "known"


def normalize_memory_policy(value: Any, *, mode: str = "", story: str = "") -> str:
    """One short memory rule — not a free essay or menu dump."""
    raw = str(value or "").strip()
    low = raw.lower()
    story_l = str(story or "").lower()
    mode_l = str(mode or "").lower()
    for canon in MEMORY_POLICY_CANON:
        if low == canon:
            return canon
    if raw.count(",") >= 3 or raw.count(";") >= 2 or len(raw) > 90:
        raw = ""
        low = ""
    if any(m in low for m in ("remembers former", "full former", "intact former", "clear former")):
        # Policy or story mentions fragments → keep partial recall, not full
        if any(m in low or m in story_l for m in ("fragment", "partial", "half-memor", "half remember", "half-remember")):
            return "former life fragments"
        return "remembers former life"
    if any(m in low or m in story_l for m in ("fragment", "half-memor", "partial", "bits of", "scraps of")):
        if any(
            m in mode_l or m in story_l or m in low
            for m in ("former", "previous", "reincarn", "transmigr", "another world", "desk", "office")
        ):
            return "former life fragments"
        return "details emerge through choices"
    if any(m in low for m in ("rumor", "may be wrong", "uncertain")):
        return "rumors may be wrong"
    if any(m in low for m in ("private", "stay private")):
        return "private details stay private"
    if any(m in low for m in ("ordinary memory", "known memory", "clear memory")) or low in {"known", "ordinary"}:
        # Mode implies former life — don't leave pure "known"
        if any(m in mode_l for m in ("reincarnat", "transmigrat")):
            return "former life fragments"
        return "ordinary memory"
    if not raw:
        if any(m in mode_l for m in ("reincarnat", "transmigrat")):
            return "former life fragments"
        return "ordinary memory"
    # Collapse long free prose into closest canon
    if len(raw) > 60:
        if "fragment" in low:
            return "former life fragments"
        if "former" in low or "previous" in low:
            return "remembers former life"
        return "details emerge through choices"
    return raw[:80]


def normalize_previous_life_age(value: Any) -> str:
    """Prefer digits (e.g. 27). Map word ages; drop junk."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    m = re.search(r"\b(\d{1,3})\b", raw)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 120:
            return str(n)
    word_map = {
        "early twenties": "22",
        "mid twenties": "25",
        "late twenties": "28",
        "twenties": "25",
        "early thirties": "32",
        "mid thirties": "35",
        "late thirties": "38",
        "thirties": "35",
        "forty": "40",
        "fifty": "50",
    }
    for k, v in word_map.items():
        if k in raw:
            return v
    # "twenty-seven" style
    ones = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
        "thirteen": 13,
        "fourteen": 14,
        "fifteen": 15,
        "sixteen": 16,
        "seventeen": 17,
        "eighteen": 18,
        "nineteen": 19,
    }
    tens = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}
    for t, tv in tens.items():
        if t in raw:
            for o, ov in ones.items():
                if o in raw and o != "ten":
                    return str(tv + ov)
            return str(tv)
    for o, ov in ones.items():
        if re.search(rf"\b{o}\b", raw):
            return str(ov)
    return ""


def rewrite_backstory_third_person(story: str) -> str:
    """Setup backstories are third-person character history, not diary voice."""
    text = str(story or "").strip()
    if not text:
        return text
    # Only rewrite if clearly first-person dominant (case-insensitive)
    first = len(re.findall(r"\b(I|I'm|I've|I'd|I'll|me|my|mine)\b", text, flags=re.I))
    third = len(re.findall(r"\b(they|their|them|she|he|her|his)\b", text, flags=re.I))
    if first < 1:
        return text
    if first <= third and third > 0:
        return text
    out = text
    replacements = [
        (r"\bI've\b", "they've"),
        (r"\bI'm\b", "they're"),
        (r"\bI'd\b", "they'd"),
        (r"\bI'll\b", "they'll"),
        (r"\bI was\b", "they were"),
        (r"\bI am\b", "they are"),
        (r"\bI had\b", "they had"),
        (r"\bI have\b", "they have"),
        (r"\bI\b", "they"),
        (r"\bme\b", "them"),
        (r"\bmy\b", "their"),
        (r"\bmine\b", "theirs"),
    ]
    for pat, rep in replacements:
        out = re.sub(pat, rep, out, flags=re.I)
    out = re.sub(r"\bthey was\b", "they were", out, flags=re.I)
    out = re.sub(r"\bthey is\b", "they are", out, flags=re.I)
    return re.sub(r"\s+", " ", out).strip()


_FORMER_WORLD_MARKERS = (
    "former life",
    "previous life",
    "old world",
    "before dying",
    "before the transport",
    "before transport",
    "earth",
    "modern",
    "office",
    "desk",
    "commute",
    "apartment",
    "warehouse",
    "forklift",
    "hospital",
    "tokyo",
    "city job",
    "night-shift",
    "night shift",
    "smartphone",
    "near-future",
    "near future",
    "technician",
    "salaryman",
    "university",
    "high school",
    "truck",
    "logistics",
    "neon",
    "megacity",
    "corporate",
    "hospital stair",
    "blackout",
)

_TRANSPORT_MARKERS = (
    "died",
    "death",
    "killed",
    "truck",
    "accident",
    "crash",
    "summon",
    "portal",
    "transported",
    "transmigrat",
    "woke",
    "waking",
    "opened their eyes",
    "opened my eyes",
    "into the body",
    "into a body",
    "inside the body",
    "body of a",
    "ritual",
    "torn from",
    "yanked",
    "dumped into",
    "arrived through",
    "last night",
    "dirt road",
)

_NATIVE_FANTASY_PLOT_MARKERS = (
    "disgraced noble",
    "noble heir",
    "failed coup",
    "forced into exile",
    "wandering merchant",
    "town's festival",
    "towns festival",
    "guest right",
    "way back to their homeland",
    "collapsing empire",
    "sect outer disciple",
    "posing as a",
    "distant town",
    "court intrigue",
)

_BACKSTORY_SKILL_META_MARKERS = (
    "weak seed",
    "seed skill",
    "compounding",
    "growth math",
    "guest right",
    "once per day",
    "xp_to_next",
    "rank f",
    "system window",
    "status window",
)


def transmigration_story_score(story: str) -> dict[str, Any]:
    """Score whether a backstory actually covers former life + transport for transmigrated mode."""
    low = re.sub(r"\s+", " ", str(story or "").strip().lower())
    has_former = any(m in low for m in _FORMER_WORLD_MARKERS)
    has_transport = any(m in low for m in _TRANSPORT_MARKERS)
    # Must land somewhere / wake somewhere — death alone is not enough
    has_arrival_place = any(
        m in low
        for m in (
            "woke",
            "waking",
            "another world",
            "other world",
            "this world",
            "dirt road",
            "into the body",
            "inside the body",
            "opened their eyes",
            "found themselves",
            "found themself",
        )
    )
    native_plot = sum(1 for m in _NATIVE_FANTASY_PLOT_MARKERS if m in low)
    skill_meta = any(m in low for m in _BACKSTORY_SKILL_META_MARKERS)
    # "another world" alone at the end of a bolt-on sentence is weak if no former-life job
    bolted = "woke in another world with ordinary work habits" in low or (
        "torn from that life" in low and not has_former
    )
    ok = (
        has_former
        and has_transport
        and has_arrival_place
        and not skill_meta
        and native_plot < 2
        and not bolted
    )
    return {
        "ok": ok,
        "has_former_world": has_former,
        "has_transport": has_transport,
        "has_arrival_place": has_arrival_place,
        "native_fantasy_plot_hits": native_plot,
        "skill_meta": skill_meta,
        "bolted_generic_arrival": bolted,
    }


def build_transmigration_backstory(
    *,
    old_story: str = "",
    idea: str = "",
    world_style: str = "",
) -> str:
    """
    Canonical transmigrated structure (third person):
    1) life before transport  2) how transported  3) start at arrival / just before.
    """
    idea_l = re.sub(r"\s+", " ", str(idea or "").strip().lower())
    ws = re.sub(r"\s+", " ", str(world_style or "").strip().lower())
    old = re.sub(r"\s+", " ", str(old_story or "").strip())

    # Infer former vocation from idea / old text
    blob = f"{idea_l} {old.lower()}"
    if any(m in blob for m in ("forklift", "warehouse", "logistics")):
        former = (
            "In their former life they worked night shifts at a logistics warehouse, "
            "living by schedules, debt, and cargo marks rather than swords or titles"
        )
        transport = (
            "A truck accident ended that life; they woke on a dirt road at the edge of "
        )
    elif any(m in blob for m in ("desk", "office", "clerk", "salaryman")):
        former = (
            "In their former life they were an overworked office clerk who measured days in emails, "
            "commutes, and unpaid overtime"
        )
        transport = (
            "They died at a desk / on the way home and woke with those ordinary habits still intact at the edge of "
        )
    elif any(m in blob for m in ("maintenance", "technician", "engineer", "repair")):
        former = (
            "In their former life they were a maintenance technician who fixed machines and systems for a living, "
            "not magic or politics"
        )
        transport = (
            "They died on the job or mid-shift and opened their eyes in "
        )
    elif any(m in blob for m in ("student", "university", "high school", "college")):
        former = (
            "In their former life they were an ordinary student with exams, part-time work, and a small rented room"
        )
        transport = "A sudden accident tore them out of that life; they woke in "
    elif any(m in blob for m in ("summon", "ritual")):
        former = (
            "In their former life they were a city civilian on an ordinary street, not a warrior or chosen hero"
        )
        transport = (
            "A failed summoning ritual yanked them across worlds still wearing street clothes into "
        )
    else:
        former = (
            "In their former life they held an ordinary job in a modern city — rent, work shifts, and small debts, "
            "with no training for swords, sects, or empire games"
        )
        transport = (
            "Death or forced transport tore them out of that life; they woke in "
        )

    if "sect" in ws or "wuxia" in ws:
        place = "a sect compound's outer court in another world"
    elif "compound" in ws or "isekai" in ws:
        place = "a river-compound yard and dirt road in another world"
    elif "harbor" in ws or "port" in ws:
        place = "a rationed harbor district in another world"
    else:
        place = "an unfamiliar low-tech world they had never seen before"

    now = (
        f"{place}, with only the clothes and pocket scraps from before transport. "
        "The story starts at that arrival (or the hours just before), not as a native exile already living a local plot. "
        "They have no free hero kit — only ordinary habits and the need to learn which rules of this world can kill them."
    )
    return f"{former}. {transport}{now}"[:1600]


def ensure_isekai_arrival_beat(story: str, *, mode: str = "", idea: str = "", world_style: str = "") -> str:
    """
    For transmigrated mode: require former-world life + transport + arrival start.

    Never bolt a generic 'woke in another world' line onto a native fantasy plot
    (disgraced noble / festival guest / local quest). Rewrite those entirely.
    """
    text = str(story or "").strip()
    mode_l = str(mode or "").lower()
    idea_l = str(idea or "").lower()
    needs = "transmigrat" in mode_l or any(
        m in idea_l for m in ("isekai", "transmigrat", "summon", "truck", "another world", "other world")
    )
    # Reincarnated is a different shape — do not force truck-kun structure
    if "reincarnat" in mode_l or "reborn" in mode_l:
        return text
    if not needs:
        return text

    score = transmigration_story_score(text)
    if score["ok"]:
        return text

    # Broken: native fantasy plot, skill meta, missing former world, or bolted generic line
    return build_transmigration_backstory(
        old_story=text,
        idea=idea,
        world_style=world_style,
    )


def normalize_origin_package(
    fields: dict[str, Any],
    *,
    idea: str = "",
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Normalize mode/memory/story/previous-life fields for isekai & native starts."""
    out = dict(fields)
    dirty: dict[str, list[str]] = {}
    merged = {**(context or {}), **out}
    idea_s = str(idea or merged.get("_randomize_idea") or "")
    story = str(out.get("character_backstory", merged.get("character_backstory")) or "")
    mode_in = out.get("backstory_mode", merged.get("backstory_mode"))
    mem_in = out.get("memory_policy", merged.get("memory_policy"))

    if "backstory_mode" in out or "character_backstory" in out or idea_s:
        mode = normalize_backstory_mode(mode_in, story=story, idea=idea_s)
        if mode and mode != str(mode_in or "").strip():
            dirty.setdefault("backstory_mode", []).append("normalized_origin_mode")
            out["backstory_mode"] = mode
        elif "backstory_mode" in out:
            out["backstory_mode"] = mode or out.get("backstory_mode")

    mode_now = str(out.get("backstory_mode", merged.get("backstory_mode")) or "")
    if "memory_policy" in out or "backstory_mode" in out or "character_backstory" in out:
        mem = normalize_memory_policy(mem_in, mode=mode_now, story=story)
        if mem != str(mem_in or "").strip():
            dirty.setdefault("memory_policy", []).append("normalized_memory_policy")
        if "memory_policy" in out or dirty.get("memory_policy"):
            out["memory_policy"] = mem

    if "character_backstory" in out or story:
        rewritten = rewrite_backstory_third_person(story)
        # Strip skill/power-fantasy dumps from backstory prose
        if any(m in rewritten.lower() for m in _BACKSTORY_SKILL_META_MARKERS):
            dirty.setdefault("character_backstory", []).append("stripped_skill_meta_from_backstory")
            # Full rebuild if skill essay polluted the history
            rewritten = ""
        rewritten = ensure_isekai_arrival_beat(
            rewritten,
            mode=mode_now,
            idea=idea_s,
            world_style=str(out.get("world_style", merged.get("world_style")) or ""),
        )
        if rewritten != story:
            dirty.setdefault("character_backstory", []).append("normalized_origin_backstory")
            out["character_backstory"] = rewritten

    if "previous_life_age" in out or "previous_life_age" in merged:
        age_in = out.get("previous_life_age", merged.get("previous_life_age"))
        age = normalize_previous_life_age(age_in)
        # Only keep previous-life age for former-life modes
        if not any(m in mode_now.lower() for m in ("reincarnat", "transmigrat", "fragment")):
            age = ""
        if str(age_in or "").strip() != age:
            dirty.setdefault("previous_life_age", []).append("normalized_previous_life_age")
            out["previous_life_age"] = age
        elif "previous_life_age" in out:
            out["previous_life_age"] = age

    if "previous_life_sex" in out:
        if not any(m in mode_now.lower() for m in ("reincarnat", "transmigrat", "fragment")):
            if out.get("previous_life_sex"):
                dirty.setdefault("previous_life_sex", []).append("cleared_without_former_life")
            out["previous_life_sex"] = ""

    # world_style: reject slogan genres ("Compound Clerk's Fair Edge")
    if "world_style" in out:
        ws = str(out.get("world_style") or "").strip()
        low = ws.lower()
        if (
            len(ws) > 48
            or any(m in low for m in ("fair edge", "op mc", "compounding", "weak seed", "player agency"))
            or (ws.count(" ") >= 6 and not any(m in low for m in ("fantasy", "isekai", "kingdom", "sect", "cyber", "city")))
        ):
            dirty.setdefault("world_style", []).append("slogan_world_style")
            if "isekai" in idea_s.lower() or "isekai" in low:
                out["world_style"] = "isekai fantasy compound"
            else:
                out["world_style"] = "frontier dark fantasy"

    return out, dirty


def apply_consistency_lint(
    fields: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """
    Cross-field consistency pass.
    - race_magic_rules / race_ability_rules must not invent peoples absent from world_races
    - memory_policy should match backstory_mode + character_backstory wording
    - hair / facial_features / appearance stay de-duplicated and in the right fields
    - isekai/transmigrated origin package (mode/memory/story) is canonicalized
    """
    out = dict(fields)
    dirty: dict[str, list[str]] = {}
    merged = {**(context or {}), **out}

    # Origin package first so memory lint sees canonical modes
    origin_out, origin_dirty = normalize_origin_package(
        out,
        idea=str((context or {}).get("_randomize_idea") or (context or {}).get("idea") or ""),
        context=merged,
    )
    out.update(origin_out)
    for field, reasons in origin_dirty.items():
        dirty.setdefault(field, []).extend(reasons)
    merged = {**(context or {}), **out}

    look_out, look_dirty = normalize_look_fields(out, context=merged)
    out.update(look_out)
    for field, reasons in look_dirty.items():
        dirty.setdefault(field, []).extend(reasons)

    races_value = out.get("world_races", merged.get("world_races"))
    # When world_races changes, also repair race rules present in context so the form stays coherent.
    race_fields = ("race_magic_rules", "race_ability_rules")
    check_race_fields = [f for f in race_fields if f in out or "world_races" in out]
    if not check_race_fields and any(f in out for f in race_fields):
        check_race_fields = [f for f in race_fields if f in out]
    for field in check_race_fields:
        value = out.get(field, merged.get(field))
        if value is None or value == "":
            continue
        # Only rewrite fields already in this batch, or inject when world_races changed.
        if field not in out and "world_races" not in out:
            continue
        reasons = race_rules_mismatch_reasons(races_value, value)
        if not reasons:
            continue
        dirty[field] = list(reasons)
        out[field] = rebuild_race_rules(field, races_value, merged)

    # Memory / backstory / mode
    mem_keys = ("memory_policy", "character_backstory", "backstory_mode")
    if any(k in out or k in (context or {}) for k in mem_keys):
        mode = out.get("backstory_mode", merged.get("backstory_mode"))
        policy = out.get("memory_policy", merged.get("memory_policy"))
        story = out.get("character_backstory", merged.get("character_backstory"))
        # Only act when we can write memory_policy (in batch or world-level full sanitize)
        if "memory_policy" in out or any(k in out for k in ("character_backstory", "backstory_mode")):
            new_policy, reasons = resolve_memory_policy(mode, policy, story)
            if new_policy and reasons:
                dirty["memory_policy"] = list(reasons)
                out["memory_policy"] = new_policy

    return out, dirty


def structural_fallback(field: str, context: dict[str, Any] | None = None) -> Any:
    """Deterministic clean value when a structure field was contaminated."""
    ctx = context or {}
    intent = ctx.get("_compose_intent") if isinstance(ctx.get("_compose_intent"), dict) else {}
    if not intent and isinstance(ctx.get("_intent"), dict):
        intent = ctx["_intent"]
    genre = str(intent.get("genre") or ctx.get("world_style") or "").lower()
    isekai = bool(intent.get("isekai")) or "isekai" in genre
    keywords = " ".join(str(k) for k in (intent.get("keywords") or [])).lower()
    blob = f"{genre} {keywords} {ctx.get('start_location') or ''} {ctx.get('custom_style') or ''}".lower()
    coastal = any(k in blob for k in ("coast", "harbor", "harbour", "dock", "shallow", "sea", "fish", "port"))
    library = "library" in blob or "fragment" in blob

    table: dict[str, Any] = {
        "quest_style": (
            "job board and personal mysteries"
            if isekai
            else "emergent local work"
            if not library
            else "personal mysteries and archival errands"
        ),
        "faction_pressure": (
            "guild control and harbor politics"
            if coastal
            else "local disputes under quiet faction pressure"
            if not library
            else "archive orders and rival collectors"
        ),
        "economy": (
            "scarce dock markets"
            if coastal
            else "coin-driven with scarce rare goods"
            if isekai
            else "scarce"
        ),
        "npc_stat_scaling": "mostly weaker early, relative ranks later",
        "npc_skill_frequency": "some trained NPCs" if not isekai else "rare specialists and occasional trainers",
        "npc_density": "sparse with occasional faction patrols" if coastal or isekai else "moderate",
        "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
        "world_races": "human" if isekai or "human" in genre else "human, elf, dwarf",
        "difficulty": "normal",
        "death_rules": "downed, not deleted",
        "loot_rarity": "earned and uncommon",
        "tone": "curious, tense, grounded" if isekai else "grounded adventure",
        "tech_level": "near future" if "modern" in genre else "medieval",
        "magic_level": "common utility" if isekai else "rare",
        "system_style": "subtle blue-window system",
        "skill_style": (
            "training-heavy"
            if isinstance(intent.get("power_fantasy"), dict)
            and intent["power_fantasy"].get("growth") == "compounding"
            else "standard"
        ),
        "world_style": (intent.get("genre") or "frontier dark fantasy")[:120] if intent.get("genre") else "frontier dark fantasy",
        "custom_style": _clean_custom_style_fallback(intent, ctx),
        "race_magic_rules": (
            "Humans need formal training for most casting. Gifted lineages may hold innate sparks, "
            "but overall magic stays limited unless the setting says otherwise."
        ),
        "race_ability_rules": (
            "Humans learn broadly through practice. Other peoples may have modest innate senses or crafts; "
            "starting racial gifts stay small and never replace skills."
        ),
    }
    if field in table:
        return table[field]
    # Enums / booleans fall back via SETUP_RANDOMIZER elsewhere
    examples = field_contract(field).get("examples") or []
    if examples:
        return examples[0]
    return None


def _clean_custom_style_fallback(intent: dict[str, Any], ctx: dict[str, Any]) -> str:
    bits: list[str] = []
    if intent.get("isekai") or "isekai" in str(intent.get("genre") or "").lower():
        bits.append("Isekai RPG lean: new-world pressure with fair stakes.")
    if isinstance(intent.get("power_fantasy"), dict) and intent["power_fantasy"].get("system_ui"):
        bits.append("System UI may appear diegetically when game_system is on; keep windows short.")
    if isinstance(intent.get("power_fantasy"), dict) and intent["power_fantasy"].get("growth") == "compounding":
        bits.append("Start weak; growth compounds through play — never auto-win. Put timers in skill rules, not race rules.")
    dm = str(intent.get("dm_stance") or "").strip()
    if dm:
        bits.append(f"DM stance: {dm}")
    genre = str(intent.get("genre") or ctx.get("world_style") or "").strip()
    if genre and genre.lower() not in " ".join(bits).lower():
        bits.insert(0, f"Setting frame: {genre}.")
    return " ".join(bits)[:800] if bits else "Keep openings local and personal; reputation is earned."


def sanitize_field_value(
    field: str,
    value: Any,
    *,
    idea: str = "",
    context: dict[str, Any] | None = None,
) -> tuple[Any, list[str]]:
    """Return (clean_value, reasons). If clean, reasons is empty and value unchanged."""
    reasons = field_contamination_reasons(field, value, idea)
    if not reasons:
        return value, []
    clean = structural_fallback(field, {**(context or {}), "field": field})
    if clean is None:
        return value, reasons
    return clean, reasons


def sanitize_setup_fields(
    fields: dict[str, Any],
    *,
    idea: str = "",
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """Sanitize a randomizer result dict; returns (fields, {field: reasons})."""
    out = dict(fields)
    dirty: dict[str, list[str]] = {}
    ctx = {**(context or {}), **{k: v for k, v in out.items() if not str(k).startswith("_")}}
    for field, value in list(out.items()):
        if str(field).startswith("_") or field in ("notes",):
            continue
        clean, reasons = sanitize_field_value(field, value, idea=idea, context=ctx)
        if reasons:
            dirty[field] = reasons
            out[field] = clean
    # Second pass: cross-field consistency (races ↔ race rules; memory ↔ backstory).
    ctx = {**ctx, "idea": idea or ctx.get("idea") or "", "_randomize_idea": idea or ctx.get("_randomize_idea") or ""}
    out, cross = apply_consistency_lint(out, context=ctx)
    for field, reasons in cross.items():
        dirty.setdefault(field, []).extend(reasons)
    # Third pass: starter gear / clothes vs arrival logic (isekai vs reincarnation vs native).
    gear_keys = ("starter_equipment", "appearance", "backstory_mode", "character_backstory", "memory_policy")
    if any(k in out or k in ctx for k in gear_keys):
        try:
            from app.starter_logic import apply_starter_logic_to_setup

            intent = None
            if isinstance(ctx.get("_compose_intent"), dict):
                intent = ctx["_compose_intent"]
            elif isinstance(out.get("_compose_intent"), dict):
                intent = out["_compose_intent"]
            merged_for_gear = {**ctx, **out}
            gear_in = {
                k: merged_for_gear.get(k)
                for k in (
                    "starter_equipment",
                    "appearance",
                    "backstory_mode",
                    "memory_policy",
                    "character_backstory",
                    "world_style",
                    "tech_level",
                    "magic_level",
                    "special_ability_origin",
                )
            }
            gear_out, gear_dirty = apply_starter_logic_to_setup(gear_in, intent=intent)
            for field, reason in gear_dirty.items():
                dirty.setdefault(field, []).append(reason)
                out[field] = gear_out.get(field)
            if gear_out.get("_starter_logic"):
                out["_starter_logic"] = gear_out["_starter_logic"]
        except Exception:
            pass
    # Fourth pass: board-wide duplicates / patterns / inconsistencies.
    try:
        from app.setup_crosscheck import crosscheck_setup_fields

        report = crosscheck_setup_fields(
            out,
            idea=idea or str(ctx.get("_randomize_idea") or ""),
            context=ctx,
            repair=True,
        )
        if isinstance(report.get("fields"), dict):
            for key, value in report["fields"].items():
                if str(key).startswith("_"):
                    continue
                if out.get(key) != value:
                    dirty.setdefault(key, []).append("setup_crosscheck")
                    out[key] = value
        out["_setup_crosscheck"] = {
            "ok": bool(report.get("ok")),
            "summary": report.get("summary") or {},
            "findings": list(report.get("findings") or [])[:40],
        }
    except Exception:
        pass
    return out, dirty
