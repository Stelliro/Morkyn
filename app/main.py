from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.db import init_db
from app.image_backends import (
    assess_character_art_readiness,
    build_character_prompt_pack,
    build_portrait_prompt,
    fetch_backend_catalog,
    generate_character_set,
    generate_image,
    get_image_config,
    image_readiness,
    install_image_component,
    launch_image_backend,
    list_comfy_workflows,
    list_image_installables,
    list_local_checkpoints,
    list_local_loras,
    delete_local_portrait,
    list_local_portraits,
    load_image_presets,
    probe_character_lock,
    probe_iib_status,
    probe_image_backend,
    public_image_config,
    public_image_presets,
    reset_image_presets,
    resolve_character_consistency_mode,
    resolve_lora_preview_path,
    resolve_portrait_file,
    save_image_presets,
    search_backend_roots,
    store_player_art_assets,
    update_image_config,
)
from app.gpu_gate import gate_status as gpu_gate_status
from app.tile_world import (
    add_tile_image,
    apply_survey,
    ascii_preview,
    clear_run_disables,
    delete_tile_images,
    disable_tile_images_for_run,
    full_map_view,
    generate_map,
    get_map,
    grant_lived_area_knowledge,
    grant_map_knowledge,
    list_maps,
    list_settlements,
    list_tile_states,
    list_world_presets,
    local_map_view,
    move_player,
    search_tile_images,
    set_tile_images_disabled_forever,
    suggest_tile_prompt,
)
from app.failsafe import FailsafeBlocked, classify_failure, problem_detail
from app.llm import (
    LlmError,
    coherence_review_setup,
    compose_setup_intent,
    ensure_llm_adapter_ready,
    fallback_setup_randomization,
    generate_setup_randomization,
    get_llm_runtime,
    get_model_config,
    public_model_config,
    soft_recycle_llm_backend,
    test_model_connection,
    try_hot_swap_llm_lora,
    update_model_config,
)
from app.setup_composer import (
    composer_tree_public,
    intent_to_field_overrides,
    session_theme_from_intent,
)
from app.idea_bank import (
    append_user_idea,
    idea_bank_stats,
    idea_sparks_for_prompt,
    load_idea_cards,
    search_idea_bank,
)
from app.starter_logic import fact_check_starter_loadout
from app.skill_checks import (
    catalog_public,
    player_with_gear_scores,
    register_or_adjust_skill,
    resolve_check,
    scores_from_gear_bonuses,
    set_skill_enabled,
    settings_from_setup,
)
from app.launcher_prefs import apply_prefs_to_env, load_prefs, save_prefs
from app.updates import apply_update, check_for_updates, current_status as update_status, rollback
from app.world import (
    AUTOSAVE_SLOT,
    MECHANICS_CONTEXT_VERSION,
    TURN_CONTEXT_PLANNER_VERSION,
    add_alias,
    autosave_campaign,
    initiate_fight,
    consolidate_memory,
    create_player_alias,
    delete_player_alias,
    delete_campaign_slot,
    export_world,
    get_context_health,
    get_input_suggestions,
    get_session_theme,
    get_state,
    get_world_bible,
    has_continuable_save,
    import_world,
    load_player_art,
    player_art_token,
    list_campaign_slots,
    load_campaign_slot,
    play_continue_turn,
    play_turn,
    play_wait_turn,
    apply_map_travel_step,
    play_world_event_turn,
    queue_quest_stage_event,
    queue_world_event,
    list_due_world_events,
    list_pending_world_events,
    get_quest_stages,
    cancel_world_event,
    consume_due_world_events,
    resolve_social_disengage,
    resolve_social_persist,
    get_weather,
    regenerate_last_turn,
    resume_snapshot,
    rewind_last_turn,
    save_campaign_slot,
    search_world,
    start_playthrough_with_opening,
    update_player_alias_state,
    update_session_theme,
    update_gm_notes,
)


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
MEDIA_DIR = ROOT / "Media"
APP_VERSION = "V0.10.1-wip"

app = FastAPI(title="Mørkyn")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if MEDIA_DIR.is_dir():
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


class TurnRequest(BaseModel):
    text: str = Field(default="", max_length=2000)
    # False: a model failure comes back as a 503 problem instead of an offline-narrator turn.
    allow_fallback: bool = True


class ContinueRequest(BaseModel):
    allow_fallback: bool = True


class SpecialAbilitySetup(BaseModel):
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=800)
    locked: bool = False
    prerequisites: str = Field(default="", max_length=500)
    cost: str = Field(default="", max_length=300)
    growth_math: str = Field(default="", max_length=800)

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for key in ("name", "description", "prerequisites", "cost", "growth_math"):
            value = normalized.get(key)
            normalized[key] = "" if value is None else str(value)
        if normalized.get("locked") is None:
            normalized["locked"] = False
        return normalized


SETUP_STRING_DEFAULTS = {
    "player_name": "Wanderer",
    "player_public_name": "",
    "player_title": "",
    "player_age": "",
    "player_sex": "",
    "previous_life_age": "",
    "previous_life_sex": "",
    "backstory_mode": "known",
    "character_backstory": "",
    "hair": "",
    "facial_features": "",
    "appearance": "",
    "starter_equipment": "",
    "memory_policy": "known",
    "difficulty": "normal",
    "narration_detail": "rich",
    "world_style": "frontier dark fantasy",
    "custom_style": "",
    # Empty = "nobody chose"; world.py picks from this world's themed pool.
    "start_location": "",
    "system_style": "subtle blue-window system",
    "special_ability_origin": "none",
    "special_ability_name": "",
    "special_ability_description": "",
    "skill_style": "standard",
    "new_skill_frequency": "normal",
    "proficiency_access": "learned",
    "skill_growth_speed": "normal",
    "proficiency_growth_speed": "normal",
    "xp_growth_speed": "normal",
    "skill_growth_note": "",
    "proficiency_growth_note": "",
    "xp_growth_note": "",
    "custom_skills": "",
    "death_rules": "downed, not deleted",
    "npc_stat_scaling": "relative ranks",
    "npc_skill_frequency": "some trained NPCs",
    "rank_scale": "F,E,D,C,B,A,S,SS,SSS",
    "economy": "scarce",
    "loot_rarity": "earned and uncommon",
    "inventory_rules": "",
    "magic_level": "rare",
    "world_races": "human",
    "race_magic_rarity": "same as world magic",
    "race_magic_rules": "",
    "race_ability_rules": "",
    "tech_level": "iron age",
    "tone": "grounded adventure",
    "npc_density": "moderate",
    "quest_style": "emergent",
    "faction_pressure": "local disputes",
    "check_difficulty": "normal",
    "event_check_frequency": "normal",
    "encounter_check_frequency": "normal",
    "custom_check_notes": "",
}

SETUP_TEXT_LIMITS = {
    "player_name": 80,
    "player_public_name": 100,
    "player_title": 100,
    "player_age": 60,
    "player_sex": 80,
    "previous_life_age": 60,
    "previous_life_sex": 80,
    "backstory_mode": 60,
    "character_backstory": 1600,
    "hair": 120,
    "facial_features": 300,
    "appearance": 400,
    "starter_equipment": 500,
    "memory_policy": 80,
    "difficulty": 60,
    "narration_detail": 120,
    "world_style": 120,
    "custom_style": 800,
    "start_location": 100,
    "system_style": 120,
    "special_ability_origin": 40,
    "special_ability_name": 100,
    "special_ability_description": 800,
    "skill_style": 60,
    "new_skill_frequency": 80,
    "proficiency_access": 80,
    "skill_growth_speed": 80,
    "proficiency_growth_speed": 80,
    "xp_growth_speed": 80,
    "skill_growth_note": 500,
    "proficiency_growth_note": 500,
    "xp_growth_note": 500,
    "custom_skills": 1200,
    "death_rules": 80,
    "npc_stat_scaling": 80,
    "npc_skill_frequency": 100,
    "rank_scale": 100,
    "economy": 80,
    "loot_rarity": 80,
    "inventory_rules": 900,
    "magic_level": 80,
    "world_races": 400,
    "race_magic_rarity": 100,
    "race_magic_rules": 1200,
    "race_ability_rules": 1200,
    "tech_level": 80,
    "tone": 100,
    "npc_density": 80,
    "quest_style": 80,
    "faction_pressure": 100,
    "check_difficulty": 40,
    "event_check_frequency": 40,
    "encounter_check_frequency": 40,
    "custom_check_notes": 1200,
}

SETUP_BOOL_DEFAULTS = {
    "leveling_system": True,
    "game_system": False,
    "special_ability": False,
    "special_ability_locked": False,
    "skill_levels_enabled": True,
    "proficiency_system": True,
    "race_magic_enabled": False,
    "dice_checks_enabled": False,
    "partial_on_specialized_skill": True,
    "negative_outcomes": True,
    "show_rolls_in_ui": True,
    "crit_on_natural_max": True,
    "fumble_on_natural_1": True,
    "contested_checks": True,
    "power_rng": True,
    "unskilled_mishaps": True,
    "severe_mishap_on_crit_fail": True,
    "auto_check_on_risky_actions": True,
    "degree_flavor": True,
}

SETUP_INT_DEFAULTS = {
    "inventory_weight_limit": 60,
    "inventory_slot_limit": 24,
    "dice_sides": 20,
    "attribute_floor_for_partial": 6,
    "specialized_skill_partial_threshold": 2,
    "power_variance": 3,
    "unskilled_rank_threshold": 1,
}

SETUP_FLOAT_FIELDS = {"skill_growth_multiplier", "proficiency_growth_multiplier", "xp_growth_multiplier"}


def _clean_setup_bool(value: Any, default: bool) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return value


def _clean_setup_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    return int(number)


def _clean_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class SetupRequest(BaseModel):
    player_name: str = Field(default="Wanderer", max_length=80)
    player_public_name: str = Field(default="", max_length=100)
    player_title: str = Field(default="", max_length=100)
    player_age: str = Field(default="", max_length=60)
    player_sex: str = Field(default="", max_length=80)
    previous_life_age: str = Field(default="", max_length=60)
    previous_life_sex: str = Field(default="", max_length=80)
    backstory_mode: str = Field(default="known", max_length=60)
    character_backstory: str = Field(default="", max_length=1600)
    hair: str = Field(default="", max_length=120)
    facial_features: str = Field(default="", max_length=300)
    appearance: str = Field(default="", max_length=400)
    starter_equipment: str = Field(default="", max_length=500)
    memory_policy: str = Field(default="known", max_length=80)
    difficulty: str = Field(default="normal", max_length=60)
    narration_detail: str = Field(default="rich", max_length=120)
    world_style: str = Field(default="frontier dark fantasy", max_length=120)
    custom_style: str = Field(default="", max_length=800)
    start_location: str = Field(default="", max_length=100)
    leveling_system: bool = True
    game_system: bool = False
    system_style: str = Field(default="subtle blue-window system", max_length=120)
    special_ability_origin: str = Field(default="none", max_length=40)
    special_ability: bool = False
    special_ability_locked: bool = False
    special_ability_name: str = Field(default="", max_length=100)
    special_ability_description: str = Field(default="", max_length=800)
    special_abilities: list[SpecialAbilitySetup] = Field(default_factory=list)
    skill_style: str = Field(default="standard", max_length=60)
    skill_levels_enabled: bool = True
    new_skill_frequency: str = Field(default="normal", max_length=80)
    proficiency_system: bool = True
    proficiency_access: str = Field(default="learned", max_length=80)
    skill_growth_speed: str = Field(default="normal", max_length=80)
    proficiency_growth_speed: str = Field(default="normal", max_length=80)
    xp_growth_speed: str = Field(default="normal", max_length=80)
    skill_growth_multiplier: float | None = None
    proficiency_growth_multiplier: float | None = None
    xp_growth_multiplier: float | None = None
    skill_growth_note: str = Field(default="", max_length=500)
    proficiency_growth_note: str = Field(default="", max_length=500)
    xp_growth_note: str = Field(default="", max_length=500)
    custom_skills: str = Field(default="", max_length=1200)
    death_rules: str = Field(default="downed, not deleted", max_length=80)
    npc_stat_scaling: str = Field(default="relative ranks", max_length=80)
    npc_skill_frequency: str = Field(default="some trained NPCs", max_length=100)
    rank_scale: str = Field(default="F,E,D,C,B,A,S,SS,SSS", max_length=100)
    economy: str = Field(default="scarce", max_length=80)
    loot_rarity: str = Field(default="earned and uncommon", max_length=80)
    inventory_weight_limit: int = Field(default=60)
    inventory_slot_limit: int = Field(default=24)
    inventory_rules: str = Field(default="", max_length=900)
    magic_level: str = Field(default="rare", max_length=80)
    world_races: str = Field(default="human", max_length=400)
    race_magic_enabled: bool = False
    race_magic_rarity: str = Field(default="same as world magic", max_length=100)
    race_magic_rules: str = Field(default="", max_length=1200)
    race_ability_rules: str = Field(default="", max_length=1200)
    tech_level: str = Field(default="iron age", max_length=80)
    tone: str = Field(default="grounded adventure", max_length=100)
    npc_density: str = Field(default="moderate", max_length=80)
    quest_style: str = Field(default="emergent", max_length=80)
    faction_pressure: str = Field(default="local disputes", max_length=100)
    # Form snapshot for the preset menu. Stored aside from the play rules.
    setup_form: dict = Field(default_factory=dict)
    # Dice / skill checks (setup tab 5)
    # Compiled Randomize intent → durable DM+genre lean for this playthrough.
    session_theme: dict = Field(default_factory=dict)
    dice_checks_enabled: bool = False
    dice_sides: int = Field(default=20)
    check_difficulty: str = Field(default="normal", max_length=40)
    event_check_frequency: str = Field(default="normal", max_length=40)
    encounter_check_frequency: str = Field(default="normal", max_length=40)
    partial_on_specialized_skill: bool = True
    negative_outcomes: bool = True
    show_rolls_in_ui: bool = True
    crit_on_natural_max: bool = True
    fumble_on_natural_1: bool = True
    contested_checks: bool = True
    power_rng: bool = True
    power_variance: int = Field(default=3)
    unskilled_mishaps: bool = True
    unskilled_rank_threshold: int = Field(default=1)
    severe_mishap_on_crit_fail: bool = True
    auto_check_on_risky_actions: bool = True
    degree_flavor: bool = True
    attribute_floor_for_partial: int = Field(default=6)
    specialized_skill_partial_threshold: int = Field(default=2)
    custom_check_notes: str = Field(default="", max_length=1200)

    @model_validator(mode="before")
    @classmethod
    def normalize_setup_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for key, default in SETUP_STRING_DEFAULTS.items():
            value = normalized.get(key, default)
            text = default if value is None else str(value)
            normalized[key] = text[: SETUP_TEXT_LIMITS[key]]
        for key, default in SETUP_BOOL_DEFAULTS.items():
            normalized[key] = _clean_setup_bool(normalized.get(key, default), default)
        for key, default in SETUP_INT_DEFAULTS.items():
            normalized[key] = _clean_setup_int(normalized.get(key, default), default)
        for key in SETUP_FLOAT_FIELDS:
            normalized[key] = _clean_optional_float(normalized.get(key))
        if normalized.get("special_abilities") is None:
            normalized["special_abilities"] = []
        return normalized


class AliasRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=80)
    entity_type: str = Field(min_length=1, max_length=20)
    entity_code: str = Field(min_length=1, max_length=20)


class PlayerAliasRequest(BaseModel):
    alias: str = Field(min_length=1, max_length=80)
    notes: str = Field(default="", max_length=900)


class PlayerAliasStateRequest(BaseModel):
    alias_id: int | None = None
    active: bool | None = None
    disguised: bool | None = None
    disguise_description: str = Field(default="", max_length=300)


class PlayerAliasDeleteRequest(BaseModel):
    alias_id: int


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)


class GmNotesRequest(BaseModel):
    content: str = Field(default="", max_length=6000)


class RewindRequest(BaseModel):
    snapshot_id: int | None = None


class ModelConfigRequest(BaseModel):
    provider: str = Field(default="llama_cpp", max_length=40)
    mle_model: str = Field(default="qwen3:8b", max_length=200)
    llama_cpp_base_url: str = Field(default="http://localhost:8080", max_length=300)
    gguf_model_path: str = Field(default="", max_length=1000)
    api_base_url: str = Field(default="https://api.x.ai/v1", max_length=400)
    api_model: str = Field(default="grok-4.5", max_length=200)
    api_key: str = Field(default="", max_length=500)
    api_preset: str = Field(default="xai", max_length=40)
    response_token_cap: int = Field(default=1500, ge=64, le=100000)
    response_token_hard_cap: int = Field(default=2000, ge=64, le=100000)
    # Optional: adapter_hint → MLE model / API model / GGUF path for turn-time routing.
    theme_adapter_map: dict[str, str] = Field(default_factory=dict)
    # UI posts these on Save. Omitting them made the LoRA fields look saved, then vanish.
    theme_llm_lora_map: dict[str, Any] = Field(default_factory=dict)
    lora_path: str = Field(default="", max_length=1000)
    # Token limits: "auto" lets the model's own header and the GPU decide;
    # "custom" keeps the numbers below for this model and remembers them.
    limits_mode: str | None = Field(default=None, max_length=12)
    context_tokens: int | None = Field(default=None, ge=0, le=131072)


class ImageConfigRequest(BaseModel):
    provider: str = Field(default="off", max_length=40)
    forge_base_url: str = Field(default="http://127.0.0.1:7860", max_length=400)
    comfy_base_url: str = Field(default="http://127.0.0.1:8188", max_length=400)
    comfy_checkpoint: str = Field(default="", max_length=300)
    comfy_workflow: str = Field(default="txt2img_api.json", max_length=200)
    negative_prompt: str = Field(default="", max_length=2000)
    primary_prompt: str = Field(default="", max_length=1200)
    primary_negative: str = Field(default="", max_length=1200)
    portrait_style: str = Field(default="", max_length=800)
    default_width: int = Field(default=512, ge=64, le=2048)
    default_height: int = Field(default=512, ge=64, le=2048)
    default_steps: int = Field(default=20, ge=1, le=150)
    default_cfg: float = Field(default=7.0, ge=1.0, le=30.0)
    timeout_seconds: int = Field(default=180, ge=10, le=900)
    forge_root: str = Field(default="", max_length=1000)
    comfy_root: str = Field(default="", max_length=1000)
    # Extra folders (absolute). One path per list entry — outside install roots if needed.
    lora_dirs: list[str] = Field(default_factory=list)
    checkpoint_dirs: list[str] = Field(default_factory=list)
    auto_launch_if_offline: bool = True
    # Forge generation
    forge_checkpoint: str = Field(default="", max_length=400)
    forge_vae: str = Field(default="", max_length=400)
    forge_sampler: str = Field(default="Euler a", max_length=120)
    forge_scheduler: str = Field(default="Automatic", max_length=120)
    forge_clip_skip: int = Field(default=1, ge=1, le=12)
    forge_restore_faces: bool = False
    forge_tiling: bool = False
    forge_enable_hr: bool = False
    forge_hr_scale: float = Field(default=1.5, ge=1.0, le=4.0)
    forge_hr_upscaler: str = Field(default="R-ESRGAN 4x+", max_length=200)
    forge_denoising_strength: float = Field(default=0.45, ge=0.0, le=1.0)
    forge_hr_second_pass_steps: int = Field(default=0, ge=0, le=150)
    forge_active_loras: list[dict[str, Any]] = Field(default_factory=list)
    fullbody_use_face_ref: bool = True
    fullbody_ref_denoise: float = Field(default=0.88, ge=0.55, le=0.95)
    character_consistency: str = Field(default="light", max_length=20)
    character_lock_weight: float = Field(default=0.65, ge=0.1, le=1.5)
    adetailer_enable: bool = False
    adetailer_model: str = Field(default="face_yolov8n.pt", max_length=120)
    adetailer_denoise: float = Field(default=0.4, ge=0.1, le=0.9)
    adetailer_on_face: bool = True
    adetailer_on_fullbody: bool = True
    adetailer_use_face_ref: bool = True
    auto_generate_npc_portraits: bool = False
    # Infinite Image Browsing port (embed | tab | off)
    iib_open_mode: str = Field(default="embed", max_length=20)
    iib_base_url: str = Field(default="", max_length=400)
    # Comfy extras
    comfy_sampler_name: str = Field(default="euler", max_length=80)
    comfy_scheduler: str = Field(default="normal", max_length=80)


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    width: int | None = Field(default=None, ge=64, le=2048)
    height: int | None = Field(default=None, ge=64, le=2048)
    steps: int | None = Field(default=None, ge=1, le=150)
    cfg_scale: float | None = Field(default=None, ge=1.0, le=30.0)
    seed: int | None = Field(default=None)
    purpose: str = Field(default="generic", max_length=80)


class PortraitRequest(BaseModel):
    name: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=120)
    known_as: str = Field(default="", max_length=120)
    backstory: str = Field(default="", max_length=2000)
    world_style: str = Field(default="", max_length=300)
    extra: str = Field(default="", max_length=400)
    equipment: list[str] = Field(default_factory=list)
    level: int | None = None
    injuries: list[str] = Field(default_factory=list)
    age: str = Field(default="", max_length=60)
    sex: str = Field(default="", max_length=80)
    from_state: bool = False
    width: int | None = Field(default=None, ge=64, le=2048)
    height: int | None = Field(default=None, ge=64, le=2048)
    steps: int | None = Field(default=None, ge=1, le=150)
    seed: int | None = Field(default=None)


class MapGenerateRequest(BaseModel):
    preset_id: str = Field(default="forest_march", max_length=80)
    seed: int | None = None
    width: int | None = Field(default=None, ge=8, le=96)
    height: int | None = Field(default=None, ge=8, le=96)
    assign_images: bool = True
    # world: the 16,383 grid. board: the older preset-sized chart, also used when width is sent.
    scale: str = Field(default="world", max_length=16)
    density_percent: int | None = Field(default=None, ge=0, le=100)
    notice_percent: int | None = Field(default=None, ge=0, le=100)


class MapRevealRequest(BaseModel):
    x: int = Field(ge=0, le=16382)
    y: int = Field(ge=0, le=16382)
    radius: int = Field(default=1, ge=0, le=4)
    label: str = Field(default="", max_length=80)


class MapMarkerRequest(BaseModel):
    x: int = Field(ge=0, le=16382)
    y: int = Field(ge=0, le=16382)
    label: str = Field(default="mark", max_length=80)


class TileImageSearchRequest(BaseModel):
    query: str = Field(default="", max_length=200)
    state_id: str = Field(default="", max_length=80)
    include_disabled: bool = False
    run_id: str = Field(default="", max_length=120)
    limit: int = Field(default=80, ge=1, le=500)


class TileImageAddRequest(BaseModel):
    state_id: str = Field(min_length=1, max_length=80)
    path: str = Field(default="", max_length=1000)
    data_url: str = Field(default="", max_length=2_500_000)
    source: str = Field(default="user", max_length=40)
    prompt: str = Field(default="", max_length=2000)
    tags: str = Field(default="", max_length=500)
    quality: str = Field(default="8bit", max_length=40)


class TileImageBulkRequest(BaseModel):
    image_ids: list[int] = Field(default_factory=list)
    run_id: str = Field(default="", max_length=120)
    disabled: bool = True


class TileImageGenerateRequest(BaseModel):
    state_id: str = Field(min_length=1, max_length=80)
    preset_id: str = Field(default="", max_length=80)
    quality: str = Field(default="8bit", max_length=40)
    prompt: str = Field(default="", max_length=2000)
    tags: str = Field(default="", max_length=500)
    width: int | None = Field(default=64, ge=32, le=1024)
    height: int | None = Field(default=64, ge=32, le=1024)
    steps: int | None = Field(default=None, ge=1, le=150)


class AgentTurnRequest(BaseModel):
    text: str = Field(default="", max_length=4000)
    token: str = Field(default="", max_length=200)


class UpdateApplyRequest(BaseModel):
    target: str = Field(default="", max_length=200)
    confirm: bool = False


class RollbackRequest(BaseModel):
    target: str = Field(default="", max_length=200)
    confirm: bool = False


class RandomizeSetupRequest(BaseModel):
    group: str = Field(default="all", max_length=80)
    current: dict = Field(default_factory=dict)


class ComposeIntentRequest(BaseModel):
    idea: str = Field(default="", max_length=400)
    current: dict = Field(default_factory=dict)


class SuggestionRequest(BaseModel):
    instruction: str = Field(default="", max_length=500)


@app.on_event("startup")
def startup() -> None:
    init_db()
    # Load content packs from content/packs (built-in) and data/packs (user),
    # then push their tables into the dice and encounter systems. Dropping a
    # JSON file in data/packs is the whole install step.
    try:
        from app.content_packs import apply_active_packs, sync_packs_from_disk

        synced = sync_packs_from_disk()
        apply_active_packs()
        for failure in synced.get("failed") or []:
            print(f"[content-packs] skipped {failure.get('file')}: {failure.get('error')}")
    except Exception as exc:  # never block startup on optional content
        print(f"[content-packs] load skipped: {exc}")

    # Thin the per-turn history of characters nobody has played for months.
    # Once per launch: it walks every slot, and nothing about it is urgent
    # enough to pay for on a turn.
    try:
        from app.world import archive_idle_campaigns

        report = archive_idle_campaigns()
        for entry in report.get("archived") or []:
            print(
                f"[saves] archived {entry.get('campaign_id')}: kept {entry.get('kept')} turns, "
                f"dropped {len(entry.get('removed') or [])} (last played {entry.get('last_played')})"
            )
    except Exception as exc:  # a housekeeping pass must never block startup
        print(f"[saves] archive pass skipped: {exc}")


BUNDLE_ASSETS: tuple[str, ...] = ("app.js", "styles.css", "ui/tokens.css", "ui/skin.css", "ui/interact.js", "ui/failsafe.js")
BUNDLE_PLACEHOLDER = "__BUNDLE__"
_bundle_cache: dict[str, Any] = {"stamp": None, "token": "", "html": ""}


def _bundle_stamp() -> tuple[tuple[float, int], ...]:
    """Cheap change detector: (mtime, size) per asset, no hashing."""
    stamp: list[tuple[float, int]] = []
    for name in (*BUNDLE_ASSETS, "index.html"):
        try:
            info = (STATIC_DIR / name).stat()
            stamp.append((info.st_mtime, info.st_size))
        except OSError:
            stamp.append((0.0, 0))
    return tuple(stamp)


def bundle_token() -> str:
    """
    A cache-busting token computed from what app.js and styles.css actually
    contain, rather than copied from the version by hand.

    The hand-written token is what withheld 0.9.11 from every browser that had
    already loaded the game: index.html still asked for `app.js?v=v0-9-1-wip`,
    the URL each of them already had cached, so the release arrived as nothing.
    Deriving it here means the URL changes whenever the file changes, which is
    the only version of this that cannot be forgotten.
    """
    digest = hashlib.sha256()
    for name in BUNDLE_ASSETS:
        try:
            digest.update((STATIC_DIR / name).read_bytes())
        except OSError:
            # A missing asset must not take the page down. Fall back to the
            # version, which is what this replaced and is better than nothing.
            return APP_VERSION.lower().replace(".", "-")
    return digest.hexdigest()[:16]


def index_html() -> tuple[str, str]:
    """(html, token), recomputed only when a file on disk actually changes."""
    stamp = _bundle_stamp()
    if _bundle_cache["stamp"] != stamp:
        token = bundle_token()
        raw = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        _bundle_cache.update(
            {"stamp": stamp, "token": token, "html": raw.replace(BUNDLE_PLACEHOLDER, token)}
        )
    return str(_bundle_cache["html"]), str(_bundle_cache["token"])


@app.get("/")
def index() -> HTMLResponse:
    html, token = index_html()
    # no-cache means revalidate, not "do not store". The page itself must never
    # be served from cache without checking, or the browser keeps an old copy
    # naming an old token and the whole scheme buys nothing. The assets it
    # points at stay freely cacheable, because their URLs change with them.
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache", "ETag": f'W/"{token}"'},
    )


@app.get("/api/updates/status")
def api_updates_status():
    """Local git status only — does not contact the network."""
    return update_status()


@app.post("/api/updates/check")
def api_updates_check():
    """User-initiated: git fetch + GitHub latest release. Only outbound contact for updates."""
    return check_for_updates()


@app.post("/api/updates/apply")
def api_updates_apply(request: UpdateApplyRequest):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to apply an update.")
    result = apply_update(request.target or "")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Update failed")
    return result


@app.post("/api/updates/rollback")
def api_updates_rollback(request: RollbackRequest):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Set confirm=true to roll back.")
    result = rollback(request.target or "")
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Rollback failed")
    return result


@app.get("/api/state")
def api_state():
    return get_state()


@app.get("/api/version")
def api_version():
    git = update_status()
    return {
        "app": "Mørkyn",
        "version": APP_VERSION,
        "planner_version": TURN_CONTEXT_PLANNER_VERSION,
        "mechanics_version": MECHANICS_CONTEXT_VERSION,
        "git_describe": git.get("describe") if git.get("ok") else None,
        "git_head": git.get("head") if git.get("ok") else None,
    }


@app.get("/api/model-config")
def api_model_config():
    return public_model_config()


@app.post("/api/model-config")
def api_update_model_config(request: ModelConfigRequest):
    # Only keys the client sent. A full dump would reset lora_path / theme maps
    # to empty defaults on partial posts (Ensure adapter, older clients).
    return update_model_config(request.model_dump(exclude_unset=True))


class ModelLimitsRequest(BaseModel):
    mode: str = Field(default="auto", max_length=12)
    context_tokens: int | None = Field(default=None, ge=0, le=131072)
    response_token_cap: int | None = Field(default=None, ge=0, le=100000)
    response_token_hard_cap: int | None = Field(default=None, ge=0, le=100000)


@app.get("/api/model-limits")
def api_model_limits():
    """The token limits for the configured model, with where each number came from."""
    from app.model_limits import resolve_limits

    return resolve_limits()


@app.post("/api/model-limits")
def api_set_model_limits(request: ModelLimitsRequest):
    """Keep the player's numbers for the current model, or go back to automatic."""
    from app.llm import get_model_config
    from app.model_limits import model_facts, resolve_limits, set_limits

    key = str(model_facts(get_model_config(ignore_override=True, resolve_limits=False)).get("key") or "")
    if not key:
        raise HTTPException(status_code=400, detail="No model is configured to remember limits for.")
    if request.mode.strip().lower() == "custom":
        set_limits(
            key,
            {
                "context_tokens": request.context_tokens,
                "response_token_cap": request.response_token_cap,
                "response_token_hard_cap": request.response_token_hard_cap,
            },
        )
    else:
        set_limits(key, None)
    return resolve_limits()


class SessionThemeRequest(BaseModel):
    """Patch session_theme for the active playthrough (theme_model routing, light metadata)."""

    theme_model: str = Field(default="", max_length=120)
    adapter_hint: str | None = Field(default=None, max_length=80)
    genre: str | None = Field(default=None, max_length=120)
    tone: str | None = Field(default=None, max_length=120)
    edge: str | None = Field(default=None, max_length=200)
    dm_stance: str | None = Field(default=None, max_length=240)
    style_notes: str | None = Field(default=None, max_length=400)
    isekai: bool | None = None


@app.get("/api/session-theme")
def api_session_theme():
    """Current playthrough session_theme (empty object before Start)."""
    state = get_state()
    theme = get_session_theme()
    return {
        "session_theme": theme,
        "theme_model": str(theme.get("theme_model") or ""),
        "adapter_hint": str(theme.get("adapter_hint") or ""),
        "setup_complete": bool(state.get("setup_complete")),
    }


@app.post("/api/session-theme")
def api_update_session_theme(request: SessionThemeRequest):
    """
    Set per-playthrough theme_model (wins over theme_adapter_map on turns).
    Only applies when a playthrough is active; setup uses client lastSessionTheme until Start.
    """
    state = get_state()
    if not state.get("setup_complete"):
        raise HTTPException(
            status_code=400,
            detail="No active playthrough. Set theme_model in setup (Model modal) and Start, or continue a save.",
        )
    dump = request.model_dump()
    patch: dict[str, Any] = {"theme_model": str(dump.get("theme_model") or "")}
    for key in ("adapter_hint", "genre", "tone", "edge", "dm_stance", "style_notes", "isekai"):
        if dump.get(key) is not None:
            patch[key] = dump[key]
    theme = update_session_theme(patch)
    return {
        "session_theme": theme,
        "theme_model": str(theme.get("theme_model") or ""),
        "adapter_hint": str(theme.get("adapter_hint") or ""),
        "ok": True,
    }


@app.get("/api/image-config")
def api_image_config():
    """Local image backend settings (Forge / ComfyUI). Default provider is off."""
    return public_image_config()


@app.post("/api/image-config")
def api_update_image_config(request: ImageConfigRequest):
    # Only apply fields the client actually sent — full model_dump() would reset
    # forge_root / path lists / LoRAs to defaults on partial patches.
    return update_image_config(request.model_dump(exclude_unset=True))


@app.post("/api/image-status")
def api_image_status():
    """Probe the configured local image server (no generation)."""
    return probe_image_backend()


class ImageCatalogRequest(BaseModel):
    provider: str = Field(default="", max_length=40)


@app.get("/api/image-catalog")
@app.post("/api/image-catalog")
def api_image_catalog(request: ImageCatalogRequest | None = None):
    """Live models/samplers/VAEs/workflows from Forge or Comfy when online + disk checkpoints."""
    provider = (request.provider if request else "") or None
    catalog = fetch_backend_catalog(provider)
    catalog["comfy_workflows_on_disk"] = list_comfy_workflows()
    catalog["disk_checkpoints"] = list_local_checkpoints()
    # Ensure disk LoRAs carry sidecar weight/keywords/preview even if merge skipped some
    try:
        catalog["disk_loras"] = list_local_loras()
    except Exception:
        catalog.setdefault("disk_loras", catalog.get("disk_loras") or [])
    return catalog


@app.get("/api/image/lora-preview")
def api_lora_preview(name: str = ""):
    """
    Serve a small LoRA preview image from the configured LoRA folders.
    Only files under forge_root / custom lora_dirs are allowed.
    """
    path = resolve_lora_preview_path(name)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="LoRA preview not found")
    suffix = path.suffix.lower()
    media = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "application/octet-stream")
    return FileResponse(
        path,
        media_type=media,
        headers={
            "Cache-Control": "public, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/gpu-gate")
def api_gpu_gate():
    """Whether LLM/image are busy and VRAM headroom for parallel work."""
    return gpu_gate_status()


@app.get("/api/image-presets")
def api_image_presets():
    """Editable face/fullbody generation presets (data/image_presets.json)."""
    return public_image_presets()


@app.post("/api/image-presets")
def api_save_image_presets(payload: dict[str, Any] | None = None):
    if isinstance(payload, dict) and payload:
        save_image_presets(payload)
    return public_image_presets()


@app.post("/api/image-presets/reset")
def api_reset_image_presets():
    reset_image_presets()
    return public_image_presets()


class ImageReadinessRequest(BaseModel):
    launch_if_offline: bool = False


@app.get("/api/image-readiness")
@app.post("/api/image-readiness")
def api_image_readiness(request: ImageReadinessRequest | None = None):
    """Structured checklist for image backend readiness."""
    launch = bool(request.launch_if_offline) if request else False
    return image_readiness(launch_if_offline=launch)


class ImagePathSearchRequest(BaseModel):
    kind: str = Field(default="forge", max_length=20)  # forge | comfyui
    max_results: int = Field(default=12, ge=1, le=30)
    max_seconds: float = Field(default=12.0, ge=2.0, le=30.0)


@app.post("/api/image-path-search")
def api_image_path_search(request: ImagePathSearchRequest):
    """User-consented search for Forge/Comfy install roots."""
    return search_backend_roots(
        request.kind,
        max_results=request.max_results,
        max_seconds=request.max_seconds,
    )


class ImageLaunchRequest(BaseModel):
    provider: str = Field(default="", max_length=40)
    force: bool = False  # only open a new process if true (default: reuse if API is up)


@app.post("/api/image-launch")
def api_image_launch(request: ImageLaunchRequest):
    """Start Forge/Comfy only if API is offline (unless force=true)."""
    result = launch_image_backend(request.provider or None, force=bool(request.force))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Launch failed")
    return result


@app.get("/api/image-installables")
def api_image_installables():
    """
    Checklist of Forge/Comfy install pieces (InstantID, FaceID, nodes, roots).
    Status is disk-based against saved install roots.
    """
    return list_image_installables()


class ImageBrowserRequest(BaseModel):
    launch_if_offline: bool = False


@app.get("/api/image-browser")
@app.post("/api/image-browser")
def api_image_browser(request: ImageBrowserRequest | None = None):
    """
    Infinite Image Browsing (IIB) port status + native portrait list.
    IIB is never vendored — only probed/opened when the user installed it under Forge.
    """
    launch = bool(request.launch_if_offline) if request else False
    iib = probe_iib_status(launch_if_offline=launch)
    portraits = list_local_portraits(limit=120)
    return {
        "ok": True,
        "iib": iib,
        "portraits": portraits,
        "menu": {
            "label": "Image Browser",
            "source": "iib" if iib.get("can_embed") or iib.get("can_open_tab") else "native",
            "hint": iib.get("message") or "",
        },
    }


class PlayerArtStoreRequest(BaseModel):
    """Persist pre-game setup face/body into the active playthrough settings."""

    face_data_url: str = Field(default="", max_length=8_000_000)
    fullbody_data_url: str = Field(default="", max_length=8_000_000)


@app.post("/api/player/art")
def api_player_art_store(request: PlayerArtStoreRequest):
    """
    Save setup-generated face/fullbody into world settings so play UI + reloads keep them.
    Accepts data:image… URLs only (no file:// paths).
    """
    face_url = str(request.face_data_url or "").strip()
    body_url = str(request.fullbody_data_url or "").strip()
    if face_url and not face_url.startswith("data:image"):
        raise HTTPException(status_code=400, detail="face_data_url must be a data:image URL")
    if body_url and not body_url.startswith("data:image"):
        raise HTTPException(status_code=400, detail="fullbody_data_url must be a data:image URL")
    if not face_url and not body_url:
        raise HTTPException(status_code=400, detail="Provide face_data_url and/or fullbody_data_url")
    store_player_art_assets(
        face={"data_url": face_url, "kind": "face"} if face_url else None,
        fullbody={"data_url": body_url, "kind": "fullbody"} if body_url else None,
        meta={"source": "setup_handoff"},
    )
    state = get_state()
    # get_state names a slot only when an image is stored, so presence is the entry itself.
    return {
        "ok": True,
        "has_face": bool(state.get("player_portrait")),
        "has_fullbody": bool(state.get("player_fullbody")),
    }


PLAYER_ART_IMMUTABLE = "public, max-age=31536000, immutable"


def player_art_response(kind: str, requested_token: str = "") -> Response:
    """
    The stored face or full-body picture as image bytes.

    The state payload names the picture by token (`player_portrait.url`), so a
    browser fetches it once per change and polls and turns stop carrying the
    base64. A URL carrying the current token is immutable to the cache; one
    carrying an old or no token still gets the current picture, revalidated.
    """
    entry = load_player_art(kind)
    if not entry:
        raise HTTPException(status_code=404, detail="No stored player art for that slot")
    data_url = str(entry.get("data_url") or "")
    token = player_art_token(data_url)
    try:
        header, payload = data_url.split(",", 1)
        media = header[len("data:"):].split(";")[0].strip().lower()
        if ";base64" not in header or not media.startswith("image/"):
            raise ValueError("not a base64 image data URL")
        body = base64.b64decode(payload, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Stored player art unreadable") from exc
    return Response(
        content=body,
        media_type=media,
        headers={
            "Cache-Control": PLAYER_ART_IMMUTABLE if requested_token == token else "no-cache",
            "ETag": f'"{token}"',
            "X-Content-Type-Options": "nosniff",
            "X-Player-Art-Token": token,
        },
    )


@app.get("/api/player-art/{kind}")
def api_player_art(kind: str, v: str = ""):
    """Serve the stored player art for `kind` (face or fullbody); 404 when none is stored."""
    return player_art_response(kind, v)


@app.get("/api/portraits")
def api_list_portraits(limit: int = 120):
    """Native Mørkyn portrait library under data/portraits."""
    return list_local_portraits(limit=limit)


@app.get("/api/portraits/file")
def api_portrait_file(name: str = ""):
    """Serve a single file from data/portraits (filename only)."""
    path = resolve_portrait_file(name)
    if not path:
        raise HTTPException(status_code=404, detail="Portrait not found")
    media = "image/png"
    low = path.suffix.lower()
    if low in {".jpg", ".jpeg"}:
        media = "image/jpeg"
    elif low == ".webp":
        media = "image/webp"
    elif low == ".gif":
        media = "image/gif"
    return FileResponse(path, media_type=media, filename=path.name)


class PortraitDeleteRequest(BaseModel):
    name: str = Field(default="", max_length=260)


@app.post("/api/portraits/delete")
@app.delete("/api/portraits")
def api_delete_portrait(request: PortraitDeleteRequest | None = None, name: str = ""):
    """Delete one native portrait under data/portraits (filename only)."""
    target = str((request.name if request else "") or name or "").strip()
    result = delete_local_portrait(target)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error") or "Portrait not found")
    return result


class ImageInstallRequest(BaseModel):
    id: str = Field(default="", max_length=80)


@app.post("/api/image-installables/install")
def api_image_installable_install(request: ImageInstallRequest):
    """Download/install one catalog entry into the matching Forge or Comfy root."""
    component_id = str(request.id or "").strip()
    if not component_id:
        raise HTTPException(status_code=400, detail="Missing installable id")
    result = install_image_component(component_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Install failed")
    # Return fresh checklist after install
    listing = list_image_installables()
    return {"ok": True, "install": result, **listing}


class LoraWeight(BaseModel):
    name: str = Field(default="", max_length=200)
    # Same range as the setup slider and format_lora_tags (age sliders sit outside 0–2).
    weight: float = Field(default=1.0, ge=-5.0, le=5.0)


class CharacterSetRequest(BaseModel):
    from_state: bool = False
    name: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=100)
    known_as: str = Field(default="", max_length=100)
    backstory: str = Field(default="", max_length=4000)
    world_style: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=200)
    extra: str = Field(default="", max_length=1200)
    hair: str = Field(default="", max_length=120)
    facial_features: str = Field(default="", max_length=300)
    appearance: str = Field(default="", max_length=400)
    age: str = Field(default="", max_length=60)
    sex: str = Field(default="", max_length=80)
    equipment: list[str] = Field(default_factory=list)
    injuries: list[str] = Field(default_factory=list)
    level: int | None = None
    kinds: list[str] = Field(default_factory=lambda: ["face", "fullbody"])
    seed: int | None = None
    # Hook existing API first; if still offline, may start one backend instance.
    launch_if_offline: bool = True
    persist: bool = True
    # What the *player* can see — drives partial/obscured art instead of inventing a full look.
    visibility_note: str = Field(default="", max_length=400)
    observed_description: str = Field(default="", max_length=800)
    subject: str = Field(default="player", max_length=40)  # player | npc | other
    loras: list[LoraWeight] = Field(default_factory=list)
    use_face_reference: bool | None = None
    reference_data_url: str = Field(default="", max_length=12_000_000)
    # Shared negatives from presets are often 1k+ chars after frame/child tags.
    negative_override: str = Field(default="", max_length=4000)
    # Player-edited engine prompts (final strings sent to Forge when non-empty).
    face_prompt: str = Field(default="", max_length=8000)
    fullbody_prompt: str = Field(default="", max_length=8000)
    face_negative: str = Field(default="", max_length=4000)
    fullbody_negative: str = Field(default="", max_length=4000)
    # Optional hires overrides (UI quality bar) — applied for this gen even if config save races.
    forge_enable_hr: bool | None = None
    forge_hr_scale: float | None = Field(default=None, ge=1.0, le=4.0)
    forge_hr_upscaler: str | None = Field(default=None, max_length=200)
    forge_denoising_strength: float | None = Field(default=None, ge=0.0, le=1.0)
    forge_hr_second_pass_steps: int | None = Field(default=None, ge=0, le=150)


class CharacterPromptPreviewRequest(BaseModel):
    from_state: bool = False
    name: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=100)
    known_as: str = Field(default="", max_length=100)
    backstory: str = Field(default="", max_length=4000)
    world_style: str = Field(default="", max_length=500)
    location: str = Field(default="", max_length=200)
    extra: str = Field(default="", max_length=1200)
    hair: str = Field(default="", max_length=120)
    facial_features: str = Field(default="", max_length=300)
    appearance: str = Field(default="", max_length=400)
    age: str = Field(default="", max_length=60)
    sex: str = Field(default="", max_length=80)
    equipment: list[str] = Field(default_factory=list)
    injuries: list[str] = Field(default_factory=list)
    level: int | None = None
    kinds: list[str] = Field(default_factory=lambda: ["face", "fullbody"])
    loras: list[LoraWeight] = Field(default_factory=list)
    negative_override: str = Field(default="", max_length=4000)
    visibility_note: str = Field(default="", max_length=400)
    observed_description: str = Field(default="", max_length=800)
    subject: str = Field(default="player", max_length=40)


class CharacterArtReadyRequest(BaseModel):
    from_state: bool = False
    name: str = Field(default="", max_length=100)
    title: str = Field(default="", max_length=100)
    known_as: str = Field(default="", max_length=100)
    backstory: str = Field(default="", max_length=1600)
    world_style: str = Field(default="", max_length=200)
    extra: str = Field(default="", max_length=400)
    hair: str = Field(default="", max_length=120)
    facial_features: str = Field(default="", max_length=300)
    appearance: str = Field(default="", max_length=400)
    age: str = Field(default="", max_length=60)
    sex: str = Field(default="", max_length=80)
    equipment: list[str] = Field(default_factory=list)
    injuries: list[str] = Field(default_factory=list)
    visibility_note: str = Field(default="", max_length=400)
    observed_description: str = Field(default="", max_length=800)
    subject: str = Field(default="player", max_length=40)


@app.post("/api/image/character-prompts")
def api_image_character_prompts(request: CharacterPromptPreviewRequest):
    """
    Assemble face/body engine prompts from identity + settings (no GPU).
    Does not modify player identity fields — UI shows these as editable send buffers.
    """
    name = request.name
    title = request.title
    known_as = request.known_as
    backstory = request.backstory
    world_style = request.world_style
    location = request.location
    extra = request.extra
    hair = request.hair
    facial_features = request.facial_features
    appearance = request.appearance
    age = request.age
    sex = request.sex
    equipment = list(request.equipment or [])
    injuries = list(request.injuries or [])
    level = request.level
    if request.from_state:
        state = get_state()
        player = state.get("player") or {}
        options = ((state.get("settings") or {}).get("playthrough_options") or {})
        name = name or str(player.get("name") or "")
        title = title or str(player.get("title") or "")
        known_as = known_as or str(player.get("public_name") or "")
        backstory = backstory or str(player.get("backstory") or "")
        world_style = world_style or str(options.get("world_style") or "")
        location = location or str(options.get("start_location") or "")
        hair = hair or str(options.get("hair") or "")
        facial_features = facial_features or str(options.get("facial_features") or "")
        appearance = appearance or str(options.get("appearance") or "")
        age = age or str(player.get("age") or "")
        sex = sex or str(player.get("sex") or "")
        try:
            level = int(player.get("level") or level or 1)
        except (TypeError, ValueError):
            level = 1
        if not equipment:
            starter = str(options.get("starter_equipment") or "")
            equipment = [p.strip() for p in starter.replace(";", ",").split(",") if p.strip()][:14]
            if not equipment:
                for item in state.get("inventory") or []:
                    if not isinstance(item, dict):
                        continue
                    label = str(item.get("name") or "").strip()
                    if label:
                        equipment.append(label)
                equipment = equipment[:14]
    lora_payload = [
        {"name": str(item.name or "").strip(), "weight": float(item.weight)}
        for item in (request.loras or [])
        if str(item.name or "").strip()
    ]
    return build_character_prompt_pack(
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        location=location,
        extra=extra,
        hair=hair,
        facial_features=facial_features,
        appearance=appearance,
        equipment=equipment,
        injuries=injuries,
        level=level,
        age=age,
        sex=sex,
        visibility_note=request.visibility_note,
        observed_description=request.observed_description,
        subject=(request.subject or "player").strip().lower() or "player",
        loras=lora_payload,
        negative_override=request.negative_override or "",
        kinds=request.kinds or ["face", "fullbody"],
    )


@app.get("/api/image/character-lock")
@app.post("/api/image/character-lock")
def api_image_character_lock():
    """Probe Forge for InstantID / IP-Adapter Face / ReActor (no GPU)."""
    return probe_character_lock()


@app.post("/api/image/character-lock-test")
def api_image_character_lock_test():
    """
    Test character-lock stack: API up? ControlNet? InstantID/FaceID models?
    Does not generate an image — install checklist only (plus resolved mode).
    """
    probe = probe_character_lock()
    resolved = resolve_character_consistency_mode()
    return {
        "ok": bool(probe.get("ok")),
        "probe": probe,
        "resolved": {
            "mode": resolved.get("mode"),
            "use_strong": resolved.get("use_strong"),
            "use_light_img2img": resolved.get("use_light_img2img"),
            "fallback_reason": resolved.get("fallback_reason"),
        },
        "message": probe.get("message") or "",
        "install_hints": probe.get("install_hints") or [],
        "pass": bool(probe.get("strong_ready") or probe.get("api_ok")),
    }


@app.post("/api/image/character-ready")
def api_image_character_ready(request: CharacterArtReadyRequest):
    """Check whether identity + visibility are enough to generate art (no GPU work)."""
    name = request.name
    title = request.title
    known_as = request.known_as
    backstory = request.backstory
    world_style = request.world_style
    extra = request.extra
    age = request.age
    sex = request.sex
    equipment = list(request.equipment or [])
    injuries = list(request.injuries or [])
    visibility_note = request.visibility_note
    observed_description = request.observed_description
    subject = (request.subject or "player").strip().lower() or "player"
    if request.from_state:
        state = get_state()
        player = state.get("player") or {}
        options = ((state.get("settings") or {}).get("playthrough_options") or {})
        name = name or str(player.get("name") or "")
        title = title or str(player.get("title") or "")
        known_as = known_as or str(player.get("public_name") or "")
        backstory = backstory or str(player.get("backstory") or "")
        world_style = world_style or str(options.get("world_style") or "")
        age = age or str(player.get("age") or "")
        sex = sex or str(player.get("sex") or "")
    return assess_character_art_readiness(
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        age=age,
        sex=sex,
        equipment=equipment,
        injuries=injuries,
        visibility_note=visibility_note,
        observed_description=observed_description,
        subject=subject,
        require_backend=True,
    )


@app.post("/api/image/character-set")
def api_image_character_set(request: CharacterSetRequest):
    """Generate face + full-body character art (preset-driven dual pass)."""
    name = request.name
    title = request.title
    known_as = request.known_as
    backstory = request.backstory
    world_style = request.world_style
    extra = request.extra
    hair = request.hair
    facial_features = request.facial_features
    appearance = request.appearance
    equipment = list(request.equipment or [])
    injuries = list(request.injuries or [])
    level = request.level
    age = request.age
    sex = request.sex
    visibility_note = request.visibility_note
    observed_description = request.observed_description
    subject = (request.subject or "player").strip().lower() or "player"
    persist = bool(request.persist)
    if request.from_state:
        state = get_state()
        player = state.get("player") or {}
        options = ((state.get("settings") or {}).get("playthrough_options") or {})
        name = name or str(player.get("name") or "")
        title = title or str(player.get("title") or "")
        known_as = known_as or str(player.get("public_name") or "")
        backstory = backstory or str(player.get("backstory") or "")
        world_style = world_style or str(options.get("world_style") or "")
        hair = hair or str(options.get("hair") or "")
        facial_features = facial_features or str(options.get("facial_features") or "")
        appearance = appearance or str(options.get("appearance") or "")
        age = age or str(player.get("age") or "")
        sex = sex or str(player.get("sex") or "")
        try:
            level = int(player.get("level") or level or 1)
        except (TypeError, ValueError):
            level = 1
        if not equipment:
            starter = str(options.get("starter_equipment") or "")
            equipment = [p.strip() for p in starter.replace(";", ",").split(",") if p.strip()][:14]
            for item in state.get("inventory") or []:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("name") or "").strip()
                if not label:
                    continue
                if item.get("equipped_slot"):
                    equipment.append(f"{label} (equipped {item.get('equipped_slot')})")
                elif str(item.get("rarity") or "").lower() not in {"", "common", "mundane"}:
                    equipment.append(label)
            # de-dupe preserve order
            seen: set[str] = set()
            unique: list[str] = []
            for label in equipment:
                key = label.lower()
                if key in seen:
                    continue
                seen.add(key)
                unique.append(label)
            equipment = unique[:14]
        if not injuries:
            for cond in state.get("conditions") or []:
                if isinstance(cond, dict) and cond.get("name"):
                    injuries.append(str(cond.get("name")))
                elif isinstance(cond, dict) and cond.get("summary"):
                    injuries.append(str(cond.get("summary"))[:80])
        persist = True
        subject = "player"
    lora_payload = [
        {"name": str(item.name or "").strip(), "weight": float(item.weight)}
        for item in (request.loras or [])
        if str(item.name or "").strip()
    ]
    result = generate_character_set(
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        hair=hair,
        facial_features=facial_features,
        appearance=appearance,
        equipment=equipment,
        injuries=injuries,
        level=level,
        age=age,
        sex=sex,
        kinds=request.kinds or ["face", "fullbody"],
        seed=request.seed,
        launch_if_offline=bool(request.launch_if_offline),
        persist=persist,
        visibility_note=visibility_note,
        observed_description=observed_description,
        subject=subject,
        loras=lora_payload,
        use_face_reference=request.use_face_reference,
        reference_data_url=request.reference_data_url or "",
        negative_override=request.negative_override or "",
        face_prompt=request.face_prompt or "",
        fullbody_prompt=request.fullbody_prompt or "",
        face_negative=request.face_negative or "",
        fullbody_negative=request.fullbody_negative or "",
        forge_enable_hr=request.forge_enable_hr,
        forge_hr_scale=request.forge_hr_scale,
        forge_hr_upscaler=request.forge_hr_upscaler,
        forge_denoising_strength=request.forge_denoising_strength,
        forge_hr_second_pass_steps=request.forge_hr_second_pass_steps,
    )
    if not result.get("ok"):
        # 424 Failed Dependency-ish; use 400 with structured body for UI
        raise HTTPException(
            status_code=400,
            detail={
                "error": result.get("error") or "Character art generation failed",
                "missing": result.get("missing")
                or result.get("subject_readiness", {}).get("missing")
                or result.get("readiness", {}).get("missing")
                or [],
                "readiness": result.get("readiness"),
                "subject_readiness": result.get("subject_readiness"),
                "visibility_mode": result.get("visibility_mode"),
                "install_hints": (result.get("readiness") or {}).get("install_hints") or [],
            },
        )
    return result


@app.post("/api/image/generate")
def api_image_generate(request: ImageGenerateRequest):
    result = generate_image(
        prompt=request.prompt,
        negative_prompt=request.negative_prompt,
        width=request.width,
        height=request.height,
        steps=request.steps,
        cfg_scale=request.cfg_scale,
        seed=request.seed,
        purpose=request.purpose or "generic",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Image generation failed")
    # Avoid huge accidental double payloads in logs — still return data_url for UI.
    return result


@app.post("/api/image/portrait")
def api_image_portrait(request: PortraitRequest):
    """Player portrait; when from_state=true, pulls gear/level/injuries from world."""
    name = request.name
    title = request.title
    known_as = request.known_as
    backstory = request.backstory
    world_style = request.world_style
    extra = request.extra
    equipment = list(request.equipment or [])
    injuries = list(request.injuries or [])
    level = request.level
    age = request.age
    sex = request.sex
    if request.from_state:
        state = get_state()
        player = state.get("player") or {}
        options = ((state.get("settings") or {}).get("playthrough_options") or {})
        name = name or str(player.get("name") or "")
        title = title or str(player.get("title") or "")
        known_as = known_as or str(player.get("public_name") or "")
        backstory = backstory or str(player.get("backstory") or "")
        world_style = world_style or str(options.get("world_style") or "")
        age = age or str(player.get("age") or "")
        sex = sex or str(player.get("sex") or "")
        try:
            level = int(player.get("level") or level or 1)
        except (TypeError, ValueError):
            level = 1
        if not equipment:
            for item in state.get("inventory") or []:
                if not isinstance(item, dict):
                    continue
                # Prefer equipped; still include notable carried gear.
                label = str(item.get("name") or "").strip()
                if not label:
                    continue
                if item.get("equipped_slot"):
                    equipment.append(f"{label} (equipped {item.get('equipped_slot')})")
                elif str(item.get("rarity") or "").lower() not in {"", "common", "mundane"}:
                    equipment.append(label)
            equipment = equipment[:14]
        if not injuries:
            for cond in state.get("conditions") or []:
                if isinstance(cond, dict) and cond.get("name"):
                    injuries.append(str(cond.get("name")))
                elif isinstance(cond, dict) and cond.get("summary"):
                    injuries.append(str(cond.get("summary"))[:80])
    prompt = build_portrait_prompt(
        name=name,
        title=title,
        known_as=known_as,
        backstory=backstory,
        world_style=world_style,
        extra=extra,
        equipment=equipment,
        level=level,
        injuries=injuries,
        age=age,
        sex=sex,
    )
    result = generate_image(
        prompt=prompt,
        width=request.width,
        height=request.height,
        steps=request.steps,
        seed=request.seed,
        purpose="portrait",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Portrait generation failed")
    result["built_prompt"] = prompt
    result["equipment_used"] = equipment
    result["injuries_used"] = injuries
    # Cache last player portrait for UI reloads
    if result.get("data_url") and request.from_state:
        try:
            from app.db import connect as _connect

            with _connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('player_portrait', ?)",
                    (
                        json.dumps(
                            {
                                "data_url": result.get("data_url"),
                                "path": result.get("path") or "",
                                "prompt": prompt[:8000],
                                "equipment": equipment,
                                "level": level,
                                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            },
                            ensure_ascii=True,
                        ),
                    ),
                )
        except Exception:
            pass
    return result


class NpcPortraitRequest(BaseModel):
    code: str = Field(default="", max_length=40)
    name: str = Field(default="", max_length=100)
    role: str = Field(default="", max_length=120)
    race: str = Field(default="", max_length=80)
    summary: str = Field(default="", max_length=600)
    personality: str = Field(default="", max_length=400)
    extra: str = Field(default="", max_length=300)
    visibility_note: str = Field(default="", max_length=400)
    observed_description: str = Field(default="", max_length=800)
    width: int | None = None
    height: int | None = None


@app.post("/api/image/npc-portrait")
def api_image_npc_portrait(request: NpcPortraitRequest):
    """Portrait for an NPC using race/role/summary traits.

    Art is scoped to what the player can see: a drain-glimpse stays a glimpse,
    not a full invented character sheet.
    """
    from app.world import get_state

    name = request.name
    role = request.role
    race = request.race
    summary = request.summary
    personality = request.personality
    visibility_note = request.visibility_note
    observed_description = request.observed_description
    npc_appearance = ""
    if request.code:
        state = get_state()
        for loc in state.get("locations") or []:
            for npc in loc.get("npcs") or []:
                if str(npc.get("code") or "") == request.code or str(npc.get("name") or "") == request.code:
                    name = name or str(npc.get("name") or "")
                    role = role or str(npc.get("role") or "")
                    race = race or str(npc.get("race") or "")
                    summary = summary or str(npc.get("summary") or "")
                    personality = personality or str(npc.get("personality") or "")
                    npc_appearance = str(npc.get("appearance") or "").strip()
                    # Prefer explicit NPC visibility fields when present.
                    if not visibility_note:
                        visibility_note = str(
                            npc.get("visibility_note")
                            or npc.get("player_visibility")
                            or npc.get("seen_as")
                            or ""
                        )
                    if not observed_description:
                        known = npc.get("known_facts")
                        if isinstance(known, list):
                            known = "; ".join(str(k) for k in known[:6] if k)
                        observed_description = str(
                            npc.get("observed_description")
                            or npc_appearance
                            or known
                            or summary
                            or ""
                        )
                    break
    options = ((get_state().get("settings") or {}).get("playthrough_options") or {})
    world_style = str(options.get("world_style") or "")
    observed = (observed_description or summary or "").strip()
    # Build a short observed blob for readiness/visibility.
    observed_blob = ", ".join(
        p
        for p in (
            f"{race}" if race else "",
            f"{role}" if role else "",
            observed,
            personality[:120] if personality else "",
        )
        if p
    )
    gate = assess_character_art_readiness(
        name=name or "",
        title=role or "",
        backstory=summary or "",
        world_style=world_style,
        extra=request.extra or "",
        visibility_note=visibility_note,
        observed_description=observed_blob or observed,
        subject="npc",
        require_backend=True,
    )
    if not gate.get("can_generate"):
        raise HTTPException(
            status_code=400,
            detail={
                "error": gate.get("message") or "Not enough visible info for NPC art.",
                "missing": gate.get("missing") or [],
                "subject_readiness": gate,
                "visibility_mode": gate.get("visibility_mode"),
            },
        )
    vis_mode = str(gate.get("visibility_mode") or "full")
    vis_note = str(gate.get("visibility_note") or visibility_note or "")
    extra_bits = ", ".join(
        p
        for p in (
            f"{race} person" if race and vis_mode == "full" else "",
            f"role {role}" if role and vis_mode == "full" else "",
            personality[:160] if personality and vis_mode == "full" else "",
            request.extra,
        )
        if p
    )
    # Wardrobe input: explicit appearance, else what the player observed (zone-filtered).
    npc_look = (npc_appearance or observed_description or observed or "").strip()
    prompt = build_portrait_prompt(
        name=name or "npc",
        title=role if vis_mode == "full" else "",
        backstory=summary if vis_mode == "full" else "",
        world_style=world_style,
        extra=extra_bits,
        appearance=npc_look,
        equipment=[],
        visibility_mode=vis_mode,
        visibility_note=vis_note,
        observed_description=observed_blob or observed,
        kind="face",
    )
    result = generate_image(
        prompt=prompt,
        width=request.width or 384,
        height=request.height or 384,
        purpose="npc_portrait",
        # No silent forge_active_loras injection — LoRAs only when the request passes them.
        loras=None,
        apply_loras=False,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "NPC portrait failed")
    result["built_prompt"] = prompt
    result["visibility_mode"] = vis_mode
    result["visibility_note"] = vis_note
    result["subject_readiness"] = gate
    result["npc"] = {"code": request.code, "name": name, "role": role, "race": race}
    return result


# --- Tile world / map presets / image archive ---------------------------------


def _location_special_runtime() -> dict[str, Any]:
    """Read map_blank / movement_locked flags (heavens prison, etc.)."""
    from app.db import connect as _connect

    flags: dict[str, Any] = {}
    movement_locked = False
    map_blank = False
    try:
        with _connect() as conn:
            rows = {
                str(r["key"]): r["value"]
                for r in conn.execute(
                    "SELECT key, value FROM settings WHERE key IN "
                    "('location_special_flags', 'movement_locked', 'map_blank')"
                ).fetchall()
            }
        raw = rows.get("location_special_flags")
        if raw:
            try:
                loaded = json.loads(raw) if isinstance(raw, str) else raw
                if isinstance(loaded, dict):
                    flags = loaded
            except Exception:
                flags = {}
        ml = rows.get("movement_locked")
        if ml is not None:
            try:
                movement_locked = bool(json.loads(ml)) if str(ml).strip()[:1] in "[{tTfF0123456789" else str(ml).lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            except Exception:
                movement_locked = str(ml).lower() in {"1", "true", "yes", "on"}
        else:
            movement_locked = bool(flags.get("movement_locked"))
        mb = rows.get("map_blank")
        if mb is not None:
            try:
                map_blank = bool(json.loads(mb)) if str(mb).strip()[:1] in "[{tTfF0123456789" else str(mb).lower() in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            except Exception:
                map_blank = str(mb).lower() in {"1", "true", "yes", "on"}
        else:
            map_blank = bool(flags.get("map_blank"))
    except Exception:
        pass
    return {
        "flags": flags,
        "movement_locked": bool(movement_locked),
        "map_blank": bool(map_blank),
        "label": str(flags.get("label") or ("Bound" if movement_locked else "")),
        "hint": str(
            flags.get("hint")
            or (
                "The map shows nothing. You cannot walk free until something changes your confinement."
                if map_blank or movement_locked
                else ""
            )
        ),
    }


def _blank_map_payload(*, radius: int | None = None, full: bool = False) -> dict[str, Any]:
    """Empty map view for heavens / prison confinement."""
    runtime = _location_special_runtime()
    payload: dict[str, Any] = {
        "empty": True,
        "map_blank": True,
        "movement_locked": True,
        "tiles": [],
        "ascii": "",
        "player": {"x": 0, "y": 0},
        "settlements": [],
        "settlements_nearby": [],
        "markers": [],
        "visited_count": 0,
        "vision_radius": 0,
        "location_special_flags": runtime.get("flags") or {},
        "confinement": {
            "label": runtime.get("label") or "The Heavens — bound",
            "hint": runtime.get("hint")
            or "The map shows nothing. You cannot walk free until something changes your confinement.",
            "reason": (runtime.get("flags") or {}).get("reason") or "celestial_confinement",
        },
    }
    if radius is not None:
        payload["radius"] = radius
    if full:
        payload["mode"] = "full"
    return payload


@app.get("/api/tiles/states")
def api_tile_states():
    return {"states": list_tile_states()}


@app.get("/api/tiles/presets")
def api_tile_presets():
    return {"presets": list_world_presets()}


@app.get("/api/tiles/maps")
def api_tile_maps():
    return {"maps": list_maps()}


@app.get("/api/tiles/map")
def api_tile_map(map_id: str = "", legacy: bool = False):
    runtime = _location_special_runtime()
    if runtime.get("map_blank") and not legacy:
        return _blank_map_payload()
    if legacy:
        from app.tile_world import get_legacy_map

        data = get_legacy_map()
    else:
        data = get_map(map_id or None)
    if not data:
        # Soft empty payload so the UI can boot without a hard 404.
        payload = {"id": None, "tiles": [], "ascii": "", "empty": True}
        if legacy:
            payload["legacy"] = True
            payload["map_role"] = "legacy"
        return payload
    if data.get("scale") == "world":
        from app.world_scale import preview_window

        preview = preview_window(data)
        data["preview"] = preview
        data["ascii"] = preview.get("ascii") or ""
        data.pop("cell_index", None)
    else:
        data["ascii"] = ascii_preview(data)
    data["empty"] = False
    data["map_blank"] = False
    data["movement_locked"] = bool(runtime.get("movement_locked"))
    data["location_special_flags"] = runtime.get("flags") or {}
    # Drop heavy nested grid duplicate if client only needs tiles
    return data


def _map_avatar_payload() -> dict[str, Any]:
    from app.db import connect as _connect

    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'map_avatar'").fetchone()
    if not row:
        # Fall back to player portrait if present
        with _connect() as conn:
            prow = conn.execute("SELECT value FROM settings WHERE key = 'player_portrait'").fetchone()
        if prow:
            try:
                portrait = json.loads(prow["value"] or "{}")
                if isinstance(portrait, dict) and portrait.get("data_url"):
                    return {
                        "data_url": "",
                        "source": "portrait_available",
                        "has_portrait": True,
                        "portrait_data_url": portrait.get("data_url"),
                    }
            except Exception:
                pass
        return {"data_url": "", "source": "none", "has_portrait": False}
    try:
        raw = json.loads(row["value"] or "{}")
        if isinstance(raw, dict):
            return {
                "data_url": str(raw.get("data_url") or "")[:2_000_000],
                "source": str(raw.get("source") or "upload"),
                "tile_px": int(raw.get("tile_px") or 32),
                "has_portrait": True,
            }
    except Exception:
        pass
    return {"data_url": "", "source": "none"}


@app.get("/api/tiles/map/local")
def api_tile_map_local(radius: int = 6):
    """Circular local map centered on the player (follows). Vision is still 1-tile LOS."""
    runtime = _location_special_runtime()
    if runtime.get("map_blank"):
        blank = _blank_map_payload(radius=radius)
        blank["map_avatar"] = _map_avatar_payload()
        blank["tile_px"] = int((_map_avatar_payload() or {}).get("tile_px") or 32)
        return blank
    data = get_map(None)
    if not data:
        return {"empty": True, "tiles": [], "radius": radius}
    view = local_map_view(data, radius=radius)
    if data.get("scale") == "world":
        view["ascii"] = (
            f"{data.get('width')}×{data.get('height')} · density {data.get('density_percent')}% · "
            f"{len(data.get('cities') or [])} settlements"
        )
        view["scale"] = "world"
    else:
        view["ascii"] = ascii_preview(data)
    view["id"] = data.get("id")
    view["preset_id"] = data.get("preset_id")
    view["map_avatar"] = _map_avatar_payload()
    view["tile_px"] = int((_map_avatar_payload() or {}).get("tile_px") or 32)
    view["map_blank"] = False
    view["movement_locked"] = bool(runtime.get("movement_locked"))
    view["location_special_flags"] = runtime.get("flags") or {}
    return view


@app.get("/api/tiles/map/full")
def api_tile_map_full():
    runtime = _location_special_runtime()
    if runtime.get("map_blank"):
        blank = _blank_map_payload(full=True)
        blank["map_avatar"] = _map_avatar_payload()
        blank["tile_px"] = int((_map_avatar_payload() or {}).get("tile_px") or 32)
        return blank
    data = get_map(None)
    if not data:
        return {"empty": True, "tiles": [], "settlements": []}
    view = full_map_view(data)
    view["map_avatar"] = _map_avatar_payload()
    view["tile_px"] = int((_map_avatar_payload() or {}).get("tile_px") or 32)
    view["map_blank"] = False
    view["movement_locked"] = bool(runtime.get("movement_locked"))
    view["location_special_flags"] = runtime.get("flags") or {}
    return view


class MapSurveyRequest(BaseModel):
    """Survey / lookout: DM decides height (vantage) and clarity (weather/distance)."""

    radius: int = Field(default=3, ge=1, le=16)
    height: int | None = Field(default=None, ge=0, le=4)
    clarity: float = Field(default=1.0, ge=0.1, le=1.5)


@app.post("/api/tiles/map/survey")
def api_tile_map_survey(request: MapSurveyRequest):
    """Expand map vision from the player's tile with LOS (mountains block unless height helps)."""
    runtime = _location_special_runtime()
    if runtime.get("map_blank") or runtime.get("movement_locked"):
        raise HTTPException(
            status_code=409,
            detail=runtime.get("hint") or "No map to survey — you are confined.",
        )
    data = get_map(None)
    if not data:
        raise HTTPException(status_code=400, detail="No active map.")
    result = apply_survey(
        data,
        radius=int(request.radius),
        height=request.height,
        clarity=float(request.clarity),
    )
    view = full_map_view(data)
    return {"ok": True, "survey": result, "map": view, "local": local_map_view(data, radius=6)}


class MapKnowledgeRequest(BaseModel):
    """Intel from locals, maps, or lived memory — towns/danger without full terrain."""

    settlement_ids: list[str] = Field(default_factory=list)
    danger: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[dict[str, Any]] = Field(default_factory=list)
    source: str = Field(default="rumor", max_length=60)
    # Lived-life helper (optional): auto-grant nearby towns/danger from age/traveler.
    lived: bool = False
    age: int = Field(default=25, ge=12, le=120)
    traveler: bool = True


@app.post("/api/tiles/map/knowledge")
def api_tile_map_knowledge(request: MapKnowledgeRequest):
    data = get_map(None)
    if not data:
        raise HTTPException(status_code=400, detail="No active map.")
    lived_result = None
    if request.lived:
        lived_result = grant_lived_area_knowledge(
            data,
            age=int(request.age),
            traveler=bool(request.traveler),
            source=str(request.source or "lived"),
        )
    knowledge = grant_map_knowledge(
        data,
        settlement_ids=list(request.settlement_ids or []),
        danger=list(request.danger or []),
        notes=list(request.notes or []),
        source=str(request.source or "rumor"),
        save=True,
    )
    view = full_map_view(data)
    return {
        "ok": True,
        "knowledge": knowledge,
        "lived": lived_result,
        "map": view,
        "settlements": view.get("settlements") or [],
        "markers": view.get("markers") or [],
    }


class MapAvatarRequest(BaseModel):
    """Set the player head token drawn on the map."""

    data_url: str = Field(default="", max_length=2_500_000)
    from_portrait: bool = False
    crop_head: bool = True
    tile_px: int = Field(default=32, ge=16, le=32)  # 16-bit or 32-bit style cells
    clear: bool = False


@app.get("/api/map-avatar")
def api_map_avatar_get():
    return _map_avatar_payload()


@app.post("/api/map-avatar")
def api_map_avatar_set(request: MapAvatarRequest):
    """Upload a head image, crop from player portrait, or clear."""
    from app.db import connect as _connect

    if request.clear:
        with _connect() as conn:
            conn.execute("DELETE FROM settings WHERE key = 'map_avatar'")
        return {"ok": True, "cleared": True, **_map_avatar_payload()}

    data_url = (request.data_url or "").strip()
    source = "upload"
    if request.from_portrait and not data_url:
        with _connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'player_portrait'").fetchone()
        if not row:
            raise HTTPException(status_code=400, detail="No player portrait yet. Generate one on the Player tab first.")
        try:
            portrait = json.loads(row["value"] or "{}")
            data_url = str(portrait.get("data_url") or "")
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Stored portrait unreadable") from exc
        if not data_url.startswith("data:image"):
            raise HTTPException(status_code=400, detail="Portrait has no image data")
        source = "portrait_head" if request.crop_head else "portrait"
        # Client usually crops; if raw portrait used, store as-is (UI prefers crop).
    if not data_url.startswith("data:image"):
        raise HTTPException(status_code=400, detail="Provide a data:image… URL or from_portrait=true")
    # Cap ~1.5MB of base64 payload for DB sanity
    if len(data_url) > 1_800_000:
        raise HTTPException(status_code=400, detail="Image too large for map avatar (keep under ~1MB).")
    tile_px = 16 if int(request.tile_px) <= 16 else 32
    payload = {
        "data_url": data_url,
        "source": source,
        "tile_px": tile_px,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('map_avatar', ?)",
            (json.dumps(payload, ensure_ascii=True),),
        )
    return {"ok": True, **payload, "data_url": data_url[:80] + "…"}


class MapMoveRequest(BaseModel):
    """Absolute tile or one-step delta. Adjacent steps (arrow keys) never require Continue."""
    x: int | None = None
    y: int | None = None
    dx: int = 0
    dy: int = 0
    force: bool = False
    # free = map walk only (no scene lock). scene = long jump / settlement walk may gate.
    mode: str = Field(default="free", max_length=20)


@app.post("/api/tiles/map/move")
def api_tile_map_move(request: MapMoveRequest):
    from app.db import connect as _connect
    from app.world import get_state

    runtime = _location_special_runtime()
    if runtime.get("movement_locked") or runtime.get("map_blank"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": runtime.get("hint")
                or "You cannot move — confined (blank map / prison state).",
                "movement_locked": True,
                "map_blank": bool(runtime.get("map_blank")),
                "label": runtime.get("label") or "Bound",
                "reason": (runtime.get("flags") or {}).get("reason") or "confinement",
            },
        )
    data = get_map(None)
    if not data:
        raise HTTPException(status_code=400, detail="No active map.")
    px = int((data.get("player") or {}).get("x") or 0)
    py = int((data.get("player") or {}).get("y") or 0)
    # Prefer absolute coords; else apply one-step delta (arrow keys / d-pad).
    if request.x is not None and request.y is not None:
        tx, ty = int(request.x), int(request.y)
    else:
        dx = max(-1, min(1, int(request.dx or 0)))
        dy = max(-1, min(1, int(request.dy or 0)))
        if dx == 0 and dy == 0:
            raise HTTPException(status_code=400, detail="Provide x,y or dx,dy.")
        tx, ty = px + dx, py + dy
    manh = abs(tx - px) + abs(ty - py)
    cheb = max(abs(tx - px), abs(ty - py))
    # Orthogonal or diagonal one-tile steps stay free (no Continue / travel lock).
    free_step = cheb <= 1 and manh > 0 and (request.mode or "free").lower() != "scene"
    # Long jumps still respect travel_ready unless force
    if not free_step and not request.force:
        with _connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'travel_ready'").fetchone()
        ready = True
        if row:
            try:
                ready = (
                    json.loads(row["value"])
                    if str(row["value"]).strip()[:1] in "[{tTfF0123456789"
                    else str(row["value"]).lower() in {"1", "true", "yes", "on"}
                )
            except Exception:
                ready = str(row["value"]).lower() in {"1", "true", "yes", "on"}
        if not ready:
            raise HTTPException(
                status_code=409,
                detail="Long travel is locked until the scene is free — use adjacent steps (arrows) anytime.",
            )
    try:
        view = move_player(None, tx, ty)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Adjacent free steps keep travel open so the player can keep walking.
    # Scene/settlement jumps still close travel for a beat.
    next_ready = True if free_step else False
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', ?)",
            (json.dumps(next_ready),),
        )
    travel = view.get("travel") if isinstance(view, dict) else None
    travel_result = {}
    scene_turn = None
    try:
        # Advance in-world minutes, seed rulers, roll path/forest encounters into DB shells
        travel_result = apply_map_travel_step(travel, get_state(include_hidden=False))
    except Exception:
        travel_result = {"error": "travel_apply_failed"}
    # Exhausted: undo map move so position matches server resource gate
    if isinstance(travel_result, dict) and travel_result.get("blocked"):
        try:
            from app.tile_world import restore_player_position

            view = restore_player_position(None, px, py)
            # Keep travel meta for UI feedback
            if isinstance(view, dict):
                view["travel"] = travel if isinstance(travel, dict) else {}
                view["travel_blocked"] = True
        except Exception:
            pass
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Too exhausted to travel — wait, meditate, or sleep to recover energy.",
                "reasons": (travel_result.get("resource_spend") or {}).get("reasons")
                or travel_result.get("reasons")
                or ["insufficient_energy"],
                "resources": travel_result.get("resources"),
                "resource_spend": travel_result.get("resource_spend"),
            },
        )
    # Ambush / path event → full scene turn (RNG already decided)
    if travel_result.get("needs_scene") and travel_result.get("queued_event"):
        try:
            # Lock long travel during the beat; free steps stay allowed via free_step logic later
            next_ready = False
            with _connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('travel_ready', ?)",
                    (json.dumps(False),),
                )
            scene_turn = play_world_event_turn(travel_result["queued_event"], input_kind="event")
            travel_result["scene_fired"] = True
        except Exception as exc:
            travel_result["scene_error"] = str(exc)[:300]
    try:
        autosave_campaign()
    except Exception:
        pass
    state = get_state()
    payload = {
        "map": view,
        "travel_ready": next_ready if scene_turn is None else False,
        "state": (scene_turn or {}).get("state") or state,
        "ok": True,
        "step": {
            "from": [px, py],
            "to": [tx, ty],
            "free": free_step,
            "minutes": (travel or {}).get("minutes") if isinstance(travel, dict) else 0,
            "terrain": (travel or {}).get("terrain") if isinstance(travel, dict) else "",
        },
        "travel": travel if isinstance(travel, dict) else {},
        "travel_result": travel_result,
    }
    if scene_turn:
        payload["scene_turn"] = scene_turn
        payload["turn"] = scene_turn.get("turn")
        payload["narration"] = (scene_turn.get("turn") or {}).get("narration") or scene_turn.get("narration")
        payload["used_fallback"] = scene_turn.get("used_fallback")
        payload["input_kind"] = "event"
        payload["world_event"] = scene_turn.get("world_event")
    # Ambient DM color never locks movement
    payload["ambient"] = (travel_result or {}).get("ambient") or ""
    payload["weather"] = (travel_result or {}).get("weather") or (state or {}).get("weather")
    return payload


@app.get("/api/tiles/map/settlements")
def api_tile_settlements():
    data = get_map(None)
    if not data:
        return {"settlements": []}
    return {"settlements": list_settlements(data)}


@app.get("/api/travel-status")
def api_travel_status():
    from app.db import connect as _connect

    runtime = _location_special_runtime()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'travel_ready'").fetchone()
    ready = True
    if row:
        try:
            ready = json.loads(row["value"])
        except Exception:
            ready = str(row["value"]).lower() in {"1", "true", "yes", "on"}
    if runtime.get("movement_locked") or runtime.get("map_blank"):
        ready = False
    return {
        "travel_ready": bool(ready),
        "movement_locked": bool(runtime.get("movement_locked")),
        "map_blank": bool(runtime.get("map_blank")),
        "location_special_flags": runtime.get("flags") or {},
        "confinement_label": runtime.get("label") or "",
        "confinement_hint": runtime.get("hint") or "",
    }


@app.post("/api/tiles/generate")
def api_tiles_generate(request: MapGenerateRequest):
    try:
        # An explicit width stays on the small board. The default is the world grid.
        if request.width is None and request.height is None and request.scale != "board":
            from app.tile_world import generate_scaled_world

            data = generate_scaled_world(
                preset_id=request.preset_id or "forest_march",
                seed=request.seed,
                density_percent=request.density_percent,
                notice_percent=request.notice_percent,
            )
        else:
            data = generate_map(
                preset_id=request.preset_id or "forest_march",
                seed=request.seed,
                width=request.width,
                height=request.height,
                assign_images=request.assign_images,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not data.get("ascii"):
        data["ascii"] = ascii_preview(data)
    # Response size: omit nested grid if large; keep flat tiles
    data.pop("grid", None)
    data.pop("cell_index", None)
    return data


@app.post("/api/tiles/map/reveal")
def api_tiles_map_reveal(request: MapRevealRequest):
    from app.local_intel import run_map_command

    label = request.label or ""
    result = run_map_command("reveal", f"{request.x} {request.y} {request.radius} {label}".strip())
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "Could not reveal that cell."))
    return result


@app.post("/api/tiles/map/marker")
def api_tiles_map_marker(request: MapMarkerRequest):
    from app.local_intel import run_map_command

    result = run_map_command("mark", f"{request.x} {request.y} {request.label}".strip())
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "Could not mark that cell."))
    return result


@app.post("/api/tiles/images/search")
def api_tile_images_search(request: TileImageSearchRequest):
    items = search_tile_images(
        query=request.query,
        state_id=request.state_id,
        include_disabled=request.include_disabled,
        run_id=request.run_id,
        limit=request.limit,
    )
    return {"images": items, "count": len(items)}


@app.post("/api/tiles/images")
def api_tile_images_add(request: TileImageAddRequest):
    try:
        item = add_tile_image(
            state_id=request.state_id,
            path=request.path,
            data_url=request.data_url,
            source=request.source,
            prompt=request.prompt,
            tags=request.tags,
            quality=request.quality,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


@app.post("/api/tiles/images/disable-forever")
def api_tile_images_disable_forever(request: TileImageBulkRequest):
    n = set_tile_images_disabled_forever(request.image_ids, disabled=request.disabled)
    return {"updated": n, "disabled": request.disabled}


@app.post("/api/tiles/images/disable-run")
def api_tile_images_disable_run(request: TileImageBulkRequest):
    if not request.run_id:
        raise HTTPException(status_code=400, detail="run_id required")
    n = disable_tile_images_for_run(request.image_ids, request.run_id)
    return {"updated": n, "run_id": request.run_id}


@app.post("/api/tiles/images/clear-run-disables")
def api_tile_images_clear_run(request: TileImageBulkRequest):
    if not request.run_id:
        raise HTTPException(status_code=400, detail="run_id required")
    clear_run_disables(request.run_id)
    return {"ok": True, "run_id": request.run_id}


@app.post("/api/tiles/images/delete")
def api_tile_images_delete(request: TileImageBulkRequest):
    n = delete_tile_images(request.image_ids, delete_files=True)
    return {"deleted": n}


@app.post("/api/tiles/images/generate")
def api_tile_images_generate(request: TileImageGenerateRequest):
    """Create tile art via Forge/Comfy and archive it under the state."""
    prompt = request.prompt.strip() or suggest_tile_prompt(
        request.state_id,
        quality=request.quality or "8bit",
        preset_id=request.preset_id or "",
    )
    result = generate_image(
        prompt=prompt,
        width=request.width or 64,
        height=request.height or 64,
        steps=request.steps,
        purpose=f"tile-{request.state_id}",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Tile image generation failed")
    try:
        item = add_tile_image(
            state_id=request.state_id,
            path=str(result.get("path") or ""),
            data_url=str(result.get("data_url") or ""),
            source="generated",
            prompt=prompt,
            tags=request.tags or request.state_id,
            quality=request.quality or "8bit",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"image": item, "generation": {k: result.get(k) for k in ("ok", "provider", "seed", "elapsed_ms", "path")}}


def _agent_authorized(token: str = "") -> bool:
    """Optional shared secret for external agents. Empty AI_RPG_AGENT_TOKEN = open local trust."""
    expected = str(os.getenv("AI_RPG_AGENT_TOKEN") or "").strip()
    if not expected:
        return True
    return str(token or "").strip() == expected


@app.get("/api/agent/health")
def api_agent_health():
    cfg = public_model_config()
    return {
        "ok": True,
        "app": "Morkyn",
        "agent_bridge": True,
        "auth_required": bool(str(os.getenv("AI_RPG_AGENT_TOKEN") or "").strip()),
        "provider": cfg.get("provider"),
        "api_model": cfg.get("api_model"),
        "api_key_set": cfg.get("api_key_set"),
    }


@app.get("/api/agent/state")
def api_agent_state(token: str = ""):
    if not _agent_authorized(token):
        raise HTTPException(status_code=401, detail="Invalid agent token")
    return get_state()


@app.post("/api/agent/turn")
def api_agent_turn(request: AgentTurnRequest):
    """External agents (Grok, scripts, tools) submit player actions here."""
    if not _agent_authorized(request.token):
        raise HTTPException(status_code=401, detail="Invalid agent token")
    text = (request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    try:
        return play_turn(text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/agent/opening")
def api_agent_opening(token: str = ""):
    if not _agent_authorized(token):
        raise HTTPException(status_code=401, detail="Invalid agent token")
    try:
        from app.world import play_opening_turn

        return play_opening_turn()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/launcher-prefs")
def api_launcher_prefs_get():
    return {"prefs": load_prefs(), "path": "data/launcher_prefs.json"}


class LauncherPrefsRequest(BaseModel):
    prefs: dict[str, Any] = Field(default_factory=dict)
    apply_env: bool = True


@app.post("/api/launcher-prefs")
def api_launcher_prefs_set(request: LauncherPrefsRequest):
    saved = save_prefs(request.prefs or {})
    if request.apply_env:
        apply_prefs_to_env(saved)
        # Also push into live model config when possible
        try:
            cfg = get_model_config()
            if saved.get("model_provider"):
                cfg["provider"] = saved["model_provider"]
            if saved.get("mle_model"):
                cfg["mle_model"] = saved["mle_model"]
            if saved.get("gguf_model_path"):
                cfg["gguf_model_path"] = saved["gguf_model_path"]
            if saved.get("api_base_url"):
                cfg["api_base_url"] = saved["api_base_url"]
            if saved.get("api_model"):
                cfg["api_model"] = saved["api_model"]
            if saved.get("soft_response_tokens"):
                cfg["response_token_cap"] = int(saved["soft_response_tokens"])
            if saved.get("hard_response_tokens"):
                cfg["response_token_hard_cap"] = int(saved["hard_response_tokens"])
            update_model_config(cfg)
        except Exception:
            pass
    return {"ok": True, "prefs": saved, "applied_env": bool(request.apply_env)}


@app.get("/api/model-status")
def api_model_status():
    try:
        status = test_model_connection()
        if isinstance(status, dict):
            status["llm_runtime"] = get_llm_runtime()
            notice = _context_notice_safely()
            if notice:
                status["notice"] = notice
            if not status.get("ok"):
                from app.mle import last_problem

                provider = str(status.get("provider") or "")
                problem = last_problem() if provider == "mle" else None
                status["problem"] = problem or classify_failure(
                    status.get("error") or "", stage="load", provider=provider
                )
        return status
    except Exception as exc:
        return JSONResponse(
            status_code=200,
            content={
                "ok": False,
                "provider": "unknown",
                "url": "",
                "error": f"Model status check failed: {exc}",
                "config": {},
                "managed_start": None,
                "llm_runtime": get_llm_runtime(),
                "problem": classify_failure(str(exc), stage="load"),
            },
        )


@app.get("/api/llm-runtime")
def api_llm_runtime():
    """
    LLM process phase only. Web/UI is always independent.
    phase: offline | starting | switching | ready | error
    method: none | hot_swap | soft_recycle | already_ready
    """
    snap = get_llm_runtime()
    if snap.get("phase") == "error":
        snap["problem"] = classify_failure(snap.get("error") or snap.get("user_message") or "", stage="runtime")
    else:
        notice = _context_notice_safely()
        if notice:
            snap["notice"] = notice
    return snap


def _context_notice_safely() -> dict[str, Any] | None:
    """The too-small-context notice, or None; a status route must never fail over it."""
    try:
        from app.llm import context_contract_notice

        return context_contract_notice()
    except Exception:
        return None


@app.post("/api/failsafe/mle-fallback")
def api_mle_fallback():
    """The player accepted the smaller context. Load with it now and report."""
    from app.llm import get_model_config
    from app.mle import allow_context_fallback, status as mle_status

    allow_context_fallback(True)
    config = get_model_config()
    report = mle_status(str(config.get("mle_model") or ""))
    body: dict[str, Any] = {"ok": bool(report.get("ok")), "status": report}
    if not report.get("ok"):
        body["problem"] = report.get("problem") or classify_failure(
            str(report.get("detail") or ""), stage="load", provider="mle"
        )
    return body


class LlmEnsureRequest(BaseModel):
    """Optional: force ensure with current model config (+ theme LoRA already in config if set)."""
    force_soft_recycle: bool = False


@app.post("/api/llm-runtime/ensure")
def api_llm_runtime_ensure(request: LlmEnsureRequest | None = None):
    """
    Ensure LLM base + LoRA match saved config.
    Tries hot-swap first; otherwise soft-recycles only the managed LLM process.
    Website stays up — client should poll GET /api/llm-runtime while phase is switching/starting.
    """
    req = request or LlmEnsureRequest()
    config = get_model_config(ignore_override=True)
    provider = str(config.get("provider") or "").strip().lower()
    if req.force_soft_recycle and provider in {"llama_cpp", "llamacpp", "llama.cpp", ""}:
        base_url = str(config.get("llama_cpp_base_url") or "http://localhost:8080").rstrip("/")
        return soft_recycle_llm_backend(config, base_url)
    try:
        return ensure_llm_adapter_ready(config)
    except LlmError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class SkillCheckRequest(BaseModel):
    skill_code: str = Field(default="general", max_length=80)
    difficulty: str = Field(default="", max_length=40)
    dc: int | None = None
    context_note: str = Field(default="", max_length=400)
    player_stats: dict[str, Any] = Field(default_factory=dict)
    player_skills: list[dict[str, Any]] = Field(default_factory=list)
    opposition: dict[str, Any] = Field(default_factory=dict)
    weapon_or_tool: str = Field(default="", max_length=80)
    settings: dict[str, Any] = Field(default_factory=dict)


class SkillRegisterRequest(BaseModel):
    name: str = Field(default="", max_length=80)
    code: str = Field(default="", max_length=64)
    category: str = Field(default="general", max_length=40)
    attribute: str = Field(default="intelligence", max_length=40)
    secondary: str = Field(default="wisdom", max_length=40)
    description: str = Field(default="", max_length=400)
    tags: list[str] = Field(default_factory=list)
    base_dc: int = 12
    source: str = Field(default="user", max_length=40)


class SkillEnableRequest(BaseModel):
    code: str = Field(..., max_length=64)
    enabled: bool = True


@app.get("/api/skill-checks/catalog")
def api_skill_check_catalog():
    return catalog_public()


@app.post("/api/skill-checks/resolve")
def api_skill_check_resolve(request: SkillCheckRequest):
    try:
        state = get_state()
        options = ((state.get("settings") or {}).get("playthrough_options") or {}) if isinstance(state, dict) else {}
        settings = request.settings or options.get("skill_check_settings") or options
        player = (state.get("player") or {}) if isinstance(state, dict) else {}
        explicit = request.player_stats if isinstance(request.player_stats, dict) else {}
        if explicit:
            stats = explicit
        elif isinstance(player.get("effective_stats"), dict):
            stats = scores_from_gear_bonuses(player.get("effective_stats"))
        else:
            raw_stats = player.get("stats")
            stats = raw_stats if isinstance(raw_stats, dict) else {}
        skills = request.player_skills or (state.get("skills") if isinstance(state, dict) else []) or []
        inventory = state.get("inventory") if isinstance(state, dict) else None
        abilities = state.get("abilities") if isinstance(state, dict) else None
        return resolve_check(
            skill_code=request.skill_code or "general",
            difficulty=request.difficulty or None,
            dc=request.dc,
            player_stats=stats if isinstance(stats, dict) else {},
            player_skills=skills if isinstance(skills, list) else [],
            opposition=request.opposition if isinstance(request.opposition, dict) else None,
            settings=settings if isinstance(settings, dict) else {},
            context_note=request.context_note,
            weapon_or_tool=request.weapon_or_tool or "",
            inventory=inventory if isinstance(inventory, list) else None,
            abilities=abilities if isinstance(abilities, list) else None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-checks/register")
def api_skill_check_register(request: SkillRegisterRequest):
    name = (request.name or request.code or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        return register_or_adjust_skill(request.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/skill-checks/enable")
def api_skill_check_enable(request: SkillEnableRequest):
    row = set_skill_enabled(request.code, request.enabled)
    if not row:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"skill": row}


# --- content packs -----------------------------------------------------------


class PackPayloadRequest(BaseModel):
    pack: dict[str, Any] = Field(default_factory=dict)


class PackIdRequest(BaseModel):
    pack_id: str = Field(..., max_length=64)


class PackEnableRequest(BaseModel):
    pack_id: str = Field(..., max_length=64)
    enabled: bool = True


@app.get("/api/content-packs")
def api_content_packs():
    """Installed packs with per-section counts."""
    from app.content_packs import list_packs

    return {"packs": list_packs()}


@app.get("/api/content-packs/authoring-bundle")
def api_content_pack_bundle():
    """
    Everything an external LLM needs to author a pack with zero project context:
    schema, field-to-column mapping, hard rules, an example, and existing codes.
    """
    from app.content_packs import authoring_bundle

    return authoring_bundle()


@app.post("/api/content-packs/validate")
def api_content_pack_validate(request: PackPayloadRequest):
    """Check a pack without installing it. Errors carry a JSON path and a fix."""
    from app.content_packs import validate_pack

    return validate_pack(request.pack)


@app.post("/api/content-packs/install")
def api_content_pack_install(request: PackPayloadRequest):
    from app.content_packs import PackError, apply_active_packs, install_pack

    try:
        result = install_pack(request.pack, source="api")
    except PackError as exc:
        raise HTTPException(status_code=400, detail=json.loads(str(exc))) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    apply_active_packs()
    return result


@app.post("/api/content-packs/remove")
def api_content_pack_remove(request: PackIdRequest):
    from app.content_packs import apply_active_packs, remove_pack

    result = remove_pack(request.pack_id)
    if not result.get("removed"):
        raise HTTPException(status_code=400, detail=result)
    apply_active_packs()
    return result


@app.post("/api/content-packs/enable")
def api_content_pack_enable(request: PackEnableRequest):
    from app.content_packs import apply_active_packs, set_pack_enabled

    result = set_pack_enabled(request.pack_id, request.enabled)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result)
    apply_active_packs()
    return result


@app.get("/api/content-packs/export/{pack_id}")
def api_content_pack_export(pack_id: str):
    """Get a pack back as JSON — for editing by hand or by another model."""
    from app.content_packs import export_pack

    pack = export_pack(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="Pack not installed")
    return pack


# --- dice + danger audit ------------------------------------------------------


@app.get("/api/dice/recent")
def api_dice_recent(limit: int = 40, turn: int | None = None):
    """Every server-rolled amount, newest first. This is the 'why did I get 7 gold' feed."""
    from app.rng import recent_rolls

    return {"rolls": recent_rolls(limit=limit, turn=turn)}


@app.get("/api/danger")
def api_danger():
    """Current danger assessment for the player's tile, with its factor breakdown."""
    from app import encounters as encounters_mod
    from app.world import get_weather, get_world_time

    try:
        snapshot = encounters_mod.player_snapshot()
        terrain = "plains"
        settlement = None
        try:
            from app.tile_world import get_map

            world_map = get_map(None)
            if world_map:
                px = int((world_map.get("player") or {}).get("x") or 0)
                py = int((world_map.get("player") or {}).get("y") or 0)
                for tile in world_map.get("tiles") or []:
                    if int(tile.get("x") or -1) == px and int(tile.get("y") or -1) == py:
                        terrain = str(tile.get("state") or "plains")
                        sid = tile.get("settlement_id")
                        if sid:
                            for meta in world_map.get("settlements_meta") or []:
                                if str(meta.get("id")) == str(sid):
                                    settlement = meta
                                    break
                        break
        except Exception:
            pass

        assessment = encounters_mod.assess_danger(
            terrain=terrain,
            weather=get_weather(),
            world_time=get_world_time(),
            player=player_with_gear_scores(snapshot.get("player")),
            skills=snapshot.get("skills"),
            resources=snapshot.get("resources"),
            inventory_summary=snapshot.get("inventory_summary"),
            options=snapshot.get("options"),
            settlement=settlement,
            area_reputation=int(snapshot.get("area_reputation") or 0),
            on_road=terrain in {"road", "bridge"},
        )
        return {
            "danger": assessment.get("danger"),
            "band": assessment.get("band"),
            "terrain": terrain,
            "environment": assessment.get("environment"),
            "player_multiplier": assessment.get("player_multiplier"),
            "factors": assessment.get("factors"),
            "narrator_view": encounters_mod.danger_context_block(assessment),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/generation-progress")
def api_generation_progress():
    """Live phase + partial narration while a turn/opening is generating."""
    try:
        from app.generation_progress import snapshot

        return snapshot()
    except Exception as exc:
        return {
            "active": False,
            "phase": "error",
            "detail": str(exc),
            "lines": [],
            "preview": "",
            "step": 0,
            "total_steps": 0,
            "elapsed_seconds": 0,
        }


@app.get("/api/debug-trace")
def api_debug_trace(name: str = ""):
    """
    Read a model-trace file for the per-turn Debug panel.
    Only basenames under the model-trace directory are allowed.
    """
    from app.world import model_trace_dir

    clean = Path(str(name or "").strip()).name
    if not clean or clean in {".", ".."} or not clean.endswith(".json"):
        raise HTTPException(status_code=400, detail="Provide a .json trace file name.")
    if any(ch in clean for ch in ("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid trace name.")
    path = (model_trace_dir() / clean).resolve()
    root = model_trace_dir().resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Trace path escapes model-trace directory.") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Trace not found: {clean}")
    try:
        raw = path.read_text(encoding="utf-8")
        # Cap response size for the browser panel (~2 MB).
        if len(raw) > 2_000_000:
            raw = raw[:2_000_000] + "\n/* truncated for browser view */\n"
        try:
            data = json.loads(raw) if not raw.endswith("/* truncated for browser view */\n") else None
        except Exception:
            data = None
        return {
            "ok": True,
            "name": clean,
            "path": str(path).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "json": data,
            "text": raw if data is None else None,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/select-model-file")
def api_select_model_file():
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Select LLM model file",
            filetypes=[("GGUF model files", "*.gguf"), ("All files", "*.*")],
        )
        root.destroy()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not open file picker: {exc}") from exc
    return {"path": path or ""}


class SelectFolderRequest(BaseModel):
    """Native folder picker (server-side tkinter). kind only changes the dialog title."""

    kind: str = Field(default="folder", max_length=40)
    title: str = Field(default="", max_length=200)
    initial_dir: str = Field(default="", max_length=1000)


@app.post("/api/select-folder")
def api_select_folder(request: SelectFolderRequest | None = None):
    """
    Open a desktop folder chooser so users can pick Forge/Comfy install roots
    (or any custom directory) without pasting paths by hand.
    """
    kind = str((request.kind if request else "") or "folder").strip().lower()
    title = str((request.title if request else "") or "").strip()
    initial = str((request.initial_dir if request else "") or "").strip()
    if not title:
        titles = {
            "forge": "Select Forge / ForgeSD install folder",
            "comfyui": "Select ComfyUI install folder",
            "comfy": "Select ComfyUI install folder",
            "models": "Select models folder",
            "controlnet": "Select ControlNet models folder",
            "lora": "Select LoRA folder",
            "loras": "Select LoRA folder",
            "checkpoint": "Select checkpoint folder",
            "checkpoints": "Select checkpoint folder",
        }
        title = titles.get(kind, "Select folder")
    initial_dir = initial if initial and Path(initial).is_dir() else str(Path.home())
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title=title, initialdir=initial_dir, mustexist=True)
        root.destroy()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not open folder picker: {exc}") from exc
    chosen = str(path or "").strip()
    # Soft validation hints for known kinds (never block a free choice).
    hint = ""
    valid = bool(chosen and Path(chosen).is_dir())
    if chosen and kind in {"forge", "comfyui", "comfy"}:
        from app.image_backends import validate_backend_root

        check_kind = "comfyui" if kind in {"comfy", "comfyui"} else "forge"
        check = validate_backend_root(check_kind, chosen)
        valid = bool(check.get("ok"))
        hint = str(check.get("message") or "")
    return {
        "path": chosen,
        "kind": kind,
        "looks_valid": valid,
        "message": hint
        or (
            "Folder selected."
            if chosen
            else "No folder selected."
        ),
    }


@app.get("/api/setup/composer")
def api_setup_composer():
    """Field dependency tree + load order for Randomize walks."""
    return composer_tree_public()


@app.post("/api/setup/compose-intent")
def api_compose_intent(request: ComposeIntentRequest):
    """Compile the Randomize idea into structured intent + session theme + field overrides."""
    try:
        result = compose_setup_intent(request.idea, request.current)
    except LlmError as exc:
        # Keyword-only plan still works offline.
        from app.setup_composer import apply_keyword_intent

        plan = apply_keyword_intent(request.idea)
        result = {
            "intent": plan,
            "session_theme": session_theme_from_intent(plan),
            "source": "keywords",
            "fallback_reason": str(exc),
        }
    intent = result.get("intent") if isinstance(result.get("intent"), dict) else {}
    locked = set((request.current or {}).get("_locked_fields") or [])
    overrides = intent_to_field_overrides(intent, locked)
    return {
        **result,
        "field_overrides": overrides,
        "field_order": composer_tree_public()["field_order"],
    }


@app.post("/api/randomize-setup")
def api_randomize_setup(request: RandomizeSetupRequest):
    try:
        return generate_setup_randomization(request.group, request.current)
    except LlmError as exc:
        fallback = fallback_setup_randomization(request.group, request.current, str(exc))
        if fallback is not None:
            return fallback
        raise HTTPException(status_code=503, detail=f"Model randomization failed: {exc}") from exc


class IdeaBankSearchRequest(BaseModel):
    query: str = Field(default="", max_length=600)
    kind: str = Field(default="", max_length=40)
    kinds: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=24)
    fields: list[str] = Field(default_factory=list)
    current: dict[str, Any] = Field(default_factory=dict)
    intent: dict[str, Any] | None = None


class IdeaBankAddRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    text: str = Field(default="", max_length=800)
    kind: str = Field(default="style", max_length=40)
    keywords: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    id: str = Field(default="", max_length=80)


@app.get("/api/idea-bank")
def api_idea_bank_stats():
    """Cold-storage idea bank stats (keyword search only — not embeddings/weights)."""
    return idea_bank_stats()


@app.get("/api/idea-bank/search")
def api_idea_bank_search_get(q: str = "", kind: str = "", limit: int = 8):
    hits = search_idea_bank(q, kind=kind or None, limit=limit)
    return {"query": q, "count": len(hits), "hits": hits, "weighted": False}


@app.post("/api/idea-bank/search")
def api_idea_bank_search(request: IdeaBankSearchRequest):
    """Keyword search cold storage. Optionally build query from setup + fields."""
    if request.fields or request.current or request.intent:
        pkg = idea_sparks_for_prompt(
            request.current,
            fields=request.fields or None,
            intent=request.intent,
            limit=request.limit,
            query=request.query or None,
        )
        return {**pkg, "count": len(pkg.get("sparks") or [])}
    hits = search_idea_bank(
        request.query,
        kind=request.kind or None,
        kinds=request.kinds or None,
        limit=request.limit,
    )
    return {
        "query": request.query,
        "count": len(hits),
        "hits": hits,
        "weighted": False,
        "mode": "cold_storage_keyword_search",
    }


@app.post("/api/idea-bank/add")
def api_idea_bank_add(request: IdeaBankAddRequest):
    """Append a user idea card under data/idea_bank/ (cold storage, not training)."""
    try:
        row = append_user_idea(
            {
                "id": request.id,
                "title": request.title,
                "text": request.text,
                "kind": request.kind,
                "keywords": request.keywords,
                "tags": request.tags,
                "examples": request.examples,
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "card": row, "stats": idea_bank_stats()}


@app.get("/api/idea-bank/cards")
def api_idea_bank_cards(kind: str = "", limit: int = 50):
    """List cards (for browsing). Limit capped."""
    cards = load_idea_cards()
    if kind:
        cards = [c for c in cards if c.get("kind") == kind.lower()]
    return {"count": len(cards), "cards": cards[: max(1, min(limit, 200))]}


class CoherencePassRequest(BaseModel):
    current: dict[str, Any] = Field(default_factory=dict)
    locked_fields: list[str] = Field(default_factory=list)
    intent: dict[str, Any] | None = None


@app.post("/api/setup/coherence-pass")
def api_setup_coherence_pass(request: CoherencePassRequest):
    """
    After field-by-field Randomize, review the full package for tacky/AI-generic prose.
    Never overwrites locked fields. Slower; optional second model pass.
    """
    try:
        return coherence_review_setup(
            request.current,
            locked_fields=request.locked_fields,
            intent=request.intent,
        )
    except LlmError as exc:
        return {
            "fields": {},
            "special_abilities": None,
            "notes": f"Coherence pass failed: {exc}",
            "changed": [],
            "fallback_used": True,
        }


class StarterLogicRequest(BaseModel):
    starter_equipment: str = Field(default="", max_length=500)
    appearance: str = Field(default="", max_length=400)
    backstory_mode: str = Field(default="", max_length=80)
    memory_policy: str = Field(default="", max_length=120)
    character_backstory: str = Field(default="", max_length=4000)
    world_style: str = Field(default="", max_length=200)
    tech_level: str = Field(default="", max_length=80)
    magic_level: str = Field(default="", max_length=80)
    special_ability_origin: str = Field(default="", max_length=40)
    intent: dict[str, Any] | None = None
    apply_fixes: bool = True


@app.post("/api/setup/starter-logic")
def api_setup_starter_logic(request: StarterLogicRequest):
    """
    Fact-check starter gear / clothes against arrival story.
    Isekai arrival cannot start with a fantasy shield; reincarnated can own this-life gear.
    """
    return fact_check_starter_loadout(
        starter_equipment=request.starter_equipment,
        appearance=request.appearance,
        backstory_mode=request.backstory_mode,
        memory_policy=request.memory_policy,
        character_backstory=request.character_backstory,
        intent=request.intent,
        world_style=request.world_style,
        tech_level=request.tech_level,
        magic_level=request.magic_level,
        special_ability_origin=request.special_ability_origin,
        apply_fixes=bool(request.apply_fixes),
    )


class AskRequest(BaseModel):
    text: str = Field(default="", max_length=500)


class CommandRequest(BaseModel):
    text: str = Field(default="", max_length=2000)


@app.post("/api/command")
def api_command(request: CommandRequest):
    """Debug and help commands. Does not play a scene."""
    from app.debug_commands import handle_command

    result = handle_command(request.text)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "Command failed."))
    return result


@app.post("/api/ask")
def api_ask(request: AskRequest):
    """Look something up. Does not advance the turn."""
    from app.ask import ask_about

    result = ask_about(request.text)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=str(result.get("error") or "Ask failed."))
    return result


@app.post("/api/turn")
def api_turn(request: TurnRequest):
    if request.text.strip().startswith("/"):
        from app.debug_commands import handle_command

        result = handle_command(request.text)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=str(result.get("error") or "Command failed."))
        return result
    try:
        if not request.text.strip():
            return play_continue_turn(allow_fallback=request.allow_fallback)
        return play_turn(request.text, allow_fallback=request.allow_fallback)
    except FailsafeBlocked as exc:
        raise HTTPException(status_code=503, detail=problem_detail(exc.problem)) from exc


@app.post("/api/continue")
def api_continue(request: ContinueRequest | None = None):
    allow = request.allow_fallback if request else True
    try:
        return play_continue_turn(allow_fallback=allow)
    except FailsafeBlocked as exc:
        raise HTTPException(status_code=503, detail=problem_detail(exc.problem)) from exc


class InitiateFightRequest(BaseModel):
    npc_code: str = Field(max_length=10)


@app.post("/api/initiate-fight")
def api_initiate_fight(request: InitiateFightRequest):
    """
    Player explicitly starts a fight with an NPC by code.
    Pre-warms NPC combat stats, then fires a full combat turn.
    Response shape is identical to /api/turn.
    """
    code = request.npc_code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="npc_code is required")
    try:
        return initiate_fight(code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class WaitRequest(BaseModel):
    # -1 = until dawn; 1–1440 custom or preset
    minutes: int = Field(default=60, ge=-1, le=1440)
    # wait | meditate | sleep — recovery rates differ
    kind: str = Field(default="wait", max_length=40)
    # False: a model failure comes back as a 503 problem instead of an offline-narrator turn.
    allow_fallback: bool = True


@app.post("/api/wait")
def api_wait(request: WaitRequest | None = None):
    """Spend in-world time; server RNG rolls events before the DM narrates.
    minutes=-1 waits until next dawn (06:00).
    kind=wait|meditate|sleep recovers energy/mana/fatigue at different rates."""
    minutes = int(request.minutes) if request else 60
    kind = str(request.kind or "wait") if request else "wait"
    allow = request.allow_fallback if request else True
    try:
        return play_wait_turn(minutes, kind=kind, allow_fallback=allow)
    except FailsafeBlocked as exc:
        raise HTTPException(status_code=503, detail=problem_detail(exc.problem)) from exc


class QuestStageRequest(BaseModel):
    stage_id: str = Field(..., max_length=80)
    kind: str = Field(default="quest_force", max_length=40)
    summary: str = Field(default="", max_length=800)
    force: bool = True
    due_in_turns: int = Field(default=1, ge=0, le=50)
    payload: dict = Field(default_factory=dict)


class WorldEventQueueRequest(BaseModel):
    kind: str = Field(default="custom", max_length=80)
    summary: str = Field(default="", max_length=1400)
    trigger: str = Field(default="", max_length=900)
    due_turn: int | None = None
    force: bool = False
    priority: int = Field(default=5, ge=0, le=10)
    payload: dict = Field(default_factory=dict)


@app.post("/api/events/quest-stage")
def api_quest_stage(request: QuestStageRequest):
    """Mark a quest stage; optionally force a beat N turns from now (default next turn)."""
    stage_id = str(request.stage_id or "").strip()
    if not stage_id:
        raise HTTPException(status_code=400, detail="stage_id is required.")
    return {
        "ok": True,
        "event": queue_quest_stage_event(
            stage_id,
            kind=request.kind,
            summary=request.summary,
            force=request.force,
            due_in_turns=request.due_in_turns,
            payload=request.payload,
        ),
        "quest": get_quest_stages(),
    }


@app.get("/api/events/quest-stages")
def api_quest_stages():
    """Reached stages + pending quest bus events for the stage editor UI."""
    return {"ok": True, **get_quest_stages()}


@app.get("/api/events/pending")
def api_events_pending(limit: int = 24):
    """All pending/active world-bus events (tools)."""
    return {"ok": True, "events": list_pending_world_events(limit=max(1, min(80, int(limit or 24))))}


class CancelWorldEventRequest(BaseModel):
    event_id: int = Field(..., ge=1)


@app.post("/api/events/cancel")
def api_events_cancel(request: CancelWorldEventRequest):
    """Cancel a pending world-bus event (does not rewrite history)."""
    ok = cancel_world_event(int(request.event_id))
    if not ok:
        raise HTTPException(status_code=404, detail="Event not found or not cancellable.")
    return {"ok": True, "event_id": int(request.event_id)}


@app.post("/api/events/queue")
def api_events_queue(request: WorldEventQueueRequest):
    """Queue a world event (RNG flavor or force). For tools / quest systems."""
    return {
        "ok": True,
        "event": queue_world_event(
            kind=request.kind,
            summary=request.summary,
            trigger=request.trigger or request.kind,
            due_turn=request.due_turn,
            force=request.force,
            priority=request.priority,
            payload=request.payload,
        ),
    }


@app.get("/api/events/due")
def api_events_due(force_only: bool = False):
    return {"events": list_due_world_events(force_only=force_only, limit=12)}


class SocialActionRequest(BaseModel):
    """Player chooses walk-away vs keep pushing after a cold social beat."""
    action: str = Field(default="walk_away", max_length=40)  # walk_away | persist
    npc_code: str = Field(default="", max_length=40)


@app.post("/api/social/resolve")
def api_social_resolve(request: SocialActionRequest):
    """
    Explicit social choice after an NPC resists chat.
    walk_away when cold → small rep gain; persist → rep loss.
    Does not require a full scene turn.
    """
    from app.db import connect as _connect

    action = str(request.action or "walk_away").strip().lower()
    with _connect() as conn:
        settings = {}
        try:
            from app.world import _settings as _ws

            settings = _ws(conn)
        except Exception:
            pass
        last = settings.get("last_social") if isinstance(settings.get("last_social"), dict) else {}
        code = str(request.npc_code or last.get("npc_code") or "").strip()
        loc_id = last.get("location_id")
        if not code:
            raise HTTPException(status_code=400, detail="No social target (npc_code or last_social).")
        if action in {"walk_away", "leave", "disengage"}:
            result = resolve_social_disengage(
                conn, npc_code=code, walked_away=True, location_id=int(loc_id) if loc_id else None
            )
        else:
            result = resolve_social_persist(
                conn, npc_code=code, location_id=int(loc_id) if loc_id else None
            )
    return {"ok": True, "result": result, "state": get_state()}


@app.get("/api/weather")
def api_weather():
    return {"weather": get_weather()}


@app.post("/api/suggestions")
def api_suggestions(request: SuggestionRequest | None = None):
    try:
        return get_input_suggestions(request.instruction if request else "")
    except LlmError as exc:
        raise HTTPException(status_code=503, detail=f"Model suggestion generation failed: {exc}") from exc


@app.post("/api/setup")
def api_setup(request: SetupRequest):
    return start_playthrough_with_opening(request.model_dump())


@app.post("/api/alias")
def api_alias(request: AliasRequest):
    return add_alias(request.alias, request.entity_type, request.entity_code)


@app.post("/api/player-alias")
def api_player_alias(request: PlayerAliasRequest):
    try:
        return create_player_alias(request.alias, request.notes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/player-alias/state")
def api_player_alias_state(request: PlayerAliasStateRequest):
    try:
        return update_player_alias_state(request.alias_id, request.active, request.disguised, request.disguise_description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/player-alias/delete")
def api_player_alias_delete(request: PlayerAliasDeleteRequest):
    try:
        return delete_player_alias(request.alias_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/rewind")
def api_rewind(request: RewindRequest | None = None):
    try:
        return rewind_last_turn(request.snapshot_id if request else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class RegenerateRequest(BaseModel):
    # False: a model failure comes back as a 503 problem instead of an offline-narrator turn.
    allow_fallback: bool = True


@app.post("/api/regenerate")
def api_regenerate(request: RegenerateRequest | None = None):
    allow = request.allow_fallback if request else True
    try:
        return regenerate_last_turn(allow_fallback=allow)
    except FailsafeBlocked as exc:
        raise HTTPException(status_code=503, detail=problem_detail(exc.problem)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/export")
def api_export():
    return JSONResponse(export_world())


@app.post("/api/import")
def api_import(data: dict):
    try:
        return import_world(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CampaignSlotRequest(BaseModel):
    slot: str = Field(default="", max_length=64)


@app.get("/api/setup/game-starts")
def api_game_start_presets():
    from app.world import list_game_start_presets

    return {"starts": list_game_start_presets()}


@app.get("/api/setup/game-starts/{campaign_id}")
def api_game_start_preset(campaign_id: str):
    from app.world import get_game_start_preset

    found = get_game_start_preset(campaign_id)
    if not found:
        raise HTTPException(status_code=404, detail="No starting setup for that game.")
    return found


@app.get("/api/campaign-slots")
def api_list_campaign_slots():
    return {"slots": list_campaign_slots(), "autosave_slot": AUTOSAVE_SLOT}


class SaveEditRequest(BaseModel):
    edits: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = False


@app.get("/api/save-editor/{slot}")
def api_read_save(slot: str):
    """
    The editable contents of a save.

    Same endpoint for the browser editor and for an agent, on purpose: two
    implementations of "what may be edited" would eventually disagree, and the
    one that disagreed quietly would be the one writing to a save file.
    """
    from app.save_editor import SaveEditError, read_save

    try:
        return read_save(slot)
    except SaveEditError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/save-editor/{slot}")
def api_edit_save(slot: str, payload: SaveEditRequest):
    """
    Apply edits to a save. All or nothing, and a backup is written first.

    Pass dry_run to see exactly what would change, including the previous
    values, without writing anything.
    """
    from app.save_editor import SaveEditError, apply_edits

    try:
        return apply_edits(slot, payload.edits, dry_run=payload.dry_run)
    except SaveEditError as exc:
        # The message names the offending edit and what was wrong with it, and
        # is written to be shown to whoever asked rather than logged.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/playthrough/continue")
def api_playthrough_continue_status():
    """Whether the main-menu Continue button should be enabled."""
    return has_continuable_save()


@app.post("/api/playthrough/continue")
def api_playthrough_continue_load():
    """Resume last playthrough from live DB or autosave slot `last`."""
    info = has_continuable_save()
    if not info.get("ok"):
        raise HTTPException(
            status_code=404,
            detail="No playthrough to continue. Start a new game or load a slot.",
        )
    try:
        if info.get("source") == "live":
            autosave_campaign()
            state = get_state()
        else:
            state = load_campaign_slot(AUTOSAVE_SLOT)
        resume = resume_snapshot(state)
        return {
            "ok": True,
            "source": info.get("source") or "live",
            "slot": AUTOSAVE_SLOT if info.get("source") == "slot" else info.get("slot"),
            "state": state,
            "resume": resume,
            "meta": info,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/campaign-slots/save")
def api_save_campaign_slot(request: CampaignSlotRequest):
    try:
        return save_campaign_slot(request.slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/campaign-slots/load")
def api_load_campaign_slot(request: CampaignSlotRequest):
    try:
        state = load_campaign_slot(request.slot)
        return {
            "ok": True,
            "slot": request.slot,
            "state": state,
            "resume": resume_snapshot(state),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/campaign-slots/delete")
def api_delete_campaign_slot(request: CampaignSlotRequest):
    try:
        return delete_campaign_slot(request.slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/diagnostics/context")
def api_context_health():
    return get_context_health()


@app.post("/api/memory/consolidate")
def api_memory_consolidate():
    try:
        return consolidate_memory()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/search")
def api_search(request: SearchRequest):
    return search_world(request.query)


@app.get("/api/bible")
def api_bible():
    return get_world_bible()


@app.post("/api/gm-notes")
def api_gm_notes(request: GmNotesRequest):
    return update_gm_notes(request.content)


@app.get("/api/gm-notes")
def api_get_gm_notes():
    return get_state(include_hidden=True).get("gm_notes", {"content": ""})


# ---------------------------------------------------------------------------
# Quest endpoints (0.9.13)
# ---------------------------------------------------------------------------

class RelationshipUpdateRequest(BaseModel):
    affinity_delta: int = 0
    fear_delta: int = 0
    respect_delta: int = 0
    reason: str = ""


@app.get("/api/quests")
def api_get_quests():
    from app.quests import get_active_quests
    from app.db import connect
    with connect() as conn:
        quests = get_active_quests(conn)
    return {"ok": True, "quests": quests}


@app.get("/api/quests/markers")
def api_quest_markers():
    """
    Return one marker per active quest, for the current (active) step only.
    Only steps with a location_coords set produce a marker.
    """
    import json as _json
    from app.db import connect

    markers: list[dict] = []
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT q.id AS quest_id, q.title AS quest_name, q.current_step,
                   qs.step_number AS step_index, qs.description AS step_description,
                   qs.location_name, qs.location_coords
              FROM quests q
              JOIN quest_steps qs
                ON qs.quest_id = q.id AND qs.step_number = q.current_step
             WHERE q.status = 'active'
               AND qs.location_coords != ''
             ORDER BY q.id
            """
        ).fetchall()
        for row in rows:
            try:
                coords = _json.loads(row["location_coords"])
            except Exception:
                continue
            if not isinstance(coords, dict) or coords.get("x") is None:
                continue
            markers.append(
                {
                    "quest_id": row["quest_id"],
                    "quest_name": row["quest_name"],
                    "step_index": row["step_index"],
                    "step_description": row["step_description"],
                    "location_name": row["location_name"] or "",
                    "coords": {"x": float(coords["x"]), "y": float(coords["y"])},
                    "is_current_step": True,
                }
            )
    return markers


@app.get("/api/map/npc-markers")
def api_npc_markers():
    """
    Return NPC map markers for all placed NPCs.

    Marker types (by priority, highest first):
      "watched"   — player has pinned this NPC (purple 📌)
      "quest_npc" — NPC is the giver of an active quest (orange 👤)
      "vendor"    — NPC sells items / is a shop keeper (blue 🛒)

    Lazily assigns/updates positions via update_npc_map_positions.
    """
    import json as _json
    from app.db import connect
    from app.world import update_npc_map_positions

    # Role keywords that indicate a vendor/shopkeeper
    VENDOR_ROLES = frozenset({
        "merchant", "trader", "shopkeeper", "vendor", "peddler", "innkeeper",
        "bartender", "barkeeper", "blacksmith", "alchemist", "armourer",
        "armorer", "weaponsmith", "tailor", "herbalist", "apothecary",
        "jeweller", "jeweler", "fence", "hawker", "stall vendor", "tinker",
    })

    with connect() as conn:
        # Update NPC positions before reading them
        try:
            update_npc_map_positions(conn)
        except Exception:
            pass

        # Collect watched NPC ids
        try:
            watched_ids = {
                int(r["npc_id"])
                for r in conn.execute("SELECT npc_id FROM watched_npcs").fetchall()
            }
        except Exception:
            watched_ids = set()

        # Collect active-quest giver NPC ids
        try:
            quest_npc_ids = {
                int(r["giver_npc_id"])
                for r in conn.execute(
                    "SELECT giver_npc_id FROM quests WHERE status = 'active' AND giver_npc_id IS NOT NULL"
                ).fetchall()
                if r["giver_npc_id"] is not None
            }
        except Exception:
            quest_npc_ids = set()

        # Collect keeper_npc_ids (NPCs who are shopkeepers of venue locations)
        try:
            keeper_ids = {
                int(r["keeper_npc_id"])
                for r in conn.execute(
                    "SELECT keeper_npc_id FROM locations WHERE keeper_npc_id > 0 AND kind != ''"
                ).fetchall()
            }
        except Exception:
            keeper_ids = set()

        # Fetch all placed NPCs
        try:
            rows = conn.execute(
                """
                SELECT n.id, n.name, n.role, n.map_x, n.map_y, n.is_moving,
                       l.kind AS loc_kind
                  FROM npcs n
                  LEFT JOIN locations l ON l.id = n.location_id
                 WHERE n.map_x >= 0 AND n.map_y >= 0
                """
            ).fetchall()
        except Exception:
            rows = []

        markers = []
        for row in rows:
            npc_id = int(row["id"])
            role = str(row["role"] or "").lower()
            loc_kind = str(row["loc_kind"] or "").lower()

            # Determine marker type (highest priority first)
            if npc_id in watched_ids:
                marker_type = "watched"
            elif npc_id in quest_npc_ids:
                marker_type = "quest_npc"
            elif (
                npc_id in keeper_ids
                or any(kw in role for kw in VENDOR_ROLES)
                or loc_kind != ""  # venue child location → likely a shop
            ):
                marker_type = "vendor"
            else:
                continue  # no marker type → not shown on map

            # Build note from role
            note = str(row["role"] or "").replace("_", " ").title()

            markers.append({
                "npc_id": str(npc_id),
                "name": str(row["name"] or ""),
                "marker_type": marker_type,
                "coords": {
                    "x": float(row["map_x"]),
                    "y": float(row["map_y"]),
                },
                "is_moving": bool(row["is_moving"]),
                "note": note,
            })

    return markers


@app.post("/api/npc/{npc_id}/watch")
def api_npc_watch_toggle(npc_id: int):
    """Toggle the player's watch pin on an NPC. Returns {"watching": bool}."""
    from app.db import connect

    with connect() as conn:
        # Verify NPC exists
        npc = conn.execute("SELECT id FROM npcs WHERE id = ?", (npc_id,)).fetchone()
        if not npc:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="NPC not found")

        turn_row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(turn_row["value"] or 0) if turn_row else 0

        existing = conn.execute(
            "SELECT npc_id FROM watched_npcs WHERE npc_id = ?", (npc_id,)
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM watched_npcs WHERE npc_id = ?", (npc_id,))
            watching = False
        else:
            conn.execute(
                "INSERT OR REPLACE INTO watched_npcs (npc_id, added_turn) VALUES (?, ?)",
                (npc_id, turn),
            )
            watching = True

    return {"watching": watching}


@app.post("/api/quests/{quest_id}/advance")
def api_advance_quest(quest_id: int):
    from app.quests import advance_quest_step
    from app.db import connect
    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(row["value"]) if row else 0
        result = advance_quest_step(conn, quest_id, turn=turn)
        if result.get("completed"):
            try:
                conn.execute(
                    "UPDATE player SET gold = gold + ?, xp = xp + ? WHERE id = 1",
                    (result["reward_gold"], result["reward_xp"]),
                )
            except Exception:
                pass
            # Apply quest completion relationship delta to the giver NPC
            try:
                quest_row = conn.execute(
                    "SELECT giver_npc_id FROM quests WHERE id = ?", (quest_id,)
                ).fetchone()
                giver_npc_id = int(quest_row["giver_npc_id"]) if quest_row and quest_row["giver_npc_id"] else None
                if giver_npc_id:
                    from app.relationships import update_relationship, RELATIONSHIP_EVENTS
                    update_relationship(
                        conn, giver_npc_id,
                        reason=f"Player completed quest {quest_id}",
                        **RELATIONSHIP_EVENTS["quest_complete_for_npc"],
                    )
            except Exception:
                pass
    return result


class QuestCreateRequest(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(default="", max_length=800)
    difficulty: str = Field(default="normal", max_length=40)
    steps: list[dict] = Field(default_factory=list)
    reward_gold: int | None = None
    reward_xp: int | None = None
    reward_item: str = Field(default="", max_length=120)
    giver_npc_id: int | None = None
    timer_turns: int = Field(default=0)


@app.post("/api/quests")
def api_create_quest(request: QuestCreateRequest):
    from app.quests import create_quest
    from app.db import connect

    difficulty_map = {"easy": "easy", "medium": "normal", "hard": "hard", "legendary": "deadly", "normal": "normal", "trivial": "trivial", "deadly": "deadly"}
    difficulty = difficulty_map.get(str(request.difficulty or "normal").lower(), "normal")

    steps = request.steps or []
    if not steps:
        return {"ok": False, "error": "At least one step is required"}
    if len(steps) > 6:
        return {"ok": False, "error": "At most 6 steps allowed"}

    reward_items = [request.reward_item] if request.reward_item else []

    with connect() as conn:
        row = conn.execute("SELECT value FROM pacing WHERE key = 'turn'").fetchone()
        turn = int(row["value"]) if row else 0
        try:
            quest_id = create_quest(
                conn,
                title=request.title,
                description=request.description,
                steps=steps,
                reward_gold=request.reward_gold,
                reward_xp=request.reward_xp,
                reward_items=reward_items,
                difficulty=difficulty,
                timer_turns=request.timer_turns or 0,
                giver_npc_id=request.giver_npc_id,
                created_turn=turn,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": True, "quest_id": quest_id}


@app.post("/api/quests/seed")
def api_seed_quests():
    from app.quests import seed_starter_quests
    from app.db import connect
    with connect() as conn:
        seed_starter_quests(conn)
    return {"ok": True}


# ---------------------------------------------------------------------------
# NPC relationship endpoints (0.9.13)
# ---------------------------------------------------------------------------


@app.get("/api/relationships")
def api_get_relationships():
    from app.relationships import all_relationships_for_llm
    from app.db import connect
    with connect() as conn:
        rels = all_relationships_for_llm(conn)
    return {"ok": True, "relationships": rels}


@app.get("/api/relationships/{npc_id}")
def api_get_npc_relationship(npc_id: int):
    from app.relationships import get_relationship_summary
    from app.db import connect
    with connect() as conn:
        rel = get_relationship_summary(conn, npc_id)
    return {"ok": True, "relationship": rel}


@app.post("/api/relationships/{npc_id}/update")
def api_update_npc_relationship(npc_id: int, request: RelationshipUpdateRequest):
    from app.relationships import update_relationship
    from app.db import connect
    with connect() as conn:
        rel = update_relationship(
            conn,
            npc_id,
            affinity_delta=request.affinity_delta,
            fear_delta=request.fear_delta,
            respect_delta=request.respect_delta,
            reason=request.reason,
        )
    return {"ok": True, "relationship": rel}


# ── Titles ────────────────────────────────────────────────────────────────────


@app.get("/api/titles")
def api_player_titles():
    """Player's currently earned titles with stat bonuses."""
    from app.titles import get_entity_titles
    from app.db import connect
    with connect() as conn:
        titles = get_entity_titles(1, "player", include_hidden=False, conn=conn)
    return {"ok": True, "titles": titles}


@app.get("/api/titles/all")
def api_all_titles():
    """Full title catalogue with requirements (for reference)."""
    from app.titles import get_all_titles
    from app.db import connect
    with connect() as conn:
        titles = get_all_titles(conn=conn)
    return {"ok": True, "titles": titles}


class TitlesSettingRequest(BaseModel):
    enabled: bool = True


@app.post("/api/settings/titles")
def api_titles_setting(request: TitlesSettingRequest):
    """Toggle the titles system on/off for this playthrough."""
    from app.db import connect
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('titles_enabled', ?)",
            ("true" if request.enabled else "false",),
        )
    return {"ok": True, "titles_enabled": request.enabled}


# ── Party ─────────────────────────────────────────────────────────────────────


@app.get("/api/party")
def api_get_party():
    """Current party members with morale and combat bonus."""
    from app.party import get_party
    from app.db import connect
    with connect() as conn:
        members = get_party(conn=conn)
    return {"ok": True, "party": members}


class PartyInviteRequest(BaseModel):
    npc_id: int
    role: str = Field(default="companion", max_length=20)


@app.post("/api/party/invite")
def api_party_invite(request: PartyInviteRequest):
    """Invite an NPC to the party (requires affinity >= Friendly / 40)."""
    from app.party import invite_npc_to_party
    from app.db import connect
    with connect() as conn:
        result = invite_npc_to_party(request.npc_id, role=request.role, conn=conn)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Could not invite NPC")
    return result


class PartyRemoveRequest(BaseModel):
    npc_id: int


@app.post("/api/party/remove")
def api_party_remove(request: PartyRemoveRequest):
    """Remove an NPC from the party (applies affinity −10)."""
    from app.party import remove_from_party
    from app.db import connect
    with connect() as conn:
        result = remove_from_party(request.npc_id, conn=conn)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "NPC not in party")
    return result


# [NARRATOR ONLY] — This endpoint exposes hidden NPC psychology for debugging
# and narrator LLM inspection. It must NEVER be wired into any player-facing UI.
# The player sees only affinity/fear/respect from /api/relationships/{npc_id}.
@app.get("/api/npc/{npc_id}/psychology")
def api_npc_psychology(npc_id: int):
    """
    [NARRATOR ONLY] Full hidden psychology dump for one NPC.
    Returns private feelings, active agendas, family ties, and a compact narrator text block.
    Never expose this to the player-facing interface.
    """
    from app.npc_psychology import get_full_psychology_dump, init_psychology_tables
    from app.db import connect
    with connect() as conn:
        init_psychology_tables(conn)
        dump = get_full_psychology_dump(conn, npc_id)
    if "error" in dump:
        raise HTTPException(status_code=404, detail=dump["error"])
    return {"ok": True, **dump}


@app.post("/api/npc/psychology/seed-demo")
def api_npc_psychology_seed_demo():
    """
    [NARRATOR ONLY] Seed the three demonstration psychology scenarios.
    Idempotent — skips any scenario that already has the relevant feeling/agenda.
    """
    from app.npc_psychology import seed_demo_psychology, init_psychology_tables
    from app.db import connect
    with connect() as conn:
        init_psychology_tables(conn)
        report = seed_demo_psychology(conn)
    return {"ok": True, **report}
