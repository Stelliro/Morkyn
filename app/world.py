from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
import random
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from app.db import connect, row_to_dict, rows_to_dicts
from app.llm import LlmError, context_window_tokens, fallback_turn, generate_input_suggestions, generate_turn

HISTORY_SUMMARY_PATH = Path(os.getenv("AI_RPG_HISTORY_SUMMARY", "data/history_summaries.jsonl"))
SOURCE_INDEX_DIR = Path(os.getenv("AI_RPG_SOURCE_INDEX", "data/source_index"))
SOURCE_INDEX_MANIFEST = SOURCE_INDEX_DIR / "manifest.json"
MODEL_TRACE_DIR = Path(os.getenv("AI_RPG_MODEL_TRACE_DIR", "data/model_traces"))
CONSOLIDATED_FACTS_PATH = Path(os.getenv("AI_RPG_CONSOLIDATED_FACTS", "data/consolidated_facts.jsonl"))
CAMPAIGN_SLOTS_DIR = Path(os.getenv("AI_RPG_CAMPAIGN_SLOTS", "data/campaign_slots"))
MEMORY_CONSOLIDATE_KEEP_SUMMARIES = max(4, int(os.getenv("AI_RPG_MEMORY_KEEP_SUMMARIES", "12")))
MEMORY_CONSOLIDATE_MAX_FACTS = max(20, int(os.getenv("AI_RPG_MEMORY_MAX_FACTS", "200")))
GM_OFFSCREEN_INTERVAL = max(2, int(os.getenv("AI_RPG_GM_OFFSCREEN_INTERVAL", "8")))
WORLD_TABLES = [
    "locations",
    "player",
    "npcs",
    "relationships",
    "inventory",
    "equipment_slots",
    "inventory_capacity_modifiers",
    "player_skills",
    "abilities",
    "events",
    "conversations",
    "response_drafts",
    "aliases",
    "player_aliases",
    "karma_history",
    "turn_summaries",
    "model_logs",
    "verification_memory",
    "journal",
    "pacing",
    "settings",
    "gm_notes",
    "gm_events",
]
OPENING_SCENE_INPUT = (
    "__opening_scene_request__: Begin the playthrough before the player acts. "
    "Establish the immediate situation, include concrete hooks, and wait for the player's first choice."
)
OPENING_SCENE_JOURNAL = "Opening scene: the model introduced the initial situation before the player acted."
CONTINUE_SCENE_INPUT = (
    "__continue_scene_request__: The player did not enter an action. Continue the current scene just enough to "
    "give more context, pressure, or openings, without choosing for the player."
)
CONTINUE_SCENE_JOURNAL = "Continue: the model advanced the current situation without a player action."
AUTOINC_TABLES = [
    "locations",
    "npcs",
    "relationships",
    "inventory",
    "equipment_slots",
    "inventory_capacity_modifiers",
    "player_skills",
    "abilities",
    "events",
    "conversations",
    "response_drafts",
    "aliases",
    "player_aliases",
    "karma_history",
    "turn_summaries",
    "model_logs",
    "verification_memory",
    "journal",
    "gm_events",
]
RESTORE_ORDER = [
    "turn_snapshots",
    "response_drafts",
    "model_logs",
    "verification_memory",
    "aliases",
    "equipment_slots",
    "inventory_capacity_modifiers",
    "player_aliases",
    "karma_history",
    "turn_summaries",
    "conversations",
    "relationships",
    "events",
    "abilities",
    "player_skills",
    "inventory",
    "npcs",
    "player",
    "locations",
    "journal",
    "pacing",
    "settings",
    "gm_notes",
    "gm_events",
]


GROWTH_MULTIPLIERS = {
    "very slow": 0.25,
    "slow": 0.5,
    "normal": 1.0,
    "fast": 1.5,
    "very fast": 2.0,
}

DEFAULT_EQUIPMENT_SLOTS = [
    ("HEAD", "Head", "head", 1, ["helmet", "hat", "mask", "headgear"], 10),
    ("NECK", "Neck", "necklace", 3, ["necklace", "amulet", "collar", "scarf"], 20),
    ("TORSO", "Armor", "armor", 1, ["armor", "robe", "coat", "clothing"], 30),
    ("UNDER", "Underarmor", "underarmor", 1, ["underarmor", "undersuit", "lining"], 40),
    ("BACK", "Back", "back", 1, ["cloak", "backpack", "cape", "wings"], 50),
    ("MAIN", "Main Hand", "hand", 1, ["weapon", "tool", "focus"], 60),
    ("OFF", "Off Hand", "hand", 1, ["shield", "weapon", "tool", "focus"], 70),
    ("WRIST", "Wrists", "wrist", 4, ["bracelet", "bracer", "wrist accessory"], 80),
    ("FINGER", "Fingers", "ring", 10, ["ring", "finger accessory"], 90),
    ("WAIST", "Waist", "waist", 1, ["belt", "sash", "pouch", "sheath"], 100),
    ("FEET", "Feet", "feet", 1, ["boots", "shoes", "greaves"], 110),
    ("DECAL", "Decals", "decal", 8, ["decal", "insignia", "sigil", "badge", "cosmetic"], 120),
]

TURN_CONTEXT_PLANNER_VERSION = "V0.1.0"
MECHANICS_CONTEXT_VERSION = "V0.1.0"
VERIFICATION_MEMORY_VERSION = "V0.1.0"
VERIFICATION_MEMORY_CONFIDENCE_MIN = 0.86
VERIFICATION_MEMORY_LIMIT = 24
EVENT_PERSISTENCE_VALUES = {"persistent", "temporary", "recurring", "traveling", "background"}
TURN_REFERENCE_PATTERN = re.compile(r"(?:@([A-Z]{1,3})|#(L\d+)|!(I\d+)|&(E\d+)|\[\[([A-Z]{1,3}|L\d+|I\d+|E\d+)\]\])", re.IGNORECASE)
COMBAT_ATTACK_KEYWORDS = {
    "attack", "fight", "punch", "kick", "stab", "slash", "shoot", "strike", "hit", "swing", "thrust", "jab", "smash", "bash", "club", "slice", "cut", "fire", "throw",
}
UNARMED_ATTACK_KEYWORDS = {"punch", "kick", "headbutt", "grapple", "shove", "tackle", "elbow", "knee"}
STAT_ALIASES = {
    "strength": {"strength", "str", "power", "might", "attack", "melee", "force"},
    "defense": {"defense", "defence", "armor", "armour", "endurance", "toughness", "resilience", "guard"},
    "dodge": {"dodge", "evasion", "agility", "speed", "reflex", "reflexes", "mobility"},
    "damage": {"damage", "weapon_damage", "attack_damage", "power", "impact"},
}
RARITY_ATTACK_BONUS = {
    "common": 0,
    "mundane": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 4,
    "legendary": 7,
    "unique": 3,
}
TURN_INTENT_KEYWORDS = {
    "conversation": {
        "ask", "talk", "tell", "say", "speak", "question", "answer", "convince", "persuade", "negotiate", "threaten", "lie", "deceive", "bribe", "argue",
    },
    "claim_check": {"claim", "said", "told", "promised", "allowed", "permission", "prove", "verify", "truth", "rumor"},
    "combat": {"attack", "fight", "punch", "kick", "stab", "slash", "shoot", "cast", "strike", "block", "dodge", "parry", "ambush"},
    "investigation": {"look", "inspect", "search", "listen", "examine", "investigate", "watch", "read", "study", "track", "peek", "scan"},
    "travel": {"go", "move", "walk", "run", "travel", "head", "enter", "leave", "return", "approach", "climb", "cross", "follow"},
    "trade": {"buy", "sell", "pay", "trade", "barter", "shop", "hire", "rent", "price", "cost"},
    "inventory": {"use", "equip", "wear", "drop", "take", "grab", "loot", "craft", "store", "pack", "unpack", "draw", "hold"},
    "training": {"train", "practice", "learn", "teach", "mentor", "study", "drill", "improve"},
    "rest": {"sleep", "rest", "wait", "pause", "camp", "recover", "heal"},
    "ability": {"ability", "power", "skill", "spell", "magic", "system", "status", "quest", "window"},
}
TURN_INTENT_LIMITS = {
    "opening_scene": {"locations": 4, "local_npcs": 6, "remote_npcs": 2, "local_events": 4, "events": 8, "conversations": 4, "response_drafts": 2, "summaries": 6, "history": 8, "sources": 6, "relationships": 8, "recognition": 4},
    "continue_scene": {"locations": 6, "local_npcs": 8, "remote_npcs": 2, "local_events": 5, "events": 10, "conversations": 8, "response_drafts": 3, "summaries": 8, "history": 10, "sources": 8, "relationships": 10, "recognition": 5},
    "conversation": {"locations": 6, "local_npcs": 12, "remote_npcs": 3, "local_events": 6, "events": 16, "conversations": 28, "response_drafts": 8, "summaries": 12, "history": 12, "sources": 10, "relationships": 18, "recognition": 8},
    "claim_check": {"locations": 6, "local_npcs": 12, "remote_npcs": 3, "local_events": 8, "events": 24, "conversations": 32, "response_drafts": 12, "summaries": 14, "history": 14, "sources": 12, "relationships": 18, "recognition": 8},
    "combat": {"locations": 5, "local_npcs": 12, "remote_npcs": 2, "local_events": 6, "events": 12, "conversations": 8, "response_drafts": 4, "summaries": 10, "history": 10, "sources": 8, "relationships": 14, "recognition": 6},
    "investigation": {"locations": 8, "local_npcs": 10, "remote_npcs": 3, "local_events": 8, "events": 18, "conversations": 14, "response_drafts": 5, "summaries": 14, "history": 14, "sources": 12, "relationships": 12, "recognition": 6},
    "travel": {"locations": 12, "local_npcs": 8, "remote_npcs": 4, "local_events": 5, "events": 14, "conversations": 8, "response_drafts": 3, "summaries": 10, "history": 10, "sources": 10, "relationships": 10, "recognition": 6},
    "trade": {"locations": 6, "local_npcs": 10, "remote_npcs": 2, "local_events": 5, "events": 12, "conversations": 16, "response_drafts": 5, "summaries": 10, "history": 10, "sources": 8, "relationships": 12, "recognition": 5},
    "inventory": {"locations": 5, "local_npcs": 8, "remote_npcs": 2, "local_events": 5, "events": 12, "conversations": 8, "response_drafts": 3, "summaries": 10, "history": 10, "sources": 8, "relationships": 8, "recognition": 4},
    "training": {"locations": 6, "local_npcs": 10, "remote_npcs": 3, "local_events": 5, "events": 12, "conversations": 12, "response_drafts": 3, "summaries": 12, "history": 12, "sources": 8, "relationships": 12, "recognition": 5},
    "rest": {"locations": 5, "local_npcs": 6, "remote_npcs": 2, "local_events": 5, "events": 10, "conversations": 6, "response_drafts": 2, "summaries": 8, "history": 8, "sources": 6, "relationships": 8, "recognition": 4},
    "ability": {"locations": 6, "local_npcs": 8, "remote_npcs": 2, "local_events": 5, "events": 12, "conversations": 10, "response_drafts": 4, "summaries": 12, "history": 12, "sources": 8, "relationships": 10, "recognition": 5},
    "general": {"locations": 8, "local_npcs": 8, "remote_npcs": 3, "local_events": 6, "events": 16, "conversations": 14, "response_drafts": 5, "summaries": 12, "history": 12, "sources": 10, "relationships": 12, "recognition": 6},
}
ACTION_SEGMENT_RULES = {
    "opening_scene": [
        ("world_setup", "Read setup identity, current location, playthrough options, and nearby hooks; establish the world without choosing for the player.", ["setup", "opening", "location", "identity", "hooks"]),
        ("starting_limits", "Respect starting health, derived equipment effects, inventory limits, ability origin, and the no-default-skills rule.", ["health", "effective_stats", "inventory", "abilities", "skills"]),
    ],
    "continue_scene": [
        ("immediate_pressure", "Use current location, nearby NPCs/events, hidden clocks, and the last summaries to advance only a small beat.", ["location", "npc", "events", "pressure", "choice"]),
    ],
    "travel": [
        ("movement_limits", "Compare the attempted route with current health, derived movement stats/abilities, carried load, local terrain, weather, exits, and active events.", ["route", "terrain", "weather", "carry", "fatigue", "speed"]),
        ("environment_pressure", "Consider hazards, visibility, witnesses, local rules, and whether temporary events should persist or fade when leaving.", ["hazard", "visibility", "event", "witness", "departure"]),
    ],
    "combat": [
        ("combat_opposition", "Use mechanics_context first when present, then compare player health, effective_stats, relevant skills, and abilities against target NPC rank, stat_profile, skill_profile, combat_profile, allies, and terrain; equipment effects are already folded into those player fields.", ["mechanics_context", "rank", "stat_profile", "skill_profile", "combat_profile", "effective_stats", "abilities", "terrain"]),
        ("damage_and_consequence", "Use deterministic damage/health resolution from mechanics_context when present, then scale stamina, karma visibility, noise, witnesses, loot, and escape routes from the focused facts only.", ["mechanics_context", "damage", "health", "stamina", "karma", "witness", "noise", "escape"]),
    ],
    "ability": [
        ("ability_constraints", "Read the named/relevant ability, lock state, base_description, prerequisites, cost, player health/effective_stats, race/magic rules, and target resistance; equipment-granted abilities are already in abilities while equipped.", ["ability", "cost", "prerequisite", "locked", "magic", "target"]),
        ("effect_scope", "Keep the effect inside stored limits and update ability details only when play reveals a justified cost, limit, or unlock path.", ["scope", "cooldown", "resource", "unlock", "limitation"]),
    ],
    "inventory": [
        ("item_handling", "Use focused inventory, equipped slots, containers, carry capacity, item metadata, and whether the action adds, removes, equips, crafts, or stores an item.", ["item", "equip", "container", "weight", "slots", "craft"]),
    ],
    "trade": [
        ("trade_constraints", "Use gold, economy, local NPC role, item rarity, relationship/trust, and inventory capacity before changing money or goods.", ["gold", "price", "rarity", "merchant", "trust", "capacity"]),
    ],
    "conversation": [
        ("npc_knowledge", "Use the addressed NPC's known facts, personality, likes/principles/dislikes, relationship, recognition, and indexed conversations only.", ["npc", "knowledge", "trust", "principles", "recognition", "relationship"]),
    ],
    "claim_check": [
        ("evidence_check", "Search focused conversations, events, response drafts, and explicit references before accepting a claim as true.", ["claim", "permission", "evidence", "conversation", "event", "verdict"]),
    ],
    "investigation": [
        ("environment_scan", "Use current location details, nearby events/NPCs, relevant abilities, senses, light, tracks, concealment, and relevant source hits.", ["inspect", "ability", "light", "tracks", "hidden", "source"]),
    ],
    "training": [
        ("growth_requirements", "Use demonstrated actions, mentors, tools, custom skill rules, current skills, and progression speed before granting skill or XP changes.", ["practice", "mentor", "training", "skill", "progression", "xp"]),
    ],
    "rest": [
        ("rest_safety", "Use current location safety, active events, injuries, watches, supplies, and hidden clocks before recovery or time passage.", ["safety", "sleep", "injury", "supplies", "time", "ambush"]),
    ],
    "general": [
        ("focused_facts", "Use explicit references, current location, nearby actors, and relevant source hits; do not mine unrelated player/world data.", ["focus", "refs", "nearby", "relevant", "limits"]),
    ],
}


def norm_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name.strip())
    return cleaned[:100]


def _ability_origin(value: Any, has_requested_abilities: bool = False) -> str:
    cleaned = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if cleaned in {"none", "no abilities", "no special abilities"}:
        return "none"
    if cleaned in {"innate", "born with", "inborn", "inherent", "natural"}:
        return "innate"
    if cleaned in {"acquired", "gained", "learned", "earned", "unlocked"}:
        return "acquired"
    return "acquired" if has_requested_abilities else "none"


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _scaled_delta(delta: int, speed: str, multiplier: float | None = None) -> int:
    if delta == 0:
        return 0
    active_multiplier = multiplier if multiplier and multiplier > 0 else GROWTH_MULTIPLIERS.get(str(speed or "normal").lower(), 1.0)
    active_multiplier = max(0.01, min(100.0, float(active_multiplier)))
    scaled = int(round(delta * active_multiplier))
    if scaled == 0:
        return 1 if delta > 0 else -1
    return scaled


def alpha_code(number: int) -> str:
    result = ""
    n = max(1, number)
    while n:
        n -= 1
        result = chr(65 + (n % 26)) + result
        n //= 26
    return result


def _max_id(conn, table: str) -> int:
    row = conn.execute(f"SELECT COALESCE(MAX(id), 0) AS value FROM {table}").fetchone()
    return int(row["value"])


def _next_code(conn, table: str, prefix: str) -> str:
    return f"{prefix}{_max_id(conn, table) + 1}"


def _json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else value
    except json.JSONDecodeError:
        return fallback


def _settings(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result: dict[str, Any] = {}
    for row in rows:
        result[row["key"]] = _json(row["value"], row["value"])
    return result


def _float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int_from_any(value: Any, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _playthrough_options(state: dict[str, Any]) -> dict[str, Any]:
    return ((state.get("settings") or {}).get("playthrough_options") or {})


def _rank_labels(options: dict[str, Any]) -> list[str]:
    raw = str(options.get("rank_scale") or "F,E,D,C,B,A,S,SS,SSS")
    labels = [part.strip().upper() for part in raw.split(",") if part.strip()]
    return labels or ["F", "E", "D", "C", "B", "A", "S", "SS", "SSS"]


def _rank_index_from_text(value: Any, labels: list[str]) -> int | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    by_label = {label: index for index, label in enumerate(labels)}
    if text in by_label:
        return by_label[text]
    for label in sorted(labels, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(label)}(?![A-Z0-9])", text):
            return by_label[label]
    return None


def _rank_index(value: Any, options: dict[str, Any]) -> int:
    labels = _rank_labels(options)
    found = _rank_index_from_text(value, labels)
    return clamp(found if found is not None else 0, 0, max(0, len(labels) - 1))


def _stat_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _numeric_stat_total(profile: dict[str, Any], aliases: set[str]) -> int:
    total = 0.0
    for key, value in profile.items():
        normalized = _stat_key(key)
        if normalized not in aliases and not any(alias in normalized for alias in aliases):
            continue
        if isinstance(value, list):
            values = value
        else:
            values = [value]
        for item in values:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                total += float(item)
            elif isinstance(item, str) and re.fullmatch(r"[-+]?\d+(?:\.\d+)?", item.strip()):
                total += float(item)
    return int(round(total))


def _profile_rank_adjustment(profile: dict[str, Any], aliases: set[str], labels: list[str], base_rank_index: int) -> int:
    parts: list[str] = []
    for key, value in profile.items():
        normalized = _stat_key(key)
        if normalized in aliases or any(alias in normalized for alias in aliases):
            parts.append(str(value or ""))
    text = " ".join(parts).lower()
    if not text:
        return 0
    ranked = _rank_index_from_text(text, labels)
    if ranked is not None:
        return clamp((ranked - base_rank_index) * 2, -8, 12)
    adjustment = 0
    if any(marker in text for marker in ("very high", "elite", "exceptional", "overwhelming")):
        adjustment += 4
    elif any(marker in text for marker in ("high", "strong", "fast", "tough", "above")):
        adjustment += 2
    if any(marker in text for marker in ("very low", "weak", "poor", "frail", "slow")):
        adjustment -= 3
    elif any(marker in text for marker in ("low", "below")):
        adjustment -= 2
    return adjustment


def _difficulty_combat_bias(options: dict[str, Any]) -> int:
    difficulty = str(options.get("difficulty") or "normal").lower()
    scaling = str(options.get("npc_stat_scaling") or "relative ranks").lower()
    bias = 0
    if "easy" in difficulty:
        bias -= 1
    elif "hard" in difficulty:
        bias += 1
    elif "brutal" in difficulty or "deadly" in difficulty:
        bias += 2
    if "mostly weaker" in scaling:
        bias -= 1
    elif "near player" in scaling:
        bias += 0
    elif "elite" in scaling:
        bias += 2
    return bias


def _all_npcs_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [npc for location in state.get("locations", []) for npc in location.get("npcs", [])]


def _local_npcs_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    current_code = (state.get("current_location") or {}).get("code")
    return [npc for location in state.get("locations", []) if location.get("code") == current_code for npc in location.get("npcs", [])]


def _combat_profile_from_npc(npc: dict[str, Any]) -> dict[str, Any]:
    max_health = _int_from_any(npc.get("max_health"), 0)
    health = clamp(_int_from_any(npc.get("health"), max_health), 0, max(0, max_health)) if max_health else 0
    return {
        "initialized": max_health > 0,
        "health": health,
        "max_health": max_health,
        "attack_min": _int_from_any(npc.get("attack_min"), 0),
        "attack_max": _int_from_any(npc.get("attack_max"), 0),
        "defense": _int_from_any(npc.get("defense"), 0),
        "dodge": _int_from_any(npc.get("dodge"), 0),
    }


def _derive_npc_combat_profile(npc: dict[str, Any], state: dict[str, Any]) -> dict[str, int]:
    options = _playthrough_options(state)
    labels = _rank_labels(options)
    player = state.get("player") or {}
    player_level = clamp(_int_from_any(player.get("level"), 1), 1, 100)
    base_rank_index = _rank_index(npc.get("rank"), options)
    profile = npc.get("stat_profile") or {}
    if not isinstance(profile, dict):
        profile = _json(profile, {}) if isinstance(profile, str) else {}
    bias = _difficulty_combat_bias(options)
    rank_pressure = max(0, base_rank_index + bias)
    level_basis = max(1, player_level + bias)
    strength = clamp(
        4 + level_basis * 2 + rank_pressure * 3 + _profile_rank_adjustment(profile, STAT_ALIASES["strength"], labels, base_rank_index),
        1,
        999,
    )
    defense = clamp(
        2 + level_basis + rank_pressure * 2 + _profile_rank_adjustment(profile, STAT_ALIASES["defense"], labels, base_rank_index),
        0,
        999,
    )
    dodge = clamp(
        2 + level_basis + rank_pressure * 2 + _profile_rank_adjustment(profile, STAT_ALIASES["dodge"], labels, base_rank_index),
        0,
        999,
    )
    max_health = clamp(10 + level_basis * 5 + rank_pressure * 8 + defense * 2, 1, 9999)
    attack_min = clamp(1 + strength // 5 + rank_pressure // 2, 1, 999)
    attack_max = clamp(max(attack_min + 1, attack_min + 2 + strength // 3 + rank_pressure), attack_min, 999)
    existing = _combat_profile_from_npc(npc)
    if existing["max_health"] > 0:
        max_health = existing["max_health"]
        health = clamp(existing["health"], 0, max_health)
    else:
        health = max_health
    return {
        "health": health,
        "max_health": max_health,
        "attack_min": existing["attack_min"] or attack_min,
        "attack_max": existing["attack_max"] or attack_max,
        "defense": existing["defense"] or defense,
        "dodge": existing["dodge"] or dodge,
    }


def _combat_action_kind(player_input: str) -> str:
    tokens = _tokens(player_input)
    if tokens & COMBAT_ATTACK_KEYWORDS:
        return "player_attack"
    return "combat_positioning"


def _combat_target_candidates(state: dict[str, Any], player_input: str, refs: dict[str, list[str]]) -> list[dict[str, Any]]:
    all_npcs = _all_npcs_from_state(state)
    if refs.get("npcs"):
        referenced = {code.upper() for code in refs.get("npcs", [])}
        return [npc for npc in all_npcs if str(npc.get("code") or "").upper() in referenced]
    query = _tokens(player_input)
    local_npcs = _local_npcs_from_state(state)
    scored = [(_score_text(query, npc.get("code"), npc.get("name"), npc.get("summary"), npc.get("role")), index, npc) for index, npc in enumerate(local_npcs)]
    if any(score for score, _index, _npc in scored):
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return [npc for score, _index, npc in scored if score > 0]
    return local_npcs


def _clear_combat_target(state: dict[str, Any], player_input: str, refs: dict[str, list[str]]) -> dict[str, Any] | None:
    candidates = _combat_target_candidates(state, player_input, refs)
    if not candidates:
        return None
    if refs.get("npcs"):
        return candidates[0]
    query = _tokens(player_input)
    scored = [(_score_text(query, npc.get("code"), npc.get("name"), npc.get("summary"), npc.get("role")), npc) for npc in candidates]
    scored = [item for item in scored if item[0] > 0]
    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        if len(scored) == 1 or scored[0][0] > scored[1][0]:
            return scored[0][1]
    if len(candidates) == 1:
        return candidates[0]
    hostile = [npc for npc in candidates if str(npc.get("attitude") or "").lower() in {"hostile", "aggressive", "violent"}]
    return hostile[0] if len(hostile) == 1 else None


def _ensure_combat_profiles_for_input(state: dict[str, Any], player_input: str) -> bool:
    intent, _secondary = _turn_intent(player_input)
    if intent != "combat":
        return False
    refs = _explicit_turn_references(player_input)
    candidates = _combat_target_candidates(state, player_input, refs)[:4]
    if not candidates:
        return False
    changed = False
    with connect() as conn:
        for npc in candidates:
            combat = _combat_profile_from_npc(npc)
            if combat["max_health"] > 0 and combat["attack_max"] > 0:
                continue
            derived = _derive_npc_combat_profile(npc, state)
            conn.execute(
                """
                UPDATE npcs
                SET health = ?, max_health = ?, attack_min = ?, attack_max = ?, defense = ?, dodge = ?
                WHERE code = ?
                """,
                (
                    derived["health"],
                    derived["max_health"],
                    derived["attack_min"],
                    derived["attack_max"],
                    derived["defense"],
                    derived["dodge"],
                    npc.get("code"),
                ),
            )
            changed = True
    return changed


def _equipped_items_by_slot(inventory: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    equipped: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        slot = str(item.get("equipped_slot") or "").strip().upper()
        if slot:
            equipped.setdefault(slot, []).append(item)
    return equipped


def _selected_attack_weapon(state: dict[str, Any], player_input: str, refs: dict[str, list[str]]) -> dict[str, Any] | None:
    inventory = state.get("inventory") or []
    tokens = _tokens(player_input)
    if tokens & UNARMED_ATTACK_KEYWORDS:
        return None
    referenced_items = {code.upper() for code in refs.get("items", [])}
    for item in inventory:
        if str(item.get("code") or "").upper() in referenced_items:
            return item
    equipped = _equipped_items_by_slot(inventory)
    for slot in ("MAIN", "OFF"):
        for item in equipped.get(slot, []):
            item_type = str(item.get("item_type") or "").lower()
            if item_type in {"weapon", "tool", "focus"}:
                return item
    return None


def _item_attack_bonus(item: dict[str, Any] | None) -> int:
    if not item:
        return 0
    modifiers = _normalize_stat_modifiers(item.get("stat_modifiers"))
    bonus = _numeric_stat_total(modifiers, STAT_ALIASES["damage"] | STAT_ALIASES["strength"])
    rarity = str(item.get("rarity") or "common").lower()
    bonus += RARITY_ATTACK_BONUS.get(rarity, 0)
    if bonus <= 0 and str(item.get("item_type") or "").lower() == "weapon":
        bonus += max(1, min(6, int(round(_float(item.get("weight"), 1.0)))))
    return clamp(bonus, 0, 999)


def _player_combat_stats(state: dict[str, Any]) -> dict[str, int]:
    player = state.get("player") or {}
    effective_stats = player.get("effective_stats") or (state.get("equipment_effects") or {}).get("stat_modifiers") or {}
    if not isinstance(effective_stats, dict):
        effective_stats = {}
    level = clamp(_int_from_any(player.get("level"), 1), 1, 100)
    return {
        "strength": clamp(5 + level * 2 + _numeric_stat_total(effective_stats, STAT_ALIASES["strength"]), 1, 999),
        "defense": clamp(3 + level + _numeric_stat_total(effective_stats, STAT_ALIASES["defense"]), 0, 999),
        "dodge": clamp(3 + level + _numeric_stat_total(effective_stats, STAT_ALIASES["dodge"]), 0, 999),
    }


def _player_attack_profile(state: dict[str, Any], player_input: str, refs: dict[str, list[str]]) -> dict[str, Any]:
    stats = _player_combat_stats(state)
    weapon = _selected_attack_weapon(state, player_input, refs)
    weapon_bonus = _item_attack_bonus(weapon)
    if weapon:
        attack_min = clamp(1 + stats["strength"] // 4 + weapon_bonus // 2, 1, 999)
        attack_max = clamp(max(attack_min + 1, 3 + stats["strength"] // 2 + weapon_bonus), attack_min, 999)
        weapon_name = str(weapon.get("name") or "equipped weapon")
        weapon_code = str(weapon.get("code") or "")
        equipment_used = {str(weapon.get("equipped_slot") or "held"): [weapon_code or weapon_name]}
    else:
        attack_min = clamp(1 + stats["strength"] // 5, 1, 999)
        attack_max = clamp(max(attack_min + 1, 2 + stats["strength"] // 3), attack_min, 999)
        weapon_name = "unarmed"
        weapon_code = ""
        equipment_used = {}
    return {
        "weapon": weapon_name,
        "weapon_code": weapon_code,
        "equipment": equipment_used,
        "strength": stats["strength"],
        "defense": stats["defense"],
        "dodge": stats["dodge"],
        "attack_min": attack_min,
        "attack_max": attack_max,
    }


def _resolve_player_attack(state: dict[str, Any], player_input: str, target: dict[str, Any], attack: dict[str, Any]) -> dict[str, Any]:
    target_combat = _combat_profile_from_npc(target)
    if target_combat["max_health"] <= 0:
        target_combat.update(_derive_npc_combat_profile(target, state))
    seed = f"{_current_turn_number() + 1}|{player_input}|{target.get('code')}|{target_combat.get('health')}"
    roller = random.Random(seed)
    attack_roll = roller.randint(1, 20)
    raw_damage = roller.randint(max(1, int(attack.get("attack_min") or 1)), max(1, int(attack.get("attack_max") or 1)))
    attack_total = attack_roll + max(0, int(attack.get("strength") or 0) // 3)
    evasion_target = 8 + max(0, int(target_combat.get("dodge") or 0))
    if attack_total < evasion_target - 4:
        outcome = "miss"
        damage = 0
    else:
        defense_absorb = max(0, int(target_combat.get("defense") or 0) // 4)
        damage = max(1, raw_damage - defense_absorb)
        if attack_total < evasion_target:
            outcome = "glancing_hit"
            damage = max(1, damage // 2)
        else:
            outcome = "hit"
    health_value = target_combat.get("health")
    health_before = max(0, int(health_value if health_value is not None else target_combat.get("max_health") or 0))
    health_after = clamp(health_before - damage, 0, max(health_before, int(target_combat.get("max_health") or health_before)))
    return {
        "outcome": outcome,
        "attack_roll": attack_roll,
        "attack_total": attack_total,
        "evasion_target": evasion_target,
        "raw_damage_roll": raw_damage,
        "damage": damage,
        "target_health_before": health_before,
        "target_health_after": health_after,
        "target_defeated": health_after == 0 and health_before > 0,
    }


def _combat_target_summary(npc: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": npc.get("code"),
        "name": npc.get("name"),
        "rank": npc.get("rank"),
        "attitude": npc.get("attitude"),
        "combat_profile": _combat_profile_from_npc(npc),
    }


def _build_mechanics_context(state: dict[str, Any], player_input: str) -> dict[str, Any]:
    intent, _secondary = _turn_intent(player_input)
    mechanics = {
        "version": MECHANICS_CONTEXT_VERSION,
        "purpose": "Deterministic mechanics facts reduce LLM stat math. The model narrates and chooses special abilities/consequences; SQLite applies resolved core combat math.",
    }
    if intent != "combat":
        mechanics["combat"] = {"status": "not_combat"}
        return mechanics
    refs = _explicit_turn_references(player_input)
    action_kind = _combat_action_kind(player_input)
    candidates = _combat_target_candidates(state, player_input, refs)[:6]
    target = _clear_combat_target(state, player_input, refs)
    attack = _player_attack_profile(state, player_input, refs)
    combat_context: dict[str, Any] = {
        "status": "needs_target" if target is None else action_kind,
        "action_kind": action_kind,
        "player_attack": attack,
        "target_candidates": [_combat_target_summary(npc) for npc in candidates],
        "rules": [
            "Use player_attack.weapon and player_attack.equipment as the mechanical attack source.",
            "Do not recalculate core damage or NPC health when resolution is present; narrate the listed result and immediate consequences.",
            "Special abilities, enemy tactics, surrender, death, capture, noise, witnesses, and morale remain narrative/model decisions when justified.",
            "NPC health 0 means unable to keep fighting, not automatically dead unless narration and context justify it.",
        ],
    }
    if target is not None:
        combat_context["target"] = _combat_target_summary(target)
    if target is not None and action_kind == "player_attack":
        combat_context["resolution"] = _resolve_player_attack(state, player_input, target, attack)
        combat_context["status"] = "resolved_player_attack"
    mechanics["combat"] = combat_context
    return mechanics


def _inventory_summary(settings: dict[str, Any], inventory: list[dict[str, Any]], equipment_slots: list[dict[str, Any]], capacity_modifiers: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    options = settings.get("playthrough_options") or {}
    base_weight_capacity = max(1.0, _float(options.get("inventory_weight_limit"), 60.0))
    base_slot_capacity = max(1, int(_float(options.get("inventory_slot_limit"), 24)))
    equipped_codes = {str(item.get("code") or "") for item in inventory if str(item.get("equipped_slot") or "").strip()}
    equipped_containers = [
        item
        for item in inventory
        if str(item.get("equipped_slot") or "").strip()
        and str(item.get("item_type") or "").lower() in {"backpack", "pack", "container", "dimensional space", "storage"}
    ]

    bonus_weight = sum(max(0.0, _float(item.get("container_bonus_weight"), 0.0)) for item in equipped_containers)
    bonus_slots = sum(max(0, int(_float(item.get("container_bonus_slots"), 0))) for item in equipped_containers)
    dimensional_count = sum(1 for item in equipped_containers if int(item.get("dimensional_space") or 0))
    for modifier in capacity_modifiers or []:
        bonus_weight += max(0.0, _float(modifier.get("weight_bonus"), 0.0))
        bonus_slots += max(0, int(_float(modifier.get("slot_bonus"), 0)))
        if int(modifier.get("dimensional_space") or 0):
            dimensional_count += 1
    dimensional_multiplier = 2**min(dimensional_count, 6) if dimensional_count else 1
    slot_capacity = None if dimensional_count else base_slot_capacity + bonus_slots
    weight_capacity = (base_weight_capacity + bonus_weight) * dimensional_multiplier

    carry_efficiency = 1.0
    for item in equipped_containers:
        modifier = _float(item.get("carry_modifier"), 1.0)
        if modifier < 1:
            carry_efficiency *= max(0.75, min(1.0, modifier))
    for modifier in capacity_modifiers or []:
        carry_modifier = _float(modifier.get("carry_modifier"), 1.0)
        if carry_modifier < 1:
            carry_efficiency *= max(0.5, min(1.0, carry_modifier))
    carry_efficiency = max(0.55, min(1.25, carry_efficiency))

    total_weight = 0.0
    effective_weight = 0.0
    packed_weight = 0.0
    equipped_weight = 0.0
    slots_used = 0
    for item in inventory:
        quantity = max(0, int(item.get("quantity") or 0))
        if quantity <= 0:
            continue
        item_weight = max(0.0, _float(item.get("weight"), 1.0)) * quantity
        item_modifier = max(0.05, min(5.0, _float(item.get("carry_modifier"), 1.0)))
        total_weight += item_weight
        if str(item.get("equipped_slot") or "").strip():
            equipped_weight += item_weight * item_modifier
            effective_weight += item_weight * item_modifier
            continue
        packed_weight += item_weight
        effective_weight += item_weight * item_modifier * carry_efficiency
        stack_limit = max(1, int(_float(item.get("stack_limit"), 20)))
        slot_size = max(0, int(_float(item.get("slot_size"), 1)))
        slots_used += math.ceil(quantity / stack_limit) * slot_size

    equipped_by_slot: dict[str, list[str]] = {}
    for item in inventory:
        slot = str(item.get("equipped_slot") or "").strip()
        if not slot:
            continue
        equipped_by_slot.setdefault(slot, []).append(str(item.get("code") or item.get("name") or ""))

    return {
        "base_weight_capacity": round(base_weight_capacity, 2),
        "weight_capacity": round(weight_capacity, 2),
        "base_slot_capacity": base_slot_capacity,
        "slot_capacity": slot_capacity,
        "slot_capacity_infinite": slot_capacity is None,
        "slots_used": slots_used,
        "total_weight": round(total_weight, 2),
        "effective_weight": round(effective_weight, 2),
        "packed_weight": round(packed_weight, 2),
        "equipped_weight": round(equipped_weight, 2),
        "carry_efficiency": round(carry_efficiency, 3),
        "dimensional_spaces": dimensional_count,
        "over_weight": max(0, round(effective_weight - weight_capacity, 2)),
        "over_slots": 0 if slot_capacity is None else max(0, slots_used - slot_capacity),
        "equipped_slots": equipped_by_slot,
        "equipment_slot_count": len(equipment_slots),
        "capacity_modifiers": [modifier.get("source") for modifier in capacity_modifiers or []],
        "equipped_item_codes": sorted(code for code in equipped_codes if code),
    }


def _clean_effect_name(value: Any, fallback: str = "") -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    return text[:120]


def _normalize_stat_modifiers(value: Any) -> dict[str, Any]:
    raw = _json(value, {})
    modifiers: dict[str, Any] = {}
    if isinstance(raw, dict):
        for key, stat_value in raw.items():
            name = _clean_effect_name(key).lower().replace(" ", "_")
            if not name:
                continue
            if isinstance(stat_value, (int, float)) and not isinstance(stat_value, bool):
                modifiers[name] = round(float(stat_value), 3)
            elif stat_value not in (None, ""):
                modifiers[name] = str(stat_value)[:160]
    elif isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                name = _clean_effect_name(entry.get("stat") or entry.get("name")).lower().replace(" ", "_")
                if not name:
                    continue
                stat_value = entry.get("delta") if "delta" in entry else entry.get("value", entry.get("modifier"))
                if isinstance(stat_value, (int, float)) and not isinstance(stat_value, bool):
                    modifiers[name] = round(float(stat_value), 3)
                elif stat_value not in (None, ""):
                    modifiers[name] = str(stat_value)[:160]
            elif isinstance(entry, str):
                text = _clean_effect_name(entry, "equipment effect")
                if text:
                    modifiers.setdefault("notes", [])
                    if isinstance(modifiers["notes"], list):
                        modifiers["notes"].append(text[:160])
    elif isinstance(raw, str):
        notes = [_clean_effect_name(part) for part in raw.split(",") if _clean_effect_name(part)]
        if notes:
            modifiers["notes"] = notes[:8]
    return modifiers


def _normalize_granted_abilities(value: Any, item: dict[str, Any]) -> list[dict[str, Any]]:
    raw = _json(value, [])
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(raw, list):
        return []
    abilities: list[dict[str, Any]] = []
    item_code = str(item.get("code") or "")
    item_name = str(item.get("name") or "equipped item")
    for entry in raw:
        if isinstance(entry, str):
            name = _clean_effect_name(entry)
            if not name:
                continue
            ability = {
                "name": name,
                "description": f"Granted by equipped {item_name}.",
                "base_description": f"Granted by equipped {item_name}.",
                "cost": "",
                "prerequisites": f"Equip {item_name}.",
                "additions": "Removed automatically when the item is unequipped.",
                "locked": 0,
            }
        elif isinstance(entry, dict):
            name = _clean_effect_name(entry.get("name") or entry.get("ability"))
            if not name:
                continue
            description = str(entry.get("description") or entry.get("base_description") or f"Granted by equipped {item_name}.")[:700]
            ability = {
                "name": name,
                "description": description,
                "base_description": str(entry.get("base_description") or description)[:700],
                "cost": str(entry.get("cost") or "")[:300],
                "prerequisites": str(entry.get("prerequisites") or f"Equip {item_name}.")[:500],
                "additions": str(entry.get("additions") or entry.get("notes") or "Removed automatically when the item is unequipped.")[:1200],
                "locked": 1 if bool(entry.get("locked")) else 0,
            }
        else:
            continue
        ability["source"] = f"equipment:{item_code or item_name}"
        ability["source_type"] = "equipment"
        ability["equipment_item_code"] = item_code
        ability["equipment_item_name"] = item_name
        abilities.append(ability)
    return abilities[:12]


def _merge_stat_total(total: dict[str, Any], stat: str, value: Any) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        total[stat] = round(_float(total.get(stat), 0.0) + float(value), 3)
        return
    text = str(value or "")[:160]
    if not text:
        return
    existing = total.get(stat)
    if isinstance(existing, list):
        if text not in existing:
            existing.append(text)
    elif existing:
        if str(existing) != text:
            total[stat] = [str(existing), text]
    else:
        total[stat] = text


def _equipment_effects(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    stat_totals: dict[str, Any] = {}
    stat_sources: list[dict[str, Any]] = []
    abilities: list[dict[str, Any]] = []
    equipped_item_codes: list[str] = []
    for item in inventory:
        if not str(item.get("equipped_slot") or "").strip():
            continue
        item_code = str(item.get("code") or "")
        item_name = str(item.get("name") or "")
        if item_code:
            equipped_item_codes.append(item_code)
        modifiers = _normalize_stat_modifiers(item.get("stat_modifiers"))
        for stat, value in modifiers.items():
            values = value if isinstance(value, list) else [value]
            for entry in values:
                _merge_stat_total(stat_totals, stat, entry)
                stat_sources.append({"stat": stat, "value": entry, "item_code": item_code, "item_name": item_name})
        abilities.extend(_normalize_granted_abilities(item.get("granted_abilities"), item))
    return {
        "active_item_codes": equipped_item_codes[:24],
        "stat_modifiers": stat_totals,
        "stat_sources": stat_sources[:24],
        "granted_abilities": abilities[:24],
    }


def _state_with_refreshed_source_index(include_hidden: bool = False) -> dict[str, Any]:
    state = get_state(include_hidden=include_hidden)
    _write_source_index(state)
    return state


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def _index_record(kind: str, title: str, text: str, code: str = "", turn: int | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record = {
        "kind": kind,
        "code": str(code or ""),
        "title": str(title or "")[:160],
        "text": str(text or "")[:1600],
    }
    if turn is not None:
        record["turn"] = turn
    if extra:
        record.update(extra)
    return record


def _write_source_index(state: dict[str, Any]) -> None:
    SOURCE_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    for existing in SOURCE_INDEX_DIR.rglob("*.jsonl"):
        existing.unlink()
    player = state.get("player") or {}
    identity_rows = [
        _index_record(
            "player",
            player.get("name") or "Player",
            " | ".join(
                str(value)
                for value in (
                    player.get("public_name"),
                    player.get("title"),
                    player.get("backstory_mode"),
                    player.get("memory_policy"),
                    player.get("backstory"),
                )
                if value
            ),
            "PLAYER",
        )
    ]
    alias_rows = [
        _index_record(
            "player_alias",
            alias.get("alias"),
            f"reputation {alias.get('reputation', 0)}; active {bool(alias.get('active'))}; disguised {bool(alias.get('disguised'))}; worn disguise {alias.get('disguise_description') or 'none'}; {alias.get('notes') or ''}",
            f"PA{alias.get('id')}",
            int(alias.get("last_used_turn") or alias.get("created_turn") or 0),
        )
        for alias in state.get("player_aliases", [])
    ]
    entity_alias_rows = [
        _index_record("entity_alias", alias.get("alias"), f"{alias.get('alias')} resolves to {alias.get('entity_type')} {alias.get('entity_code')}", alias.get("entity_code"))
        for alias in state.get("aliases", [])
    ]
    location_rows: list[dict[str, Any]] = []
    npc_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    for location in state.get("locations", []):
        location_rows.append(_index_record("location", location.get("name"), location.get("summary"), location.get("code")))
        for npc in location.get("npcs", []):
            npc_rows.append(
                _index_record(
                    "npc",
                    npc.get("name"),
                    " | ".join(str(npc.get(key) or "") for key in ("race", "role", "summary", "attitude", "personality", "likes", "principles", "dislikes", "known_facts", "combat_profile")),
                    npc.get("code"),
                    extra={"location_code": location.get("code")},
                )
            )
        for event in location.get("events", []):
            event_rows.append(
                _index_record(
                    "event",
                    event.get("title"),
                    " | ".join(str(event.get(key) or "") for key in ("summary", "status", "persistence", "fame_scope", "rumor_summary")),
                    event.get("code"),
                    int(event.get("turn") or 0),
                    {"location_code": location.get("code")},
                )
            )
    item_rows = [
        _index_record(
            "item",
            item.get("name"),
            f"quantity {item.get('quantity')}; rarity {item.get('rarity')}; type {item.get('item_type')}; weight {item.get('weight')}; slots {item.get('slot_size')}; equipped {item.get('equipped_slot') or 'no'}; enchantments {item.get('enchantments')}; stat modifiers {item.get('stat_modifiers')}; granted abilities {[ability.get('name') for ability in item.get('granted_abilities', []) if isinstance(ability, dict)]}; {item.get('description') or ''}",
            item.get("code"),
        )
        for item in state.get("inventory", [])
    ]
    equipment_effects = state.get("equipment_effects") or {}
    equipment_effect_rows = [
        _index_record(
            "equipment_effects",
            "Active Equipment Effects",
            f"active item codes {equipment_effects.get('active_item_codes', [])}; stat modifiers {equipment_effects.get('stat_modifiers', {})}; granted abilities {[ability.get('name') for ability in equipment_effects.get('granted_abilities', []) if isinstance(ability, dict)]}",
            "EQFX",
        )
    ]
    equipment_rows = [
        _index_record(
            "equipment_slot",
            slot.get("name"),
            f"category {slot.get('category')}; capacity {slot.get('capacity')}; accepts {slot.get('accepts')}; source item {slot.get('source_item_code') or 'base'}; {slot.get('notes') or ''}",
            slot.get("code"),
        )
        for slot in state.get("equipment_slots", [])
    ]
    modifier_rows = [
        _index_record(
            "inventory_capacity_modifier",
            modifier.get("source"),
            f"weight bonus {modifier.get('weight_bonus')}; slot bonus {modifier.get('slot_bonus')}; carry modifier {modifier.get('carry_modifier')}; dimensional {bool(modifier.get('dimensional_space'))}; {modifier.get('notes') or ''}",
            modifier.get("code"),
        )
        for modifier in state.get("inventory_capacity_modifiers", [])
    ]
    inventory_summary = state.get("inventory_summary") or {}
    inventory_rows = [
        _index_record(
            "inventory_summary",
            "Inventory Limits",
            f"effective weight {inventory_summary.get('effective_weight')}/{inventory_summary.get('weight_capacity')}; slots {inventory_summary.get('slots_used')}/{inventory_summary.get('slot_capacity') if inventory_summary.get('slot_capacity') is not None else 'infinite'}; dimensional spaces {inventory_summary.get('dimensional_spaces')}; over weight {inventory_summary.get('over_weight')}; over slots {inventory_summary.get('over_slots')}",
            "INV",
        )
    ]
    conversation_rows = [
        _index_record("conversation", convo.get("topic") or convo.get("npc_name") or "Conversation", convo.get("summary"), convo.get("npc_code"), int(convo.get("turn") or 0))
        for convo in state.get("conversations", [])
    ]
    summary_rows = [
        _index_record("turn_summary", f"Turn {summary.get('turn')}", summary.get("summary"), f"T{summary.get('turn')}", int(summary.get("turn") or 0))
        for summary in state.get("turn_summaries", [])
    ]
    consolidated_rows = _load_consolidated_fact_records()
    files = {
        "identity/player.jsonl": identity_rows,
        "identity/player_aliases.jsonl": alias_rows,
        "identity/entity_aliases.jsonl": entity_alias_rows,
        "entities/locations.jsonl": location_rows,
        "entities/npcs.jsonl": npc_rows,
        "entities/items.jsonl": item_rows,
        "entities/equipment_slots.jsonl": equipment_rows,
        "inventory/equipment_effects.jsonl": equipment_effect_rows,
        "inventory/capacity_modifiers.jsonl": modifier_rows,
        "entities/events.jsonl": event_rows,
        "inventory/summary.jsonl": inventory_rows,
        "memory/conversations.jsonl": conversation_rows,
        "memory/turn_summaries.jsonl": summary_rows,
        "memory/consolidated_facts.jsonl": consolidated_rows,
    }
    for relative, rows in files.items():
        _write_jsonl(SOURCE_INDEX_DIR / relative, rows)
    manifest = {
        "format": "ai-rpg-source-index-v1",
        "description": "Line-oriented source index for searching durable RPG facts without loading full history into the LLM prompt.",
        "files": {relative: {"records": len(rows)} for relative, rows in files.items()},
    }
    SOURCE_INDEX_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")


def _source_importance(record: dict[str, Any]) -> float:
    """Heuristic importance weight for source_index ranking."""
    if record.get("importance") is not None:
        try:
            value = float(record.get("importance") or 0)
            return max(0.0, min(1.0, value))
        except (TypeError, ValueError):
            pass
    kind = str(record.get("kind") or "").lower()
    kind_base = {
        "consolidated_fact": 0.72,
        "event": 0.62,
        "turn_summary": 0.5,
        "npc": 0.48,
        "conversation": 0.45,
        "item": 0.42,
        "location": 0.4,
        "player": 0.55,
    }.get(kind, 0.4)
    text = f"{record.get('title') or ''} {record.get('text') or ''}".lower()
    boost = 0.0
    for term in (
        "killed", "died", "death", "quest", "betray", "secret", "attack", "battle",
        "oath", "alliance", "enemy", "artifact", "prophecy", "stole", "murder", "crowned",
    ):
        if term in text:
            boost += 0.04
    return max(0.0, min(1.0, kind_base + boost))


def _score_source_record(query_tokens: set[str], record: dict[str, Any], current_turn: int = 0) -> float:
    """Combined keyword overlap + recency + importance for relevant_sources selection."""
    keyword_hits = _score_text(query_tokens, record.get("code"), record.get("title"), record.get("text"))
    if keyword_hits <= 0 and str(record.get("kind") or "") != "consolidated_fact":
        return 0.0
    importance = _source_importance(record)
    turn = _int_from_any(record.get("turn"), 0)
    if turn > 0 and current_turn > 0:
        age = max(0, current_turn - turn)
        recency = math.exp(-age / 80.0)
    else:
        recency = 0.45
    keyword_strength = min(1.0, keyword_hits / max(1, min(6, len(query_tokens) or 1)))
    # Weights: keyword gate + recency + importance
    score = (0.45 * keyword_strength) + (0.30 * recency) + (0.25 * importance)
    if str(record.get("kind") or "") == "consolidated_fact" and keyword_hits <= 0:
        # Allow high-importance consolidated facts to surface weakly without exact keyword hits.
        score = 0.15 * recency + 0.35 * importance
    return score


def search_source_index(query: str, limit: int = 16, current_turn: int = 0) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    if not query_tokens or not SOURCE_INDEX_DIR.exists():
        return []
    results: list[dict[str, Any]] = []
    for path in SOURCE_INDEX_DIR.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    score = _score_source_record(query_tokens, record, current_turn=current_turn)
                    if score > 0:
                        results.append(
                            {
                                "kind": record.get("kind"),
                                "code": record.get("code", ""),
                                "title": record.get("title", ""),
                                "text": record.get("text", ""),
                                "turn": record.get("turn"),
                                "importance": _source_importance(record),
                                "source": str(path.relative_to(SOURCE_INDEX_DIR)).replace("\\", "/"),
                                "line": line_number,
                                "score": round(score, 4),
                            }
                        )
        except OSError:
            continue
    return sorted(results, key=lambda item: (item["score"], item.get("importance") or 0), reverse=True)[:limit]


def _load_consolidated_facts() -> list[dict[str, Any]]:
    if not CONSOLIDATED_FACTS_PATH.exists():
        return []
    facts: list[dict[str, Any]] = []
    try:
        with CONSOLIDATED_FACTS_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid consolidated fact JSON: {exc}") from exc
                if not isinstance(row, dict) or not str(row.get("fact") or "").strip():
                    raise ValueError("Consolidated fact rows must include fact text.")
                facts.append(row)
    except OSError as exc:
        raise ValueError(f"Failed to read consolidated facts: {exc}") from exc
    return facts


def _load_consolidated_fact_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for fact in _load_consolidated_facts():
        records.append(
            _index_record(
                "consolidated_fact",
                str(fact.get("title") or "Memory fact")[:160],
                str(fact.get("fact") or "")[:1600],
                str(fact.get("id") or fact.get("code") or ""),
                _int_from_any(fact.get("turn"), 0) or None,
                {
                    "importance": _source_importance({"kind": "consolidated_fact", "importance": fact.get("importance"), "title": fact.get("title"), "text": fact.get("fact")}),
                },
            )
        )
    return records


def _write_consolidated_facts(facts: list[dict[str, Any]]) -> None:
    CONSOLIDATED_FACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    trimmed = facts[-MEMORY_CONSOLIDATE_MAX_FACTS:]
    _write_jsonl(CONSOLIDATED_FACTS_PATH, trimmed)


def consolidate_memory(keep_recent_summaries: int | None = None, max_facts: int | None = None) -> dict[str, Any]:
    """
    Hierarchical memory consolidation: roll older turn summaries into durable source_index facts
    and prune bloated summary files so prompt context stays lean.
    """
    keep = keep_recent_summaries if keep_recent_summaries is not None else MEMORY_CONSOLIDATE_KEEP_SUMMARIES
    keep = max(4, int(keep))
    fact_cap = max_facts if max_facts is not None else MEMORY_CONSOLIDATE_MAX_FACTS
    fact_cap = max(20, int(fact_cap))

    with connect() as conn:
        summaries = rows_to_dicts(conn.execute("SELECT turn, summary FROM turn_summaries ORDER BY turn ASC").fetchall())
        turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        current_turn = int(turn_row["value"]) if turn_row else 0

    if len(summaries) <= keep:
        return {
            "skipped": True,
            "reason": "not_enough_summaries",
            "summary_count": len(summaries),
            "facts_total": len(_load_consolidated_facts()),
            "current_turn": current_turn,
        }

    to_roll = summaries[:-keep]
    existing = _load_consolidated_facts()
    existing_keys = {str(item.get("source_turn")) for item in existing if item.get("source_turn") is not None}
    added = 0
    for row in to_roll:
        turn = _int_from_any(row.get("turn"), 0)
        key = str(turn)
        if key in existing_keys:
            continue
        text = str(row.get("summary") or "").strip()
        if len(text) < 12:
            continue
        importance = _source_importance({"kind": "turn_summary", "title": f"Turn {turn}", "text": text})
        existing.append(
            {
                "id": f"CF{turn}",
                "code": f"CF{turn}",
                "title": f"Turn {turn} fact",
                "fact": text[:700],
                "turn": turn,
                "source_turn": turn,
                "importance": importance,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        existing_keys.add(key)
        added += 1

    # Prefer higher importance, then newer turns when trimming.
    existing.sort(key=lambda item: (float(item.get("importance") or 0), _int_from_any(item.get("turn"), 0)), reverse=True)
    existing = existing[:fact_cap]
    _write_consolidated_facts(existing)

    # Keep JSONL history summaries from ballooning: retain only recent lines.
    if HISTORY_SUMMARY_PATH.exists():
        try:
            lines = [line for line in HISTORY_SUMMARY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
            if len(lines) > keep:
                HISTORY_SUMMARY_PATH.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"Failed to prune history summaries: {exc}") from exc

    # Refresh source index so consolidated facts are searchable.
    state = get_state(include_hidden=True)
    _write_source_index(state)

    return {
        "skipped": False,
        "facts_added": added,
        "facts_total": len(existing),
        "rolled_summaries": len(to_roll),
        "kept_recent_summaries": keep,
        "current_turn": current_turn,
    }


def _safe_slot_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        raise ValueError("Campaign slot name is required.")
    if len(cleaned) > 64:
        raise ValueError("Campaign slot name is too long.")
    return cleaned


def list_campaign_slots() -> list[dict[str, Any]]:
    CAMPAIGN_SLOTS_DIR.mkdir(parents=True, exist_ok=True)
    slots: list[dict[str, Any]] = []
    for path in sorted(CAMPAIGN_SLOTS_DIR.glob("*/world.json")):
        slot_name = path.parent.name
        meta_path = path.parent / "metadata.json"
        metadata: dict[str, Any] = {"slot": slot_name}
        if meta_path.exists():
            try:
                metadata.update(json.loads(meta_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
        metadata["path"] = str(path.parent).replace("\\", "/")
        metadata["modified"] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        slots.append(metadata)
    slots.sort(key=lambda item: str(item.get("modified") or ""), reverse=True)
    return slots


def save_campaign_slot(slot_name: str) -> dict[str, Any]:
    safe = _safe_slot_name(slot_name)
    payload = export_world()
    slot_dir = CAMPAIGN_SLOTS_DIR / safe
    slot_dir.mkdir(parents=True, exist_ok=True)
    world_path = slot_dir / "world.json"
    world_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    state = get_state(include_hidden=False)
    player = state.get("player") or {}
    location = state.get("current_location") or {}
    metadata = {
        "slot": safe,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "player_name": player.get("name"),
        "player_level": player.get("level"),
        "location": location.get("name"),
        "turn": next((int(item.get("turn") or 0) for item in state.get("turn_summaries", [])[::-1]), 0),
        "format": payload.get("format"),
    }
    (slot_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    return metadata


def load_campaign_slot(slot_name: str) -> dict[str, Any]:
    safe = _safe_slot_name(slot_name)
    world_path = CAMPAIGN_SLOTS_DIR / safe / "world.json"
    if not world_path.exists():
        raise ValueError(f"Campaign slot '{safe}' was not found.")
    try:
        data = json.loads(world_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read campaign slot '{safe}': {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Campaign slot '{safe}' is not a valid world export object.")
    return import_world(data)


def delete_campaign_slot(slot_name: str) -> dict[str, Any]:
    safe = _safe_slot_name(slot_name)
    slot_dir = CAMPAIGN_SLOTS_DIR / safe
    if not slot_dir.exists():
        raise ValueError(f"Campaign slot '{safe}' was not found.")
    shutil.rmtree(slot_dir)
    return {"deleted": safe}


def get_context_health() -> dict[str, Any]:
    state = get_state(include_hidden=True)
    budget = state.get("model_budget") or {}
    facts = _load_consolidated_facts()
    summaries = state.get("turn_summaries") or []
    gm_events = state.get("gm_events") or []
    pending_gm = [event for event in gm_events if str(event.get("status") or "pending") in {"pending", "active", "background", ""}]
    return {
        "model_budget": budget,
        "memory": {
            "turn_summaries": len(summaries),
            "consolidated_facts": len(facts),
            "keep_recent_summaries": MEMORY_CONSOLIDATE_KEEP_SUMMARIES,
            "max_facts": MEMORY_CONSOLIDATE_MAX_FACTS,
            "health": (
                "needs_consolidation"
                if len(summaries) > MEMORY_CONSOLIDATE_KEEP_SUMMARIES + 8 and len(facts) < 3
                else "heavy"
                if len(facts) > MEMORY_CONSOLIDATE_MAX_FACTS * 0.85
                else "ok"
            ),
        },
        "gm_events": {
            "total": len(gm_events),
            "pending": len(pending_gm),
            "interval_turns": GM_OFFSCREEN_INTERVAL,
        },
        "campaign_slots": list_campaign_slots(),
        "setup_complete": bool(state.get("setup_complete")),
    }


def _maybe_spawn_offscreen_gm_event(conn, turn: int) -> None:
    """Lightweight proactive off-screen pressure without an extra LLM call."""
    if turn <= 0 or turn % GM_OFFSCREEN_INTERVAL != 0:
        return
    pending = conn.execute(
        "SELECT COUNT(*) AS count FROM gm_events WHERE status IN ('pending', 'active', 'background', 'seeded', '')"
    ).fetchone()
    if pending and int(pending["count"] or 0) >= 12:
        return
    player = row_to_dict(conn.execute("SELECT * FROM player WHERE id = 1").fetchone()) or {}
    location_id = player.get("current_location_id")
    location = row_to_dict(
        conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    ) or {}
    npc = row_to_dict(
        conn.execute(
            "SELECT * FROM npcs WHERE location_id = ? ORDER BY RANDOM() LIMIT 1",
            (location_id,),
        ).fetchone()
    ) if location_id else None
    templates = [
        "Rumors thicken away from the player; loyalties may shift before the next meeting.",
        "A delayed consequence of recent public actions continues off-screen.",
        "Local pressure builds quietly: supply, suspicion, or opportunity moves without the player present.",
    ]
    if npc:
        templates.append(f"{npc.get('name') or 'An NPC'} pursues private business that may matter later.")
    if location.get("name"):
        templates.append(f"Off-screen movement continues around {location.get('name')}.")
    summary = random.choice(templates)
    conn.execute(
        """
        INSERT INTO gm_events (turn, trigger, summary, status, priority, location_id, npc_id, event_id)
        VALUES (?, ?, ?, 'pending', ?, ?, ?, NULL)
        """,
        (
            turn,
            "offscreen_tick",
            summary[:700],
            2,
            location_id,
            npc.get("id") if npc else None,
        ),
    )


def get_state(include_hidden: bool = False) -> dict[str, Any]:
    with connect() as conn:
        settings = _settings(conn)
        if settings.get("setup_complete") == "true" or settings.get("setup_complete") is True:
            has_slots = conn.execute("SELECT 1 FROM equipment_slots LIMIT 1").fetchone()
            if has_slots is None:
                _ensure_default_equipment_slots(conn)
        player = row_to_dict(
            conn.execute(
                """
                SELECT p.*, l.name AS current_location_name, l.code AS current_location_code
                FROM player p
                LEFT JOIN locations l ON l.id = p.current_location_id
                WHERE p.id = 1
                """
            ).fetchone()
        )
        locations = rows_to_dicts(
            conn.execute("SELECT * FROM locations ORDER BY name COLLATE NOCASE").fetchall()
        )
        npcs = rows_to_dicts(
            conn.execute(
                """
                SELECT n.*, l.name AS location_name, l.code AS location_code
                FROM npcs n
                JOIN locations l ON l.id = n.location_id
                ORDER BY l.name COLLATE NOCASE, n.id
                """
            ).fetchall()
        )
        relationships = rows_to_dicts(
            conn.execute(
                """
                SELECT r.*, s.code AS source_code, s.name AS source_name, t.code AS target_code, t.name AS target_name
                FROM relationships r
                JOIN npcs s ON s.id = r.source_npc_id
                JOIN npcs t ON t.id = r.target_npc_id
                ORDER BY r.id DESC
                """
            ).fetchall()
        )
        inventory = rows_to_dicts(
            conn.execute("SELECT * FROM inventory WHERE quantity > 0 ORDER BY id").fetchall()
        )
        equipment_slots = rows_to_dicts(
            conn.execute("SELECT * FROM equipment_slots ORDER BY sort_order, id").fetchall()
        )
        inventory_capacity_modifiers = rows_to_dicts(
            conn.execute("SELECT * FROM inventory_capacity_modifiers WHERE active = 1 ORDER BY id").fetchall()
        )
        skills = rows_to_dicts(
            conn.execute("SELECT * FROM player_skills ORDER BY name COLLATE NOCASE").fetchall()
        )
        abilities = rows_to_dicts(
            conn.execute("SELECT * FROM abilities ORDER BY id").fetchall()
        )
        events = rows_to_dicts(
            conn.execute(
                """
                SELECT e.*, l.code AS location_code, l.name AS location_name, n.code AS npc_code, n.name AS npc_name
                FROM events e
                LEFT JOIN locations l ON l.id = e.location_id
                LEFT JOIN npcs n ON n.id = e.npc_id
                ORDER BY e.id DESC
                """
            ).fetchall()
        )
        conversations = rows_to_dicts(
            conn.execute(
                """
                SELECT c.*, n.code AS npc_code, n.name AS npc_name
                FROM conversations c
                LEFT JOIN npcs n ON n.id = c.npc_id
                ORDER BY c.id DESC
                LIMIT 80
                """
            ).fetchall()
        )
        response_drafts = rows_to_dicts(
            conn.execute("SELECT * FROM response_drafts ORDER BY id DESC LIMIT 40").fetchall()
        )
        aliases = rows_to_dicts(
            conn.execute("SELECT * FROM aliases ORDER BY alias COLLATE NOCASE").fetchall()
        )
        player_aliases = rows_to_dicts(
            conn.execute("SELECT * FROM player_aliases ORDER BY active DESC, updated_at DESC, alias COLLATE NOCASE").fetchall()
        )
        karma_history = rows_to_dicts(
            conn.execute("SELECT * FROM karma_history ORDER BY id DESC LIMIT 60").fetchall()
        )
        turn_summaries = rows_to_dicts(
            conn.execute("SELECT * FROM turn_summaries ORDER BY id DESC LIMIT 80").fetchall()
        )
        model_logs = rows_to_dicts(
            conn.execute("SELECT * FROM model_logs ORDER BY id DESC LIMIT 30").fetchall()
        )
        verification_memory = rows_to_dicts(
            conn.execute("SELECT * FROM verification_memory ORDER BY updated_at DESC, id DESC LIMIT 120").fetchall()
        ) if include_hidden else []
        rewind_points = rows_to_dicts(
            conn.execute("SELECT id, turn, created_at FROM turn_snapshots ORDER BY id DESC LIMIT 5").fetchall()
        )
        gm_notes = row_to_dict(conn.execute("SELECT * FROM gm_notes WHERE id = 1").fetchone()) if include_hidden else None
        gm_events = rows_to_dicts(
            conn.execute(
                """
                SELECT g.*, l.code AS location_code, l.name AS location_name, n.code AS npc_code, n.name AS npc_name, e.code AS event_code, e.title AS event_title
                FROM gm_events g
                LEFT JOIN locations l ON l.id = g.location_id
                LEFT JOIN npcs n ON n.id = g.npc_id
                LEFT JOIN events e ON e.id = g.event_id
                ORDER BY g.id DESC
                LIMIT 80
                """
            ).fetchall()
        ) if include_hidden else []
        journal = rows_to_dicts(
            conn.execute("SELECT * FROM journal ORDER BY id DESC LIMIT 160").fetchall()
        )

    for npc in npcs:
        npc["known_facts"] = _json(npc.get("known_facts"), [])
        npc["stat_profile"] = _json(npc.get("stat_profile"), {})
        npc["skill_profile"] = _json(npc.get("skill_profile"), {})
        npc["combat_profile"] = _combat_profile_from_npc(npc)
    for convo in conversations:
        convo["player_claims"] = _json(convo.get("player_claims"), [])
    for item in inventory:
        item["enchantments"] = _json(item.get("enchantments"), [])
        item["stat_modifiers"] = _normalize_stat_modifiers(item.get("stat_modifiers"))
        item["granted_abilities"] = _normalize_granted_abilities(item.get("granted_abilities"), item)
    for slot in equipment_slots:
        slot["accepts"] = _json(slot.get("accepts"), [])
    for entry in verification_memory:
        entry["entity_codes"] = _json(entry.get("entity_codes"), [])

    equipment_effects = _equipment_effects(inventory)
    state_abilities = [*abilities, *equipment_effects["granted_abilities"]]
    if player is not None:
        player["effective_stats"] = equipment_effects["stat_modifiers"]
        player["equipment_ability_names"] = [ability.get("name") for ability in equipment_effects["granted_abilities"] if ability.get("name")]

    location_tree: list[dict[str, Any]] = []
    for location in locations:
        local_npcs = [npc for npc in npcs if npc["location_id"] == location["id"]]
        local_events = [event for event in events if event.get("location_id") == location["id"]]
        location_tree.append({**location, "npcs": local_npcs, "events": local_events})

    current_location = None
    if player:
        current_location = next(
            (location for location in locations if location["id"] == player["current_location_id"]),
            None,
        )

    context_window = context_window_tokens()
    latest_budget = max((int(log.get("estimated_tokens") or 0) for log in model_logs[:2]), default=0)
    state = {
        "setup_complete": settings.get("setup_complete") == "true" or settings.get("setup_complete") is True,
        "settings": settings,
        "player": player,
        "current_location": current_location,
        "locations": location_tree,
        "inventory": inventory,
        "equipment_slots": equipment_slots,
        "inventory_capacity_modifiers": inventory_capacity_modifiers,
        "inventory_summary": _inventory_summary(settings, inventory, equipment_slots, inventory_capacity_modifiers),
        "equipment_effects": equipment_effects,
        "skills": skills,
        "abilities": state_abilities,
        "events": events,
        "relationships": relationships,
        "conversations": conversations,
        "response_drafts": response_drafts,
        "aliases": aliases,
        "player_aliases": player_aliases,
        "active_player_alias": next((alias for alias in player_aliases if int(alias.get("active") or 0)), None),
        "karma_history": karma_history,
        "turn_summaries": turn_summaries,
        "model_logs": model_logs,
        "model_budget": {
            "context_window": context_window,
            "warning_threshold": int(context_window * 0.75),
            "latest_estimated_tokens": latest_budget,
            "warning": latest_budget >= int(context_window * 0.75),
            "consolidated_facts": len(_load_consolidated_facts()) if CONSOLIDATED_FACTS_PATH.exists() else 0,
            "turn_summaries": len(turn_summaries),
        },
        "rewind_points": rewind_points,
        "history": journal,
    }
    if include_hidden:
        state["gm_notes"] = gm_notes or {"id": 1, "content": ""}
        state["gm_events"] = gm_events
        state["verification_memory"] = verification_memory
    return state


def _set_setting(conn, key: str, value: Any) -> None:
    encoded = json.dumps(value) if isinstance(value, (dict, list, bool, int, float)) else str(value)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, encoded),
    )


def _clear_playthrough(conn) -> None:
    for table in (
        "response_drafts",
        "aliases",
        "player_aliases",
        "karma_history",
        "turn_summaries",
        "model_logs",
        "verification_memory",
        "gm_events",
        "turn_snapshots",
        "conversations",
        "events",
        "relationships",
        "abilities",
        "player_skills",
        "journal",
        "inventory",
        "equipment_slots",
        "inventory_capacity_modifiers",
        "npcs",
        "player",
        "locations",
    ):
        conn.execute(f"DELETE FROM {table}")
    conn.execute(
        """
        DELETE FROM sqlite_sequence
        WHERE name IN ('locations', 'npcs', 'inventory', 'equipment_slots', 'inventory_capacity_modifiers', 'player_skills', 'abilities', 'events', 'conversations', 'response_drafts', 'aliases', 'player_aliases', 'karma_history', 'turn_summaries', 'model_logs', 'verification_memory', 'gm_events', 'turn_snapshots', 'journal')
        """
    )
    conn.execute("DELETE FROM pacing")
    conn.execute("UPDATE gm_notes SET content = '', updated_at = CURRENT_TIMESTAMP WHERE id = 1")
    if HISTORY_SUMMARY_PATH.exists():
        HISTORY_SUMMARY_PATH.unlink()
    if SOURCE_INDEX_DIR.exists():
        shutil.rmtree(SOURCE_INDEX_DIR)


def start_playthrough(options: dict[str, Any]) -> dict[str, Any]:
    player_name = norm_name(str(options.get("player_name") or "Wanderer"))
    public_name = norm_name(str(options.get("player_public_name") or ""))
    player_title = norm_name(str(options.get("player_title") or ""))
    player_age = str(options.get("player_age") or "").strip()[:60]
    player_sex = str(options.get("player_sex") or "").strip()[:80]
    previous_life_age = str(options.get("previous_life_age") or "").strip()[:60]
    previous_life_sex = str(options.get("previous_life_sex") or "").strip()[:80]
    backstory_mode = str(options.get("backstory_mode") or "known")[:60]
    character_backstory = str(options.get("character_backstory") or "").strip()[:1600]
    memory_policy = str(options.get("memory_policy") or "known")[:80]
    world_style = str(options.get("world_style") or "frontier dark fantasy")
    custom_style = str(options.get("custom_style") or "").strip()
    narration_detail = str(options.get("narration_detail") or "rich").strip()[:120]
    world_races = str(options.get("world_races") or "human").strip()[:400]
    race_magic_rules = str(options.get("race_magic_rules") or "").strip()[:1200]
    race_ability_rules = str(options.get("race_ability_rules") or "").strip()[:1200]
    loot_rarity = str(options.get("loot_rarity") or "earned and uncommon")[:80]
    inventory_weight_limit = max(1, min(100000, int(_float(options.get("inventory_weight_limit"), 60))))
    inventory_slot_limit = max(1, min(10000, int(_float(options.get("inventory_slot_limit"), 24))))
    inventory_rules = str(options.get("inventory_rules") or "").strip()[:900]
    start_location = norm_name(str(options.get("start_location") or "Mosswake Gate"))
    skill_style = str(options.get("skill_style") or "standard")
    custom_skills = str(options.get("custom_skills") or "").strip()
    special_name = norm_name(str(options.get("special_ability_name") or "Unwritten Talent"))
    raw_abilities = options.get("special_abilities") or []
    requested_abilities = bool(options.get("special_ability")) or (isinstance(raw_abilities, list) and bool(raw_abilities))
    special_ability_origin = _ability_origin(options.get("special_ability_origin"), requested_abilities)
    special_abilities: list[dict[str, Any]] = []
    if special_ability_origin != "none" and isinstance(raw_abilities, list):
        for ability in raw_abilities:
            if not isinstance(ability, dict):
                continue
            name = norm_name(str(ability.get("name") or ""))
            if not name:
                continue
            special_abilities.append(
                {
                    "name": name,
                    "description": str(ability.get("description") or "A rare starting ability defined by the playthrough setup.")[:800],
                    "locked": bool(ability.get("locked")),
                    "prerequisites": str(ability.get("prerequisites") or "")[:500],
                    "cost": str(ability.get("cost") or "")[:300],
                }
            )
    has_special = special_ability_origin != "none" and (bool(options.get("special_ability")) or bool(special_abilities))
    special_locked = bool(options.get("special_ability_locked"))
    if has_special and not special_abilities:
        special_abilities.append(
            {
                "name": special_name,
                "description": str(options.get("special_ability_description") or "A rare starting ability defined by the playthrough setup.")[:800],
                "locked": special_locked,
                "prerequisites": "",
                "cost": "",
            }
        )

    with connect() as conn:
        _clear_playthrough(conn)
        conn.execute("INSERT INTO pacing (key, value) VALUES ('turn', '0')")

        cursor = conn.execute(
            "INSERT INTO locations (code, name, summary, visit_count) VALUES (?, ?, ?, ?)",
            (
                "L1",
                start_location,
                f"Starting location for a {world_style} playthrough. {custom_style}".strip(),
                1,
            ),
        )
        start_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO player (id, name, public_name, title, age, sex, previous_life_age, previous_life_sex, backstory_mode, backstory, memory_policy, health, max_health, level, xp, gold, karma, current_location_id)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (player_name, public_name, player_title, player_age, player_sex, previous_life_age, previous_life_sex, backstory_mode, character_backstory, memory_policy, 20, 20, 1, 0, 12, 0, start_id),
        )
        _ensure_default_equipment_slots(conn)

        for ability in special_abilities:
            conn.execute(
                """
                INSERT INTO abilities (name, description, locked, base_description, cost, prerequisites, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ability["name"],
                    ability["description"],
                    1 if ability["locked"] else 0,
                    ability["description"],
                    ability["cost"],
                    ability["prerequisites"],
                    special_ability_origin,
                ),
            )

        stored_options = {
            "difficulty": options.get("difficulty") or "normal",
            "narration_detail": narration_detail or "rich",
            "world_style": world_style,
            "custom_style": custom_style,
            "leveling_system": bool(options.get("leveling_system", True)),
            "game_system": bool(options.get("game_system", False)),
            "system_style": options.get("system_style") or "subtle blue-window system",
            "death_rules": options.get("death_rules") or "downed, not deleted",
            "economy": options.get("economy") or "scarce",
            "magic_level": options.get("magic_level") or "rare",
            "world_races": world_races or "human",
            "race_magic_enabled": bool(options.get("race_magic_enabled", False)),
            "race_magic_rarity": options.get("race_magic_rarity") or "same as world magic",
            "race_magic_rules": race_magic_rules,
            "race_ability_rules": race_ability_rules,
            "loot_rarity": loot_rarity,
            "inventory_weight_limit": inventory_weight_limit,
            "inventory_slot_limit": inventory_slot_limit,
            "inventory_rules": inventory_rules,
            "tech_level": options.get("tech_level") or "iron age",
            "tone": options.get("tone") or "grounded adventure",
            "npc_density": options.get("npc_density") or "moderate",
            "quest_style": options.get("quest_style") or "emergent",
            "faction_pressure": options.get("faction_pressure") or "local disputes",
            "skill_style": skill_style,
            "skill_levels_enabled": bool(options.get("skill_levels_enabled", True)),
            "new_skill_frequency": options.get("new_skill_frequency") or "normal",
            "proficiency_system": bool(options.get("proficiency_system", True)),
            "proficiency_access": options.get("proficiency_access") or "learned",
            "skill_growth_speed": options.get("skill_growth_speed") or "normal",
            "proficiency_growth_speed": options.get("proficiency_growth_speed") or "normal",
            "xp_growth_speed": options.get("xp_growth_speed") or "normal",
            "skill_growth_multiplier": options.get("skill_growth_multiplier"),
            "proficiency_growth_multiplier": options.get("proficiency_growth_multiplier"),
            "xp_growth_multiplier": options.get("xp_growth_multiplier"),
            "skill_growth_note": options.get("skill_growth_note") or "",
            "proficiency_growth_note": options.get("proficiency_growth_note") or "",
            "xp_growth_note": options.get("xp_growth_note") or "",
            "npc_stat_scaling": options.get("npc_stat_scaling") or "relative ranks",
            "npc_skill_frequency": options.get("npc_skill_frequency") or "some trained NPCs",
            "rank_scale": options.get("rank_scale") or "F,E,D,C,B,A,S,SS,SSS",
            "custom_skills": custom_skills,
            "player_public_name": public_name,
            "player_title": player_title,
            "player_age": player_age,
            "player_sex": player_sex,
            "previous_life_age": previous_life_age,
            "previous_life_sex": previous_life_sex,
            "backstory_mode": backstory_mode,
            "character_backstory": character_backstory,
            "memory_policy": memory_policy,
            "special_ability": has_special,
            "special_ability_origin": special_ability_origin,
            "special_abilities": special_abilities,
            "special_ability_locked": special_abilities[0]["locked"] if special_abilities else False,
            "special_ability_name": special_abilities[0]["name"] if special_abilities else "",
        }
        _set_setting(conn, "setup_complete", "true")
        _set_setting(conn, "playthrough_options", stored_options)
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (0, "setup", f"Playthrough started: {json.dumps(stored_options, ensure_ascii=True)}"),
        )
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (
                0,
                "system",
                "Initialization phase pending: on the first model turn, establish base play assumptions, respect immutable ability base descriptions, do not seed default player skills, and set any model-decided ability costs or prerequisites through ability_updates.",
            ),
        )
        if character_backstory:
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (0, "backstory", f"{backstory_mode}/{memory_policy}: {character_backstory}"[:1800]),
            )

    return _state_with_refreshed_source_index()


def _table_rows(conn, table: str) -> list[dict[str, Any]]:
    return rows_to_dicts(conn.execute(f"SELECT * FROM {table}").fetchall())


def export_world() -> dict[str, Any]:
    with connect() as conn:
        return {
            "format": "ai-rpg-world-v1",
            "tables": {table: _table_rows(conn, table) for table in WORLD_TABLES},
            "history_summaries": HISTORY_SUMMARY_PATH.read_text(encoding="utf-8") if HISTORY_SUMMARY_PATH.exists() else "",
        }


def _restore_world(data: dict[str, Any]) -> None:
    tables = data.get("tables") or {}
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            for table in RESTORE_ORDER:
                if table in WORLD_TABLES or table == "turn_snapshots":
                    conn.execute(f"DELETE FROM {table}")
            for table in WORLD_TABLES:
                rows = tables.get(table) or []
                for row in rows:
                    columns = list(row.keys())
                    placeholders = ", ".join("?" for _ in columns)
                    names = ", ".join(columns)
                    conn.execute(
                        f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
                        [row[column] for column in columns],
                    )
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA foreign_key_check")
        except Exception:
            conn.rollback()
            raise
    text = str(data.get("history_summaries") or "")
    HISTORY_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_SUMMARY_PATH.write_text(text, encoding="utf-8")


def import_world(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("format") != "ai-rpg-world-v1" or not isinstance(data.get("tables"), dict):
        raise ValueError("Unsupported world export format.")
    _restore_world(data)
    return _state_with_refreshed_source_index()


def update_gm_notes(content: str) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            "UPDATE gm_notes SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
            (content[:6000],),
        )
    return {"ok": True}


def search_world(query: str) -> dict[str, Any]:
    state = get_state()
    _write_source_index(state)
    query_tokens = _tokens(query)
    results: list[dict[str, Any]] = []
    current_code = (state.get("current_location") or {}).get("code")
    relationship_strength: dict[str, int] = {}
    for rel in state.get("relationships", []):
        relationship_strength[rel.get("source_code", "")] = relationship_strength.get(rel.get("source_code", ""), 0) + abs(int(rel.get("weight") or 0))
        relationship_strength[rel.get("target_code", "")] = relationship_strength.get(rel.get("target_code", ""), 0) + abs(int(rel.get("weight") or 0))

    def add(kind: str, code: str, title: str, text: str, boost: int = 0) -> None:
        score = _score_text(query_tokens, code, title, text) + boost
        if score:
            results.append({"kind": kind, "code": code, "title": title, "text": text, "score": score})

    for location in state.get("locations", []):
        local_boost = 4 if location.get("code") == current_code else 0
        add("location", location.get("code", ""), location.get("name", ""), location.get("summary", ""), local_boost)
        for npc in location.get("npcs", []):
            npc_boost = local_boost + min(4, relationship_strength.get(npc.get("code", ""), 0))
            add("npc", npc.get("code", ""), npc.get("name", ""), " ".join(str(npc.get(key, "")) for key in ("summary", "personality", "likes", "principles", "dislikes")), npc_boost)
        for event in location.get("events", []):
            add("event", event.get("code", ""), event.get("title", ""), event.get("summary", ""), local_boost + max(0, 4 - int(event.get("id", 0)) // 25))
    for item in state.get("inventory", []):
        add("item", item.get("code", ""), item.get("name", ""), item.get("description", ""))
    for convo in state.get("conversations", []):
        add("conversation", f"T{convo.get('turn')}", convo.get("topic", ""), convo.get("summary", ""), max(0, 5 - int(convo.get("id", 0)) // 10))
    for summary in state.get("turn_summaries", []):
        add("summary", f"T{summary.get('turn')}", "Turn summary", summary.get("summary", ""), max(0, 5 - int(summary.get("id", 0)) // 10))

    source_results = search_source_index(query, 20)
    return {
        "query": query,
        "results": sorted(results, key=lambda item: item["score"], reverse=True)[:40],
        "source_index": {
            "manifest": str(SOURCE_INDEX_MANIFEST).replace("\\", "/"),
            "results": source_results,
        },
    }


def get_world_bible() -> dict[str, Any]:
    state = get_state()
    current_code = (state.get("current_location") or {}).get("code")
    active_location = next((location for location in state.get("locations", []) if location.get("code") == current_code), None)
    important_npcs = sorted(
        [npc for location in state.get("locations", []) for npc in location.get("npcs", [])],
        key=lambda npc: (abs(int(npc.get("trust") or 0)), len(str(npc.get("summary") or ""))),
        reverse=True,
    )[:12]
    highlights = state.get("turn_summaries", [])[:12]
    active_events = [event for event in state.get("events", []) if event.get("status") in {"active", "background"}][:12]
    return {
        "active_location": active_location,
        "important_npcs": important_npcs,
        "active_events": active_events,
        "journal_highlights": highlights,
        "player": state.get("player"),
    }


def _snapshot_row(conn, table: str, where: str, params: tuple[Any, ...], rows: dict[str, list[dict[str, Any]]]) -> None:
    found = rows_to_dicts(conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall())
    if found:
        bucket = rows.setdefault(table, [])
        seen = {(row.get("id"), row.get("key")) for row in bucket}
        for row in found:
            marker = (row.get("id"), row.get("key"))
            if marker not in seen:
                bucket.append(row)
                seen.add(marker)


def _save_snapshot(conn, turn: int, result: dict[str, Any]) -> None:
    rows: dict[str, list[dict[str, Any]]] = {}
    _snapshot_row(conn, "player", "id = 1", (), rows)
    _snapshot_row(conn, "player_aliases", "id >= 0", (), rows)
    _snapshot_row(conn, "equipment_slots", "id >= 0", (), rows)
    _snapshot_row(conn, "inventory_capacity_modifiers", "id >= 0", (), rows)
    _snapshot_row(conn, "verification_memory", "id >= 0", (), rows)
    _snapshot_row(conn, "pacing", "key = 'turn'", (), rows)

    for location in result.get("locations") or []:
        name = norm_name(str(location.get("name", "")))
        if name:
            _snapshot_row(conn, "locations", "name = ?", (name,), rows)

    player_patch = result.get("player") or {}
    move_to = player_patch.get("move_to_location") or player_patch.get("move_to_location_code")
    if move_to:
        value = norm_name(str(move_to))
        _snapshot_row(conn, "locations", "code = ? OR name = ?", (value, value), rows)

    for npc in result.get("npcs") or []:
        code = norm_name(str(npc.get("code", "")))
        name = norm_name(str(npc.get("name", "")))
        if code:
            _snapshot_row(conn, "npcs", "code = ?", (code,), rows)
        if name:
            _snapshot_row(conn, "npcs", "name = ?", (name,), rows)

    for change in result.get("inventory_changes") or []:
        name = norm_name(str(change.get("name", "")))
        if name:
            _snapshot_row(conn, "inventory", "name = ?", (name,), rows)

    for change in result.get("equipment_changes") or []:
        if not isinstance(change, dict):
            continue
        for item_ref in (change.get("item_code"), change.get("item_name"), change.get("name")):
            value = norm_name(str(item_ref or ""))
            if value:
                _snapshot_row(conn, "inventory", "code = ? OR name = ?", (value, value), rows)
        slot_ref = norm_name(str(change.get("slot_code") or "")).upper()
        slot_name = norm_name(str(change.get("slot_name") or change.get("slot") or ""))
        if slot_ref or slot_name:
            slot = conn.execute("SELECT code FROM equipment_slots WHERE code = ? OR name = ?", (slot_ref, slot_name)).fetchone()
            if slot:
                _snapshot_row(conn, "inventory", "equipped_slot = ?", (slot["code"],), rows)

    for change in result.get("skill_changes") or []:
        name = norm_name(str(change.get("name", ""))).lower()
        if name:
            _snapshot_row(conn, "player_skills", "name = ?", (name,), rows)

    for event in result.get("events") or []:
        code = norm_name(str(event.get("code", "")))
        title = norm_name(str(event.get("title", "")))
        if code:
            _snapshot_row(conn, "events", "code = ?", (code,), rows)
        if title:
            _snapshot_row(conn, "events", "title = ?", (title,), rows)

    for rel in result.get("relationships") or []:
        source_id = _npc_id_by_ref(conn, rel.get("source_code") or rel.get("source"), rel.get("location"))
        target_id = _npc_id_by_ref(conn, rel.get("target_code") or rel.get("target"), rel.get("location"))
        if source_id and target_id:
            _snapshot_row(
                conn,
                "relationships",
                "source_npc_id = ? AND target_npc_id = ?",
                (source_id, target_id),
                rows,
            )

    for update in result.get("index_updates") or []:
        code = norm_name(str(update.get("code", "")))
        entity_type = str(update.get("entity_type") or "").lower()
        table = {"npc": "npcs", "location": "locations", "item": "inventory", "event": "events"}.get(entity_type)
        if table and code:
            _snapshot_row(conn, table, "code = ?", (code,), rows)

    deterministic_combat = result.get("_deterministic_combat") or {}
    target_code = str((deterministic_combat.get("target") or {}).get("code") or "").strip()
    if target_code:
        _snapshot_row(conn, "npcs", "code = ?", (target_code,), rows)

    max_ids = {table: _max_id(conn, table) for table in AUTOINC_TABLES}
    snapshot = {
        "format": "ai-rpg-delta-v1",
        "turn": turn,
        "max_ids": max_ids,
        "rows": rows,
        "history_summaries": HISTORY_SUMMARY_PATH.read_text(encoding="utf-8") if HISTORY_SUMMARY_PATH.exists() else "",
    }
    conn.execute("INSERT INTO turn_snapshots (turn, snapshot) VALUES (?, ?)", (turn, json.dumps(snapshot, ensure_ascii=True)))
    conn.execute("DELETE FROM turn_snapshots WHERE id NOT IN (SELECT id FROM turn_snapshots ORDER BY id DESC LIMIT 12)")


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z0-9]{2,}", text)}


def _score_text(query_tokens: set[str], *parts: Any) -> int:
    haystack = _tokens(" ".join(str(part or "") for part in parts))
    return len(query_tokens & haystack)


def _turn_kind(player_input: str) -> str:
    if str(player_input).startswith("__opening_scene_request__"):
        return "opening_scene"
    if str(player_input).startswith("__continue_scene_request__"):
        return "continue_scene"
    return "player_action"


def _explicit_turn_references(player_input: str) -> dict[str, list[str]]:
    refs = {"npcs": [], "locations": [], "items": [], "events": [], "all": []}
    for match in TURN_REFERENCE_PATTERN.finditer(str(player_input or "")):
        code = next((group for group in match.groups() if group), "").upper()
        if not code or code in refs["all"]:
            continue
        refs["all"].append(code)
        if code.startswith("L"):
            refs["locations"].append(code)
        elif code.startswith("I"):
            refs["items"].append(code)
        elif code.startswith("E"):
            refs["events"].append(code)
        else:
            refs["npcs"].append(code)
    return refs


def _turn_intent(player_input: str) -> tuple[str, list[str]]:
    kind = _turn_kind(player_input)
    if kind != "player_action":
        return kind, []
    tokens = _tokens(player_input)
    scores: list[tuple[str, int]] = []
    lowered = str(player_input or "").lower()
    for intent, keywords in TURN_INTENT_KEYWORDS.items():
        score = len(tokens & keywords)
        if intent == "claim_check" and any(phrase in lowered for phrase in ("said i could", "told me i could", "gave me permission", "said we could")):
            score += 3
        if score:
            scores.append((intent, score))
    if not scores:
        return "general", []
    scores.sort(key=lambda item: item[1], reverse=True)
    primary = scores[0][0]
    secondary = [intent for intent, score in scores[1:4] if score > 0]
    if primary == "conversation" and "claim_check" in secondary:
        primary = "claim_check"
        secondary = [intent for intent, _score in scores if intent != "claim_check"][:3]
    return primary, secondary


def _context_limit_profile(intent: str, state: dict[str, Any]) -> dict[str, int]:
    limits = dict(TURN_INTENT_LIMITS.get(intent) or TURN_INTENT_LIMITS["general"])
    budget = state.get("model_budget") or {}
    context_window = int(budget.get("context_window") or context_window_tokens())
    warning = bool(budget.get("warning"))
    scale = 1.0
    if context_window <= 4096 or warning:
        scale = 0.65
    elif context_window >= 12000:
        scale = 1.25
    for key, value in list(limits.items()):
        limits[key] = max(2, int(round(value * scale)))
    return limits


def _turn_risk_checks(intent: str, state: dict[str, Any], refs: dict[str, list[str]]) -> list[str]:
    checks = ["entity_references", "state_delta_justification"]
    if intent in {"conversation", "claim_check"}:
        checks.extend(["npc_knowledge", "relationship_consistency"])
    if intent == "claim_check":
        checks.extend(["conversation_claims", "event_evidence", "response_drafts"])
    if intent in {"inventory", "trade"}:
        checks.extend(["inventory_capacity", "equipment_state"])
    if intent == "combat":
        checks.extend(["npc_stats", "damage_scale", "karma_visibility"])
    if intent == "travel":
        checks.extend(["location_continuity", "movement_plausibility"])
    if intent in {"training", "ability"}:
        checks.extend(["skill_growth_rules", "ability_constraints"])
    if intent == "opening_scene":
        checks.append("no_default_starting_skills")
    if refs["all"]:
        checks.append("explicit_reference_resolution")
    if state.get("active_player_alias"):
        checks.append("alias_reputation_leakage")
    if state.get("recognition"):
        checks.append("recognition_fame_cap")
    options = ((state.get("settings") or {}).get("playthrough_options") or {})
    if options.get("race_magic_rules") or options.get("race_ability_rules"):
        checks.append("race_rules")
    unique_checks: list[str] = []
    for check in checks:
        if check not in unique_checks:
            unique_checks.append(check)
    return unique_checks


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))


def _short_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:20]


def _verification_entity_codes(context: dict[str, Any]) -> list[str]:
    turn_plan = context.get("turn_plan") or {}
    refs = turn_plan.get("explicit_references") or {}
    codes = {str(code or "").upper() for code in refs.get("all", []) if str(code or "").strip()}
    working_set = context.get("working_set") or {}
    for key in ("current_location_code", "nearby_npc_codes", "nearby_event_codes", "source_hits"):
        value = working_set.get(key)
        if isinstance(value, list):
            codes.update(str(item or "").upper() for item in value if str(item or "").strip())
        elif value:
            codes.add(str(value).upper())
    mechanics = context.get("mechanics_context") or {}
    combat = mechanics.get("combat") if isinstance(mechanics, dict) else {}
    if isinstance(combat, dict):
        target = combat.get("target") if isinstance(combat.get("target"), dict) else {}
        if target.get("code"):
            codes.add(str(target["code"]).upper())
        weapon_code = (combat.get("player_attack") or {}).get("weapon_code") if isinstance(combat.get("player_attack"), dict) else ""
        if weapon_code:
            codes.add(str(weapon_code).upper())
    return sorted(codes)[:24]


def _verification_mechanics_signature(context: dict[str, Any]) -> dict[str, Any]:
    mechanics = context.get("mechanics_context") or {}
    combat = mechanics.get("combat") if isinstance(mechanics, dict) else {}
    if not isinstance(combat, dict):
        return {}
    target = combat.get("target") if isinstance(combat.get("target"), dict) else {}
    attack = combat.get("player_attack") if isinstance(combat.get("player_attack"), dict) else {}
    resolution = combat.get("resolution") if isinstance(combat.get("resolution"), dict) else {}
    return {
        "status": combat.get("status"),
        "action_kind": combat.get("action_kind"),
        "target_code": target.get("code"),
        "weapon": attack.get("weapon"),
        "weapon_code": attack.get("weapon_code"),
        "damage": resolution.get("damage"),
        "target_health_before": resolution.get("target_health_before"),
        "target_health_after": resolution.get("target_health_after"),
        "outcome": resolution.get("outcome"),
    }


def _verification_scope_basis(context: dict[str, Any], check_name: str) -> dict[str, Any]:
    turn_plan = context.get("turn_plan") or {}
    refs = turn_plan.get("explicit_references") or {}
    current_location = context.get("current_location") or {}
    player = context.get("player") or {}
    options = ((context.get("settings") or {}).get("playthrough_options") or {})
    active_alias = context.get("active_player_alias") or {}
    equipment_effects = context.get("equipment_effects") or {}
    inventory_summary = context.get("inventory_summary") or {}
    basis: dict[str, Any] = {
        "version": VERIFICATION_MEMORY_VERSION,
        "check_name": check_name,
        "turn_kind": turn_plan.get("turn_kind"),
        "primary_intent": turn_plan.get("primary_intent"),
        "secondary_intents": turn_plan.get("secondary_intents") or [],
        "current_location_code": current_location.get("code"),
        "refs": refs.get("all", []),
        "focus_terms": turn_plan.get("focus_terms") or [],
    }
    if check_name in {"entity_references", "explicit_reference_resolution"}:
        basis["working_set"] = context.get("working_set") or {}
    elif check_name in {"npc_stats", "damage_scale"}:
        basis["mechanics"] = _verification_mechanics_signature(context)
        basis["player_level"] = player.get("level")
        basis["effective_stats"] = player.get("effective_stats") or {}
    elif check_name == "karma_visibility":
        basis["active_alias"] = {
            "id": active_alias.get("id"),
            "active": active_alias.get("active"),
            "disguised": active_alias.get("disguised"),
        }
        basis["recognition_codes"] = [item.get("event_code") for item in context.get("recognition") or [] if isinstance(item, dict)][:12]
        basis["player_karma"] = player.get("karma")
    elif check_name in {"location_continuity", "movement_plausibility"}:
        basis["working_set"] = context.get("working_set") or {}
        basis["inventory_summary"] = {
            "over_weight": inventory_summary.get("over_weight"),
            "over_slots": inventory_summary.get("over_slots"),
        }
    elif check_name in {"npc_knowledge", "relationship_consistency", "conversation_claims", "event_evidence", "response_drafts"}:
        basis["npc_refs"] = refs.get("npcs", [])
        basis["conversation_ids"] = [item.get("id") for item in context.get("conversations") or [] if isinstance(item, dict)][:16]
        basis["relationship_ids"] = [item.get("id") for item in context.get("relationships") or [] if isinstance(item, dict)][:16]
        basis["event_codes"] = [item.get("code") for item in context.get("events") or [] if isinstance(item, dict)][:16]
    elif check_name in {"inventory_capacity", "equipment_state"}:
        basis["item_refs"] = refs.get("items", [])
        basis["inventory_summary"] = inventory_summary
        basis["active_item_codes"] = equipment_effects.get("active_item_codes") or []
    elif check_name in {"skill_growth_rules", "ability_constraints"}:
        basis["skill_names"] = [item.get("name") for item in context.get("skills") or [] if isinstance(item, dict)][:16]
        basis["ability_names"] = [item.get("name") for item in context.get("abilities") or [] if isinstance(item, dict)][:16]
        basis["progression"] = {
            "skill_style": options.get("skill_style"),
            "skill_growth_speed": options.get("skill_growth_speed"),
            "proficiency_growth_speed": options.get("proficiency_growth_speed"),
        }
    elif check_name == "race_rules":
        basis["race_rules"] = {
            "world_races": options.get("world_races"),
            "magic_level": options.get("magic_level"),
            "race_magic_rules": options.get("race_magic_rules"),
            "race_ability_rules": options.get("race_ability_rules"),
        }
    else:
        basis["working_set"] = context.get("working_set") or {}
    return basis


def _verification_memory_scopes(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    turn_plan = context.get("turn_plan") or {}
    scopes: dict[str, dict[str, Any]] = {}
    for check_name in turn_plan.get("verification_checks") or []:
        check = str(check_name or "").strip()
        if not check:
            continue
        basis = _verification_scope_basis(context, check)
        context_signature = _short_hash(basis)
        scopes[check] = {
            "check_name": check,
            "scope_key": f"{check}:{context_signature}",
            "context_signature": context_signature,
            "basis": basis,
        }
    return scopes


def _verification_memory_context(context: dict[str, Any]) -> dict[str, Any]:
    scopes = _verification_memory_scopes(context)
    if not scopes:
        return {"version": VERIFICATION_MEMORY_VERSION, "entries": [], "covered_checks": []}
    scope_keys = [scope["scope_key"] for scope in scopes.values()]
    placeholders = ", ".join("?" for _ in scope_keys)
    params: list[Any] = [*scope_keys, VERIFICATION_MEMORY_CONFIDENCE_MIN, VERIFICATION_MEMORY_LIMIT]
    with connect() as conn:
        entries = rows_to_dicts(
            conn.execute(
                f"""
                SELECT *
                FROM verification_memory
                WHERE scope_key IN ({placeholders}) AND confidence >= ?
                ORDER BY updated_at DESC, confidence DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        )
    for entry in entries:
        entry["entity_codes"] = _json(entry.get("entity_codes"), [])
    covered_checks = sorted({str(entry.get("check_name") or "") for entry in entries if entry.get("check_name")})
    return {
        "version": VERIFICATION_MEMORY_VERSION,
        "confidence_min": VERIFICATION_MEMORY_CONFIDENCE_MIN,
        "covered_checks": covered_checks,
        "entries": entries,
        "scopes": [
            {"check_name": scope["check_name"], "scope_key": scope["scope_key"], "context_signature": scope["context_signature"]}
            for scope in scopes.values()
        ],
    }


def _score_row(query: set[str], row: dict[str, Any], fields: tuple[str, ...], refs: dict[str, list[str]], current_codes: set[str] | None = None) -> int:
    current_codes = current_codes or set()
    values = [row.get(field) for field in fields]
    score = _score_text(query, *values)
    row_codes = {str(row.get(key) or "").upper() for key in ("code", "npc_code", "location_code", "source_code", "target_code", "item_code") if row.get(key)}
    if row_codes & set(refs["all"]):
        score += 12
    if row_codes & current_codes:
        score += 4
    if not query and row_codes & current_codes:
        score += 1
    return score


def _select_rows(rows: list[dict[str, Any]], query: set[str], limit: int, fields: tuple[str, ...], refs: dict[str, list[str]], current_codes: set[str] | None = None) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    scored = [(_score_row(query, row, fields, refs, current_codes), index, row) for index, row in enumerate(rows)]
    if not any(score for score, _index, _row in scored):
        return rows[:limit]
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    selected = [row for score, _index, row in scored if score > 0][:limit]
    return selected or rows[:limit]


def _row_identity(row: dict[str, Any]) -> str:
    for key in ("id", "code", "name", "title", "npc_code", "location_code", "source_code"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return f"{key}:{value}"
    return str(id(row))


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    for row in rows:
        identity = _row_identity(row)
        if identity in seen:
            continue
        seen.add(identity)
        unique_rows.append(row)
    return unique_rows


def _intent_slice_limit(intent: str, limits: dict[str, int]) -> int:
    base_limits = {
        "opening_scene": 18,
        "continue_scene": 12,
        "combat": 16,
        "ability": 14,
        "inventory": 24,
        "trade": 20,
        "travel": 12,
        "investigation": 12,
        "training": 12,
        "conversation": 8,
        "claim_check": 8,
        "rest": 8,
        "general": 8,
    }
    source_limit = int(limits.get("sources") or 8)
    return max(4, min(base_limits.get(intent, 8), source_limit + 10))


def _select_inventory_context(inventory: list[dict[str, Any]], query: set[str], refs: dict[str, list[str]], intent: str, limits: dict[str, int]) -> list[dict[str, Any]]:
    limit = _intent_slice_limit(intent, limits)
    referenced_items = {code.upper() for code in refs.get("items", [])}
    equipped_items = [item for item in inventory if str(item.get("equipped_slot") or "").strip()]
    explicit_items = [item for item in inventory if str(item.get("code") or "").upper() in referenced_items]
    item_context_intents = {"inventory", "trade", "opening_scene"}
    selected = _dedupe_rows([*equipped_items, *explicit_items] if intent in item_context_intents else explicit_items)
    if intent not in item_context_intents:
        return selected[:limit]
    remaining = [item for item in inventory if _row_identity(item) not in {_row_identity(row) for row in selected}]
    if len(selected) < limit:
        selected.extend(
            _select_rows(
                remaining,
                query,
                limit - len(selected),
                ("code", "name", "description", "item_type", "rarity", "equipped_slot", "enchantments", "stat_modifiers", "granted_abilities"),
                refs,
            )
        )
    return _dedupe_rows(selected)[:limit]


def _select_skill_context(skills: list[dict[str, Any]], query: set[str], refs: dict[str, list[str]], intent: str, limits: dict[str, int]) -> list[dict[str, Any]]:
    limit_by_intent = {
        "combat": 14,
        "ability": 12,
        "training": 16,
        "conversation": 8,
        "claim_check": 8,
        "investigation": 8,
        "travel": 6,
        "opening_scene": 8,
        "continue_scene": 8,
        "general": 6,
    }
    limit = max(3, min(limit_by_intent.get(intent, 6), int(limits.get("summaries") or 8)))
    return _select_rows(skills, query, limit, ("name", "value", "notes"), refs)


def _select_ability_context(abilities: list[dict[str, Any]], query: set[str], refs: dict[str, list[str]], intent: str, limits: dict[str, int]) -> list[dict[str, Any]]:
    limit_by_intent = {
        "ability": 16,
        "combat": 10,
        "training": 10,
        "opening_scene": 10,
        "continue_scene": 6,
        "general": 6,
    }
    limit = max(2, min(limit_by_intent.get(intent, 4), int(limits.get("summaries") or 8)))
    return _select_rows(
        abilities,
        query,
        limit,
        ("name", "description", "base_description", "cost", "prerequisites", "source"),
        refs,
    )


def _select_capacity_modifier_context(modifiers: list[dict[str, Any]], query: set[str], refs: dict[str, list[str]], intent: str) -> list[dict[str, Any]]:
    if intent in {"travel", "inventory", "trade", "combat", "ability", "training", "rest", "opening_scene", "continue_scene"}:
        return _select_rows(modifiers, query, 8, ("code", "source", "notes"), refs)
    return _select_rows(modifiers, query, 4, ("code", "source", "notes"), refs)


def _select_equipment_slot_context(slots: list[dict[str, Any]], inventory: list[dict[str, Any]], intent: str) -> list[dict[str, Any]]:
    if intent in {"inventory", "trade"}:
        return slots[:24]
    return []


def _segment_source_slices(segment_name: str) -> list[str]:
    source_map = {
        "world_setup": ["settings.playthrough_options", "player", "current_location", "locations", "event_lifecycle"],
        "starting_limits": ["player", "equipment_effects", "skills", "abilities", "inventory_summary"],
        "immediate_pressure": ["current_location", "locations", "events", "gm_events", "turn_summaries"],
        "movement_limits": ["player", "equipment_effects", "current_location", "locations", "events", "inventory_summary", "inventory_capacity_modifiers"],
        "environment_pressure": ["current_location", "locations", "events", "event_lifecycle", "gm_events"],
        "combat_opposition": ["mechanics_context", "player", "equipment_effects", "skills", "abilities", "locations.npcs", "relationships", "events"],
        "damage_and_consequence": ["mechanics_context", "player", "inventory_summary", "events", "recognition", "relationships", "settings.playthrough_options"],
        "ability_constraints": ["abilities", "player", "equipment_effects", "locations.npcs", "settings.playthrough_options"],
        "effect_scope": ["abilities", "skills", "events", "turn_summaries", "settings.playthrough_options"],
        "item_handling": ["inventory", "inventory_summary", "equipment_slots", "inventory_capacity_modifiers"],
        "trade_constraints": ["player", "inventory", "inventory_summary", "locations.npcs", "relationships", "settings.playthrough_options"],
        "npc_knowledge": ["locations.npcs", "relationships", "conversations", "recognition", "response_drafts"],
        "evidence_check": ["conversations", "events", "response_drafts", "explicit_references"],
        "environment_scan": ["current_location", "locations", "events", "abilities", "relevant_sources"],
        "growth_requirements": ["skills", "abilities", "locations.npcs", "settings.playthrough_options", "turn_summaries"],
        "rest_safety": ["player", "current_location", "locations", "events", "gm_events", "inventory"],
        "focused_facts": ["explicit_references", "current_location", "locations", "relevant_sources", "working_set"],
    }
    return source_map.get(segment_name, source_map["focused_facts"])


def _local_context_codes(locations: list[dict[str, Any]], current_code: str | None) -> tuple[list[str], list[str]]:
    npc_codes: list[str] = []
    event_codes: list[str] = []
    for location in locations:
        if current_code and location.get("code") != current_code:
            continue
        npc_codes.extend([npc.get("code") for npc in location.get("npcs", []) if npc.get("code")])
        event_codes.extend([event.get("code") for event in location.get("events", []) if event.get("code")])
    return npc_codes[:12], event_codes[:12]


def _action_context(
    intent: str,
    secondary: list[str],
    state: dict[str, Any],
    query: set[str],
    refs: dict[str, list[str]],
    locations: list[dict[str, Any]],
    inventory: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    abilities: list[dict[str, Any]],
    capacity_modifiers: list[dict[str, Any]],
) -> dict[str, Any]:
    current_code = (state.get("current_location") or {}).get("code")
    local_npc_codes, local_event_codes = _local_context_codes(locations, current_code)
    equipment_effects = state.get("equipment_effects") or _equipment_effects(state.get("inventory", []))
    intent_order = [intent, *secondary, "general"]
    segments: list[dict[str, Any]] = []
    attention_keywords: list[str] = []
    seen_segments: set[str] = set()
    for segment_intent in intent_order:
        for segment_name, use_when, keywords in ACTION_SEGMENT_RULES.get(segment_intent, ACTION_SEGMENT_RULES["general"]):
            if segment_name in seen_segments:
                continue
            seen_segments.add(segment_name)
            attention_keywords.extend(keywords)
            segments.append(
                {
                    "name": segment_name,
                    "intent": segment_intent,
                    "attention_keywords": keywords,
                    "source_slices": _segment_source_slices(segment_name),
                }
            )
    player = state.get("player") or {}
    inventory_summary = state.get("inventory_summary") or {}
    equipped_codes = [item.get("code") for item in inventory if str(item.get("equipped_slot") or "").strip() and item.get("code")]
    target_npc_codes = refs.get("npcs") or (local_npc_codes[:4] if intent in {"combat", "ability", "conversation", "claim_check"} else [])
    action_context = {
        "planner_instruction": "Read priority_segments first. For normal turns, inspect only the named source_slices plus hard explicit references; omitted broad player/world records are intentional, not false.",
        "broad_context_allowed": intent == "opening_scene",
        "primary_intent": intent,
        "secondary_intents": secondary,
        "priority_segments": segments[:8],
        "attention_keywords": sorted(set([*attention_keywords, *list(query)]))[:36],
        "hard_reference_codes": refs.get("all", []),
        "target_codes": {
            "npcs": target_npc_codes[:8],
            "locations": refs.get("locations", [])[:8] or ([current_code] if current_code else []),
            "items": refs.get("items", [])[:8],
            "events": refs.get("events", [])[:8] or local_event_codes[:6],
        },
        "player_limits_snapshot": {
            "health": player.get("health"),
            "max_health": player.get("max_health"),
            "level": player.get("level"),
            "karma": player.get("karma"),
            "gold": player.get("gold"),
            "carrying": {
                "effective_weight": inventory_summary.get("effective_weight"),
                "weight_capacity": inventory_summary.get("weight_capacity"),
                "slots_used": inventory_summary.get("slots_used"),
                "slot_capacity": inventory_summary.get("slot_capacity"),
                "over_weight": inventory_summary.get("over_weight"),
                "over_slots": inventory_summary.get("over_slots"),
            },
            "effective_stats": equipment_effects.get("stat_modifiers") or {},
            "equipment_ability_names": [ability.get("name") for ability in equipment_effects.get("granted_abilities", []) if ability.get("name")][:12],
            "active_capacity_modifier_codes": [modifier.get("code") for modifier in capacity_modifiers if modifier.get("code")][:8],
            "relevant_skill_names": [skill.get("name") for skill in skills if skill.get("name")][:12],
            "relevant_ability_names": [ability.get("name") for ability in abilities if ability.get("name")][:12],
        },
        "local_focus_codes": {
            "current_location": current_code,
            "nearby_npcs": local_npc_codes[:8],
            "nearby_events": local_event_codes[:8],
        },
    }
    return action_context


def _turn_plan(player_input: str, state: dict[str, Any], query: set[str], refs: dict[str, list[str]], limits: dict[str, int]) -> dict[str, Any]:
    intent, secondary = _turn_intent(player_input)
    return {
        "version": TURN_CONTEXT_PLANNER_VERSION,
        "turn_kind": _turn_kind(player_input),
        "primary_intent": intent,
        "secondary_intents": secondary,
        "focus_terms": sorted(query)[:24],
        "explicit_references": refs,
        "verification_checks": _turn_risk_checks(intent, state, refs),
        "context_limits": limits,
        "strategy": "Sequential context planner: classify intent, gather focused facts, draft from the packet, then verify the risky surfaces.",
    }


def _working_set(current_code: str | None, locations: list[dict[str, Any]], relevant_sources: list[dict[str, Any]]) -> dict[str, Any]:
    nearby_npcs: list[str] = []
    nearby_events: list[str] = []
    for location in locations:
        if current_code and location.get("code") != current_code:
            continue
        nearby_npcs.extend([npc.get("code") for npc in location.get("npcs", []) if npc.get("code")])
        nearby_events.extend([event.get("code") for event in location.get("events", []) if event.get("code")])
    return {
        "current_location_code": current_code,
        "nearby_npc_codes": nearby_npcs[:12],
        "nearby_event_codes": nearby_events[:12],
        "source_hits": [source.get("code") or source.get("title") for source in relevant_sources[:8]],
    }


def _event_lifecycle_context(state: dict[str, Any]) -> dict[str, Any]:
    current_location = state.get("current_location") or {}
    current_id = current_location.get("id")
    current_events = [event for event in state.get("events", []) if event.get("location_id") == current_id]
    active_events = [event for event in current_events if event.get("status") in {"active", "background"}]
    temporary_events = [event for event in active_events if str(event.get("persistence") or "persistent") in {"temporary", "traveling", "recurring"}]
    return {
        "current_location_code": current_location.get("code"),
        "visit_count": int(current_location.get("visit_count") or 0),
        "active_event_codes": [event.get("code") for event in active_events if event.get("code")][:8],
        "temporary_event_codes": [event.get("code") for event in temporary_events if event.get("code")][:8],
        "focus_point_range": {"min": 1, "max": 6},
        "return_event_guidance": "Keep local NPCs durable, keep current-visit events stable while the player remains here, let temporary opportunities often fade after departure, and add new return events sparingly when the location has changed or time has plausibly moved.",
    }


def build_prompt_context(state: dict[str, Any], player_input: str) -> dict[str, Any]:
    _write_source_index(state)
    query = _tokens(player_input)
    refs = _explicit_turn_references(player_input)
    intent, _secondary = _turn_intent(player_input)
    limits = _context_limit_profile(intent, state)
    current_code = (state.get("current_location") or {}).get("code")
    recognition = _recognition_candidates(state)
    locations = []
    for location in state.get("locations", []):
        local = location.get("code") == current_code
        score = _score_text(query, location.get("code"), location.get("name"), location.get("summary")) + (8 if local else 0)
        npcs = sorted(
            location.get("npcs", []),
            key=lambda npc: _score_text(query, npc.get("code"), npc.get("name"), npc.get("summary"), npc.get("known_facts")) + (4 if local else 0),
            reverse=True,
        )[:limits["local_npcs"] if local else limits["remote_npcs"]]
        events = sorted(
            location.get("events", []),
            key=lambda event: _score_text(query, event.get("code"), event.get("title"), event.get("summary")),
            reverse=True,
        )[:limits["local_events"] if local else 3]
        if score or local or npcs or events:
            locations.append({**location, "npcs": npcs, "events": events, "_relevance": score})
    locations = sorted(locations, key=lambda item: item.get("_relevance", 0), reverse=True)[:limits["locations"]]
    for location in locations:
        location.pop("_relevance", None)

    current_npc_codes = {
        npc.get("code")
        for location in locations
        if location.get("code") == current_code
        for npc in location.get("npcs", [])
        if npc.get("code")
    }
    current_event_codes = {
        event.get("code")
        for location in locations
        if location.get("code") == current_code
        for event in location.get("events", [])
        if event.get("code")
    }
    current_codes = {code for code in [current_code, *current_npc_codes, *current_event_codes] if code}

    events = _select_rows(
        state.get("events", []),
        query,
        limits["events"],
        ("code", "title", "summary", "location_code", "npc_code", "rumor_summary"),
        refs,
        current_codes,
    )
    conversations = _select_rows(
        state.get("conversations", []),
        query,
        limits["conversations"],
        ("npc_code", "npc_name", "topic", "summary", "player_claims"),
        refs,
        current_codes,
    )
    summaries = _select_rows(
        state.get("turn_summaries", []),
        query,
        limits["summaries"],
        ("summary",),
        refs,
        current_codes,
    )
    relationships = _select_rows(
        state.get("relationships", []),
        query,
        limits["relationships"],
        ("source_code", "source_name", "target_code", "target_name", "summary"),
        refs,
        current_codes,
    )
    response_drafts = _select_rows(
        state.get("response_drafts", []),
        query,
        limits["response_drafts"],
        ("claim", "verdict", "skill", "result", "notes"),
        refs,
        current_codes,
    )
    gm_events = _select_rows(
        state.get("gm_events", []),
        query,
        8,
        ("trigger", "summary", "status", "location_code", "npc_code", "event_code"),
        refs,
        current_codes,
    )
    search_query = " ".join(
        [
            player_input,
            str((state.get("current_location") or {}).get("name") or ""),
            " ".join(refs["all"]),
        ]
    ).strip()
    current_turn = _int_from_any((state.get("player") or {}).get("turn"), 0)
    if not current_turn:
        summaries = state.get("turn_summaries") or []
        if summaries:
            current_turn = max(_int_from_any(item.get("turn"), 0) for item in summaries)
    relevant_sources = search_source_index(search_query or player_input, limits["sources"], current_turn=current_turn)
    equipment_effects = state.get("equipment_effects") or _equipment_effects(state.get("inventory", []))
    state_abilities = state.get("abilities", [])
    if not state.get("equipment_effects"):
        state_abilities = [*state_abilities, *equipment_effects.get("granted_abilities", [])]
    context_player = dict(state.get("player") or {})
    context_player["effective_stats"] = equipment_effects.get("stat_modifiers") or {}
    context_player["equipment_ability_names"] = [ability.get("name") for ability in equipment_effects.get("granted_abilities", []) if ability.get("name")]
    inventory = _select_inventory_context(state.get("inventory", []), query, refs, intent, limits)
    skills = _select_skill_context(state.get("skills", []), query, refs, intent, limits)
    abilities = _select_ability_context(state_abilities, query, refs, intent, limits)
    inventory_capacity_modifiers = _select_capacity_modifier_context(state.get("inventory_capacity_modifiers", []), query, refs, intent)
    equipment_slots = _select_equipment_slot_context(state.get("equipment_slots", []), inventory, intent)
    planner_state = {**state, "recognition": recognition}
    turn_plan = _turn_plan(player_input, planner_state, query, refs, limits)
    action_context = _action_context(
        intent,
        turn_plan["secondary_intents"],
        state,
        query,
        refs,
        locations,
        inventory,
        skills,
        abilities,
        inventory_capacity_modifiers,
    )
    turn_plan["action_segments"] = [segment.get("name") for segment in action_context.get("priority_segments", [])]
    turn_plan["attention_keywords"] = action_context.get("attention_keywords", [])
    turn_plan["included_counts"] = {
        "locations": len(locations),
        "events": len(events),
        "conversations": len(conversations),
        "relationships": len(relationships),
        "response_drafts": len(response_drafts),
        "turn_summaries": len(summaries),
        "inventory": len(inventory),
        "equipment_slots": len(equipment_slots),
        "skills": len(skills),
        "abilities": len(abilities),
        "inventory_capacity_modifiers": len(inventory_capacity_modifiers),
        "mechanics_context": 1 if state.get("mechanics_context") else 0,
        "hidden_gm_events": len(gm_events),
        "source_hits": len(relevant_sources),
        "recognition": min(len(recognition), limits["recognition"]),
    }
    event_lifecycle = _event_lifecycle_context(state)

    prompt_context = {
        **state,
        "player": context_player,
        "locations": locations,
        "events": events,
        "conversations": conversations,
        "relationships": relationships,
        "response_drafts": response_drafts,
        "turn_summaries": summaries,
        "inventory": inventory,
        "equipment_slots": equipment_slots,
        "inventory_capacity_modifiers": inventory_capacity_modifiers,
        "equipment_effects": equipment_effects,
        "skills": skills,
        "abilities": abilities,
        "gm_events": gm_events,
        "player_aliases": state.get("player_aliases", []),
        "active_player_alias": state.get("active_player_alias"),
        "relevant_sources": relevant_sources,
        "recognition": recognition[:limits["recognition"]],
        "history": [],
        "turn_plan": turn_plan,
        "action_context": action_context,
        "working_set": _working_set(current_code, locations, relevant_sources),
        "event_lifecycle": event_lifecycle,
        "retrieval": {
            "method": "sequential deterministic context planner plus mechanics context, action-specific player slices, active-location scoring, and source_index JSONL search",
            "planner": TURN_CONTEXT_PLANNER_VERSION,
            "primary_intent": turn_plan["primary_intent"],
            "action_segments": turn_plan["action_segments"],
            "verification_checks": turn_plan["verification_checks"],
            "query_terms": sorted(query)[:30],
            "included_locations": [location.get("code") for location in locations],
            "source_index_manifest": str(SOURCE_INDEX_MANIFEST).replace("\\", "/"),
            "source_hits": len(relevant_sources),
        },
    }
    verification_memory = _verification_memory_context(prompt_context)
    prompt_context["verification_memory"] = verification_memory
    prompt_context["turn_plan"]["included_counts"]["verification_memory_hits"] = len(verification_memory.get("entries") or [])
    prompt_context["retrieval"]["verification_memory_hits"] = len(verification_memory.get("entries") or [])
    prompt_context["retrieval"]["verification_memory_covered_checks"] = verification_memory.get("covered_checks") or []
    return prompt_context


def _recognition_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    current_location = state.get("current_location") or {}
    current_code = current_location.get("code")
    visited_codes = {
        location.get("code")
        for location in state.get("locations", [])
        if int(location.get("visit_count") or 0) > 0 and location.get("code")
    }
    candidates: list[dict[str, Any]] = []
    for event in state.get("events", []):
        fame = clamp(int(event.get("fame_score") or 0), 0, 80)
        if fame <= 0:
            continue
        event_location = event.get("location_code")
        if event_location == current_code:
            distance_multiplier = 1.0
            distance = "same_location"
        elif event_location in visited_codes:
            distance_multiplier = 0.65
            distance = "previously_visited_location"
        else:
            distance_multiplier = 0.25
            distance = "distant_or_unvisited"
        chance = clamp(int(round(fame * distance_multiplier)), 0, 80)
        if chance <= 0:
            continue
        candidates.append(
            {
                "event_code": event.get("code"),
                "event_title": event.get("title"),
                "location_code": event_location,
                "location_name": event.get("location_name"),
                "npc_code": event.get("npc_code"),
                "fame_score": fame,
                "recognition_chance_percent_cap": chance,
                "distance": distance,
                "scope": event.get("fame_scope") or "local",
                "rumor_summary": event.get("rumor_summary") or event.get("summary"),
            }
        )
    return sorted(candidates, key=lambda item: item["recognition_chance_percent_cap"], reverse=True)[:12]


def _primary_key(table: str) -> str:
    return "key" if table in {"pacing", "settings"} else "id"


def _restore_snapshot_rows(conn, rows: dict[str, list[dict[str, Any]]]) -> None:
    for table in ("player", "pacing", "settings", "gm_notes"):
        for row in rows.get(table, []):
            _update_or_insert_row(conn, table, row)

    delete_order = [
        "response_drafts",
        "model_logs",
        "verification_memory",
        "karma_history",
        "turn_summaries",
        "gm_events",
        "journal",
        "conversations",
        "relationships",
        "events",
        "abilities",
        "player_skills",
        "player_aliases",
        "equipment_slots",
        "inventory_capacity_modifiers",
        "inventory",
        "npcs",
        "locations",
        "aliases",
    ]
    max_ids = rows.get("__max_ids__", [{}])[0]
    for table in delete_order:
        max_id = int(max_ids.get(table, 0))
        conn.execute(f"DELETE FROM {table} WHERE id > ?", (max_id,))

    restore_order = [
        "locations",
        "player",
        "npcs",
        "inventory",
        "events",
        "gm_events",
        "relationships",
        "player_skills",
        "abilities",
        "player_aliases",
        "equipment_slots",
        "inventory_capacity_modifiers",
        "aliases",
        "karma_history",
        "turn_summaries",
        "model_logs",
        "verification_memory",
        "journal",
        "conversations",
        "response_drafts",
    ]
    for table in restore_order:
        for row in rows.get(table, []):
            _update_or_insert_row(conn, table, row)


def _update_or_insert_row(conn, table: str, row: dict[str, Any]) -> None:
    pk = _primary_key(table)
    columns = list(row.keys())
    exists = conn.execute(f"SELECT 1 FROM {table} WHERE {pk} = ?", (row[pk],)).fetchone()
    if exists:
        setters = ", ".join(f"{column} = ?" for column in columns if column != pk)
        values = [row[column] for column in columns if column != pk] + [row[pk]]
        if setters:
            conn.execute(f"UPDATE {table} SET {setters} WHERE {pk} = ?", values)
    else:
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
            [row[column] for column in columns],
        )


def rewind_last_turn(snapshot_id: int | None = None) -> dict[str, Any]:
    with connect() as conn:
        if snapshot_id is None:
            row = conn.execute("SELECT * FROM turn_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = conn.execute("SELECT * FROM turn_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise ValueError("No rewind snapshot is available.")
        snapshot = json.loads(row["snapshot"])
        if snapshot.get("format") == "ai-rpg-delta-v1":
            rows = snapshot.get("rows") or {}
            rows["__max_ids__"] = [snapshot.get("max_ids") or {}]
            conn.execute("PRAGMA foreign_keys = OFF")
            _restore_snapshot_rows(conn, rows)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA foreign_key_check")
            HISTORY_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_SUMMARY_PATH.write_text(str(snapshot.get("history_summaries") or ""), encoding="utf-8")
        else:
            _restore_world(snapshot)
        conn.execute("DELETE FROM turn_snapshots WHERE id >= ?", (row["id"],))
    return _state_with_refreshed_source_index()


def _latest_regeneration_target() -> dict[str, Any]:
    with connect() as conn:
        snapshot = conn.execute("SELECT id, turn FROM turn_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        if snapshot is None:
            raise ValueError("No turn is available to regenerate.")
        journal = conn.execute(
            """
            SELECT kind, content
            FROM journal
            WHERE turn = ? AND kind IN ('opening', 'player', 'continue')
            ORDER BY id ASC
            LIMIT 1
            """,
            (int(snapshot["turn"]),),
        ).fetchone()
        if journal is None:
            raise ValueError("The latest turn does not have a regeneratable input.")
        return {
            "snapshot_id": int(snapshot["id"]),
            "turn": int(snapshot["turn"]),
            "input_kind": str(journal["kind"]),
            "content": str(journal["content"] or ""),
        }


def regenerate_last_turn() -> dict[str, Any]:
    target = _latest_regeneration_target()
    rewind_last_turn(target["snapshot_id"])

    input_kind = target["input_kind"]
    if input_kind == "opening":
        payload = play_opening_turn()
    elif input_kind == "continue":
        payload = play_continue_turn()
    else:
        player_input = target["content"].strip()
        if not player_input:
            raise ValueError("The latest player input is empty and cannot be regenerated.")
        payload = play_turn(player_input)

    payload["regenerated"] = True
    payload["regenerated_turn"] = target["turn"]
    payload["regenerated_input_kind"] = input_kind
    return payload


def _next_turn(conn) -> int:
    row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
    turn = int(row["value"]) + 1 if row else 1
    conn.execute(
        "INSERT INTO pacing (key, value) VALUES ('turn', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(turn),),
    )
    return turn


def _upsert_location(conn, name: str, summary: str = "") -> int:
    name = norm_name(name)
    if not name:
        raise ValueError("Location name is required.")
    existing = conn.execute("SELECT id, summary FROM locations WHERE name = ?", (name,)).fetchone()
    if existing:
        if summary and summary not in existing["summary"]:
            merged = f"{existing['summary']} {summary}".strip()[:1400]
            conn.execute("UPDATE locations SET summary = ? WHERE id = ?", (merged, existing["id"]))
        return int(existing["id"])
    cursor = conn.execute(
        "INSERT INTO locations (code, name, summary, visit_count) VALUES (?, ?, ?, 0)",
        (_next_code(conn, "locations", "L"), name, summary[:1400]),
    )
    return int(cursor.lastrowid)


def _find_location_id(conn, name_or_code: str | None) -> int:
    if name_or_code:
        value = norm_name(str(name_or_code))
        value = _alias_target(conn, value, "location") or value
        row = conn.execute("SELECT id FROM locations WHERE code = ? OR name = ?", (value, value)).fetchone()
        if row:
            return int(row["id"])
        return _upsert_location(conn, value)
    player = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    return int(player["current_location_id"])


def _slot_code_from_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name.strip().upper()).strip("_")[:18]
    return base or "SLOT"


def _upsert_equipment_slot(conn, slot: dict[str, Any]) -> str:
    name = norm_name(str(slot.get("name") or slot.get("slot_name") or slot.get("category") or "Gear Slot"))
    code = norm_name(str(slot.get("code") or slot.get("slot_code") or _slot_code_from_name(name))).upper()
    category = str(slot.get("category") or name or "gear")[:80]
    capacity = max(1, min(99, int(slot.get("capacity") or 1)))
    accepts = slot.get("accepts") or []
    if isinstance(accepts, str):
        accepts = [part.strip() for part in accepts.split(",") if part.strip()]
    if not isinstance(accepts, list):
        accepts = []
    source_item = norm_name(str(slot.get("source_item_code") or slot.get("source_item") or ""))
    notes = str(slot.get("notes") or "")[:700]
    sort_order = int(slot.get("sort_order") or 500)
    existing = conn.execute("SELECT * FROM equipment_slots WHERE code = ? OR name = ?", (code, name)).fetchone()
    if existing:
        merged_accepts = _json(existing["accepts"] or "[]", [])
        for item in accepts:
            if item not in merged_accepts:
                merged_accepts.append(str(item)[:80])
        conn.execute(
            """
            UPDATE equipment_slots
            SET name = ?, category = ?, capacity = MAX(capacity, ?), accepts = ?,
                source_item_code = COALESCE(NULLIF(?, ''), source_item_code),
                notes = ?, sort_order = MIN(sort_order, ?)
            WHERE id = ?
            """,
            (name, category, capacity, json.dumps(merged_accepts, ensure_ascii=True), source_item, _merge_text(existing["notes"], notes, 900), sort_order, existing["id"]),
        )
        return str(existing["code"])
    conn.execute(
        """
        INSERT INTO equipment_slots (code, name, category, capacity, accepts, source_item_code, notes, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (code, name, category, capacity, json.dumps(accepts, ensure_ascii=True), source_item, notes, sort_order),
    )
    return code


def _ensure_default_equipment_slots(conn) -> None:
    for code, name, category, capacity, accepts, sort_order in DEFAULT_EQUIPMENT_SLOTS:
        _upsert_equipment_slot(
            conn,
            {
                "code": code,
                "name": name,
                "category": category,
                "capacity": capacity,
                "accepts": accepts,
                "sort_order": sort_order,
                "notes": "Base body slot.",
            },
        )


def _alias_target(conn, value: str, entity_type: str | None = None) -> str | None:
    alias = norm_name(value).lower()
    if not alias:
        return None
    if entity_type:
        row = conn.execute(
            "SELECT entity_code FROM aliases WHERE lower(alias) = ? AND entity_type = ?",
            (alias, entity_type),
        ).fetchone()
    else:
        row = conn.execute("SELECT entity_code FROM aliases WHERE lower(alias) = ?", (alias,)).fetchone()
    return str(row["entity_code"]) if row else None


def _npc_id_by_ref(conn, ref: str | None, location_name: str | None = None) -> int | None:
    if not ref:
        return None
    value = norm_name(str(ref))
    value = _alias_target(conn, value, "npc") or value
    npc = conn.execute("SELECT id FROM npcs WHERE code = ? OR name = ?", (value, value)).fetchone()
    if npc:
        return int(npc["id"])
    if location_name:
        location_id = _find_location_id(conn, location_name)
        npc = conn.execute(
            "SELECT id FROM npcs WHERE location_id = ? AND name = ?",
            (location_id, value),
        ).fetchone()
        return int(npc["id"]) if npc else None
    return None


def _event_id_by_ref(conn, ref: str | None) -> int | None:
    if not ref:
        return None
    value = norm_name(str(ref))
    value = _alias_target(conn, value, "event") or value
    row = conn.execute("SELECT id FROM events WHERE code = ? OR title = ?", (value, value)).fetchone()
    return int(row["id"]) if row else None


def _upsert_npc(conn, npc: dict[str, Any]) -> int | None:
    name = norm_name(str(npc.get("name", "")))
    code = norm_name(str(npc.get("code", "")))
    if not name and code:
        existing = conn.execute("SELECT id FROM npcs WHERE code = ?", (code,)).fetchone()
        return int(existing["id"]) if existing else None
    if not name:
        return None

    location_id = _find_location_id(conn, npc.get("location") or npc.get("location_code"))
    race = str(npc.get("race") or npc.get("species") or "human")[:80]
    role = str(npc.get("role") or "local")[:100]
    summary = str(npc.get("summary") or "")[:1400]
    attitude = str(npc.get("attitude") or "neutral")[:80]
    personality = str(npc.get("personality") or "")[:700]
    likes = str(npc.get("likes") or "")[:700]
    principles = str(npc.get("principles") or npc.get("values") or "")[:700]
    dislikes = str(npc.get("dislikes") or "")[:700]
    rank = str(npc.get("rank") or npc.get("overall_rank") or "F")[:20]
    stat_profile = npc.get("stat_profile") or npc.get("stats") or {}
    skill_profile = npc.get("skill_profile") or npc.get("skills") or {}
    if not isinstance(stat_profile, dict):
        stat_profile = {"notes": str(stat_profile)[:700]}
    if not isinstance(skill_profile, dict):
        skill_profile = {"notes": str(skill_profile)[:700]}
    trust_delta = int(npc.get("trust_delta") or 0)
    known_fact = str(npc.get("known_fact") or "").strip()
    mentioned_by = npc.get("mentioned_by") or npc.get("mentioned_by_code")
    mentioned_by = norm_name(str(mentioned_by)) if mentioned_by else None

    existing = None
    if code:
        existing = conn.execute("SELECT * FROM npcs WHERE code = ?", (code,)).fetchone()
    if existing is None:
        existing = conn.execute(
            "SELECT * FROM npcs WHERE location_id = ? AND name = ?",
            (location_id, name),
        ).fetchone()

    if existing:
        facts = _json(existing["known_facts"] or "[]", [])
        if known_fact and known_fact not in facts:
            facts.append(known_fact[:350])
        merged_summary = existing["summary"]
        if summary and summary not in merged_summary:
            merged_summary = f"{merged_summary} {summary}".strip()[:1400]
        conn.execute(
            """
            UPDATE npcs
            SET location_id = ?, role = ?, summary = ?, attitude = ?,
                race = COALESCE(NULLIF(?, ''), race),
                personality = COALESCE(NULLIF(?, ''), personality),
                likes = COALESCE(NULLIF(?, ''), likes),
                principles = COALESCE(NULLIF(?, ''), principles),
                dislikes = COALESCE(NULLIF(?, ''), dislikes),
                rank = COALESCE(NULLIF(?, ''), rank),
                stat_profile = COALESCE(NULLIF(?, '{}'), stat_profile),
                skill_profile = COALESCE(NULLIF(?, '{}'), skill_profile),
                trust = ?,
                known_facts = ?, mentioned_by = COALESCE(?, mentioned_by)
            WHERE id = ?
            """,
            (
                location_id,
                role,
                merged_summary,
                attitude,
                race,
                personality,
                likes,
                principles,
                dislikes,
                rank,
                json.dumps(stat_profile, ensure_ascii=True),
                json.dumps(skill_profile, ensure_ascii=True),
                clamp(int(existing["trust"]) + trust_delta, -100, 100),
                json.dumps(facts),
                mentioned_by,
                existing["id"],
            ),
        )
        return int(existing["id"])

    new_code = alpha_code(_max_id(conn, "npcs") + 1)
    facts = [known_fact[:350]] if known_fact else []
    cursor = conn.execute(
        """
        INSERT INTO npcs (code, location_id, name, race, role, summary, attitude, personality, likes, principles, dislikes, rank, stat_profile, skill_profile, trust, known_facts, mentioned_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_code,
            location_id,
            name,
            race,
            role,
            summary,
            attitude,
            personality,
            likes,
            principles,
            dislikes,
            rank,
            json.dumps(stat_profile, ensure_ascii=True),
            json.dumps(skill_profile, ensure_ascii=True),
            clamp(trust_delta, -100, 100),
            json.dumps(facts),
            mentioned_by,
        ),
    )
    return int(cursor.lastrowid)


def _apply_inventory(conn, changes: list[dict[str, Any]]) -> None:
    for change in changes:
        name = norm_name(str(change.get("name", "")))
        if not name:
            continue
        delta = int(change.get("quantity_delta") or 0)
        description = str(change.get("description") or "")[:700]
        has_weight = "weight" in change
        has_slot_size = "slot_size" in change
        has_item_type = "item_type" in change or "type" in change
        has_rarity = "rarity" in change
        has_stat_modifiers = "stat_modifiers" in change or "stats" in change or "stat_bonuses" in change
        has_granted_abilities = "granted_abilities" in change or "equipment_abilities" in change or "abilities" in change
        has_stack_limit = "stack_limit" in change
        has_carry_modifier = "carry_modifier" in change
        has_bonus_weight = "container_bonus_weight" in change
        has_bonus_slots = "container_bonus_slots" in change
        has_dimensional = "dimensional_space" in change
        weight = max(0.0, _float(change.get("weight"), 1.0))
        slot_size = max(0, min(99, int(_float(change.get("slot_size"), 1))))
        item_type = str(change.get("item_type") or change.get("type") or "misc")[:80]
        rarity = str(change.get("rarity") or "common")[:80]
        enchantments = change.get("enchantments") or []
        if isinstance(enchantments, str):
            enchantments = [part.strip() for part in enchantments.split(",") if part.strip()]
        if not isinstance(enchantments, list):
            enchantments = []
        stat_modifiers = _normalize_stat_modifiers(change.get("stat_modifiers") or change.get("stats") or change.get("stat_bonuses") or {})
        granted_abilities = _normalize_granted_abilities(
            change.get("granted_abilities") or change.get("equipment_abilities") or change.get("abilities") or [],
            {"name": name, "code": ""},
        )
        stack_limit = max(1, min(1_000_000, int(_float(change.get("stack_limit"), 20))))
        carry_modifier = max(0.05, min(5.0, _float(change.get("carry_modifier"), 1.0)))
        container_bonus_weight = max(0.0, _float(change.get("container_bonus_weight"), 0.0))
        container_bonus_slots = max(0, min(10000, int(_float(change.get("container_bonus_slots"), 0))))
        dimensional_space = 1 if bool(change.get("dimensional_space")) else 0
        existing = conn.execute("SELECT * FROM inventory WHERE name = ?", (name,)).fetchone()
        if existing:
            quantity = max(0, int(existing["quantity"]) + delta)
            merged_description = existing["description"]
            if description and description not in merged_description:
                merged_description = f"{merged_description} {description}".strip()[:900]
            merged_enchantments = _json(existing["enchantments"] or "[]", [])
            for enchantment in enchantments:
                text = str(enchantment)[:160]
                if text and text not in merged_enchantments:
                    merged_enchantments.append(text)
            conn.execute(
                """
                UPDATE inventory
                SET quantity = ?, description = ?,
                    weight = CASE WHEN ? THEN ? ELSE weight END,
                    slot_size = CASE WHEN ? THEN ? ELSE slot_size END,
                    item_type = CASE WHEN ? THEN ? ELSE item_type END,
                    rarity = CASE WHEN ? THEN ? ELSE rarity END,
                    enchantments = ?,
                    stat_modifiers = CASE WHEN ? THEN ? ELSE stat_modifiers END,
                    granted_abilities = CASE WHEN ? THEN ? ELSE granted_abilities END,
                    stack_limit = CASE WHEN ? THEN MAX(stack_limit, ?) ELSE stack_limit END,
                    carry_modifier = CASE WHEN ? THEN ? ELSE carry_modifier END,
                    container_bonus_weight = CASE WHEN ? THEN MAX(container_bonus_weight, ?) ELSE container_bonus_weight END,
                    container_bonus_slots = CASE WHEN ? THEN MAX(container_bonus_slots, ?) ELSE container_bonus_slots END,
                    dimensional_space = CASE WHEN ? THEN MAX(dimensional_space, ?) ELSE dimensional_space END
                WHERE id = ?
                """,
                (
                    quantity,
                    merged_description,
                    int(has_weight),
                    weight,
                    int(has_slot_size),
                    slot_size,
                    int(has_item_type),
                    item_type,
                    int(has_rarity),
                    rarity,
                    json.dumps(merged_enchantments, ensure_ascii=True),
                    int(has_stat_modifiers),
                    json.dumps(stat_modifiers, ensure_ascii=True),
                    int(has_granted_abilities),
                    json.dumps(granted_abilities, ensure_ascii=True),
                    int(has_stack_limit),
                    stack_limit,
                    int(has_carry_modifier),
                    carry_modifier,
                    int(has_bonus_weight),
                    container_bonus_weight,
                    int(has_bonus_slots),
                    container_bonus_slots,
                    int(has_dimensional),
                    dimensional_space,
                    existing["id"],
                ),
            )
            if quantity <= 0:
                conn.execute("UPDATE inventory SET equipped_slot = '' WHERE id = ?", (existing["id"],))
        elif delta > 0:
            conn.execute(
                """
                INSERT INTO inventory (code, name, description, quantity, weight, slot_size, item_type, rarity, enchantments, stat_modifiers, granted_abilities, stack_limit, carry_modifier, container_bonus_weight, container_bonus_slots, dimensional_space)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _next_code(conn, "inventory", "I"),
                    name,
                    description,
                    delta,
                    weight,
                    slot_size,
                    item_type,
                    rarity,
                    json.dumps([str(item)[:160] for item in enchantments], ensure_ascii=True),
                    json.dumps(stat_modifiers, ensure_ascii=True),
                    json.dumps(granted_abilities, ensure_ascii=True),
                    stack_limit,
                    carry_modifier,
                    container_bonus_weight,
                    container_bonus_slots,
                    dimensional_space,
                ),
            )


def _item_by_ref(conn, item_ref: Any) -> sqlite3.Row | None:
    value = norm_name(str(item_ref or ""))
    if not value:
        return None
    value = _alias_target(conn, value, "item") or value
    return conn.execute("SELECT * FROM inventory WHERE code = ? OR name = ?", (value, value)).fetchone()


def _slot_by_ref(conn, slot_ref: Any, slot_name: Any = None) -> sqlite3.Row | None:
    values = [norm_name(str(slot_ref or "")).upper(), norm_name(str(slot_name or ""))]
    for value in values:
        if not value:
            continue
        row = conn.execute("SELECT * FROM equipment_slots WHERE code = ? OR name = ?", (value, value)).fetchone()
        if row:
            return row
    return None


def _apply_equipment_slots(conn, slots: list[dict[str, Any]]) -> None:
    for slot in slots:
        if isinstance(slot, dict):
            _upsert_equipment_slot(conn, slot)


def _slot_capacity_cap(category: str) -> int:
    category = category.lower()
    if category in {"ring", "finger", "finger accessory"}:
        return 15
    if category in {"neck", "necklace"}:
        return 6
    if category in {"wrist", "bracelet"}:
        return 8
    if category in {"decal", "sigil", "cosmetic"}:
        return 20
    return 1


def _apply_equipment_changes(conn, changes: list[dict[str, Any]]) -> None:
    for change in changes:
        if not isinstance(change, dict):
            continue
        item = _item_by_ref(conn, change.get("item_code") or change.get("item_name") or change.get("name"))
        if item is None:
            continue
        equip = change.get("equip")
        if equip is False or str(change.get("action") or "").lower() in {"unequip", "remove"}:
            conn.execute("UPDATE inventory SET equipped_slot = '' WHERE id = ?", (item["id"],))
            continue
        slot = _slot_by_ref(conn, change.get("slot_code"), change.get("slot_name") or change.get("slot"))
        if slot is None:
            slot_code = _upsert_equipment_slot(
                conn,
                {
                    "name": change.get("slot_name") or change.get("slot") or str(item["item_type"] or "Gear Slot"),
                    "category": change.get("slot_category") or item["item_type"] or "gear",
                    "capacity": change.get("capacity") or 1,
                    "accepts": [item["item_type"] or item["name"]],
                    "source_item_code": change.get("source_item_code") or "",
                    "notes": change.get("notes") or "DM-created equipment slot.",
                },
            )
            slot = conn.execute("SELECT * FROM equipment_slots WHERE code = ?", (slot_code,)).fetchone()
        if slot is None:
            continue
        equipped_count = conn.execute("SELECT COUNT(*) AS count FROM inventory WHERE equipped_slot = ?", (slot["code"],)).fetchone()["count"]
        capacity = max(1, int(slot["capacity"] or 1))
        if equipped_count >= capacity:
            category = str(slot["category"] or "")
            cap = _slot_capacity_cap(category)
            if capacity < cap:
                capacity += 1
                conn.execute("UPDATE equipment_slots SET capacity = ? WHERE id = ?", (capacity, slot["id"]))
            else:
                conn.execute("UPDATE inventory SET equipped_slot = '' WHERE equipped_slot = ?", (slot["code"],))
        conn.execute("UPDATE inventory SET equipped_slot = ? WHERE id = ?", (slot["code"], item["id"]))


def _apply_inventory_capacity_modifiers(conn, modifiers: list[dict[str, Any]]) -> None:
    for modifier in modifiers:
        if not isinstance(modifier, dict):
            continue
        source = norm_name(str(modifier.get("source") or modifier.get("name") or "Capacity Effect"))
        if not source:
            continue
        code = norm_name(str(modifier.get("code") or _slot_code_from_name(source))).upper()
        active = 0 if modifier.get("active") is False or str(modifier.get("action") or "").lower() in {"remove", "inactive", "end"} else 1
        conn.execute(
            """
            INSERT INTO inventory_capacity_modifiers (code, source, weight_bonus, slot_bonus, carry_modifier, dimensional_space, active, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                source = excluded.source,
                weight_bonus = excluded.weight_bonus,
                slot_bonus = excluded.slot_bonus,
                carry_modifier = excluded.carry_modifier,
                dimensional_space = excluded.dimensional_space,
                active = excluded.active,
                notes = excluded.notes
            """,
            (
                code,
                source,
                max(0.0, _float(modifier.get("weight_bonus"), 0.0)),
                max(0, int(_float(modifier.get("slot_bonus"), 0))),
                max(0.05, min(5.0, _float(modifier.get("carry_modifier"), 1.0))),
                1 if bool(modifier.get("dimensional_space")) else 0,
                active,
                str(modifier.get("notes") or "")[:700],
            ),
        )


def _apply_skills(conn, changes: list[dict[str, Any]]) -> None:
    settings = _settings(conn).get("playthrough_options", {})
    speed = settings.get("skill_growth_speed") or "normal"
    multiplier = settings.get("skill_growth_multiplier")
    for change in changes:
        name = norm_name(str(change.get("name", ""))).lower()
        if not name:
            continue
        delta = _scaled_delta(int(change.get("delta") or 0), str(speed), float(multiplier) if multiplier else None)
        notes = str(change.get("notes") or "")[:700]
        existing = conn.execute("SELECT id, value, notes FROM player_skills WHERE name = ?", (name,)).fetchone()
        if existing:
            value = clamp(int(existing["value"]) + delta, -10, 100)
            merged_notes = existing["notes"]
            if notes and notes not in merged_notes:
                merged_notes = f"{merged_notes} {notes}".strip()[:900]
            conn.execute(
                "UPDATE player_skills SET value = ?, notes = ? WHERE id = ?",
                (value, merged_notes, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO player_skills (name, value, notes) VALUES (?, ?, ?)",
                (name, clamp(delta, -10, 100), notes),
            )


def _apply_player(conn, player_patch: dict[str, Any]) -> None:
    player = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    if not player:
        return

    settings = _settings(conn).get("playthrough_options", {})
    max_health = clamp(int(player["max_health"]) + int(player_patch.get("max_health_delta") or 0), 1, 999)
    health = clamp(int(player["health"]) + int(player_patch.get("health_delta") or 0), 0, max_health)
    level_delta = int(player_patch.get("level_delta") or 0) if settings.get("leveling_system", True) else 0
    xp_delta = (
        _scaled_delta(
            int(player_patch.get("xp_delta") or 0),
            str(settings.get("xp_growth_speed") or "normal"),
            float(settings.get("xp_growth_multiplier")) if settings.get("xp_growth_multiplier") else None,
        )
        if settings.get("leveling_system", True)
        else 0
    )
    level = clamp(int(player["level"]) + level_delta, 1, 100)
    xp = clamp(int(player["xp"]) + xp_delta, 0, 1_000_000)
    gold = clamp(int(player["gold"]) + int(player_patch.get("gold_delta") or 0), 0, 1_000_000)
    raw_karma_delta = clamp(int(player_patch.get("karma_delta") or 0), -25, 25)
    karma_reason = str(player_patch.get("karma_reason") or "Karma changed because of the player's action.")[:900]
    karma_visibility = str(player_patch.get("karma_visibility") or "local")[:80]
    turn = _turn_value(conn)
    active_alias, alias_note = _apply_active_alias_reputation(conn, raw_karma_delta, turn, karma_reason)
    if active_alias is not None and raw_karma_delta:
        karma_delta, leak_note = _alias_reputation_leak_delta(raw_karma_delta, karma_visibility, bool(active_alias["disguised"]))
        karma_reason = f"{karma_reason}{alias_note}{leak_note}"[:900]
    else:
        karma_delta = raw_karma_delta
    karma = clamp(int(player["karma"]) + karma_delta, -1000, 1000)
    location_id = int(player["current_location_id"])
    previous_location_id = location_id

    move_to = player_patch.get("move_to_location") or player_patch.get("move_to_location_code")
    if move_to:
        location_id = _find_location_id(conn, str(move_to))
        if location_id != previous_location_id:
            _settle_departed_location_events(conn, previous_location_id, turn)
            conn.execute("UPDATE locations SET visit_count = visit_count + 1 WHERE id = ?", (location_id,))
            _refresh_arrived_location_events(conn, location_id, turn)

    conn.execute(
        """
        UPDATE player
        SET health = ?, max_health = ?, level = ?, xp = ?, gold = ?, karma = ?, current_location_id = ?
        WHERE id = 1
        """,
        (health, max_health, level, xp, gold, karma, location_id),
    )
    if karma_delta:
        conn.execute(
            """
            INSERT INTO karma_history (turn, delta, total, reason, visibility)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                turn,
                karma_delta,
                karma,
                karma_reason,
                karma_visibility,
            ),
        )


def _event_persistence(value: Any, status: str = "active", fame_score: int = 0) -> str:
    persistence = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "scene": "temporary",
        "transient": "temporary",
        "one_off": "temporary",
        "one_time": "temporary",
        "traveling_visitor": "traveling",
        "travelling": "traveling",
        "durable": "persistent",
        "local": "persistent",
    }
    persistence = aliases.get(persistence, persistence)
    if persistence in EVENT_PERSISTENCE_VALUES:
        return persistence
    if status == "background" or fame_score > 0:
        return "persistent"
    return "temporary"


def _event_default_disappear_chance(persistence: str) -> int:
    if persistence == "temporary":
        return 70
    if persistence == "traveling":
        return 82
    if persistence == "recurring":
        return 45
    return 0


def _event_default_respawn_chance(persistence: str) -> int:
    if persistence == "recurring":
        return 12
    if persistence == "traveling":
        return 4
    return 0


def _event_chance(value: Any, default: int) -> int:
    try:
        chance = int(float(value))
    except (TypeError, ValueError):
        chance = default
    return clamp(chance, 0, 95)


def _first_lifecycle_value(event: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = event.get(key)
        if value is not None and value != "":
            return value
    return None


def _settle_departed_location_events(conn, location_id: int, turn: int) -> None:
    rows = conn.execute(
        """
        SELECT id, persistence, disappear_chance
        FROM events
        WHERE location_id = ? AND status = 'active' AND persistence IN ('temporary', 'traveling', 'recurring')
        """,
        (location_id,),
    ).fetchall()
    for row in rows:
        persistence = str(row["persistence"] or "temporary")
        chance = _event_chance(row["disappear_chance"], _event_default_disappear_chance(persistence))
        if random.randint(1, 100) <= chance:
            next_status = "background" if persistence == "recurring" else "resolved"
            conn.execute(
                "UPDATE events SET status = ?, last_seen_turn = ? WHERE id = ?",
                (next_status, turn, row["id"]),
            )
        else:
            conn.execute("UPDATE events SET last_seen_turn = ? WHERE id = ?", (turn, row["id"]))


def _refresh_arrived_location_events(conn, location_id: int, turn: int) -> None:
    conn.execute(
        "UPDATE events SET last_seen_turn = ? WHERE location_id = ? AND status IN ('active', 'background')",
        (turn, location_id),
    )
    rows = conn.execute(
        """
        SELECT id, persistence, respawn_chance
        FROM events
        WHERE location_id = ? AND status IN ('resolved', 'background') AND persistence IN ('traveling', 'recurring')
        """,
        (location_id,),
    ).fetchall()
    for row in rows:
        persistence = str(row["persistence"] or "recurring")
        chance = _event_chance(row["respawn_chance"], _event_default_respawn_chance(persistence))
        if chance and random.randint(1, 100) <= chance:
            conn.execute("UPDATE events SET status = 'active', last_seen_turn = ? WHERE id = ?", (turn, row["id"]))


def _apply_relationships(conn, relationships: list[dict[str, Any]]) -> None:
    for rel in relationships:
        source_ref = rel.get("source_code") or rel.get("source")
        target_ref = rel.get("target_code") or rel.get("target")
        source_id = _npc_id_by_ref(conn, source_ref, rel.get("location"))
        target_id = _npc_id_by_ref(conn, target_ref, rel.get("location"))
        if source_id is None or target_id is None or source_id == target_id:
            continue
        summary = str(rel.get("summary") or "")[:1100]
        delta = int(rel.get("weight_delta") or 1)
        existing = conn.execute(
            "SELECT id, weight, summary FROM relationships WHERE source_npc_id = ? AND target_npc_id = ?",
            (source_id, target_id),
        ).fetchone()
        if existing:
            weight = clamp(int(existing["weight"]) + delta, -10, 10)
            merged = existing["summary"]
            if summary and summary not in merged:
                merged = f"{merged} {summary}".strip()[:1100]
            conn.execute(
                "UPDATE relationships SET weight = ?, summary = ? WHERE id = ?",
                (weight, merged, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO relationships (source_npc_id, target_npc_id, summary, weight) VALUES (?, ?, ?, ?)",
                (source_id, target_id, summary, clamp(delta, -10, 10)),
            )


def _apply_events(conn, events: list[dict[str, Any]], turn: int) -> None:
    for event in events:
        title = norm_name(str(event.get("title", "")))
        if not title:
            continue
        code = norm_name(str(event.get("code", "")))
        location_ref = event.get("location") or event.get("location_code")
        if location_ref:
            location_ref = _alias_target(conn, str(location_ref), "location") or location_ref
        location_id = _find_location_id(conn, location_ref) if location_ref else None
        npc_id = _npc_id_by_ref(conn, event.get("npc_code") or event.get("npc"))
        summary = str(event.get("summary") or "")[:1400]
        status = str(event.get("status") or "active")[:60]
        fame_score = clamp(int(event.get("fame_score") or event.get("fame") or 0), 0, 80)
        fame_scope = str(event.get("fame_scope") or "local")[:80]
        rumor_summary = str(event.get("rumor_summary") or event.get("rumor") or "")[:700]
        persistence = _event_persistence(event.get("persistence") or event.get("event_type") or event.get("lifecycle"), status, fame_score)
        disappear_chance = _event_chance(_first_lifecycle_value(event, "disappear_chance", "despawn_chance"), _event_default_disappear_chance(persistence))
        respawn_chance = _event_chance(_first_lifecycle_value(event, "respawn_chance", "return_chance"), _event_default_respawn_chance(persistence))

        existing = None
        if code:
            existing = conn.execute("SELECT * FROM events WHERE code = ?", (code,)).fetchone()
        if existing is None:
            existing = conn.execute("SELECT * FROM events WHERE title = ?", (title,)).fetchone()

        if existing:
            merged = existing["summary"]
            if summary and summary not in merged:
                merged = f"{merged} {summary}".strip()[:1400]
            conn.execute(
                """
                UPDATE events
                SET location_id = COALESCE(?, location_id),
                    npc_id = COALESCE(?, npc_id),
                    summary = ?,
                    status = ?,
                    fame_score = MAX(fame_score, ?),
                    fame_scope = CASE WHEN ? != '' THEN ? ELSE fame_scope END,
                    rumor_summary = CASE WHEN ? != '' THEN ? ELSE rumor_summary END,
                    persistence = ?,
                    disappear_chance = ?,
                    respawn_chance = ?,
                    last_seen_turn = ?
                WHERE id = ?
                """,
                (location_id, npc_id, merged, status, fame_score, fame_scope, fame_scope, rumor_summary, rumor_summary, persistence, disappear_chance, respawn_chance, turn, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO events (code, location_id, npc_id, title, summary, status, fame_score, fame_scope, rumor_summary, persistence, disappear_chance, respawn_chance, last_seen_turn, turn)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (_next_code(conn, "events", "E"), location_id, npc_id, title, summary, status, fame_score, fame_scope, rumor_summary, persistence, disappear_chance, respawn_chance, turn, turn),
            )


def _apply_gm_events(conn, gm_events: list[dict[str, Any]], turn: int) -> None:
    for event in gm_events:
        if not isinstance(event, dict):
            continue
        summary = str(event.get("summary") or event.get("secret") or event.get("plan") or "").strip()[:1400]
        trigger = str(event.get("trigger") or event.get("condition") or event.get("when") or "").strip()[:900]
        if not summary and not trigger:
            continue
        status = str(event.get("status") or "pending").strip().lower()[:40]
        if status not in {"pending", "seeded", "active", "resolved", "suppressed"}:
            status = "pending"
        priority = clamp(int(_float(event.get("priority") or event.get("weight"), 3)), 0, 10)
        location_ref = event.get("location_code") or event.get("location")
        npc_ref = event.get("npc_code") or event.get("npc")
        event_ref = event.get("event_code") or event.get("event")
        location_id = _find_location_id(conn, str(location_ref)) if location_ref else None
        npc_id = _npc_id_by_ref(conn, npc_ref)
        visible_event_id = _event_id_by_ref(conn, event_ref)
        conn.execute(
            """
            INSERT INTO gm_events (turn, trigger, summary, status, priority, location_id, npc_id, event_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (turn, trigger, summary, status, priority, location_id, npc_id, visible_event_id),
        )


def _apply_conversations(conn, conversations: list[dict[str, Any]], turn: int) -> None:
    for convo in conversations:
        summary = str(convo.get("summary") or "")[:1400]
        if not summary:
            continue
        npc_id = _npc_id_by_ref(conn, convo.get("npc_code") or convo.get("npc"))
        claims = convo.get("player_claims") or []
        conn.execute(
            "INSERT INTO conversations (turn, npc_id, topic, summary, player_claims) VALUES (?, ?, ?, ?, ?)",
            (
                turn,
                npc_id,
                str(convo.get("topic") or "")[:120],
                summary,
                json.dumps(claims if isinstance(claims, list) else [str(claims)]),
            ),
        )


def _apply_response_drafts(conn, drafts: list[dict[str, Any]], turn: int) -> None:
    for draft in drafts:
        claim = str(draft.get("claim") or "")[:700]
        if not claim:
            continue
        conn.execute(
            """
            INSERT INTO response_drafts (turn, claim, verdict, skill, difficulty_class, result, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                turn,
                claim,
                str(draft.get("verdict") or "unknown")[:80],
                str(draft.get("skill") or "")[:80],
                clamp(int(draft.get("difficulty_class") or 10), 1, 40),
                str(draft.get("result") or "")[:120],
                str(draft.get("notes") or "")[:1000],
            ),
        )


def _merge_text(existing: str, addition: str, limit: int) -> str:
    addition = addition.strip()
    if not addition:
        return existing
    if addition in existing:
        return existing
    return f"{existing} {addition}".strip()[:limit]


def _apply_index_updates(conn, updates: list[dict[str, Any]]) -> None:
    for update in updates:
        entity_type = str(update.get("entity_type") or "").lower()
        code = norm_name(str(update.get("code") or ""))
        summary_append = str(update.get("summary_append") or "")[:1000]
        if not entity_type or not code:
            continue

        if entity_type == "npc":
            npc = conn.execute("SELECT * FROM npcs WHERE code = ?", (code,)).fetchone()
            if not npc:
                continue
            facts = _json(npc["known_facts"] or "[]", [])
            known_fact = str(update.get("known_fact") or "").strip()
            if known_fact and known_fact not in facts:
                facts.append(known_fact[:350])
            stat_profile = _json(npc["stat_profile"] or "{}", {})
            skill_profile = _json(npc["skill_profile"] or "{}", {})
            if isinstance(update.get("stat_profile"), dict):
                stat_profile.update(update["stat_profile"])
            if isinstance(update.get("skill_profile"), dict):
                skill_profile.update(update["skill_profile"])
            conn.execute(
                """
                UPDATE npcs
                SET summary = ?, known_facts = ?,
                    personality = COALESCE(NULLIF(?, ''), personality),
                    race = COALESCE(NULLIF(?, ''), race),
                    likes = COALESCE(NULLIF(?, ''), likes),
                    principles = COALESCE(NULLIF(?, ''), principles),
                    dislikes = COALESCE(NULLIF(?, ''), dislikes),
                    rank = COALESCE(NULLIF(?, ''), rank),
                    stat_profile = ?,
                    skill_profile = ?
                WHERE code = ?
                """,
                (
                    _merge_text(npc["summary"], summary_append, 1400),
                    json.dumps(facts),
                    str(update.get("personality") or "")[:700],
                    str(update.get("race") or update.get("species") or "")[:80],
                    str(update.get("likes") or "")[:700],
                    str(update.get("principles") or "")[:700],
                    str(update.get("dislikes") or "")[:700],
                    str(update.get("rank") or "")[:20],
                    json.dumps(stat_profile, ensure_ascii=True),
                    json.dumps(skill_profile, ensure_ascii=True),
                    code,
                ),
            )
        elif entity_type == "location":
            row = conn.execute("SELECT summary FROM locations WHERE code = ?", (code,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE locations SET summary = ? WHERE code = ?",
                    (_merge_text(row["summary"], summary_append, 1400), code),
                )
        elif entity_type == "item":
            row = conn.execute("SELECT description FROM inventory WHERE code = ?", (code,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE inventory SET description = ? WHERE code = ?",
                    (_merge_text(row["description"], summary_append, 900), code),
                )
        elif entity_type == "event":
            row = conn.execute("SELECT summary FROM events WHERE code = ?", (code,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE events SET summary = ?, status = COALESCE(NULLIF(?, ''), status) WHERE code = ?",
                    (
                        _merge_text(row["summary"], summary_append, 1500),
                        str(update.get("status") or "")[:60],
                        code,
                    ),
                )


def _apply_ability_updates(conn, updates: list[dict[str, Any]]) -> None:
    for update in updates:
        name = norm_name(str(update.get("name") or ""))
        if not name:
            continue
        ability = conn.execute("SELECT * FROM abilities WHERE name = ?", (name,)).fetchone()
        if not ability:
            continue
        additions = _merge_text(ability["additions"] or "", str(update.get("addition") or update.get("additions") or ""), 1200)
        cost = str(update.get("cost") or "")[:300]
        prerequisites = str(update.get("prerequisites") or "")[:500]
        conn.execute(
            """
            UPDATE abilities
            SET additions = ?,
                cost = COALESCE(NULLIF(?, ''), cost),
                prerequisites = COALESCE(NULLIF(?, ''), prerequisites)
            WHERE id = ?
            """,
            (additions, cost, prerequisites, ability["id"]),
        )


def _summarize_turn(result: dict[str, Any], player_input: str) -> str:
    summary = str(result.get("turn_summary") or "").strip()
    if summary:
        return summary[:700]
    scene_focus = str(result.get("scene_focus") or "scene")
    codes = sorted(set(re.findall(r"\[\[([A-Z]+|L\d+|I\d+|E\d+)]]", str(result.get("narration") or ""), re.IGNORECASE)))
    code_text = ", ".join(codes[:10]) if codes else "no indexed refs"
    return f"player: {player_input[:160]}. response: {scene_focus}; mentioned {code_text}."[:700]


def _write_turn_summary(conn, turn: int, result: dict[str, Any], player_input: str) -> None:
    summary = _summarize_turn(result, player_input)
    conn.execute("INSERT INTO turn_summaries (turn, summary) VALUES (?, ?)", (turn, summary))
    HISTORY_SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_SUMMARY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"turn": turn, "summary": summary}, ensure_ascii=True) + "\n")


def _write_model_usage(conn, turn: int, result: dict[str, Any]) -> None:
    for entry in result.get("_model_usage") or []:
        conn.execute(
            "INSERT INTO model_logs (turn, phase, chars, estimated_tokens) VALUES (?, ?, ?, ?)",
            (
                turn,
                str(entry.get("phase") or "unknown")[:40],
                int(entry.get("chars") or 0),
                int(entry.get("estimated_tokens") or 0),
            ),
        )


def _verified_memory_source(result: dict[str, Any]) -> str:
    phases = {str(entry.get("phase") or "") for entry in result.get("_model_usage") or [] if isinstance(entry, dict)}
    if "verify_skipped_certainty" in phases:
        return "deterministic_policy"
    if any(phase.startswith("verify") for phase in phases):
        return "model_verifier"
    return ""


def _write_verification_memory(
    conn,
    turn: int,
    result: dict[str, Any],
    prompt_context: dict[str, Any] | None,
    used_fallback: bool,
) -> None:
    if used_fallback or not isinstance(prompt_context, dict):
        return
    self_check = result.get("self_check") if isinstance(result.get("self_check"), dict) else {}
    if self_check.get("passed") is not True:
        return
    source = _verified_memory_source(result)
    if not source:
        return
    turn_plan = prompt_context.get("turn_plan") or {}
    if turn_plan.get("turn_kind") in {"opening_scene", "continue_scene"}:
        return
    checks = [str(check or "").strip() for check in turn_plan.get("verification_checks") or [] if str(check or "").strip()]
    if not checks:
        return
    scopes = _verification_memory_scopes(prompt_context)
    policy = result.get("_verification_policy") if isinstance(result.get("_verification_policy"), dict) else {}
    try:
        policy_certainty = float(policy.get("certainty") or 0)
    except (TypeError, ValueError):
        policy_certainty = 0
    confidence = max(VERIFICATION_MEMORY_CONFIDENCE_MIN, policy_certainty, 0.92 if source == "model_verifier" else 0.88)
    confidence = min(1.0, round(confidence, 3))
    evidence = json.dumps(
        {
            "reference_check": self_check.get("reference_check"),
            "consistency_check": self_check.get("consistency_check"),
            "turn_summary": result.get("turn_summary"),
            "policy_mode": policy.get("mode"),
        },
        ensure_ascii=True,
    )[:1400]
    entity_codes = json.dumps(_verification_entity_codes(prompt_context), ensure_ascii=True)
    for check in checks:
        scope = scopes.get(check)
        if not scope:
            continue
        conn.execute(
            """
            INSERT INTO verification_memory (
                scope_key, check_name, intent, turn_kind, entity_codes, confidence, source,
                last_verified_turn, hit_count, evidence, context_signature
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(scope_key, check_name) DO UPDATE SET
                confidence = MAX(verification_memory.confidence, excluded.confidence),
                source = excluded.source,
                last_verified_turn = excluded.last_verified_turn,
                hit_count = verification_memory.hit_count + 1,
                evidence = excluded.evidence,
                context_signature = excluded.context_signature,
                entity_codes = excluded.entity_codes,
                intent = excluded.intent,
                turn_kind = excluded.turn_kind,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                scope["scope_key"],
                check,
                str(turn_plan.get("primary_intent") or "")[:80],
                str(turn_plan.get("turn_kind") or "")[:80],
                entity_codes,
                confidence,
                source,
                turn,
                evidence,
                scope["context_signature"],
            ),
        )


def _apply_deterministic_combat(conn, combat: dict[str, Any], turn: int) -> None:
    if not isinstance(combat, dict) or combat.get("status") != "resolved_player_attack":
        return
    target = combat.get("target") if isinstance(combat.get("target"), dict) else {}
    resolution = combat.get("resolution") if isinstance(combat.get("resolution"), dict) else {}
    target_code = norm_name(str(target.get("code") or ""))
    damage = max(0, _int_from_any(resolution.get("damage"), 0))
    if not target_code:
        return
    row = conn.execute("SELECT id, name, health, max_health FROM npcs WHERE code = ?", (target_code,)).fetchone()
    if row is None:
        return
    max_health = max(0, int(row["max_health"] or 0))
    current_health = int(row["health"] if row["health"] is not None else max_health)
    if max_health <= 0:
        return
    next_health = clamp(current_health - damage, 0, max_health)
    conn.execute("UPDATE npcs SET health = ? WHERE id = ?", (next_health, row["id"]))
    weapon = str((combat.get("player_attack") or {}).get("weapon") or "unarmed")[:120]
    outcome = str(resolution.get("outcome") or "resolved")[:80]
    conn.execute(
        "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
        (
            turn,
            "mechanics",
            f"Deterministic combat: {weapon} vs {target_code} {row['name']} resolved as {outcome}; damage {damage}; health {current_health}->{next_health}/{max_health}."[:1400],
        ),
    )


def _public_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _safe_trace_kind(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "turn").strip().lower()).strip("-")
    return cleaned or "turn"


def _turn_without_private_trace(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"_model_trace", "_model_usage"}}


def _prune_model_trace_files() -> None:
    keep = max(1, min(500, int(_float(os.getenv("AI_RPG_MODEL_TRACE_KEEP"), 50))))
    files = sorted(MODEL_TRACE_DIR.glob("turn-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old_path in files[keep:]:
        try:
            old_path.unlink()
        except OSError:
            pass


def _write_model_trace_file(
    turn: int,
    input_kind: str,
    player_input: str,
    model_input: str,
    prompt_context: dict[str, Any],
    result: dict[str, Any],
    used_fallback: bool,
    fallback_reason: str,
) -> str:
    MODEL_TRACE_DIR.mkdir(parents=True, exist_ok=True)
    fallback_notice = _fallback_notice(fallback_reason) if used_fallback else ""
    payload = {
        "format": "ai-rpg-model-trace-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "turn": turn,
        "input_kind": input_kind,
        "handoff_model": [
            "world.get_state include_hidden=True",
            "world.build_prompt_context deterministic planner",
            "world.verification_memory matching for already-cleared checks",
            "llm deterministic context cleanup before draft",
            "llm.generate_turn draft JSON call",
            "llm deterministic draft payload cleanup before verifier",
            "llm certainty policy uses deterministic and cached checks",
            "llm JSON repair/retry paths as needed",
            "llm verifier JSON call when remaining checks require it",
            "llm deterministic verified payload cleanup before world application",
            "llm narration depth retry as needed",
            "world.apply_turn SQLite state application or deterministic fallback",
        ],
        "trace_note": "This file contains observable prompts, raw model output, parsed JSON, deterministic handoff cleanup decisions, verifier self_check, app decisions, errors, and fallback data. It cannot include private hidden chain-of-thought that the model did not return.",
        "player_input": player_input,
        "model_input": model_input,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "fallback_notice": fallback_notice,
        "prompt_context": prompt_context,
        "final_turn": _turn_without_private_trace(result),
        "model_usage": result.get("_model_usage") or [],
        "model_trace": result.get("_model_trace") or [],
    }
    suffix = "-fallback" if used_fallback else ""
    path = MODEL_TRACE_DIR / f"turn-{turn:06d}-{_safe_trace_kind(input_kind)}{suffix}.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    _prune_model_trace_files()
    return _public_path(path)


def _narration_text(result: dict[str, Any]) -> str:
    segments = result.get("narration_segments")
    if isinstance(segments, list) and segments:
        joined = "\n\n".join(str(segment.get("text") or "") for segment in segments if isinstance(segment, dict)).strip()
        if joined:
            result["narration"] = joined
            return joined
    return str(result.get("narration") or "")


def _active_player_alias_row(conn) -> Any:
    return conn.execute("SELECT * FROM player_aliases WHERE active = 1 ORDER BY updated_at DESC LIMIT 1").fetchone()


def _turn_value(conn) -> int:
    row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
    return int(row["value"]) if row else 0


def create_player_alias(alias: str, notes: str = "") -> dict[str, Any]:
    alias = norm_name(alias)
    notes = str(notes or "")[:900]
    if not alias:
        raise ValueError("Alias is required.")

    with connect() as conn:
        settings = _settings(conn)
        turn = _turn_value(conn)
        if settings.get("setup_complete") != "true" and settings.get("setup_complete") is not True:
            raise ValueError("Start the playthrough before creating a gameplay alias.")
        if turn <= 0:
            raise ValueError("Gameplay aliases become available after the opening turn.")
        conn.execute("UPDATE player_aliases SET active = 0, updated_at = CURRENT_TIMESTAMP")
        conn.execute(
            """
            INSERT INTO player_aliases (alias, reputation, notes, active, disguised, disguise_description, created_turn, last_used_turn)
            VALUES (?, 0, ?, 1, 0, '', ?, ?)
            ON CONFLICT(alias) DO UPDATE SET
                notes = COALESCE(NULLIF(excluded.notes, ''), notes),
                active = 1,
                last_used_turn = excluded.last_used_turn,
                updated_at = CURRENT_TIMESTAMP
            """,
            (alias, notes, turn, turn),
        )
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, "alias", f"Player began using gameplay alias '{alias}'. Disguise is not active."[:1400]),
        )
    return _state_with_refreshed_source_index()


def update_player_alias_state(alias_id: int | None, active: bool | None = None, disguised: bool | None = None, disguise_description: str = "") -> dict[str, Any]:
    disguise_description = str(disguise_description or "")[:300]
    with connect() as conn:
        turn = _turn_value(conn)
        if alias_id is None:
            conn.execute("UPDATE player_aliases SET active = 0, updated_at = CURRENT_TIMESTAMP")
            conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)", (turn, "alias", "Player stopped using an active gameplay alias."))
            return _state_with_refreshed_source_index()

        alias = conn.execute("SELECT * FROM player_aliases WHERE id = ?", (alias_id,)).fetchone()
        if alias is None:
            raise ValueError("Unknown gameplay alias.")
        if active is True:
            conn.execute("UPDATE player_aliases SET active = 0, updated_at = CURRENT_TIMESTAMP")
        active_value = int(alias["active"] if active is None else bool(active))
        disguised_value = int(alias["disguised"] if disguised is None else bool(disguised))
        description_value = disguise_description if disguise_description or disguised is not None else alias["disguise_description"]
        conn.execute(
            """
            UPDATE player_aliases
            SET active = ?, disguised = ?, disguise_description = ?, last_used_turn = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (active_value, disguised_value, description_value, turn, alias_id),
        )
        status = "active" if active_value else "inactive"
        disguise = "disguised" if disguised_value else "not disguised"
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, "alias", f"Gameplay alias '{alias['alias']}' is {status} and {disguise}. Worn disguise: {description_value or 'none'}."[:1400]),
        )
    return _state_with_refreshed_source_index()


def _alias_reputation_leak_delta(delta: int, visibility: str, disguised: bool) -> tuple[int, str]:
    if not delta:
        return 0, ""
    visibility = str(visibility or "local").lower()
    if disguised:
        multiplier = {"private": 0.0, "local": 0.25, "faction": 0.5, "public": 0.75}.get(visibility, 0.25)
        leaked = int(round(delta * multiplier))
        note = " Active alias is disguised, so true-identity reputation only leaks by witness scope."
        return clamp(leaked, -25, 25), note
    penalty = -max(1, min(5, (abs(delta) + 3) // 4)) if delta < 0 else 0
    note = " Active alias is not protected by a disguise, so true-identity reputation also changes."
    if penalty:
        note += " Bad actions take an extra no-disguise reputation penalty."
    return clamp(delta + penalty, -25, 25), note


def _apply_active_alias_reputation(conn, delta: int, turn: int, reason: str) -> tuple[sqlite3.Row | None, str]:
    alias = _active_player_alias_row(conn)
    if alias is None or not delta:
        return alias, ""
    reputation = clamp(int(alias["reputation"] or 0) + delta, -1000, 1000)
    notes = _merge_text(str(alias["notes"] or ""), f"T{turn}: {delta:+} {reason}"[:260], 1400)
    conn.execute(
        """
        UPDATE player_aliases
        SET reputation = ?, notes = ?, last_used_turn = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (reputation, notes, turn, alias["id"]),
    )
    conn.execute(
        "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
        (turn, "alias", f"Alias '{alias['alias']}' reputation changed by {delta:+} to {reputation}: {reason}"[:1400]),
    )
    return alias, f" Active alias '{alias['alias']}' reputation changed by {delta:+}."


def add_alias(alias: str, entity_type: str, entity_code: str) -> dict[str, Any]:
    alias = norm_name(alias).lower()
    entity_type = norm_name(entity_type).lower()
    entity_code = norm_name(entity_code)
    allowed = {"npc", "location", "item", "event"}
    if entity_type not in allowed:
        raise ValueError("Unknown entity type.")
    if not alias or not entity_code:
        raise ValueError("Alias and entity code are required.")

    with connect() as conn:
        exists = False
        if entity_type == "npc":
            exists = conn.execute("SELECT 1 FROM npcs WHERE code = ?", (entity_code,)).fetchone() is not None
        elif entity_type == "location":
            exists = conn.execute("SELECT 1 FROM locations WHERE code = ?", (entity_code,)).fetchone() is not None
        elif entity_type == "item":
            exists = conn.execute("SELECT 1 FROM inventory WHERE code = ?", (entity_code,)).fetchone() is not None
        elif entity_type == "event":
            exists = conn.execute("SELECT 1 FROM events WHERE code = ?", (entity_code,)).fetchone() is not None
        if not exists:
            raise ValueError("Entity code does not exist.")
        conn.execute(
            """
            INSERT INTO aliases (alias, entity_type, entity_code)
            VALUES (?, ?, ?)
            ON CONFLICT(alias) DO UPDATE SET entity_type = excluded.entity_type, entity_code = excluded.entity_code
            """,
            (alias, entity_type, entity_code),
        )
    return _state_with_refreshed_source_index()


def _expand_input_references(context: dict[str, Any], player_input: str) -> str:
    refs: dict[str, str] = {}
    for location in context.get("locations", []):
        refs[f"#{location['code']}"] = f"{location['name']} ({location['code']}, location)"
        for npc in location.get("npcs", []):
            refs[f"@{npc['code']}"] = f"{npc['name']} ({npc['code']}, NPC)"
    for item in context.get("inventory", []):
        refs[f"!{item['code']}"] = f"{item['name']} ({item['code']}, item)"
    for event in context.get("events", []):
        refs[f"&{event['code']}"] = f"{event['title']} ({event['code']}, event)"
    for alias in context.get("aliases", []):
        prefix = {"npc": "@", "location": "#", "item": "!", "event": "&"}.get(alias["entity_type"], "")
        if prefix:
            refs[f"{prefix}{alias['alias']}"] = f"{alias['entity_code']} ({alias['entity_type']} alias: {alias['alias']})"

    found = {token: label for token, label in refs.items() if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", player_input, re.IGNORECASE)}
    if not found:
        return player_input
    expansions = "; ".join(f"{token} = {label}" for token, label in sorted(found.items()))
    return f"{player_input}\n\nResolved player references: {expansions}"


def apply_turn(
    result: dict[str, Any],
    player_input: str,
    used_fallback: bool = False,
    fallback_reason: str = "",
    input_kind: str = "player",
    prompt_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        next_turn = int(row["value"]) + 1 if row else 1
        _save_snapshot(conn, next_turn, result)
        turn = _next_turn(conn)
        narration = _narration_text(result)

        for location in result.get("locations") or []:
            _upsert_location(conn, str(location.get("name", "")), str(location.get("summary") or ""))

        for npc in result.get("npcs") or []:
            _upsert_npc(conn, npc)

        _apply_relationships(conn, result.get("relationships") or [])
        _apply_inventory(conn, result.get("inventory_changes") or [])
        _apply_equipment_slots(conn, result.get("equipment_slots") or [])
        _apply_equipment_changes(conn, result.get("equipment_changes") or [])
        _apply_inventory_capacity_modifiers(conn, result.get("inventory_capacity_modifiers") or [])
        _apply_skills(conn, result.get("skill_changes") or [])
        _apply_player(conn, result.get("player") or {})
        _apply_events(conn, result.get("events") or [], turn)
        _apply_gm_events(conn, result.get("gm_events") or [], turn)
        _apply_conversations(conn, result.get("conversations") or [], turn)
        _apply_response_drafts(conn, result.get("response_drafts") or [], turn)
        _apply_index_updates(conn, result.get("index_updates") or [])
        _apply_ability_updates(conn, result.get("ability_updates") or [])
        _apply_deterministic_combat(conn, result.get("_deterministic_combat") or {}, turn)
        _write_turn_summary(conn, turn, result, player_input)
        _write_model_usage(conn, turn, result)
        _write_verification_memory(conn, turn, result, prompt_context, used_fallback)
        _maybe_spawn_offscreen_gm_event(conn, turn)

        conn.execute("INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)", (turn, input_kind[:40] or "player", player_input[:2000]))
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, "narration", narration[:3600]),
        )
        if result.get("self_check"):
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (turn, "self_check", json.dumps(result.get("self_check"), ensure_ascii=True)[:1800]),
            )
        if used_fallback:
            reason = fallback_reason or "Local LLM was unavailable or returned invalid JSON."
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (turn, "system", f"Used deterministic fallback. LLM error: {reason}"[:1400]),
            )
        for entry in result.get("journal") or []:
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (turn, str(entry.get("kind") or "fact")[:40], str(entry.get("content") or "")[:1400]),
            )

    # Hierarchical memory: roll older summaries into durable facts after enough history accumulates.
    try:
        with connect() as conn:
            summary_count = conn.execute("SELECT COUNT(*) AS count FROM turn_summaries").fetchone()
            count = int(summary_count["count"] or 0) if summary_count else 0
        if count > MEMORY_CONSOLIDATE_KEEP_SUMMARIES + 2:
            consolidate_memory()
    except Exception:
        # Consolidation must not block turn application; use /api/memory/consolidate to force and surface errors.
        pass
    return _state_with_refreshed_source_index()


def _turn_reward_summary(before_state: dict[str, Any], after_state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    before_player = before_state.get("player") or {}
    after_player = after_state.get("player") or {}
    xp_gain = max(0, int(after_player.get("xp") or 0) - int(before_player.get("xp") or 0))
    items_gained: list[dict[str, Any]] = []
    for change in result.get("inventory_changes") or []:
        if not isinstance(change, dict):
            continue
        quantity = int(_float(change.get("quantity_delta"), 0))
        name = norm_name(str(change.get("name") or ""))
        if quantity <= 0 or not name:
            continue
        items_gained.append(
            {
                "name": name,
                "quantity": quantity,
                "rarity": str(change.get("rarity") or "common")[:80],
                "item_type": str(change.get("item_type") or change.get("type") or "misc")[:80],
                "description": str(change.get("description") or "")[:240],
            }
        )
    return {
        "xp_gain": xp_gain,
        "items_gained": items_gained,
    }


def _fallback_notice(reason: str) -> str:
    clean_reason = str(reason or "").strip()
    lower_reason = clean_reason.lower()
    if "without narration text" in lower_reason or "no usable narration" in lower_reason or "did not include usable narration" in lower_reason:
        return "The visible prose is deterministic fallback narration. The local model response was rejected because its JSON did not include usable narration text."
    if "no model response was generated" in lower_reason or "connection refused" in lower_reason:
        return "The visible prose is deterministic fallback narration. The local model server did not produce a usable response for this turn."
    if clean_reason:
        return f"The visible prose is deterministic fallback narration. The local model response could not be used: {clean_reason}"[:900]
    return "The visible prose is deterministic fallback narration because the local model response could not be used."


def play_turn(player_input: str, input_kind: str = "player", journal_input: str | None = None) -> dict[str, Any]:
    context = get_state(include_hidden=True)
    used_fallback = False
    fallback_reason = ""
    model_input = _expand_input_references(context, player_input)
    if _ensure_combat_profiles_for_input(context, model_input):
        context = get_state(include_hidden=True)
        model_input = _expand_input_references(context, player_input)
    mechanics_context = _build_mechanics_context(context, model_input)
    context["mechanics_context"] = mechanics_context
    prompt_context = build_prompt_context(context, model_input)
    try:
        result = generate_turn(prompt_context, model_input)
    except LlmError as exc:
        fallback_reason = str(exc) or exc.__class__.__name__
        result = fallback_turn(context, player_input)
        result["llm_error"] = fallback_reason
        model_usage = getattr(exc, "model_usage", None)
        if model_usage:
            result["_model_usage"] = model_usage
        model_trace = list(getattr(exc, "model_trace", None) or [])
        model_trace.append(
            {
                "phase": "world_fallback",
                "event": "deterministic_fallback",
                "reason": fallback_reason,
                "fallback_narration_chars": len(str(result.get("narration") or "")),
            }
        )
        result["_model_trace"] = model_trace
        used_fallback = True

    result["_deterministic_combat"] = mechanics_context.get("combat") or {}

    actual_player_input = journal_input if journal_input is not None else player_input
    state = apply_turn(
        result,
        actual_player_input,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        input_kind=input_kind,
        prompt_context=prompt_context,
    )
    debug_trace_path = _write_model_trace_file(
        _current_turn_number(),
        input_kind,
        actual_player_input,
        model_input,
        prompt_context,
        result,
        used_fallback,
        fallback_reason,
    )
    result.pop("_model_trace", None)
    rewards = _turn_reward_summary(context, state, result)
    return {
        "turn": result,
        "state": state,
        "rewards": rewards,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "fallback_notice": _fallback_notice(fallback_reason) if used_fallback else "",
        "debug_trace_path": debug_trace_path,
        "input_kind": input_kind,
    }


def play_opening_turn() -> dict[str, Any]:
    return play_turn(OPENING_SCENE_INPUT, input_kind="opening", journal_input=OPENING_SCENE_JOURNAL)


def _current_turn_number() -> int:
    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
    return int(row["value"]) if row else 0


def play_continue_turn() -> dict[str, Any]:
    if _current_turn_number() <= 0:
        return play_opening_turn()
    return play_turn(CONTINUE_SCENE_INPUT, input_kind="continue", journal_input=CONTINUE_SCENE_JOURNAL)


def start_playthrough_with_opening(options: dict[str, Any]) -> dict[str, Any]:
    start_playthrough(options)
    return play_opening_turn()


def get_input_suggestions(instruction: str = "") -> dict[str, Any]:
    context = get_state(include_hidden=False)
    prompt_context = build_prompt_context(context, f"suggest next player inputs {instruction}".strip())
    return generate_input_suggestions(prompt_context, instruction)
