from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator

from app.db import connect
from app.idea_bank import idea_sparks_for_prompt
from app.setup_composer import (
    COMPOSER_FIELD_ORDER,
    apply_keyword_intent,
    empty_intent,
    field_contamination_reasons,
    field_contract,
    field_is_contaminated,
    intent_slice_for_field,
    merge_intent_plans,
    opening_feel_prompt_block,
    sanitize_setup_fields,
    session_theme_from_intent,
    structural_fallback,
    theme_prompt_block,
)
from app.prompts import (
    COMPACT_SYSTEM_PROMPT,
    COMPACT_VERIFY_PROMPT,
    SYSTEM_PROMPT,
    VERIFY_PROMPT,
    build_user_prompt,
    build_verify_prompt,
)
from app.turn_dsl import (
    DSL_SYSTEM_PROMPT,
    TurnDslError,
    build_dsl_user_prompt,
    draft_mode_enabled,
    parse_dsl_turn,
)
from app.narration_pipeline import (
    ops_summary_from_turn,
    parse_consolidated_paragraphs,
    pipeline_enabled,
    run_narration_pipeline,
)


class LlmError(RuntimeError):
    pass


class MalformedJsonError(LlmError):
    def __init__(self, message: str, content: str = "", repair_error: str = "") -> None:
        super().__init__(message)
        self.content = content
        self.repair_error = repair_error


_managed_llama_process: subprocess.Popen | None = None
_managed_llama_base_url = ""
_managed_llama_logs: dict[str, str] = {}


DEFAULT_GGUF_MODEL = ""
DEFAULT_CONTEXT_TOKENS = 8192
DEFAULT_RESPONSE_TOKEN_CAP = 1500
DEFAULT_RESPONSE_HARD_CAP = 2000
MIN_TURN_NARRATION_CHARS = 1000
TARGET_TURN_NARRATION_CHARS = 1500
MAX_TURN_NARRATION_CHARS = 2400
VERIFICATION_POLICY_VERSION = "V0.1.0"
DEFAULT_VERIFY_SKIP_CERTAINTY = 0.88
DEFAULT_VERIFY_MEMORY_CERTAINTY = 0.86
SUGGESTION_TARGET_CHARS = 100
SUGGESTION_MAX_CHARS = 120
OPTIONAL_IDENTITY_FIELDS = {"player_public_name", "player_title"}
REFERENCE_CODE_PATTERN = re.compile(r"\[\[([A-Z]{1,3}|L\d+|I\d+|E\d+)\]\]", re.IGNORECASE)
HIGH_RISK_TURN_CHANGE_KEYS = {
    "skill_changes",
    "inventory_changes",
    "equipment_slots",
    "equipment_changes",
    "inventory_capacity_modifiers",
    "locations",
    "npcs",
    "relationships",
    "events",
    "conversations",
    "response_drafts",
    "index_updates",
    "ability_updates",
}
VERIFY_REQUIRED_INTENTS = {"opening_scene", "continue_scene", "conversation", "claim_check", "inventory", "trade", "ability", "training"}
LOW_RISK_SKIP_INTENTS = {"general", "investigation", "rest", "travel", "combat"}
TURN_WRAPPER_KEYS = ("turn", "result", "response", "output")
TURN_NARRATION_KEYS = ("narration", "narrative", "story", "scene_text", "scene", "response", "text", "content", "message", "description", "prose")
TURN_SEGMENT_KEYS = ("narration_segments", "segments", "scene_segments", "response_segments")
TURN_SEGMENT_TEXT_KEYS = ("text", "content", "narration", "narrative", "description", "prose", "body", "scene")
TURN_SEGMENT_LABEL_KEYS = ("label", "title", "name", "type", "kind")
TURN_SHAPE_KEYS = {
    "scene_plan",
    "narration_segments",
    "narration",
    "player",
    "self_check",
    "turn_summary",
    "scene_focus",
    "skill_changes",
    "inventory_changes",
    "equipment_slots",
    "equipment_changes",
    "inventory_capacity_modifiers",
    "locations",
    "npcs",
    "relationships",
    "events",
    "conversations",
    "response_drafts",
    "index_updates",
    "ability_updates",
    "gm_events",
    "journal",
}
TURN_SHAPE_ORDER = (
    "scene_plan",
    "narration_segments",
    "narration",
    "player",
    "self_check",
    "turn_summary",
    "scene_focus",
    "skill_changes",
    "inventory_changes",
    "equipment_slots",
    "equipment_changes",
    "inventory_capacity_modifiers",
    "locations",
    "npcs",
    "relationships",
    "events",
    "conversations",
    "response_drafts",
    "index_updates",
    "ability_updates",
    "gm_events",
    "journal",
)
HANDOFF_BASE_CONTEXT_KEYS = {
    "settings",
    "gm_notes",
    "player",
    "current_location",
    "mechanics_context",
    "verification_policy",
    "turn_plan",
    "action_context",
    "working_set",
    "event_lifecycle",
    "equipment_effects",
    "inventory_summary",
    "active_player_alias",
    "relevant_sources",
    "retrieval",
}
HANDOFF_OPTIONAL_CONTEXT_KEYS = {
    "gm_events",
    "skills",
    "abilities",
    "player_aliases",
    "inventory",
    "equipment_slots",
    "inventory_capacity_modifiers",
    "locations",
    "recognition",
    "relationships",
    "events",
    "conversations",
    "response_drafts",
    "karma_history",
    "turn_summaries",
}
HANDOFF_CONTEXT_LIST_LIMITS = {
    "gm_events": 8,
    "skills": 12,
    "abilities": 12,
    "player_aliases": 6,
    "inventory": 18,
    "equipment_slots": 16,
    "inventory_capacity_modifiers": 10,
    "locations": 6,
    "recognition": 4,
    "relationships": 12,
    "events": 10,
    "conversations": 10,
    "response_drafts": 6,
    "karma_history": 4,
    "relevant_sources": 8,
    "turn_summaries": 8,
}
HANDOFF_TURN_LIST_LIMITS = {
    "narration_segments": 8,
    "skill_changes": 8,
    "inventory_changes": 12,
    "equipment_slots": 8,
    "equipment_changes": 12,
    "inventory_capacity_modifiers": 8,
    "locations": 6,
    "npcs": 10,
    "relationships": 12,
    "events": 12,
    "conversations": 8,
    "response_drafts": 8,
    "index_updates": 12,
    "ability_updates": 8,
    "gm_events": 8,
    "journal": 8,
}
HANDOFF_PLAYER_FIELDS = {
    "health_delta",
    "max_health_delta",
    "xp_delta",
    "gold_delta",
    "level_delta",
    "move_to_location",
    "move_to_location_code",
    "karma_delta",
    "karma_reason",
    "karma_visibility",
}
MISSING_NARRATION_MESSAGE = "Model JSON did not include usable narration text."
PREVIOUS_LIFE_IDENTITY_FIELDS = {"previous_life_age", "previous_life_sex"}
SETUP_RANDOMIZER_FIELD_GROUPS = {
    "character": [
        "backstory_mode",
        "memory_policy",
        "character_backstory",
        "player_name",
        "player_public_name",
        "player_title",
        "player_age",
        "player_sex",
        "hair",
        "facial_features",
        "appearance",
        "starter_equipment",
        "previous_life_age",
        "previous_life_sex",
        "special_ability_origin",
        "special_abilities",
    ],
    "world": [
        "world_style",
        "magic_level",
        "world_races",
        "race_magic_enabled",
        "race_magic_rarity",
        "tech_level",
        "tone",
        "economy",
        "start_location",
        "custom_style",
        "race_magic_rules",
        "race_ability_rules",
    ],
    "people": ["npc_density", "quest_style", "faction_pressure", "npc_stat_scaling", "npc_skill_frequency", "rank_scale"],
    "rules": [
        "difficulty",
        "death_rules",
        "narration_detail",
        "loot_rarity",
        "inventory_weight_limit",
        "inventory_slot_limit",
        "inventory_rules",
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
}
# Shared with frontend via /api/setup/composer — dependency-safe load order.
SETUP_RANDOMIZER_ALL_FIELD_ORDER = list(COMPOSER_FIELD_ORDER)
SETUP_RANDOMIZER_FALLBACKS = {
    "player_name": ["Mara", "Corvin", "Iris Vale", "Ren", "Sable", "Tamsin", "Kael"],
    "player_public_name": ["", "Ash", "River", "Patch", "Northlight", "Second Bell"],
    "player_title": ["", "the Weatherwise", "of Kiln Street", "the Long Listener", "the Spare Key"],
    "player_age": ["17", "19", "24", "31", "middle-aged", "appears 30", "adult"],
    # Sex uses weighted picker in _fallback_sex_value (male/female majority).
    "player_sex": ["female", "male", "", "intersex", "sexless or constructed", "varies by form"],
    "previous_life_age": ["19", "27", "34", "46", "elderly", "unknown"],
    "previous_life_sex": ["female", "male", "", "intersex", "sexless or constructed", "varies by form"],
    "special_ability_origin": ["none", "acquired", "innate"],
    "backstory_mode": ["known", "hidden", "fragmented memories", "reincarnated", "transmigrated", "nameless drifter"],
    "memory_policy": ["known", "ordinary memory", "details emerge through choices", "rumors may be wrong", "private details stay private", "remembers former life"],
    "hair": [
        "short brown hair",
        "long silver braid",
        "messy black hair",
        "cropped sandy hair",
        "wavy auburn hair",
    ],
    "facial_features": [
        "green eyes, light freckles, soft jaw",
        "dark brown eyes, thin scar on left cheek",
        "grey eyes, tired lids, square jaw",
        "hazel eyes, faint laugh lines, straight nose",
    ],
    "appearance": [
        "torso: travel-stained coat; feet: dusty boots; waist: rope coil",
        "torso: plain work tunic; torso: leather apron; hands: work gloves; feet: practical boots",
        "torso: frayed cloak; legs: patched trousers; bag: worn satchel",
        "torso: simple street clothes; feet: cheap shoes; bag: thin travel bag",
    ],
    "starter_equipment": [
        "worn coat, coiled rope, pocket knife, dusty boots, water skin, 3 days rations",
        "plain clothes, work gloves, small tool pouch, practical boots, copper coins",
        "travel cloak, empty satchel, wooden charm, heel of bread",
        "secondhand jacket, notebook stub, stub of chalk, water flask",
    ],
    "character_backstory": [
        "Born in a canal district where freight crews raised children as extra hands, they grew up reading cargo marks, weather signs, and people's excuses. Before the story begins, they worked as a route clerk who kept small settlements supplied, and they reached the starting area carrying one delayed delivery, two unpaid favors, and a fear that their last ledger was altered.",
        "Born in a hill village that treated old ruins as common landmarks, they spent most of their life repairing tools, copying maps, and guiding travelers through roads locals considered ordinary. They left after a winter landslide exposed sealed stonework under the village shrine, bringing practical skills, a few local contacts, and one question their elders refused to answer.",
        "In their former life, they died in a hospital stairwell during a citywide blackout after spending years as an overworked emergency technician. They woke in this world with most memories intact but no proof of who they had been, carrying modern habits of triage, suspicion of official silence, and a need to learn which rules of the new world can still kill them.",
    ],
    "skill_style": ["standard", "generous", "training-heavy", "strict"],
    "proficiency_access": ["learned", "familiar actions free", "only expert tasks require training"],
    "new_skill_frequency": ["normal", "very rare", "rare", "frequent", "very frequent"],
    "world_style": ["frontier dark fantasy", "wuxia sect politics", "system apocalypse", "post-collapse settlement", "mage academy intrigue", "low magic mercantile city", "space frontier salvage"],
    "start_location": ["Mosswake Gate", "Blackwater Relay", "The Ninth Stair", "Cinder Market", "Ashford Clinic", "Red Lantern Dock", "Saint Vale Station"],
    "tone": ["grounded adventure", "survival pressure", "political intrigue", "mythic progression", "grim road story"],
    "economy": ["scarce", "barter-heavy", "coin-driven", "guild-controlled"],
    "loot_rarity": ["earned and uncommon", "scarce mundane", "generous adventuring", "high-magic loot"],
    "inventory_weight_limit": [45, 60, 80, 120],
    "inventory_slot_limit": [18, 24, 32, 40],
    "inventory_rules": [
        "Backpacks add organization more than strength; magic storage is rare and carries risks.",
        "Accessory slots follow anatomy unless an ability, spell, or special item creates more room.",
        "Superhuman stacks require clear stats, magic, or container support.",
    ],
    "magic_level": ["rare", "forbidden", "common utility", "cultivation", "none"],
    "world_races": ["human", "human, elf, dwarf", "human, beastfolk", "human, riverfolk, stonekin"],
    "race_magic_rarity": ["same as world magic", "rare except gifted races", "common for specific races", "bloodline locked", "cultural training based"],
    "race_magic_rules": [
        "Humans need formal training, elves inherit low magic, dwarves specialize in rune craft, and beastfolk rarely cast spells but sense spirits.",
        "Magic is learned culturally: each people has different schools, taboos, and costs rather than equal access.",
        "Only a few bloodlines can cast, but every race has at least one rare path into magic through training, vows, or relics.",
    ],
    "race_ability_rules": [
        "Humans have broad training access, elves can sense old growth and glamour, dwarves learn craft-oaths, and beastfolk inherit heightened senses.",
        "Racial abilities are social and biological rather than class powers; they should help in scenes without replacing skills.",
        "Innate gifts are modest at the start and stronger racial arts require culture, mentors, rites, or long practice.",
    ],
    "custom_skills": [
        "Do not seed starting skills; discover skill names only after repeated use, training, or clear milestones.",
        "Specialized proficiencies require mentors or manuals, ordinary attempts are allowed, mastery needs downtime.",
        "Combat, social, craft, and survival skills appear only after the player actually practices or earns them in play.",
        "Seed skill Ropework rank F; XP_to_next = 50 * rank_index^1.4; use grants 5-12 skill XP × risk (1/2/3); after C practice XP ×0.5 until mentor breakthrough; +1 domain check per rank above F; no second combat toolkit",
    ],
    "tech_level": ["iron age", "medieval", "early industrial", "near future", "spacefaring salvage"],
    "custom_style": ["", "Keep the opening local and personal before revealing larger threats.", "Every settlement should have at least one practical reason to exist.", "Avoid chosen-one framing; make reputation earned through visible choices."],
    "npc_density": ["moderate", "sparse", "dense", "faction-heavy"],
    "quest_style": ["emergent", "job board", "faction chains", "personal mysteries"],
    "faction_pressure": ["local disputes", "sect hierarchy", "guild control", "military occupation", "hidden cults"],
    "npc_stat_scaling": ["relative ranks", "mostly weaker", "near player", "swingy ranks", "elite-heavy"],
    "npc_skill_frequency": ["some trained NPCs", "no special NPC skills", "rare specialists", "many trained NPCs", "almost everyone has skills"],
    "rank_scale": ["F,E,D,C,B,A,S,SS,SSS", "D,C,B,A,S", "Common,Trained,Veteran,Elite,Mythic"],
    "difficulty": ["normal", "easy", "hard", "brutal"],
    "narration_detail": ["balanced", "rich", "expansive", "concise"],
    "skill_growth_speed": ["normal", "very slow", "slow", "fast", "very fast"],
    "proficiency_growth_speed": ["normal", "very slow", "slow", "fast", "very fast"],
    "xp_growth_speed": ["normal", "very slow", "slow", "fast", "very fast"],
    "death_rules": ["downed, not deleted", "lasting injuries", "permadeath threat", "narrative setback"],
    "system_style": ["subtle blue-window system", "cold quest-log interface", "cultivation status pane", "diegetic omen prompts"],
}
SETUP_RANDOMIZER_BOOLEAN_FALLBACKS = {
    "race_magic_enabled": [False, True],
    "leveling_system": [True, False],
    "game_system": [False, True],
    "proficiency_system": [True, False],
    "skill_levels_enabled": [True, False],
}
GROWTH_MATH_SAMPLES = [
    "rank F→E@80 E→D@200 D→C@450 C→B@900; domain use 5-12 skill XP × risk (1 safe/2 contested/3 life-risk); XP_to_next = 50 * rank_index^1.4; after C practice XP ×0.5 until mentor breakthrough; +1 domain check per rank above F",
    "levels 1-10; XP_to_next = 30 + 12*level; successful use grants 3-8 XP; crit success ×2; soft cap at L6 (XP ×0.6 until setback recovery); effect magnitude +8% per level",
    "thresholds F0 E100 D250 C500 B1000 A2000 S4000; practice 4 XP, contested 10, mentor drill 15; rank bonus +1 check / +5% effect; breakthrough needed after B",
    "XP_to_next = 40 * rank_index^1.5 (F=1); use grants 4-10 XP × risk (1/2/3); soft cap after rank C practice ×0.5; each rank above F: +1 domain check",
]

SETUP_RANDOMIZER_ABILITY_FALLBACKS = [
    {
        "name": "Echo Step",
        "description": "A short burst of impossible movement, useful for escapes or sudden positioning.",
        "locked": False,
        "prerequisites": "",
        "cost": "brief fatigue after repeated use",
        "growth_math": GROWTH_MATH_SAMPLES[0],
    },
    {
        "name": "Ashen Oath",
        "description": "Can sense when someone nearby is hiding a binding promise or unpaid debt.",
        "locked": True,
        "prerequisites": "Awakens after witnessing a broken oath with real consequences.",
        "cost": "mental strain when pushed",
        "growth_math": GROWTH_MATH_SAMPLES[1],
    },
    {
        "name": "Thread Sense",
        "description": "Briefly notices the emotional weight attached to an object or place.",
        "locked": False,
        "prerequisites": "",
        "cost": "sensory overload after repeated use",
        "growth_math": GROWTH_MATH_SAMPLES[2],
    },
    {
        "name": "Quiet Ledger",
        "description": "Keeps an instinctive count of small favors, debts, and who last broke a deal nearby.",
        "locked": False,
        "prerequisites": "",
        "cost": "distraction when overloaded with social noise",
        "growth_math": GROWTH_MATH_SAMPLES[3],
    },
    {
        "name": "Rust Touch",
        "description": "Slightly accelerates wear on a single tool or lock with prolonged contact—barely useful at first.",
        "locked": True,
        "prerequisites": "Needs a full night of handling scrap metal without rest.",
        "cost": "numb fingers for hours",
        "growth_math": GROWTH_MATH_SAMPLES[0],
    },
    {
        "name": "Second Breath",
        "description": "Once per hard day, recovers a single exhausted breath mid-sprint or mid-climb.",
        "locked": False,
        "prerequisites": "",
        "cost": "deep hunger afterward",
        "growth_math": GROWTH_MATH_SAMPLES[1],
    },
    {
        "name": "Ink Memory",
        "description": "Perfectly recalls one short written passage seen in the last day, nothing more.",
        "locked": False,
        "prerequisites": "",
        "cost": "mild headache when forced twice in a row",
        "growth_math": GROWTH_MATH_SAMPLES[2],
    },
    {
        "name": "False Stillness",
        "description": "Can hold perfectly still for a short count, enough to avoid a casual glance—not true stealth magic.",
        "locked": True,
        "prerequisites": "Unlocks after a failed escape that cost something real.",
        "cost": "muscle cramps",
        "growth_math": GROWTH_MATH_SAMPLES[3],
    },
]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def context_window_tokens(config: dict[str, Any] | None = None) -> int:
    model_config = config or get_model_config()
    if model_config.get("provider") == "llama_cpp":
        return _env_int("AI_RPG_LLAMA_CPP_CONTEXT", _env_int("OLLAMA_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS))
    return _env_int("OLLAMA_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS)


def _response_token_settings(config: dict[str, Any] | None = None) -> tuple[int, int]:
    model_config = config or get_model_config()
    soft_default = _env_int("AI_RPG_MAX_RESPONSE_TOKENS", DEFAULT_RESPONSE_TOKEN_CAP)
    hard_default = _env_int("AI_RPG_RESPONSE_HARD_CAP_TOKENS", _env_int("AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS", DEFAULT_RESPONSE_HARD_CAP))
    soft_cap = max(64, _int_value(model_config.get("response_token_cap"), soft_default))
    hard_cap = max(soft_cap, _int_value(model_config.get("response_token_hard_cap"), hard_default))
    return soft_cap, hard_cap


def _configured_response_tokens(config: dict[str, Any], max_tokens: int | None) -> int:
    soft_cap, hard_cap = _response_token_settings(config)
    requested = _int_value(max_tokens, soft_cap) if max_tokens is not None else soft_cap
    return max(1, min(requested, hard_cap))


def _response_token_cap(config: dict[str, Any], system_prompt: str, user_prompt: str, max_tokens: int | None) -> int:
    requested_tokens = _configured_response_tokens(config, max_tokens)
    context_window = max(512, context_window_tokens(config))
    reserve_tokens = max(0, _env_int("AI_RPG_CONTEXT_RESERVE_TOKENS", 96))
    available_tokens = context_window - estimated_tokens(f"{system_prompt}\n{user_prompt}") - reserve_tokens
    if available_tokens <= 0:
        return min(requested_tokens, max(64, _env_int("AI_RPG_MIN_RESPONSE_TOKENS", 160)))
    return max(1, min(requested_tokens, available_tokens))


def _json_repair_token_cap(config: dict[str, Any], max_tokens: int | None) -> int:
    soft_cap, hard_cap = _response_token_settings(config)
    requested = max(_int_value(max_tokens, soft_cap) if max_tokens is not None else soft_cap, soft_cap, 700)
    repair_hard_cap = _env_int("AI_RPG_JSON_REPAIR_TOKENS", hard_cap)
    return max(1, min(requested, hard_cap, repair_hard_cap))


def _is_context_length_error(exc: Exception) -> bool:
    text = str(exc).lower()
    markers = (
        "context_length_exceeded",
        "maximum context length",
        "context length",
        "reduce the length of the messages",
        "requested too many tokens",
        "num_ctx",
        "n_ctx",
    )
    return any(marker in text for marker in markers)


def _is_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    reason = getattr(exc, "reason", None)
    if reason is not None:
        text = f"{text} {reason}".lower()
    return "timed out" in text or "timeout" in text


def _is_connection_refused_error(exc: Any) -> bool:
    text = str(exc).lower()
    reason = getattr(exc, "reason", None)
    if reason is not None:
        text = f"{text} {reason}".lower()
    markers = (
        "winerror 10061",
        "errno 111",
        "connection refused",
        "refused connection",
        "refused the connection",
        "actively refused",
        "no connection could be made",
        "failed to establish a new connection",
    )
    return any(marker in text for marker in markers)


def _transport_error_message(exc: Exception, timeout: int) -> str:
    if _is_timeout_error(exc):
        return f"timed out after {timeout}s"
    if _is_connection_refused_error(exc):
        text = str(exc) or exc.__class__.__name__
        if " server refused connection at " in text:
            return text
        return "model server refused the connection; start the configured local LLM server or update the model server URL"
    return str(exc) or exc.__class__.__name__


def _connection_refused_message(provider: str, url: str) -> str:
    return f"{provider} server refused connection at {url}; start that server or update Model settings to a running local LLM endpoint"


def _prompt_size_message(total_prompt: str, label: str = "prompt") -> str:
    return f"{label} estimate ~{estimated_tokens(total_prompt)} tokens from {len(total_prompt)} chars"


def _chat_error_message(phase: str, reason: str, total_prompt: str, response_cap: int, hard_cap: int) -> str:
    if _is_connection_refused_error(reason):
        return f"{phase} {reason} ({_prompt_size_message(total_prompt)}; no model response was generated, so no token cap was hit)"
    return f"{phase} {reason} ({_prompt_size_message(total_prompt)}, configured soft response target {response_cap}, configured hard cap {hard_cap})"


def _repair_error_message(phase: str, reason: str, total_prompt: str, repair_cap: int, hard_cap: int) -> str:
    if _is_connection_refused_error(reason):
        return f"{phase}_repair {reason} after malformed JSON ({_prompt_size_message(total_prompt, 'repair prompt')}; no repair response was generated, so no token cap was hit)"
    return f"{phase}_repair {reason} after malformed JSON ({_prompt_size_message(total_prompt, 'repair prompt')}, configured repair cap {repair_cap}, configured hard cap {hard_cap})"


def _trace_limit() -> int:
    return max(1000, _env_int("AI_RPG_TRACE_VALUE_LIMIT", 200_000))


def _append_trace(trace: list[dict[str, Any]] | None, entry: dict[str, Any]) -> None:
    if trace is None:
        return
    trace.append(_trim_strings({"recorded_at": round(time.time(), 3), **entry}, _trace_limit()))


def _attach_model_usage(exc: LlmError, usage: list[dict[str, Any]], trace: list[dict[str, Any]] | None = None) -> LlmError:
    exc.model_usage = list(usage)
    if trace is not None:
        exc.model_trace = list(trace)
    return exc


def _trim_text(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _trim_strings(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        return _trim_text(value, limit)
    if isinstance(value, list):
        return [_trim_strings(item, limit) for item in value]
    if isinstance(value, dict):
        return {key: _trim_strings(item, limit) for key, item in value.items()}
    return value


def _decode_jsonish_string(raw: str) -> str:
    candidate = str(raw or "").replace("\r", "\\r").replace("\n", "\\n")
    try:
        return str(json.loads(f'"{candidate}"'))
    except json.JSONDecodeError:
        return str(raw or "").replace("\\n", "\n").replace("\\r", "\r").replace('\\"', '"')


def _jsonish_strings_for_key(text: str, key: str, limit: int = 6) -> list[str]:
    matches: list[str] = []
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*"', re.IGNORECASE)
    for match in pattern.finditer(str(text or "")):
        start = match.end()
        escaped = False
        chars: list[str] = []
        for char in text[start:]:
            if escaped:
                chars.append(f"\\{char}")
                escaped = False
                continue
            if char == "\\":
                escaped = True
                continue
            if char == '"':
                break
            chars.append(char)
        value = _decode_jsonish_string("".join(chars)).strip()
        if value:
            matches.append(value)
        if len(matches) >= limit:
            break
    return matches


def _salvage_narration_from_text(content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return ""
    candidates: list[str] = []
    for key in TURN_NARRATION_KEYS:
        candidates.extend(_jsonish_strings_for_key(text, key, 2))
    if not candidates:
        for key in ("text", "prose", "body", "scene"):
            candidates.extend(_jsonish_strings_for_key(text, key, 6))
            if candidates:
                break
    if not candidates and not text.startswith(("{", "[")):
        candidates.append(text)

    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        value = candidate.strip().strip("`").strip()
        if value.lower().startswith("json"):
            value = value[4:].strip()
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value).strip()
        key = value.lower()
        if len(value) < 40 or key in seen:
            continue
        if value.count("{") + value.count("}") > max(4, len(value) // 90):
            continue
        seen.add(key)
        cleaned.append(value)
        if len(cleaned) >= 5:
            break
    return "\n\n".join(cleaned).strip()[:5600]


def _narration_only_turn_from_text(content: str, context: dict[str, Any], reason: str) -> dict[str, Any]:
    narration = _salvage_narration_from_text(content)
    if not narration:
        raise LlmError("Malformed draft JSON did not contain readable narration to salvage.")
    location = str((context.get("current_location") or {}).get("name") or "the current location")
    return {
        "scene_plan": {
            "goal": "Keep the current scene playable without committing unverified world changes.",
            "focus_points": [
                {
                    "kind": "scene",
                    "summary": f"Hold the immediate scene around {location} while preserving only visible narration.",
                    "event_worthy": False,
                    "persistence": "temporary",
                }
            ],
        },
        "narration_segments": [{"label": "paragraph", "text": narration}],
        "narration": narration,
        "player": {
            "health_delta": 0,
            "max_health_delta": 0,
            "xp_delta": 0,
            "gold_delta": 0,
            "level_delta": 0,
            "move_to_location": None,
            "move_to_location_code": None,
            "karma_delta": 0,
            "karma_reason": "",
            "karma_visibility": "private",
        },
        "inventory_changes": [],
        "skill_changes": [],
        "locations": [],
        "npcs": [],
        "relationships": [],
        "events": [],
        "conversations": [],
        "response_drafts": [],
        "index_updates": [],
        "ability_updates": [],
        "gm_events": [],
        "self_check": {
            "passed": False,
            "issues_found": [
                "Draft JSON was malformed; recovered narration only.",
                _trim_text(reason, 220),
            ],
            "corrections_made": ["Ignored unparseable model-proposed state changes."],
            "reference_check": "not verified",
            "consistency_check": "not verified",
        },
        "turn_summary": f"Recovered readable draft narration at {location}; no unparseable state changes were applied."[:700],
        "journal": [],
        "scene_focus": "filler",
    }


def _comma_separated_phrases(value: Any, limit: int = 1200) -> str:
    if isinstance(value, list):
        raw = ",".join(str(item or "") for item in value)
    else:
        raw = str(value or "")
    for separator in ("\r", "\n", ";", "|"):
        raw = raw.replace(separator, ",")
    parts: list[str] = []
    seen: set[str] = set()
    for part in raw.split(","):
        clean = part.strip()
        if clean.startswith(("- ", "* ")):
            clean = clean[2:].strip()
        marker, _, rest = clean.partition(" ")
        if marker.rstrip(".)").isdigit() and marker.endswith((".", ")")):
            clean = rest.strip()
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        parts.append(clean)
    return ", ".join(parts)[:limit]


def _compact_list(value: Any, limit: int, string_limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [_trim_strings(item, string_limit) for item in value[:limit]]


def _compact_locations(value: Any) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return locations
    for location in value[:4]:
        if not isinstance(location, dict):
            continue
        compact_location = {
            "code": location.get("code"),
            "name": location.get("name"),
            "summary": location.get("summary"),
            "visit_count": location.get("visit_count"),
            "npcs": _compact_list(location.get("npcs"), 5, 360),
            "events": _compact_list(location.get("events"), 4, 360),
        }
        locations.append(_trim_strings(compact_location, 500))
    return locations


def _compact_turn_context(context: dict[str, Any]) -> dict[str, Any]:
    compact = dict(context)
    compact.pop("history", None)
    compact["settings"] = _trim_strings(context.get("settings"), 700)
    compact["gm_notes"] = _trim_strings(context.get("gm_notes"), 900)
    compact["gm_events"] = _compact_list(context.get("gm_events"), 8, 360)
    compact["player"] = _trim_strings(context.get("player"), 500)
    compact["current_location"] = _trim_strings(context.get("current_location"), 500)
    compact["mechanics_context"] = _trim_strings(context.get("mechanics_context"), 900)
    compact["verification_policy"] = _trim_strings(context.get("verification_policy"), 900)
    compact["action_context"] = _trim_strings(context.get("action_context"), 700)
    compact["skills"] = _compact_list(context.get("skills"), 12, 360)
    compact["abilities"] = _compact_list(context.get("abilities"), 10, 420)
    compact["player_aliases"] = _compact_list(context.get("player_aliases"), 6, 360)
    compact["active_player_alias"] = _trim_strings(context.get("active_player_alias"), 360)
    compact["inventory"] = _compact_list(context.get("inventory"), 18, 360)
    compact["equipment_slots"] = _compact_list(context.get("equipment_slots"), 16, 320)
    compact["equipment_effects"] = _trim_strings(context.get("equipment_effects"), 520)
    compact["inventory_capacity_modifiers"] = _compact_list(context.get("inventory_capacity_modifiers"), 12, 320)
    compact["inventory_summary"] = _trim_strings(context.get("inventory_summary"), 420)
    compact["locations"] = _compact_locations(context.get("locations"))
    compact["recognition"] = _compact_list(context.get("recognition"), 4, 360)
    compact["relationships"] = _compact_list(context.get("relationships"), 12, 320)
    compact["events"] = _compact_list(context.get("events"), 8, 360)
    compact["conversations"] = _compact_list(context.get("conversations"), 8, 360)
    compact["response_drafts"] = _compact_list(context.get("response_drafts"), 4, 320)
    compact["karma_history"] = _compact_list(context.get("karma_history"), 4, 320)
    compact["relevant_sources"] = _compact_list(context.get("relevant_sources"), 6, 320)
    compact["retrieval"] = _trim_strings(context.get("retrieval"), 360)
    compact["turn_summaries"] = _compact_list(context.get("turn_summaries"), 6, 260)
    return compact


def _json_size(value: Any) -> tuple[int, int]:
    try:
        text = json.dumps(value, ensure_ascii=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        text = str(value)
    return len(text), estimated_tokens(text)


def _handoff_source_slices(context: dict[str, Any]) -> list[str]:
    action_context = context.get("action_context") or {}
    slices: list[str] = []
    for segment in action_context.get("priority_segments") or []:
        if not isinstance(segment, dict):
            continue
        for source_slice in segment.get("source_slices") or []:
            value = str(source_slice or "").strip()
            if value and value not in slices:
                slices.append(value)
    return slices


def _handoff_context_roots(context: dict[str, Any]) -> set[str]:
    roots = set(HANDOFF_BASE_CONTEXT_KEYS)
    for source_slice in _handoff_source_slices(context):
        root = source_slice.split(".", 1)[0]
        if root == "explicit_references":
            roots.add("turn_plan")
        elif root in HANDOFF_OPTIONAL_CONTEXT_KEYS or root in HANDOFF_BASE_CONTEXT_KEYS:
            roots.add(root)
    turn_plan = context.get("turn_plan") or {}
    refs = turn_plan.get("explicit_references") or {}
    if refs.get("items"):
        roots.update({"inventory", "equipment_slots", "inventory_capacity_modifiers", "inventory_summary", "equipment_effects"})
    if refs.get("npcs"):
        roots.update({"locations", "relationships", "conversations", "recognition", "response_drafts"})
    if refs.get("events"):
        roots.update({"events", "locations", "gm_events", "turn_summaries"})
    if refs.get("locations"):
        roots.update({"locations", "events", "turn_summaries"})
    return roots


def _clean_context_locations(value: Any, limit: int) -> list[dict[str, Any]]:
    locations: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return locations
    for location in value[:limit]:
        if not isinstance(location, dict):
            continue
        cleaned_location = dict(location)
        cleaned_location["npcs"] = _compact_list(location.get("npcs"), 8, 420)
        cleaned_location["events"] = _compact_list(location.get("events"), 6, 420)
        locations.append(_trim_strings(cleaned_location, 700))
    return locations


def _clean_context_value_for_handoff(key: str, value: Any, broad_context: bool) -> Any:
    if key == "history":
        return []
    if key == "locations":
        return _clean_context_locations(value, 8 if broad_context else HANDOFF_CONTEXT_LIST_LIMITS["locations"])
    if isinstance(value, list):
        limit = HANDOFF_CONTEXT_LIST_LIMITS.get(key, 8)
        if broad_context and key in {"inventory", "events", "conversations", "turn_summaries", "locations"}:
            limit = min(limit + 4, 24)
        return _compact_list(value, limit, 520 if broad_context else 420)
    string_limit = 900 if key in {"settings", "gm_notes", "player", "current_location", "mechanics_context", "verification_policy", "turn_plan", "action_context"} else 620
    return _trim_strings(value, string_limit)


def _clean_context_for_handoff(context: dict[str, Any], phase: str, trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    turn_plan = context.get("turn_plan") or {}
    action_context = context.get("action_context") or {}
    broad_context = bool(action_context.get("broad_context_allowed")) or str(turn_plan.get("turn_kind") or "") == "opening_scene"
    kept_keys = _handoff_context_roots(context)
    if broad_context:
        kept_keys.update(HANDOFF_OPTIONAL_CONTEXT_KEYS)
    cleaned: dict[str, Any] = {}
    for key in sorted(kept_keys):
        if key in context:
            cleaned[key] = _clean_context_value_for_handoff(key, context.get(key), broad_context)
    cleaned["history"] = []
    retrieval = dict(cleaned.get("retrieval") or {})
    retrieval["handoff_cleanup"] = {
        "phase": phase,
        "mode": "broad" if broad_context else "focused",
        "kept_keys": sorted(key for key in kept_keys if key in context),
        "dropped_keys": sorted(key for key in context.keys() if key not in kept_keys and key != "history"),
    }
    cleaned["retrieval"] = retrieval
    before_chars, before_tokens = _json_size(context)
    after_chars, after_tokens = _json_size(cleaned)
    _append_trace(
        trace,
        {
            "phase": phase,
            "event": "handoff_context_cleanup",
            "cleanup_agent": "deterministic_context_steward",
            "mode": "broad" if broad_context else "focused",
            "source_slices": _handoff_source_slices(context),
            "kept_keys": retrieval["handoff_cleanup"]["kept_keys"],
            "dropped_keys": retrieval["handoff_cleanup"]["dropped_keys"],
            "before_chars": before_chars,
            "after_chars": after_chars,
            "before_estimated_tokens": before_tokens,
            "after_estimated_tokens": after_tokens,
        },
    )
    return cleaned


def _turn_max_tokens(context: dict[str, Any], phase: str, compact: bool = False) -> int:
    env_name = "AI_RPG_TURN_VERIFY_TOKENS" if phase == "verify" else "AI_RPG_TURN_DRAFT_TOKENS"
    requested_tokens = _env_int(env_name, _turn_token_default(context, phase))
    if not compact:
        return requested_tokens
    compact_default = 700 if phase == "verify" else 900
    compact_env = "AI_RPG_TURN_COMPACT_VERIFY_TOKENS" if phase == "verify" else "AI_RPG_TURN_COMPACT_DRAFT_TOKENS"
    return min(requested_tokens, _env_int(compact_env, compact_default))


def _model_timeout(default_ollama: int, default_llama_cpp: int, env_name: str = "") -> int:
    config = get_model_config()
    default = default_llama_cpp if config.get("provider") == "llama_cpp" else default_ollama
    if env_name and os.getenv(env_name):
        return _env_int(env_name, default)
    if config.get("provider") == "llama_cpp":
        return _env_int("AI_RPG_LLAMA_CPP_TIMEOUT", default_llama_cpp)
    return _env_int("AI_RPG_OLLAMA_TIMEOUT", default_ollama)


# OpenAI-compatible cloud / agent backends (xAI Grok, OpenAI, custom gateways).
API_PROVIDER_ALIASES = {
    "openai": "openai",
    "openai_compat": "openai",
    "api": "openai",
    "xai": "openai",
    "grok": "openai",
    "spacexai": "openai",
}
API_PRESETS = {
    "xai": {
        "api_base_url": "https://api.x.ai/v1",
        "api_model": "grok-4.5",
        "label": "xAI / Grok",
        "key_env": "XAI_API_KEY",
    },
    "openai": {
        "api_base_url": "https://api.openai.com/v1",
        "api_model": "gpt-4.1-mini",
        "label": "OpenAI",
        "key_env": "OPENAI_API_KEY",
    },
    "custom": {
        "api_base_url": "http://127.0.0.1:4000/v1",
        "api_model": "local-agent",
        "label": "Custom OpenAI-compatible",
        "key_env": "AI_RPG_API_KEY",
    },
}


def _normalize_provider(name: str) -> str:
    raw = str(name or "").strip().lower()
    if raw in API_PROVIDER_ALIASES:
        return API_PROVIDER_ALIASES[raw]
    if raw in {"ollama", "llama_cpp", "openai"}:
        return raw
    return "llama_cpp"


def resolve_api_key(config: dict[str, Any] | None = None) -> str:
    """API key from config, then common env vars. Never log this value."""
    cfg = config or get_model_config()
    stored = str(cfg.get("api_key") or "").strip()
    if stored:
        return stored
    for env_name in (
        "AI_RPG_API_KEY",
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
    ):
        value = os.getenv(env_name)
        if value and str(value).strip():
            return str(value).strip()
    return ""


# Known session_theme.adapter_hint values from setup_composer. Empty map values = use base model.
THEME_ADAPTER_HINTS: tuple[str, ...] = ("isekai_rpg", "system_rpg", "grimdark", "default")

# Per-request model config override (theme routing during generate_turn).
_model_config_override: ContextVar[dict[str, Any] | None] = ContextVar("model_config_override", default=None)


def default_theme_adapter_map() -> dict[str, str]:
    return {hint: "" for hint in THEME_ADAPTER_HINTS}


def normalize_theme_adapter_map(raw: Any) -> dict[str, str]:
    """Merge user map onto known hints; allow extra custom adapter keys."""
    out = default_theme_adapter_map()
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        hint = str(key or "").strip()[:80]
        if not hint:
            continue
        out[hint] = str(value or "").strip()[:200]
    return out


def resolve_theme_model_override(
    session_theme: dict[str, Any] | None,
    adapter_map: dict[str, str] | None = None,
) -> tuple[str, str]:
    """
    Pick optional model override for this session.
    Priority: session_theme.theme_model → theme_adapter_map[adapter_hint].
    Returns (source_label, model_name) or ("", "") when no override.
    """
    if not isinstance(session_theme, dict) or not session_theme:
        return "", ""
    explicit = str(session_theme.get("theme_model") or "").strip()
    if explicit:
        return "session_theme.theme_model", explicit[:200]
    amap = normalize_theme_adapter_map(adapter_map)
    hint = str(session_theme.get("adapter_hint") or "default").strip() or "default"
    mapped = str(amap.get(hint) or "").strip()
    if mapped:
        return f"theme_adapter_map[{hint}]", mapped[:200]
    return "", ""


def apply_theme_model_routing(
    config: dict[str, Any],
    session_theme: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Return a copy of model config with theme-based model swap applied (turn-time only).
    Ollama → ollama_model; OpenAI-compatible → api_model; llama.cpp path-like → gguf_model_path.
    """
    out = dict(config or {})
    adapter_map = normalize_theme_adapter_map(out.get("theme_adapter_map"))
    out["theme_adapter_map"] = adapter_map
    source, model = resolve_theme_model_override(
        session_theme if isinstance(session_theme, dict) else None,
        adapter_map,
    )
    out["theme_model_source"] = source
    out["theme_model_active"] = model
    if not model:
        return out
    provider = _normalize_provider(out.get("provider"))
    if provider == "ollama":
        out["ollama_model"] = model
    elif provider == "openai":
        out["api_model"] = model
    else:
        # llama.cpp: path-like values swap the managed GGUF; otherwise label only
        # (server may already host a themed merge — Morkyn still records the intent).
        lowered = model.lower()
        if ".gguf" in lowered or "/" in model or "\\" in model:
            out["gguf_model_path"] = model
        out["model"] = model
    return out


@contextmanager
def model_config_scope(config: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Force get_model_config() to return this config for nested chat calls (theme routing)."""
    token = _model_config_override.set(dict(config))
    try:
        yield config
    finally:
        _model_config_override.reset(token)


def public_model_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safe config for UI/API responses — never includes raw secrets."""
    cfg = dict(config or get_model_config(ignore_override=True))
    key = resolve_api_key(cfg)
    cfg["api_key"] = ""
    cfg["api_key_set"] = bool(key)
    cfg["api_key_hint"] = ("••••" + key[-4:]) if len(key) >= 4 else ("" if not key else "••••")
    cfg["api_presets"] = {
        name: {"api_base_url": meta["api_base_url"], "api_model": meta["api_model"], "label": meta["label"], "key_env": meta["key_env"]}
        for name, meta in API_PRESETS.items()
    }
    cfg["theme_adapter_map"] = normalize_theme_adapter_map(cfg.get("theme_adapter_map"))
    cfg["theme_adapter_hints"] = list(THEME_ADAPTER_HINTS)
    # Ephemeral routing fields are turn-only; strip from public settings blob.
    cfg.pop("theme_model_source", None)
    cfg.pop("theme_model_active", None)
    return cfg


def get_model_config(*, ignore_override: bool = False) -> dict[str, Any]:
    if not ignore_override:
        override = _model_config_override.get()
        if override is not None:
            return dict(override)
    default = {
        "provider": os.getenv("AI_RPG_MODEL_PROVIDER", "llama_cpp"),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.1"),
        "llama_cpp_base_url": os.getenv("LLAMA_CPP_BASE_URL", "http://localhost:8080"),
        "gguf_model_path": os.getenv("AI_RPG_GGUF_MODEL", DEFAULT_GGUF_MODEL),
        "api_base_url": os.getenv("AI_RPG_API_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.x.ai/v1")),
        "api_model": os.getenv("AI_RPG_API_MODEL", os.getenv("OPENAI_MODEL", "grok-4.5")),
        "api_key": os.getenv("AI_RPG_API_KEY", ""),
        "api_preset": os.getenv("AI_RPG_API_PRESET", "xai"),
        "response_token_cap": _env_int("AI_RPG_MAX_RESPONSE_TOKENS", DEFAULT_RESPONSE_TOKEN_CAP),
        "response_token_hard_cap": _env_int("AI_RPG_RESPONSE_HARD_CAP_TOKENS", _env_int("AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS", DEFAULT_RESPONSE_HARD_CAP)),
        "theme_adapter_map": default_theme_adapter_map(),
    }
    try:
        with connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'model_config'").fetchone()
    except Exception:
        default["provider"] = _normalize_provider(default["provider"])
        default["theme_adapter_map"] = normalize_theme_adapter_map(default.get("theme_adapter_map"))
        return default
    if not row:
        default["provider"] = _normalize_provider(default["provider"])
        default["theme_adapter_map"] = normalize_theme_adapter_map(default.get("theme_adapter_map"))
        return default
    try:
        stored = json.loads(row["value"])
    except json.JSONDecodeError:
        default["provider"] = _normalize_provider(default["provider"])
        default["theme_adapter_map"] = normalize_theme_adapter_map(default.get("theme_adapter_map"))
        return default
    merged = {**default, **stored}
    explicit_env = {
        "provider": "AI_RPG_MODEL_PROVIDER",
        "ollama_base_url": "OLLAMA_BASE_URL",
        "ollama_model": "OLLAMA_MODEL",
        "llama_cpp_base_url": "LLAMA_CPP_BASE_URL",
        "gguf_model_path": "AI_RPG_GGUF_MODEL",
        "api_base_url": "AI_RPG_API_BASE_URL",
        "api_model": "AI_RPG_API_MODEL",
        "api_key": "AI_RPG_API_KEY",
        "api_preset": "AI_RPG_API_PRESET",
    }
    for key, env_name in explicit_env.items():
        value = os.getenv(env_name)
        if value is not None and str(value).strip():
            merged[key] = str(value).strip()
    # Prefer dedicated cloud keys when api_key empty
    if not str(merged.get("api_key") or "").strip():
        for env_name in ("XAI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
            value = os.getenv(env_name)
            if value and str(value).strip():
                merged["api_key"] = str(value).strip()
                break
    if os.getenv("AI_RPG_MAX_RESPONSE_TOKENS"):
        merged["response_token_cap"] = _env_int("AI_RPG_MAX_RESPONSE_TOKENS", DEFAULT_RESPONSE_TOKEN_CAP)
    if os.getenv("AI_RPG_RESPONSE_HARD_CAP_TOKENS") or os.getenv("AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS"):
        merged["response_token_hard_cap"] = _env_int("AI_RPG_RESPONSE_HARD_CAP_TOKENS", _env_int("AI_RPG_MAX_RESPONSE_HARD_CAP_TOKENS", DEFAULT_RESPONSE_HARD_CAP))
    merged["provider"] = _normalize_provider(merged.get("provider"))
    merged["theme_adapter_map"] = normalize_theme_adapter_map(merged.get("theme_adapter_map"))
    return merged


def update_model_config(config: dict[str, Any]) -> dict[str, Any]:
    current = get_model_config(ignore_override=True)
    allowed = {
        "provider",
        "ollama_base_url",
        "ollama_model",
        "llama_cpp_base_url",
        "gguf_model_path",
        "api_base_url",
        "api_model",
        "api_key",
        "api_preset",
    }
    next_config = {**current}
    for key in allowed:
        if key not in config:
            continue
        # Empty api_key in POST means "keep existing" so the UI never has to re-send secrets.
        if key == "api_key" and not str(config.get(key) or "").strip():
            continue
        next_config[key] = str(config.get(key) or "").strip()
    if "theme_adapter_map" in config:
        next_config["theme_adapter_map"] = normalize_theme_adapter_map(config.get("theme_adapter_map"))
    if "response_token_cap" in config:
        next_config["response_token_cap"] = max(64, min(100_000, _int_value(config.get("response_token_cap"), DEFAULT_RESPONSE_TOKEN_CAP)))
    if "response_token_hard_cap" in config:
        next_config["response_token_hard_cap"] = max(64, min(100_000, _int_value(config.get("response_token_hard_cap"), DEFAULT_RESPONSE_HARD_CAP)))
    soft_cap, hard_cap = _response_token_settings(next_config)
    next_config["response_token_cap"] = soft_cap
    next_config["response_token_hard_cap"] = hard_cap
    next_config["provider"] = _normalize_provider(next_config.get("provider"))
    next_config["theme_adapter_map"] = normalize_theme_adapter_map(next_config.get("theme_adapter_map"))
    # Apply preset defaults when switching to openai without custom URL
    preset_name = str(next_config.get("api_preset") or "xai").strip().lower()
    if next_config["provider"] == "openai" and preset_name in API_PRESETS:
        preset = API_PRESETS[preset_name]
        if not next_config.get("api_base_url"):
            next_config["api_base_url"] = preset["api_base_url"]
        if not next_config.get("api_model"):
            next_config["api_model"] = preset["api_model"]
    # Never persist ephemeral routing diagnostics.
    next_config.pop("theme_model_source", None)
    next_config.pop("theme_model_active", None)
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("model_config", json.dumps(next_config, ensure_ascii=True)),
        )
    return public_model_config(next_config)


def _read_models_url(url: str, timeout: int = 5) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"data": payload}
    return {"data": []}


def _tail_text(path: str, limit: int = 1600) -> str:
    if not path:
        return ""
    try:
        file_path = Path(path)
        if not file_path.is_file():
            return ""
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-limit:].strip()


def _managed_log_tail() -> dict[str, str]:
    _ensure_managed_llama_state()
    return {
        "stdout_tail": _tail_text(_managed_llama_logs.get("stdout", "")),
        "stderr_tail": _tail_text(_managed_llama_logs.get("stderr", "")),
    }


def _llama_cpp_host_port(base_url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(base_url if "://" in base_url else f"http://{base_url}")
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8080
    if host.lower() == "localhost":
        host = "127.0.0.1"
    return host, port


def _llama_cpp_gpu_layers() -> int:
    requested = _env_int("AI_RPG_LLAMA_CPP_GPU_LAYERS", -1)
    if requested == 0:
        return 0
    try:
        from llama_cpp import llama_cpp as llama_cpp_bindings

        if not llama_cpp_bindings.llama_supports_gpu_offload():
            return 0
    except Exception:
        return requested
    return requested


def _managed_process_running(base_url: str) -> bool:
    _ensure_managed_llama_state()
    return bool(
        _managed_llama_process
        and _managed_llama_base_url == base_url
        and _managed_llama_process.poll() is None
    )


def _ensure_managed_llama_state() -> None:
    global _managed_llama_base_url, _managed_llama_logs, _managed_llama_process
    if "_managed_llama_process" not in globals():
        _managed_llama_process = None
    if "_managed_llama_base_url" not in globals():
        _managed_llama_base_url = ""
    if "_managed_llama_logs" not in globals() or not isinstance(_managed_llama_logs, dict):
        _managed_llama_logs = {}


def _start_managed_llama_cpp(config: dict[str, Any], base_url: str) -> dict[str, Any]:
    global _managed_llama_base_url, _managed_llama_logs, _managed_llama_process

    if _managed_process_running(base_url):
        return {"started": False, "managed": True, "message": "Managed llama.cpp server is already starting or running.", "logs": _managed_llama_logs}

    model_path = str(config.get("gguf_model_path") or "").strip()
    if not model_path:
        return {"started": False, "managed": False, "error": "No GGUF model path is saved. Select a GGUF model file, save the model settings, then test again."}
    if not Path(model_path).is_file():
        return {"started": False, "managed": False, "error": f"Saved GGUF model file was not found: {model_path}"}

    host, port = _llama_cpp_host_port(base_url)
    context_tokens = _env_int("AI_RPG_LLAMA_CPP_CONTEXT", _env_int("OLLAMA_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS))
    gpu_layers = _llama_cpp_gpu_layers()
    flash_attention = os.getenv("AI_RPG_LLAMA_CPP_FLASH_ATTN", "True")
    log_mode = os.getenv("AI_RPG_LLM_LOG_MODE", "quiet").strip().lower()
    stdout_handle = None
    stderr_handle = None
    stdout_path = ""
    stderr_path = ""
    if log_mode != "console":
        log_dir = Path(tempfile.gettempdir()) / "ai-rpg-logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        stdout_path = str(log_dir / f"llama-ui-{stamp}.out.log")
        stderr_path = str(log_dir / f"llama-ui-{stamp}.err.log")
        stdout_handle = open(stdout_path, "a", encoding="utf-8")
        stderr_handle = open(stderr_path, "a", encoding="utf-8")

    args = [
        sys.executable,
        "-m",
        "llama_cpp.server",
        "--model",
        model_path,
        "--model_alias",
        "ai-rpg-local",
        "--host",
        host,
        "--port",
        str(port),
        "--n_ctx",
        str(context_tokens),
        "--n_gpu_layers",
        str(gpu_layers),
        "--flash_attn",
        flash_attention,
        "--verbose",
        "False",
    ]
    try:
        _managed_llama_process = subprocess.Popen(args, stdout=stdout_handle or subprocess.DEVNULL, stderr=stderr_handle or subprocess.DEVNULL)
    except Exception as exc:
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()
        return {"started": False, "managed": False, "error": f"Could not start llama.cpp server: {exc}"}

    if stdout_handle:
        stdout_handle.close()
    if stderr_handle:
        stderr_handle.close()
    _managed_llama_base_url = base_url
    _managed_llama_logs = {"stdout": stdout_path, "stderr": stderr_path}
    return {
        "started": True,
        "managed": True,
        "message": "Started managed llama.cpp server from saved GGUF model path.",
        "pid": _managed_llama_process.pid,
        "logs": _managed_llama_logs,
    }


def _wait_for_models(url: str, process: subprocess.Popen | None, timeout_seconds: int) -> tuple[dict[str, Any] | None, str]:
    deadline = time.monotonic() + max(1, timeout_seconds)
    last_error = ""
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            tails = _managed_log_tail()
            detail = tails.get("stderr_tail") or tails.get("stdout_tail")
            suffix = f" Log tail: {detail}" if detail else ""
            return None, f"Managed llama.cpp server stopped before it became ready.{suffix}"
        try:
            return _read_models_url(url, timeout=2), ""
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    return None, f"Timed out waiting {timeout_seconds}s for llama.cpp server readiness at {url}. Last error: {last_error}"


def _ensure_llama_cpp_ready_for_generation(config: dict[str, Any], base_url: str) -> None:
    models_url = f"{base_url.rstrip('/')}/v1/models"
    start_result = _start_managed_llama_cpp(config, base_url.rstrip("/"))
    if not (start_result.get("started") or start_result.get("managed")):
        raise LlmError(str(start_result.get("error") or "Could not start managed llama.cpp server."))
    payload, wait_error = _wait_for_models(models_url, _managed_llama_process, _env_int("AI_RPG_LLM_STARTUP_TIMEOUT", 180))
    if payload is None:
        raise LlmError(wait_error)


def _urlopen_json(req: urllib.request.Request, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_models_url_auth(url: str, api_key: str = "", timeout: int = 8) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"data": payload}
    return {"data": []}


def test_model_connection() -> dict[str, Any]:
    config = get_model_config()
    provider = _normalize_provider(config.get("provider") or "llama_cpp")
    base_url = ""
    url = ""
    try:
        if provider == "llama_cpp":
            base_url = str(config.get("llama_cpp_base_url") or "http://localhost:8080").rstrip("/")
            url = f"{base_url}/v1/models"
        elif provider == "openai":
            base_url = str(config.get("api_base_url") or "https://api.x.ai/v1").rstrip("/")
            url = f"{base_url}/models"
            api_key = resolve_api_key(config)
            if not api_key:
                return {
                    "ok": False,
                    "provider": provider,
                    "url": url,
                    "error": "No API key set. Use XAI_API_KEY / OPENAI_API_KEY / AI_RPG_API_KEY or LLM Settings.",
                    "config": public_model_config(config),
                    "managed_start": None,
                }
            try:
                payload = _read_models_url_auth(url, api_key=api_key, timeout=10)
            except Exception as exc:
                # Some gateways only expose chat; treat key+base as ok if models list fails with 404.
                err = str(exc)
                if "404" in err:
                    return {
                        "ok": True,
                        "provider": provider,
                        "url": url,
                        "models": [str(config.get("api_model") or "configured-model")],
                        "config": public_model_config(config),
                        "managed_start": None,
                        "note": "Models list unavailable; using configured api_model.",
                    }
                return {
                    "ok": False,
                    "provider": provider,
                    "url": url,
                    "error": err,
                    "config": public_model_config(config),
                    "managed_start": None,
                }
            return _model_status_payload(provider, url, payload, config)
        else:
            base_url = str(config.get("ollama_base_url") or "http://localhost:11434").rstrip("/")
            url = f"{base_url}/api/tags"

        try:
            payload = _read_models_url(url, timeout=5)
        except Exception as exc:
            start_result: dict[str, Any] | None = None
            if provider == "llama_cpp" and _is_connection_refused_error(exc):
                start_result = _start_managed_llama_cpp(config, base_url)
                if start_result.get("started") or start_result.get("managed"):
                    payload, wait_error = _wait_for_models(url, _managed_llama_process, _env_int("AI_RPG_LLM_STARTUP_TIMEOUT", 180))
                    if payload is not None:
                        return _model_status_payload(provider, url, payload, config, start_result)
                    return {
                        "ok": False,
                        "provider": provider,
                        "url": url,
                        "error": wait_error,
                        "config": public_model_config(config),
                        "managed_start": start_result,
                    }
            provider_name = "llama.cpp" if provider == "llama_cpp" else "Ollama"
            error = _connection_refused_message(provider_name, url) if _is_connection_refused_error(exc) else str(exc)
            if start_result and start_result.get("error"):
                error = f"{error}. {start_result['error']}"
            return {
                "ok": False,
                "provider": provider,
                "url": url,
                "error": error,
                "config": public_model_config(config),
                "managed_start": start_result,
            }

        return _model_status_payload(provider, url, payload, config)
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider,
            "url": url or base_url,
            "error": f"Model status check failed: {exc}",
            "config": public_model_config(config),
            "managed_start": None,
        }


def _model_status_payload(provider: str, url: str, payload: dict[str, Any], config: dict[str, Any], managed_start: dict[str, Any] | None = None) -> dict[str, Any]:

    if not isinstance(payload, dict):
        payload = {"data": payload if isinstance(payload, list) else []}
    models = payload.get("data") or payload.get("models") or []
    if not isinstance(models, list):
        models = []
    model_names = []
    for model in models[:8]:
        if isinstance(model, dict):
            model_names.append(str(model.get("id") or model.get("name") or model.get("model") or "unknown"))
        else:
            model_names.append(str(model))
    return {
        "ok": True,
        "provider": provider,
        "url": url,
        "models": model_names,
        "config": public_model_config(config),
        "managed_start": managed_start,
    }


def _setup_randomizer_return_fields(group: str, current_setup: dict[str, Any], text_mode: bool = False) -> list[str]:
    locked_fields = set(current_setup.get("_locked_fields") or [])
    if text_mode:
        return [group.split(":", 1)[1]]
    if group.startswith("field:"):
        return_fields = [group.split(":", 1)[1]]
    elif group == "all":
        return_fields = SETUP_RANDOMIZER_ALL_FIELD_ORDER
    else:
        return_fields = SETUP_RANDOMIZER_FIELD_GROUPS.get(group, SETUP_RANDOMIZER_FIELD_GROUPS["character"])
    return [field for field in return_fields if field not in locked_fields]


def _world_supports_exotic_sex(current_setup: dict[str, Any]) -> bool:
    """True when races/style clearly support constructs, spirits, shapeshifters, etc."""
    blob = " ".join(
        str(current_setup.get(key) or "")
        for key in (
            "world_races",
            "world_style",
            "custom_style",
            "race_ability_rules",
            "character_backstory",
            "tech_level",
        )
    ).lower()
    # Word-ish markers only — avoid substring traps like "ai" inside "isekai".
    if re.search(
        r"\b("
        r"constructs?|golems?|androids?|robots?|spirits?|undead|"
        r"shapeshift(?:er|ing)?s?|slimes?|elementals?|"
        r"homunculi|homunculus|dolls?|genderless|sexless|"
        r"machine(?:s|folk|race)?|synthetic|cyborgs?"
        r")\b",
        blob,
    ):
        return True
    if "varies by form" in blob or "fluid form" in blob:
        return True
    # Standalone AI as a people/body type, not the "ai" letters in isekai.
    if re.search(r"(?<![a-z])ai(?![a-z])", blob) or "a.i." in blob:
        return True
    return False


def _fallback_sex_value(field: str, current_setup: dict[str, Any]) -> str:
    """Prefer male/female (~80–90%) over blank/unsexed/exotic categories."""
    exotic_ok = _world_supports_exotic_sex(current_setup)
    if exotic_ok:
        weighted = [
            ("female", 38),
            ("male", 38),
            ("", 8),
            ("intersex", 6),
            ("sexless or constructed", 5),
            ("varies by form", 5),
        ]
    else:
        # Ordinary humanoid / human-leaning worlds: almost always male or female.
        weighted = [
            ("female", 44),
            ("male", 44),
            ("", 7),
            ("intersex", 3),
            ("sexless or constructed", 1),
            ("varies by form", 1),
        ]
    population = [value for value, weight in weighted for _ in range(max(1, int(weight)))]
    return random.choice(population)


def _fallback_setup_value(field: str, current_setup: dict[str, Any]) -> Any:
    if field in PREVIOUS_LIFE_IDENTITY_FIELDS and not _setup_has_former_life_identity(current_setup):
        return ""
    if field in OPTIONAL_IDENTITY_FIELDS:
        chance = _optional_identity_fill_chance(field, current_setup)
        if random.random() > chance:
            return ""
    if field in ("player_sex", "previous_life_sex"):
        return _fallback_sex_value(field, current_setup)
    if field in SETUP_RANDOMIZER_BOOLEAN_FALLBACKS:
        return random.choice(SETUP_RANDOMIZER_BOOLEAN_FALLBACKS[field])
    if field == "special_abilities":
        return _fallback_special_abilities(current_setup)
    values = SETUP_RANDOMIZER_FALLBACKS.get(field)
    if values:
        value = random.choice(values)
        if field == "custom_skills":
            return _comma_separated_phrases(value)
        return value
    return current_setup.get(field)


def _ability_fingerprint(ability: dict[str, Any] | None) -> str:
    if not isinstance(ability, dict):
        return ""
    name = str(ability.get("name") or "").strip().lower()
    desc = str(ability.get("description") or "").strip().lower()
    return f"{name}||{desc}"


def _abilities_match_existing(new_list: list[Any], existing: list[Any]) -> bool:
    """True if the new roll is effectively the same set as what the player already has."""
    if not isinstance(new_list, list) or not isinstance(existing, list):
        return False
    if not existing or not new_list:
        return False
    new_fps = {_ability_fingerprint(a) for a in new_list if isinstance(a, dict) and _ability_fingerprint(a)}
    old_fps = {_ability_fingerprint(a) for a in existing if isinstance(a, dict) and _ability_fingerprint(a)}
    if not new_fps or not old_fps:
        return False
    # Same single ability, or full set overlap
    if len(new_fps) == 1 and len(old_fps) == 1 and new_fps == old_fps:
        return True
    return new_fps == old_fps


def _fallback_special_abilities(current_setup: dict[str, Any]) -> list[dict[str, Any]]:
    field_context = current_setup.get("_field_context") if isinstance(current_setup.get("_field_context"), dict) else {}
    origin = str(field_context.get("ability_origin") or current_setup.get("special_ability_origin") or "none").strip().lower()
    if origin == "none":
        return []
    quantity_locked = bool(field_context.get("quantity_locked"))
    try:
        requested_count = max(
            0,
            min(
                5,
                int(
                    field_context.get("requested_count")
                    if field_context.get("requested_count") is not None
                    else field_context.get("existing_count")
                    or 0
                ),
            ),
        )
    except (TypeError, ValueError):
        requested_count = 0
    # One-skill / near-useless intents → single seed ability
    intent = _resolve_setup_intent(current_setup)
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    one_skillish = str(pf.get("growth") or "").lower() == "compounding" or str(pf.get("start_power") or "").lower() in {
        "near_useless",
        "weak",
    }
    if quantity_locked and requested_count:
        count = requested_count
    elif one_skillish:
        count = 1
    else:
        count = random.randint(1, 3)
    pool = list(SETUP_RANDOMIZER_ABILITY_FALLBACKS)
    random.shuffle(pool)
    # Avoid reusing whatever is already on the form when possible
    existing = current_setup.get("special_abilities") if isinstance(current_setup.get("special_abilities"), list) else []
    existing_fps = {_ability_fingerprint(a) for a in existing if isinstance(a, dict)}
    ordered = [a for a in pool if _ability_fingerprint(a) not in existing_fps] + [
        a for a in pool if _ability_fingerprint(a) in existing_fps
    ]
    abilities: list[dict[str, Any]] = []
    for index in range(count):
        ability = dict(ordered[index % len(ordered)])
        if origin == "acquired":
            ability["locked"] = True
            ability["prerequisites"] = ability.get("prerequisites") or (
                "Unlocks through training, a mentor, or a costly field discovery."
            )
        if one_skillish:
            # Keep seed modest; compounding happens in play
            ability["locked"] = origin == "acquired" or bool(ability.get("locked"))
            if not str(ability.get("prerequisites") or "").strip() and ability["locked"]:
                ability["prerequisites"] = "Barely usable seed; deepens only through repeated risky practice."
        if not str(ability.get("growth_math") or "").strip():
            ability["growth_math"] = random.choice(GROWTH_MATH_SAMPLES)
        elif one_skillish:
            # Always ensure one-skill fallbacks carry concrete math
            ability["growth_math"] = str(ability.get("growth_math") or random.choice(GROWTH_MATH_SAMPLES))[:800]
        abilities.append(ability)
    return abilities


def _ability_has_calculable_math(text: str) -> bool:
    raw = str(text or "").strip().lower()
    if len(raw) < 24:
        return False
    markers = (
        "xp",
        "rank",
        "threshold",
        "level",
        "×",
        "x0.",
        "x1",
        "x2",
        "x3",
        "*",
        "^",
        "%",
        "bonus",
        "soft cap",
        "per-use",
        "per use",
        "multiplier",
        "formula",
        "to_next",
        "to next",
    )
    digit = any(ch.isdigit() for ch in raw)
    return digit and any(marker in raw for marker in markers)


def _ensure_ability_growth_math(
    abilities: list[dict[str, Any]] | None,
    *,
    force_fill: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(abilities, list):
        return []
    out: list[dict[str, Any]] = []
    for ability in abilities:
        if not isinstance(ability, dict):
            continue
        next_ability = dict(ability)
        math_text = str(next_ability.get("growth_math") or "").strip()
        if force_fill or not _ability_has_calculable_math(math_text):
            next_ability["growth_math"] = random.choice(GROWTH_MATH_SAMPLES)
        else:
            next_ability["growth_math"] = math_text[:800]
        # Keep other string fields bounded
        for key, limit in (
            ("name", 100),
            ("description", 800),
            ("prerequisites", 500),
            ("cost", 300),
            ("growth_math", 800),
        ):
            if key in next_ability and next_ability[key] is not None:
                next_ability[key] = str(next_ability[key])[:limit]
        out.append(next_ability)
    return out


def _maybe_optimize_ability_growth_math(
    abilities: list[dict[str, Any]],
    *,
    intent_plan: dict[str, Any],
    current_setup: dict[str, Any],
) -> list[dict[str, Any]]:
    """Invent/balance growth_math strings; optimize on a schedule rather than every roll."""
    ensured = _ensure_ability_growth_math(abilities, force_fill=False)
    if not ensured:
        return ensured
    pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
    one_skillish = str(pf.get("growth") or "").lower() == "compounding" or str(pf.get("start_power") or "").lower() in {
        "near_useless",
        "weak",
    }
    # Discretion: always optimize one-skill; otherwise ~40% of rolls, or any missing math.
    needs_math = any(not _ability_has_calculable_math(str(a.get("growth_math") or "")) for a in ensured)
    should_optimize = one_skillish or needs_math or random.random() < 0.4
    if not should_optimize:
        return ensured

    optimize_prompt = {
        "task": "Optimize growth_math for each ability: invent random but balanced playable calculation settings, then tighten them.",
        "intent": {
            "power_fantasy": pf,
            "difficulty": intent_plan.get("difficulty") or current_setup.get("difficulty"),
            "genre": intent_plan.get("genre") or current_setup.get("world_style"),
        },
        "abilities": [
            {
                "name": a.get("name"),
                "description": str(a.get("description") or "")[:200],
                "growth_math": a.get("growth_math") or "",
            }
            for a in ensured
        ],
        "return_shape": {
            "special_abilities": [
                {
                    "name": "same name as input",
                    "growth_math": "optimized compact formulas only",
                }
            ]
        },
        "rules": [
            "Return JSON only with special_abilities list matching input order/names.",
            "Rewrite growth_math only; do not change ability names.",
            "Each growth_math must include concrete numbers: thresholds or XP_to_next, per-use XP with risk mult, and at least one rank→bonus or soft-cap rule.",
            "Vary numbers across rolls; do not copy inspiration templates verbatim.",
            "Keep each growth_math under 800 characters, compact, DM-usable.",
            "Weaker starts should ramp slower early and snowball later if compounding; ordinary abilities stay modest.",
        ],
        "inspiration_only": GROWTH_MATH_SAMPLES,
    }
    try:
        raw = _chat_json(
            "Return JSON only. Optimize ability growth_math formulas for fair RPG play.",
            json.dumps(optimize_prompt, ensure_ascii=True),
            timeout=_model_timeout(25, 120, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
            phase="setup_ability_growth_math_optimize",
            max_tokens=500,
        )
    except Exception:
        return ensured

    optimized = raw.get("special_abilities") if isinstance(raw, dict) else None
    if not isinstance(optimized, list):
        return ensured
    by_name: dict[str, str] = {}
    for entry in optimized:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip().lower()
        math_text = str(entry.get("growth_math") or "").strip()
        if name and _ability_has_calculable_math(math_text):
            by_name[name] = math_text[:800]
    if not by_name:
        return ensured
    out: list[dict[str, Any]] = []
    for ability in ensured:
        next_ability = dict(ability)
        key = str(next_ability.get("name") or "").strip().lower()
        if key in by_name:
            next_ability["growth_math"] = by_name[key]
        out.append(next_ability)
    return _ensure_ability_growth_math(out, force_fill=False)


def fallback_setup_randomization(group: str, current: dict[str, Any] | None = None, reason: str = "") -> dict[str, Any] | None:
    if group.startswith(("text:", "optimize:")):
        return None
    current_setup = current or {}
    return_fields = _setup_randomizer_return_fields(group, current_setup)
    if not return_fields:
        return {"fields": {}, "fallback_used": True, "fallback_reason": _trim_text(reason, 240) if reason else "No unlocked setup fields were requested."}
    fields: dict[str, Any] = {}
    intent_plan = _resolve_setup_intent(current_setup)
    idea = str(current_setup.get("_randomize_idea") or intent_plan.get("raw_idea") or "")
    for field in return_fields:
        value = _fallback_setup_value(field, {**current_setup, **fields})
        if value is None:
            continue
        if field_is_contaminated(field, value, idea):
            clean = structural_fallback(field, {**current_setup, **fields, "_compose_intent": intent_plan})
            if clean is not None:
                value = clean
        fields[field] = value
    if "custom_skills" in fields:
        fields["custom_skills"] = _comma_separated_phrases(fields.get("custom_skills"))
    fields, _dirty = sanitize_setup_fields(
        fields,
        idea=idea,
        context={**current_setup, **fields, "_compose_intent": intent_plan},
    )
    return {
        "fields": fields,
        "fallback_used": True,
        "fallback_reason": _trim_text(reason, 240) if reason else "Model randomizer failed; deterministic setup fallback was used.",
    }


def coherence_review_setup(
    current: dict[str, Any] | None = None,
    *,
    locked_fields: list[str] | None = None,
    intent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Full-setup coherence pass after field-by-field Randomize.

    Reviews filled form values for tacky/cheesy/AI-generic prose and mis-slotted
    power fantasy. Never overwrites locked fields or empty user blanks that were
    intentionally left empty for optional identity. Returns patches only.
    """
    current_setup = dict(current or {})
    locked = set(locked_fields or current_setup.get("_locked_fields") or [])
    intent_plan = intent if isinstance(intent, dict) else _resolve_setup_intent(current_setup)
    idea = str(
        current_setup.get("_randomize_idea") or intent_plan.get("raw_idea") or ""
    ).strip()[:400]

    # Only review free-text / list-ish fields that tend to go cheesy.
    review_keys = [
        "character_backstory",
        "custom_style",
        "custom_skills",
        "race_magic_rules",
        "race_ability_rules",
        "inventory_rules",
        "start_location",
        "world_style",
        "tone",
        "quest_style",
        "faction_pressure",
        "system_style",
        "player_title",
        "player_public_name",
        "special_abilities",
        "starter_equipment",
        "appearance",
        "backstory_mode",
        "memory_policy",
    ]
    snapshot = {
        k: current_setup.get(k)
        for k in review_keys
        if k not in locked and current_setup.get(k) not in (None, "", [], {})
    }
    if not snapshot:
        return {
            "fields": {},
            "special_abilities": None,
            "notes": "Nothing to review (locked or empty).",
            "changed": [],
        }

    pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
    prompt = {
        "task": (
            "Review this RPG setup package for coherence. Keep the same game concept, "
            "but rewrite only values that are tacky, cheesy, cliché, AI-generic, "
            "or inconsistent with the rest of the package. Prefer sparse, concrete "
            "tabletop language over purple prose."
        ),
        "player_idea": idea,
        "intent_plan": {
            "genre": intent_plan.get("genre"),
            "isekai": intent_plan.get("isekai"),
            "difficulty": intent_plan.get("difficulty"),
            "dm_stance": intent_plan.get("dm_stance"),
            "power_fantasy": pf,
            "keywords": intent_plan.get("keywords"),
        },
        "locked_fields": sorted(locked),
        "setup_snapshot": snapshot,
        "return_shape": {
            "field_patches": {
                "any_reviewed_field": "rewritten value or omit if fine as-is",
            },
            "special_abilities": "optional full replacement list only if abilities need rewrite; else omit",
            "notes": "one short line on what you fixed",
        },
        "rules": [
            "Return JSON only.",
            "Only include fields you actually change in field_patches.",
            "Never invent locked_fields keys.",
            "Do not dilute a one-skill / compounding fantasy: if intent says one weak compounding skill, "
            "custom_skills must still encode seed skill name/domain, start rank, tracking style, XP sources, "
            "and hard limits. Put concrete calculable growth math on each ability's growth_math field "
            "(XP_to_next or rank thresholds, per-use XP ± risk multipliers, soft caps, rank→bonus formulas). "
            "Vague 'gets stronger over time' is not enough — invent numbers on growth_math.",
            "You may rewrite ability growth_math solely to add missing calculable math when fiction is fine.",
            "If special_abilities are present and one-skill fantasy, keep exactly one modest seed ability "
            "aligned with custom_skills; do not invent a second combat toolkit.",
            "When rewriting special_abilities, preserve or fill growth_math with concrete calculable formulas.",
            "Prefer concrete nouns and limits over adjectives like 'mysterious', 'ancient destiny', 'chosen'.",
            "Keep custom_skills as one comma-separated string (no bullets).",
            "STARTER GEAR LOGIC: starter_equipment is what the player owns the instant Start is pressed. "
            "Fact-check against backstory_mode: pure isekai/summon/just-transported → only clothes/pockets "
            "from the moment of transport (no fantasy shield/sword/armor/god loot). "
            "Reincarnated/grew-up-here → this-life gear only. Native life → gear must fit their job/life. "
            "God gifts, quest rewards, system packages happen AFTER Start in play — never pre-seed them. "
            "If gear is illogical, rewrite starter_equipment and/or appearance; do not invent a free arsenal.",
            "If everything is already solid, return empty field_patches and omit special_abilities.",
            "User-facing names/titles already filled should only change if clearly cheesy.",
        ],
    }
    try:
        raw = _chat_json(
            "Return JSON only. Coherence edit of RPG setup fields. Prefer omit over rewrite.",
            json.dumps(prompt, ensure_ascii=True),
            timeout=_model_timeout(45, 240, "AI_RPG_SETUP_COHERENCE_TIMEOUT"),
            phase="setup_coherence_review",
            max_tokens=700,
        )
    except Exception as exc:
        return {
            "fields": {},
            "special_abilities": None,
            "notes": f"Coherence pass skipped: {exc}",
            "changed": [],
            "fallback_used": True,
        }

    patches = raw.get("field_patches") if isinstance(raw.get("field_patches"), dict) else {}
    if not patches and isinstance(raw, dict):
        # Allow model to return flat field map
        patches = {
            k: v
            for k, v in raw.items()
            if k in review_keys and k not in locked and v not in (None, "", [], {})
        }
    fields: dict[str, Any] = {}
    for key, value in patches.items():
        if key in locked or key not in review_keys:
            continue
        if value in (None, "", [], {}):
            continue
        if key == "special_abilities":
            continue
        fields[key] = value

    abilities = raw.get("special_abilities")
    if "special_abilities" in locked:
        abilities = None
    elif not isinstance(abilities, list):
        abilities = None

    if "custom_skills" in fields:
        fields["custom_skills"] = _comma_separated_phrases(fields.get("custom_skills"))

    fields, _dirty = sanitize_setup_fields(
        fields,
        idea=idea,
        context={**current_setup, **fields, "_compose_intent": intent_plan},
    )
    changed = list(fields.keys())
    if abilities is not None:
        abilities = _ensure_ability_growth_math(abilities if isinstance(abilities, list) else [])
        changed.append("special_abilities")
    return {
        "fields": fields,
        "special_abilities": abilities,
        "notes": str(raw.get("notes") or "").strip()[:300],
        "changed": changed,
        "fallback_used": False,
    }


def compose_setup_intent(idea: str, current: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compile Randomize idea into a structured intent plan (keyword + optional LLM refine)."""
    idea_text = str(idea or "").strip()[:400]
    keyword_plan = apply_keyword_intent(idea_text)
    if not idea_text:
        theme = session_theme_from_intent(keyword_plan)
        return {"intent": keyword_plan, "session_theme": theme, "source": "empty"}

    llm_plan: dict[str, Any] | None = None
    try:
        try:
            compose_sparks = idea_sparks_for_prompt(
                {"_randomize_idea": idea_text},
                fields=["world_style", "tone", "custom_skills"],
                intent=keyword_plan,
                limit=3,
            )
        except Exception:
            compose_sparks = None
        prompt = {
            "task": "Compile a short structured setup intent plan for an endless AI RPG from the player's idea.",
            "idea": idea_text,
            "current_locked_hints": {
                k: (current or {}).get(k)
                for k in ("world_style", "difficulty", "game_system", "backstory_mode")
                if current and k in current
            },
            "idea_sparks": compose_sparks,
            "return_shape": {
                "genre": "short genre/setting phrase",
                "isekai": False,
                "portal_or_rebirth": "other_world | same_world_rebirth | ambiguous",
                "difficulty": "easy | normal | hard | brutal",
                "edge": "short edge/injury/loot pressure note",
                "power_fantasy": {
                    "start_power": "near_useless | ordinary | strong",
                    "growth": "steady | compounding",
                    "system_ui": False,
                    "skill_summary": "optional short skill fantasy note",
                },
                "tone": "short tone phrase",
                "keywords": ["up to 8 content keywords"],
                "adapter_hint": "isekai_rpg | system_rpg | grimdark | default",
                "dm_stance": "always keep fair DM player-agency stance",
                "style_notes": "optional short style note",
            },
            "rules": [
                "Return JSON only matching return_shape.",
                "difficulty must be one of easy, normal, hard, brutal — never a slogan.",
                "isekai true when the idea implies another world, transmigration, reincarnation into fantasy, or isekai.",
                "system_ui true when status windows, skill UI, levels, or game-system framing is requested.",
                "dm_stance must always prioritize fair pressure and player agency over genre pastiche.",
                "Do not write character backstory or ability lists here.",
                "idea_sparks are optional cold-storage wording ideas only — not weighted training; borrow flavor words, do not copy titles as genre slogans.",
            ],
        }
        llm_plan = _chat_json(
            "Return JSON only. Compile setup intent. Do not explain.",
            json.dumps(prompt, ensure_ascii=True),
            timeout=_model_timeout(30, 90, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
            phase="setup_compose_intent",
            max_tokens=320,
        )
    except LlmError:
        llm_plan = None
    except Exception:
        llm_plan = None

    plan = merge_intent_plans(keyword_plan, llm_plan if isinstance(llm_plan, dict) else None)
    # Optional: attach cold-storage idea hits for UI / downstream rolls (never trained weights).
    try:
        sparks = idea_sparks_for_prompt(
            {"_randomize_idea": idea_text},
            fields=["world_style", "tone", "custom_skills", "special_abilities"],
            intent=plan,
            limit=4,
        )
    except Exception:
        sparks = None
    return {
        "intent": plan,
        "session_theme": session_theme_from_intent(plan),
        "source": "llm+keywords" if llm_plan else "keywords",
        "idea_sparks": sparks,
    }


def _resolve_setup_intent(current_setup: dict[str, Any]) -> dict[str, Any]:
    raw = current_setup.get("_compose_intent") or current_setup.get("_intent")
    if isinstance(raw, dict) and (raw.get("genre") is not None or raw.get("raw_idea") or raw.get("isekai") is not None):
        return apply_keyword_intent(str(raw.get("raw_idea") or current_setup.get("_randomize_idea") or ""), raw)
    idea = str(current_setup.get("_randomize_idea") or "").strip()[:400]
    if idea:
        return apply_keyword_intent(idea)
    return empty_intent()


def generate_setup_randomization(group: str, current: dict[str, Any] | None = None) -> dict[str, Any]:
    current_setup = current or {}
    locked_fields = set(current_setup.get("_locked_fields") or [])
    raw_locked_values = current_setup.get("_locked_values") if isinstance(current_setup.get("_locked_values"), dict) else {}
    locked_setup = {field: raw_locked_values.get(field) for field in locked_fields if field in raw_locked_values}
    optimize_mode = group.startswith("optimize:")
    text_fill_mode = group.startswith("text:")
    text_mode = optimize_mode or text_fill_mode
    intent_plan = _resolve_setup_intent(current_setup)

    return_fields = _setup_randomizer_return_fields(group, current_setup, text_mode)
    if not return_fields:
        return {}
    if return_fields == ["special_abilities"]:
        field_context = current_setup.get("_field_context") if isinstance(current_setup.get("_field_context"), dict) else {}
        if str(field_context.get("ability_origin") or current_setup.get("special_ability_origin") or "none").lower() == "none":
            return {"special_abilities": []}

    base_rules = [
        "Return one JSON object only.",
        "Do not include task, rules, return_fields, current_setup, output_shape, or placeholder values.",
        "Do not return the current field value unchanged unless it is the only coherent option.",
        "Only include generated values for return_fields, plus notes if useful.",
        "Use concise values that fit form fields.",
        "Use only the supplied setup context and broad RPG playability; do not assume a default genre, species, class, moral alignment, tragic past, hidden past, amnesia, destiny, noble bloodline, revenge motive, or combat role unless the context supports it.",
        "Treat current_setup as the already-filled setup only. Do not use, infer, or depend on later fields that are not present in current_setup.",
        "locked_setup contains user-locked immutable settings, including possible later fields. Use locked_setup as compatibility constraints, but never regenerate, overwrite, or return those locked fields.",
        "Aim for a fresh playable concept with one concrete hook rather than a familiar template.",
        "Never paste the player's full idea slogan into enum, short_phrase, rank_scale, quest_style, difficulty, or economy fields.",
        "Stay in DM/setup-form mindset: each field is a typed game setting, not a free-form story dump.",
    ]
    # Structured intent (preferred) or loose idea string.
    randomize_idea = str(current_setup.get("_randomize_idea") or intent_plan.get("raw_idea") or "").strip()[:400]
    intent_for_fields = {
        field: intent_slice_for_field(intent_plan, field) for field in return_fields if field in COMPOSER_FIELD_ORDER
    }
    if randomize_idea or any(intent_for_fields.values()):
        base_rules.extend(
            [
                "A compiled intent_plan guides this roll. Prefer field_intent (keys allowed for this field) over the raw idea.",
                "Do not ignore locked_setup or already-filled current_setup just to force the idea; fold the idea into what remains coherent.",
                "If the idea is vague, pick one concrete interpretation and stay consistent across fields.",
            ]
        )
        if randomize_idea:
            base_rules.append(f"Raw player idea (background only): {randomize_idea}")
    # Cold-storage idea bank: keyword sparks only (not weights / not training data).
    idea_sparks_pkg: dict[str, Any] | None = None
    try:
        idea_sparks_pkg = idea_sparks_for_prompt(
            current_setup,
            fields=return_fields,
            intent=intent_plan,
            limit=5 if return_fields == ["special_abilities"] else 4,
        )
        if idea_sparks_pkg.get("sparks"):
            base_rules.append(
                "idea_sparks are cold-storage keyword hits for wider wording — inspiration only, not a ranked model."
            )
    except Exception:
        idea_sparks_pkg = None
    prompt: dict[str, Any]
    if text_mode:
        field = return_fields[0]
        source_text = str(current_setup.get("_optimize_text") or current_setup.get(field) or "").strip()
        user_prompt = str(current_setup.get("_user_prompt") or "").strip()[:700]
        text_options = current_setup.get("_text_ai_options") if isinstance(current_setup.get("_text_ai_options"), dict) else {}
        stage = str(current_setup.get("_text_ai_stage") or ("optimize" if optimize_mode else "draft"))
        field_context = current_setup.get("_field_context") or {}
        context_keys = [
            "backstory_mode",
            "world_style",
            "magic_level",
            "world_races",
            "race_magic_enabled",
            "race_magic_rarity",
            "tech_level",
            "tone",
            "economy",
            "difficulty",
            "death_rules",
            "narration_detail",
            "loot_rarity",
            "inventory_weight_limit",
            "inventory_slot_limit",
            "inventory_rules",
            "leveling_system",
            "game_system",
            "system_style",
            "proficiency_system",
            "skill_levels_enabled",
            "skill_style",
            "proficiency_access",
            "new_skill_frequency",
            "xp_growth_speed",
            "skill_growth_speed",
            "proficiency_growth_speed",
            "memory_policy",
            "start_location",
            "custom_style",
            "race_magic_rules",
            "race_ability_rules",
            "npc_density",
            "quest_style",
            "faction_pressure",
            "npc_stat_scaling",
            "npc_skill_frequency",
            "rank_scale",
            "player_name",
            "player_public_name",
            "player_title",
            "player_age",
            "player_sex",
            "previous_life_age",
            "previous_life_sex",
            "special_ability_origin",
            "character_backstory",
            "hair",
            "facial_features",
            "appearance",
            "starter_equipment",
            "custom_skills",
            "special_abilities",
        ]
        nearby_setup = {key: current_setup.get(key) for key in context_keys if key in current_setup}
        optimize_notes = {
            "character_backstory": "Keep this as concrete character history. Preserve the user's facts, but improve clarity, specificity, and playable hooks.",
            "hair": "Keep as short hair length/color/style only.",
            "facial_features": "Keep as face-only portrait cues (eyes, scars, freckles). No clothes.",
            "appearance": "Keep clothing zone tags only (torso/feet…). No hair or face details here.",
            "starter_equipment": "Keep as comma-separated mundane starting items; align with appearance; no legendaries.",
            "custom_style": "Keep this as setting constraints, themes, bans, and must-have world details.",
            "race_magic_rules": "Keep this as clear per-race magic access rules. Preserve which races can cast, need training, or use alternate traditions.",
            "race_ability_rules": "Keep this as clear per-race innate or learned ability rules. Preserve limits and starting strength.",
            "custom_skills": "Keep this as comma-separated skill discovery, training limits, progression rules, or named proficiencies. Use commas between every proficiency or rule phrase. Include starting proficiencies only when the user explicitly asks for named starting skills.",
            "ability_description": "Rewrite only the ability's immutable base description. Preserve scope and avoid adding broad new powers unless the user asked for them.",
            "ability_prerequisites": "Rewrite only the unlock condition, training need, item, oath, event, or other prerequisite.",
            "ability_cost": "Rewrite only the cost, cooldown, limit, injury, resource, debt, or drawback.",
            "ability_growth_math": (
                "Rewrite only the calculable growth rules for this power: XP curves, rank thresholds, "
                "per-use XP with risk multipliers, soft caps, rank→bonus formulas. Invent balanced numbers."
            ),
            "xp_growth_speed_note": "Rewrite only the custom XP gain rule.",
            "skill_growth_speed_note": "Rewrite only the custom skill gain rule.",
            "proficiency_growth_speed_note": "Rewrite only the custom proficiency gain rule.",
        }
        prompt = {
            "task": f"{'Optimize the draft for' if optimize_mode else 'Write text for'} the setup field {field}.",
            "field": field,
            "field_label": current_setup.get("_field_label") or field,
            "stage": stage,
            "user_prompt": user_prompt,
            "user_text": source_text,
            "options": {
                "optimize_after_draft": bool(text_options.get("optimize")),
                "simplify_language": bool(text_options.get("simplify")),
                "add_detail": bool(text_options.get("expand")),
                "preserve_key_phrases": bool(text_options.get("preserve_phrases")),
            },
            "nearby_setup": nearby_setup,
            "locked_setup": locked_setup,
            "ability_context": current_setup.get("_ability_context"),
            "field_context": field_context,
            "field_note": optimize_notes.get(field, "Improve clarity, specificity, and usefulness while preserving the user's intent."),
            "return_shape": {field: "generated text for this same field"},
            "rules": base_rules
            + [
                "The user_prompt is the player's instruction for this exact field. Follow it directly while keeping the field type in mind.",
                "Use field_label, field_context.related_name, and ability_context.name when present so the text fits the named thing being filled.",
                "Preserve the user's meaning, constraints, tone, named facts, limits, costs, training paths, and boundaries unless they are contradictory.",
                "Do not replace the idea with an unrelated random concept or generic RPG template.",
                "If preserve_key_phrases is true, keep distinctive phrases and named terms unless the optimize pass can clearly compress them without losing meaning.",
                "If simplify_language is true, use simpler grammar and fewer clauses without deleting important constraints.",
                "If add_detail is true, add practical boundaries, examples, unlock paths, or scene-usable specifics that fit the user's prompt.",
                "If optimize_after_draft is true and this is the draft stage, include the full idea and all important details; a later optimization pass may compact the wording.",
                "If this is the optimize stage, rewrite the draft to be cleaner and tighter while preserving all important information from user_prompt and user_text. Compact phrases are allowed when meaning survives, such as changing 'unfathomed knowledge' to a precise shorter term only if it still matches the requested power.",
                "If user_prompt and user_text are both empty, create one concise useful value for this field from nearby_setup.",
                "Fit the field_context.max_length when supplied.",
                "Return only the generated field value in JSON.",
            ],
        }
    elif return_fields == ["player_name"]:
        prompt = {
            "task": "Generate one playable RPG player name without assuming a default genre.",
            "forbidden_name": current_setup.get("player_name") or "Wanderer",
            "context": "broad RPG character creation",
            "return_shape": {"player_name": "new generated name"},
            "rules": base_rules,
        }
    elif return_fields == ["special_abilities"]:
        field_context = current_setup.get("_field_context") or {}
        quantity_locked = bool(field_context.get("quantity_locked"))
        try:
            requested_count = max(
                0,
                min(
                    5,
                    int(
                        field_context.get("requested_count")
                        if field_context.get("requested_count") is not None
                        else field_context.get("existing_count")
                        or 0
                    ),
                ),
            )
        except (TypeError, ValueError):
            requested_count = 0
        existing_abilities = (
            current_setup.get("special_abilities")
            if isinstance(current_setup.get("special_abilities"), list)
            else []
        )
        forbid_names = [
            str(a.get("name") or "").strip()
            for a in existing_abilities
            if isinstance(a, dict) and str(a.get("name") or "").strip()
        ]
        forbid_descs = [
            str(a.get("description") or "").strip()[:160]
            for a in existing_abilities
            if isinstance(a, dict) and str(a.get("description") or "").strip()
        ]
        pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
        one_skillish = str(pf.get("growth") or "").lower() == "compounding" or str(
            pf.get("start_power") or ""
        ).lower() in {"near_useless", "weak"}
        diversity_seed = random.randint(1000, 9999)
        domain_hints = [
            "craft/repair",
            "trade/barter",
            "memory of text",
            "balance/climbing",
            "tracking footprints",
            "animal calm",
            "poison/tincture smell",
            "map sense",
            "sleep discipline",
            "lie detection (weak)",
            "tool improvisation",
            "pain tolerance",
            "quiet footwork",
            "fire-tending",
            "knot-work",
        ]
        random.shuffle(domain_hints)
        prompt = {
            "task": (
                "Generate NEW setup special abilities according to ability_origin. "
                "This is a re-roll: invent different names and effects than any forbidden list. "
                f"Diversity seed {diversity_seed} — pick a fresh domain (suggested pool: {', '.join(domain_hints[:5])})."
            ),
            "ability_origin": field_context.get("ability_origin")
            or current_setup.get("special_ability_origin")
            or "none",
            "quantity_locked": quantity_locked,
            "requested_count": requested_count,
            "must_not_reuse": {
                "names": forbid_names,
                "description_prefixes": forbid_descs,
            },
            "current_setup": {
                "player_name": current_setup.get("player_name"),
                "player_public_name": current_setup.get("player_public_name"),
                "player_title": current_setup.get("player_title"),
                "player_age": current_setup.get("player_age"),
                "player_sex": current_setup.get("player_sex"),
                "previous_life_age": current_setup.get("previous_life_age"),
                "previous_life_sex": current_setup.get("previous_life_sex"),
                "special_ability_origin": current_setup.get("special_ability_origin"),
                "backstory_mode": current_setup.get("backstory_mode"),
                "memory_policy": current_setup.get("memory_policy"),
                "character_backstory": current_setup.get("character_backstory"),
                "world_style": current_setup.get("world_style"),
                "magic_level": current_setup.get("magic_level"),
                "world_races": current_setup.get("world_races"),
                "race_magic_enabled": current_setup.get("race_magic_enabled"),
                "race_magic_rules": current_setup.get("race_magic_rules"),
                "race_ability_rules": current_setup.get("race_ability_rules"),
                "difficulty": current_setup.get("difficulty"),
                "death_rules": current_setup.get("death_rules"),
                "loot_rarity": current_setup.get("loot_rarity"),
                "inventory_weight_limit": current_setup.get("inventory_weight_limit"),
                "inventory_slot_limit": current_setup.get("inventory_slot_limit"),
                "inventory_rules": current_setup.get("inventory_rules"),
                "game_system": current_setup.get("game_system"),
                "system_style": current_setup.get("system_style"),
                "skill_style": current_setup.get("skill_style"),
                # Hint only — do not copy domain words into a new ability name blindly
                "custom_skills_hint": current_setup.get("custom_skills"),
            },
            "locked_setup": locked_setup,
            "return_shape": {
                "special_abilities": [
                    {
                        "name": "ability name",
                        "description": "one concrete immutable base description",
                        "locked": False,
                        "prerequisites": "",
                        "cost": "no cost",
                        "growth_math": "playable XP/rank formulas for this power (not empty for compounding seeds)",
                    }
                ]
            },
            "growth_math_contract": {
                "purpose": "THIS is the home for calculable growth math on each power. Invent numbers the DM can apply each turn.",
                "must_include_at_least_two": [
                    "XP_to_next formula or rank XP thresholds",
                    "per-use skill/ability XP with risk multipliers",
                    "soft-cap / breakthrough rule",
                    "rank→check or effect bonus",
                ],
                "examples_inspiration_only": GROWTH_MATH_SAMPLES,
                "you_may_invent": "Any playable numbers/formulas; vary them each roll. No calculus; tabletop-clear.",
            },
            "field_intent": intent_slice_for_field(intent_plan, "special_abilities"),
            "field_contract": field_contract("special_abilities"),
            "idea_sparks": idea_sparks_pkg,
            "rules": base_rules
            + [
                "Do not return the current abilities unchanged. Invent new names and descriptions.",
                "Never reuse must_not_reuse.names or paraphrase must_not_reuse.description_prefixes.",
                "Do not default to weather, sandstorms, storms, invisibility, or pure Observation/environment-sense powers unless the diversity seed points there.",
                "If ability_origin is none, return an empty special_abilities list.",
                "If ability_origin is acquired, abilities should usually be locked or have prerequisites and feel learned, earned, trained, system-granted, event-awakened, tool-based, or recovered through play.",
                "If ability_origin is innate, abilities should usually be usable at the start and feel inherent, inborn, inherited, racial, bodily, soul-deep, or otherwise natural to the character.",
                "Use locked true for abilities that should exist but not be usable at the start.",
                "Let backstory_mode and character_backstory decide whether abilities come from current race, training, former-life remnants, system awakening, vows, tools, or no special source at all.",
                "For reincarnated or transmigrated characters, former strength may justify a locked remnant or remembered technique, but do not force former power unless the backstory supports it.",
                "If field_intent.power_fantasy.start_power is near_useless or weak, abilities should start locked or extremely modest; compounding growth belongs to later play, not opening god-mode.",
                "If growth is compounding / one-skill fantasy: return exactly ONE ability that is a weak seed power in a concrete domain (not a full toolkit). Domain must vary across re-rolls.",
                "ALWAYS fill growth_math with concrete calculable rules for each ability (especially compounding / one-skill). Do not leave it empty. Do not put long formula essays only in custom_skills — growth_math is the math box on the power.",
                "For one-skill fantasy, the ability is the playable expression of the seed skill; put fiction/tracking/limits in custom_skills; put XP/rank math in growth_math.",
                "If custom_skills_hint or ONE_SKILL_FRAME is present, invent a matching seed domain and describe the ability as the weak practical expression of that skill.",
            ],
        }
        if one_skillish and not quantity_locked:
            prompt["rules"] = prompt["rules"] + ["Return exactly 1 special_abilities entry for this one-skill / weak-start run."]
        if quantity_locked:
            prompt["rules"] = prompt["rules"] + [
                f"Return exactly {requested_count} special_abilities entries, no more and no fewer."
            ]
    elif len(return_fields) == 1:
        field = return_fields[0]
        field_context = current_setup.get("_field_context") or {}
        is_multi_select = field_context.get("type") == "multi_select"
        context_keys = [
            "backstory_mode",
            "world_style",
            "magic_level",
            "world_races",
            "race_magic_enabled",
            "race_magic_rarity",
            "tech_level",
            "tone",
            "economy",
            "difficulty",
            "death_rules",
            "narration_detail",
            "loot_rarity",
            "inventory_weight_limit",
            "inventory_slot_limit",
            "inventory_rules",
            "leveling_system",
            "game_system",
            "system_style",
            "proficiency_system",
            "skill_levels_enabled",
            "skill_style",
            "proficiency_access",
            "new_skill_frequency",
            "xp_growth_speed",
            "skill_growth_speed",
            "proficiency_growth_speed",
            "memory_policy",
            "start_location",
            "custom_style",
            "race_magic_rules",
            "race_ability_rules",
            "npc_density",
            "quest_style",
            "faction_pressure",
            "npc_stat_scaling",
            "npc_skill_frequency",
            "rank_scale",
            "player_name",
            "player_public_name",
            "player_title",
            "player_age",
            "player_sex",
            "previous_life_age",
            "previous_life_sex",
            "character_backstory",
            "hair",
            "facial_features",
            "appearance",
            "starter_equipment",
            "custom_skills",
            "special_abilities",
        ]
        nearby_setup = {key: current_setup.get(key) for key in context_keys if key in current_setup and key != field}
        field_notes = {
            "player_public_name": "Usually return a blank string. Generate an alias, public name, or nickname only when character_backstory and backstory_mode make it useful, such as a reincarnated former identity, a hidden local alias, a nameless drifter's handle, or a name NPCs would plausibly know.",
            "player_title": "Usually return a blank string. Generate a concise title or epithet only when character_backstory and backstory_mode justify reputation, former status, high power, formal office, infamous deeds, reincarnation from strength, or a title NPCs would plausibly use.",
            "player_age": "Generate the character's current age or apparent age in this life. Text is allowed for unusual species, constructs, or immortal starts. Do not use age to force personality or stereotypes.",
            "player_sex": (
                "Prefer female or male for ordinary humanoid characters (about 80-90% of rolls). "
                "Blank/unspecified is occasional. Intersex is uncommon. "
                "Sexless/constructed or varies-by-form only when world_races, custom_style, race rules, or backstory clearly support constructs, spirits, shapeshifters, or similar. "
                "Do not default to sexless or constructed for mundane humans or office-worker isekai. "
                "Sex is a descriptive identity fact only — not a personality stereotype."
            ),
            "previous_life_age": "Return a former-life remembered age only for reincarnated, transmigrated, reborn, or former-life starts. Otherwise return a blank string.",
            "previous_life_sex": (
                "Former-life sex only for reincarnated/transmigrated/former-life starts; otherwise blank. "
                "Prefer female or male for ordinary former lives. Sexless/constructed or varies-by-form only when the former-world body is clearly nonstandard. "
                "Blank is fine when former sex does not matter."
            ),
            "special_ability_origin": "Return one of: none, acquired, innate. Use none when special powers would overdefine the character; acquired when abilities are learned, earned, unlocked, system-granted, trained, or recovered through play; innate when abilities are inborn, inherited, racial, bodily, soul-deep, or natural to the character.",
            "backstory_mode": "Generate one concise way the character relates to their past. Known past, ordinary remembered life, reincarnated, transmigrated, hidden past, fragmented memories, and locally known history are all valid. Do not default to tragedy, amnesia, exile, destiny, noble bloodline, revenge, or combat roles unless supported.",
            "memory_policy": "Generate one concise memory rule. Known ordinary memory, remembered former life, partial former-life fragments, uncertain rumors, slow discovery, or a custom variant are all valid; do not force mystery unless it fits.",
            "character_backstory": "Generate 2-4 concise sentences of actual character history, not a motto or personality trait. Include: where they were born or what world/community they came from; how they lived before the RPG starts, such as work, family, training, debts, duties, or social position; why they are near the starting point now; and, only if the backstory_mode/world_style suggests reincarnation/transmigration, whether and how they died and what they remember from the former life. Keep it playable and original, but avoid chosen-one framing, noble lineage, revenge, or a combat profession unless supported.",
            "hair": (
                "Hair only for art: length + color + style in a short phrase "
                "(e.g. short brown hair, long silver braid). No face details, no clothes."
            ),
            "facial_features": (
                "Face-only portrait cues: eyes, freckles, scars, jaw, brows, marks. "
                "2–5 short phrases. No hair (use hair field), no clothing, no personality essays."
            ),
            "appearance": (
                "Clothing / worn gear only for art. Prefer zone tags: "
                "'torso: travel coat; feet: dusty boots'. "
                "Do NOT put hair or facial features here — use hair and facial_features fields. "
                "Portraits only use upper-body zones. Weak starts: ordinary clothes."
            ),
            "starter_equipment": (
                "Comma-separated mundane starting items at Start (inventory). "
                "3–7 items. Clothes + tools matching role. Wearables also feed art by body zone. "
                "Near-useless starts: no combat kit/legendaries. Match appearance."
            ),
            "world_races": "Generate a concise list of peoples/species only (e.g. human; human, elf, beastfolk). Include human unless excluded. Never power labels like Low-Power Human, and never skill/growth slogans.",
            "race_magic_rules": "Generate clear per-race magic access rules only. State who can cast, training vs innate, taboos. Do NOT paste global skill compounding delays, cooldowns, or player power fantasy.",
            "race_ability_rules": "Generate clear per-race non-spell ability rules only. Cover modest innate gifts and learned racial arts. Do NOT dump 'near-useless skill compounds' or level-delay timers for all races.",
            "narration_detail": "Generate one prose-detail preference such as concise, balanced, rich, expansive, or a short custom rule for how much scene text each turn should include.",
            "loot_rarity": "Generate one loot rarity policy. It should control how often mundane, rare, enchanted, unique, or legendary items appear.",
            "inventory_weight_limit": "Generate a practical base carry weight limit as a number. Low-powered starts should be modest; superhuman starts can be higher if supported.",
            "inventory_slot_limit": "Generate a practical packed inventory slot limit as a number. Backpacks and containers can change slots later, but base slots should stay understandable.",
            "inventory_rules": "Generate concise carrying and equipment rules, including whether magic storage, backpacks, many accessories, or superhuman item quantities are common.",
            "custom_skills": (
                "Comma-separated skill rules and named seed skills. For weak-seed / compounding fantasy "
                "include: (1) seed skill name/domain, (2) starting rank, (3) how it compounds in fiction, "
                "(4) how ranks are tracked (system UI vs DM notes), (5) XP sources in prose "
                "(practice/mentors/risk/milestones), (6) hard limits. "
                "Do NOT dump long XP formulas here — those belong on the ability growth_math field. "
                "If current_setup has special_abilities, align the seed skill with that ability. "
                "Never default to weather/observation/sandstorm. Use commas between phrases. "
                "User-locked custom_skills must not be rewritten."
            ),
            "quest_style": "Quest STRUCTURE only: how hooks arrive (emergent, job board, faction chains, personal mysteries). Never describe player skills, compounding, near-useless abilities, or power fantasy.",
            "faction_pressure": "Who squeezes the setting socially/politically (guilds, cults, military, local disputes). Never player skill growth or delayed compounding slogans.",
            "economy": "How goods and money move (scarce, coin-driven, barter, guild markets). Never skills, abilities, or compounding.",
            "npc_stat_scaling": "NPC rank pressure vs the player only (mostly weaker, near player, relative ranks, elite-heavy). Never level-delay timers or player skill compounding.",
            "npc_skill_frequency": "How often NPCs have special skills (rare specialists, some trained). Not player growth rules.",
            "npc_density": "How crowded scenes feel (sparse, moderate, dense, faction patrols). No skill slogans.",
            "rank_scale": "A rank ladder string only such as F,E,D,C,B,A,S,SS,SSS.",
            "skill_style": "Short skill-learning policy only (standard, generous, training-heavy, strict). Put long compounding essays in custom_skills instead.",
            "custom_style": "World constraints, genre lean, DM stance. Do not paste only skill timers; put growth timers in custom_skills.",
            "world_style": "Setting/genre phrase only (e.g. modern isekai coastal fantasy). Not an ability description.",
        }
        contract = field_contract(field)
        field_intent = intent_slice_for_field(intent_plan, field)
        contract_rules = [
            f"Field kind: {contract.get('kind') or 'short_phrase'}.",
            str(contract.get("forbidden") or ""),
        ]
        if contract.get("allowed_values"):
            contract_rules.append(
                "Allowed values (pick one exactly unless custom is clearly required by field_context): "
                + ", ".join(str(v) for v in contract["allowed_values"])
            )
        if contract.get("examples"):
            contract_rules.append(
                "Good examples for this field (adapt, do not copy blindly): "
                + " | ".join(str(e) for e in contract["examples"][:4])
            )
        if contract.get("ban_growth_slogans") or contract.get("ban_growth_timers"):
            contract_rules.append(
                "Reject any answer about compounding skills, near-useless skills, level delays, or cooldowns for this field. "
                "Those belong in custom_skills / growth speed fields only."
            )
        prompt = {
            "task": f"Generate one setup value for {field}.",
            "field": field,
            "current_value": current_setup.get(field),
            "nearby_setup": nearby_setup,
            "locked_setup": locked_setup,
            "field_context": field_context,
            "field_contract": contract,
            "field_intent": field_intent,
            "intent_plan_summary": {
                "genre": intent_plan.get("genre"),
                "isekai": intent_plan.get("isekai"),
                "difficulty": intent_plan.get("difficulty"),
                "adapter_hint": intent_plan.get("adapter_hint"),
                "dm_stance": intent_plan.get("dm_stance"),
            }
            if intent_plan.get("raw_idea") or intent_plan.get("genre") or intent_plan.get("isekai")
            else {},
            "field_note": field_notes.get(field, ""),
            "return_shape": {field: "one generated custom phrase for the Custom box" if is_multi_select else "generated value"},
            "rules": base_rules
            + [r for r in contract_rules if r]
            + [
                "If field_intent is present, use only those intent keys for this field; do not invent values from unrelated idea words.",
                "If field_context.random_selected is true, use field_context.selected_values as weighted inspiration, not as the final output.",
                "For multi_select fields, always return one generated custom phrase. Do not return existing option labels as the final value.",
                "For multi_select fields, checked options are weights/inspiration only. The UI will always place your result under Custom.",
                "For world_races, include human unless the concept strongly excludes humans.",
                "For player_public_name and player_title, blank is the normal result; only fill these rare fields when the existing backstory makes them clearly useful.",
                "For previous_life_age and previous_life_sex, blank is the normal result unless the setup clearly includes reincarnation, transmigration, rebirth, or remembered former life.",
                "For special_ability_origin, return exactly one of none, acquired, or innate.",
            ],
        }
    else:
        prompt_current_setup = current_setup
        if group == "character":
            prompt_current_setup = {
                "player_name": current_setup.get("player_name"),
                "player_public_name": current_setup.get("player_public_name"),
                "player_title": current_setup.get("player_title"),
                "player_age": current_setup.get("player_age"),
                "player_sex": current_setup.get("player_sex"),
                "previous_life_age": current_setup.get("previous_life_age"),
                "previous_life_sex": current_setup.get("previous_life_sex"),
                "special_ability_origin": current_setup.get("special_ability_origin"),
                "backstory_mode": current_setup.get("backstory_mode"),
                "memory_policy": current_setup.get("memory_policy"),
                "character_backstory": current_setup.get("character_backstory"),
                "special_abilities": current_setup.get("special_abilities"),
            }
        prompt = {
            "task": "Generate playable setup values for an endless AI RPG. Return the generated JSON object only.",
            "group": group,
            "current_setup": prompt_current_setup,
            "locked_setup": locked_setup,
            "return_fields": return_fields,
            "character_identity_rules": [
                "player_public_name is rare. Leave it blank by default; fill it only when the backstory implies an alias, public handle, former-world name, or name strangers would plausibly know.",
                "player_title is rare. Leave it blank by default; fill it only when reputation, formal office, reincarnated former power, high strength, infamous deeds, or local rumors make a title more playable.",
                "player_age and player_sex are current-life descriptive identity fields. Prefer male/female for ordinary humanoids; rare exotic sex categories only when the world supports them. Keep them concise, and do not make them behavior constraints or stereotypes.",
                "previous_life_age and previous_life_sex are only for reincarnated, transmigrated, reborn, or former-life starts. Leave them blank for ordinary known, hidden, or nameless starts without former-life memory.",
                "Backstory mode affects both optional identity fields: reincarnated/transmigrated characters may carry former-world names or former-rank titles, while hidden/amnesia/nameless starts often stay blank unless the backstory gives NPC-facing clues.",
                "backstory_mode and memory_policy describe how much of the past matters at the start without forcing mystery, trauma, or amnesia.",
                "character_backstory should be 2-4 concise sentences with concrete origin details: birthplace/original world, former livelihood or role, important ties/debts/duties, why the character is at the opening, and death/reincarnation details only when fitting.",
                "custom_skills and special_abilities should fit the concrete backstory, race rules, world rules, and any optional identity fields already generated.",
                "custom_skills must be one comma-separated string when present; never use bullets or newlines for proficiencies.",
                "special_ability_origin controls ability generation: none should prevent setup abilities, acquired should lean toward future unlocked or earned abilities, and innate should lean toward inherent starting abilities.",
            ],
            "rules": base_rules + ["Generate fields one at a time in the order requested. Later fields must fit earlier current_setup values."],
        }
    if text_mode:
        source_length = len(str(current_setup.get("_optimize_text") or ""))
        prompt_length = len(str(current_setup.get("_user_prompt") or ""))
        token_cap = max(220, min(620, (source_length + prompt_length) // 3 + 180))
    elif return_fields == ["player_name"]:
        token_cap = 80
    elif return_fields == ["special_abilities"]:
        token_cap = 700
    elif not text_mode and return_fields == ["character_backstory"]:
        token_cap = 360
    elif not text_mode and return_fields == ["custom_skills"]:
        token_cap = 640
    elif not text_mode and len(return_fields) == 1:
        token_cap = 180
    else:
        token_cap = _env_int("AI_RPG_RANDOMIZER_TOKENS", 520)

    # Expand ONE_SKILL_FRAME skeleton when rolling custom_skills
    if not text_mode and return_fields == ["custom_skills"]:
        cur_skills = str(current_setup.get("custom_skills") or "")
        pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
        one_skillish = (
            "ONE_SKILL_FRAME" in cur_skills
            or str(pf.get("growth") or "").lower() == "compounding"
            or str(pf.get("start_power") or "").lower() in {"near_useless", "weak"}
        )
        if one_skillish and isinstance(prompt, dict):
            abilities = current_setup.get("special_abilities")
            ability_hint = ""
            if isinstance(abilities, list) and abilities:
                a0 = abilities[0] if isinstance(abilities[0], dict) else {}
                ability_hint = f"{a0.get('name') or ''}: {str(a0.get('description') or '')[:120]}"
            prompt["task"] = (
                "Expand skill fiction rules for a hardcore one-skill / compounding run into a rich custom_skills string. "
                "Leave long XP formulas for the ability growth_math field; mention math only briefly if at all."
            )
            prompt["one_skill_expansion"] = {
                "seed_ability_if_any": ability_hint,
                "must_include": [
                    "exact seed skill/domain name (fresh; not weather/observation by default)",
                    "starting rank/power (near-useless / F / level 1)",
                    "how compounding works in fiction",
                    "how the DM or system tracks rank/level",
                    "how XP or progress is earned (practice, mentors, risk, or DM milestones) — prose, not formula tables",
                    "hard limits (no second combat skill toolkit at start)",
                ],
                "math_home": "Put calculable XP/rank formulas on special_abilities[].growth_math when abilities are rolled, not here.",
            }
            prompt["rules"] = list(prompt.get("rules") or []) + [
                "Output a single comma-separated custom_skills string (no bullets).",
                "If a seed ability already exists, align the skill domain with it.",
                "Do not invent multiple independent combat skills.",
                "Be concrete and tabletop-playable.",
            ]

    if idea_sparks_pkg and isinstance(prompt, dict) and idea_sparks_pkg.get("sparks"):
        # Inject once for all field groups (abilities already set earlier; others get it here).
        prompt.setdefault("idea_sparks", idea_sparks_pkg)
    try:
        result = _chat_json(
            "Return JSON only. Generate direct values. Do not explain. Do not echo the request.",
            json.dumps(prompt, ensure_ascii=True),
            timeout=_model_timeout(45, 240, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
            phase="setup_randomize",
            max_tokens=token_cap,
        )
        validated = _validate_setup_randomization(group, result)
    except Exception as first_exc:
        # Small local models often break ability JSON shape — fall back instead of hard-failing setup.
        if return_fields == ["special_abilities"]:
            validated = {"special_abilities": _fallback_special_abilities(current_setup)}
        else:
            raise first_exc
    if not text_mode and return_fields == ["player_name"]:
        current_name = str(current_setup.get("player_name") or "").strip().lower()
        generated_name = str(validated.get("player_name") or "").strip().lower()
        if current_name and generated_name == current_name:
            retry_prompt = {
                "task": "Generate one new playable RPG player name.",
                "forbidden_name": current_setup.get("player_name"),
                "return_shape": {"player_name": "new name that is not the forbidden_name"},
            }
            validated = _validate_setup_randomization(
                group,
                _chat_json(
                    "Return JSON only. Create a different name. Do not explain.",
                    json.dumps(retry_prompt, ensure_ascii=True),
                    timeout=_model_timeout(30, 120, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                    phase="setup_randomize_name_retry",
                    max_tokens=80,
                ),
            )
    elif not text_mode and return_fields == ["character_backstory"]:
        generated_backstory = str(validated.get("character_backstory") or "").strip()
        if _backstory_is_too_vague(generated_backstory):
            retry_prompt = {
                "task": "Regenerate the character backstory as concrete RPG setup history.",
                "rejected_backstory": generated_backstory,
                "nearby_setup": prompt.get("nearby_setup") if isinstance(prompt, dict) else current_setup,
                "return_shape": {"character_backstory": "2-4 concise sentences of concrete history"},
                "required_details": [
                    "birthplace, original world, or home community",
                    "how the character lived before play: work, training, family, duties, debts, or social position",
                    "why the character is at or near the starting point now",
                    "death and reincarnation/transmigration details only if the setup calls for them",
                ],
                "rules": [
                    "Do not return a motto, personality trait, vague lesson, or single aphorism.",
                    "Keep it playable and leave room for discovery.",
                ],
            }
            validated = _validate_setup_randomization(
                group,
                _chat_json(
                    "Return JSON only. Create concrete character history, not a vague hook.",
                    json.dumps(retry_prompt, ensure_ascii=True),
                    timeout=_model_timeout(30, 180, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                    phase="setup_randomize_backstory_retry",
                    max_tokens=360,
                ),
            )
    elif not text_mode and return_fields == ["special_abilities"]:
        existing = (
            current_setup.get("special_abilities")
            if isinstance(current_setup.get("special_abilities"), list)
            else []
        )
        generated = validated.get("special_abilities")
        if _abilities_match_existing(generated if isinstance(generated, list) else [], existing):
            retry_prompt = {
                "task": "Generate different special abilities. The previous roll was rejected as a duplicate.",
                "forbidden_abilities": existing,
                "ability_origin": (current_setup.get("_field_context") or {}).get("ability_origin")
                or current_setup.get("special_ability_origin"),
                "field_intent": intent_slice_for_field(intent_plan, "special_abilities"),
                "return_shape": {
                    "special_abilities": [
                        {
                            "name": "new ability name",
                            "description": "new concrete description, not a paraphrase of forbidden_abilities",
                            "locked": False,
                            "prerequisites": "",
                            "cost": "no cost",
                            "growth_math": "concrete XP/rank formulas",
                        }
                    ]
                },
                "rules": [
                    "Return JSON only.",
                    "Do not reuse names or paraphrase descriptions from forbidden_abilities.",
                    "Avoid weather/sandstorm/invisibility/observation clichés unless the world is clearly about that.",
                    "If growth/compounding or near_useless start_power: return exactly one weak seed ability.",
                    "Invent a fresh domain (craft, social, memory, movement, craft, etc.).",
                    "Always fill growth_math with calculable numbers for each ability.",
                ],
            }
            try:
                validated = _validate_setup_randomization(
                    group,
                    _chat_json(
                        "Return JSON only. New abilities only — not duplicates.",
                        json.dumps(retry_prompt, ensure_ascii=True),
                        timeout=_model_timeout(30, 180, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                        phase="setup_randomize_abilities_retry",
                        max_tokens=700,
                    ),
                )
            except Exception:
                validated = {"special_abilities": _fallback_special_abilities(current_setup)}
            # Still same? Force local variety pool.
            gen2 = validated.get("special_abilities")
            if _abilities_match_existing(gen2 if isinstance(gen2, list) else [], existing):
                validated = {"special_abilities": _fallback_special_abilities(current_setup)}
        # Ensure math + discretionary optimize pass on growth_math
        abilities_out = validated.get("special_abilities")
        if isinstance(abilities_out, list):
            validated["special_abilities"] = _maybe_optimize_ability_growth_math(
                abilities_out,
                intent_plan=intent_plan,
                current_setup=current_setup,
            )
    elif not text_mode and len(return_fields) == 1:
        field = return_fields[0]
        field_context = current_setup.get("_field_context") or {}
        if field_context.get("random_selected"):
            selected = [str(value).strip() for value in field_context.get("selected_values") or [] if str(value).strip()]
            selected_joined = ", ".join(selected).lower()
            current_value = str(current_setup.get(field) or "").strip().lower()
            generated_raw = validated.get(field)
            if isinstance(generated_raw, list):
                generated_value = ", ".join(str(value).strip() for value in generated_raw if str(value).strip()).lower()
            else:
                generated_value = str(generated_raw or "").strip().lower()
            if generated_value and generated_value in {selected_joined, current_value}:
                retry_prompt = {
                    "task": f"Create one generated custom setup value for {field}.",
                    "selected_weights": selected,
                    "world_style": current_setup.get("world_style"),
                    "rule": "Use selected_weights as inspiration, but do not return the weights unchanged. Combine, expand, or reinterpret them into one coherent setting phrase.",
                    "return_shape": {field: "generated custom value"},
                }
                validated = _validate_setup_randomization(
                    group,
                    _chat_json(
                        "Return JSON only. Create a generated custom value, not the selected option list.",
                        json.dumps(retry_prompt, ensure_ascii=True),
                        timeout=_model_timeout(30, 120, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                        phase="setup_randomize_weight_retry",
                        max_tokens=min(token_cap, 180),
                    ),
                )
    normalized = _normalize_previous_life_identity_fields(return_fields, current_setup, validated)
    normalized = _thin_optional_identity_fields(return_fields, current_setup, normalized)
    if "custom_skills" in normalized:
        normalized["custom_skills"] = _comma_separated_phrases(normalized.get("custom_skills"))
    if isinstance(normalized.get("special_abilities"), list):
        # If abilities arrived via a multi-field group path, still guarantee math exists.
        if return_fields != ["special_abilities"]:
            pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
            one_skillish = str(pf.get("growth") or "").lower() == "compounding" or str(
                pf.get("start_power") or ""
            ).lower() in {"near_useless", "weak"}
            if one_skillish or random.random() < 0.35:
                normalized["special_abilities"] = _maybe_optimize_ability_growth_math(
                    normalized["special_abilities"],
                    intent_plan=intent_plan,
                    current_setup=current_setup,
                )
            else:
                normalized["special_abilities"] = _ensure_ability_growth_math(normalized["special_abilities"])
        else:
            normalized["special_abilities"] = _ensure_ability_growth_math(normalized["special_abilities"])
    # Prefer realistic male/female distribution unless the world supports exotic sexes.
    if not text_mode:
        normalized = _normalize_sex_fields(return_fields, current_setup, normalized)
    # Post-lint: reject growth slogans in structure fields; one repair attempt then deterministic clean.
    if not text_mode:
        normalized = _lint_and_repair_setup_fields(
            group=group,
            return_fields=return_fields,
            current_setup=current_setup,
            intent_plan=intent_plan,
            result=normalized,
            randomize_idea=randomize_idea,
        )
    return normalized


def _normalize_sex_fields(
    return_fields: list[str],
    current_setup: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Nudge exotic sex rolls toward male/female when the world is ordinary humanoid."""
    next_result = dict(result)
    exotic_ok = _world_supports_exotic_sex({**current_setup, **next_result})
    exotic_values = {"sexless or constructed", "varies by form"}
    rare_values = {"intersex"}
    for field in ("player_sex", "previous_life_sex"):
        if field not in return_fields or field not in next_result:
            continue
        value = str(next_result.get(field) or "").strip().lower()
        if not value:
            continue
        if value in exotic_values and not exotic_ok:
            # ~95% remap to male/female; tiny chance keep blank
            next_result[field] = random.choice(["female", "male", "female", "male", "female", "male", ""])
        elif value in rare_values and not exotic_ok and random.random() < 0.55:
            # Soften intersex frequency on mundane worlds
            next_result[field] = random.choice(["female", "male"])
    return next_result


def _lint_and_repair_setup_fields(
    *,
    group: str,
    return_fields: list[str],
    current_setup: dict[str, Any],
    intent_plan: dict[str, Any],
    result: dict[str, Any],
    randomize_idea: str,
) -> dict[str, Any]:
    """Strip mis-slotted power-fantasy slogans from structure fields."""
    idea = randomize_idea or str(intent_plan.get("raw_idea") or "")
    context = {**current_setup, **result, "_compose_intent": intent_plan}
    dirty_fields = [
        field
        for field in return_fields
        if field in result and field_is_contaminated(field, result.get(field), idea)
    ]
    if not dirty_fields:
        return result

    repaired = dict(result)
    # One LLM repair pass for single-field requests (cheap, targeted).
    if len(return_fields) == 1 and dirty_fields == return_fields:
        field = return_fields[0]
        contract = field_contract(field)
        reasons = field_contamination_reasons(field, result.get(field), idea)
        try:
            repair_prompt = {
                "task": f"Repair the setup value for {field}; the previous value was rejected.",
                "field": field,
                "rejected_value": result.get(field),
                "reject_reasons": reasons,
                "field_contract": contract,
                "examples": contract.get("examples") or [],
                "nearby_setup": {
                    k: current_setup.get(k)
                    for k in (
                        "world_style",
                        "tone",
                        "start_location",
                        "difficulty",
                        "game_system",
                        "custom_skills",
                    )
                    if k in current_setup
                },
                "intent_summary": {
                    "genre": intent_plan.get("genre"),
                    "isekai": intent_plan.get("isekai"),
                    "keywords": intent_plan.get("keywords"),
                },
                "return_shape": {field: "clean value matching field_contract only"},
                "rules": [
                    "Return JSON only with the repaired field.",
                    str(contract.get("forbidden") or ""),
                    "Do not mention compounding, near-useless skills, level delays, or cooldowns unless this field is custom_skills or skill growth.",
                    "Match examples' shape: short structural phrase for structure fields.",
                ],
            }
            repaired_raw = _validate_setup_randomization(
                group,
                _chat_json(
                    "Return JSON only. Repair the contaminated setup field.",
                    json.dumps(repair_prompt, ensure_ascii=True),
                    timeout=_model_timeout(20, 90, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                    phase="setup_randomize_field_lint_repair",
                    max_tokens=160,
                ),
            )
            candidate = repaired_raw.get(field)
            if candidate is not None and not field_is_contaminated(field, candidate, idea):
                repaired[field] = candidate
                return repaired
        except Exception:
            pass

    # Deterministic sanitize for anything still dirty (or multi-field batches).
    cleaned, _dirty = sanitize_setup_fields(repaired, idea=idea, context=context)
    for field in dirty_fields:
        if field in cleaned:
            repaired[field] = cleaned[field]
        elif field in return_fields:
            fallback = structural_fallback(field, context)
            if fallback is not None:
                repaired[field] = fallback
    return repaired


def _thin_optional_identity_fields(return_fields: list[str], current_setup: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    next_result = dict(result)
    requested_fields = set(return_fields)
    for field in OPTIONAL_IDENTITY_FIELDS.intersection(next_result).intersection(requested_fields):
        value = str(next_result.get(field) or "").strip()
        if not value:
            next_result[field] = ""
            continue
        if random.random() > _optional_identity_fill_chance(field, current_setup):
            next_result[field] = ""
        else:
            next_result[field] = value
    return next_result


def _normalize_previous_life_identity_fields(return_fields: list[str], current_setup: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    next_result = dict(result)
    requested_fields = set(return_fields)
    if _setup_has_former_life_identity({**current_setup, **next_result}):
        for field in PREVIOUS_LIFE_IDENTITY_FIELDS.intersection(next_result).intersection(requested_fields):
            next_result[field] = str(next_result.get(field) or "").strip()
        return next_result
    for field in PREVIOUS_LIFE_IDENTITY_FIELDS.intersection(requested_fields):
        next_result[field] = ""
    return next_result


def _setup_has_former_life_identity(setup: dict[str, Any]) -> bool:
    context_text = " ".join(
        str(setup.get(key) or "")
        for key in ("backstory_mode", "memory_policy", "character_backstory")
    ).lower()
    return any(marker in context_text for marker in ("reincarnated", "transmigrated", "former life", "former-life", "reborn"))


def _optional_identity_fill_chance(field: str, current_setup: dict[str, Any]) -> float:
    backstory_mode = str(current_setup.get("backstory_mode") or "").lower()
    memory_policy = str(current_setup.get("memory_policy") or "").lower()
    backstory = str(current_setup.get("character_backstory") or "").lower()
    context_text = " ".join([backstory_mode, memory_policy, backstory])
    chance = 0.22 if field == "player_public_name" else 0.14

    if any(marker in context_text for marker in ("reincarnated", "transmigrated", "former life", "another world", "reborn")):
        chance += 0.12 if field == "player_public_name" else 0.16
    if any(marker in context_text for marker in ("hidden", "amnesia", "fragment", "nameless", "unknown")):
        chance += 0.10 if field == "player_public_name" else 0.06

    if field == "player_public_name":
        alias_markers = ("known as", "called", "alias", "nickname", "public name", "handle", "street name", "false name")
        if any(marker in context_text for marker in alias_markers):
            chance += 0.24
    else:
        title_markers = (
            "title",
            "rank",
            "emperor",
            "empress",
            "king",
            "queen",
            "lord",
            "lady",
            "general",
            "commander",
            "champion",
            "hero",
            "saint",
            "archmage",
            "sect master",
            "elder",
            "ascendant",
            "s-rank",
            "mythic",
        )
        if any(marker in context_text for marker in title_markers):
            chance += 0.32

    return min(chance, 0.68)


def _backstory_is_too_vague(backstory: str) -> bool:
    text = backstory.strip().lower()
    if len(text) < 140:
        return True
    origin_markers = {
        "born",
        "raised",
        "grew up",
        "from ",
        "village",
        "town",
        "city",
        "district",
        "settlement",
        "world",
        "former life",
        "woke",
        "reincarnated",
        "transmigrated",
    }
    life_markers = {
        "worked",
        "trained",
        "apprentice",
        "family",
        "parent",
        "crew",
        "guild",
        "duty",
        "debt",
        "job",
        "trade",
        "lived",
        "served",
        "studied",
        "kept",
        "career",
        "profession",
        "technician",
        "student",
        "office",
        "years as",
        "spent years",
    }
    transition_markers = {"arrived", "left", "sent", "reached", "came", "fled", "returned", "woke", "now"}
    has_origin = any(marker in text for marker in origin_markers)
    has_prior_life = any(marker in text for marker in life_markers)
    has_transition = any(marker in text for marker in transition_markers)
    return not (has_origin and has_prior_life and has_transition)


def _validate_setup_randomization(group: str, result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise LlmError("Randomizer returned a non-object JSON value.")

    echoed_prompt_keys = {"task", "allowed_groups", "output_shape", "rules", "current_setup", "locked_setup", "return_fields"}
    if len(echoed_prompt_keys.intersection(result)) >= 2:
        raise LlmError("Randomizer echoed the setup schema instead of generating playable values.")

    placeholder_values = {
        "string",
        "boolean",
        "string or comma-separated list",
        "immutable base description",
        "no cost/model decides/custom cost text",
    }
    generated_keys = {
        key
        for key, value in result.items()
        if key not in {"notes", "locked_setup", "current_setup", "return_fields", "rules", "task"}
        and value not in (None, "", [], {})
        and str(value).strip().lower() not in placeholder_values
    }
    requested_field = group.split(":", 1)[1] if group.startswith(("field:", "optimize:", "text:")) else ""
    if requested_field in OPTIONAL_IDENTITY_FIELDS and requested_field in result:
        generated_keys.add(requested_field)
    if requested_field == "special_abilities" and "special_abilities" in result:
        generated_keys.add("special_abilities")
    if not generated_keys:
        raise LlmError("Randomizer returned no usable setup values.")

    if group.startswith(("field:", "optimize:", "text:")):
        requested = requested_field
        if requested not in generated_keys:
            raise LlmError(f"Randomizer did not return the requested field: {requested}.")

    if "special_abilities" in result:
        abilities = result["special_abilities"]
        # Small models often return one ability object instead of a list — coerce.
        if isinstance(abilities, dict):
            abilities = [abilities]
            result["special_abilities"] = abilities
        elif isinstance(abilities, str) and abilities.strip():
            # Rare: model dumps a single ability name/description string
            abilities = [{"name": abilities.strip()[:100], "description": abilities.strip()[:400]}]
            result["special_abilities"] = abilities
        if not isinstance(abilities, list):
            raise LlmError("Randomizer returned special_abilities, but it was not a list.")
        cleaned_abilities: list[dict[str, Any]] = []
        for ability in abilities:
            if isinstance(ability, str) and ability.strip():
                ability = {"name": ability.strip()[:100], "description": ability.strip()[:400]}
            if not isinstance(ability, dict):
                raise LlmError("Randomizer returned a malformed special ability.")
            name = str(ability.get("name") or "").strip().lower()
            description = str(ability.get("description") or "").strip().lower()
            if name in placeholder_values or description in placeholder_values:
                raise LlmError("Randomizer returned placeholder special ability values.")
            cleaned_abilities.append(ability)
        result["special_abilities"] = cleaned_abilities

    if "special_ability_origin" in result:
        origin = str(result.get("special_ability_origin") or "").strip().lower().replace("-", " ").replace("_", " ")
        aliases = {
            "none": "none",
            "no abilities": "none",
            "no special abilities": "none",
            "gained": "acquired",
            "acquired": "acquired",
            "learned": "acquired",
            "earned": "acquired",
            "unlocked": "acquired",
            "born with": "innate",
            "inborn": "innate",
            "innate": "innate",
            "inherent": "innate",
            "natural": "innate",
        }
        if origin not in aliases:
            raise LlmError("Randomizer returned an invalid special_ability_origin.")
        result["special_ability_origin"] = aliases[origin]

    return result


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        first_object = _first_json_object(stripped)
        if first_object:
            return json.loads(first_object)
        raise


def _first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return ""


def fallback_turn(context: dict[str, Any], player_input: str) -> dict[str, Any]:
    location = context.get("current_location", {}).get("name", "the road")
    is_opening_scene = str(player_input).startswith("__opening_scene_request__")
    is_continue_scene = str(player_input).startswith("__continue_scene_request__")
    opts = ((context.get("settings") or {}).get("playthrough_options") or {}) if isinstance(context, dict) else {}
    opts = opts if isinstance(opts, dict) else {}
    if is_opening_scene:
        difficulty = str(opts.get("difficulty") or "normal").lower()
        pressure = {
            "easy": "The pressure is light but real — a missed chance more than a killing blow.",
            "normal": "The place has enough pressure to make standing still feel like a decision.",
            "hard": "The air already feels tight: scarce help, sharp eyes, and little room for loud mistakes.",
            "brutal": "Nothing here is soft. The first wrong step could cost blood, coin, or a name.",
        }.get(difficulty, "The place has enough pressure to make standing still feel like a decision.")
        system_bit = ""
        if opts.get("game_system"):
            style = str(opts.get("system_style") or "subtle blue-window system")
            seed = opts.get("weak_skill_seed") if isinstance(opts.get("weak_skill_seed"), dict) else {}
            seed_name = str(seed.get("name") or "Observation")
            seed_val = seed.get("value", 1)
            system_bit = (
                f"\n\nFor a heartbeat the world overlays a thin {style} edge — nothing loud, only readable:\n"
                f"[ STATUS ] Location: {location}\n"
                f"[ SKILL  ] {seed_name} … rank F / value {seed_val} (nearly useless)\n"
                "[ NOTE   ] No combat suite. Grow through practice and risk.\n"
                "The window fades as quickly as it arrived, leaving only the ordinary street and that one thin promise of growth."
            )
        elif isinstance(opts.get("weak_skill_seed"), dict):
            seed = opts["weak_skill_seed"]
            system_bit = (
                f"\n\nSomething in you recognizes a faint aptitude — {seed.get('name') or 'Observation'} — "
                "so slight it barely counts, more a habit of looking than a power."
            )
        narration = (
            f"{location} comes into focus without waiting for a command. Damp air gathers at the edges of the street, "
            "voices move behind closed doors, and something nearby is just unresolved enough to invite a first choice. "
            "The first details are practical rather than grand: where the ground is slick, where the nearest shelter or exit might be, "
            "who seems busy enough to ignore trouble, and which small sound keeps tugging attention back toward the center of the scene. "
            f"{pressure}"
            f"{system_bit}\n\n"
            "A few possible openings sit close together. You could listen before anyone notices you listening, approach the nearest sign of activity, "
            "inspect the odd detail that does not quite belong, ask a passerby for the local shape of things, or move on before the moment chooses a shape for you. "
            "The world offers a modest opening instead of a grand revelation, with room for caution, curiosity, conversation, or immediate motion. "
            "Whatever you choose first will give the scene its sharper edge."
        )
        event_summary = f"The opening scene settled around {location} before the player acted."
        event_title = "Opening scene"
        turn_summary = f"opening: established the first playable moment at {location}."
        journal_content = event_summary
    elif is_continue_scene:
        narration = (
            f"The moment in {location} keeps moving. A nearby sound sharpens, someone shifts where they thought they were hidden, "
            "and the scene offers a little more shape without forcing your hand. The air has the patient tension of a place deciding whether it is ordinary or dangerous: "
            "a pause in conversation, a scrape of movement, a glance that lingers too long, or a route that suddenly seems more important than it did a breath ago. "
            "None of it declares an answer by itself, but together it gives the current situation more weight.\n\n"
            "You still have room to approach, wait, speak, investigate, prepare, or walk away. Waiting may reveal who is involved, acting may seize the initiative, "
            "and leaving may avoid a problem before it grows teeth. The scene advances only a step, enough to keep the world alive while preserving your next choice. "
            "There is still useful information in the texture around you: where attention gathers, where the safest retreat might be, who benefits if no one interferes, "
            "and which detail feels newly urgent now that the silence has had time to stretch."
        )
        event_summary = f"The scene at {location} advanced slightly while the player waited for more context."
        event_title = "Scene pressure"
        turn_summary = f"continue: advanced the current scene around {location} without a player action."
        journal_content = event_summary
    else:
        intent = _trim_text(player_input, 260)
        narration = (
            f"You take a careful moment in {location}. The world does not leap to answer all at once: "
            "someone coughs behind a shutter, damp air clings to your sleeves, and your last choice hangs in the street. "
            "The immediate surroundings answer with small, grounded details rather than a perfect result: a shift in posture, a sound from the side, "
            "a hint of opportunity, and the quiet cost of being observed while you decide what comes next.\n\n"
            f"Your intent was clear: {intent}. The place gives you a response that is playable but cautious. If you press forward, you can turn that intent into a direct confrontation, "
            "a careful investigation, a practical search for tools or exits, or a conversation that tests who here is willing to help. If you hold back, the scene still has texture: "
            "weather, distance, witnesses, and uncertainty all matter. For now, the world leaves the next move in your hands instead of inventing one for you. "
            "The safest next step is not obvious, but several playable paths are close enough to reach."
        )
        event_summary = f"The player paused to act deliberately: {player_input}"
        event_title = "A cautious pause"
        turn_summary = f"player: acted cautiously in current location. response: fallback pause around {location}."
        journal_content = f"The player acted in {location}: {player_input}"
    return {
        "scene_plan": {
            "goal": "Keep the current location playable without forcing a player action.",
            "focus_points": [
                {
                    "kind": "location",
                    "summary": f"Ground the scene around {location} with one immediate choice opening.",
                    "event_worthy": False,
                    "persistence": "temporary",
                }
            ],
        },
        "narration_segments": [{"label": "fallback", "text": narration}],
        "narration": narration,
        "player": {
            "health_delta": 0,
            "max_health_delta": 0,
            "xp_delta": 0,
            "gold_delta": 0,
            "level_delta": 0,
            "move_to_location": None,
            "move_to_location_code": None,
            "karma_delta": 0,
            "karma_reason": "",
            "karma_visibility": "private",
        },
        "inventory_changes": [],
        "skill_changes": [],
        "locations": [],
        "npcs": [],
        "relationships": [],
        "events": [
            {
                "title": event_title,
                "location": location,
                "summary": event_summary,
                "status": "background",
                "persistence": "background",
                "disappear_chance": 0,
                "respawn_chance": 0,
            }
        ],
        "conversations": [],
        "response_drafts": [],
        "index_updates": [],
        "gm_events": [],
        "self_check": {
            "passed": True,
            "issues_found": [],
            "corrections_made": [],
            "reference_check": "Fallback used no indexed references.",
            "consistency_check": "Fallback does not alter player state.",
        },
        "turn_summary": turn_summary,
        "journal": [{"kind": "event", "content": journal_content}],
        "scene_focus": "filler",
    }


def generate_input_suggestions(context: dict[str, Any], instruction: str = "") -> dict[str, Any]:
    settings = context.get("settings") or {}
    suggestion_instruction = str(instruction or "").strip()[:500]
    compact_context = {
        "settings": {
            "setup_complete": settings.get("setup_complete"),
            "playthrough_options": settings.get("playthrough_options"),
        },
        "player": context.get("player"),
        "active_player_alias": context.get("active_player_alias"),
        "current_location": context.get("current_location"),
        "skills": context.get("skills"),
        "abilities": context.get("abilities"),
        "inventory": context.get("inventory"),
        "equipment_slots": context.get("equipment_slots"),
        "inventory_capacity_modifiers": context.get("inventory_capacity_modifiers"),
        "inventory_summary": context.get("inventory_summary"),
        "locations": context.get("locations", [])[:4],
        "events": context.get("events", [])[:8],
        "conversations": context.get("conversations", [])[:6],
        "relevant_sources": context.get("relevant_sources", [])[:6],
        "turn_summaries": context.get("turn_summaries", [])[:6],
    }
    prompt = {
        "task": "Generate exactly 3 recommended player inputs for the next RPG turn.",
        "world_state": compact_context,
        "user_instruction": suggestion_instruction,
        "return_shape": {"suggestions": ["player input option", "player input option", "player input option"]},
        "rules": [
            "Return JSON only.",
            "Each suggestion must be a direct action or spoken intent the player could submit next.",
            "If user_instruction is present, use it to steer the suggestions while staying consistent with the scene.",
            "Use the current scene and known indexed facts; do not reveal hidden information or future outcomes.",
            "Do not continue the story, narrate results, or decide that the player already chose an option.",
            f"Keep each suggestion concise, specific, and playable. Aim for about {SUGGESTION_TARGET_CHARS} visible characters and never exceed {SUGGESTION_MAX_CHARS} characters.",
            "Offer meaningfully different approaches such as cautious, social, investigative, practical, risky, or evasive when they fit.",
        ],
    }
    result = _chat_json(
        "Return JSON only. Create concise RPG player input suggestions. Do not explain.",
        json.dumps(prompt, ensure_ascii=True),
        timeout=_model_timeout(45, 240, "AI_RPG_SUGGESTION_TIMEOUT"),
        phase="input_suggestions",
        max_tokens=_env_int("AI_RPG_SUGGESTION_TOKENS", 180),
    )
    raw_suggestions = result.get("suggestions") or result.get("options") or []
    suggestions: list[str] = []
    if isinstance(raw_suggestions, list):
        for item in raw_suggestions:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("input") or item.get("suggestion") or "").strip()
            else:
                text = str(item or "").strip()
            text = _clip_suggestion_text(text)
            if text and text not in suggestions:
                suggestions.append(text)
            if len(suggestions) == 3:
                break
    if len(suggestions) != 3:
        raise LlmError("Model did not return exactly 3 usable input suggestions.")
    return {"suggestions": suggestions}


def _clip_suggestion_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip("-0123456789. )\t"))
    if len(cleaned) <= SUGGESTION_MAX_CHARS:
        return cleaned
    clipped = cleaned[:SUGGESTION_MAX_CHARS].rsplit(" ", 1)[0].rstrip(" ,.;:-")
    return clipped or cleaned[:SUGGESTION_MAX_CHARS].rstrip()


def estimated_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def enforce_token_budget(
    system_prompt: str,
    user_prompt: str,
    *,
    max_input_tokens: int | None = None,
    reserve_output_tokens: int | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """
    Pre-call estimation and pruning so prompt input stays under a safe budget.
    Prefer truncating the user prompt body (world packet) while preserving the system prompt.
    """
    config = get_model_config()
    context_window = int(config.get("context_window") or context_window_tokens() or DEFAULT_CONTEXT_TOKENS)
    soft_cap, hard_cap = _response_token_settings(config)
    requested_reserve = int(
        reserve_output_tokens if reserve_output_tokens is not None else (hard_cap or soft_cap or DEFAULT_RESPONSE_HARD_CAP)
    )
    # Never reserve so much that the system prompt alone cannot fit.
    system = str(system_prompt or "")
    user = str(user_prompt or "")
    system_tokens = estimated_tokens(system)
    # Keep at least ~20% of context for output, but leave headroom for system + a usable user packet.
    reserve = min(requested_reserve, max(256, context_window // 5))
    budget = int(max_input_tokens if max_input_tokens is not None else max(1024, context_window - reserve))
    if system_tokens + 512 > budget:
        # Expand effective input budget when the fixed system contract is large (common for this game).
        budget = min(context_window - 256, system_tokens + max(1500, context_window // 3))
        reserve = max(0, context_window - budget)
    total = system_tokens + estimated_tokens(user)
    diagnostics: dict[str, Any] = {
        "enabled": True,
        "context_window": context_window,
        "reserve_output_tokens": reserve,
        "effective_input_budget": budget,
        "before_estimated_tokens": total,
        "pruned": False,
        "truncated_chars": 0,
        "soft_pass": False,
    }
    if total <= budget:
        diagnostics["after_estimated_tokens"] = total
        diagnostics["within_budget"] = True
        return system, user, diagnostics

    # Keep system intact; shrink user prompt from the middle until under budget.
    allowed_user = max(256, budget - system_tokens - 16)
    max_user_chars = max(600, allowed_user * 4 - 96)
    original_user_len = len(user)
    attempts = 0
    while estimated_tokens(system) + estimated_tokens(user) > budget and attempts < 8:
        attempts += 1
        if len(user) <= 500:
            break
        target_chars = min(len(user) - 250, max_user_chars)
        target_chars = max(500, target_chars)
        head = int(target_chars * 0.55)
        tail = max(160, target_chars - head - 80)
        user = (
            user[:head]
            + "\n…[truncated by enforce_token_budget for input token limit]…\n"
            + user[-tail:]
        )
        max_user_chars = max(500, int(max_user_chars * 0.8))
        diagnostics["pruned"] = True
    diagnostics["truncated_chars"] = max(0, original_user_len - len(user))
    total_after = estimated_tokens(system) + estimated_tokens(user)
    diagnostics["after_estimated_tokens"] = total_after
    diagnostics["within_budget"] = total_after <= budget
    if not diagnostics["within_budget"]:
        # Soft-pass rather than killing the turn: still send the pruned packet.
        # Hard-fail only if the system prompt alone cannot fit the context window.
        if system_tokens >= context_window - 128:
            raise LlmError(
                f"Token budget exceeded: system prompt alone is ~{system_tokens} tokens "
                f"for context_window={context_window}."
            )
        diagnostics["soft_pass"] = True
        diagnostics["within_budget"] = False
    return system, user, diagnostics


def _turn_token_default(context: dict[str, Any], phase: str) -> int:
    options = (context.get("settings") or {}).get("playthrough_options") or {}
    detail = str(options.get("narration_detail") or "rich").strip().lower()
    draft_defaults = {
        "concise": 900,
        "balanced": DEFAULT_RESPONSE_TOKEN_CAP,
        "rich": 1700,
        "expansive": 2400,
    }
    verify_defaults = {
        "concise": 700,
        "balanced": 950,
        "rich": 1300,
        "expansive": 1800,
    }
    defaults = verify_defaults if phase == "verify" else draft_defaults
    return defaults.get(detail, defaults["rich"])


def _chat_text(
    system_prompt: str,
    user_prompt: str,
    timeout: int = 90,
    usage: list[dict[str, Any]] | None = None,
    phase: str = "draft_dsl",
    max_tokens: int | None = None,
    trace: list[dict[str, Any]] | None = None,
    temperature: float = 0.7,
) -> str:
    """Plain-text model call (no JSON response_format). Used for NAR+OPS drafts."""
    started_at = time.time()
    system_prompt, user_prompt, budget_diag = enforce_token_budget(system_prompt, user_prompt)
    total = f"{system_prompt}\n{user_prompt}"
    if usage is not None:
        entry = {"phase": phase, "chars": len(total), "estimated_tokens": estimated_tokens(total)}
        if budget_diag.get("pruned"):
            entry["token_budget"] = budget_diag
        usage.append(entry)
    config = get_model_config()
    _append_trace(
        trace,
        {
            "phase": phase,
            "event": "request",
            "provider": config.get("provider"),
            "timeout_seconds": timeout,
            "requested_max_tokens": max_tokens,
            "prompt_chars": len(total),
            "prompt_estimated_tokens": estimated_tokens(total),
            "token_budget": budget_diag,
            "response_format": "text",
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        },
    )
    try:
        content = _chat_content(
            system_prompt,
            user_prompt,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=None,
        )
    except LlmError as exc:
        _append_trace(
            trace,
            {
                "phase": phase,
                "event": "transport_error",
                "duration_seconds": round(time.time() - started_at, 3),
                "error": str(exc),
            },
        )
        raise
    _append_trace(
        trace,
        {
            "phase": phase,
            "event": "response",
            "duration_seconds": round(time.time() - started_at, 3),
            "response_chars": len(content),
            "raw_content": content,
        },
    )
    return content


def _chat_json(
    system_prompt: str,
    user_prompt: str,
    timeout: int = 90,
    usage: list[dict[str, Any]] | None = None,
    phase: str = "draft",
    max_tokens: int | None = None,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    started_at = time.time()
    system_prompt, user_prompt, budget_diag = enforce_token_budget(system_prompt, user_prompt)
    total = f"{system_prompt}\n{user_prompt}"
    if usage is not None:
        entry = {"phase": phase, "chars": len(total), "estimated_tokens": estimated_tokens(total)}
        if budget_diag.get("pruned"):
            entry["token_budget"] = budget_diag
        usage.append(entry)
    config = get_model_config()
    _append_trace(
        trace,
        {
            "phase": phase,
            "event": "request",
            "provider": config.get("provider"),
            "timeout_seconds": timeout,
            "requested_max_tokens": max_tokens,
            "prompt_chars": len(total),
            "prompt_estimated_tokens": estimated_tokens(total),
            "token_budget": budget_diag,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        },
    )
    try:
        content = _chat_content(system_prompt, user_prompt, timeout=timeout, max_tokens=max_tokens)
    except LlmError as exc:
        response_cap = _response_token_cap(config, system_prompt, user_prompt, max_tokens)
        _, hard_cap = _response_token_settings(config)
        reason = _transport_error_message(exc, timeout)
        _append_trace(
            trace,
            {
                "phase": phase,
                "event": "transport_error",
                "duration_seconds": round(time.time() - started_at, 3),
                "error": reason,
                "soft_response_target": response_cap,
                "hard_cap": hard_cap,
            },
        )
        raise LlmError(_chat_error_message(phase, reason, total, response_cap, hard_cap)) from exc
    _append_trace(
        trace,
        {
            "phase": phase,
            "event": "raw_response",
            "duration_seconds": round(time.time() - started_at, 3),
            "response_chars": len(content),
            "raw_content": content,
        },
    )
    try:
        parsed = _extract_json(content)
        _append_trace(
            trace,
            {
                "phase": phase,
                "event": "parsed_json",
                "keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
                "parsed_json": parsed,
            },
        )
        return parsed
    except json.JSONDecodeError as parse_exc:
        _append_trace(
            trace,
            {
                "phase": phase,
                "event": "json_parse_error",
                "error": str(parse_exc),
                "raw_content": content,
            },
        )
        repair_tokens = _json_repair_token_cap(config, max_tokens)
        _, hard_cap = _response_token_settings(config)
        repair_system_prompt = "Return valid JSON only. Repair the malformed JSON without adding new content."
        repair_user_prompt = json.dumps({"malformed": content}, ensure_ascii=True)
        repair_timeout = _model_timeout(45, 120, "AI_RPG_JSON_REPAIR_TIMEOUT")
        repair_total = f"{repair_system_prompt}\n{repair_user_prompt}"
        if usage is not None:
            usage.append({"phase": f"{phase}_repair", "chars": len(repair_total), "estimated_tokens": estimated_tokens(repair_total)})
        repair_started_at = time.time()
        _append_trace(
            trace,
            {
                "phase": f"{phase}_repair",
                "event": "request",
                "provider": config.get("provider"),
                "timeout_seconds": repair_timeout,
                "requested_max_tokens": repair_tokens,
                "prompt_chars": len(repair_total),
                "prompt_estimated_tokens": estimated_tokens(repair_total),
                "system_prompt": repair_system_prompt,
                "user_prompt": repair_user_prompt,
            },
        )
        try:
            repaired = _chat_content(
                repair_system_prompt,
                repair_user_prompt,
                timeout=repair_timeout,
                temperature=0.0,
                max_tokens=repair_tokens,
            )
        except LlmError as repair_exc:
            reason = _transport_error_message(repair_exc, repair_timeout)
            _append_trace(
                trace,
                {
                    "phase": f"{phase}_repair",
                    "event": "transport_error",
                    "duration_seconds": round(time.time() - repair_started_at, 3),
                    "error": reason,
                    "repair_cap": repair_tokens,
                    "hard_cap": hard_cap,
                },
            )
            raise MalformedJsonError(
                _repair_error_message(phase, reason, repair_total, repair_tokens, hard_cap),
                content=content,
                repair_error=str(repair_exc),
            ) from repair_exc
        _append_trace(
            trace,
            {
                "phase": f"{phase}_repair",
                "event": "raw_response",
                "duration_seconds": round(time.time() - repair_started_at, 3),
                "response_chars": len(repaired),
                "raw_content": repaired,
            },
        )
        try:
            parsed = _extract_json(repaired)
            _append_trace(
                trace,
                {
                    "phase": f"{phase}_repair",
                    "event": "parsed_json",
                    "keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
                    "parsed_json": parsed,
                },
            )
            return parsed
        except json.JSONDecodeError as exc:
            _append_trace(
                trace,
                {
                    "phase": f"{phase}_repair",
                    "event": "json_parse_error",
                    "error": str(exc),
                    "raw_content": repaired,
                },
            )
            raise MalformedJsonError(
                f"{phase}_repair returned invalid JSON after malformed JSON: {exc}",
                content=content,
                repair_error=str(exc),
            ) from exc


def _chat_content(
    system_prompt: str,
    user_prompt: str,
    timeout: int = 90,
    temperature: float = 0.75,
    max_tokens: int | None = None,
    response_format: str | None = "json",
) -> str:
    from app.gpu_gate import gpu_session

    # Wait for image jobs to finish unless VRAM headroom allows parallel use.
    wait_s = float(os.getenv("AI_RPG_GPU_WAIT_TIMEOUT", "900"))
    with gpu_session("llm", wait=True, timeout=wait_s):
        return _chat_content_unlocked(
            system_prompt,
            user_prompt,
            timeout=timeout,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )


def _chat_content_unlocked(
    system_prompt: str,
    user_prompt: str,
    timeout: int = 90,
    temperature: float = 0.75,
    max_tokens: int | None = None,
    response_format: str | None = "json",
) -> str:
    config = get_model_config()
    response_tokens = _response_token_cap(config, system_prompt, user_prompt, max_tokens)
    provider = _normalize_provider(config.get("provider"))
    if provider in {"llama_cpp", "openai"}:
        return _chat_content_openai_compatible(
            config,
            system_prompt,
            user_prompt,
            timeout,
            temperature,
            response_tokens,
            response_format=response_format,
            managed_llama=(provider == "llama_cpp"),
        )

    base_url = str(config.get("ollama_base_url") or "http://localhost:11434").rstrip("/")
    model = str(config.get("ollama_model") or "llama3.1")
    # Qwen3 and similar "thinking" models spend num_predict on message.thinking and leave
    # message.content empty unless thinking is disabled. Default off for playable JSON turns.
    ollama_think = os.getenv("OLLAMA_THINK", "0").strip().lower() in {"1", "true", "yes", "on"}
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": ollama_think,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "num_ctx": context_window_tokens(config),
            "num_predict": response_tokens,
        },
    }
    if response_format == "json":
        body["format"] = "json"

    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LlmError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        if _is_connection_refused_error(exc):
            raise LlmError(_connection_refused_message("Ollama", f"{base_url}/api/chat")) from exc
        raise LlmError(_transport_error_message(exc, timeout)) from exc

    message = payload.get("message") or {}
    content = str(message.get("content") or "").strip()
    # Last-resort salvage if a model still emitted usable JSON only in thinking.
    if not content:
        thinking = str(message.get("thinking") or "").strip()
        if thinking:
            content = thinking
    if not content:
        raise LlmError("Ollama returned an empty response.")
    return content


def _chat_content_openai_compatible(
    config: dict[str, Any],
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    temperature: float,
    max_tokens: int | None = None,
    response_format: str | None = "json",
    managed_llama: bool = True,
) -> str:
    provider = _normalize_provider(config.get("provider"))
    if provider == "openai" or not managed_llama:
        base_url = str(config.get("api_base_url") or "https://api.x.ai/v1").rstrip("/")
        model = str(config.get("api_model") or config.get("model") or "grok-4.5")
        api_key = resolve_api_key(config)
        label = "OpenAI-compatible API"
    else:
        base_url = str(config.get("llama_cpp_base_url") or "http://localhost:8080").rstrip("/")
        model = str(config.get("model") or "ai-rpg-local")
        api_key = ""
        label = "llama.cpp"

    def post_json(path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{base_url}{path}"

        def make_request() -> urllib.request.Request:
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            return urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )

        try:
            return _urlopen_json(make_request(), timeout)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LlmError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if not _is_connection_refused_error(exc):
                raise LlmError(_transport_error_message(exc, timeout)) from exc
            if not managed_llama or provider == "openai":
                raise LlmError(_connection_refused_message(label, url)) from exc
            _ensure_llama_cpp_ready_for_generation(config, base_url)
            try:
                return _urlopen_json(make_request(), timeout)
            except urllib.error.HTTPError as retry_http_exc:
                detail = retry_http_exc.read().decode("utf-8", errors="replace")
                raise LlmError(f"HTTP {retry_http_exc.code}: {detail}") from retry_http_exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as retry_exc:
                if _is_connection_refused_error(retry_exc):
                    raise LlmError(_connection_refused_message("llama.cpp", url)) from retry_exc
                raise LlmError(_transport_error_message(retry_exc, timeout)) from retry_exc

    if (
        managed_llama
        and provider != "openai"
        and os.getenv("AI_RPG_LLAMA_CPP_CHAT_COMPLETIONS", "1").strip().lower() not in {"1", "true", "yes"}
    ):
        prompt = (
            "System:\n"
            f"{system_prompt.strip()}\n\n"
            "User:\n"
            f"{user_prompt.strip()}\n\n"
            "Return exactly one compact JSON object. Do not include markdown, comments, explanations, or additional JSON objects.\n"
            "JSON:\n"
        )
        body = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": 0.9,
            "max_tokens": max_tokens or _env_int("AI_RPG_MAX_RESPONSE_TOKENS", DEFAULT_RESPONSE_TOKEN_CAP),
            "stream": False,
            "stop": ["<|im_end|>"],
        }
        payload = post_json("/v1/completions", body)
        content = payload.get("choices", [{}])[0].get("text", "")
        if not content:
            raise LlmError("llama.cpp compatible server returned an empty response.")
        return content

    if provider == "openai" and not api_key:
        raise LlmError(
            "OpenAI-compatible provider needs an API key. Set XAI_API_KEY / OPENAI_API_KEY / AI_RPG_API_KEY "
            "or paste a key in LLM Settings (stored locally)."
        )

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens or _env_int("AI_RPG_MAX_RESPONSE_TOKENS", DEFAULT_RESPONSE_TOKEN_CAP),
        "stream": False,
    }
    # Local llama often wants stop tokens; cloud APIs usually do not.
    if managed_llama and provider != "openai":
        body["stop"] = ["<|im_end|>"]
    use_json_format = response_format == "json" and (
        (provider == "openai" and os.getenv("AI_RPG_API_RESPONSE_FORMAT", "1").strip().lower() in {"1", "true", "yes", "on"})
        or (
            provider != "openai"
            and os.getenv("AI_RPG_LLAMA_CPP_RESPONSE_FORMAT", "1").strip().lower() in {"1", "true", "yes"}
        )
    )
    if use_json_format:
        body["response_format"] = {"type": "json_object"}
    payload = post_json("/v1/chat/completions", body)

    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    if isinstance(content, list):
        # Some OpenAI-compat APIs return content parts
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        content = "".join(parts)
    content = str(content or "").strip()
    if not content:
        raise LlmError(f"{label} returned an empty chat completion.")
    return content


def _turn_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise LlmError("Model returned a non-object turn JSON value.")
    for key in TURN_WRAPPER_KEYS:
        wrapped = result.get(key)
        if isinstance(wrapped, dict) and TURN_SHAPE_KEYS.intersection(wrapped):
            outer = {outer_key: outer_value for outer_key, outer_value in result.items() if outer_key not in TURN_WRAPPER_KEYS}
            return {**outer, **wrapped}
    return dict(result)


def _narration_value_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n\n".join(_narration_value_text(item) for item in value).strip()
    if isinstance(value, dict):
        for key in TURN_SEGMENT_TEXT_KEYS:
            text = _narration_value_text(value.get(key))
            if text:
                return text
    return ""


def _segment_label(segment: dict[str, Any], fallback: str) -> str:
    for key in TURN_SEGMENT_LABEL_KEYS:
        label = str(segment.get(key) or "").strip()
        if label:
            return label
    return fallback


def _segment_text(segment: dict[str, Any]) -> str:
    for key in TURN_SEGMENT_TEXT_KEYS:
        text = _narration_value_text(segment.get(key))
        if text:
            return text
    return ""


def _coerce_segments(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if any(key in value for key in TURN_SEGMENT_TEXT_KEYS):
            return [value]
        return [{"label": key, "text": item} for key, item in value.items()]
    text = _narration_value_text(value)
    return [text] if text else []


def _narration_segments_from_result(result: dict[str, Any]) -> list[Any]:
    for key in TURN_SEGMENT_KEYS:
        segments = _coerce_segments(result.get(key))
        if segments:
            return segments
    for key in TURN_NARRATION_KEYS:
        text = _narration_value_text(result.get(key))
        if text:
            return [{"label": "scene", "text": text}]
    return []


def _is_missing_narration_error(exc: Exception) -> bool:
    return MISSING_NARRATION_MESSAGE.lower() in str(exc).lower()


def _normalize_turn(result: dict[str, Any]) -> dict[str, Any]:
    result = _turn_payload(result)
    segments = _narration_segments_from_result(result)
    result["narration_segments"] = segments
    normalized_segments: list[dict[str, str]] = []
    for index, segment in enumerate(segments):
        if isinstance(segment, dict):
            text = _segment_text(segment)
            label = _segment_label(segment, "scene" if index == 0 else "result")
        else:
            text = _narration_value_text(segment)
            label = "scene" if index == 0 else "result"
        if text:
            normalized_segments.append({"label": label[:40], "text": text})
    result["narration_segments"] = normalized_segments
    joined = "\n\n".join(segment["text"] for segment in normalized_segments).strip()
    if joined:
        result["narration"] = joined[:5600]
    else:
        raise LlmError(MISSING_NARRATION_MESSAGE)
    if "self_check" not in result:
        result["self_check"] = {
            "passed": False,
            "issues_found": ["Verifier did not return self_check."],
            "corrections_made": [],
            "reference_check": "unknown",
            "consistency_check": "unknown",
        }
    result.setdefault("index_updates", [])
    result.setdefault("turn_summary", "")
    return result


def _clean_scene_plan_for_handoff(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        text = _narration_value_text(value)
        return {"goal": _trim_text(text, 300), "focus_points": []} if text else {"goal": "", "focus_points": []}
    focus_points: list[dict[str, Any]] = []
    raw_focus_points = value.get("focus_points") or value.get("beats") or []
    if isinstance(raw_focus_points, dict):
        raw_focus_points = list(raw_focus_points.values())
    if isinstance(raw_focus_points, list):
        for point in raw_focus_points[:6]:
            if isinstance(point, dict):
                cleaned_point = {
                    "kind": _trim_text(str(point.get("kind") or point.get("type") or "scene"), 40),
                    "summary": _trim_text(str(point.get("summary") or point.get("text") or point.get("description") or ""), 320),
                    "event_worthy": bool(point.get("event_worthy")),
                    "persistence": _trim_text(str(point.get("persistence") or ""), 40),
                }
            else:
                cleaned_point = {
                    "kind": "scene",
                    "summary": _trim_text(str(point or ""), 320),
                    "event_worthy": False,
                    "persistence": "",
                }
            if cleaned_point["summary"]:
                focus_points.append(cleaned_point)
    return {
        "goal": _trim_text(str(value.get("goal") or value.get("summary") or ""), 360),
        "focus_points": focus_points,
    }


def _clean_narration_segments_for_handoff(value: Any) -> list[dict[str, str]]:
    segments = _coerce_segments(value)
    cleaned: list[dict[str, str]] = []
    for index, segment in enumerate(segments[: HANDOFF_TURN_LIST_LIMITS["narration_segments"]]):
        if isinstance(segment, dict):
            label = _segment_label(segment, "paragraph")
            text = _segment_text(segment)
        else:
            label = "paragraph"
            text = _narration_value_text(segment)
        text = re.sub(r"\n{3,}", "\n\n", str(text or "")).strip()
        if text:
            cleaned.append({"label": _trim_text(label or f"paragraph {index + 1}", 40), "text": _trim_text(text, 2800)})
    joined = "\n\n".join(segment["text"] for segment in cleaned).strip()
    if len(joined) > 5600:
        joined = _trim_text(joined, 5600)
        return [{"label": "paragraph", "text": joined}]
    return cleaned


def _clean_player_delta_for_handoff(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key in HANDOFF_PLAYER_FIELDS:
        if key not in value:
            continue
        item = value.get(key)
        cleaned[key] = _trim_text(str(item), 260) if isinstance(item, str) else item
    return cleaned


def _clean_self_check_for_handoff(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "passed": False,
            "issues_found": ["Cleanup stage received a non-object self_check."],
            "corrections_made": [],
            "reference_check": "unknown",
            "consistency_check": "unknown",
        }
    issues = value.get("issues_found") if isinstance(value.get("issues_found"), list) else []
    corrections = value.get("corrections_made") if isinstance(value.get("corrections_made"), list) else []
    return {
        "passed": bool(value.get("passed")),
        "issues_found": [_trim_text(str(item), 260) for item in issues[:8]],
        "corrections_made": [_trim_text(str(item), 260) for item in corrections[:8]],
        "reference_check": _trim_text(str(value.get("reference_check") or "unknown"), 500),
        "consistency_check": _trim_text(str(value.get("consistency_check") or "unknown"), 500),
    }


def _clean_turn_list_for_handoff(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    cleaned: list[Any] = []
    for item in value[:limit]:
        if isinstance(item, dict):
            cleaned.append(_trim_strings(item, 520))
        elif isinstance(item, str):
            text = _trim_text(item, 520)
            if text:
                cleaned.append(text)
    return cleaned


def _keep_cleaned_turn_value(key: str, value: Any) -> bool:
    if key in {"scene_plan", "narration_segments", "narration", "player", "self_check", "turn_summary", "scene_focus"}:
        return True
    return key in TURN_SHAPE_KEYS and value not in (None, [], {})


def _clean_turn_for_handoff(turn: dict[str, Any], phase: str, trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    # Preserve pipeline debug meta across normalize/cleanup (not part of world schema).
    pipeline_meta = turn.get("_narration_pipeline") if isinstance(turn, dict) else None
    normalized = _normalize_turn(turn)
    before_chars, before_tokens = _json_size(normalized)
    cleaned: dict[str, Any] = {}
    cleaned["scene_plan"] = _clean_scene_plan_for_handoff(normalized.get("scene_plan"))
    cleaned["narration_segments"] = _clean_narration_segments_for_handoff(normalized.get("narration_segments"))
    narration = "\n\n".join(segment["text"] for segment in cleaned["narration_segments"]).strip()
    cleaned["narration"] = narration or _trim_text(str(normalized.get("narration") or ""), 5600)
    cleaned["player"] = _clean_player_delta_for_handoff(normalized.get("player"))
    cleaned["self_check"] = _clean_self_check_for_handoff(normalized.get("self_check"))
    cleaned["turn_summary"] = _trim_text(str(normalized.get("turn_summary") or ""), 700)
    cleaned["scene_focus"] = _trim_text(str(normalized.get("scene_focus") or "filler"), 80)
    for key in TURN_SHAPE_ORDER:
        if key in cleaned or key not in normalized:
            continue
        if key in HANDOFF_TURN_LIST_LIMITS:
            cleaned[key] = _clean_turn_list_for_handoff(normalized.get(key), HANDOFF_TURN_LIST_LIMITS[key])
        else:
            cleaned[key] = _trim_strings(normalized.get(key), 520)
    cleaned = {key: value for key, value in cleaned.items() if _keep_cleaned_turn_value(key, value)}
    if pipeline_meta:
        cleaned["_narration_pipeline"] = pipeline_meta
    after_chars, after_tokens = _json_size(cleaned)
    _append_trace(
        trace,
        {
            "phase": phase,
            "event": "handoff_turn_cleanup",
            "cleanup_agent": "deterministic_payload_steward",
            "before_chars": before_chars,
            "after_chars": after_chars,
            "before_estimated_tokens": before_tokens,
            "after_estimated_tokens": after_tokens,
            "removed_keys": sorted(key for key in normalized.keys() if key not in cleaned),
            "narration_chars": _narration_char_count(cleaned),
            "list_counts": {key: len(value) for key, value in cleaned.items() if isinstance(value, list)},
            "narration_pipeline_preserved": bool(pipeline_meta),
        },
    )
    return cleaned


def _merge_verified_with_draft_narration(verified: dict[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    merged = {**draft, **_turn_payload(verified)}
    merged["narration_segments"] = draft.get("narration_segments") or []
    merged["narration"] = draft.get("narration") or ""
    if not merged.get("turn_summary"):
        merged["turn_summary"] = draft.get("turn_summary") or ""
    return _normalize_turn(merged)


def _turn_for_depth_retry(turn: dict[str, Any]) -> dict[str, Any]:
    return _trim_strings({key: turn.get(key) for key in TURN_SHAPE_KEYS if key in turn}, MAX_TURN_NARRATION_CHARS)


def _narration_char_count(turn: dict[str, Any]) -> int:
    return len(str(turn.get("narration") or ""))


def _turn_kind_from_player_input(player_input: str) -> str:
    if str(player_input).startswith("__opening_scene_request__"):
        return "opening_scene"
    if str(player_input).startswith("__continue_scene_request__"):
        return "continue_scene"
    return "player_action"


def _primary_intent(context: dict[str, Any], player_input: str) -> str:
    turn_plan = context.get("turn_plan") or {}
    intent = str(turn_plan.get("primary_intent") or "").strip()
    if intent:
        return intent
    return _turn_kind_from_player_input(player_input)


def _known_context_codes(context: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for key in ("current_location",):
        value = context.get(key)
        if isinstance(value, dict) and value.get("code"):
            codes.add(str(value["code"]).upper())
    for location in context.get("locations") or []:
        if not isinstance(location, dict):
            continue
        if location.get("code"):
            codes.add(str(location["code"]).upper())
        for npc in location.get("npcs") or []:
            if isinstance(npc, dict) and npc.get("code"):
                codes.add(str(npc["code"]).upper())
        for event in location.get("events") or []:
            if isinstance(event, dict) and event.get("code"):
                codes.add(str(event["code"]).upper())
    for root in ("inventory", "events", "conversations", "relationships"):
        for item in context.get(root) or []:
            if not isinstance(item, dict):
                continue
            for key in ("code", "npc_code", "location_code", "source_code", "target_code", "event_code", "item_code"):
                if item.get(key):
                    codes.add(str(item[key]).upper())
    mechanics = context.get("mechanics_context") or {}
    combat = mechanics.get("combat") if isinstance(mechanics, dict) else {}
    if isinstance(combat, dict):
        for target_key in ("target",):
            target = combat.get(target_key)
            if isinstance(target, dict) and target.get("code"):
                codes.add(str(target["code"]).upper())
        for target in combat.get("target_candidates") or []:
            if isinstance(target, dict) and target.get("code"):
                codes.add(str(target["code"]).upper())
    return codes


def _created_draft_codes(turn: dict[str, Any]) -> set[str]:
    codes: set[str] = set()
    for key in ("locations", "npcs", "events", "index_updates"):
        for item in turn.get(key) or []:
            if isinstance(item, dict) and item.get("code"):
                codes.add(str(item["code"]).upper())
    return codes


def _referenced_turn_codes(turn: dict[str, Any]) -> set[str]:
    text = "\n".join(
        str(value or "")
        for value in (
            turn.get("narration"),
            turn.get("turn_summary"),
            json.dumps(turn.get("scene_plan") or {}, ensure_ascii=True, default=str),
        )
    )
    return {match.group(1).upper() for match in REFERENCE_CODE_PATTERN.finditer(text)}


def _scene_plan_is_valid(turn: dict[str, Any]) -> bool:
    plan = turn.get("scene_plan")
    if not isinstance(plan, dict):
        return False
    points = plan.get("focus_points") or []
    return isinstance(points, list) and 1 <= len(points) <= 6


def _has_meaningful_player_delta(turn: dict[str, Any]) -> bool:
    player = turn.get("player") or {}
    if not isinstance(player, dict):
        return False
    numeric_fields = ("health_delta", "max_health_delta", "xp_delta", "gold_delta", "level_delta", "karma_delta")
    if any(_int_value(player.get(field), 0) != 0 for field in numeric_fields):
        return True
    return bool(player.get("move_to_location") or player.get("move_to_location_code"))


def _nonempty_turn_keys(turn: dict[str, Any], keys: set[str]) -> list[str]:
    changed: list[str] = []
    for key in sorted(keys):
        value = turn.get(key)
        if value not in (None, [], {}, ""):
            changed.append(key)
    return changed


def _verification_memory_covered_checks(context: dict[str, Any], checks: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    memory = context.get("verification_memory") or {}
    entries = memory.get("entries") if isinstance(memory, dict) else []
    if not isinstance(entries, list):
        return [], []
    threshold = max(0.0, min(1.0, _env_float("AI_RPG_VERIFY_MEMORY_CERTAINTY", DEFAULT_VERIFY_MEMORY_CERTAINTY)))
    planned_checks = {str(check) for check in checks}
    covered: list[str] = []
    hits: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        check_name = str(entry.get("check_name") or "")
        if check_name not in planned_checks:
            continue
        try:
            confidence = float(entry.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence = 0
        if confidence < threshold:
            continue
        if check_name not in covered:
            covered.append(check_name)
        hits.append(
            {
                "check_name": check_name,
                "confidence": round(confidence, 3),
                "last_verified_turn": entry.get("last_verified_turn"),
                "source": entry.get("source"),
            }
        )
    return covered, hits[:12]


def _verification_policy(context: dict[str, Any], player_input: str, draft: dict[str, Any]) -> dict[str, Any]:
    turn_plan = context.get("turn_plan") or {}
    checks = [str(check) for check in turn_plan.get("verification_checks") or [] if str(check).strip()]
    intent = _primary_intent(context, player_input)
    turn_kind = str(turn_plan.get("turn_kind") or _turn_kind_from_player_input(player_input))
    deterministic: list[str] = []
    remaining: list[str] = []
    blockers: list[str] = []
    reasons: list[str] = []
    certainty = 0.45
    memory_verified, memory_hits = _verification_memory_covered_checks(context, checks)
    if memory_verified:
        deterministic.extend(memory_verified)
        certainty += min(0.18, 0.04 * len(memory_verified))
        reasons.append(f"Verification memory covered: {', '.join(memory_verified[:8])}")

    referenced = _referenced_turn_codes(draft)
    allowed_codes = _known_context_codes(context) | _created_draft_codes(draft)
    unresolved = sorted(code for code in referenced if code not in allowed_codes)
    if unresolved:
        blockers.append("unresolved_entity_references")
        remaining.append("entity_references")
        reasons.append(f"Unresolved refs: {', '.join(unresolved[:8])}")
        certainty -= 0.25
    else:
        deterministic.append("entity_references")
        deterministic.append("explicit_reference_resolution")
        certainty += 0.12

    if _scene_plan_is_valid(draft):
        deterministic.append("scene_plan_shape")
        certainty += 0.08
    else:
        blockers.append("scene_plan_shape")
        remaining.append("scene_plan")
        certainty -= 0.12

    if _narration_char_count(draft) >= MIN_TURN_NARRATION_CHARS:
        deterministic.append("narration_depth")
        certainty += 0.12
    else:
        blockers.append("short_narration")
        remaining.append("narration_depth")
        certainty -= 0.15

    self_check = draft.get("self_check") if isinstance(draft.get("self_check"), dict) else {}
    if self_check.get("passed") is True:
        deterministic.append("draft_self_check")
        certainty += 0.1
    else:
        blockers.append("draft_self_check_not_passed")
        remaining.append("self_check")
        certainty -= 0.12

    high_risk_keys = _nonempty_turn_keys(draft, HIGH_RISK_TURN_CHANGE_KEYS)
    if high_risk_keys:
        blockers.append("high_risk_state_changes")
        reasons.append(f"Draft changes require model verification: {', '.join(high_risk_keys[:12])}")
        remaining.extend(["state_delta_justification", "persistence_changes"])
        certainty -= min(0.35, 0.08 * len(high_risk_keys))
    elif _has_meaningful_player_delta(draft):
        blockers.append("player_state_delta")
        remaining.append("state_delta_justification")
        certainty -= 0.18
    else:
        deterministic.append("no_high_risk_state_delta")
        deterministic.append("state_delta_justification")
        deterministic.append("karma_visibility")
        certainty += 0.18

    mechanics = context.get("mechanics_context") or {}
    combat = mechanics.get("combat") if isinstance(mechanics, dict) else {}
    if isinstance(combat, dict) and combat.get("status") == "resolved_player_attack":
        deterministic.append("mechanics_combat_resolution")
        deterministic.append("damage_scale")
        deterministic.append("npc_stats")
        certainty += 0.08

    if turn_kind in {"opening_scene", "continue_scene"}:
        blockers.append("intent_requires_model_verifier")
        remaining.extend(checks or ["intent_specific_consistency"])
        certainty -= 0.2
    elif intent in VERIFY_REQUIRED_INTENTS:
        required_remaining = [check for check in checks if check not in deterministic]
        if required_remaining:
            blockers.append("intent_requires_model_verifier")
            remaining.extend(required_remaining or ["intent_specific_consistency"])
            certainty -= 0.2
        else:
            deterministic.append("verification_memory_covers_required_intent")
            certainty += 0.06
    elif intent in LOW_RISK_SKIP_INTENTS:
        deterministic.append("low_risk_intent")
        certainty += 0.08

    if referenced:
        reasons.append(f"Referenced codes checked: {', '.join(sorted(referenced)[:10])}")
    if not reasons:
        reasons.append("Draft has stable shape, no risky state deltas, and only deterministic checks remain.")

    deterministic = list(dict.fromkeys(deterministic))
    remaining_checks = list(dict.fromkeys([check for check in [*checks, *remaining] if check not in deterministic]))
    blockers = list(dict.fromkeys(blockers))
    threshold = max(0.0, min(1.0, _env_float("AI_RPG_VERIFY_SKIP_CERTAINTY", DEFAULT_VERIFY_SKIP_CERTAINTY)))
    certainty = max(0.0, min(1.0, round(certainty, 3)))
    fast_enabled = _env_bool("AI_RPG_FAST_VERIFICATION", True)
    mode = "full_model_verifier"
    if fast_enabled and not blockers and not remaining_checks and certainty >= threshold:
        mode = "skip_model_verifier"
    elif deterministic:
        mode = "targeted_model_verifier"
    return {
        "version": VERIFICATION_POLICY_VERSION,
        "mode": mode,
        "certainty": certainty,
        "skip_threshold": threshold,
        "fast_verification_enabled": fast_enabled,
        "turn_kind": turn_kind,
        "primary_intent": intent,
        "deterministically_verified": deterministic,
        "memory_verified": memory_verified,
        "memory_hits": memory_hits,
        "remaining_checks": remaining_checks,
        "blockers": blockers,
        "reasons": reasons[:8],
    }


def _mark_draft_verified_by_policy(draft: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    result = dict(draft)
    self_check = result.get("self_check") if isinstance(result.get("self_check"), dict) else {}
    issues = self_check.get("issues_found") if isinstance(self_check.get("issues_found"), list) else []
    corrections = self_check.get("corrections_made") if isinstance(self_check.get("corrections_made"), list) else []
    corrections = [*corrections, f"Skipped model verifier at certainty {policy.get('certainty')} after deterministic checks."]
    result["self_check"] = {
        "passed": True,
        "issues_found": issues,
        "corrections_made": corrections[:8],
        "reference_check": "Deterministic verification policy cleared entity references.",
        "consistency_check": "High-certainty draft accepted without model verifier; no risky state deltas were present.",
    }
    result["_verification_policy"] = policy
    return result


def _retry_short_narration(
    context: dict[str, Any],
    player_input: str,
    turn: dict[str, Any],
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleaned_context = _clean_context_for_handoff(_compact_turn_context(context), f"{phase}_context_cleanup", trace)
    prompt = {
        "repair_task": "The previous turn JSON was valid but the player-visible narration was too short. Return a complete full turn JSON with deeper narration while preserving the same facts and state changes.",
        "current_narration_chars": _narration_char_count(turn),
        "minimum_narration_chars": MIN_TURN_NARRATION_CHARS,
        "target_narration_chars": TARGET_TURN_NARRATION_CHARS,
        "maximum_narration_chars": MAX_TURN_NARRATION_CHARS,
        "world_turn_prompt": json.loads(build_user_prompt(cleaned_context, player_input)),
        "previous_turn": _turn_for_depth_retry(_clean_turn_for_handoff(turn, f"{phase}_previous_turn_cleanup", trace)),
        "rules": [
            "Return JSON only.",
            "Preserve scene_plan intent, existing entity references, player changes, inventory changes, events, gm_events, and turn_summary unless a contradiction must be corrected.",
            f"Expand narration_segments and narration to at least {MIN_TURN_NARRATION_CHARS} visible characters, normally around {TARGET_TURN_NARRATION_CHARS}, and under {MAX_TURN_NARRATION_CHARS}.",
            "Add sensory detail, NPC reaction, immediate consequence, environmental pressure, and concrete choice context instead of padding or repeating text.",
            "For opening_scene or continue_scene, do not invent a player action.",
        ],
    }
    return _chat_json(
        system_prompt,
        json.dumps(prompt, ensure_ascii=True, separators=(",", ":")),
        timeout=timeout,
        usage=usage,
        phase=phase,
        max_tokens=max(_turn_max_tokens(context, "draft"), DEFAULT_RESPONSE_TOKEN_CAP),
        trace=trace,
    )


def _ensure_narration_depth(
    turn: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = _normalize_turn(turn)
    original_chars = _narration_char_count(normalized)
    if original_chars >= MIN_TURN_NARRATION_CHARS:
        return normalized
    try:
        expanded = _normalize_turn(_retry_short_narration(context, player_input, normalized, system_prompt, timeout, usage, phase, trace))
        if _narration_char_count(expanded) >= MIN_TURN_NARRATION_CHARS or _narration_char_count(expanded) > original_chars:
            return expanded
    except LlmError as exc:
        usage.append({"phase": f"{phase}_failed", "error": _trim_text(str(exc), 500)})
        _append_trace(trace, {"phase": phase, "event": "depth_retry_failed", "error": str(exc)})
    self_check = normalized.get("self_check")
    if not isinstance(self_check, dict):
        self_check = {}
        normalized["self_check"] = self_check
    issues = self_check.setdefault("issues_found", [])
    if isinstance(issues, list):
        issues.append(f"Narration was shorter than {MIN_TURN_NARRATION_CHARS} characters after depth retry.")
    return normalized


def _turn_number_hint(context: dict[str, Any]) -> int:
    from app.narration_pipeline import infer_turn_number

    return infer_turn_number(context)


def _pipeline_config_snapshot() -> dict[str, Any]:
    config = get_model_config()
    return {
        **config,
        "context_window": context_window_tokens(config),
        "response_token_cap": config.get("response_token_cap"),
        "response_token_hard_cap": config.get("response_token_hard_cap"),
        "ollama_model": config.get("ollama_model"),
        "gguf_model_path": config.get("gguf_model_path"),
    }


def _make_pipeline_paragraph_writer(
    usage: list[dict[str, Any]],
    trace: list[dict[str, Any]] | None,
    timeout: int,
):
    from app.narration_pipeline import polish_paragraph

    from app.prompts import PROSE_VOICE

    system = (
        "You write ONE playable RPG narration paragraph only. "
        "No headings, no bullet lists, no JSON, no OPS lines. "
        "Use [[codes]] only when the brief lists them. "
        "Do not repeat facts listed under forbidden_repeat. "
        "Continue from previous_paragraph_tail without restarting the scene. "
        "Always finish every sentence completely — never stop mid-word or mid-clause. "
        + PROSE_VOICE
    )

    def writer(brief: dict[str, Any], previous_paragraph: str, ledger: Any) -> str:
        limits = brief.get("model_limits") if isinstance(brief.get("model_limits"), dict) else {}
        # Give small models headroom so max_tokens does not cut mid-sentence.
        max_tokens = max(160, min(520, int(limits.get("max_tokens") or 200) + 80))
        max_chars = max(120, min(800, int(limits.get("max_chars") or 420)))
        rules = [
            f"Target about {limits.get('min_chars', 200)}-{max_chars} visible characters.",
            "One paragraph only.",
            "Do not restate the whole prior scene.",
            "If dual actions appear, sequence them with then/after/before.",
            "End on a complete sentence with . ! or ?",
            "Direct, readable sentences; varied plain vocabulary — no inverted poetic templates.",
        ]
        for extra in brief.get("rules_extra") or []:
            if extra and str(extra) not in rules:
                rules.append(str(extra))
        payload = {
            "task": "Write exactly one paragraph for this beat.",
            "brief": brief,
            "previous_paragraph_tail": (previous_paragraph or "")[-400:],
            "already_said": list(ledger.forbidden_repeats())[:12],
            "rejected_attempts": list(ledger.previously_attempted_texts(int(brief.get("beat_index") or 1) - 1))[:3],
            "rules": rules,
        }
        raw = _chat_text(
            system,
            json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
            timeout=max(30, min(timeout, 180)),
            usage=usage,
            phase=f"narration_para_{brief.get('beat_index', 0)}",
            max_tokens=max_tokens,
            trace=trace,
            # Slightly warmer than rigid JSON calls so wording varies without chaos.
            temperature=0.82,
        )
        # Strip accidental multi-paragraph / fences
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:\w+)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        # Keep first paragraph block if model spilled
        parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        text = parts[0] if parts else text
        text = re.sub(r"\s+", " ", text).strip()
        # Never hard-slice mid-word; polish to last complete sentence.
        return polish_paragraph(text, max_chars=max_chars)

    return writer


def _make_pipeline_consolidator(
    usage: list[dict[str, Any]],
    trace: list[dict[str, Any]] | None,
    timeout: int,
):
    system = (
        "You are the scene consolidator. Read all paragraphs together. "
        "Fix doubling, contradictions, and simultaneous dual intents. "
        "Prefer surgical rewrites of later paragraphs. "
        "Return the full scene only as labeled blocks, no commentary."
    )

    def consolidator(paragraphs: list[str], ledger: Any) -> list[str]:
        if len(paragraphs) <= 1:
            return paragraphs
        labeled = "\n".join(f"===P{i + 1}===\n{p}" for i, p in enumerate(paragraphs))
        payload = {
            "task": "Return cleaned paragraphs with the same count when possible.",
            "said_facts": [f.text for f in getattr(ledger, "said_facts", [])][:20],
            "issues_to_watch": [
                "same fact twice",
                "entity present after removed",
                "two incompatible actions without sequence",
            ],
            "input": labeled,
            "output_format": "===P1===\\nparagraph\\n===P2===\\nparagraph",
        }
        try:
            raw = _chat_text(
                system,
                json.dumps(payload, ensure_ascii=True, separators=(",", ":")),
                timeout=max(30, min(timeout, 180)),
                usage=usage,
                phase="narration_consolidate",
                max_tokens=min(1200, max(300, sum(len(p) for p in paragraphs) // 3 + 200)),
                trace=trace,
                temperature=0.4,
            )
        except LlmError as exc:
            usage.append({"phase": "narration_consolidate_failed", "error": _trim_text(str(exc), 400)})
            return paragraphs
        parsed = parse_consolidated_paragraphs(raw, expected=len(paragraphs))
        if not parsed:
            return paragraphs
        # Preserve count when possible; allow drop of pure duplicates only.
        if len(parsed) < max(1, len(paragraphs) - 1):
            return paragraphs
        return parsed

    return consolidator


def _apply_narration_pipeline(
    turn: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    usage: list[dict[str, Any]],
    trace: list[dict[str, Any]] | None,
    timeout: int,
) -> dict[str, Any]:
    """Replace turn narration via adaptive paragraph pipeline. Keeps OPS/state fields."""
    if not pipeline_enabled():
        return turn
    try:
        from app.generation_progress import update as progress_update
    except Exception:
        def progress_update(*_a: Any, **_k: Any) -> None:
            return None

    result = dict(turn)
    config = _pipeline_config_snapshot()
    ops_summary = ops_summary_from_turn(result)
    turn_number = _turn_number_hint(context)
    progress_update(
        "narration",
        "Adaptive narration pipeline rewriting the scene…",
        step=4,
        line="Paragraph pipeline: drafting beats (progress updates as each is accepted).",
    )
    # Consolidator callback is provided; pipeline still skips it on lean 2-para low-density
    # turns via budget["skip_consolidator"] (see should_skip_consolidator).
    consolidator_fn = None
    if _env_bool("AI_RPG_NARRATION_PIPELINE_CONSOLIDATE", True):
        consolidator_fn = _make_pipeline_consolidator(usage, trace, timeout)
    try:
        pipeline_out = run_narration_pipeline(
            context,
            player_input,
            config=config,
            ops_summary=ops_summary,
            turn_number=turn_number,
            writer=_make_pipeline_paragraph_writer(usage, trace, timeout),
            consolidator=consolidator_fn,
        )
    except Exception as exc:
        usage.append({"phase": "narration_pipeline_failed", "error": _trim_text(str(exc), 500)})
        _append_trace(trace, {"phase": "narration_pipeline", "event": "failed", "error": str(exc)})
        return result

    segments = pipeline_out.get("narration_segments") or []
    narration = str(pipeline_out.get("narration") or "").strip()
    if not narration and segments:
        narration = "\n\n".join(str(s.get("text") or "") for s in segments if isinstance(s, dict)).strip()
    if not narration:
        usage.append({"phase": "narration_pipeline_empty", "chars": 0, "estimated_tokens": 0})
        return result

    result["narration_segments"] = segments
    result["narration"] = narration
    result["_narration_pipeline"] = {
        "budget": pipeline_out.get("budget"),
        "ledger_path": pipeline_out.get("ledger_path"),
        "pipeline_version": pipeline_out.get("pipeline_version"),
        "chars": len(narration),
        "consolidator_skipped": bool(pipeline_out.get("consolidator_skipped")),
        "turn": turn_number,
    }
    usage.append(
        {
            "phase": "narration_pipeline",
            "chars": len(narration),
            "estimated_tokens": estimated_tokens(narration),
            "paragraphs": len(segments),
            "tier": (pipeline_out.get("budget") or {}).get("tier"),
            "consolidator_skipped": bool(pipeline_out.get("consolidator_skipped")),
            "density": ((pipeline_out.get("budget") or {}).get("density") or {}).get("score"),
        }
    )
    _append_trace(
        trace,
        {
            "phase": "narration_pipeline",
            "event": "applied",
            "paragraphs": len(segments),
            "chars": len(narration),
            "budget": pipeline_out.get("budget"),
            "ledger_path": pipeline_out.get("ledger_path"),
        },
    )
    return result


def _ensure_narration_quality(
    turn: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    When AI_RPG_NARRATION_PIPELINE is on: paragraph pipeline (packed, tier-aware).
    Otherwise: legacy whole-turn depth retry when under MIN_TURN_NARRATION_CHARS.
    """
    if pipeline_enabled():
        refined = _apply_narration_pipeline(turn, context, player_input, usage, trace, timeout)
        budget = (refined.get("_narration_pipeline") or {}).get("budget") or {}
        soft_target = int(budget.get("soft_total_chars") or MIN_TURN_NARRATION_CHARS)
        # Small models aim lower; only fall back to whole-turn depth retry if still very short.
        floor = max(400, min(MIN_TURN_NARRATION_CHARS, int(soft_target * 0.65)))
        if _narration_char_count(refined) >= floor:
            return refined
        return _ensure_narration_depth(refined, context, player_input, system_prompt, timeout, usage, phase, trace)
    return _ensure_narration_depth(turn, context, player_input, system_prompt, timeout, usage, phase, trace)


def _retry_missing_narration(
    context: dict[str, Any],
    player_input: str,
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cleaned_context = _clean_context_for_handoff(_compact_turn_context(context), f"{phase}_context_cleanup", trace)
    prompt = {
        "repair_task": "The previous turn JSON had no usable narration. Return a complete turn JSON with narration_segments containing playable prose.",
        "world_turn_prompt": json.loads(build_user_prompt(cleaned_context, player_input)),
        "rules": [
            "Return JSON only.",
            "Include narration_segments with at least one object whose text is non-empty.",
            "Include scene_plan with 1-6 focus_points plus player, self_check, turn_summary, and scene_focus.",
            "For opening_scene or continue_scene, do not invent a player action.",
        ],
    }
    return _chat_json(
        system_prompt,
        json.dumps(prompt, ensure_ascii=True, separators=(",", ":")),
        timeout=timeout,
        usage=usage,
        phase=phase,
        max_tokens=_turn_max_tokens(context, "draft", compact=True),
        trace=trace,
    )


def _try_dsl_draft(
    context: dict[str, Any],
    player_input: str,
    timeout: int,
    usage: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    system_prompt: str | None = None,
) -> dict[str, Any] | None:
    """Attempt NAR+OPS draft. Returns turn dict or None to fall back to JSON draft."""
    if not draft_mode_enabled():
        return None
    active_context = _clean_context_for_handoff(context, "planner_to_dsl_draft", trace)
    dsl_prompt = build_dsl_user_prompt(active_context, player_input)
    max_tokens = min(_turn_max_tokens(active_context, "draft"), 1400)
    dsl_system = system_prompt or DSL_SYSTEM_PROMPT
    try:
        raw = _chat_text(
            dsl_system,
            dsl_prompt,
            timeout=timeout,
            usage=usage,
            phase="draft_dsl",
            max_tokens=max_tokens,
            trace=trace,
        )
    except LlmError as exc:
        _append_trace(trace, {"phase": "draft_dsl", "event": "failed", "error": str(exc)})
        return None
    try:
        turn = parse_dsl_turn(raw, player_input=player_input)
        turn = _clean_turn_for_handoff(_normalize_turn(turn), "dsl_to_verify", trace)
        _append_trace(
            trace,
            {
                "phase": "draft_dsl",
                "event": "transcoded",
                "narration_chars": _narration_char_count(turn),
                "ops_count": (turn.get("_dsl") or {}).get("ops_count"),
            },
        )
        return turn
    except (TurnDslError, LlmError, ValueError) as exc:
        _append_trace(
            trace,
            {
                "phase": "draft_dsl",
                "event": "parse_failed",
                "error": str(exc),
                "raw_preview": str(raw)[:800],
            },
        )
        # If model emitted usable prose without valid ops, salvage narration-only turn.
        try:
            from app.turn_dsl import split_nar_ops

            narration, _ops = split_nar_ops(raw)
            if len(narration.strip()) >= 200:
                salvaged = _narration_only_turn_from_text(narration, active_context, f"dsl_ops_failed: {exc}")
                salvaged = _clean_turn_for_handoff(_normalize_turn(salvaged), "dsl_salvage_to_verify", trace)
                usage.append({"phase": "draft_dsl_salvage", "chars": len(raw), "estimated_tokens": estimated_tokens(raw)})
                return salvaged
        except Exception:
            pass
        return None


def generate_turn(context: dict[str, Any], player_input: str) -> dict[str, Any]:
    from app.generation_progress import begin as progress_begin
    from app.generation_progress import end as progress_end
    from app.generation_progress import fail as progress_fail
    from app.generation_progress import set_preview as progress_preview
    from app.generation_progress import update as progress_update

    usage: list[dict[str, Any]] = []
    trace: list[dict[str, Any]] = []
    timeout = _model_timeout(90, 900, "AI_RPG_TURN_DRAFT_TIMEOUT")
    verify_timeout = _model_timeout(45, 480, "AI_RPG_TURN_VERIFY_TIMEOUT")
    base_config = get_model_config(ignore_override=True)
    # Session theme bias: soft on-the-fly genre lean (isekai RPG etc.) while keeping DM core.
    playthrough_options = (
        ((context.get("settings") or {}).get("playthrough_options") or {})
        if isinstance(context, dict)
        else {}
    )
    playthrough_options = playthrough_options if isinstance(playthrough_options, dict) else {}
    session_theme = playthrough_options.get("session_theme")
    session_theme = session_theme if isinstance(session_theme, dict) else None
    # Optional hard routing: theme_model or theme_adapter_map[adapter_hint] → model name for this turn.
    config = apply_theme_model_routing(base_config, session_theme)
    system_prompt = COMPACT_SYSTEM_PROMPT if config.get("provider") == "llama_cpp" else SYSTEM_PROMPT
    verify_prompt = COMPACT_VERIFY_PROMPT if config.get("provider") == "llama_cpp" else VERIFY_PROMPT
    theme_block = theme_prompt_block(session_theme, playthrough_options)
    dsl_system_prompt = DSL_SYSTEM_PROMPT
    is_opening = str(player_input or "").startswith("__opening_scene_request__")
    if theme_block:
        system_prompt = f"{system_prompt.rstrip()}\n\n{theme_block}"
        dsl_system_prompt = f"{DSL_SYSTEM_PROMPT.rstrip()}\n\n{theme_block}"
    if is_opening:
        open_block = opening_feel_prompt_block(session_theme, playthrough_options)
        if open_block:
            system_prompt = f"{system_prompt.rstrip()}\n\n{open_block}"
            dsl_system_prompt = f"{dsl_system_prompt.rstrip()}\n\n{open_block}"
    progress_begin(
        "opening" if is_opening else "turn",
        total_steps=6,
        detail="Preparing context for the local model…",
    )
    progress_update(
        "start",
        "Building the turn context packet…",
        step=1,
        line="Collecting world state and planner packet.",
    )
    _append_trace(
        trace,
        {
            "phase": "pipeline",
            "event": "start",
            "draft_mode": "dsl" if draft_mode_enabled() else "json",
            "handoff_model": [
                "world.build_prompt_context planner packet",
                "deterministic context cleanup before draft",
                "draft NAR+OPS model call (default) with deterministic transcoder",
                "JSON draft fallback when DSL parse fails",
                "deterministic draft payload cleanup before verifier",
                "certainty-based verification policy scoring",
                "malformed JSON repair or retry when needed",
                "verifier JSON model call when remaining checks require it",
                "deterministic verified payload cleanup before world application",
                "optional adaptive paragraph narration pipeline when AI_RPG_NARRATION_PIPELINE is on",
                "narration depth retry when needed (or after pipeline floor miss)",
                "world.apply_turn SQLite state application or deterministic fallback",
            ],
            "narration_pipeline_enabled": pipeline_enabled(),
            "note": "Trace contains observable prompts, raw model outputs, parsed JSON, handoff cleanup decisions, verifier self_check, errors, and fallback decisions. It cannot include private hidden chain-of-thought that the model did not return.",
            "provider": config.get("provider"),
            "ollama_model": config.get("ollama_model"),
            "api_model": config.get("api_model"),
            "theme_model_source": config.get("theme_model_source") or "",
            "theme_model_active": config.get("theme_model_active") or "",
            "adapter_hint": (session_theme or {}).get("adapter_hint") if session_theme else "",
            "draft_timeout_seconds": timeout,
            "verify_timeout_seconds": verify_timeout,
        },
    )
    try:
        # Scope so nested _chat_content / pipeline calls use the themed model.
        with model_config_scope(config):
            result = _generate_turn_body(
                context,
                player_input,
                usage=usage,
                trace=trace,
                timeout=timeout,
                verify_timeout=verify_timeout,
                config=config,
                system_prompt=system_prompt,
                verify_prompt=verify_prompt,
                dsl_system_prompt=dsl_system_prompt,
                progress_update=progress_update,
                progress_preview=progress_preview,
                progress_end=progress_end,
                progress_fail=progress_fail,
            )
        narr = ""
        if isinstance(result, dict):
            narr = str(result.get("narration") or "")
            if not narr:
                segs = result.get("narration_segments") or []
                narr = "\n\n".join(
                    str(s.get("text") or "") for s in segs if isinstance(s, dict)
                )
            if narr.strip():
                progress_preview(narr.strip(), append_paragraph=False)
        progress_update(
            "done",
            "Scene ready.",
            step=6,
            line=f"Finished ({len(narr)} characters).",
        )
        progress_end(detail="Scene ready.")
        return result
    except Exception as exc:
        progress_fail(str(exc)[:240])
        raise


def _generate_turn_body(
    context: dict[str, Any],
    player_input: str,
    *,
    usage: list[dict[str, Any]],
    trace: list[dict[str, Any]],
    timeout: int,
    verify_timeout: int,
    config: dict[str, Any],
    system_prompt: str,
    verify_prompt: str,
    dsl_system_prompt: str | None = None,
    progress_update: Any,
    progress_preview: Any,
    progress_end: Any,
    progress_fail: Any,
) -> dict[str, Any]:
    active_context = _clean_context_for_handoff(context, "planner_to_draft", trace)
    progress_update(
        "draft",
        "Asking the local model for the scene draft…",
        step=2,
        line="Model draft call in progress (this is usually the longest step).",
    )
    dsl_draft = _try_dsl_draft(
        context,
        player_input,
        timeout,
        usage,
        trace,
        system_prompt=dsl_system_prompt or DSL_SYSTEM_PROMPT,
    )
    if dsl_draft is not None:
        draft = dsl_draft
        progress_update(
            "draft_ready",
            "Draft received; scoring verification…",
            step=3,
            line="DSL draft complete.",
        )
        if str(draft.get("narration") or "").strip():
            progress_preview(str(draft.get("narration") or "").strip(), append_paragraph=False)
        # Jump to verification path with DSL-produced JSON-compatible turn.
        verification_policy = _verification_policy(context, player_input, draft)
        active_context = {**active_context, "verification_policy": verification_policy}
        _append_trace(trace, {"phase": "verification_policy", "event": "scored", **verification_policy})
        # Prefer skip-verify for low-risk DSL turns; still allow model verify when needed.
        if verification_policy.get("mode") == "skip_model_verifier" or os.getenv(
            "AI_RPG_DSL_SKIP_VERIFY", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}:
            usage.append({"phase": "verify_skipped_dsl", "chars": 0, "estimated_tokens": 0})
            progress_update(
                "verify_skip",
                "Verifier skipped; polishing narration…",
                step=4,
                line="Low-risk draft — skipping model verifier.",
            )
            result = _mark_draft_verified_by_policy(draft, verification_policy)
            # Only expand narration if clearly short; avoid expensive depth retries when DSL already wrote prose.
            result = _ensure_narration_quality(
                result, active_context, player_input, system_prompt, timeout, usage, "narration_depth_dsl_retry", trace
            )
            result = _clean_turn_for_handoff(result, "dsl_to_world", trace)
            result["_verification_policy"] = verification_policy
            result["_draft_mode"] = "dsl"
            _append_trace(
                trace,
                {
                    "phase": "pipeline",
                    "event": "success",
                    "draft_mode": "dsl",
                    "narration_chars": _narration_char_count(result),
                    "used_fallback": False,
                    "verifier_skipped": True,
                    "narration_pipeline": bool(result.get("_narration_pipeline")),
                },
            )
            result["_model_usage"] = usage
            result["_model_trace"] = trace
            return result
        try:
            progress_update(
                "verify",
                "Verifier is checking continuity and state changes…",
                step=3,
                line="Model verifier pass in progress.",
            )
            verified = _chat_json(
                verify_prompt,
                build_verify_prompt(active_context, player_input, draft),
                timeout=verify_timeout,
                usage=usage,
                phase="verify",
                max_tokens=_turn_max_tokens(active_context, "verify"),
                trace=trace,
            )
            try:
                result = _normalize_turn(verified)
            except LlmError as exc:
                if not _is_missing_narration_error(exc):
                    raise
                result = _merge_verified_with_draft_narration(verified, draft)
            progress_update(
                "narration",
                "Polishing narration quality…",
                step=4,
                line="Narration quality / pipeline pass.",
            )
            result = _ensure_narration_quality(
                result, active_context, player_input, system_prompt, timeout, usage, "narration_depth_retry", trace
            )
            result = _clean_turn_for_handoff(result, "verifier_to_world", trace)
            result["_verification_policy"] = verification_policy
            result["_draft_mode"] = "dsl"
            _append_trace(
                trace,
                {
                    "phase": "pipeline",
                    "event": "success",
                    "draft_mode": "dsl",
                    "narration_chars": _narration_char_count(result),
                    "used_fallback": False,
                    "narration_pipeline": bool(result.get("_narration_pipeline")),
                },
            )
            result["_model_usage"] = usage
            result["_model_trace"] = trace
            return result
        except LlmError as exc:
            draft = _normalize_turn(draft)
            draft["self_check"] = {
                "passed": False,
                "issues_found": [f"Verifier pass failed after DSL draft; using DSL draft. {exc}"],
                "corrections_made": ["dsl_unverified"],
                "reference_check": "not verified",
                "consistency_check": "not verified",
            }
            draft = _ensure_narration_quality(
                draft, active_context, player_input, system_prompt, timeout, usage, "narration_depth_draft_retry", trace
            )
            draft = _clean_turn_for_handoff(draft, "dsl_to_world_unverified", trace)
            draft["_verification_policy"] = verification_policy
            draft["_draft_mode"] = "dsl"
            _append_trace(
                trace,
                {
                    "phase": "pipeline",
                    "event": "using_unverified_dsl_draft",
                    "verifier_error": str(exc),
                    "narration_chars": _narration_char_count(draft),
                },
            )
            draft["_model_usage"] = usage
            draft["_model_trace"] = trace
            return draft

    draft_prompt = build_user_prompt(active_context, player_input)
    progress_update(
        "draft_json",
        "Asking the local model for a full scene draft…",
        step=2,
        line="JSON draft call in progress.",
    )
    try:
        draft = _chat_json(
            system_prompt,
            draft_prompt,
            timeout=timeout,
            usage=usage,
            phase="draft",
            max_tokens=_turn_max_tokens(active_context, "draft"),
            trace=trace,
        )
    except MalformedJsonError as exc:
        try:
            draft = _narration_only_turn_from_text(exc.content, active_context, str(exc))
            usage.append({"phase": "draft_salvage", "chars": len(exc.content), "estimated_tokens": estimated_tokens(exc.content)})
            _append_trace(trace, {"phase": "draft_salvage", "event": "narration_only_salvage", "reason": str(exc), "raw_content": exc.content})
        except LlmError:
            try:
                compact_context = _clean_context_for_handoff(_compact_turn_context(context), "planner_to_draft_parse_retry", trace)
                retry_prompt = build_user_prompt(compact_context, player_input)
                retry_system_prompt = f"{system_prompt}\n\nThe previous draft was malformed JSON and could not be repaired in time. Return one valid compact JSON object only."
                active_context = compact_context
                draft = _chat_json(
                    retry_system_prompt,
                    retry_prompt,
                    timeout=timeout,
                    usage=usage,
                    phase="draft_parse_retry",
                    max_tokens=_turn_max_tokens(active_context, "draft", compact=True),
                    trace=trace,
                )
            except LlmError as retry_exc:
                raise _attach_model_usage(retry_exc, usage, trace)
    except LlmError as exc:
        if _is_connection_refused_error(exc):
            raise _attach_model_usage(exc, usage, trace)
        if _is_timeout_error(exc):
            raise _attach_model_usage(exc, usage, trace)
        if _is_context_length_error(exc):
            active_context = _clean_context_for_handoff(_compact_turn_context(context), "planner_to_draft_compact_retry", trace)
            try:
                draft = _chat_json(
                    system_prompt,
                    build_user_prompt(active_context, player_input),
                    timeout=timeout,
                    usage=usage,
                    phase="draft_compact_retry",
                    max_tokens=_turn_max_tokens(active_context, "draft", compact=True),
                    trace=trace,
                )
            except LlmError as retry_exc:
                raise _attach_model_usage(retry_exc, usage, trace)
        else:
            try:
                draft = _chat_json(
                    system_prompt,
                    draft_prompt,
                    timeout=timeout,
                    usage=usage,
                    phase="draft_retry",
                    max_tokens=_turn_max_tokens(active_context, "draft"),
                    trace=trace,
                )
            except LlmError as retry_exc:
                    raise _attach_model_usage(retry_exc, usage, trace)
    try:
        draft = _clean_turn_for_handoff(_normalize_turn(draft), "draft_to_verify", trace)
        _append_trace(trace, {"phase": "draft_normalize", "event": "normalized", "narration_chars": _narration_char_count(draft), "keys": sorted(draft.keys())})
    except LlmError as exc:
        if not _is_missing_narration_error(exc):
            _append_trace(trace, {"phase": "draft_normalize", "event": "error", "error": str(exc)})
            raise _attach_model_usage(exc, usage, trace)
        try:
            _append_trace(trace, {"phase": "draft_normalize", "event": "missing_narration_retry", "error": str(exc)})
            draft = _clean_turn_for_handoff(_normalize_turn(
                _retry_missing_narration(
                    active_context,
                    player_input,
                    system_prompt,
                    timeout,
                    usage,
                    "draft_missing_narration_retry",
                    trace,
                )
            ), "draft_missing_narration_to_verify", trace)
            _append_trace(trace, {"phase": "draft_missing_narration_retry", "event": "normalized", "narration_chars": _narration_char_count(draft), "keys": sorted(draft.keys())})
        except LlmError as retry_exc:
            raise _attach_model_usage(retry_exc, usage, trace)
    progress_update(
        "draft_ready",
        "Draft received; scoring verification…",
        step=3,
        line="Draft normalized.",
    )
    if isinstance(draft, dict) and str(draft.get("narration") or "").strip():
        progress_preview(str(draft.get("narration") or "").strip(), append_paragraph=False)
    verification_policy = _verification_policy(context, player_input, draft)
    active_context = {**active_context, "verification_policy": verification_policy}
    _append_trace(trace, {"phase": "verification_policy", "event": "scored", **verification_policy})
    if verification_policy.get("mode") == "skip_model_verifier":
        usage.append({"phase": "verify_skipped_certainty", "chars": 0, "estimated_tokens": 0})
        progress_update(
            "verify_skip",
            "Verifier skipped; polishing narration…",
            step=4,
            line="Certainty policy skipped model verifier.",
        )
        result = _mark_draft_verified_by_policy(draft, verification_policy)
        result = _ensure_narration_quality(result, active_context, player_input, system_prompt, timeout, usage, "narration_depth_certainty_retry", trace)
        result = _clean_turn_for_handoff(result, "draft_certainty_to_world", trace)
        result["_verification_policy"] = verification_policy
        _append_trace(
            trace,
            {
                "phase": "pipeline",
                "event": "success",
                "narration_chars": _narration_char_count(result),
                "used_fallback": False,
                "verifier_skipped": True,
                "verification_certainty": verification_policy.get("certainty"),
                "narration_pipeline": bool(result.get("_narration_pipeline")),
            },
        )
        result["_model_usage"] = usage
        result["_model_trace"] = trace
        return result
    try:
        progress_update(
            "verify",
            "Verifier is checking continuity and state changes…",
            step=3,
            line="Model verifier pass in progress.",
        )
        verified = _chat_json(
            verify_prompt,
            build_verify_prompt(active_context, player_input, draft),
            timeout=verify_timeout,
            usage=usage,
            phase="verify",
            max_tokens=_turn_max_tokens(active_context, "verify"),
            trace=trace,
        )
        try:
            result = _normalize_turn(verified)
        except LlmError as exc:
            if not _is_missing_narration_error(exc):
                raise
            result = _merge_verified_with_draft_narration(verified, draft)
        progress_update(
            "narration",
            "Polishing narration quality…",
            step=4,
            line="Narration quality / pipeline pass.",
        )
        result = _ensure_narration_quality(result, active_context, player_input, system_prompt, timeout, usage, "narration_depth_retry", trace)
        result = _clean_turn_for_handoff(result, "verifier_to_world", trace)
        result["_verification_policy"] = verification_policy
        _append_trace(
            trace,
            {
                "phase": "pipeline",
                "event": "success",
                "narration_chars": _narration_char_count(result),
                "used_fallback": False,
                "narration_pipeline": bool(result.get("_narration_pipeline")),
            },
        )
        result["_model_usage"] = usage
        result["_model_trace"] = trace
        return result
    except LlmError as exc:
        if _is_context_length_error(exc):
            try:
                compact_context = _clean_context_for_handoff(_compact_turn_context(active_context), "planner_to_verify_compact_retry", trace)
                verified = _chat_json(
                    verify_prompt,
                    build_verify_prompt(compact_context, player_input, draft),
                    timeout=verify_timeout,
                    usage=usage,
                    phase="verify_compact_retry",
                    max_tokens=_turn_max_tokens(compact_context, "verify", compact=True),
                    trace=trace,
                )
                try:
                    result = _normalize_turn(verified)
                except LlmError as verify_exc:
                    if not _is_missing_narration_error(verify_exc):
                        raise
                    result = _merge_verified_with_draft_narration(verified, draft)
                result = _ensure_narration_quality(result, compact_context, player_input, system_prompt, timeout, usage, "narration_depth_compact_retry", trace)
                result = _clean_turn_for_handoff(result, "verifier_compact_retry_to_world", trace)
                result["_verification_policy"] = verification_policy
                _append_trace(
                    trace,
                    {
                        "phase": "pipeline",
                        "event": "success",
                        "narration_chars": _narration_char_count(result),
                        "used_fallback": False,
                        "narration_pipeline": bool(result.get("_narration_pipeline")),
                    },
                )
                result["_model_usage"] = usage
                result["_model_trace"] = trace
                return result
            except LlmError:
                pass
        draft = _normalize_turn(draft)
        draft["self_check"] = {
            "passed": False,
            "issues_found": ["Verifier pass failed; using draft."],
            "corrections_made": [],
            "reference_check": "not verified",
            "consistency_check": "not verified",
        }
        draft = _ensure_narration_quality(draft, active_context, player_input, system_prompt, timeout, usage, "narration_depth_draft_retry", trace)
        draft = _clean_turn_for_handoff(draft, "draft_to_world_unverified", trace)
        draft["_verification_policy"] = verification_policy
        _append_trace(
            trace,
            {
                "phase": "pipeline",
                "event": "using_unverified_draft",
                "verifier_error": str(exc),
                "narration_chars": _narration_char_count(draft),
                "narration_pipeline": bool(draft.get("_narration_pipeline")),
            },
        )
        draft["_model_usage"] = usage
        draft["_model_trace"] = trace
        return draft
