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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app import venues
from app.db import connect, row_to_dict, rows_to_dicts
from app.llm import (
    LlmError,
    ambient_llm_enabled,
    context_window_tokens,
    fallback_turn,
    generate_ambient_move_line,
    generate_input_suggestions,
    generate_turn,
)

# Runtime paths are resolved per call, never frozen at import.
#
# These were module constants. Whichever module imported app.world first decided
# them for the whole process, so a test that set AI_RPG_* afterwards silently
# wrote its fixtures into the player's real data/ folder. Functions re-read the
# environment every time, which is what makes test isolation actually hold.


def history_summary_path() -> Path:
    return Path(os.getenv("AI_RPG_HISTORY_SUMMARY", "data/history_summaries.jsonl"))


def source_index_dir() -> Path:
    return Path(os.getenv("AI_RPG_SOURCE_INDEX", "data/source_index"))


def source_index_manifest() -> Path:
    return source_index_dir() / "manifest.json"


def model_trace_dir() -> Path:
    return Path(os.getenv("AI_RPG_MODEL_TRACE_DIR", "data/model_traces"))


def consolidated_facts_path() -> Path:
    return Path(os.getenv("AI_RPG_CONSOLIDATED_FACTS", "data/consolidated_facts.jsonl"))


def campaign_slots_dir() -> Path:
    return Path(os.getenv("AI_RPG_CAMPAIGN_SLOTS", "data/campaign_slots"))
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
    # Tile overworld (not FK-linked to locations); must round-trip with Continue/load.
    "world_maps",
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

# In-world day length (minutes). Clock lives in pacing keys world_day / world_minute.
WORLD_DAY_LENGTH_MINUTES = 24 * 60
WORLD_DEFAULT_START_MINUTE = 8 * 60  # 08:00
WAIT_MINUTE_CHOICES = (1, 10, 60, 360)  # 1m, 10m, 1h, 6h
WAIT_EVENT_KINDS = (
    "ambient",
    "rumor",
    "patrol_pass",
    "crowd_noise",
    "weather_shift",
    "pickpocket_attempt",
    "fight_nearby",
    "stranger_passes",
)

# World-event bus kinds (RNG + forced quest beats share one queue).
WORLD_EVENT_KINDS = (
    "travel_ambush",
    "travel_wild",
    "travel_hidden_base",
    "travel_traveler",
    "wait_event",
    "quest_force",
    "quest_portal",
    "quest_stage",
    "rumor_spike",
    "faction_pressure",
    "weather",
    "discovery",
    "custom",
)
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
    "world_maps",
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
    "travel": {
        "go", "move", "walk", "run", "travel", "head", "enter", "leave", "return", "approach", "climb", "cross", "follow",
        "ride", "sail", "march", "depart", "exit", "wander", "journey", "flee", "descend", "ascend", "board", "hike", "trek",
    },
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
        ("starting_limits", "Respect starting health, derived equipment effects, inventory limits, ability locks/prerequisites, and the no-default-skills rule.", ["health", "effective_stats", "inventory", "abilities", "skills"]),
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
        ("ability_constraints", "Read the named/relevant ability, lock state, base_description, prerequisites, cost, growth_math, player health/effective_stats, race/magic rules, and target resistance; equipment-granted abilities are already in abilities while equipped. Apply growth_math numbers when awarding progress.", ["ability", "cost", "prerequisite", "growth_math", "locked", "magic", "target"]),
        ("effect_scope", "Keep the effect inside stored limits and update ability details only when play reveals a justified cost, limit, unlock path, or clearer growth_math.", ["scope", "cooldown", "resource", "unlock", "limitation", "growth_math"]),
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


# Sentence/event fragments that must never become NPC or place display names.
_NAME_VERB_RE = re.compile(
    r"\b("
    r"pings?|appears?|offers?|retriev\w*|helping|seeking|walks?|runs?|says?|tells?|"
    r"gives?|takes?|asks?|whispers?|vanishes?|emerges?|approaches?|requests?|"
    r"rewards?|grants?|spawns?|triggers?|starts?|begins?|continues?"
    r")\b",
    re.I,
)
_NAME_SYSTEM_RE = re.compile(
    r"\b("
    r"system\s+pings?|status\s+window|quest\s+log|level\s*up|xp\s+gain|"
    r"local\s+job|in\s+exchange\s+for|lost\s+item|copper\s+coins"
    r")\b",
    re.I,
)
# Scenery / architecture — fine for places, never for people (classic: "Sky-crack first window")
_NAME_SCENERY_RE = re.compile(
    r"\b("
    r"window|windowsill|sill|door|doorway|gate|arch|alley|street|road|pavement|"
    r"railing|fire\s*escape|lantern|lamp|crack|sky-?crack|ledge|rooftop|roof|"
    r"balcony|stair|stairs|corridor|hallway|threshold|frame|glass|pane"
    r")\b",
    re.I,
)
# Worn gear / props — never person names (classic: "travel-stained coat" cast as an NPC/faction)
_NAME_GEAR_RE = re.compile(
    r"\b("
    r"coat|cloak|jacket|robe|tunic|vest|shirt|boots?|shoes?|gloves?|hat|hood|"
    r"satchel|bag|pack|pouch|belt|scabbard|sheath|sword|dagger|blade|bow|crossbow|"
    r"armor|armour|helm|helmet|shield|staff|wand|tankard|mug|scrolls?|map|"
    r"travel-?stained|oil-?stained|frayed|weathered|patched|worn\s+tool"
    r")\b",
    re.I,
)
# Generic person labels a model reaches for instead of naming someone.
# A 7B run produced an NPC literally recorded as "Woman" (code C), then referred
# to it in prose as "a tall woman [[C]]" for 30 turns. These are descriptions,
# not names: the head noun tells you nothing that the role column doesn't.
_NAME_GENERIC_HEADS = frozenset(
    {
        "man", "men", "woman", "women", "boy", "girl", "lad", "lass", "kid",
        "child", "children", "person", "people", "guy", "gal", "fellow", "folk",
        "figure", "silhouette", "shape", "form", "shadow", "stranger", "newcomer",
        "passerby", "bystander", "onlooker", "witness", "local", "native",
        "traveler", "traveller", "wanderer", "visitor", "guest", "customer",
        "patron", "youth", "elder", "adult", "teen", "teenager", "adolescent",
        "male", "female", "one", "someone", "somebody", "individual",
    }
)
# Occupations: fine as a role, never as the whole display name on their own.
_NAME_GENERIC_ROLES = frozenset(
    {
        "guard", "guardsman", "soldier", "warrior", "knight", "sentry", "watchman",
        "merchant", "trader", "shopkeeper", "vendor", "peddler", "innkeeper",
        "barkeep", "bartender", "blacksmith", "smith", "baker", "butcher",
        "farmer", "fisher", "fisherman", "hunter", "miner", "priest", "priestess",
        "monk", "cleric", "acolyte", "healer", "scholar", "scribe", "clerk",
        "mage", "wizard", "sorcerer", "witch", "druid", "bard", "thief", "bandit",
        "brigand", "mercenary", "assassin", "beggar", "servant", "maid", "cook",
        "porter", "sailor", "captain", "officer", "noble", "lord", "lady",
        "gentleman", "commoner", "peasant", "villager", "townsfolk", "townsperson",
        "citizen", "apprentice", "student", "teacher", "master", "mistress",
        "messenger", "courier", "courtier", "official", "magistrate", "jailer",
        "cultist", "raider", "scout", "ranger", "tracker", "guide", "driver",
        "stablehand", "groom", "nurse", "doctor", "physician", "alchemist",
    }
)
# Adjectives that only ever describe — they cannot carry a name by themselves.
_NAME_GENERIC_MODIFIERS = frozenset(
    {
        "old", "young", "elderly", "aged", "middle-aged", "tall", "short", "thin",
        "slim", "lean", "stout", "fat", "burly", "broad", "small", "large", "big",
        "little", "hooded", "cloaked", "robed", "masked", "veiled", "bearded",
        "scarred", "grizzled", "weathered", "ragged", "shabby", "wealthy", "rich",
        "poor", "nervous", "anxious", "angry", "quiet", "silent", "loud", "kind",
        "cruel", "friendly", "hostile", "suspicious", "wary", "drunk", "drunken",
        "wounded", "injured", "sick", "tired", "weary", "dark", "pale", "fair",
        "grey", "gray", "white", "black", "red", "blonde", "blond", "brown",
        "haired", "eyed", "unnamed", "unknown", "mysterious", "strange", "odd",
        "familiar", "another", "other", "certain", "same", "new", "random",
        "generic", "nameless", "faceless", "anonymous", "armed", "armored",
        "armoured", "uniformed", "well-dressed", "plain", "ordinary", "average",
    }
)

_NAME_FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "from",
        "for",
        "with",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "at",
        "by",
        "your",
        "you",
        "their",
        "his",
        "her",
        "its",
        "this",
        "that",
        "near",
        "nearby",
        "first",
        "second",
        "third",
        "last",
        "only",
        "main",
        "upper",
        "lower",
    }
)


def is_generic_person_label(name: str) -> bool:
    """
    True when a "name" is only a description: "Woman", "Old Man", "The Hooded Figure",
    "Guard". These carry no identity — the role/summary columns already hold that —
    and they read badly in prose ("a tall woman [[C]]" every turn for 30 turns).

    A single proper-noun token anywhere keeps the name: "Old Mara", "Captain Thornrow",
    and "Guard Aria" are all real names with a descriptive modifier attached.
    """
    n = norm_name(str(name or "")).lower()
    if not n:
        return True
    # Strip punctuation the model sometimes glues on ("the woman," / "woman?")
    tokens = [tok for tok in re.split(r"[^a-z0-9'-]+", n) if tok]
    if not tokens:
        return True
    if len(tokens) > 5:
        return False
    generic = _NAME_GENERIC_HEADS | _NAME_GENERIC_ROLES | _NAME_GENERIC_MODIFIERS
    saw_generic = False
    for token in tokens:
        if token in _NAME_FUNCTION_WORDS:
            continue
        if token in generic:
            saw_generic = True
            continue
        # Any token that is not an article, a modifier, or a generic head is
        # treated as the actual name.
        return False
    return saw_generic


def is_plausible_person_name(name: str) -> bool:
    """True for short proper names/titles — not event blurbs, scenery, gear, or system job lines."""
    n = norm_name(str(name or ""))
    if len(n) < 2 or len(n) > 48:
        return False
    words = n.split()
    if len(words) > 4:
        return False
    # Descriptions are not names ("Woman", "Hooded Figure", "The Old Guard")
    if is_generic_person_label(n):
        return False
    if _NAME_VERB_RE.search(n) or _NAME_SYSTEM_RE.search(n):
        return False
    # Architecture / props are not people
    if _NAME_SCENERY_RE.search(n):
        return False
    # Clothing / tools / inventory fluff is not a person or faction label
    if _NAME_GEAR_RE.search(n):
        return False
    # Hyphenated outfit tags ("travel-stained coat") are wardrobe, not names
    if re.search(r"\b\w+-\w+\s+(coat|cloak|jacket|boots?|tunic|robe)\b", n, re.I):
        return False
    # "a cloaked figure" / "local job" / "first window" style
    if len(words) >= 3 and sum(1 for w in words if w.lower() in _NAME_FUNCTION_WORDS) >= 2:
        return False
    if re.search(r"\b(a local|from the|in exchange|offering|retrieving|help with)\b", n, re.I):
        return False
    # Ordinal + object ("first window", "second gate") is not a person
    if re.search(r"\b(first|second|third|last|only)\s+\w+\b", n, re.I) and len(words) <= 3:
        return False
    # Bare entity codes (case-insensitive): L1, I2, E3, A, AB — never people
    if re.fullmatch(r"[A-Za-z]{1,3}\d{0,3}", n):
        return False
    if re.fullmatch(r"[LIElie]\d+", n):
        return False
    # Bare place nouns ("the inn", "nearby street", "gate") are not people
    if re.fullmatch(
        r"(the\s+)?(inn|tavern|pub|bar|gate|road|street|square|market|harbor|harbour|"
        r"dock|bridge|tower|temple|church|school|manor|castle|keep|fort|camp|"
        r"village|town|city|forest|cave|ruins?|alley|plaza|hall)",
        n,
        re.I,
    ):
        return False
    # Place-ish multiword heads ("… Inn", "… Gate", "… Street")
    if re.search(
        r"\b(inn|tavern|pub|gate|road|street|square|market|harbor|harbour|bridge|"
        r"tower|temple|church|manor|castle|keep|fort|village|town|city|alley|plaza|hall)\s*$",
        n,
        re.I,
    ) and len(words) >= 2:
        return False
    return True


# Bare directions and relative positions are not places. A live run recorded
# `MOVE East` and put a location called "East" on the player's map.
_BARE_DIRECTION_RE = re.compile(
    r"^(?:the\s+)?(?:far\s+|deep\s+|due\s+)?"
    r"(?:north|south|east|west|northeast|northwest|southeast|southwest|"
    r"up|down|left|right|ahead|onward|onwards|forward|forwards|back|backward|"
    r"beyond|nearby|elsewhere|somewhere|there|here|outside|inside|away)"
    r"(?:\s+(?:side|end|way|ward|wards))?$",
    re.I,
)


def is_plausible_place_name(name: str) -> bool:
    """Places can be multi-word, but not full system/event sentences or bare props."""
    # Unwrap first, so this holds whether or not the caller ran the name through
    # humanize_place_name. The setup form calls it on raw model output, and a
    # "[[L1]]" that is only judged inside _upsert_location is judged too late.
    n = humanize_place_name(str(name or ""))
    if len(n) < 2 or len(n) > 60:
        return False
    # "East", "the far side", "ahead" — a heading, not a destination
    if _BARE_DIRECTION_RE.match(n):
        return False
    words = n.split()
    if len(words) > 6:
        return False
    # Entity codes are not toponyms. L1/I2/E3 name rows; A..ZZ name NPCs. The
    # person check has refused these for a while; places never did, so a bare
    # code that survived humanize_place_name became a row on the player's map.
    # Letters-then-digits only, plus all-caps stubs -- "Ys" and "Oz" are fine.
    if re.fullmatch(r"[A-Za-z]{1,3}\d{1,4}", n) or re.fullmatch(r"[A-Z]{1,3}", n):
        return False
    if _NAME_VERB_RE.search(n) or _NAME_SYSTEM_RE.search(n):
        return False
    if re.search(r"\b(in exchange|offering|retrieving|help with|appears?,)\b", n, re.I):
        return False
    if n.lower().startswith("system "):
        return False
    # Bare props / furniture / "first window" are not place names
    if re.fullmatch(r"(the\s+)?(first|second|third|only)\s+(window|door|gate|sill|ledge)", n, re.I):
        return False
    if re.fullmatch(r"(the\s+)?(window|door|sill|railing|lantern|lamp|pane|frame)", n, re.I):
        return False
    # "... window/door/sill" as the head noun (Sky-crack first window) is scenery, not a locale label
    if re.search(
        r"\b(window|windowsill|sill|doorway|railing|fire\s*escape|lantern|lamp|pane|frame)\s*$",
        n,
        re.I,
    ):
        return False
    return True


def name_seed(*parts: Any) -> int:
    """
    Stable seed for replacement names.

    Python's ``hash()`` is randomized per process, so the same corrupt save
    reopened tomorrow used to rename the same NPC to something else. Rewind and
    reload must land on the same face.
    """
    try:
        from app.rng import seed_from

        return seed_from("npc_name", *parts)
    except Exception:
        payload = "|".join(str(p) for p in parts).encode("utf-8", "replace")
        return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big") & 0x7FFFFFFFFFFFFFFF


def invent_person_name(*, seed: int | None = None) -> str:
    """Deterministic-ish shell name for NPCs when the model invents garbage labels."""
    rng = random.Random(seed if seed is not None else random.randint(1, 10**9))
    return f"{rng.choice(_SHELL_NAME_PARTS_A)}{rng.choice(_SHELL_NAME_PARTS_B)}"


def _person_name_taken(conn, name: str) -> bool:
    """True when any NPC anywhere already holds this name."""
    try:
        row = conn.execute(
            "SELECT 1 FROM npcs WHERE name = ? COLLATE NOCASE LIMIT 1", (str(name or ""),)
        ).fetchone()
    except Exception:
        return False
    return bool(row)


def unique_person_name(conn, seed: int, *, attempts: int = 24) -> str:
    """
    A replacement name no live NPC already holds.

    The name space is 20x20; a live run with seven repaired NPCs produced two
    called "Saltbin", which reads as one character in two places. Re-roll on
    collision, still deterministically, and only fall back to a suffix if the
    pool is genuinely exhausted.
    """
    try:
        taken = {
            str(row["name"] or "").strip().lower()
            for row in conn.execute("SELECT name FROM npcs").fetchall()
        }
    except Exception:
        taken = set()
    name = invent_person_name(seed=seed)
    for attempt in range(attempts):
        if name.strip().lower() not in taken:
            return name
        name = invent_person_name(seed=name_seed(seed, "retry", attempt))
    for suffix in range(2, 40):
        candidate = f"{name} {suffix}"
        if candidate.strip().lower() not in taken:
            return candidate
    return name


def _ability_origin(value: Any, has_requested_abilities: bool = False) -> str:
    """
    Legacy playthrough option. UI no longer exposes Ability Origin —
    empty ability list means no powers; non-empty list uses per-card locks.
    When abilities are present but origin is missing/none, default to both.
    """
    cleaned = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    if cleaned in {"innate", "born with", "inborn", "inherent", "natural"}:
        return "innate"
    if cleaned in {"acquired", "gained", "learned", "earned", "unlocked"}:
        return "acquired"
    if cleaned in {"both", "mixed", "mix", "acquired and innate", "innate and acquired"}:
        return "both"
    if cleaned in {"none", "no abilities", "no special abilities"}:
        # Prefer the ability list over a stale "none" origin from old saves.
        return "both" if has_requested_abilities else "none"
    return "both" if has_requested_abilities else "none"


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


def _next_alpha_code(conn, table: str = "npcs") -> str:
    """
    Allocate a free A/B/.../AA style code.
    max(id)+1 can collide when ids and codes drift (deletes, mixed allocators).
    """
    n = max(1, _max_id(conn, table) + 1)
    for _ in range(20_000):
        code = alpha_code(n)
        row = conn.execute(f"SELECT 1 AS ok FROM {table} WHERE code = ?", (code,)).fetchone()
        if not row:
            return code
        n += 1
    raise RuntimeError(f"Could not allocate free code for {table}")


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


def _pacing_get(conn, key: str, default: str = "0") -> str:
    row = conn.execute("SELECT value FROM pacing WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row else default


def _pacing_set(conn, key: str, value: str | int) -> None:
    conn.execute(
        "INSERT INTO pacing (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )


def format_world_time(
    day: int,
    minute: int,
    day_length: int = WORLD_DAY_LENGTH_MINUTES,
    *,
    epoch_label: str = "",
) -> dict[str, Any]:
    day = max(1, int(day))
    day_length = max(60, int(day_length))
    minute = int(minute) % day_length
    hour = minute // 60
    moh = minute % 60
    core = f"Day {day} · {hour:02d}:{moh:02d}"
    epoch = str(epoch_label or "").strip()
    return {
        "day": day,
        "minute": minute,
        "hour": hour,
        "minute_of_hour": moh,
        "day_length_minutes": day_length,
        "epoch_label": epoch,
        "label": f"{epoch} · {core}" if epoch else core,
    }


def get_world_time(conn=None) -> dict[str, Any]:
    """Read in-world clock from pacing (defaults if missing)."""
    if conn is None:
        with connect() as c:
            return get_world_time(c)
    day = max(1, int(_float(_pacing_get(conn, "world_day", "1"), 1)))
    minute = int(_float(_pacing_get(conn, "world_minute", str(WORLD_DEFAULT_START_MINUTE)), WORLD_DEFAULT_START_MINUTE))
    epoch = str(_pacing_get(conn, "world_epoch_label", "") or "").strip()
    if not epoch:
        epoch = str(_settings(conn).get("world_epoch_label") or "").strip()
    return format_world_time(day, minute, epoch_label=epoch)


def init_world_clock(
    conn,
    *,
    day: int = 1,
    minute: int = WORLD_DEFAULT_START_MINUTE,
    epoch_label: str = "",
) -> dict[str, Any]:
    _pacing_set(conn, "world_day", max(1, int(day)))
    _pacing_set(conn, "world_minute", max(0, int(minute) % WORLD_DAY_LENGTH_MINUTES))
    epoch = str(epoch_label or "").strip()[:60]
    if not epoch:
        # Soft default from world style if present in setup options later
        epoch = ""
    _pacing_set(conn, "world_epoch_label", epoch)
    if epoch:
        _set_setting(conn, "world_epoch_label", epoch)
    set_weather(conn, _default_weather())
    return get_world_time(conn)


def minutes_until_hour(conn, target_hour: int = 6) -> int:
    """Minutes from now until next occurrence of target_hour:00 (default dawn 06:00)."""
    wt = get_world_time(conn)
    now = int(wt["minute"])
    target = max(0, min(23, int(target_hour))) * 60
    if now < target:
        return target - now
    return (wt["day_length_minutes"] - now) + target


def normalize_wait_minutes(minutes: int | str, conn=None) -> int:
    """Clamp wait duration; supports until_dawn sentinel via minutes==-1 or 'dawn'."""
    if isinstance(minutes, str):
        s = minutes.strip().lower()
        if s in {"dawn", "until_dawn", "until dawn", "morning"}:
            minutes = -1
        else:
            try:
                minutes = int(s)
            except ValueError:
                minutes = 60
    minutes = int(minutes)
    if minutes == -1:
        if conn is None:
            with connect() as c:
                return max(1, min(WORLD_DAY_LENGTH_MINUTES, minutes_until_hour(c, 6)))
        return max(1, min(WORLD_DAY_LENGTH_MINUTES, minutes_until_hour(conn, 6)))
    if minutes in WAIT_MINUTE_CHOICES:
        return minutes
    # Custom: clamp 1 minute … 24 hours
    return max(1, min(WORLD_DAY_LENGTH_MINUTES, minutes))


def advance_world_time(conn, minutes: int) -> dict[str, Any]:
    """Advance clock by minutes; returns {before, after, advanced_minutes, weather}."""
    before = get_world_time(conn)
    add = max(0, int(minutes))
    total = before["minute"] + add
    days_add = total // before["day_length_minutes"]
    new_minute = total % before["day_length_minutes"]
    new_day = before["day"] + days_add
    _pacing_set(conn, "world_day", new_day)
    _pacing_set(conn, "world_minute", new_minute)
    after = get_world_time(conn)
    weather_tick = tick_weather(conn, minutes_advanced=add, time_after=after)
    return {
        "before": before,
        "after": after,
        "advanced_minutes": add,
        "weather": weather_tick.get("weather"),
        "weather_changed": bool(weather_tick.get("changed")),
        "weather_announce": weather_tick.get("announce"),
    }


# ---------------------------------------------------------------------------
# Weather (fully server-side RNG; LLM only narrates changes)
# ---------------------------------------------------------------------------

WEATHER_KINDS = (
    "clear",
    "cloudy",
    "rain",
    "storm",
    "fog",
    "snow",
    "heat",
    "wind",
)

# Travel time multipliers + event pressure deltas by weather (strength scales 0–1)
WEATHER_TRAVEL_MULT = {
    "clear": 1.0,
    "cloudy": 1.05,
    "rain": 1.2,
    "storm": 1.45,
    "fog": 1.25,
    "snow": 1.4,
    "heat": 1.15,
    "wind": 1.1,
}
WEATHER_EVENT_DELTA = {
    "clear": 0.0,
    "cloudy": 0.02,
    "rain": 0.04,
    "storm": 0.12,
    "fog": 0.08,
    "snow": 0.06,
    "heat": 0.03,
    "wind": 0.05,
}


def _default_weather() -> dict[str, Any]:
    return {
        "kind": "clear",
        "strength": 0.0,
        "minutes_active": 0,
        "label": "Clear",
        "changed": False,
        "announce": None,
    }


def get_weather(conn=None) -> dict[str, Any]:
    if conn is None:
        with connect() as c:
            return get_weather(c)
    raw = _settings(conn).get("world_weather")
    if isinstance(raw, dict) and raw.get("kind"):
        w = dict(_default_weather())
        w.update(raw)
        w["kind"] = str(w.get("kind") or "clear").lower()
        if w["kind"] not in WEATHER_KINDS:
            w["kind"] = "clear"
        w["strength"] = max(0.0, min(1.0, float(_float(w.get("strength"), 0.0))))
        w["minutes_active"] = max(0, int(_float(w.get("minutes_active"), 0)))
        w["label"] = _weather_label(w["kind"], w["strength"])
        return w
    return _default_weather()


def _weather_label(kind: str, strength: float) -> str:
    intensity = "light" if strength < 0.34 else ("heavy" if strength > 0.7 else "steady")
    if kind == "clear":
        return "Clear"
    if kind == "cloudy":
        return "Overcast" if strength > 0.5 else "Cloudy"
    return f"{intensity.capitalize()} {kind}"


def set_weather(conn, weather: dict[str, Any]) -> dict[str, Any]:
    w = dict(_default_weather())
    w.update(weather or {})
    w["kind"] = str(w.get("kind") or "clear").lower()
    if w["kind"] not in WEATHER_KINDS:
        w["kind"] = "clear"
    w["strength"] = max(0.0, min(1.0, float(_float(w.get("strength"), 0.0))))
    w["minutes_active"] = max(0, int(_float(w.get("minutes_active"), 0)))
    w["label"] = _weather_label(w["kind"], w["strength"])
    _set_setting(conn, "world_weather", w)
    return w


def tick_weather(
    conn,
    *,
    minutes_advanced: int,
    time_after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Pure RNG weather. Chance to start, strengthen, or end as time passes.
    Does not call the LLM — only sets announce text for the DM later.
    """
    minutes_advanced = max(0, int(minutes_advanced))
    if minutes_advanced <= 0:
        w = get_weather(conn)
        return {"weather": w, "changed": False, "announce": None}

    w = get_weather(conn)
    prev_kind = w.get("kind")
    prev_str = float(w.get("strength") or 0)
    w["minutes_active"] = int(w.get("minutes_active") or 0) + minutes_advanced
    hours = minutes_advanced / 60.0
    # Seed from clock so reloads stay stable for the same minute
    ta = time_after or get_world_time(conn)
    seed = (int(ta.get("day") or 1) * 1440 + int(ta.get("minute") or 0)) ^ (minutes_advanced * 17)
    rng = random.Random(seed & 0x7FFFFFFF)

    changed = False
    announce = None

    if w["kind"] == "clear" or w["strength"] <= 0.05:
        # Chance to start weather scales with hours passed
        p_start = min(0.55, 0.08 + 0.12 * hours)
        # Slightly more storms at night
        hour = int(ta.get("hour") or 12)
        if hour < 6 or hour >= 20:
            p_start += 0.04
        if rng.random() < p_start:
            kind = rng.choices(
                ["cloudy", "rain", "fog", "wind", "storm", "snow", "heat"],
                weights=[22, 22, 14, 14, 10, 8, 10],
                k=1,
            )[0]
            strength = round(rng.uniform(0.25, 0.85), 3)
            w = {
                "kind": kind,
                "strength": strength,
                "minutes_active": 0,
                "label": _weather_label(kind, strength),
                "changed": True,
            }
            changed = True
            announce = f"Weather shifts to {w['label']}."
    else:
        # Ongoing: chance to intensify, ease, or end
        p_end = min(0.65, 0.06 + 0.1 * hours + (w["minutes_active"] / 600.0) * 0.15)
        p_shift = min(0.4, 0.05 + 0.08 * hours)
        roll = rng.random()
        if roll < p_end:
            announce = f"The {w['label'].lower()} breaks; sky eases toward clear."
            w = _default_weather()
            w["changed"] = True
            changed = True
        elif roll < p_end + p_shift:
            delta = rng.uniform(-0.25, 0.3)
            new_s = max(0.1, min(1.0, float(w["strength"]) + delta))
            if abs(new_s - prev_str) >= 0.12:
                changed = True
                direction = "worsens" if new_s > prev_str else "eases"
                w["strength"] = round(new_s, 3)
                w["label"] = _weather_label(w["kind"], w["strength"])
                w["changed"] = True
                announce = f"The weather {direction}: now {w['label']}."
            else:
                w["strength"] = round(new_s, 3)
                w["label"] = _weather_label(w["kind"], w["strength"])
        # Small chance to transform rain→storm etc.
        if not changed and w["kind"] == "rain" and rng.random() < 0.08 * max(1.0, hours):
            w["kind"] = "storm"
            w["strength"] = min(1.0, float(w["strength"]) + 0.2)
            w["label"] = _weather_label("storm", w["strength"])
            w["changed"] = True
            changed = True
            announce = "Rain thickens into a storm."

    if not changed:
        w["changed"] = False
        w["announce"] = None
    else:
        w["changed"] = True
        w["announce"] = announce
        w["prev_kind"] = prev_kind

    set_weather(conn, w)
    if announce:
        # Pending DM line for next scene / ambient (non-blocking)
        _set_setting(
            conn,
            "weather_announce_pending",
            {"text": announce, "weather": {"kind": w["kind"], "strength": w["strength"], "label": w["label"]}},
        )
        try:
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (_turn_value(conn), "weather", announce[:900]),
            )
        except Exception:
            pass
    # Extreme weather can force a shelter beat (once per storm peak)
    if (
        w.get("kind") in {"storm", "snow", "fog"}
        and float(w.get("strength") or 0) >= 0.78
        and int(w.get("minutes_active") or 0) >= 30
    ):
        try:
            flag = f"weather_shelter:{w.get('kind')}:{int(ta.get('day') or 1)}"
            if not _settings(conn).get(flag):
                _set_setting(conn, flag, True)
                turn_now = _turn_value(conn)
                prow = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
                loc_id = int(prow["current_location_id"]) if prow and prow["current_location_id"] else None
                conn.execute(
                    """
                    INSERT INTO gm_events (turn, trigger, summary, status, priority, location_id, npc_id, event_id, kind, due_turn, force, payload)
                    VALUES (?, ?, ?, 'pending', 7, ?, NULL, NULL, ?, ?, 1, ?)
                    """,
                    (
                        turn_now,
                        f"weather:{w.get('kind')}",
                        f"Severe {w.get('label') or w.get('kind')} presses for shelter or cover.",
                        loc_id,
                        "weather",
                        turn_now + 1,
                        json.dumps(
                            {
                                "kind": "weather",
                                "weather": {"kind": w.get("kind"), "strength": w.get("strength"), "label": w.get("label")},
                                "immutable": False,
                                "requires_scene": True,
                                "player_is_trigger": True,
                            },
                            ensure_ascii=True,
                        )[:4000],
                    ),
                )
        except Exception:
            pass
    return {"weather": w, "changed": changed, "announce": announce}


def weather_travel_multiplier(weather: dict[str, Any] | None = None) -> float:
    w = weather or {}
    kind = str(w.get("kind") or "clear").lower()
    strength = max(0.0, min(1.0, float(_float(w.get("strength"), 0.0))))
    base = WEATHER_TRAVEL_MULT.get(kind, 1.0)
    # Strength pulls multiplier toward harsher end
    harsh = 1.0 + (base - 1.0) * (0.45 + 0.55 * strength)
    return max(0.9, min(1.8, harsh if kind != "clear" else 1.0))


def weather_event_chance_delta(weather: dict[str, Any] | None = None) -> float:
    w = weather or {}
    kind = str(w.get("kind") or "clear").lower()
    strength = max(0.0, min(1.0, float(_float(w.get("strength"), 0.0))))
    d = WEATHER_EVENT_DELTA.get(kind, 0.0)
    return d * (0.5 + 0.5 * strength)


def estimate_action_minutes(player_input: str) -> int:
    """Rough in-world minutes for a free-text player action (not walk/wait)."""
    text = (player_input or "").lower().strip()
    if not text or text.startswith("__"):
        return 0
    if re.search(r"\b(attack|fight|combat|chase|flee|run)\b", text):
        return 8
    if re.search(r"\b(search|investigate|examine|study|read|craft|repair)\b", text):
        return 15
    if re.search(r"\b(talk|ask|speak|persuade|negotiate|lie|intimidate|greet)\b", text):
        return 5
    if re.search(r"\b(rest|eat|drink|bandage|wait a moment)\b", text):
        return 20
    if re.search(r"\b(sneak|hide|climb|swim|force|break|lock)\b", text):
        return 10
    return 6


# ---------------------------------------------------------------------------
# Area / NPC reputation (server authority)
# ---------------------------------------------------------------------------

def get_area_reputation(conn, location_id: int | None = None, location_code: str = "") -> int:
    reps = _settings(conn).get("area_reputation")
    if not isinstance(reps, dict):
        reps = {}
    key = str(location_code or location_id or "")
    if not key and location_id:
        row = conn.execute("SELECT code FROM locations WHERE id = ?", (int(location_id),)).fetchone()
        key = str(row["code"] if row else location_id)
    try:
        return int(reps.get(key) or reps.get(str(location_id)) or 0)
    except (TypeError, ValueError):
        return 0


def adjust_area_reputation(
    conn,
    *,
    location_id: int | None,
    delta: int,
    reason: str = "",
    location_code: str = "",
) -> dict[str, Any]:
    reps = _settings(conn).get("area_reputation")
    if not isinstance(reps, dict):
        reps = {}
    code = location_code
    if not code and location_id:
        row = conn.execute("SELECT code FROM locations WHERE id = ?", (int(location_id),)).fetchone()
        code = str(row["code"] if row else location_id)
    key = str(code or location_id or "unknown")
    before = int(reps.get(key) or 0)
    after = max(-100, min(100, before + int(delta)))
    reps[key] = after
    _set_setting(conn, "area_reputation", reps)
    if delta:
        try:
            # Optional global karma nudge for big area swings only
            if abs(int(delta)) >= 3:
                prow = conn.execute("SELECT karma FROM player WHERE id = 1").fetchone()
                total = int(prow["karma"] or 0) + int(delta)
                conn.execute("UPDATE player SET karma = ? WHERE id = 1", (total,))
                conn.execute(
                    "INSERT INTO karma_history (turn, delta, total, reason, visibility) VALUES (?, ?, ?, ?, ?)",
                    (_turn_value(conn), int(delta), total, f"area:{key}:{reason}"[:400], "local"),
                )
        except Exception:
            pass
    return {"location": key, "before": before, "after": after, "delta": int(delta), "reason": reason}


def adjust_npc_trust(conn, npc_code: str, delta: int, *, reason: str = "") -> dict[str, Any] | None:
    code = str(npc_code or "").strip()
    if not code:
        return None
    row = conn.execute("SELECT id, trust, name, attitude FROM npcs WHERE code = ?", (code,)).fetchone()
    if not row:
        return None
    before = int(row["trust"] or 0)
    after = max(-100, min(100, before + int(delta)))
    conn.execute("UPDATE npcs SET trust = ? WHERE id = ?", (after, int(row["id"])))
    return {
        "code": code,
        "name": row["name"],
        "before": before,
        "after": after,
        "delta": int(delta),
        "reason": reason,
    }


def apply_social_association_penalty(
    conn,
    *,
    location_id: int | None,
    befriended_npc_code: str,
    trust_gained: int,
) -> list[dict[str, Any]]:
    """
    If the player gains trust with a locally disliked NPC, others sour slightly.
    Reversible later via positive events.
    """
    if trust_gained <= 0 or not location_id:
        return []
    target = conn.execute(
        "SELECT id, code, name, trust, attitude, power_rank FROM npcs WHERE code = ?",
        (str(befriended_npc_code),),
    ).fetchone()
    if not target:
        return []
    # Disliked: low trust from world OR hostile/wary attitude OR low power_rank outsider
    disliked = (
        int(target["trust"] or 0) < -5
        or str(target["attitude"] or "").lower() in {"hostile", "antagonistic", "wary", "apprehensive"}
        or int(target["power_rank"] or 10) <= 8
    )
    if not disliked:
        return []
    others = conn.execute(
        """
        SELECT id, code, name, trust, power_rank, attitude FROM npcs
        WHERE location_id = ? AND code != ?
        ORDER BY power_rank DESC LIMIT 12
        """,
        (int(location_id), str(befriended_npc_code)),
    ).fetchall()
    hits: list[dict[str, Any]] = []
    # Stronger hit if local elites care
    for o in others:
        pr = int(o["power_rank"] or 10)
        if pr < 15 and str(o["attitude"] or "").lower() not in {"hostile", "proud"}:
            continue
        # Small negative: scales with how much the outsider was befriended
        delta = -max(1, min(6, trust_gained // 2 + (1 if pr >= 40 else 0)))
        before = int(o["trust"] or 0)
        after = max(-100, min(100, before + delta))
        conn.execute("UPDATE npcs SET trust = ? WHERE id = ?", (after, int(o["id"])))
        hits.append({"code": o["code"], "name": o["name"], "delta": delta, "after": after})
    if hits:
        adjust_area_reputation(
            conn,
            location_id=location_id,
            delta=-max(1, min(4, len(hits))),
            reason=f"associated_with_disliked:{befriended_npc_code}",
        )
        # Settlement "heat" meter: how much association friction is active
        try:
            row = conn.execute("SELECT code FROM locations WHERE id = ?", (int(location_id),)).fetchone()
            key = str(row["code"] if row else location_id)
            heat = _settings(conn).get("association_heat")
            if not isinstance(heat, dict):
                heat = {}
            heat[key] = min(100, int(heat.get(key) or 0) + max(1, len(hits)))
            _set_setting(conn, "association_heat", heat)
        except Exception:
            pass
    return hits


def apply_event_help_reputation(
    conn,
    *,
    location_id: int | None,
    helper_npc_code: str = "",
    helped_player: bool = True,
) -> dict[str, Any]:
    """Helping the player during an event can repair area rep and helper trust."""
    out: dict[str, Any] = {"area": None, "npc": None, "association_repair": []}
    if not helped_player:
        return out
    if location_id:
        out["area"] = adjust_area_reputation(
            conn, location_id=location_id, delta=3, reason="helped_player_in_event"
        )
    if helper_npc_code:
        out["npc"] = adjust_npc_trust(conn, helper_npc_code, 8, reason="helped_player_in_event")
        # Soften association: small trust to other locals
        others = conn.execute(
            "SELECT code FROM npcs WHERE location_id = ? AND code != ? LIMIT 6",
            (int(location_id or 0), str(helper_npc_code)),
        ).fetchall() if location_id else []
        for o in others:
            r = adjust_npc_trust(conn, str(o["code"]), 1, reason="event_ripple")
            if r:
                out["association_repair"].append(r)
        # Cool association heat after public help
        if location_id:
            try:
                row = conn.execute("SELECT code FROM locations WHERE id = ?", (int(location_id),)).fetchone()
                key = str(row["code"] if row else location_id)
                heat = _settings(conn).get("association_heat")
                if not isinstance(heat, dict):
                    heat = {}
                heat[key] = max(0, int(heat.get(key) or 0) - 8)
                _set_setting(conn, "association_heat", heat)
                out["heat_after"] = heat.get(key)
            except Exception:
                pass
    return out


def resolve_social_disengage(
    conn,
    *,
    npc_code: str,
    walked_away: bool,
    location_id: int | None = None,
) -> dict[str, Any]:
    """
    Player stops engaging after NPC resistance.
    Instant walk-away when they don't want to chat → small rep gain.
    """
    area = get_area_reputation(conn, location_id)
    npc = conn.execute(
        "SELECT code, name, trust, attitude FROM npcs WHERE code = ?",
        (str(npc_code),),
    ).fetchone()
    result: dict[str, Any] = {"npc_code": npc_code, "walked_away": walked_away, "deltas": []}
    if not npc:
        return result
    attitude = str(npc["attitude"] or "").lower()
    resisted = attitude in {
        "dismissive",
        "apprehensive",
        "condescending",
        "antagonistic",
        "hostile",
        "wary",
    } or int(npc["trust"] or 0) < 0
    if walked_away and resisted:
        # Respecting their wish: better with low prior area rep (harder goodwill)
        trust_delta = 3 if area < 0 else 2
        area_delta = 1 if area < 10 else 0
        t = adjust_npc_trust(conn, npc_code, trust_delta, reason="walked_away_when_unwelcome")
        a = adjust_area_reputation(
            conn, location_id=location_id, delta=area_delta, reason="courteous_disengage"
        )
        result["deltas"].append({"npc": t, "area": a})
        result["flavor"] = "respectful_disengage"
    elif walked_away:
        t = adjust_npc_trust(conn, npc_code, 1, reason="ended_chat_politely")
        result["deltas"].append({"npc": t})
        result["flavor"] = "polite_end"
    return result


def resolve_social_persist(
    conn,
    *,
    npc_code: str,
    location_id: int | None = None,
) -> dict[str, Any]:
    """Player keeps pushing talk after cold reception → rep loss (scaled by area rep)."""
    area = get_area_reputation(conn, location_id)
    npc = conn.execute(
        "SELECT code, name, trust, attitude FROM npcs WHERE code = ?",
        (str(npc_code),),
    ).fetchone()
    result: dict[str, Any] = {"npc_code": npc_code, "deltas": []}
    if not npc:
        return result
    attitude = str(npc["attitude"] or "").lower()
    cold = attitude in {
        "dismissive",
        "apprehensive",
        "condescending",
        "antagonistic",
        "hostile",
        "wary",
    }
    if not cold and int(npc["trust"] or 0) >= 5:
        return result  # not a pushy situation
    # Worse if already poorly regarded in the area
    trust_delta = -4 if area < 0 else -2
    area_delta = -2 if area < 5 else -1
    t = adjust_npc_trust(conn, npc_code, trust_delta, reason="persisted_unwanted_chat")
    a = adjust_area_reputation(conn, location_id=location_id, delta=area_delta, reason="pushy_social")
    result["deltas"].append({"npc": t, "area": a})
    result["flavor"] = "pushy_persist"
    return result


def build_ambient_move_line(
    *,
    travel: dict[str, Any],
    travel_result: dict[str, Any],
    weather: dict[str, Any] | None = None,
) -> str:
    """
    Short DM color for free movement — does NOT lock the player or start a scene.
    Significance only: settlement entry, road, ruins, weather change, discovered camps.
    """
    bits: list[str] = []
    terrain = str(travel.get("terrain") or "")
    from_t = str(travel.get("from_terrain") or "")
    mins = int(travel.get("minutes") or 0)
    if travel_result.get("weather_changed") and travel_result.get("weather_announce"):
        bits.append(str(travel_result["weather_announce"]))
    elif weather and weather.get("kind") not in {"clear", None, ""}:
        bits.append(f"{weather.get('label') or weather.get('kind')} holds overhead.")

    if travel.get("base_discovered") or travel_result.get("base_discovered"):
        hb = travel.get("hidden_base") or travel_result.get("hidden_base") or {}
        owner = str(hb.get("owner") or "hidden")
        bits.append(
            f"You uncover a {owner} camp here — a place that will stay marked on your map."
        )
    elif travel.get("settlement_id") and from_t not in {"city", "town", "village", "harbor", "colony"}:
        sm = travel.get("settlement") if isinstance(travel.get("settlement"), dict) else {}
        name = sm.get("name") or sm.get("class") or terrain or "settlement"
        bits.append(f"You enter the bounds of {name}.")
    elif terrain == "road" and from_t != "road":
        bits.append("Bootfalls find packed road — faster going, busier eyes.")
    elif terrain == "forest" and from_t != "forest":
        bits.append("Trees close in; sound flattens under the canopy.")
    elif terrain in {"ruins", "dungeon"}:
        bits.append("Old work shows through the ground here.")
    elif mins >= 20:
        bits.append(f"The crossing takes about {mins} minutes.")

    if travel_result.get("ruler") and isinstance(travel_result["ruler"], dict):
        r = travel_result["ruler"]
        bits.append(f"Local authority ({r.get('name') or 'someone important'}) is known here.")
        hier = r.get("hierarchy") if isinstance(r.get("hierarchy"), list) else []
        if len(hier) > 1:
            bits.append(f"A small staff of {len(hier) - 1} underlings answers to them.")

    # Never invent combat in ambient — encounters fire real scenes separately
    return " ".join(bits).strip()


def consume_weather_announce(conn) -> dict[str, Any] | None:
    pending = _settings(conn).get("weather_announce_pending")
    if not isinstance(pending, dict) or not pending.get("text"):
        return None
    _set_setting(conn, "weather_announce_pending", None)
    return pending


def _lerp(a: float, b: float, t: float) -> float:
    t = max(0.0, min(1.0, float(t)))
    return float(a) + (float(b) - float(a)) * t


def _time_of_day_crowd_mods(
    hour: int,
    *,
    settlement_like: bool,
    market_like: bool,
) -> dict[str, float]:
    """
    n5: Scale crowd/danger by clock hour.
    Settlements: market day (08–16) busier; night quieter but riskier alleys.
    Wilds: night slightly emptier crowd, higher danger.
    Returns multipliers (crowd_mul, danger_mul) around 1.0 and a band label.
    """
    hour = max(0, min(23, int(hour)))
    # Bands: night 22–5, dawn 5–8, day 8–16 (market peak 10–14), evening 16–22
    if 5 <= hour < 8:
        band = "dawn"
        crowd_mul, danger_mul = 0.75, 0.95
    elif 8 <= hour < 16:
        band = "day"
        crowd_mul, danger_mul = 1.15, 0.9
        if 10 <= hour < 14:
            band = "market"
            crowd_mul, danger_mul = 1.35, 0.85
    elif 16 <= hour < 22:
        band = "evening"
        crowd_mul, danger_mul = 1.05, 1.0
    else:
        band = "night"
        crowd_mul, danger_mul = 0.45, 1.2

    if settlement_like:
        if band == "night":
            # Quiet streets, more petty risk
            crowd_mul *= 0.85
            danger_mul *= 1.1
        elif band in {"day", "market"}:
            crowd_mul *= 1.05
            danger_mul *= 0.95
        if market_like and band in {"day", "market"}:
            crowd_mul = min(1.6, crowd_mul * 1.15)
    else:
        # Wild / road: fewer faces at night, more threat
        if band == "night":
            crowd_mul *= 0.7
            danger_mul *= 1.15
        elif band == "dawn":
            danger_mul *= 1.05

    return {
        "band": band,
        "hour": hour,
        "crowd_mul": round(crowd_mul, 3),
        "danger_mul": round(danger_mul, 3),
    }


def _local_crowd_danger(context: dict[str, Any] | None = None) -> dict[str, float]:
    """0–1 crowd and danger from setup + local NPCs + map tile + time-of-day."""
    context = context or {}
    opts = ((context.get("settings") or {}).get("playthrough_options") or {})
    if not isinstance(opts, dict):
        opts = {}
    density = str(opts.get("npc_density") or "moderate").lower()
    difficulty = str(opts.get("difficulty") or "normal").lower()
    crowd = 0.45
    if "sparse" in density:
        crowd = 0.2
    elif "dense" in density or "faction" in density:
        crowd = 0.75
    elif "moderate" in density:
        crowd = 0.45
    loc = context.get("current_location") or {}
    local_npcs = []
    if isinstance(loc, dict) and loc.get("id") is not None:
        for location in context.get("locations") or []:
            if isinstance(location, dict) and location.get("id") == loc.get("id"):
                local_npcs = list(location.get("npcs") or [])
                break
    # Shells still count toward crowd
    crowd = min(1.0, crowd + min(0.35, len(local_npcs) * 0.04))

    danger = 0.25
    if difficulty in {"hard", "brutal"}:
        danger = 0.45 if difficulty == "hard" else 0.6
    elif difficulty == "easy":
        danger = 0.12
    # Map tile danger if present on context
    tile = context.get("map_tile") if isinstance(context.get("map_tile"), dict) else {}
    tile_state = str(tile.get("state") or "").lower()
    high = {"dungeon", "wreck", "ruins", "volcano", "lava", "anomaly", "ash"}
    mid = {"swamp", "mountain", "cliff", "desert", "tundra", "forest"}
    low = {"city", "town", "village", "farm", "harbor", "station", "colony", "road"}
    settlement_like = tile_state in low or bool(context.get("settlement_meta"))
    if tile_state in high:
        danger = min(1.0, danger + 0.35)
        settlement_like = False
    elif tile_state in mid:
        danger = min(1.0, danger + 0.15)
        settlement_like = False
    elif tile_state in low:
        danger = max(0.05, danger - 0.12)
        crowd = min(1.0, crowd + 0.08)
    # Settlement meta indices when walking a city blob
    sm = context.get("settlement_meta") if isinstance(context.get("settlement_meta"), dict) else {}
    if sm.get("crowd_index") is not None:
        try:
            crowd = max(crowd, min(1.0, float(sm["crowd_index"])))
            settlement_like = True
        except (TypeError, ValueError):
            pass
    if sm.get("danger_index") is not None:
        try:
            danger = max(danger, min(1.0, float(sm["danger_index"])))
        except (TypeError, ValueError):
            pass
    name = str(loc.get("name") or "").lower()
    market_like = any(w in name for w in ("market", "bazaar", "forum", "plaza", "square"))
    if any(w in name for w in ("dungeon", "ruin", "wild", "waste", "ash")):
        danger = min(1.0, danger + 0.1)
        settlement_like = False
    if any(w in name for w in ("market", "gate", "ward", "harbor", "pier", "town", "city")):
        crowd = min(1.0, crowd + 0.1)
        danger = max(0.05, danger - 0.05)
        settlement_like = True

    # Time-of-day modulation (n5)
    hour = 12
    try:
        wt = context.get("world_time") if isinstance(context.get("world_time"), dict) else None
        if wt and wt.get("hour") is not None:
            hour = int(wt["hour"])
        else:
            hour = int(get_world_time().get("hour") or 12)
    except Exception:
        hour = 12
    tod = _time_of_day_crowd_mods(hour, settlement_like=settlement_like, market_like=market_like)
    crowd = max(0.02, min(1.0, crowd * float(tod["crowd_mul"])))
    danger = max(0.02, min(1.0, danger * float(tod["danger_mul"])))

    out = {
        "crowd": round(crowd, 3),
        "danger": round(danger, 3),
        "time_band": tod["band"],
        "hour": hour,
        "crowd_mul": tod["crowd_mul"],
        "danger_mul": tod["danger_mul"],
    }

    # Standing still is exposure too: run the same player-aware danger model
    # the travel path uses, so resting wounded and exhausted in a bad place is
    # actually riskier than resting fresh in a good one. Crowd stays as
    # computed above — how many people are around is not about the player.
    try:
        from app import encounters as encounters_mod

        snapshot = encounters_mod.player_snapshot()
        assessment = encounters_mod.assess_danger(
            terrain=tile_state or ("town" if settlement_like else "plains"),
            weather=context.get("weather") if isinstance(context.get("weather"), dict) else get_weather(),
            world_time=context.get("world_time") if isinstance(context.get("world_time"), dict) else {"hour": hour},
            player=snapshot.get("player"),
            skills=snapshot.get("skills"),
            resources=snapshot.get("resources"),
            inventory_summary=snapshot.get("inventory_summary"),
            options=opts,
            settlement=sm or None,
            area_reputation=int(snapshot.get("area_reputation") or 0),
        )
        # Blend rather than replace: the location-flavour heuristics above know
        # things the terrain table does not (named wards, market squares).
        blended = (float(assessment.get("danger") or danger) + danger) / 2.0
        out["danger"] = round(max(0.02, min(1.0, blended)), 3)
        out["danger_band"] = assessment.get("band")
        out["danger_factors"] = assessment.get("factors") or []
        out["danger_environment"] = assessment.get("environment")
        out["danger_player_multiplier"] = assessment.get("player_multiplier")
    except Exception:
        pass

    return out


def roll_wait_events(
    *,
    minutes: int,
    crowd: float,
    danger: float,
    seed: int,
) -> dict[str, Any]:
    """
    Event exposure scales with hours waited.
    base_per_hour grows with danger and crowd; p = 1-(1-base)^hours.
    """
    minutes = max(1, int(minutes))
    hours = minutes / 60.0
    base_per_hour = _lerp(0.05, 0.55, danger) * _lerp(0.5, 1.4, crowd)
    # Weather pressure (server weather snapshot, if any, on field_context via seed only — caller can pre-boost danger)
    base_per_hour = max(0.02, min(0.85, base_per_hour))
    p_any = 1.0 - (1.0 - base_per_hour) ** hours
    expected = min(4.0, base_per_hour * hours)
    rng = random.Random(int(seed) & 0x7FFFFFFF)
    events: list[dict[str, Any]] = []
    # Number of events: poisson-ish from expected
    n = 0
    if rng.random() < p_any:
        n = 1
        while n < 4 and rng.random() < min(0.55, expected / max(1.0, n + 1)):
            n += 1
    for i in range(n):
        kind = rng.choice(WAIT_EVENT_KINDS)
        # Violent / social pressure → prefer nameless shells
        if kind in {"fight_nearby", "pickpocket_attempt", "stranger_passes", "patrol_pass"}:
            tier = "nameless" if rng.random() < 0.75 else "background"
        elif kind in {"rumor"}:
            tier = "background" if rng.random() < 0.6 else "event_worthy"
        else:
            tier = "background"
        events.append(
            {
                "kind": kind,
                "participant_tier": tier,
                "outcome_seed": rng.randint(1, 999999),
                "index": i,
            }
        )
    return {
        "minutes": minutes,
        "hours": round(hours, 4),
        "base_per_hour": round(base_per_hour, 4),
        "p_any": round(p_any, 4),
        "expected": round(expected, 4),
        "event_count": len(events),
        "events": events,
        "crowd": round(float(crowd), 3),
        "danger": round(float(danger), 3),
        "seed": int(seed),
    }


_SHELL_NAME_PARTS_A = (
    "Ash", "Bell", "Cinder", "Dock", "Elm", "Fog", "Grain", "Hearth", "Ivy", "Jet",
    "Kite", "Lark", "Moss", "Nettle", "Oak", "Pike", "Quill", "Reed", "Salt", "Thorn",
)
_SHELL_NAME_PARTS_B = (
    "walker", "hand", "wick", "bin", "well", "line", "post", "cut", "mark", "field",
    "row", "gate", "path", "coil", "hook", "rest", "lane", "drift", "watch", "keep",
)


def create_shell_npc(
    conn,
    location_id: int,
    *,
    presence: str = "nameless",
    power_rank: int = 0,
    role: str = "passerby",
    seed: int | None = None,
    appearance: str = "",
) -> dict[str, Any]:
    """
    Minimal NPC for crowd / one-shot drama. No portrait, no deep stats.

    `role` is an occupation; `appearance` is how they look. Folding the two
    together is what produced a world where every face was a "hooded stranger".
    """
    presence = presence if presence in {"nameless", "background", "event_worthy"} else "nameless"
    # Uniqueness is world-wide, not per-location: the pool is 20x20, and a run
    # with sixteen seeded faces produced three separate people all called
    # "Grainwick". Two of anyone reads as one character in two places.
    name = unique_person_name(
        conn,
        seed if seed is not None else random.randint(1, 10**9),
    )
    code = _next_alpha_code(conn, "npcs")
    shell = 1 if presence in {"nameless", "background"} else 0
    portrait = 0 if shell else 1
    power_rank = max(0, min(100, int(power_rank)))
    cur = conn.execute(
        """
        INSERT INTO npcs (
            code, location_id, name, race, role, summary, attitude,
            personality, likes, principles, dislikes, trust, known_facts,
            rank, stat_profile, skill_profile, health, max_health,
            presence, power_rank, portrait_eligible, shell
        ) VALUES (?, ?, ?, 'human', ?, ?, 'neutral', '', '', '', '', 0, '[]', 'F', '{}', '{}', 0, 0, ?, ?, ?, ?)
        """,
        (
            code,
            int(location_id),
            name,
            str(role or "passerby")[:80],
            (("A brief face in the crowd." if presence == "nameless" else "Someone at the edge of the scene.")
             + str(appearance or ""))[:300],
            presence,
            power_rank,
            portrait,
            shell,
        ),
    )
    row = conn.execute("SELECT * FROM npcs WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row) if row else {"code": code, "name": name, "presence": presence, "power_rank": power_rank, "shell": shell}


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
    resources = state.get("resources")
    if not isinstance(resources, dict) and isinstance(state.get("player"), dict):
        resources = (state.get("player") or {}).get("resources")
    if isinstance(resources, dict) and resources:
        mechanics["resources"] = {
            "energy": resources.get("energy"),
            "max_energy": resources.get("max_energy"),
            "mana": resources.get("mana"),
            "max_mana": resources.get("max_mana"),
            "fatigue": resources.get("fatigue"),
            "max_fatigue": resources.get("max_fatigue"),
            "band": resources.get("band"),
            "fatigue_stamina_mult": resources.get("fatigue_stamina_mult"),
            "mana_enabled": resources.get("mana_enabled"),
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
    source_index_dir().mkdir(parents=True, exist_ok=True)
    for existing in source_index_dir().rglob("*.jsonl"):
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
        _write_jsonl(source_index_dir() / relative, rows)
    manifest = {
        "format": "ai-rpg-source-index-v1",
        "description": "Line-oriented source index for searching durable RPG facts without loading full history into the LLM prompt.",
        "files": {relative: {"records": len(rows)} for relative, rows in files.items()},
    }
    source_index_manifest().write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")


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
    if not query_tokens or not source_index_dir().exists():
        return []
    results: list[dict[str, Any]] = []
    for path in source_index_dir().rglob("*.jsonl"):
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
                                "source": str(path.relative_to(source_index_dir())).replace("\\", "/"),
                                "line": line_number,
                                "score": round(score, 4),
                            }
                        )
        except OSError:
            continue
    return sorted(results, key=lambda item: (item["score"], item.get("importance") or 0), reverse=True)[:limit]


def _load_consolidated_facts() -> list[dict[str, Any]]:
    if not consolidated_facts_path().exists():
        return []
    facts: list[dict[str, Any]] = []
    try:
        with consolidated_facts_path().open("r", encoding="utf-8") as handle:
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
    consolidated_facts_path().parent.mkdir(parents=True, exist_ok=True)
    trimmed = facts[-MEMORY_CONSOLIDATE_MAX_FACTS:]
    _write_jsonl(consolidated_facts_path(), trimmed)


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
    if history_summary_path().exists():
        try:
            lines = [line for line in history_summary_path().read_text(encoding="utf-8").splitlines() if line.strip()]
            if len(lines) > keep:
                history_summary_path().write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
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
    campaign_slots_dir().mkdir(parents=True, exist_ok=True)
    slots: list[dict[str, Any]] = []
    for path in sorted(campaign_slots_dir().glob("*/world.json")):
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


AUTOSAVE_SLOT = "last"


def save_campaign_slot(slot_name: str) -> dict[str, Any]:
    safe = _safe_slot_name(slot_name)
    payload = export_world()
    slot_dir = campaign_slots_dir() / safe
    slot_dir.mkdir(parents=True, exist_ok=True)
    world_path = slot_dir / "world.json"
    world_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    state = get_state(include_hidden=False)
    player = state.get("player") or {}
    location = state.get("current_location") or {}
    turn = 0
    for item in state.get("turn_summaries") or []:
        try:
            turn = max(turn, int(item.get("turn") or 0))
        except (TypeError, ValueError):
            pass
    try:
        with connect() as conn:
            row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
            if row:
                turn = max(turn, int(row["value"] or 0))
    except Exception:
        pass
    snap = resume_snapshot(state)
    metadata = {
        "slot": safe,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "player_name": player.get("name"),
        "player_level": player.get("level"),
        "location": location.get("name"),
        "turn": turn or snap.get("turn") or 0,
        "format": payload.get("format"),
        "setup_complete": bool(state.get("setup_complete")),
        "autosave": safe == AUTOSAVE_SLOT,
        "history_count": snap.get("history_count") or 0,
        "has_map": bool(snap.get("has_map")),
        "active_world_map_id": snap.get("active_world_map_id") or "",
    }
    (slot_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    return metadata


def autosave_campaign() -> dict[str, Any] | None:
    """Persist current world to the continue-game slot. Safe to call after every turn."""
    try:
        state = get_state(include_hidden=False)
        if not state.get("setup_complete"):
            return None
        return save_campaign_slot(AUTOSAVE_SLOT)
    except Exception:
        return None


def resume_snapshot(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Last narration/input + counts for Continue UI rehydration."""
    state = state if isinstance(state, dict) else get_state(include_hidden=False)
    history = list(state.get("history") or [])
    # journal/history is newest-first from get_state
    narration = next((h for h in history if str(h.get("kind") or "") == "narration"), None)
    last_input = next(
        (
            h
            for h in history
            if str(h.get("kind") or "") in {"player", "opening", "continue", "regenerate", "wait"}
        ),
        None,
    )
    summaries = list(state.get("turn_summaries") or [])
    summary_text = ""
    if summaries:
        summary_text = str(summaries[0].get("summary") or "").strip()
    settings = state.get("settings") or {}
    map_id = str(settings.get("active_world_map_id") or "").strip()
    has_map = False
    if map_id:
        try:
            with connect() as conn:
                row = conn.execute("SELECT id FROM world_maps WHERE id = ?", (map_id,)).fetchone()
                has_map = row is not None
                if not has_map:
                    # Fall back: any map exists
                    any_map = conn.execute("SELECT id FROM world_maps LIMIT 1").fetchone()
                    has_map = any_map is not None
                    if has_map and not map_id:
                        map_id = str(any_map["id"])
        except Exception:
            has_map = False
    return {
        "last_narration": str((narration or {}).get("content") or "").strip(),
        "last_input": str((last_input or {}).get("content") or "").strip(),
        "last_input_kind": str((last_input or {}).get("kind") or "").strip(),
        "last_summary": summary_text,
        "history_count": len(history),
        "summary_count": len(summaries),
        "has_map": has_map,
        "active_world_map_id": map_id,
        "turn": int((narration or last_input or {}).get("turn") or 0) if (narration or last_input) else 0,
    }


def has_continuable_save() -> dict[str, Any]:
    """Whether Continue can load a previous playthrough."""
    # Live DB first
    try:
        state = get_state(include_hidden=False)
        if state.get("setup_complete"):
            loc = (state.get("current_location") or {}).get("name") or ""
            player = (state.get("player") or {}).get("name") or ""
            turn = 0
            try:
                with connect() as conn:
                    row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
                    if row:
                        turn = int(row["value"] or 0)
            except Exception:
                pass
            snap = resume_snapshot(state)
            if snap.get("turn"):
                turn = max(turn, int(snap["turn"] or 0))
            return {
                "ok": True,
                "source": "live",
                "slot": AUTOSAVE_SLOT,
                "player_name": player,
                "location": loc,
                "turn": turn,
                "history_count": snap.get("history_count") or 0,
                "has_map": bool(snap.get("has_map")),
            }
    except Exception:
        pass
    # Disk autosave
    meta_path = campaign_slots_dir() / AUTOSAVE_SLOT / "metadata.json"
    world_path = campaign_slots_dir() / AUTOSAVE_SLOT / "world.json"
    if world_path.exists():
        meta: dict[str, Any] = {}
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        return {
            "ok": True,
            "source": "slot",
            "slot": AUTOSAVE_SLOT,
            "player_name": meta.get("player_name") or "",
            "location": meta.get("location") or "",
            "turn": meta.get("turn") or 0,
            "saved_at": meta.get("saved_at") or "",
            "has_map": bool(meta.get("has_map")),
        }
    return {"ok": False, "source": "none", "slot": AUTOSAVE_SLOT}


def load_campaign_slot(slot_name: str) -> dict[str, Any]:
    safe = _safe_slot_name(slot_name)
    world_path = campaign_slots_dir() / safe / "world.json"
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
    slot_dir = campaign_slots_dir() / safe
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


def _is_place_or_item_code(value: Any) -> bool:
    """True for location/item/event codes (L1, I2, E3) — never valid NPC codes."""
    return bool(re.fullmatch(r"[LIElie]\d+", str(value or "").strip()))


def _looks_like_misfiled_location(npc: dict[str, Any]) -> bool:
    """
    Model sometimes puts a place into the npcs[] array:
      {code: L1, name: \"Second Shadow Inn\", role: location|place|inn}
    Those must not become people.
    """
    if not isinstance(npc, dict):
        return True
    code = str(npc.get("code") or "").strip()
    name = norm_name(str(npc.get("name") or ""))
    role = str(npc.get("role") or "").strip().lower()
    if _is_place_or_item_code(code) and (
        not name
        or not is_plausible_person_name(name)
        or role in {"location", "place", "locale", "site", "area", "room", "building", "inn", "gate", "road"}
    ):
        return True
    if role in {"location", "place", "locale", "site", "area", "room", "building"}:
        return True
    # Name is only a place code
    if _is_place_or_item_code(name):
        return True
    return False


def _collect_npcs_from_turn_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Flatten top-level npcs + nested locations[].npcs.
    8B models often nest cast under the place and leave top-level npcs empty —
    that was creating places with zero people, then prose fell back to [[L1]] as a 'character'.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(raw: Any, *, default_location: str = "") -> None:
        if isinstance(raw, str):
            text = norm_name(raw)
            if not text or _is_place_or_item_code(text):
                return
            raw = {"name": text, "location": default_location}
        if not isinstance(raw, dict):
            return
        npc = dict(raw)
        if _looks_like_misfiled_location(npc):
            return
        # Strip place/item codes forced into npc.code (allocate real alpha on insert)
        code = str(npc.get("code") or "").strip()
        if _is_place_or_item_code(code) or re.fullmatch(r"I\d+|E\d+", code, re.I):
            npc["code"] = ""
        if default_location and not (npc.get("location") or npc.get("location_code")):
            npc["location"] = default_location
        name = norm_name(str(npc.get("name") or ""))
        # Reject bare place codes as names
        if _is_place_or_item_code(name):
            return
        key = f"{str(npc.get('code') or '').upper()}|{name.lower()}"
        if key in seen or key == "|":
            return
        seen.add(key)
        out.append(npc)

    for npc in result.get("npcs") or []:
        add(npc)
    for loc in result.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        loc_ref = str(loc.get("name") or loc.get("code") or "").strip()
        nested = loc.get("npcs") or loc.get("people") or loc.get("characters") or []
        if isinstance(nested, list):
            for npc in nested:
                add(npc, default_location=loc_ref)
    # Conversations / events often name speakers the model forgot to put in npcs[]
    for convo in result.get("conversations") or []:
        if not isinstance(convo, dict):
            continue
        ref = str(convo.get("npc_name") or convo.get("name") or "").strip()
        code = str(convo.get("npc_code") or convo.get("code") or "").strip()
        if _is_place_or_item_code(code):
            code = ""
        if ref and not _is_place_or_item_code(ref):
            add({"name": ref, "code": code, "role": "local", "presence": "event_worthy"})
        elif code and re.fullmatch(r"[A-Za-z]{1,3}", code):
            # Known alpha code only — let upsert match existing; no place codes
            add({"code": code, "name": "", "role": "local"})
    for event in result.get("events") or []:
        if not isinstance(event, dict):
            continue
        ref = str(event.get("npc_name") or "").strip()
        code = str(event.get("npc_code") or "").strip()
        if _is_place_or_item_code(code):
            code = ""
        if ref and not _is_place_or_item_code(ref):
            add(
                {
                    "name": ref,
                    "code": code,
                    "location": event.get("location") or event.get("location_code") or "",
                    "role": "local",
                    "presence": "event_worthy",
                }
            )
    return out


def _sanitize_stored_entity_names(conn) -> None:
    """One-shot cleanup for corrupt saves (event titles used as people/places)."""
    try:
        # NPC rows that stole location/item codes (L1/I1) → reassign alpha codes
        for row in conn.execute("SELECT id, name, code FROM npcs").fetchall():
            code = str(row["code"] or "").strip()
            if _is_place_or_item_code(code) or re.fullmatch(r"I\d+|E\d+", code, re.I) or not code:
                try:
                    new_code = _next_alpha_code(conn, "npcs")
                    conn.execute("UPDATE npcs SET code = ? WHERE id = ?", (new_code, int(row["id"])))
                    code = new_code
                except Exception:
                    pass
            name = str(row["name"] or "")
            if is_plausible_person_name(name):
                continue
            fixed = invent_person_name(seed=name_seed(code, row["id"]))
            conn.execute("UPDATE npcs SET name = ? WHERE id = ?", (fixed, int(row["id"])))
        for row in conn.execute("SELECT id, name, code FROM locations").fetchall():
            name = str(row["name"] or "")
            if is_plausible_place_name(name):
                continue
            code = str(row["code"] or "L?")
            fixed = f"Place {code}" if code else "Nearby street"
            # Prefer a short generic over a sentence
            if re.fullmatch(r"L\d+", code, flags=re.I):
                fixed = f"Locale {code}"
            conn.execute("UPDATE locations SET name = ? WHERE id = ?", (fixed, int(row["id"])))
    except Exception:
        pass


def get_state(include_hidden: bool = False) -> dict[str, Any]:
    with connect() as conn:
        settings = _settings(conn)
        if settings.get("setup_complete") == "true" or settings.get("setup_complete") is True:
            has_slots = conn.execute("SELECT 1 FROM equipment_slots LIMIT 1").fetchone()
            if has_slots is None:
                _ensure_default_equipment_slots(conn)
            _sanitize_stored_entity_names(conn)
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
        world_time = get_world_time(conn)
        turn_number = int(_float(_pacing_get(conn, "turn", "0"), 0))

    for npc in npcs:
        npc["known_facts"] = _json(npc.get("known_facts"), [])
        npc["stat_profile"] = _json(npc.get("stat_profile"), {})
        npc["skill_profile"] = _json(npc.get("skill_profile"), {})
        raw_role = str(npc.get("role") or "")
        clean_role = _sanitize_npc_role(raw_role)
        if clean_role != raw_role:
            npc["role"] = clean_role
        npc["combat_profile"] = _combat_profile_from_npc(npc)
    for convo in conversations:
        convo["player_claims"] = _json(convo.get("player_claims"), [])
    for item in inventory:
        item["enchantments"] = _json(item.get("enchantments"), [])
        item["stat_modifiers"] = _normalize_stat_modifiers(item.get("stat_modifiers"))
        item["granted_abilities"] = _normalize_granted_abilities(item.get("granted_abilities"), item)
        # Machine-usable links: canonical stat keys, referenced power codes,
        # and the check modifiers the dice roller applies while equipped.
        item["stat_links"] = _json(item.get("stat_links"), {})
        item["power_codes"] = _json(item.get("power_codes"), [])
        item["roll_profile"] = _json(item.get("roll_profile"), {})
    for slot in equipment_slots:
        slot["accepts"] = _json(slot.get("accepts"), [])
    for entry in verification_memory:
        entry["entity_codes"] = _json(entry.get("entity_codes"), [])

    for ability in abilities:
        ability["roll_profile"] = _json(ability.get("roll_profile"), {})
        ability["resource_cost"] = _json(ability.get("resource_cost"), {})
        ability["read_only"] = bool(ability.get("read_only", 1))

    equipment_effects = _equipment_effects(inventory)
    state_abilities = [*abilities, *equipment_effects["granted_abilities"]]
    if player is not None:
        player["effective_stats"] = equipment_effects["stat_modifiers"]
        player["equipment_ability_names"] = [ability.get("name") for ability in equipment_effects["granted_abilities"] if ability.get("name")]

    # Flat check modifiers currently in effect from equipped gear and passive
    # or item-granted powers. Surfaced so the UI can show why a roll succeeded
    # and so the narrator never has to compute a bonus itself.
    try:
        from app.skill_checks import gear_roll_modifiers

        gear_rolls = gear_roll_modifiers(inventory, state_abilities)
    except Exception:
        gear_rolls = {"modifiers": {}, "sources": []}

    # Energy / fatigue / mana pools (server-enforced)
    resources: dict[str, Any] = {}
    opts = settings.get("playthrough_options") if isinstance(settings.get("playthrough_options"), dict) else {}
    try:
        from app.player_resources import ensure_player_resources

        with connect() as res_conn:
            resources = ensure_player_resources(
                res_conn,
                opts,
                player=player,
                stats=(player or {}).get("effective_stats") if isinstance(player, dict) else None,
            )
        if isinstance(player, dict) and resources:
            for key in (
                "energy",
                "max_energy",
                "mana",
                "max_mana",
                "fatigue",
                "max_fatigue",
            ):
                if key in resources:
                    player[key] = resources[key]
            player["resources"] = resources
    except Exception:
        resources = {}

    collapse: dict[str, Any] = {}
    res_settings: dict[str, Any] = {}
    try:
        from app.player_resources import collapse_state, resource_settings as _resource_settings

        collapse = collapse_state(resources) if resources else {}
        res_settings = _resource_settings(opts) if opts else _resource_settings({})
        if isinstance(player, dict) and collapse:
            player["collapse"] = collapse
    except Exception:
        collapse = {}
        res_settings = {}

    # Stamp power costs + cooldown / afford flags on abilities
    try:
        from app.player_resources import (
            enrich_ability_runtime,
            load_ability_cooldowns,
            magic_allows_mana,
        )

        magic_ok = magic_allows_mana(str(opts.get("magic_level") or ""), opts)
        cds = load_ability_cooldowns(settings)
        res_for_afford = dict(resources) if resources else {}
        if isinstance(player, dict) and player.get("health") is not None:
            res_for_afford["health"] = player.get("health")
        enriched: list[dict[str, Any]] = []
        for ab in state_abilities:
            if not isinstance(ab, dict):
                continue
            # Persist missing resource_cost for DB-backed abilities
            needs_persist = False
            if ab.get("id") is not None:
                raw_rc = ab.get("resource_cost")
                if not raw_rc or raw_rc in ("{}", ""):
                    needs_persist = True
            stamped = enrich_ability_runtime(
                ab,
                magic_ok=magic_ok,
                cooldowns=cds,
                world_time=world_time,
                resources=res_for_afford,
            )
            if needs_persist and stamped.get("resource_cost") and ab.get("id") is not None:
                try:
                    with connect() as ab_conn:
                        ab_conn.execute(
                            "UPDATE abilities SET resource_cost = ?, cost = COALESCE(NULLIF(cost, ''), ?) WHERE id = ?",
                            (
                                json.dumps(stamped["resource_cost"], ensure_ascii=True),
                                str(stamped.get("cost") or "")[:300],
                                int(ab["id"]),
                            ),
                        )
                except Exception:
                    pass
            enriched.append(stamped)
        state_abilities = enriched
        abilities = [a for a in enriched if a.get("id") is not None or a.get("source") not in {None}]
    except Exception:
        pass

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
    if current_location:
        # What can be walked into from right here, and whether it is open at this
        # hour. Without this the model has no way to know a shop exists, so it
        # invents one -- which is how an apothecary appeared in a hamlet.
        current_location = dict(current_location)
        inside_id = int(current_location.get("parent_id") or 0)
        current_location["venues_here"] = venues_at(conn, int(current_location["id"]))
        if inside_id:
            parent = next((loc for loc in locations if loc["id"] == inside_id), None)
            current_location["inside_venue"] = True
            current_location["venue_kind"] = str(current_location.get("kind") or "")
            current_location["exit_to"] = str((parent or {}).get("name") or "")
            keeper_id = int(current_location.get("keeper_npc_id") or 0)
            keeper = next((n for n in npcs if int(n.get("id") or 0) == keeper_id), None) if keeper_id else None
            if keeper:
                current_location["keeper"] = {
                    "code": str(keeper.get("code") or ""),
                    "name": str(keeper.get("name") or ""),
                    "role": str(keeper.get("role") or ""),
                }
            # Siblings share the street outside, so they are one step away, not two.
            current_location["venues_here"] = venues_at(conn, inside_id)
        else:
            current_location["inside_venue"] = False
            current_location["settlement_size"] = settlement_size_for(conn, current_location)

    context_window = context_window_tokens()
    latest_budget = max((int(log.get("estimated_tokens") or 0) for log in model_logs[:2]), default=0)
    state = {
        "setup_complete": settings.get("setup_complete") == "true" or settings.get("setup_complete") is True,
        "settings": settings,
        "player": player,
        "resources": resources,
        "collapse": collapse,
        "resource_settings": res_settings,
        "current_location": current_location,
        "locations": location_tree,
        "inventory": inventory,
        "equipment_slots": equipment_slots,
        "inventory_capacity_modifiers": inventory_capacity_modifiers,
        "inventory_summary": _inventory_summary(settings, inventory, equipment_slots, inventory_capacity_modifiers),
        "equipment_effects": equipment_effects,
        "gear_roll_modifiers": gear_rolls,
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
            "consolidated_facts": len(_load_consolidated_facts()) if consolidated_facts_path().exists() else 0,
            "turn_summaries": len(turn_summaries),
        },
        "rewind_points": rewind_points,
        "history": journal,
        "world_time": world_time,
        "turn": turn_number,
        "weather": get_weather(conn),
    }
    raw_conditions = settings.get("player_conditions")
    if isinstance(raw_conditions, list):
        state["conditions"] = raw_conditions
    elif isinstance(raw_conditions, str) and raw_conditions.strip():
        try:
            state["conditions"] = json.loads(raw_conditions)
        except Exception:
            state["conditions"] = []
    else:
        state["conditions"] = []
    tr = settings.get("travel_ready")
    if isinstance(tr, bool):
        state["travel_ready"] = tr
    else:
        state["travel_ready"] = str(tr).lower() in {"1", "true", "yes", "on"} if tr is not None else True
    # Location specials: heavens prison (blank map + no free movement), etc.
    loc_flags = settings.get("location_special_flags")
    if isinstance(loc_flags, str) and loc_flags.strip():
        try:
            loc_flags = json.loads(loc_flags)
        except Exception:
            loc_flags = {}
    if not isinstance(loc_flags, dict):
        loc_flags = {}
    ml = settings.get("movement_locked")
    if isinstance(ml, bool):
        movement_locked = ml
    else:
        movement_locked = str(ml).lower() in {"1", "true", "yes", "on"} if ml is not None else bool(
            loc_flags.get("movement_locked")
        )
    mb = settings.get("map_blank")
    if isinstance(mb, bool):
        map_blank = mb
    else:
        map_blank = str(mb).lower() in {"1", "true", "yes", "on"} if mb is not None else bool(
            loc_flags.get("map_blank")
        )
    state["location_special_flags"] = loc_flags
    state["movement_locked"] = bool(movement_locked)
    state["map_blank"] = bool(map_blank)
    portrait = settings.get("player_portrait")
    if isinstance(portrait, dict):
        state["player_portrait"] = portrait
    elif isinstance(portrait, str) and portrait.strip().startswith("{"):
        try:
            state["player_portrait"] = json.loads(portrait)
        except Exception:
            state["player_portrait"] = None
    else:
        state["player_portrait"] = None
    fullbody = settings.get("player_fullbody")
    if isinstance(fullbody, dict):
        state["player_fullbody"] = fullbody
    elif isinstance(fullbody, str) and fullbody.strip().startswith("{"):
        try:
            state["player_fullbody"] = json.loads(fullbody)
        except Exception:
            state["player_fullbody"] = None
    else:
        state["player_fullbody"] = None
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


def get_session_theme() -> dict[str, Any]:
    """Current playthrough session_theme (empty if setup not complete / no theme)."""
    state = get_state()
    options = ((state.get("settings") or {}).get("playthrough_options") or {})
    theme = options.get("session_theme") if isinstance(options, dict) else None
    return dict(theme) if isinstance(theme, dict) else {}


def update_session_theme(patch: dict[str, Any] | None) -> dict[str, Any]:
    """
    Merge fields into playthrough_options.session_theme (mid-run override).
    Supports theme_model (model routing) and light metadata fields.
    """
    if not isinstance(patch, dict):
        patch = {}
    with connect() as conn:
        raw = conn.execute("SELECT value FROM settings WHERE key = 'playthrough_options'").fetchone()
        options: dict[str, Any] = {}
        if raw and raw["value"]:
            try:
                loaded = json.loads(raw["value"])
                if isinstance(loaded, dict):
                    options = loaded
            except json.JSONDecodeError:
                options = {}
        theme = options.get("session_theme") if isinstance(options.get("session_theme"), dict) else {}
        theme = dict(theme)
        if "theme_model" in patch:
            theme["theme_model"] = str(patch.get("theme_model") or "")[:120]
        for key, limit in (
            ("adapter_hint", 80),
            ("genre", 120),
            ("tone", 120),
            ("edge", 200),
            ("dm_stance", 240),
            ("style_notes", 400),
        ):
            if key in patch and patch[key] is not None:
                theme[key] = str(patch.get(key) or "")[:limit]
        if "isekai" in patch:
            theme["isekai"] = bool(patch.get("isekai"))
        if "power_fantasy" in patch and isinstance(patch.get("power_fantasy"), dict):
            existing_pf = theme.get("power_fantasy") if isinstance(theme.get("power_fantasy"), dict) else {}
            theme["power_fantasy"] = {**existing_pf, **patch["power_fantasy"]}
        options["session_theme"] = theme
        _set_setting(conn, "playthrough_options", options)
    return theme


def _clear_playthrough(conn) -> None:
    # A new playthrough gets fresh luck: forget the memoized seed and the old
    # roll history so audit rows never bleed across campaigns.
    try:
        from app.rng import reset_seed_cache

        reset_seed_cache()
        conn.execute("DELETE FROM settings WHERE key = 'campaign_rng_seed'")
        conn.execute("DELETE FROM dice_rolls")
    except Exception:
        pass

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
    if history_summary_path().exists():
        history_summary_path().unlink()
    if source_index_dir().exists():
        shutil.rmtree(source_index_dir())


def _sanitize_item_name(name: Any) -> str:
    """
    Clean inventory labels: strip bracket tags and accidental multi-item merges.
    e.g. 'water skin [mixed] — stained coat' → 'water skin'
    """
    n = re.sub(r"\s+", " ", str(name or "").strip())
    if not n:
        return ""
    # Drop bracketed provenance/type tags
    n = re.sub(r"\[[^\]]*\]", " ", n)
    # Split accidental multi-item joins on em/en dash
    if re.search(r"[—–]", n) or " - " in n:
        parts = re.split(r"\s*[—–]\s*|\s+-\s+", n)
        parts = [re.sub(r"\s+", " ", p).strip(" .,;:") for p in parts if p and p.strip()]
        if len(parts) >= 2:
            # Prefer the first chunk if it looks like a real item phrase
            first, rest = parts[0], parts[1]
            # If first is tiny, take the longer piece
            n = first if len(first) >= 3 else rest
            # If first is a full phrase and rest is another item, keep first only
            if len(first) >= 3:
                n = first
    n = re.sub(r"\s+", " ", n).strip(" .,;:|/\\")
    # Refuse pure punctuation / empty after clean
    if len(n) < 2:
        return ""
    return n[:100]


def _default_equip_slot_for_item(name: str, item_type: str = "") -> str:
    """Map worn starter gear to a body slot code (TORSO/FEET/…)."""
    low = f"{name} {item_type}".lower()
    if any(w in low for w in ("boot", "shoe", "sandal", "greave")):
        return "FEET"
    if any(w in low for w in ("helm", "helmet", "hat", "hood", "mask", "cap")):
        return "HEAD"
    if any(w in low for w in ("coat", "cloak", "robe", "jacket", "armor", "armour", "tunic", "dress", "shirt", "vest")):
        return "TORSO"
    if any(w in low for w in ("belt", "sash", "sheath")):
        return "WAIST"
    if "glove" in low or "bracer" in low:
        return "WRIST"
    if any(w in low for w in ("ring",)):
        return "FINGER"
    if any(w in low for w in ("amulet", "necklace", "collar", "scarf")):
        return "NECK"
    return ""


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
    # Isekai / transmigrated: play begins at NEW-WORLD arrival, never previous-life workplace
    try:
        from app.setup_composer import ensure_isekai_start_location

        _sess_theme = options.get("session_theme") if isinstance(options.get("session_theme"), dict) else None
        start_location, _loc_changed = ensure_isekai_start_location(
            start_location,
            backstory_mode=str(options.get("backstory_mode") or ""),
            idea=str(options.get("_randomize_idea") or options.get("custom_style") or ""),
            world_style=str(options.get("world_style") or ""),
            genre=str((_sess_theme or {}).get("genre") or options.get("world_style") or ""),
            character_backstory=str(options.get("character_backstory") or ""),
            session_theme=_sess_theme,
        )
        start_location = norm_name(start_location or "Mosswake Gate")
    except Exception:
        pass
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
            raw_name = str(ability.get("name") or "")
            try:
                from app.llm import sanitize_ability_name

                raw_name = sanitize_ability_name(raw_name) or raw_name
            except Exception:
                pass
            name = norm_name(raw_name)
            if not name:
                continue
            # Normalize prereq placeholders ("[]"), lock policy, and desc↔cost timing splits.
            try:
                from app.llm import (
                    normalize_ability_lock_and_prerequisites,
                    repair_ability_cross_field_consistency,
                )

                cleaned = normalize_ability_lock_and_prerequisites(
                    ability,
                    origin=special_ability_origin,
                )
                cleaned = repair_ability_cross_field_consistency(cleaned)
                cleaned = normalize_ability_lock_and_prerequisites(
                    cleaned,
                    origin=special_ability_origin,
                )
            except Exception:
                cleaned = dict(ability)
            entry = {
                "name": name,
                "description": str(
                    cleaned.get("description")
                    or ability.get("description")
                    or "A rare starting ability defined by the playthrough setup."
                )[:800],
                "locked": bool(cleaned.get("locked")),
                "prerequisites": str(cleaned.get("prerequisites") or "")[:500],
                "cost": str(cleaned.get("cost") or ability.get("cost") or "")[:300],
                "growth_math": str(cleaned.get("growth_math") or ability.get("growth_math") or "")[:800],
                "power_type": str(cleaned.get("power_type") or ability.get("power_type") or "")[:40],
            }
            if isinstance(cleaned.get("resource_cost"), dict):
                entry["resource_cost"] = cleaned["resource_cost"]
            elif isinstance(ability.get("resource_cost"), dict):
                entry["resource_cost"] = ability["resource_cost"]
            special_abilities.append(entry)
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
                "growth_math": "",
            }
        )

    with connect() as conn:
        _clear_playthrough(conn)
        # Drop harness leftovers so they never ride into a live export
        _purge_test_settings(conn)
        conn.execute("INSERT INTO pacing (key, value) VALUES ('turn', '0')")
        # Calendar label from world style (short), not a full slogan
        epoch = str(world_style or "").strip().split(",")[0].strip()[:40]
        if len(epoch) < 3:
            epoch = "Common Era"
        init_world_clock(conn, day=1, minute=WORLD_DEFAULT_START_MINUTE, epoch_label=epoch)

        # Keep location summary place-like — never dump setup slogans into the map label
        style_short = str(world_style or "frontier dark fantasy").strip().split(",")[0].strip()[:80]
        loc_summary = f"Starting location for a {style_short} playthrough."
        cursor = conn.execute(
            "INSERT INTO locations (code, name, summary, visit_count) VALUES (?, ?, ?, ?)",
            (
                "L1",
                start_location,
                loc_summary[:400],
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
        try:
            from app.player_resources import seed_player_resources

            seed_player_resources(
                conn,
                options,
                player={
                    "level": 1,
                    "name": player_name,
                    "effective_stats": {},
                },
            )
        except Exception:
            pass
        _ensure_default_equipment_slots(conn)

        magic_ok = True
        stamped_batch: list[dict[str, Any]] = list(special_abilities)
        try:
            from app.llm import diversify_ability_prerequisites
            from app.player_resources import diversify_resource_costs, magic_allows_mana, stamp_abilities

            magic_ok = magic_allows_mana(str(options.get("magic_level") or ""), options)
            stamped_batch = stamp_abilities(special_abilities, magic_ok=magic_ok)
            # stamp_abilities already diversifies; re-run force if clones remain
            stamped_batch = diversify_resource_costs(stamped_batch, magic_ok=magic_ok, force=True)
            stamped_batch = diversify_ability_prerequisites(
                stamped_batch,
                force=True,
                origin=special_ability_origin,
            )
            from app.llm import assign_ability_locks_after_creation

            stamped_batch = assign_ability_locks_after_creation(
                stamped_batch,
                origin=special_ability_origin,
            )
        except Exception:
            stamped_batch = list(special_abilities)

        for ab_index, ability in enumerate(stamped_batch):
            cost_text = str(ability.get("cost") or "")[:300]
            rc = ability.get("resource_cost") if isinstance(ability.get("resource_cost"), dict) else {}
            rc_json = json.dumps(rc, ensure_ascii=True) if rc else "{}"
            power_type = str(ability.get("power_type") or "linear").strip().lower().replace("-", "_")
            if power_type not in {
                "compounding",
                "passive",
                "linear",
                "soft_cap",
                "breakthrough",
                "flat",
                "item_bound",
            }:
                power_type = "linear"
            ab_code = str(ability.get("code") or "").strip().upper() or f"AB{ab_index + 1}"
            conn.execute(
                """
                INSERT INTO abilities (
                    code, name, description, locked, power_type, base_description,
                    cost, prerequisites, growth_math, resource_cost, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ab_code[:20],
                    ability["name"],
                    ability["description"],
                    1 if ability.get("locked") else 0,
                    power_type[:40],
                    ability.get("description") or "",
                    cost_text,
                    ability.get("prerequisites") or "",
                    ability.get("growth_math") or "",
                    rc_json,
                    special_ability_origin,
                ),
            )

        # Seed starter gear only after arrival fact-check (isekai ≠ free shield).
        starter_raw = str(options.get("starter_equipment") or "").strip()
        appearance_raw = str(options.get("appearance") or "").strip()
        starter_logic_report: dict[str, Any] = {}
        try:
            from app.starter_logic import fact_check_starter_loadout

            theme = options.get("session_theme") if isinstance(options.get("session_theme"), dict) else {}
            intent_hint = {
                "isekai": bool(theme.get("isekai")),
                "genre": theme.get("genre") or options.get("world_style"),
                "portal_or_rebirth": theme.get("portal_or_rebirth") or "",
                "adapter_hint": theme.get("adapter_hint") or "",
            }
            starter_logic_report = fact_check_starter_loadout(
                starter_equipment=starter_raw,
                appearance=appearance_raw,
                backstory_mode=backstory_mode,
                memory_policy=memory_policy,
                character_backstory=character_backstory,
                intent=intent_hint,
                world_style=world_style,
                tech_level=str(options.get("tech_level") or ""),
                magic_level=str(options.get("magic_level") or ""),
                special_ability_origin=str(options.get("special_ability_origin") or ""),
                apply_fixes=True,
            )
            starter_raw = str(starter_logic_report.get("starter_equipment") or starter_raw)[:500]
            if starter_logic_report.get("appearance"):
                appearance_raw = str(starter_logic_report.get("appearance") or appearance_raw)[:400]
            # Origin/backstory may be rewritten to match world vibe (with gear).
            if starter_logic_report.get("character_backstory"):
                character_backstory = str(starter_logic_report.get("character_backstory") or character_backstory)[
                    :1600
                ]
            if starter_logic_report.get("backstory_mode"):
                backstory_mode = str(starter_logic_report.get("backstory_mode") or backstory_mode)[:60]
            if starter_logic_report.get("memory_policy"):
                memory_policy = str(starter_logic_report.get("memory_policy") or memory_policy)[:80]
        except Exception:
            starter_logic_report = {}

        starter_items: list[str] = []
        if starter_raw:
            for part in re.split(r"[,;|]+", starter_raw):
                name_item = _sanitize_item_name(part)
                if name_item and name_item.lower() not in {s.lower() for s in starter_items}:
                    starter_items.append(name_item[:100])
        for index, item_name in enumerate(starter_items[:12]):
            low = item_name.lower()
            weight = 0.4
            slot_size = 1
            item_type = "misc"
            if any(w in low for w in ("coat", "cloak", "robe", "jacket", "armor", "tunic", "dress", "clothes")):
                item_type = "clothing"
                weight = 1.2
            elif any(w in low for w in ("boot", "shoe", "sandal")):
                item_type = "clothing"
                weight = 0.8
            elif any(w in low for w in ("knife", "blade", "sword", "axe", "dagger")):
                item_type = "weapon"
                weight = 0.6
            elif any(w in low for w in ("rope", "coil")):
                item_type = "tool"
                weight = 1.5
            elif any(w in low for w in ("ration", "bread", "food")):
                item_type = "consumable"
                weight = 0.5
            elif any(w in low for w in ("water", "flask", "skin")):
                item_type = "consumable"
                weight = 0.8
            elif any(w in low for w in ("bag", "satchel", "pack", "pouch")):
                item_type = "container"
                weight = 0.5
                slot_size = 1
            # Provenance note from fact-check when available
            provenance = "setup"
            latent = False
            for row in starter_logic_report.get("kept") or []:
                if not isinstance(row, dict):
                    continue
                kept_name = _sanitize_item_name(str(row.get("name") or "")).lower()
                if kept_name == low or str(row.get("name") or "").lower() == low:
                    provenance = str(row.get("provenance") or "setup")
                    latent = bool(row.get("latent_possible"))
                    break
            # Starter kit is always mundane at Start — no free enchantments / granted powers.
            # Latent flags are DM-only metadata in starter_logic, not active item powers.
            desc = f"Starting gear ({provenance}): ordinary {item_name}."
            if latent:
                desc += " Looks mundane; no known special power at Start."
            else:
                desc += " Mundane at Start."
            code = f"I{index + 1}"
            equip_slot = _default_equip_slot_for_item(item_name, item_type) or ""
            # Only one item per exclusive body slot at start
            if equip_slot:
                taken = conn.execute(
                    "SELECT COUNT(*) AS c FROM inventory WHERE equipped_slot = ?",
                    (equip_slot,),
                ).fetchone()
                if taken and int(taken["c"] or 0) > 0:
                    equip_slot = ""
            conn.execute(
                """
                INSERT INTO inventory (
                    code, name, description, quantity, weight, slot_size, item_type, rarity,
                    enchantments, stat_modifiers, granted_abilities, stack_limit, carry_modifier,
                    container_bonus_weight, container_bonus_slots, dimensional_space, equipped_slot
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    item_name,
                    desc[:400],
                    1,
                    weight,
                    slot_size,
                    item_type,
                    "common",
                    "[]",
                    "{}",
                    "[]",
                    20,
                    1.0,
                    0.0,
                    0,
                    0,
                    equip_slot,
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
            # Same reasoning as tech_level below: "rare" is what this field
            # holds when nobody picked, and a world set up for "open magic"
            # was told it had rare magic on every turn.
            "magic_level": coherent_magic_level(options),
            "world_races": world_races or "human",
            "race_magic_enabled": bool(options.get("race_magic_enabled", False)),
            "race_magic_rarity": options.get("race_magic_rarity") or "same as world magic",
            "race_magic_rules": race_magic_rules,
            "race_ability_rules": race_ability_rules,
            "loot_rarity": loot_rarity,
            "inventory_weight_limit": inventory_weight_limit,
            "inventory_slot_limit": inventory_slot_limit,
            "inventory_rules": inventory_rules,
            "hair": str(options.get("hair") or "")[:120],
            "facial_features": str(options.get("facial_features") or "")[:300],
            "appearance": appearance_raw[:400] if appearance_raw else str(options.get("appearance") or "")[:400],
            "starter_equipment": starter_raw[:500],
            "starter_logic": {
                "arrival": (starter_logic_report.get("arrival") or {}),
                "ordinary_start": bool(starter_logic_report.get("ordinary_start")),
                "latent_candidates": list(starter_logic_report.get("latent_candidates") or [])[:12],
                "summary": str(starter_logic_report.get("summary") or "")[:300],
                "gm_brief": str(starter_logic_report.get("gm_brief") or "")[:1600],
                "show_popup": bool(starter_logic_report.get("show_popup")),
                "popup_title": str(starter_logic_report.get("popup_title") or "")[:120],
                "player_messages": list(starter_logic_report.get("player_messages") or [])[:20],
                "deferred": [
                    {
                        "name": str(d.get("name") or ""),
                        "reason": str(d.get("player_reason") or (d.get("reasons") or [""])[0] or ""),
                    }
                    for d in (starter_logic_report.get("deferred") or [])
                    if isinstance(d, dict)
                ][:12],
                "stripped": [
                    {
                        "name": str(s.get("name") or ""),
                        "reason": str(s.get("player_reason") or (s.get("reasons") or [""])[0] or ""),
                    }
                    for s in (starter_logic_report.get("stripped") or [])
                    if isinstance(s, dict)
                ][:12],
                "notes": list(starter_logic_report.get("notes") or [])[:10],
            }
            if starter_logic_report
            else {},
            # Never ship a tech level that contradicts the world the player
            # described. A far-future setup that never touched the tech dropdown
            # kept the field's "iron age" default, and the packet asserted
            # "tech_level":"iron age" beside "far-future interstellar
            # civilisation, faster-than-light travel" on every single turn.
            "tech_level": coherent_tech_level(options),
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
        # Durable session theme bias (intent composer / Randomize idea → DM+genre lean).
        raw_theme = options.get("session_theme")
        if isinstance(raw_theme, dict) and raw_theme:
            stored_options["session_theme"] = {
                "adapter_hint": str(raw_theme.get("adapter_hint") or "default")[:80],
                "genre": str(raw_theme.get("genre") or "")[:120],
                "isekai": bool(raw_theme.get("isekai")),
                "dm_stance": str(raw_theme.get("dm_stance") or "fair pressure, player agency, no chosen-one autopilot")[:240],
                "power_fantasy": raw_theme.get("power_fantasy")
                if isinstance(raw_theme.get("power_fantasy"), dict)
                else {},
                "tone": str(raw_theme.get("tone") or "")[:120],
                "edge": str(raw_theme.get("edge") or "")[:200],
                "keywords": [str(k)[:40] for k in (raw_theme.get("keywords") or []) if k][:12]
                if isinstance(raw_theme.get("keywords"), list)
                else [],
                "style_notes": str(raw_theme.get("style_notes") or "")[:400],
                "theme_model": str(raw_theme.get("theme_model") or "")[:120],
            }
        try:
            from app.skill_checks import gm_context_block, settings_from_setup

            check_settings = settings_from_setup(options)
            stored_options["skill_check_settings"] = check_settings
            stored_options["dice_checks_enabled"] = bool(check_settings.get("dice_checks_enabled"))
            # Deliberately NOT storing the skill catalog here. playthrough_options
            # ships inside every turn prompt, so a catalog stored on it was sent
            # to the model every turn forever. build_prompt_context() now attaches
            # a per-turn, action-filtered block instead.
            stored_options.pop("skill_check_context", None)
        except Exception:
            stored_options["dice_checks_enabled"] = bool(options.get("dice_checks_enabled"))
        # Optional weak skill seed (isekai / compounding / near_useless) — one seed only, not a toolkit.
        try:
            from app.setup_composer import weak_skill_seed_spec

            seed = weak_skill_seed_spec(stored_options, stored_options.get("session_theme"))
            if seed and seed.get("name"):
                conn.execute(
                    "INSERT OR IGNORE INTO player_skills (name, value, notes) VALUES (?, ?, ?)",
                    (
                        str(seed["name"])[:80],
                        int(seed.get("value") or 1),
                        str(seed.get("notes") or "")[:700],
                    ),
                )
                stored_options["weak_skill_seed"] = {
                    "name": str(seed["name"])[:80],
                    "value": int(seed.get("value") or 1),
                }
        except Exception:
            pass
        _set_setting(conn, "setup_complete", "true")
        _set_setting(conn, "playthrough_options", stored_options)
        # Location specials (heavens = blank map + movement lock; themed arrivals keep theme id)
        try:
            from app.setup_composer import apply_location_special_flags

            loc_flags = apply_location_special_flags(
                start_location,
                world_style=str(world_style or ""),
                genre=str((stored_options.get("session_theme") or {}).get("genre") or world_style or "")
                if isinstance(stored_options.get("session_theme"), dict)
                else str(world_style or ""),
                idea=str(options.get("_randomize_idea") or options.get("custom_style") or ""),
                session_theme=stored_options.get("session_theme")
                if isinstance(stored_options.get("session_theme"), dict)
                else None,
            )
            _set_setting(conn, "location_special_flags", loc_flags)
            _set_setting(conn, "movement_locked", bool(loc_flags.get("movement_locked")))
            _set_setting(conn, "map_blank", bool(loc_flags.get("map_blank")))
            if loc_flags.get("movement_locked"):
                _set_setting(conn, "travel_ready", False)
            stored_options["location_theme"] = str(loc_flags.get("theme") or "")
            stored_options["location_special_flags"] = loc_flags
            _set_setting(conn, "playthrough_options", stored_options)
        except Exception:
            _set_setting(conn, "location_special_flags", {})
            _set_setting(conn, "movement_locked", False)
            _set_setting(conn, "map_blank", False)
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (0, "setup", f"Playthrough started: {json.dumps(stored_options, ensure_ascii=True)}"),
        )
        seed_note = ""
        if isinstance(stored_options.get("weak_skill_seed"), dict):
            seed_note = (
                f" Weak skill seed already recorded: {stored_options['weak_skill_seed'].get('name')} "
                f"(value {stored_options['weak_skill_seed'].get('value')}); make it visible once in the opening if game_system allows."
            )
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (
                0,
                "system",
                "Initialization phase pending: on the first model turn, establish base play assumptions, respect immutable ability base descriptions, "
                "do not seed default player skills beyond any recorded weak skill seed, and set any model-decided ability costs or prerequisites through ability_updates."
                + seed_note,
            ),
        )
        if character_backstory:
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (0, "backstory", f"{backstory_mode}/{memory_policy}: {character_backstory}"[:1800]),
            )

    # Lived-area map intel: natives / long-lived travelers know towns & danger without
    # having walked every tile. Amnesia starts colder.
    try:
        from app.tile_world import get_map, grant_lived_area_knowledge

        m = get_map(None)
        if m:
            mode = str(backstory_mode or "").lower()
            mem = str(memory_policy or "").lower()
            amnesia = "amnesia" in mode or "hidden" in mode or "amnesia" in mem
            if not amnesia:
                age_n = 25
                try:
                    age_n = int(str(player_age).strip().split()[0])
                except (TypeError, ValueError):
                    age_n = 25
                traveler = any(
                    w in f"{character_backstory} {memory_policy}".lower()
                    for w in ("travel", "road", "merchant", "wander", "pilgrim", "caravan", "scout")
                ) or age_n >= 30
                # Reincarnated/transmigrated with known memory still recall this-life local geography
                # if they have been living here; pure isekai newcomers get less (only if native-ish).
                is_newcomer = any(
                    w in mode for w in ("isekai", "transmigrat", "truck")
                ) and "reincarnat" not in mode
                if not is_newcomer or age_n >= 28:
                    grant_lived_area_knowledge(
                        m,
                        age=age_n if not is_newcomer else max(18, age_n // 2),
                        traveler=traveler and not is_newcomer,
                        source="lived",
                    )
    except Exception:
        pass

    return _state_with_refreshed_source_index()


def _table_rows(conn, table: str) -> list[dict[str, Any]]:
    return rows_to_dicts(conn.execute(f"SELECT * FROM {table}").fetchall())


def _is_test_settings_key(key: str) -> bool:
    """Ephemeral / harness keys that must not pollute player exports or live saves."""
    k = str(key or "")
    if k.startswith("settlement_ruler:Stest"):
        return True
    if k.startswith("settlement_ruler:test"):
        return True
    if k in {"quest_stages"}:
        # Only drop pure-test quest stage bags (all keys look like tests)
        return False  # handled by value scrub below
    return False


def _scrub_settings_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter test pollution from settings for export."""
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "")
        if _is_test_settings_key(key):
            continue
        if key == "quest_stages":
            try:
                raw = json.loads(str(row.get("value") or "{}"))
            except Exception:
                raw = {}
            if isinstance(raw, dict):
                cleaned = {
                    k: v
                    for k, v in raw.items()
                    if "test" not in str(k).lower()
                    and not (isinstance(v, dict) and "test" in str(v.get("kind") or "").lower())
                }
                if not cleaned:
                    continue
                row = {**row, "value": json.dumps(cleaned, ensure_ascii=True)}
        out.append(row)
    return out


def _purge_test_settings(conn) -> None:
    """Remove harness leftovers so live playthroughs stay clean."""
    try:
        conn.execute("DELETE FROM settings WHERE key LIKE 'settlement_ruler:Stest%'")
        conn.execute("DELETE FROM settings WHERE key LIKE 'settlement_ruler:test%'")
        row = conn.execute("SELECT value FROM settings WHERE key = 'quest_stages'").fetchone()
        if row and row["value"]:
            try:
                raw = json.loads(str(row["value"]))
            except Exception:
                raw = None
            if isinstance(raw, dict):
                cleaned = {
                    k: v
                    for k, v in raw.items()
                    if "test" not in str(k).lower()
                    and not (isinstance(v, dict) and "test" in str(v.get("kind") or "").lower())
                }
                if cleaned:
                    conn.execute(
                        "UPDATE settings SET value = ? WHERE key = 'quest_stages'",
                        (json.dumps(cleaned, ensure_ascii=True),),
                    )
                else:
                    conn.execute("DELETE FROM settings WHERE key = 'quest_stages'")
    except Exception:
        pass


def export_world() -> dict[str, Any]:
    with connect() as conn:
        tables = {table: _table_rows(conn, table) for table in WORLD_TABLES}
        if "settings" in tables:
            tables["settings"] = _scrub_settings_rows(list(tables.get("settings") or []))
        return {
            "format": "ai-rpg-world-v1",
            "tables": tables,
            "history_summaries": history_summary_path().read_text(encoding="utf-8") if history_summary_path().exists() else "",
        }


def _restore_world(data: dict[str, Any]) -> None:
    # The incoming world carries its own campaign_rng_seed; drop the memoized
    # one so restored saves keep their own luck instead of inheriting the
    # seed of whatever world happened to be loaded before.
    try:
        from app.rng import reset_seed_cache

        reset_seed_cache()
    except Exception:
        pass

    tables = data.get("tables") or {}
    # Older campaign slots predate world_maps in WORLD_TABLES. Only replace maps
    # when the export explicitly includes that key (even if the list is empty).
    restore_maps = isinstance(tables, dict) and "world_maps" in tables
    with connect() as conn:
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            for table in RESTORE_ORDER:
                if table == "world_maps" and not restore_maps:
                    continue
                if table in WORLD_TABLES or table == "turn_snapshots":
                    try:
                        conn.execute(f"DELETE FROM {table}")
                    except Exception:
                        pass
            for table in WORLD_TABLES:
                if table == "world_maps" and not restore_maps:
                    continue
                rows = tables.get(table) or []
                if not rows:
                    continue
                try:
                    conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
                except Exception:
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    columns = list(row.keys())
                    if not columns:
                        continue
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
    history_summary_path().parent.mkdir(parents=True, exist_ok=True)
    history_summary_path().write_text(text, encoding="utf-8")


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
            "manifest": str(source_index_manifest()).replace("\\", "/"),
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
        "history_summaries": history_summary_path().read_text(encoding="utf-8") if history_summary_path().exists() else "",
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


# Irregular past/present forms the suffix stemmer below cannot reach.
_IRREGULAR_ACTION_STEMS = {
    "went": "go", "gone": "go", "ran": "run", "rode": "ride", "left": "leave",
    "came": "come", "flew": "fly", "swam": "swim", "fled": "flee", "drove": "drive",
    "took": "take", "gave": "give", "bought": "buy", "sold": "sell", "paid": "pay",
    "told": "tell", "said": "say", "spoke": "speak", "fought": "fight",
    "struck": "strike", "shot": "shoot", "found": "find", "saw": "see",
    "heard": "listen", "wore": "wear", "held": "hold", "drew": "draw",
    "slept": "sleep", "taught": "teach", "read": "read", "hid": "hide",
}


def _intent_tokens(player_input: str) -> set[str]:
    """
    Input tokens plus crude verb stems.

    Intent keywords are stored as bare verbs, so "keep walking east" scored zero
    for travel and fell through to `general` — which is exactly the input the
    movement contract most needs to fire on.
    """
    tokens = _tokens(player_input)
    stems = set(tokens)
    for token in tokens:
        mapped = _IRREGULAR_ACTION_STEMS.get(token)
        if mapped:
            stems.add(mapped)
        for suffix in ("ing", "ed", "es", "s"):
            if len(token) <= len(suffix) + 1 or not token.endswith(suffix):
                continue
            stem = token[: -len(suffix)]
            stems.add(stem)
            stems.add(stem + "e")  # moving -> move, riding -> ride
            if len(stem) > 2 and stem[-1] == stem[-2]:
                stems.add(stem[:-1])  # running -> run, stopping -> stop
    return stems


def travel_intent(player_input: str) -> bool:
    """
    True when the turn reads as movement, primary or secondary.

    Ties between intents are broken by keyword-table order, which puts travel
    behind conversation, combat, and investigation — so "look for the north road
    and walk there" classifies as investigation. For deciding whether a MOVE was
    expected, a secondary travel signal is enough.
    """
    primary, secondary = _turn_intent(player_input)
    return primary == "travel" or "travel" in secondary


def _turn_intent(player_input: str) -> tuple[str, list[str]]:
    kind = _turn_kind(player_input)
    if kind != "player_action":
        return kind, []
    tokens = _intent_tokens(player_input)
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


# --- movement authority ------------------------------------------------------
#
# A 30-turn 7B run emitted zero MOVE and zero LOC_NEW ops across ~10 explicit
# travel actions: prose described leaving town, the player never left the
# starting tile, and the world stayed one location wide forever. The model is
# not reliable enough to remember a state opcode it only needs occasionally, so
# movement gets the same treatment as amounts — the server states the contract
# up front and repairs the omission afterwards.

_TRAVEL_ARRIVAL_RE = re.compile(
    r"\b("
    r"arriv\w*|reach(?:es|ed|ing)?|enter(?:s|ed|ing)?|"
    r"step(?:s|ped|ping)?\s+(?:in|into|out|onto|through|past|beyond)|"
    r"cross(?:es|ed|ing)?\s+(?:into|over)|come(?:s)?\s+(?:to|upon)|came\s+(?:to|upon)|"
    r"find\s+yourself|now\s+stand\w*|leav(?:e|es|ing)\s+behind|left\s+behind|"
    r"set(?:s|ting)?\s+(?:out|off)|walk(?:s|ed|ing)?\s+(?:into|through|out|on)|"
    r"ride(?:s|ing)?\s+(?:into|through)|rode\s+(?:into|through)|"
    r"the\s+gates?\s+(?:of|close|open)|behind\s+you"
    r")\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Venues: shops and interiors you can actually be inside
# ---------------------------------------------------------------------------


def _world_minute(conn) -> int:
    return int(_float(_pacing_get(conn, "world_minute", str(WORLD_DEFAULT_START_MINUTE)), WORLD_DEFAULT_START_MINUTE))


def _location_row(conn, location_id: int):
    if not location_id:
        return None
    try:
        return conn.execute("SELECT * FROM locations WHERE id = ?", (int(location_id),)).fetchone()
    except Exception:
        return None


def venues_at(conn, parent_id: int) -> list[dict[str, Any]]:
    """Venues whose parent is this place, with their open/closed state right now."""
    if not parent_id:
        return []
    try:
        rows = conn.execute(
            "SELECT * FROM locations WHERE parent_id = ? ORDER BY id", (int(parent_id),)
        ).fetchall()
    except Exception:
        return []
    now = _world_minute(conn)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "code": str(row["code"] or ""),
                "name": str(row["name"] or ""),
                "kind": str(row["kind"] or ""),
                "open": venues.is_open(row["open_minute"], row["close_minute"], now),
                "hours": venues.hours_note(row, now),
            }
        )
    return out


def settlement_size_for(conn, row) -> str:
    """This place's settlement size, inferred and stored the first time it is asked for."""
    if row is None:
        return "village"
    stored = str(venues._field(row, "settlement_size", "") or "").strip()
    if stored:
        return stored
    # A venue inherits its parent's size: the apothecary is not its own town.
    parent_id = int(venues._field(row, "parent_id", 0) or 0)
    if parent_id:
        return settlement_size_for(conn, _location_row(conn, parent_id))
    # Deliberately does not write the inferred value back. This runs from
    # get_state, which is a read path -- persisting here opened a write inside
    # someone else's transaction and deadlocked the database. The inference is
    # deterministic, so caching it buys nothing; the column exists so a value can
    # be set explicitly and then wins over the guess.
    return venues.settlement_size_from_name(
        str(venues._field(row, "name", "") or ""), str(venues._field(row, "summary", "") or "")
    )


def venue_capacity_left(conn, parent_id: int, kind: str) -> int:
    """How many more venues of this kind this settlement can hold."""
    normalized = venues.normalize_kind(kind) or kind
    if not normalized:
        return 99
    try:
        existing = int(
            conn.execute(
                "SELECT COUNT(*) FROM locations WHERE parent_id = ? AND kind = ?",
                (int(parent_id), normalized),
            ).fetchone()[0]
        )
    except Exception:
        existing = 0
    return max(0, venues.kind_capacity(normalized) - existing)


def stamp_venue_fields(conn, location_id: int, *, parent_id: int, kind: str) -> None:
    """Record containment, kind and the kind's default opening hours."""
    normalized = venues.normalize_kind(kind) or kind
    open_minute, close_minute = venues.default_hours(normalized)
    try:
        conn.execute(
            "UPDATE locations SET parent_id = ?, kind = ?, open_minute = ?, close_minute = ? WHERE id = ?",
            (int(parent_id), normalized, int(open_minute), int(close_minute), int(location_id)),
        )
    except Exception:
        pass


def bind_venue_keeper(conn, venue_id: int) -> int:
    """Pin one NPC behind this venue's counter, so the keeper stops changing identity.

    A live probe visited "the same" apothecary three times and met Jethook, then
    "a woman with a kind face", then "a man in worn clothes" -- nobody was bound
    to the shop, so the model reinvented the keeper each visit.
    """
    row = _location_row(conn, venue_id)
    if row is None or not str(row["kind"] or ""):
        return 0
    existing = int(venues._field(row, "keeper_npc_id", 0) or 0)
    if existing and conn.execute("SELECT 1 FROM npcs WHERE id = ?", (existing,)).fetchone():
        return existing
    npc = conn.execute(
        "SELECT id FROM npcs WHERE location_id = ? AND COALESCE(shell, 0) = 0 ORDER BY id LIMIT 1",
        (int(venue_id),),
    ).fetchone()
    if npc is None:
        return 0
    conn.execute("UPDATE locations SET keeper_npc_id = ? WHERE id = ?", (int(npc["id"]), int(venue_id)))
    return int(npc["id"])


def venue_entry_check(conn, player_location_id: int, venue_row, *, world_minute: int | None = None) -> dict[str, Any]:
    """Can the player enter this venue right now, and if not, where should they go?

    Two rules, both of which a flat location table could not express:
      * You enter a venue from its parent. Standing two locations away and saying
        "back to the apothecary" used to teleport the player straight inside.
      * A venue obeys its opening hours against the world clock.
    """
    if venue_row is None:
        return {"ok": True, "reason": ""}
    kind = str(venues._field(venue_row, "kind", "") or "")
    parent_id = int(venues._field(venue_row, "parent_id", 0) or 0)
    venue_id = int(venues._field(venue_row, "id", 0) or 0)
    if not kind and not parent_id:
        return {"ok": True, "reason": ""}
    if venue_id and int(player_location_id or 0) == venue_id:
        return {"ok": True, "reason": ""}
    if parent_id and int(player_location_id or 0) != parent_id:
        return {
            "ok": False,
            "reason": "unreachable",
            "redirect_to": parent_id,
            "detail": "a venue is entered from the place it stands in",
        }
    now = _world_minute(conn) if world_minute is None else int(world_minute)
    if not venues.is_open(
        venues._field(venue_row, "open_minute", -1), venues._field(venue_row, "close_minute", -1), now
    ):
        return {
            "ok": False,
            "reason": "closed",
            "detail": venues.hours_note(venue_row, now),
        }
    return {"ok": True, "reason": ""}


def venue_plausibility(conn, parent_id: int, kind: str) -> dict[str, Any]:
    """Could a venue of this kind open here at all?

    Stops a hamlet from conjuring an apothecary the moment a player asks for one.
    """
    normalized = venues.normalize_kind(kind) or kind
    if not normalized:
        return {"ok": True, "reason": ""}
    parent = _location_row(conn, parent_id)
    size = settlement_size_for(conn, parent)
    if not venues.kind_allowed(normalized, size):
        return {
            "ok": False,
            "reason": "too_small",
            "detail": f"a {size} has no {venues.kind_label(normalized)}",
            "size": size,
        }
    if venue_capacity_left(conn, parent_id, normalized) <= 0:
        return {
            "ok": False,
            "reason": "already_served",
            "detail": f"this {size} already has as many as it supports",
            "size": size,
        }
    return {"ok": True, "reason": "", "size": size}


# Going through a door is travel, but the words that say so are too common to add
# to the keyword set: "in" and "out" turned "I put the coin in my pocket" and
# "I hand out the flyers" into travel turns. These match the phrase instead.
_VENUE_ENTER_RE = re.compile(
    r"\b(?:step|steps|stepping|walk|walks|walking|go|goes|going|head|heads|heading|duck|ducks|ducking|"
    r"slip|slips|slipping|push|pushes|pushing|enter|enters|entering|move|moves|moving|come|comes|coming)\b"
    r"[^.!?]{0,40}?\b(?:in|into|inside|through)\b",
    re.I,
)
_VENUE_EXIT_RE = re.compile(
    r"\b(?:step|steps|stepping|walk|walks|walking|go|goes|going|head|heads|heading|come|comes|coming|"
    r"back|leave|leaves|leaving|exit|exits|exiting)\b[^.!?]{0,40}?\b(?:out|outside|back out|out onto)\b",
    re.I,
)


def venue_move_intent(text: str) -> str:
    """"enter", "exit" or "" for a line that walks the player through a doorway."""
    line = str(text or "")
    if _VENUE_EXIT_RE.search(line):
        return "exit"
    if _VENUE_ENTER_RE.search(line):
        return "enter"
    return ""


def _venue_named_anywhere(conn, player_input: str, *, exclude_parent: int = 0):
    """A venue anywhere in the world that the player's line names.

    Used only for a return from somewhere else, so it prefers places already
    visited -- "that apothecary I visited earlier" means the one they know, not
    a same-trade shop in another town.
    """
    text = str(player_input or "").lower()
    if not text:
        return None
    try:
        rows = conn.execute(
            "SELECT * FROM locations WHERE parent_id != 0 AND parent_id != ? "
            "ORDER BY visit_count DESC, id",
            (int(exclude_parent or 0),),
        ).fetchall()
    except Exception:
        return None
    for row in rows:
        name = str(row["name"] or "").lower()
        if name and name in text:
            return row
    for row in rows:
        kind = str(row["kind"] or "")
        if not kind:
            continue
        label = venues.kind_label(kind).lower()
        if (label and label in text) or kind.replace("_", " ") in text:
            return row
    return None


def _mint_venue_from_request(conn, parent_id: int, player_input: str) -> str:
    """Open the kind of venue the player just asked to walk into, if it fits here.

    Only the player's own words are consulted -- letting the narration mint venues
    would put a shop wherever the prose drifted. Returns the new venue's name, or
    "" when the settlement cannot support that trade.
    """
    if not parent_id:
        return ""
    parent = _location_row(conn, parent_id)
    if parent is None:
        return ""
    text = str(player_input or "").lower()
    kind = ""
    for candidate, spec in venues.VENUE_KINDS.items():
        label = venues.kind_label(candidate).lower()
        if label and re.search(rf"\b{re.escape(label)}\b", text):
            kind = candidate
            break
    if not kind:
        kind = venues.venue_kind_from_name(text)
    if not kind:
        return ""
    if not venue_plausibility(conn, parent_id, kind)["ok"]:
        return ""
    parent_name = str(parent["name"] or "").strip()
    base = re.sub(r"\s+(square|market|green|commons|gate|row|street|lane)$", "", parent_name, flags=re.I).strip()
    name = f"{base or parent_name} {venues.kind_label(kind).title()}".strip()
    if _match_location_by_name(conn, name) is not None:
        return ""
    new_id = _upsert_location(conn, name, "", parent_id=parent_id, kind=kind)
    row = _location_row(conn, new_id)
    return str(row["name"] or "") if row is not None else ""


def _venue_named_in(conn, parent_id: int, player_input: str, narration: str):
    """A venue standing in `parent_id` that the player's line (or the prose) names.

    Matches the venue's own name first, then its kind word ("the apothecary"),
    so "I go back inside the same apothecary" resolves without the player having
    to reproduce the shop's proper name.
    """
    if not parent_id:
        return None
    try:
        rows = conn.execute(
            "SELECT * FROM locations WHERE parent_id = ? ORDER BY id", (int(parent_id),)
        ).fetchall()
    except Exception:
        return None
    if not rows:
        return None
    text = f"{player_input or ''} {str(narration or '')[-600:]}".lower()
    for row in rows:
        name = str(row["name"] or "").lower()
        if name and name in text:
            return row
    for row in rows:
        kind = str(row["kind"] or "")
        if not kind:
            continue
        label = venues.kind_label(kind).lower()
        if label and label in text:
            return row
        if kind.replace("_", " ") in text:
            return row
    return None


def _movement_rule_example(known: list[dict[str, Any]], current_name: str = "") -> str:
    """
    The "do not extend a known name" rule, worked through this world's own map.

    Hardcoding a toponym here taught it. "Riverbend Camp" sat in this rule and in
    the DSL rules, and "Redmill Ford" in the DSL MOVE line; between them they
    produced 44 of the 170 place names recorded across 42 runs and appeared in
    half of all worlds -- including a high-fantasy campaign that was set up for
    open magic and old empires and ended up at Riverbend Piers.
    """
    names = [str(entry.get("name") or "").strip() for entry in known]
    # known_places excludes where the player is standing, so turn one has none.
    # The current place is the right exemplar anyway: it is the name the model
    # is most likely to extend, which is how "Mosswake Gate Market Square"
    # happened.
    names.append(str(current_name or "").strip())
    for name in names:
        if name:
            return (
                f'if the map already holds "{name}", the next place is neither '
                f'"{name} East" nor "{name}" with its last word dropped. Either it IS '
                f"{name}, or it has a genuinely different name."
            )
    return (
        "a place is either one already in known_places, or one with a genuinely different "
        "name — never a listed name with a word added or removed."
    )


def movement_contract(state: dict[str, Any], player_input: str, intent: str) -> dict[str, Any]:
    """Server-stated travel rule for the turn packet: where the player is, and what op moves them."""
    current = state.get("current_location") or {}
    current_code = str(current.get("code") or "")
    known: list[dict[str, str]] = []
    for location in state.get("locations") or []:
        if not isinstance(location, dict):
            continue
        code = str(location.get("code") or "")
        if not code or code == current_code:
            continue
        # Interiors are listed separately under venues_here with their own rule.
        # Leaving them in known_places invited "travel" straight into a shop from
        # across the map, which is exactly what the containment rule forbids.
        if int(location.get("parent_id") or 0):
            continue
        known.append({"code": code, "name": str(location.get("name") or "")})
        if len(known) >= 10:
            break
    travel = intent == "travel" or travel_intent(player_input) or bool(venue_move_intent(player_input))
    current_name = str(current.get("name") or "")
    contract: dict[str, Any] = {
        "current_location": {"code": current_code, "name": current_name},
        "travel_intent": travel,
        # Names, not codes. Given a code list a 7B reuses the nearest listed code
        # as a stand-in for anywhere new, so the map stayed two places wide while
        # the prose wandered through ruins and river valleys that never existed.
        # move_to_location resolves by name against existing places first, so a
        # name is safe for somewhere old and correct for somewhere new.
        "known_places": [entry["name"] for entry in known if entry.get("name")],
        # The worked example uses this world's own first known place, never an
        # invented one. Two hardcoded exemplars -- "Riverbend Camp" here and in
        # the DSL rules, "Redmill Ford" in the DSL MOVE line -- accounted for 44
        # of the 170 place names across 42 recorded runs, in half of all worlds.
        # A high-fantasy world set up for "open magic and old empires" was handed
        # "Riverbend Camp" on every turn and drifted into Riverbend Piers and
        # Riverbend Village. An example named after a place that already exists
        # here costs nothing when it is copied: the move simply resolves to that
        # row instead of minting a river hamlet in someone's space opera.
        "rule": (
            "Location is state, not prose. Player ends the turn somewhere other than "
            f"{current_name or 'here'} => write that place's NAME in player.move_to_location. "
            "An existing name moves there; a new name creates it. Write the name the prose "
            "actually describes — never substitute a different known place, and never invent a "
            "location code (an unlisted code is discarded and the player does not move). "
            "A new place needs its own name, not a known one with a word bolted on and not a "
            f"known one with its qualifier stripped off: {_movement_rule_example(known, current_name)}"
        ),
    }
    # Venues here, so the model works from what exists instead of conjuring a shop.
    #
    # The rule ships even when nothing has been built yet: without it the model
    # narrated stepping into a shop and recorded no move at all, which is the
    # whole defect. An empty settlement needs to be told that going inside is a
    # move, and which kinds of place could plausibly be here.
    here_venues = [v for v in (current.get("venues_here") or []) if isinstance(v, dict)]
    settlement = str(current.get("settlement_size") or "")
    if here_venues or (settlement and not current.get("inside_venue")):
        if here_venues:
            contract["venues_here"] = [
                {"name": v.get("name"), "kind": v.get("kind"), "hours": v.get("hours")} for v in here_venues[:8]
            ]
        contract["settlement_size"] = settlement
        contract["venue_rule"] = (
            "Interiors are places, not scenery. Whenever the player goes inside a shop, inn, forge or "
            "temple, write that building's NAME in player.move_to_location — stepping through a door is "
            "a move. Use a name from venues_here when one fits; otherwise name the new building "
            f"(\"{current_name} Apothecary\", \"The Salt Crow\") and it is created here. "
            f"Interiors are entered only from {current_name or 'outside'}: a player standing anywhere "
            "else must travel here first. When the player steps back out, move them to "
            f"\"{current_name}\"."
        )
        if settlement:
            allowed = venues.plausible_kinds(settlement)
            contract["venue_kinds_possible"] = [venues.kind_label(k) for k in allowed][:18]
            contract["venue_rule"] += (
                f" This is a {settlement}; only the trades in venue_kinds_possible plausibly exist here. "
                "If the player looks for something a place this size would not have, say so in the prose "
                "instead of producing one."
            )
        shut = [str(v.get("name") or "") for v in here_venues if not v.get("open")]
        if shut:
            contract["closed_now"] = shut
            contract["venue_rule"] += (
                " Closed at this hour and cannot be entered: " + ", ".join(shut[:6]) + "."
            )
    if current.get("inside_venue"):
        contract["inside_venue"] = {
            "name": current_name,
            "kind": str(current.get("venue_kind") or ""),
            "exit_to": str(current.get("exit_to") or ""),
        }
        keeper = current.get("keeper") or {}
        if keeper.get("name"):
            contract["inside_venue"]["keeper"] = f"{keeper['name']} ({keeper.get('role') or 'keeper'})"
            contract["inside_venue"]["keeper_rule"] = (
                f"{keeper['name']} keeps this place. Do not introduce a different keeper, "
                "and do not re-describe them as a stranger."
            )
        contract["rule"] += (
            f" The player is currently INSIDE {current_name}. Leaving means writing "
            f"\"{current.get('exit_to') or 'the street outside'}\" in player.move_to_location."
        )

    # Only worth the tokens on turns that might actually move: most turns are not travel.
    if travel:
        contract["expectation"] = (
            "This input is travel. The player already decided to go; complete the journey in prose "
            "and end the scene somewhere specific. Do not end still deciding, and do not offer the "
            "trip back as a choice. Name where they end up in player.move_to_location — if the "
            "scene reaches somewhere not in known_places, invent a fitting name for it."
        )
    return contract


# --- narrative voice authority -----------------------------------------------
#
# Same 30-turn run: 22 turns opened in second person, 11 in third, and the
# player character — declared sex "unspecified" — drew 21 he/his sentences
# against 12 she/her. Both facts are server-known, so neither should be left to
# the model to remember.

_PRONOUN_SETS = {
    "female": {"subject": "she", "object": "her", "possessive": "her", "reflexive": "herself"},
    "male": {"subject": "he", "object": "him", "possessive": "his", "reflexive": "himself"},
    "neutral": {"subject": "they", "object": "them", "possessive": "their", "reflexive": "themself"},
}
_FEMALE_WORDS = frozenset({"female", "woman", "girl", "f", "fem", "feminine", "she", "her", "lady"})
_MALE_WORDS = frozenset({"male", "man", "boy", "m", "masc", "masculine", "he", "him", "his"})


def player_pronouns(sex: Any) -> dict[str, str]:
    """
    Pronoun set for the player character.

    Anything that is not clearly male or female — blank, "unspecified",
    "sexless or constructed", "varies by form" — resolves to they/them rather
    than letting the model coin-flip a gender it will then flip again next turn.
    """
    value = str(sex or "").strip().lower()
    tokens = {tok for tok in re.split(r"[^a-z]+", value) if tok}
    if tokens & _FEMALE_WORDS and not (tokens & _MALE_WORDS):
        return dict(_PRONOUN_SETS["female"])
    if tokens & _MALE_WORDS and not (tokens & _FEMALE_WORDS):
        return dict(_PRONOUN_SETS["male"])
    return dict(_PRONOUN_SETS["neutral"])


def narrative_voice_contract(state: dict[str, Any]) -> dict[str, Any]:
    """Locked narration person plus the player's pronouns, stated as server truth."""
    player = state.get("player") or {}
    options = ((state.get("settings") or {}).get("playthrough_options") or {})
    sex = player.get("sex") or options.get("player_sex") or ""
    pronouns = player_pronouns(sex)
    name = str(player.get("public_name") or player.get("name") or "").strip()
    cast = cast_pronoun_contract(state)
    return {
        "person": "second",
        "player_address": "you / your",
        "player_pronouns": pronouns,
        "player_name": name,
        # Pinned per NPC, so the cast keeps the pronouns it was introduced with.
        # Over one 100-turn run the same bargeman was "he" 41 times and "they"
        # 128 times, because nothing ever stated which was right.
        "cast_pronouns": cast,
        "cast_rule": (
            "Each named character keeps the pronouns listed in cast_pronouns for the whole "
            "scene. Do not switch between he/she and they for the same character."
            if cast
            else ""
        ),
        # Short on purpose: the full point-of-view rule lives in the system
        # prompt, which the server sends once and the runtime caches. This block
        # is per-turn packet text, so it carries only the campaign-specific facts.
        "rule": (
            "Second person for the player (\"you\")"
            + (f", never \"{name} walks\"" if name else "")
            + f". Third-person references to the player use {pronouns['subject']}/{pronouns['object']}/"
            f"{pronouns['possessive']} only, every turn."
        ),
    }


_SECOND_PERSON_RE = re.compile(r"\b(you|your|yours|yourself|yourselves)\b", re.I)
_PRONOUN_COUNT_RE = {
    "he": re.compile(r"\b(he|him|his|himself)\b", re.I),
    "she": re.compile(r"\b(she|her|hers|herself)\b", re.I),
    "they": re.compile(r"\b(they|them|their|theirs|themself|themselves)\b", re.I),
}


PRONOUN_SETS: dict[str, dict[str, str]] = {
    "he": {"subject": "he", "object": "him", "possessive": "his"},
    "she": {"subject": "she", "object": "her", "possessive": "her"},
    "they": {"subject": "they", "object": "them", "possessive": "their"},
}

_MASC_WORDS = {"he", "him", "his", "man", "men", "boy", "father", "brother", "son", "sir", "lord"}
_FEM_WORDS = {"she", "her", "hers", "woman", "women", "girl", "mother", "sister", "daughter", "lady"}


def pronoun_set_for(key: str) -> dict[str, str]:
    return dict(PRONOUN_SETS.get(str(key or "").strip().lower() or "they", PRONOUN_SETS["they"]))


def infer_npc_pronouns(name: str, narration: str, others: Sequence[str] = ()) -> str:
    """Guess an NPC's pronoun key from the sentences that name them.

    Only sentences naming exactly this NPC count. A character window picks up
    whoever else is in the paragraph, which is precisely how a bargeman ends up
    counted as "her".

    ``others`` is the rest of the known cast. Pass it whenever the roster is at
    hand: the capitalised-token heuristic below cannot see a name in the one
    position that matters most, the start of a sentence, and that is how

        "Eldrin, the fishmonger, narrows his eyes ... around Cinderrow bundle"

    pinned Cinderrow as "he" off Eldrin's three "his".
    """
    person = str(name or "").strip()
    text = str(narration or "")
    if not person or not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    low_person = person.lower()
    low_others = {
        str(o).strip().lower()
        for o in (others or ())
        if str(o).strip() and str(o).strip().lower() != low_person
    }

    def _names_someone_else(sentence: str) -> bool:
        """True when another character is named here, so its pronouns are not ours."""
        low = sentence.lower()
        if any(other in low for other in low_others):
            return True
        for match in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b", sentence):
            token = match.group(1)
            if token.lower() != low_person and token not in {"You", "Your"}:
                return True
        return False

    masc = fem = 0
    for index, sentence in enumerate(sentences):
        if low_person not in sentence.lower():
            continue
        # The sentence has to be about this NPC alone. Sharing it with another
        # named character is how a weaver introduced beside "a young boy, Liora"
        # got pinned masculine off the boy.
        if _names_someone_else(sentence):
            continue
        # The naming sentence, plus the next one when it clearly continues about
        # the same person. Prose almost never puts the pronoun in the sentence
        # that introduces the name -- "Mara counts the coins. She frowns." -- so
        # a one-sentence window pins virtually nothing.
        window = [sentence]
        nxt = sentences[index + 1] if index + 1 < len(sentences) else ""
        if nxt and low_person not in nxt.lower() and not _names_someone_else(nxt):
            window.append(nxt)
        for part in window:
            words = set(re.findall(r"[a-z]+", part.lower()))
            masc += len(words & _MASC_WORDS)
            fem += len(words & _FEM_WORDS)
    if masc and not fem:
        return "he"
    if fem and not masc:
        return "she"
    return ""


def bind_npc_pronouns(conn, narration: str, npcs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Pin each NPC's pronouns the first time the prose commits to them.

    Write-once, like ``keeper_npc_id``. Re-inferring every turn is what let one
    NPC be "he" in one scene and "they" in the next; once pinned the contract
    states it and the model stops choosing afresh.
    """
    bound: list[dict[str, Any]] = []
    rows = npcs
    if rows is None:
        try:
            rows = [dict(r) for r in conn.execute("SELECT id, name, pronouns FROM npcs")]
        except Exception:
            return bound
    roster = [
        str(r.get("name") or "").strip()
        for r in (rows or [])
        if isinstance(r, dict) and str(r.get("name") or "").strip()
    ]
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("pronouns") or "").strip():
            continue
        name = str(row.get("name") or "")
        others = [n for n in roster if n.lower() != name.strip().lower()]
        guess = infer_npc_pronouns(name, narration, others)
        if not guess:
            continue
        try:
            conn.execute("UPDATE npcs SET pronouns = ? WHERE id = ?", (guess, int(row.get("id") or 0)))
        except Exception:
            continue
        bound.append({"id": row.get("id"), "name": row.get("name"), "pronouns": guess})
    return bound


def cast_pronoun_contract(state: dict[str, Any], limit: int = 8) -> list[dict[str, Any]]:
    """Pronouns for the NPCs on stage, so the model does not re-decide each turn."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    current_id = (state.get("current_location") or {}).get("id")
    for loc in state.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        if current_id and loc.get("id") != current_id:
            continue
        for npc in loc.get("npcs") or []:
            if not isinstance(npc, dict):
                continue
            name = str(npc.get("name") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            key = str(npc.get("pronouns") or "").strip().lower() or "they"
            out.append({"name": name, "code": str(npc.get("code") or ""), **pronoun_set_for(key)})
            if len(out) >= limit:
                return out
    return out


# A line where the player commits to *producing content*: an explanation, an
# answer, an account. The narration then owes that content, the same way a
# naming demand owes a name.
_ANSWER_ACT_RE = re.compile(
    r"\bi\s+(?:explain|tell|answer|confess|admit|describe|recount|state)\b", re.I
)

# Words that carry no topic. Kept generous: a false "unanswered" verdict costs a
# wasted model pass, so the bar for flagging has to stay high.
_ANSWER_TOPIC_STOP = {
    "explain", "tell", "tells", "answer", "answers", "confess", "admit", "describe",
    "recount", "state", "says", "said", "that", "this", "them", "him", "her", "they",
    "their", "there", "here", "what", "who", "whom", "why", "how", "with", "from",
    "about", "exactly", "particular", "problem", "confusion", "honestly", "aloud",
    "someone", "person", "people", "thing", "things", "much", "when", "which",
    "before", "after", "just", "very", "also", "still", "then", "than", "into",
}


def check_answer_act(player_input: str, narration: str) -> dict[str, Any]:
    """Did a turn where the player committed to an explanation actually deliver it?

    A 100-turn probe asked the player to explain a fear of deep water. The
    narration described kneeling at a marked spot while an NPC watched, and
    never touched the subject -- it even mentioned the river without engaging.
    Same family as the naming dodge: the model writes *around* the thing it owes.

    Deliberately narrow. Only fires when the line is an explicit answer act and
    **none** of its topic words survive into the narration; a partial answer is
    left alone. Broader "did the narration respond to the action?" detection was
    tried against 100 real turns and rejected -- a category-overlap version
    flagged five turns of which at least three were plainly responsive ("You ask
    about..." for a line about listening for rumours), and firing a rewrite on
    responsive prose makes the turn worse, not better.
    """
    line = str(player_input or "")
    text = str(narration or "")
    report: dict[str, Any] = {"answer_act": False, "topics": [], "hits": [], "unanswered": False}
    if not line.strip() or not _ANSWER_ACT_RE.search(line):
        return report

    topics = [
        word
        for word in re.findall(r"[a-z]{4,}", line.lower())
        if word not in _ANSWER_TOPIC_STOP
    ]
    report["answer_act"] = True
    report["topics"] = topics[:12]
    if not topics:
        return report

    low = text.lower()
    hits = [w for w in topics if w in low or (w.endswith("s") and w[:-1] in low)]
    report["hits"] = hits[:12]
    report["unanswered"] = not hits and len(text) > 200
    return report


# Amounts spelled as words. A dodge drops the number as readily as the name, and
# "eleven silver" is the half of "who I owe, how much" that digits never cover.
_AMOUNT_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty",
    "seventy", "eighty", "ninety", "hundred", "thousand",
}

# Capitalised words that are never a proper noun worth demanding back.
_NOT_A_NAME = {
    "You", "Your", "Yours", "The", "This", "That", "These", "Those", "There",
    "Here", "They", "Them", "Their", "He", "She", "His", "Her", "It", "Its",
    "And", "But", "Nearby", "Across", "Somewhere", "Someone", "Nobody", "Then",
    "When", "While", "After", "Before", "Now", "Still", "Even", "Every", "Both",
}


def _recall_stem(word: str) -> str:
    """Plural folding only, so a question about "debts" matches a record of a "debt".

    Verb-inflection stemming ("tied" -> "tie") was tried to reach a ribbon probe
    that shares only "around/left/wrist" with its plant, and rejected: it never
    matched that pair anyway, and it pulled the one true positive's overlap from
    0.60 down to 0.50, onto the threshold. A looser metric that gains nothing and
    narrows a working margin is a straight loss.
    """
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _recall_topics(text: str) -> set[str]:
    """Topic words, stemmed, so a question about "debts" matches a record of a "debt"."""
    out: set[str] = set()
    for word in re.findall(r"[a-z]{3,}", str(text or "").lower()):
        stemmed = _recall_stem(word)
        if word in _ANSWER_TOPIC_STOP or stemmed in _ANSWER_TOPIC_STOP:
            continue
        out.add(stemmed)
    return out


def recall_specifics(text: str) -> list[str]:
    """The proper nouns and amounts in a record -- what a dodge leaves out.

    Restricted to this class on purpose. Demanding topic words back catches
    prose that answered in its own words; demanding a name or a number back
    catches only prose that never committed to one.
    """
    found: list[str] = []
    seen: set[str] = set()

    def _add(token: str) -> None:
        key = token.lower()
        if key not in seen:
            seen.add(key)
            found.append(token)

    for sentence in re.split(r"(?<=[.!?])\s+", str(text or "")):
        for match in re.finditer(r"(?<!^)\b([A-Z][a-z]{2,})\b", sentence):
            token = match.group(1)
            if token not in _NOT_A_NAME:
                _add(token)
    for match in re.finditer(r"\b(\d+)\b", str(text or "")):
        _add(match.group(1))
    for word in re.findall(r"[a-z]+", str(text or "").lower()):
        if word in _AMOUNT_WORDS:
            _add(word)
    return found[:8]


def _recall_records(state: dict[str, Any], sources: list[dict[str, Any]] | None = None) -> list[str]:
    """Durable disclosures the world has already written down.

    ``sources`` is the already-scored source_index retrieval, which reaches
    further back than the conversation window does -- the plant that failed was
    71 turns old.
    """
    out: list[str] = []
    for row in (state.get("conversations") or [])[:80]:
        if not isinstance(row, dict):
            continue
        text = f"{row.get('topic') or ''} {row.get('summary') or ''}".strip()
        if text:
            out.append(text)
    for row in (state.get("response_drafts") or [])[:40]:
        if isinstance(row, dict) and str(row.get("claim") or "").strip():
            out.append(str(row["claim"]))
    for row in (sources or [])[:24]:
        if isinstance(row, dict) and str(row.get("text") or "").strip():
            out.append(str(row["text"]))
    return out


def recall_contract(
    state: dict[str, Any],
    player_input: str,
    threshold: float = 0.5,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """What the prose owes when the player answers a question the world can already answer.

    Turn 88 of the 20260823 probe asked "who I owe, how much, and when". The
    answer -- "eleven silver to a lender called Hask" -- was in that very
    prompt six times over, and the narration still wrote only

        You answer honestly: who you owe, how much, and when.

    So this is not a retrieval problem and prompt text did not fix it. Same
    remedy as the naming dodge: state the specifics as a contract, then check.

    Scored against all 100 turns of that run it selects exactly one, the real
    failure, at every threshold from 0.3 to 0.5. Kept at 0.5 for margin.
    """
    empty = {"required": False, "specifics": [], "record": "", "overlap": 0.0}
    line = str(player_input or "")
    if not line.strip() or not _ANSWER_ACT_RE.search(line):
        return empty
    wanted = _recall_topics(line)
    if not wanted:
        return empty

    scored: list[tuple[float, str]] = []
    for text in _recall_records(state, sources):
        words = _recall_topics(text)
        if not words:
            continue
        overlap = len(wanted & words) / len(wanted)
        if overlap >= threshold:
            scored.append((overlap, text))
    scored.sort(key=lambda pair: -pair[0])

    # The best match is often the question echoed back -- the world records the
    # player's own line every turn, and it scores 1.0 against itself. Those carry
    # no name and no number, so take the best match that actually has specifics
    # rather than letting a self-echo win and report nothing.
    for overlap, text in scored[:12]:
        specifics = recall_specifics(text)
        if not specifics:
            continue
        best_text, best_overlap = text, overlap
        break
    else:
        return empty
    return {
        "required": True,
        "specifics": specifics,
        "record": best_text[:400],
        "overlap": round(best_overlap, 3),
        "rule": (
            "The player is answering a question this world already has an answer to. "
            "State these specifics in the prose; do not describe the answer being given."
        ),
    }


def check_recall_specifics(contract: dict[str, Any] | None, narration: str) -> dict[str, Any]:
    """Did the prose actually state any of the specifics it owed?

    One is enough. Demanding all of them would fire on prose that answered well
    but naturally, and a rewrite of good prose is a loss.
    """
    report = {"required": False, "specifics": [], "stated": [], "missing": False}
    if not isinstance(contract, dict) or not contract.get("required"):
        return report
    specifics = [str(s) for s in (contract.get("specifics") or []) if str(s).strip()]
    report["required"] = True
    report["specifics"] = specifics
    if not specifics:
        return report
    low = str(narration or "").lower()
    stated = [s for s in specifics if s.lower() in low]
    report["stated"] = stated
    report["missing"] = not stated and len(str(narration or "")) > 200
    return report


# Deliberately narrow verbs. "you take" is excluded: a 100-turn probe is full of
# "you take a slow breath", "you take stock", "you take the road", and an earlier
# grounding metric built on it was pure false positives. These verbs mean one
# thing. "now carry" is excluded too -- it matched "the burden you now carry"
# about the letter the player already held.
_ACQUIRE_RE = re.compile(
    r"\byou\s+(?:pick up|picks up|pocket|pockets|are handed|receive|receives)\s+"
    r"(?:the|a|an|your|its)\s+([a-z][a-z'\- ]{2,40}?)\b"
    r"(?=[,.;:]|\s+(?:and|its|it|from|with|then|as|in|on|for)\b)",
    re.I,
)

# Nouns that are never an object you can carry away.
_NOT_AN_ITEM = {
    "moment", "chance", "time", "step", "breath", "path", "road", "way", "lead",
    "risk", "turn", "look", "seat", "rest", "hint", "offer", "point", "measure",
}


def acquisition_claims(narration: str) -> list[str]:
    """Objects the prose says the player just took.

    Only claims naming a concrete object count. "You pocket it" is skipped on
    purpose: the repair has to know what to grant, and guessing the referent is
    how a scene about a dagger grants "it".
    """
    found: list[str] = []
    seen: set[str] = set()
    for match in _ACQUIRE_RE.finditer(str(narration or "")):
        name = " ".join(match.group(1).split()).strip(" -'").lower()
        if not name or name in _NOT_AN_ITEM or name in seen:
            continue
        head = name.rsplit(" ", 1)[-1]
        if head in _NOT_AN_ITEM:
            continue
        seen.add(name)
        found.append(name)
    return found[:3]


def _names_in_inventory_changes(turn: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for row in turn.get("inventory_changes") or []:
        if isinstance(row, dict) and str(row.get("name") or "").strip():
            out.add(str(row["name"]).strip().lower())
    return out


def ground_acquisitions(turn: dict[str, Any], narration: str, state: dict[str, Any]) -> list[str]:
    """Grant what the prose says the player picked up and the ops forgot.

    Same shape as the movement repair: the narration asserts a state change, the
    model emitted no op for it, and the server makes the world match the story
    rather than letting the two drift.

    Over one 100-turn run the prose said the player pocketed something on seven
    turns and emitted GRANT on one. The sign in that run was "picked up" on three
    separate turns because it never left the ground.
    """
    claimed = acquisition_claims(narration)
    if not claimed:
        return []
    have = _names_in_inventory_changes(turn)
    for row in (state or {}).get("inventory") or []:
        if isinstance(row, dict) and str(row.get("name") or "").strip():
            have.add(str(row["name"]).strip().lower())

    granted: list[str] = []
    for name in claimed:
        if any(name in existing or existing in name for existing in have):
            continue
        turn.setdefault("inventory_changes", []).append(
            {
                "name": name[:120],
                "description": "Picked up in the scene.",
                "quantity_band": "trivial",
                "weight": 1.0,
                "slot_size": 1,
                "item_type": "misc",
                "rarity": "common",
                "enchantments": [],
            }
        )
        have.add(name)
        granted.append(name)
    return granted


def check_narrative_voice(narration: str, state: dict[str, Any]) -> dict[str, Any]:
    """
    Measure point-of-view drift on a finished narration.

    ``drift`` marks the unambiguous failure — a full narration that never once
    addresses the player as "you". Pronoun counts are reported but not acted on:
    NPCs have genders too, so a raw he/she tally cannot tell a mis-gendered
    player from a correctly gendered cast, and a regex rewrite would break more
    prose than it fixed.
    """
    text = str(narration or "")
    voice = state.get("narrative_voice") if isinstance(state.get("narrative_voice"), dict) else None
    if voice is None:
        voice = narrative_voice_contract(state)
    expected = str((voice.get("player_pronouns") or {}).get("subject") or "they")
    second = len(_SECOND_PERSON_RE.findall(text))
    name = str(voice.get("player_name") or "").strip()
    name_subject = 0
    if len(name) >= 3:
        name_subject = len(
            re.findall(rf"(?<!\w){re.escape(name)}(?!\w)\s+(?:[a-z]+s|is|was|had|does|goes|has)\b", text)
        )
    return {
        "expected_person": "second",
        "expected_player_pronoun": expected,
        "second_person_refs": second,
        "player_name_as_subject": name_subject,
        "pronoun_mix": {key: len(pattern.findall(text)) for key, pattern in _PRONOUN_COUNT_RE.items()},
        "drift": bool(len(text) > 200 and second == 0),
    }


# Terrain/settlement head nouns worth minting a place from when the model
# relocated the player in prose but never named where.
_PLACE_HEAD_NOUNS = (
    "clearing", "crossroads", "crossing", "ford", "bridge", "riverbank", "bank",
    "ridge", "hollow", "gully", "ravine", "pass", "hill", "hilltop", "slope",
    "treeline", "thicket", "grove", "woods", "forest", "glade", "meadow", "field",
    "moor", "marsh", "fen", "bog", "shore", "beach", "cove", "cliff", "quarry",
    "mine", "cave", "cavern", "ruins", "ruin", "tower", "keep", "fort", "camp",
    "campsite", "village", "hamlet", "town", "settlement", "outpost", "waystation",
    "inn", "tavern", "mill", "farmstead", "barn", "chapel", "shrine", "graveyard",
    "gate", "gatehouse", "road", "track", "trail", "path", "lane", "junction",
    "market", "square", "courtyard", "hall", "cellar", "docks", "wharf", "pier",
)
# Only text introduced by a destination preposition is a candidate. "The road
# narrows" is scenery; "you step into the clearing" is an address. Without this
# anchor the extractor happily named the world after the first capitalised word
# in the paragraph, and after whichever noun the prose opened on.
_ARRIVAL_PREP = (
    r"(?:into|onto|to|toward|towards|through|past|beyond|inside|"
    r"reach(?:es|ed)?|enter(?:s|ed)?|arrive[sd]?\s+(?:at|in)|"
    r"come[s]?\s+(?:to|upon)|came\s+(?:to|upon)|step[s|ped]*\s+(?:in|into|onto|through))"
)
_ARRIVAL_PROPER_RE = re.compile(
    _ARRIVAL_PREP + r"\s+(?:the\s+)?([A-Z][a-z'’-]{2,}(?:\s+[A-Z][a-z'’-]{2,}){0,3})",
)
_ARRIVAL_HEAD_RE = re.compile(
    _ARRIVAL_PREP + r"\s+(?:the|a|an)\s+([a-z]+\s+)?(" + "|".join(_PLACE_HEAD_NOUNS) + r")\b",
    re.I,
)
_WEAK_PLACE_MODIFIERS = frozenset(
    {"same", "other", "only", "very", "quiet", "still", "next", "far", "near", "open", "empty"}
)


def _movement_destination_from_narration(
    tail: str,
    *,
    known_names: set[str],
    person_names: set[str],
    current_name: str,
) -> str:
    """
    Name the place the prose just moved the player into.

    Last resort, reached only when the model signalled travel it could not
    address (it invented a location code) and nothing already in the database
    matches. Both patterns require a destination preposition, so only text the
    prose actually presents as somewhere-you-went is eligible.

    A proper noun wins ("...into Thistledown Hollow"); failing that a terrain
    head noun becomes a plain title ("...into a clearing" -> "Clearing"). The
    second is a duller name than the model would have chosen, but the player
    does leave town.

    Matches are scanned last-first: arrival is the end of the scene.
    """
    blocked = {n.strip().lower() for n in (known_names | person_names) if n and n.strip()}
    blocked.add(current_name.strip().lower())

    def _blocked(value: str) -> bool:
        low = value.lower()
        return any(low == name or (len(name) > 3 and (low in name or name in low)) for name in blocked)

    for match in reversed(list(_ARRIVAL_PROPER_RE.finditer(tail))):
        candidate = norm_name(match.group(1))
        if not candidate or _blocked(candidate):
            continue
        if candidate.lower() in _NAME_FUNCTION_WORDS:
            continue
        if is_plausible_place_name(candidate):
            return candidate

    for match in reversed(list(_ARRIVAL_HEAD_RE.finditer(tail))):
        modifier = (match.group(1) or "").strip()
        noun = match.group(2).strip()
        if modifier.lower() in _WEAK_PLACE_MODIFIERS:
            modifier = ""
        name = norm_name(f"{modifier} {noun}".strip().title())
        if name and not _blocked(name) and is_plausible_place_name(name):
            return name
    return ""


def _movement_destination_from_input(rows: list[Any], player_input: str, current_name: str) -> Any:
    """Match a known place named in the player's own words. Exact word-boundary only — no fuzzy guessing."""
    lowered = f" {str(player_input or '').lower()} "
    best = None
    for row in rows:
        name = str(row["name"] or "").strip()
        if len(name) < 4 or name == current_name:
            continue
        if re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", lowered):
            # Longest match wins: "Mosswake Gate" beats "Mosswake"
            if best is None or len(name) > len(str(best["name"] or "")):
                best = row
    return best


def gate_venue_move(conn, from_location_id: int, to_location_id: int) -> dict[str, Any]:
    """Decide whether a move into a venue is allowed, and where it lands instead.

    Interiors are not reachable from across the map and are not open at every
    hour. A live probe walked from Riverbend Camp straight into an apothecary two
    locations away, at night, and was served by a keeper who had never existed.

      * Standing anywhere but the venue's parent -> the move is redirected to the
        parent, so the journey still happens and entering costs the next turn.
      * Closed -> the player stays put and the turn reports the hours.
    """
    to_id = int(to_location_id or 0)
    from_id = int(from_location_id or 0)
    if not to_id or to_id == from_id:
        return {"location_id": to_id or from_id, "note": None}
    row = _location_row(conn, to_id)
    if row is None:
        return {"location_id": to_id, "note": None}
    check = venue_entry_check(conn, from_id, row)
    if check.get("ok"):
        return {"location_id": to_id, "note": None}
    venue_name = str(venues._field(row, "name", "") or "")
    if check.get("reason") == "unreachable":
        parent_id = int(check.get("redirect_to") or 0)
        parent = _location_row(conn, parent_id)
        parent_name = str(venues._field(parent, "name", "") or "") if parent is not None else ""
        if parent_id and parent_id != from_id:
            return {
                "location_id": parent_id,
                "note": {
                    "kind": "venue_redirect",
                    "venue": venue_name,
                    "landed": parent_name,
                    "detail": f"{venue_name} is entered from {parent_name}; the journey ends there.",
                },
            }
        return {
            "location_id": from_id,
            "note": {
                "kind": "venue_unreachable",
                "venue": venue_name,
                "detail": f"{venue_name} cannot be reached from here.",
            },
        }
    if check.get("reason") == "closed":
        return {
            "location_id": from_id,
            "note": {
                "kind": "venue_closed",
                "venue": venue_name,
                "detail": f"{venue_name} is {check.get('detail') or 'closed'}.",
            },
        }
    return {"location_id": to_id, "note": None}


def resolve_movement(
    conn,
    result: dict[str, Any],
    player_input: str,
    *,
    intent: str,
    narration: str,
) -> dict[str, Any]:
    """
    Fill in a MOVE the model forgot, and report what happened either way.

    Only fires on travel intent, and only through evidence the model itself
    produced this turn. Three rules, most-confident first:

    1. It minted a new place this turn — on a travel turn that is where the
       player went. (Accepts the rare false positive of a place merely named in
       passing; the alternative was never moving at all.)
    2. The player's own input names a known place by its exact stored name.
    3. The narration's tail says the player arrived somewhere and tags an
       existing [[L#]] that is not the current location.

    Returns a report; ``status`` is one of ``model`` (the model did its job),
    ``not_travel``, ``repaired``, or ``unresolved``.
    """
    player_patch = result.get("player")
    if not isinstance(player_patch, dict):
        player_patch = {}
        result["player"] = player_patch

    row = conn.execute(
        """
        SELECT l.id AS id, l.code AS code, l.name AS name
        FROM player p LEFT JOIN locations l ON l.id = p.current_location_id
        WHERE p.id = 1
        """
    ).fetchone()
    current_code = str((row["code"] if row else "") or "")
    current_name = str((row["name"] if row else "") or "")

    rows = conn.execute("SELECT id, code, name FROM locations ORDER BY id").fetchall()
    known_codes = {str(row["code"] or "").upper() for row in rows if row["code"]}

    note = ""
    explicit_code = str(player_patch.get("move_to_location_code") or "").strip().upper()
    explicit_name = str(player_patch.get("move_to_location") or "").strip()
    if explicit_code:
        if explicit_code == current_code.upper():
            # "Move to where you already are" is not a move; do not burn a visit.
            player_patch["move_to_location_code"] = None
            note = "same_place_code"
        elif explicit_code not in known_codes:
            # Observed on a 7B: it wants to travel, cannot name the destination,
            # and invents the next code in sequence ("MOVE L2" with only L1 in
            # the world). _find_location_id resolves an unknown L-code back to
            # the current location, so the move silently became a no-op — the
            # model looked compliant while the world never advanced.
            player_patch["move_to_location_code"] = None
            note = "invented_code"
        else:
            report = {"status": "model", "from": current_code, "destination": explicit_code}
            # Flag, do not "fix": when the model reuses a listed code as a
            # stand-in for somewhere new, the prose and the map disagree (a live
            # run narrated a river valley while recording a move back to town).
            # There is no reliable way to recover the intended place from prose
            # that never names it, so surface it for measurement instead of
            # guessing a destination and being confidently wrong.
            dest_name = next(
                (str(row["name"] or "") for row in rows if str(row["code"] or "").upper() == explicit_code),
                "",
            )
            tail = str(narration or "")[-900:].lower()
            if dest_name and dest_name.lower() not in tail and explicit_code.lower() not in tail:
                report["prose_mismatch"] = dest_name
            return report
    if explicit_name:
        # Same-place guard for names, not just codes. A live run answered "head
        # back to that apothecary" with MOVE naming the camp the player was
        # already standing in; that counted as the model doing its job, so the
        # repair rules never ran and the player never moved.
        resolved = _match_location_by_name(conn, humanize_place_name(explicit_name))
        current_id = int((row["id"] if row is not None and "id" in row.keys() else 0) or 0)
        if resolved is not None and current_id and int(resolved["id"]) == current_id:
            player_patch["move_to_location"] = None
            note = note or "same_place_name"
        else:
            return {"status": "model", "from": current_code, "destination": explicit_name[:120]}

    # A doorway is a move the model reliably narrates and reliably fails to record.
    # Resolve it from state rather than hoping: the venues here are known, and so
    # is the way out of the one the player is standing in.
    doorway = venue_move_intent(player_input)
    if doorway:
        here_row = conn.execute(
            "SELECT l.* FROM player p JOIN locations l ON l.id = p.current_location_id WHERE p.id = 1"
        ).fetchone()
        if here_row is not None:
            here_id = int(here_row["id"])
            inside_of = int(venues._field(here_row, "parent_id", 0) or 0)
            if doorway == "exit" and inside_of:
                parent = _location_row(conn, inside_of)
                if parent is not None:
                    player_patch["move_to_location"] = str(parent["name"] or "")[:120]
                    return {
                        "status": "repaired",
                        "rule": "venue_exit",
                        "from": current_code,
                        "destination": str(parent["name"] or ""),
                    }
            if doorway == "enter":
                parent_for_venues = inside_of or here_id
                target = _venue_named_in(conn, parent_for_venues, player_input, narration)
                if target is not None and int(target["id"]) != here_id:
                    player_patch["move_to_location"] = str(target["name"] or "")[:120]
                    return {
                        "status": "repaired",
                        "rule": "venue_enter",
                        "from": current_code,
                        "destination": str(target["name"] or ""),
                    }
                # Bootstrap: the player asked to walk into a kind of shop this
                # settlement supports and none exists yet. Rules that pick an
                # existing place cannot help, and the model reliably narrates the
                # visit without recording it, so mint the venue here.
                minted = _mint_venue_from_request(conn, parent_for_venues, player_input)
                if minted:
                    player_patch["move_to_location"] = minted[:120]
                    return {
                        "status": "repaired",
                        "rule": "venue_opened",
                        "from": current_code,
                        "destination": minted,
                    }

    if intent != "travel" and not travel_intent(player_input) and not doorway:
        status = {"status": "not_travel", "from": current_code, "intent": intent}
        if note:
            status["rejected"] = note
        return status

    for location in result.get("locations") or []:
        if not isinstance(location, dict):
            continue
        name = norm_name(str(location.get("name") or ""))
        if not name or name == current_name or _is_place_or_item_code(name):
            continue
        if not is_plausible_place_name(name):
            continue
        player_patch["move_to_location"] = name[:120]
        return {"status": "repaired", "rule": "new_location", "from": current_code, "destination": name}

    named = _movement_destination_from_input(rows, player_input, current_name)
    if named is not None:
        player_patch["move_to_location_code"] = str(named["code"])
        return {
            "status": "repaired",
            "rule": "player_input",
            "from": current_code,
            "destination": str(named["name"] or ""),
        }

    # "Head back to that apothecary" from two locations away. Naming a venue is
    # not a doorway phrase -- there is no "inside" in it -- so it belongs here, on
    # the travel path. Aim at the venue and let the entry gate redirect the move
    # to its parent: the journey home happens this turn, going inside costs the
    # next one. Without this the player simply stood still.
    remote_venue = _venue_named_anywhere(conn, player_input)
    if remote_venue is not None and int(remote_venue["id"]) != _find_location_id(conn, current_code or ""):
        player_patch["move_to_location"] = str(remote_venue["name"] or "")[:120]
        return {
            "status": "repaired",
            "rule": "venue_return",
            "from": current_code,
            "destination": str(remote_venue["name"] or ""),
        }

    tail = str(narration or "")[-900:]
    arrived = bool(_TRAVEL_ARRIVAL_RE.search(tail))
    if arrived:
        by_code = {str(r["code"] or "").upper(): r for r in rows}
        for code in reversed(re.findall(r"\[\[\s*(L\d+)\s*\]\]", tail, re.I)):
            code = code.upper()
            if code != current_code.upper() and code in by_code:
                player_patch["move_to_location_code"] = code
                return {
                    "status": "repaired",
                    "rule": "narration_code",
                    "from": current_code,
                    "destination": str(by_code[code]["name"] or ""),
                }

    # Bootstrap: the model said it was travelling (by inventing a code) but the
    # world has nowhere to go yet. Rules 1-3 can only pick an existing place, so
    # without this the first journey out of the starting location can never
    # happen and the map stays one tile wide forever.
    if arrived and note == "invented_code":
        person_names = {
            str(row["name"] or "")
            for row in conn.execute("SELECT name FROM npcs").fetchall()
        }
        minted = _movement_destination_from_narration(
            tail,
            known_names={str(row["name"] or "") for row in rows},
            person_names=person_names,
            current_name=current_name,
        )
        if minted:
            player_patch["move_to_location"] = minted[:120]
            return {
                "status": "repaired",
                "rule": "narration_place",
                "from": current_code,
                "destination": minted,
            }

    report = {"status": "unresolved", "from": current_code}
    if note:
        report["rejected"] = note
    return report


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
            "magic_level": coherent_magic_level(options),
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


# Words the narrator leans on across a whole run. Single-turn frequency cannot
# see these: "hooded" appeared 63 times in 72 turns — under once a turn, so no
# per-turn threshold ever caught it, yet it is exactly what made every scene
# read the same.
_TIC_STOPWORDS = frozenset(
    {
        "with", "from", "that", "this", "have", "will", "your", "into", "when", "only",
        "more", "than", "over", "under", "through", "about", "after", "before", "they",
        "them", "their", "there", "here", "what", "where", "which", "while", "would",
        "could", "should", "been", "were", "said", "just", "like", "back", "then",
        "still", "even", "also", "some", "very", "across", "around", "toward", "towards",
        "between", "without", "another", "something", "someone", "nothing", "everything",
        "because", "though", "these", "those", "much", "many", "each", "both", "does",
        "seems", "seem", "feels", "look", "looks", "into", "onto", "upon", "away",
        "down", "under", "again", "against", "being", "want", "wants", "know", "knows",
        "make", "makes", "take", "takes", "come", "comes", "goes", "give", "gives",
        "hand", "hands", "head", "turn", "turns", "step", "steps", "walk", "walks",
    }
)


def narration_tics(conn, *, lookback: int = 14, min_rate: float = 0.45, limit: int = 10) -> list[str]:
    """
    Words the last `lookback` narrations reused often enough to be a tic.

    `min_rate` is occurrences per narration, so a word must show up in most
    scenes to qualify. Entity names are not filtered here — `anti_repetition_block`
    protects those, because it is the layer that knows the current cast.
    """
    try:
        rows = conn.execute(
            "SELECT content FROM journal WHERE kind = 'narration' ORDER BY id DESC LIMIT ?",
            (max(2, int(lookback)),),
        ).fetchall()
    except Exception:
        return []
    texts = [str(row["content"] or "") for row in rows if row and row["content"]]
    if len(texts) < 3:
        return []
    # Every name in the world, not just this turn's packet: the packet caps how
    # many NPCs it carries, so an off-screen cast member could otherwise be
    # handed to the model as a word to stop using.
    protected: set[str] = set()
    for table in ("npcs", "locations", "inventory"):
        try:
            for row in conn.execute(f"SELECT name FROM {table}").fetchall():
                for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", str(row["name"] or "")):
                    protected.add(token.lower())
        except Exception:
            continue
    try:
        prow = conn.execute("SELECT name, public_name, title FROM player WHERE id = 1").fetchone()
        for key in ("name", "public_name", "title"):
            for token in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", str((prow[key] if prow else "") or "")):
                protected.add(token.lower())
    except Exception:
        pass
    counts: dict[str, int] = {}
    for text in texts:
        for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", text):
            word = token.lower()
            if word in _TIC_STOPWORDS or word in protected:
                continue
            counts[word] = counts.get(word, 0) + 1
    threshold = max(2, int(round(min_rate * len(texts))))
    ranked = sorted(
        ((word, n) for word, n in counts.items() if n >= threshold),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return [word for word, _ in ranked[:limit]]


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


def _recent_narration_tics() -> list[str]:
    """Tic list for the turn packet; never lets a stats query break a turn."""
    try:
        with connect() as conn:
            return narration_tics(conn)
    except Exception:
        return []


def _naming_contract_for(state: dict[str, Any], player_input: str) -> dict[str, Any] | None:
    try:
        from app.naming import naming_contract

        return naming_contract(resolve_turn_naming(state, player_input))
    except Exception:
        return None


def _recall_contract_for(
    state: dict[str, Any], player_input: str, sources: list[dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    try:
        contract = recall_contract(state, player_input, sources=sources)
    except Exception:
        return None
    return contract if contract.get("required") else None


def _narration_text_of(result: dict[str, Any]) -> str:
    """The prose of a turn, wherever it happens to live.

    Model turns fill ``narration``; the deterministic fallback fills only
    ``narration_segments``. Reading one and not the other is how a repair can
    report success and change nothing the player ever sees.
    """
    text = str((result or {}).get("narration") or "").strip()
    if text:
        return text
    segments = (result or {}).get("narration_segments") or []
    parts = [
        str(seg.get("text") or "").strip()
        for seg in segments
        if isinstance(seg, dict) and str(seg.get("text") or "").strip()
    ]
    return "\n\n".join(parts).strip()


def _set_narration_text(result: dict[str, Any], text: str) -> None:
    """Write prose back to both places, so nothing downstream reads a stale copy."""
    value = str(text or "")
    result["narration"] = value
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", value) if p.strip()]
    result["narration_segments"] = [
        {"label": "paragraph", "text": para} for para in (paragraphs or [value])
    ]


def resolve_turn_naming(state: dict[str, Any], player_input: str) -> dict[str, Any]:
    """Answer a naming demand before the model writes, so the answer is fixed.

    Resolving up front means the contract the model sees and the repair applied
    afterwards agree on one name. Resolving twice would let them disagree, which
    is how "the name is X" ends up next to a paragraph naming Y.
    """
    try:
        from app.naming import resolve_name_demand

        known: list[str] = []
        for item in state.get("inventory") or []:
            if isinstance(item, dict) and item.get("name"):
                known.append(str(item["name"]))
        for loc in state.get("locations") or []:
            if not isinstance(loc, dict):
                continue
            for npc in loc.get("npcs") or []:
                if isinstance(npc, dict) and npc.get("name"):
                    known.append(str(npc["name"]))
        turn = int((state.get("pacing") or {}).get("turn") or 0)
        player_name = str((state.get("player") or {}).get("name") or "")
        with connect() as conn:
            return resolve_name_demand(
                conn, player_input, known_names=known, turn=turn, player_name=player_name
            )
    except Exception:
        return {"asked": False, "kind": "", "subject": "", "name": "", "source": ""}


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
    # Recent narration for anti-repetition (history itself is stripped from the packet).
    last_narration = ""
    for row in state.get("history") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("kind") or "") != "narration":
            continue
        last_narration = str(row.get("content") or "").strip()
        if last_narration:
            break

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
        "last_narration": last_narration,
        "turn_plan": turn_plan,
        "action_context": action_context,
        "working_set": _working_set(current_code, locations, relevant_sources),
        "event_lifecycle": event_lifecycle,
        "movement_contract": movement_contract(state, player_input, intent),
        "narrative_voice": narrative_voice_contract(state),
        "naming_contract": _naming_contract_for(state, player_input),
        "recall_contract": _recall_contract_for(state, player_input, relevant_sources),
        "overused_words": _recent_narration_tics(),
        "retrieval": {
            "method": "sequential deterministic context planner plus mechanics context, action-specific player slices, active-location scoring, and source_index JSONL search",
            "planner": TURN_CONTEXT_PLANNER_VERSION,
            "primary_intent": turn_plan["primary_intent"],
            "action_segments": turn_plan["action_segments"],
            "verification_checks": turn_plan["verification_checks"],
            "query_terms": sorted(query)[:30],
            "included_locations": [location.get("code") for location in locations],
            "source_index_manifest": str(source_index_manifest()).replace("\\", "/"),
            "source_hits": len(relevant_sources),
        },
    }
    try:
        from app.skill_checks import gm_context_block, merge_check_settings

        opts = ((state.get("settings") or {}).get("playthrough_options") or {})
        check_cfg = merge_check_settings(opts.get("skill_check_settings") if isinstance(opts.get("skill_check_settings"), dict) else opts)
        # Search the catalog for what this action needs instead of shipping all
        # ~60 skills every turn (~6.4KB / ~1600 tokens of a 7B's window).
        prompt_context["skill_check_context"] = gm_context_block(check_cfg, query=str(player_input or ""))
    except Exception:
        prompt_context["skill_check_context"] = {"dice_checks_enabled": False}
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
    rewound_turn = 0
    with connect() as conn:
        if snapshot_id is None:
            row = conn.execute("SELECT * FROM turn_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        else:
            row = conn.execute("SELECT * FROM turn_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        if row is None:
            raise ValueError("No rewind snapshot is available.")
        rewound_turn = int(row["turn"] or 0)
        snapshot = json.loads(row["snapshot"])
        if snapshot.get("format") == "ai-rpg-delta-v1":
            rows = snapshot.get("rows") or {}
            rows["__max_ids__"] = [snapshot.get("max_ids") or {}]
            conn.execute("PRAGMA foreign_keys = OFF")
            _restore_snapshot_rows(conn, rows)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA foreign_key_check")
            history_summary_path().parent.mkdir(parents=True, exist_ok=True)
            history_summary_path().write_text(str(snapshot.get("history_summaries") or ""), encoding="utf-8")
        else:
            _restore_world(snapshot)
        # Drop this snapshot and any newer ones (they are no longer valid after rewind)
        conn.execute("DELETE FROM turn_snapshots WHERE id >= ?", (row["id"],))
        # Also drop journal/summary rows that may have been written for the rewound turn
        # if max_ids restore missed them (edge cases around wait/opening).
        if rewound_turn > 0:
            conn.execute("DELETE FROM journal WHERE turn >= ?", (rewound_turn,))
            conn.execute("DELETE FROM turn_summaries WHERE turn >= ?", (rewound_turn,))
            conn.execute("DELETE FROM model_logs WHERE turn >= ?", (rewound_turn,))
            # pacing.turn should already be restored from snapshot; clamp if missing
            pace = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
            if pace is not None:
                try:
                    cur = int(pace["value"] or 0)
                except (TypeError, ValueError):
                    cur = 0
                if cur >= rewound_turn:
                    conn.execute(
                        "UPDATE pacing SET value = ? WHERE key = 'turn'",
                        (str(max(0, rewound_turn - 1)),),
                    )
    state = _state_with_refreshed_source_index()
    # UI needs last narration/input after undo (not a blank “Rewound one turn.” shell)
    state["resume"] = resume_snapshot(state)
    state["rewound"] = True
    state["rewound_turn"] = rewound_turn
    return state


def _latest_regeneration_target() -> dict[str, Any]:
    with connect() as conn:
        snapshot = conn.execute("SELECT id, turn FROM turn_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        if snapshot is None:
            raise ValueError("No turn is available to regenerate.")
        journal = conn.execute(
            """
            SELECT kind, content
            FROM journal
            WHERE turn = ? AND kind IN ('opening', 'player', 'continue', 'wait')
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
    elif input_kind == "wait":
        # Re-run wait from journal summary if possible; fall back to continue
        content = str(target.get("content") or "")
        minutes = 60
        import re as _re

        m = _re.search(r"Waited\s+(\d+)", content, _re.I)
        if m:
            minutes = int(m.group(1))
        payload = play_wait_turn(minutes)
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


def humanize_place_name(name: str) -> str:
    """
    Turn an identifier-shaped destination into a readable place name.

    A 7B given "MOVE <name>" sometimes answers with a slug rather than a name —
    a live run produced a location displayed to the player as `east_road`.
    Separators become spaces and all-lowercase names get title case, so the map
    reads "East Road". Names that already have capitals are left alone, so
    "Mosswake Gate" and "Second Shadow Inn" are untouched.
    """
    text = norm_name(str(name or ""))
    if not text:
        return text
    # Strip entity-code brackets before anything else. A live space-opera run
    # spent three of six turns at a location literally called "[[L1]]": the
    # model answered MOVE with the code wrapper instead of a name, and every
    # guard below reads the wrapper as an ordinary word. Unwrapped, "L1" hits
    # the existing code check in _find_location_id and resolves to the real row.
    unwrapped = re.fullmatch(r"[\[(<{]{1,2}\s*([^\[\]()<>{}]+?)\s*[\])>}]{1,2}", text)
    if unwrapped:
        text = norm_name(unwrapped.group(1))
    if not text:
        return text
    if re.search(r"[_]|(?<=[a-z])-(?=[a-z])", text):
        text = norm_name(re.sub(r"[_-]+", " ", text))
    if text and not any(ch.isupper() for ch in text):
        text = " ".join(word[:1].upper() + word[1:] if word else word for word in text.split(" "))
    return text


def _match_location_by_name(conn, name: str):
    """
    Find an existing place by name, tolerating case and a leading article.

    Naming is now the primary way to move ("MOVE Redmill Ford"), so "the Redmill
    Ford" and "redmill ford" must land on the existing row instead of minting a
    near-duplicate beside it.
    """
    value = humanize_place_name(name)
    if not value:
        return None
    row = conn.execute(
        "SELECT id, summary FROM locations WHERE name = ? COLLATE NOCASE", (value,)
    ).fetchone()
    if row:
        return row
    # Leading descriptors too: a live run produced both "Ruins by the River" and
    # "Old Ruins by the River" as separate map entries.
    bare = re.sub(
        r"^(?:the|a|an|old|new|great|little|lesser|greater|upper|lower|"
        r"abandoned|ruined|broken|forgotten|ancient)\s+",
        "",
        value,
        flags=re.I,
    ).strip()
    if bare and bare.lower() != value.lower():
        row = conn.execute(
            "SELECT id, summary FROM locations WHERE name = ? COLLATE NOCASE", (bare,)
        ).fetchone()
        if row:
            return row
    return conn.execute(
        "SELECT id, summary FROM locations WHERE name = ? COLLATE NOCASE OR name = ? COLLATE NOCASE",
        (f"The {value}", f"The {bare}" if bare else value),
    ).fetchone()


# Generic tail nouns a model bolts onto a name it already used. A live run
# produced Riverbend Camp, Riverbend Hillcrest, Riverbend Hillcrest Camp and
# Riverbend Hillcrest Post — four map entries for what the prose treated as one
# area, and names the player cannot tell apart.
_PLACE_TAIL_NOUNS = frozenset(
    {
        "camp", "campsite", "post", "outpost", "site", "area", "place", "spot",
        "road", "path", "trail", "track", "way", "lane", "crossing", "bend",
        "edge", "side", "end", "gate", "entrance", "approach", "outskirts",
        "grounds", "quarter", "district", "square", "yard", "clearing",
        # Bearings and storeys add no toponym. Replaying six recorded runs
        # through _upsert_location, "Hills Beyond Mosswake Gate" was still
        # followed onto the map by "Hills Beyond Mosswake Gate Eastward" --
        # the same hills, one direction word longer, as its own row.
        "north", "south", "east", "west", "northward", "southward",
        "eastward", "westward", "upper", "lower", "level", "interior",
        "annex", "beyond", "near", "nearby",
    }
)


def _place_extension_target(conn, name: str):
    """
    An existing place this name is merely an extension of.

    Only fires when an existing name is a full leading prefix and everything
    added is a generic tail noun: "Riverbend Hillcrest" + "Camp". A genuinely
    new place ("Redmill Ford" next to "Mosswake Gate") shares no prefix and is
    untouched, and a distinctive added word ("Riverbend Chapel") is kept as its
    own place because "chapel" is not in the generic list.
    """
    tokens = [t for t in re.split(r"\s+", humanize_place_name(name).lower()) if t]
    if len(tokens) < 2:
        return None
    try:
        rows = conn.execute("SELECT id, name, summary FROM locations ORDER BY id").fetchall()
    except Exception:
        return None
    best = None
    best_len = 0
    for row in rows:
        existing = [t for t in re.split(r"\s+", str(row["name"] or "").lower()) if t]
        if not existing or len(existing) >= len(tokens):
            continue
        if tokens[: len(existing)] != existing:
            continue
        extra = tokens[len(existing):]
        if len(extra) > 2 or not all(word in _PLACE_TAIL_NOUNS for word in extra):
            continue
        if len(existing) > best_len:
            best, best_len = row, len(existing)
    return best


def _place_stem_target(conn, name: str):
    """
    The one existing place a bare stem is already the name of.

    The mirror of _place_extension_target: the model drops the qualifier
    instead of adding one. Replaying recorded runs, "Riverbend" arrived after
    "Riverbend Camp" and "Mosswake" after "Mosswake Gate", and each opened a
    second row for a place the player was already standing in.

    Deliberately strict. Exactly one existing place may match, and the words it
    adds must all be generic, so a real settlement keeps its own row when the
    map holds "Riverbend Camp" AND "Riverbend Ford" -- there the stem names the
    area rather than either place, and guessing between them would teleport the
    player. The cost is the reverse case: a genuine town called "Mosswake"
    beside its own "Mosswake Gate" folds into the gate. Rows are cheap to split
    later; a player moved somewhere they did not go is not.
    """
    tokens = [t for t in re.split(r"\s+", humanize_place_name(name).lower()) if t]
    if not tokens:
        return None
    try:
        rows = conn.execute("SELECT id, name, summary FROM locations ORDER BY id").fetchall()
    except Exception:
        return None
    matches = []
    for row in rows:
        existing = [t for t in re.split(r"\s+", str(row["name"] or "").lower()) if t]
        if len(existing) <= len(tokens):
            continue
        if existing[: len(tokens)] != tokens:
            continue
        extra = existing[len(tokens):]
        if len(extra) > 2 or not all(word in _PLACE_TAIL_NOUNS for word in extra):
            continue
        matches.append(row)
    return matches[0] if len(matches) == 1 else None


_POSSESSIVE_RE = re.compile(r"['\u2019]s\b", re.I)


def _place_possessive_target(conn, name: str):
    """
    An existing place a possessive chain has wandered off the end of.

    A place name carries at most one possessive. One is an ordinary toponym --
    "Deadman's Hollow", "The Water's Edge Camp", "The Sunken Colonnade's
    Shadow". Two is the model walking further into its own noun phrase, and a
    live high-fantasy run walked all the way:

        The Sunken Colonnade
        The Sunken Colonnade's Shadow
        The Sunken Colonnade's Shadow's Heart
        The Sunken Colonnade's Shadow's Heart Passage

    Four rows for one place, and the deepest one is unsayable. The token-prefix
    guard cannot see it: "colonnade's" is not the token "colonnade", so the
    names share no prefix as far as _place_extension_target is concerned.

    Only fires when an existing place is a literal prefix of the new name, so a
    world that genuinely opens on "The Lord's Keeper's Tower" keeps it -- there
    is nothing to fold into, and refusing a name outright is not this
    function's job.
    """
    value = humanize_place_name(name)
    if len(_POSSESSIVE_RE.findall(value)) < 2:
        return None
    try:
        rows = conn.execute("SELECT id, name, summary FROM locations ORDER BY id").fetchall()
    except Exception:
        return None
    low = value.lower()
    best = None
    best_len = 0
    for row in rows:
        existing = str(row["name"] or "").strip()
        if not existing or len(existing) >= len(value):
            continue
        if not low.startswith(existing.lower()):
            continue
        if len(existing) > best_len:
            best, best_len = row, len(existing)
    return best


def _venue_parent_for_new_place(conn, kind: str) -> int:
    """Which place a newly named venue belongs to: where the player is standing.

    Venues do not nest -- if the player is already inside a shop, a second shop
    named this turn belongs to the street outside, not to the shop.
    """
    if not kind:
        return 0
    try:
        player = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
    except Exception:
        return 0
    here_id = int((player["current_location_id"] if player else 0) or 0)
    here = _location_row(conn, here_id)
    if here is None:
        return 0
    parent_of_here = int(venues._field(here, "parent_id", 0) or 0)
    return parent_of_here or here_id


def _upsert_location(conn, name: str, summary: str = "", *, parent_id: int | None = None, kind: str | None = None) -> int:
    name = humanize_place_name(name)
    if not name:
        raise ValueError("Location name is required.")
    # Refuse event/system sentence fragments as place names (e.g. "System pings a local job")
    if not is_plausible_place_name(name):
        # Prefer the player's current place rather than inventing a garbage toponym
        try:
            player = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
            if player and player["current_location_id"]:
                return int(player["current_location_id"])
        except Exception:
            pass
        name = "Nearby street"
    existing = _match_location_by_name(conn, name)
    if existing is None:
        existing = (
            _place_extension_target(conn, name)
            or _place_stem_target(conn, name)
            or _place_possessive_target(conn, name)
        )
    if existing:
        if summary and summary not in existing["summary"]:
            # Don't merge wall-of-setup-text into a place summary
            short = summary[:1400]
            if len(short) > 400 and ("playthrough" in short.lower() or "power fantasy" in short.lower()):
                short = ""
            if short:
                merged = f"{existing['summary']} {short}".strip()[:1400]
                conn.execute("UPDATE locations SET summary = ? WHERE id = ?", (merged, existing["id"]))
        return int(existing["id"])
    # A place whose name says "apothecary" is an interior, not a second town.
    resolved_kind = venues.venue_kind_from_name(name) if kind is None else (kind or "")
    resolved_parent = 0
    if resolved_kind:
        resolved_parent = (
            _venue_parent_for_new_place(conn, resolved_kind) if parent_id is None else int(parent_id or 0)
        )
        if resolved_parent and not venue_plausibility(conn, resolved_parent, resolved_kind)["ok"]:
            # A hamlet has no apothecary. Asking for one used to conjure it; now
            # the player simply stays where they are and finds no such place.
            return resolved_parent

    cursor = conn.execute(
        "INSERT INTO locations (code, name, summary, visit_count) VALUES (?, ?, ?, 0)",
        (_next_code(conn, "locations", "L"), name, summary[:1400] if len(summary or "") < 500 else summary[:200]),
    )
    new_id = int(cursor.lastrowid)
    if resolved_kind and resolved_parent and resolved_parent != new_id:
        stamp_venue_fields(conn, new_id, parent_id=resolved_parent, kind=resolved_kind)
    return new_id


def _find_location_id(conn, name_or_code: str | None) -> int:
    if name_or_code:
        # Slugs must resolve to the same row as their readable form, or
        # "east_road" and "East Road" become two locations.
        value = humanize_place_name(str(name_or_code))
        value = _alias_target(conn, value, "location") or value
        row = conn.execute("SELECT id FROM locations WHERE code = ?", (value.upper(),)).fetchone()
        if row:
            return int(row["id"])
        row = _match_location_by_name(conn, value)
        if row:
            return int(row["id"])
        # Codes like L1 should not invent a place named "L1" if already current
        if re.fullmatch(r"L\d+", value, flags=re.I):
            player = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
            if player and player["current_location_id"]:
                return int(player["current_location_id"])
        # Never mint a location from an event blurb masquerading as a place name
        if not is_plausible_place_name(value):
            player = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
            if player and player["current_location_id"]:
                return int(player["current_location_id"])
            value = "Nearby street"
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


# Map / terrain kinds must never become NPC job roles (LLM often copies landmark state).
_MAP_KIND_AS_ROLE: dict[str, str] = {
    "gate": "gatekeeper",
    "jump gate": "gatekeeper",
    "jumpgate": "gatekeeper",
    "road": "traveler",
    "bridge": "traveler",
    "ruins": "scavenger",
    "dungeon": "delver",
    "monolith": "local",
    "waterfall": "local",
    "city": "resident",
    "town": "resident",
    "village": "villager",
    "station": "crew",
    "harbor": "dockhand",
    "shipyard": "shipwright",
    "colony": "colonist",
    "wreck": "scavenger",
    "anomaly": "local",
    "forest": "local",
    "mountain": "local",
    "hill": "local",
    "plains": "local",
    "water": "local",
    "void": "local",
    "lava": "local",
    "cliff": "local",
    "desert": "local",
    "swamp": "local",
    "beach": "local",
    "farm": "farmer",
    "asteroid": "local",
    "nebula": "local",
    "cavern": "local",
    "crystal": "local",
    "volcano": "local",
    "mushroom": "local",
    "tundra": "local",
    "mesa": "local",
    "ash": "local",
    "ice": "local",
    "landmark": "local",
    "settlement": "resident",
    "terrain": "local",
    "tile": "local",
    "npc": "local",
    "event": "local",
    "location": "local",
}


def _sanitize_npc_role(role: Any) -> str:
    """Keep role as a job/social identity; never a map landmark kind."""
    text = str(role or "").strip()
    if not text:
        return "local"
    key = re.sub(r"\s+", " ", text.lower())
    if key in _MAP_KIND_AS_ROLE:
        return _MAP_KIND_AS_ROLE[key]
    # Bare single-token map kinds only (allow "gate guard", "road warden", etc.)
    first = key.split(" ", 1)[0]
    if " " not in key and first in _MAP_KIND_AS_ROLE:
        return _MAP_KIND_AS_ROLE[first]
    return text[:100]


def _upsert_npc(conn, npc: dict[str, Any]) -> int | None:
    if not isinstance(npc, dict):
        return None
    # Places/items misfiled as NPCs (code L1 + inn name) — skip entirely
    if _looks_like_misfiled_location(npc):
        return None
    name = norm_name(str(npc.get("name", "")))
    code = norm_name(str(npc.get("code", "")))
    # Never look up / treat location or item codes as NPC codes
    if _is_place_or_item_code(code) or re.fullmatch(r"I\d+|E\d+", code, re.I):
        code = ""
    if _is_place_or_item_code(name):
        name = ""
    if not name and code:
        # Only alpha NPC codes can resolve an existing face without a name
        if not re.fullmatch(r"[A-Za-z]{1,3}", code):
            return None
        existing = conn.execute("SELECT id FROM npcs WHERE code = ?", (code,)).fetchone()
        return int(existing["id"]) if existing else None
    if not name:
        return None
    # Event titles / system job lines must not become people ("System pings a local job")
    if not is_plausible_person_name(name):
        name = unique_person_name(conn, name_seed(code, name, npc.get("role") or ""))
        npc["name"] = name

    # Prefer named place; if model stuffed location_code=L1, resolve that place — do not invent a person from L1
    loc_ref = npc.get("location") or npc.get("location_code") or npc.get("place")
    if _is_place_or_item_code(str(loc_ref or "")):
        # Keep L1 as a place ref (good) — _find_location_id handles L#
        pass
    location_id = _find_location_id(conn, loc_ref)
    race = str(npc.get("race") or npc.get("species") or "human")[:80]
    role = _sanitize_npc_role(npc.get("role") or "local")
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
    if existing is None:
        # Same name elsewhere is the same person, not a twin. The lookup used to
        # be per-location, so a live run ended with two NPCs both called "Aria",
        # both bakers, in different places. People also legitimately travel, so
        # matching by name world-wide and moving them is the right reading.
        existing = conn.execute(
            "SELECT * FROM npcs WHERE name = ? COLLATE NOCASE LIMIT 1", (name,)
        ).fetchone()
        if existing is not None and int(existing["location_id"] or 0) != int(location_id or 0):
            try:
                conn.execute(
                    "UPDATE npcs SET location_id = ? WHERE id = ?",
                    (int(location_id), int(existing["id"])),
                )
            except Exception:
                pass

    if existing:
        # Shell / nameless / background: refuse full-cast promotion from LLM dumps
        try:
            existing_presence = str(existing["presence"] if "presence" in existing.keys() else "full")
            existing_shell = int(existing["shell"] if "shell" in existing.keys() else 0)
        except Exception:
            existing_presence = "full"
            existing_shell = 0
        is_shell = existing_shell == 1 or existing_presence in {"nameless", "background"}
        if is_shell:
            # Only attitude / short summary / trust_delta — no stat blocks or deep lore
            short_sum = summary[:200] if summary else ""
            facts = _json(existing["known_facts"] or "[]", [])
            trust = int(existing["trust"] or 0) + trust_delta
            conn.execute(
                """
                UPDATE npcs
                SET attitude = COALESCE(NULLIF(?, ''), attitude),
                    summary = CASE WHEN ? != '' AND instr(summary, ?) = 0
                        THEN substr(trim(summary || ' ' || ?), 1, 400) ELSE summary END,
                    trust = ?,
                    known_facts = ?
                WHERE id = ?
                """,
                (
                    attitude if attitude != "neutral" else "",
                    short_sum,
                    short_sum[:40] if short_sum else "",
                    short_sum,
                    max(-100, min(100, trust)),
                    json.dumps(facts),
                    int(existing["id"]),
                ),
            )
            return int(existing["id"])
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

    new_code = _next_alpha_code(conn, "npcs")
    facts = [known_fact[:350]] if known_fact else []
    # New faces: honor shell/presence; demote crowd extras and apex ranks until earned.
    presence = str(npc.get("presence") or "").strip().lower()
    if presence not in {"full", "event_worthy", "nameless", "background", ""}:
        presence = "full"
    role_l = role.lower()
    shell = 1 if (
        bool(npc.get("shell"))
        or presence in {"nameless", "background"}
        or any(x in role_l for x in ("passerby", "bystander", "crowd", "extra", "faceless"))
    ) else 0
    if shell:
        presence = presence if presence in {"nameless", "background"} else "nameless"
        # Thin shells — no full cast dump
        personality = ""
        likes = ""
        principles = ""
        dislikes = ""
        stat_profile = {}
        skill_profile = {}
        summary = (summary or "A brief face in the crowd.")[:200]
        rank = "F"
    else:
        presence = presence or "full"
        # Brand-new NPCs cannot spawn as S/SS/SSS (model apex inflation)
        if str(rank).upper() in {"S", "SS", "SSS"}:
            rank = "C"
    power_rank = clamp(int(_float(npc.get("power_rank"), 0 if shell else 10)), 0, 100)
    if shell:
        power_rank = min(power_rank, 15)
    portrait_eligible = 0 if shell else 1
    cursor = conn.execute(
        """
        INSERT INTO npcs (
            code, location_id, name, race, role, summary, attitude, personality, likes, principles, dislikes,
            rank, stat_profile, skill_profile, trust, known_facts, mentioned_by,
            presence, power_rank, portrait_eligible, shell
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            presence or "full",
            power_rank,
            portrait_eligible,
            shell,
        ),
    )
    return int(cursor.lastrowid)


def _filter_inventory_changes(
    conn,
    changes: list[dict[str, Any]],
    *,
    narration: str = "",
    player_input: str = "",
    input_kind: str = "player",
) -> list[dict[str, Any]]:
    """
    Drop positive inventory gains that invent items not already owned and not
    mentioned in narration/input. Losses and updates to existing stacks always ok.

    Server authority: the model cannot self-authorize gains via justified/source
    flags alone — prose or clear player acquisition intent is required.
    """
    if not isinstance(changes, list):
        return []
    text = f"{narration}\n{player_input}".lower()
    player_l = str(player_input or "").lower()
    acquire_intent = bool(
        re.search(
            r"\b(buy|bought|purchase|loot|pick(?:ed)?\s+up|take|took|steal|stole|"
            r"craft|forage|find|found|receive|received|accept|gift|reward|claim|trade)\b",
            player_l,
        )
    )
    kept: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        name = _sanitize_item_name(str(change.get("name", "")))
        if not name:
            continue
        change = dict(change)
        change["name"] = name
        try:
            delta = int(change.get("quantity_delta") or 0)
        except (TypeError, ValueError):
            delta = 0
        # Cap absurd single-turn minting even when grounded
        if delta > 99:
            change["quantity_delta"] = 99
            delta = 99
        existing = conn.execute("SELECT id, quantity FROM inventory WHERE name = ?", (name,)).fetchone()
        # Removals / metadata-only always allowed
        if delta <= 0 or existing:
            # Strip dimensional_space promotions on existing items unless already set or named in prose
            if existing and bool(change.get("dimensional_space")):
                try:
                    row = conn.execute(
                        "SELECT dimensional_space FROM inventory WHERE id = ?",
                        (int(existing["id"]),),
                    ).fetchone()
                    already = int(row["dimensional_space"] or 0) if row else 0
                except Exception:
                    already = 0
                if not already and "dimensional" not in text and "bag of holding" not in text:
                    change = dict(change)
                    change["dimensional_space"] = False
            kept.append(change)
            continue
        # New item gain: require prose grounding. Model flags alone never suffice.
        name_l = name.lower()
        tokens = [tok for tok in re.findall(r"[a-z0-9']{4,}", name_l)]
        token_hits = sum(1 for tok in tokens if tok in text)
        token_ok = bool(tokens) and token_hits >= max(1, (len(tokens) + 1) // 2)
        name_in_text = name_l in text
        # Source tags only count when the player clearly tried to acquire something
        # and at least one distinctive token appears in prose (blocks free "loot" mint).
        source = str(change.get("source") or change.get("reason") or "").lower()
        source_tag = any(
            s in source for s in ("loot", "purchase", "craft", "gift", "quest", "reward", "found", "trade")
        )
        source_ok = acquire_intent and source_tag and (name_in_text or token_ok)
        grounded = name_in_text or token_ok or source_ok
        # Never honor bare justified/true from the model
        # Opening: only trust what was already set up (no free combat kit)
        if input_kind == "opening" and not existing:
            grounded = False
        # New items cannot start as dimensional storage without explicit prose
        if grounded and bool(change.get("dimensional_space")):
            if "dimensional" not in text and "bag of holding" not in text and "void bag" not in text:
                change = dict(change)
                change["dimensional_space"] = False
        if grounded:
            kept.append(change)
        else:
            try:
                conn.execute(
                    "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                    (
                        _turn_value(conn),
                        "inventory_reject",
                        f"Rejected invented gain: {name} x{delta}"[:900],
                    ),
                )
            except Exception:
                pass
    return kept


# Which check an item type shifts when nothing explicit is declared. This is
# how a plain "Iron Sword" from the model still ends up affecting melee rolls
# without the model ever being asked to reason about modifiers.
_ITEM_TYPE_ROLL_SKILL: dict[str, str] = {
    "weapon": "melee",
    "sword": "melee",
    "blade": "melee",
    "axe": "melee",
    "spear": "melee",
    "club": "melee",
    "bow": "ranged",
    "crossbow": "ranged",
    "gun": "ranged",
    "firearm": "ranged",
    "rifle": "ranged",
    "thrown": "ranged",
    "armor": "defense",
    "shield": "defense",
    "helm": "defense",
    "tool": "craft",
    "tools": "craft",
    "lockpick": "lockpicking",
    "lockpicks": "lockpicking",
    "medical": "medicine",
    "instrument": "performance",
    "map": "navigation",
    "compass": "navigation",
    "cloak": "stealth",
    "disguise": "disguise",
}

_RARITY_ROLL_BONUS: dict[str, int] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
    "unique": 4,
    "mythic": 5,
}


def _roll_skill_for_item(name: str, item_type: str) -> str:
    """Best-guess skill an item helps with, from its type then its name."""
    text = f"{item_type} {name}".lower()
    for keyword, skill in _ITEM_TYPE_ROLL_SKILL.items():
        if re.search(rf"\b{re.escape(keyword)}", text):
            return skill
    return ""


def _derive_item_links(
    conn,
    *,
    name: str,
    item_type: str,
    rarity: str,
    stat_modifiers: dict[str, Any],
    granted_abilities: list[dict[str, Any]],
    change: dict[str, Any],
) -> tuple[dict[str, int], list[str], dict[str, int]]:
    """
    Turn the model's free-text item description into machine-usable links.

    Returns ``(stat_links, power_codes, roll_profile)``:

    * **stat_links** — ``stat_modifiers`` collapsed onto the six canonical
      attribute keys, so "Might +2" and "strength: 2" mean the same thing.
    * **power_codes** — codes of powers this item grants, resolved against
      installed content packs and existing ability rows. Inline
      ``granted_abilities`` keep working unchanged; this only adds a reference
      when a real power already exists to point at.
    * **roll_profile** — flat check modifiers. Taken from the change when
      declared, otherwise derived from item type, rarity and stat links, so
      gear affects dice without the narrator doing arithmetic.
    """
    try:
        from app.content_packs import active_powers, normalize_stat_key
    except Exception:  # pragma: no cover - packs are optional
        active_powers, normalize_stat_key = (lambda: {}), (lambda v: str(v or "").strip().lower())

    stat_links: dict[str, int] = {}
    for key, value in (stat_modifiers or {}).items():
        canon = normalize_stat_key(key)
        if not canon:
            continue
        try:
            stat_links[canon] = stat_links.get(canon, 0) + int(_float(value, 0))
        except (TypeError, ValueError):
            continue

    # --- powers this item points at ------------------------------------------
    power_codes: list[str] = []
    declared = change.get("power_codes") or change.get("ability_codes") or []
    if isinstance(declared, str):
        declared = [p.strip() for p in declared.split(",") if p.strip()]
    pack_powers = active_powers()
    by_name = {str(p.get("name") or "").strip().lower(): code for code, p in pack_powers.items()}

    for ref in declared or []:
        ref = str(ref).strip()
        if ref and (ref in pack_powers or ref.lower() in by_name):
            power_codes.append(ref if ref in pack_powers else by_name[ref.lower()])

    for ability in granted_abilities or []:
        if not isinstance(ability, dict):
            continue
        label = str(ability.get("name") or "").strip()
        if not label:
            continue
        code = ability.get("code") or by_name.get(label.lower())
        if not code:
            row = conn.execute(
                "SELECT code FROM abilities WHERE lower(name) = ?", (label.lower(),)
            ).fetchone()
            code = row["code"] if row else None
        if code and str(code) not in power_codes:
            power_codes.append(str(code))

    # --- how this item shifts dice -------------------------------------------
    roll_profile: dict[str, int] = {}
    declared_profile = change.get("roll_profile")
    if isinstance(declared_profile, dict):
        for key, value in declared_profile.items():
            skill = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if not skill:
                continue
            try:
                roll_profile[skill] = max(-12, min(12, int(_float(value, 0))))
            except (TypeError, ValueError):
                continue

    if not roll_profile:
        skill = _roll_skill_for_item(name, item_type)
        if skill:
            bonus = _RARITY_ROLL_BONUS.get(str(rarity or "common").strip().lower(), 0)
            # A relevant attribute bonus also shows up at the tip of the tool.
            bonus += min(2, sum(max(0, v) for v in stat_links.values()) // 2)
            if bonus:
                roll_profile[skill] = max(-12, min(12, bonus))

    return stat_links, power_codes[:12], roll_profile


def _apply_inventory(conn, changes: list[dict[str, Any]]) -> None:
    for change in changes:
        name = _sanitize_item_name(str(change.get("name", "")))
        if not name:
            continue
        change = {**change, "name": name}
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
        stat_links, power_codes, roll_profile = _derive_item_links(
            conn,
            name=name,
            item_type=item_type,
            rarity=rarity,
            stat_modifiers=stat_modifiers,
            granted_abilities=granted_abilities,
            change=change,
        )
        has_links = bool(has_stat_modifiers or has_granted_abilities or change.get("roll_profile") or change.get("power_codes"))
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
                    dimensional_space = CASE WHEN ? THEN MAX(dimensional_space, ?) ELSE dimensional_space END,
                    stat_links = CASE WHEN ? THEN ? ELSE stat_links END,
                    power_codes = CASE WHEN ? THEN ? ELSE power_codes END,
                    roll_profile = CASE WHEN ? THEN ? ELSE roll_profile END
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
                    int(has_links),
                    json.dumps(stat_links, ensure_ascii=True),
                    int(has_links),
                    json.dumps(power_codes, ensure_ascii=True),
                    int(has_links),
                    json.dumps(roll_profile, ensure_ascii=True),
                    existing["id"],
                ),
            )
            if quantity <= 0:
                conn.execute("UPDATE inventory SET equipped_slot = '' WHERE id = ?", (existing["id"],))
        elif delta > 0:
            conn.execute(
                """
                INSERT INTO inventory (code, name, description, quantity, weight, slot_size, item_type, rarity, enchantments, stat_modifiers, granted_abilities, stack_limit, carry_modifier, container_bonus_weight, container_bonus_slots, dimensional_space, stat_links, power_codes, roll_profile)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(stat_links, ensure_ascii=True),
                    json.dumps(power_codes, ensure_ascii=True),
                    json.dumps(roll_profile, ensure_ascii=True),
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
    if not isinstance(modifiers, list):
        return
    # Cap model spam / infinite storage exploits per turn
    for modifier in modifiers[:8]:
        if not isinstance(modifier, dict):
            continue
        source = norm_name(str(modifier.get("source") or modifier.get("name") or "Capacity Effect"))
        if not source:
            continue
        code = norm_name(str(modifier.get("code") or _slot_code_from_name(source))).upper()
        active = 0 if modifier.get("active") is False or str(modifier.get("action") or "").lower() in {"remove", "inactive", "end"} else 1
        notes = str(modifier.get("notes") or "")[:700]
        blob = f"{source} {notes}".lower()
        # Dimensional storage only when fiction explicitly names it (not free model flag)
        want_dim = bool(modifier.get("dimensional_space"))
        dim_ok = want_dim and any(
            k in blob for k in ("dimensional", "bag of holding", "void bag", "extradimensional", "portable hole")
        )
        weight_bonus = max(0.0, min(200.0, _float(modifier.get("weight_bonus"), 0.0)))
        slot_bonus = max(0, min(40, int(_float(modifier.get("slot_bonus"), 0))))
        if dim_ok:
            # Still cap extreme bonuses even for legitimate dimensional effects
            weight_bonus = min(weight_bonus, 500.0)
            slot_bonus = min(slot_bonus, 200)
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
                weight_bonus,
                slot_bonus,
                max(0.05, min(5.0, _float(modifier.get("carry_modifier"), 1.0))),
                1 if dim_ok else 0,
                active,
                notes,
            ),
        )


def _apply_skills(conn, changes: list[dict[str, Any]]) -> None:
    settings = _settings(conn).get("playthrough_options", {})
    speed = settings.get("skill_growth_speed") or "normal"
    multiplier = settings.get("skill_growth_multiplier")
    if not isinstance(changes, list):
        return
    for change in changes[:12]:
        name = norm_name(str(change.get("name", ""))).lower()
        if not name:
            continue
        raw_delta = clamp(int(change.get("delta") or 0), -5, 8)
        delta = _scaled_delta(raw_delta, str(speed), float(multiplier) if multiplier else None)
        delta = clamp(int(delta), -5, 12)
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
            # New skills start modest — no free rank-100 mint
            conn.execute(
                "INSERT INTO player_skills (name, value, notes) VALUES (?, ?, ?)",
                (name, clamp(delta if delta > 0 else 1, 1, 15), notes),
            )


def _apply_player(conn, player_patch: dict[str, Any]) -> None:
    player = conn.execute("SELECT * FROM player WHERE id = 1").fetchone()
    if not player:
        return

    settings = _settings(conn).get("playthrough_options", {})
    # Per-turn caps: stop model minting (economy / progression). Totals still hard-capped below.
    max_health = clamp(int(player["max_health"]) + clamp(int(player_patch.get("max_health_delta") or 0), -50, 20), 1, 999)
    health = clamp(int(player["health"]) + clamp(int(player_patch.get("health_delta") or 0), -200, 100), 0, max_health)
    level_delta = (
        clamp(int(player_patch.get("level_delta") or 0), 0, 1)
        if settings.get("leveling_system", True)
        else 0
    )
    xp_delta = (
        _scaled_delta(
            clamp(int(player_patch.get("xp_delta") or 0), 0, 500),
            str(settings.get("xp_growth_speed") or "normal"),
            float(settings.get("xp_growth_multiplier")) if settings.get("xp_growth_multiplier") else None,
        )
        if settings.get("leveling_system", True)
        else 0
    )
    level = clamp(int(player["level"]) + level_delta, 1, 100)
    xp = clamp(int(player["xp"]) + xp_delta, 0, 1_000_000)
    gold_delta = clamp(int(player_patch.get("gold_delta") or 0), -50_000, 5_000)
    gold = clamp(int(player["gold"]) + gold_delta, 0, 1_000_000)
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
    venue_note: dict[str, Any] | None = None
    if move_to:
        location_id = _find_location_id(conn, str(move_to))
        gate = gate_venue_move(conn, previous_location_id, location_id)
        location_id = int(gate["location_id"] or previous_location_id)
        venue_note = gate.get("note")
        if location_id != previous_location_id:
            _settle_departed_location_events(conn, previous_location_id, turn)
            conn.execute("UPDATE locations SET visit_count = visit_count + 1 WHERE id = ?", (location_id,))
            _refresh_arrived_location_events(conn, location_id, turn)
    if venue_note:
        conn.execute(
            "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
            (turn, venue_note["kind"], str(venue_note.get("detail") or "")[:900]),
        )

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
    """Model-authored hidden notes only — never force/due bus rows (server queues those)."""
    if not isinstance(gm_events, list):
        return
    applied = 0
    for event in gm_events:
        if applied >= 6:
            break
        if not isinstance(event, dict):
            continue
        summary = str(event.get("summary") or event.get("secret") or event.get("plan") or "").strip()[:1400]
        trigger = str(event.get("trigger") or event.get("condition") or event.get("when") or "").strip()[:900]
        if not summary and not trigger:
            continue
        status = str(event.get("status") or "pending").strip().lower()[:40]
        if status not in {"pending", "seeded", "active", "resolved", "suppressed"}:
            status = "pending"
        # Model cannot mint force/immutable bus events through this path
        if status == "active":
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
            INSERT INTO gm_events (turn, trigger, summary, status, priority, location_id, npc_id, event_id, kind, due_turn, force, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, '{}')
            """,
            (turn, trigger, summary, status, priority, location_id, npc_id, visible_event_id),
        )
        applied += 1


def _apply_conversations(conn, conversations: list[dict[str, Any]], turn: int) -> None:
    for convo in conversations:
        summary = str(convo.get("summary") or "")[:1400]
        if not summary:
            continue
        npc_id = _npc_id_by_ref(conn, convo.get("npc_code") or convo.get("npc"))
        # Fallback: attach orphan dialogue to a face at the player's location
        if npc_id is None:
            try:
                prow = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
                loc_id = int(prow["current_location_id"]) if prow and prow["current_location_id"] else None
            except Exception:
                loc_id = None
            if loc_id:
                row = conn.execute(
                    """
                    SELECT id FROM npcs
                    WHERE location_id = ?
                    ORDER BY CASE WHEN shell = 0 THEN 0 ELSE 1 END, id DESC
                    LIMIT 1
                    """,
                    (loc_id,),
                ).fetchone()
                if row:
                    npc_id = int(row["id"])
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


# Roles for NPCs seeded from prose.
#
# This used to be a fixed four-item cycle starting "hooded stranger", "cloaked
# local" — and because a scene rarely seeds more than two faces, those two won
# almost every time: 24 of 27 NPCs across three live runs. Worse, it fed back on
# itself. The seeder wrote hooded strangers into the cast, the cast went into the
# next prompt, and the model kept writing hooded figures for the seeder to catch.
#
# A role is an occupation — what this person does here. Appearance belongs in the
# summary, so a baker can still be wearing a hood.
_SEED_ROLE_POOLS: dict[str, dict[str, tuple[str, ...]]] = {
    "preindustrial": {
        "indoor": (
            "patron", "server", "cook", "lodger", "card player", "musician",
            "kitchen hand", "regular", "landlord's son", "wine seller",
        ),
        "water": (
            "ferryman", "net mender", "boatwright", "mudlark", "dock hand",
            "eel fisher", "bargeman", "salt carrier",
        ),
        "wilderness": (
            "forager", "trapper", "charcoal burner", "pilgrim", "goatherd",
            "woodcutter", "road warden", "peddler", "hermit", "surveyor",
            "beekeeper", "deserter",
        ),
        "settlement": (
            "carter", "baker", "tanner", "porter", "stablehand", "roofer",
            "herbalist", "scribe", "cooper", "weaver", "drover", "toll keeper",
            "off-duty guard", "apprentice", "message runner", "rag picker",
            "well keeper", "chandler",
        ),
    },
    "industrial": {
        "indoor": (
            "barkeep", "boarder", "card player", "piano player", "cook",
            "travelling salesman", "night clerk", "regular", "kitchen hand",
        ),
        "water": (
            "stevedore", "riverboat hand", "dock clerk", "crane hand",
            "ferry clerk", "coal heaver", "harbour watchman",
        ),
        "wilderness": (
            "prospector", "line rider", "trapper", "surveyor", "drover",
            "teamster", "homesteader", "track walker", "hunter",
        ),
        "settlement": (
            "rail hand", "telegraph clerk", "teamster", "farrier", "storekeeper",
            "deputy", "freight agent", "printer", "assayer", "stable hand",
            "millwright", "seamstress", "undertaker", "off-duty brakeman",
        ),
    },
    "modern": {
        "indoor": (
            "customer", "server", "line cook", "cleaner", "night clerk",
            "regular", "delivery driver", "barista", "off-shift nurse",
        ),
        "water": (
            "dock worker", "boat mechanic", "harbour clerk", "crane operator",
            "deckhand", "port inspector",
        ),
        "wilderness": (
            "ranger", "surveyor", "scavenger", "line worker", "trucker",
            "field tech", "hunter", "drifter",
        ),
        "settlement": (
            "courier", "shop clerk", "mechanic", "paramedic", "security guard",
            "street vendor", "dispatcher", "technician", "cab driver",
            "building super", "scrap dealer", "off-duty officer",
        ),
    },
    "future": {
        "indoor": (
            "off-shift crew", "mess server", "bunkmate", "galley hand",
            "card player", "medtech", "systems intern", "night-cycle clerk",
        ),
        # Docks, bays, gantries: wherever things arrive.
        "water": (
            "cargo loader", "dock tech", "hull welder", "freight checker",
            "gantry hand", "tug pilot", "manifest clerk",
        ),
        # Outside the hull: wastes, belts, wrecks.
        "wilderness": (
            "salvager", "prospector", "surveyor", "drone handler", "scrapper",
            "hauler", "claim jumper", "rig hand",
        ),
        "settlement": (
            "comms clerk", "hab technician", "quartermaster", "dock inspector",
            "systems tech", "stall vendor", "courier", "medtech", "fabricator",
            "recycler", "off-duty marshal", "data broker",
        ),
    },
}

# Values that mean "nobody chose one". `tech_level` is a Pydantic field with
# default="iron age" (app/main.py), so a recorded "iron age" cannot be told
# apart from a deliberate pick -- and the style prose the player actually typed
# is the stronger signal when the two disagree.
_DEFAULTED_TECH_LEVELS = {"iron age"}

# The canonical tech_level vocabulary (app/llm.py TECH LEVEL options).
_TECH_LEVEL_ERA = {
    "iron age": "preindustrial",
    "medieval": "preindustrial",
    "early industrial": "industrial",
    "near future": "modern",
    "spacefaring salvage": "future",
}

# Fallback when tech_level is unset or a player typed their own. Ordered
# most-specific first so "near future" is not swallowed by "modern", and
# "cyberpunk"/"arcology" land in the same pool as starships rather than in
# the pre-industrial default.
_ERA_TEXT_HINTS = (
    ("future", (
        "spacefaring", "starship", "interstellar", "orbital", "faster-than-light",
        "colony ship", "far-future", "far future", "science fiction", "sci-fi",
        "space opera", "cyberpunk", "megacity", "arcology", "space station",
    )),
    ("modern", (
        "near future", "near-future", "modern", "contemporary", "present day",
        "post-collapse", "post-apocalyptic", "apocalypse", "wasteland", "urban",
    )),
    ("industrial", (
        "early industrial", "industrial", "steam", "victorian", "gaslight",
        "railroad", "wild west", "weird west", "frontier west", "1880", "1890",
    )),
    ("preindustrial", (
        "iron age", "medieval", "bronze age", "ancient", "feudal", "dark age",
        "high fantasy", "sword and sorcery", "mythic",
    )),
)


def resolve_world_era(tech_level: str = "", *style_text: str) -> str:
    """Which technological era this world runs in.

    Defaults to preindustrial, which is what every pool used to be
    unconditionally: a space station was staffed with bargemen and coopers, and
    a cyberpunk arcology got a well keeper, because occupation was chosen from
    the location's name alone and the genre never entered the function.
    """
    tech = str(tech_level or "").strip().lower()
    blob = " ".join(str(part or "") for part in style_text).lower()
    prose_era = ""
    for era, hints in _ERA_TEXT_HINTS:
        if any(hint in blob for hint in hints):
            prose_era = era
            break
    # An explicit, non-default tech_level is server truth and wins.
    if tech in _TECH_LEVEL_ERA and tech not in _DEFAULTED_TECH_LEVELS:
        return _TECH_LEVEL_ERA[tech]
    # Otherwise the style prose speaks first. "iron age" is the field's Pydantic
    # default, applied whenever nobody chose one, and it is indistinguishable
    # from a deliberate pick at this layer -- so a player who typed "far-future
    # interstellar civilisation" and never touched the tech dropdown had their
    # station staffed with boatwrights, and the packet told the model the world
    # was iron age at the same time.
    if prose_era:
        return prose_era
    if tech in _TECH_LEVEL_ERA:
        return _TECH_LEVEL_ERA[tech]
    for era, hints in _ERA_TEXT_HINTS:
        if any(hint in tech for hint in hints):
            return era
    return "preindustrial"


# The tech level to state as world truth, per era. Only used to replace a
# defaulted value that contradicts the setting; an explicit pick is never
# overridden.
_ERA_TECH_LEVEL = {
    "preindustrial": "iron age",
    "industrial": "early industrial",
    "modern": "near future",
    "future": "spacefaring salvage",
}


def coherent_tech_level(options: dict[str, Any] | None) -> str:
    """The tech level the packet should state, given everything else the world says.

    Returns the recorded value untouched unless it is the field's silent default
    AND the style prose describes a different era, in which case the prose wins
    and the era's canonical tech level is stated instead.
    """
    opts = options if isinstance(options, dict) else {}
    recorded = str(opts.get("tech_level") or "").strip()
    if recorded and recorded.lower() not in _DEFAULTED_TECH_LEVELS:
        return recorded
    era = resolve_world_era(
        recorded,
        str(opts.get("world_style") or ""),
        str(opts.get("custom_style") or ""),
    )
    return _ERA_TECH_LEVEL.get(era, recorded or "iron age")


# "rare" is the magic_level Pydantic default (app/main.py), applied whenever
# nobody touches the dropdown, and at this layer it cannot be told apart from a
# deliberate pick. Exactly the trap _DEFAULTED_TECH_LEVELS covers on the tech
# axis: a world set up as "high fantasy with open magic and old empires" was
# handed magic_level="rare" in its packet on every turn, and the prose obeyed
# the state rather than the style. That world scored 1 of 8 on its own genre
# vocabulary in the genre matrix -- the weakest of six settings.
_DEFAULTED_MAGIC_LEVELS = {"rare"}

# Ordered most-specific first. "no magic" must beat "magic", and "cultivation"
# must beat the generic open-magic words that a xianxia blurb also contains.
_MAGIC_TEXT_HINTS = (
    ("none", (
        "no magic", "magicless", "without magic", "non-magical", "nonmagical",
        "grounded medieval realism", "mundane world",
    )),
    ("cultivation", (
        "cultivation", "xianxia", "wuxia", "qi ", "sect politics", "immortal sect",
        "spirit realm ladder",
    )),
    ("forbidden", (
        "forbidden magic", "magic is banned", "banned magic", "outlawed magic",
        "illegal magic", "witch hunt", "inquisition", "heresy", "post-magic",
        "magic is taboo",
    )),
    ("common utility", (
        "open magic", "high magic", "common magic", "everyday magic",
        "magic is common", "magitech", "magepunk", "arcane industry",
        "mage academy", "spell markets", "wizard city",
    )),
    ("rare", (
        "low magic", "magic is rumor", "magic is rumour", "hedge magic",
        "scarce magic", "magic is rare",
    )),
)


def resolve_world_magic(magic_level: str = "", *style_text: str) -> str:
    """The magic level this world actually runs at.

    An explicit, non-default magic_level is server truth and wins. Otherwise
    the style prose speaks, because "rare" is what the field holds when nobody
    chose anything at all.
    """
    magic = str(magic_level or "").strip().lower()
    blob = " ".join(str(part or "") for part in style_text).lower()
    if magic and magic not in _DEFAULTED_MAGIC_LEVELS:
        return magic
    for level, hints in _MAGIC_TEXT_HINTS:
        if any(hint in blob for hint in hints):
            return level
    return magic or "rare"


def coherent_magic_level(options: dict[str, Any] | None) -> str:
    """The magic level the packet should state, given everything else the world says.

    Returns the recorded value untouched unless it is the field's silent
    default AND the style prose describes a different world, in which case the
    prose wins. Mirrors coherent_tech_level(); the two defaults failed the same
    way for the same reason.
    """
    opts = options if isinstance(options, dict) else {}
    recorded = str(opts.get("magic_level") or "").strip()
    if recorded and recorded.lower() not in _DEFAULTED_MAGIC_LEVELS:
        return recorded
    return resolve_world_magic(
        recorded,
        str(opts.get("world_style") or ""),
        str(opts.get("custom_style") or ""),
        str(opts.get("race_magic_rules") or ""),
    )


def _campaign_era(conn) -> str:
    """Read the world's era from the campaign's own settings."""
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = 'playthrough_options'"
        ).fetchone()
        options = json.loads(row["value"]) if row and row["value"] else {}
    except Exception:
        options = {}
    if not isinstance(options, dict):
        return "preindustrial"
    return resolve_world_era(
        str(options.get("tech_level") or ""),
        str(options.get("world_style") or ""),
        str(options.get("custom_style") or ""),
    )


# Scored, not first-hit: a town summary that merely mentions "the road" used to
# classify the place as wilderness and staff a gate-town with charcoal burners.
# Ambiguous words ("road", "path") are deliberately absent — they appear
# everywhere. Settlement is the default when nothing scores.
# The place axis is era-independent -- "somewhere indoors", "where things
# arrive", "outside the settled area", "the settled area itself" -- so each
# keyword list carries the words for every era. A docking bay is a "water"
# place in a starship world for the same reason a wharf is in a medieval one.
_SEED_POOL_HINTS = (
    ("indoor", (
        "inn", "tavern", "hall", "cellar", "kitchen", "chapel", "temple", "hearth",
        "common room", "taproom",
        "mess", "galley", "bunk", "cabin", "lounge", "bar", "clinic", "office", "ward",
    )),
    ("water", (
        "ford", "river", "dock", "wharf", "harbor", "harbour", "riverbank", "beach",
        "shore", "bridge", "mill", "quay", "ferry",
        "bay", "hangar", "gantry", "berth", "port", "airlock", "landing",
    )),
    ("wilderness", (
        "forest", "woods", "woodland", "moor", "ridge", "cave", "ruins", "wilds",
        "clearing", "marsh", "thicket", "glade", "hollow", "wilderness",
        "wastes", "waste", "outland", "surface", "belt", "expanse", "wreck", "scrapyard",
    )),
    ("settlement", (
        "town", "village", "city", "market", "square", "gate", "street", "quarter",
        "district", "hamlet", "settlement", "keep", "fort", "caravan",
        "station", "hab", "deck", "sublevel", "stack", "arcology", "concourse",
        "block", "depot", "platform", "terminal",
    )),
)
# Appearance words a model reaches for; kept out of the role column entirely.
_APPEARANCE_WORDS = (
    "hooded", "cloaked", "masked", "veiled", "robed", "tall", "short", "older",
    "young", "weathered", "scarred", "lean", "burly", "thin", "stocky", "armoured", "armored",
)


def _seed_role_pool(conn, location_id: int) -> tuple[str, ...]:
    """Pick an occupation pool that fits where the scene is happening."""
    try:
        row = conn.execute(
            "SELECT name, summary FROM locations WHERE id = ?", (int(location_id),)
        ).fetchone()
    except Exception:
        row = None
    text = f"{(row['name'] if row else '')} {(row['summary'] if row else '')}".lower()
    scores = {
        pool: sum(1 for word in keywords if word in text)
        for pool, keywords in _SEED_POOL_HINTS
    }
    best = max(scores, key=lambda pool: (scores[pool], pool == "settlement"))
    place = best if scores[best] else "settlement"
    era = _campaign_era(conn)
    return _SEED_ROLE_POOLS.get(era, _SEED_ROLE_POOLS["preindustrial"])[place]


def _seed_role_for(conn, location_id: int, hint: str, index: int, salt: Any = "") -> str:
    """
    An occupation for a prose-seeded face, avoiding roles already standing here.

    An explicit occupation in the prose always wins; otherwise the pool is walked
    deterministically from a campaign-stable seed so reruns and rewinds agree.
    """
    low = str(hint or "").lower()
    for word, role in (
        ("merchant", "merchant"), ("guard", "guard"), ("innkeeper", "innkeeper"),
        ("barkeep", "innkeeper"), ("bartender", "innkeeper"), ("soldier", "soldier"),
        ("scout", "scout"), ("broker", "broker"), ("server", "server"),
        ("barmaid", "server"), ("barman", "server"), ("keeper", "keeper"),
        ("traveler", "traveler"), ("traveller", "traveler"), ("wanderer", "traveler"),
        ("patron", "patron"), ("guest", "guest"),
    ):
        if word in low:
            return role
    pool = _seed_role_pool(conn, location_id)
    try:
        taken = {
            str(r["role"] or "").strip().lower()
            for r in conn.execute("SELECT role FROM npcs WHERE location_id = ?", (int(location_id),)).fetchall()
        }
    except Exception:
        taken = set()
    start = name_seed("seed_role", location_id, salt, index) % len(pool)
    for step in range(len(pool)):
        candidate = pool[(start + step) % len(pool)]
        if candidate.lower() not in taken:
            return candidate
    return pool[start]


def _appearance_note(hint: str) -> str:
    """Keep the model'sappearance, in the summary where it belongs."""
    low = str(hint or "").lower()
    found = [word for word in _APPEARANCE_WORDS if word in low]
    if not found:
        return ""
    return f" Looks {found[0]}."


_FIGURE_HINT_RE = re.compile(
    r"\b("
    r"(?:a|an|the)\s+(?:hooded|cloaked|masked|armou?red|ash[- ]?gr[ae]y|gray[- ]?cloaked|"
    r"tall|short|older|young|weathered|scarred|lean|burly|thin|stocky)\s+"
    r"(?:figure|man|woman|stranger|person|traveler|traveller|merchant|guard|patron|guest)|"
    r"(?:a|an|the)\s+(?:second|third|another|nearby|watching)\s+figure|"
    r"(?:a|an)\s+(?:stranger|merchant|guard|innkeeper|bartender|barkeep|traveler|traveller|"
    r"wanderer|broker|scout|soldier|patron|guest|keeper|server|barmaid|barman)|"
    # Spoken dialogue with a named/titled speaker: Mara says / the innkeeper asks
    r"(?:the\s+)?(?:innkeeper|bartender|barkeep|guard|merchant|stranger|keeper|"
    r"server|barmaid|barman|captain|clerk)\s+(?:says?|asks?|mutters?|whispers?|calls?|snorts?|grunts?)|"
    r"[A-Z][a-z]{2,12}\s+(?:says?|asks?|mutters?|whispers?|calls?|snorts?|grunts?|replies?|answers?)"
    r")\b",
    re.I,
)


def _ensure_npcs_from_narration(
    conn,
    result: dict[str, Any],
    narration: str,
    location_id: int | None,
) -> list[dict[str, Any]]:
    """
    If prose introduces speaking/visible figures but the model returned no/few npcs,
    seed shell NPC rows so the cast table matches the scene.
    """
    if not location_id:
        return []
    text = str(narration or "")
    if not text.strip():
        return []
    hints = [m.group(0).strip() for m in _FIGURE_HINT_RE.finditer(text)]
    # Dialogue without a listed speaker still implies at least one face
    has_dialogue = bool(re.search(r'[“"][^”"]{8,}[”"]', text))
    existing = [n for n in (result.get("npcs") or []) if isinstance(n, dict)]
    # Also count DB faces at this location (already upserted this turn)
    db_count = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM npcs WHERE location_id = ?",
            (int(location_id),),
        ).fetchone()["c"]
        or 0
    )
    target = min(3, max(len(hints), 1 if has_dialogue and not existing and db_count == 0 else 0))
    if target <= 0:
        return []
    need = max(0, target - max(len(existing), db_count))
    if need <= 0 and existing:
        return []
    if need <= 0 and db_count > 0:
        return []
    # If model listed none but hints exist, seed from hint count
    if not existing and db_count == 0:
        need = min(3, max(len(hints), 1 if has_dialogue else 0))
    created: list[dict[str, Any]] = []
    for i in range(need):
        hint = hints[i] if i < len(hints) else ""
        role = _seed_role_for(conn, int(location_id), hint, i, salt=text[:40])
        try:
            shell = create_shell_npc(
                conn,
                int(location_id),
                presence="event_worthy",
                power_rank=8 + i * 2,
                role=role,
                seed=name_seed("shell_npc", location_id, hint, i, text[:40]),
                appearance=_appearance_note(hint),
            )
        except Exception:
            continue
        if not shell:
            continue
        entry = {
            "code": shell.get("code"),
            "name": shell.get("name"),
            "role": shell.get("role") or role,
            "summary": shell.get("summary") or "Present in the opening scene.",
            "attitude": "neutral",
            "location": "",
            "presence": "event_worthy",
            "shell": False,
            "power_rank": shell.get("power_rank") or 8,
            "_seeded_from_narration": True,
        }
        created.append(entry)
        existing.append(entry)
    if created:
        result["npcs"] = existing
    return created


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
        growth_math = str(update.get("growth_math") or "")[:800]
        power_type = str(update.get("power_type") or "").strip().lower().replace("-", "_")
        if power_type and power_type not in {
            "compounding",
            "passive",
            "linear",
            "soft_cap",
            "breakthrough",
            "flat",
            "item_bound",
        }:
            power_type = ""
        rc_json = ""
        if "resource_cost" in update and update.get("resource_cost") is not None:
            try:
                from app.player_resources import format_resource_cost, parse_resource_cost

                rc = parse_resource_cost(update.get("resource_cost"))
                rc_json = json.dumps(rc, ensure_ascii=True)
                if not cost:
                    cost = format_resource_cost(rc)[:300]
            except Exception:
                if isinstance(update.get("resource_cost"), dict):
                    rc_json = json.dumps(update["resource_cost"], ensure_ascii=True)
                else:
                    rc_json = str(update.get("resource_cost") or "")[:800]
        if rc_json:
            conn.execute(
                """
                UPDATE abilities
                SET additions = ?,
                    cost = COALESCE(NULLIF(?, ''), cost),
                    prerequisites = COALESCE(NULLIF(?, ''), prerequisites),
                    growth_math = COALESCE(NULLIF(?, ''), growth_math),
                    resource_cost = ?,
                    power_type = COALESCE(NULLIF(?, ''), power_type)
                WHERE id = ?
                """,
                (additions, cost, prerequisites, growth_math, rc_json, power_type, ability["id"]),
            )
        else:
            conn.execute(
                """
                UPDATE abilities
                SET additions = ?,
                    cost = COALESCE(NULLIF(?, ''), cost),
                    prerequisites = COALESCE(NULLIF(?, ''), prerequisites),
                    growth_math = COALESCE(NULLIF(?, ''), growth_math),
                    power_type = COALESCE(NULLIF(?, ''), power_type)
                WHERE id = ?
                """,
                (additions, cost, prerequisites, growth_math, power_type, ability["id"]),
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
    history_summary_path().parent.mkdir(parents=True, exist_ok=True)
    with history_summary_path().open("a", encoding="utf-8") as handle:
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
    files = sorted(model_trace_dir().glob("turn-*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for old_path in files[keep:]:
        try:
            old_path.unlink()
        except OSError:
            pass


def debug_mode_enabled() -> bool:
    """
    Extra-verbose server debug. Trace files are always written for per-turn UI toggles;
    this flag only forces richer on-disk retention defaults if set.
    """
    raw = os.getenv("AI_RPG_DEBUG")
    if raw is None or not str(raw).strip():
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


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
    # Always write: the play UI offers a per-turn Debug toggle to view/copy the file.
    model_trace_dir().mkdir(parents=True, exist_ok=True)
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
    path = model_trace_dir() / f"turn-{turn:06d}-{_safe_trace_kind(input_kind)}{suffix}.json"
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


# Which turn fields are amounts, and which magnitude table rolls each one.
#   (container path, band key, numeric key, magnitude kind, allows negative)
_BAND_FIELDS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("player", "xp_band", "xp_delta", "xp", False),
    ("player", "gold_band", "gold_delta", "gold", True),
    ("player", "health_band", "health_delta", "damage", True),
    ("player", "karma_band", "karma_delta", "karma", True),
)


def band_authority_mode(options: dict[str, Any] | None = None) -> str:
    """
    How much numeric authority the model keeps.

    ``rolled``  (default) — bands are rolled, and bare numbers are read as band
                hints and re-rolled. The server owns every amount.
    ``bands``   — bands are rolled; explicit numbers are passed through (still
                clamped as before).
    ``off``     — legacy behaviour, bands ignored.
    """
    env = str(os.getenv("AI_RPG_BAND_AUTHORITY") or "").strip().lower()
    if env in {"rolled", "bands", "off"}:
        return env
    opts = options if isinstance(options, dict) else {}
    mode = str(opts.get("band_authority") or "").strip().lower()
    return mode if mode in {"rolled", "bands", "off"} else "rolled"


def _resolve_amount(
    *,
    kind: str,
    band: Any,
    raw_number: Any,
    mode: str,
    level: int,
    options: dict[str, Any],
    turn: int,
    tag: str,
    seed: int,
    allow_negative: bool = False,
) -> tuple[int | None, dict[str, Any] | None]:
    """
    Decide one amount. Returns ``(value, roll_record)``; ``value`` is None when
    nothing should change.

    A declared band always wins. A bare number is treated as an intent signal:
    it says roughly how big the model *wanted* the change to be, and the server
    rolls that band properly. This keeps old prompts, cached browser clients,
    and third-party agents working while still moving the arithmetic here.
    """
    from app import rng as rng_mod

    has_band = band is not None and str(band).strip() != ""
    try:
        number = int(_float(raw_number, 0))
    except (TypeError, ValueError):
        number = 0

    if mode == "off":
        return (number if number else None), None

    if not has_band:
        if not number:
            return None, None
        if mode == "bands":
            return number, None
        band = rng_mod.band_from_number(kind, number, level=level)
    else:
        # A model that invents a band word ("fresh", "modest") still clearly
        # meant *something* to happen. Falling through to "none" silently
        # deleted the change; treat an unrecognized word as a small one.
        canon = rng_mod.normalize_band(str(band).lstrip("-"), default="")
        if not canon:
            band = ("-" if str(band).startswith("-") else "") + "small"

    negative = False
    if allow_negative:
        negative = number < 0 or str(band).strip().lower().startswith(("-", "lose", "spend"))

    roll = rng_mod.resolve_magnitude(
        kind,
        str(band).lstrip("-"),
        level=level,
        difficulty=str(options.get("difficulty") or "normal"),
        options=options,
        negative=negative,
        turn=turn,
        tag=tag,
        seed=seed,
    )
    return roll["value"], roll


def resolve_turn_bands(
    conn,
    result: dict[str, Any],
    *,
    turn: int,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Replace every "how much" the model proposed with a server-rolled amount.

    Local models are poor at restraint with numbers — asked for XP they mint
    250, then 400 next turn. Asking them only for a *band* ("small", "large")
    and rolling the amount here keeps rewards on a curve, makes them respond
    to level/difficulty/growth settings automatically, and makes the whole
    thing auditable in the ``dice_rolls`` table.
    """
    from app import rng as rng_mod

    options = options if isinstance(options, dict) else {}
    mode = band_authority_mode(options)
    if mode == "off":
        return {"mode": mode, "rolls": []}

    try:
        prow = conn.execute("SELECT level FROM player WHERE id = 1").fetchone()
        level = int(prow["level"]) if prow else 1
    except Exception:
        level = 1

    # Resolve the campaign seed once, from the connection already held. Letting
    # each roll open its own connection made SQLite block on its busy timeout
    # against this transaction (1.9s benchmark -> 117s).
    seed = rng_mod.campaign_seed(conn)
    rolls: list[dict[str, Any]] = []

    # Amounts the server itself computed this turn (skill-check injuries,
    # resolved combat damage). They are already dice results; re-rolling them
    # would replace real mechanics with a second, unrelated roll.
    server_authored = {str(p) for p in (result.get("_server_authored") or [])}

    for container, band_key, number_key, kind, signed in _BAND_FIELDS:
        block = result.get(container)
        if not isinstance(block, dict):
            continue
        if f"{container}.{number_key}" in server_authored:
            block.pop(band_key, None)
            continue
        value, roll = _resolve_amount(
            kind=kind,
            band=block.get(band_key),
            raw_number=block.get(number_key),
            mode=mode,
            level=level,
            options=options,
            turn=turn,
            seed=seed,
            tag=f"{container}.{number_key}",
            allow_negative=signed,
        )
        if roll:
            rolls.append(roll)
        if value is None:
            block.pop(number_key, None)
        else:
            block[number_key] = value
        block.pop(band_key, None)

    for change in result.get("inventory_changes") or []:
        if not isinstance(change, dict):
            continue
        band = change.get("quantity_band")
        raw = change.get("quantity_delta")
        if band is None and raw in (None, ""):
            continue
        losing = str(band or "").strip().lower().startswith(("-", "lose")) or _float(raw, 0) < 0
        value, roll = _resolve_amount(
            kind="item_count",
            band=band,
            raw_number=raw,
            mode=mode,
            level=level,
            options=options,
            turn=turn,
            seed=seed,
            tag=f"item:{str(change.get('name') or '')[:32]}",
        )
        if roll:
            rolls.append(roll)
        change.pop("quantity_band", None)
        if value is None:
            continue
        change["quantity_delta"] = -abs(value) if losing else abs(value)

    for npc in result.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        if npc.get("trust_band") is None and not npc.get("trust_delta"):
            continue
        losing = str(npc.get("trust_band") or "").strip().lower().startswith(("-", "lose")) or _float(npc.get("trust_delta"), 0) < 0
        value, roll = _resolve_amount(
            kind="trust",
            band=npc.get("trust_band"),
            raw_number=npc.get("trust_delta"),
            mode=mode,
            level=level,
            options=options,
            turn=turn,
            seed=seed,
            tag=f"trust:{str(npc.get('code') or npc.get('name') or '')[:24]}",
        )
        if roll:
            rolls.append(roll)
        npc.pop("trust_band", None)
        if value is not None:
            npc["trust_delta"] = -abs(value) if losing else abs(value)

    for event in result.get("events") or []:
        if not isinstance(event, dict):
            continue
        if event.get("fame_band") is None and not event.get("fame_score"):
            continue
        value, roll = _resolve_amount(
            kind="fame",
            band=event.get("fame_band"),
            raw_number=event.get("fame_score"),
            mode=mode,
            level=level,
            options=options,
            turn=turn,
            seed=seed,
            tag=f"fame:{str(event.get('title') or '')[:24]}",
        )
        if roll:
            rolls.append(roll)
        event.pop("fame_band", None)
        if value is not None:
            event["fame_score"] = max(0, min(80, value))

    for change in result.get("skill_changes") or []:
        if not isinstance(change, dict):
            continue
        if change.get("delta_band") is None and not change.get("delta"):
            continue
        value, roll = _resolve_amount(
            kind="skill_gain",
            band=change.get("delta_band"),
            raw_number=change.get("delta"),
            mode=mode,
            level=level,
            options=options,
            turn=turn,
            seed=seed,
            tag=f"skill:{str(change.get('name') or '')[:24]}",
        )
        if roll:
            rolls.append(roll)
        change.pop("delta_band", None)
        if value is not None:
            change["delta"] = value

    rng_mod.record_rolls(conn, rolls, turn=turn, source="turn_bands")
    return {
        "mode": mode,
        "rolls": rolls,
        "lines": [rng_mod.explain(r) for r in rolls],
    }


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

        # Movement runs before the snapshot so a repaired destination is part of
        # the rewind record, not applied on top of it.
        try:
            movement_report = resolve_movement(
                conn,
                result,
                player_input,
                intent=_turn_intent(player_input)[0],
                narration=_narration_text(result),
            )
        except Exception as exc:
            movement_report = {"status": "error", "error": f"{type(exc).__name__}: {exc}"[:200]}

        _save_snapshot(conn, next_turn, result)
        turn = _next_turn(conn)

        # Every "how much" the model proposed becomes a server-rolled amount
        # before anything touches the database. Runs first so the snapshot
        # above still holds the model's raw proposal for debugging.
        try:
            band_report = resolve_turn_bands(
                conn,
                result,
                turn=turn,
                options=_settings(conn).get("playthrough_options") or {},
            )
        except Exception as exc:
            # Falling back here means the model's raw numbers pass through
            # unrolled, so make it loud rather than a silent downgrade.
            band_report = {"mode": "error", "rolls": [], "error": f"{type(exc).__name__}: {exc}"[:200]}
            try:
                conn.execute(
                    "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                    (turn, "system", f"Band resolution failed; amounts were not rolled. {band_report['error']}"),
                )
            except Exception:
                pass

        narration = _narration_text(result)
        # Last-line defense: expand [[codes]] / fill blank subjects using live cast names
        try:
            from app.llm import _repair_entity_names_in_turn

            # Minimal context so repair can see current cast
            loc_id = None
            try:
                prow = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
                loc_id = int(prow["current_location_id"]) if prow and prow["current_location_id"] else None
            except Exception:
                loc_id = None
            cast: list[dict[str, Any]] = []
            if loc_id:
                cast = rows_to_dicts(
                    conn.execute(
                        "SELECT code, name, role FROM npcs WHERE location_id = ? ORDER BY id",
                        (loc_id,),
                    ).fetchall()
                )
            mini_ctx = {
                "locations": [{"code": "", "name": "", "npcs": cast}],
                "npcs": cast,
            }
            repaired = _repair_entity_names_in_turn(dict(result), mini_ctx)
            if isinstance(repaired, dict):
                result = repaired
                narration = _narration_text(result)
        except Exception:
            pass

        for location in result.get("locations") or []:
            if not isinstance(location, dict):
                continue
            # Never treat a location row whose "name" is only L1/I1 as a new place label
            loc_name = str(location.get("name") or "")
            if _is_place_or_item_code(loc_name):
                continue
            _upsert_location(conn, loc_name, str(location.get("summary") or ""))

        # Flatten nested locations[].npcs + conversation speakers; drop place-as-person junk
        collected_npcs = _collect_npcs_from_turn_result(result)
        result["npcs"] = collected_npcs
        for npc in collected_npcs:
            _upsert_npc(conn, npc)

        # Pin one keeper per venue. Without this the model reinvented whoever was
        # behind the counter on every visit -- the same apothecary was staffed by
        # a man, then a woman, then a different man across three visits.
        try:
            here_row = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
            here_id = int((here_row["current_location_id"] if here_row else 0) or 0)
            if here_id and str(venues._field(_location_row(conn, here_id), "kind", "") or ""):
                bind_venue_keeper(conn, here_id)
        except Exception:
            pass

        # Opening/scene figures without structured npcs → seed cast so export isn't empty
        try:
            loc_id_seed = None
            prow2 = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
            if prow2 and prow2["current_location_id"]:
                loc_id_seed = int(prow2["current_location_id"])
            seeded = _ensure_npcs_from_narration(conn, result, narration, loc_id_seed)
            if seeded:
                # Re-run name repair so prose can pick up new codes/names if needed
                try:
                    from app.llm import _repair_entity_names_in_turn

                    cast2 = rows_to_dicts(
                        conn.execute(
                            "SELECT code, name, role FROM npcs WHERE location_id = ? ORDER BY id",
                            (loc_id_seed,),
                        ).fetchall()
                    ) if loc_id_seed else []
                    mini_ctx2 = {
                        "locations": [{"code": "L1", "name": "", "npcs": cast2}],
                        "npcs": cast2,
                        "inventory": rows_to_dicts(
                            conn.execute("SELECT code, name FROM inventory ORDER BY id").fetchall()
                        ),
                        "current_location": {"code": "L1", "name": ""},
                    }
                    # Prefer real location code/name
                    if loc_id_seed:
                        lrow = conn.execute(
                            "SELECT code, name FROM locations WHERE id = ?", (loc_id_seed,)
                        ).fetchone()
                        if lrow:
                            mini_ctx2["current_location"] = {
                                "code": lrow["code"],
                                "name": lrow["name"],
                            }
                            mini_ctx2["locations"] = [
                                {"code": lrow["code"], "name": lrow["name"], "npcs": cast2}
                            ]
                    repaired2 = _repair_entity_names_in_turn(dict(result), mini_ctx2)
                    if isinstance(repaired2, dict):
                        result = repaired2
                        narration = _narration_text(result)
                except Exception:
                    pass
        except Exception:
            pass

        _apply_relationships(conn, result.get("relationships") or [])
        # Inventory fidelity: strip hallucinated gains not grounded in narration/existing stack
        inv_changes = _filter_inventory_changes(
            conn,
            result.get("inventory_changes") or [],
            narration=narration,
            player_input=player_input,
            input_kind=input_kind,
        )
        result["inventory_changes"] = inv_changes
        _apply_inventory(conn, inv_changes)
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
        # Movement repairs are state changes the model did not ask for — say so.
        if movement_report.get("status") == "repaired":
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (
                    turn,
                    "system",
                    "Travel action with no MOVE op; server moved the player to "
                    f"{movement_report.get('destination') or '?'} ({movement_report.get('rule')})."[:1400],
                ),
            )
        elif movement_report.get("status") == "unresolved":
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (turn, "system", "Travel action with no MOVE op and no resolvable destination; player stayed put."),
            )
        # Keep the dice visible: the player can always ask why they got 7 gold.
        if band_report.get("lines"):
            result["_band_rolls"] = band_report
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (turn, "dice", " · ".join(band_report["lines"])[:1400]),
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
    state = _state_with_refreshed_source_index()
    # Surface this turn's dice on the returned state. `result` is discarded
    # here, so anything left only on it (as _band_rolls originally was) is
    # invisible to the API and the UI.
    if isinstance(state, dict) and band_report.get("rolls"):
        state["dice_rolls"] = {
            "mode": band_report.get("mode"),
            "turn": turn,
            "lines": band_report.get("lines") or [],
            "rolls": band_report.get("rolls") or [],
        }
    if isinstance(state, dict):
        # Measurable: a playtest can count model / repaired / unresolved travel turns.
        state["movement"] = {**movement_report, "turn": turn}
        state["voice_check"] = check_narrative_voice(narration, state)
    return state


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
    ability_use_pack: dict[str, Any] | None = None
    action_spend_pack: dict[str, Any] | None = None
    model_input = _expand_input_references(context, player_input)
    if _ensure_combat_profiles_for_input(context, model_input):
        context = get_state(include_hidden=True)
        model_input = _expand_input_references(context, player_input)

    # Social walk-away / persist (player agency after cold reception)
    social_rep_note: dict[str, Any] | None = None
    if input_kind == "player":
        try:
            low = str(model_input or "").lower()
            walk_away = bool(
                re.search(
                    r"\b(walk away|leave (them|him|her)|excuse myself|never ?mind|forget it|i('ll| will) go)\b",
                    low,
                )
            )
            persist = bool(
                re.search(
                    r"\b(insist|keep (talking|asking)|press (them|him|her)|won't leave|don't walk away|again,? (i )?(ask|say|talk))\b",
                    low,
                )
            )
            if walk_away or persist:
                with connect() as c_soc:
                    last = _settings(c_soc).get("last_social")
                    if isinstance(last, dict) and last.get("npc_code"):
                        loc_id = last.get("location_id")
                        if walk_away:
                            social_rep_note = resolve_social_disengage(
                                c_soc,
                                npc_code=str(last["npc_code"]),
                                walked_away=True,
                                location_id=int(loc_id) if loc_id else None,
                            )
                        elif persist and last.get("cold"):
                            social_rep_note = resolve_social_persist(
                                c_soc,
                                npc_code=str(last["npc_code"]),
                                location_id=int(loc_id) if loc_id else None,
                            )
        except Exception:
            social_rep_note = None

    # Forced world events (quest portal, etc.) inject into any non-event turn.
    # Consume at most one force beat per turn so a second due event is not left
    # stuck as status=active without resolution.
    forced_events: list[dict[str, Any]] = []
    if input_kind != "event" and not str(model_input).startswith("__event_request__"):
        try:
            forced_events = consume_due_world_events(force_only=True, limit=1)
            if forced_events:
                top = forced_events[0]
                pl0 = top.get("payload") if isinstance(top.get("payload"), dict) else {}
                # Full replace for any force bus event (quest, travel ambush, weather shelter)
                # or explicit block flags — player action does not run.
                if input_kind in {"player", "continue", "wait"} and (
                    bool(top.get("force"))
                    or pl0.get("blocks_player_action")
                    or pl0.get("replace_turn")
                    or pl0.get("immutable")
                ):
                    return play_world_event_turn(top, input_kind="event")
                pl = pl0
                model_input = (
                    model_input
                    + "\n\n__forced_world_events__ (already decided; must appear this turn):\n"
                    + (
                        f"- kind={top.get('kind')} force=1 summary={str(top.get('summary') or '')[:180]} "
                        f"stage={pl.get('stage_id') or ''} adjacent={pl.get('place') or pl.get('adjacent') or ''}"
                    )
                    + "\nconstraints: do not cancel force events; place adjacent if marked; player is trigger when stage set."
                )
        except Exception:
            forced_events = []

    mechanics_context = _build_mechanics_context(context, model_input)
    mechanics_context = dict(mechanics_context or {})
    # Weather + pending announce for DM prose (non-blocking system)
    try:
        with connect() as _cw:
            wx = get_weather(_cw)
            mechanics_context["weather"] = {
                "kind": wx.get("kind"),
                "strength": wx.get("strength"),
                "label": wx.get("label"),
            }
            pending_wx = _settings(_cw).get("weather_announce_pending")
            if isinstance(pending_wx, dict) and pending_wx.get("text"):
                mechanics_context["weather_announce"] = pending_wx.get("text")
                # Clear so it is mentioned once in a real scene
                consume_weather_announce(_cw)
            loc = context.get("current_location") or {}
            lid = loc.get("id")
            mechanics_context["area_reputation"] = get_area_reputation(
                _cw, int(lid) if lid else None, str(loc.get("code") or "")
            )
            last_social = _settings(_cw).get("last_social")
            if isinstance(last_social, dict):
                mechanics_context["last_social"] = last_social
    except Exception:
        pass

    # Power use: match named ability, gate on lock/CD/pools, apply spend + debuffs
    if input_kind in {"player", "continue"} and not str(model_input).startswith("__"):
        try:
            from app.player_resources import (
                ability_use_prompt_block,
                apply_ability_use,
                match_ability_from_input,
            )

            abs_list = context.get("abilities") if isinstance(context.get("abilities"), list) else []
            matched = match_ability_from_input(model_input, abs_list)
            # Also try intent keyword path when "use my ability X"
            if matched is None:
                intent_chk, _ = _turn_intent(model_input)
                if intent_chk == "ability" and abs_list:
                    # Prefer unlocked actives with names present loosely
                    matched = match_ability_from_input(model_input, abs_list)
            if matched is not None:
                opts = ((context.get("settings") or {}).get("playthrough_options") or {})
                wt = context.get("world_time") or get_world_time()
                turn_n = int(_float(context.get("turn"), _current_turn_number()) or 0)

                def _sg():
                    with connect() as c:
                        return _settings(c)

                def _ss(key: str, value: Any):
                    with connect() as c:
                        _set_setting(c, key, value)

                with connect() as c_ab:
                    ability_use_pack = apply_ability_use(
                        c_ab,
                        matched,
                        options=opts if isinstance(opts, dict) else {},
                        world_time=wt if isinstance(wt, dict) else {},
                        turn=turn_n,
                        hard_block=True,
                        settings_get=lambda: _settings(c_ab),
                        settings_set=lambda k, v: _set_setting(c_ab, k, v),
                    )
                if ability_use_pack:
                    mechanics_context["ability_use"] = {
                        "ok": ability_use_pack.get("ok"),
                        "blocked": ability_use_pack.get("blocked"),
                        "ability": ability_use_pack.get("ability"),
                        "reasons": ability_use_pack.get("reasons") or [],
                        "cost": ability_use_pack.get("cost"),
                        "cooldown": ability_use_pack.get("cooldown"),
                        "debuffs": ability_use_pack.get("debuffs") or [],
                        "resources_after": ability_use_pack.get("after"),
                    }
                    if ability_use_pack.get("after"):
                        mechanics_context["resources"] = ability_use_pack["after"]
                        context["resources"] = ability_use_pack["after"]
                    block = ability_use_prompt_block(ability_use_pack)
                    if block:
                        model_input = model_input + "\n\n__ability_use__:\n" + block
        except Exception:
            ability_use_pack = None
    if forced_events:
        mechanics_context["forced_events"] = [
            {
                "id": e.get("id"),
                "kind": e.get("kind"),
                "summary": e.get("summary"),
                "force": True,
                "payload": e.get("payload") if isinstance(e.get("payload"), dict) else {},
            }
            for e in forced_events
        ]
    if social_rep_note:
        mechanics_context["social_reputation"] = social_rep_note
        model_input = (
            model_input
            + f"\n\n__social_rep__: flavor={social_rep_note.get('flavor')} "
            f"npc={social_rep_note.get('npc_code')} walked_away={social_rep_note.get('walked_away')}. "
            "Reflect trust/area reputation change lightly; do not invent inventory."
        )
    context["mechanics_context"] = mechanics_context
    context["weather"] = mechanics_context.get("weather")

    # Spend in-world minutes for ordinary actions (walk/wait already advanced time)
    if input_kind == "player" and not str(model_input).startswith("__"):
        try:
            spent = estimate_action_minutes(model_input)
            if spent > 0:
                with connect() as c_time:
                    advance_world_time(c_time, spent)
                mechanics_context = dict(context.get("mechanics_context") or {})
                mechanics_context["action_minutes"] = spent
                context["mechanics_context"] = mechanics_context
                context["world_time"] = get_world_time()
                context["weather"] = get_weather()
            # Action-kind energy/fatigue drain (ability spend is separate)
            if ability_use_pack is None:
                from app.player_resources import action_kind_from_text, apply_action_spend, collapse_state

                akind = action_kind_from_text(model_input)
                opts = ((context.get("settings") or {}).get("playthrough_options") or {})
                player = context.get("player") if isinstance(context.get("player"), dict) else {}
                stats = player.get("effective_stats") if isinstance(player.get("effective_stats"), dict) else None
                with connect() as c_act:
                    action_spend_pack = apply_action_spend(
                        c_act,
                        kind=akind,
                        minutes=spent if spent > 0 else estimate_action_minutes(model_input) or 6,
                        options=opts if isinstance(opts, dict) else {},
                        stats=stats,
                        hard_block=True,
                    )
                if action_spend_pack:
                    mechanics_context = dict(context.get("mechanics_context") or {})
                    mechanics_context["action_spend"] = {
                        "ok": action_spend_pack.get("ok"),
                        "blocked": action_spend_pack.get("blocked"),
                        "kind": action_spend_pack.get("kind"),
                        "reasons": action_spend_pack.get("reasons") or [],
                        "delta": action_spend_pack.get("delta"),
                        "collapse": action_spend_pack.get("collapse"),
                        "resources_after": action_spend_pack.get("after"),
                    }
                    if action_spend_pack.get("after"):
                        mechanics_context["resources"] = action_spend_pack["after"]
                        context["resources"] = action_spend_pack["after"]
                        col = action_spend_pack.get("collapse") or collapse_state(action_spend_pack["after"])
                        mechanics_context["collapse"] = col
                    context["mechanics_context"] = mechanics_context
                    if action_spend_pack.get("blocked"):
                        model_input = (
                            model_input
                            + "\n\n__action_blocked__: reasons="
                            + ",".join(action_spend_pack.get("reasons") or ["exhausted"])
                            + ". Player is too exhausted for this physical action. "
                            "Narrate failure or forced rest — do not complete the full physical feat. "
                            "Suggest wait/meditate/sleep."
                        )
        except Exception:
            action_spend_pack = None

    # Pre-resolve action checks so the LLM must honor social rolls / DCs.
    skill_check_results: list[dict[str, Any]] = []
    try:
        from app.skill_checks import (
            infer_check_from_action,
            merge_check_settings,
            resolve_check,
            social_attitude_from_check,
        )

        opts = ((context.get("settings") or {}).get("playthrough_options") or {})
        check_cfg = merge_check_settings(
            opts.get("skill_check_settings") if isinstance(opts.get("skill_check_settings"), dict) else opts
        )
        if check_cfg.get("dice_checks_enabled") and input_kind == "player":
            player = context.get("player") or {}
            stats = player.get("effective_stats") or player.get("stats") or {}
            skills = context.get("skills") or []
            pending: list[dict[str, Any]] = []
            if check_cfg.get("auto_check_on_risky_actions") or check_cfg.get("auto_social_on_talk"):
                inferred = infer_check_from_action(model_input, context)
                if inferred and (inferred.get("social") or check_cfg.get("auto_check_on_risky_actions")):
                    pending = [inferred]
            for item in pending[:4]:
                if not isinstance(item, dict):
                    continue
                resolved = resolve_check(
                    skill_code=str(item.get("skill_code") or item.get("code") or item.get("skill") or "general"),
                    difficulty=item.get("difficulty"),
                    dc=item.get("dc"),
                    player_stats=stats if isinstance(stats, dict) else {},
                    player_skills=skills if isinstance(skills, list) else [],
                    opposition=item.get("opposition"),
                    settings=check_cfg,
                    context_note=str(item.get("context_note") or item.get("note") or model_input)[:400],
                    weapon_or_tool=str(item.get("weapon_or_tool") or item.get("weapon") or ""),
                )
                if item.get("social") or str(resolved.get("skill_code") or "") in {
                    "persuasion",
                    "deception",
                    "intimidation",
                    "insight",
                    "etiquette",
                    "performance",
                    "streetwise",
                }:
                    npc_ref = item.get("npc_ref") if isinstance(item.get("npc_ref"), dict) else {}
                    outcome = str(resolved.get("outcome") or resolved.get("result") or "failure")
                    attitude = social_attitude_from_check(outcome, npc_ref)
                    resolved["social_attitude"] = attitude
                    resolved["social_direction"] = (
                        f"NPC reaction lean: {attitude}. Honor traits. Low rolls colder/harsher. "
                        f"If they refuse chat and the player walks away immediately, that is courteous; "
                        f"if the player keeps pushing talk, reputation falls."
                    )
                    code = str(npc_ref.get("code") or "").strip()
                    if code and attitude:
                        try:
                            from app.db import connect as _c

                            with _c() as c2:
                                c2.execute(
                                    "UPDATE npcs SET attitude = ? WHERE code = ?",
                                    (attitude.lower(), code),
                                )
                                # Track last social target for walk-away / persist API
                                loc_id = None
                                prow = c2.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
                                if prow:
                                    loc_id = prow["current_location_id"]
                                cold = attitude.lower() in {
                                    "dismissive",
                                    "apprehensive",
                                    "condescending",
                                    "antagonistic",
                                    "hostile",
                                }
                                _set_setting(
                                    c2,
                                    "last_social",
                                    {
                                        "npc_code": code,
                                        "attitude": attitude.lower(),
                                        "cold": cold,
                                        "turn": _current_turn_number(),
                                        "location_id": loc_id,
                                        "outcome": outcome,
                                    },
                                )
                                # Success with a disliked local → association penalty
                                if outcome in {"success", "critical_success"}:
                                    apply_social_association_penalty(
                                        c2,
                                        location_id=int(loc_id) if loc_id else None,
                                        befriended_npc_code=code,
                                        trust_gained=4 if outcome == "critical_success" else 2,
                                    )
                                    adjust_npc_trust(
                                        c2,
                                        code,
                                        3 if outcome == "success" else 5,
                                        reason="social_success",
                                    )
                                elif outcome in {"failure", "critical_failure"} and cold:
                                    # Soft flag: next push will hurt more
                                    adjust_npc_trust(c2, code, -1, reason="cold_social")
                        except Exception:
                            pass
                skill_check_results.append(resolved)
            if skill_check_results:
                mechanics_context = dict(mechanics_context or {})
                mechanics_context["resolved_checks"] = skill_check_results
                mechanics_context["social_attitudes"] = [
                    {
                        "skill": c.get("skill_code"),
                        "outcome": c.get("outcome"),
                        "attitude": c.get("social_attitude"),
                        "direction": c.get("social_direction"),
                    }
                    for c in skill_check_results
                    if c.get("social_attitude")
                ]
                inv = context.get("inventory") or []
                mechanics_context["player_inventory_codes"] = [
                    {"code": i.get("code"), "name": i.get("name"), "qty": i.get("quantity")}
                    for i in inv
                    if isinstance(i, dict)
                ][:40]
                context["mechanics_context"] = mechanics_context
    except Exception:
        skill_check_results = []

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

    # Attach pre-resolved checks to turn output (and any extra model-proposed checks).
    try:
        from app.skill_checks import apply_check_to_turn, merge_check_settings, resolve_check

        opts = ((context.get("settings") or {}).get("playthrough_options") or {})
        check_cfg = merge_check_settings(
            opts.get("skill_check_settings") if isinstance(opts.get("skill_check_settings"), dict) else opts
        )
        for resolved in skill_check_results:
            result = apply_check_to_turn(result, resolved)
        if check_cfg.get("dice_checks_enabled") and input_kind == "player":
            player = context.get("player") or {}
            stats = player.get("effective_stats") or player.get("stats") or {}
            skills = context.get("skills") or []
            for item in list(result.get("skill_checks") or [])[:4]:
                if not isinstance(item, dict):
                    continue
                if item.get("natural") is not None:
                    continue
                code = str(item.get("skill_code") or item.get("code") or "")
                if any(str(r.get("skill_code")) == code for r in skill_check_results):
                    continue
                resolved = resolve_check(
                    skill_code=code or "general",
                    difficulty=item.get("difficulty"),
                    dc=item.get("dc"),
                    player_stats=stats if isinstance(stats, dict) else {},
                    player_skills=skills if isinstance(skills, list) else [],
                    opposition=item.get("opposition"),
                    settings=check_cfg,
                    context_note=str(item.get("context_note") or model_input)[:400],
                    weapon_or_tool=str(item.get("weapon_or_tool") or ""),
                )
                skill_check_results.append(resolved)
                result = apply_check_to_turn(result, resolved)
        if skill_check_results:
            result["skill_checks"] = skill_check_results
            result["_skill_check_ui"] = {
                "show": bool(check_cfg.get("show_rolls_in_ui", True)),
                "checks": skill_check_results,
            }
            social_bits = [
                f"{c.get('skill_code')}:{c.get('outcome')}→{c.get('social_attitude')}"
                for c in skill_check_results
                if c.get("social_attitude")
            ]
            if social_bits:
                result["resolved_social"] = social_bits
    except Exception:
        pass

    # Naming repair. The contract above asks the model to state the name; this
    # is what makes it true. A 100-turn probe showed the model will happily
    # write "the name you read brings a weight to your chest" and never say it,
    # so the answer is resolved server-side and appended when the prose dodges.
    # Runs on the fallback path too -- deterministic narration dodges as well.
    naming_repair: dict[str, Any] | None = None
    try:
        from app.naming import enforce_named_answer

        _naming = resolve_turn_naming(context, model_input)
        if _naming.get("asked") and _naming.get("name"):
            # The prose may live in narration, in narration_segments, or both --
            # the fallback path fills only the segments. Writing `narration`
            # alone silently lost the repair: the payload and the journal are
            # rebuilt from the segments.
            fixed, repaired = enforce_named_answer(_narration_text_of(result), _naming)
            if repaired:
                _set_narration_text(result, fixed)
            naming_repair = {
                "subject": _naming.get("subject"),
                "name": _naming.get("name"),
                "source": _naming.get("source"),
                "repaired": bool(repaired),
            }
    except Exception:
        naming_repair = None

    # Prose says the player pocketed something and the ops never granted it.
    # Injected before apply_turn so the ordinary inventory pipeline handles it.
    acquisitions: list[str] = []
    try:
        acquisitions = ground_acquisitions(result, _narration_text_of(result), context)
    except Exception:
        acquisitions = []

    # Was a remembered specific owed, and did the prose state it? Recomputed here
    # rather than read off the turn dict: the handoff cleanups strip underscore
    # keys, and this has to be true of the prose that actually shipped.
    recall_check: dict[str, Any] | None = None
    try:
        _rc = check_recall_specifics(
            (prompt_context or {}).get("recall_contract"), _narration_text_of(result)
        )
        if _rc.get("required"):
            recall_check = _rc
    except Exception:
        recall_check = None

    # Pin each NPC's pronouns from the first prose that commits to them, so the
    # next turn's contract can state it instead of letting the model re-decide.
    try:
        with connect() as _conn_pron:
            bind_npc_pronouns(_conn_pron, _narration_text_of(result))
    except Exception:
        pass

    actual_player_input = journal_input if journal_input is not None else player_input
    state = apply_turn(
        result,
        actual_player_input,
        used_fallback=used_fallback,
        fallback_reason=fallback_reason,
        input_kind=input_kind,
        prompt_context=prompt_context,
    )
    # apply_turn annotates the state it returns; later code re-reads state from
    # the database on some paths (injuries), which silently dropped these on
    # about half the turns. Keep them locally and re-attach after any refresh.
    turn_telemetry = {
        key: (state or {}).get(key)
        for key in ("dice_rolls", "movement", "voice_check")
        if isinstance(state, dict) and state.get(key)
    }
    if ability_use_pack:
        result["ability_use"] = {
            "ok": ability_use_pack.get("ok"),
            "blocked": ability_use_pack.get("blocked"),
            "ability": ability_use_pack.get("ability"),
            "reasons": ability_use_pack.get("reasons") or [],
            "cost": ability_use_pack.get("cost"),
            "cooldown": ability_use_pack.get("cooldown"),
            "debuffs": ability_use_pack.get("debuffs") or [],
            "resources_after": ability_use_pack.get("after"),
        }
    if action_spend_pack:
        result["action_spend"] = {
            "ok": action_spend_pack.get("ok"),
            "blocked": action_spend_pack.get("blocked"),
            "kind": action_spend_pack.get("kind"),
            "reasons": action_spend_pack.get("reasons") or [],
            "delta": action_spend_pack.get("delta"),
            "collapse": action_spend_pack.get("collapse"),
            "resources_after": action_spend_pack.get("after"),
        }
    # Force events that were injected into a normal turn are done after narration.
    for ev in forced_events:
        try:
            if ev.get("id"):
                resolve_world_event(int(ev["id"]), status="resolved")
        except Exception:
            pass
    # Store lasting conditions on player via settings when injuries fired.
    try:
        if skill_check_results:
            from app.db import connect as _db_connect

            injuries = [c.get("injury") for c in skill_check_results if isinstance(c.get("injury"), dict)]
            if injuries:
                with _db_connect() as conn:
                    row = conn.execute("SELECT value FROM settings WHERE key = 'player_conditions'").fetchone()
                    existing = []
                    if row:
                        try:
                            existing = json.loads(row["value"] or "[]")
                        except Exception:
                            existing = []
                    if not isinstance(existing, list):
                        existing = []
                    for inj in injuries:
                        existing.append(
                            {
                                "id": f"inj_{inj.get('limb')}_{_current_turn_number()}",
                                "name": f"Injured {inj.get('limb')}",
                                "summary": inj.get("summary"),
                                "penalties": inj.get("combat_penalty") or {},
                                "severe": bool(inj.get("severe")),
                                "turn": _current_turn_number(),
                            }
                        )
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value) VALUES ('player_conditions', ?)",
                        (json.dumps(existing[-40:], ensure_ascii=True),),
                    )
                state = get_state(include_hidden=False)
    except Exception:
        pass
    if isinstance(state, dict):
        for key, value in turn_telemetry.items():
            state.setdefault(key, value)
        if naming_repair:
            state.setdefault("naming", naming_repair)
        if recall_check:
            state.setdefault("recall", recall_check)
        if acquisitions:
            state.setdefault("acquisitions", acquisitions)
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
    model_usage = list(result.get("_model_usage") or [])
    model_trace_steps = result.get("_model_trace") or []
    pipeline_meta = result.get("_narration_pipeline") if isinstance(result.get("_narration_pipeline"), dict) else None
    result.pop("_model_trace", None)
    # Keep turn payload lean for the client; full dump lives in the trace file.
    result.pop("_model_usage", None)
    result.pop("_narration_pipeline", None)
    rewards = _turn_reward_summary(context, state, result)
    narration_chars = len(_narration_text(result) or str(result.get("narration") or ""))
    trace_name = Path(debug_trace_path).name if debug_trace_path else ""
    debug_bundle = {
        "turn": _current_turn_number(),
        "input_kind": input_kind,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason or "",
        "self_check": result.get("self_check") if isinstance(result.get("self_check"), dict) else {},
        "model_usage": model_usage,
        "pipeline_phases": [
            {
                "phase": step.get("phase"),
                "event": step.get("event"),
                "error": step.get("error"),
            }
            for step in model_trace_steps
            if isinstance(step, dict)
        ][-40:],
        "narration_pipeline": pipeline_meta,
        "narration_chars": narration_chars,
        "trace_path": debug_trace_path or "",
        "trace_name": trace_name,
    }
    # Travel gate: AI may set travel.ready / travel_ready; else auto-heuristic.
    travel_ready = True
    try:
        travel_block = result.get("travel") if isinstance(result.get("travel"), dict) else {}
        if "ready" in travel_block:
            travel_ready = bool(travel_block.get("ready"))
        elif "travel_ready" in result:
            travel_ready = bool(result.get("travel_ready"))
        else:
            # Auto: lock during active combat resolution; unlock when scene looks resolved.
            combat = (result.get("_deterministic_combat") or mechanics_context.get("combat") or {}) if isinstance(mechanics_context, dict) else {}
            status = str((combat.get("status") if isinstance(combat, dict) else "") or "").lower()
            if status in {"active", "ongoing", "engaged"}:
                travel_ready = False
            # Player move this turn implies they already walked.
            player_patch = result.get("player") if isinstance(result.get("player"), dict) else {}
            if player_patch.get("move_to_location") or player_patch.get("move_to_location_code"):
                travel_ready = False
            # Explicit scene_plan goal "resolve" / "leave" unlocks
            plan = result.get("scene_plan") if isinstance(result.get("scene_plan"), dict) else {}
            goal = str(plan.get("goal") or "").lower()
            if any(token in goal for token in ("leave", "travel", "depart", "move on", "open road")):
                travel_ready = True
            # Opening locks travel until player acts once
            if input_kind == "opening":
                travel_ready = False
        with connect() as conn:
            _set_setting(conn, "travel_ready", bool(travel_ready))
    except Exception:
        travel_ready = True

    # Always persist after a choice so Continue / Load last works.
    autosave_meta = None
    try:
        autosave_meta = autosave_campaign()
    except Exception:
        autosave_meta = None

    payload = {
        "turn": result,
        "state": state,
        "rewards": rewards,
        "used_fallback": used_fallback,
        "fallback_reason": fallback_reason,
        "fallback_notice": _fallback_notice(fallback_reason) if used_fallback else "",
        "input_kind": input_kind,
        "debug_trace_path": debug_trace_path or "",
        "debug": debug_bundle,
        "skill_checks": skill_check_results or result.get("skill_checks") or [],
        # Amounts the server rolled this turn, alongside skill_checks so the UI
        # can show both kinds of dice in one place.
        "dice_rolls": (state or {}).get("dice_rolls") or {},
        # Continuity telemetry: whether the model moved the player itself, the
        # server had to, or a travel turn resolved nowhere; plus point-of-view drift.
        "movement": (state or {}).get("movement") or {},
        "voice_check": (state or {}).get("voice_check") or {},
        # Which name answered a naming demand, where it came from, and whether
        # the prose had to be repaired to say it.
        "naming": (state or {}).get("naming") or {},
        # Whether the prose owed a remembered name/amount and whether it stated it.
        "recall": (state or {}).get("recall") or {},
        # Items the prose said the player took that the ops never granted.
        "acquisitions": (state or {}).get("acquisitions") or [],
        "travel_ready": bool(travel_ready),
        "travel": {
            "ready": bool(travel_ready),
            "hint": (
                "You may choose a destination on the Map."
                if travel_ready
                else "Finish the current scene/event before traveling."
            ),
        },
        "autosave": autosave_meta,
    }
    return payload


def play_opening_turn() -> dict[str, Any]:
    return play_turn(OPENING_SCENE_INPUT, input_kind="opening", journal_input=OPENING_SCENE_JOURNAL)


def _current_turn_number() -> int:
    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
    return int(row["value"]) if row else 0


def play_continue_turn() -> dict[str, Any]:
    if _current_turn_number() <= 0:
        return play_opening_turn()
    # Forced world events can steal Continue (portal opens no matter what).
    forced = consume_due_world_events(force_only=True, limit=1)
    if forced:
        return play_world_event_turn(forced[0], input_kind="event")
    return play_turn(CONTINUE_SCENE_INPUT, input_kind="continue", journal_input=CONTINUE_SCENE_JOURNAL)


# ---------------------------------------------------------------------------
# World-event bus: RNG encounters + forced quest beats share one queue
# ---------------------------------------------------------------------------

def queue_world_event(
    *,
    kind: str,
    summary: str,
    trigger: str = "",
    due_turn: int | None = None,
    force: bool = False,
    priority: int = 5,
    location_id: int | None = None,
    npc_id: int | None = None,
    payload: dict[str, Any] | None = None,
    status: str = "pending",
) -> dict[str, Any]:
    """
    Queue a world event.
    - force=True + due_turn=N: fires on turn N no matter what the player tries
      (walk/wait/continue/action) — e.g. quest portal beside the player.
    - force=False: RNG/background; may fire when due if pulled into a scene.
    """
    kind = str(kind or "custom").strip()[:80] or "custom"
    summary = str(summary or "").strip()[:1400]
    trigger = str(trigger or kind).strip()[:900]
    turn_now = _current_turn_number()
    due = int(due_turn) if due_turn is not None else max(1, turn_now + 1)
    priority = clamp(int(priority), 0, 10)
    payload = payload if isinstance(payload, dict) else {}
    payload.setdefault("kind", kind)
    payload.setdefault("queued_turn", turn_now)
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO gm_events (turn, trigger, summary, status, priority, location_id, npc_id, event_id, kind, due_turn, force, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
            """,
            (
                turn_now,
                trigger,
                summary,
                str(status or "pending")[:40],
                priority,
                location_id,
                npc_id,
                kind,
                due,
                1 if force else 0,
                json.dumps(payload, ensure_ascii=True)[:4000],
            ),
        )
        eid = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM gm_events WHERE id = ?", (eid,)).fetchone()
    return row_to_dict(row) if row else {"id": eid, "kind": kind, "due_turn": due, "force": force}


def queue_quest_stage_event(
    stage_id: str,
    *,
    kind: str = "quest_force",
    summary: str = "",
    force: bool = True,
    due_in_turns: int = 1,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Mark a quest stage and force a beat N turns from now (default next turn)."""
    stage_id = str(stage_id or "").strip()[:80]
    turn_now = _current_turn_number()
    due = turn_now + max(0, int(due_in_turns))
    if due <= turn_now:
        due = turn_now  # fire as soon as next scene resolution
    pack = dict(payload or {})
    pack["stage_id"] = stage_id
    pack["player_is_trigger"] = True
    # Force quest stages fully replace the next player/continue/wait turn
    if force:
        pack.setdefault("replace_turn", True)
        pack.setdefault("immutable", True)
    # Persist stage flag for versatile branching
    with connect() as conn:
        stages = _settings(conn).get("quest_stages")
        if not isinstance(stages, dict):
            stages = {}
        stages[stage_id] = {
            "reached_turn": turn_now,
            "due_turn": due,
            "kind": kind,
            "summary": (summary or "")[:400],
            "force": bool(force),
        }
        _set_setting(conn, "quest_stages", stages)
        prow = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        loc_id = int(prow["current_location_id"]) if prow and prow["current_location_id"] else None
    return queue_world_event(
        kind=kind or "quest_stage",
        summary=summary or f"Quest stage '{stage_id}' resolves near the player.",
        trigger=f"quest_stage:{stage_id}",
        due_turn=due,
        force=force,
        priority=9 if force else 5,
        location_id=loc_id,
        payload=pack,
    )


def get_quest_stages() -> dict[str, Any]:
    """Reached stages + pending quest-related bus events (for stage editor UI)."""
    turn = _current_turn_number()
    with connect() as conn:
        stages = _settings(conn).get("quest_stages")
        if not isinstance(stages, dict):
            stages = {}
        rows = conn.execute(
            """
            SELECT * FROM gm_events
            WHERE status IN ('pending', 'active', 'seeded', '')
              AND (
                kind IN ('quest_force', 'quest_portal', 'quest_stage')
                OR trigger LIKE 'quest_stage:%'
                OR kind LIKE 'quest_%'
              )
            ORDER BY force DESC, due_turn ASC, priority DESC, id ASC
            LIMIT 40
            """
        ).fetchall()
        pending = [_gm_row_to_event_pack(row_to_dict(r) or {}) for r in rows]
        # Graph-style ordered list for UI
        ordered = []
        for sid, meta in stages.items():
            if not isinstance(meta, dict):
                meta = {"reached_turn": meta}
            ordered.append(
                {
                    "stage_id": str(sid),
                    "reached_turn": int(meta.get("reached_turn") or 0),
                    "due_turn": int(meta.get("due_turn") or 0),
                    "kind": str(meta.get("kind") or "quest_stage"),
                    "summary": str(meta.get("summary") or ""),
                    "force": bool(meta.get("force", True)),
                }
            )
        ordered.sort(key=lambda s: (s.get("reached_turn") or 0, s.get("stage_id") or ""))
    return {
        "turn": turn,
        "stages": ordered,
        "stages_map": stages,
        "pending_events": pending,
    }


def list_pending_world_events(*, limit: int = 24) -> list[dict[str, Any]]:
    """All non-resolved bus events (for tools UI), not only currently due."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM gm_events
            WHERE status IN ('pending', 'active', 'seeded', '')
            ORDER BY force DESC, due_turn ASC, priority DESC, id ASC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return [_gm_row_to_event_pack(row_to_dict(r) or {}) for r in rows]


def cancel_world_event(event_id: int) -> bool:
    """Soft-cancel a pending bus event (stage editor / tools)."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE gm_events SET status = 'cancelled' WHERE id = ? AND status IN ('pending', 'seeded', '')",
            (int(event_id),),
        )
        return cur.rowcount > 0


def _gm_row_to_event_pack(row: dict[str, Any]) -> dict[str, Any]:
    payload = _json(row.get("payload"), {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "id": row.get("id"),
        "kind": str(row.get("kind") or payload.get("kind") or "custom"),
        "summary": row.get("summary") or "",
        "trigger": row.get("trigger") or "",
        "status": row.get("status") or "pending",
        "priority": int(row.get("priority") or 0),
        "due_turn": int(row.get("due_turn") or 0),
        "force": bool(int(row.get("force") or 0)),
        "location_id": row.get("location_id"),
        "npc_id": row.get("npc_id"),
        "payload": payload,
    }


def list_due_world_events(
    *,
    force_only: bool = False,
    limit: int = 8,
    include_active: bool = True,
) -> list[dict[str, Any]]:
    turn = _current_turn_number()
    # For consume: only pending/seeded so already-active stuck beats need explicit recovery
    # (list API may still show active for tools UI).
    if include_active:
        status_sql = "status IN ('pending', 'active', 'seeded', '')"
    else:
        status_sql = "status IN ('pending', 'seeded', '')"
    with connect() as conn:
        if force_only:
            rows = conn.execute(
                f"""
                SELECT * FROM gm_events
                WHERE {status_sql}
                  AND force = 1
                  AND (due_turn <= ? OR due_turn = 0)
                ORDER BY priority DESC, due_turn ASC, id ASC
                LIMIT ?
                """,
                (turn, max(1, limit)),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT * FROM gm_events
                WHERE {status_sql}
                  AND (due_turn <= ? OR due_turn = 0)
                ORDER BY force DESC, priority DESC, due_turn ASC, id ASC
                LIMIT ?
                """,
                (turn, max(1, limit)),
            ).fetchall()
    return [_gm_row_to_event_pack(row_to_dict(r) or {}) for r in rows]


def consume_due_world_events(*, force_only: bool = False, limit: int = 3) -> list[dict[str, Any]]:
    """Return due pending events and mark them firing (status=active). Does not re-take active rows."""
    due = list_due_world_events(force_only=force_only, limit=limit, include_active=False)
    if not due:
        # Recovery: one stuck active force beat may re-fire after a failed turn
        stuck = list_due_world_events(force_only=force_only, limit=1, include_active=True)
        stuck = [e for e in stuck if str(e.get("status") or "") == "active"]
        return stuck[:1] if stuck else []
    with connect() as conn:
        for ev in due:
            conn.execute(
                "UPDATE gm_events SET status = 'active' WHERE id = ? AND status IN ('pending', 'seeded', '')",
                (int(ev["id"]),),
            )
    return due


def resolve_world_event(event_id: int, *, status: str = "resolved") -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE gm_events SET status = ? WHERE id = ?",
            (str(status)[:40], int(event_id)),
        )


def play_world_event_turn(event_pack: dict[str, Any], *, input_kind: str = "event") -> dict[str, Any]:
    """
    Full scene turn driven by a resolved RNG/force pack (ambush, portal, etc.).
    Database already decided the event; LLM only narrates.
    """
    pack = dict(event_pack or {})
    payload = pack.get("payload") if isinstance(pack.get("payload"), dict) else {}
    kind = str(pack.get("kind") or payload.get("kind") or "custom")
    eid = pack.get("id")
    # Mark bus row active while narrating (map path queues pending then plays immediately)
    if eid:
        try:
            with connect() as conn:
                conn.execute(
                    "UPDATE gm_events SET status = 'active' WHERE id = ? AND status IN ('pending', 'seeded', '')",
                    (int(eid),),
                )
        except Exception:
            pass
    wt = get_world_time()
    shells = payload.get("shells") if isinstance(payload.get("shells"), list) else []
    shell_bits = ",".join(
        f"{s.get('code')}:{s.get('name')}" for s in shells if isinstance(s, dict) and s.get("code")
    )
    force = bool(pack.get("force") or payload.get("force"))
    immutable = bool(payload.get("immutable") or force)
    model_input = (
        f"__event_request__: kind={kind}\n"
        f"force={1 if force else 0} immutable={1 if immutable else 0}\n"
        f"summary: {str(pack.get('summary') or '')[:500]}\n"
        f"trigger: {str(pack.get('trigger') or '')[:200]}\n"
        f"world_time: {wt.get('label')}\n"
        f"payload_keys: {','.join(sorted(payload.keys())[:24])}\n"
        f"shells: {shell_bits or 'none'}\n"
        f"npc_codes: {payload.get('npc_code') or ''}\n"
        "constraints: this event already happened in the world clock/RNG; "
        "narrate it now; do not cancel a force/immutable event; "
        "do not invent player inventory; shells have no deep stats/portraits."
    )
    if kind in {"quest_portal", "quest_force", "quest_stage"}:
        model_input += (
            "\nquest: player is the trigger; place the beat next to them if payload says adjacent; "
            "stage_id=" + str(payload.get("stage_id") or "")
        )
    if kind.startswith("travel_"):
        model_input += (
            f"\ntravel: terrain={payload.get('terrain') or ''} "
            f"hostile_default={payload.get('hostile_default')} "
            f"wary_not_evil={payload.get('wary_not_evil')}"
        )
    journal = f"World event [{kind}]: {str(pack.get('summary') or kind)[:200]}"
    try:
        result = play_turn(model_input, input_kind=input_kind, journal_input=journal)
    except Exception:
        # Leave event active for retry / recovery consume; do not resolve
        raise
    if eid:
        try:
            resolve_world_event(int(eid), status="resolved")
        except Exception:
            pass
    # Reputation: someone helped during a non-hostile / mixed event (or RNG ally in ambush)
    help_rep = None
    try:
        help_rep = _maybe_apply_event_help_reputation(kind=kind, payload=payload, result=result)
    except Exception:
        help_rep = None
    result["world_event"] = {
        "id": eid,
        "kind": kind,
        "force": force,
        "payload": payload,
        "summary": pack.get("summary"),
        "help_reputation": help_rep,
    }
    result["input_kind"] = input_kind
    return result


def _maybe_apply_event_help_reputation(
    *,
    kind: str,
    payload: dict[str, Any],
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    After an event scene, if a local/shell helped the player, repair area/helper rep.
    Hostile ambushes only grant help when a non-hostile shell is listed or model flags help.
    """
    kind = str(kind or "")
    payload = payload if isinstance(payload, dict) else {}
    shells = payload.get("shells") if isinstance(payload.get("shells"), list) else []
    helper = str(payload.get("helper_npc_code") or payload.get("npc_code") or "").strip()
    # Prefer explicit helper; else first shell that isn't pure ambush bandit
    if not helper:
        for s in shells:
            if not isinstance(s, dict):
                continue
            att = str(s.get("attitude") or "").lower()
            role = str(s.get("role") or s.get("kind") or "").lower()
            if att in {"hostile", "antagonistic"} or "bandit" in role:
                continue
            if s.get("code"):
                helper = str(s.get("code"))
                break
    hostile_default = bool(payload.get("hostile_default"))
    # Travel traveler / civilian base / quests: help is plausible
    friendly_kinds = {
        "travel_traveler",
        "travel_hidden_base",
        "quest_portal",
        "quest_force",
        "quest_stage",
        "discovery",
        "rumor_spike",
    }
    helped = False
    if kind in friendly_kinds or payload.get("wary_not_evil"):
        helped = True
    elif kind in {"travel_ambush", "travel_wild"}:
        # 30% chance a shell sided with the player (seeded)
        seed = int(payload.get("outcome_seed") or 0)
        if helper and (seed % 10) < 3:
            helped = True
        # Model can signal help
        narr = str((result or {}).get("narration") or _narration_text(result or {}) or "").lower()
        if any(w in narr for w in ("helped you", "came to your aid", "sided with you", "pulled you free")):
            helped = True
    elif payload.get("helped_player") is True:
        helped = True
    if not helped:
        return None
    # Hostile-only packs without a helper code: skip
    if hostile_default and not helper and kind.startswith("travel_ambush"):
        if (int(payload.get("outcome_seed") or 0) % 10) >= 3:
            return None
    with connect() as conn:
        prow = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        loc_id = int(prow["current_location_id"]) if prow and prow["current_location_id"] else None
        # If no helper, still small area bump for surviving with local goodwill
        if not helper and shells:
            helper = str(shells[0].get("code") or "")
        rep = apply_event_help_reputation(
            conn,
            location_id=loc_id,
            helper_npc_code=helper,
            helped_player=True,
        )
        try:
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (
                    _turn_value(conn),
                    "reputation",
                    f"Event help rep: helper={helper or 'none'} area={rep.get('area')}"[:900],
                ),
            )
        except Exception:
            pass
        return rep


def queue_travel_encounter_event(travel: dict[str, Any], travel_result: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a map travel encounter into a force-now world event + optional scene."""
    enc = (travel_result or {}).get("encounter") or (travel or {}).get("encounter") or {}
    if not enc.get("happened"):
        return None
    kind_map = {
        "bandit_ambush": "travel_ambush",
        "wild_threat": "travel_wild",
        "hidden_base": "travel_hidden_base",
        "traveler": "travel_traveler",
    }
    raw_kind = str(enc.get("kind") or "wild_threat")
    kind = kind_map.get(raw_kind, "travel_ambush")
    shells = (travel_result or {}).get("shells") or []
    payload = {
        "kind": kind,
        "terrain": (travel or {}).get("terrain"),
        "minutes": (travel or {}).get("minutes"),
        "hostile_default": enc.get("hostile_default"),
        "wary_not_evil": enc.get("wary_not_evil"),
        "outcome_seed": enc.get("outcome_seed"),
        "npc_code": enc.get("npc_code"),
        "npc_name": enc.get("npc_name"),
        "shells": shells,
        "from": (travel or {}).get("from"),
        "to": (travel or {}).get("to"),
        "immutable": True,
        "replace_turn": True,
        "requires_scene": True,
    }
    summary = {
        "travel_ambush": "Bandits try the path — organized pressure on the road.",
        "travel_wild": "Something wild presses from the terrain.",
        "travel_hidden_base": "A hidden camp reacts to the player's approach.",
        "travel_traveler": "A traveler is encountered; reaction depends on checks and traits.",
    }.get(kind, "A travel event interrupts the walk.")
    turn_now = _current_turn_number()
    return queue_world_event(
        kind=kind,
        summary=summary,
        trigger=f"travel:{raw_kind}",
        due_turn=turn_now,  # fire immediately on this walk
        force=True,
        priority=8,
        payload=payload,
    )


_RULER_ROLE_BY_CLASS = {
    "city": "city reeve",
    "town": "town head",
    "village": "village elder",
    "harbor": "harbor master",
    "colony": "colony overseer",
    "station": "station chief",
    "farm": "landholder",
    "shipyard": "yard master",
}


def ensure_settlement_ruler(
    conn,
    *,
    location_id: int,
    settlement: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """
    On first visit to a settlement blob, seed ruler + officers + workers (power ranks).
    Idempotent via settings key settlement_ruler:{id}.
    """
    if not settlement or not location_id:
        return None
    sid = str(settlement.get("id") or "").strip()
    if not sid:
        return None
    flag_key = f"settlement_ruler:{sid}"
    settings = _settings(conn)
    if settings.get(flag_key):
        row = conn.execute(
            """
            SELECT * FROM npcs
            WHERE location_id = ? AND power_rank >= 40
            ORDER BY power_rank DESC, id ASC LIMIT 1
            """,
            (int(location_id),),
        ).fetchone()
        return row_to_dict(row) if row else None

    sclass = str(settlement.get("state") or settlement.get("class") or "town").lower()
    power = int(settlement.get("ruler_power_rank") or 50)
    power = max(30, min(100, power))
    role = _RULER_ROLE_BY_CLASS.get(sclass, "local authority")
    rng = random.Random(name_seed("ruler", sid))
    surnames = ["Vale", "Reed", "Cross", "Hale", "Morn", "Wick", "Ash", "Quay"]
    summary = f"Holds authority in this {sclass}; power rank {power}."
    code = ""
    name = ""
    cur = None
    for attempt in range(12):
        code = _next_alpha_code(conn, "npcs")
        # npcs is UNIQUE(location_id, name), so the insert retry below cannot
        # catch a duplicate in a different place. Check the whole world.
        base = f"{rng.choice(_SHELL_NAME_PARTS_A)} {rng.choice(surnames)}"
        name = base if attempt == 0 else f"{base} {sid[-4:]}{attempt}"
        if _person_name_taken(conn, name):
            name = unique_person_name(conn, name_seed("ruler", sid, attempt))
        try:
            cur = conn.execute(
                """
                INSERT INTO npcs (
                    code, location_id, name, race, role, summary, attitude,
                    personality, likes, principles, dislikes, trust, known_facts,
                    rank, stat_profile, skill_profile, health, max_health,
                    presence, power_rank, portrait_eligible, shell
                ) VALUES (?, ?, ?, 'human', ?, ?, 'neutral', 'measured', 'order', 'duty', 'chaos', 0, '[]',
                          'C', '{"authority":"high"}', '{"etiquette":"C","insight":"D"}', 12, 12,
                          'full', ?, 1, 0)
                """,
                (code, int(location_id), name[:80], role[:80], summary[:400], power),
            )
            break
        except Exception:
            if attempt >= 11:
                raise
            continue
    if cur is None:
        return None
    hierarchy = [{"code": code, "name": name, "role": role, "power_rank": power, "tier": "ruler"}]

    # Officers (mid rank) and workers (low rank) under the ruler
    officer_roles = {
        "city": ["guard captain", "clerk of stores"],
        "town": ["constable", "market warden"],
        "village": ["reeve's hand", "watch volunteer"],
        "harbor": ["dock sergeant", "customs runner"],
        "colony": ["gate officer", "ration clerk"],
        "station": ["shift lead", "security aide"],
    }.get(sclass, ["deputy", "scribe"])
    worker_roles = {
        "city": ["porter", "street cleaner"],
        "town": ["carter", "apprentice"],
        "village": ["farm hand", "herder"],
        "harbor": ["stevedore", "net mender"],
        "colony": ["laborer", "runner"],
        "station": ["technician", "mess hand"],
    }.get(sclass, ["laborer", "helper"])

    def _seed_local(nrole: str, pr: int, presence: str = "event_worthy") -> dict[str, Any]:
        shell = 1 if presence in {"nameless", "background"} else 0
        nname = ""
        ncode = ""
        for attempt in range(12):
            ncode = _next_alpha_code(conn, "npcs")
            base = f"{rng.choice(_SHELL_NAME_PARTS_A)}{rng.choice(_SHELL_NAME_PARTS_B)}"
            nname = base if attempt == 0 else f"{base} {nrole.split()[0][:6]}{attempt}"
            if _person_name_taken(conn, nname):
                nname = unique_person_name(conn, name_seed("local_cast", nrole, attempt))
            try:
                conn.execute(
                    """
                    INSERT INTO npcs (
                        code, location_id, name, race, role, summary, attitude,
                        personality, likes, principles, dislikes, trust, known_facts,
                        rank, stat_profile, skill_profile, health, max_health,
                        presence, power_rank, portrait_eligible, shell
                    ) VALUES (?, ?, ?, 'human', ?, ?, 'neutral', '', '', '', '', 0, '[]',
                              'D', '{}', '{}', 8, 8, ?, ?, ?, ?)
                    """,
                    (
                        ncode,
                        int(location_id),
                        nname[:80],
                        nrole[:80],
                        f"Works under local authority in this {sclass}."[:400],
                        presence,
                        max(1, min(99, pr)),
                        0 if shell else 1,
                        shell,
                    ),
                )
                break
            except Exception:
                if attempt >= 11:
                    raise
                continue
        return {"code": ncode, "name": nname, "role": nrole, "power_rank": pr, "tier": "staff"}

    for i, orole in enumerate(officer_roles[:2]):
        hierarchy.append(_seed_local(orole, max(15, power - 20 - i * 5), "event_worthy"))
    for i, wrole in enumerate(worker_roles[:2]):
        hierarchy.append(_seed_local(wrole, max(5, power // 4 - i * 2), "background"))

    _set_setting(
        conn,
        flag_key,
        {
            "npc_code": code,
            "name": name,
            "power_rank": power,
            "settlement_id": sid,
            "hierarchy": hierarchy,
        },
    )
    row = conn.execute("SELECT * FROM npcs WHERE id = ?", (cur.lastrowid,)).fetchone()
    out = row_to_dict(row) if row else {"code": code, "name": name, "power_rank": power, "role": role}
    if isinstance(out, dict):
        out["hierarchy"] = hierarchy
    return out


def apply_map_travel_step(travel: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    After map move: advance world clock, seed rulers, optionally spawn encounter shells.
    Returns travel resolution pack for UI / optional scene.
    """
    travel = travel if isinstance(travel, dict) else {}
    minutes = max(0, int(travel.get("minutes") or 0))
    encounter = travel.get("encounter") if isinstance(travel.get("encounter"), dict) else {}
    settlement = travel.get("settlement") if isinstance(travel.get("settlement"), dict) else None
    out: dict[str, Any] = {
        "minutes": minutes,
        "time": None,
        "ruler": None,
        "encounter": encounter,
        "shells": [],
        "weather": None,
        "weather_changed": False,
        "weather_announce": None,
        "ambient": "",
    }
    with connect() as conn:
        opts = ((context or {}).get("settings") or {}).get("playthrough_options") or {}
        if not isinstance(opts, dict):
            opts = _settings(conn).get("playthrough_options") or {}
        if not isinstance(opts, dict):
            opts = {}

        # Preview travel cost BEFORE advancing time — hard-block if too exhausted
        travel_blocked = False
        spend_preview: dict[str, Any] = {}
        if minutes > 0:
            try:
                from app.player_resources import apply_travel_spend, get_player_resources

                inv_sum = (context or {}).get("inventory_summary") or {}
                cap = max(1.0, float(inv_sum.get("weight_capacity") or 60.0))
                eff = max(0.0, float(inv_sum.get("effective_weight") or 0.0))
                load_ratio = min(2.2, eff / cap) if cap else 0.4
                wx0 = get_weather(conn)
                kind0 = str((wx0 or {}).get("kind") or "clear")
                wmult = float(WEATHER_TRAVEL_MULT.get(kind0, 1.0))
                strength = max(0.0, min(1.0, float(_float((wx0 or {}).get("strength"), 0.0))))
                if wmult > 1.0:
                    wmult = 1.0 + (wmult - 1.0) * (0.5 + 0.5 * strength)
                if travel.get("weather_mult"):
                    try:
                        wmult = float(travel.get("weather_mult") or wmult)
                    except (TypeError, ValueError):
                        pass
                player = (context or {}).get("player") if isinstance((context or {}).get("player"), dict) else {}
                stats = player.get("effective_stats") if isinstance(player.get("effective_stats"), dict) else None
                # Dry-run via apply with hard_block; spend only if ok (transaction-like)
                before_res = get_player_resources(conn, opts)
                spend_preview = apply_travel_spend(
                    conn,
                    terrain=str(travel.get("terrain") or ""),
                    minutes=minutes,
                    load_ratio=load_ratio,
                    weather_mult=wmult,
                    options=opts,
                    stats=stats,
                    hard_block=True,
                )
                if spend_preview.get("blocked"):
                    travel_blocked = True
                    # Undo accidental spend if any (hard_block path does not spend)
                    out["resources"] = before_res
                    out["resource_spend"] = {
                        "blocked": True,
                        "reasons": spend_preview.get("reasons") or ["insufficient_energy"],
                        "travel": spend_preview.get("travel"),
                        "collapse": spend_preview.get("collapse"),
                    }
                    out["blocked"] = True
                    out["block_reason"] = "insufficient_energy"
                    out["weather"] = wx0
            except Exception:
                spend_preview = {}

        if travel_blocked:
            # Do not advance clock, spawn encounters, or journal this step
            return out

        if minutes > 0:
            out["time"] = advance_world_time(conn, minutes)
            out["weather"] = (out["time"] or {}).get("weather") or get_weather(conn)
            out["weather_changed"] = bool((out["time"] or {}).get("weather_changed"))
            out["weather_announce"] = (out["time"] or {}).get("weather_announce")
        else:
            out["weather"] = get_weather(conn)

        # Terrain / weather / load energy+fatigue spend (already applied if preview ran)
        if minutes > 0 and spend_preview and not spend_preview.get("blocked"):
            out["resources"] = spend_preview.get("after") or {}
            out["resource_spend"] = {
                "deltas": spend_preview.get("deltas"),
                "travel": spend_preview.get("travel"),
                "soft_blocked": spend_preview.get("soft_blocked"),
                "reasons": spend_preview.get("reasons") or [],
                "collapse": spend_preview.get("collapse"),
            }
        elif minutes > 0 and not spend_preview:
            try:
                from app.player_resources import apply_travel_spend

                inv_sum = (context or {}).get("inventory_summary") or {}
                cap = max(1.0, float(inv_sum.get("weight_capacity") or 60.0))
                eff = max(0.0, float(inv_sum.get("effective_weight") or 0.0))
                load_ratio = min(2.2, eff / cap) if cap else 0.4
                wx = out.get("weather") if isinstance(out.get("weather"), dict) else get_weather(conn)
                kind = str((wx or {}).get("kind") or "clear")
                wmult = float(WEATHER_TRAVEL_MULT.get(kind, 1.0))
                player = (context or {}).get("player") if isinstance((context or {}).get("player"), dict) else {}
                stats = player.get("effective_stats") if isinstance(player.get("effective_stats"), dict) else None
                spend = apply_travel_spend(
                    conn,
                    terrain=str(travel.get("terrain") or ""),
                    minutes=minutes,
                    load_ratio=load_ratio,
                    weather_mult=wmult,
                    options=opts,
                    stats=stats,
                )
                out["resources"] = spend.get("after") or {}
                out["resource_spend"] = {
                    "deltas": spend.get("deltas"),
                    "travel": spend.get("travel"),
                    "soft_blocked": spend.get("soft_blocked"),
                    "reasons": spend.get("reasons") or [],
                }
            except Exception:
                out["resources"] = None

        loc = (context or {}).get("current_location") or {}
        # Prefer player location id from DB
        prow = conn.execute("SELECT current_location_id FROM player WHERE id = 1").fetchone()
        loc_id = int(prow["current_location_id"]) if prow and prow["current_location_id"] else loc.get("id")
        if settlement and loc_id:
            ruler = ensure_settlement_ruler(conn, location_id=int(loc_id), settlement=settlement)
            if ruler:
                out["ruler"] = {
                    "code": ruler.get("code"),
                    "name": ruler.get("name"),
                    "role": ruler.get("role"),
                    "power_rank": ruler.get("power_rank"),
                    "hierarchy": ruler.get("hierarchy") or [],
                }
        # Pass discovery flags for ambient / UI
        if travel.get("base_discovered"):
            out["base_discovered"] = True
            out["hidden_base"] = travel.get("hidden_base")
        if encounter.get("happened") and loc_id:
            tier = str(encounter.get("participant_tier") or "nameless")
            role = {
                "bandit_ambush": "bandit",
                "wild_threat": "wild threat",
                "hidden_base": "camp lookout",
                "traveler": "traveler",
            }.get(str(encounter.get("kind") or ""), "passerby")
            # Hostile-by-default bandits are still shells until promoted by story
            presence = "nameless" if tier == "nameless" else "event_worthy"
            shell = create_shell_npc(
                conn,
                int(loc_id),
                presence=presence if presence in {"nameless", "background", "event_worthy"} else "nameless",
                power_rank=5 if encounter.get("hostile_default") else 2,
                role=role,
                seed=int(encounter.get("outcome_seed") or 0),
            )
            if shell:
                # Mark attitude for wary-but-not-evil
                attitude = "hostile" if encounter.get("hostile_default") else ("wary" if encounter.get("wary_not_evil") else "neutral")
                try:
                    conn.execute(
                        "UPDATE npcs SET attitude = ? WHERE code = ?",
                        (attitude, shell.get("code")),
                    )
                except Exception:
                    pass
                out["shells"].append(
                    {
                        "code": shell.get("code"),
                        "name": shell.get("name"),
                        "presence": shell.get("presence"),
                        "attitude": attitude,
                        "kind": encounter.get("kind"),
                    }
                )
                encounter = dict(encounter)
                encounter["npc_code"] = shell.get("code")
                encounter["npc_name"] = shell.get("name")
                out["encounter"] = encounter
        if minutes > 0 or out.get("shells") or out.get("ruler"):
            bits = [f"Walked {minutes}m on {travel.get('terrain') or 'terrain'}."]
            if out.get("time"):
                bits.append(f"Time {out['time']['before']['label']} → {out['time']['after']['label']}.")
            if encounter.get("happened"):
                bits.append(f"Encounter: {encounter.get('kind')}.")
            if out.get("ruler"):
                bits.append(f"Authority present: {out['ruler'].get('name')}.")
            conn.execute(
                "INSERT INTO journal (turn, kind, content) VALUES (?, ?, ?)",
                (_turn_value(conn), "travel", " ".join(bits)[:1400]),
            )
    # Ambush / path event → queue force-now world event for a full scene turn
    out["needs_scene"] = False
    out["queued_event"] = None
    if encounter.get("happened"):
        try:
            queued = queue_travel_encounter_event(travel, out)
            out["queued_event"] = queued
            out["needs_scene"] = bool(queued)
        except Exception:
            out["needs_scene"] = bool(encounter.get("happened"))
    # Non-blocking ambient color (never stops free walking)
    try:
        template = build_ambient_move_line(
            travel=travel or {},
            travel_result=out,
            weather=out.get("weather"),
        )
    except Exception:
        template = ""
    out["ambient"] = template
    out["ambient_source"] = "template"
    # Optional short LLM polish (off by default; never blocks movement on failure)
    try:
        with connect() as conn:
            settings = _settings(conn)
    except Exception:
        settings = {}
    if template and ambient_llm_enabled(settings if isinstance(settings, dict) else None):
        try:
            polished = generate_ambient_move_line(
                template,
                travel=travel or {},
                weather=out.get("weather") if isinstance(out.get("weather"), dict) else {},
                settings=settings if isinstance(settings, dict) else {},
            )
            if polished and polished.strip():
                out["ambient"] = polished.strip()
                out["ambient_source"] = "llm" if polished.strip() != template else "template"
        except Exception:
            out["ambient"] = template
            out["ambient_source"] = "template"
    return out


def play_wait_turn(minutes: int, kind: str = "wait") -> dict[str, Any]:
    """
    Spend in-world time at current location. RNG decides events before the LLM narrates.
    kind: wait | meditate | sleep — all recover energy/mana/fatigue at different rates.
    """
    kind_l = str(kind or "wait").strip().lower()
    if kind_l in {"meditate", "meditation", "cultivate", "breathe"}:
        kind_l = "meditate"
    elif kind_l in {"sleep", "rest", "nap", "dawn", "until_dawn"}:
        kind_l = "sleep"
    else:
        kind_l = "wait"

    if _current_turn_number() <= 0:
        # Opening must exist first
        opening = play_opening_turn()
        # Still allow wait after opening in same call? Prefer require opening first.
        if _current_turn_number() <= 0:
            return opening

    # Normalize duration first (supports -1 / dawn / custom 1–1440)
    with connect() as c_norm:
        minutes = normalize_wait_minutes(minutes, c_norm)

    # Forced quest beats interrupt wait: clock still advances so wait is not free cancel.
    forced = consume_due_world_events(force_only=True, limit=1)
    if forced:
        with connect() as c_force:
            advance_world_time(c_force, minutes)
            try:
                from app.player_resources import apply_regen

                opts = _settings(c_force).get("playthrough_options") or {}
                apply_regen(c_force, minutes=minutes, kind=kind_l, options=opts if isinstance(opts, dict) else {})
            except Exception:
                pass
        result = play_world_event_turn(forced[0], input_kind="event")
        result["wait_interrupted"] = True
        result["wait_minutes_applied"] = minutes
        result["wait_kind"] = kind_l
        try:
            result["world_time"] = get_world_time()
        except Exception:
            pass
        return result

    context = get_state(include_hidden=True)
    # Attach map tile if available for danger/crowd
    try:
        from app.tile_world import get_map, local_map_view

        m = get_map(None)
        if m:
            view = local_map_view(m, radius=1)
            player_tile = next(
                (t for t in (view.get("tiles") or []) if isinstance(t, dict) and t.get("is_player")),
                None,
            )
            context["map_tile"] = player_tile or {}
            context["map_seed"] = m.get("seed")
            # Settlement meta for live crowd/danger
            sid = (player_tile or {}).get("settlement_id")
            if sid:
                for sm in m.get("settlements_meta") or []:
                    if str(sm.get("id")) == str(sid):
                        context["settlement_meta"] = sm
                        break
    except Exception:
        pass

    risk = _local_crowd_danger(context)
    with connect() as conn:
        before = get_world_time(conn)
        wx = get_weather(conn)
        danger = min(1.0, risk["danger"] + weather_event_chance_delta(wx))
        seed_bits = (
            int(_float(context.get("map_seed"), 0))
            ^ (before["day"] * 10007)
            ^ (before["minute"] * 17)
            ^ (_current_turn_number() * 131)
            ^ (name_seed(str((context.get("current_location") or {}).get("code") or "")) & 0xFFFF)
        )
        rng_pack = roll_wait_events(
            minutes=minutes,
            crowd=risk["crowd"],
            danger=danger,
            seed=seed_bits,
        )
        rng_pack["weather"] = {"kind": wx.get("kind"), "strength": wx.get("strength"), "label": wx.get("label")}
        time_delta = advance_world_time(conn, minutes)
        after = time_delta["after"]

        # Spawn shell NPCs for events that need a face
        shells: list[dict[str, Any]] = []
        loc_id = (context.get("current_location") or {}).get("id")
        if loc_id:
            for ev in rng_pack.get("events") or []:
                tier = str(ev.get("participant_tier") or "nameless")
                if tier in {"nameless", "background", "event_worthy"}:
                    shell = create_shell_npc(
                        conn,
                        int(loc_id),
                        presence=tier if tier != "event_worthy" else "background",
                        power_rank=0 if tier == "nameless" else 5,
                        role="passerby" if tier == "nameless" else "bystander",
                        seed=int(ev.get("outcome_seed") or 0),
                    )
                    if shell:
                        shells.append(shell)
                        ev["npc_code"] = shell.get("code")
                        ev["npc_name"] = shell.get("name")

        _pacing_set(conn, "last_wait_rng", json.dumps(rng_pack, ensure_ascii=True))

        # Recover energy / mana / lower fatigue by wait kind
        regen_pack: dict[str, Any] = {}
        try:
            from app.player_resources import apply_regen, resources_prompt_block

            opts = _settings(conn).get("playthrough_options") or {}
            if not isinstance(opts, dict):
                opts = ((context.get("settings") or {}).get("playthrough_options") or {})
            regen_pack = apply_regen(
                conn,
                minutes=minutes,
                kind=kind_l,
                options=opts if isinstance(opts, dict) else {},
            )
        except Exception:
            regen_pack = {}

    # Structured model input — outcomes already decided
    event_lines = []
    for ev in rng_pack.get("events") or []:
        bit = f"{ev.get('kind')}:{ev.get('participant_tier')}"
        if ev.get("npc_code"):
            bit += f"@{ev.get('npc_code')}"
        event_lines.append(bit)
    res_after = (regen_pack or {}).get("after") or {}
    res_delta = (regen_pack or {}).get("deltas") or {}
    try:
        from app.player_resources import resources_prompt_block

        res_block = resources_prompt_block(res_after) if res_after else ""
    except Exception:
        res_block = ""
    kind_label = {"wait": "wait", "meditate": "meditate", "sleep": "sleep"}.get(kind_l, "wait")
    model_input = (
        f"__wait_request__: kind={kind_label} minutes={minutes}\n"
        f"world_time_before: {before.get('label')}\n"
        f"world_time_after: {after.get('label')}\n"
        f"rng_event_count: {rng_pack.get('event_count')}\n"
        f"rng_events: {', '.join(event_lines) if event_lines else 'none'}\n"
        f"crowd: {risk['crowd']} danger: {risk['danger']}\n"
        f"resource_regen: energy{int(res_delta.get('energy') or 0):+d} mana{int(res_delta.get('mana') or 0):+d} "
        f"fatigue{int(res_delta.get('fatigue') or 0):+d}\n"
        f"{res_block}\n"
        f"constraints: narrate this {kind_label} only; do not invent extra major events; "
        "nameless/background codes are shells (no portrait, no deep inventory/stats); "
        "do not invent player inventory; reflect recovery only as listed in resource_regen."
    )
    wait_verb = {"wait": "Waited", "meditate": "Meditated", "sleep": "Slept"}.get(kind_l, "Waited")
    journal = (
        f"{wait_verb} {minutes} minute(s). {before.get('label')} → {after.get('label')}. "
        f"Events: {rng_pack.get('event_count')}."
    )
    payload = play_turn(model_input, input_kind="wait", journal_input=journal)
    payload["world_time"] = after
    payload["wait"] = {
        "minutes": minutes,
        "kind": kind_l,
        "before": before,
        "after": after,
        "rng": rng_pack,
        "shells": [{"code": s.get("code"), "name": s.get("name"), "presence": s.get("presence")} for s in shells],
        "resources": res_after,
        "resource_regen": res_delta,
    }
    # Refresh state time on payload if nested
    if isinstance(payload.get("state"), dict):
        payload["state"]["world_time"] = after
        if res_after:
            payload["state"]["resources"] = res_after
            if isinstance(payload["state"].get("player"), dict):
                for key in ("energy", "max_energy", "mana", "max_mana", "fatigue", "max_fatigue"):
                    if key in res_after:
                        payload["state"]["player"][key] = res_after[key]
    return payload


def start_playthrough_with_opening(options: dict[str, Any]) -> dict[str, Any]:
    state = start_playthrough(options)
    opening = play_opening_turn()
    # Surface gear fact-check to the UI (popup when items were stripped/deferred)
    try:
        opts = ((state or {}).get("settings") or {}).get("playthrough_options") or {}
        logic = opts.get("starter_logic") if isinstance(opts, dict) else None
        if isinstance(logic, dict) and logic:
            opening["starter_logic"] = logic
            if isinstance(opening.get("state"), dict):
                # ensure nested state also carries it
                p_opts = ((opening["state"].get("settings") or {}).get("playthrough_options") or {})
                if isinstance(p_opts, dict) and not p_opts.get("starter_logic"):
                    p_opts = dict(p_opts)
                    p_opts["starter_logic"] = logic
                    settings = dict(opening["state"].get("settings") or {})
                    settings["playthrough_options"] = p_opts
                    opening["state"]["settings"] = settings
    except Exception:
        pass
    return opening


def get_input_suggestions(instruction: str = "") -> dict[str, Any]:
    context = get_state(include_hidden=False)
    prompt_context = build_prompt_context(context, f"suggest next player inputs {instruction}".strip())
    return generate_input_suggestions(prompt_context, instruction)
