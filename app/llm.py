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
from app.idea_bank import idea_sparks_for_prompt, prompt_sparks
from app.setup_composer import (
    COMPOSER_FIELD_ORDER,
    OVERUSED_SEED_DOMAINS,
    SEED_SKILL_DOMAIN_POOL,
    apply_keyword_intent,
    coerce_setup_bool,
    coerce_typed_setup_fields,
    empty_intent,
    field_contamination_reasons,
    field_contract,
    field_is_contaminated,
    intent_slice_for_field,
    is_instruction_echo,
    is_overused_seed_domain,
    merge_intent_plans,
    normalize_look_fields,
    normalize_magic_level,
    opening_feel_prompt_block,
    pick_seed_skill_domain,
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
    anti_repetition_block,
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
# Set after successful start; used to detect base-model / LoRA swaps.
_managed_llama_signature = ""
# LLM-only lifecycle (web app never restarts for LoRA/theme swaps).
_llm_runtime: dict[str, Any] = {
    "phase": "offline",  # offline | starting | switching | ready | error
    "method": "none",  # none | hot_swap | soft_recycle | already_ready
    "message": "LLM not started yet.",
    "detail": "",
    "signature": "",
    "lora_path": "",
    "base_model": "",
    "updated_at": 0.0,
    "error": "",
}
_llm_runtime_lock = __import__("threading").Lock()


DEFAULT_GGUF_MODEL = ""
# 8192 could not hold SYSTEM_PROMPT (~9100 tokens), so a default launch fell back
# to deterministic prose on every turn. 32768 matches the context the README
# benchmarks and the playtest tools in tools/ already use.
DEFAULT_CONTEXT_TOKENS = 32768
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
    "response_drafts",
    "index_updates",
    "ability_updates",
}

# --- verifier circuit breaker ------------------------------------------------
#
# Small local models cannot do the verify pass. Measured on qwen2.5:7b-instruct:
# `verify` returned an echo of the input world_state on 42/42 turns, then
# `verify_repair` failed on all 42 too — ~26s per turn spent producing nothing.
#
# Rather than a per-model config flag nobody will set, watch the pass and stop
# calling it once it has clearly proven itself useless on this machine. On a
# model where verification works, the breaker never trips and nothing changes.
_VERIFY_FAILURE_STREAK = 0
_VERIFY_DISABLED_REASON = ""


def _verify_breaker_limit() -> int:
    try:
        return max(0, int(os.getenv("AI_RPG_VERIFY_FAILURE_LIMIT", "3")))
    except (TypeError, ValueError):
        return 3


def verifier_is_disabled() -> bool:
    """True once the verify pass has failed enough times to stop trying."""
    limit = _verify_breaker_limit()
    return bool(limit) and _VERIFY_FAILURE_STREAK >= limit


def _note_verify_outcome(ok: bool, reason: str = "") -> None:
    global _VERIFY_FAILURE_STREAK, _VERIFY_DISABLED_REASON
    if ok:
        _VERIFY_FAILURE_STREAK = 0
        _VERIFY_DISABLED_REASON = ""
        return
    _VERIFY_FAILURE_STREAK += 1
    if verifier_is_disabled() and not _VERIFY_DISABLED_REASON:
        _VERIFY_DISABLED_REASON = (
            f"Model verifier failed {_VERIFY_FAILURE_STREAK} times in a row "
            f"({reason or 'unusable output'}); skipping it for this session. "
            f"Set AI_RPG_VERIFY_FAILURE_LIMIT=0 to always retry."
        )


def _verified_output_is_useful(verified: Any, draft: dict[str, Any]) -> bool:
    """
    Did the verifier actually return a corrected turn?

    The characteristic small-model failure is regurgitation: it echoes the
    ``world_state`` it was given back as its answer. That parses as JSON and
    looks like success, so check for turn-shaped content instead of validity.
    """
    if not isinstance(verified, dict):
        return False
    # Echoing the prompt back: the reply carries the input wrapper keys.
    if "world_state" in verified or "draft_turn" in verified:
        return False
    turn_keys = {"narration", "narration_segments", "scene_plan", "turn_summary", "self_check"}
    if not (turn_keys & set(verified)):
        return False
    # A verifier that returns nothing but an empty shell is not useful either.
    return bool(_narration_char_count(_coerce_turn_shape(verified)) or verified.get("narration_segments"))


def _coerce_turn_shape(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def verifier_breaker_status() -> dict[str, Any]:
    return {
        "failure_streak": _VERIFY_FAILURE_STREAK,
        "disabled": verifier_is_disabled(),
        "reason": _VERIFY_DISABLED_REASON,
        "limit": _verify_breaker_limit(),
    }


def reset_verifier_breaker() -> None:
    """Clear the breaker — used by tests and when model config changes."""
    global _VERIFY_FAILURE_STREAK, _VERIFY_DISABLED_REASON
    _VERIFY_FAILURE_STREAK = 0
    _VERIFY_DISABLED_REASON = ""


# Recording that a conversation happened is not a risky state change — it
# writes a topic and a summary, mints nothing, and cannot unbalance a run.
# It was the single most common reason verification could not be skipped
# (fired on most talk turns), so it now carries only a small certainty cost.
LOW_RISK_TURN_CHANGE_KEYS = {"conversations"}
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
    # Server-stated contracts. Omitting a key here nulls it out of the packet
    # silently — the same failure that stripped the band fields off `player`.
    "movement_contract",
    "narrative_voice",
    "naming_contract",
    "recall_contract",
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
    # Band forms of the amounts above. This is an allowlist: anything missing
    # here is silently stripped during handoff cleanup, so omitting the bands
    # made the model's amounts vanish before world.apply_turn could roll them.
    "health_band",
    "xp_band",
    "gold_band",
    "karma_band",
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
    # Legal/given names (or given + family). Not handles, street nicknames, or epithets.
    "player_name": [
        "Mara Ellison",
        "Corvin Hale",
        "Iris Vale",
        "Tamsin Reed",
        "Kael Morin",
        "Elena Croft",
        "Jonas Pike",
        "Sable Quinn",
        "Ren Ashford",
        "Liora Dane",
        "Marcus Bell",
        "Nadia Voss",
        "Tobias Wren",
        "Helena Kade",
        "Darius Cole",
        "Miriam Shaw",
        "Owen Graves",
        "Celia Thorn",
        "Felix Rourke",
        "Ava Mercer",
    ],
    # Handles / nicknames / public aliases only (usually blank).
    "player_public_name": ["", "Ash", "River", "Patch", "Northlight", "Second Bell"],
    "player_title": ["", "the Weatherwise", "of Kiln Street", "the Long Listener", "the Spare Key"],
    "player_age": ["17", "19", "24", "31", "middle-aged", "appears 30", "adult"],
    # Sex uses weighted picker in _fallback_sex_value (male/female majority).
    "player_sex": ["female", "male", "", "intersex", "sexless or constructed", "varies by form"],
    "previous_life_age": ["19", "27", "34", "46", "elderly", "unknown"],
    "previous_life_sex": ["female", "male", "", "intersex", "sexless or constructed", "varies by form"],
    "backstory_mode": ["known", "hidden", "fragmented memories", "reincarnated", "transmigrated", "nameless drifter"],
    "memory_policy": ["known", "ordinary memory", "details emerge through choices", "rumors may be wrong", "private details stay private", "remembers former life"],
    "hair": [
        "short brown hair",
        "long black braid",
        "messy copper curls",
        "cropped black hair",
        "shoulder-length ash blonde",
        "tight cornrows",
        "bald with stubble shadow",
        "white undercut",
        "wavy auburn hair",
        "chin-length dark hair",
        "high ponytail, black",
        "salt-and-pepper buzz cut",
        "long red waves",
        "short green-dyed tips",
        "neat side part, brown",
        "messy silver fringe",
    ],
    "facial_features": [
        "green eyes, light freckles, soft jaw",
        "dark brown eyes, thin scar on left cheek",
        "amber eyes, high cheekbones, crooked smile",
        "blue-grey eyes, deep-set, narrow nose",
        "black eyes, round face, small burn near temple",
        "hazel eyes, faint laugh lines, straight nose",
        "pale blue eyes, freckled bridge, soft mouth",
        "gold-flecked brown eyes, thick brows, cleft chin",
        "one cloudy eye, sharp cheekbones, thin lips",
        "warm brown eyes, full cheeks, broken nose healed",
        "violet contacts, painted freckles, pointed chin",
        "green-brown eyes, deep laugh creases, strong brow",
    ],
    "appearance": list(
        # Filled from setup_composer seed pool at import end if available; keep local fallbacks:
        [
            "torso: plain travel clothes; feet: practical shoes; bag: thin shoulder bag",
            "torso: secondhand work shirt; feet: scuffed shoes; hands: cheap gloves",
            "torso: light jacket over tee; feet: sneakers; bag: small daypack",
            "torso: rain-damp hoodie; feet: wet sneakers",
            "torso: hospital scrub top under coat; feet: soft shoes; neck: badge lanyard",
            "torso: kitchen apron over street clothes; feet: non-slip shoes",
            "torso: delivery jacket; hands: bike gloves; feet: trail shoes",
            "torso: teacher cardigan over blouse; feet: flats; bag: tote",
            "torso: patched canvas vest; hands: work gloves; feet: worn boots",
            "torso: coarse hooded tunic; feet: scuffed leather shoes; bag: worn satchel",
            "torso: travel cloak; legs: patched trousers; feet: dusty boots",
            "torso: plain work tunic; waist: rope belt; feet: practical boots",
            "torso: oilcloth rain cloak; legs: tough trousers; bag: waterproof wrap",
            "torso: simple robes; feet: cloth shoes",
            "torso: ferry-hand jacket; feet: salt-stained boots; bag: net pouch",
            "torso: market stall apron; feet: soft shoes; bag: coin purse",
            "torso: quilted work vest; hands: fingerless gloves; feet: trail boots",
            "torso: formal vest over shirt; feet: cracked shoes",
        ]
    ),
    "starter_equipment": [
        "worn coat, coiled rope, pocket knife, dusty boots, water skin, 3 days rations",
        "plain clothes, work gloves, small tool pouch, practical boots",
        "travel cloak, empty satchel, wooden charm, heel of bread",
        "secondhand jacket, notebook stub, stub of chalk, water flask",
        "canvas bag, multi-tool, duct tape roll, cheap flashlight, snacks",
        "rain cloak, fishing line, tin cup, flint kit, dried fish",
        "cracked phone, house keys, transit card, light jacket, half-empty water bottle",
        "hospital badge on a lanyard, soft shoes, zip hoodie, folded scrub top, cheap earbuds",
        "bike gloves, delivery bag, rain poncho, dead phone, protein bar",
        "teacher's tote, red pen, lesson notes, cardigan, bus pass",
        "hotel keycard, pressed shirt, small umbrella, mints, spare name tag",
        "kitchen apron, burn cream tube, non-slip shoes, spare hair tie, street wallet",
        "folding knife, tin cup, wool scarf, oilcloth wrap, day of hard bread",
        "sewing kit, scrap cloth, wooden needle case, soft shoes, dried fruit",
        "fishing hooks, line spool, tin cup, straw hat, smoked fish",
        "ledger stub, charcoal pencil, plain tunic, belt pouch, water skin",
        "dead phone, wallet with useless cards, apartment keys, light jacket",
        "ID badge, lanyard, soft shoes, hoodie, half pack of mints",
        "messenger bag, cracked earbuds, bus pass, secondhand jacket",
        "work gloves, repair pouch, patched vest, worn boots, water skin",
    ],
    "character_backstory": [
        "Born in a canal district where freight crews raised children as extra hands, they grew up reading cargo marks, weather signs, and people's excuses. Before the story begins, they worked as a route clerk who kept small settlements supplied, and they reached the starting area carrying one delayed delivery, two unpaid favors, and a fear that their last ledger was altered.",
        "Born in a hill village that treated old ruins as common landmarks, they spent most of their life repairing tools, copying maps, and guiding travelers through roads locals considered ordinary. They left after a winter landslide exposed sealed stonework under the village shrine, bringing practical skills, a few local contacts, and one question their elders refused to answer.",
        "They taught evening classes in a rented room above a laundry, grading papers until the building fire alarm failed. Smoke and a wrong turn on the stair took them; they woke under open sky beside a timber gate, still clutching a red pen and a bus pass that means nothing here.",
        "A ride-share driver chasing surge pay died when a truck jumped a curb. They opened their eyes on a muddy road outside a walled settlement, phone dead, only street clothes and ordinary driving habits left.",
        "Hospital admissions night shift ended mid-code when the power cut and something else cut through. They came to on stone steps above foreign rooftops with a lanyard badge and soft shoes, no free power — only crisis habits.",
        "A failed outer-court ritual yanked them out of a rainy city street and into a sect compound still wearing street clothes. They remember the summon circle, the smell of burnt paper, and the awkward silence of disciples who expected a legendary spirit instead of a confused outsider.",
        "Reborn into a canal village as a child years ago, they grew up hauling water and copying notice-board marks while half-remembering glass towers and night traffic from a life that no longer has a body. Locals know them only as a quiet apprentice, not as anyone from another world.",
        "They cooked line food until a kitchen gas blast blacked them out. Next breath was cold air and rope smells in a low-tech alley; apron gone, only burns and street clothes remaining.",
    ],
    "skill_style": ["standard", "generous", "training-heavy", "strict"],
    "proficiency_access": ["learned", "familiar actions free", "only expert tasks require training"],
    "new_skill_frequency": ["normal", "very rare", "rare", "frequent", "very frequent"],
    "world_style": ["frontier dark fantasy", "wuxia sect politics", "system apocalypse", "post-collapse settlement", "mage academy intrigue", "low magic mercantile city", "space frontier salvage"],
    "start_location": [
        "Mosswake Gate",
        "Blackwater Relay",
        "The Ninth Stair",
        "Cinder Market Edge",
        "Ashford Clinic Gate",
        "Red Lantern Dock",
        "Saint Vale Station",
        "Outer Compound Yard",
        "Ash Road Cut",
        "Ferry Landing Stone",
        "Low Gate Timber Arch",
        "Saltwind Pier",
        "Iron Bell Crossroads",
        "Pale Bridge Footing",
        "Sect Outer Court Gate",
        "Ration Yard Post",
    ],
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
        "Seed skill Digging rank F; track ranks in subtle system UI; practice/risk/mentor XP in prose; no free second combat toolkit at Start",
        "Seed skill Coin Ring rank F; compounds via careful market work; passives OK later; opening kit thin",
        "Seed skill Residue Glow rank F; unreliable magic sense; ranks through risky attunement; more powers unlock later",
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
    "OP seed: F→E@60 E→D@140 D→C@320 C→B@700 B→A@1500 A→S@3200 S→SS@7000 SS→SSS@15000; use 6-14 XP × risk (1/2/3/5); XP_to_next = 40 * rank_index^1.55; soft caps after each band ×0.55 until contested breakthrough; effect mult ≈ 1.22^ranks_above_F; +1 domain check/rank; S+ may unlock passives",
    "levels 1-10; XP_to_next = 30 + 12*level; successful use grants 3-8 XP; crit success ×2; soft cap at L6 (XP ×0.6 until setback recovery); effect magnitude +8% per level",
    "thresholds F0 E100 D250 C500 B1000 A2000 S4000 SS9000 SSS20000; practice 5 XP, contested 12, mentor 18, life-risk 25; rank +1 check / +12–20% compound; breakthrough after B and A before S-tier; passives at C/A/S",
    "XP_to_next = 36 * rank_index^1.58 (F=1); use 5-11 XP × risk (1/2/3/4); soft cap after C ×0.55 until breakthrough; ladder F…S/SS/SSS; each rank +1 check / +14–22% effect",
]

SETUP_RANDOMIZER_ABILITY_FALLBACKS = [
    {
        "name": "Echo Step",
        "description": "A short burst of awkward repositioning — half a pace that should not fit, useful only for clumsy escapes.",
        "locked": False,
        "prerequisites": "",
        "cost": "brief fatigue after repeated use",
        "growth_math": GROWTH_MATH_SAMPLES[0],
    },
    {
        "name": "Ashen Oath",
        "description": "Can sense when someone nearby is hiding a binding promise or unpaid debt — a pressure, not a transcript.",
        "locked": True,
        "prerequisites": "Awakens after witnessing a broken oath with real consequences.",
        "cost": "mental strain when pushed",
        "growth_math": GROWTH_MATH_SAMPLES[1],
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
    {
        "name": "Coin Ring",
        "description": "Tap-tests cheap coin forgeries; misses good fakes and cannot price goods.",
        "locked": False,
        "prerequisites": "",
        "cost": "sore fingers after long market days",
        "growth_math": GROWTH_MATH_SAMPLES[0],
    },
    {
        "name": "Camp Ash",
        "description": "Judges roughly how old a cold fire is — hours vs days, not exact times.",
        "locked": False,
        "prerequisites": "",
        "cost": "soot in the lungs if sniffed too close",
        "growth_math": GROWTH_MATH_SAMPLES[1],
    },
    {
        "name": "Draft Feel",
        "description": "Skin prickles near air leaks, open flues, or poorly sealed doors.",
        "locked": True,
        "prerequisites": "Unlocks after sleeping in a drafty ruin without a fire.",
        "cost": "chills and distraction in wind",
        "growth_math": GROWTH_MATH_SAMPLES[2],
    },
    {
        "name": "Residue Glow",
        "description": "Faint unreliable sense of spent magic on objects — often wrong at F rank.",
        "locked": True,
        "prerequisites": "Awakens after touching a spent ward or failed charm.",
        "cost": "migraine after forced use",
        "growth_math": GROWTH_MATH_SAMPLES[3],
    },
    {
        "name": "Hauling",
        "description": "Awkward loads ride a little better — fewer dropped crates, not superhuman strength.",
        "locked": False,
        "prerequisites": "",
        "cost": "back ache that lingers",
        "growth_math": GROWTH_MATH_SAMPLES[0],
    },
    {
        "name": "Ward Itch",
        "description": "Skin itches near crude wards and hex-lines; sophisticated magic feels like nothing yet.",
        "locked": True,
        "prerequisites": "Needs a night sleeping against a marked threshold.",
        "cost": "rash if pushed",
        "growth_math": GROWTH_MATH_SAMPLES[1],
    },
    {
        "name": "Throw Line",
        "description": "Lobs a small object closer to the intended mark — stones, keys, bottles; not weapons mastery.",
        "locked": False,
        "prerequisites": "",
        "cost": "shoulder strain after repeats",
        "growth_math": GROWTH_MATH_SAMPLES[2],
    },
    {
        "name": "Spoilage Nose",
        "description": "Smells food going bad a day early; cannot identify poison reliably.",
        "locked": False,
        "prerequisites": "",
        "cost": "nausea in crowded kitchens",
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


# Room a turn needs beyond the fixed system contract: the world packet plus the
# reserved output. If the system prompt cannot leave this much, it does not fit.
MIN_TURN_HEADROOM_TOKENS = 2048


def fitting_system_prompts(config: dict[str, Any] | None = None) -> tuple[str, str, bool]:
    """Pick the largest system contract that actually fits the context window.

    Returns ``(system_prompt, verify_prompt, degraded)``.

    A default Ollama launch ran with ``context_window=8192`` while
    ``SYSTEM_PROMPT`` alone estimates ~9100 tokens. ``enforce_token_budget``
    then raised "system prompt alone is ~N tokens", every turn fell back to
    deterministic prose, and the player got canned narration with no obvious
    cause. Degrading to the compact contract keeps the model in the loop; the
    caller reports ``degraded`` so the reason is visible instead of silent.
    """
    model_config = config or get_model_config()
    if model_config.get("provider") == "llama_cpp":
        return COMPACT_SYSTEM_PROMPT, COMPACT_VERIFY_PROMPT, False
    window = int(
        model_config.get("context_window")
        or context_window_tokens(model_config)
        or DEFAULT_CONTEXT_TOKENS
    )
    if estimated_tokens(SYSTEM_PROMPT) + MIN_TURN_HEADROOM_TOKENS > window:
        return COMPACT_SYSTEM_PROMPT, COMPACT_VERIFY_PROMPT, True
    return SYSTEM_PROMPT, VERIFY_PROMPT, False


_WARNED_COMPACT_CONTRACT = False


def _warn_compact_contract_once(window: int) -> None:
    """Say once, on the server console, why the compact contract is in use.

    Silent degradation is what made this hard to diagnose in the first place:
    the player saw flat narration with nothing anywhere explaining that the
    context window could not hold the full contract.
    """
    global _WARNED_COMPACT_CONTRACT
    if _WARNED_COMPACT_CONTRACT:
        return
    _WARNED_COMPACT_CONTRACT = True
    print(
        f"[morkyn] context window {window} is too small for the full system contract "
        f"(~{estimated_tokens(SYSTEM_PROMPT)} tokens). Using the compact contract. "
        f"Raise the context size in the launcher (Advanced -> context) for richer turns.",
        file=sys.stderr,
        flush=True,
    )


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
THEME_ADAPTER_HINTS: tuple[str, ...] = (
    "isekai_rpg",
    "system_rpg",
    "grimdark",
    "mundane",
    "default",
)

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


def default_theme_llm_lora_map() -> dict[str, dict[str, Any]]:
    """Per-theme LLM LoRA (GGUF adapter) paths for llama.cpp. Empty path = base model only."""
    return {hint: {"path": "", "scale": 1.0, "note": ""} for hint in THEME_ADAPTER_HINTS}


def normalize_theme_llm_lora_map(raw: Any) -> dict[str, dict[str, Any]]:
    """
    Normalize theme → LLM LoRA map.
    Accepts:
      { "isekai_rpg": "D:/loras/isekai.gguf" }
      { "isekai_rpg": { "path": "...", "scale": 0.8, "note": "..." } }
    Multiple simultaneous LoRAs are not supported by llama-cpp-python server (one lora_path);
    use one adapter per theme, or Ollama models that already bake ADAPTER weights.
    """
    out = default_theme_llm_lora_map()
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        hint = str(key or "").strip()[:80]
        if not hint:
            continue
        entry: dict[str, Any] = {"path": "", "scale": 1.0, "note": ""}
        if isinstance(value, str):
            entry["path"] = value.strip()[:1000]
        elif isinstance(value, dict):
            entry["path"] = str(value.get("path") or value.get("lora_path") or "").strip()[:1000]
            try:
                entry["scale"] = max(0.0, min(2.0, float(value.get("scale") if value.get("scale") is not None else 1.0)))
            except (TypeError, ValueError):
                entry["scale"] = 1.0
            entry["note"] = str(value.get("note") or value.get("label") or "").strip()[:120]
        out[hint] = entry
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


def resolve_theme_llm_lora(
    session_theme: dict[str, Any] | None,
    lora_map: dict[str, Any] | None = None,
) -> tuple[str, str, float]:
    """
    Pick LLM LoRA path for this session theme.
    Priority: session_theme.theme_lora_path → theme_llm_lora_map[adapter_hint] → map[default].
    Returns (source_label, path, scale).
    """
    lmap = normalize_theme_llm_lora_map(lora_map)
    if isinstance(session_theme, dict) and session_theme:
        explicit = str(session_theme.get("theme_lora_path") or session_theme.get("llm_lora_path") or "").strip()
        if explicit:
            try:
                scale = float(session_theme.get("theme_lora_scale") if session_theme.get("theme_lora_scale") is not None else 1.0)
            except (TypeError, ValueError):
                scale = 1.0
            return "session_theme.theme_lora_path", explicit[:1000], max(0.0, min(2.0, scale))
        hint = str(session_theme.get("adapter_hint") or "default").strip() or "default"
        entry = lmap.get(hint) or {}
        path = str(entry.get("path") or "").strip()
        if path:
            try:
                scale = float(entry.get("scale") if entry.get("scale") is not None else 1.0)
            except (TypeError, ValueError):
                scale = 1.0
            return f"theme_llm_lora_map[{hint}]", path[:1000], max(0.0, min(2.0, scale))
    # Fallback default pack even without a session theme (optional base style LoRA).
    default_entry = lmap.get("default") or {}
    path = str(default_entry.get("path") or "").strip()
    if path:
        try:
            scale = float(default_entry.get("scale") if default_entry.get("scale") is not None else 1.0)
        except (TypeError, ValueError):
            scale = 1.0
        return "theme_llm_lora_map[default]", path[:1000], max(0.0, min(2.0, scale))
    return "", "", 1.0


def apply_theme_model_routing(
    config: dict[str, Any],
    session_theme: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    Return a copy of model config with theme-based model + LLM LoRA applied (turn-time only).
    Ollama → ollama_model; OpenAI-compatible → api_model; llama.cpp path-like → gguf_model_path.
    LLM LoRA (GGUF adapter) → lora_path for managed llama.cpp server.
    """
    out = dict(config or {})
    adapter_map = normalize_theme_adapter_map(out.get("theme_adapter_map"))
    lora_map = normalize_theme_llm_lora_map(out.get("theme_llm_lora_map"))
    out["theme_adapter_map"] = adapter_map
    out["theme_llm_lora_map"] = lora_map
    source, model = resolve_theme_model_override(
        session_theme if isinstance(session_theme, dict) else None,
        adapter_map,
    )
    out["theme_model_source"] = source
    out["theme_model_active"] = model
    lora_source, lora_path, lora_scale = resolve_theme_llm_lora(
        session_theme if isinstance(session_theme, dict) else None,
        lora_map,
    )
    out["theme_lora_source"] = lora_source
    out["theme_lora_active"] = lora_path
    provider = _normalize_provider(out.get("provider"))
    # Theme-resolved LoRA wins; otherwise keep always-on lora_path from model settings.
    if lora_path:
        out["lora_path"] = lora_path
        out["lora_scale"] = lora_scale
    else:
        out["lora_path"] = str(out.get("lora_path") or "").strip()
        try:
            out["lora_scale"] = max(0.0, min(2.0, float(out.get("lora_scale") if out.get("lora_scale") is not None else 1.0)))
        except (TypeError, ValueError):
            out["lora_scale"] = 1.0
    # Ollama cannot load GGUF LoRA files mid-request — theme_adapter_map should point at
    # Ollama models that already include the ADAPTER (or full fine-tunes).
    if provider != "llama_cpp":
        # Still record intent for UI/traces, but do not force a GGUF path onto non-llama providers.
        pass
    if model:
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
    cfg["theme_adapter_map"] = normalize_theme_adapter_map(cfg.get("theme_adapter_map"))
    cfg["theme_llm_lora_map"] = normalize_theme_llm_lora_map(cfg.get("theme_llm_lora_map"))
    cfg["theme_adapter_hints"] = list(THEME_ADAPTER_HINTS)
    cfg["lora_path"] = str(cfg.get("lora_path") or "").strip()
    try:
        cfg["lora_scale"] = max(0.0, min(2.0, float(cfg.get("lora_scale") if cfg.get("lora_scale") is not None else 1.0)))
    except (TypeError, ValueError):
        cfg["lora_scale"] = 1.0
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
        "theme_llm_lora_map": default_theme_llm_lora_map(),
        # Optional always-on LLM LoRA (overridden by theme map when a theme path resolves).
        "lora_path": os.getenv("AI_RPG_LLM_LORA_PATH", ""),
        "lora_scale": 1.0,
    }
    try:
        with connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'model_config'").fetchone()
    except Exception:
        default["provider"] = _normalize_provider(default["provider"])
        default["theme_adapter_map"] = normalize_theme_adapter_map(default.get("theme_adapter_map"))
        default["theme_llm_lora_map"] = normalize_theme_llm_lora_map(default.get("theme_llm_lora_map"))
        return default
    if not row:
        default["provider"] = _normalize_provider(default["provider"])
        default["theme_adapter_map"] = normalize_theme_adapter_map(default.get("theme_adapter_map"))
        default["theme_llm_lora_map"] = normalize_theme_llm_lora_map(default.get("theme_llm_lora_map"))
        return default
    try:
        stored = json.loads(row["value"])
    except json.JSONDecodeError:
        default["provider"] = _normalize_provider(default["provider"])
        default["theme_adapter_map"] = normalize_theme_adapter_map(default.get("theme_adapter_map"))
        default["theme_llm_lora_map"] = normalize_theme_llm_lora_map(default.get("theme_llm_lora_map"))
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
    merged["theme_llm_lora_map"] = normalize_theme_llm_lora_map(merged.get("theme_llm_lora_map"))
    merged["lora_path"] = str(merged.get("lora_path") or "").strip()
    try:
        merged["lora_scale"] = max(0.0, min(2.0, float(merged.get("lora_scale") if merged.get("lora_scale") is not None else 1.0)))
    except (TypeError, ValueError):
        merged["lora_scale"] = 1.0
    if os.getenv("AI_RPG_LLM_LORA_PATH"):
        merged["lora_path"] = str(os.getenv("AI_RPG_LLM_LORA_PATH") or "").strip()
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
        "lora_path",
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
    if "theme_llm_lora_map" in config:
        next_config["theme_llm_lora_map"] = normalize_theme_llm_lora_map(config.get("theme_llm_lora_map"))
    if "lora_scale" in config:
        try:
            next_config["lora_scale"] = max(0.0, min(2.0, float(config.get("lora_scale"))))
        except (TypeError, ValueError):
            next_config["lora_scale"] = 1.0
    if "response_token_cap" in config:
        next_config["response_token_cap"] = max(64, min(100_000, _int_value(config.get("response_token_cap"), DEFAULT_RESPONSE_TOKEN_CAP)))
    if "response_token_hard_cap" in config:
        next_config["response_token_hard_cap"] = max(64, min(100_000, _int_value(config.get("response_token_hard_cap"), DEFAULT_RESPONSE_HARD_CAP)))
    soft_cap, hard_cap = _response_token_settings(next_config)
    next_config["response_token_cap"] = soft_cap
    next_config["response_token_hard_cap"] = hard_cap
    next_config["provider"] = _normalize_provider(next_config.get("provider"))
    next_config["theme_adapter_map"] = normalize_theme_adapter_map(next_config.get("theme_adapter_map"))
    next_config["theme_llm_lora_map"] = normalize_theme_llm_lora_map(next_config.get("theme_llm_lora_map"))
    next_config["lora_path"] = str(next_config.get("lora_path") or "").strip()
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


def _managed_llama_config_signature(config: dict[str, Any]) -> str:
    """Identity of the loaded base GGUF + optional LLM LoRA."""
    model_path = str(config.get("gguf_model_path") or "").strip()
    lora_path = str(config.get("lora_path") or "").strip()
    return f"{model_path}||{lora_path}"


def _set_llm_runtime(**kwargs: Any) -> dict[str, Any]:
    """Update LLM runtime phase for UI polling (web app stays up during switches)."""
    with _llm_runtime_lock:
        _llm_runtime.update(kwargs)
        _llm_runtime["updated_at"] = time.time()
        return dict(_llm_runtime)


def get_llm_runtime() -> dict[str, Any]:
    """Public snapshot: website always works; phase describes LLM backend only."""
    with _llm_runtime_lock:
        snap = dict(_llm_runtime)
    snap["web_ok"] = True
    snap["llm_ok"] = snap.get("phase") == "ready"
    snap["busy"] = snap.get("phase") in {"starting", "switching"}
    # Friendly copy for banner
    phase = str(snap.get("phase") or "offline")
    if phase == "switching":
        snap.setdefault(
            "user_message",
            "Website stays online — swapping LLM adapter. Wait a moment before the next turn.",
        )
    elif phase == "starting":
        snap.setdefault(
            "user_message",
            "Website stays online — starting the local LLM. Generation waits until it is ready.",
        )
    elif phase == "ready":
        snap.setdefault("user_message", "LLM ready.")
    elif phase == "error":
        snap.setdefault("user_message", snap.get("error") or "LLM backend error.")
    else:
        snap.setdefault("user_message", "LLM offline (site still works).")
    return snap


def _list_native_lora_adapters(base_url: str, timeout: int = 3) -> list[dict[str, Any]] | None:
    """
    Native llama-server exposes GET /lora-adapters for multi-LoRA hot-swap.
    llama-cpp-python's OpenAI server does not — returns None when unavailable.
    """
    url = f"{base_url.rstrip('/')}/lora-adapters"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [row for row in payload["data"] if isinstance(row, dict)]
    return None


def try_hot_swap_llm_lora(
    base_url: str,
    *,
    lora_path: str = "",
    scale: float = 1.0,
) -> dict[str, Any]:
    """
    Prefer true hot-swap when the LLM server already loaded adapters (native llama-server).
    Does not restart the web app or the LLM process.
    """
    adapters = _list_native_lora_adapters(base_url)
    if adapters is None:
        return {
            "ok": False,
            "method": "hot_swap",
            "error": "Server has no /lora-adapters endpoint (typical for llama-cpp-python). Soft-recycle will be used instead.",
        }
    wanted = str(lora_path or "").strip()
    wanted_name = Path(wanted).name.lower() if wanted else ""
    body: list[dict[str, Any]] = []
    matched = False
    for row in adapters:
        aid = row.get("id")
        if aid is None:
            continue
        path = str(row.get("path") or row.get("name") or "")
        name = Path(path).name.lower() if path else ""
        if not wanted:
            # Clear all adapters
            body.append({"id": aid, "scale": 0.0})
            continue
        if path == wanted or name == wanted_name or wanted.lower() in path.lower():
            body.append({"id": aid, "scale": max(0.0, min(2.0, float(scale)))})
            matched = True
        else:
            body.append({"id": aid, "scale": 0.0})
    if wanted and not matched:
        return {
            "ok": False,
            "method": "hot_swap",
            "error": (
                f"LoRA not preloaded on server: {wanted_name or wanted}. "
                "Start native llama-server with --lora for each theme adapter and --lora-init-without-apply, "
                "or use soft-recycle (managed llama-cpp-python)."
            ),
            "adapters": adapters,
        }
    if not body and not wanted:
        return {"ok": True, "method": "hot_swap", "message": "No adapters to clear.", "adapters": adapters}
    url = f"{base_url.rstrip('/')}/lora-adapters"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
        try:
            result = json.loads(raw) if raw.strip() else {"ok": True}
        except json.JSONDecodeError:
            result = {"ok": True, "raw": raw[:200]}
        return {
            "ok": True,
            "method": "hot_swap",
            "message": f"Hot-swapped LLM LoRA scales ({len(body)} adapter slot(s)).",
            "applied": body,
            "server": result,
            "adapters": adapters,
        }
    except Exception as exc:
        return {"ok": False, "method": "hot_swap", "error": f"Hot-swap POST failed: {exc}", "adapters": adapters}


def _stop_managed_llama_cpp() -> None:
    """Stop only the managed LLM process. Web/API process is untouched."""
    global _managed_llama_process, _managed_llama_base_url, _managed_llama_signature
    proc = _managed_llama_process
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:
                proc.kill()
        except Exception:
            pass
    _managed_llama_process = None
    _managed_llama_base_url = ""
    _managed_llama_signature = ""


def soft_recycle_llm_backend(config: dict[str, Any], base_url: str) -> dict[str, Any]:
    """
    Soft-recycle: stop and restart only the managed LLM process.
    The Mørkyn web frontend/backend keep running; the user waits for LLM ready.
    """
    model_path = str(config.get("gguf_model_path") or "").strip()
    lora_path = str(config.get("lora_path") or "").strip()
    wanted = _managed_llama_config_signature(config)
    _set_llm_runtime(
        phase="switching",
        method="soft_recycle",
        message="Recycling LLM process for new base model / LoRA…",
        detail="Web UI stays online. Turns wait until the local model is ready.",
        signature=wanted,
        lora_path=lora_path,
        base_model=model_path,
        error="",
    )
    if _managed_process_running(base_url):
        _stop_managed_llama_cpp()
        # Brief pause so the port is released before rebind.
        time.sleep(0.6)
    result = _start_managed_llama_cpp(config, base_url, force_new=True)
    if result.get("error"):
        _set_llm_runtime(
            phase="error",
            method="soft_recycle",
            message="LLM recycle failed.",
            error=str(result.get("error") or "unknown"),
            signature="",
            lora_path=lora_path,
            base_model=model_path,
        )
        return result
    models_url = f"{base_url.rstrip('/')}/v1/models"
    payload, wait_error = _wait_for_models(
        models_url,
        _managed_llama_process,
        _env_int("AI_RPG_LLM_STARTUP_TIMEOUT", 180),
    )
    if payload is None:
        _set_llm_runtime(
            phase="error",
            method="soft_recycle",
            message="LLM did not become ready after recycle.",
            error=wait_error,
            signature="",
            lora_path=lora_path,
            base_model=model_path,
        )
        result["error"] = wait_error
        result["ok"] = False
        return result
    _set_llm_runtime(
        phase="ready",
        method="soft_recycle",
        message=result.get("message") or "LLM ready after soft recycle.",
        detail="Adapter/base loaded. Website never stopped.",
        signature=wanted,
        lora_path=lora_path,
        base_model=model_path,
        error="",
    )
    result["ok"] = True
    result["method"] = "soft_recycle"
    result["runtime"] = get_llm_runtime()
    return result


def ensure_llm_adapter_ready(config: dict[str, Any]) -> dict[str, Any]:
    """
    Make sure the running LLM matches config's base + LoRA.
    Order: already ready → native hot-swap → soft-recycle managed process.
    Never restarts the FastAPI/web process.
    """
    global _managed_llama_signature

    provider = _normalize_provider(config.get("provider"))
    if provider != "llama_cpp":
        _set_llm_runtime(
            phase="ready",
            method="none",
            message=f"Provider {provider} — no GGUF LoRA process to manage.",
            error="",
        )
        return {"ok": True, "method": "none", "provider": provider, "runtime": get_llm_runtime()}

    base_url = str(config.get("llama_cpp_base_url") or "http://localhost:8080").rstrip("/")
    wanted = _managed_llama_config_signature(config)
    lora_path = str(config.get("lora_path") or "").strip()
    scale = 1.0
    try:
        scale = float(config.get("lora_scale") if config.get("lora_scale") is not None else 1.0)
    except (TypeError, ValueError):
        scale = 1.0

    # Already on the right signature with our managed process.
    if _managed_process_running(base_url) and _managed_llama_signature == wanted:
        _set_llm_runtime(
            phase="ready",
            method="already_ready",
            message="LLM already running with the requested base/LoRA.",
            signature=wanted,
            lora_path=lora_path,
            base_model=str(config.get("gguf_model_path") or ""),
            error="",
        )
        return {"ok": True, "method": "already_ready", "runtime": get_llm_runtime()}

    # Same base model already up: try hot-swap first (native llama-server multi-LoRA).
    models_alive = False
    try:
        _read_models_url(f"{base_url}/v1/models", timeout=2)
        models_alive = True
    except Exception:
        models_alive = False

    if models_alive:
        hot = try_hot_swap_llm_lora(base_url, lora_path=lora_path, scale=scale)
        if hot.get("ok"):
            # Hot-swap only changes adapter scales; track signature if we own process or trust external.
            if _managed_process_running(base_url) or not _managed_llama_process:
                _managed_llama_signature = wanted
            _set_llm_runtime(
                phase="ready",
                method="hot_swap",
                message=str(hot.get("message") or "Hot-swapped LLM LoRA."),
                signature=wanted,
                lora_path=lora_path,
                base_model=str(config.get("gguf_model_path") or ""),
                error="",
            )
            return {**hot, "runtime": get_llm_runtime()}

    # Soft-recycle managed LLM only (or start fresh).
    return soft_recycle_llm_backend(config, base_url)


def _start_managed_llama_cpp(
    config: dict[str, Any],
    base_url: str,
    *,
    force_new: bool = False,
) -> dict[str, Any]:
    global _managed_llama_base_url, _managed_llama_logs, _managed_llama_process, _managed_llama_signature

    model_path = str(config.get("gguf_model_path") or "").strip()
    if not model_path:
        return {"started": False, "managed": False, "error": "No GGUF model path is saved. Select a GGUF model file, save the model settings, then test again."}
    if not Path(model_path).is_file():
        return {"started": False, "managed": False, "error": f"Saved GGUF model file was not found: {model_path}"}

    lora_path = str(config.get("lora_path") or "").strip()
    if lora_path and not Path(lora_path).is_file():
        return {
            "started": False,
            "managed": False,
            "error": f"LLM LoRA adapter file was not found: {lora_path}",
        }

    wanted = _managed_llama_config_signature(config)
    if not force_new and _managed_process_running(base_url):
        if _managed_llama_signature == wanted or (not _managed_llama_signature and not lora_path):
            _set_llm_runtime(
                phase="ready",
                method="already_ready",
                message="Managed llama.cpp already running.",
                signature=_managed_llama_signature or wanted,
                lora_path=lora_path,
                base_model=model_path,
                error="",
            )
            return {
                "started": False,
                "managed": True,
                "message": "Managed llama.cpp server is already starting or running.",
                "logs": _managed_llama_logs,
                "signature": _managed_llama_signature or wanted,
            }
        # Theme/base LoRA changed — soft-recycle LLM only (web stays up).
        return soft_recycle_llm_backend(config, base_url)

    _set_llm_runtime(
        phase="starting",
        method="soft_recycle" if force_new else "none",
        message="Starting managed LLM process…",
        detail="Web UI stays online.",
        signature=wanted,
        lora_path=lora_path,
        base_model=model_path,
        error="",
    )

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
    # llama-cpp-python server: single LoRA adapter (GGUF LoRA from convert_lora_to_gguf / GGUF-my-LoRA).
    # Multi-theme: soft-recycle with a different --lora_path, or use native llama-server + hot-swap.
    if lora_path:
        args.extend(["--lora_path", lora_path])
    try:
        _managed_llama_process = subprocess.Popen(args, stdout=stdout_handle or subprocess.DEVNULL, stderr=stderr_handle or subprocess.DEVNULL)
    except Exception as exc:
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()
        _set_llm_runtime(phase="error", message="Could not start LLM.", error=str(exc))
        return {"started": False, "managed": False, "error": f"Could not start llama.cpp server: {exc}"}

    if stdout_handle:
        stdout_handle.close()
    if stderr_handle:
        stderr_handle.close()
    _managed_llama_base_url = base_url
    _managed_llama_signature = wanted
    _managed_llama_logs = {"stdout": stdout_path, "stderr": stderr_path}
    lora_note = f" + LoRA {Path(lora_path).name}" if lora_path else ""
    return {
        "started": True,
        "managed": True,
        "message": f"Started managed llama.cpp server from saved GGUF model path{lora_note}.",
        "pid": _managed_llama_process.pid,
        "logs": _managed_llama_logs,
        "signature": wanted,
        "lora_path": lora_path,
        "web_unaffected": True,
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
    """
    Ensure the LLM process matches this config's base + LoRA.
    Prefer hot-swap; otherwise soft-recycle only the LLM (website stays up).
    """
    ensure = ensure_llm_adapter_ready(config)
    if ensure.get("ok") is False and ensure.get("error"):
        raise LlmError(str(ensure.get("error")))
    if ensure.get("method") in {"hot_swap", "already_ready", "none"}:
        # Confirm /v1/models still answers
        try:
            _read_models_url(f"{base_url.rstrip('/')}/v1/models", timeout=4)
            return
        except Exception:
            pass
    # Soft-recycle path already waited, but double-check if process just started without wait.
    if ensure.get("method") == "soft_recycle" and ensure.get("ok"):
        return
    models_url = f"{base_url.rstrip('/')}/v1/models"
    if _managed_process_running(base_url.rstrip("/")):
        payload, wait_error = _wait_for_models(
            models_url,
            _managed_llama_process,
            _env_int("AI_RPG_LLM_STARTUP_TIMEOUT", 180),
        )
        if payload is None:
            raise LlmError(wait_error)
        _set_llm_runtime(
            phase="ready",
            method=str(ensure.get("method") or "soft_recycle"),
            message="LLM ready.",
            signature=_managed_llama_signature,
            error="",
        )
        return
    # Cold start
    start_result = _start_managed_llama_cpp(config, base_url.rstrip("/"))
    if not (start_result.get("started") or start_result.get("managed")):
        raise LlmError(str(start_result.get("error") or "Could not start managed llama.cpp server."))
    payload, wait_error = _wait_for_models(
        models_url,
        _managed_llama_process,
        _env_int("AI_RPG_LLM_STARTUP_TIMEOUT", 180),
    )
    if payload is None:
        _set_llm_runtime(phase="error", error=wait_error, message="LLM failed to start.")
        raise LlmError(wait_error)
    _set_llm_runtime(
        phase="ready",
        method="soft_recycle",
        message=str(start_result.get("message") or "LLM ready."),
        signature=_managed_llama_signature,
        lora_path=str(config.get("lora_path") or ""),
        base_model=str(config.get("gguf_model_path") or ""),
        error="",
    )


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
    elif group == "special_abilities":
        # Critical: must be ONLY special_abilities. Defaulting to the character group
        # silently skips the ability quality gate and ships name=description junk from 8B models.
        return_fields = ["special_abilities"]
    elif group in SETUP_RANDOMIZER_FIELD_GROUPS:
        return_fields = SETUP_RANDOMIZER_FIELD_GROUPS[group]
    elif group in SETUP_RANDOMIZER_ALL_FIELD_ORDER or group in {
        "special_abilities",
        "custom_skills",
    }:
        # Single known field name (not a group key)
        return_fields = [group]
    else:
        # Unknown group — do NOT default to the entire character block (that was a real bug).
        return_fields = SETUP_RANDOMIZER_FIELD_GROUPS.get(group, [])
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


# Single-token handles / nature-noun nicknames that belong in public_name, not player_name.
_PLAYER_NAME_NICKNAME_BLOCKLIST = frozenset(
    {
        "ash",
        "river",
        "patch",
        "vellum",
        "thorn",
        "spark",
        "shadow",
        "ghost",
        "fox",
        "wolf",
        "raven",
        "crow",
        "blade",
        "storm",
        "ember",
        "cinder",
        "northlight",
        "second bell",
        "wanderer",
        "stranger",
        "traveler",
        "traveller",
        "drifter",
        "nameless",
        "hero",
        "protagonist",
        "player",
        "mc",
    }
)


def _is_nickname_style_player_name(name: str) -> bool:
    """True for handles, epithets, compound shell-nicknames — not a real personal name."""
    raw = re.sub(r"\s+", " ", str(name or "").strip())
    if not raw:
        return True
    low = raw.lower()
    if low in _PLAYER_NAME_NICKNAME_BLOCKLIST:
        return True
    # "the Red", "of Kiln Street", title-style
    if re.match(r"^(the|of)\s+", low):
        return True
    # Quoted handles / code-like
    if raw.startswith('"') or raw.startswith("'") or re.fullmatch(r"[A-Za-z]{1,3}\d+", raw):
        return True
    # Compound shell nicknames: Ashwalker, Reedwick, Mossgate (nature+job/place stem)
    if re.fullmatch(
        r"[A-Za-z]+(?:walker|wick|well|bin|line|post|cut|mark|field|row|gate|path|coil|hook|rest|lane|drift|watch|keep)",
        raw,
        re.I,
    ):
        return True
    # Single evocative noun without a capital surname pattern (Patch, River) already blocked;
    # multi-word with only lowercase is not a proper name
    words = raw.split()
    if len(words) == 1 and len(words[0]) <= 4 and words[0].lower() in _PLAYER_NAME_NICKNAME_BLOCKLIST:
        return True
    return False


# Stock starter kits the 8B model welds into every isekai roll.
_STARTER_STOCK_MARKERS = (
    "rusted wrench",
    "copper coins",
    "worn satchel",
    "rain-slicked hoodie",
    "scuffed sneakers",
    "half-eaten bento",
    "faded id badge",
)


def _diversify_starter_equipment(value: Any) -> str:
    """
    Break the set-in-stone isekai pocket kit (wrench + copper coins + satchel + hoodie…).
    If the roll is a stock clone, replace with a random varied fallback.
    """
    raw = str(value or "").strip()
    if isinstance(value, list):
        raw = ", ".join(str(x).strip() for x in value if str(x or "").strip())
    # Flatten list-as-string junk
    low = raw.lower()
    stock_hits = sum(1 for m in _STARTER_STOCK_MARKERS if m in low)
    # Always-on coins + wrench is the worst clone
    if stock_hits >= 3 or ("wrench" in low and "copper" in low and "satchel" in low):
        try:
            from app.setup_composer import pick_starter_kit_seed

            return pick_starter_kit_seed(modern_arrival=True)[:500]
        except Exception:
            pool = list(SETUP_RANDOMIZER_FALLBACKS.get("starter_equipment") or [])
            random.shuffle(pool)
            for cand in pool:
                cl = str(cand).lower()
                if sum(1 for m in _STARTER_STOCK_MARKERS if m in cl) < 2:
                    return str(cand)[:500]
            return "cracked phone, house keys, light jacket, transit card, half-empty water bottle"
    # Soft-remove overused copper coins when the kit already has 4+ items
    parts = [p.strip() for p in re.split(r"[,;]+", raw) if p.strip()]
    if len(parts) >= 4:
        parts = [p for p in parts if not re.fullmatch(r"(a\s+)?(few\s+)?copper coins?", p, flags=re.I)]
    # Cap duplicate tool spam
    seen: set[str] = set()
    cleaned: list[str] = []
    for p in parts:
        key = re.sub(r"\s+", " ", p.lower())
        # Collapse wrench variants
        if "wrench" in key or "spanner" in key:
            key_stem = "wrench"
        elif "copper coin" in key:
            key_stem = "coins"
        else:
            key_stem = key
        if key_stem in seen:
            continue
        seen.add(key_stem)
        cleaned.append(p)
    return ", ".join(cleaned)[:500] if cleaned else raw[:500]


def _sanitize_player_name(value: Any, *, forbidden: str = "") -> str:
    """
    player_name = personal/legal name NPCs would put on a record.
    Nicknames, street handles, and epithets belong in player_public_name / player_title.
    """
    name = re.sub(r"\s+", " ", str(value or "").strip())[:80]
    forbid = re.sub(r"\s+", " ", str(forbidden or "").strip()).lower()
    if name and not _is_nickname_style_player_name(name) and name.lower() != forbid:
        # Prefer Title Case for display (keep short particles if any)
        parts = []
        for w in name.split():
            if w.lower() in {"de", "del", "van", "von", "of", "da", "di"}:
                parts.append(w.lower())
            else:
                parts.append(w[:1].upper() + w[1:] if w else w)
        return " ".join(parts)[:80]
    pool = list(SETUP_RANDOMIZER_FALLBACKS.get("player_name") or ["Mara Ellison"])
    random.shuffle(pool)
    for candidate in pool:
        c = str(candidate).strip()
        if c.lower() != forbid and not _is_nickname_style_player_name(c):
            return c[:80]
    return "Mara Ellison"


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
    if field == "player_name":
        forbid = str(current_setup.get("player_name") or "")
        values = list(SETUP_RANDOMIZER_FALLBACKS.get("player_name") or [])
        random.shuffle(values)
        for value in values:
            cleaned = _sanitize_player_name(value, forbidden=forbid)
            if cleaned.lower() != forbid.strip().lower():
                return cleaned
        return _sanitize_player_name("", forbidden=forbid)
    if field == "start_location":
        # SETUP_RANDOMIZER_FALLBACKS["start_location"] is one flat fantasy-leaning
        # list, so the LLM-unavailable path handed a space opera "Mosswake Gate"
        # or "Sect Outer Court Gate". Draw from this world's own theme bank
        # instead -- the same picker the normal path uses.
        try:
            from app.setup_composer import pick_isekai_arrival_location

            return pick_isekai_arrival_location(
                world_style=str(current_setup.get("world_style") or ""),
                genre=str(current_setup.get("world_style") or ""),
                idea=str(current_setup.get("custom_style") or ""),
                session_theme=(
                    current_setup.get("session_theme")
                    if isinstance(current_setup.get("session_theme"), dict)
                    else None
                ),
            )
        except Exception:
            pass
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


# Near-duplicate ability cross-check (batch + vs existing).
ABILITY_DEDUPE_MAX_ROUNDS = 4
ABILITY_NEAR_DUP_THRESHOLD = 0.45

# Fiction synonym clusters (shared cluster ⇒ near-dup signal).
_ABILITY_NAME_SYNONYM_CLUSTERS: tuple[frozenset[str], ...] = (
    frozenset({"veil", "shroud", "cloak", "mantle", "curtain", "cover", "mask"}),
    frozenset({"echo", "mimic", "copy", "recall", "resound", "reverberate"}),
    frozenset({"ward", "barrier", "shield", "aegis", "bulwark", "guard"}),
    frozenset({"bolt", "blast", "strike", "slash", "shot", "lance"}),
    frozenset({"whisper", "murmur", "listen", "hear", "eavesdrop"}),
    frozenset({"mend", "heal", "salve", "knit", "restore"}),
    frozenset({"summon", "call", "conjure", "manifest", "spawn"}),
    frozenset({"boost", "enhance", "overclock", "empower", "amplify", "synergy"}),
)

_ABILITY_STOPWORDS = frozenset(
    """
    a an the and or but if to of in on at by for with from as is are was were be been being
    you your yours they their them he she it its this that these those can may might will
    would should could into onto over under after before while when where which who whom
    not no nor only just also more most less least very into across through during
    ability power skill effect use used using once per day hour scene rest week rank
    level xp small brief briefly minor slightly short long temporary
    """.split()
)

# Coarse mechanical lanes — shared lane + high token overlap ⇒ near-duplicate.
_ABILITY_EFFECT_LANES: dict[str, tuple[str, ...]] = {
    "summon": ("summon", "construct", "create a", "spawn", "call forth", "manifest a creature"),
    "shield": ("shield", "barrier", "deflect", "block attack", "ward", "aegis", "protect"),
    "heal": ("heal", "mend", "restore health", "regenerat", "salve", "cure wound"),
    "sense": ("sense", "detect", "perceive", "read emotion", "read intent", "scry", "hear whisper"),
    "distract": ("distract", "mimic", "echo sound", "noise", "disrupt focus", "feint"),
    "stealth": ("veil", "obscure", "hide", "invisible", "cloak", "shadow", "silent"),
    "time": ("time", "chrono", "rewind", "duplicate of yourself", "past action", "echo of yourself"),
    "buff": ("boost", "enhance", "synergy", "overclock", "empower", "amplify", "strengthen"),
    "strike": ("strike", "slash", "blast", "damage", "kill", "sever", "impale", "burn"),
    "control": ("control", "bind", "root", "stun", "paralyze", "dominate", "charm", "fear"),
    "craft": ("craft", "repair", "forge", "tool", "build", "solder", "stitch"),
    "social": ("persuade", "lie", "bargain", "intimidate", "face", "reputation", "rumor"),
}


def _ability_content_tokens(ability: dict[str, Any] | None) -> set[str]:
    if not isinstance(ability, dict):
        return set()
    blob = " ".join(
        [
            str(ability.get("name") or ""),
            str(ability.get("description") or ""),
            str(ability.get("power_type") or ""),
        ]
    ).lower()
    words = re.findall(r"[a-z][a-z0-9'-]{2,}", blob)
    return {w for w in words if w not in _ABILITY_STOPWORDS and len(w) > 2}


def _ability_effect_lanes(ability: dict[str, Any] | None) -> set[str]:
    if not isinstance(ability, dict):
        return set()
    blob = f"{ability.get('name') or ''} {ability.get('description') or ''}".lower()
    hits: set[str] = set()
    for lane, markers in _ABILITY_EFFECT_LANES.items():
        if any(m in blob for m in markers):
            hits.add(lane)
    return hits


def _ability_synonym_cluster_hits(text: str) -> set[int]:
    words = set(re.findall(r"[a-z][a-z0-9'-]{2,}", (text or "").lower()))
    hits: set[int] = set()
    for idx, cluster in enumerate(_ABILITY_NAME_SYNONYM_CLUSTERS):
        if words & cluster:
            hits.add(idx)
    return hits


def ability_similarity_score(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float:
    """0..1 similarity. High means near-duplicate fiction/mechanics."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return 0.0
    na = re.sub(r"\s+", " ", str(a.get("name") or "").strip().lower())
    nb = re.sub(r"\s+", " ", str(b.get("name") or "").strip().lower())
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Substring / shared multiword name stem
    if na in nb or nb in na:
        name_score = 0.92
    else:
        ta = set(na.replace("-", " ").split())
        tb = set(nb.replace("-", " ").split())
        if ta and tb:
            name_score = len(ta & tb) / max(1, len(ta | tb))
        else:
            name_score = 0.0
        # Soft stem: first token match (Veil of X / Veil of Y)
        if ta and tb and next(iter(sorted(ta))) == next(iter(sorted(tb))):
            name_score = max(name_score, 0.55)
        # Synonym clusters in names (Veil vs Shroud)
        ca = _ability_synonym_cluster_hits(na)
        cb = _ability_synonym_cluster_hits(nb)
        if ca and cb and ca & cb:
            name_score = max(name_score, 0.72)

    da = re.sub(r"\s+", " ", str(a.get("description") or "").strip().lower())[:400]
    db = re.sub(r"\s+", " ", str(b.get("description") or "").strip().lower())[:400]
    if da and db and da == db:
        return 1.0
    if da and db and (da[:60] == db[:60] and len(da) > 40):
        desc_prefix = 0.85
    else:
        desc_prefix = 0.0

    tok_a = _ability_content_tokens(a)
    tok_b = _ability_content_tokens(b)
    if tok_a and tok_b:
        jacc = len(tok_a & tok_b) / max(1, len(tok_a | tok_b))
    else:
        jacc = 0.0

    # Expand jaccard with synonym clusters present in full text
    full_a = f"{na} {da}"
    full_b = f"{nb} {db}"
    syn_a = _ability_synonym_cluster_hits(full_a)
    syn_b = _ability_synonym_cluster_hits(full_b)
    syn_overlap = 0.0
    if syn_a and syn_b:
        syn_overlap = len(syn_a & syn_b) / max(1, len(syn_a | syn_b))

    lanes_a = _ability_effect_lanes(a)
    lanes_b = _ability_effect_lanes(b)
    if lanes_a and lanes_b:
        lane_overlap = len(lanes_a & lanes_b) / max(1, len(lanes_a | lanes_b))
    else:
        lane_overlap = 0.0

    # Weighted blend
    score = (
        0.30 * name_score
        + 0.24 * jacc
        + 0.24 * lane_overlap
        + 0.12 * syn_overlap
        + 0.10 * desc_prefix
    )
    # Shared stealth/shield/etc + overlapping fiction words
    shared_lanes = lanes_a & lanes_b
    if shared_lanes and (jacc >= 0.18 or syn_overlap >= 0.34 or name_score >= 0.5):
        score = max(score, 0.50)
    # Same lanes exactly
    if lanes_a and lanes_a == lanes_b and (jacc >= 0.2 or syn_overlap >= 0.3):
        score = max(score, 0.58)
    if name_score >= 0.7 and (jacc >= 0.18 or syn_overlap >= 0.3):
        score = max(score, 0.62)
    # Synonym names in same mechanical story (veil/shroud hide/obscure)
    if syn_overlap >= 0.5 and (lane_overlap >= 0.34 or jacc >= 0.15):
        score = max(score, 0.56)
    return round(min(1.0, score), 3)


def find_near_duplicate_pairs(
    abilities: list[Any],
    *,
    existing: list[Any] | None = None,
    threshold: float = ABILITY_NEAR_DUP_THRESHOLD,
) -> list[dict[str, Any]]:
    """Return near-dup pairs: {i, j, score, weaker_index, stronger_index, against_existing?}."""
    items = [a for a in abilities if isinstance(a, dict)]
    pairs: list[dict[str, Any]] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            sc = ability_similarity_score(items[i], items[j])
            if sc >= threshold:
                weaker = pick_weaker_ability_index(items, i, j)
                stronger = j if weaker == i else i
                pairs.append(
                    {
                        "i": i,
                        "j": j,
                        "score": sc,
                        "weaker_index": weaker,
                        "stronger_index": stronger,
                        "against_existing": False,
                        "names": [
                            str(items[i].get("name") or ""),
                            str(items[j].get("name") or ""),
                        ],
                    }
                )
    # Also vs existing form abilities
    for ei, ex in enumerate(existing or []):
        if not isinstance(ex, dict):
            continue
        for i, ab in enumerate(items):
            sc = ability_similarity_score(ab, ex)
            if sc >= threshold:
                pairs.append(
                    {
                        "i": i,
                        "j": None,
                        "existing_index": ei,
                        "score": sc,
                        "weaker_index": i,  # always rework the new one
                        "stronger_index": None,
                        "against_existing": True,
                        "names": [str(ab.get("name") or ""), str(ex.get("name") or "")],
                    }
                )
    # Highest similarity first
    pairs.sort(key=lambda p: float(p.get("score") or 0), reverse=True)
    return pairs


def pick_weaker_ability_index(items: list[dict[str, Any]], i: int, j: int) -> int:
    """Prefer reworking the thinner / milder / lower-quality entry."""
    a, b = items[i], items[j]
    ra = evaluate_ability_quality(a, require_strong_math=False, one_skillish=False)
    rb = evaluate_ability_quality(b, require_strong_math=False, one_skillish=False)
    sa, sb = int(ra.get("score") or 0), int(rb.get("score") or 0)
    if sa != sb:
        return i if sa < sb else j
    la = len(str(a.get("description") or ""))
    lb = len(str(b.get("description") or ""))
    if la != lb:
        return i if la < lb else j
    # Mild utility loses to a more distinct combat fantasy when scores tie
    strength_rank = {"mild": 0, "moderate": 1, "strong": 2}
    sta = strength_rank.get(estimate_ability_opening_strength(a), 1)
    stb = strength_rank.get(estimate_ability_opening_strength(b), 1)
    if sta != stb:
        return i if sta < stb else j
    return j  # default: rework the later card


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


def _ability_count_bounds(field_context: dict[str, Any]) -> tuple[int, int]:
    """Shared 1–4 ability count range for Simple + Advanced randomize."""
    try:
        count_min = int(field_context.get("count_min") if field_context.get("count_min") is not None else 1)
    except (TypeError, ValueError):
        count_min = 1
    try:
        count_max = int(field_context.get("count_max") if field_context.get("count_max") is not None else 4)
    except (TypeError, ValueError):
        count_max = 4
    count_min = max(1, min(4, count_min))
    count_max = max(1, min(4, count_max))
    if count_min > count_max:
        count_min, count_max = count_max, count_min
    return count_min, count_max


def _roll_ability_count(field_context: dict[str, Any], *, one_skillish: bool = False) -> int:
    """
    Ability slot count for this randomize.

    - Quantity locked → fixed slot count (existing cards or min).
    - Otherwise pure RNG: uniform random integer in [count_min, count_max].
    - If the client already rolled (`count_rolled` + `requested_count`/`target_count`), honor that roll.
    """
    _ = one_skillish  # kept for call-site compat; count is no longer biased by OP-MC intent
    quantity_locked = bool(field_context.get("quantity_locked"))
    count_min, count_max = _ability_count_bounds(field_context)
    try:
        requested_count = max(
            0,
            min(
                4,
                int(
                    field_context.get("target_count")
                    if field_context.get("target_count") is not None
                    else field_context.get("requested_count")
                    if field_context.get("requested_count") is not None
                    else 0
                ),
            ),
        )
    except (TypeError, ValueError):
        requested_count = 0

    if quantity_locked:
        if requested_count:
            return max(1, min(4, requested_count))
        try:
            existing = max(0, min(4, int(field_context.get("existing_count") or 0)))
        except (TypeError, ValueError):
            existing = 0
        if existing:
            return max(1, existing)
        return count_min

    # Client already rolled once for this request — do not re-roll.
    if field_context.get("count_rolled") and requested_count:
        return max(count_min, min(count_max, requested_count))

    # Pure RNG between the user's min and max (inclusive).
    return random.randint(count_min, count_max)


def _enforce_ability_count(
    abilities: list[Any] | None,
    target: int,
    *,
    current_setup: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Slice or pad the ability list to exactly `target` entries."""
    target = max(0, min(4, int(target or 0)))
    clean = [dict(a) for a in (abilities or []) if isinstance(a, dict)]
    if target <= 0:
        return []
    if len(clean) > target:
        return clean[:target]
    if len(clean) < target:
        # Pad from fallback seeds so the rolled count is honored even if the model shorted
        try:
            setup = dict(current_setup or {})
            fc = setup.get("_field_context") if isinstance(setup.get("_field_context"), dict) else {}
            fc = dict(fc)
            fc["target_count"] = target
            fc["requested_count"] = target
            fc["count_rolled"] = True
            fc["quantity_locked"] = True  # force exact fill from roll
            setup["_field_context"] = fc
            pad = _fallback_special_abilities(setup)
            names = {str(a.get("name") or "").lower() for a in clean}
            for ab in pad:
                if len(clean) >= target:
                    break
                if not isinstance(ab, dict):
                    continue
                n = str(ab.get("name") or "").lower()
                if n and n in names:
                    continue
                clean.append(dict(ab))
                names.add(n)
        except Exception:
            pass
        # Last resort: pad with a distinct seed-domain ability (never "Power (2)" / "Name 52")
        while len(clean) < target:
            try:
                pad_one = _local_remake_ability(
                    forbidden_names=names,
                    origin=str((current_setup or {}).get("special_ability_origin") or "both"),
                    world_style=str((current_setup or {}).get("world_style") or ""),
                )
                n = sanitize_ability_name(pad_one.get("name")) or "Quiet Craft"
                pad_one["name"] = n
                if n.lower() in names:
                    n = _unique_ability_display_name(n, names, salt=f"pad|{len(clean)}")
                    pad_one["name"] = n
                clean.append(pad_one)
                names.add(n.lower())
            except Exception:
                # Absolute last resort: word-only unique name, not a number
                extra = dict(clean[-1]) if clean else {"name": "Quiet Craft", "description": "A thin practical edge."}
                extra = dict(extra)
                extra["name"] = _unique_ability_display_name(
                    str(extra.get("name") or "Quiet Craft"),
                    names,
                    salt=f"pad_fallback|{len(clean)}",
                )
                clean.append(extra)
                names.add(str(extra.get("name") or "").lower())
                if len(clean) >= target:
                    break
    return clean[:target]


def _fallback_special_abilities(current_setup: dict[str, Any]) -> list[dict[str, Any]]:
    field_context = current_setup.get("_field_context") if isinstance(current_setup.get("_field_context"), dict) else {}
    # Origin UI removed — locks are per ability; default batch policy is "both".
    origin = str(
        field_context.get("ability_origin") or current_setup.get("special_ability_origin") or "both"
    ).strip().lower()
    if origin in {"none", "off", "no", ""}:
        origin = "both"
    # One-skill / near-useless intents → single seed ability when range allows
    intent = _resolve_setup_intent(current_setup)
    pf = intent.get("power_fantasy") if isinstance(intent.get("power_fantasy"), dict) else {}
    one_skillish = str(pf.get("growth") or "").lower() == "compounding" or str(pf.get("start_power") or "").lower() in {
        "near_useless",
        "weak",
    }
    count = _roll_ability_count(field_context, one_skillish=one_skillish)
    pool = list(SETUP_RANDOMIZER_ABILITY_FALLBACKS)
    random.shuffle(pool)
    # Avoid reusing whatever is already on the form when possible
    existing = current_setup.get("special_abilities") if isinstance(current_setup.get("special_abilities"), list) else []
    existing_fps = {_ability_fingerprint(a) for a in existing if isinstance(a, dict)}
    ordered = [a for a in pool if _ability_fingerprint(a) not in existing_fps] + [
        a for a in pool if _ability_fingerprint(a) in existing_fps
    ]
    # Inject fresh domain-driven seeds (quality-gate fallback after LLM denials).
    from app.setup_composer import player_facing_domain_description

    cost_options = [
        "A brief headache and ringing in the ears",
        "One point of fatigue until you rest or eat",
        "Numb fingers / shaky hands for a few minutes",
        "A nosebleed or iron taste if pushed twice in a row",
        "Drains a small personal focus (candle, salt, named tool) when used",
        "Leaves you socially flat — harder to charm for a short while",
    ]
    prereq_options = list(ABILITY_PREREQ_VARIETY_POOL)
    for _ in range(min(4, max(1, count + 1))):
        dom = pick_seed_skill_domain(
            avoid=[str(a.get("name") or "") for a in ordered if isinstance(a, dict)],
            world_style=str(current_setup.get("world_style") or ""),
            salt=f"fallback|{time.time_ns()}|{random.randint(1, 1_000_000)}",
        )
        ordered.insert(
            0,
            {
                "name": dom["name"],
                "description": player_facing_domain_description(dom),
                "locked": True,
                "prerequisites": random.choice(prereq_options),
                "cost": random.choice(cost_options),
                "growth_math": random.choice(GROWTH_MATH_SAMPLES),
                "power_type": "compounding",
                "_fallback_source": "seed_domain_pool",
            },
        )
    power_types = ["compounding", "passive", "linear", "soft_cap", "breakthrough", "flat", "item_bound"]
    abilities: list[dict[str, Any]] = []
    for index in range(count):
        ability = dict(ordered[index % len(ordered)])
        # Locks assigned after the full batch exists (see assign_ability_locks_after_creation).
        ability["locked"] = False
        ability["prerequisites"] = ""
        if one_skillish:
            if index == 0:
                ability["power_type"] = "compounding"
            else:
                ability["power_type"] = ability.get("power_type") if ability.get("power_type") == "passive" else "passive"
        if not ability.get("power_type"):
            ability["power_type"] = random.choice(power_types)
        if not str(ability.get("growth_math") or "").strip():
            ability["growth_math"] = random.choice(GROWTH_MATH_SAMPLES)
        elif one_skillish:
            # Always ensure OP-MC fallbacks carry concrete late-game math
            ability["growth_math"] = str(ability.get("growth_math") or random.choice(GROWTH_MATH_SAMPLES))[:800]
        abilities.append(ability)
    # Create → score power → roll how many locked → lock strongest + fair prereqs
    return assign_ability_locks_after_creation(abilities, origin=origin)


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


# Vague / unusable ability prose the quality gate rejects.
_ABILITY_VAGUE_DESC = re.compile(
    r"\b("
    r"mysterious power|unknown force|special ability|does something cool|"
    r"to be determined|tbd|as the dm decides|whatever feels right|"
    r"grows stronger somehow|vaguely powerful|ultimate power|"
    r"chosen one|destiny itself"
    r")\b",
    re.I,
)
# Design-meta that must never appear on a player-facing ability card.
_ABILITY_META_LEAK = re.compile(
    r"("
    r"compounds toward\s*:|"
    r"\b(?:advanced|simple)\s+tier\b|"
    r"\b(?:arcane|mundane|tool|weapon|support|summon|necro|hybrid|tech)\s+lane\b|"
    r"\bdesign tier\b|\bdesign lane\b|"
    r"when you try,\s*|"
    r"prompt_hint"
    r")",
    re.I,
)
_ABILITY_ACTION_HINT = re.compile(
    r"\b("
    r"can |may |when |once |briefly |slightly |touch|speak|hold|draw|strike|"
    r"sense|see|hear|smell|call|summon|heal|bind|cut|block|read|write|brew|"
    r"require|needs |with a |using |costs? |until |after |before |if |"
    r"generat|knock|blast|push|pull|create|release|fire|cast|channel|"
    r"shield|slash|dash|cloak|veil|wave|force|project|emit|throw|hurl"
    r")\b",
    re.I,
)
_ABILITY_FREE_GOD = re.compile(
    r"\b("
    r"unlimited|no limit|infinite|instantly win|auto[- ]?win|always succeed|"
    r"omnipotent|invincible|no cost ever|free forever"
    r")\b",
    re.I,
)
# Model collapse: every power costs "1 hour each day/dawn in [biome] to maintain".
_ABILITY_MAINTENANCE_HOUR_TEMPLATE = re.compile(
    r"\b("
    r"spend\s+\d+\s*hours?\s+each\s+(?:day|dawn|dusk|night|morning)|"
    r"must\s+spend\s+\d+\s*hours?\s+each\s+(?:day|dawn|dusk|night|morning)|"
    r"\d+\s*hours?\s+(?:each|every)\s+(?:day|dawn|dusk|night)\s+(?:in|near|at)\b|"
    r"to\s+maintain\s+this\s+ability|"
    r"maintain\s+this\s+(?:ability|power|gift)"
    r")\b",
    re.I,
)


def _cost_structure_fingerprint(text: str) -> str:
    """Normalize cost prose so copy-paste recharge/maintenance clones collide.

    Important: classify *before* stripping digits/punctuation. A prior bug lowercased
    then deleted 'N' placeholders, so "1 hour of meditation to recharge" never
    collapsed to one fingerprint — every ability could ship the same cost.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    low = re.sub(r"\s+", " ", raw.lower())

    # High-signal templates first (match original text shapes).
    if _ABILITY_MAINTENANCE_HOUR_TEMPLATE.search(raw):
        return "MAINTAIN_HOUR_ENV_DAILY"
    if re.search(r"\b\d+\s*hours?\b.*\b(meditat|recharge|recover)\b", low) or re.search(
        r"\b(meditat|recharge|recover)\b.*\b\d+\s*hours?\b", low
    ):
        # "Once per rank/day; 1 hour of meditation to recharge after use"
        if re.search(r"\bonce per (day|rank|scene|hour|use|rest|week)\b", low):
            return "ONCE_PER_X_PLUS_HOUR_MEDITATION_RECHARGE"
        return "HOUR_MEDITATION_RECHARGE"
    if re.search(r"\bhour of meditation\b", low) or re.search(r"\bmeditation to recharge\b", low):
        return "HOUR_MEDITATION_RECHARGE"
    if re.search(r"\bonce per day\b", low) and re.search(r"\bhour\b", low):
        return "ONCE_DAY_PLUS_HOUR"
    if re.search(r"\bonce per rank\b", low):
        if re.search(r"\b(breath\s*control|stamina\s*drain|\d+%\s*stamina)\b", low):
            return "ONCE_PER_RANK_BREATH_STAMINA"
        if re.search(r"\b\d+[-–]?\s*(minute|second)s?\s+cooldown\b", low):
            return "ONCE_PER_RANK_PLUS_SHORT_CD"
        return "ONCE_PER_RANK"
    if re.search(r"\b\d+\s*(minute|second)s?\s+of\s+breath\s*control\b", low) or re.search(
        r"\bbreath\s*control\b.*\b\d+%\s*stamina", low
    ):
        return "BREATH_CONTROL_STAMINA_DRAIN"
    if re.search(r"\bonce per (day|scene|encounter|rest|week|hour)\b", low) and len(low) < 48:
        return "ONCE_PER_" + re.search(r"\bonce per (day|scene|encounter|rest|week|hour)\b", low).group(1).upper()

    # Drop biome/place nouns so only the cost *shape* remains.
    shaped = re.sub(
        r"\b(with|in|near|at|under|inside|within)\s+[a-z0-9 ,/+\-]{3,80}?(?=\s+to\s+maintain|\s*$|[.])",
        " in ENV",
        low,
    )
    shaped = re.sub(r"\b\d+\b", "n", shaped)
    shaped = re.sub(
        r"\b(natural light|heavy ash|smoke|dust|water|swamp|forest|mountain|cave|city|desert|snow|blood|salt|fire)\b",
        "env",
        shaped,
    )
    shaped = re.sub(r"[^a-z ]+", " ", shaped)
    shaped = re.sub(r"\s+", " ", shaped).strip()
    if re.search(r"\bn hour\b.*\b(recharge|recover|meditat)", shaped):
        return "HOUR_MEDITATION_RECHARGE"
    return shaped[:90]
_VALID_POWER_TYPES = frozenset(
    {
        "compounding",
        "passive",
        "linear",
        "soft_cap",
        "breakthrough",
        "flat",
        "item_bound",
    }
)
# Max quality-denied rolls before seed-pool fallback (initial + retries).
ABILITY_QUALITY_MAX_ATTEMPTS = 3
BACKSTORY_QUALITY_MAX_ATTEMPTS = 3

# Duration / recharge units → minutes for cross-field fact-check.
_TIME_UNIT_MINUTES = {
    "sec": 1 / 60,
    "secs": 1 / 60,
    "second": 1 / 60,
    "seconds": 1 / 60,
    "min": 1.0,
    "mins": 1.0,
    "minute": 1.0,
    "minutes": 1.0,
    "hr": 60.0,
    "hrs": 60.0,
    "hour": 60.0,
    "hours": 60.0,
    "day": 24 * 60.0,
    "days": 24 * 60.0,
    "week": 7 * 24 * 60.0,
    "weeks": 7 * 24 * 60.0,
}


def _parse_time_to_minutes(num: str | float, unit: str) -> float | None:
    try:
        n = float(num)
    except (TypeError, ValueError):
        return None
    u = (unit or "").strip().lower()
    mult = _TIME_UNIT_MINUTES.get(u)
    if mult is None:
        return None
    return n * mult


def extract_ability_timing_facts(text: str) -> dict[str, Any]:
    """Pull use frequency, recharge, and duration numbers from free text."""
    raw = str(text or "")
    low = raw.lower()
    facts: dict[str, Any] = {
        "use_period_minutes": None,  # minimum gap between uses implied by "once per X"
        "uses_per_period": None,
        "recharge_minutes": None,
        "duration_minutes": None,
        "uses_per_day": None,
        "once_per_rank": False,
        "stamina_pct": None,
        "has_usage_limit_language": False,
        "raw_hits": [],
    }
    # once per day / scene / rest / hour / long rest / rank
    m = re.search(
        r"\b(?:once|1\s*time|one\s+time)\s+per\s+(day|daily|hour|hr|scene|encounter|rest|long\s+rest|short\s+rest|week|rank|level|use)\b",
        low,
    )
    if m:
        period = m.group(1).replace(" ", "_")
        period_map = {
            "day": 24 * 60.0,
            "daily": 24 * 60.0,
            "hour": 60.0,
            "hr": 60.0,
            "scene": 30.0,  # soft tabletop scene ≈ half hour for compare
            "encounter": 15.0,
            "rest": 8 * 60.0,
            "long_rest": 8 * 60.0,
            "short_rest": 60.0,
            "week": 7 * 24 * 60.0,
            # Rank/level caps are not pure time; mark separately (no period minutes)
            "rank": None,
            "level": None,
            "use": None,
        }
        if period in {"rank", "level"}:
            facts["once_per_rank"] = True
            facts["has_usage_limit_language"] = True
            facts["raw_hits"].append("once_per_rank")
        elif period == "use":
            facts["has_usage_limit_language"] = True
            facts["raw_hits"].append("once_per_use")
        else:
            facts["use_period_minutes"] = period_map.get(period)
            facts["uses_per_period"] = 1
            if period in {"day", "daily"}:
                facts["uses_per_day"] = 1
            facts["has_usage_limit_language"] = True
            facts["raw_hits"].append(f"once_per_{period}")

    m = re.search(r"\b(\d+)\s*times?\s+per\s+(day|hour|scene|encounter|rank)\b", low)
    if m:
        n = int(m.group(1))
        period = m.group(2)
        facts["uses_per_period"] = n
        facts["has_usage_limit_language"] = True
        if period == "day":
            facts["uses_per_day"] = n
            facts["use_period_minutes"] = (24 * 60.0) / max(1, n)
        elif period == "hour":
            facts["use_period_minutes"] = 60.0 / max(1, n)
        elif period == "rank":
            facts["once_per_rank"] = True
        facts["raw_hits"].append(f"{n}_per_{period}")

    # daily / each day without "once"
    if facts["uses_per_day"] is None and re.search(r"\b(once\s+a\s+day|daily\s+use|per\s+day)\b", low):
        facts["uses_per_day"] = 1
        facts["use_period_minutes"] = facts["use_period_minutes"] or 24 * 60.0
        facts["has_usage_limit_language"] = True
        facts["raw_hits"].append("daily_use")

    # "with a 1-minute cooldown after each use" / "1-minute cooldown"
    for m in re.finditer(
        r"\b(\d+(?:\.\d+)?)\s*[-–]?\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)\s+"
        r"(?:cooldown|cool\s*down)\b",
        low,
    ):
        unit = m.group(2)
        unit_norm = {
            "s": "seconds",
            "sec": "seconds",
            "secs": "seconds",
            "m": "minutes",
            "min": "minutes",
            "mins": "minutes",
            "h": "hours",
            "hr": "hours",
            "hrs": "hours",
        }.get(unit, unit)
        mins = _parse_time_to_minutes(m.group(1), unit_norm)
        if mins is not None:
            facts["recharge_minutes"] = mins
            facts["has_usage_limit_language"] = True
            facts["raw_hits"].append(f"cooldown_{mins}m")
            break
    if facts["recharge_minutes"] is None:
        for m in re.finditer(
            r"\b(?:a\s+)?(\d+(?:\.\d+)?)\s*[-–]?\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s+"
            r"cooldown\s+after\b",
            low,
        ):
            mins = _parse_time_to_minutes(m.group(1), m.group(2))
            if mins is not None:
                facts["recharge_minutes"] = mins
                facts["has_usage_limit_language"] = True
                facts["raw_hits"].append(f"cooldown_after_{mins}m")
                break

    # recharge / recover / cooldown: "1 hour of meditation to recharge"
    if facts["recharge_minutes"] is None:
        for m in re.finditer(
            r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b"
            r"[^.\n]{0,40}\b(recharge|recover|recovery|cooldown|cool\s*down|rest\s+to|to\s+recharge|to\s+recover|before\s+(?:you\s+)?(?:can\s+)?use\s+again)\b",
            low,
        ):
            mins = _parse_time_to_minutes(m.group(1), m.group(2))
            if mins is not None:
                facts["recharge_minutes"] = mins
                facts["has_usage_limit_language"] = True
                facts["raw_hits"].append(f"recharge_{mins}m")
                break
    if facts["recharge_minutes"] is None:
        for m in re.finditer(
            r"\b(recharge|recover|recovery|cooldown|cool\s*down)\b[^.\n]{0,40}"
            r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?)\b",
            low,
        ):
            mins = _parse_time_to_minutes(m.group(2), m.group(3))
            if mins is not None:
                facts["recharge_minutes"] = mins
                facts["has_usage_limit_language"] = True
                facts["raw_hits"].append(f"recharge_{mins}m")
                break
    # "1 hour of meditation" / "1 minute of breath control" (cost fields often omit "recharge")
    if facts["recharge_minutes"] is None and re.search(
        r"\b(meditat|breath\s*control|breathing|rest|sleep|pray|ritual|channel)\b", low
    ):
        m = re.search(
            r"\b(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b",
            low,
        )
        if m:
            mins = _parse_time_to_minutes(m.group(1), m.group(2))
            if mins is not None and mins >= 1:
                facts["recharge_minutes"] = mins
                facts["has_usage_limit_language"] = True
                facts["raw_hits"].append(f"implied_recharge_{mins}m")

    # Stamina / energy percent drains (cost side)
    m = re.search(r"\b(\d{1,3})\s*%\s*(stamina|energy|fatigue)\b", low)
    if m:
        facts["stamina_pct"] = max(0, min(100, int(m.group(1))))
        facts["raw_hits"].append(f"stamina_pct_{facts['stamina_pct']}")
    elif re.search(r"\b(stamina|energy)\s+drain\b", low):
        facts["stamina_pct"] = facts["stamina_pct"] or 10
        facts["raw_hits"].append("stamina_drain")

    # duration: lasts for 10 seconds
    m = re.search(
        r"\b(?:lasts?(?:\s+for)?|duration(?:\s+of)?|for\s+up\s+to)\s+(\d+(?:\.\d+)?)\s*"
        r"(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b",
        low,
    )
    if m:
        mins = _parse_time_to_minutes(m.group(1), m.group(2))
        if mins is not None:
            facts["duration_minutes"] = mins
            facts["raw_hits"].append(f"duration_{mins}m")
    # math-side max duration 25s
    if facts["duration_minutes"] is None:
        m = re.search(r"\bmax\s+duration\s+(\d+(?:\.\d+)?)\s*(s|sec|secs|seconds?|m|min|minutes?|h|hours?)?\b", low)
        if m:
            unit = m.group(2) or "s"
            unit_map = {"s": "seconds", "sec": "seconds", "secs": "seconds", "m": "minutes", "min": "minutes", "h": "hours"}
            u = unit_map.get(unit, unit)
            mins = _parse_time_to_minutes(m.group(1), u if u.endswith("s") or u in _TIME_UNIT_MINUTES else "seconds")
            if mins is not None:
                facts["duration_minutes"] = mins
                facts["raw_hits"].append(f"max_duration_{mins}m")

    if re.search(
        r"\b(once\s+per|times?\s+per|cooldown|cool\s*down|can\s+be\s+used\s+once|recharge\s+after)\b",
        low,
    ):
        facts["has_usage_limit_language"] = True

    return facts


def ability_cross_field_fact_check(ability: dict[str, Any]) -> dict[str, Any]:
    """Fact-check description vs cost vs growth_math for timing contradictions.

    Classic fail: description 'once per day' + cost '1 hour meditation to recharge'.
    """
    if not isinstance(ability, dict):
        return {"ok": False, "hard_fail": ["not_an_object"], "soft": [], "details": {}}

    desc = str(ability.get("description") or "")
    cost = str(ability.get("cost") or "")
    math_text = str(ability.get("growth_math") or "")
    prereq = str(ability.get("prerequisites") or "")

    d_facts = extract_ability_timing_facts(desc)
    c_facts = extract_ability_timing_facts(cost)
    m_facts = extract_ability_timing_facts(math_text)
    p_facts = extract_ability_timing_facts(prereq)

    hard: list[str] = []
    soft: list[str] = []
    details: dict[str, Any] = {
        "description": d_facts,
        "cost": c_facts,
        "growth_math": m_facts,
        "prerequisites": p_facts,
    }

    def _period(facts: dict[str, Any]) -> float | None:
        if facts.get("use_period_minutes") is not None:
            return float(facts["use_period_minutes"])
        if facts.get("uses_per_day") is not None:
            return (24 * 60.0) / max(1, int(facts["uses_per_day"]))
        return None

    # Description once/day vs cost short recharge (e.g. 1 hour)
    d_period = _period(d_facts)
    c_recharge = c_facts.get("recharge_minutes")
    c_period = _period(c_facts)
    if d_period is not None and c_recharge is not None:
        # Conflict if cost recharge is meaningfully shorter than stated use period
        # and cost does not also state the same period.
        if c_period is None and c_recharge < d_period * 0.5:
            hard.append("use_limit_vs_recharge_mismatch")
        elif c_period is not None and abs(c_period - d_period) / max(d_period, 1) > 0.35:
            # once per day in desc, once per hour in cost
            hard.append("use_period_conflict_desc_vs_cost")

    # Two different use periods stated in desc vs cost
    if d_period is not None and c_period is not None:
        ratio = max(d_period, c_period) / max(min(d_period, c_period), 1e-6)
        if ratio >= 2.0:
            hard.append("conflicting_use_frequency_desc_vs_cost")

    # Duration contradiction: desc 10s vs math max duration 25s is OK (growth).
    # But desc "lasts 1 hour" vs math "max duration 10s" is a problem at F rank.
    d_dur = d_facts.get("duration_minutes")
    m_dur = m_facts.get("duration_minutes")
    if d_dur is not None and m_dur is not None:
        # If math max is far below starting description duration
        if m_dur < d_dur * 0.5 and d_dur >= (10 / 60):  # ignore tiny noise
            soft.append("duration_desc_exceeds_math_max")
        # If description duration wildly longer than cost recharge (effect outlasts recharge)
        if c_recharge is not None and d_dur > c_recharge * 1.05:
            hard.append("duration_longer_than_recharge")

    # Cost says once/day but description says once/hour (or vice versa) already handled.
    # Description packs frequency into effect while cost packs different frequency.
    if d_facts.get("uses_per_day") and c_facts.get("uses_per_day"):
        if int(d_facts["uses_per_day"]) != int(c_facts["uses_per_day"]):
            hard.append("uses_per_day_conflict")

    # Recharge stated in both desc and cost with different values
    d_rech = d_facts.get("recharge_minutes")
    if d_rech is not None and c_recharge is not None:
        ratio = max(d_rech, c_recharge) / max(min(d_rech, c_recharge), 1e-6)
        if ratio >= 1.5:
            hard.append("recharge_conflict_desc_vs_cost")

    # Description embeds use-frequency / cooldown while cost carries a different strain story.
    # Classic fail: desc "once per rank + 1-minute cooldown" vs cost "breath control; 10% stamina".
    if d_facts.get("has_usage_limit_language") and (
        d_facts.get("once_per_rank")
        or d_facts.get("use_period_minutes") is not None
        or d_facts.get("recharge_minutes") is not None
        or d_facts.get("uses_per_day") is not None
    ):
        # Always prefer limits in cost only — hard fail so repair runs.
        hard.append("usage_limits_embedded_in_description")

    # once per rank in desc but cost never mentions rank/limit
    if d_facts.get("once_per_rank") and not c_facts.get("once_per_rank"):
        if not re.search(r"\bonce per rank\b", cost, re.I):
            hard.append("once_per_rank_missing_from_cost")

    # Desc cooldown vs cost breath-control recharge mismatch already partially covered;
    # if desc has short CD and cost has different recharge, flag when both present and diverge.
    if d_rech is not None and c_recharge is not None and abs(float(d_rech) - float(c_recharge)) >= 0.5:
        if "recharge_conflict_desc_vs_cost" not in hard:
            # Same axis, different numbers (e.g. 1m CD vs 1m breath is OK if equal)
            ratio = max(d_rech, c_recharge) / max(min(d_rech, c_recharge), 1e-6)
            if ratio >= 1.5:
                hard.append("recharge_conflict_desc_vs_cost")

    return {
        "ok": not hard,
        "hard_fail": hard,
        "soft": soft,
        "details": details,
    }


# Fair unlock lines — rotated so multi-ability batches are not clones.
ABILITY_PREREQ_VARIETY_POOL: tuple[str, ...] = (
    "Unlocks after deliberate practice under real risk — not safe drills alone.",
    "Unlocks when a mentor names the limit once, then leaves you to hold it alone.",
    "Unlocks after a costly field discovery tied to this aptitude (tool, scar, or debt).",
    "Unlocks after you fail a related check publicly and recover without quitting.",
    "Unlocks after a night of focused practice with no audience and no shortcuts.",
    "Unlocks when a rival or ally forces the half-formed version into play once.",
    "Unlocks after studying a worn manual, mural, or scrap that matches the domain.",
    "Unlocks after paying a real price (time, favor, or coin) to learn the first form.",
    "Unlocks after surviving a setback that would have been easier with this already known.",
    "Unlocks after you teach someone the outline — and realize what you still lack.",
    "Unlocks at a marked place of practice (range, shrine, yard, workshop) after repeated visits.",
    "Unlocks after a witnessed oath or contract about using this carefully.",
    "Unlocks after you trade a comfort or privilege for focused training time.",
    "Unlocks after a near-miss where instinct almost fires this power untrained.",
    "Held until a campaign scene makes the unlock feel earned (mentor, trial, or discovery).",
)

_GENERIC_PREREQ_NORMALIZED: frozenset[str] = frozenset(
    {
        "unlocks through training, a mentor, or a costly field discovery.",
        "unlocks through training, a mentor, or a costly field discovery",
        "barely usable seed; deepens only through repeated risky practice.",
        "barely usable seed; deepens only through repeated risky practice",
        "held for later: the dm may unlock this when the fiction supports it (mid/late campaign event, mentor, or costly breakthrough) — not free at start.",
        "held for later: unlocks through a hard-earned breakthrough, mentor, or campaign event.",
        "held for later: unlocks through a hard-earned breakthrough, mentor, or campaign event",
    }
)


def _prereq_fingerprint(text: str) -> str:
    low = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not low:
        return ""
    if low in _GENERIC_PREREQ_NORMALIZED or low.startswith("unlocks through training, a mentor"):
        return "GENERIC_TRAINING_MENTOR_FIELD"
    if low.startswith("held for later"):
        return "GENERIC_HELD_FOR_LATER"
    if low.startswith("barely usable seed"):
        return "GENERIC_BARELY_USABLE_SEED"
    # Collapse near-identical mentor/field wording
    shaped = re.sub(r"\b(mentor|trainer|teacher|master)\b", "mentor", low)
    shaped = re.sub(r"\b(field discovery|discovery|find)\b", "discovery", shaped)
    shaped = re.sub(r"\b(train|training|practice|drill)\b", "train", shaped)
    return shaped[:80]


def is_generic_prereq(text: str) -> bool:
    fp = _prereq_fingerprint(text)
    return fp.startswith("GENERIC_") or fp in {
        "GENERIC_TRAINING_MENTOR_FIELD",
        "GENERIC_HELD_FOR_LATER",
        "GENERIC_BARELY_USABLE_SEED",
    }


def pick_default_prereq(
    ability: dict[str, Any] | None = None,
    *,
    index: int = 0,
    strength: str = "",
    origin: str = "",
) -> str:
    """Pick a fair, non-identical unlock sentence (stable-ish from name + index)."""
    name = str((ability or {}).get("name") or "")
    blob = f"{name}|{index}|{strength}|{origin}"
    h = sum(ord(c) for c in blob) + index * 17
    pool = ABILITY_PREREQ_VARIETY_POOL
    # Strong openers prefer "held until scene" flavors at end of pool
    if (strength or "").lower() == "strong":
        strong_pool = [p for p in pool if p.lower().startswith("held") or "campaign" in p.lower() or "setback" in p.lower()]
        if not strong_pool:
            strong_pool = list(pool[-4:])
        return strong_pool[h % len(strong_pool)]
    return pool[h % len(pool)]


def ability_power_lock_score(ability: dict[str, Any] | None) -> tuple[int, str]:
    """
    Rank powers for post-creation lock assignment.
    Higher score → more likely locked (stronger / costlier).
    Returns (score, strength_label).
    """
    if not isinstance(ability, dict):
        return (1, "moderate")
    strength = estimate_ability_opening_strength(ability)
    base = {"mild": 0, "moderate": 10, "strong": 30}.get(strength, 10)
    blob = f"{ability.get('name') or ''} {ability.get('description') or ''} {ability.get('cost') or ''}".lower()
    # Structured resource costs when already stamped
    rc = ability.get("resource_cost")
    if isinstance(rc, str) and rc.strip():
        try:
            rc = json.loads(rc)
        except Exception:
            rc = {}
    if isinstance(rc, dict):
        try:
            base += min(12, int(rc.get("energy") or 0))
            base += min(16, int(rc.get("mana") or 0) * 2)
            base += min(8, int(rc.get("fatigue") or 0) * 2)
            base += min(10, int(rc.get("health") or 0) * 3)
            cd = int(rc.get("cooldown_minutes") or 0)
            if cd >= 60:
                base += 8
            elif cd >= 15:
                base += 4
        except (TypeError, ValueError):
            pass
    # Fiction weight
    if any(w in blob for w in ("battlefield", "army", "mass ", "dominate", "annihilat", "kill", "slay")):
        base += 8
    if any(w in blob for w in ("minor", "briefly", "tiny", "whisper", "distract", "utility", "hint")):
        base -= 4
    if str(ability.get("power_type") or "").lower() == "passive" and strength != "strong":
        base += 2  # passives often delayed for acquired kits
    return (max(0, base), strength)


def roll_lock_count_for_batch(n: int, *, origin: str = "acquired") -> int:
    """
    Pure RNG: how many of the N created powers should be locked.
    Origin shapes the range; stronger powers are chosen later for those slots.
    """
    n = max(0, int(n or 0))
    if n <= 0:
        return 0
    origin_l = str(origin or "acquired").strip().lower()
    if origin_l in {"none", "innate"}:
        return 0
    if origin_l == "both":
        # Mix: 0..n with soft bias toward ~40% locked
        return sum(1 for _ in range(n) if random.random() < 0.4)
    # acquired: roll k in [0, n] with light bias away from all-unlocked when n>=2
    # Uniform first, then nudge if everyone open on multi-power kits
    k = random.randint(0, n)
    if n >= 2 and k == 0 and random.random() < 0.55:
        k = random.randint(1, max(1, n // 2 + 1))
    if n >= 3 and k == n and random.random() < 0.45:
        # Avoid locking the entire batch too often
        k = random.randint(max(1, n - 2), n - 1)
    return max(0, min(n, k))


def assign_ability_locks_after_creation(
    abilities: list[Any] | None,
    *,
    origin: str = "acquired",
) -> list[dict[str, Any]]:
    """
    After powers exist: roll how many are locked, then lock the *strongest* ones
    and attach fair prerequisites only to those. Weaker powers stay usable at Start.

    Order of operations (caller):
      1) roll quantity
      2) create abilities
      3) this function
      4) diversify costs/prereqs if needed
    """
    if not isinstance(abilities, list) or not abilities:
        return []
    origin_l = str(origin or "acquired").strip().lower()
    out: list[dict[str, Any]] = [dict(a) for a in abilities if isinstance(a, dict)]
    if not out:
        return []

    if origin_l in {"none"}:
        return out

    # Score every power now that fiction/cost exist
    scored: list[tuple[int, int, str, dict[str, Any]]] = []
    for i, ab in enumerate(out):
        score, strength = ability_power_lock_score(ab)
        ab["_opening_strength"] = strength
        ab["_lock_score"] = score
        scored.append((score, i, strength, ab))

    if origin_l == "innate":
        for ab in out:
            ab["locked"] = False
            ab["prerequisites"] = ""
        return out

    n = len(out)
    lock_count = roll_lock_count_for_batch(n, origin=origin_l)

    # Always lock "strong" powers when acquired/both — raise floor
    strong_idxs = [i for _s, i, strength, _ab in scored if strength == "strong"]
    if origin_l in {"acquired", "both"} and strong_idxs:
        lock_count = max(lock_count, len(strong_idxs))
        lock_count = min(n, lock_count)

    # Prefer keeping pure mild open: if all mild and lock_count high, reduce
    mild_n = sum(1 for _s, _i, strength, _ab in scored if strength == "mild")
    if mild_n == n and lock_count > 0 and n >= 2:
        # At most one mild can be held back
        lock_count = min(lock_count, 1) if random.random() < 0.35 else 0
    elif mild_n > 0 and lock_count > (n - mild_n):
        # Don't lock more than non-mild + maybe one mild
        lock_count = min(lock_count, (n - mild_n) + (1 if random.random() < 0.25 else 0))

    # Rank strongest first; tie-break random
    ranked = sorted(scored, key=lambda t: (t[0], random.random()), reverse=True)
    locked_indices = {t[1] for t in ranked[:lock_count]}

    for i, ab in enumerate(out):
        strength = str(ab.get("_opening_strength") or "moderate")
        if i in locked_indices:
            ab["locked"] = True
            existing_p = normalize_ability_prerequisites(ab.get("prerequisites") or ab.get("prerequisite"))
            if not existing_p or is_generic_prereq(existing_p):
                ab["prerequisites"] = pick_default_prereq(
                    ab, index=i, strength=strength, origin=origin_l
                )
            else:
                ab["prerequisites"] = existing_p
        else:
            ab["locked"] = False
            ab["prerequisites"] = ""

    # Distinct unlock paths for the locked subset
    out = diversify_ability_prerequisites(out, force=False, origin=origin_l)
    for ab in out:
        if not ab.get("locked"):
            ab["prerequisites"] = ""
    return out


def diversify_ability_prerequisites(
    abilities: list[Any] | None,
    *,
    force: bool = False,
    origin: str = "",
) -> list[dict[str, Any]]:
    """
    Ensure locked abilities do not all share the same mentor/training boilerplate.
    Unlocked/empty prereqs stay empty. Deterministic pool rotation.
    """
    if not isinstance(abilities, list):
        return []
    out: list[dict[str, Any]] = []
    seen_fps: list[str] = []
    pool_i = 0
    generic_hits = 0
    for ab in abilities:
        if isinstance(ab, dict):
            p = str(ab.get("prerequisites") or "").strip()
            if p and is_generic_prereq(p):
                generic_hits += 1
    identical_batch = False
    fps_all = [
        _prereq_fingerprint(str(a.get("prerequisites") or ""))
        for a in abilities
        if isinstance(a, dict) and str(a.get("prerequisites") or "").strip()
    ]
    if len(fps_all) >= 2 and len(set(fps_all)) == 1:
        identical_batch = True

    for idx, ab in enumerate(abilities):
        if not isinstance(ab, dict):
            continue
        next_ab = dict(ab)
        prereq = normalize_ability_prerequisites(next_ab.get("prerequisites") or next_ab.get("prerequisite"))
        locked = bool(next_ab.get("locked"))
        # Unlocked mild powers keep empty prereq
        if not locked and not prereq:
            next_ab["prerequisites"] = ""
            out.append(next_ab)
            continue
        if not prereq and not locked:
            next_ab["prerequisites"] = ""
            out.append(next_ab)
            continue

        fp = _prereq_fingerprint(prereq)
        must_replace = False
        if not prereq and locked:
            must_replace = True
        if is_generic_prereq(prereq) and (force or generic_hits >= 2 or identical_batch or fp in seen_fps):
            must_replace = True
        if fp and fp in seen_fps and (force or identical_batch or len(seen_fps) >= 1):
            must_replace = True
        if must_replace:
            used = {str(x.get("prerequisites") or "").strip().lower() for x in out}
            used.update(seen_fps)
            pick = None
            strength = str(next_ab.get("_opening_strength") or "")
            for _ in range(len(ABILITY_PREREQ_VARIETY_POOL) + 3):
                cand = ABILITY_PREREQ_VARIETY_POOL[pool_i % len(ABILITY_PREREQ_VARIETY_POOL)]
                pool_i += 1
                # Prefer name-tinted default first attempt
                if pick is None and pool_i == 1:
                    cand = pick_default_prereq(next_ab, index=idx, strength=strength, origin=origin)
                cfp = _prereq_fingerprint(cand)
                if cand.lower() not in used and cfp not in seen_fps:
                    pick = cand
                    fp = cfp
                    break
            if pick is None:
                pick = pick_default_prereq(next_ab, index=idx + pool_i, strength=strength, origin=origin)
                # Force uniqueness with light suffix if still colliding
                if _prereq_fingerprint(pick) in seen_fps:
                    pick = f"{pick.rstrip('.')} — specific to {str(next_ab.get('name') or 'this power')[:40]}."
                fp = _prereq_fingerprint(pick)
            next_ab["prerequisites"] = pick[:500]
            next_ab["_prereq_diversified"] = True
        else:
            next_ab["prerequisites"] = prereq
        if fp:
            seen_fps.append(fp)
        out.append(next_ab)
    return out


def normalize_ability_prerequisites(value: Any) -> str:
    """Coerce list/JSON leftovers into a clean human prereq string (never '[]')."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = [str(x).strip() for x in value if str(x).strip()]
        return "; ".join(parts)[:500]
    if isinstance(value, dict):
        # Model sometimes returns {"condition": "..."} or empty {}
        for key in ("text", "condition", "prerequisites", "prerequisite", "unlock"):
            if value.get(key):
                return normalize_ability_prerequisites(value.get(key))
        return ""
    text = str(value).strip()
    if not text:
        return ""
    # Empty JSON / placeholder forms that leak into the UI
    if text.lower() in {
        "[]",
        "{}",
        "null",
        "none",
        "nil",
        "n/a",
        "na",
        "-",
        "—",
        "undefined",
        "false",
        "true",
        "0",
        "1",
        "locked",
        "unlocked",
        "locked=true",
        "locked=false",
        "locked:true",
        "locked:false",
        "yes",
        "no",
    }:
        return ""
    # Model dumps field-control junk into prereq (e.g. "locked=true")
    if re.fullmatch(r"locked\s*[=:]\s*(true|false|yes|no|1|0)", text, flags=re.I):
        return ""
    if re.fullmatch(r"(true|false)\s*[=:]\s*locked", text, flags=re.I):
        return ""
    # Stringified empty list with spaces
    if re.fullmatch(r"\[\s*\]", text) or re.fullmatch(r"\{\s*\}", text):
        return ""
    # Accidental JSON array of strings
    if text.startswith("[") and text.endswith("]"):
        try:
            import json

            parsed = json.loads(text)
            return normalize_ability_prerequisites(parsed)
        except Exception:
            pass
    return text[:500]


def estimate_ability_opening_strength(ability: dict[str, Any] | None) -> str:
    """
    Classify opening strength for lock policy.

    - mild: small utility / distraction / once-per-day soft effects → usable at Start
    - strong: combat-winning / always-on heavy powers → may stay locked for later DM unlock
    - moderate: everything else
    """
    if not isinstance(ability, dict):
        return "moderate"
    blob = " ".join(
        [
            str(ability.get("name") or ""),
            str(ability.get("description") or ""),
            str(ability.get("cost") or ""),
        ]
    ).lower()
    strong_markers = (
        "invulnerab",
        "instant kill",
        "one-shot",
        "oneshot",
        "mind control",
        "time stop",
        "omnipoten",
        "always on",
        "permanently",
        "no cooldown",
        "unlimited",
        "annihilat",
        "god-slay",
        "erase from existence",
        "dominate all",
        " SSS",
        "sss-rank",
        "auto-win",
        "cannot miss",
        "ignore all defenses",
        "mass death",
        "level drain",
        "absolute defense",
        "absolute attack",
    )
    mild_markers = (
        "minor distraction",
        "briefly",
        "small ",
        "tiny ",
        "mimic the sound",
        "replicate its effect in a pinch",
        "distract",
        "disrupt an enemy's focus",
        "remember the exact sound",
        "hint of",
        "faint ",
        "whisper",
        "notice",
        "sense a",
        "once per day",
        "once a day",
        "short moment",
        "momentary",
        "mild ",
        "slight ",
        "flavor",
        "utility",
        "flavorful",
    )
    combat_weight = sum(
        1
        for w in (
            "damage",
            "kill",
            "slay",
            "blast",
            "strike down",
            "overwhelm",
            "dominate",
            "control minds",
            "summon army",
            "immune to",
        )
        if w in blob
    )
    if any(m in blob for m in strong_markers) or combat_weight >= 2:
        return "strong"
    mild_hits = sum(1 for m in mild_markers if m in blob)
    # Classic "once per day minor distraction" pattern
    if mild_hits >= 2 or (
        mild_hits >= 1
        and combat_weight == 0
        and any(x in blob for x in ("distract", "mimic", "sound", "whisper", "sense", "notice", "remember"))
    ):
        return "mild"
    if combat_weight == 0 and re.search(r"\bonce per (day|scene|rest)\b", blob) and len(blob) < 420:
        # Bounded soft actives default mild unless wording is heavy
        if not any(w in blob for w in ("devastate", "destroy", "execute", "slaughter", "obliterate")):
            return "mild"
    return "moderate"


def normalize_ability_lock_and_prerequisites(
    ability: dict[str, Any] | None,
    *,
    origin: str = "",
) -> dict[str, Any]:
    """
    Clean prereq placeholders and apply strength-based lock policy.

    - Never leave prerequisites as '[]' / null-ish.
    - Mild powers: unlocked at Start with empty prereq (usable off the bat).
    - Strong powers: may stay locked for later DM unlock, but need a real unlock sentence.
    - Acquired origin no longer forces every mild utility behind a fake lock.
    """
    if not isinstance(ability, dict):
        return {}
    out = dict(ability)
    prereq = normalize_ability_prerequisites(
        out.get("prerequisites") if "prerequisites" in out else out.get("prerequisite")
    )
    out["prerequisites"] = prereq
    if "prerequisite" in out:
        out["prerequisite"] = prereq

    # Coerce messy locked flags (None / "true" / "locked=true")
    raw_locked = out.get("locked")
    if isinstance(raw_locked, str):
        low_l = raw_locked.strip().lower()
        if low_l in {"", "false", "0", "no", "none", "null", "unlocked"}:
            out["locked"] = False
        elif low_l in {"true", "1", "yes", "locked", "locked=true"}:
            out["locked"] = True
        else:
            out["locked"] = False
    elif raw_locked is None:
        out["locked"] = False
    else:
        out["locked"] = bool(raw_locked)

    locked = bool(out.get("locked"))
    strength = estimate_ability_opening_strength(out)
    out["_opening_strength"] = strength
    origin_l = str(origin or "").strip().lower()

    empty_prereq = not prereq

    if strength == "mild":
        # Soft powers should be playable immediately; empty "[]" lock is never correct.
        if locked and empty_prereq:
            out["locked"] = False
            out["prerequisites"] = ""
        elif locked and prereq and prereq.lower() in {
            "unlocks through training, a mentor, or a costly field discovery.",
            "barely usable seed; deepens only through repeated risky practice.",
        }:
            # Generic acquired lock boilerplate on a mild utility → unlock
            out["locked"] = False
            out["prerequisites"] = ""
        else:
            # Mild with a specific story prereq can stay locked (player chose a condition).
            out["locked"] = locked
    elif strength == "strong":
        # Strong openers may be held for DM/play unlock — but never with blank/[] prereq.
        if locked and empty_prereq:
            out["prerequisites"] = pick_default_prereq(out, index=0, strength="strong", origin=origin_l)
        elif not locked and origin_l == "acquired" and empty_prereq:
            # Acquired + strong: prefer locked until earned
            out["locked"] = True
            out["prerequisites"] = pick_default_prereq(out, index=1, strength="strong", origin=origin_l)
    else:
        # moderate
        if locked and empty_prereq:
            if origin_l == "innate":
                out["locked"] = False
                out["prerequisites"] = ""
            else:
                out["prerequisites"] = pick_default_prereq(out, index=2, strength="moderate", origin=origin_l)

    # Final sanitization
    out["prerequisites"] = normalize_ability_prerequisites(out.get("prerequisites"))
    if not out["prerequisites"]:
        # Empty prereq implies usable unless explicitly locked with a real reason (shouldn't happen)
        if out.get("locked") and not out["prerequisites"]:
            out["locked"] = False
    return out


def _strip_usage_limits_from_description(desc: str) -> str:
    """Remove frequency/cooldown clauses; keep pure effect + duration."""
    cleaned = str(desc or "")
    patterns = (
        # Can be used once per rank/day/..., with a 1-minute cooldown...
        r"\s*(?:,|;|\.)?\s*(?:and\s+)?(?:can\s+be\s+)?used\s+once\s+per\s+(?:day|hour|scene|encounter|rest|long\s+rest|week|rank|level|use)\b"
        r"(?:\s*,?\s*with\s+(?:a\s+)?\d+[-–]?\s*(?:second|minute|hour)s?\s+cooldown(?:\s+after(?:\s+each\s+use)?)?)?",
        r"\s*(?:,|;|\.)?\s*(?:once|1\s*time|one\s+time)\s+per\s+(?:day|hour|scene|encounter|rest|long\s+rest|week|rank|level|use)\b"
        r"(?:\s*,?\s*with\s+(?:a\s+)?\d+[-–]?\s*(?:second|minute|hour)s?\s+cooldown(?:\s+after(?:\s+each\s+use)?)?)?",
        r"\s*(?:,|;|\.)?\s*\d+\s*times?\s+per\s+(?:day|hour|scene|encounter|rank)\b",
        r"\s*(?:,|;|\.)?\s*(?:once\s+a\s+day|daily\s+use)\b",
        r"\s*(?:,|;|\.)?\s*with\s+(?:a\s+)?\d+[-–]?\s*(?:second|minute|hour|min|sec)s?\s+cooldown(?:\s+after(?:\s+each\s+use)?)?\b",
        r"\s*(?:,|;|\.)?\s*\d+[-–]?\s*(?:second|minute|hour)s?\s+cooldown(?:\s+after(?:\s+each\s+use)?)?\b",
        r"\s*(?:,|;|\.)?\s*(?:recharges?|recovers?)\s+after\s+\d+[-–]?\s*(?:second|minute|hour)s?\b",
    )
    for pat in patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;.")
    # Fix trailing fragments
    cleaned = re.sub(r"\s+\.\s*$", ".", cleaned)
    if cleaned and not cleaned.endswith("."):
        cleaned += "."
    return cleaned


def _unified_cost_from_desc_and_cost(desc: str, cost: str, d_facts: dict[str, Any], c_facts: dict[str, Any]) -> str:
    """Merge frequency + recharge + strain into one cost string."""
    freq_bits: list[str] = []
    if d_facts.get("once_per_rank") or c_facts.get("once_per_rank") or re.search(r"\bonce per rank\b", cost, re.I):
        freq_bits.append("Once per rank")
    elif d_facts.get("uses_per_day") == 1 or (
        d_facts.get("use_period_minutes") and abs(float(d_facts["use_period_minutes"]) - 24 * 60) < 1
    ):
        freq_bits.append("Once per day")
    elif d_facts.get("uses_per_day"):
        freq_bits.append(f"{int(d_facts['uses_per_day'])} times per day")
    elif d_facts.get("use_period_minutes"):
        mins = float(d_facts["use_period_minutes"])
        if abs(mins - 60) < 0.5:
            freq_bits.append("Once per hour")
        elif abs(mins - 30) < 0.5:
            freq_bits.append("Once per scene")
        elif abs(mins - 24 * 60) < 1:
            freq_bits.append("Once per day")
        else:
            freq_bits.append(f"At most once every {mins:g} minutes")

    # Prefer shorter of desc/cost recharge when both set (CD is the mechanical gate)
    rech = None
    for src in (d_facts.get("recharge_minutes"), c_facts.get("recharge_minutes")):
        if src is not None:
            rech = float(src) if rech is None else min(rech, float(src))
    cd_bit = ""
    if rech is not None and rech > 0:
        if rech < 1:
            secs = max(1, int(round(rech * 60)))
            cd_bit = f"{secs}-second cooldown"
        elif abs(rech - int(rech)) < 0.05:
            mins_i = int(round(rech))
            cd_bit = f"{mins_i}-minute cooldown" if mins_i != 60 else "1-hour cooldown"
        else:
            cd_bit = f"{rech:g}-minute cooldown"

    cost_core = str(cost or "").strip()
    if cost_core.lower() in {"", "no cost", "none", "free", "model decides", "[]"}:
        cost_core = ""

    # Drop clone-y breath/meditation-only openers if we have a real CD + frequency
    # Keep stamina/energy drain fragments.
    strain_bits: list[str] = []
    m_pct = re.search(r"(\d{1,3})\s*%\s*(stamina|energy|fatigue)", cost_core, re.I)
    if m_pct:
        strain_bits.append(f"{m_pct.group(1)}% {m_pct.group(2).lower()} drain")
    elif re.search(r"\b(stamina|energy)\s+drain\b", cost_core, re.I):
        strain_bits.append("stamina drain")
    # Other non-timing cost text (noise, debt, reagent…) keep if not pure breath/meditation filler
    residual = cost_core
    residual = re.sub(r"\b\d+\s*(second|minute|hour)s?\s+of\s+(breath\s*control|meditation|breathing)\b[;,]?", "", residual, flags=re.I)
    residual = re.sub(r"\b\d+\s*%\s*(stamina|energy|fatigue)\s*drain\b[;,]?", "", residual, flags=re.I)
    residual = re.sub(r"\bonce\s+per\s+(rank|day|hour|scene|use)\b[;,]?", "", residual, flags=re.I)
    residual = re.sub(r"\d+[-–]?\s*(second|minute|hour)s?\s+cooldown\b[;,]?", "", residual, flags=re.I)
    residual = re.sub(r"\s{2,}", " ", residual).strip(" .;,")
    if residual and len(residual) > 8 and not re.search(
        r"^(breath\s*control|meditation to recharge|1 hour of meditation)\b", residual, re.I
    ):
        if residual.lower() not in {s.lower() for s in strain_bits}:
            strain_bits.append(residual.rstrip("."))

    pieces: list[str] = []
    for bit in freq_bits:
        if not any(bit.lower() in p.lower() for p in pieces):
            pieces.append(bit)
    if cd_bit and not any("cooldown" in p.lower() for p in pieces):
        pieces.append(cd_bit)
    for s in strain_bits:
        if s and not any(s.lower() in p.lower() for p in pieces):
            pieces.append(s)
    if not pieces and cost_core:
        return cost_core if cost_core.endswith(".") else cost_core + "."
    if not pieces:
        return "Short recovery after use."
    return "; ".join(pieces) + "."


def repair_ability_cross_field_consistency(ability: dict[str, Any]) -> dict[str, Any]:
    """Auto-fix common timing contradictions on a single ability.

    Preference when description has use frequency and cost has a shorter recharge:
    - Keep effect + duration in description
    - Move frequency + recharge together into cost (player-readable, one place of truth)
    """
    if not isinstance(ability, dict):
        return {}
    out = normalize_ability_lock_and_prerequisites(ability)
    desc = str(out.get("description") or "").strip()
    cost = str(out.get("cost") or "").strip()
    check = ability_cross_field_fact_check(out)
    d_facts = extract_ability_timing_facts(desc)
    c_facts = extract_ability_timing_facts(cost)

    fails = set(check.get("hard_fail") or [])
    # Always strip usage limits from description when present (even if check somehow passed)
    needs_strip = bool(d_facts.get("has_usage_limit_language")) or bool(
        fails
        & {
            "use_limit_vs_recharge_mismatch",
            "use_period_conflict_desc_vs_cost",
            "conflicting_use_frequency_desc_vs_cost",
            "uses_per_day_conflict",
            "recharge_conflict_desc_vs_cost",
            "usage_limits_embedded_in_description",
            "once_per_rank_missing_from_cost",
        }
    )

    if needs_strip:
        cleaned = _strip_usage_limits_from_description(desc)
        if cleaned and cleaned != desc:
            out["description"] = cleaned
        out["cost"] = _unified_cost_from_desc_and_cost(
            desc, cost, d_facts, c_facts
        )
        if out.get("cost") and str(out.get("cost")).lower() not in {"no cost", "model decides"}:
            out["cost_mode"] = "custom"

        # Sync structured resource_cost from unified timing + stamina %
        try:
            from app.player_resources import parse_resource_cost

            rc = parse_resource_cost(out.get("resource_cost"))
            rech = d_facts.get("recharge_minutes")
            if rech is None:
                rech = c_facts.get("recharge_minutes")
            # Re-read after unify
            u_facts = extract_ability_timing_facts(str(out.get("cost") or ""))
            if u_facts.get("recharge_minutes") is not None:
                rech = u_facts["recharge_minutes"]
            if rech is not None and _int_safe(rc.get("cooldown_minutes"), 0) == 0:
                rc["cooldown_minutes"] = max(0, int(round(float(rech))))
            pct = u_facts.get("stamina_pct") or d_facts.get("stamina_pct") or c_facts.get("stamina_pct")
            if pct and _int_safe(rc.get("energy"), 0) == 0:
                # Map % of a 20 baseline pool → absolute energy cost (min 1)
                rc["energy"] = max(1, int(round(20 * float(pct) / 100.0)))
            out["resource_cost"] = rc
        except Exception:
            pass

    # Duration longer than recharge: shorten description duration note is risky;
    # instead append clarification to cost that recharge starts after the effect ends.
    if "duration_longer_than_recharge" in fails:
        c = str(out.get("cost") or "").rstrip(".")
        if c and "after the effect ends" not in c.lower():
            out["cost"] = c + ". Recharge begins after the effect ends."
        # Soft: also strip nothing; if still failing, quality gate will deny for LLM rewrite.

    return out


def _int_safe(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def evaluate_ability_quality(
    ability: dict[str, Any] | None,
    *,
    existing: list[dict[str, Any]] | None = None,
    sibling_names: set[str] | None = None,
    one_skillish: bool = False,
    origin: str = "",
    require_strong_math: bool = True,
) -> dict[str, Any]:
    """Score one power for playability + stability. ok=False means quality-deny."""
    hard: list[str] = []
    soft: list[str] = []
    score = 100
    if not isinstance(ability, dict):
        return {"ok": False, "score": 0, "hard_fail": ["not_an_object"], "soft": [], "ability": {}}

    name = str(ability.get("name") or "").strip()
    desc = str(ability.get("description") or "").strip()
    cost = str(ability.get("cost") or "").strip()
    prereq = str(ability.get("prerequisites") or ability.get("prerequisite") or "").strip()
    math_text = str(ability.get("growth_math") or "").strip()
    power_type = str(ability.get("power_type") or "").strip().lower()
    locked = bool(ability.get("locked"))

    # --- name ---
    if len(name) < 2:
        hard.append("name_missing")
        score -= 40
    elif len(name) > 80:
        hard.append("name_too_long")
        score -= 15
    elif name.lower() in {"ability", "power", "skill", "special ability", "seed", "passive", "active"}:
        hard.append("name_generic")
        score -= 35
    if name and ability_name_has_numeric_junk(name):
        hard.append("name_numeric_suffix")
        score -= 30
    if name and is_overused_seed_domain(name):
        hard.append("name_overused_domain")
        score -= 30
    sib = sibling_names or set()
    if name and name.lower() in {s.lower() for s in sib if s}:
        hard.append("name_duplicate_in_batch")
        score -= 25
    for ex in existing or []:
        if isinstance(ex, dict) and str(ex.get("name") or "").strip().lower() == name.lower() and name:
            hard.append("name_matches_existing")
            score -= 25
            break

    # --- description ---
    if len(desc) < 36:
        hard.append("description_too_short")
        score -= 30
    elif len(desc) < 55:
        soft.append("description_thin")
        score -= 8
    # 8B failure mode: description is a copy of the name (or a keyword dump)
    name_key = re.sub(r"\s+", " ", name).strip().lower()
    desc_key = re.sub(r"\s+", " ", desc).strip().lower()
    if name_key and desc_key and name_key == desc_key:
        hard.append("description_equals_name")
        score -= 40
    if name and ("," in name or ";" in name) and len(name) > 28:
        hard.append("name_looks_like_keyword_dump")
        score -= 20
    if desc and len(desc.split()) <= 6 and len(desc) < 48:
        hard.append("description_keyword_stub")
        score -= 25
    if _ABILITY_VAGUE_DESC.search(desc):
        hard.append("description_vague_cliche")
        score -= 25
    if _ABILITY_META_LEAK.search(desc):
        hard.append("description_leaks_design_meta")
        score -= 35
    if desc and not _ABILITY_ACTION_HINT.search(desc):
        hard.append("description_no_playable_hook")
        score -= 20
    if _ABILITY_FREE_GOD.search(desc) or _ABILITY_FREE_GOD.search(cost):
        hard.append("description_or_cost_unstable_godmode")
        score -= 40
    # Generic template leftovers
    if re.search(r"barely useful at f rank;\s*practice and risk compound", desc, re.I):
        hard.append("description_template_boilerplate")
        score -= 20
    if re.search(r"fatigue,\s*strain,\s*or a short aftereffect when forced", cost, re.I):
        soft.append("cost_generic_template")
        score -= 8
    # Banned: "spend 1 hour each day/dawn in [place] to maintain this ability"
    if _ABILITY_MAINTENANCE_HOUR_TEMPLATE.search(cost) or _ABILITY_MAINTENANCE_HOUR_TEMPLATE.search(desc):
        hard.append("cost_maintenance_hour_template")
        score -= 35
    if re.search(
        r"\byou must spend\s+\d+\s*hours?\s+each\s+(day|dawn|dusk|night)\b",
        cost,
        re.I,
    ):
        hard.append("cost_must_spend_hours_each_day")
        score -= 30
    # Obscure is fine; pure nonsense with no who/what/when fails above.

    # --- growth math ---
    if require_strong_math or one_skillish or power_type in {"compounding", "soft_cap", "breakthrough"}:
        if not _ability_has_calculable_math(math_text):
            hard.append("growth_math_not_calculable")
            score -= 35
        else:
            # Soft stability: should mention rank path or XP somehow for compounding
            low = math_text.lower()
            if one_skillish or power_type == "compounding":
                if not any(k in low for k in ("rank", "xp", "level", "threshold")):
                    soft.append("growth_math_missing_rank_or_xp_path")
                    score -= 10
                if not any(k in low for k in ("soft", "break", "cap", "s/ss", "sss", "late")):
                    soft.append("growth_math_weak_late_game_path")
                    score -= 6
    elif math_text and not _ability_has_calculable_math(math_text):
        soft.append("growth_math_weak")
        score -= 12

    # --- cost ---
    cost_l = cost.lower()
    freeish = (not cost) or cost_l in {"none", "no cost", "free", "n/a", "-", "0"}
    if power_type == "passive":
        if not cost:
            # Passiveives may omit cost; stamp a stable default later if needed
            soft.append("passive_cost_empty_ok")
        elif freeish:
            soft.append("passive_no_cost")
    else:
        if freeish and one_skillish:
            soft.append("active_seed_should_have_strain_cost")
            score -= 8
        if freeish and not one_skillish and power_type not in {"flat", ""}:
            soft.append("active_missing_meaningful_cost")
            score -= 10
        if not cost:
            hard.append("cost_missing")
            score -= 15
    if cost and len(cost) > 280:
        soft.append("cost_too_long")
        score -= 5

    # --- prerequisites vs locked / origin ---
    origin_l = (origin or "").lower()
    prereq_norm = normalize_ability_prerequisites(prereq)
    if prereq_norm != prereq:
        soft.append("prereq_placeholder_form")
        score -= 4
        prereq = prereq_norm
    # Literal "[]" / empty JSON must never ship as a prerequisite
    if prereq.strip() in {"[]", "{}"} or re.fullmatch(r"\[\s*\]", prereq or ""):
        hard.append("prereq_json_placeholder")
        score -= 25
    if locked and len(prereq) < 8:
        hard.append("locked_without_prerequisites")
        score -= 20
    if origin_l == "acquired" and locked and len(prereq) < 8:
        hard.append("acquired_locked_needs_prereq")
        score -= 10
    if origin_l == "innate" and locked and "remnant" not in prereq.lower() and "awaken" not in prereq.lower():
        soft.append("innate_locked_odd")
        score -= 5
    # Mild utility powers should not be locked behind empty/placeholder prereqs
    strength = estimate_ability_opening_strength(ability)
    if strength == "mild" and locked and len(prereq) < 8:
        hard.append("mild_power_locked_without_real_prereq")
        score -= 18
    if prereq and len(prereq) > 480:
        soft.append("prereq_too_long")
        score -= 4

    # --- power_type ---
    if power_type and power_type not in _VALID_POWER_TYPES:
        soft.append("power_type_unknown")
        score -= 6
    if one_skillish and power_type and power_type not in {"compounding", "passive", "soft_cap", "breakthrough", ""}:
        soft.append("power_type_odd_for_seed")
        score -= 4

    # --- cross-field fact check (description ↔ cost ↔ math) ---
    xf = ability_cross_field_fact_check(ability)
    for fail in xf.get("hard_fail") or []:
        hard.append(str(fail))
        score -= 22
    for warn in xf.get("soft") or []:
        soft.append(str(warn))
        score -= 6

    score = max(0, min(100, score))
    # Hard fails always deny; otherwise require a solid score.
    ok = not hard and score >= 62
    return {
        "ok": ok,
        "score": score,
        "hard_fail": hard,
        "soft": soft,
        "name": name,
        "ability": ability,
        "cross_field": xf.get("details") or {},
    }


def quality_gate_abilities(
    abilities: list[Any] | None,
    *,
    existing: list[Any] | None = None,
    one_skillish: bool = False,
    origin: str = "",
    require_strong_math: bool = True,
    auto_repair: bool = True,
) -> dict[str, Any]:
    """Verify a whole ability batch. All entries must pass for ok=True."""
    existing_clean = [a for a in (existing or []) if isinstance(a, dict)]
    raw_list = [a for a in (abilities or []) if isinstance(a, dict)]
    if not raw_list:
        return {
            "ok": False,
            "score": 0,
            "abilities": [],
            "reports": [],
            "denial_summary": ["empty_ability_list"],
        }
    reports: list[dict[str, Any]] = []
    names_seen: set[str] = set()
    denial_summary: list[str] = []
    scores: list[int] = []
    repaired_list: list[dict[str, Any]] = []
    for ab in raw_list:
        candidate = dict(ab)
        # Strip "Salt Circle 52" style junk before quality scoring
        if candidate.get("name"):
            cleaned_name = sanitize_ability_name(candidate.get("name"))
            if cleaned_name:
                candidate["name"] = cleaned_name
        if auto_repair:
            candidate = normalize_ability_lock_and_prerequisites(candidate, origin=origin)
            candidate = repair_ability_cross_field_consistency(candidate)
            # Repair already calls normalize, but re-apply origin-aware lock policy after timing fixes
            candidate = normalize_ability_lock_and_prerequisites(candidate, origin=origin)
        else:
            candidate["prerequisites"] = normalize_ability_prerequisites(
                candidate.get("prerequisites") or candidate.get("prerequisite")
            )
        rep = evaluate_ability_quality(
            candidate,
            existing=existing_clean,
            sibling_names=names_seen,
            one_skillish=one_skillish,
            origin=origin,
            require_strong_math=require_strong_math,
        )
        # If still failing only on cross-field, keep repaired text for retry prompts.
        reports.append(rep)
        scores.append(int(rep.get("score") or 0))
        repaired_list.append(candidate if rep.get("ok") else candidate)
        n = str(candidate.get("name") or ab.get("name") or "").strip()
        if n:
            names_seen.add(n)
        if not rep.get("ok"):
            denial_summary.append(
                f"{n or '?'}: " + ", ".join(rep.get("hard_fail") or rep.get("soft") or ["low_score"])
            )
    avg = int(round(sum(scores) / max(1, len(scores))))
    all_ok = all(r.get("ok") for r in reports)
    # Batch variety: two near-identical descriptions fail the gate.
    descs = [
        re.sub(r"\s+", " ", str(a.get("description") or "").lower())[:80]
        for a in repaired_list
    ]
    if len(descs) >= 2 and len(set(descs)) < len(descs):
        all_ok = False
        denial_summary.append("batch_duplicate_descriptions")
    # Near-duplicates (same lane / similar fiction) — not only exact string clones
    near_pairs = find_near_duplicate_pairs(repaired_list, existing=existing_clean)
    if near_pairs:
        all_ok = False
        top = near_pairs[0]
        denial_summary.append(
            "batch_near_duplicate_abilities:"
            f"{top.get('names')}:{top.get('score')}"
        )
    # Batch cost variety: reject clone costs (meditation-hour spam, identical shapes).
    cost_fps = [_cost_structure_fingerprint(str(a.get("cost") or "")) for a in repaired_list]
    cost_fps_nonzero = [fp for fp in cost_fps if fp]
    if len(cost_fps_nonzero) >= 2:
        unique_costs = set(cost_fps_nonzero)
        if len(unique_costs) == 1:
            all_ok = False
            denial_summary.append("batch_identical_cost_structure")
        elif len(repaired_list) >= 3 and len(unique_costs) < max(2, (len(repaired_list) + 1) // 2):
            all_ok = False
            denial_summary.append("batch_low_cost_variety")
        # Specific ban: 2+ maintenance-hour templates in one roll
        maint_hits = sum(1 for fp in cost_fps_nonzero if fp == "MAINTAIN_HOUR_ENV_DAILY")
        if maint_hits >= 2:
            all_ok = False
            denial_summary.append("batch_maintenance_hour_spam")
        # Specific ban: 2+ "1 hour meditation to recharge" (with or without once-per-X)
        med_hits = sum(
            1
            for fp in cost_fps_nonzero
            if fp
            in {
                "HOUR_MEDITATION_RECHARGE",
                "ONCE_PER_X_PLUS_HOUR_MEDITATION_RECHARGE",
                "HOUR_RITUAL_RECHARGE",
                "ONCE_DAY_PLUS_HOUR",
            }
        )
        if med_hits >= 2:
            all_ok = False
            denial_summary.append("batch_meditation_hour_recharge_spam")
    # Prerequisite variety (same "mentor or field discovery" on every card is weak)
    prereq_fps = [
        _prereq_fingerprint(str(a.get("prerequisites") or ""))
        for a in repaired_list
        if str(a.get("prerequisites") or "").strip()
    ]
    generic_prereq_hits = sum(1 for fp in prereq_fps if str(fp).startswith("GENERIC_"))
    if len(prereq_fps) >= 2 and (len(set(prereq_fps)) == 1 or generic_prereq_hits >= 2):
        try:
            repaired_list = diversify_ability_prerequisites(repaired_list, force=True, origin=origin)
            prereq_fps = [
                _prereq_fingerprint(str(a.get("prerequisites") or ""))
                for a in repaired_list
                if str(a.get("prerequisites") or "").strip()
            ]
        except Exception:
            pass
        if len(prereq_fps) >= 2 and len(set(prereq_fps)) == 1:
            all_ok = False
            denial_summary.append("batch_identical_prerequisites")
        elif generic_prereq_hits >= 2 and sum(
            1 for fp in prereq_fps if str(fp).startswith("GENERIC_")
        ) >= 2:
            # Diversify failed to break generics — soft deny for retry
            all_ok = False
            denial_summary.append("batch_generic_prerequisite_spam")
    return {
        "ok": all_ok,
        "score": avg,
        # Prefer auto-repaired text (unified cost/use limits) even when later denials remain.
        "abilities": repaired_list,
        "reports": reports,
        "denial_summary": denial_summary,
        "auto_repaired": auto_repair,
        "near_duplicate_pairs": near_pairs[:8] if near_pairs else [],
    }


# Word-only name variants when a seed domain collides — never bare integers (no "Salt Circle 52").
_ABILITY_NAME_PREFIXES = (
    "Deep",
    "Quiet",
    "Ashen",
    "Iron",
    "Pale",
    "Hollow",
    "Bright",
    "Rough",
    "Still",
    "Cold",
    "Soft",
    "Wild",
)
_ABILITY_NAME_SUFFIXES = (
    "Mark",
    "Craft",
    "Edge",
    "Rite",
    "Sense",
    "Thread",
    "Ward",
    "Hand",
    "Step",
    "Breath",
    "Line",
    "Knack",
)


def sanitize_ability_name(name: Any) -> str:
    """Strip accidental numeric suffixes from ability names (e.g. 'Salt Circle 52' → 'Salt Circle')."""
    text = re.sub(r"\s+", " ", str(name or "").strip())
    if not text:
        return ""
    # Order matters: strip "Variant 7" / "(2)" before bare trailing digits.
    text = re.sub(r"\s+Variant\s+\d{1,3}$", "", text, flags=re.I)
    text = re.sub(r"\s*\(\d{1,3}\)\s*$", "", text)
    # "Salt Circle 52", "Name Whisper 40", "Lamp Glare 87"
    text = re.sub(r"\s+\d{1,3}$", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:100]


def ability_name_has_numeric_junk(name: str) -> bool:
    """True if the display name ends with a bare number / Variant N / (N)."""
    text = re.sub(r"\s+", " ", str(name or "").strip())
    if re.search(r"\s+\d{1,3}$", text):
        return True
    if re.search(r"\s+Variant\s+\d{1,3}$", text, re.I):
        return True
    if re.search(r"\s*\(\d{1,3}\)\s*$", text):
        return True
    return False


def _unique_ability_display_name(
    base: str,
    forbidden_names: set[str] | list[str] | None,
    *,
    world_style: str = "",
    salt: str = "",
) -> str:
    """
    Return a player-facing ability name that is not in forbidden_names.
    Never appends bare integers. Prefers alternate seed domains, then word variants.
    """
    from app.setup_composer import pick_seed_skill_domain, seed_skill_domain_names

    forbidden = {
        re.sub(r"\s+", " ", str(f or "").strip().lower())
        for f in (forbidden_names or [])
        if str(f or "").strip()
    }
    # Also treat numbered clones of a base as taken (Salt Circle 12 blocks Salt Circle)
    forbidden_bases = {re.sub(r"\s+\d{1,3}$", "", f).strip() for f in forbidden if f}

    def _taken(n: str) -> bool:
        key = re.sub(r"\s+", " ", str(n or "").strip().lower())
        if not key:
            return True
        if key in forbidden or key in forbidden_bases:
            return True
        # Exact match only — do not use substring "name in forbidden" (false positives)
        return False

    clean_base = sanitize_ability_name(base) or "Quiet Craft"
    if not _taken(clean_base):
        return clean_base[:100]

    # Try several fresh seed domains
    avoid = list(forbidden) + [clean_base]
    for i in range(12):
        dom = pick_seed_skill_domain(
            avoid=avoid,
            world_style=world_style,
            salt=f"{salt}|uniq|{i}|{time.time_ns()}",
        )
        cand = sanitize_ability_name(str(dom.get("name") or ""))
        if cand and not _taken(cand):
            return cand[:100]
        if cand:
            avoid.append(cand)

    # Word-only variants of the cleaned base
    words = clean_base.split()
    short = " ".join(words[:2]) if words else clean_base
    for prefix in random.sample(list(_ABILITY_NAME_PREFIXES), k=len(_ABILITY_NAME_PREFIXES)):
        cand = f"{prefix} {short}".strip()
        if not _taken(cand):
            return cand[:100]
    for suffix in random.sample(list(_ABILITY_NAME_SUFFIXES), k=len(_ABILITY_NAME_SUFFIXES)):
        cand = f"{short} {suffix}".strip()
        if not _taken(cand):
            return cand[:100]

    # Last resort: uncommon two-word combo from seed name halves (still no digits)
    pool_names = [n for n in seed_skill_domain_names() if n and not _taken(n)]
    if pool_names:
        return random.choice(pool_names)[:100]
    # Extremely rare full exhaustion
    return f"{random.choice(_ABILITY_NAME_PREFIXES)} {random.choice(_ABILITY_NAME_SUFFIXES)}"[:100]


def _local_remake_ability(
    *,
    forbidden_names: set[str],
    origin: str = "",
    world_style: str = "",
) -> dict[str, Any]:
    """Deterministic distinct ability when LLM rework/remake fails."""
    from app.setup_composer import player_facing_domain_description, pick_seed_skill_domain

    avoid = [n for n in forbidden_names if n]
    dom = pick_seed_skill_domain(
        avoid=avoid,
        world_style=world_style,
        salt=f"dedupe_remake|{time.time_ns()}|{random.randint(1, 99999)}",
    )
    name = _unique_ability_display_name(
        str(dom.get("name") or "Quiet Craft"),
        forbidden_names,
        world_style=world_style,
        salt=f"local_remake|{time.time_ns()}",
    )
    # If we had to rename away from the domain, keep description from domain but name unique
    desc = player_facing_domain_description(dom)
    ab = {
        "name": name,
        "description": desc,
        "locked": origin == "acquired",
        "prerequisites": (
            pick_default_prereq({"name": name}, index=random.randint(0, 20), origin=origin)
            if origin == "acquired"
            else ""
        ),
        "cost": random.choice(
            [
                "A brief headache and ringing in the ears",
                "One point of fatigue until you rest or eat",
                "Numb fingers / shaky hands for a few minutes",
                "Leaves you socially flat — harder to charm for a short while",
            ]
        ),
        "growth_math": random.choice(GROWTH_MATH_SAMPLES),
        "power_type": "compounding" if origin == "acquired" else "linear",
        "_dedupe_source": "local_remake",
    }
    return normalize_ability_lock_and_prerequisites(ab, origin=origin)


def _llm_rework_or_remake_ability(
    *,
    weaker: dict[str, Any],
    keepers: list[dict[str, Any]],
    mode: str,
    origin: str = "",
    world_style: str = "",
    one_skillish: bool = False,
) -> dict[str, Any] | None:
    """Ask the model to rework (modify) or fully remake a near-duplicate ability."""
    mode_l = "remake" if str(mode).lower().startswith("remake") else "rework"
    forbidden = [str(k.get("name") or "").strip() for k in keepers if isinstance(k, dict)]
    forbidden = [n for n in forbidden if n]
    prompt = {
        "task": (
            f"{'REMAKE' if mode_l == 'remake' else 'REWORK'} one special ability so it is not a near-duplicate "
            "of the keepers. Output must feel mechanically and fictionally distinct."
        ),
        "mode": mode_l,
        "weaker_ability": {
            "name": weaker.get("name"),
            "description": weaker.get("description"),
            "cost": weaker.get("cost"),
            "prerequisites": weaker.get("prerequisites"),
            "growth_math": weaker.get("growth_math"),
            "power_type": weaker.get("power_type"),
            "locked": weaker.get("locked"),
        },
        "keepers_do_not_copy": [
            {
                "name": k.get("name"),
                "description": str(k.get("description") or "")[:220],
                "power_type": k.get("power_type"),
                "effect_lanes": sorted(_ability_effect_lanes(k)),
            }
            for k in keepers
            if isinstance(k, dict)
        ],
        "forbidden_names": forbidden,
        "ability_origin": origin,
        "world_style": world_style,
        "rules": [
            "Return JSON only: {\"ability\": {name, description, locked, prerequisites, cost, growth_math, power_type}}.",
            "Change the core action and domain — not just rename synonyms of the same power.",
            "If mode is rework: keep a thin thematic link if possible, but different verb, limit, and payoff.",
            "If mode is remake: invent a wholly new power in a different effect lane than keepers.",
            "Description must be concrete playable prose (≥1 clear action), not equal to the name.",
            "Fill growth_math with digits and XP/rank path.",
            "Cost must be real and not clone keeper cost structures.",
            "Never reuse forbidden_names or paraphrase keeper descriptions.",
        ],
        "preferred_lanes_if_remake": [
            lane
            for lane in _ABILITY_EFFECT_LANES
            if lane not in set().union(*(_ability_effect_lanes(k) for k in keepers if isinstance(k, dict)))
        ][:6],
    }
    try:
        raw = _chat_json(
            "Return JSON only. One distinct ability. No explanations.",
            json.dumps(prompt, ensure_ascii=True),
            timeout=_model_timeout(30, 150, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
            phase=f"setup_ability_dedupe_{mode_l}",
            max_tokens=500,
        )
    except Exception:
        return None
    ab = None
    if isinstance(raw, dict):
        if isinstance(raw.get("ability"), dict):
            ab = raw["ability"]
        elif isinstance(raw.get("special_abilities"), list) and raw["special_abilities"]:
            cand = raw["special_abilities"][0]
            if isinstance(cand, dict):
                ab = cand
        elif raw.get("name") or raw.get("description"):
            ab = raw
    if not isinstance(ab, dict):
        return None
    cleaned = normalize_ability_lock_and_prerequisites(dict(ab), origin=origin)
    cleaned = repair_ability_cross_field_consistency(cleaned)
    cleaned = normalize_ability_lock_and_prerequisites(cleaned, origin=origin)
    if not str(cleaned.get("growth_math") or "").strip():
        cleaned["growth_math"] = random.choice(GROWTH_MATH_SAMPLES)
    # Quality solo check (soft math for non-seed unless one_skillish)
    rep = evaluate_ability_quality(
        cleaned,
        existing=keepers,
        sibling_names={str(k.get("name") or "") for k in keepers if isinstance(k, dict)},
        one_skillish=one_skillish,
        origin=origin,
        require_strong_math=bool(one_skillish),
    )
    if not rep.get("ok"):
        return None
    # Must be distinct from keepers
    for k in keepers:
        if ability_similarity_score(cleaned, k) >= ABILITY_NEAR_DUP_THRESHOLD:
            return None
    cleaned["_dedupe_source"] = mode_l
    return cleaned


def ensure_distinct_abilities(
    abilities: list[Any] | None,
    *,
    existing: list[Any] | None = None,
    origin: str = "",
    one_skillish: bool = False,
    world_style: str = "",
    max_rounds: int = ABILITY_DEDUPE_MAX_ROUNDS,
    use_llm: bool = True,
) -> dict[str, Any]:
    """
    Cross-check a batch for duplicates / near-duplicates.

    For each near-pair: rework the weaker ability; if still similar, remake entirely;
    re-check against the full set; rinse and repeat until clean or rounds exhausted.
    """
    items: list[dict[str, Any]] = [dict(a) for a in (abilities or []) if isinstance(a, dict)]
    existing_clean = [a for a in (existing or []) if isinstance(a, dict)]
    log: list[dict[str, Any]] = []
    if len(items) + len(existing_clean) < 2:
        return {"abilities": items, "ok": True, "rounds": 0, "log": log, "pairs_remaining": []}

    for round_i in range(1, max(1, max_rounds) + 1):
        pairs = find_near_duplicate_pairs(items, existing=existing_clean)
        if not pairs:
            return {
                "abilities": items,
                "ok": True,
                "rounds": round_i - 1,
                "log": log,
                "pairs_remaining": [],
            }
        pair = pairs[0]
        weaker_i = int(pair["weaker_index"])
        if weaker_i < 0 or weaker_i >= len(items):
            break
        weaker = items[weaker_i]
        keepers = [ab for idx, ab in enumerate(items) if idx != weaker_i] + existing_clean
        forbidden = {str(k.get("name") or "").strip() for k in keepers if str(k.get("name") or "").strip()}
        forbidden.add(str(weaker.get("name") or "").strip())

        entry: dict[str, Any] = {
            "round": round_i,
            "pair": pair.get("names"),
            "score": pair.get("score"),
            "weaker": weaker.get("name"),
            "actions": [],
        }

        replacement: dict[str, Any] | None = None
        if use_llm:
            replacement = _llm_rework_or_remake_ability(
                weaker=weaker,
                keepers=keepers,
                mode="rework",
                origin=origin,
                world_style=world_style,
                one_skillish=one_skillish,
            )
            entry["actions"].append("llm_rework" if replacement else "llm_rework_failed")
            if replacement:
                # still similar?
                still = any(
                    ability_similarity_score(replacement, k) >= ABILITY_NEAR_DUP_THRESHOLD for k in keepers
                )
                if still:
                    entry["actions"].append("rework_still_similar")
                    replacement = None

        if replacement is None and use_llm:
            replacement = _llm_rework_or_remake_ability(
                weaker=weaker,
                keepers=keepers,
                mode="remake",
                origin=origin,
                world_style=world_style,
                one_skillish=one_skillish,
            )
            entry["actions"].append("llm_remake" if replacement else "llm_remake_failed")
            if replacement and any(
                ability_similarity_score(replacement, k) >= ABILITY_NEAR_DUP_THRESHOLD for k in keepers
            ):
                entry["actions"].append("remake_still_similar")
                replacement = None

        if replacement is None:
            replacement = _local_remake_ability(
                forbidden_names=forbidden,
                origin=origin,
                world_style=world_style,
            )
            entry["actions"].append("local_remake")
            # If local remake still collides (rare), pick a fully distinct name + niche note — no bare numbers.
            if any(ability_similarity_score(replacement, k) >= ABILITY_NEAR_DUP_THRESHOLD for k in keepers):
                replacement["name"] = _unique_ability_display_name(
                    str(replacement.get("name") or "Craft Edge"),
                    forbidden | {str(replacement.get("name") or "")},
                    world_style=world_style,
                    salt=f"forced_distinct|{time.time_ns()}",
                )
                replacement["description"] = (
                    str(replacement.get("description") or "").rstrip(".")
                    + " Focuses on a different practical niche than the character's other powers."
                )
                entry["actions"].append("local_remake_forced_distinct")

        # Always sanitize numeric junk on the way out of a remake
        if isinstance(replacement, dict):
            replacement["name"] = sanitize_ability_name(replacement.get("name")) or str(
                replacement.get("name") or "Quiet Craft"
            )[:100]
        items[weaker_i] = replacement
        entry["result_name"] = replacement.get("name")
        log.append(entry)

    pairs_left = find_near_duplicate_pairs(items, existing=existing_clean)
    return {
        "abilities": items,
        "ok": not pairs_left,
        "rounds": max_rounds,
        "log": log,
        "pairs_remaining": pairs_left[:6],
    }


def evaluate_custom_skills_quality(
    text: str,
    *,
    abilities: list[Any] | None = None,
    one_skillish: bool = False,
) -> dict[str, Any]:
    """Quality-check custom_skills prose (especially weak-seed / OP frames)."""
    raw = str(text or "").strip()
    hard: list[str] = []
    soft: list[str] = []
    score = 100
    if not raw:
        return {"ok": False, "score": 0, "hard_fail": ["empty"], "soft": []}
    low = raw.lower()
    # Still a skeleton frame — not expanded fiction.
    if "op_mc_frame" in low or "one_skill_frame" in low:
        if len(raw) < 160 or "weak seed skill:" not in low:
            hard.append("still_skeleton_frame")
            score -= 40
    if one_skillish:
        if "weak seed skill:" not in low and "seed skill" not in low:
            # Align with first ability name if present
            a0 = ""
            if isinstance(abilities, list) and abilities and isinstance(abilities[0], dict):
                a0 = str(abilities[0].get("name") or "").strip()
            if not a0 or a0.lower() not in low:
                hard.append("missing_named_seed")
                score -= 25
        if is_overused_seed_domain(raw[:80]) or any(
            bad in low for bad in ("observation", "ropework", "knot-work", "lie detection", "barter")
        ):
            # Only hard-fail if the *seed name* is overused, not if banned words appear in ban list
            m = re.search(r"weak\s+seed\s+skill\s*:\s*([A-Za-z][A-Za-z0-9 \-]{1,40})", raw, re.I)
            if m and is_overused_seed_domain(m.group(1)):
                hard.append("seed_overused_domain")
                score -= 30
        if len(raw) < 100:
            hard.append("custom_skills_too_thin")
            score -= 20
    if len(raw) > 4000:
        soft.append("custom_skills_very_long")
        score -= 5
    score = max(0, min(100, score))
    return {"ok": not hard and score >= 60, "score": score, "hard_fail": hard, "soft": soft}


def _fallback_custom_skills_from_domain(
    current_setup: dict[str, Any],
    *,
    domain: dict[str, str] | None = None,
) -> str:
    """Last-resort custom_skills string after quality denials — uses seed pool."""
    abilities = current_setup.get("special_abilities") if isinstance(current_setup.get("special_abilities"), list) else []
    name = ""
    if abilities and isinstance(abilities[0], dict):
        name = str(abilities[0].get("name") or "").strip()
    if not name or is_overused_seed_domain(name):
        dom = domain or pick_seed_skill_domain(
            world_style=str(current_setup.get("world_style") or ""),
            salt=f"cs_fallback|{time.time_ns()}",
        )
        name = str(dom.get("name") or "Digging")
        # Use clean hint only (never prompt_hint with tier/lane tags).
        hint = str(dom.get("hint") or "a thin practical edge").strip().rstrip(".")
        req = str(dom.get("requires") or "")
        late = str(dom.get("compounds_to") or "late-domain mastery")
    else:
        hint = "weak practical expression of the seed ability"
        req = ""
        late = "late compounding mastery of this domain"
    parts = [
        f"weak seed skill: {name}",
        "near-useless rank F / level 1",
        hint,
        f"works best with {req}" if req else "no free combat kit at Start",
        "track ranks via system UI if on else DM notes",
        "XP from practice, mentors, risk, and breakthroughs",
        f"late path: {late}",
        "passives OK as domain expressions later",
        "more powers may unlock in play not at Start",
    ]
    return ", ".join(p for p in parts if p)[:1200]


def _ability_quality_retry_prompt(
    *,
    denied: dict[str, Any],
    existing: list[Any],
    origin: str,
    intent_plan: dict[str, Any],
    attempt: int,
    count_min: int,
    count_max: int,
) -> dict[str, Any]:
    """Prompt the model to invent again after a quality denial (not copy the pool)."""
    return {
        "task": (
            f"QUALITY DENIAL #{attempt}: previous special_abilities failed the quality gate. "
            "Invent NEW original powers — exhaust fresh ideas. Do not copy catalog seed names "
            "unless you truly cannot invent (even then, reinvent the fiction)."
        ),
        "denial_summary": denied.get("denial_summary") or [],
        "failed_reports": [
            {
                "name": r.get("name"),
                "score": r.get("score"),
                "hard_fail": r.get("hard_fail"),
                "soft": r.get("soft"),
            }
            for r in (denied.get("reports") or [])[:6]
        ],
        "forbidden_abilities": existing,
        "ability_origin": origin,
        "count_min": count_min,
        "count_max": count_max,
        "field_intent": intent_slice_for_field(intent_plan, "special_abilities"),
        "quality_bar": {
            "name": "evocative, specific, not generic Ability/Power, not overused cliché domains",
            "description": "≥1 concrete playable hook (what you do / when / limit); no vague mystery power",
            "growth_math": "calculable XP/rank numbers a DM can apply; include soft-cap/breakthrough for seeds",
            "cost": "meaningful strain/resource for actives; passives may be always-on with a drawback",
            "prerequisites": "required when locked=true; concrete unlock path",
            "stability": "no unlimited/omnipotent/auto-win wording",
            "cross_field_consistency": (
                "Description, cost, prerequisites, and growth_math must agree on use limits. "
                "Never say 'once per day' in description while cost says '1 hour to recharge' — "
                "put frequency + recharge together in cost, or use the same period in both fields."
            ),
        },
        "ban_overused_domains": sorted(OVERUSED_SEED_DOMAINS),
        "return_shape": {
            "special_abilities": [
                {
                    "name": "original ability name",
                    "description": "concrete playable base description",
                    "locked": False,
                    "prerequisites": "",
                    "cost": "concrete cost or drawback",
                    "growth_math": "concrete XP/rank formulas with numbers",
                    "power_type": "compounding|passive|linear|soft_cap|breakthrough|flat|item_bound",
                }
            ]
        },
        "rules": [
            "Return JSON only with special_abilities.",
            "Fix every hard_fail from failed_reports.",
            "Do not reuse forbidden_abilities names or paraphrase their descriptions.",
            "Invent domains freely (summon, necro, heal support, weapon-bound, tool rites, weird hybrid) — original first.",
            "Seed catalog names are last-resort inspiration only, not a menu to pick from.",
            "Always fill growth_math with digits and rank/XP path.",
            "If locked, prerequisites must be a real unlock sentence.",
            "FACT-CHECK TIMING: description and cost must agree on use limits. Prefer effect+duration in description; "
            "put frequency in cost when needed. Do NOT stamp every ability with the same meditation-hour recharge.",
            "If hard_fail includes use_limit_vs_recharge_mismatch, unify frequency and recharge for THAT ability only.",
            "If denial mentions batch_maintenance_hour_spam / batch_identical_cost_structure / batch_meditation_hour_recharge_spam: "
            "each ability MUST get a DIFFERENT cost shape. BANNED clone: 'Once per rank/day; 1 hour of meditation to recharge after use' on more than one power. "
            "Use varied costs: fatigue, reagent, social debt, tool wear, noise, once-per-scene breathlessness, nosebleed, heat drain — not identical meditation rituals.",
            "Across a multi-ability batch, costs and prerequisites must not be the same sentence with one noun swapped.",
        ],
    }


# Distinct cost shapes for batch diversification (never all meditation-hour clones).
_ABILITY_COST_VARIETY_POOL = (
    "A brief headache and ringing in the ears after use.",
    "One point of fatigue until you rest or eat.",
    "Numb fingers / shaky hands for a few minutes.",
    "Spends a small personal focus (candle, salt pinch, named tool scrap) when used.",
    "Leaves you socially flat — harder to charm for a short while.",
    "A nosebleed or iron taste if forced twice in a row.",
    "Makes a noticeable noise or scent; nearby people may investigate.",
    "Tool or cloth wear: one piece of gear frays or dulls slightly.",
    "Once per scene; short breathlessness after.",
    "Once per day; mild mental fog for ten minutes after.",
    "Costs a favor, coin, or small social debt when used in public.",
    "Drains body heat; you shiver until warmed.",
)


def diversify_ability_costs(
    abilities: list[Any] | None,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    """
    If two or more abilities share the same cost *structure* (especially the
    'Once per X; 1 hour meditation to recharge' clone), rewrite later costs
    to distinct pool entries. Deterministic — no LLM required.
    """
    if not isinstance(abilities, list):
        return []
    out: list[dict[str, Any]] = []
    seen_fps: list[str] = []
    pool_i = 0
    clone_templates = {
        "HOUR_MEDITATION_RECHARGE",
        "ONCE_PER_X_PLUS_HOUR_MEDITATION_RECHARGE",
        "HOUR_RITUAL_RECHARGE",
        "ONCE_DAY_PLUS_HOUR",
        "MAINTAIN_HOUR_ENV_DAILY",
        "ONCE_PER_RANK",
        "ONCE_PER_RANK_BREATH_STAMINA",
        "ONCE_PER_RANK_PLUS_SHORT_CD",
        "BREATH_CONTROL_STAMINA_DRAIN",
    }
    # Count meditation-family hits to know if we must diversify
    fps_all = [_cost_structure_fingerprint(str(a.get("cost") or "")) for a in abilities if isinstance(a, dict)]
    med_count = sum(1 for fp in fps_all if fp in clone_templates)
    identical = len(set(fp for fp in fps_all if fp)) <= 1 and len(fps_all) >= 2

    for ab in abilities:
        if not isinstance(ab, dict):
            continue
        next_ab = dict(ab)
        cost = str(next_ab.get("cost") or "").strip()
        fp = _cost_structure_fingerprint(cost)
        must_replace = False
        if force and fp in seen_fps and fp:
            must_replace = True
        if fp in seen_fps and fp:
            must_replace = True
        if med_count >= 2 and fp in clone_templates and seen_fps and any(s in clone_templates for s in seen_fps):
            # Keep first meditation cost; diversify the rest
            must_replace = True
        if identical and seen_fps:
            must_replace = True
        if must_replace or (not cost and str(next_ab.get("power_type") or "").lower() != "passive"):
            # Pick a pool cost not already used
            used_text = {str(x.get("cost") or "").strip().lower() for x in out}
            pick = None
            for _ in range(len(_ABILITY_COST_VARIETY_POOL)):
                cand = _ABILITY_COST_VARIETY_POOL[pool_i % len(_ABILITY_COST_VARIETY_POOL)]
                pool_i += 1
                if cand.lower() not in used_text:
                    pick = cand
                    break
            if pick is None:
                pick = f"{_ABILITY_COST_VARIETY_POOL[pool_i % len(_ABILITY_COST_VARIETY_POOL)]} (variant {pool_i})."
                pool_i += 1
            next_ab["cost"] = pick
            next_ab["_cost_diversified"] = True
            fp = _cost_structure_fingerprint(pick)
        if fp:
            seen_fps.append(fp)
        out.append(next_ab)
    # Also diversify structured resource_cost shapes (mana/energy/fatigue/CD)
    try:
        from app.player_resources import diversify_resource_costs, magic_allows_mana

        magic_ok = magic_allows_mana(str((out[0] if out else {}).get("_magic_level") or ""), None)
        # Prefer caller context via env of first ability if stamped later; default True
        out = diversify_resource_costs(out, magic_ok=True, force=force)
    except Exception:
        pass
    # Prerequisite variety (same mentor/field line on every card)
    try:
        out = diversify_ability_prerequisites(out, force=force)
    except Exception:
        pass
    return out


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
            "Do not dilute an OP MC / compounding fantasy: if intent says a weak compounding seed, "
            "custom_skills must encode seed name/domain, start rank, tracking style, XP sources, "
            "and start-kit limits — not a permanent ban on later powers. Put concrete calculable growth_math "
            "that can snowball toward late OP (F…S/SS/SSS, risk mult, soft caps, breakthroughs, rank→bonus). "
            "Vague 'gets stronger over time' is not enough — invent numbers on growth_math.",
            "You may rewrite ability growth_math solely to add missing calculable math when fiction is fine.",
            "If special_abilities are present and OP MC fantasy, keep a thin opening kit (usually one compounding "
            "seed; optional locked passive); do not invent a free second combat toolkit at Start. "
            "Fiction may allow more powers later through play.",
            "When rewriting special_abilities, preserve or fill growth_math with concrete calculable formulas.",
            "Prefer concrete nouns and limits over adjectives like 'mysterious', 'ancient destiny', 'chosen'.",
            "Keep custom_skills as one comma-separated string (no bullets).",
            "STARTER GEAR + ORIGIN LOGIC: starter_equipment is what the player owns the instant Start is pressed. "
            "Origin, character_backstory, clothes, and kit must match world vibe as one package. "
            "If the destination is low-tech/fantasy isekai and the origin is modern/near-future tech life, "
            "rewrite origin/backstory into a local vocation (optional faint otherworld memory) and localize gear — "
            "do not leave a near-future maintenance tech hanging in a compound fantasy world. "
            "Pure isekai/summon with explicit just-arrived Earth life may keep Earth origin, but kit is thin "
            "(clothes + tiny pockets only — no free trade pack, no fantasy arsenal). "
            "Reincarnated/grew-up-here → this-life gear only. Native life → gear must fit their job/life. "
            "God gifts, quest rewards, system packages happen AFTER Start in play — never pre-seed them. "
            "If illogical, rewrite character_backstory and/or starter_equipment/appearance together.",
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
            "idea_sparks": prompt_sparks(compose_sparks),
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


def _field_contracts_for_prompt(return_fields: list[str]) -> dict[str, Any]:
    """
    The typed contract for each requested field, small enough to send.

    A multi-field group roll used to ship `return_fields` as a bare name list
    with no shape at all -- no return_shape, no contracts, nothing saying which
    fields are closed enums. Measured live over eight rolls, the model answered
    magic_level with "low", "Low", "low-magic", "post", and "Limited to arcane
    crafters and guilds"; every one of those falls through
    normalize_magic_level to its default, so the stored value was "rare" 12
    times out of 12 and race_magic_enabled barely moved off False.

    The contracts already existed and were already sent on the single-field and
    repair paths. This just stops the group path from being the one caller that
    asks a five-value enum an open question.
    """
    out: dict[str, Any] = {}
    for field in return_fields:
        try:
            contract = field_contract(field)
        except Exception:
            continue
        if not isinstance(contract, dict):
            continue
        slim = {"kind": contract.get("kind")}
        allowed = contract.get("allowed_values")
        if allowed:
            slim["allowed_values"] = list(allowed)
        forbidden = str(contract.get("forbidden") or "").strip()
        if forbidden:
            slim["forbidden"] = forbidden[:240]
        out[field] = slim
    return out


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
    # Ability origin UI removed — special_abilities always generate when requested.

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
            "task": (
                "Generate one personal/legal character name for the player character "
                "(what goes on papers and in formal address)."
            ),
            "forbidden_name": current_setup.get("player_name") or "Wanderer",
            "context": {
                "world_style": current_setup.get("world_style"),
                "player_sex": current_setup.get("player_sex"),
                "backstory_mode": current_setup.get("backstory_mode"),
            },
            "return_shape": {"player_name": "Given name, or Given + family name"},
            "name_rules": [
                "player_name is a real personal name: given name alone (Elena, Tomas) OR given + family (Mara Ellison, Corvin Hale).",
                "Prefer two-part names about half the time; single given names are fine when they sound like names, not handles.",
                "NOT a nickname, street handle, callsign, epithet, title, or compound fantasy moniker.",
                "Forbidden style examples: Ash, River, Patch, Northlight, Second Bell, the Red, Ashwalker, Wanderer, Shadow.",
                "Those belong in player_public_name or player_title — never here.",
                "No quotes, no ranks (Captain…), no 'the …', no pure nature-noun handles.",
                "Match world_style lightly (modern vs fantasy surnames) without becoming a joke name.",
                "Must differ from forbidden_name.",
            ],
            "rules": base_rules
            + [
                "Return only player_name in the JSON object.",
                "Use ordinary personal-name shape, not a nickname.",
            ],
        }
    elif return_fields == ["special_abilities"]:
        field_context = current_setup.get("_field_context") if isinstance(current_setup.get("_field_context"), dict) else {}
        field_context = dict(field_context or {})
        quantity_locked = bool(field_context.get("quantity_locked"))
        count_min, count_max = _ability_count_bounds(field_context)
        pf_early = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
        one_skillish_early = str(pf_early.get("growth") or "").lower() == "compounding" or str(
            pf_early.get("start_power") or ""
        ).lower() in {"near_useless", "weak"}
        # Roll target count once (or honor client roll) before asking the model.
        target_count = _roll_ability_count(field_context, one_skillish=one_skillish_early)
        field_context["target_count"] = target_count
        field_context["requested_count"] = target_count
        field_context["count_rolled"] = True
        current_setup["_field_context"] = field_context
        requested_count = target_count
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
        diversity_seed = random.randint(1000, 999999)
        # Catalog seeds are FALLBACK / spice only — model must invent first.
        sample_n = min(6, len(SEED_SKILL_DOMAIN_POOL))
        inspiration_only = [
            {
                "name": d.get("name"),
                # Clean player-facing effect only — never paste tier/lane tags into ability text.
                "effect_hint": d.get("hint"),
                "requires": d.get("requires") or "",
                "late_payoff_fiction": d.get("compounds_to") or "",
                "lane": d.get("lane"),
                "tier": d.get("tier"),
            }
            for d in random.sample(list(SEED_SKILL_DOMAIN_POOL), k=sample_n)
        ]
        prompt = {
            "task": (
                "Generate NEW setup special abilities. "
                "INVENT original powers first — exhaust creative variety on your own. "
                f"Diversity seed {diversity_seed}. "
                "A small inspiration_only list is optional spice if you are stuck; do NOT treat it as a menu. "
                "Outputs pass a quality gate (name, description, growth_math, cost, prerequisites)."
            ),
            "invention_first": True,
            "inspiration_only": inspiration_only,
            "inspiration_policy": (
                "Optional. Use at most as loose thematic spice. Prefer wholly original names/effects. "
                "Copying an inspiration name is a last resort when truly out of ideas."
            ),
            "ban_overused_domains": sorted(OVERUSED_SEED_DOMAINS),
            "quality_bar": {
                "name": "specific evocative name; not Ability/Power; not banned cliché domains",
                "description": "concrete playable hook (action + duration); put use-frequency in cost when a recharge also exists",
                "growth_math": "digits + XP/rank path a DM can apply; soft-cap/breakthrough for seeds",
                "cost": "real strain/resource; include once/day or recharge here consistently — no mismatch with description",
                "prerequisites": "required when locked=true",
                "stability": "no unlimited/omnipotent/auto-win",
                "cross_field": "description/cost/math timing facts must agree",
            },
            "quantity_locked": quantity_locked,
            # Server/client already rolled — model must return this exact count.
            "target_count": target_count,
            "requested_count": target_count,
            "count_min": count_min,
            "count_max": count_max,
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
                "custom_skills_hint": current_setup.get("custom_skills"),
            },
            "locked_setup": locked_setup,
            "return_shape": {
                "special_abilities": [
                    {
                        "name": "original ability name",
                        "description": "one concrete immutable base description with playable hook",
                        "locked": False,
                        "prerequisites": "unlock path when locked; else empty",
                        "cost": "concrete cost or drawback (not empty free god-mode)",
                        "growth_math": "playable XP/rank formulas with numbers",
                        "power_type": "compounding|passive|linear|soft_cap|breakthrough|flat|item_bound",
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
            "idea_sparks": prompt_sparks(idea_sparks_pkg),
            "rules": base_rules
            + [
                "Do not return the current abilities unchanged. Invent new names and descriptions.",
                "Never reuse must_not_reuse.names or paraphrase must_not_reuse.description_prefixes.",
                "INVENTION FIRST: create original domains and effects. Do not default to catalog seed names.",
                "inspiration_only is optional spice if stuck — not a required domain list.",
                "NEVER put design meta in description: no 'advanced tier', 'arcane lane', 'compounds toward:', 'When you try,'. Write fiction the player reads in play.",
                "Description = what the character can do now (weak/limited). Late payoff belongs in growth fiction/math, not as labeled meta tags.",
                "FACT-CHECK across description, cost, prerequisites, and growth_math: use limits must not contradict. "
                "Description = effect + duration; cost = that ability's own drawback or frequency — not a shared stamp.",
                "COST VARIETY (critical when returning 2+ abilities): each ability needs a DIFFERENT cost shape. "
                "BANNED clone spam: the same 'Once per rank/day; 1 hour of meditation to recharge after use' on every power. "
                "BANNED: 'You must spend 1 hour each day/dawn in [biome] to maintain this ability' with only the place swapped. "
                "At most ONE ability in a batch may use a long meditation recharge. Others must use different costs: "
                "short fatigue, scarce reagent, social debt, tool wear, noise, once-per-scene breathlessness, nosebleed, heat drain, attention cost.",
                "NO NEAR-DUPLICATES: each ability must use a different core action and effect lane "
                "(e.g. not two shields, two veil/stealth cloaks, two echo/distract sounds, or two generic buffs). "
                "If two powers would feel the same in play, replace the weaker one with a distinct domain.",
                "Do not use banned overused domains (Observation, knots/ropework, fabric/thread sense, barter, lie detection, footstep tracking, weather/sandstorm defaults).",
                "Obscure is good; unusable is not. Every ability needs a concrete turn-1 action or always-on effect with a limit.",
                "Spectrum is allowed: simple practical powers AND advanced lanes (summoning, necromancy, healing/support, weapon-bound arts, tool rites).",
                "If a power needs a tool/weapon/focus, state that in description or cost; F-rank clumsy, high ranks make the item legendary-adjacent.",
                "Focus on inventing distinct powers (name, description, cost, growth_math). Mix inherent and trained-feeling fiction as fits the world. The app assigns locked/prerequisites AFTER generation: stronger powers are more likely locked with unlock paths; weaker ones stay usable at Start. You may still set locked as a hint, but power level of the fiction matters more.",
                "When you set locked=true, prerequisites must be a real unlock path — but prefer leaving lock decisions to strength of the power text.",
                "Set power_type on each ability to one of: compounding, passive, linear, soft_cap, breakthrough, flat, item_bound.",
                "Passive = always-on (may omit activate cost but should note a drawback or rank limit); can still have growth_math ranks.",
                "Let backstory_mode and character_backstory decide ability source; do not force former-life power without support.",
                "If field_intent.power_fantasy.start_power is near_useless or weak, abilities should start locked or extremely modest; compounding toward late OP belongs to later play, not opening god-mode.",
                "If growth is compounding / OP MC fantasy and quantity is not locked: prefer ONE weak seed ability when count_min allows 1; if count_max≥2 you may add one locked passive domain expression. Never exceed count_max. Opening kit is thin — more powers may unlock later in play, not at Start.",
                "ALWAYS fill growth_math with concrete calculable rules (especially OP compounding). Include a path toward high ranks (S/SS/SSS) with soft caps and breakthroughs. Empty growth_math fails the quality gate.",
                "Cost and prerequisites will be quality-checked for stability — no unlimited free power.",
                "If custom_skills_hint names a seed, you may align — still invent original fiction, do not paste slogans.",
            ],
        }
        # Count is decided by RNG (or quantity lock) before this prompt — never "pick 4 because max is 4".
        prompt["rules"] = prompt["rules"] + [
            f"Return exactly {max(1, int(target_count))} special_abilities entries, no more and no fewer. "
            f"That count was rolled randomly in [{count_min}, {count_max}]"
            + (" (quantity lock)" if quantity_locked else " (RNG)")
            + ". Do not invent a different count."
        ]
        if one_skillish:
            prompt["rules"] = prompt["rules"] + [
                "This is an OP MC / weak-start run: keep the opening kit modest in power "
                f"even though you must still return exactly {max(1, int(target_count))} abilities."
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
            "backstory_mode": (
                "Return ONLY one short label from: known, hidden, fragmented memories, reincarnated, transmigrated, "
                "nameless drifter, amnesia. Never write a sentence here. "
                "Use reincarnated when they grew up in this world after rebirth. "
                "Use transmigrated for same-day portal/summon/truck/body-drop into this world. "
                "Do not default to tragedy, destiny, noble bloodline, or revenge."
            ),
            "memory_policy": (
                "Return ONLY one short phrase from: ordinary memory, remembers former life, former life fragments, "
                "details emerge through choices, rumors may be wrong, private details stay private. "
                "For transmigrated same-day drops, prefer remembers former life or former life fragments. "
                "For reincarnated childhood, prefer former life fragments."
            ),
            "character_backstory": (
                "Generate 2-4 concise third-person sentences of actual character history (use they/their, never I/my). "
                "INVENT a FRESH job, city, death/transport method, and arrival detail every roll — do NOT reuse stock clones. "
                "BANNED stock motifs (never use): Seoul warehouse, expired coffee, half-eaten bento, coin that always lands heads, "
                "collapsing ceiling + blue light, dust-covered alley + rusted wrench, Neo-Silicon, Iron Spire, night-shift forklift clones, "
                "freight and labels, schedules and sore feet, bent pair of glasses, 'no free hero kit', "
                "'not as a native already living a local plot', work-yard fence line, dirt-road-at-the-edge clones. "
                "Vary former jobs: teacher, nurse, courier, cook, clerk, student, hotel desk, bike delivery, florist, radio host, janitor — not always warehouse/freight. "
                "Vary transport: fall, medical emergency, summon, portal, train, ferry, fire — not always truck accident. "
                "IMPORTANT: backstory_mode 'transmigrated' means TRANSPORT from another life/world — not a native fantasy biography. "
                "For transmigrated REQUIRED structure: (1) concrete life BEFORE transport (job, place, ordinary stakes in the former world); "
                "(2) HOW they were transported (death, truck, summon ritual, portal, body-drop); "
                "(3) start at the moment of arrival or the hours just before — not already living as a local merchant/exile mid-plot. "
                "Do NOT write disgraced nobles, festival guests, or local coup exiles as if they were always from this world. "
                "Do NOT paste skill names, weak-seed blurbs, compounding, or ability rules into the backstory. "
                "ONE coherent stance on magic. Match world_style. No chosen-one, free hero kit, or revenge-by-default. "
                "Return a single prose string (not a JSON list of sentences)."
            ),
            "hair": (
                "Hair ONLY: length + color + style in one short phrase "
                "(e.g. messy copper curls, cropped black hair, white undercut). "
                "No eyes, jaw, freckles, scars, or clothes. "
                "Do NOT reuse current_setup.hair if present — invent a different look. "
                "Avoid always defaulting to silver/cropped/grey tired face tropes."
            ),
            "facial_features": (
                "Face ONLY: eyes, freckles, scars, jaw, brows, marks — 2–5 short phrases. "
                "NEVER include hair (no 'cropped silver hair', braids, ponytails). "
                "No clothing. No personality essays. "
                "Do NOT return the overused stack 'grey eyes, tired lids, square jaw'. "
                "Do NOT reuse current_setup.facial_features — pick a fresh face."
            ),
            "appearance": (
                "Clothing / worn gear ONLY. Prefer zone tags: "
                "'torso: travel coat; feet: dusty boots'. "
                "Do NOT put hair or facial features here. "
                "Do NOT reuse current_setup.appearance if present. "
                "Portraits only use upper-body zones. Weak starts: ordinary clothes."
            ),
            "starter_equipment": (
                "Comma-separated mundane starting items at Start (inventory). "
                "3–6 items matching THIS character's job/arrival — invent a fresh kit every roll. "
                "BANNED as default every time: rusted wrench + copper coins + worn satchel + rain-slicked hoodie + scuffed sneakers stack. "
                "Do NOT always include copper coins or a wrench. Vary tools, bags, and clothes with the job. "
                "Isekai/modern arrival may keep a cracked/dead phone, keys, ID badge, wallet, or transit card — phones are fine as dead pocket tech. "
                "Fantasy natives: no modern phones; use local tools. Near-useless starts: no combat kit/legendaries. Match appearance."
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
                "Never default to weather/observation/sandstorm/knot-work/ropework/fabric/barter/lie-detection/footsteps. "
                "Pick a fresh practical domain each roll. Use commas between phrases. "
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
            ],
        }
        # Diversity seeds stop 8B from welding one stock clone across re-rolls
        if field == "character_backstory":
            prompt["diversity_seed"] = random.randint(1000, 999999)
            prompt["ban_stock_motifs"] = [
                "Seoul warehouse",
                "expired coffee",
                "half-eaten bento",
                "coin that always lands heads",
                "collapsing ceiling + blue light",
                "dust-covered alley + rusted wrench",
            ]
            prompt["rules"] = list(prompt.get("rules") or []) + [
                f"Diversity seed {prompt['diversity_seed']}: invent a NEW job/city/transport/arrival — never the banned stock motifs.",
                "Return one prose string, not a list of sentences.",
            ]
            mode_l = str(current_setup.get("backstory_mode") or "").lower()
            if "transmigrat" in mode_l or bool(intent_plan.get("isekai")):
                prompt["rules"] = list(prompt.get("rules") or []) + [
                    "End the backstory at NEW-WORLD arrival (or hours just before). "
                    "Do not leave the character still living their Earth job as the playable present.",
                    "start_location (if known) is the arrival site — match the final sentence to that place type.",
                    "Play Start = moment of teleport/death-wake in the new world — never previous-life workplace.",
                ]
        if field == "starter_equipment":
            prompt["diversity_seed"] = random.randint(1000, 999999)
            prompt["ban_default_kit"] = [
                "rusted wrench",
                "copper coins always",
                "worn satchel + rain-slicked hoodie + scuffed sneakers stack",
            ]
            try:
                from app.setup_composer import STARTER_KIT_SEED_POOL

                prompt["kit_seeds_inspiration_only"] = random.sample(
                    list(STARTER_KIT_SEED_POOL), k=min(4, len(STARTER_KIT_SEED_POOL))
                )
            except Exception:
                pass
            prompt["rules"] = list(prompt.get("rules") or []) + [
                f"Diversity seed {prompt['diversity_seed']}: fresh mundane kit matching role; phones/keys/ID ok for modern isekai.",
                "Do not return the same wrench+coins+satchel kit every time.",
            ]
        if field == "start_location":
            mode_l = str(current_setup.get("backstory_mode") or "").lower()
            idea_l = str(current_setup.get("_randomize_idea") or intent_plan.get("raw_idea") or "").lower()
            isekaiish = (
                "transmigrat" in mode_l
                or bool(intent_plan.get("isekai"))
                or any(m in idea_l for m in ("isekai", "transmigrat", "truck", "another world"))
            )
            if isekaiish:
                try:
                    from app.setup_composer import (
                        detect_location_theme,
                        pick_isekai_arrival_location,
                    )

                    prompt["diversity_seed"] = random.randint(1000, 999999)
                    theme_id = detect_location_theme(
                        world_style=str(current_setup.get("world_style") or ""),
                        genre=str(intent_plan.get("genre") or current_setup.get("world_style") or ""),
                        idea=str(idea_l or ""),
                        session_theme=intent_plan if isinstance(intent_plan, dict) else None,
                    )
                    # A theme id is a label, not a name to copy. The arrival
                    # BANK deliberately does not ship: six real entries used to
                    # go out as `arrival_location_seeds`, and ~44% of live
                    # arrival names came back a verbatim member of the list the
                    # model had just been shown. theme_hint below carries the
                    # shape without naming a single place, and the banks stay
                    # where they are load-bearing -- the offline floor below.
                    prompt["arrival_location_theme"] = theme_id
                    theme_hint = {
                        # "prison of light" was spelled out here and is itself a
                        # literal entry in the celestial bank -- the hint was
                        # leaking a name while the seeds key was being removed.
                        "celestial": "heavens/afterlife names for a place of confinement, blank map, no free movement",
                        "cyberpunk": "neon megacity / corpo / undercity arrival names",
                        "steampunk": "brass, airship, gaslamp, clockwork arrival names",
                        "wasteland": "scrap, ash, bunker, radiation-fence arrival names",
                        "space": "station airlock / hab / docking ring arrival names",
                        "noir": "rainy city crime-scene arrival names",
                        "undersea": "pressure lock / coral / trench arrival names",
                        "arctic": "ice road / glacier outpost arrival names",
                        "desert": "dune / oasis / caravanserai arrival names",
                        "gothic": "manor / crypt / chapel arrival names",
                        "fantasy": "gate / yard / pier / road-cut arrival names",
                        # No theme matched the setting. Do NOT hand this world a
                        # fantasy hint -- that default is what opened superhero
                        # and heist games at a gate-town. Ask for a name built
                        # from the setting the player actually described.
                        "generic": (
                            "a plain threshold drawn from THIS setting's own vocabulary — "
                            "wherever someone would first set foot in it"
                        ),
                    }.get(theme_id, "arrival names that fit the setting described")
                    prompt["rules"] = list(prompt.get("rules") or []) + [
                        "Isekai/transmigrated: start_location MUST be the NEW-WORLD arrival site "
                        f"matching theme '{theme_id}' ({theme_hint}) — NEVER Seoul/warehouse/office/"
                        "apartment/hospital on Earth.",
                        "Play begins the moment they arrive/die-and-wake — not mid previous-life shift.",
                        "Build the arrival name out of this setting's own vocabulary: two to four "
                        "words naming a threshold someone could stand in. Do not reuse a name from "
                        "any other world you have seen.",
                    ]
                    if theme_id == "celestial":
                        prompt["rules"].append(
                            "Celestial/heavens starts: the player is confined — map is blank and "
                            "they cannot walk free until the story changes confinement."
                        )
                    # There used to be a `prompt["_fallback_arrival_location"]`
                    # here holding one real bank entry. Nothing ever read it --
                    # grep found the write and no consumer anywhere in app/,
                    # static/, tools/ or tests/. Its only effect was to put a
                    # bank name in front of the model on every isekai roll. The
                    # genuine offline floors are elsewhere and do not go through
                    # the prompt at all: `_setup_field_fallback` (llm.py, the
                    # LLM-unavailable path) and `resolve_start_location`
                    # (setup_composer.py), both calling the same picker.
                except Exception:
                    pass
        if field == "appearance":
            try:
                from app.setup_composer import APPEARANCE_SEED_POOL

                prompt["diversity_seed"] = random.randint(1000, 999999)
                prompt["clothing_seeds_inspiration_only"] = random.sample(
                    list(APPEARANCE_SEED_POOL), k=min(5, len(APPEARANCE_SEED_POOL))
                )
                prompt["rules"] = list(prompt.get("rules") or []) + [
                    f"Diversity seed {prompt['diversity_seed']}: invent a fresh clothing set; "
                    "use zone tags; inspiration_only is optional spice not a required menu.",
                ]
            except Exception:
                pass
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
            "field_contracts": _field_contracts_for_prompt(return_fields),
            "character_identity_rules": [
                "player_name is the character's personal/legal name (Given, or Given + family). Not a nickname, handle, callsign, or epithet. Examples: Mara Ellison, Tomas Reed, Elena. Bad: Ash, River, Patch, the Red, Ashwalker, Wanderer.",
                "player_public_name is rare. Leave it blank by default; fill it only when the backstory implies an alias, public handle, former-world name, or name strangers would plausibly know. Nicknames and street names go here, not in player_name.",
                "player_title is rare. Leave it blank by default; fill it only when reputation, formal office, reincarnated former power, high strength, infamous deeds, or local rumors make a title more playable.",
                "player_age and player_sex are current-life descriptive identity fields. Prefer male/female for ordinary humanoids; rare exotic sex categories only when the world supports them. Keep them concise, and do not make them behavior constraints or stereotypes.",
                "previous_life_age and previous_life_sex are only for reincarnated, transmigrated, reborn, or former-life starts. Leave them blank for ordinary known, hidden, or nameless starts without former-life memory.",
                "Backstory mode affects both optional identity fields: reincarnated/transmigrated characters may carry former-world names or former-rank titles, while hidden/amnesia/nameless starts often stay blank unless the backstory gives NPC-facing clues.",
                "backstory_mode must be a short label (known/transmigrated/reincarnated/...), never a prose sentence.",
                "memory_policy must be a short phrase (ordinary memory / remembers former life / former life fragments/...), never a menu dump.",
                "character_backstory: third person only; 2-4 sentences.",
                "transmigrated = former-world life + transport method + start at arrival (or just before). Never a native-only fantasy plot with a bolted-on 'woke in another world' sentence.",
                "reincarnated = grew up in this world + former-life fragments. body transmigration = old mind in a local body.",
                "Prefer the word transmigrated for the mode; do not confuse the AI with using 'isekai' as the backstory_mode label.",
                "Do not write first-person diary voice (I/my). Do not invent chosen-one destiny or paste skill/compounding text into backstory.",
                "custom_skills and special_abilities should fit the concrete backstory, race rules, world rules, and any optional identity fields already generated.",
                "custom_skills must be one comma-separated string when present; never use bullets or newlines for proficiencies.",
                "special_abilities: use each card's locked + prerequisites for learned vs starting powers. Empty list means no special powers.",
            ],
            "rules": base_rules
            + [
                "Generate fields one at a time in the order requested. Later fields must fit earlier current_setup values.",
                "field_contracts is binding. When a field lists allowed_values, return one of those strings EXACTLY as written -- lowercase, no synonyms, no free text. 'low', 'low-magic', and 'limited to guilds' are all wrong for a field whose allowed_values are rare/forbidden/common utility/cultivation/none; pick the closest listed value instead.",
                "Boolean fields take true or false, not a label.",
            ],
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

    # Expand OP_MC_FRAME / legacy ONE_SKILL_FRAME when rolling custom_skills
    if not text_mode and return_fields == ["custom_skills"]:
        cur_skills = str(current_setup.get("custom_skills") or "")
        pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
        one_skillish = (
            "OP_MC_FRAME" in cur_skills
            or "ONE_SKILL_FRAME" in cur_skills
            or str(pf.get("growth") or "").lower() == "compounding"
            or str(pf.get("start_power") or "").lower() in {"near_useless", "weak"}
        )
        if one_skillish and isinstance(prompt, dict):
            abilities = current_setup.get("special_abilities")
            ability_hint = ""
            ability_name = ""
            if isinstance(abilities, list) and abilities:
                a0 = abilities[0] if isinstance(abilities[0], dict) else {}
                ability_name = str(a0.get("name") or "").strip()
                ability_hint = f"{ability_name}: {str(a0.get('description') or '')[:120]}"
            # Align with ability if present; otherwise invent — catalog is inspiration only.
            inspire = pick_seed_skill_domain(
                avoid=[ability_name] if ability_name else None,
                world_style=str(current_setup.get("world_style") or ""),
                genre=str((intent_plan.get("genre") if isinstance(intent_plan, dict) else "") or ""),
                salt=f"custom_skills|{time.time_ns()}|{current_setup.get('player_name') or ''}",
            )
            prompt["task"] = (
                "Expand skill fiction rules for an OP MC / compounding seed run into a rich custom_skills string. "
                "Invent original skill fiction first. Leave long XP formulas for ability growth_math. "
                "If a seed ability already exists, align the skill name with it."
            )
            prompt["invention_first"] = True
            prompt["inspiration_only"] = [inspire] if inspire else []
            prompt["ban_overused_domains"] = sorted(OVERUSED_SEED_DOMAINS)
            prompt["quality_bar"] = {
                "lead": "weak seed skill: <Name>",
                "must_not": "OP_MC_FRAME skeleton alone; Observation/knots/barter clichés",
                "must_include": "rank F start, tracking style, XP sources in prose, late compounding path",
            }
            prompt["one_skill_expansion"] = {
                "seed_ability_if_any": ability_hint,
                "must_include": [
                    "exact seed skill/domain name (original, or aligned to seed ability)",
                    "starting rank/power (near-useless / F / level 1)",
                    "how compounding evolves toward late OP in fiction (not permanently weak)",
                    "how the DM or system tracks rank/level",
                    "how XP or progress is earned (practice, mentors, risk, breakthroughs) — prose, not formula tables",
                    "passives allowed (always-on ranks) as domain expressions",
                    "opening kit is thin (no free second combat toolkit at Start); more powers may unlock later in play",
                ],
                "math_home": "Put calculable XP/rank/OP-snowball formulas on special_abilities[].growth_math when abilities are rolled, not here.",
            }
            prompt["rules"] = list(prompt.get("rules") or []) + [
                "Output a single comma-separated custom_skills string (no bullets).",
                "Lead with 'weak seed skill: <Name>' using an original or ability-aligned name.",
                "Invent first; inspiration_only is optional spice if stuck — not a required menu.",
                "Never use banned overused domains from ban_overused_domains as the seed name.",
                "Do not invent a free multi-skill combat kit at Start; later unlocks are fine to foreshadow.",
                "Be concrete and tabletop-playable.",
            ]

    if idea_sparks_pkg and isinstance(prompt, dict) and idea_sparks_pkg.get("sparks"):
        # Inject once for all field groups (abilities already set earlier; others get it here).
        prompt.setdefault("idea_sparks", prompt_sparks(idea_sparks_pkg))
    try:
        result = _chat_json(
            "Return JSON only. Generate direct values. Do not explain. Do not echo the request.",
            json.dumps(prompt, ensure_ascii=True),
            timeout=_model_timeout(45, 240, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
            phase="setup_randomize",
            max_tokens=token_cap,
        )
        validated = _validate_setup_randomization(group, result, current_setup)
    except Exception as first_exc:
        # Small local models often break ability JSON shape — fall back instead of hard-failing setup.
        if return_fields == ["special_abilities"]:
            validated = {"special_abilities": _fallback_special_abilities(current_setup)}
        else:
            raise first_exc
    if not text_mode and return_fields == ["player_name"]:
        current_name = str(current_setup.get("player_name") or "").strip().lower()
        generated_name = str(validated.get("player_name") or "").strip()
        if current_name and generated_name.lower() == current_name:
            retry_prompt = {
                "task": "Generate one new personal/legal RPG character name (Given or Given + family).",
                "forbidden_name": current_setup.get("player_name"),
                "return_shape": {"player_name": "new personal name that is not a nickname"},
                "name_rules": [
                    "Not a nickname/handle/epithet (Ash, River, Patch, the Red, Ashwalker are forbidden).",
                    "Prefer names like Elena Croft, Tomas Reed, or Mira.",
                ],
            }
            validated = _validate_setup_randomization(
                group,
                _chat_json(
                    "Return JSON only. Create a different personal name, not a nickname. Do not explain.",
                    json.dumps(retry_prompt, ensure_ascii=True),
                    timeout=_model_timeout(30, 120, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                    phase="setup_randomize_name_retry",
                    max_tokens=80,
                ),
            )
        # Always clamp nickname-style model output to a real personal name.
        validated["player_name"] = _sanitize_player_name(
            validated.get("player_name"),
            forbidden=str(current_setup.get("player_name") or ""),
        )
    elif not text_mode and return_fields == ["character_backstory"]:
        # Quality gate: invent → verify → retry on deny → diversified bank fallback
        # (same shape as special_abilities quality_gate_abilities).
        from app.setup_composer import (
            _normalize_backstory_prose,
            quality_gate_backstory,
        )

        mode_for_story = str(
            current_setup.get("backstory_mode") or validated.get("backstory_mode") or ""
        )
        idea_s = str(
            current_setup.get("_randomize_idea")
            or (intent_plan or {}).get("raw_idea")
            or ""
        )
        world_s = str(current_setup.get("world_style") or "")
        mem_s = str(current_setup.get("memory_policy") or validated.get("memory_policy") or "")
        transmig = "transmigrat" in mode_for_story.lower() or bool(
            (intent_plan or {}).get("isekai")
        )
        denials: list[dict[str, Any]] = []
        quality_source = "llm"
        diversity_seed = random.randint(1000, 999999)
        current_story = _normalize_backstory_prose(validated.get("character_backstory"))
        validated["character_backstory"] = current_story

        for attempt in range(1, BACKSTORY_QUALITY_MAX_ATTEMPTS + 1):
            gate = quality_gate_backstory(
                current_story,
                mode=mode_for_story,
                idea=idea_s,
                world_style=world_s,
                memory_policy=mem_s,
                rejected="" if attempt == 1 else current_story,
                auto_repair=False,  # invent-first; fallback only after max attempts
                seed=diversity_seed + attempt,
            )
            if gate.get("ok"):
                quality_source = "llm" if attempt == 1 else f"llm_retry_{attempt}"
                validated["character_backstory"] = _normalize_backstory_prose(
                    gate.get("story") or current_story
                )
                validated["quality_gate"] = {
                    "ok": True,
                    "source": quality_source,
                    "attempt": attempt,
                    "score": gate.get("score"),
                    "denials": denials,
                    "kind": "character_backstory",
                }
                break
            rep = gate.get("report") if isinstance(gate.get("report"), dict) else {}
            denials.append(
                {
                    "attempt": attempt,
                    "score": gate.get("score"),
                    "denial_summary": gate.get("denial_summary") or [],
                    "hard_fail": rep.get("hard_fail") or [],
                    "soft": rep.get("soft") or [],
                }
            )
            if attempt >= BACKSTORY_QUALITY_MAX_ATTEMPTS:
                # Exhausted invent/retry — diversified bank / repair fallback (like ability seed pool).
                final_gate = quality_gate_backstory(
                    current_story,
                    mode=mode_for_story or ("transmigrated" if transmig else "known"),
                    idea=idea_s,
                    world_style=world_s,
                    memory_policy=mem_s,
                    rejected=current_story,
                    auto_repair=True,
                    seed=diversity_seed + 99,
                )
                validated["character_backstory"] = _normalize_backstory_prose(
                    final_gate.get("story") or current_story
                )
                validated["quality_gate"] = {
                    "ok": bool(final_gate.get("ok")),
                    "source": final_gate.get("source") or "fallback_transmigration_bank",
                    "attempt": attempt,
                    "score": final_gate.get("score"),
                    "denials": denials,
                    "reason": "quality_denied_max_attempts",
                    "kind": "character_backstory",
                    "denial_summary": final_gate.get("denial_summary") or [],
                }
                quality_source = str(final_gate.get("source") or "fallback")
                break
            # Another invent pass with concrete denial feedback
            retry_prompt = _backstory_quality_retry_prompt(
                denied=gate,
                mode=mode_for_story,
                idea=idea_s,
                world_style=world_s,
                rejected=current_story,
                attempt=attempt,
                transmig=transmig,
                nearby_setup=prompt.get("nearby_setup") if isinstance(prompt, dict) else current_setup,
            )
            try:
                retried = _validate_setup_randomization(
                    group,
                    _chat_json(
                        "Return JSON only. Create a fresh concrete character history that passes the quality gate — not a synonym of the rejected clone.",
                        json.dumps(retry_prompt, ensure_ascii=True),
                        timeout=_model_timeout(30, 180, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                        phase="setup_randomize_backstory_retry",
                        max_tokens=360,
                    ),
                    current_setup,
                )
                current_story = _normalize_backstory_prose(
                    retried.get("character_backstory") or current_story
                )
                validated["character_backstory"] = current_story
            except Exception:
                # Keep current_story; next loop may fallback
                pass
        else:
            # for-else: loop completed without break (shouldn't with range max)
            pass
    elif not text_mode and (
        return_fields == ["special_abilities"]
        or group == "special_abilities"
        or (len(return_fields) == 1 and return_fields[0] == "special_abilities")
    ):
        existing = (
            current_setup.get("special_abilities")
            if isinstance(current_setup.get("special_abilities"), list)
            else []
        )
        fc = current_setup.get("_field_context") if isinstance(current_setup.get("_field_context"), dict) else {}
        origin = "both"
        pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
        one_skillish = str(pf.get("growth") or "").lower() == "compounding" or str(
            pf.get("start_power") or ""
        ).lower() in {"near_useless", "weak"}
        count_min, count_max = _ability_count_bounds(fc)
        target_count = _roll_ability_count(fc, one_skillish=one_skillish)
        # Persist roll so retries / fallback / validate all share the same target.
        fc = dict(fc)
        fc["target_count"] = target_count
        fc["requested_count"] = target_count
        fc["count_rolled"] = True
        current_setup["_field_context"] = fc
        denials: list[dict[str, Any]] = []
        quality_source = "llm"
        # Quality gate: invent → verify → retry on deny → seed-pool fallback after 2–3 denials.
        for attempt in range(1, ABILITY_QUALITY_MAX_ATTEMPTS + 1):
            generated = validated.get("special_abilities")
            gen_list = generated if isinstance(generated, list) else []
            gen_list = _enforce_ability_count(gen_list, target_count, current_setup=current_setup)
            validated["special_abilities"] = gen_list
            # Duplicate of current form is an automatic quality deny.
            if _abilities_match_existing(gen_list, existing):
                gate = {
                    "ok": False,
                    "score": 0,
                    "abilities": gen_list,
                    "reports": [],
                    "denial_summary": ["duplicate_of_existing_abilities"],
                }
            else:
                gate = quality_gate_abilities(
                    gen_list,
                    existing=existing,
                    one_skillish=one_skillish,
                    origin=origin,
                    require_strong_math=True,
                )
            if gate.get("ok"):
                quality_source = "llm" if attempt == 1 else f"llm_retry_{attempt}"
                validated["special_abilities"] = gate.get("abilities") or gen_list
                validated["quality_gate"] = {
                    "ok": True,
                    "source": quality_source,
                    "attempt": attempt,
                    "score": gate.get("score"),
                    "denials": denials,
                }
                break
            denials.append(
                {
                    "attempt": attempt,
                    "score": gate.get("score"),
                    "denial_summary": gate.get("denial_summary") or [],
                    "reports": [
                        {
                            "name": r.get("name"),
                            "score": r.get("score"),
                            "hard_fail": r.get("hard_fail"),
                            "soft": r.get("soft"),
                        }
                        for r in (gate.get("reports") or [])[:6]
                    ],
                }
            )
            if attempt >= ABILITY_QUALITY_MAX_ATTEMPTS:
                # Prefer keeping individually-passing inventions over wiping the whole batch.
                salvaged: list[dict[str, Any]] = []
                for rep in gate.get("reports") or []:
                    if not rep.get("ok"):
                        continue
                    ab = rep.get("ability")
                    if isinstance(ab, dict) and str(ab.get("name") or "").strip():
                        salvaged.append(dict(ab))
                # Also accept repaired list entries that pass a solo re-check
                if not salvaged:
                    for ab in gate.get("abilities") or gen_list:
                        if not isinstance(ab, dict):
                            continue
                        solo = evaluate_ability_quality(
                            ab,
                            existing=existing,
                            one_skillish=one_skillish,
                            origin=origin,
                            require_strong_math=True,
                        )
                        if solo.get("ok"):
                            salvaged.append(dict(ab))
                if salvaged:
                    validated = {
                        "special_abilities": _enforce_ability_count(
                            salvaged, target_count, current_setup=current_setup
                        ),
                        "quality_gate": {
                            "ok": True,
                            "source": f"llm_salvage_after_{attempt}",
                            "attempt": attempt,
                            "denials": denials,
                            "reason": "salvaged_passing_abilities",
                            "score": gate.get("score"),
                            "target_count": target_count,
                        },
                    }
                    quality_source = "llm_salvage"
                else:
                    # Exhausted invent/retry budget — curated seed-pool fallbacks.
                    validated = {
                        "special_abilities": _enforce_ability_count(
                            _fallback_special_abilities(current_setup),
                            target_count,
                            current_setup=current_setup,
                        ),
                        "quality_gate": {
                            "ok": True,
                            "source": "fallback_seed_pool",
                            "attempt": attempt,
                            "denials": denials,
                            "reason": "quality_denied_max_attempts",
                            "target_count": target_count,
                        },
                    }
                    quality_source = "fallback_seed_pool"
                break
            # Another invent pass with concrete denial feedback (not fallback yet).
            retry_prompt = _ability_quality_retry_prompt(
                denied=gate,
                existing=existing,
                origin=origin,
                intent_plan=intent_plan,
                attempt=attempt,
                count_min=target_count,
                count_max=target_count,
            )
            if isinstance(retry_prompt, dict):
                retry_prompt["target_count"] = target_count
                retry_prompt["rules"] = list(retry_prompt.get("rules") or []) + [
                    f"Return exactly {target_count} special_abilities — count was pre-rolled; do not change it."
                ]
            try:
                validated = _validate_setup_randomization(
                    group,
                    _chat_json(
                        "Return JSON only. Fix quality denials with original inventions.",
                        json.dumps(retry_prompt, ensure_ascii=True),
                        timeout=_model_timeout(30, 180, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                        phase="setup_randomize_abilities_quality_retry",
                        max_tokens=700,
                    ),
                    current_setup,
                )
            except Exception:
                # Model failed mid-retry — count as denial and continue toward fallback.
                validated = {"special_abilities": []}
        # Soft polish only after quality pass / fallback (never mask a failed gate).
        abilities_out = validated.get("special_abilities")
        if isinstance(abilities_out, list):
            # Always break clone costs (meditation-hour spam) before further polish.
            abilities_out = diversify_ability_costs(abilities_out, force=False)
            # Fallback path may already have math; LLM path must already be calculable.
            force_fill = quality_source == "fallback_seed_pool"
            polished = _ensure_ability_growth_math(abilities_out, force_fill=force_fill)
            if quality_source != "fallback_seed_pool":
                polished = _maybe_optimize_ability_growth_math(
                    polished,
                    intent_plan=intent_plan,
                    current_setup=current_setup,
                )
                # Re-check once after optimize — if polish broke quality, keep pre-optimize.
                re_gate = quality_gate_abilities(
                    polished,
                    existing=existing,
                    one_skillish=one_skillish,
                    origin=origin,
                    require_strong_math=True,
                )
                if re_gate.get("ok"):
                    validated["special_abilities"] = re_gate.get("abilities") or polished
                else:
                    validated["special_abilities"] = abilities_out
            else:
                validated["special_abilities"] = polished

            # Cross-check: near-duplicates → rework weaker → remake → re-check (rinse/repeat).
            try:
                dedupe = ensure_distinct_abilities(
                    validated.get("special_abilities") if isinstance(validated.get("special_abilities"), list) else [],
                    existing=existing,
                    origin=origin,
                    one_skillish=one_skillish,
                    world_style=str(current_setup.get("world_style") or ""),
                    max_rounds=ABILITY_DEDUPE_MAX_ROUNDS,
                    use_llm=True,
                )
                if isinstance(dedupe.get("abilities"), list) and dedupe["abilities"]:
                    # Final quality pass after dedupe swaps
                    post = quality_gate_abilities(
                        dedupe["abilities"],
                        existing=existing,
                        one_skillish=one_skillish,
                        origin=origin,
                        require_strong_math=True,
                        auto_repair=True,
                    )
                    if post.get("ok"):
                        validated["special_abilities"] = post.get("abilities") or dedupe["abilities"]
                    else:
                        # Keep distinct set even if soft quality dips; avoid reintroducing near-dups
                        validated["special_abilities"] = dedupe["abilities"]
                    if isinstance(validated.get("quality_gate"), dict):
                        validated["quality_gate"]["dedupe"] = {
                            "ok": bool(dedupe.get("ok")),
                            "rounds": dedupe.get("rounds"),
                            "log": dedupe.get("log") or [],
                            "pairs_remaining": dedupe.get("pairs_remaining") or [],
                        }
            except Exception as dedupe_exc:
                if isinstance(validated.get("quality_gate"), dict):
                    validated["quality_gate"]["dedupe_error"] = str(dedupe_exc)[:200]

            # Final hard enforce of the pre-rolled count
            validated["special_abilities"] = _enforce_ability_count(
                validated.get("special_abilities") if isinstance(validated.get("special_abilities"), list) else [],
                target_count,
                current_setup=current_setup,
            )
            # After powers exist: roll lock count, lock strongest, set prereqs only on those
            try:
                validated["special_abilities"] = assign_ability_locks_after_creation(
                    validated.get("special_abilities") if isinstance(validated.get("special_abilities"), list) else [],
                    origin=origin,
                )
            except Exception:
                pass
            if isinstance(validated.get("quality_gate"), dict):
                validated["quality_gate"]["final_count"] = len(validated["special_abilities"] or [])
                validated["quality_gate"]["target_count"] = target_count
                locked_n = sum(
                    1
                    for a in (validated.get("special_abilities") or [])
                    if isinstance(a, dict) and a.get("locked")
                )
                validated["quality_gate"]["locked_count"] = locked_n
            validated["ability_count_roll"] = {
                "target": target_count,
                "min": count_min,
                "max": count_max,
                "quantity_locked": bool(fc.get("quantity_locked")),
                "locked_count": sum(
                    1
                    for a in (validated.get("special_abilities") or [])
                    if isinstance(a, dict) and a.get("locked")
                ),
            }

    elif not text_mode and return_fields == ["custom_skills"]:
        # Quality-ensure expanded skill fiction; fall back to seed-pool prose after denials.
        pf = intent_plan.get("power_fantasy") if isinstance(intent_plan.get("power_fantasy"), dict) else {}
        one_skillish = (
            str(pf.get("growth") or "").lower() == "compounding"
            or str(pf.get("start_power") or "").lower() in {"near_useless", "weak"}
            or "op_mc_frame" in str(current_setup.get("custom_skills") or "").lower()
            or "one_skill_frame" in str(current_setup.get("custom_skills") or "").lower()
        )
        abilities = (
            current_setup.get("special_abilities")
            if isinstance(current_setup.get("special_abilities"), list)
            else []
        )
        denials_cs: list[dict[str, Any]] = []
        for attempt in range(1, ABILITY_QUALITY_MAX_ATTEMPTS + 1):
            text = str(validated.get("custom_skills") or "").strip()
            gate = evaluate_custom_skills_quality(text, abilities=abilities, one_skillish=one_skillish)
            # Always enforce a minimum quality bar (not only OP-MC frames).
            thin_non_seed = (not one_skillish) and (len(text) < 80 or text.count(",") >= 5 and len(text) < 160)
            if gate.get("ok") and not thin_non_seed:
                validated["quality_gate"] = {
                    "ok": True,
                    "source": "llm" if attempt == 1 else f"llm_retry_{attempt}",
                    "attempt": attempt,
                    "score": gate.get("score"),
                    "denials": denials_cs,
                }
                break
            denials_cs.append(
                {
                    "attempt": attempt,
                    "score": gate.get("score"),
                    "hard_fail": list(gate.get("hard_fail") or []) + (["custom_skills_thin_keyword_dump"] if thin_non_seed else []),
                    "soft": gate.get("soft"),
                }
            )
            if attempt >= ABILITY_QUALITY_MAX_ATTEMPTS:
                if one_skillish or not text or thin_non_seed:
                    validated["custom_skills"] = _fallback_custom_skills_from_domain(current_setup)
                    validated["quality_gate"] = {
                        "ok": True,
                        "source": "fallback_seed_pool",
                        "attempt": attempt,
                        "denials": denials_cs,
                        "reason": "quality_denied_max_attempts",
                    }
                else:
                    validated["quality_gate"] = {
                        "ok": True,
                        "source": "llm_kept_after_denials",
                        "attempt": attempt,
                        "denials": denials_cs,
                        "score": gate.get("score"),
                    }
                break
            retry_cs = {
                "task": (
                    f"QUALITY DENIAL #{attempt} for custom_skills. Expand into concrete skill fiction. "
                    + (
                        "Invent first; do not leave OP_MC_FRAME skeleton."
                        if one_skillish
                        else "Write playable skill rules as a readable comma-separated string (not a keyword dump)."
                    )
                ),
                "failed": gate,
                "seed_ability_if_any": (
                    f"{abilities[0].get('name')}: {str(abilities[0].get('description') or '')[:120]}"
                    if abilities and isinstance(abilities[0], dict)
                    else ""
                ),
                "ban_overused_domains": sorted(OVERUSED_SEED_DOMAINS),
                "return_shape": {"custom_skills": "comma-separated skill fiction string"},
                "rules": (
                    [
                        "Lead with 'weak seed skill: <OriginalName>'.",
                        "Include F-rank start, tracking style, XP sources in prose, late compounding path.",
                        "No Observation/knots/barter/lie-detect seed names.",
                        "Output custom_skills only as one string.",
                    ]
                    if one_skillish
                    else [
                        "Write 1-3 concrete skill rules or training paths in a single comma-separated string.",
                        "Each clause should be a full phrase (not bare keywords like 'system UI, risk').",
                        "Mention how skills grow (practice, mentors, reputation) without dumping rank tables here.",
                        "Output custom_skills only as one string.",
                    ]
                ),
            }
            try:
                validated = _validate_setup_randomization(
                    group,
                    _chat_json(
                        "Return JSON only. Fix custom_skills quality denials.",
                        json.dumps(retry_cs, ensure_ascii=True),
                        timeout=_model_timeout(30, 180, "AI_RPG_SETUP_RANDOMIZER_TIMEOUT"),
                        phase="setup_randomize_custom_skills_quality_retry",
                        max_tokens=640,
                    ),
                    current_setup,
                )
            except Exception:
                validated = {"custom_skills": ""}
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
    if not text_mode:
        normalized = _drop_echoed_custom_style(return_fields, current_setup, intent_plan, normalized)
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


def _drop_echoed_custom_style(
    return_fields: list[str],
    current_setup: dict[str, Any],
    intent_plan: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    custom_style must add something world_style did not already say.

    Twice in twelve measured rolls the model put one idea-card title in both
    slots -- world_style AND custom_style were each "Grimdark mud calculus",
    then each "system-apocalypse UI weather". custom_style is the prose field
    for world constraints and DM stance, so a verbatim restatement of the genre
    phrase leaves the setup with nothing where its stance should be.

    The structural fallback is a real improvement here rather than a downgrade:
    it keeps the style as the setting frame and appends the stance the field
    exists to carry.
    """
    if "custom_style" not in result:
        return result
    style = str(result.get("world_style") or current_setup.get("world_style") or "").strip().lower()
    custom = str(result.get("custom_style") or "").strip().lower()
    if not style or not custom or custom != style:
        return result
    context = {**current_setup, **result, "_compose_intent": intent_plan}
    replacement = structural_fallback("custom_style", context)
    if not replacement:
        return result
    return {**result, "custom_style": replacement}


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


def _backstory_quality_retry_prompt(
    *,
    denied: dict[str, Any],
    mode: str,
    idea: str,
    world_style: str,
    rejected: str,
    attempt: int,
    transmig: bool,
    nearby_setup: Any = None,
) -> dict[str, Any]:
    """Prompt the model to invent again after a backstory quality denial (not stamp the freight template)."""
    rep = denied.get("report") if isinstance(denied.get("report"), dict) else {}
    hard = list(rep.get("hard_fail") or denied.get("denial_summary") or [])
    soft = list(rep.get("soft") or [])
    ban = list(
        {
            "Seoul warehouse",
            "expired coffee",
            "half-eaten bento",
            "coin that always lands heads",
            "collapsing ceiling",
            "blue light",
            "dust-covered alley",
            "rusted wrench",
            "freight and labels",
            "bent pair of glasses",
            "no free hero kit",
            "schedules and sore feet",
            "work-yard fence line",
            "night shifts moving freight",
            "not as a native already living a local plot",
            "which rules of this world can kill them",
            *list(rep.get("stock_motifs") or []),
        }
    )
    return {
        "task": (
            f"QUALITY DENIAL #{attempt}: previous character_backstory failed the quality gate. "
            "Invent a FRESH concrete life — different job, transport, arrival place, and pocket props. "
            "Do NOT paraphrase the rejected_backstory or stamp the freight/truck/dirt-road template."
        ),
        "denial_summary": denied.get("denial_summary") or hard,
        "hard_fail": hard,
        "soft": soft,
        "diversity_seed": random.randint(1000, 999999),
        "backstory_mode": mode or ("transmigrated" if transmig else "known"),
        "rejected_backstory": str(rejected or "")[:500],
        "ban_motifs": ban,
        "idea": str(idea or "")[:400],
        "world_style": str(world_style or "")[:200],
        "nearby_setup": nearby_setup,
        "return_shape": {"character_backstory": "2-4 concise third-person sentences as ONE string"},
        "required_details": (
            [
                "concrete former-world job NEVER used in rejected_backstory (teacher, nurse, cook, courier, clerk, florist, radio host, janitor, stagehand…)",
                "HOW they were transported (vary: fall, medical, summon, portal, train, ferry — not always truck/freight)",
                "start at NEW-WORLD arrival with different pocket props",
                "no skill names, compounding, weak seed, or ability rules",
                "no 'no free hero kit' / 'freight and labels' / 'bent pair of glasses' boilerplate",
            ]
            if transmig
            else [
                "fresh birthplace and livelihood",
                "why they are near the starting point",
                "no banned stock motifs",
            ]
        ),
        "quality_bar": {
            "person": "third person they/their only",
            "length": "2-4 sentences, ≥140 characters",
            "transmigrated": "former life + transport + arrival place required",
            "forbidden": "stock clones, skill meta, first person, native fantasy plot for isekai",
        },
        "rules": [
            "Third person only (they/their).",
            "Do NOT paraphrase rejected_backstory with synonym swaps.",
            "Return prose string only, not a JSON list of sentences.",
            "Fix every hard_fail from the denial.",
        ],
    }


def _backstory_is_too_vague(backstory: str, *, mode: str = "") -> bool:
    text = backstory.strip().lower()
    if len(text) < 140:
        return True
    # Skill / progression dumps are not character history
    if any(
        m in text
        for m in (
            "weak seed",
            "seed skill",
            "compounding",
            "growth math",
            "guest right",
            "xp_to_next",
            "rank f",
        )
    ):
        return True
    # Internal stance clashes fail quality (magic tool vs not wizardry, etc.)
    try:
        from app.setup_composer import backstory_self_contradictions

        if not bool(backstory_self_contradictions(backstory).get("ok")):
            return True
    except Exception:
        pass
    mode_l = str(mode or "").lower()
    if "transmigrat" in mode_l:
        try:
            from app.setup_composer import transmigration_story_score

            return not bool(transmigration_story_score(backstory).get("ok"))
        except Exception:
            pass
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
    transition_markers = {"arrived", "left", "sent", "reached", "came", "fled", "returned", "woke", "now", "died", "summon"}
    has_origin = any(marker in text for marker in origin_markers)
    has_prior_life = any(marker in text for marker in life_markers)
    has_transition = any(marker in text for marker in transition_markers)
    return not (has_origin and has_prior_life and has_transition)


def _validate_setup_randomization(
    group: str,
    result: dict[str, Any],
    current_setup: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        allowed_power_types = {
            "compounding",
            "passive",
            "linear",
            "soft_cap",
            "breakthrough",
            "flat",
            "item_bound",
        }
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
            power_type = str(ability.get("power_type") or "").strip().lower().replace("-", "_").replace(" ", "_")
            if power_type in {"softcap", "soft_capped"}:
                power_type = "soft_cap"
            if power_type in {"item", "itembound", "gear_bound", "gear"}:
                power_type = "item_bound"
            if power_type in {"one_skill", "oneskill", "compound", "op_mc", "opmc"}:
                power_type = "compounding"
            if power_type in {"aura", "always_on", "always-on", "passive_aura"}:
                power_type = "passive"
            if power_type not in allowed_power_types:
                power_type = "linear"
            ability["power_type"] = power_type
            cleaned_abilities.append(ability)
        # Clamp to the same 1–4 range / lock policy the UI uses (Simple + Advanced).
        setup = current_setup if isinstance(current_setup, dict) else {}
        field_context = setup.get("_field_context") if isinstance(setup.get("_field_context"), dict) else {}
        # Honor pre-rolled target (RNG min–max or quantity lock). Never leave "always max".
        target = _roll_ability_count(field_context, one_skillish=False)
        cleaned_abilities = _enforce_ability_count(
            cleaned_abilities,
            target,
            current_setup=setup,
        )
        result["ability_count_roll"] = {
            "target": target,
            "min": _ability_count_bounds(field_context)[0],
            "max": _ability_count_bounds(field_context)[1],
            "quantity_locked": bool(field_context.get("quantity_locked")),
        }
        result["special_abilities"] = cleaned_abilities

    # Drop legacy special_ability_origin if a model still returns it.
    result.pop("special_ability_origin", None)

    result = _sanitize_setup_randomization_values(result)
    # Hair / face / clothes: strip cross-field contamination and overused stacks.
    if any(k in result for k in ("hair", "facial_features", "appearance")):
        look_ctx = dict(current_setup or {})
        look_ctx.update({k: result.get(k) for k in ("hair", "facial_features", "appearance") if k in result})
        look_out, _look_dirty = normalize_look_fields(
            {k: result[k] for k in ("hair", "facial_features", "appearance") if k in result},
            context=look_ctx,
        )
        result.update(look_out)
        # If model echoed the current face/hair, force a different fallback pool pick.
        for look_key in ("hair", "facial_features", "appearance"):
            if look_key not in result:
                continue
            cur = str((current_setup or {}).get(look_key) or "").strip().lower()
            got = str(result.get(look_key) or "").strip().lower()
            if cur and got and cur == got:
                pool = list(SETUP_RANDOMIZER_FALLBACKS.get(look_key) or [])
                alt = [p for p in pool if str(p).strip().lower() != cur]
                if alt:
                    result[look_key] = random.choice(alt)
            # Ban the classic collapse face
            if look_key == "facial_features" and "grey eyes, tired lids, square jaw" in got:
                pool = list(SETUP_RANDOMIZER_FALLBACKS.get("facial_features") or [])
                alt = [p for p in pool if "tired lids" not in str(p).lower()]
                result[look_key] = random.choice(alt) if alt else "hazel eyes, faint laugh lines, straight nose"
    return result


def _sanitize_setup_randomization_values(result: dict[str, Any]) -> dict[str, Any]:
    """Clamp 8B slop: bools-as-strings, enums, instruction echoes, growth slogans in structure fields."""
    if not isinstance(result, dict):
        return result
    out = dict(result)

    # player_name: personal/legal name only — not handles/nicknames/epithets
    if "player_name" in out:
        out["player_name"] = _sanitize_player_name(out.get("player_name"))

    # character_backstory: join list dumps + kill stock Seoul/warehouse clones
    if "character_backstory" in out:
        try:
            from app.setup_composer import (
                _normalize_backstory_prose,
                backstory_has_overused_motifs,
                build_transmigration_backstory,
            )

            story = _normalize_backstory_prose(out.get("character_backstory"))
            if backstory_has_overused_motifs(story):
                story = build_transmigration_backstory(
                    old_story="",
                    idea=str(out.get("_randomize_idea") or ""),
                    world_style=str(out.get("world_style") or ""),
                    seed=random.randint(1, 10**9),
                )
            out["character_backstory"] = story
        except Exception:
            pass

    # starter_equipment: break the wrench+coins+satchel+hoodie stone kit
    if "starter_equipment" in out:
        out["starter_equipment"] = _diversify_starter_equipment(out.get("starter_equipment"))

    # start_location: never previous-life workplace for isekai/transmigrated
    if "start_location" in out or "backstory_mode" in out or "character_backstory" in out:
        try:
            from app.setup_composer import ensure_isekai_start_location

            loc_in = str(out.get("start_location") or "")
            loc_fixed, changed = ensure_isekai_start_location(
                loc_in,
                backstory_mode=str(out.get("backstory_mode") or ""),
                idea=str(out.get("_randomize_idea") or ""),
                world_style=str(out.get("world_style") or ""),
                genre=str(out.get("world_style") or ""),
                character_backstory=str(out.get("character_backstory") or ""),
                session_theme=out.get("session_theme") if isinstance(out.get("session_theme"), dict) else None,
            )
            if changed or (loc_fixed and "start_location" in out):
                out["start_location"] = loc_fixed
        except Exception:
            pass

    # Shared type coercion (bools, magic_level, difficulty, growth speeds, instruction echoes).
    out, _typed = coerce_typed_setup_fields(out)

    # Extra bool defaults if coercion saw UI labels without a contract hit.
    for bkey in (
        "leveling_system",
        "game_system",
        "proficiency_system",
        "skill_levels_enabled",
        "race_magic_enabled",
    ):
        if bkey in out and not isinstance(out[bkey], bool):
            out[bkey] = coerce_setup_bool(out[bkey], default=False)

    if "magic_level" in out:
        out["magic_level"] = normalize_magic_level(out.get("magic_level"), default="rare")

    # memory_policy: one phrase, not a menu dump
    if "memory_policy" in out:
        mp = str(out["memory_policy"] or "").strip()
        if is_instruction_echo(mp) or mp.count(",") >= 3 or mp.count(";") >= 2 or len(mp) > 100:
            out["memory_policy"] = "known"

    # death_rules slogans / instruction echo
    if "death_rules" in out:
        dr = str(out["death_rules"] or "")
        low = dr.lower()
        if is_instruction_echo(dr) or "scar economy" in low or "compound" in low:
            out["death_rules"] = "downed, not deleted"

    # system_style: bool echoes or slogan paste
    if "system_style" in out:
        ss = str(out.get("system_style") or "").strip()
        if is_instruction_echo(ss) or ss.lower() in {"true", "false", "yes", "no", "on", "off"}:
            out["system_style"] = "subtle blue-window system" if out.get("game_system") else ""

    # special abilities: keep model lock flags; batch lock assignment runs elsewhere
    if isinstance(out.get("special_abilities"), list):
        cleaned = [dict(ab) for ab in out["special_abilities"] if isinstance(ab, dict)]
        out["special_abilities"] = cleaned

    # Align custom_skills weakly with first ability name if empty/slogan (g14 soft)
    if isinstance(out.get("special_abilities"), list) and out["special_abilities"]:
        first = out["special_abilities"][0]
        aname = str(first.get("name") or "").strip()
        cs = str(out.get("custom_skills") or "").strip()
        if aname and (
            not cs
            or is_instruction_echo(cs)
            or any(m in cs.lower() for m in ("one-skill", "compounding", "seed frame"))
        ):
            out["custom_skills"] = f"{aname} practice, modest seed, ranks through use"[:200]

    return out


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
        # Prefer coded entity refs so the UI can make them clickable (Name [[L1]] / Name [[I2]])
        loc_obj = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
        loc_name = str(loc_obj.get("name") or location or "the road").strip()
        loc_code = str(loc_obj.get("code") or "L1").strip().upper() or "L1"
        place_ref = f"{loc_name} [[{loc_code}]]" if loc_name else f"[[{loc_code}]]"
        inv_bits: list[str] = []
        for it in (context.get("inventory") or [])[:6]:
            if not isinstance(it, dict):
                continue
            iname = str(it.get("name") or "").strip()
            icode = str(it.get("code") or "").strip().upper()
            if iname and icode:
                inv_bits.append(f"{iname} [[{icode}]]")
            elif iname:
                inv_bits.append(iname)
        gear_bit = ""
        if inv_bits:
            if len(inv_bits) == 1:
                gear_bit = f" What you still carry is plain: {inv_bits[0]}."
            else:
                gear_bit = (
                    " What you still carry is plain: "
                    + ", ".join(inv_bits[:-1])
                    + f", and {inv_bits[-1]}."
                )
        npc_bits: list[str] = []
        for npc in (context.get("npcs") or [])[:4]:
            if not isinstance(npc, dict):
                continue
            nname = str(npc.get("name") or "").strip()
            ncode = str(npc.get("code") or "").strip().upper()
            if nname and ncode and re.fullmatch(r"[A-Z]{1,3}", ncode):
                npc_bits.append(f"{nname} [[{ncode}]]")
            elif nname:
                npc_bits.append(nname)
        # Also scan nested location cast
        for loc in context.get("locations") or []:
            if not isinstance(loc, dict):
                continue
            for npc in loc.get("npcs") or []:
                if not isinstance(npc, dict) or len(npc_bits) >= 4:
                    continue
                nname = str(npc.get("name") or "").strip()
                ncode = str(npc.get("code") or "").strip().upper()
                label = f"{nname} [[{ncode}]]" if nname and ncode else nname
                if label and label not in npc_bits:
                    npc_bits.append(label)
        people_bit = ""
        if npc_bits:
            people_bit = (
                " Nearby faces or voices you can already pin to a name: "
                + ", ".join(npc_bits[:3])
                + "."
            )
        system_bit = ""
        if opts.get("game_system"):
            style = str(opts.get("system_style") or "subtle blue-window system")
            seed = opts.get("weak_skill_seed") if isinstance(opts.get("weak_skill_seed"), dict) else {}
            seed_name = str(seed.get("name") or pick_seed_skill_domain(salt=f"open|{location}").get("name") or "Digging")
            seed_val = seed.get("value", 1)
            system_bit = (
                f"\n\nFor a heartbeat the world overlays a thin {style} edge — nothing loud, only readable:\n"
                f"[ STATUS ] Location: {place_ref}\n"
                f"[ SKILL  ] {seed_name} … rank F / value {seed_val} (nearly useless)\n"
                "[ NOTE   ] No combat suite. Grow through practice and risk.\n"
                "The window fades as quickly as it arrived, leaving only the ordinary street and that one thin promise of growth."
            )
        elif isinstance(opts.get("weak_skill_seed"), dict):
            seed = opts["weak_skill_seed"]
            seed_name = str(seed.get("name") or pick_seed_skill_domain(salt=f"open2|{location}").get("name") or "Digging")
            system_bit = (
                f"\n\nSomething in you recognizes a faint aptitude — {seed_name} — "
                "so slight it barely counts, a thin practical habit rather than a power."
            )
        narration = (
            f"{place_ref} comes into focus without waiting for a command. Damp air gathers at the edges of the street, "
            "voices move behind closed doors, and something nearby is just unresolved enough to invite a first choice. "
            "The first details are practical rather than grand: where the ground is slick, where the nearest shelter or exit might be, "
            "who seems busy enough to ignore trouble, and which small sound keeps tugging attention back toward the center of the scene. "
            f"{pressure}"
            f"{gear_bit}{people_bit}"
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


def ambient_llm_enabled(settings: dict[str, Any] | None = None) -> bool:
    """
    Optional short ambient LLM for free map steps.
    Off by default — enable with AI_RPG_AMBIENT_LLM=1 or settings.ambient_llm=true.
    """
    if _env_bool("AI_RPG_AMBIENT_LLM", False):
        return True
    if isinstance(settings, dict):
        raw = settings.get("ambient_llm")
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str) and raw.strip().lower() in {"1", "true", "yes", "on"}:
            return True
    return False


def generate_ambient_move_line(
    template: str,
    *,
    travel: dict[str, Any] | None = None,
    weather: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> str:
    """
    Optional micro-narration for free walking. Returns plain text (no JSON).
    Fails soft: returns the template on any error or when disabled.
    Never invents combat, loot, inventory, or blocking scenes.
    """
    base = re.sub(r"\s+", " ", str(template or "").strip())
    if not ambient_llm_enabled(settings):
        return base
    travel = travel if isinstance(travel, dict) else {}
    weather = weather if isinstance(weather, dict) else {}
    facts = {
        "template_facts": base,
        "terrain": travel.get("terrain") or "",
        "from_terrain": travel.get("from_terrain") or "",
        "minutes": int(travel.get("minutes") or 0),
        "settlement": (travel.get("settlement") or {}).get("name")
        if isinstance(travel.get("settlement"), dict)
        else "",
        "weather": weather.get("label") or weather.get("kind") or "",
        "base_discovered": bool(travel.get("base_discovered")),
    }
    system = (
        "You write one short ambient DM line for free map movement in a tabletop RPG. "
        "Plain text only. One or two sentences, under 220 characters. "
        "Ground the line in the provided facts. Do not invent combat, loot, inventory, "
        "quest outcomes, blocking scenes, or new named NPCs. No JSON, no quotes wrapper."
    )
    user = json.dumps({"task": "ambient_move_line", "facts": facts}, ensure_ascii=True)
    try:
        raw = _chat_text(
            system,
            user,
            timeout=_model_timeout(20, 60, "AI_RPG_AMBIENT_TIMEOUT"),
            phase="ambient_move",
            max_tokens=_env_int("AI_RPG_AMBIENT_TOKENS", 90),
            temperature=0.65,
        )
    except Exception:
        return base
    line = re.sub(r"\s+", " ", str(raw or "").strip().strip("\"'"))
    # Strip accidental labels / JSON wrappers
    if line.startswith("{") and "ambient" in line.lower():
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                line = str(parsed.get("ambient") or parsed.get("text") or parsed.get("line") or line)
                line = re.sub(r"\s+", " ", line.strip().strip("\"'"))
        except Exception:
            pass
    for prefix in ("Ambient:", "DM:", "Narration:", "Line:"):
        if line.lower().startswith(prefix.lower()):
            line = line[len(prefix) :].strip()
    if len(line) > 280:
        line = line[:280].rsplit(" ", 1)[0].rstrip(" ,.;:-") or line[:280]
    # Reject empty, combat-y, or inventory hallucinations vs empty template
    if not line or len(line) < 8:
        return base
    lower = line.lower()
    banned = (
        "you draw",
        "you attack",
        "you kill",
        "you fight",
        "in your inventory",
        "you gain",
        "loot:",
        "quest complete",
        "level up",
        "[[",
    )
    if any(b in lower for b in banned):
        return base
    return line


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


def _entity_code_name_map(context: dict[str, Any] | None, turn: dict[str, Any] | None = None) -> dict[str, str]:
    """code -> display name for NPCs/locations/items/events (world + this turn's creates)."""
    out: dict[str, str] = {}

    def add(code: Any, name: Any, title: Any = None) -> None:
        c = str(code or "").strip().upper()
        if not c:
            return
        label = str(name or title or "").strip()
        if not label:
            return
        # Prefer first non-empty name; don't overwrite with empties
        if c not in out:
            out[c] = label

    ctx = context if isinstance(context, dict) else {}
    for loc in ctx.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        add(loc.get("code"), loc.get("name"))
        for npc in loc.get("npcs") or []:
            if isinstance(npc, dict):
                add(npc.get("code"), npc.get("name"))
        for ev in loc.get("events") or []:
            if isinstance(ev, dict):
                add(ev.get("code"), ev.get("title") or ev.get("name"))
    cur = ctx.get("current_location")
    if isinstance(cur, dict):
        add(cur.get("code"), cur.get("name"))
    for key in ("inventory", "events", "npcs"):
        for item in ctx.get(key) or []:
            if not isinstance(item, dict):
                continue
            add(item.get("code"), item.get("name") or item.get("title"))
    # Working set / shells often carry the live cast for this beat
    for key in ("nearby_npcs", "shells", "npcs"):
        bucket = (ctx.get("working_set") or {}).get(key) if isinstance(ctx.get("working_set"), dict) else None
        if not isinstance(bucket, list):
            bucket = ctx.get(key) if key in {"shells", "npcs"} else None
        for item in bucket or []:
            if isinstance(item, dict):
                add(item.get("code"), item.get("name") or item.get("title"))
    draft = turn if isinstance(turn, dict) else {}
    for key in ("locations", "npcs", "events", "index_updates"):
        for item in draft.get(key) or []:
            if not isinstance(item, dict):
                continue
            add(item.get("code"), item.get("name") or item.get("title"))
            # index_updates use entity fields
            add(item.get("code"), item.get("name") or item.get("summary"))
    return out


def _strip_leaked_entity_html(text: str) -> str:
    """Remove accidental entity-button HTML that leaked into plain narration."""
    if not text:
        return text or ""
    # Fragments may lack '<' (broken mid-tag paste) — still clean type="button"
    if "<" not in text and "type=" not in text.lower() and "button" not in text.lower():
        return text
    out = text
    out = re.sub(
        r"<button\b[^>]*\bentityLink\b[^>]*>(.*?)</button>",
        r"\1",
        out,
        flags=re.I | re.S,
    )
    out = re.sub(
        r'([A-Za-z][A-Za-z0-9\' .\-]{1,60}?)\s+\1"\s*type="button">\1',
        r"\1",
        out,
        flags=re.I,
    )
    out = re.sub(r'["\']\s*type\s*=\s*["\']button["\']\s*>', " ", out, flags=re.I)
    out = re.sub(r"</?button\b[^>]*>", " ", out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def _collapse_repeated_entity_names(text: str, names: list[str]) -> str:
    """Collapse consecutive repeated entity labels."""
    out = text or ""
    for name in sorted({str(n).strip() for n in names if str(n or "").strip()}, key=len, reverse=True):
        if len(name) < 3:
            continue
        out = re.sub(
            rf"(?<![\w])(?:{re.escape(name)}\s+){{1,4}}{re.escape(name)}(?=[\w]*'s|[^\w]|$)",
            name,
            out,
            flags=re.IGNORECASE,
        )
    return out


def _inject_entity_codes_for_known_names(text: str, code_to_name: dict[str, str]) -> str:
    """
    When prose names a known place/NPC/item without [[code]], append the code once
    after each occurrence so the UI can link it:  Low Gate Timber Arch → … [[L1]]

    Longest names first. Skips very short / generic labels.
    """
    if not text or not code_to_name:
        return text or ""
    # Prefer first code for a given display name
    name_to_code: dict[str, str] = {}
    for code, name in code_to_name.items():
        c = str(code or "").strip().upper()
        n = str(name or "").strip()
        if not c or not n or len(n) < 3:
            continue
        if n.lower() in {
            "the street",
            "the road",
            "the room",
            "someone",
            "stranger",
            "unknown",
            "nearby street",
            "a worn item",
        }:
            continue
        key = n.lower()
        if key not in name_to_code:
            name_to_code[key] = c
    if not name_to_code:
        return text
    out = text
    for name_l, code in sorted(name_to_code.items(), key=lambda kv: -len(kv[0])):
        # Capture original casing from first match via re.I; don't double-append [[code]]
        # Look for name not already followed by [[same code]]
        pattern = re.compile(
            rf"(?<!\[\[)\b({re.escape(name_l)})\b(?!\s*\[\[{re.escape(code)}\]\])",
            flags=re.IGNORECASE,
        )

        def _repl(m: re.Match[str], _code: str = code) -> str:
            return f"{m.group(1)} [[{_code}]]"

        out = pattern.sub(_repl, out)
    # Collapse accidental "Name [[L1]] [[L1]]"
    out = re.sub(r"(\[\[(?:[A-Z]{1,3}|L\d+|I\d+|E\d+)\]\])(?:\s+\1)+", r"\1", out, flags=re.I)
    return out


def _repair_prose_entity_labels(text: str, code_to_name: dict[str, str]) -> str:
    """
    Fix common LLM naming holes:
    - bare [[A]] without a readable name -> Name [[A]]
    - known names without codes -> Name [[code]] (UI clickability)
    - blank subjects / possessives using ordered cast names

    Conservative: do NOT inject names before every mid-sentence stands/leans
    (that caused Name Name stands spam when a scenery label was cast as an NPC).
    """
    if not text or not isinstance(text, str):
        return text or ""
    code_to_name = {str(k).upper(): str(v).strip() for k, v in (code_to_name or {}).items() if str(v or "").strip()}

    repaired = _strip_leaked_entity_html(text)
    # Names known to the world but written without codes (opening often does this)
    repaired = _inject_entity_codes_for_known_names(repaired, code_to_name)

    def expand_code(match: re.Match[str]) -> str:
        full = match.group(0)
        code = match.group(1).upper()
        name = code_to_name.get(code, "")
        if not name:
            return full
        start = match.start()
        window = repaired[max(0, start - (len(name) + 8)) : start]
        if re.search(rf"{re.escape(name)}\s*$", window, flags=re.IGNORECASE):
            return full
        return f"{name} [[{code}]]"

    repaired = REFERENCE_CODE_PATTERN.sub(expand_code, repaired)

    npc_names = [
        code_to_name[c]
        for c in sorted(code_to_name.keys(), key=lambda x: (len(x), x))
        if re.fullmatch(r"[A-Z]{1,3}", c)
    ]
    ordered: list[str] = []
    for m in REFERENCE_CODE_PATTERN.finditer(repaired):
        n = code_to_name.get(m.group(1).upper(), "")
        if n and n not in ordered:
            ordered.append(n)
    for n in npc_names:
        if n not in ordered:
            ordered.append(n)

    name_i = 0

    def next_name() -> str:
        nonlocal name_i
        if name_i >= len(ordered):
            return ordered[0] if ordered else ""
        n = ordered[name_i]
        name_i += 1
        return n

    def fill_subject(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        verb = match.group(2)
        n = next_name()
        if not n:
            return match.group(0)
        if prefix.endswith("—") or prefix.endswith("–") or prefix.endswith("-"):
            return f"{prefix} {n} {verb}"
        return f"{prefix}{n} {verb}"

    repaired = re.sub(
        r"([—–]\s*|(?<=[.!?]\s)|^\s*)"
        r"(is|was|are|were|leans?|stands?|flicks?|watches?|glances?|smirks?|"
        r"grunts?|nods?|shakes?|steps?|moves?|turns?|says?|asks?|whispers?|"
        r"crosses|parts?|twitches?|darts?)\b",
        fill_subject,
        repaired,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    def fill_possessive(match: re.Match[str]) -> str:
        prefix = match.group(1) or ""
        n = next_name()
        if not n:
            return match.group(0)
        return f"{prefix}{n}'s"

    repaired = re.sub(
        r"([—–,\(]|(?<=\s\s)|^)(?:\s*)'s\b",
        fill_possessive,
        repaired,
        flags=re.MULTILINE,
    )
    repaired = _collapse_repeated_entity_names(repaired, ordered + list(code_to_name.values()))
    repaired = re.sub(r"[ \t]{2,}", " ", repaired)
    repaired = re.sub(r" +([,.;:!?])", r"\1", repaired)
    return repaired

def _repair_bare_code_possessives(
    text: str,
    *,
    code_map: dict[str, str] | None = None,
    item_codes: set[str] | None = None,
    place_codes: set[str] | None = None,
) -> str:
    """
    Models often dump bare codes as people: \"L1's allies or I1's rebels\".
    Expand place codes to names; never treat item codes as faction agents.
    """
    out = text or ""
    if not out:
        return out
    cmap = {str(k).upper(): str(v).strip() for k, v in (code_map or {}).items() if str(v or "").strip()}
    items = {str(c).upper() for c in (item_codes or set())}
    places = {str(c).upper() for c in (place_codes or set())}
    group_noun = (
        r"allies|rebels|men|women|crew|gang|forces|soldiers|band|faction|enemies|"
        r"friends|followers|people|side|sides|camp|company|party"
    )

    def repl(m: re.Match[str]) -> str:
        code = m.group(1).upper()
        group = m.group(2)
        # Item code used as faction head → drop code, keep group
        if code in items or re.fullmatch(r"I\d+", code):
            return f"the {group}"
        name = cmap.get(code, "")
        if name:
            # Places may keep a light possessive when they are locales
            if code in places or re.fullmatch(r"L\d+", code):
                return f"{name}'s {group}"
            # NPC codes: proper Name's group
            if re.fullmatch(r"[A-Z]{1,3}", code):
                return f"{name}'s {group}"
            return f"{name}'s {group}"
        # Unknown L# → soft place phrase
        if re.fullmatch(r"L\d+", code):
            return f"the inn's {group}" if group else m.group(0)
        if re.fullmatch(r"I\d+", code):
            return f"the {group}"
        return m.group(0)

    out = re.sub(
        rf"\b([A-Z]{{1,3}}|L\d+|I\d+|E\d+)(?:'s|’s)\s+({group_noun})\b",
        repl,
        out,
        flags=re.I,
    )
    # Bare place/item codes used as subjects (not inside [[ ]]) — expand or neutralize
    def bare_place_item(m: re.Match[str]) -> str:
        code = m.group(1).upper()
        start = m.start()
        window = out[max(0, start - 2) : start + len(m.group(0)) + 2]
        if "[[" in window or "]]" in window:
            return m.group(0)
        name = cmap.get(code, "")
        if re.fullmatch(r"L\d+", code):
            return f"{name} [[{code}]]" if name else m.group(0)
        if re.fullmatch(r"I\d+", code):
            return name if name else "a worn item"
        return m.group(0)

    out = re.sub(r"(?<!\[\[)\b(L\d+|I\d+)\b(?!\]\])", bare_place_item, out)
    return out


def _repair_gear_as_agent_prose(text: str, *, inventory_names: list[str] | None = None) -> str:
    """
    Fix classic 8B failures where wardrobe / gear is treated as a person or faction:
      "travel-stained coat's rebels" → "the rebels"
      "worn tool satchel's allies" → "the allies"
    Also rejoin split weapons: "cross, bow" / "cross bow" → "crossbow".
    """
    out = text or ""
    if not out:
        return out

    # Split compound weapons (common "cross, bow" → "crossbow")
    out = re.sub(r"\bcross\s*[,/]\s*bow\b", "crossbow", out, flags=re.I)
    out = re.sub(r"\bcross\s+bow\b", "crossbow", out, flags=re.I)
    out = re.sub(r"\bhilt of a\s+cross\b(?!\s*bow)", "hilt of a crossbow", out, flags=re.I)

    gear_head = (
        r"coat|cloaks?|jackets?|robes?|tunics?|vests?|shirts?|boots?|shoes?|gloves?|"
        r"hats?|hoods?|satchels?|bags?|packs?|pouches?|belts?|scabbards?|sheaths?|"
        r"swords?|daggers?|blades?|bows?|crossbows?|armor|armour|helms?|helmets?|"
        r"shields?|staves|staffs?|wands?|tankards?|mugs?|scrolls?|maps?"
    )
    group_noun = (
        r"allies|rebels|men|women|crew|gang|forces|soldiers|band|faction|enemies|"
        r"friends|followers|people|side|sides|camp|company|party"
    )
    # Multi-word gear phrase ending in a gear head noun, possessive + group
    # e.g. "travel-stained coat's rebels", "the frayed cloak's men"
    out = re.sub(
        rf"\b(?:the\s+|a\s+|an\s+)?"
        rf"(?:[\w\-]+[\s\-]+){{0,3}}(?:{gear_head})"
        rf"(?:'s|’s)\s+({group_noun})\b",
        r"the \1",
        out,
        flags=re.I,
    )
    # Bare "coat's rebels" without modifiers
    out = re.sub(
        rf"\b(?:{gear_head})(?:'s|’s)\s+({group_noun})\b",
        r"the \1",
        out,
        flags=re.I,
    )

    # Inventory item names used as agents: "Rusty Knife says" / "Rusty Knife's voice"
    for iname in sorted({str(n).strip() for n in (inventory_names or []) if str(n or "").strip()}, key=len, reverse=True):
        if len(iname) < 4:
            continue
        # Only rewrite when the item name looks like gear, not a proper person-like title
        try:
            from app.world import is_plausible_person_name

            if is_plausible_person_name(iname) and not re.search(
                r"\b(coat|cloak|boots?|satchel|sword|dagger|knife|bow)\b", iname, re.I
            ):
                continue
        except Exception:
            pass
        # Possessive group / voice / hand as if person
        out = re.sub(
            rf"(?<![\w]){re.escape(iname)}(?:'s|’s)\s+({group_noun}|voice|hand|eyes?|gaze|boot|bootheel)\b",
            lambda m, _n=iname: (
                f"the {m.group(1)}"
                if re.fullmatch(group_noun, m.group(1), flags=re.I)
                else f"its {m.group(1)}"
            ),
            out,
            flags=re.I,
        )
        # Agent verbs on pure gear names
        out = re.sub(
            rf"(?<![\w]){re.escape(iname)}(?=\s+(?:stands?|leans?|says?|asks?|watches?|glances?|"
            rf"smirks?|grunts?|nods?|whispers?|shouts?)\b)",
            "Someone",
            out,
            flags=re.I,
        )

    # "Choose your side—X's allies or Y's rebels" with gear already cleaned → tidy double "the"
    out = re.sub(r"\bthe\s+the\b", "the", out, flags=re.I)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out


def _repair_entity_names_in_turn(result: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministic name/code repair on narration after model output."""
    if not isinstance(result, dict):
        return result
    try:
        from app.world import invent_person_name, is_plausible_person_name, is_plausible_place_name, name_seed
    except Exception:
        invent_person_name = None  # type: ignore
        is_plausible_person_name = lambda n: bool(str(n or "").strip())  # type: ignore
        is_plausible_place_name = lambda n: bool(str(n or "").strip())  # type: ignore
        import hashlib as _hl
        # Still blake2b, not hash(): the fallback must stay reproducible too.
        name_seed = lambda *parts: int.from_bytes(  # type: ignore
            _hl.blake2b("|".join(str(p) for p in parts).encode("utf-8", "replace"), digest_size=8).digest(),
            "big",
        ) & 0x7FFFFFFFFFFFFFFF

    code_map = _entity_code_name_map(context, result)
    # Bad → good renames so we can rewrite prose (e.g. "System pings a local job" → "Ashwalker")
    rename_pairs: list[tuple[str, str]] = []

    inv_names: list[str] = []
    if isinstance(context, dict):
        for it in context.get("inventory") or []:
            if isinstance(it, dict) and it.get("name"):
                inv_names.append(str(it.get("name")))
    for ch in result.get("inventory_changes") or []:
        if isinstance(ch, dict) and ch.get("name"):
            inv_names.append(str(ch.get("name")))

    # Ensure draft NPCs always have a non-empty *plausible* person name.
    # Strip location/item codes (L1/I1) — those must never be people.
    cleaned_npcs: list[dict[str, Any]] = []
    for npc in result.get("npcs") or []:
        if not isinstance(npc, dict):
            continue
        npc = dict(npc)
        name = str(npc.get("name") or "").strip()
        code = str(npc.get("code") or "").strip().upper()
        role = str(npc.get("role") or "").strip().lower()
        # Misfiled place rows (common 8B bug: place lands in npcs[])
        if re.fullmatch(r"L\d+|I\d+|E\d+", code) and (
            not name
            or role in {"location", "place", "locale", "site", "inn", "gate", "road"}
            or not is_plausible_person_name(name)
        ):
            continue
        if re.fullmatch(r"L\d+|I\d+|E\d+", code):
            code = ""
            npc["code"] = ""
        if re.fullmatch(r"L\d+|I\d+|E\d+", name, re.I):
            name = ""
        if not name or not is_plausible_person_name(name):
            fallback = ""
            if code and code_map.get(code) and is_plausible_person_name(code_map[code]):
                fallback = code_map[code]
            elif invent_person_name is not None:
                fallback = invent_person_name(seed=name_seed(code, name, npc.get("role") or ""))
            else:
                fallback = f"Stranger {code}" if code and re.fullmatch(r"[A-Z]{1,3}", code) else "Stranger"
            if name and name != fallback:
                rename_pairs.append((name, fallback))
            npc["name"] = fallback
            if code and re.fullmatch(r"[A-Z]{1,3}", code):
                code_map[code] = fallback
        elif code and re.fullmatch(r"[A-Z]{1,3}", code):
            code_map.setdefault(code, name)
        cleaned_npcs.append(npc)
    result["npcs"] = cleaned_npcs

    # Locations: drop sentence-like toponyms (often copied from event titles)
    for loc in result.get("locations") or []:
        if not isinstance(loc, dict):
            continue
        lname = str(loc.get("name") or "").strip()
        if lname and not is_plausible_place_name(lname):
            # Prefer existing current location name from context
            cur = ""
            if isinstance(context, dict):
                cl = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
                cur = str(cl.get("name") or "").strip()
            new_name = cur if cur and is_plausible_place_name(cur) else "Nearby street"
            if lname != new_name:
                rename_pairs.append((lname, new_name))
            loc["name"] = new_name

    # Inventory rows: never keep outfit-prompt garbage as if it were a person (names stay as items)
    for ch in result.get("inventory_changes") or []:
        if not isinstance(ch, dict):
            continue
        iname = str(ch.get("name") or "").strip()
        # Underscore prompt tags → spaces for display items
        if "_" in iname and " " not in iname and not iname.startswith("<"):
            cleaned = iname.replace("_", " ")
            if cleaned != iname:
                rename_pairs.append((iname, cleaned))
                ch["name"] = cleaned
                inv_names.append(cleaned)

    item_codes: set[str] = set()
    place_codes: set[str] = set()
    if isinstance(context, dict):
        for it in context.get("inventory") or []:
            if isinstance(it, dict) and it.get("code"):
                item_codes.add(str(it.get("code")).upper())
        cl = context.get("current_location") if isinstance(context.get("current_location"), dict) else {}
        if cl.get("code"):
            place_codes.add(str(cl.get("code")).upper())
        for loc in context.get("locations") or []:
            if isinstance(loc, dict) and loc.get("code"):
                place_codes.add(str(loc.get("code")).upper())
    for loc in result.get("locations") or []:
        if isinstance(loc, dict) and loc.get("code"):
            place_codes.add(str(loc.get("code")).upper())
    for ch in result.get("inventory_changes") or []:
        if isinstance(ch, dict) and ch.get("code"):
            item_codes.add(str(ch.get("code")).upper())
    # Always treat I# pattern as items even without map
    item_codes |= {c for c in code_map if re.fullmatch(r"I\d+", c)}

    def rewrite_names(text: str) -> str:
        out = text or ""
        out = _repair_bare_code_possessives(
            out,
            code_map=code_map,
            item_codes=item_codes,
            place_codes=place_codes,
        )
        out = _repair_gear_as_agent_prose(out, inventory_names=inv_names)
        # Longest first so multi-word bad names replace cleanly
        for old, new in sorted(rename_pairs, key=lambda p: len(p[0]), reverse=True):
            if not old or old == new:
                continue
            # 1) Agent uses: "Name stands/leans/says..."
            out = re.sub(
                rf"(?<![\w]){re.escape(old)}(?=\s+(?:stands?|leans?|says?|asks?|watches?|"
                rf"glances?|smirks?|grunts?|nods?|shakes?|steps?|moves?|turns?|"
                rf"crosses|walks?|runs?|offers?|appears?)\b)",
                new,
                out,
                flags=re.IGNORECASE,
            )
            # 2) Possessive: Name's
            out = re.sub(
                rf"(?<![\w]){re.escape(old)}('s)\b",
                rf"{new}\1",
                out,
                flags=re.IGNORECASE,
            )
            # 3) Remaining bare mentions — skip determiner+object ("the X is your only view")
            #    so physical props keep reading as objects after a person rename.
            def _bare_repl(m: re.Match[str], _new: str = new) -> str:
                start = m.start()
                prev = out[max(0, start - 5) : start].lower()
                if re.search(r"\b(the|a|an)\s+$", prev):
                    return m.group(0)
                return _new

            out = re.sub(
                rf"(?<![\w]){re.escape(old)}(?=[\w]*'s|[^\w]|$)",
                _bare_repl,
                out,
                flags=re.IGNORECASE,
            )
        out = _repair_gear_as_agent_prose(out, inventory_names=inv_names)
        out = _repair_bare_code_possessives(
            out,
            code_map=code_map,
            item_codes=item_codes,
            place_codes=place_codes,
        )
        return out

    segments = result.get("narration_segments")
    if isinstance(segments, list) and segments:
        new_segments: list[Any] = []
        for seg in segments:
            if isinstance(seg, dict):
                text = rewrite_names(str(seg.get("text") or ""))
                text = _repair_prose_entity_labels(text, code_map)
                new_segments.append({**seg, "text": text})
            else:
                new_segments.append(seg)
        result["narration_segments"] = new_segments
        joined = "\n\n".join(
            str(s.get("text") or "") for s in new_segments if isinstance(s, dict)
        ).strip()
        if joined:
            result["narration"] = joined[:5600]
    elif result.get("narration"):
        text = rewrite_names(str(result.get("narration") or ""))
        result["narration"] = _repair_prose_entity_labels(text, code_map)[:5600]

    if result.get("turn_summary"):
        text = rewrite_names(str(result.get("turn_summary") or ""))
        result["turn_summary"] = _repair_prose_entity_labels(text, code_map)[:700]

    # Scene plan event labels can keep system-job wording; clean NPC-looking entries only
    plan = result.get("scene_plan") if isinstance(result.get("scene_plan"), dict) else None
    if plan and rename_pairs:
        for key in ("focus_points", "events", "notes"):
            items = plan.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    for field in ("summary", "title", "label", "text", "content"):
                        if item.get(field):
                            item[field] = rewrite_names(str(item.get(field)))
                elif isinstance(item, str):
                    pass

    self_check = result.get("self_check") if isinstance(result.get("self_check"), dict) else None
    if self_check is not None:
        corrections = self_check.setdefault("corrections_made", [])
        if isinstance(corrections, list):
            note = "Deterministic entity name/code repair applied to narration."
            if rename_pairs:
                note += " Replaced non-person labels: " + ", ".join(
                    f"{a!r}→{b!r}" for a, b in rename_pairs[:4]
                )
            corrections.append(note)
    return result


def _normalize_turn(result: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
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
    # Always run name repair (uses draft npcs even without full context)
    result = _repair_entity_names_in_turn(result, context)
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
        # Short narration is NOT a verifier blocker. Length is the depth
        # retry's job; the consistency verifier does not lengthen prose, and
        # on small models forcing it here cost ~26s per turn to produce
        # nothing. Measured on a 7B: verify+verify_repair fired on 42/42 turns
        # and never once returned a usable object. Keep the certainty penalty
        # so a short draft still leans toward verification when something
        # *else* is also shaky.
        reasons.append("Draft narration is short; depth retry handles length, not the verifier.")
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

    low_risk_keys = _nonempty_turn_keys(draft, LOW_RISK_TURN_CHANGE_KEYS)
    if low_risk_keys:
        reasons.append(f"Low-risk records present (not a blocker): {', '.join(low_risk_keys[:6])}")
        certainty -= 0.04

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


def _retry_narration_prose(
    context: dict[str, Any],
    player_input: str,
    turn: dict[str, Any],
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Ask only for longer prose, then splice it into the existing turn.

    The original depth retry asked for a complete replacement turn JSON. That
    had two failure modes, both observed on a 7B: the full turn schema does not
    fit in the response cap (it truncated mid-object every time, 18/18), and
    regenerating the whole turn risks losing the structured ops the draft had
    already produced.

    Prose is the smallest possible thing to ask for, cannot truncate into
    invalid JSON, and leaves every state change from the draft untouched.
    """
    existing = str(turn.get("narration") or "")
    plan = turn.get("scene_plan") if isinstance(turn.get("scene_plan"), dict) else {}
    instruction = "\n".join(
        [
            "Rewrite this scene as longer, richer prose. Return ONLY the prose.",
            "No JSON. No headers. No markdown fences. No commentary. Just the scene text.",
            "",
            f"Target about {TARGET_TURN_NARRATION_CHARS} characters, never below "
            f"{MIN_TURN_NARRATION_CHARS}, never above {MAX_TURN_NARRATION_CHARS}.",
            "Keep every fact, name, and [[CODE]] reference from the draft. Add sensory",
            "detail, NPC reaction, consequence, and concrete choices the player could take.",
            "Do not invent new rewards, items, or numbers. Do not decide the player's next action.",
            "",
            f"Scene goal: {str(plan.get('goal') or '')[:300]}",
            f"Player action: {str(player_input or '')[:300]}",
            "",
            "Draft scene to expand:",
            existing[:4000],
        ]
    )
    raw = _chat_text(
        system_prompt,
        instruction,
        timeout=timeout,
        usage=usage,
        phase=phase,
        max_tokens=max(_turn_max_tokens(context, "draft"), DEFAULT_RESPONSE_TOKEN_CAP),
        trace=trace,
    )
    prose = _clean_retry_prose(raw)
    if len(prose.strip()) <= len(existing.strip()):
        raise LlmError("Depth retry returned no additional prose.")
    return _splice_prose_into_turn(turn, prose)


def _splice_prose_into_turn(turn: dict[str, Any], prose: str) -> dict[str, Any]:
    """
    Replace only the narration on a turn, leaving every structured op intact.

    Honours the upper bound: asked for "longer", a 7B happily returned 3,351
    characters against a 2,400 ceiling, so trim on paragraph boundaries and the
    scene still ends on a complete beat rather than mid-sentence.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", str(prose or "").strip()) if p.strip()]
    kept: list[str] = []
    running = 0
    for para in paragraphs[:12]:
        if kept and running + len(para) > MAX_TURN_NARRATION_CHARS:
            break
        kept.append(para[:2800])
        running += len(para)
    if not kept:
        kept = [str(prose or "")[:MAX_TURN_NARRATION_CHARS]]

    expanded = dict(turn)
    expanded["narration"] = "\n\n".join(kept)[:MAX_TURN_NARRATION_CHARS]
    expanded["narration_segments"] = [{"label": "paragraph", "text": para} for para in kept]
    return expanded


def _clean_retry_prose(raw: str) -> str:
    """Strip anything the model wrapped around the prose despite being told not to."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    # Some models still emit the DSL markers or a JSON wrapper out of habit.
    for marker in ("===NAR===", "===NARRATION===", "@NAR"):
        if marker in text.upper():
            idx = text.upper().find(marker)
            text = text[idx + len(marker):]
    for marker in ("===OPS===", "@OPS"):
        idx = text.upper().find(marker)
        if idx >= 0:
            text = text[:idx]
    if text.lstrip().startswith("{"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return str(parsed.get("narration") or "").strip()
        except json.JSONDecodeError:
            pass
    return text.strip()


# Stock closers that hand the turn back to the player instead of resolving it.
# Deliberately narrow: only endings that carry no information, so deleting one
# can never lose a fact. Broader "you could X or Y" phrasings are left alone —
# those sometimes contain real detail, and a wrong cut costs more than a menu.
_MENU_CLOSER_RE = re.compile(
    r"^(?:"
    r"(?:the\s+)?(?:choice|decision|call)\s+is\s+yours\.?"
    r"|what\s+(?:will|do)\s+you\s+do(?:\s+next)?\??"
    # "Or do you continue your journey...?" — the second half of a two-part menu
    # arrives as its own sentence, so the leading conjunction must be allowed.
    r"|(?:(?:so|or|and)[,]?\s+)?(?:do|will|would)\s+you\s+\w+[^.?!]{0,200}\?"
    r"|which\s+(?:path|way|one)\s+(?:will|do)\s+you\s+\w+[^.?!]{0,80}\?"
    r"|the\s+choice\s+before\s+you[^.?!]{0,80}[.?!]"
    # The menu split across two sentences: "You could approach the group...
    # Or, you could continue down the road." Both halves are closers, and the
    # two-sentence cap in _trim_menu_ending removes exactly the pair.
    # "You could hear the mill wheel" is description; only offered *actions* count.
    r"|(?:or,?\s+)?you\s+(?:could|might)\s+"
    r"(?!hear|see|smell|feel|taste|sense|tell|make\s+out|swear|imagine|almost|just|well|barely)"
    r"[^.?!]{0,160}[.?!]"
    r")$",
    re.I,
)


# "You could: \n- Follow the main road... \n- Head north..." — the same menu in
# list form, and also a plain formatting violation: the contract asks for
# continuous prose. Seen on 5/24 turns of a live run.
_OPTION_LIST_RE = re.compile(r"\n[ \t]*(?:[-*•–]|\d+[.)])[ \t]+\S", re.M)
# The sentence that introduces the list ("You could:", "Your options are:").
# Matched per-sentence, not per-line: the body is usually one long paragraph, so
# a line-anchored pattern never reached it.
_LIST_LEAD_IN_RE = re.compile(
    r"(?:you\s+(?:could|can|might|may)|your\s+options|choose\s+from|several\s+(?:paths?|options)|"
    r"the\s+following|options?\s+(?:are|before\s+you))",
    re.I,
)


def _trim_option_list(narration: str, *, floor: int = MIN_TURN_NARRATION_CHARS) -> tuple[str, int]:
    """
    Cut a trailing bullet/numbered option list, plus the line that introduces it.

    Only trailing lists: a list in the middle of a scene is more likely to be
    something the player is reading in-world (a notice, a ledger) than a menu.
    """
    text = str(narration or "").rstrip()
    match = _OPTION_LIST_RE.search(text)
    if not match:
        return text, 0
    head = text[: match.start()].rstrip()
    # Everything after the first bullet must itself be list-shaped, otherwise
    # prose resumed below it and this is not a closing menu.
    tail = text[match.start():]
    tail_lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]
    if not tail_lines:
        return text, 0
    bulleted = sum(1 for ln in tail_lines if re.match(r"^(?:[-*•–]|\d+[.)])\s+", ln))
    # Every remaining line must be a bullet. If prose resumed under the list,
    # the list was something in the world (a notice, a ledger), not a menu.
    if bulleted < 2 or bulleted != len(tail_lines):
        return text, 0
    # Drop the sentence(s) that set the list up; a colon-terminated sentence
    # immediately above a bullet list is always the lead-in.
    for _ in range(2):
        sentences = re.split(r"(?<=[.!?:])\s+", head.strip())
        if len(sentences) < 2:
            break
        last = sentences[-1].strip()
        if not (last.endswith(":") or _LIST_LEAD_IN_RE.search(last)):
            break
        candidate = " ".join(sentences[:-1]).rstrip()
        if len(candidate) < floor:
            break
        head = candidate
    if len(head) < floor:
        return text, 0
    return head, bulleted


def _trim_menu_ending(narration: str, *, floor: int = MIN_TURN_NARRATION_CHARS) -> tuple[str, int]:
    """
    Drop trailing "The choice is yours." style closers.

    A 7B restates the player's options as a menu on roughly a quarter of turns
    even when the system prompt forbids it; the behaviour did not move with
    prompting. Since the UI already asks the player what they want to do, these
    sentences are filler, and cutting them is cheaper and more reliable than
    another generation pass.

    Never trims below `floor` characters and never removes more than two
    sentences, so a short scene keeps its body even if the ending is weak.
    """
    text = str(narration or "").rstrip()
    if not text:
        return text, 0
    removed = 0
    for _ in range(2):
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        if len(parts) < 2:
            break
        last = parts[-1].strip()
        if not _MENU_CLOSER_RE.match(last):
            break
        candidate = " ".join(parts[:-1]).rstrip()
        if len(candidate) < floor:
            break
        text = candidate
        removed += 1
    return text, removed


def _apply_menu_trim(turn: dict[str, Any]) -> dict[str, Any]:
    """Strip trailing option lists and menu closers, rebuilding segments to match."""
    original = str(turn.get("narration") or "")
    listless, list_removed = _trim_option_list(original)
    trimmed, removed = _trim_menu_ending(listless)
    removed += list_removed
    if not removed:
        return turn
    turn["narration"] = trimmed
    segments = turn.get("narration_segments")
    if isinstance(segments, list) and segments:
        rebuilt = [p.strip() for p in re.split(r"\n\s*\n", trimmed) if p.strip()]
        if rebuilt:
            turn["narration_segments"] = [{"label": "paragraph", "text": p} for p in rebuilt]
    turn["_menu_trimmed"] = removed
    return turn


def _narration_voice_drift(turn: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Point-of-view check on a drafted turn. Returns the report, drift flag included."""
    try:
        from app.world import check_narrative_voice

        state = {
            "narrative_voice": context.get("narrative_voice"),
            "player": context.get("player") or {},
            "settings": context.get("settings") or {},
        }
        return check_narrative_voice(str(turn.get("narration") or ""), state)
    except Exception:
        return {"drift": False}


def _retry_narration_voice(
    context: dict[str, Any],
    player_input: str,
    turn: dict[str, Any],
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Rewrite a third-person narration into second person, changing nothing else.

    Only fires on unambiguous drift (a full narration that never says "you"), so
    it costs one extra prose pass on the rare turn instead of every turn.
    """
    existing = str(turn.get("narration") or "")
    voice = context.get("narrative_voice") if isinstance(context.get("narrative_voice"), dict) else {}
    pronouns = voice.get("player_pronouns") if isinstance(voice.get("player_pronouns"), dict) else {}
    subject = str(pronouns.get("subject") or "they")
    obj = str(pronouns.get("object") or "them")
    possessive = str(pronouns.get("possessive") or "their")
    name = str(voice.get("player_name") or "").strip()
    instruction = "\n".join(
        [
            "Rewrite this scene in SECOND PERSON. Return ONLY the prose.",
            "No JSON. No headers. No markdown fences. No commentary. Just the scene text.",
            "",
            "The player character is addressed as \"you\" / \"your\" throughout.",
            (
                f"Replace every third-person reference to {name} with \"you\"."
                if name
                else "Replace every third-person reference to the player character with \"you\"."
            ),
            f"If another character speaks about the player, use {subject}/{obj}/{possessive}.",
            "Other characters keep their own names and pronouns exactly as written.",
            "",
            "Change nothing else: same events, same facts, same names, same [[CODE]] references,",
            "same order, same length. This is a person change, not a rewrite.",
            "",
            "Scene to convert:",
            existing[:4000],
        ]
    )
    raw = _chat_text(
        system_prompt,
        instruction,
        timeout=timeout,
        usage=usage,
        phase=phase,
        max_tokens=max(_turn_max_tokens(context, "draft"), DEFAULT_RESPONSE_TOKEN_CAP),
        trace=trace,
    )
    prose = _clean_retry_prose(raw)
    if len(prose.strip()) < max(200, int(len(existing.strip()) * 0.5)):
        raise LlmError("Voice retry returned too little prose to trust.")
    spliced = _splice_prose_into_turn(turn, prose)
    if _narration_voice_drift(spliced, context).get("drift"):
        raise LlmError("Voice retry came back in third person again.")
    return spliced


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
    normalized = _normalize_turn(turn, context)
    original_chars = _narration_char_count(normalized)
    if original_chars >= MIN_TURN_NARRATION_CHARS:
        return normalized

    # Prose-only first: it is the smallest thing to ask for, cannot truncate
    # into invalid JSON, and preserves the draft's structured ops. The
    # full-turn JSON retry stays as a fallback for models that handle it.
    for attempt, retry in (
        ("prose", _retry_narration_prose),
        ("json", _retry_short_narration),
    ):
        try:
            expanded = _normalize_turn(
                retry(context, player_input, normalized, system_prompt, timeout, usage, phase, trace),
                context,
            )
            expanded_chars = _narration_char_count(expanded)
            if expanded_chars >= MIN_TURN_NARRATION_CHARS or expanded_chars > original_chars:
                _append_trace(
                    trace,
                    {
                        "phase": phase,
                        "event": "depth_retry_ok",
                        "mode": attempt,
                        "before_chars": original_chars,
                        "after_chars": expanded_chars,
                    },
                )
                return expanded
        except LlmError as exc:
            usage.append({"phase": f"{phase}_{attempt}_failed", "error": _trim_text(str(exc), 500)})
            _append_trace(
                trace,
                {"phase": phase, "event": "depth_retry_failed", "mode": attempt, "error": str(exc)},
            )
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
            deep = refined
        else:
            deep = _ensure_narration_depth(refined, context, player_input, system_prompt, timeout, usage, phase, trace)
    else:
        deep = _ensure_narration_depth(turn, context, player_input, system_prompt, timeout, usage, phase, trace)
    voiced = _ensure_narration_voice(deep, context, player_input, system_prompt, timeout, usage, phase, trace)
    answered = _ensure_answer_act(voiced, context, player_input, system_prompt, timeout, usage, phase, trace)
    recalled = _ensure_recall_specifics(answered, context, player_input, system_prompt, timeout, usage, phase, trace)
    return _apply_menu_trim(recalled)


def _voice_repair_enabled() -> bool:
    return str(os.getenv("AI_RPG_VOICE_REPAIR", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _ensure_narration_voice(
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
    One prose pass to fix a narration that drifted out of second person.

    Deliberately narrow: only fires when the narration never addresses the
    player at all. Partial drift (a stray third-person sentence) is left to the
    prompt contract — a rewrite for that would cost a pass on most turns and
    risk mangling correct prose.
    """
    report = _narration_voice_drift(turn, context)
    turn["_voice_check"] = report
    if not report.get("drift") or not _voice_repair_enabled():
        return turn
    try:
        fixed = _normalize_turn(
            _retry_narration_voice(context, player_input, turn, system_prompt, timeout, usage, f"{phase}_voice", trace),
            context,
        )
        fixed["_voice_check"] = {**_narration_voice_drift(fixed, context), "repaired": True}
        _append_trace(trace, {"phase": phase, "event": "voice_retry_ok", "before": report})
        return fixed
    except LlmError as exc:
        usage.append({"phase": f"{phase}_voice_failed", "error": _trim_text(str(exc), 500)})
        _append_trace(trace, {"phase": phase, "event": "voice_retry_failed", "error": str(exc)})
    return turn


def _answer_act_report(turn: dict[str, Any], player_input: str) -> dict[str, Any]:
    try:
        from app.world import check_answer_act

        return check_answer_act(player_input, str(turn.get("narration") or ""))
    except Exception:
        return {"answer_act": False, "topics": [], "hits": [], "unanswered": False}


def _retry_answer_act(
    context: dict[str, Any],
    player_input: str,
    turn: dict[str, Any],
    report: dict[str, Any],
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rewrite a scene that owed an explanation and never gave one.

    Prose-only, like the voice repair. The substance is the model's job -- there
    is nothing deterministic to substitute here, unlike a name -- so this asks
    once and accepts the result. If the second pass still dodges, the turn
    stands: inventing the player's own explanation would be worse than a thin
    one.
    """
    existing = str(turn.get("narration") or "")
    topics = ", ".join(str(t) for t in (report.get("topics") or [])[:8])
    instruction = "\n".join(
        [
            "Rewrite this scene so it actually delivers what the player said they would say.",
            "Return ONLY the prose. No JSON, no headers, no markdown fences, no commentary.",
            "",
            f'The player\'s line was: "{str(player_input or "").strip()}"',
            "That line commits the player to explaining or telling something. The scene as",
            "written never covers it.",
            f"Cover it plainly, in the player's own words, on the subject of: {topics}." if topics else
            "Cover it plainly, in the player's own words.",
            "",
            "Keep everything else: same location, same characters, same events, same",
            "[[CODE]] references, same second-person voice, similar length. Add the missing",
            "answer into the scene; do not restart it.",
            "",
            "--- SCENE ---",
            existing[:4000],
        ]
    )
    raw = _chat_text(
        system_prompt,
        instruction,
        timeout=timeout,
        usage=usage,
        phase=f"{phase}_answer",
        max_tokens=max(_turn_max_tokens(context, "draft"), DEFAULT_RESPONSE_TOKEN_CAP),
        trace=trace,
    )
    prose = _clean_retry_prose(raw)
    if len(prose.strip()) < max(200, int(len(existing.strip()) * 0.5)):
        raise LlmError("Answer retry returned too little prose to trust.")
    spliced = _splice_prose_into_turn(turn, prose)
    if _answer_act_report(spliced, player_input).get("unanswered"):
        raise LlmError("Answer retry still did not cover what the player said they would say.")
    return spliced


def _recall_report(turn: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    try:
        from app.world import check_recall_specifics

        return check_recall_specifics(
            (context or {}).get("recall_contract"), str(turn.get("narration") or "")
        )
    except Exception:
        return {"required": False, "specifics": [], "stated": [], "missing": False}


def _retry_recall_specifics(
    context: dict[str, Any],
    player_input: str,
    turn: dict[str, Any],
    report: dict[str, Any],
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rewrite a scene that owed remembered specifics and stated none.

    Unlike the answer-act retry there IS something deterministic to hand back:
    the world already wrote this down, so the record goes into the instruction
    verbatim. The model only has to place it in the prose.
    """
    contract = (context or {}).get("recall_contract") or {}
    existing = str(turn.get("narration") or "")
    specifics = ", ".join(str(s) for s in (report.get("specifics") or [])[:8])
    record = str(contract.get("record") or "").strip()
    line = str(player_input or "").strip()
    instruction = "\n".join(
        [
            "Rewrite this scene so the player actually states what they already know.",
            "Return ONLY the prose. No JSON, no headers, no markdown fences, no commentary.",
            "",
            f"The player's line was: {line}",
            "This world has already recorded the answer:",
            f"    {record[:400]}",
            f"The scene as written never states: {specifics}.",
            "Put those specifics into the player's own words in the scene. Echoing the",
            "question back is not an answer.",
            "",
            "Keep everything else: same location, same characters, same events, same",
            "[[CODE]] references, same second-person voice, similar length. Add the missing",
            "detail into the scene; do not restart it.",
            "",
            "--- SCENE ---",
            existing[:4000],
        ]
    )
    raw = _chat_text(
        system_prompt,
        instruction,
        timeout=timeout,
        usage=usage,
        phase=f"{phase}_recall",
        max_tokens=max(_turn_max_tokens(context, "draft"), DEFAULT_RESPONSE_TOKEN_CAP),
        trace=trace,
    )
    prose = _clean_retry_prose(raw)
    if len(prose.strip()) < max(200, int(len(existing.strip()) * 0.5)):
        raise LlmError("Recall retry returned too little prose to trust.")
    spliced = _splice_prose_into_turn(turn, prose)
    if _recall_report(spliced, context).get("missing"):
        raise LlmError("Recall retry still did not state the remembered specifics.")
    return spliced


def _ensure_recall_specifics(
    turn: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One prose pass when the prose owed a remembered name or amount and gave none."""
    report = _recall_report(turn, context)
    turn["_recall_check"] = report
    if not report.get("missing") or not _answer_repair_enabled():
        return turn
    try:
        fixed = _normalize_turn(
            _retry_recall_specifics(
                context, player_input, turn, report, system_prompt, timeout, usage, phase, trace
            ),
            context,
        )
        fixed["_recall_check"] = {**_recall_report(fixed, context), "repaired": True}
        _append_trace(trace, {"phase": phase, "event": "recall_retry_ok", "before": report})
        return fixed
    except LlmError as exc:
        usage.append({"phase": f"{phase}_recall_failed", "error": _trim_text(str(exc), 500)})
        _append_trace(trace, {"phase": phase, "event": "recall_retry_failed", "error": str(exc)})
    return turn


def _ensure_answer_act(
    turn: dict[str, Any],
    context: dict[str, Any],
    player_input: str,
    system_prompt: str,
    timeout: int,
    usage: list[dict[str, Any]],
    phase: str,
    trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One prose pass when the player promised an explanation and got none."""
    report = _answer_act_report(turn, player_input)
    turn["_answer_check"] = report
    if not report.get("unanswered") or not _answer_repair_enabled():
        return turn
    try:
        fixed = _normalize_turn(
            _retry_answer_act(
                context, player_input, turn, report, system_prompt, timeout, usage, phase, trace
            ),
            context,
        )
        fixed["_answer_check"] = {
            **_answer_act_report(fixed, player_input),
            "repaired": True,
        }
        _append_trace(trace, {"phase": phase, "event": "answer_retry_ok", "before": report})
        return fixed
    except LlmError as exc:
        usage.append({"phase": f"{phase}_answer_failed", "error": _trim_text(str(exc), 500)})
        _append_trace(trace, {"phase": phase, "event": "answer_retry_failed", "error": str(exc)})
    return turn


def _answer_repair_enabled() -> bool:
    return str(os.getenv("AI_RPG_ANSWER_REPAIR", "1")).strip().lower() not in {"0", "false", "no"}


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
    # A timeout is a ceiling, not a delay: raising it costs a fast machine
    # nothing, and the cost of hitting it is the worst failure this app has --
    # the turn silently falls back to canned deterministic prose.
    #
    # Measured on an RTX 4070 Ti with qwen3:8b and a ~9k-token packet, the draft
    # call took 27-37s on an idle GPU and 75-100s with an ordinary desktop load
    # on the card (a second model runner, a recorder, a browser). The old 90s
    # default sat *inside* that range: a continuity probe timed out at exactly
    # 90s, and a 100-turn run measured drafts at 99.7s. Anyone on slower hardware
    # than this, or merely watching a video, was falling back every turn.
    timeout = _model_timeout(300, 900, "AI_RPG_TURN_DRAFT_TIMEOUT")
    verify_timeout = _model_timeout(150, 480, "AI_RPG_TURN_VERIFY_TIMEOUT")
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
    system_prompt, verify_prompt, prompt_degraded = fitting_system_prompts(config)
    if prompt_degraded:
        _warn_compact_contract_once(context_window_tokens(config))
    theme_block = theme_prompt_block(session_theme, playthrough_options)
    dsl_system_prompt = DSL_SYSTEM_PROMPT
    is_opening = str(player_input or "").startswith("__opening_scene_request__")
    if theme_block:
        system_prompt = f"{system_prompt.rstrip()}\n\n{theme_block}"
        dsl_system_prompt = f"{DSL_SYSTEM_PROMPT.rstrip()}\n\n{theme_block}"
    avoid_block = anti_repetition_block(context)
    if avoid_block:
        system_prompt = f"{system_prompt.rstrip()}\n\n{avoid_block}"
        dsl_system_prompt = f"{dsl_system_prompt.rstrip()}\n\n{avoid_block}"
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

        if verifier_is_disabled():
            # Breaker tripped: this model cannot produce a usable verify object.
            _append_trace(
                trace,
                {"phase": "verify", "event": "verifier_disabled", **verifier_breaker_status()},
            )
            usage.append({"phase": "verify_skipped_breaker", "reason": _VERIFY_DISABLED_REASON})
            result = _ensure_narration_quality(
                draft, active_context, player_input, system_prompt, timeout, usage, "narration_depth_retry", trace
            )
            result = _clean_turn_for_handoff(result, "dsl_draft_to_world", trace)
            result["_verification_policy"] = {
                **(verification_policy if isinstance(verification_policy, dict) else {}),
                "verifier_breaker": verifier_breaker_status(),
            }
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
                result = _normalize_turn(verified, active_context)
            except LlmError as exc:
                if not _is_missing_narration_error(exc):
                    raise
                result = _merge_verified_with_draft_narration(verified, draft)
            _note_verify_outcome(_verified_output_is_useful(verified, draft), "echoed input")
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
            _note_verify_outcome(False, _trim_text(str(exc), 120))
            draft = _normalize_turn(draft, active_context)
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
        draft = _clean_turn_for_handoff(
            _normalize_turn(draft, active_context), "draft_to_verify", trace
        )
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
                ),
                active_context,
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
    if verifier_is_disabled():
        # The breaker has tripped: this model cannot produce a usable verify
        # object, so go straight to the draft + depth pass instead of burning
        # a timeout on it every turn.
        _append_trace(
            trace,
            {
                "phase": "verify",
                "event": "verifier_disabled",
                **verifier_breaker_status(),
            },
        )
        usage.append({"phase": "verify_skipped_breaker", "reason": _VERIFY_DISABLED_REASON})
        result = _ensure_narration_quality(
            draft, active_context, player_input, system_prompt, timeout, usage, "narration_depth_retry", trace
        )
        result = _clean_turn_for_handoff(result, "draft_to_world", trace)
        result["_verification_policy"] = {
            **verification_policy,
            "verifier_breaker": verifier_breaker_status(),
        }
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
            result = _normalize_turn(verified, active_context)
        except LlmError as exc:
            if not _is_missing_narration_error(exc):
                raise
            result = _merge_verified_with_draft_narration(verified, draft)
        _note_verify_outcome(_verified_output_is_useful(verified, draft), "echoed input")
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
        # Any hard verify failure counts toward the breaker too, not just
        # syntactically-valid garbage.
        _note_verify_outcome(False, _trim_text(str(exc), 120))
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
                    result = _normalize_turn(verified, active_context)
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
        draft = _normalize_turn(draft, active_context)
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
