from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.db import init_db
from app.llm import LlmError, fallback_setup_randomization, generate_setup_randomization, get_model_config, test_model_connection, update_model_config
from app.world import (
    TURN_CONTEXT_PLANNER_VERSION,
    add_alias,
    create_player_alias,
    export_world,
    get_input_suggestions,
    get_state,
    get_world_bible,
    import_world,
    play_continue_turn,
    play_turn,
    regenerate_last_turn,
    rewind_last_turn,
    search_world,
    start_playthrough_with_opening,
    update_player_alias_state,
    update_gm_notes,
)


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
APP_VERSION = "V0.6.0"

app = FastAPI(title="AI RPG Consistency Prototype")
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
}

SETUP_BOOL_DEFAULTS = {
    "leveling_system": True,
    "game_system": False,
    "special_ability": False,
    "special_ability_locked": False,
    "skill_levels_enabled": True,
    "proficiency_system": True,
    "race_magic_enabled": False,
}

SETUP_INT_DEFAULTS = {
    "inventory_weight_limit": 60,
    "inventory_slot_limit": 24,
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
    response_token_cap: int = Field(default=1500, ge=64, le=100000)
    response_token_hard_cap: int = Field(default=2000, ge=64, le=100000)


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


@app.get("/api/state")
def api_state():
    return get_state()


@app.get("/api/version")
def api_version():
    return {
        "app": "AI RPG Consistency Prototype",
        "version": APP_VERSION,
        "planner_version": TURN_CONTEXT_PLANNER_VERSION,
    }


@app.get("/api/model-config")
def api_model_config():
    return get_model_config()


@app.post("/api/model-config")
def api_update_model_config(request: ModelConfigRequest):
    return update_model_config(request.model_dump())


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
