"""Shared launcher prefs (Gatehouse + web Settings). Stored in data/launcher_prefs.json."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PREFS_PATH = Path(os.getenv("AI_RPG_LAUNCHER_PREFS") or (ROOT / "data" / "launcher_prefs.json"))


def default_prefs() -> dict[str, Any]:
    return {
        "launch_mode": "local",  # local | lan | vpn
        "app_port": 8000,
        "model_provider": "ollama",  # ollama | llama_cpp | openai
        "ollama_model": "qwen3:8b",
        "ollama_base_url": "http://127.0.0.1:11434",
        "ollama_think": False,
        "gguf_model_path": "",
        "api_base_url": "https://api.x.ai/v1",
        "api_model": "grok-4.5",
        "api_preset": "xai",
        "llama_cpp_context": 8192,
        "llama_cpp_gpu_layers": -1,
        "soft_response_tokens": 1000,
        "hard_response_tokens": 1500,
        "draft_mode": "dsl",
        "narration_pipeline": True,
        "narration_consolidate": True,
        "fast_verification": True,
        "open_browser": True,
        "ui_theme": "dusk",
    }


def load_prefs() -> dict[str, Any]:
    base = default_prefs()
    if not PREFS_PATH.is_file():
        return base
    try:
        raw = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in base:
                    base[key] = value
    except Exception:
        pass
    return base


def save_prefs(updates: dict[str, Any] | None) -> dict[str, Any]:
    current = load_prefs()
    if isinstance(updates, dict):
        for key, value in updates.items():
            if key in current:
                current[key] = value
    # normalize
    mode = str(current.get("launch_mode") or "local").lower()
    current["launch_mode"] = mode if mode in {"local", "lan", "vpn"} else "local"
    prov = str(current.get("model_provider") or "ollama").lower()
    current["model_provider"] = prov if prov in {"ollama", "llama_cpp", "openai"} else "ollama"
    try:
        current["app_port"] = max(1, min(65535, int(current.get("app_port") or 8000)))
    except (TypeError, ValueError):
        current["app_port"] = 8000
    for bkey in (
        "ollama_think",
        "narration_pipeline",
        "narration_consolidate",
        "fast_verification",
        "open_browser",
    ):
        current[bkey] = bool(current.get(bkey))
    PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREFS_PATH.write_text(json.dumps(current, ensure_ascii=True, indent=2), encoding="utf-8")
    return current


def apply_prefs_to_env(prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-effort apply prefs to process env (affects new model calls in this process)."""
    p = prefs or load_prefs()
    os.environ["AI_RPG_LAUNCH_MODE"] = str(p.get("launch_mode") or "local")
    os.environ["AI_RPG_APP_PORT"] = str(p.get("app_port") or 8000)
    os.environ["AI_RPG_MODEL_PROVIDER"] = str(p.get("model_provider") or "ollama")
    os.environ["OLLAMA_MODEL"] = str(p.get("ollama_model") or "qwen3:8b")
    os.environ["OLLAMA_BASE_URL"] = str(p.get("ollama_base_url") or "http://127.0.0.1:11434")
    os.environ["AI_RPG_NARRATION_PIPELINE"] = "1" if p.get("narration_pipeline") else "0"
    os.environ["AI_RPG_NARRATION_PIPELINE_CONSOLIDATE"] = "1" if p.get("narration_consolidate") else "0"
    os.environ["AI_RPG_FAST_VERIFICATION"] = "1" if p.get("fast_verification") else "0"
    os.environ["AI_RPG_DRAFT_MODE"] = str(p.get("draft_mode") or "dsl")
    if p.get("gguf_model_path"):
        os.environ["AI_RPG_GGUF_MODEL"] = str(p.get("gguf_model_path"))
    if p.get("api_base_url"):
        os.environ["AI_RPG_API_BASE_URL"] = str(p.get("api_base_url"))
    if p.get("api_model"):
        os.environ["AI_RPG_API_MODEL"] = str(p.get("api_model"))
    return p
