"""Shared launcher prefs (app window, web Settings, Gatehouse). Stored in data/launcher_prefs.json.

One table of keys and one env mapping. The Python launcher (`morkyn_app.py`,
`app/launcher.py`) builds the server's environment from `prefs_to_env`, and the
running server applies the same mapping to itself when Settings are saved, so a
setting cannot mean one thing at launch and another after a save.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.paths import ROOT  # the repo root, or the folder beside the packaged exe
def prefs_path() -> Path:
    """Resolved per call so AI_RPG_LAUNCHER_PREFS is honoured whatever the import order."""
    return Path(os.getenv("AI_RPG_LAUNCHER_PREFS") or (ROOT / "data" / "launcher_prefs.json"))


PROVIDERS = ("mle", "llama_cpp", "openai")
LAUNCH_MODES = ("local", "lan", "vpn")
# Older names the PowerShell Gatehouse and the CLI accepted for the same reach.
LAUNCH_MODE_ALIASES = {
    "machine": "local",
    "network": "lan",
    "web": "lan",
    "phone": "lan",
    "tunnel": "vpn",
    "tailscale": "vpn",
    "wireguard": "vpn",
    "zerotier": "vpn",
}
WINDOW_MODES = ("app", "browser", "none")


def default_prefs() -> dict[str, Any]:
    return {
        "launch_mode": "local",  # local | lan | vpn
        "app_port": 8000,
        "model_provider": "mle",  # mle | llama_cpp | openai
        "mle_model": "qwen3:8b",
        "gguf_model_path": "",
        "api_base_url": "https://api.x.ai/v1",
        "api_model": "grok-4.5",
        "api_preset": "xai",
        # "auto": the model's own header and the GPU size the window and the
        # response caps (app/model_limits.py). A number here is an explicit
        # choice for every model and is exported as the env override.
        "llama_cpp_context": "auto",
        "llama_cpp_gpu_layers": -1,
        "llama_cpp_flash_attn": True,
        "llm_log_mode": "quiet",  # quiet | console
        "llm_startup_timeout": 180,
        "soft_response_tokens": 0,
        "hard_response_tokens": 0,
        "draft_mode": "dsl",
        "narration_pipeline": False,
        "narration_consolidate": True,
        "fast_verification": True,
        "dsl_skip_verify": False,
        # Where the game opens when the launcher starts it: Mørkyn's own
        # window, the system browser, or nowhere (server only).
        "window_mode": "app",
        # Kept for the PowerShell Gatehouse, which only knows this switch.
        "open_browser": True,
        "ui_theme": "dusk",
    }


# Changing these only takes effect when the server (and a managed llama.cpp
# server) starts again: the bind address, the port, and every flag handed to
# llama.cpp on its command line.
RESTART_KEYS = frozenset(
    {
        "launch_mode",
        "app_port",
        "model_provider",
        "gguf_model_path",
        "llama_cpp_context",
        "llama_cpp_gpu_layers",
        "llama_cpp_flash_attn",
        "llm_log_mode",
        "llm_startup_timeout",
    }
)
# Of RESTART_KEYS, these only matter when the engine is llama.cpp.
_LLAMA_ONLY_KEYS = frozenset(
    {"gguf_model_path", "llama_cpp_gpu_layers", "llama_cpp_flash_attn", "llm_log_mode", "llm_startup_timeout"}
)

_BOOL_KEYS = (
    "narration_pipeline",
    "narration_consolidate",
    "fast_verification",
    "dsl_skip_verify",
    "llama_cpp_flash_attn",
    "open_browser",
)


def explicit_pref_int(value: Any) -> int:
    """A positive number from a pref, or 0 for auto / blank / anything else."""
    text = str(value if value is not None else "").strip().lower()
    if not text or text == "auto":
        return 0
    try:
        number = int(float(text))
    except ValueError:
        return 0
    return number if number > 0 else 0


def _provider_name(value: Any) -> str:
    prov = str(value or "mle").strip().lower()
    return prov if prov in PROVIDERS else "mle"


def launch_mode_name(value: Any) -> str:
    mode = str(value or "local").strip().lower()
    mode = LAUNCH_MODE_ALIASES.get(mode, mode)
    return mode if mode in LAUNCH_MODES else "local"


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _auto_or_int(value: Any) -> Any:
    return explicit_pref_int(value) or "auto"


def normalize_prefs(prefs: dict[str, Any]) -> dict[str, Any]:
    """Coerce every key to its type and range; unknown values fall back to the default."""
    base = default_prefs()
    out = dict(base)
    for key in base:
        if key in prefs:
            out[key] = prefs[key]
    out["launch_mode"] = launch_mode_name(out.get("launch_mode"))
    out["model_provider"] = _provider_name(out.get("model_provider"))
    out["app_port"] = _as_int(out.get("app_port"), 8000, 1, 65535)
    out["llama_cpp_gpu_layers"] = _as_int(out.get("llama_cpp_gpu_layers"), -1, -1, 999)
    out["llm_startup_timeout"] = _as_int(out.get("llm_startup_timeout"), 180, 10, 3600)
    out["llama_cpp_context"] = _auto_or_int(out.get("llama_cpp_context"))
    out["soft_response_tokens"] = explicit_pref_int(out.get("soft_response_tokens"))
    out["hard_response_tokens"] = explicit_pref_int(out.get("hard_response_tokens"))
    for key in _BOOL_KEYS:
        out[key] = _as_bool(out.get(key))
    log_mode = str(out.get("llm_log_mode") or "quiet").strip().lower()
    out["llm_log_mode"] = log_mode if log_mode in {"quiet", "console"} else "quiet"
    draft = str(out.get("draft_mode") or "dsl").strip().lower()
    out["draft_mode"] = draft if draft in {"dsl", "json"} else "dsl"
    window = str(out.get("window_mode") or "app").strip().lower()
    out["window_mode"] = window if window in WINDOW_MODES else "app"
    for key in ("mle_model", "gguf_model_path", "api_base_url", "api_model", "api_preset", "ui_theme"):
        out[key] = str(out.get(key) or "").strip()
    if not out["mle_model"]:
        out["mle_model"] = base["mle_model"]
    if not out["ui_theme"]:
        out["ui_theme"] = base["ui_theme"]
    return out


def load_prefs() -> dict[str, Any]:
    base = default_prefs()
    if not prefs_path().is_file():
        return base
    raw: Any = None
    try:
        raw = json.loads(prefs_path().read_text(encoding="utf-8-sig"))
    except Exception:
        return base
    if not isinstance(raw, dict):
        return base
    merged = {key: value for key, value in raw.items() if key in base}
    # A prefs file saved before MLE kept the model name under the old key.
    if not str(merged.get("mle_model") or "").strip():
        retired = raw.get("ollama_model")
        if str(retired or "").strip():
            merged["mle_model"] = str(retired).strip()
    # A file written only by the PowerShell Gatehouse has open_browser but no
    # window_mode; "don't open a browser" there meant "server only".
    if "window_mode" not in raw and "open_browser" in raw and not _as_bool(raw.get("open_browser")):
        merged["window_mode"] = "none"
    return normalize_prefs(merged)


def save_prefs(updates: dict[str, Any] | None) -> dict[str, Any]:
    current = load_prefs()
    if isinstance(updates, dict):
        for key, value in updates.items():
            if key in current:
                current[key] = value
    current = normalize_prefs(current)
    current["open_browser"] = current["window_mode"] != "none"
    # Keys this module does not know (written by another launcher) survive a save.
    extra: dict[str, Any] = {}
    try:
        raw = json.loads(prefs_path().read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            extra = {key: value for key, value in raw.items() if key not in current}
    except Exception:
        extra = {}
    prefs_path().parent.mkdir(parents=True, exist_ok=True)
    prefs_path().write_text(json.dumps({**extra, **current}, ensure_ascii=True, indent=2), encoding="utf-8")
    return current


def restart_keys_changed(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """The keys whose change only takes effect after a server restart."""
    before_n = normalize_prefs(before)
    after_n = normalize_prefs(after)
    llama_now = after_n["model_provider"] == "llama_cpp" or before_n["model_provider"] == "llama_cpp"
    changed: list[str] = []
    for key in sorted(RESTART_KEYS):
        if before_n.get(key) == after_n.get(key):
            continue
        if key in _LLAMA_ONLY_KEYS and not llama_now:
            continue
        if key == "model_provider" and "llama_cpp" not in {before_n[key], after_n[key]}:
            # mle <-> openai switches live; only starting or stopping the
            # managed llama.cpp server needs the launcher.
            continue
        changed.append(key)
    return changed


def prefs_to_env(prefs: dict[str, Any] | None = None) -> dict[str, str | None]:
    """Env var -> value for these prefs. None means the variable must be unset."""
    p = normalize_prefs(prefs or load_prefs())
    env: dict[str, str | None] = {
        "AI_RPG_LAUNCH_MODE": p["launch_mode"],
        "AI_RPG_APP_PORT": str(p["app_port"]),
        "AI_RPG_MODEL_PROVIDER": p["model_provider"],
        "MLE_MODEL": p["mle_model"],
        "AI_RPG_LLAMA_CPP_GPU_LAYERS": str(p["llama_cpp_gpu_layers"]),
        "AI_RPG_LLAMA_CPP_FLASH_ATTN": "True" if p["llama_cpp_flash_attn"] else "False",
        "AI_RPG_LLM_LOG_MODE": p["llm_log_mode"],
        "AI_RPG_LLM_STARTUP_TIMEOUT": str(p["llm_startup_timeout"]),
        "AI_RPG_DRAFT_MODE": p["draft_mode"],
        "AI_RPG_NARRATION_PIPELINE": "1" if p["narration_pipeline"] else "0",
        "AI_RPG_NARRATION_PIPELINE_CONSOLIDATE": "1" if p["narration_consolidate"] else "0",
        "AI_RPG_FAST_VERIFICATION": "1" if p["fast_verification"] else "0",
        "AI_RPG_DSL_SKIP_VERIFY": "1" if p["dsl_skip_verify"] else "0",
        "AI_RPG_GGUF_MODEL": p["gguf_model_path"] or None,
        "AI_RPG_API_BASE_URL": p["api_base_url"] or None,
        "AI_RPG_API_MODEL": p["api_model"] or None,
        "AI_RPG_API_PRESET": p["api_preset"] or None,
        "AI_RPG_MAX_RESPONSE_TOKENS": str(p["soft_response_tokens"]) if p["soft_response_tokens"] else None,
        "AI_RPG_RESPONSE_HARD_CAP_TOKENS": str(p["hard_response_tokens"]) if p["hard_response_tokens"] else None,
        "AI_RPG_NO_BROWSER": None if p["window_mode"] != "none" else "1",
    }
    context = explicit_pref_int(p["llama_cpp_context"])
    # auto: leave both unset so the server resolves the window per model.
    env["AI_RPG_CONTEXT_TOKENS"] = str(context) if context else None
    env["AI_RPG_LLAMA_CPP_CONTEXT"] = str(context) if context else None
    for gone in ("OLLAMA_MODEL", "OLLAMA_BASE_URL", "OLLAMA_THINK", "OLLAMA_CONTEXT_TOKENS"):
        env[gone] = None
    return env


def apply_env(env: dict[str, str | None], target: Any = None) -> None:
    target = os.environ if target is None else target
    for key, value in env.items():
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value


def apply_prefs_to_env(prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply prefs to this process's env (affects new model calls in this process)."""
    p = normalize_prefs(prefs or load_prefs())
    env = prefs_to_env(p)
    # The bind address and port belong to the process that is already
    # listening; rewriting them here would only make the env lie about it.
    for live in ("AI_RPG_LAUNCH_MODE", "AI_RPG_APP_PORT"):
        env.pop(live, None)
    apply_env(env)
    return p
