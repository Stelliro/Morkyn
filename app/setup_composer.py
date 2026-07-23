"""Setup composer tree: load-order phases, field contracts, intent compile helpers.

The Randomize walk is a dependency tree, not a flat stamp of the idea box.
Phase order is topological; each field only receives matching intent keys.
"""

from __future__ import annotations

import re
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
        "forbidden": "Concrete character history only; not a setup slogan.",
    },
    "hair": {
        "kind": "short_phrase",
        "intent_keys": ["genre", "keywords", "tone"],
        "forbidden": "Hair only: length, color, style. Not face, clothes, or backstory.",
        "examples": [
            "short brown hair",
            "long silver braid",
            "messy black hair",
            "cropped sandy hair",
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
            "grey eyes, tired lids, square jaw",
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
            "Must pass arrival logic: isekai/summon = only clothes/pockets from transport; "
            "reincarnated = this-life gear only; native = life-justified gear. "
            "No free shields/swords/armor/god gifts at isekai arrival — those come AFTER Start. "
            "No legendaries."
        ),
        "examples": [
            "worn coat, pocket notebook, copper coins, water flask",
            "plain work clothes, work gloves, small tool pouch",
            "travel cloak, empty satchel, wooden charm, heel of bread",
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
        "allowed_values": ["none", "acquired", "innate"],
        "intent_keys": ["power_fantasy", "isekai"],
        "forbidden": "Return only none, acquired, or innate.",
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

    # Isekai / portal
    if any(k in text for k in ("isekai", "another world", "other world", "transmigrat", "reincarnat", "summoned to", "transported to")):
        out["isekai"] = True
        out["adapter_hint"] = "isekai_rpg"
        if "reincarn" in text or "reborn" in text:
            out["portal_or_rebirth"] = "same_world_rebirth" if "same world" in text else "other_world"
        elif "transmigrat" in text or "transported" in text or "summoned" in text:
            out["portal_or_rebirth"] = "other_world"
        if not out.get("genre"):
            out["genre"] = "isekai dark fantasy" if "dark" in text else "isekai fantasy"

    # System UI
    if any(k in text for k in ("system", "status window", "skill ui", "blue window", "game system", "status panel", "level up")):
        out["power_fantasy"]["system_ui"] = True
        if out.get("adapter_hint") in ("", "default"):
            out["adapter_hint"] = "system_rpg"

    # Power fantasy growth
    if any(k in text for k in ("compounding", "compounds", "compound", "exponential", "snowball", "stacking growth", "op later")):
        out["power_fantasy"]["growth"] = "compounding"
    if any(k in text for k in ("near useless", "useless skill", "weak start", "starts weak", "powerless", "bottom tier", "rank f")):
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

    # Skill summary from idea
    if "one weak skill" in text or "single skill" in text or "one skill" in text:
        out["power_fantasy"]["skill_summary"] = out["power_fantasy"].get("skill_summary") or "one weak skill that can snowball"

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
        set_if_free("new_skill_frequency", "rare")  # one skill fantasy — not a skill soup
        set_if_free("skill_levels_enabled", True)
        set_if_free("proficiency_system", True)
        set_if_free("skill_style", "training-heavy")
        # Structural skeleton only — LLM expands domain + concrete math during custom_skills roll.
        # Never hardcode Observation/weather domains here.
        set_if_free(
            "custom_skills",
            "ONE_SKILL_FRAME: exactly one weak seed skill/ability domain (domain chosen later; never default "
            "weather/observation); starts near-useless (rank F / level 1); compounds only through use, "
            "training, and risk; track ranks via subtle system UI when on, else DM notes; XP from practice, "
            "mentors, and high-risk successes; put calculable XP/rank formulas on the ability Growth Math "
            "field; soft caps until breakthroughs; no second combat/speech toolkit at start",
        )
        if not str(pf.get("skill_summary") or "").strip():
            # Stash on intent for UI / later ability alignment (not a form field)
            intent.setdefault("power_fantasy", {})
            if isinstance(intent.get("power_fantasy"), dict):
                intent["power_fantasy"]["skill_summary"] = (
                    "One compounding seed skill: weak start, trackable ranks, growth_math on ability, use/risk/training"
                )

    if start_power in ("near_useless", "weak"):
        set_if_free("special_ability_origin", "acquired")
        # abilities filled later by walk; origin acquired + locked weak seed
        if "custom_skills" not in fields and "custom_skills" not in locked:
            set_if_free(
                "custom_skills",
                "ONE_SKILL_FRAME: exactly one weak seed skill (domain varies); near-useless at start; "
                "compounds via practice/risk; track levels (system or DM); formulas live on ability Growth Math; "
                "no broad toolkit",
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
            set_if_free("memory_policy", "remembers former life")
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

    edge = str(intent.get("edge") or "").lower()
    if "injur" in edge:
        set_if_free("death_rules", "lasting injuries")
    if "permadeath" in edge:
        set_if_free("death_rules", "permadeath threat")
    if "scarce" in edge or "loot" in edge:
        set_if_free("loot_rarity", "scarce mundane")

    genre = str(intent.get("genre") or "").strip()
    if genre and "world_style" not in locked:
        fields["world_style"] = genre[:120]

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


def weak_skill_seed_spec(
    playthrough_options: dict[str, Any] | None = None,
    session_theme: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    When setup wants a near-useless start / compounding seed, return one skill row to insert.
    Prefer an explicit name in custom_skills; else a modest Observation seed.
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
    )
    if not wants_seed:
        return None

    name = ""
    # Named seed: "weak seed skill: Foo" / "One weak seed skill: Observation"
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
    if not name:
        summary = str(pf.get("skill_summary") or "").strip()
        m3 = re.search(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]+)?)\b", summary)
        if m3 and m3.group(1).lower() not in {"the", "and", "with"}:
            name = m3.group(1)
    if not name:
        name = "Observation"

    notes = (
        "Weak opening seed: nearly useless now; can compound through careful practice, training, and risk. "
        "Not a free power spike."
    )[:700]
    return {"name": name[:80], "value": 1, "notes": notes}


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


def apply_consistency_lint(
    fields: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, list[str]]]:
    """
    Cross-field consistency pass.
    - race_magic_rules / race_ability_rules must not invent peoples absent from world_races
    - memory_policy should match backstory_mode + character_backstory wording
    """
    out = dict(fields)
    dirty: dict[str, list[str]] = {}
    merged = {**(context or {}), **out}

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
    return out, dirty
