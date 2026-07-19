from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.db import init_db
from app.image_backends import (
    build_portrait_prompt,
    generate_image,
    get_image_config,
    probe_image_backend,
    public_image_config,
    update_image_config,
)
from app.tile_world import (
    add_tile_image,
    ascii_preview,
    clear_run_disables,
    delete_tile_images,
    disable_tile_images_for_run,
    generate_map,
    get_map,
    list_maps,
    list_tile_states,
    list_world_presets,
    search_tile_images,
    set_tile_images_disabled_forever,
    suggest_tile_prompt,
)
from app.llm import (
    LlmError,
    fallback_setup_randomization,
    generate_setup_randomization,
    get_model_config,
    public_model_config,
    test_model_connection,
    update_model_config,
)
from app.skill_checks import (
    catalog_public,
    register_or_adjust_skill,
    resolve_check,
    set_skill_enabled,
    settings_from_setup,
)
from app.updates import apply_update, check_for_updates, current_status as update_status, rollback
from app.world import (
    MECHANICS_CONTEXT_VERSION,
    TURN_CONTEXT_PLANNER_VERSION,
    add_alias,
    consolidate_memory,
    create_player_alias,
    delete_campaign_slot,
    export_world,
    get_context_health,
    get_input_suggestions,
    get_state,
    get_world_bible,
    import_world,
    list_campaign_slots,
    load_campaign_slot,
    play_continue_turn,
    play_turn,
    regenerate_last_turn,
    rewind_last_turn,
    save_campaign_slot,
    search_world,
    start_playthrough_with_opening,
    update_player_alias_state,
    update_gm_notes,
)


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
APP_VERSION = "V0.8.0"

app = FastAPI(title="Mørkyn")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class TurnRequest(BaseModel):
    text: str = Field(default="", max_length=2000)


class SpecialAbilitySetup(BaseModel):
    name: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=800)
    locked: bool = False
    prerequisites: str = Field(default="", max_length=500)
    cost: str = Field(default="", max_length=300)

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_values(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        for key in ("name", "description", "prerequisites", "cost"):
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
    "memory_policy": "known",
    "difficulty": "normal",
    "narration_detail": "rich",
    "world_style": "frontier dark fantasy",
    "custom_style": "",
    "start_location": "Mosswake Gate",
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
    "custom_skills": 800,
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
}

SETUP_INT_DEFAULTS = {
    "inventory_weight_limit": 60,
    "inventory_slot_limit": 24,
    "dice_sides": 20,
    "attribute_floor_for_partial": 6,
    "specialized_skill_partial_threshold": 2,
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
    memory_policy: str = Field(default="known", max_length=80)
    difficulty: str = Field(default="normal", max_length=60)
    narration_detail: str = Field(default="rich", max_length=120)
    world_style: str = Field(default="frontier dark fantasy", max_length=120)
    custom_style: str = Field(default="", max_length=800)
    start_location: str = Field(default="Mosswake Gate", max_length=100)
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
    custom_skills: str = Field(default="", max_length=800)
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
    # Dice / skill checks (setup tab 5)
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


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)


class GmNotesRequest(BaseModel):
    content: str = Field(default="", max_length=6000)


class RewindRequest(BaseModel):
    snapshot_id: int | None = None


class ModelConfigRequest(BaseModel):
    provider: str = Field(default="llama_cpp", max_length=40)
    ollama_base_url: str = Field(default="http://localhost:11434", max_length=300)
    ollama_model: str = Field(default="llama3.1", max_length=200)
    llama_cpp_base_url: str = Field(default="http://localhost:8080", max_length=300)
    gguf_model_path: str = Field(default="", max_length=1000)
    api_base_url: str = Field(default="https://api.x.ai/v1", max_length=400)
    api_model: str = Field(default="grok-4.5", max_length=200)
    api_key: str = Field(default="", max_length=500)
    api_preset: str = Field(default="xai", max_length=40)
    response_token_cap: int = Field(default=1500, ge=64, le=100000)
    response_token_hard_cap: int = Field(default=2000, ge=64, le=100000)


class ImageConfigRequest(BaseModel):
    provider: str = Field(default="off", max_length=40)
    forge_base_url: str = Field(default="http://127.0.0.1:7860", max_length=400)
    comfy_base_url: str = Field(default="http://127.0.0.1:8188", max_length=400)
    comfy_checkpoint: str = Field(default="", max_length=300)
    comfy_workflow: str = Field(default="txt2img_api.json", max_length=200)
    negative_prompt: str = Field(default="", max_length=2000)
    portrait_style: str = Field(default="", max_length=800)
    default_width: int = Field(default=512, ge=64, le=2048)
    default_height: int = Field(default=512, ge=64, le=2048)
    default_steps: int = Field(default=20, ge=1, le=150)
    default_cfg: float = Field(default=7.0, ge=1.0, le=30.0)
    timeout_seconds: int = Field(default=180, ge=10, le=900)


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
    group: str = Field(default="all", max_length=40)
    current: dict = Field(default_factory=dict)


class SuggestionRequest(BaseModel):
    instruction: str = Field(default="", max_length=500)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/privacy")
def privacy_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "privacy.html")


@app.get("/api/privacy")
def api_privacy():
    path = ROOT / "PRIVACY_POLICY.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Privacy policy missing")
    return {
        "title": "Mørkyn Privacy Policy",
        "markdown": path.read_text(encoding="utf-8"),
        "path": "PRIVACY_POLICY.md",
    }


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
    return update_model_config(request.model_dump())


@app.get("/api/image-config")
def api_image_config():
    """Local image backend settings (Forge / ComfyUI). Default provider is off."""
    return public_image_config()


@app.post("/api/image-config")
def api_update_image_config(request: ImageConfigRequest):
    return update_image_config(request.model_dump())


@app.post("/api/image-status")
def api_image_status():
    """Probe the configured local image server (no generation)."""
    return probe_image_backend()


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
    prompt = build_portrait_prompt(
        name=request.name,
        title=request.title,
        known_as=request.known_as,
        backstory=request.backstory,
        world_style=request.world_style,
        extra=request.extra,
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
    return result


# --- Tile world / map presets / image archive ---------------------------------


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
def api_tile_map(map_id: str = ""):
    data = get_map(map_id or None)
    if not data:
        # Soft empty payload so the UI can boot without a hard 404.
        return {"id": None, "tiles": [], "ascii": "", "empty": True}
    data["ascii"] = ascii_preview(data)
    data["empty"] = False
    # Drop heavy nested grid duplicate if client only needs tiles
    return data


@app.post("/api/tiles/generate")
def api_tiles_generate(request: MapGenerateRequest):
    try:
        data = generate_map(
            preset_id=request.preset_id or "forest_march",
            seed=request.seed,
            width=request.width,
            height=request.height,
            assign_images=request.assign_images,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    data["ascii"] = ascii_preview(data)
    # Response size: omit nested grid if large; keep flat tiles
    data.pop("grid", None)
    return data


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


@app.get("/api/model-status")
def api_model_status():
    try:
        return test_model_connection()
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
            },
        )


class SkillCheckRequest(BaseModel):
    skill_code: str = Field(default="general", max_length=80)
    difficulty: str = Field(default="", max_length=40)
    dc: int | None = None
    context_note: str = Field(default="", max_length=400)
    player_stats: dict[str, Any] = Field(default_factory=dict)
    player_skills: list[dict[str, Any]] = Field(default_factory=list)
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
        stats = request.player_stats or player.get("effective_stats") or player.get("stats") or {}
        skills = request.player_skills or (state.get("skills") if isinstance(state, dict) else []) or []
        return resolve_check(
            skill_code=request.skill_code or "general",
            difficulty=request.difficulty or None,
            dc=request.dc,
            player_stats=stats if isinstance(stats, dict) else {},
            player_skills=skills if isinstance(skills, list) else [],
            settings=settings if isinstance(settings, dict) else {},
            context_note=request.context_note,
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
    from app.world import MODEL_TRACE_DIR

    clean = Path(str(name or "").strip()).name
    if not clean or clean in {".", ".."} or not clean.endswith(".json"):
        raise HTTPException(status_code=400, detail="Provide a .json trace file name.")
    if any(ch in clean for ch in ("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid trace name.")
    path = (MODEL_TRACE_DIR / clean).resolve()
    root = MODEL_TRACE_DIR.resolve()
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


@app.post("/api/randomize-setup")
def api_randomize_setup(request: RandomizeSetupRequest):
    try:
        return generate_setup_randomization(request.group, request.current)
    except LlmError as exc:
        fallback = fallback_setup_randomization(request.group, request.current, str(exc))
        if fallback is not None:
            return fallback
        raise HTTPException(status_code=503, detail=f"Model randomization failed: {exc}") from exc


@app.post("/api/turn")
def api_turn(request: TurnRequest):
    if not request.text.strip():
        return play_continue_turn()
    return play_turn(request.text)


@app.post("/api/continue")
def api_continue():
    return play_continue_turn()


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


@app.post("/api/rewind")
def api_rewind(request: RewindRequest | None = None):
    try:
        return rewind_last_turn(request.snapshot_id if request else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/regenerate")
def api_regenerate():
    try:
        return regenerate_last_turn()
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


@app.get("/api/campaign-slots")
def api_list_campaign_slots():
    return {"slots": list_campaign_slots()}


@app.post("/api/campaign-slots/save")
def api_save_campaign_slot(request: CampaignSlotRequest):
    try:
        return save_campaign_slot(request.slot)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/campaign-slots/load")
def api_load_campaign_slot(request: CampaignSlotRequest):
    try:
        return load_campaign_slot(request.slot)
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
